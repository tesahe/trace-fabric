"""Shared fixtures for signals tests.

Two important roles:

  1. Make ``signals.*`` importable when pytest is run from inside
     ``logic-engine/`` (the directory name has a hyphen so it's not a
     valid Python package).
  2. Provide a Matcher singleton + fixture-loader helpers so per-test
     setup is one line.

The Matcher is a session-scoped fixture because pattern compilation is
the expensive bit (~3000 techs, ~15000 patterns) and the matcher has no
per-scan state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pytest

# logic-engine/ -> on sys.path so `import signals.matcher` works.
_LOGIC_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_LOGIC_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_LOGIC_ENGINE_ROOT))

from signals.matcher import Matcher  # noqa: E402
from signals.raw_lead_builder import build_raw_lead_from_html  # noqa: E402


FIXTURES_ROOT = Path(__file__).resolve().parent / "fixtures"
RAW_HTML_DIR = FIXTURES_ROOT / "raw_html"
EXPECTED_DIR = FIXTURES_ROOT / "expected"


@pytest.fixture(scope="session")
def matcher() -> Matcher:
    """One Matcher per test session — pattern compilation is expensive."""
    return Matcher()


@pytest.fixture(scope="session")
def matcher_no_blocklist() -> Matcher:
    """Matcher with the blocklist disabled, for tests that need raw output."""
    return Matcher(apply_blocklist=False)


def load_expected(fixture_name: str) -> dict:
    """Read the canonical expected-detections JSON for one fixture."""
    stem = Path(fixture_name).stem
    path = EXPECTED_DIR / f"{stem}.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_fixture_lead(fixture_name: str, expected: Optional[dict] = None) -> dict:
    """Build a RawLead dict from a fixture HTML + its expected JSON's hints.

    The expected JSON optionally carries ``url``, ``synthetic_headers``, and
    ``robots_body`` blocks — they are forwarded into the RawLead so header /
    cookie / DNS / robots patterns are testable from disk-only inputs.
    """
    html_path = RAW_HTML_DIR / fixture_name
    if expected is None:
        expected = load_expected(fixture_name)
    return build_raw_lead_from_html(
        html_path=html_path,
        url=expected.get("url", ""),
        synthetic_headers=expected.get("synthetic_headers"),
        robots_body=expected.get("robots_body"),
    )
