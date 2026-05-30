from __future__ import annotations

import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from campaigns import load_runtime_config
from database import AsyncSessionLocal, ScoredLeadModel
from gatekeeper import HeuristicScanner, get_ruleset_for_campaign
from lead_evaluation import build_lead_evaluation
from llm_contracts import build_lead_eval_context
from tier1_router import (
    Tier1Gatekeeper,
    build_skip_record,
    protected_tier1_call,
    should_run_tier1,
)
from tier2_orchestrator import Tier2Orchestrator, should_run_tier2


logger = logging.getLogger(__name__)

runtime_config = load_runtime_config()
tier1 = (
    Tier1Gatekeeper(model=runtime_config.tier1_model)
    if runtime_config.llm_enabled and runtime_config.tier1_enabled
    else None
)
tier2 = (
    Tier2Orchestrator(
        model=runtime_config.tier2_model,
        rpm_limit=500,
        max_concurent=15,
        queue_size=2000,
    )
    if runtime_config.llm_enabled and runtime_config.tier2_enabled
    else None
)

if runtime_config.signals_v2_enabled:
    from signals.matcher import Matcher  # noqa: E402

    _MATCHER: "Matcher | None" = Matcher()
    print(f"[Tier 0] signals_v2 ENABLED — matcher loaded ({len(_MATCHER._techs_list)} techs)")
else:
    _MATCHER = None

ml_executor = ThreadPoolExecutor(max_workers=4)


class LeadClassifier:
    def __init__(self):
        print("XGBoost Model Stub Initialized into memory.")

    def predict(self, raw_html: str) -> float:
        import time

        time.sleep(0.1)
        return round(random.uniform(0.0, 1.0), 4)


classifier = LeadClassifier()


def parse_json_object(raw_value: str) -> dict:
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def build_lead_payload(lead) -> dict[str, Any]:
    return {
        "id": lead.id,
        "run_id": lead.run_id,
        "source_url": lead.source_url,
        "initial_url": lead.initial_url,
        "final_url": lead.final_url,
        "timestamp": lead.timestamp,
        "discovery_source": lead.discovery_source,
        "target_industry": lead.target_industry,
        "target_location": lead.target_location,
        "crawl_allowed": lead.crawl_allowed,
        "crawl_disallowed_reason": lead.crawl_disallowed_reason,
        "is_no_website_opportunity": lead.is_no_website_opportunity,
        "provider_fsq_id": lead.provider_fsq_id,
        "company_name": lead.company_name,
        "category": lead.category,
        "phone_number": lead.phone_number,
        "address": lead.address,
        "provider_provenance": parse_json_object(lead.provider_provenance_json),
        "website_provenance": parse_json_object(lead.website_provenance_json),
        "location_confidence": lead.location_confidence,
        "category_confidence": lead.category_confidence,
        "http_status": lead.http_status,
        "is_https": lead.is_https,
        "redirect_count": lead.redirect_count,
        "fetch_duration_ms": lead.fetch_duration_ms,
        "response_size_bytes": lead.response_size_bytes,
        "content_type": lead.content_type,
        "page_title": lead.page_title,
        "manifest_url": lead.manifest_url,
        "raw_html": lead.raw_html,
        "text_content": lead.text_content,
        "response_headers": [{"key": h.key, "value": h.value} for h in lead.response_headers],
        "anchor_hrefs": [
            {"url": x.url, "is_internal": x.is_internal, "label": x.label}
            for x in lead.anchor_hrefs
        ],
        "script_srcs": [
            {"url": x.url, "is_internal": x.is_internal, "label": x.label}
            for x in lead.script_srcs
        ],
        "stylesheet_hrefs": [
            {"url": x.url, "is_internal": x.is_internal, "label": x.label}
            for x in lead.stylesheet_hrefs
        ],
        "robots_txt": {
            "path": lead.robots_txt.path,
            "http_status": lead.robots_txt.http_status,
            "exists": lead.robots_txt.exists,
            "content_type": lead.robots_txt.content_type,
            "body": lead.robots_txt.body,
        },
        "sitemap_xml": {
            "path": lead.sitemap_xml.path,
            "http_status": lead.sitemap_xml.http_status,
            "exists": lead.sitemap_xml.exists,
            "content_type": lead.sitemap_xml.content_type,
            "body": lead.sitemap_xml.body,
        },
        "word_count": lead.word_count,
        "has_viewport": lead.has_viewport,
        "has_form": lead.has_form,
        "has_tel_link": lead.has_tel_link,
        "has_mailto_link": lead.has_mailto_link,
        "is_parked_domain": lead.is_parked_domain,
        "outbound_domain_count": lead.outbound_domain_count,
        "schema_org_business_type": lead.schema_org_business_type,
        "email_address": lead.email_address,
        "meta_description": lead.meta_description,
        "social_linkedin": lead.social_linkedin,
        "social_facebook": lead.social_facebook,
        "social_instagram": lead.social_instagram,
        "copyright_year": lead.copyright_year,
        "has_booking_signal": lead.has_booking_signal,
        "has_cta_signal": lead.has_cta_signal,
        "has_hours_signal": lead.has_hours_signal,
        "has_reviews_signal": lead.has_reviews_signal,
        "has_contact_page": lead.has_contact_page,

    }


