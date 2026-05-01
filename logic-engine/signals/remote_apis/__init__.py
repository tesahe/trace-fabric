"""Remote-API signal providers (PSI, Mozilla Observatory).

These wrappers fetch a small number of free third-party signals (mobile
performance score, security headers grade) and surface them as
``Detection`` records on the same MatchSource enum the local matcher
uses.

Every wrapper:
  * Returns ``None`` on any kind of failure (network, parse, auth).
  * Never raises into the matcher.
  * Caches by URL/host with a short TTL so repeated scans of the same lead
    don't re-hit the upstream API in a single process lifetime.

Public API:
  - ``fetch_psi_signals(url, *, api_key, timeout_s=30) -> dict | None``
  - ``fetch_observatory_grade(host, *, timeout_s=30) -> dict | None``
  - ``RemoteProviders`` bundle with ``.collect(raw_lead) -> list[Detection]``
"""

from __future__ import annotations

from .psi import fetch_psi_signals
from .observatory import fetch_observatory_grade
from .providers import RemoteProviders

__all__ = [
    "fetch_psi_signals",
    "fetch_observatory_grade",
    "RemoteProviders",
]
