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


def build_discovery_query(industry:str, location: str) -> str:
    return f"{industry.strip()} in {location.strip()}"


@dataclass(frozen=True)
class RuntimeConfig:
    target_industry: str
    target_location: str
    campaign_type: str
    discovery_query: str
    llm_enabled: bool


def load_runtime_config() -> RuntimeConfig:
    target_industry = os.getenv("TARGET_INDUSTRY", "hvac").strip()
    target_location = os.getenv("TARGET_LOCATION", "Portland, OR").strip()
    campaign_type = normalize_campaign_type(os.getenv("OFFER_TYPE", "website_modernization"))
    discovery_query = os.getenv(
        "DISCOVERY_QUERY",
        build_discovery_query(target_industry, target_location),
    ).strip()

    return RuntimeConfig(
        target_industry=target_industry,
        target_location=target_location,
        campaign_type=campaign_type,
        discovery_query=discovery_query,
        llm_enabled=os.getenv("ENABLE_LLM_PIPELINE", "false").lower() == "true",
    )