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
    # When True, ``lead_processor`` instantiates the Tier 0 signature matcher
    # at module import and merges the detections into
    # ``heuristic_flags["technologies"]`` after the deterministic evaluator
    # runs. Default False so production behavior is unchanged until we opt in.
    # Set ``TRACEFAB_SIGNALS_V2=1`` to enable.
    signals_v2_enabled: bool = False


def _env_truthy(value: str | None) -> bool:
    """Coerce common env-var truthy values ('1', 'true', 'yes', 'on')."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_runtime_config() -> RuntimeConfig:
    campaign_type = normalize_campaign_type(os.getenv("OFFER_TYPE", "website_modernization"))

    return RuntimeConfig(
        campaign_type=campaign_type,
        llm_enabled=os.getenv("ENABLE_LLM_PIPELINE", "false").lower() == "true",
        # Read once at startup — module-level Matcher instantiation in
        # lead_processor depends on this value, so flipping the env var at
        # runtime won't take effect until the process restarts.
        signals_v2_enabled=_env_truthy(os.getenv("TRACEFAB_SIGNALS_V2")),
    )
