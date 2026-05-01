"""Implies / requires / excludes graph resolver.

Wappalyzer technology entries describe relationships between techs:

- ``excludes``: drop any matched tech named in this list.
- ``requires``: keep this tech only if every named tech is also matched.
- ``requiresCategory``: keep this tech only if at least one matched tech is
  in the named category.
- ``implies``: emit synthetic detections for every implied tech, even if no
  raw pattern matched it.

Order of operations matters. We do excludes first (to shrink the working
set), then requires (to drop now-orphaned techs), then implies (to grow
back the inferred ones), then a final dedup pass keyed on (name, pack).

The resolver is deliberately a pure function over its inputs. The matcher
calls it once per scan with the matched detections and the loaded
catalog.
"""

from __future__ import annotations

import logging
from typing import Iterable

from .detection import Detection, MatchSource
from .loader import Technology

logger = logging.getLogger(__name__)


def _by_name(detections: Iterable[Detection]) -> dict[str, list[Detection]]:
    out: dict[str, list[Detection]] = {}
    for d in detections:
        out.setdefault(d.name, []).append(d)
    return out


def _matched_categories(detections: Iterable[Detection]) -> set[int]:
    cats: set[int] = set()
    for d in detections:
        cats.update(d.categories)
    return cats


def _apply_excludes(
    detections: list[Detection], catalog: dict[str, Technology]
) -> list[Detection]:
    """Drop any detection whose tech is named in another matched tech's ``excludes``."""
    excluded: set[str] = set()
    for d in detections:
        tech = catalog.get(d.name)
        if tech is None:
            continue
        for ex_name in tech.excludes:
            excluded.add(ex_name)
    if not excluded:
        return detections
    pruned = [d for d in detections if d.name not in excluded]
    if len(pruned) != len(detections):
        logger.debug("resolver: excludes dropped %d detections", len(detections) - len(pruned))
    return pruned


def _apply_requires(
    detections: list[Detection], catalog: dict[str, Technology]
) -> list[Detection]:
    """Drop detections whose ``requires`` / ``requiresCategory`` aren't satisfied.

    We iterate to a fixed point because dropping one tech may invalidate
    another that required it. Bounded at 5 iterations to avoid pathological
    catalogs producing infinite loops; in practice 1-2 passes is enough.
    """
    current = list(detections)
    for _ in range(5):
        names = {d.name for d in current}
        cats = _matched_categories(current)
        kept: list[Detection] = []
        for d in current:
            tech = catalog.get(d.name)
            if tech is None:
                kept.append(d)
                continue
            if any(req not in names for req in tech.requires):
                continue
            if tech.requires_category and not any(rc in cats for rc in tech.requires_category):
                continue
            kept.append(d)
        if len(kept) == len(current):
            return kept
        current = kept
    return current


def _apply_implies(
    detections: list[Detection], catalog: dict[str, Technology]
) -> list[Detection]:
    """Emit synthetic Detection objects for every implied tech.

    Confidence for an implied tech: take the parent detection's confidence,
    then attenuate to 50 if not already lower (we don't trust transitive
    implies as much as direct hits). The deduplication pass later keeps the
    highest-confidence entry per (name, pack), so a real direct match
    always wins over the implied placeholder.
    """
    existing_names = {d.name for d in detections}
    inferred: list[Detection] = []
    seen_implied: set[str] = set()

    for d in detections:
        tech = catalog.get(d.name)
        if tech is None:
            continue
        for imp_name in tech.implies:
            if imp_name in existing_names or imp_name in seen_implied:
                continue
            imp_tech = catalog.get(imp_name)
            inferred_conf = min(d.confidence, 50)
            inferred.append(
                Detection(
                    name=imp_name,
                    pack=imp_tech.pack if imp_tech else d.pack,
                    categories=imp_tech.categories if imp_tech else (),
                    confidence=inferred_conf,
                    version=None,
                    source=MatchSource.IMPLIED,
                    matched_field=f"implied_by:{d.name}",
                    matched_value=f"implied by detection of {d.name}",
                    pattern_id=f"implied:{d.name}->{imp_name}",
                    cpe=imp_tech.cpe if imp_tech else None,
                    pricing=imp_tech.pricing if imp_tech else (),
                    saas=imp_tech.saas if imp_tech else False,
                    oss=imp_tech.oss if imp_tech else False,
                    website=imp_tech.website if imp_tech else None,
                )
            )
            seen_implied.add(imp_name)

    return list(detections) + inferred


def _dedup_keep_best(detections: list[Detection]) -> list[Detection]:
    """Collapse to one Detection per (name, pack), keeping highest confidence.

    Ties on confidence are broken by preferring a concrete source over the
    synthetic ``IMPLIED`` source, then by version-presence (a detection
    that pinned a version is more useful than one that didn't), then by
    insertion order.
    """
    best: dict[tuple[str, str], Detection] = {}
    for d in detections:
        key = (d.name, d.pack)
        prior = best.get(key)
        if prior is None:
            best[key] = d
            continue
        if d.confidence > prior.confidence:
            best[key] = d
        elif d.confidence == prior.confidence:
            prior_synthetic = prior.source == MatchSource.IMPLIED
            d_synthetic = d.source == MatchSource.IMPLIED
            if prior_synthetic and not d_synthetic:
                best[key] = d
            elif prior_synthetic == d_synthetic and prior.version is None and d.version is not None:
                best[key] = d
    return list(best.values())


def resolve(
    raw_detections: list[Detection], catalog: dict[str, Technology]
) -> list[Detection]:
    """Resolve raw matcher output into the final detection list.

    Order: excludes -> requires -> implies -> dedup. See module docstring
    for why each step happens when it does.
    """
    if not raw_detections:
        return []
    after_excludes = _apply_excludes(raw_detections, catalog)
    after_requires = _apply_requires(after_excludes, catalog)
    after_implies = _apply_implies(after_requires, catalog)
    return _dedup_keep_best(after_implies)
