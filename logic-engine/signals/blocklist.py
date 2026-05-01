"""False-positive blocklist for the matcher.

Loaded from ``signals/false_positive_blocklist.yaml``. Three operations:

  * ``suppress``   — drop a (name, pack) detection outright.
  * ``downgrade``  — cap a detection's confidence when it was triggered by
    only a configured set of MatchSources (a stronger source still keeps
    full confidence).
  * ``require_corroboration`` — drop a detection if it is the only one in
    the lead, i.e. nothing else corroborates it.

Applied AFTER ``resolver.resolve``. ``Detection`` is frozen so we rebuild
each modified one via ``dataclasses.replace``.

The YAML schema lives in ``false_positive_blocklist.yaml`` next to this
module. Keep it human-curated — sourced from prior-art research
(phase1c-prior-art-validation.md) and growing as we observe FPs in the
wild.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional

import yaml

from .detection import Detection, MatchSource

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DowngradeRule:
    """Cap a detection's confidence when its source matches a narrow set."""

    name: str
    pack: str
    only_source: frozenset[str]   # MatchSource.value strings (e.g. "headers")
    cap_confidence: int
    requires_corroboration: bool = False
    reason: str = ""


@dataclass
class BlocklistConfig:
    suppress_keys: set[tuple[str, str]] = field(default_factory=set)   # (name, pack)
    downgrade_rules: list[DowngradeRule] = field(default_factory=list)
    require_corroboration: set[str] = field(default_factory=set)       # tech names


# Default empty config so callers can always do `apply(detections, config)`
# even before a YAML is loaded.
EMPTY_CONFIG = BlocklistConfig()


# Loader ---------------------------------------------------------------------


def load_blocklist(path: Path) -> BlocklistConfig:
    """Parse the YAML blocklist into a typed config.

    Returns ``EMPTY_CONFIG`` (no-op) if the file is missing or unreadable;
    we do not want a missing blocklist to break the matcher pipeline.
    """
    if not path.exists():
        logger.warning("blocklist: file not found at %s; using empty config", path)
        return EMPTY_CONFIG
    try:
        with path.open(encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("blocklist: failed to parse %s: %s", path, exc)
        return EMPTY_CONFIG

    suppress_keys: set[tuple[str, str]] = set()
    for entry in payload.get("suppress", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        pack = entry.get("pack")
        if isinstance(name, str) and isinstance(pack, str):
            suppress_keys.add((name, pack))

    downgrade_rules: list[DowngradeRule] = []
    for entry in payload.get("downgrade", []) or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        pack = entry.get("pack")
        sources = entry.get("only_source") or []
        cap = entry.get("cap_confidence")
        if not isinstance(name, str) or not isinstance(pack, str):
            continue
        if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
            continue
        try:
            cap_i = max(0, min(100, int(cap)))
        except (TypeError, ValueError):
            continue
        downgrade_rules.append(
            DowngradeRule(
                name=name,
                pack=pack,
                only_source=frozenset(sources),
                cap_confidence=cap_i,
                requires_corroboration=bool(entry.get("requires_corroboration", False)),
                reason=str(entry.get("reason", "")),
            )
        )

    require_corroboration: set[str] = set()
    for entry in payload.get("require_corroboration", []) or []:
        if isinstance(entry, str):
            require_corroboration.add(entry)

    config = BlocklistConfig(
        suppress_keys=suppress_keys,
        downgrade_rules=downgrade_rules,
        require_corroboration=require_corroboration,
    )
    logger.info(
        "blocklist: loaded %d suppress, %d downgrade, %d require_corroboration entries",
        len(config.suppress_keys),
        len(config.downgrade_rules),
        len(config.require_corroboration),
    )
    return config


# Apply ----------------------------------------------------------------------


def _matching_downgrade(d: Detection, config: BlocklistConfig) -> Optional[DowngradeRule]:
    """Return the first downgrade rule whose name+pack+source-set match this detection."""
    for rule in config.downgrade_rules:
        if rule.name != d.name or rule.pack != d.pack:
            continue
        # The rule fires only if the detection's source is INSIDE the rule's
        # narrow source list. A "stronger" source (one not listed) keeps full
        # confidence — that's the whole point of `only_source`.
        if d.source.value in rule.only_source:
            return rule
    return None


def apply(detections: list[Detection], config: BlocklistConfig) -> list[Detection]:
    """Apply suppression, downgrade, and corroboration to a detection list.

    Returns a NEW list. Detections are frozen, so any modified entries are
    rebuilt via ``dataclasses.replace``.
    """
    if not detections:
        return list(detections)

    # 1. Suppress outright.
    after_suppress = [d for d in detections if (d.name, d.pack) not in config.suppress_keys]

    # 2. Downgrade confidence on the rules that match.
    after_downgrade: list[Detection] = []
    downgraded_with_corroboration_req: set[tuple[str, str]] = set()
    for d in after_suppress:
        rule = _matching_downgrade(d, config)
        if rule is None:
            after_downgrade.append(d)
            continue
        new_conf = min(d.confidence, rule.cap_confidence)
        if new_conf != d.confidence:
            after_downgrade.append(replace(d, confidence=new_conf))
        else:
            after_downgrade.append(d)
        if rule.requires_corroboration:
            downgraded_with_corroboration_req.add((d.name, d.pack))

    # 3. Corroboration: drop detections in `require_corroboration` (or those
    # carrying a `requires_corroboration` downgrade rule) when they're the
    # only detection in the entire list.
    other_names = {d.name for d in after_downgrade}
    final: list[Detection] = []
    for d in after_downgrade:
        needs_corroboration = (
            d.name in config.require_corroboration
            or (d.name, d.pack) in downgraded_with_corroboration_req
        )
        if needs_corroboration:
            # "Corroboration" = at least one OTHER detection (different name)
            # is also present. Implied detections count, since they are at
            # least evidence the catalog thinks the parent tech is real.
            others = other_names - {d.name}
            if not others:
                logger.debug(
                    "blocklist: dropping %s/%s (no corroborating detections)",
                    d.name,
                    d.pack,
                )
                continue
        final.append(d)

    return final
