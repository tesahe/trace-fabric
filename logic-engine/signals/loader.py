"""Signature pack loaders.

Reads the vendored Wappalyzer / RetireJS / local_biz JSON files off disk
and converts each technology entry into a ``Technology`` object with
pre-compiled regex patterns bucketed by ``MatchSource``.

Pre-compiling once at startup mirrors the rverton/webanalyze pattern: the
matcher then makes one pass per artifact type rather than one pass per
pattern, which is much friendlier to CPU caches when there are ~5k
techs and ~15k patterns total.

Pattern types we drop at load time (no JS runtime, no browser, no live
network in-band): ``js``, ``dom``, ``xhr``, ``probe``, ``certIssuer``.
The drop is silent per-signature but counted and logged in aggregate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from .detection import MatchSource
from .regex_safe import CompiledPattern, compile as compile_pattern

logger = logging.getLogger(__name__)

# Wappalyzer pattern keys that we cannot evaluate against a static RawLead.
DROPPED_WAPPALYZER_KEYS = frozenset({"js", "dom", "xhr", "probe", "certIssuer"})

# Map from Wappalyzer JSON key -> MatchSource.
# (cookies/headers/meta have dict-shape values; the rest are list-shape.)
WAPPALYZER_KEY_TO_SOURCE: dict[str, MatchSource] = {
    "scriptSrc": MatchSource.SCRIPT_SRC,
    "html": MatchSource.HTML,
    "css": MatchSource.CSS,
    "headers": MatchSource.HEADERS,
    "cookies": MatchSource.COOKIES,
    "meta": MatchSource.META,
    "url": MatchSource.URL,
    "robots": MatchSource.ROBOTS,
    "text": MatchSource.TEXT,
    "dns": MatchSource.DNS_HEADER,  # partial: only matches if value already in headers
}

# Wappalyzer keys with dict values; the dict key is preserved as
# ``CompiledPattern.qualifier`` so e.g. cookie name / header name is
# retained for the matcher.
DICT_VALUED_KEYS = frozenset({"headers", "cookies", "meta", "dns"})


@dataclass
class LoadedPattern:
    """Wraps a CompiledPattern with the dict-key qualifier (for headers/cookies/meta/dns)."""

    compiled: CompiledPattern
    qualifier: Optional[str]   # e.g. "Set-Cookie" header name, or "generator" meta name
    pattern_index: int         # stable index for pattern_id traceability


@dataclass
class Technology:
    """A single technology entry, post-load.

    ``patterns_by_source`` is the hot-path data structure the matcher walks.
    Empty source buckets are omitted entirely so the matcher doesn't iterate
    over no-op lists.
    """

    name: str
    pack: str                                  # "wappalyzer" | "retirejs" | "local_biz"
    categories: tuple[int, ...]
    pricing: tuple[str, ...]
    saas: bool
    oss: bool
    website: Optional[str]
    cpe: Optional[str]
    patterns_by_source: dict[MatchSource, list[LoadedPattern]] = field(default_factory=dict)
    implies: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    requires_category: list[int] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)

    def has_patterns(self) -> bool:
        return any(self.patterns_by_source.values())


# Loader stats ----------------------------------------------------------------


@dataclass
class PackStats:
    pack: str
    total_entries: int = 0
    loaded: int = 0
    empty_after_drop: int = 0
    total_patterns: int = 0
    invalid_patterns: int = 0


# Helpers ---------------------------------------------------------------------


def _as_list(value) -> list[str]:
    """Wappalyzer fields are either a string or a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    if isinstance(value, str):
        return [value]
    return []


def _extract_implies_for_resolver(value) -> list[str]:
    """``implies`` entries can carry their own ``\\;confidence:N`` suffix.

    For the resolver we only care about the tech name, so strip any
    annotation. The annotation parser in regex_safe gives us the head.
    """
    from .regex_safe import split_annotations

    out: list[str] = []
    for entry in _as_list(value):
        head, _ = split_annotations(entry)
        head = head.strip()
        if head:
            out.append(head)
    return out


def _coerce_categories(value) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(int(c) for c in value if isinstance(c, (int, str)) and str(c).isdigit())


# Wappalyzer ------------------------------------------------------------------


