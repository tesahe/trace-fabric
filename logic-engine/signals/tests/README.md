# signals tests

Tests for the matcher engine, blocklist, regex_safe wrapper, and resolver.

## Running

The repo's top-level directory is `logic-engine` (with a hyphen) which is
not a valid Python package name. Run pytest from inside that directory so
the project layout works:

```bash
cd logic-engine
pytest signals/tests/ -v
```

`signals/tests/conftest.py` puts `logic-engine/` on `sys.path` so
`import signals.matcher` resolves regardless of where you launch pytest
from, but `pyproject.toml`'s `[tool.pytest.ini_options]` is anchored at
`logic-engine/` so the simplest invocation is the one above.

## Layout

```
signals/tests/
  conftest.py                  # Matcher singleton + fixture loaders
  fixtures/
    raw_html/                  # 12 hand-crafted HTML samples
    expected/                  # canonical expected detections per fixture
  test_matcher_snapshots.py    # parametrized over the 12 fixtures
  test_resolver_implies.py     # implies/requires/excludes/dedup
  test_regex_safe.py           # re2 backend + ReDoS bound
  test_blocklist.py            # FP suppression / downgrade / corroboration
```

## Adding a fixture

1. Drop a realistic HTML sample into `fixtures/raw_html/<name>.html`.
2. Write `fixtures/expected/<name>.json` with the schema:

```json
{
  "fixture": "<name>.html",
  "url": "https://...",
  "synthetic_headers": [
    {"key": "...", "value": "..."}
  ],
  "must_detect": [
    {"name": "TechName", "pack": "wappalyzer", "min_confidence": 80}
  ],
  "must_not_detect": ["FalsePositiveTech"],
  "notes": "human notes"
}
```

3. Add `<name>.html` to the `FIXTURE_NAMES` list in
   `test_matcher_snapshots.py`.

`must_detect` items are mandatory — the test fails if any are missing.
`must_not_detect` items are mandatory absent — the test fails if any
appear. Extras beyond `must_detect` are allowed.
