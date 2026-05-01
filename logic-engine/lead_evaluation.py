"""Pure-function bridge between Tier 0 evaluation and the signals_v2 matcher.

Lives outside ``lead_processor`` so it can be exercised in tests without
importing SQLAlchemy / asyncio / Tier 1 / Tier 2. ``lead_processor``
re-exports ``build_lead_evaluation`` to preserve the existing call shape.

No DB writes, no network. Given a parsed lead dict and an optional
matcher instance, this returns the same dict shape that
``deterministic_evaluator.evaluate_lead`` does — with an additional
``heuristic_flags["technologies"]`` entry when the matcher is supplied.

Failure handling: if the matcher raises for any reason we log it and
fall back to the unmodified evaluation. Tier 0 must never fail a lead
because of an experimental signal pack.

Sprint 2 addition: ``apply_scoring_v2`` runs the weighted scorer over
the matcher detections + existing-evaluator signals and lands the
result in ``heuristic_flags["score_v2"]`` + ``heuristic_flags["score_v2_breakdown"]``.
It NEVER overwrites the existing ``score`` / ``is_qualified_lead``
fields — those still come from the legacy formula and remain the
authoritative pipeline gate until we explicitly cut over.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from deterministic_evaluator import evaluate_lead


logger = logging.getLogger(__name__)


def apply_signals_v2(evaluation: dict, lead_payload: dict, matcher: Any) -> dict:
    """Run the matcher and merge detections into ``evaluation`` in-place.

    ``matcher`` is duck-typed: anything with a ``match(raw_lead) -> list``
    method works, which keeps test-double substitution trivial. Returns the
    same dict for fluent composition.
    """
    if matcher is None:
        return evaluation

    try:
        # Imported lazily so callers that don't pass a matcher never pay the
        # cost of bringing in the signals package or its compiled patterns.
        from signals.detection import detections_to_payload

        detections = matcher.match(lead_payload)
        payload = detections_to_payload(detections)
        flags = evaluation.setdefault("heuristic_flags", {})
        flags["technologies"] = payload
    except Exception:
        logger.exception("[Tier 0] signals_v2 matcher raised — falling back to evaluation as-is")

    return evaluation


def _build_existing_signals(evaluation: dict, lead_payload: dict) -> dict:
    """Translate the deterministic evaluator's output into the flat dict
    the scorer's ``signals_from_existing_evaluator`` block expects.

    We surface both the ``has_X`` positive form AND the ``no_X`` negative
    form so weight configs can talk in whichever direction reads better.
    Booleans only — the scorer uses truthiness.
    """
    signals: dict = {}
    if not isinstance(evaluation, dict):
        return signals

    evidence = evaluation.get("deterministic_evidence") or {}
    if isinstance(evidence, dict):
        # Direct passthrough of every has_X / boolean field.
        for key, value in evidence.items():
            if isinstance(value, bool):
                signals[key] = value
                # Mirror to the negative form for "no_X" lookups.
                if key.startswith("has_"):
                    signals[f"no_{key[4:]}"] = not value

    # The "missing_critical_features" + "identified_service_gaps" lists name
    # specific gaps; project them into the flat namespace as bools so weight
    # configs can target them ("no_form": 20).
    for tag in (evaluation.get("missing_critical_features") or []):
        if isinstance(tag, str):
            signals[_normalize_gap_to_no_x(tag)] = True
            signals[tag] = True
    for tag in (evaluation.get("identified_service_gaps") or []):
        if isinstance(tag, str):
            signals[tag] = True
            if tag.startswith("missing_"):
                signals[f"no_{tag[len('missing_'):]}"] = True

    # is_no_website_opportunity / is_parked_domain (universal-reject signals).
    payload_flag = lead_payload.get("is_no_website_opportunity") if isinstance(lead_payload, dict) else None
    if payload_flag:
        signals["is_no_website_opportunity"] = True

    flags = evaluation.get("heuristic_flags") or {}
    if isinstance(flags, dict):
        if flags.get("is_parked_domain"):
            signals["is_parked_domain"] = True

    return signals


def _normalize_gap_to_no_x(tag: str) -> str:
    """Map evaluator gap tag -> ``no_X`` key the scorer YAML uses."""
    mapping = {
        "mobile_responsive_design": "no_viewport",
        "contact_form": "no_form",
        "clear_primary_cta": "no_cta",
        "privacy_policy": "no_privacy",
        "phone_conversion_flow": "no_phone_signal",
        "appointment_capture": "no_booking",
        "published_hours": "no_hours",
        "social_presence_links": "no_social_presence",
        "social_proof": "no_reviews",
        "campaign_landing_cta": "no_cta",
    }
    return mapping.get(tag, tag)


def apply_scoring_v2(
    *,
    evaluation: dict,
    detections: Optional[list] = None,
    runtime_config: Any = None,
    weight_configs: Optional[dict] = None,
    lead_payload: Optional[dict] = None,
    campaign: Optional[str] = None,
    industry: Optional[str] = None,
    location: Optional[str] = None,
) -> dict:
    """Compute score_v2 from detections + existing evaluation.

    Lands in ``evaluation['heuristic_flags']['score_v2']`` +
    ``evaluation['heuristic_flags']['score_v2_breakdown']``. Does NOT
    touch the existing ``score`` or ``is_qualified_lead`` fields.

    Gated on ``runtime_config.signals_v2_scoring_enabled`` (env
    ``TRACEFAB_SCORING_V2=1``). Returns ``evaluation`` unchanged when
    the flag is off, when no weight configs are supplied, or when the
    scorer raises.
    """
    if runtime_config is not None and not getattr(
        runtime_config, "signals_v2_scoring_enabled", False
    ):
        return evaluation
    if not weight_configs:
        return evaluation

    try:
        from scoring import score_lead

        # Source detections: prefer explicit arg, else read from heuristic_flags.
        if detections is None:
            flags = evaluation.get("heuristic_flags") or {}
            detections = flags.get("technologies") or []

        existing_signals = _build_existing_signals(evaluation, lead_payload or {})

        # Pull contextual fields from the runtime / payload if not supplied.
        if campaign is None and runtime_config is not None:
            campaign = getattr(runtime_config, "campaign_type", "")
        if industry is None and isinstance(lead_payload, dict):
            industry = lead_payload.get("target_industry", "")
        if location is None and isinstance(lead_payload, dict):
            location = lead_payload.get("target_location", "")

        result = score_lead(
            detections=detections or [],
            existing_signals=existing_signals,
            campaign=campaign or "",
            industry=industry or "",
            location=location or "",
            weight_configs=weight_configs,
        )

        flags = evaluation.setdefault("heuristic_flags", {})
        flags["score_v2"] = round(result.score, 4)
        flags["score_v2_breakdown"] = result.to_dict()
    except Exception:
        logger.exception("[Tier 0] signals_v2 scoring raised — leaving evaluation untouched")

    return evaluation


def build_lead_evaluation(
    lead_payload: dict,
    *,
    campaign_type: str,
    target_industry: str,
    heuristic_flags: dict,
    matcher: Any = None,
    weight_configs: Optional[dict] = None,
    runtime_config: Any = None,
) -> dict:
    """Run Tier 0 deterministic evaluator + (optional) signal matcher + (optional) scorer.

    Pure function — no DB, no async, no network. Pulled out of
    ``process_incoming_lead`` so integration tests can cover the
    evaluation + matcher + scorer merge without standing up SQLAlchemy.
    """
    evaluation = evaluate_lead(
        lead_data=lead_payload,
        campaign_type=campaign_type,
        target_industry=target_industry,
        heuristic_flags=heuristic_flags,
    )
    evaluation = apply_signals_v2(evaluation, lead_payload, matcher)
    if runtime_config is not None and weight_configs:
        evaluation = apply_scoring_v2(
            evaluation=evaluation,
            runtime_config=runtime_config,
            weight_configs=weight_configs,
            lead_payload=lead_payload,
            campaign=campaign_type,
            industry=target_industry,
            location=lead_payload.get("target_location", "") if isinstance(lead_payload, dict) else "",
        )
    return evaluation
