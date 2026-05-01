"""Coverage for the Sprint 2 weighted scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from scoring import (
    ScoreContribution,
    ScoreResult,
    WeightConfig,
    load_all_campaign_configs,
    score_lead,
)
from signals.detection import Detection, MatchSource


CAMPAIGNS_DIR = Path(__file__).resolve().parents[2] / "campaigns"


@pytest.fixture(scope="module")
def configs() -> dict:
    cfgs = load_all_campaign_configs(CAMPAIGNS_DIR)
    assert cfgs, f"no campaign configs loaded from {CAMPAIGNS_DIR}"
    return cfgs


def _det(name: str, pack: str = "wappalyzer") -> Detection:
    return Detection(
        name=name,
        pack=pack,
        categories=(),
        confidence=100,
        version=None,
        source=MatchSource.HTML,
        matched_field="raw_html",
        matched_value="",
        pattern_id=f"test:{name}",
    )


# ---- WeightConfig load -----------------------------------------------------


def test_load_all_three_campaign_configs(configs):
    assert "website_modernization" in configs
    assert "voice_ai_agent" in configs
    assert "smma" in configs


def test_weight_config_round_trip_fields(configs):
    cfg = configs["website_modernization"]
    assert cfg.version == 1
    assert cfg.score_baseline == 0.30
    assert cfg.qualification_threshold == 0.55
    assert "WordPress:wappalyzer" in cfg.weights_universal["detections"]


# ---- Universal weights -----------------------------------------------------


def test_baseline_only_score_no_signals(configs):
    result = score_lead(
        detections=[],
        existing_signals={},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert result.score == pytest.approx(0.30)
    assert result.is_qualified is False


def test_universal_detection_weight_fires(configs):
    result = score_lead(
        detections=[_det("WordPress")],
        existing_signals={},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    # YAML weights are percentage points: WordPress weight 15 -> +0.15 contribution
    # baseline 0.30 + 0.15 = 0.45
    assert result.score == pytest.approx(0.45)
    paths = {c.rule_path for c in result.contributions}
    assert "weights_universal.detections.WordPress:wappalyzer" in paths


def test_universal_existing_signal_weight_fires(configs):
    result = score_lead(
        detections=[],
        existing_signals={"no_viewport": True},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    # baseline 0.30 + no_viewport (weight 25 -> +0.25) = 0.55
    assert result.score == pytest.approx(0.55)
    assert any(
        c.rule_path == "weights_universal.signals_from_existing_evaluator.no_viewport"
        for c in result.contributions
    )


def test_no_x_translation_from_has_x(configs):
    """has_viewport=False should satisfy a 'no_viewport' weight."""
    result = score_lead(
        detections=[],
        existing_signals={"has_viewport": False},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert any(
        c.rule_path == "weights_universal.signals_from_existing_evaluator.no_viewport"
        for c in result.contributions
    )


# ---- Industry overrides ----------------------------------------------------


def test_industry_override_stacks_with_universal(configs):
    """Salon detection 'Mindbody:local_biz' is not a reject for SMMA but
    is a -8 industry weight. Verify it lands as an additive contribution."""
    result = score_lead(
        detections=[_det("Mindbody", pack="local_biz")],
        existing_signals={},
        campaign="smma",
        industry="salon",
        location="",
        weight_configs=configs,
    )
    industry_contribs = [c for c in result.contributions if c.source == "industry:salon"]
    assert any(c.rule_path.endswith("Mindbody:local_biz") for c in industry_contribs)


def test_industry_unknown_does_not_break(configs):
    result = score_lead(
        detections=[],
        existing_signals={},
        campaign="website_modernization",
        industry="ufologist",
        location="",
        weight_configs=configs,
    )
    assert result.is_rejected is False
    assert result.score == pytest.approx(0.30)


# ---- Region multipliers ----------------------------------------------------


def test_high_cost_metro_multiplier_applied(configs):
    base = score_lead(
        detections=[],
        existing_signals={"no_viewport": True},
        campaign="website_modernization",
        industry="",
        location="dallas, tx",
        weight_configs=configs,
    )
    sf = score_lead(
        detections=[],
        existing_signals={"no_viewport": True},
        campaign="website_modernization",
        industry="",
        location="San Francisco, CA",
        weight_configs=configs,
    )
    # Weights are percentage points: no_viewport=25 -> +0.25 contribution.
    # base (no region): 0.30 + 0.25 = 0.55
    # sf: multiplier applies to the entire accumulated raw score
    #     (0.30 + 0.25) * 1.2 = 0.66
    # See test_region_multiplier_visible_when_not_clamped below for the smaller-signal variant.
    assert base.score == pytest.approx(0.55)
    assert sf.score == pytest.approx(0.66)
    # Region match recorded.
    assert "high_cost_metros" in sf.region_matches
    assert "high_cost_metros" not in base.region_matches


def test_region_multiplier_visible_when_not_clamped(configs):
    """Use a small signal so the 1.2x multiplier doesn't get hidden by clamp."""
    sf = score_lead(
        detections=[],
        existing_signals={"no_page_title": True},  # +8
        campaign="website_modernization",
        industry="",
        location="boston metro area",
        weight_configs=configs,
    )
    # baseline 0.30 + 0.08 = 0.38; * 1.2 = 0.456
    assert sf.score == pytest.approx(0.456, abs=1e-3)
    assert "high_cost_metros" in sf.region_matches


