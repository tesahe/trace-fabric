from deterministic_evaluator import evaluate_lead
from tests.fixtures import (
    directory_like_lead,
    smma_candidate_without_socials,
    voice_ai_candidate_lead,
    weak_website_hvac_lead,
)


def test_website_modernization_qualifies_real_business_with_clear_gaps():
    lead_data = weak_website_hvac_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is True
    assert result["pipeline_status"] == "qualified_deterministic"
    assert "missing_mobile_viewport" in result["identified_service_gaps"]
    assert "privacy_policy" in result["missing_critical_features"]


def test_voice_ai_agent_flags_missing_booking_or_hours():
    lead_data = voice_ai_candidate_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="voice_ai_agent",
        target_industry="Plumbing",
        heuristic_flags={"campaign": "voice_ai_agent"},
    )

    assert result["is_qualified_lead"] is True
    assert result["pipeline_status"] == "qualified_deterministic"
    assert "appointment_capture" in result["missing_critical_features"] or "published_hours" in result["missing_critical_features"]


def test_smma_flags_missing_social_presence():
    lead_data = smma_candidate_without_socials()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="smma",
        target_industry="Auto Detailing",
        heuristic_flags={"campaign": "smma"},
    )

    assert result["pipeline_status"] == "qualified_deterministic"
    assert "social_presence_links" in result["missing_critical_features"]


def test_directory_like_host_is_not_qualified():
    lead_data = directory_like_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is False
    assert result["pipeline_status"] == "rejected_deterministic"
    assert result["rejection_reason"] == "deterministic_gate_reject"
