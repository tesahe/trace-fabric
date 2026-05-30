from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import instructor
from aiolimiter import AsyncLimiter
from google import genai
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from database import AsyncSessionLocal, ScoredLeadModel
from llm_contracts import (
    DEFAULT_PROVIDER,
    INPUT_PAYLOAD_VERSION,
    LeadEvalContext,
    TIER2_PROMPT_VERSION,
    TIER2_SCHEMA_VERSION,
)
from schemas import Tier2EnrichmentOutput


logger = logging.getLogger(__name__)


class LLMRatelimitException(Exception):
    pass


class Tier2StageRecord(BaseModel):
    stage: str = "tier2"
    status: str
    provider: str = DEFAULT_PROVIDER
    model: str
    prompt_version: str = TIER2_PROMPT_VERSION
    schema_version: str = TIER2_SCHEMA_VERSION
    input_payload_version: str = INPUT_PAYLOAD_VERSION
    latency_ms: int | None = None
    tokens: dict[str, int] | None = None
    provider_error: dict[str, Any] | None = None
    raw_validated_output: dict[str, Any] | None = None
    normalized_output: dict[str, Any] | None = None


def should_run_tier2(context: LeadEvalContext, runtime_config: Any) -> tuple[bool, str | None]:
    if not runtime_config.llm_enabled:
        return False, "llm_pipeline_disabled"
    if not runtime_config.tier2_enabled:
        return False, "tier2_disabled"

    campaign = context.business.campaign_type.strip().lower()
    industry = context.business.target_industry.strip().lower()
    if runtime_config.tier2_supported_campaigns and campaign not in runtime_config.tier2_supported_campaigns:
        return False, "unsupported_campaign"
    if runtime_config.tier2_supported_industries and industry not in runtime_config.tier2_supported_industries:
        return False, "unsupported_industry"
    return True, None


def apply_tier2_enrichment_to_record(
    lead_record: ScoredLeadModel,
    stage_record: Tier2StageRecord,
) -> None:
    if stage_record.normalized_output is None:
        lead_record.pipeline_status = stage_record.status
        lead_record.tier2_result = stage_record.model_dump()
        return

    payload = Tier2EnrichmentOutput.model_validate(stage_record.normalized_output)
    profile = payload.business_profile
    gaps = payload.service_gaps

    if profile.business_name and not lead_record.company_name:
        lead_record.company_name = profile.business_name
    if profile.category and not lead_record.category:
        lead_record.category = profile.category
    if profile.phone_number and not lead_record.phone_number:
        lead_record.phone_number = profile.phone_number
    if profile.address and not lead_record.address:
        lead_record.address = profile.address

    lead_record.has_booking_widget = gaps.has_online_booking
    lead_record.is_mobile_optimized = gaps.is_mobile_optimized
    lead_record.has_clear_contact_info = gaps.has_clear_contact_info
    lead_record.identified_service_gaps = gaps.outdated_indicators
    lead_record.missing_critical_features = gaps.missing_critical_features
    lead_record.overall_digital_health = payload.operator_summary
    lead_record.pipeline_status = "tier2_complete"
    lead_record.tier2_result = stage_record.model_dump()

    llm_output = dict(lead_record.llm_output or {})
    llm_output["tier2"] = {
        "status": stage_record.status,
        "confidence": payload.confidence,
        "summary": payload.operator_summary,
    }
    lead_record.llm_output = llm_output

    full_payload = dict(lead_record.full_llm_payload or {})
    full_payload["tier2"] = stage_record.model_dump()
    lead_record.full_llm_payload = full_payload


