"""Detection dataclass + MatchSource enum.

The matcher emits ``Detection`` records (one per signature pattern hit) and
the resolver post-processes them (deduplicate, apply implies/requires/
excludes) before returning the final list to the caller.

``Detection`` is ``frozen=True`` so the entire object is hashable. That lets
callers drop a list straight into a ``set[Detection]`` for cheap dedup of
"same tech triggered by multiple patterns" cases without writing custom
__hash__ / __eq__ code.

Audit-trail fields (``matched_field``, ``matched_value``, ``pattern_id``)
are mandatory because every detection eventually has to be defensible from
the gatekeeper output back to the raw artifact that triggered it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MatchSource(str, Enum):
    """Which artifact in the RawLead a Detection was triggered by."""

    SCRIPT_SRC = "script_src"
    HTML = "html"
    CSS = "css"
    HEADERS = "headers"
    COOKIES = "cookies"
    META = "meta"
    URL = "url"
    ROBOTS = "robots"
    TEXT = "text"
    DNS_HEADER = "dns_header"
    # Synthetic sources produced by the resolver, not by raw pattern matches.
    IMPLIED = "implied"
    REQUIRED = "required"
    # Sprint 2: structured-data + remote-API enrichment sources.
    STRUCTURED_DATA = "structured_data"
    REMOTE_PSI = "remote_psi"
    REMOTE_OBSERVATORY = "remote_observatory"


@dataclass(frozen=True)
class Detection:
    """A single technology hit, with full audit-trail context.

    ``frozen=True`` makes the dataclass hashable so a ``set[Detection]``
    deduplicates same-tech-multiple-pattern occurrences naturally. The
    resolver still runs a final dedup pass keyed on ``(name, pack)`` to
    keep the highest-confidence occurrence.
    """

    name: str                          # canonical tech name from sig pack
    pack: str                          # "wappalyzer" | "retirejs" | "local_biz"
    categories: tuple[int, ...]        # category IDs from sig pack
    confidence: int                    # 0..100, propagated from pattern annotation
    version: Optional[str]             # extracted via \1 group if pattern matched
    source: MatchSource                # which artifact type triggered this
    matched_field: str                 # "script_srcs[3].url" or similar locator
    matched_value: str                 # truncated to ~200 chars
    pattern_id: str                    # signature_id + pattern_index for traceability
    cpe: Optional[str] = None          # if upstream provides CPE
    pricing: tuple[str, ...] = ()      # ("recurring", "high") if upstream provides
    saas: bool = False
    oss: bool = False
    website: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize for storage in the ``heuristic_flags`` JSON column.

        Tuples become lists so the payload survives ``json.dumps`` cleanly,
        and ``MatchSource`` is reduced to its string ``value`` so the JSON
        round-trip never depends on the enum class being importable in the
        consumer.
        """
        return {
            "name": self.name,
            "pack": self.pack,
            "categories": list(self.categories),
            "confidence": self.confidence,
            "version": self.version,
            "source": self.source.value if hasattr(self.source, "value") else str(self.source),
            "matched_field": self.matched_field,
            "matched_value": self.matched_value,
            "pattern_id": self.pattern_id,
            "cpe": self.cpe,
            "pricing": list(self.pricing),
            "saas": self.saas,
            "oss": self.oss,
            "website": self.website,
        }


def detections_to_payload(detections: list[Detection]) -> list[dict]:
    """Serialize a list of Detections into a JSON-storable list of dicts.

    Convenience wrapper around ``Detection.to_dict`` so callers in
    ``lead_processor`` (and any future Tier 0 consumer) don't have to
    reach into the dataclass themselves.
    """
    return [d.to_dict() for d in detections]


def truncate_value(value: str, limit: int = 200) -> str:
    """Truncate a matched value for inclusion in a Detection.

    Centralised so all callers truncate consistently. Appends "..." when
    the value is actually trimmed so downstream readers can see it was
    cut.
    """
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
