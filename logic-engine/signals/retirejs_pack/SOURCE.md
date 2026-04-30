# retirejs_pack provenance

## Upstream

- **Project:** [RetireJS/retire.js](https://github.com/RetireJS/retire.js)
- **License:** Apache-2.0 (see `LICENSE` in this directory)
- **Snapshot commit:** `4e8af8ee6fa94c929f7de462fcbd05ffe28196b7`
- **Snapshot date:** 2026-04-24 (upstream commit timestamp)
- **Vendored on:** 2026-04-30
- **File size:** ~596 KB (`data/jsrepository.json`), 70 library entries

## What we vendor

- `data/jsrepository.json` — the canonical RetireJS vulnerability /
  version detection database. Used by the matcher engine to detect
  outdated JS libraries and known CVEs on candidate sites. We vendor
  the file verbatim (no filtering); it is small enough (< 1 MB) that
  selective filtering is not worth the maintenance overhead.
- `LICENSE` — Apache-2.0 copy from upstream root.

## How this pack is refreshed

```
git clone --depth=1 https://github.com/RetireJS/retire.js.git /tmp/retire-source
cp /tmp/retire-source/repository/jsrepository.json \
   logic-engine/signals/retirejs_pack/data/jsrepository.json
cp /tmp/retire-source/LICENSE.md \
   logic-engine/signals/retirejs_pack/LICENSE
```

Then update the **Snapshot commit** and **Snapshot date** fields above.

A scheduled refresh job is planned in
`logic-engine/signals/scripts/refresh_packs.py`.