def build_record_kwargs(lead, lead_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": lead.id,
        "timestamp": lead.timestamp,
        "run_id": lead.run_id,
        "source_url": lead.source_url,
        "initial_url": lead.initial_url,
        "final_url": lead.final_url,
        "discovery_source": lead.discovery_source,
        "target_industry": lead.target_industry,
        "target_location": lead.target_location,
        "crawl_allowed": lead.crawl_allowed,
        "crawl_disallowed_reason": lead.crawl_disallowed_reason,
        "is_no_website_opportunity": lead.is_no_website_opportunity,
        "provider_fsq_id": lead.provider_fsq_id,
        "provider_provenance": parse_json_object(lead.provider_provenance_json),
        "website_provenance": parse_json_object(lead.website_provenance_json),
        "location_confidence": lead.location_confidence,
        "category_confidence": lead.category_confidence,
        "company_name": lead.company_name,
        "category": lead.category,
        "phone_number": lead.phone_number,
        "address": lead.address,
        "http_status": lead.http_status,
        "is_https": lead.is_https,
        "redirect_count": lead.redirect_count,
        "fetch_duration_ms": lead.fetch_duration_ms,
        "response_size_bytes": lead.response_size_bytes,
        "content_type": lead.content_type,
        "page_title": lead.page_title,
        "manifest_url": lead.manifest_url,
        "raw_html": lead.raw_html,
        "text_content": lead.text_content,
        "response_headers": lead_payload["response_headers"],
        "anchor_hrefs": lead_payload["anchor_hrefs"],
        "script_srcs": lead_payload["script_srcs"],
        "stylesheet_hrefs": lead_payload["stylesheet_hrefs"],
        "robots_txt": lead_payload["robots_txt"],
        "sitemap_xml": lead_payload["sitemap_xml"],
        "word_count": lead.word_count,
        "has_viewport": lead.has_viewport,
        "has_form": lead.has_form,
        "has_tel_link": lead.has_tel_link,
        "has_mailto_link": lead.has_mailto_link,
        "is_parked_domain": lead.is_parked_domain,
        "outbound_domain_count": lead.outbound_domain_count,
        "schema_org_business_type": lead.schema_org_business_type,
        "email_address": lead.email_address,
        "meta_description": lead.meta_description,
        "social_linkedin": lead.social_linkedin,
        "social_facebook": lead.social_facebook,
        "social_instagram": lead.social_instagram,
        "copyright_year": lead.copyright_year,
        "has_booking_signal": lead.has_booking_signal,
        "has_cta_signal": lead.has_cta_signal,
        "has_hours_signal": lead.has_hours_signal,
        "has_reviews_signal": lead.has_reviews_signal,
        "has_contact_page": lead.has_contact_page,

    }


