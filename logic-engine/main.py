import asyncio
from contextlib import asynccontextmanager
import zmq
import zmq.asyncio
from fastapi import FastAPI
import uvicorn

from concurrent.futures import ThreadPoolExecutor
import random

import lead_v1_pb2

from database import engine, Base, AsyncSessionLocal, ScoredLeadModel
from gatekeeper import HeuristicScanner, WEBSITE_MODERNIZATION_CAMPAIGN
from tier1_router import Tier1Gatekeeper, protected_tier1_call

ctx = zmq.asyncio.Context()

# Thread pool for CPU-bound ML inference
# 4 threads = 4 concurrent XGBoost predictions
ml_executor = ThreadPoolExecutor(max_workers=4)

# LLM Gatekeeper init once, reused across all leads
tier1 = Tier1Gatekeeper()

class LeadClassifier:
    def __init__(self):
        print("XGBoost Model Stub Initialized into memory.")

    
    def predict(self, raw_html: str) -> float:
        import time
        time.sleep(0.1)

        return round(random.uniform(0.0, 1.0), 4)
        # "proprensity to buy" score - random for now for testing

classifier = LeadClassifier()




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
                print(f"[Ingest] Lead ID: {lead.id} | Source: {lead.source_url}")

                # TIER 0: Heuristic Scanner
                scanner = HeuristicScanner(lead.raw_html, WEBSITE_MODERNIZATION_CAMPAIGN)
                passed, heuristic_flags, status = scanner.run_all_checks()

                if not passed: 
                    print(f"[Tier 0] Rejected Lead {lead.id} | Reason: {status}")
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            rejected_record = ScoredLeadModel(
                                id=lead.id,
                                source_url=lead.source_url,
                                score=0.0,
                                company_name=lead.company_name,
                                raw_html=lead.raw_html,
                                timestamp=lead.timestamp,
                                pipeline_status=status,
                                heuristic_flags=heuristic_flags,
                            )
                            session.add(rejected_record)
                    continue

                # TIER 1: Probabilistic LLM Validator

                tier1_result = await protected_tier1_call(tier1, scanner.text_content)

                if not tier1_result.is_real_local_business:
                    print(f"[Tier1 REJECT] Lead ID: {lead.id} | Reason: {tier1_result.reason}")
                    async with AsyncSessionLocal() as session:
                        async with session.begin():
                            rejected_record = ScoredLeadModel(
                                id=lead.id,
                                source_url=lead.source_url,
                                score=0.0,
                                company_name=lead.company_name,
                                raw_html=lead.raw_html,
                                timestamp=lead.timestamp,
                                pipeline_status="rejected_tier1_not_a_business",
                                heuristic_flags=heuristic_flags  # still preserve the Tier 0 data
                            )
                            session.add(rejected_record)
                    continue

                # TIERS 0 + 1 PASSED → Proceed to XGBoost / Tier 2

                # loop = asyncio.get_running_loop()
                # score = await loop.run_in_executor(
                #     ml_executor,
                #     classifier.predict,
                #     lead.raw_html
                # )

                # print(f"[Scored] Lead ID: {lead.id} -> {score}")

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        new_record = ScoredLeadModel(
                            id=lead.id,
                            source_url=lead.source_url,
                            score=0.0,
                            company_name=lead.company_name,
                            raw_html=lead.raw_html,
                            timestamp=lead.timestamp,
                            pipeline_status="pending_tier2",   # ← ready for deep LLM extraction
                            heuristic_flags=heuristic_flags
                        )
                        session.add(new_record)

                print(f"[Persist] Lead ID: {lead.id} -> DB")


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
    print(" Database schema verified.")

    # STARTUP - ZeroMQ listener as a concurrent asyncio Task
    worker_task = asyncio.create_task(zmq_pull_worker())


    # fastAPI control here
    yield

    # Shutdown 
    worker_task.cancel()

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
    


    
