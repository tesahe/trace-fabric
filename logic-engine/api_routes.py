from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from database import AsyncSessionLocal, ScoredLeadModel


def register_routes(app: FastAPI) -> None:
    @app.get("/metrics")
    async def metrics_dashboard():
        return {
            "status": "healthy",
            "service": "brain-py",
            "architect": "TraceFabric",
        }

    @app.get("/leads/recent")
    async def get_recent_leads(limit: int = 10):
        safe_limit = max(1, min(limit, 50))

        async with AsyncSessionLocal() as session:
            stmt = (
                select(ScoredLeadModel)
                .order_by(ScoredLeadModel.created_at.desc())
                .limit(safe_limit)
            )

            result = await session.execute(stmt)
            leads = result.scalars().all()

            return {
                "count": len(leads),
                "items": [
                    {
                        "id": lead.id,
                        "created_at": lead.created_at,
                        "company_name": lead.company_name,
                        "source_url": lead.source_url,
                        "pipeline_status": lead.pipeline_status,
                        "score": lead.score,
                        "is_qualified_lead": lead.is_qualified_lead,
                        "rejection_reason": lead.rejection_reason,
                        "overall_digital_health": lead.overall_digital_health,
                        "identified_service_gaps": lead.identified_service_gaps,
                        "missing_critical_features": lead.missing_critical_features,
                    }
                    for lead in leads
                ],
            }

    @app.get("/leads/{lead_id}")
    async def get_lead_by_id(lead_id: str):
        async with AsyncSessionLocal() as session:
            stmt = select(ScoredLeadModel).where(ScoredLeadModel.id == lead_id)
            result = await session.execute(stmt)
            lead = result.scalar_one_or_none()

            if lead is None:
                raise HTTPException(status_code=404, detail="Lead not found")

            return {
                "id": lead.id,
                "created_at": lead.created_at,
                "timestamp": lead.timestamp,
                "source_url": lead.source_url,
                "initial_url": lead.initial_url,
                "final_url": lead.final_url,
                "discovery_source": lead.discovery_source,
                "target_industry": lead.target_industry,
                "target_location": lead.target_location,
                "company_name": lead.company_name,
                "category": lead.category,
                "phone_number": lead.phone_number,
                "address": lead.address,
                "pipeline_status": lead.pipeline_status,
                "score": lead.score,
                "is_qualified_lead": lead.is_qualified_lead,
                "rejection_reason": lead.rejection_reason,
                "overall_digital_health": lead.overall_digital_health,
                "heuristic_flags": lead.heuristic_flags,
                "deterministic_evidence": lead.deterministic_evidence,
                "identified_service_gaps": lead.identified_service_gaps,
                "missing_critical_features": lead.missing_critical_features,
                "crawl_allowed": lead.crawl_allowed,
                "crawl_disallowed_reason": lead.crawl_disallowed_reason,
                "http_status": lead.http_status,
                "is_https": lead.is_https,
                "redirect_count": lead.redirect_count,
                "content_type": lead.content_type,
                "page_title": lead.page_title,
                "provider_provenance": lead.provider_provenance,
                "website_provenance": lead.website_provenance,
                "robots_txt": lead.robots_txt,
                "sitemap_xml": lead.sitemap_xml,
            }