def build_llm_summary(
    *,
    tier1_record: dict[str, Any] | None = None,
    tier2_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    if tier1_record:
        normalized = tier1_record.get("normalized_output") or {}
        summary["tier1"] = {
            "status": tier1_record.get("status"),
            "confidence": normalized.get("confidence"),
            "verdict": normalized.get("verdict"),
            "rejection_code": normalized.get("rejection_code"),
            "summary": normalized.get("rationale_short"),
        }
    if tier2_record:
        normalized = tier2_record.get("normalized_output") or {}
        summary["tier2"] = {
            "status": tier2_record.get("status"),
            "confidence": normalized.get("confidence"),
            "summary": normalized.get("operator_summary"),
        }
    return summary


def build_full_llm_payload(
    *,
    lead_eval_context: dict[str, Any] | None = None,
    tier1_record: dict[str, Any] | None = None,
    tier2_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if lead_eval_context is not None:
        payload["lead_eval_context"] = lead_eval_context
    if tier1_record is not None:
        payload["tier1"] = tier1_record
    if tier2_record is not None:
        payload["tier2"] = tier2_record
    return payload


async def persist_record(record: ScoredLeadModel) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(record)


async def process_incoming_lead(lead) -> None:
    print(f"[Ingest] Lead ID: {lead.id} | Source: {lead.source_url}")

    if lead.crawl_allowed is False:
        print(
            f"[Tier 0] Skipped heuristic scan for Lead ID: {lead.id} "
            f"(Disallowed by Compliance: {lead.crawl_disallowed_reason})"
        )
        passed = False
        status = "rejected_compliance"
        heuristic_flags = {"reason": lead.crawl_disallowed_reason}
        scanner = None
    else:
        print(f"[Tier 0] Starting heuristic scan for Lead ID: {lead.id}")
        scanner = HeuristicScanner(
            lead,
            get_ruleset_for_campaign(runtime_config.campaign_type),
        )
        passed, heuristic_flags, status = scanner.run_all_checks()
        print(f"[Tier 0] Completed for Lead ID: {lead.id} | passed={passed} | status={status}")

    lead_payload = build_lead_payload(lead)
    record_kwargs = build_record_kwargs(lead, lead_payload)

    if not passed:
        print(f"[Tier 0] Rejected Lead {lead.id} | Reason: {status}")
        await persist_record(
            ScoredLeadModel(
                **record_kwargs,
                score=0.0,
                pipeline_status=status,
                heuristic_flags=heuristic_flags,
            )
        )
        return

    evaluation = build_lead_evaluation(
        lead_payload,
        campaign_type=runtime_config.campaign_type,
        target_industry=lead.target_industry,
        heuristic_flags=heuristic_flags,
        matcher=_MATCHER,
    )
    context = build_lead_eval_context(
        lead_payload=lead_payload,
        evaluation=evaluation,
        campaign_type=runtime_config.campaign_type,
        target_industry=lead.target_industry,
    )

    tier1_record = None
    tier2_record = None
    pipeline_status = evaluation["pipeline_status"]
    is_qualified_lead = evaluation["is_qualified_lead"]
    rejection_reason = evaluation["rejection_reason"]

    if runtime_config.llm_enabled and tier1 is not None:
        should_run, skip_reason = should_run_tier1(context, runtime_config)
        if should_run:
            print(f"[Tier 1] Starting LLM gate for Lead ID: {lead.id}")
            tier1_stage = await protected_tier1_call(tier1, context)
        else:
            tier1_stage = build_skip_record(model=runtime_config.tier1_model, reason=skip_reason or "tier1_skipped")

        tier1_record = tier1_stage.model_dump()
        evaluation.setdefault("heuristic_flags", {})["tier1"] = tier1_record
        normalized = tier1_record.get("normalized_output") or {}
        verdict = normalized.get("verdict")

        if tier1_stage.status == "tier1_rejected" or verdict == "reject":
            pipeline_status = "tier1_rejected"
            is_qualified_lead = False
            rejection_reason = normalized.get("rejection_code") or normalized.get("rationale_short") or "tier1_rejected"

            await persist_record(
                ScoredLeadModel(
                    **record_kwargs,
                    score=evaluation["score"],
                    pipeline_status=pipeline_status,
                    heuristic_flags=evaluation["heuristic_flags"],
                    deterministic_evidence=evaluation["deterministic_evidence"],
                    is_qualified_lead=is_qualified_lead,
                    has_booking_widget=evaluation["has_booking_widget"],
                    is_mobile_optimized=evaluation["is_mobile_optimized"],
                    has_clear_contact_info=evaluation["has_clear_contact_info"],
                    overall_digital_health=evaluation["overall_digital_health"],
                    rejection_reason=rejection_reason,
                    identified_service_gaps=evaluation["identified_service_gaps"],
                    missing_critical_features=evaluation["missing_critical_features"],
                    tier1_result=tier1_record,
                    tier2_result={},
                    llm_output=build_llm_summary(tier1_record=tier1_record),
                    full_llm_payload=build_full_llm_payload(
                        lead_eval_context=context.model_dump(),
                        tier1_record=tier1_record,
                    ),
                )
            )
            return

        tier2_allowed, tier2_skip_reason = should_run_tier2(context, runtime_config)
        if tier2 is not None and tier2_allowed:
            pipeline_status = "tier2_queued"
        elif tier1_stage.status == "tier1_failed_fallback":
            pipeline_status = "tier1_failed_fallback"
        elif tier1_stage.status == "tier1_passed":
            pipeline_status = "tier1_passed"
        else:
            pipeline_status = evaluation["pipeline_status"]

        if tier2_skip_reason is not None:
            tier2_record = {
                "stage": "tier2",
                "status": "tier2_skipped",
                "provider": "gemini",
                "model": runtime_config.tier2_model,
                "prompt_version": "tier2_enrichment.v1",
                "schema_version": "tier2_enrichment_output.v1",
                "input_payload_version": context.input_payload_version,
                "latency_ms": None,
                "tokens": None,
                "provider_error": {"type": "skip", "message": tier2_skip_reason},
                "raw_validated_output": None,
                "normalized_output": None,
            }
            evaluation["heuristic_flags"]["tier2"] = tier2_record

    new_record = ScoredLeadModel(
        **record_kwargs,
        score=evaluation["score"],
        pipeline_status=pipeline_status,
        heuristic_flags=evaluation["heuristic_flags"],
        deterministic_evidence=evaluation["deterministic_evidence"],
        is_qualified_lead=is_qualified_lead,
        has_booking_widget=evaluation["has_booking_widget"],
        is_mobile_optimized=evaluation["is_mobile_optimized"],
        has_clear_contact_info=evaluation["has_clear_contact_info"],
        overall_digital_health=evaluation["overall_digital_health"],
        rejection_reason=rejection_reason,
        identified_service_gaps=evaluation["identified_service_gaps"],
        missing_critical_features=evaluation["missing_critical_features"],
        tier1_result=tier1_record or {},
        tier2_result=tier2_record or {},
        llm_output=build_llm_summary(tier1_record=tier1_record, tier2_record=tier2_record),
        full_llm_payload=build_full_llm_payload(
            lead_eval_context=context.model_dump(),
            tier1_record=tier1_record,
            tier2_record=tier2_record,
        ),
    )
    await persist_record(new_record)
    print(f"[Persist] Lead ID: {lead.id} -> DB")

    if pipeline_status == "tier2_queued" and tier2 is not None:
        await tier2.enqueue_lead(
            {
                "id": lead.id,
                "context": context.model_dump(),
            }
        )
