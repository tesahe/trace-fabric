"""Coverage for the Sprint 2 JSON-LD parser (signals/structured_data.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from signals.detection import Detection, MatchSource
from signals.structured_data import (
    extract_local_business_signals,
    parse_jsonld_blocks,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "raw_html"


# ---- parse_jsonld_blocks ---------------------------------------------------


def test_parse_empty_input():
    assert parse_jsonld_blocks("") == []
    assert parse_jsonld_blocks(None) == []  # type: ignore[arg-type]
    assert parse_jsonld_blocks(123) == []  # type: ignore[arg-type]


def test_parse_single_block():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Restaurant","name":"Joe's Diner"}
    </script>
    </head><body></body></html>
    """
    blocks = parse_jsonld_blocks(html)
    assert len(blocks) == 1
    assert blocks[0].get("@type") == "Restaurant"
    assert blocks[0].get("name") == "Joe's Diner"


def test_parse_graph_flattens_children():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@graph":[
      {"@type":"Restaurant","name":"A"},
      {"@type":"Person","name":"Chef Bob"}
    ]}
    </script>
    """
    blocks = parse_jsonld_blocks(html)
    types = {b.get("@type") for b in blocks if isinstance(b, dict)}
    assert "Restaurant" in types
    assert "Person" in types


def test_parse_silently_drops_malformed():
    """A malformed JSON-LD block must not break the parser."""
    html = """
    <script type="application/ld+json">{"@type":"Restaurant" BROKEN }</script>
    <script type="application/ld+json">{"@type":"Plumber","name":"OK"}</script>
    """
    blocks = parse_jsonld_blocks(html)
    types = {b.get("@type") for b in blocks if isinstance(b, dict)}
    assert types == {"Plumber"}


# ---- extract_local_business_signals ----------------------------------------


def test_extract_emits_business_type_detection():
    html = """
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Plumber","name":"Acme Plumbing",
     "telephone":"+1-415-555-0001","address":{"streetAddress":"1 Main St"}}
    </script>
    """
    detections = extract_local_business_signals(html)
    names = [d.name for d in detections]
    assert "Schema.org: Plumber" in names
    # Sub-property detections also surface.
    assert "Schema.org: has_telephone" in names
    assert "Schema.org: has_address" in names
    # Source is correctly tagged.
    biz = [d for d in detections if d.name == "Schema.org: Plumber"][0]
    assert biz.source == MatchSource.STRUCTURED_DATA
    assert biz.pack == "structured_data"
    assert biz.confidence == 90


def test_extract_handles_no_local_business():
    """Schema.org Person should NOT produce a LocalBusiness detection."""
    html = """
    <script type="application/ld+json">
    {"@type":"Person","name":"Solo Author"}
    </script>
    """
    detections = extract_local_business_signals(html)
    assert detections == []


def test_extract_picks_specific_subtype_over_localbusiness():
    html = """
    <script type="application/ld+json">
    {"@type":["LocalBusiness","Restaurant"],"name":"Joe's"}
    </script>
    """
    detections = extract_local_business_signals(html)
    names = [d.name for d in detections]
    assert "Schema.org: Restaurant" in names
    # Generic LocalBusiness should NOT also fire when a specific subtype matches.
    assert "Schema.org: LocalBusiness" not in names


def test_extract_dedupes_repeated_blocks():
    html = """
    <script type="application/ld+json">
    {"@type":"Restaurant","name":"Joe's","telephone":"+1-415-555-0001"}
    </script>
    <script type="application/ld+json">
    {"@type":"Restaurant","name":"Joe's","telephone":"+1-415-555-0002"}
    </script>
    """
    detections = extract_local_business_signals(html)
    type_hits = [d for d in detections if d.name == "Schema.org: Restaurant"]
    assert len(type_hits) == 1, "deduped LocalBusiness type detections expected"


def test_extract_returns_empty_on_no_jsonld():
    html = "<html><head></head><body><p>No schema here.</p></body></html>"
    assert extract_local_business_signals(html) == []


def test_extract_audit_field_populated():
    html = """
    <script type="application/ld+json">
    {"@type":"Dentist","name":"Dr Smile","aggregateRating":{"ratingValue":"4.8","reviewCount":"42"}}
    </script>
    """
    detections = extract_local_business_signals(html)
    biz = [d for d in detections if d.name == "Schema.org: Dentist"][0]
    assert biz.matched_field.startswith("jsonld_blocks[")
    assert biz.matched_field.endswith(".@type")
    assert biz.pattern_id.startswith("structured_data:LocalBusiness:Dentist")
    rating = [d for d in detections if d.name == "Schema.org: has_aggregateRating"][0]
    assert "ratingValue" in rating.matched_value or "4.8" in rating.matched_value