# ---- Rejection gates -------------------------------------------------------


def test_universal_reject_on_squarespace(configs):
    result = score_lead(
        detections=[_det("Squarespace")],
        existing_signals={},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert result.is_rejected
    assert result.score == 0.0
    assert "Squarespace:wappalyzer" in (result.rejection_reason or "")


def test_industry_reject_on_servicetitan_for_plumbing(configs):
    result = score_lead(
        detections=[_det("ServiceTitan", pack="local_biz")],
        existing_signals={},
        campaign="website_modernization",
        industry="plumbing",
        location="",
        weight_configs=configs,
    )
    assert result.is_rejected
    assert "ServiceTitan:local_biz" in (result.rejection_reason or "")


def test_industry_reject_does_not_fire_for_other_industries(configs):
    result = score_lead(
        detections=[_det("ServiceTitan", pack="local_biz")],
        existing_signals={},
        campaign="website_modernization",
        industry="restaurant",
        location="",
        weight_configs=configs,
    )
    # ServiceTitan reject is plumbing/hvac-only.
    assert result.is_rejected is False


def test_universal_signal_reject_fires(configs):
    result = score_lead(
        detections=[],
        existing_signals={"is_no_website_opportunity": True},
        campaign="smma",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert result.is_rejected
    assert "is_no_website_opportunity" in (result.rejection_reason or "")


# ---- Audit trail / contributions -------------------------------------------


def test_contributions_are_traceable(configs):
    result = score_lead(
        detections=[_det("WordPress"), _det("Mindbody", pack="local_biz")],
        existing_signals={"no_form": True, "stale_copyright_2021": True},
        campaign="website_modernization",
        industry="salon",
        location="seattle, wa",
        weight_configs=configs,
    )
    # baseline + universal WordPress + universal no_form + industry Mindbody (-20) + region SF
    sources = {c.source for c in result.contributions}
    assert "baseline" in sources
    assert "universal" in sources
    assert "industry:salon" in sources
    assert "region:high_cost_metros" in sources
    assert all(c.rule_path for c in result.contributions)


# ---- Fallback / unknown campaign -------------------------------------------


def test_unknown_campaign_returns_neutral(configs):
    result = score_lead(
        detections=[_det("WordPress")],
        existing_signals={},
        campaign="not_a_real_campaign",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert result.score == pytest.approx(0.5)
    assert "no weight config" in (result.note or "")


def test_to_dict_round_trip(configs):
    result = score_lead(
        detections=[_det("WordPress")],
        existing_signals={"no_viewport": True},
        campaign="website_modernization",
        industry="salon",
        location="boston",
        weight_configs=configs,
    )
    d = result.to_dict()
    assert isinstance(d["score"], float)
    assert d["campaign"] == "website_modernization"
    assert d["industry"] == "salon"
    assert isinstance(d["contributions"], list)
    assert all("rule_path" in c for c in d["contributions"])


# ---- Detection key serialization tolerance ---------------------------------


def test_dict_detections_also_work(configs):
    """Scorer accepts pre-serialized detection dicts (DB-payload shape)."""
    result = score_lead(
        detections=[{"name": "WordPress", "pack": "wappalyzer"}],
        existing_signals={},
        campaign="website_modernization",
        industry="",
        location="",
        weight_configs=configs,
    )
    assert any(
        c.rule_path == "weights_universal.detections.WordPress:wappalyzer"
        for c in result.contributions
    )
