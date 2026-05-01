"""Mozilla Observatory v2 wrapper.

The new MDN-hosted Observatory v2 API is a single POST to ``/api/v2/scan``
that triggers AND returns the result inline (no separate poll like v1).

Failure modes (any → return None):
  * Bad host (empty / not a string).
  * Network error / timeout.
  * Non-200 response.
  * Malformed JSON / missing ``grade``.

Rate-limiting: best-effort 1 scan per host per 60s, in-memory. Production
deployments behind a queue should layer their own backoff on top.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

OBSERVATORY_ENDPOINT = "https://observatory-api.mdn.mozilla.net/api/v2/scan"

# In-memory result cache (24h) and per-host last-scan timestamp (rate limiter).
_CACHE: dict[str, tuple[float, Optional[dict]]] = {}
_CACHE_TTL_SECONDS = 24 * 60 * 60
_LAST_SCAN_AT: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 60.0


def _cache_get(host: str) -> Optional[dict] | None:
    entry = _CACHE.get(host)
    if entry is None:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(host, None)
        return None
    return payload


def _cache_put(host: str, payload: Optional[dict]) -> None:
    _CACHE[host] = (time.time(), payload)


def _rate_limited(host: str) -> bool:
    last = _LAST_SCAN_AT.get(host)
    if last is None:
        return False
    return (time.time() - last) < _RATE_LIMIT_SECONDS


def _normalize_host(host: str) -> str:
    """Strip scheme, path, and trailing dot from a host string."""
    h = host.strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0]
    h = h.rstrip(".")
    return h


def _extract_grade(payload: dict) -> Optional[dict]:
    """Pull (grade, score) out of the v2 response payload."""
    grade = payload.get("grade")
    score = payload.get("score")
    if grade is None and score is None:
        # v2 nests the result inside scan{} on the polling endpoint; check there too.
        scan = payload.get("scan") or {}
        grade = scan.get("grade")
        score = scan.get("score")
    if grade is None and score is None:
        return None
    return {
        "grade": grade if isinstance(grade, str) else None,
        "score": int(score) if isinstance(score, (int, float)) else None,
    }


async def fetch_observatory_grade(
    host: str,
    *,
    timeout_s: float = 30.0,
) -> Optional[dict]:
    """Fetch the Mozilla Observatory grade + score for ``host``.

    Returns ``{"grade": "A+".."F", "score": int}`` or None on failure.
    Repeated calls within 60s for the same host short-circuit to None
    (rate-limit) unless a cached result is available.
    """
    if not host or not isinstance(host, str):
        return None
    h = _normalize_host(host)
    if not h:
        return None

    cached = _cache_get(h)
    if cached is not None or h in _CACHE:
        return cached

    if _rate_limited(h):
        logger.info("observatory: rate-limited for host=%s, returning None", h)
        return None

    try:
        import httpx
    except ImportError:
        logger.warning("observatory: httpx not installed; returning None")
        return None

    _LAST_SCAN_AT[h] = time.time()

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(OBSERVATORY_ENDPOINT, params={"host": h})
    except Exception as exc:
        logger.warning("observatory: request for host=%s failed: %s", h, exc)
        _cache_put(h, None)
        return None

    if resp.status_code != 200:
        logger.warning(
            "observatory: non-200 (%d) for host=%s; body head=%r",
            resp.status_code,
            h,
            resp.text[:200] if hasattr(resp, "text") else "",
        )
        _cache_put(h, None)
        return None

    try:
        payload = resp.json()
    except Exception as exc:
        logger.warning("observatory: malformed JSON for host=%s: %s", h, exc)
        _cache_put(h, None)
        return None

    extracted = _extract_grade(payload)
    _cache_put(h, extracted)
    return extracted


def clear_cache() -> None:
    """Test helper."""
    _CACHE.clear()
    _LAST_SCAN_AT.clear()
