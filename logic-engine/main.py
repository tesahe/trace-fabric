import queue
import asyncio
import json
from contextlib import asynccontextmanager
import zmq
import zmq.asyncio
from fastapi import FastAPI
import uvicorn

from concurrent.futures import ThreadPoolExecutor
import random

import lead_v1_pb2

from database import engine, Base, AsyncSessionLocal, ScoredLeadModel
from tier1_router import Tier1Gatekeeper, protected_tier1_call
from tier2_orchestrator import LLMOrchestrator

from campaigns import load_runtime_config
from deterministic_evaluator import evaluate_lead
from gatekeeper import HeuristicScanner, get_ruleset_for_campaign


runtime_config = load_runtime_config()
tier1 = Tier1Gatekeeper() if runtime_config.llm_enabled else None
tier2 = LLMOrchestrator(rpm_limit=500, max_concurent=15, queue_size=2000) if runtime_config.llm_enabled else None


ctx = zmq.asyncio.Context()

# Thread pool for CPU-bound ML inference
# 4 threads = 4 concurrent XGBoost predictions
ml_executor = ThreadPoolExecutor(max_workers=4)

# LLM Gatekeeper init once, reused across all leads

class LeadClassifier:
    def __init__(self):
        print("XGBoost Model Stub Initialized into memory.")

    
    def predict(self, raw_html: str) -> float:
        import time
        time.sleep(0.1)

        return round(random.uniform(0.0, 1.0), 4)
        # "proprensity to buy" score - random for now for testing

classifier = LeadClassifier()


# For provenance in proto transfer string, to JSON in DB
def parse_json_object(raw_value: str) -> dict:
    if not raw_value:
        return {}

    try: 
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}

