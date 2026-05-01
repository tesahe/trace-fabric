"""Matcher engine: runs vendored signature packs over a parsed RawLead.

Architectural note: we follow the rverton/webanalyze (Go) pattern of
"compile once, then one pass per artifact type." For each ``MatchSource``
we:

  1. Pre-compute the haystack string(s) from the RawLead exactly once.
  2. Iterate every Technology that has patterns of that source type.
  3. Iterate that tech's patterns, calling ``CompiledPattern.search``.

This avoids redoing string-joins (e.g. flattening response_headers) per
pattern. With ~5k Wappalyzer techs and ~15k patterns, that matters.

All regex evaluation goes through ``regex_safe.CompiledPattern`` — never
raw ``re.search``. That contract is a Sprint 1 hard requirement.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from bs4 import BeautifulSoup

from . import blocklist as blocklist_mod
from .blocklist import BlocklistConfig, EMPTY_CONFIG
from .detection import Detection, MatchSource, truncate_value
from .loader import LoadedPattern, Technology, load_all_packs
from .regex_safe import CompiledPattern
from .resolver import resolve

logger = logging.getLogger(__name__)

# Default location of the vendored signal packs (this file's parent dir).
_DEFAULT_SIGNALS_ROOT = Path(__file__).resolve().parent

# Default blocklist YAML — lives next to this module for trivially deterministic loading.
_DEFAULT_BLOCKLIST_PATH = _DEFAULT_SIGNALS_ROOT / "false_positive_blocklist.yaml"

# DNS-style header keys we are willing to treat as "DNS hints" without
# doing a live lookup. Keep this small; over-broad inclusion creates
# false positives for whatever happens to live in those headers.
_DNS_HEADER_KEYS = frozenset({"via", "server", "x-powered-by", "x-served-by"})


# Artifact pre-computation ----------------------------------------------------


def _join_url_list(items) -> str:
    """Flatten a list of {"url": ...} dicts into a newline-joined URL string."""
    if not isinstance(items, list):
        return ""
    out: list[str] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            out.append(item["url"])
        elif isinstance(item, str):
            out.append(item)
    return "\n".join(out)


def _flatten_headers(headers) -> tuple[str, str, list[tuple[str, str]]]:
    """Return (joined_kv, joined_set_cookie, raw_pairs).

    - joined_kv: "key: value" lines for use with ``headers`` patterns.
    - joined_set_cookie: just the Set-Cookie values, one per line.
    - raw_pairs: list of (key_lower, value) tuples for header-name lookups.
    """
    if not isinstance(headers, list):
        return "", "", []
    pairs: list[tuple[str, str]] = []
    kv_lines: list[str] = []
    cookie_lines: list[str] = []
    for h in headers:
        if not isinstance(h, dict):
            continue
        k = h.get("key")
        v = h.get("value")
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        pairs.append((k.lower(), v))
        kv_lines.append(f"{k}: {v}")
        if k.lower() == "set-cookie":
            cookie_lines.append(v)
    return "\n".join(kv_lines), "\n".join(cookie_lines), pairs


def _parse_meta(raw_html: str) -> str:
    """Walk meta tags in raw_html and return "name=content" lines."""
    if not raw_html:
        return ""
    try:
        soup = BeautifulSoup(raw_html, "lxml")
    except Exception:
        try:
            soup = BeautifulSoup(raw_html, "html.parser")
        except Exception:
            return ""
    lines: list[str] = []
    for meta in soup.find_all("meta"):
        # Wappalyzer ``meta`` patterns key on `name` (or `property` /
        # `http-equiv`); the value side is the meta tag's `content` attr.
        for name_attr in ("name", "property", "http-equiv", "itemprop"):
            name_val = meta.get(name_attr)
            if not name_val:
                continue
            content = meta.get("content", "") or ""
            lines.append(f"{name_val}={content}")
            break
    return "\n".join(lines)


def _pick_url(raw_lead: dict) -> str:
    final = raw_lead.get("final_url")
    if isinstance(final, str) and final:
        return final
    src = raw_lead.get("source_url")
    if isinstance(src, str):
        return src
    return ""


def _pick_robots_body(raw_lead: dict) -> str:
    robots = raw_lead.get("robots_txt") or {}
    if not isinstance(robots, dict):
        return ""
    if not robots.get("exists"):
        return ""
    body = robots.get("body")
    return body if isinstance(body, str) else ""


# Per-source matching --------------------------------------------------------


def _detect_for_pattern(
    tech: Technology,
    source: MatchSource,
    pattern: LoadedPattern,
    haystack: str,
    matched_field: str,
) -> Optional[Detection]:
    """Run one CompiledPattern over a haystack; build a Detection on hit."""
    if not haystack:
        return None
    compiled: CompiledPattern = pattern.compiled
    m = compiled.search(haystack)
    if m is None:
        return None

    # Try to lift the match span for matched_value; on re2 the API is the
    # same as re. If span() fails for any reason, fall back to a slice of
    # the haystack head so we always have *something* in the audit field.
    try:
        start, end = m.span()
        snippet = haystack[start:end]
    except Exception:
        snippet = haystack[:200]

    version = compiled.extract_version(haystack)

    return Detection(
        name=tech.name,
        pack=tech.pack,
        categories=tech.categories,
        confidence=compiled.confidence,
        version=version,
        source=source,
        matched_field=matched_field,
        matched_value=truncate_value(snippet),
        pattern_id=f"{tech.pack}:{tech.name}:{source.value}#{pattern.pattern_index}",
        cpe=tech.cpe,
        pricing=tech.pricing,
        saas=tech.saas,
        oss=tech.oss,
        website=tech.website,
    )


def _scan_source(
    techs: Iterable[Technology],
    source: MatchSource,
    haystack: str,
    matched_field: str,
    qualifier_filter=None,
) -> list[Detection]:
    """Scan one haystack with every pattern of one MatchSource across all techs.

    ``qualifier_filter`` is an optional callable ``(qualifier) -> bool``;
    used by header / cookie / meta scans to narrow patterns to those whose
    qualifier matches a specific key. Pass ``None`` (the default) to mean
    "run every pattern regardless of qualifier."
    """
    detections: list[Detection] = []
    for tech in techs:
        bucket = tech.patterns_by_source.get(source)
        if not bucket:
            continue
        for pattern in bucket:
            if qualifier_filter is not None and not qualifier_filter(pattern.qualifier):
                continue
            det = _detect_for_pattern(tech, source, pattern, haystack, matched_field)
            if det is not None:
                detections.append(det)
    return detections


# Public API ------------------------------------------------------------------


class Matcher:
    """Stateful matcher: load packs once, scan many leads.

    Construct once at process startup and reuse — pattern compilation is
    the expensive bit, and the matcher itself holds no per-scan state.
    """

    def __init__(
        self,
        packs_root: Optional[Path] = None,
        apply_blocklist: bool = True,
        blocklist_path: Optional[Path] = None,
    ) -> None:
        root = packs_root if packs_root is not None else _DEFAULT_SIGNALS_ROOT
        self.catalog: dict[str, Technology] = load_all_packs(root)
        self._techs_list: list[Technology] = list(self.catalog.values())
        logger.info("Matcher: loaded %d technologies across all packs", len(self._techs_list))

        # Blocklist is opt-in (default True). When opted out we still hold a
        # config object so callers can inspect / swap it without None-checks.
        self.apply_blocklist = apply_blocklist
        bl_path = blocklist_path if blocklist_path is not None else _DEFAULT_BLOCKLIST_PATH
        if apply_blocklist:
            self.blocklist_config: BlocklistConfig = blocklist_mod.load_blocklist(bl_path)
        else:
            self.blocklist_config = EMPTY_CONFIG

    def match(self, raw_lead: dict) -> list[Detection]:
        """Run every applicable signature against ``raw_lead``.

        ``raw_lead`` is the dict shape produced by ``lead_processor.parse``
        from the Rust scraper protobuf. Missing fields are tolerated;
        scan steps with empty haystacks are skipped.
        """
        if not isinstance(raw_lead, dict):
            return []

        # Pre-compute every haystack ONCE.
        raw_html = raw_lead.get("raw_html") or ""
        text_content = raw_lead.get("text_content") or ""
        script_src_joined = _join_url_list(raw_lead.get("script_srcs"))
        css_joined = _join_url_list(raw_lead.get("stylesheet_hrefs"))
        headers_joined, cookies_joined, header_pairs = _flatten_headers(
            raw_lead.get("response_headers")
        )
        meta_joined = _parse_meta(raw_html)
        url = _pick_url(raw_lead)
        robots_body = _pick_robots_body(raw_lead)

        techs = self._techs_list
        raw_detections: list[Detection] = []

        # script_src
        raw_detections.extend(
            _scan_source(techs, MatchSource.SCRIPT_SRC, script_src_joined, "script_srcs[].url")
        )
        # html
        raw_detections.extend(_scan_source(techs, MatchSource.HTML, raw_html, "raw_html"))
        # css (URL-only; we don't fetch live CSS bodies)
        raw_detections.extend(
            _scan_source(techs, MatchSource.CSS, css_joined, "stylesheet_hrefs[].url")
        )
        # headers — patterns may carry a qualifier (header name) in which
        # case we narrow the haystack to just lines for that header.
        for tech in techs:
            bucket = tech.patterns_by_source.get(MatchSource.HEADERS)
            if not bucket:
                continue
            for pattern in bucket:
                if pattern.qualifier:
                    qual = pattern.qualifier.lower()
                    matching_values = [v for k, v in header_pairs if k == qual]
                    if not matching_values:
                        continue
                    haystack = "\n".join(matching_values)
                    matched_field = f"response_headers[{pattern.qualifier}]"
                else:
                    haystack = headers_joined
                    matched_field = "response_headers[*]"
                det = _detect_for_pattern(
                    tech, MatchSource.HEADERS, pattern, haystack, matched_field
                )
                if det is not None:
                    raw_detections.append(det)

        # cookies — Wappalyzer ``cookies`` patterns are per-cookie-name
        # against the cookie value (NOT against the "name=value" prefix).
        # We get cookies from Set-Cookie response headers (best we can
        # do server-side without a real cookie jar).
        for tech in techs:
            bucket = tech.patterns_by_source.get(MatchSource.COOKIES)
            if not bucket:
                continue
            for pattern in bucket:
                if pattern.qualifier and cookies_joined:
                    qual = pattern.qualifier
                    prefix = f"{qual}="
                    # Strip "cookie_name=" prefix from each relevant line
                    # so the pattern actually matches the value.
                    relevant_values: list[str] = []
                    for line in cookies_joined.split("\n"):
                        stripped = line.lstrip()
                        if stripped.startswith(prefix):
                            # Cookie value runs to the first ';' (attrs follow).
                            value = stripped[len(prefix):].split(";", 1)[0]
                            relevant_values.append(value)
                    if not relevant_values:
                        continue
                    haystack = "\n".join(relevant_values)
                    matched_field = f"set_cookie[{qual}]"
                else:
                    haystack = cookies_joined
                    matched_field = "set_cookie[*]"
                det = _detect_for_pattern(
                    tech, MatchSource.COOKIES, pattern, haystack, matched_field
                )
                if det is not None:
                    raw_detections.append(det)

        # meta — qualifier is the meta name; the pattern is meant to match
        # the *content* attribute, so we strip the "name=" prefix from each
        # line before handing the haystack to the pattern.
        for tech in techs:
            bucket = tech.patterns_by_source.get(MatchSource.META)
            if not bucket:
                continue
            for pattern in bucket:
                if pattern.qualifier and meta_joined:
                    qual = pattern.qualifier
                    prefix = f"{qual}="
                    relevant_values = [
                        line[len(prefix):]
                        for line in meta_joined.split("\n")
                        if line.startswith(prefix)
                    ]
                    if not relevant_values:
                        continue
                    haystack = "\n".join(relevant_values)
                    matched_field = f"meta[{qual}]"
                else:
                    haystack = meta_joined
                    matched_field = "meta[*]"
                det = _detect_for_pattern(
                    tech, MatchSource.META, pattern, haystack, matched_field
                )
                if det is not None:
                    raw_detections.append(det)

        # url
        raw_detections.extend(_scan_source(techs, MatchSource.URL, url, "final_url"))

        # robots
        raw_detections.extend(
            _scan_source(techs, MatchSource.ROBOTS, robots_body, "robots_txt.body")
        )

        # text
        raw_detections.extend(
            _scan_source(techs, MatchSource.TEXT, text_content, "text_content")
        )

        # dns (header-only fallback) — only run patterns whose qualifier is
        # a known DNS-ish header AND that header is actually present.
        for tech in techs:
            bucket = tech.patterns_by_source.get(MatchSource.DNS_HEADER)
            if not bucket:
                continue
            for pattern in bucket:
                qual = (pattern.qualifier or "").lower()
                if qual not in _DNS_HEADER_KEYS:
                    continue
                matching_values = [v for k, v in header_pairs if k == qual]
                if not matching_values:
                    continue
                haystack = "\n".join(matching_values)
                det = _detect_for_pattern(
                    tech,
                    MatchSource.DNS_HEADER,
                    pattern,
                    haystack,
                    f"dns_header[{qual}]",
                )
                if det is not None:
                    raw_detections.append(det)

        # Final pass: implies/requires/excludes + dedup.
        resolved = resolve(raw_detections, self.catalog)
        if not self.apply_blocklist:
            return resolved
        return blocklist_mod.apply(resolved, self.blocklist_config)
