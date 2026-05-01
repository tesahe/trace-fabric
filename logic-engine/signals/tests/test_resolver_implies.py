"""Focused tests for the implies / requires / requiresCategory / excludes
resolver. We construct miniature catalogs in-memory rather than touching
the real wappalyzer pack so every test is hermetic and fast.
"""

from __future__ import annotations

from signals.detection import Detection, MatchSource
from signals.loader import Technology
from signals.resolver import resolve


def _det(name: str, pack: str = "wappalyzer", conf: int = 100, cats=()) -> Detection:
    """Build a Detection with the audit-trail fields filled with placeholders."""
    return Detection(
        name=name,
        pack=pack,
        categories=tuple(cats),
        confidence=conf,
        version=None,
        source=MatchSource.HTML,
        matched_field="raw_html",
        matched_value="<test>",
        pattern_id=f"test:{name}",
    )


def _tech(
    name: str,
    pack: str = "wappalyzer",
    cats=(),
    implies=None,
    requires=None,
    excludes=None,
    requires_category=None,
) -> Technology:
    return Technology(
        name=name,
        pack=pack,
        categories=tuple(cats),
        pricing=(),
        saas=False,
        oss=False,
        website=None,
        cpe=None,
        patterns_by_source={},
        implies=list(implies or []),
        requires=list(requires or []),
        requires_category=list(requires_category or []),
        excludes=list(excludes or []),
    )


def test_wordpress_implies_php_and_mysql():
    """A direct WordPress hit should produce synthetic PHP + MySQL detections."""
    catalog = {
        "WordPress": _tech("WordPress", cats=(1,), implies=["PHP", "MySQL"]),
        "PHP": _tech("PHP", cats=(27,)),
        "MySQL": _tech("MySQL", cats=(34,)),
    }
    detections = [_det("WordPress")]
    resolved = resolve(detections, catalog)
    names = {d.name for d in resolved}
    assert "WordPress" in names
    assert "PHP" in names
    assert "MySQL" in names
    # Implied detections carry source=IMPLIED.
    php = next(d for d in resolved if d.name == "PHP")
    assert php.source == MatchSource.IMPLIED


def test_excludes_drops_other_tech():
    """A match on TechA whose excludes list names TechB drops TechB."""
    catalog = {
        "TechA": _tech("TechA", excludes=["TechB"]),
        "TechB": _tech("TechB"),
    }
    resolved = resolve([_det("TechA"), _det("TechB")], catalog)
    names = {d.name for d in resolved}
    assert "TechA" in names
    assert "TechB" not in names


def test_requires_drops_when_dep_absent():
    """Tech with `requires: [TechZ]` is dropped if TechZ never matched."""
    catalog = {
        "TechY": _tech("TechY", requires=["TechZ"]),
        "TechZ": _tech("TechZ"),
    }
    resolved = resolve([_det("TechY")], catalog)
    assert "TechY" not in {d.name for d in resolved}


def test_requires_keeps_when_dep_present():
    catalog = {
        "TechY": _tech("TechY", requires=["TechZ"]),
        "TechZ": _tech("TechZ"),
    }
    resolved = resolve([_det("TechY"), _det("TechZ")], catalog)
    names = {d.name for d in resolved}
    assert "TechY" in names
    assert "TechZ" in names


def test_requires_category_gate():
    """`requires_category` keeps tech only if some matched tech has that cat."""
    catalog = {
        "Plugin": _tech("Plugin", requires_category=[1]),
        "CMS": _tech("CMS", cats=(1,)),
    }
    # Without a cat-1 detection: Plugin gets dropped.
    resolved_alone = resolve([_det("Plugin")], catalog)
    assert "Plugin" not in {d.name for d in resolved_alone}
    # With a cat-1 detection: Plugin survives.
    resolved_pair = resolve([_det("Plugin"), _det("CMS", cats=(1,))], catalog)
    assert "Plugin" in {d.name for d in resolved_pair}


def test_requires_iterates_to_fixed_point():
    """A -> requires B -> requires C. Drop C and both A and B should fall."""
    catalog = {
        "A": _tech("A", requires=["B"]),
        "B": _tech("B", requires=["C"]),
    }
    resolved = resolve([_det("A"), _det("B")], catalog)
    names = {d.name for d in resolved}
    # B requires C (absent) -> B drops; A then requires the dropped B -> A drops.
    assert names == set()


def test_dedup_keeps_highest_confidence():
    """Two detections of the same (name, pack); higher confidence wins."""
    catalog = {"X": _tech("X")}
    low = _det("X", conf=20)
    high = _det("X", conf=90)
    resolved = resolve([low, high], catalog)
    assert len(resolved) == 1
    assert resolved[0].confidence == 90
