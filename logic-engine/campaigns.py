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
    scoring_v2_enabled: bool
    # When True, ``lead_processor`` instantiates the Tier 0 signature matcher
    # at module import and merges the detections into
    # ``heuristic_flags["technologies"]`` after the deterministic evaluator
    # runs. Default False so production behavior is unchanged until we opt in.
    # Set ``TRACEFAB_SIGNALS_V2=1`` to enable.
    signals_v2_enabled: bool = False
    tier1_enabled: bool = True
    tier2_enabled: bool = True
    tier1_min_score: float = 0.55
    tier1_model: str = "gemini-2.5-flash-lite"
    tier2_model: str = "gemini-2.5-flash"
    tier1_supported_campaigns: tuple[str, ...] = ()
    tier1_supported_industries: tuple[str, ...] = ()
    tier2_supported_campaigns: tuple[str, ...] = ()
    tier2_supported_industries: tuple[str, ...] = ()


def _env_truthy(value: str | None) -> bool:
    """Coerce common env-var truthy values ('1', 'true', 'yes', 'on')."""
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(value: str | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value.strip())
    except ValueError:
        return default


def _env_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    parts = [item.strip().lower() for item in value.split(",")]
    return tuple(item for item in parts if item)


def load_runtime_config() -> RuntimeConfig:
    campaign_type = normalize_campaign_type(os.getenv("OFFER_TYPE", "website_modernization"))

    return RuntimeConfig(
        campaign_type=campaign_type,
        llm_enabled=os.getenv("ENABLE_LLM_PIPELINE", "false").lower() == "true",
        scoring_v2_enabled=_env_truthy(os.getenv("TRACEFAB_SCORING_V2")),
        # Read once at startup — module-level Matcher instantiation in
        # lead_processor depends on this value, so flipping the env var at
        # runtime won't take effect until the process restarts.
        signals_v2_enabled=_env_truthy(os.getenv("TRACEFAB_SIGNALS_V2")),
        tier1_enabled=not os.getenv("TRACEFAB_TIER1_ENABLED", "true").lower() == "false",
        tier2_enabled=not os.getenv("TRACEFAB_TIER2_ENABLED", "true").lower() == "false",
        tier1_min_score=_env_float(os.getenv("TRACEFAB_TIER1_MIN_SCORE"), 0.55),
        tier1_model=os.getenv("TRACEFAB_TIER1_MODEL", "gemini-2.5-flash-lite").strip(),
        tier2_model=os.getenv("TRACEFAB_TIER2_MODEL", "gemini-2.5-flash").strip(),
        tier1_supported_campaigns=_env_csv(os.getenv("TRACEFAB_TIER1_SUPPORTED_CAMPAIGNS")),
        tier1_supported_industries=_env_csv(os.getenv("TRACEFAB_TIER1_SUPPORTED_INDUSTRIES")),
        tier2_supported_campaigns=_env_csv(os.getenv("TRACEFAB_TIER2_SUPPORTED_CAMPAIGNS")),
        tier2_supported_industries=_env_csv(os.getenv("TRACEFAB_TIER2_SUPPORTED_INDUSTRIES")),
    )
