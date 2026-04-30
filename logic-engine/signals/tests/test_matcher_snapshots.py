"""Snapshot tests over the 12 hand-crafted fixture HTMLs.

For each fixture we assert:

  * Every entry in ``must_detect`` IS present (with min_confidence honored).
  * Every entry in ``must_not_detect`` is NOT present.

We deliberately do NOT enumerate every detection — the matcher will often
catch additional implied techs which is fine. The contract is "the techs
we declared are detected, the techs we declared are not detected."
"""

from __future__ import annotations

import pytest

from .conftest import load_expected, load_fixture_lead

FIXTURE_NAMES = [
    "wordpress_minimal.html",
    "squarespace_modern.html",
    "shopify_store.html",
    "wix_classic.html",
    "hubspot_landing.html",
    "calendly_inline.html",
    "mailchimp_signup.html",
    "stripe_checkout.html",
    "cloudflare_only.html",
    "kitchen_sink.html",
    "parked_domain.html",
    "static_brochure.html",
]


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_fixture_snapshot(fixture_name, matcher):
    expected = load_expected(fixture_name)
    lead = load_fixture_lead(fixture_name, expected=expected)
    detections = matcher.match(lead)

    detected_index = {(d.name, d.pack): d for d in detections}
    detected_names = {d.name for d in detections}

    # 1. Every must_detect entry shows up.
    for must in expected.get("must_detect", []):
        key = (must["name"], must["pack"])
        assert key in detected_index, (
            f"{fixture_name}: missing required detection {must['name']} ({must['pack']}). "
            f"Got: {sorted(detected_names)}"
        )
        if "min_confidence" in must:
            d = detected_index[key]
            assert d.confidence >= must["min_confidence"], (
                f"{fixture_name}: {must['name']} confidence {d.confidence} "
                f"< required {must['min_confidence']}"
            )

    # 2. Nothing in must_not_detect shows up.
    for forbidden in expected.get("must_not_detect", []):
        assert forbidden not in detected_names, (
            f"{fixture_name}: false positive {forbidden} (got: {sorted(detected_names)})"
        )


def test_negative_controls_have_few_detections(matcher):
    """Sanity: parked + brochure + cloudflare-only should each produce
    nearly nothing. Cap is loose (<=2) to leave room for catalog drift."""
    for name in ("parked_domain.html", "static_brochure.html", "cloudflare_only.html"):
        expected = load_expected(name)
        lead = load_fixture_lead(name, expected=expected)
        detections = matcher.match(lead)
        assert len(detections) <= 2, (
            f"{name}: expected near-zero detections, got "
            f"{[d.name for d in detections]}"
        )
