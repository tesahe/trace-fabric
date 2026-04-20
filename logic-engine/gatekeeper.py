import re
import logging
from typing import Dict, Any, Tuple, List, Callable
from bs4 import BeautifulSoup
from dataclasses import dataclass


logger = logging.getLogger(__name__)


# ==========================================
#  TIER 0: CAMPAIGN RULESET CONFIGURATIONS
# ==========================================

@dataclass
class RuleSet:
    """ Defines the signifiers for a specific product/service campaign."""
    campaign_name: str
    rejection_signatures: List[re.Pattern]
    # Functions that take (soup, text_content) and return dict of flags
    custom_evaluators: List[Callable[[BeautifulSoup, str], Dict[str, Any]]]


WEBSITE_MODERNIZATION_CAMPAIGN = RuleSet(
    campaign_name="website_modernization",
    rejection_signatures=[],
    custom_evaluators=[],
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



def evaluate_website_modernization(soup: BeautifulSoup, text_content: str) -> Dict[str, Any]:
    """
    Signifiers for identifying sites that need complete overhauls.
    TEMP function to work AS IS but be updated later oncee:
        DEEP RESEARCH completed on real correlations with:
            non responsive sites
            sites that need improvement
            service gaps

    
    
    """
    flags = {}
    
    # 1. Lack of viewport meta tag strongly correlates with archaic, non-mobile responsive sites!
    viewport = soup.find("meta", attrs={"name": "viewport"})
    flags["missing_mobile_viewport"] = viewport is None
    
    # 2. Check if it's Wordpress (if it is, and missing viewport, it's a prime target)
    flags["is_wordpress"] = bool(re.search(r'wp-content|wp-includes', str(soup)))
    
    return flags



# ==========================================
# TIER 0: THE ENGINE
# ==========================================
    

class HeuristicScanner: 
    """ 
    First Tier Gatekeeper: Deterministic lexical and DOM scanning.
    Executes fast checks before any LLM interference, 100% adaptable to new campaigns.
    """


    # start w/ 150 words as threshhold
    MIN_WORD_COUNT = 150


    def __init__(self, raw_html: str, active_ruleset: RuleSet = WEBSITE_MODERNIZATION_CAMPAIGN):
        """
        Parses raw HTML using lxml.  Falling back to html.parser if no lxml
        """
        self.ruleset = active_ruleset
        
        try: 
            self.soup = BeautifulSoup(raw_html, 'lxml')
        except getattr(BeautifulSoup, "FeatureNotFound", Exception):
            logger.warning("lxml not found, falling back to html.parser")
            self.soup = BeautifulSoup(raw_html, 'html.parser')

        # strip tags and extract human readable text
        self.text_content = self.soup.get_text(separator=" ", strip=True)
        
        self.raw_string = str(self.soup)


    def run_all_checks(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Executes all heuristics
        Returns: (passed: bool, flags: dict, rejection_reason: str)
        """

        flags = {"campaign": self.ruleset.campaign_name}

        

        # 1) Universal Checks (Applies to ALL campaigns)
        word_count = len(self.text_content.split())
        flags["word_count"] = word_count

        if word_count < self.MIN_WORD_COUNT:
            return False, flags, f"rejected_heuristic_low_word_count"

        if self._is_parked_domain():
            flags["parked_domain"]= True
            return False, flags, "rejected_heuristic_parked_domain"

        # 2) Campaign Specific Rejections 
        # for example, squarespace for website modification

        for rejection_pattern in self.ruleset.rejection_signatures:
            if rejection_pattern.search(self.raw_string):
                flags["rejection_signature"] = rejection_pattern.pattern
                return False, flags, f"rejected_heuristic_campaign_mismatch"

        # 3) Campaign Specific Value Extraction
        for evaluator in self.ruleset.custom_evaluators:
            eval_flags = evaluator(self.soup, self.text_content)
            flags.update(eval_flags)


        return True, flags, "pending_tier_1"



    def _is_parked_domain(self) -> bool:
        """ Check for parked domain signatures """

        parked_phrases = ["this domain is for sale", "buy this domain", "parked free", "under construction"]
        lower_text = self.text_content.lower()
        return any(phrase in lower_text for phrase in parked_phrases)
        
        

        