class Tier2Orchestrator:
    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        rpm_limit: int = 500,
        max_concurent: int = 15,
        queue_size: int = 2000,
    ):
        self.raw_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.ai_client = instructor.from_genai(
            self.raw_client,
            mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
        )
        self.model = model
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.rate_limiter = AsyncLimiter(rpm_limit, 60.0)
        self.semaphore = asyncio.Semaphore(max_concurent)
        self.workers: list[asyncio.Task] = []

    async def enqueue_lead(self, lead_data: dict[str, Any]) -> None:
        await self.queue.put(lead_data)
        logging.debug(
            "Queued lead for Tier 2. Buffer utilization: %s / %s",
            self.queue.qsize(),
            self.queue.maxsize,
        )

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(LLMRatelimitException),
    )
    async def _execute_llm(self, context: LeadEvalContext) -> Tier2StageRecord:
        async with self.rate_limiter:
            async with self.semaphore:
                started = time.perf_counter()
                try:
                    extraction: Tier2EnrichmentOutput = await asyncio.to_thread(
                        self.ai_client.chat.completions.create,
                        model=self.model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are the Tier 2 enrichment stage in a lead evaluation pipeline. "
                                    "Use only the provided JSON payload. Return structured business profile, "
                                    "service gaps, niche attributes, and a short operator summary. "
                                    "Do not change qualification state and do not return hidden reasoning."
                                ),
                            },
                            {"role": "user", "content": context.model_dump_json(indent=2)},
                        ],
                        response_model=Tier2EnrichmentOutput,
                    )
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    return Tier2StageRecord(
                        status="tier2_complete",
                        model=self.model,
                        latency_ms=latency_ms,
                        raw_validated_output=extraction.model_dump(),
                        normalized_output=extraction.model_dump(),
                    )
                except ValidationError as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    logger.error("Tier 2 schema validation failed: %s", exc)
                    return Tier2StageRecord(
                        status="tier2_failed",
                        model=self.model,
                        latency_ms=latency_ms,
                        provider_error={"type": "schema_validation", "message": str(exc)},
                    )
                except Exception as exc:
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    logger.error("Tier 2 execution failed: %s", exc)
                    return Tier2StageRecord(
                        status="tier2_failed",
                        model=self.model,
                        latency_ms=latency_ms,
                        provider_error={"type": "provider_runtime", "message": str(exc)},
                    )

    async def _worker_loop(self, worker_id: int):
        while True:
            lead_data = await self.queue.get()
            lead_id = lead_data.get("id")
            context_payload = lead_data.get("context") or {}

            try:
                context = LeadEvalContext.model_validate(context_payload)

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        stmt = select(ScoredLeadModel).where(ScoredLeadModel.id == lead_id)
                        db_result = await session.execute(stmt)
                        lead_record = db_result.scalar_one_or_none()
                        if lead_record is not None:
                            lead_record.pipeline_status = "tier2_running"

                stage_record = await self._execute_llm(context)

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        stmt = select(ScoredLeadModel).where(ScoredLeadModel.id == lead_id)
                        db_result = await session.execute(stmt)
                        lead_record = db_result.scalar_one_or_none()

                        if not lead_record:
                            logger.error(
                                "Worker %s: Lead %s not found in DB during Tier 2 persistence.",
                                worker_id,
                                lead_id,
                            )
                            continue

                        if stage_record.status == "tier2_complete":
                            apply_tier2_enrichment_to_record(lead_record, stage_record)
                        else:
                            lead_record.pipeline_status = "tier2_failed"
                            lead_record.tier2_result = stage_record.model_dump()
                            llm_output = dict(lead_record.llm_output or {})
                            llm_output["tier2"] = {
                                "status": stage_record.status,
                                "confidence": None,
                                "summary": None,
                            }
                            lead_record.llm_output = llm_output
                            full_payload = dict(lead_record.full_llm_payload or {})
                            full_payload["tier2"] = stage_record.model_dump()
                            lead_record.full_llm_payload = full_payload

                logger.info("[Tier 2] Saved results for lead ID %s | status=%s", lead_id, stage_record.status)
            except Exception as exc:
                logger.error("Worker %s failed on lead %s. Error: %s", worker_id, lead_id, exc)
            finally:
                self.queue.task_done()

    async def start(self, worker_count: int = 15):
        for i in range(worker_count):
            task = asyncio.create_task(self._worker_loop(worker_id=i))
            self.workers.append(task)

        logger.info("Started %d Tier 2 background workers.", worker_count)
