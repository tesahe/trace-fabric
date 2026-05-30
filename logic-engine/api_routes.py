from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from database import AsyncSessionLocal, ScoredLeadModel, EvaluationRunModel

import uuid
from run_schemas import CreateDiscoveryRunRequest, CreateUrlRunRequest

import asyncio
from run_launcher import launch_discovery_run, launch_url_run


async def track_run_process(run_id: str, process: asyncio.subprocess.Process) -> None:
    stdout, stderr = await process.communicate()
    final_status = "completed" if process.returncode == 0 else "failed"

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
            result = await session.execute(stmt)
            run = result.scalar_one_or_none()
            if run is not None:
                run.status = final_status

    if stdout:
        print(f"[Run {run_id}] stdout:\n{stdout.decode(errors='replace')}")
    if stderr:
        print(f"[Run {run_id}] stderr:\n{stderr.decode(errors='replace')}")


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
                        "run_id": lead.run_id,
                        "created_at": lead.created_at,
                        "company_name": lead.company_name,
                        "source_url": lead.source_url,
                        "target_industry": lead.target_industry,
                        "target_location": lead.target_location,
                        "pipeline_status": lead.pipeline_status,
                        "score": lead.score,
                        "is_qualified_lead": lead.is_qualified_lead,
                        "rejection_reason": lead.rejection_reason,
                        "overall_digital_health": lead.overall_digital_health,
                        "heuristic_flags": lead.heuristic_flags,
                        "deterministic_evidence": lead.deterministic_evidence,
                        "tier1_result": lead.tier1_result,
                        "tier2_result": lead.tier2_result,
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
                "tier1_result": lead.tier1_result,
                "tier2_result": lead.tier2_result,
                "llm_output": lead.llm_output,
                "full_llm_payload": lead.full_llm_payload,
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
                "tier1_result": lead.tier1_result,
                "tier2_result": lead.tier2_result,
                "llm_output": lead.llm_output,
                "full_llm_payload": lead.full_llm_payload,
                "run_id": lead.run_id,
            }

    @app.get("/runs")
    async def get_recent_runs(limit: int = 10):
        safe_limit = max(1, min(limit, 50))

        async with AsyncSessionLocal() as session:
            stmt = (
                select(EvaluationRunModel)
                .order_by(EvaluationRunModel.created_at.desc())
                .limit(safe_limit)
            )

            result = await session.execute(stmt)
            runs = result.scalars().all()

            return {
                "count": len(runs),
                "items": [
                    {
                        "id": run.id,
                        "input_mode": run.input_mode,
                        "status": run.status,
                        "target_industry": run.target_industry,
                        "target_location": run.target_location,
                        "direct_url": run.direct_url,
                        "candidate_limit": run.candidate_limit,
                        "max_pages": run.max_pages,
                        "campaign_type": run.campaign_type,
                        "llm_enabled": run.llm_enabled,
                        "created_at": run.created_at,
                        "updated_at": run.updated_at,
                    }
                    for run in runs
                ],
            }

    @app.get("/runs/{run_id}")
    async def get_run_by_id(run_id: str):
        async with AsyncSessionLocal() as session:
            stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
            result = await session.execute(stmt)
            run = result.scalar_one_or_none()

            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")

            return {
                "id": run.id,
                "input_mode": run.input_mode,
                "status": run.status,
                "target_industry": run.target_industry,
                "target_location": run.target_location,
                "direct_url": run.direct_url,
                "candidate_limit": run.candidate_limit,
                "max_pages": run.max_pages,
                "campaign_type": run.campaign_type,
                "llm_enabled": run.llm_enabled,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            }

    @app.get("/runs/{run_id}/leads")
    async def get_leads_for_run(run_id: str, limit: int = 50):
        safe_limit = max(1, min(limit, 200))

        async with AsyncSessionLocal() as session:
            run_stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
            run_result = await session.execute(run_stmt)
            run = run_result.scalar_one_or_none()

            if run is None:
                raise HTTPException(status_code=404, detail="Run not found")

            lead_stmt = (
                select(ScoredLeadModel)
                .where(ScoredLeadModel.run_id == run_id)
                .order_by(ScoredLeadModel.created_at.desc())
                .limit(safe_limit)
            )
            lead_result = await session.execute(lead_stmt)
            leads = lead_result.scalars().all()

            return {
                "run_id": run_id,
                "count": len(leads),
                "items": [
                    {
                        "id": lead.id,
                        "run_id": lead.run_id,
                        "created_at": lead.created_at,
                        "company_name": lead.company_name,
                        "source_url": lead.source_url,
                        "target_industry": lead.target_industry,
                        "target_location": lead.target_location,
                        "pipeline_status": lead.pipeline_status,
                        "score": lead.score,
                        "is_qualified_lead": lead.is_qualified_lead,
                        "rejection_reason": lead.rejection_reason,
                        "overall_digital_health": lead.overall_digital_health,
                        "heuristic_flags": lead.heuristic_flags,
                        "deterministic_evidence": lead.deterministic_evidence,
                        "tier1_result": lead.tier1_result,
                        "tier2_result": lead.tier2_result,
                        "identified_service_gaps": lead.identified_service_gaps,
                        "missing_critical_features": lead.missing_critical_features,
                    }
                    for lead in leads
                ],
            }

    @app.post("/runs/discovery")
    async def create_discovery_run(payload: CreateDiscoveryRunRequest):
        run_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as session:
            async with session.begin():
                run = EvaluationRunModel(
                    id=run_id,
                    input_mode="discover",
                    status="queued",
                    target_industry=payload.industry,
                    target_location=payload.location,
                    direct_url=None,
                    candidate_limit=payload.limit,
                    max_pages=payload.max_pages,
                    campaign_type=payload.campaign_type,
                    llm_enabled=payload.llm_enabled,
                )
                session.add(run)

        process = await launch_discovery_run(
            run_id=run_id,
            industry=payload.industry,
            location=payload.location,
            limit=payload.limit,
            max_pages=payload.max_pages,
        )

        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
                result = await session.execute(stmt)
                run = result.scalar_one()
                run.status = "running"

        asyncio.create_task(track_run_process(run_id, process))
        return {"run_id": run_id, "status": "running"}

    @app.post("/runs/url")
    async def create_url_run(payload: CreateUrlRunRequest):
        run_id = str(uuid.uuid4())

        async with AsyncSessionLocal() as session:
            async with session.begin():
                run = EvaluationRunModel(
                    id=run_id,
                    input_mode="url",
                    status="queued",
                    target_industry=payload.industry,
                    target_location=payload.location,
                    direct_url=str(payload.website),
                    candidate_limit=None,
                    max_pages=None,
                    campaign_type=payload.campaign_type,
                    llm_enabled=payload.llm_enabled,
                )
                session.add(run)

        process = await launch_url_run(
            run_id=run_id,
            website=str(payload.website),
            industry=payload.industry,
            location=payload.location,
        )

        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
                result = await session.execute(stmt)
                run = result.scalar_one()
                run.status = "running"

        asyncio.create_task(track_run_process(run_id, process))
        return {"run_id": run_id, "status": "running"}