def _wappalyzer_tech_from_entry(name: str, entry: dict, stats: PackStats) -> Optional[Technology]:
    """Convert one Wappalyzer JSON tech entry into a Technology.

    Returns None if the tech ends up with zero usable patterns after the
    drop filter (still counted in stats.empty_after_drop).
    """
    if not isinstance(entry, dict):
        return None

    patterns_by_source: dict[MatchSource, list[LoadedPattern]] = {}
    pattern_index = 0

    for key, raw_value in entry.items():
        if key in DROPPED_WAPPALYZER_KEYS:
            continue
        source = WAPPALYZER_KEY_TO_SOURCE.get(key)
        if source is None:
            continue

        if key in DICT_VALUED_KEYS and isinstance(raw_value, dict):
            for qualifier, pattern_str in raw_value.items():
                if not isinstance(pattern_str, str):
                    continue
                # Empty-string pattern means "this key/header exists" — we
                # use a regex matching anything as a presence check, so the
                # qualifier alone is enough to flag the tech.
                effective_pattern = pattern_str if pattern_str else ".*"
                compiled = compile_pattern(effective_pattern)
                if compiled is None:
                    stats.invalid_patterns += 1
                    continue
                patterns_by_source.setdefault(source, []).append(
                    LoadedPattern(compiled=compiled, qualifier=qualifier, pattern_index=pattern_index)
                )
                stats.total_patterns += 1
                pattern_index += 1
        else:
            for pattern_str in _as_list(raw_value):
                compiled = compile_pattern(pattern_str)
                if compiled is None:
                    stats.invalid_patterns += 1
                    continue
                patterns_by_source.setdefault(source, []).append(
                    LoadedPattern(compiled=compiled, qualifier=None, pattern_index=pattern_index)
                )
                stats.total_patterns += 1
                pattern_index += 1

    if not patterns_by_source:
        stats.empty_after_drop += 1
        return None

    return Technology(
        name=name,
        pack="wappalyzer",
        categories=_coerce_categories(entry.get("cats")),
        pricing=tuple(_as_list(entry.get("pricing"))),
        saas=bool(entry.get("saas", False)),
        oss=bool(entry.get("oss", False)),
        website=entry.get("website") if isinstance(entry.get("website"), str) else None,
        cpe=entry.get("cpe") if isinstance(entry.get("cpe"), str) else None,
        patterns_by_source=patterns_by_source,
        implies=_extract_implies_for_resolver(entry.get("implies")),
        requires=_extract_implies_for_resolver(entry.get("requires")),
        requires_category=[
            int(c) for c in _as_list(entry.get("requiresCategory")) if c.isdigit()
        ] if isinstance(entry.get("requiresCategory"), list) else [],
        excludes=_extract_implies_for_resolver(entry.get("excludes")),
    )


def load_wappalyzer_pack(data_dir: Path) -> dict[str, Technology]:
    """Load every ``[a-z_].json`` tech file from the Wappalyzer pack.

    ``categories.json`` and ``groups.json`` are skipped (they are metadata,
    not tech entries). Returns a dict keyed by canonical tech name.
    """
    stats = PackStats(pack="wappalyzer")
    techs: dict[str, Technology] = {}

    skip_files = {"categories.json", "groups.json"}
    for json_path in sorted(data_dir.glob("*.json")):
        if json_path.name in skip_files:
            continue
        try:
            with json_path.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("loader: failed to read %s: %s", json_path, exc)
            continue
        if not isinstance(payload, dict):
            continue
        for tech_name, entry in payload.items():
            stats.total_entries += 1
            tech = _wappalyzer_tech_from_entry(tech_name, entry, stats)
            if tech is None:
                continue
            techs[tech_name] = tech
            stats.loaded += 1

    logger.info(
        "loader: wappalyzer pack loaded %d/%d techs (%d empty-after-drop), "
        "%d patterns compiled, %d invalid patterns skipped",
        stats.loaded,
        stats.total_entries,
        stats.empty_after_drop,
        stats.total_patterns,
        stats.invalid_patterns,
    )
    return techs


# RetireJS --------------------------------------------------------------------

# RetireJS uses the literal sentinel ``§§version§§`` inside its extractor
# regexes; we replace it with a permissive version capture group so the
# pattern actually compiles + extracts.
_RETIRE_VERSION_TOKEN = "§§version§§"  # the §§version§§ sentinel
_RETIRE_VERSION_GROUP = r"([0-9][0-9a-zA-Z._-]*)"


def _retire_pattern_to_regex(raw: str) -> str:
    """Replace RetireJS ``§§version§§`` with a real capture group, append
    a ``\\;version:\\1`` annotation so CompiledPattern can extract it."""
    if not raw:
        return ""
    has_version = _RETIRE_VERSION_TOKEN in raw
    rewritten = raw.replace(_RETIRE_VERSION_TOKEN, _RETIRE_VERSION_GROUP)
    if has_version:
        rewritten = rewritten + r"\;version:\1"
    return rewritten


