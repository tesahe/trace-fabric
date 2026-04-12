import asyncio
import logging
from aiolimiter import AsyncLimiter
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from google import genai
from typing import Optional

import instructor
from schemas import LeadExtraction
from sqlalchemy import select
from database import AsyncSessionLocal, ScoredLeadModel


logger = logging.getLogger(__name__)

# To catch HTTP 429 errors
class LLMRatelimitException(Exception):
    pass


# Initalize Client wrapped with Instructor
raw_client = genai.Client()
ai_client = instructor.from_genai(raw_client)

async def evaluate_service_gaps(html_content: str, url:str) -> Optional[LeadExtraction]:
    """
    Tier 2 Orchestrator Core Cognitive Engine:
    Evaluates the scraped real-world HTML to extract deterministic Service Gaps using Gemini.
    """

    # System Prompt
    system_prompt = (
        "You are a Senior Digital Architect and Web Evaluator. "
        "Your objective is to evaluate small business websites to identify critical 'Service Gaps' "
        "(e.g., outdated design, lacking an online booking engine, missing contact details). "
        "If you are confident the website represents a real operational business, but it has a poor digital presence, "
        "you should flag it as a highly qualified lead.\n\n"
        "CRITICAL RULES:\n"
        "1. Strictly adhere to the provided output JSON schema.\n"
        "2. Base your findings ONLY on the provided HTML content.\n"
        "3. If the page is broken, parked, or not a real business, set is_qualified_lead to False and explain why."
    )

    try:
        # Instructor Extraction using asyncio.to_thread for safety net.
        extraction: LeadExtraction = await asyncio.to_thread(
            ai_client.create,
            response_model=LeadExtraction,
            model="gemini-2.5-flash",
            messages=[
                {"role": "user", "content": system_prompt},
                {"role": "user", "content": f"Target URL: {url}\n\nHTML Content:\n{html_content[:30000]}"} # Truncate massive HTML payloads to save tokens
            ]
        )

        return extraction

    except Exception as e:
        logger.error(f"Error evaluating service gaps for {url}: {e}")
        return None



    



    


class LLMOrchestrator:
    def __init__(self, rpm_limit: int = 500, max_concurent: int = 15, queue_size: int = 2000):
        # 1. Bounded Queue to create backpressure
        self.queue = asyncio.Queue(maxsize=queue_size)

        # 2. Rate Limiter (Token Bucket)
        self.rate_limiter = AsyncLimiter(rpm_limit, 60.0)


        # 3. Governor (Concurrency Control)
        self.semaphore = asyncio.Semaphore(max_concurent)


        self.workers = []

    # PRODUCER -- RECIEVING FROM ZeroMQ

    async def enqueue_lead(self, lead_data: dict):
        """
        Called by the Tier 1 Router.
        Because self.queue is bounded, this 'await' blocks if the system is saturated.
        This block propagates back to ZeroMQ, safely holding data in Rust/ZMQ buffers.
        """

        await self.queue.put(lead_data)
        logging.debug(f"Queued lead. Buffer utilization: {self.queue.qsize()} / {self.queue.maxsize}")
    


    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(LLMRatelimitException)
    )

    async def _save_execute_llm(self, lead_data: dict):
        """
        Executes the LLM request while obeying the Token Bucket and the Semaphore.
        """

        # Ask token bucket for permission
        async with self.rate_limiter:


            # Ask semaphore for permission
            async with self.semaphore:

                url = lead_data.get("url", "Unknown URL")
                html = lead_data.get("html", "")
                

                # TODO Fire HTTP Req to LLm API
                logger.info(f"[Tier 2] Firing LLM extraction for lead ID: {url}")

                result = await evaluate_service_gaps(html_content=html, url=url)

                if result is None:

                    # If LLm failed or timed out
                    pass




                return result


    
    # Workers

    async def _worker_loop(self, worker_id: int):
        """
        Runs infinitely in the background, consuming leads
        """

        while True:
            # 1. Wait for a lead to drop
            lead_data = await self.queue.get()
            lead_id = lead_data.get("id")
            # TODO need to see if we want this id, or the cid that comes in with serper

            try: 
                # 2. Push it through pipeline
                result: Optional[LeadExtraction] = await self._save_execute_llm(lead_data)

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        stmt = select(ScoredLeadModel).where(ScoredLeadModel.id == lead_id)
                        db_result = await session.execute(stmt)
                        lead_record = db_result.scalar_one_or_none()

                        if not lead_record:
                            logger.error(f"Worker {worker_id}: Lead {lead_id} not found in DB! Highly anomalous.")
                            continue

                        if result is not None:
                            lead_record.is_qualified_lead = result.is_qualified_lead
                            lead_record.overall_digital_health = result.overall_digital_health
                            lead_record.rejection_reason = result.rejection_reason
                            
                            # Break down the nested gaps
                            lead_record.has_booking_widget = result.service_gaps.has_online_booking
                            lead_record.is_mobile_optimized = result.service_gaps.is_mobile_optimized
                            lead_record.has_clear_contact_info = result.service_gaps.has_clear_contact_info
                            
                            # Dump the JSON data for Lists and the "Safe Haven" Payload
                            lead_record.identified_service_gaps = result.service_gaps.outdated_indicators
                            lead_record.missing_critical_features = result.service_gaps.missing_critical_features
                            lead_record.full_llm_payload = result.model_dump() # The absolute source of truth
                            
                            # Update workflow status based on the LLM's opinion
                            if result.is_qualified_lead:
                                lead_record.pipeline_status = "lead_qualified"
                            else:
                                lead_record.pipeline_status = "lead_rejected_by_llm"
                        



                logger.info(f"[Tier 2] Saved LLM results for lead ID: {lead_id} | Status: {lead_record.pipeline_status}")
            
            except Exception as e:
                logger.error(f"Worker {worker_id} completely failed on lead. Error: {e}")

                # TODO Write to a dead-letter-queue in Postgres


            finally:
                self.queue.task_done()

    async def start(self, worker_count: int = 15):
        """
        Bootstraps the workers when the application starts
        """

        for i in range(worker_count):
            task = asyncio.create_task(self._worker_loop(worker_id=i))
            self.workers.append(task)

        logger.info(f"Started {worker_count} LLM background workers.")

            