async def process_incoming_lead(lead) -> None:
    print(f"[Ingest] Lead ID: {lead.id} | Source: {lead.source_url}")

    print(f"[Tier 0] Starting heuristic scan for Lead ID: {lead.id}")

    scanner = HeuristicScanner(
        lead.raw_html,
        get_ruleset_for_campaign(runtime_config.campaign_type),
    )

    passed, heuristic_flags, status = scanner.run_all_checks()
    print(f"[Tier 0] Completed for Lead ID: {lead.id} | passed={passed} | status={status}")

    lead_payload = {
        "id": lead.id,
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
        "response_headers": [
            {"key": h.key, "value": h.value}
            for h in lead.response_headers
        ],
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
    }

    if not passed:
        print(f"[Tier 0] Rejected Lead {lead.id} | Reason: {status}")
        async with AsyncSessionLocal() as session:
            async with session.begin():
                rejected_record = ScoredLeadModel(
                    id=lead.id,
                    timestamp=lead.timestamp,
                    source_url=lead.source_url,
                    initial_url=lead.initial_url,
                    final_url=lead.final_url,
                    discovery_source=lead.discovery_source,
                    target_industry=lead.target_industry,
                    target_location=lead.target_location,
                    crawl_allowed=lead.crawl_allowed,
                    crawl_disallowed_reason=lead.crawl_disallowed_reason,
                    is_no_website_opportunity=lead.is_no_website_opportunity,
                    provider_fsq_id=lead.provider_fsq_id,
                    provider_provenance=parse_json_object(lead.provider_provenance_json),
                    website_provenance=parse_json_object(lead.website_provenance_json),
                    location_confidence=lead.location_confidence,
                    category_confidence=lead.category_confidence,
                    company_name=lead.company_name,
                    category=lead.category,
                    phone_number=lead.phone_number,
                    address=lead.address,
                    http_status=lead.http_status,
                    is_https=lead.is_https,
                    redirect_count=lead.redirect_count,
                    fetch_duration_ms=lead.fetch_duration_ms,
                    response_size_bytes=lead.response_size_bytes,
                    content_type=lead.content_type,
                    page_title=lead.page_title,
                    manifest_url=lead.manifest_url,
                    raw_html=lead.raw_html,
                    text_content=lead.text_content,
                    response_headers=lead_payload["response_headers"],
                    anchor_hrefs=lead_payload["anchor_hrefs"],
                    script_srcs=lead_payload["script_srcs"],
                    stylesheet_hrefs=lead_payload["stylesheet_hrefs"],
                    robots_txt=lead_payload["robots_txt"],
                    sitemap_xml=lead_payload["sitemap_xml"],
                    score=0.0,
                    pipeline_status=status,
                    heuristic_flags=heuristic_flags,
                )
                session.add(rejected_record)
        return

    evaluation = evaluate_lead(
        lead_data=lead_payload,
        campaign_type=runtime_config.campaign_type,
        target_industry=runtime_config.target_industry,
        heuristic_flags=heuristic_flags,
    )

    if runtime_config.llm_enabled:
        print(f"[Tier 1] Starting LLM validation for Lead ID: {lead.id}")

        tier1_result = await protected_tier1_call(tier1, scanner.text_content)
        print(
            f"[Tier 1] Completed LLM validation for Lead ID: {lead.id} "
            f"| is_real_local_business={tier1_result.is_real_local_business}"
        )

        if not tier1_result.is_real_local_business:
            print(f"[Tier1 REJECT] Lead ID: {lead.id} | Reason: {tier1_result.reason}")

            async with AsyncSessionLocal() as session:
                async with session.begin():
                    rejected_record = ScoredLeadModel(
                        id=lead.id,
                        timestamp=lead.timestamp,
                        source_url=lead.source_url,
                        initial_url=lead.initial_url,
                        final_url=lead.final_url,
                        discovery_source=lead.discovery_source,
                        target_industry=lead.target_industry,
                        target_location=lead.target_location,
                        crawl_allowed=lead.crawl_allowed,
                        crawl_disallowed_reason=lead.crawl_disallowed_reason,
                        is_no_website_opportunity=lead.is_no_website_opportunity,
                        provider_fsq_id=lead.provider_fsq_id,
                        provider_provenance=parse_json_object(lead.provider_provenance_json),
                        website_provenance=parse_json_object(lead.website_provenance_json),
                        location_confidence=lead.location_confidence,
                        category_confidence=lead.category_confidence,
                        company_name=lead.company_name,
                        category=lead.category,
                        phone_number=lead.phone_number,
                        address=lead.address,
                        http_status=lead.http_status,
                        is_https=lead.is_https,
                        redirect_count=lead.redirect_count,
                        fetch_duration_ms=lead.fetch_duration_ms,
                        response_size_bytes=lead.response_size_bytes,
                        content_type=lead.content_type,
                        page_title=lead.page_title,
                        manifest_url=lead.manifest_url,
                        raw_html=lead.raw_html,
                        text_content=lead.text_content,
                        response_headers=lead_payload["response_headers"],
                        anchor_hrefs=lead_payload["anchor_hrefs"],
                        script_srcs=lead_payload["script_srcs"],
                        stylesheet_hrefs=lead_payload["stylesheet_hrefs"],
                        robots_txt=lead_payload["robots_txt"],
                        sitemap_xml=lead_payload["sitemap_xml"],
                        score=0.0,
                        pipeline_status="rejected_tier1_not_a_business",
                        heuristic_flags={
                            **heuristic_flags,
                            "tier1_reason": tier1_result.reason,
                            "tier1_confidence": tier1_result.confidence,
                        },
                        rejection_reason=tier1_result.reason,
                    )

                    session.add(rejected_record)

            return

    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_record = ScoredLeadModel(
                id=lead.id,
                timestamp=lead.timestamp,
                source_url=lead.source_url,
                initial_url=lead.initial_url,
                final_url=lead.final_url,
                discovery_source=lead.discovery_source,
                target_industry=lead.target_industry,
                target_location=lead.target_location,
                crawl_allowed=lead.crawl_allowed,
                crawl_disallowed_reason=lead.crawl_disallowed_reason,
                is_no_website_opportunity=lead.is_no_website_opportunity,
                provider_fsq_id=lead.provider_fsq_id,
                provider_provenance=parse_json_object(lead.provider_provenance_json),
                website_provenance=parse_json_object(lead.website_provenance_json),
                location_confidence=lead.location_confidence,
                category_confidence=lead.category_confidence,
                company_name=lead.company_name,
                category=lead.category,
                phone_number=lead.phone_number,
                address=lead.address,
                http_status=lead.http_status,
                is_https=lead.is_https,
                redirect_count=lead.redirect_count,
                fetch_duration_ms=lead.fetch_duration_ms,
                response_size_bytes=lead.response_size_bytes,
                content_type=lead.content_type,
                page_title=lead.page_title,
                manifest_url=lead.manifest_url,
                raw_html=lead.raw_html,
                text_content=lead.text_content,
                response_headers=lead_payload["response_headers"],
                anchor_hrefs=lead_payload["anchor_hrefs"],
                script_srcs=lead_payload["script_srcs"],
                stylesheet_hrefs=lead_payload["stylesheet_hrefs"],
                robots_txt=lead_payload["robots_txt"],
                sitemap_xml=lead_payload["sitemap_xml"],
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
            session.add(new_record)

    print(f"[Persist] Lead ID: {lead.id} -> DB")

    if runtime_config.llm_enabled:
        await tier2.enqueue_lead(
            {
                "id": lead.id,
                "url": lead.source_url,
                "html": lead.raw_html,
                "company_name": lead.company_name,
                "timestamp": lead.timestamp,
                "phone_number": lead.phone_number,
                "address": lead.address,
                "category": lead.category,
                "discovery_source": lead.discovery_source,
                "target_location": lead.target_location,
            }
        )




async def zmq_pull_worker():
    """
    Continously pull messages from Rust in background.
    """
    
    socket = ctx.socket(zmq.PULL)
    socket.bind("tcp://127.0.0.1:5555")

    print("Logic Engine] ZMQ PULL socket bound to tcp://127.0.0.1:5555")


    try: 
        while True:
            raw_bytes = await socket.recv()

            # 1) python Protobuf container
            batch = lead_v1_pb2.LeadBatch()
            # 2) C-extension parses bytes into Python objects
            batch.ParseFromString(raw_bytes)


            
            for lead in batch.leads:
                await process_incoming_lead(lead)



                # XG BOOST SCORING BLOCK 
                # TBD IN FUTURE - WHEN TRAINING DATA COLLECTED


                # grab main running async event loop
                # loop = asyncio.get_running_loop()

                # score = await loop.run_in_executor(
                #     ml_executor, 
                #     classifier.predict,
                #     lead.raw_html 
                # )

                # print(f"[Scored] Lead ID: {lead.id} -> {score}")
                # XG BOOST ABOVE 

                # async with AsyncSessionLocal() as session:

                #     async with session.begin():
                #         new_record = ScoredLeadModel(
                #             id=lead.id,
                #             source_url=lead.source_url,
                #             score=score,
                #             company_name=lead.company_name,
                #             raw_html=lead.raw_html,
                #             timestamp=lead.timestamp,
                #         )
                #         session.add(new_record)

                #     print(f"[Persist] Lead ID: {lead.id} -> DB")

    except asyncio.CancelledError:
        print(f"[Logic Engine] ZMQ worker shutting down gracefully...")

    finally:
        socket.close()


@asynccontextmanager
async def lifespan(app: FastAPI):

    # DB Initialization
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database schema verified.")

    # STARTUP - ZeroMQ listener as a concurrent asyncio Task
    worker_task = asyncio.create_task(zmq_pull_worker())

    if runtime_config.llm_enabled and tier2 is not None:
        await tier2.start(worker_count=15)
        print("[Tier 2] LLM Workers started.")
    else:
        print("[Tier 2] Disabled for local deterministic testing.")


    # fastAPI control here
    yield

    # Shutdown 
    worker_task.cancel()

    if tier2 is not None:
        for task in tier2.workers:
            task.cancel()

    try: 
        await worker_task
    except asyncio.CancelledError:
        pass

    ctx.term()


# FastAPI Init with lifespan manager

app = FastAPI(title="TraceFabric Logic Engine", lifespan=lifespan)

@app.get("/metrics")

async def metrics_dashboard():
    return {
        "status": "healthy",
        "service": "brain-py",
        "architect": "TraceFabric"
    }



if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    


    
