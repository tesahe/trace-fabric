"""Google PageSpeed Insights v5 wrapper.

Hits ``https://www.googleapis.com/pagespeedonline/v5/runPagespeed`` for one
strategy at a time and extracts the Lighthouse performance score plus a
handful of common audit failures we feed into the scorer.

Failure modes (any → return None, log warning):
  * Missing API key (env ``GOOGLE_PSI_API_KEY``).
  * Network error / timeout.
  * Non-200 response.
  * Malformed JSON / missing ``lighthouseResult``.

Caching: per-URL+strategy, in-memory, 24h TTL. Good enough for one
process's lifetime; production deployments can swap in Redis later
without changing the call signature.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory cache: {(url, strategy): (timestamp, payload_or_none)}
_CACHE: dict[tuple[str, str], tuple[float, Optional[dict]]] = {}
_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h

PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def _cache_get(url: str, strategy: str) -> Optional[dict] | None:
    """Return cached payload if still fresh, sentinel ``None`` otherwise.

    Returns the payload dict on hit (which may itself be None for a cached
    "this URL failed last time" entry); returns the literal Python ``None``
    sentinel on miss. Callers distinguish via the ``in _CACHE`` check
    below — this helper is just a TTL filter.
    """
    entry = _CACHE.get((url, strategy))
    if entry is None:
        return None
    ts, payload = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop((url, strategy), None)
        return None
    return payload


def _cache_put(url: str, strategy: str, payload: Optional[dict]) -> None:
    _CACHE[(url, strategy)] = (time.time(), payload)


def _extract_signals(payload: dict, strategy: str) -> dict:
    """Reduce a PSI v5 response to the small dict the scorer consumes."""
    out: dict = {"strategy": strategy, "score": None, "audits": {}}

    lh = payload.get("lighthouseResult") or {}
    cats = lh.get("categories") or {}
    perf = cats.get("performance") or {}
    raw_score = perf.get("score")
    if isinstance(raw_score, (int, float)):
        # PSI returns 0..1; we expose 0..100 for human readability.
        out["score"] = int(round(raw_score * 100))

    audits = lh.get("audits") or {}
    audit_keys = (
        "first-contentful-paint",
        "largest-contentful-paint",
        "interactive",
        "speed-index",
        "total-blocking-time",
        "cumulative-layout-shift",
    )
    for key in audit_keys:
        a = audits.get(key)
        if not isinstance(a, dict):
            continue
        out["audits"][key] = {
            "score": a.get("score"),
            "displayValue": a.get("displayValue"),
        }
    return out


async def fetch_psi_signals(
    url: str,
    *,
    api_key: Optional[str] = None,
    strategy: str = "mobile",
    timeout_s: float = 30.0,
) -> Optional[dict]:
    """Fetch PSI signals for ``url``. Returns None on any failure.

    ``api_key`` defaults to env ``GOOGLE_PSI_API_KEY``. If missing, this
    function returns None without hitting the network and emits one
    warning log line per process — you cannot use PSI v5 without a key.
    """
    if not url or not isinstance(url, str):
        return None
    if api_key is None:
        api_key = os.getenv("GOOGLE_PSI_API_KEY")
    if not api_key:
        logger.warning("psi: no GOOGLE_PSI_API_KEY set; returning None")
        return None

    cached = _cache_get(url, strategy)
    if cached is not None or (url, strategy) in _CACHE:
        return cached

    try:
        import httpx  # local import: never cost the matcher when this isn't called.
    except ImportError:
        logger.warning("psi: httpx not installed; returning None")
        return None

    params = {
        "url": url,
        "strategy": strategy,
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(PSI_ENDPOINT, params=params)
    except Exception as exc:
        logger.warning("psi: request to %s failed: %s", url, exc)
        _cache_put(url, strategy, None)
        return None

    if resp.status_code != 200:
        logger.warning(
            "psi: non-200 (%d) for %s; body head=%r",
            resp.status_code,
            url,
            resp.text[:200] if hasattr(resp, "text") else "",
        )
        _cache_put(url, strategy, None)
        return None

    try:
        payload = resp.json()
    except Exception as exc:
        logger.warning("psi: malformed JSON for %s: %s", url, exc)
        _cache_put(url, strategy, None)
        return None

    try:
        signals = _extract_signals(payload, strategy)
    except Exception as exc:
        logger.warning("psi: extraction failed for %s: %s", url, exc)
        _cache_put(url, strategy, None)
        return None

    _cache_put(url, strategy, signals)
    return signals


def clear_cache() -> None:
    """Test helper. Production code should never call this."""
    _CACHE.clear()