def load_retirejs_pack(data_dir: Path) -> dict[str, Technology]:
    """Load the retire.js ``jsrepository.json`` library list.

    Each library becomes one Technology with ``script_src`` patterns
    synthesized from the ``extractors.uri`` and ``extractors.filename``
    arrays. We deliberately ignore ``extractors.func`` (JS runtime) and
    ``extractors.filecontent`` / ``hashes`` (would require fetching JS
    bodies, which the Rust scraper does not do today).

    Categories are set to ``(-1,)`` as a sentinel meaning "vulnerable JS
    library"; downstream consumers can decide how to surface that.
    """
    stats = PackStats(pack="retirejs")
    techs: dict[str, Technology] = {}

    candidate = data_dir / "jsrepository.json"
    if not candidate.exists():
        logger.warning("loader: retirejs jsrepository.json not found at %s", candidate)
        return techs

    try:
        with candidate.open(encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("loader: failed to read %s: %s", candidate, exc)
        return techs

    if not isinstance(payload, dict):
        return techs

    for lib_name, entry in payload.items():
        stats.total_entries += 1
        if not isinstance(entry, dict):
            continue
        # Skip the example/template entry shipped by upstream.
        if lib_name == "retire-example":
            continue
        extractors = entry.get("extractors") or {}
        if not isinstance(extractors, dict):
            continue

        patterns_by_source: dict[MatchSource, list[LoadedPattern]] = {}
        pattern_index = 0
        for key in ("uri", "filename", "filecontent"):
            for raw in _as_list(extractors.get(key)):
                rewritten = _retire_pattern_to_regex(raw)
                compiled = compile_pattern(rewritten)
                if compiled is None:
                    stats.invalid_patterns += 1
                    continue
                # uri + filename -> match against script_src URLs joined.
                # filecontent -> match against raw_html (best-effort: inline
                # script bodies live in raw_html, external bodies do not).
                src = MatchSource.SCRIPT_SRC if key in ("uri", "filename") else MatchSource.HTML
                patterns_by_source.setdefault(src, []).append(
                    LoadedPattern(compiled=compiled, qualifier=None, pattern_index=pattern_index)
                )
                stats.total_patterns += 1
                pattern_index += 1

        if not patterns_by_source:
            stats.empty_after_drop += 1
            continue

        techs[lib_name] = Technology(
            name=lib_name,
            pack="retirejs",
            categories=(-1,),  # sentinel: "outdated JS library"
            pricing=(),
            saas=False,
            oss=True,
            website=None,
            cpe=None,
            patterns_by_source=patterns_by_source,
        )
        stats.loaded += 1

    logger.info(
        "loader: retirejs pack loaded %d/%d libs (%d empty-after-drop), "
        "%d patterns compiled, %d invalid patterns skipped",
        stats.loaded,
        stats.total_entries,
        stats.empty_after_drop,
        stats.total_patterns,
        stats.invalid_patterns,
    )
    return techs


# local_biz -------------------------------------------------------------------


def load_local_biz_pack(data_dir: Path) -> dict[str, Technology]:
    """Load the TraceFabric-curated local-business pack.

    Schema mirrors Wappalyzer for free reuse of the loader logic. Empty
    by design today (returns ``{}`` if the pack has no JSON files yet).
    """
    stats = PackStats(pack="local_biz")
    techs: dict[str, Technology] = {}

    if not data_dir.exists():
        logger.info("loader: local_biz pack directory not present, skipping")
        return techs

    for json_path in sorted(data_dir.glob("*.json")):
        try:
            with json_path.open(encoding="utf-8") as fh:
                payload = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("loader: failed to read %s: %s", json_path, exc)
            continue
        if not isinstance(payload, dict):
            continue
        for tech_name, entry in payload.items():
            stats.total_entries += 1
            tech = _wappalyzer_tech_from_entry(tech_name, entry, stats)
            if tech is None:
                continue
            tech = Technology(
                name=tech.name,
                pack="local_biz",
                categories=tech.categories,
                pricing=tech.pricing,
                saas=tech.saas,
                oss=tech.oss,
                website=tech.website,
                cpe=tech.cpe,
                patterns_by_source=tech.patterns_by_source,
                implies=tech.implies,
                requires=tech.requires,
                requires_category=tech.requires_category,
                excludes=tech.excludes,
            )
            techs[tech_name] = tech
            stats.loaded += 1

    logger.info(
        "loader: local_biz pack loaded %d/%d techs (%d empty-after-drop), "
        "%d patterns compiled, %d invalid patterns skipped",
        stats.loaded,
        stats.total_entries,
        stats.empty_after_drop,
        stats.total_patterns,
        stats.invalid_patterns,
    )
    return techs


# Convenience -----------------------------------------------------------------


def load_all_packs(signals_root: Path) -> dict[str, Technology]:
    """Load all three packs from the conventional layout under ``signals_root``.

    Later packs overwrite earlier ones on tech-name collision in the
    returned dict. The matcher does not rely on this dict for collision
    handling — it iterates per-pack via the returned values' ``pack`` field.
    """
    out: dict[str, Technology] = {}
    out.update(load_wappalyzer_pack(signals_root / "wappalyzer_pack" / "data"))
    out.update(load_retirejs_pack(signals_root / "retirejs_pack" / "data"))
    out.update(load_local_biz_pack(signals_root / "local_biz_pack"))
    return out


def iter_packs(catalog: dict[str, Technology]) -> Iterable[tuple[str, Technology]]:
    """Iterate (tech_name, Technology) regardless of pack origin."""
    for name, tech in catalog.items():
        yield name, tech
