from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import lead_processor
from campaigns import RuntimeConfig
from llm_contracts import build_lead_eval_context
from schemas import BusinessProfile, ServiceGaps, Tier2EnrichmentOutput
from tier1_router import Tier1StageRecord, should_run_tier1
from tier2_orchestrator import Tier2StageRecord, apply_tier2_enrichment_to_record


class _AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, added):
        self.added = added

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return _AsyncContext()

    def add(self, record):
        self.added.append(record)


def make_async_session_factory(added):
    def factory():
        return FakeSession(added)

    return factory


def make_proto_lead():
    words = " ".join(["local"] * 220)
    html = f"<html><body><p>{words}</p></body></html>"
    empty_doc = SimpleNamespace(path="", http_status=0, exists=False, content_type="", body="")
    return SimpleNamespace(
        id="lead-1",
        run_id="run-1",
        source_url="https://example.com",
        initial_url="https://example.com",
        final_url="https://example.com",
        timestamp="2026-05-01T10:00:00Z",
        discovery_source="brave",
        target_industry="plumbing",
        target_location="San Francisco, CA",
        crawl_allowed=True,
        crawl_disallowed_reason="",
        is_no_website_opportunity=False,
        provider_fsq_id="",
        company_name="Example Plumbing",
        category="Plumbing",
        phone_number="503-555-1111",
        address="123 Main St",
        provider_provenance_json="{}",
        website_provenance_json="{}",
        location_confidence=0.8,
        category_confidence=0.7,
        http_status=200,
        is_https=True,
        redirect_count=0,
        fetch_duration_ms=200,
        response_size_bytes=1024,
        content_type="text/html",
        page_title="Example Plumbing",
        manifest_url="",
        raw_html=html,
        text_content=words,
        response_headers=[],
        anchor_hrefs=[],
        script_srcs=[],
        stylesheet_hrefs=[],
        robots_txt=empty_doc,
        sitemap_xml=empty_doc,
        word_count=220,
        has_viewport=False,
        has_form=False,
        has_tel_link=False,
        has_mailto_link=False,
        is_parked_domain=False,
        outbound_domain_count=0,
        schema_org_business_type="",
        email_address="",
        meta_description="",
        social_linkedin="",
        social_facebook="",
        social_instagram="",
        copyright_year=0,
        has_booking_signal=False,
        has_cta_signal=False,
        has_hours_signal=False,
        has_reviews_signal=False,
        has_contact_page=False,

    )


def make_evaluation():
    return {
        "pipeline_status": "qualified_deterministic",
        "score": 0.7,
        "is_qualified_lead": True,
        "has_booking_widget": False,
        "is_mobile_optimized": False,
        "has_clear_contact_info": True,
        "overall_digital_health": "Real local business with actionable deterministic gaps.",
        "rejection_reason": None,
        "identified_service_gaps": ["missing_mobile_viewport"],
        "missing_critical_features": ["privacy_policy"],
        "heuristic_flags": {
            "campaign": "website_modernization",
            "score_v2": 0.84,
            "score_v2_breakdown": [{"source": "baseline", "weight": 0.3}],
            "technologies": [{"name": "WordPress", "pack": "wappalyzer", "confidence": 100}],
        },
        "deterministic_evidence": {"has_contact_page": True},
    }


def make_runtime_config(**overrides) -> RuntimeConfig:
    base = RuntimeConfig(
        campaign_type="website_modernization",
        llm_enabled=True,
        scoring_v2_enabled=True,
        signals_v2_enabled=True,
        tier1_enabled=True,
        tier2_enabled=True,
        tier1_min_score=0.55,
        tier1_model="gemini-2.5-flash-lite",
        tier2_model="gemini-2.5-flash",
        tier1_supported_campaigns=(),
        tier1_supported_industries=(),
        tier2_supported_campaigns=(),
        tier2_supported_industries=(),
    )
    return replace(base, **overrides)


