"""RemoteProviders bundle: synthesizes Detections from PSI + Observatory.

The matcher receives one of these via its ``remote_providers`` arg; if
None (the default), nothing remote runs. Each provider is opt-in via its
own env flag (``TRACEFAB_REMOTE_PSI``, ``TRACEFAB_REMOTE_OBSERVATORY``)
so a deployment can fan out to one without paying for the other.

We surface the API outputs as ``Detection`` records using the existing
``MatchSource.REMOTE_PSI`` / ``MatchSource.REMOTE_OBSERVATORY`` enum
values (added in Sprint 2's first commit). They flow through the
resolver / blocklist like any other Detection.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable, Optional
from urllib.parse import urlparse

from ..detection import Detection, MatchSource, truncate_value
from .observatory import fetch_observatory_grade
from .psi import fetch_psi_signals

logger = logging.getLogger(__name__)


def _env_truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _host_from_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.netloc.lower().rstrip(".")
    except Exception:
        return ""


def _psi_to_detections(url: str, signals: dict) -> Iterable[Detection]:
    """Build one summary Detection + a PSI-mobile-low Detection if score < 50."""
    score = signals.get("score")
    strategy = signals.get("strategy", "mobile")
    if score is None:
        return
    yield Detection(
        name=f"PSI {strategy} score: {score}",
        pack="remote_apis",
        categories=(),
        confidence=100,
        version=None,
        source=MatchSource.REMOTE_PSI,
        matched_field=f"psi.{strategy}.score",
        matched_value=truncate_value(str(signals)),
        pattern_id=f"remote_psi:{strategy}:{url}",
    )
    if isinstance(score, int) and score < 50:
        yield Detection(
            name=f"psi_{strategy}_score_below_50",
            pack="remote_apis",
            categories=(),
            confidence=100,
            version=None,
            source=MatchSource.REMOTE_PSI,
            matched_field=f"psi.{strategy}.score",
            matched_value=str(score),
            pattern_id=f"remote_psi:{strategy}:below_50:{url}",
        )


def _observatory_to_detections(host: str, result: dict) -> Iterable[Detection]:
    grade = result.get("grade")
    score = result.get("score")
    if grade is None and score is None:
        return
    yield Detection(
        name=f"Observatory grade: {grade or '?'}",
        pack="remote_apis",
        categories=(),
        confidence=100,
        version=None,
        source=MatchSource.REMOTE_OBSERVATORY,
        matched_field="observatory.grade",
        matched_value=truncate_value(f"grade={grade} score={score}"),
        pattern_id=f"remote_observatory:{host}",
    )
    if isinstance(grade, str) and grade.upper() in {"F"}:
        yield Detection(
            name="observatory_grade_F",
            pack="remote_apis",
            categories=(),
            confidence=100,
            version=None,
            source=MatchSource.REMOTE_OBSERVATORY,
            matched_field="observatory.grade",
            matched_value=grade,
            pattern_id=f"remote_observatory:F:{host}",
        )


class RemoteProviders:
    """Bundle of remote-API providers, configured by env flags by default.

    Tests pass ``psi_enabled`` / ``observatory_enabled`` explicitly to
    avoid env-state coupling.
    """

    def __init__(
        self,
        *,
        psi_enabled: Optional[bool] = None,
        observatory_enabled: Optional[bool] = None,
        psi_api_key: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self.psi_enabled = (
            psi_enabled
            if psi_enabled is not None
            else _env_truthy(os.getenv("TRACEFAB_REMOTE_PSI"))
        )
        self.observatory_enabled = (
            observatory_enabled
            if observatory_enabled is not None
            else _env_truthy(os.getenv("TRACEFAB_REMOTE_OBSERVATORY"))
        )
        self.psi_api_key = psi_api_key
        self.timeout_s = timeout_s

    def is_enabled(self) -> bool:
        return self.psi_enabled or self.observatory_enabled

    async def collect(self, raw_lead: dict) -> list[Detection]:
        """Fan out PSI + Observatory in parallel; flatten to Detections.

        Each call is wrapped in try/except — a failure in one provider
        never blocks the other. Returns ``[]`` if no providers are on.
        """
        if not self.is_enabled():
            return []

        url = ""
        if isinstance(raw_lead, dict):
            url = raw_lead.get("final_url") or raw_lead.get("source_url") or ""
        host = _host_from_url(url)

        async def _psi_safe() -> Optional[dict]:
            if not self.psi_enabled or not url:
                return None
            try:
                return await fetch_psi_signals(
                    url,
                    api_key=self.psi_api_key,
                    timeout_s=self.timeout_s,
                )
            except Exception:
                logger.exception("remote_providers: PSI call raised")
                return None

        async def _obs_safe() -> Optional[dict]:
            if not self.observatory_enabled or not host:
                return None
            try:
                return await fetch_observatory_grade(host, timeout_s=self.timeout_s)
            except Exception:
                logger.exception("remote_providers: Observatory call raised")
                return None

        psi_result, obs_result = await asyncio.gather(_psi_safe(), _obs_safe())

        out: list[Detection] = []
        if psi_result:
            try:
                out.extend(list(_psi_to_detections(url, psi_result)))
            except Exception:
                logger.exception("remote_providers: PSI->Detection failed")
        if obs_result:
            try:
                out.extend(list(_observatory_to_detections(host, obs_result)))
            except Exception:
                logger.exception("remote_providers: Observatory->Detection failed")
        return out
