"""Focused tests for the false-positive blocklist module.

We construct Detection objects directly rather than going through the
matcher so the tests are isolated and don't depend on which Wappalyzer
sigs happen to be present in the loaded pack today.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from signals.blocklist import (
    BlocklistConfig,
    DowngradeRule,
    apply,
    load_blocklist,
)
from signals.detection import Detection, MatchSource


def _det(
    name: str,
    pack: str = "wappalyzer",
    source: MatchSource = MatchSource.HTML,
    confidence: int = 100,
) -> Detection:
    return Detection(
        name=name,
        pack=pack,
        categories=(),
        confidence=confidence,
        version=None,
        source=source,
        matched_field="raw_html",
        matched_value="<test>",
        pattern_id=f"test:{name}",
    )


# Suppression ----------------------------------------------------------------


def test_suppress_drops_dont_check_sentinel():
    """The retire.js 'dont check' sentinel never escapes the matcher."""
    config = BlocklistConfig(suppress_keys={("dont check", "retirejs")})
    raw = [_det("dont check", pack="retirejs"), _det("WordPress")]
    out = apply(raw, config)
    assert ("dont check", "retirejs") not in {(d.name, d.pack) for d in out}
    assert ("WordPress", "wappalyzer") in {(d.name, d.pack) for d in out}


# Downgrade ------------------------------------------------------------------


def test_cloudflare_headers_only_gets_capped():
    """Cloudflare from headers source gets confidence capped to 30."""
    rule = DowngradeRule(
        name="Cloudflare",
        pack="wappalyzer",
        only_source=frozenset({"headers"}),
        cap_confidence=30,
    )
    config = BlocklistConfig(downgrade_rules=[rule])
    raw = [_det("Cloudflare", source=MatchSource.HEADERS, confidence=100)]
    out = apply(raw, config)
    assert len(out) == 1
    assert out[0].confidence == 30


def test_cloudflare_html_source_keeps_full_confidence():
    """A Cloudflare hit from a stronger source (html) is NOT downgraded."""
    rule = DowngradeRule(
        name="Cloudflare",
        pack="wappalyzer",
        only_source=frozenset({"headers"}),
        cap_confidence=30,
    )
    config = BlocklistConfig(downgrade_rules=[rule])
    raw = [_det("Cloudflare", source=MatchSource.HTML, confidence=100)]
    out = apply(raw, config)
    assert out[0].confidence == 100


def test_downgrade_does_not_raise_confidence():
    """Cap is a ceiling — a detection already below the cap is left alone."""
    rule = DowngradeRule(
        name="GA",
        pack="wappalyzer",
        only_source=frozenset({"script_src"}),
        cap_confidence=60,
    )
    config = BlocklistConfig(downgrade_rules=[rule])
    raw = [_det("GA", source=MatchSource.SCRIPT_SRC, confidence=20)]
    out = apply(raw, config)
    assert out[0].confidence == 20  # untouched


# Corroboration --------------------------------------------------------------


def test_jquery_alone_gets_dropped_when_corroboration_required():
    """A lone jQuery detection in `require_corroboration` is dropped."""
    config = BlocklistConfig(require_corroboration={"jQuery"})
    raw = [_det("jQuery", source=MatchSource.SCRIPT_SRC)]
    out = apply(raw, config)
    assert out == []


def test_jquery_with_other_detections_survives():
    """jQuery in the same lead as other detections passes corroboration."""
    config = BlocklistConfig(require_corroboration={"jQuery"})
    raw = [
        _det("jQuery", source=MatchSource.SCRIPT_SRC),
        _det("WordPress", source=MatchSource.META),
        _det("Google Analytics", source=MatchSource.SCRIPT_SRC),
    ]
    out = apply(raw, config)
    names = {d.name for d in out}
    assert "jQuery" in names
    assert "WordPress" in names


def test_downgrade_rule_with_corroboration_flag():
    """A DowngradeRule.requires_corroboration=True implies corroboration too."""
    rule = DowngradeRule(
        name="jQuery",
        pack="wappalyzer",
        only_source=frozenset({"script_src", "html"}),
        cap_confidence=40,
        requires_corroboration=True,
    )
    config = BlocklistConfig(downgrade_rules=[rule])
    raw = [_det("jQuery", source=MatchSource.SCRIPT_SRC, confidence=100)]
    out = apply(raw, config)
    assert out == []


# Loader ---------------------------------------------------------------------


def test_load_blocklist_from_real_yaml():
    """The shipped YAML loads without error and contains the known sentinel."""
    path = Path(__file__).resolve().parents[1] / "false_positive_blocklist.yaml"
    config = load_blocklist(path)
    assert ("dont check", "retirejs") in config.suppress_keys
    assert any(r.name == "Cloudflare" for r in config.downgrade_rules)
    assert "jQuery" in config.require_corroboration


def test_load_blocklist_missing_file_returns_empty(tmp_path):
    """Missing YAML must NOT raise — matcher startup needs to be robust."""
    config = load_blocklist(tmp_path / "does_not_exist.yaml")
    assert config.suppress_keys == set()
    assert config.downgrade_rules == []
    assert config.require_corroboration == set()


# Integration with Matcher ---------------------------------------------------


def test_matcher_apply_blocklist_flag(matcher_no_blocklist):
    """Matcher(apply_blocklist=False) uses the empty config."""
    assert matcher_no_blocklist.apply_blocklist is False
    assert matcher_no_blocklist.blocklist_config.suppress_keys == set()


def test_matcher_default_loads_blocklist(matcher):
    """Matcher() with default args loads the YAML."""
    assert matcher.apply_blocklist is True
    # The shipped YAML has at least the dont-check suppress and one downgrade.
    assert ("dont check", "retirejs") in matcher.blocklist_config.suppress_keys
    assert len(matcher.blocklist_config.downgrade_rules) >= 1