def test_lead_eval_context_includes_score_v2_and_technologies():
    lead = {
        "id": "lead-1",
        "run_id": "run-1",
        "source_url": "https://example.com",
        "initial_url": "https://example.com",
        "final_url": "https://example.com",
        "timestamp": "2026-05-01T10:00:00Z",
        "target_location": "San Francisco, CA",
        "discovery_source": "brave",
        "company_name": "Example Plumbing",
        "category": "Plumbing",
        "phone_number": "503-555-1111",
        "address": "123 Main St",
        "provider_provenance": {},
        "website_provenance": {},
        "robots_txt": {},
        "sitemap_xml": {},
        "response_headers": [],
        "anchor_hrefs": [],
        "text_content": "a" * 5000,
        "raw_html": "<html>" + ("b" * 20000) + "</html>",
        "page_title": "Example Plumbing",
    }
    evaluation = make_evaluation()

    context = build_lead_eval_context(
        lead_payload=lead,
        evaluation=evaluation,
        campaign_type="website_modernization",
        target_industry="plumbing",
    )

    assert context.score_v2 == 0.84
    assert context.technologies[0]["name"] == "WordPress"
    assert len(context.snippets.text_excerpt) == 4000
    assert len(context.snippets.html_excerpt) == 12000


def test_tier1_is_skipped_when_score_v2_is_below_threshold():
    evaluation = make_evaluation()
    evaluation["heuristic_flags"]["score_v2"] = 0.2
    context = build_lead_eval_context(
        lead_payload={
            "id": "lead-1",
            "run_id": "run-1",
            "source_url": "https://example.com",
            "initial_url": "https://example.com",
            "final_url": "https://example.com",
            "timestamp": "",
            "target_location": "",
            "discovery_source": "",
            "company_name": "",
            "category": "",
            "phone_number": "",
            "address": "",
            "provider_provenance": {},
            "website_provenance": {},
            "robots_txt": {},
            "sitemap_xml": {},
            "response_headers": [],
            "anchor_hrefs": [],
            "text_content": "text",
            "raw_html": "<html></html>",
            "page_title": "",
        },
        evaluation=evaluation,
        campaign_type="website_modernization",
        target_industry="plumbing",
    )

    should_run, reason = should_run_tier1(context, make_runtime_config())
    assert should_run is False
    assert reason == "score_v2_below_threshold"


@pytest.mark.anyio
async def test_tier1_reject_stops_tier2_enqueue(monkeypatch):
    added = []
    enqueued = []
    lead = make_proto_lead()
    evaluation = make_evaluation()

    async def fake_tier1_call(_gatekeeper, _context):
        return Tier1StageRecord(
            status="tier1_rejected",
            model="gemini-2.5-flash-lite",
            normalized_output={
                "verdict": "reject",
                "rejection_code": "not_local_business",
                "confidence": 0.92,
                "is_real_local_business": False,
                "is_niche_match": False,
                "business_type_guess": "directory",
                "rationale_short": "Appears to be a directory, not an operating local business.",
                "supporting_facts": ["Directory-like wording"],
            },
            raw_validated_output={
                "verdict": "reject",
                "rejection_code": "not_local_business",
                "confidence": 0.92,
                "is_real_local_business": False,
                "is_niche_match": False,
                "business_type_guess": "directory",
                "rationale_short": "Appears to be a directory, not an operating local business.",
                "supporting_facts": ["Directory-like wording"],
            },
        )

    class FakeTier2:
        async def enqueue_lead(self, payload):
            enqueued.append(payload)

    monkeypatch.setattr(lead_processor, "AsyncSessionLocal", make_async_session_factory(added))
    monkeypatch.setattr(lead_processor, "runtime_config", make_runtime_config())
    monkeypatch.setattr(lead_processor, "build_lead_evaluation", lambda *args, **kwargs: evaluation)
    monkeypatch.setattr(lead_processor, "protected_tier1_call", fake_tier1_call)
    monkeypatch.setattr(lead_processor, "tier1", object())
    monkeypatch.setattr(lead_processor, "tier2", FakeTier2())

    await lead_processor.process_incoming_lead(lead)

    assert len(added) == 1
    saved = added[0]
    assert saved.pipeline_status == "tier1_rejected"
    assert saved.rejection_reason == "not_local_business"
    assert saved.tier1_result["schema_version"] == "tier1_gate_output.v1"
    assert enqueued == []


