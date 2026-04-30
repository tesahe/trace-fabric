"""Integration tests for the matcher + signals_v2 feature flag.

What this exercises:

- The pure ``build_lead_evaluation`` helper that ``lead_processor`` calls
  after Tier 0 gates a lead. We test the helper directly rather than
  ``process_incoming_lead`` because the latter is heavily DB-coupled
  (SQLAlchemy async sessions, Tier 1 / Tier 2 orchestrators) and pulling
  those into a unit test buys complexity, not signal.

- The contract documented in Check-in 4: when ``signals_v2_enabled=False``
  the matcher is never invoked and ``heuristic_flags["technologies"]``
  never appears; when ``signals_v2_enabled=True`` detections show up;
  and when the matcher raises the pipeline survives unchanged.

If ``deterministic_evaluator`` (and its ``bs4 / lxml`` deps) are missing,
the entire module is skipped — no point running these without the
real Tier 0 evaluator under the hood.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# logic-engine/ on sys.path so ``import lead_evaluation`` works.
_LOGIC_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_LOGIC_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_LOGIC_ENGINE_ROOT))

# Skip the whole module if the deterministic evaluator's deps aren't installed.
pytest.importorskip("bs4")
pytest.importorskip("lxml")

lead_evaluation = pytest.importorskip("lead_evaluation")
build_lead_evaluation = lead_evaluation.build_lead_evaluation

from signals.matcher import Matcher  # noqa: E402
from signals.tests.conftest import load_expected, load_fixture_lead  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _baseline_payload() -> dict:
    """Minimal Tier-0-passing lead with no technology fingerprints.

    ``deterministic_evaluator`` requires real-business signals (phone /
    contact page) to issue a non-rejection — give it those without leaking
    any wappalyzer-detectable patterns.
    """
    return {
        "raw_html": (
            "<html><head><title>Smith and Sons HVAC</title></head>"
            "<body><h1>Smith and Sons HVAC</h1>"
            "<p>Furnace and AC repair in Portland.</p>"
            "<a href='/contact'>Contact</a>"
            "<a href='tel:5035551234'>Call</a>"
            "</body></html>"
        ),
        "text_content": (
            "Smith and Sons HVAC furnace and AC repair in Portland. "
            "Contact us today for service."
        ),
        "page_title": "Smith and Sons HVAC",
        "source_url": "https://smithandsonshvac.example.com/",
        "phone_number": "503-555-1234",
        "address": "123 Main St, Portland, OR",
        "anchor_hrefs": [
            {"url": "/contact", "is_internal": True, "label": "Contact"},
        ],
        "script_srcs": [],
        "stylesheet_hrefs": [],
        "response_headers": [],
        "robots_txt": {
            "path": "/robots.txt",
            "http_status": 200,
            "exists": True,
            "content_type": "text/plain",
            "body": "User-agent: *",
        },
        "sitemap_xml": {
            "path": "/sitemap.xml",
            "http_status": 200,
            "exists": True,
            "content_type": "application/xml",
            "body": "<urlset></urlset>",
        },
        "crawl_allowed": True,
        "crawl_disallowed_reason": "",
        "is_no_website_opportunity": False,
        "discovery_source": "brave",
    }


# ---------------------------------------------------------------------------
# Test 1: flag OFF means no matcher and no technologies key
# ---------------------------------------------------------------------------


def test_flag_off_does_not_invoke_matcher_or_add_technologies_key():
    """matcher=None must produce evaluation with no ``technologies`` key.

    This is the production default. Critical: any regression here means we
    leaked matcher output into the heuristic_flags schema unconditionally.
    """
    payload = _baseline_payload()
    evaluation = build_lead_evaluation(
        payload,
        campaign_type="website_modernization",
        target_industry="HVAC",
        heuristic_flags={"campaign": "website_modernization"},
        matcher=None,
    )

    assert "heuristic_flags" in evaluation
    assert "technologies" not in evaluation["heuristic_flags"], (
        "flag OFF must not introduce a 'technologies' key in heuristic_flags"
    )


# ---------------------------------------------------------------------------
# Test 2: flag ON populates technologies from a known fixture
# ---------------------------------------------------------------------------


def test_flag_on_populates_technologies_from_wordpress_fixture(matcher: Matcher):
    """With matcher supplied, wordpress_minimal must yield WordPress detection."""
    expected = load_expected("wordpress_minimal.html")
    lead = load_fixture_lead("wordpress_minimal.html", expected)

    # Bring the lead dict up to the lead_processor.parse shape — the
    # deterministic evaluator wants a few extras the raw_lead_builder
    # doesn't bother with.
    lead.setdefault("phone_number", "")
    lead.setdefault("address", "")
    lead.setdefault("page_title", "Example Blog")
    lead.setdefault("anchor_hrefs", [])
    lead.setdefault("crawl_allowed", True)
    lead.setdefault("crawl_disallowed_reason", "")
    lead.setdefault("is_no_website_opportunity", False)
    lead.setdefault("discovery_source", "brave")
    lead.setdefault("robots_txt", {"exists": False, "body": ""})
    lead.setdefault("sitemap_xml", {"exists": False, "body": ""})

    evaluation = build_lead_evaluation(
        lead,
        campaign_type="website_modernization",
        target_industry="general",
        heuristic_flags={"campaign": "website_modernization"},
        matcher=matcher,
    )

    techs = evaluation["heuristic_flags"].get("technologies")
    assert isinstance(techs, list), "technologies key must be a list when flag is on"
    assert len(techs) > 0, "wordpress_minimal must produce at least one detection"

    # Each entry must be JSON-serializable plain dict (storage requirement).
    for entry in techs:
        assert isinstance(entry, dict)
        assert {"name", "pack", "categories", "confidence", "source"} <= set(entry.keys())

    names = {t["name"] for t in techs}
    assert "WordPress" in names, f"expected WordPress in detections, got {names}"


# ---------------------------------------------------------------------------
# Test 3: matcher exception is swallowed; pipeline still produces evaluation
# ---------------------------------------------------------------------------


class _ExplodingMatcher:
    """Stand-in matcher that always raises. Verifies the try/except guard."""

    def match(self, _raw_lead: dict) -> Any:  # noqa: D401
        raise RuntimeError("simulated matcher failure")


def test_matcher_exception_is_swallowed(caplog):
    """When matcher.match() blows up, evaluation still returns successfully."""
    payload = _baseline_payload()

    with caplog.at_level("ERROR"):
        evaluation = build_lead_evaluation(
            payload,
            campaign_type="website_modernization",
            target_industry="HVAC",
            heuristic_flags={"campaign": "website_modernization"},
            matcher=_ExplodingMatcher(),
        )

    # Evaluation completed — same shape as the deterministic-only path.
    assert "heuristic_flags" in evaluation
    assert "score" in evaluation
    # No technologies key when the matcher failed.
    assert "technologies" not in evaluation["heuristic_flags"]
    # And we logged it for ops visibility.
    assert any(
        "signals_v2 matcher raised" in rec.getMessage() for rec in caplog.records
    ), "expected a matcher-failure log line"


# ---------------------------------------------------------------------------
# Test 4: smoke test — Detection.to_dict() output is JSON-clean
# ---------------------------------------------------------------------------


def test_detections_to_payload_is_json_serializable(matcher: Matcher):
    """Belt-and-suspenders: confirm the storage payload survives json.dumps."""
    import json

    expected = load_expected("wordpress_minimal.html")
    lead = load_fixture_lead("wordpress_minimal.html", expected)
    detections = matcher.match(lead)
    assert detections, "fixture should produce detections"

    from signals.detection import detections_to_payload

    payload = detections_to_payload(detections)
    # Must round-trip through json without raising.
    serialized = json.dumps(payload)
    assert isinstance(serialized, str)
    parsed = json.loads(serialized)
    assert parsed == payload
