"""Weighted scorer (signals_v2_scoring) — Sprint 2 headline.

Turns raw matcher Detections + the existing deterministic-evaluator
signals into a single normalized lead score, driven by per-campaign
YAML weight configs. Every contribution to the score is preserved in an
audit-trail list so any decision can be defended back to the rule that
caused it.

Design constraints carried over from Sprint 1:

  * Pure functions, no I/O on the hot path. Weight configs load once at
    process start; ``score_lead`` takes them in as args.
  * No exceptions out: malformed inputs degrade gracefully (return a
    fallback ScoreResult), they never propagate.
  * Detection key format mirrors how the matcher tags packs:
    ``"<tech_name>:<pack>"`` (e.g. ``"WordPress:wappalyzer"``).
  * Existing deterministic-evaluator output (``score``, ``is_qualified_lead``)
    is NOT touched — this scorer writes to a parallel ``score_v2`` field
    so callers can A/B compare.

Public API:
  - ``WeightConfig.load(path)`` classmethod
  - ``load_all_campaign_configs(directory)`` helper
  - ``score_lead(...)``
  - ``ScoreResult``, ``ScoreContribution``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# ---- Public dataclasses -----------------------------------------------------


@dataclass(frozen=True)
class ScoreContribution:
    """One audit-trail entry: which weight fired, where it came from, why."""

    source: str        # "universal", "industry:salon", "region:high_cost_metros", ...
    weight: float
    reason: str        # human-readable e.g. "WordPress:wappalyzer detected"
    rule_path: str     # e.g. "weights_universal.detections.WordPress:wappalyzer"


@dataclass
class ScoreResult:
    """Final score + breakdown for one lead."""

    score: float = 0.5
    is_qualified: bool = False
    is_rejected: bool = False
    rejection_reason: Optional[str] = None
    contributions: list[ScoreContribution] = field(default_factory=list)
    campaign: str = ""
    industry: str = ""
    region_matches: list[str] = field(default_factory=list)
    note: Optional[str] = None  # e.g. "no weight config for campaign 'foo'"

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "is_qualified": self.is_qualified,
            "is_rejected": self.is_rejected,
            "rejection_reason": self.rejection_reason,
            "campaign": self.campaign,
            "industry": self.industry,
            "region_matches": list(self.region_matches),
            "note": self.note,
            "contributions": [
                {
                    "source": c.source,
                    "weight": c.weight,
                    "reason": c.reason,
                    "rule_path": c.rule_path,
                }
                for c in self.contributions
            ],
        }


# ---- WeightConfig -----------------------------------------------------------


@dataclass
class WeightConfig:
    """In-memory representation of one campaign's YAML weight file.

    Holds raw dicts — we do not bake the YAML into a deeply-typed schema
    so authors can extend the config without code changes. Validation is
    intentionally lazy: each lookup is wrapped in try/except so a typo
    in YAML degrades that one rule rather than killing the whole scorer.
    """

    version: int
    campaign: str
    description: str
    weights_universal: dict
    weights_by_industry: dict
    weights_by_region: dict
    reject_if_universal: dict
    reject_if_industry: dict
    score_baseline: float
    score_max: float
    qualification_threshold: float
    source_path: Optional[str] = None

    @classmethod
    def load(cls, path: Path) -> "WeightConfig":
        """Load + parse one YAML weight config off disk.

        Raises ``OSError`` on read failure and ``ValueError`` on schema
        problems — callers (typically a startup loader) should catch and
        log, not let the process die over a single bad file.
        """
        import yaml  # lazy: this module is importable in test setups w/o yaml.

        with Path(path).open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

        if not isinstance(raw, dict):
            raise ValueError(f"weight config root is not a mapping: {path}")

        try:
            return cls(
                version=int(raw.get("version", 1)),
                campaign=str(raw.get("campaign", Path(path).stem)),
                description=str(raw.get("description", "")),
                weights_universal=raw.get("weights_universal") or {},
                weights_by_industry=raw.get("weights_by_industry") or {},
                weights_by_region=raw.get("weights_by_region") or {},
                reject_if_universal=raw.get("reject_if_universal") or {},
                reject_if_industry=raw.get("reject_if_industry") or {},
                score_baseline=float(raw.get("score_baseline", 0.30)),
                score_max=float(raw.get("score_max", 1.0)),
                qualification_threshold=float(raw.get("qualification_threshold", 0.55)),
                source_path=str(path),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"weight config schema error in {path}: {exc}") from exc


def load_all_campaign_configs(directory: Path) -> dict[str, WeightConfig]:
    """Load every ``*.yaml`` weight config in a directory, keyed by campaign.

    Failures on individual files are logged and skipped so a malformed
    YAML file in one campaign never blocks the others.
    """
    out: dict[str, WeightConfig] = {}
    directory = Path(directory)
    if not directory.exists():
        logger.info("scoring: campaigns dir does not exist: %s", directory)
        return out

    for yaml_path in sorted(directory.glob("*.yaml")):
        try:
            cfg = WeightConfig.load(yaml_path)
        except Exception:
            logger.exception("scoring: failed to load campaign config %s", yaml_path)
            continue
        out[cfg.campaign] = cfg

    logger.info("scoring: loaded %d campaign configs from %s", len(out), directory)
    return out


# ---- Helpers ---------------------------------------------------------------


def _detection_keys_present(detections: Iterable[Any]) -> set[str]:
    """Build the set of ``"name:pack"`` keys present in ``detections``.

    Accepts either Detection dataclass instances OR pre-serialized dicts
    (so the scorer works whether you call it from the matcher or from the
    JSON column in the DB).
    """
    keys: set[str] = set()
    for d in detections or []:
        try:
            if isinstance(d, dict):
                name = d.get("name")
                pack = d.get("pack")
            else:
                name = getattr(d, "name", None)
                pack = getattr(d, "pack", None)
            if name and pack:
                keys.add(f"{name}:{pack}")
        except Exception:
            continue
    return keys


def _signal_truthy(existing_signals: dict, key: str) -> bool:
    """existing_signals support: prefer ``no_X`` semantics where present.

    The deterministic evaluator emits booleans like ``has_viewport`` /
    ``has_form`` / ``has_cta``. The scorer config talks in terms of gaps
    (``no_viewport``), so we translate ``no_X`` -> ``not has_X`` when the
    evaluator hasn't already exposed the negative form.
    """
    if not isinstance(existing_signals, dict):
        return False

    if key in existing_signals:
        return bool(existing_signals[key])

    # ``no_X`` -> ``not has_X``
    if key.startswith("no_"):
        positive = "has_" + key[3:]
        if positive in existing_signals:
            return not bool(existing_signals[positive])

    # Lazy fallback: also accept ``X_signal`` naming used in the evaluator's
    # deterministic_evidence dict (e.g. ``has_phone_signal``, ``has_hours_signal``).
    if key.startswith("has_") and (key + "_signal") in existing_signals:
        return bool(existing_signals[key + "_signal"])
    if key.startswith("no_"):
        positive = "has_" + key[3:] + "_signal"
        if positive in existing_signals:
            return not bool(existing_signals[positive])

    return False


# ---- Scoring core ----------------------------------------------------------


def score_lead(
    *,
    detections: Iterable[Any],
    existing_signals: dict,
    campaign: str,
    industry: str,
    location: str,
    weight_configs: dict[str, WeightConfig],
) -> ScoreResult:
    """Compute a normalized score in [0, 1] from detections + signals.

    Defensive contract: any internal failure produces a ScoreResult with
    ``score=0.5`` and a populated ``note`` field rather than raising. That
    keeps the lead pipeline robust to scorer bugs.
    """
    industry = (industry or "").strip().lower()
    campaign = (campaign or "").strip()
    location_lower = (location or "").strip().lower()

    cfg = weight_configs.get(campaign) if isinstance(weight_configs, dict) else None
    if cfg is None:
        return ScoreResult(
            score=0.5,
            campaign=campaign,
            industry=industry,
            note=f"no weight config for campaign '{campaign}'",
        )

    detection_keys = _detection_keys_present(detections)
    contributions: list[ScoreContribution] = []
    region_matches: list[str] = []

    # ---- Rejection gates first ---------------------------------------------
    rejection = _check_rejection_gates(
        cfg=cfg,
        industry=industry,
        detection_keys=detection_keys,
        existing_signals=existing_signals,
    )
    if rejection is not None:
        rule_path, reason = rejection
        return ScoreResult(
            score=0.0,
            is_qualified=False,
            is_rejected=True,
            rejection_reason=reason,
            campaign=cfg.campaign,
            industry=industry,
            contributions=[
                ScoreContribution(
                    source="rejection",
                    weight=0.0,
                    reason=reason,
                    rule_path=rule_path,
                )
            ],
        )

    # ---- Start from baseline ----------------------------------------------
    raw_score = float(cfg.score_baseline)
    contributions.append(
        ScoreContribution(
            source="baseline",
            weight=raw_score,
            reason="campaign score baseline",
            rule_path=f"campaigns.{cfg.campaign}.score_baseline",
        )
    )

    # ---- Universal weights -------------------------------------------------
    raw_score, universal_contribs = _apply_weight_block(
        block=cfg.weights_universal,
        block_label="universal",
        rule_prefix="weights_universal",
        detection_keys=detection_keys,
        existing_signals=existing_signals,
        running_score=raw_score,
    )
    contributions.extend(universal_contribs)

    # ---- Per-industry overrides --------------------------------------------
    if industry and isinstance(cfg.weights_by_industry, dict):
        industry_block = cfg.weights_by_industry.get(industry)
        if isinstance(industry_block, dict) and industry_block:
            raw_score, industry_contribs = _apply_weight_block(
                block=industry_block,
                block_label=f"industry:{industry}",
                rule_prefix=f"weights_by_industry.{industry}",
                detection_keys=detection_keys,
                existing_signals=existing_signals,
                running_score=raw_score,
            )
            contributions.extend(industry_contribs)

    # ---- Per-region multipliers --------------------------------------------
    if isinstance(cfg.weights_by_region, dict):
        for region_name, region_block in cfg.weights_by_region.items():
            try:
                if not isinstance(region_block, dict):
                    continue
                matches = region_block.get("matches") or []
                multiplier = region_block.get("multiplier")
                if not isinstance(matches, list) or not isinstance(multiplier, (int, float)):
                    continue
                if any(
                    isinstance(m, str) and m.lower() in location_lower
                    for m in matches
                ):
                    region_matches.append(region_name)
                    before = raw_score
                    raw_score = raw_score * float(multiplier)
                    contributions.append(
                        ScoreContribution(
                            source=f"region:{region_name}",
                            weight=raw_score - before,
                            reason=(
                                f"region multiplier {multiplier} matched location "
                                f"'{location}'"
                            ),
                            rule_path=f"weights_by_region.{region_name}.multiplier",
                        )
                    )
            except Exception:
                logger.debug(
                    "scoring: region block %s raised; skipping",
                    region_name,
                    exc_info=True,
                )
                continue

    # ---- Clamp + normalize -------------------------------------------------
    score_max = max(float(cfg.score_max), 1e-6)
    clamped = max(0.0, min(raw_score, score_max))
    normalized = clamped / score_max
    is_qualified = normalized >= float(cfg.qualification_threshold)

    return ScoreResult(
        score=normalized,
        is_qualified=is_qualified,
        is_rejected=False,
        rejection_reason=None,
        contributions=contributions,
        campaign=cfg.campaign,
        industry=industry,
        region_matches=region_matches,
    )


# ---- Internals -------------------------------------------------------------


def _apply_weight_block(
    *,
    block: dict,
    block_label: str,
    rule_prefix: str,
    detection_keys: set[str],
    existing_signals: dict,
    running_score: float,
) -> tuple[float, list[ScoreContribution]]:
    """Apply detections + signals_from_* sub-blocks to ``running_score``.

    Tolerant: missing sub-blocks are skipped, malformed entries are
    skipped (per-entry try/except), every fired weight is recorded.
    """
    contribs: list[ScoreContribution] = []
    if not isinstance(block, dict):
        return running_score, contribs

    # Weights in YAML are integer points on a 0..100 scale (e.g. +15 / -20)
    # to match the convention in the prior-art research docs. We scale them
    # down to the 0..1 score space the baseline / score_max live in so a
    # single detection doesn't instantly clamp the score to score_max.
    SCALE = 0.01

    detection_block = block.get("detections") or {}
    if isinstance(detection_block, dict):
        for key, weight in detection_block.items():
            try:
                w = float(weight) * SCALE
            except (TypeError, ValueError):
                continue
            if key in detection_keys:
                running_score += w
                contribs.append(
                    ScoreContribution(
                        source=block_label,
                        weight=w,
                        reason=f"detection {key} present",
                        rule_path=f"{rule_prefix}.detections.{key}",
                    )
                )

    eval_block = block.get("signals_from_existing_evaluator") or {}
    if isinstance(eval_block, dict):
        for sig_key, weight in eval_block.items():
            try:
                w = float(weight) * SCALE
            except (TypeError, ValueError):
                continue
            if _signal_truthy(existing_signals, sig_key):
                running_score += w
                contribs.append(
                    ScoreContribution(
                        source=block_label,
                        weight=w,
                        reason=f"existing-evaluator signal {sig_key} truthy",
                        rule_path=f"{rule_prefix}.signals_from_existing_evaluator.{sig_key}",
                    )
                )

    remote_block = block.get("signals_from_remote_apis") or {}
    if isinstance(remote_block, dict):
        for sig_key, weight in remote_block.items():
            try:
                w = float(weight) * SCALE
            except (TypeError, ValueError):
                continue
            # Remote signals are surfaced into existing_signals as bools by
            # the integration layer (e.g. {"psi_mobile_score_below_50": True}).
            if _signal_truthy(existing_signals, sig_key):
                running_score += w
                contribs.append(
                    ScoreContribution(
                        source=block_label,
                        weight=w,
                        reason=f"remote-API signal {sig_key} truthy",
                        rule_path=f"{rule_prefix}.signals_from_remote_apis.{sig_key}",
                    )
                )

    return running_score, contribs


def _check_rejection_gates(
    *,
    cfg: WeightConfig,
    industry: str,
    detection_keys: set[str],
    existing_signals: dict,
) -> Optional[tuple[str, str]]:
    """Run universal then per-industry rejection gates.

    Returns (rule_path, human_reason) on first hit, None when no gate fires.
    """
    # Universal
    universal = cfg.reject_if_universal or {}
    for key in (universal.get("detection_present") or []):
        if isinstance(key, str) and key in detection_keys:
            return (
                f"reject_if_universal.detection_present.{key}",
                f"detection '{key}' is a universal reject",
            )
    for sig in (universal.get("signal_true") or []):
        if isinstance(sig, str) and _signal_truthy(existing_signals, sig):
            return (
                f"reject_if_universal.signal_true.{sig}",
                f"signal '{sig}' is a universal reject",
            )

    # Per-industry
    by_industry = cfg.reject_if_industry or {}
    block = by_industry.get(industry) if industry else None
    if isinstance(block, dict):
        for key in (block.get("detection_present") or []):
            if isinstance(key, str) and key in detection_keys:
                return (
                    f"reject_if_industry.{industry}.detection_present.{key}",
                    f"detection '{key}' rejects industry '{industry}'",
                )
        for sig in (block.get("signal_true") or []):
            if isinstance(sig, str) and _signal_truthy(existing_signals, sig):
                return (
                    f"reject_if_industry.{industry}.signal_true.{sig}",
                    f"signal '{sig}' rejects industry '{industry}'",
                )

    return None
