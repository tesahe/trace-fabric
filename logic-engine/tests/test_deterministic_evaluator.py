from deterministic_evaluator import evaluate_lead
from tests.fixtures import (
    crawl_disallowed_lead,
    cross_campaign_lead,
    directory_like_lead,
    modern_business_lead,
    no_website_opportunity_lead,
    smma_candidate_with_socials,
    smma_candidate_without_socials,
    sparse_lead,
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
    assert (
        "appointment_capture" in result["missing_critical_features"]
        or "published_hours" in result["missing_critical_features"]
    )


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


def test_modern_business_does_not_qualify_for_website_modernization():
    lead_data = modern_business_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is False
    assert result["pipeline_status"] == "rejected_deterministic"
    assert result["missing_critical_features"] == []


def test_sparse_input_does_not_crash_and_rejects():
    lead_data = sparse_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is False
    assert result["pipeline_status"] == "rejected_deterministic"


def test_smma_with_social_links_does_not_flag_missing_social_presence():
    lead_data = smma_candidate_with_socials()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="smma",
        target_industry="Auto Detailing",
        heuristic_flags={"campaign": "smma"},
    )

    assert "social_presence_links" not in result["missing_critical_features"]


def test_same_lead_behaves_differently_across_campaigns():
    lead_data = cross_campaign_lead()

    website_result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )
    voice_result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="voice_ai_agent",
        target_industry="HVAC",
        heuristic_flags={"campaign": "voice_ai_agent"},
    )

    assert website_result["pipeline_status"] in {"qualified_deterministic", "rejected_deterministic"}
    assert voice_result["pipeline_status"] in {"qualified_deterministic", "rejected_deterministic"}
    assert website_result["missing_critical_features"] != voice_result["missing_critical_features"]


def test_crawl_disallowed_lead_is_excluded_from_evaluation():
    lead_data = crawl_disallowed_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is False
    assert result["pipeline_status"] == "excluded_crawl_disallowed"
    assert result["rejection_reason"] == "robots_txt_disallow_all"
    assert result["score"] == 0.0


def test_no_website_opportunity_is_excluded_from_website_evaluator():
    lead_data = no_website_opportunity_lead()

    result = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    assert result["is_qualified_lead"] is False
    assert result["pipeline_status"] == "excluded_no_website_opportunity"
    assert result["rejection_reason"] == "no_website_opportunity"
    assert result["score"] == 0.0
