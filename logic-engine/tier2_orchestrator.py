import asyncio
import logging
from aiolimiter import AsyncLimiter
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type


logger = logging.getLogger(__name__)

# To catch HTTP 429 errors
class LLMRatelimitException(Exception):
    pass

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
                

                # TODO Fire HTTP Req to LLm API
                logger.info(f"[Tier 2] Firing LLM extraction for lead ID: {lead_data.get('id')}")

                await asyncio.sleep(1)



                return {"extracted_data": "success"}


    
    # Workers

    async def _worker_loop(self, worker_id: int):
        """
        Runs infinitely in the background, consuming leads
        """

        while True:
            # 1. Wait for a lead to drop
            lead_data = await self.queue.get()

            try: 
                # 2. Push it through pipeline
                result = await self._save_execute_llm(lead_data)

                # 3. TODO Update DB
                logger.info(f"[Tier 2] Saved LLM results for lead ID: {lead_data.get('id')}")
            
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

            
        
                
        





        
