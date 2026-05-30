import re
import logging
from typing import Dict, Any, Tuple, List, Callable
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


# ==========================================
#  TIER 0: CAMPAIGN RULESET CONFIGURATIONS
# ==========================================

@dataclass
class RuleSet:
    """ Defines the signifiers for a specific product/service campaign."""
    campaign_name: str
    rejection_signatures: List[re.Pattern]
    custom_evaluators: List[Callable[[Any], Dict[str, Any]]] = field(default_factory=list)


def _url_list(lead) -> List[str]:
    return [s.url for s in lead.script_srcs] + [s.url for s in lead.stylesheet_hrefs]


def evaluate_website_modernization(lead) -> Dict[str, Any]:
    urls = _url_list(lead)
    return {
        "missing_mobile_viewport": not lead.has_viewport,
        "is_wordpress": any(
            "wp-content" in u or "wp-includes" in u for u in urls
        ),
    }

WEBSITE_MODERNIZATION_CAMPAIGN = RuleSet(
    campaign_name="website_modernization",
    rejection_signatures=[
        re.compile(r"squarespace\.com", re.IGNORECASE),
        re.compile(r"cdn\.shopify\.com", re.IGNORECASE),
        re.compile(r"wix\.com", re.IGNORECASE),
        re.compile(r"weebly\.com", re.IGNORECASE),
    ],
    custom_evaluators=[evaluate_website_modernization],
)

VOICE_AI_AGENT_CAMPAIGN = RuleSet(
    campaign_name="voice_ai_agent",
    rejection_signatures=[],
    custom_evaluators=[],
)

SMMA_CAMPAIGN = RuleSet(
    campaign_name="smma",
    rejection_signatures=[],
    custom_evaluators=[],
)

def get_ruleset_for_campaign(campaign_type: str) -> RuleSet:
    """Returns the appropriate RuleSet for the given campaign type."""

    if campaign_type == "website_modernization":
        return WEBSITE_MODERNIZATION_CAMPAIGN
    if campaign_type == "voice_ai_agent":
        return VOICE_AI_AGENT_CAMPAIGN
    if campaign_type == "smma":
        return SMMA_CAMPAIGN
    
    raise ValueError(f"Unknown campaign type: {campaign_type}")







# ==========================================
# TIER 0: THE ENGINE
# ==========================================
    

class HeuristicScanner:
    """
    Tier 0 gatekeeper. Fast deterministic rejection using proto-extracted signals.
    Reads word_count and is_parked_domain directly from the proto lead object.
    Rejection signatures are matched against extracted script/stylesheet URLs.
    """

    MIN_WORD_COUNT = 150

    def __init__(self, lead, active_ruleset: RuleSet = WEBSITE_MODERNIZATION_CAMPAIGN):
        self.lead = lead
        self.ruleset = active_ruleset

    def run_all_checks(self) -> Tuple[bool, Dict[str, Any], str]:
        flags: Dict[str, Any] = {"campaign": self.ruleset.campaign_name}

        word_count = self.lead.word_count
        flags["word_count"] = word_count
        if word_count < self.MIN_WORD_COUNT:
            return False, flags, "rejected_heuristic_low_word_count"

        if self.lead.is_parked_domain:
            flags["parked_domain"] = True
            return False, flags, "rejected_heuristic_parked_domain"

        urls = _url_list(self.lead)
        for pattern in self.ruleset.rejection_signatures:
            if any(pattern.search(u) for u in urls):
                flags["rejection_signature"] = pattern.pattern
                return False, flags, "rejected_heuristic_campaign_mismatch"

        for evaluator in self.ruleset.custom_evaluators:
            flags.update(evaluator(self.lead))

        return True, flags, "pending_tier_1"