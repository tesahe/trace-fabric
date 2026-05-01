"""Focused tests for the regex_safe wrapper.

We verify:
  * compile() builds a CompiledPattern with parsed annotations.
  * search() matches expected literals.
  * A catastrophic-backtracking pattern terminates in <500ms (timeout works).
  * The active backend is reported.
"""

from __future__ import annotations

import time

import pytest

from signals.regex_safe import (
    CompiledPattern,
    DEFAULT_TIMEOUT_MS,
    backend,
    compile as compile_pattern,
    split_annotations,
)


def test_backend_is_one_of_known():
    assert backend() in {"re2", "re"}


def test_compile_returns_compiled_pattern():
    cp = compile_pattern(r"foo")
    assert isinstance(cp, CompiledPattern)
    assert cp.confidence == 100      # default when no \;confidence: annotation
    assert cp.version_template is None


def test_compile_parses_annotations():
    cp = compile_pattern(r"WordPress(?: ([\d.]+))?\;version:\1\;confidence:75")
    assert cp.confidence == 75
    assert cp.version_template == r"\1"


def test_search_finds_known_literal():
    cp = compile_pattern(r"wp-content/plugins")
    m = cp.search("https://example.com/wp-content/plugins/foo.js")
    assert m is not None


def test_search_returns_none_on_no_match():
    cp = compile_pattern(r"shopify\.com")
    m = cp.search("https://wordpress.org/")
    assert m is None


def test_extract_version_resolves_template():
    cp = compile_pattern(r"WordPress (\d+\.\d+(?:\.\d+)?)\;version:\1")
    v = cp.extract_version("WordPress 6.4.2")
    assert v == "6.4.2"


def test_split_annotations_splits_on_backslash_semicolon_only():
    """Bare `;` inside a regex must NOT split. Only the `\\;` sentinel does."""
    head, anns = split_annotations(r"foo;bar\;version:\1")
    assert head == "foo;bar"
    assert anns == {"version": r"\1"}


def test_redos_pattern_on_re2_backend_is_linear():
    """re2 is immune to ReDoS by design — verify a textbook adversarial pattern
    completes quickly when the re2 backend is active.

    Critically, this test must verify the per-pattern backend, not just the
    global backend(). compile() may fall back per-pattern to stdlib re for
    regexes that re2 cannot handle (backreferences, lookarounds, etc.).
    Running a ReDoS pattern through the stdlib fallback would leave a
    zombie thread blocking pytest exit via atexit's executor join.
    """
    cp = compile_pattern(r"(a+)+$")
    if cp is None:
        pytest.skip("backend rejected the test pattern at compile time")
    if cp._backend != "re2":
        pytest.skip("this specific pattern fell back to stdlib re; the ReDoS test would leak a zombie thread")
    text = "a" * 30 + "b"
    start = time.monotonic()
    result = cp.search(text)
    elapsed_ms = (time.monotonic() - start) * 1000
    assert elapsed_ms < 500, f"re2 search took {elapsed_ms:.1f}ms — should be linear"
    assert result is None or hasattr(result, "span")


def test_timeout_mechanism_returns_none_on_slow_match():
    """Without exercising real backtracking, verify the fallback timeout path
    returns None (rather than hanging or raising) when a match exceeds its budget.

    We simulate a slow match by monkey-patching the compiled pattern's
    backend object with one whose ``search`` sleeps. This exercises the
    ThreadPoolExecutor + future.result(timeout=...) path without depending
    on actual regex pathology.
    """
    import time as _time

    cp = compile_pattern(r"foo")
    if cp is None:
        pytest.skip("compile_pattern returned None for a trivial regex")

    class _SlowBackend:
        def search(self, text):
            _time.sleep(0.5)  # well past 100ms timeout
            return object()  # would-be "match" if we waited

    # Force the fallback path regardless of the live backend
    cp._compiled = _SlowBackend()
    cp._backend = "re"

    start = _time.monotonic()
    result = cp.search("anything", timeout_ms=100)
    elapsed_ms = (_time.monotonic() - start) * 1000
    # Should time out at ~100ms, not wait the full 500ms
    assert elapsed_ms < 300, f"timeout did not fire: took {elapsed_ms:.1f}ms"
    assert result is None, "timed-out search should return None"


def test_re2_backend_active_when_installed():
    """If google-re2 is installed in the env, the wrapper picks it.

    Skipped (with reason) if re2 isn't installed — that's the documented
    fallback behavior, not a failure mode.
    """
    try:
        import re2  # noqa: F401
    except ImportError:
        pytest.skip("google-re2 not installed; stdlib re fallback is also acceptable")
    assert backend() == "re2", f"google-re2 importable but backend reports {backend()!r}"


def test_invalid_regex_returns_none():
    """An unparseable regex returns None (not a thrown exception)."""
    cp = compile_pattern(r"(unclosed")
    assert cp is None
