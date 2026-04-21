import uuid

import pytest
from sqlalchemy import select

from database import AsyncSessionLocal, ScoredLeadModel
from deterministic_evaluator import evaluate_lead
from tests.fixtures import weak_website_hvac_lead


@pytest.mark.anyio
async def test_deterministic_result_persists_to_database():
    lead_data = weak_website_hvac_lead()
    evaluation = evaluate_lead(
        lead_data=lead_data,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
    )

    lead_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as session:
        async with session.begin():
            row = ScoredLeadModel(
                id=lead_id,
                timestamp="2026-04-20T00:00:00Z",
                company_name="AAA Heating and Cooling",
                source_url=lead_data["source_url"],
                initial_url=lead_data["source_url"],
                final_url=lead_data["source_url"],
                discovery_source="brave",
                target_industry="HVAC",
                target_location="Portland, OR",
                crawl_allowed=True,
                crawl_disallowed_reason="",
                is_no_website_opportunity=False,
                provider_fsq_id="",
                provider_provenance={},
                website_provenance={},
                location_confidence=0.0,
                category_confidence=0.0,
                raw_html=lead_data["raw_html"],
                text_content=lead_data["text_content"],
                page_title=lead_data["page_title"],
                phone_number=lead_data["phone_number"],
                address=lead_data["address"],
                anchor_hrefs=lead_data["anchor_hrefs"],
                response_headers=[],
                script_srcs=[],
                stylesheet_hrefs=[],
                robots_txt=lead_data["robots_txt"],
                sitemap_xml=lead_data["sitemap_xml"],
                score=evaluation["score"],
                pipeline_status=evaluation["pipeline_status"],
                heuristic_flags=evaluation["heuristic_flags"],
                deterministic_evidence=evaluation["deterministic_evidence"],
                is_qualified_lead=evaluation["is_qualified_lead"],
                has_booking_widget=evaluation["has_booking_widget"],
                is_mobile_optimized=evaluation["is_mobile_optimized"],
                has_clear_contact_info=evaluation["has_clear_contact_info"],
                overall_digital_health=evaluation["overall_digital_health"],
                rejection_reason=evaluation["rejection_reason"],
                identified_service_gaps=evaluation["identified_service_gaps"],
                missing_critical_features=evaluation["missing_critical_features"],
            )
            session.add(row)

    async with AsyncSessionLocal() as session:
        stmt = select(ScoredLeadModel).where(ScoredLeadModel.id == lead_id)
        result = await session.execute(stmt)
        saved = result.scalar_one()

    assert saved.discovery_source == "brave"
    assert saved.target_industry == "HVAC"
    assert saved.target_location == "Portland, OR"
    assert saved.pipeline_status == evaluation["pipeline_status"]
    assert saved.heuristic_flags["campaign"] == "website_modernization"
    assert isinstance(saved.missing_critical_features, list)
