import os
import re
from dataclasses import dataclass


def normalize_campaign_type(raw_value: str | None) -> str:
    if not raw_value:
        return "website_modernization"

    normalized = re.sub(r"[^a-z0-9]+", "_", raw_value.strip().lower()).strip("_")
    aliases = {
        "website": "website_modernization",
        "website_creation": "website_modernization",
        "website_rebuild": "website_modernization",
        "voice_ai": "voice_ai_agent",
        "voice_agent": "voice_ai_agent",
        "voice_ai_agent": "voice_ai_agent",
        "smma": "smma",
        "social_media_management": "smma",
        "social_media_marketing": "smma",
    }
    return aliases.get(normalized, normalized)


@dataclass(frozen=True)
class RuntimeConfig:
    campaign_type: str
    llm_enabled: bool


def load_runtime_config() -> RuntimeConfig:
    campaign_type = normalize_campaign_type(os.getenv("OFFER_TYPE", "website_modernization"))

    return RuntimeConfig(
        campaign_type=campaign_type,
        llm_enabled=os.getenv("ENABLE_LLM_PIPELINE", "false").lower() == "true",
    )
