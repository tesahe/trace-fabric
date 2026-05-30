from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Literal

import instructor
from aiolimiter import AsyncLimiter
from google import genai
from pydantic import BaseModel, Field, ValidationError

from llm_contracts import (
    DEFAULT_PROVIDER,
    INPUT_PAYLOAD_VERSION,
    LeadEvalContext,
    TIER1_PROMPT_VERSION,
    TIER1_SCHEMA_VERSION,
)


logger = logging.getLogger(__name__)


class Tier1GateDecision(BaseModel):
    verdict: Literal["pass", "reject", "needs_review"] = Field(
        description="Machine verdict for the lead."
    )
    rejection_code: str | None = Field(
        default=None,
        description="Stable machine-readable rejection code when the verdict is reject.",
    )
    confidence: float = Field(ge=0.0, le=1.0)
    is_real_local_business: bool
    is_niche_match: bool
    business_type_guess: str = ""
    rationale_short: str = Field(
        description="A concise UI-safe rationale. Do not include chain-of-thought."
    )
    supporting_facts: list[str] = Field(
        default_factory=list,
        description="Short evidence bullets grounded in the provided input payload.",
    )


class Tier1StageRecord(BaseModel):
    stage: Literal["tier1"] = "tier1"
    status: str
    provider: str = DEFAULT_PROVIDER
    model: str
    prompt_version: str = TIER1_PROMPT_VERSION
    schema_version: str = TIER1_SCHEMA_VERSION
    input_payload_version: str = INPUT_PAYLOAD_VERSION
    latency_ms: int | None = None
    tokens: dict[str, int] | None = None
    provider_error: dict[str, Any] | None = None
    raw_validated_output: dict[str, Any] | None = None
    normalized_output: dict[str, Any]


def _failure_output(reason: str, rejection_code: str | None = None) -> Tier1GateDecision:
    return Tier1GateDecision(
        verdict="pass",
        rejection_code=rejection_code,
        confidence=0.0,
        is_real_local_business=True,
        is_niche_match=True,
        business_type_guess="unknown",
        rationale_short=reason,
        supporting_facts=[],
    )


def build_skip_record(*, model: str, reason: str) -> Tier1StageRecord:
    output = _failure_output(reason)
    return Tier1StageRecord(
        status="tier1_skipped",
        model=model,
        normalized_output=output.model_dump(),
    )


def should_run_tier1(context: LeadEvalContext, runtime_config: Any) -> tuple[bool, str | None]:
    if not runtime_config.llm_enabled:
        return False, "llm_pipeline_disabled"
    if not runtime_config.tier1_enabled:
        return False, "tier1_disabled"
    if not runtime_config.signals_v2_enabled:
        return False, "signals_v2_required"
    if not runtime_config.scoring_v2_enabled:
        return False, "scoring_v2_required"
    if context.pipeline_status != "qualified_deterministic":
        return False, "deterministic_path_not_qualified"
    if context.score_v2 is None:
        return False, "score_v2_missing"
    if context.score_v2 < runtime_config.tier1_min_score:
        return False, "score_v2_below_threshold"

    campaign = context.business.campaign_type.strip().lower()
    industry = context.business.target_industry.strip().lower()
    if runtime_config.tier1_supported_campaigns and campaign not in runtime_config.tier1_supported_campaigns:
        return False, "unsupported_campaign"
    if runtime_config.tier1_supported_industries and industry not in runtime_config.tier1_supported_industries:
        return False, "unsupported_industry"
    return True, None


class Tier1Gatekeeper:
    """
    Tier 1 Gemini gate. Consumes the normalized LeadEvalContext and returns
    a strict machine-first decision contract.
    """

    def __init__(self, model: str = "gemini-2.5-flash-lite"):
        self.internal_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.client = instructor.from_genai(
            self.internal_client,
            mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
        )
        self.model = model

    async def validate_business(self, context: LeadEvalContext) -> Tier1StageRecord:
        prompt = (
            "You are the Tier 1 gate for a B2B lead-evaluation pipeline. "
            "Use only the supplied JSON payload. Decide whether this lead is a real local business "
            "and whether it matches the target niche. Return only the structured response. "
            "Do not include hidden reasoning. Use supporting_facts as short, observable bullets."
        )

        started = time.perf_counter()
        try:
            loop = asyncio.get_running_loop()
            decision = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": context.model_dump_json(indent=2)},
                    ],
                    response_model=Tier1GateDecision,
                ),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            status = "tier1_rejected" if decision.verdict == "reject" else "tier1_passed"
            return Tier1StageRecord(
                status=status,
                model=self.model,
                latency_ms=latency_ms,
                raw_validated_output=decision.model_dump(),
                normalized_output=decision.model_dump(),
            )
        except ValidationError as exc:
            logger.error("Tier 1 schema validation failed: %s", exc)
            latency_ms = int((time.perf_counter() - started) * 1000)
            output = _failure_output("Tier 1 schema validation failed (fallback pass)")
            return Tier1StageRecord(
                status="tier1_failed_fallback",
                model=self.model,
                latency_ms=latency_ms,
                provider_error={"type": "schema_validation", "message": str(exc)},
                normalized_output=output.model_dump(),
            )
        except Exception as exc:
            logger.error("Tier 1 validation failed: %s", exc)
            latency_ms = int((time.perf_counter() - started) * 1000)
            output = _failure_output("Tier 1 provider/runtime failure (fallback pass)")
            return Tier1StageRecord(
                status="tier1_failed_fallback",
                model=self.model,
                latency_ms=latency_ms,
                provider_error={"type": "provider_runtime", "message": str(exc)},
                normalized_output=output.model_dump(),
            )


tier1_semaphore = asyncio.Semaphore(10)
tier1_rate_limiter = AsyncLimiter(max_rate=500, time_period=60)


async def protected_tier1_call(
    gatekeeper: Tier1Gatekeeper,
    context: LeadEvalContext,
) -> Tier1StageRecord:
    async with tier1_semaphore:
        async with tier1_rate_limiter:
            return await gatekeeper.validate_business(context)
