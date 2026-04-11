import os
import logging
import instructor
import asyncio

from google import genai
from pydantic import BaseModel, Field
from aiolimiter import AsyncLimiter

logger = logging.getLogger(__name__)


# ==========================================
# PYDANTIC SCHEMA
# ==========================================


class BusinessValidation(BaseModel):
    """Schema for LLM to output structured business validation."""

    is_real_local_business: bool = Field(
        description="True if this appears to be an active, legitimate local service business (like a plumber, bakery, or clinic). False if it is a directory, blog, generic article, placeholder, or national chain."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0"
    )
    reason: str = Field(
        description="Short 1-2 sentence reasoning for the decision"
    )
    
    
# ==========================================
#  TIER 1 ENGINE
# ==========================================

class Tier1Gatekeeper:
    """
    Tier 1 Gatekeeper: Probabilistic LLM Router.
    Uses Gemini Flash to quickly drop junk leads that bypassed deterministic heuristics.
    """

    def __init__(self):
        # instructor.from_gemini patches the client to return Pydantic objects
        # We use the new google-genai Client here
        self.internal_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.client = instructor.from_genai(
            self.internal_client,
            mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
        )
        self.cheap_model = "gemini-2.5-flash-lite"

    async def validate_business(self, text_content: str) -> BusinessValidation:
        """
        Takes the human-readable text extracted by Tier 0 and runs fast inference
        """

        # OPTIMIZATION: Truncate text. 
        # We don't need 20,000 words to know if it's a real business.
        # The first ~4000 chars (approx 1000 tokens) is enough, saving extreme costs.

        truncated_text = text_content[:4000]
        # TODO
        # CHANGE in future to use ReGex to cut it to 4000, but 4000 most important chars, first 4000

        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.cheap_model,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                            "You are a strict data-quality gatekeeper for a B2B sales pipeline. "
                            "Determine if the provided scraped website text belongs to a real, "
                            "operating local service business. Reject directories (like Yelp), "
                            "news articles, generic blogs, and parked pages.\n\n"
                            f"Website Text:\n\n{truncated_text}"
                            )
                        }
                    ],
                    response_model=BusinessValidation,
                    #temperature=0.0,
                )
            )
            return response
        except Exception as e:
            logger.error(f"Tier 1 Validation Failed: {e}")
            # Fail-Safe:
            # If the cheap LLm crashes, we assume its valid and pass to Tier 2

            return BusinessValidation(
                is_real_local_business=True,
                confidence=0.0,
                reason="Tier 1 LLM Failed to Process (Fail-Safe)"
            )


# ==========================================
# PIPELINE-LEVEL RATE PROTECTION
# ==========================================
# Concurrency cap: max 10 LLM calls in-flight simultaneously.
# If an 11th call arrives, it will WAIT here until one of the 10 finishes.

tier1_semaphore = asyncio.Semaphore(10)

# Max 500 requests per 60-second window.AsyncLimiter
tier1_rate_limiter = AsyncLimiter(max_rate=500, time_period=60)

async def protected_tier1_call(
    gatekeeper: Tier1Gatekeeper,
    text_content: str
) -> BusinessValidation:
    """
    Pipeline-level wrapper for ALL Tier 1 LLM calls.
    ALWAYS use this function instead of calling gatekeeper.validate_business() directly.
    Applies both a concurrency gate and a throughput rate gate.
    """


    async with tier1_semaphore:
        # blocks if 10 calls already going

        async with tier1_rate_limiter:
            # blocks if 500 rpm threshold is hit

            return await gatekeeper.validate_business(text_content)
