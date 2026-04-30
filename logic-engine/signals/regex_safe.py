"""ReDoS-safe regex wrapper for the signals matcher.

Backend selection (logged once at import time):

1. Preferred: ``google-re2`` (``import re2``). RE2 uses a linear-time
   automaton and is immune to catastrophic backtracking, so we never have
   to time individual matches.
2. Fallback: stdlib ``re`` wrapped in a ``concurrent.futures.ThreadPoolExecutor``
   timeout. We use a thread (not SIGALRM) because:
     - SIGALRM is Unix-only and can't be combined with other signal users.
     - The matcher may eventually be called from worker threads where main-
       thread signals do not work.
   Default ``DEFAULT_TIMEOUT_MS`` per pattern is 100ms; on timeout the match
   is treated as a non-match and a warning is logged.

Pattern annotation parsing (Wappalyzer convention) lives here too because
both the loader and any ad-hoc tooling want it. Wappalyzer encodes the
literal two-character sequence ``\\;`` (backslash + semicolon) as a
sentinel for trailing annotations, e.g. ``foo\\;version:\\1\\;confidence:75``.
We split on that two-char sequence — never on a bare ``;`` — because
plenty of legitimate regexes contain ``;``.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 100

# Backend selection -----------------------------------------------------------

try:
    import re2 as _re2_module  # type: ignore

    _BACKEND = "re2"
    logger.info("regex_safe: using google-re2 backend (linear-time, ReDoS-immune)")
except ImportError:
    _re2_module = None
    _BACKEND = "re"
    logger.info(
        "regex_safe: google-re2 unavailable, falling back to stdlib re with %dms timeout",
        DEFAULT_TIMEOUT_MS,
    )


def backend() -> str:
    """Return the active regex backend name ('re2' or 're')."""
    return _BACKEND


# A shared executor for fallback timeouts. Daemon threads so they do not
# block process exit.
#
# IMPORTANT: when a regex match times out we abandon the future, but Python
# cannot actually kill the underlying thread — the regex.search() call
# continues running on the worker until it returns. With max_workers=1 a
# single pathological pattern would block every subsequent submit() until
# the stuck thread finishes (potentially many seconds). With a larger pool
# we tolerate a handful of concurrent zombie threads at the cost of a
# small amount of memory. 4 workers is a pragmatic upper bound for our
# expected per-lead pattern fan-out under ReDoS conditions.
_TIMEOUT_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="regex_safe_timeout"
)


# Annotation parser -----------------------------------------------------------


def split_annotations(raw_pattern: str) -> tuple[str, dict]:
    """Split a Wappalyzer pattern from its trailing ``\\;key:value`` annotations.

    Wappalyzer JSON encodes the literal two-character sequence ``\\;``
    (backslash + semicolon, which appears in the parsed Python string as
    ``"\\;"``) as the sentinel that delimits annotations. We split on that
    two-char sequence specifically — *not* on a bare ``;`` — because real
    regexes legitimately contain semicolons.

    Returns ``(regex_string, {"version": "\\1", "confidence": "50"})``.
    Unknown annotation keys are kept in the dict for future use.
    """
    parts = raw_pattern.split(r"\;")
    pattern = parts[0]
    annotations: dict[str, str] = {}
    for chunk in parts[1:]:
        if ":" in chunk:
            k, v = chunk.split(":", 1)
            annotations[k.strip()] = v
        else:
            # Some entries use a bare flag; record presence as empty string.
            annotations[chunk.strip()] = ""
    return pattern, annotations


# Compiled-pattern wrapper ----------------------------------------------------


@dataclass
class CompiledPattern:
    """Backend-agnostic compiled regex with annotation metadata.

    Use the module-level ``compile()`` to build instances; do not construct
    directly unless you know the backend semantics.
    """

    raw: str                        # original (post-annotation-split) regex source
    confidence: int                 # parsed from \;confidence:N, default 100
    version_template: Optional[str]  # parsed from \;version:..., e.g. "\1" or "\1.0"
    annotations: dict               # full parsed annotation dict (forward-compat)
    _compiled: object = None        # backend-specific compiled regex object
    _backend: str = "re"

    def search(self, text: str, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        """Run a search; returns a match-like object or None.

        On the re2 backend matches are linear-time and never timeout. On the
        stdlib-re backend the call is wrapped in a thread timeout so a
        pathological pattern cannot wedge the matcher.
        """
        if self._compiled is None:
            return None
        if self._backend == "re2":
            try:
                return self._compiled.search(text)
            except Exception as exc:  # pragma: no cover - re2 rarely raises post-compile
                logger.debug("regex_safe: re2 search raised %s on pattern %r", exc, self.raw)
                return None

        # stdlib fallback with timeout
        future = _TIMEOUT_EXECUTOR.submit(self._compiled.search, text)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except FuturesTimeoutError:
            logger.warning(
                "regex_safe: pattern timed out after %dms, treating as no-match: %r",
                timeout_ms,
                self.raw,
            )
            # Note: we cannot actually cancel the underlying re call. The
            # thread will eventually finish and the executor will reuse it.
            return None
        except Exception as exc:
            logger.debug("regex_safe: re search raised %s on pattern %r", exc, self.raw)
            return None

    def match_with_groups(
        self, text: str, timeout_ms: int = DEFAULT_TIMEOUT_MS
    ) -> Optional[tuple[str, ...]]:
        """Search; on hit return the tuple of capture groups (or empty tuple).

        Returns ``None`` if no match. Returns ``()`` if the pattern matched
        but had no capture groups. The tuple is what callers feed into a
        ``version_template`` substitution like ``"\\1"`` to extract a version.
        """
        m = self.search(text, timeout_ms=timeout_ms)
        if m is None:
            return None
        try:
            return m.groups()
        except Exception:
            return ()

    def extract_version(
        self, text: str, timeout_ms: int = DEFAULT_TIMEOUT_MS
    ) -> Optional[str]:
        """If the pattern matches and a version_template is set, expand it.

        Wappalyzer version templates are usually ``\\1`` (use group 1) but
        can also be a literal-with-substitution like ``\\1.0`` or even
        ``v\\1``. We do a simple group-number substitution; complex
        templates that re2 / re cannot do via ``Match.expand`` are not
        common in the corpus.
        """
        if self.version_template is None:
            return None
        m = self.search(text, timeout_ms=timeout_ms)
        if m is None:
            return None
        template = self.version_template
        try:
            groups = m.groups()
        except Exception:
            return None
        # Substitute \1, \2, ... with capture groups.
        result = template
        for idx, grp in enumerate(groups, start=1):
            if grp is not None:
                result = result.replace(f"\\{idx}", grp)
        # If template still has unresolved \N references, treat as no version.
        if "\\" in result:
            return None
        return result.strip() or None


def compile(pattern: str) -> Optional[CompiledPattern]:  # noqa: A001 - intentional shadow
    """Compile a Wappalyzer-style pattern string into a CompiledPattern.

    Strips trailing ``\\;version:..\\;confidence:N`` annotations first,
    then compiles the regex with the active backend. Returns ``None`` if
    the regex itself is invalid (so loaders can skip + log without
    aborting the whole pack).
    """
    if not pattern:
        return None
    regex_src, annotations = split_annotations(pattern)
    if not regex_src:
        return None

    confidence_raw = annotations.get("confidence", "100")
    try:
        confidence = max(0, min(100, int(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 100

    version_template = annotations.get("version") or None

    compiled_obj = None
    backend_name = _BACKEND
    try:
        if _BACKEND == "re2" and _re2_module is not None:
            # The PyPI `re2` package does NOT expose module-level flags like
            # IGNORECASE. Case-insensitive matching is requested via Options
            # (which not all wrappers honor uniformly) or — more reliably —
            # via an inline `(?i)` prefix in the pattern itself. We prepend
            # `(?i)` here so behavior matches stdlib re's IGNORECASE.
            compiled_obj = _re2_module.compile("(?i)" + regex_src)
        else:
            compiled_obj = re.compile(regex_src, re.IGNORECASE)
    except Exception as exc:
        # re2 is stricter than re (rejects backreferences, lookarounds, ...).
        # Fall back to stdlib re for that specific pattern so we don't drop
        # signatures that happen to use unsupported re2 features.
        if _BACKEND == "re2":
            try:
                compiled_obj = re.compile(regex_src, re.IGNORECASE)
                backend_name = "re"
            except Exception as exc2:
                logger.debug(
                    "regex_safe: failed to compile pattern %r (re2: %s; re: %s)",
                    regex_src,
                    exc,
                    exc2,
                )
                return None
        else:
            logger.debug("regex_safe: failed to compile pattern %r: %s", regex_src, exc)
            return None

    return CompiledPattern(
        raw=regex_src,
        confidence=confidence,
        version_template=version_template,
        annotations=annotations,
        _compiled=compiled_obj,
        _backend=backend_name,
    )
