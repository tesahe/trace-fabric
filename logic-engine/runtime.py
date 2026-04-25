import asyncio
from contextlib import asynccontextmanager

import lead_v1_pb2
import zmq
import zmq.asyncio

from database import Base, engine
from lead_processor import process_incoming_lead, runtime_config, tier2


ctx = zmq.asyncio.Context()


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

    except asyncio.CancelledError:
        print("[Logic Engine] ZMQ worker shutting down gracefully...")

    finally:
        socket.close()


@asynccontextmanager
async def lifespan(app):
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