@pytest.mark.anyio
async def test_tier1_pass_enqueues_tier2(monkeypatch):
    added = []
    enqueued = []
    lead = make_proto_lead()
    evaluation = make_evaluation()

    async def fake_tier1_call(_gatekeeper, _context):
        return Tier1StageRecord(
            status="tier1_passed",
            model="gemini-2.5-flash-lite",
            normalized_output={
                "verdict": "pass",
                "rejection_code": None,
                "confidence": 0.88,
                "is_real_local_business": True,
                "is_niche_match": True,
                "business_type_guess": "plumber",
                "rationale_short": "Real local plumbing business with strong niche fit.",
                "supporting_facts": ["Business phone present", "Niche-aligned content"],
            },
            raw_validated_output={
                "verdict": "pass",
                "rejection_code": None,
                "confidence": 0.88,
                "is_real_local_business": True,
                "is_niche_match": True,
                "business_type_guess": "plumber",
                "rationale_short": "Real local plumbing business with strong niche fit.",
                "supporting_facts": ["Business phone present", "Niche-aligned content"],
            },
        )

    class FakeTier2:
        async def enqueue_lead(self, payload):
            enqueued.append(payload)

    monkeypatch.setattr(lead_processor, "AsyncSessionLocal", make_async_session_factory(added))
    monkeypatch.setattr(lead_processor, "runtime_config", make_runtime_config())
    monkeypatch.setattr(lead_processor, "build_lead_evaluation", lambda *args, **kwargs: evaluation)
    monkeypatch.setattr(lead_processor, "protected_tier1_call", fake_tier1_call)
    monkeypatch.setattr(lead_processor, "tier1", object())
    monkeypatch.setattr(lead_processor, "tier2", FakeTier2())

    await lead_processor.process_incoming_lead(lead)

    assert len(added) == 1
    saved = added[0]
    assert saved.pipeline_status == "tier2_queued"
    assert saved.tier1_result["prompt_version"] == "tier1_gate.v1"
    assert enqueued and enqueued[0]["context"]["input_payload_version"] == "lead_eval_context.v1"


@pytest.mark.anyio
async def test_tier1_failed_fallback_is_persisted_without_losing_pipeline(monkeypatch):
    added = []
    enqueued = []
    lead = make_proto_lead()
    evaluation = make_evaluation()

    async def fake_tier1_call(_gatekeeper, _context):
        return Tier1StageRecord(
            status="tier1_failed_fallback",
            model="gemini-2.5-flash-lite",
            provider_error={"type": "provider_runtime", "message": "boom"},
            normalized_output={
                "verdict": "pass",
                "rejection_code": None,
                "confidence": 0.0,
                "is_real_local_business": True,
                "is_niche_match": True,
                "business_type_guess": "unknown",
                "rationale_short": "Tier 1 provider/runtime failure (fallback pass)",
                "supporting_facts": [],
            },
        )

    class FakeTier2:
        async def enqueue_lead(self, payload):
            enqueued.append(payload)

    monkeypatch.setattr(lead_processor, "AsyncSessionLocal", make_async_session_factory(added))
    monkeypatch.setattr(lead_processor, "runtime_config", make_runtime_config())
    monkeypatch.setattr(lead_processor, "build_lead_evaluation", lambda *args, **kwargs: evaluation)
    monkeypatch.setattr(lead_processor, "protected_tier1_call", fake_tier1_call)
    monkeypatch.setattr(lead_processor, "tier1", object())
    monkeypatch.setattr(lead_processor, "tier2", FakeTier2())

    await lead_processor.process_incoming_lead(lead)

    saved = added[0]
    assert saved.tier1_result["status"] == "tier1_failed_fallback"
    assert saved.pipeline_status == "tier2_queued"
    assert len(enqueued) == 1


def test_tier2_success_enriches_without_changing_qualification():
    lead_record = lead_processor.ScoredLeadModel(
        id="lead-1",
        source_url="https://example.com",
        pipeline_status="tier2_running",
        is_qualified_lead=True,
    )
    stage_record = Tier2StageRecord(
        status="tier2_complete",
        model="gemini-2.5-flash",
        normalized_output=Tier2EnrichmentOutput(
            business_profile=BusinessProfile(
                business_name="Example Plumbing",
                category="Plumbing",
                phone_number="503-555-1111",
                address="123 Main St",
            ),
            service_gaps=ServiceGaps(
                has_online_booking=False,
                is_mobile_optimized=False,
                has_clear_contact_info=True,
                outdated_indicators=["stale_copyright_2021"],
                missing_critical_features=["privacy_policy"],
            ),
            niche_attributes={"dispatch_software": "unknown"},
            operator_summary="Local plumbing business with modernization opportunities.",
            confidence=0.81,
        ).model_dump(),
        raw_validated_output={},
    )

    apply_tier2_enrichment_to_record(lead_record, stage_record)

    assert lead_record.is_qualified_lead is True
    assert lead_record.pipeline_status == "tier2_complete"
    assert lead_record.tier2_result["schema_version"] == "tier2_enrichment_output.v1"
    assert lead_record.overall_digital_health == "Local plumbing business with modernization opportunities."
