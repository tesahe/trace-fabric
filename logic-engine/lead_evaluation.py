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
"""

from __future__ import annotations

import logging
from typing import Any

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


def build_lead_evaluation(
    lead_payload: dict,
    *,
    campaign_type: str,
    target_industry: str,
    heuristic_flags: dict,
    matcher: Any = None,
) -> dict:
    """Run Tier 0 deterministic evaluator + (optional) signal matcher.

    Pure function — no DB, no async, no network. Pulled out of
    ``process_incoming_lead`` so integration tests can cover the
    evaluation + matcher merge without standing up SQLAlchemy.
    """
    evaluation = evaluate_lead(
        lead_data=lead_payload,
        campaign_type=campaign_type,
        target_industry=target_industry,
        heuristic_flags=heuristic_flags,
    )
    return apply_signals_v2(evaluation, lead_payload, matcher)
