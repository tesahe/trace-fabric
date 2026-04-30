# NOTICE

TraceFabric
Copyright (c) 2026 TraceFabric authors

This product includes software developed by third parties. Their copyrights
and licenses are listed below. Each vendored dependency is isolated to its
own subdirectory under `logic-engine/signals/` so that license boundaries
are explicit and auditable.

The TraceFabric project itself is licensed under the Apache License,
Version 2.0 (see `LICENSE` at the repository root). The vendored
dependencies below retain their own licenses; nothing in this NOTICE
re-licenses them.

--------------------------------------------------------------------------------

## 1. enthec/webappanalyzer (technology fingerprints)

- **Upstream:** https://github.com/enthec/webappanalyzer
- **License:** GNU General Public License v3.0 (GPL-3.0)
- **Vendored under:** `logic-engine/signals/wappalyzer_pack/`
- **Files included:**
  - `logic-engine/signals/wappalyzer_pack/LICENSE` — GPL-3.0 verbatim
  - `logic-engine/signals/wappalyzer_pack/SOURCE.md` — provenance + snapshot commit
  - `logic-engine/signals/wappalyzer_pack/data/*.json` — filtered subset of
    upstream `src/technologies/*.json` and `src/categories.json`,
    produced by `logic-engine/signals/scripts/filter_wappalyzer.py`

Provenance, snapshot commit, and the filter category allowlist are
documented in `logic-engine/signals/wappalyzer_pack/SOURCE.md`.

### License isolation rationale

GPL-3.0 carries copyleft obligations. We treat the contents of
`logic-engine/signals/wappalyzer_pack/` as **opaque data** consumed at
runtime by the matcher engine, not as code linked into TraceFabric. To
make that boundary unambiguous:

1. The directory contains only JSON data plus this notice — no Python,
   no compiled artefacts.
2. No TraceFabric module imports from inside this directory; the
   matcher engine reads the JSON files via `pathlib`/`json.load` only.
3. Modifications to the data follow the upstream filter pipeline
   (re-run `filter_wappalyzer.py`); we do not maintain a fork of
   upstream signatures inside this pack.

If your downstream use of TraceFabric requires you to redistribute the
matcher binary alongside this signature pack, you must comply with the
GPL-3.0 terms for the contents of this directory. Stripping or
replacing the pack with your own signatures (e.g. a wholly TraceFabric-
or third-party-licensed alternative) removes that obligation.

--------------------------------------------------------------------------------

## 2. RetireJS (jsrepository.json)

- **Upstream:** https://github.com/RetireJS/retire.js
- **License:** Apache License, Version 2.0
- **Vendored under:** `logic-engine/signals/retirejs_pack/`
- **Files included:**
  - `logic-engine/signals/retirejs_pack/LICENSE` — Apache-2.0 verbatim
  - `logic-engine/signals/retirejs_pack/SOURCE.md` — provenance + snapshot commit
  - `logic-engine/signals/retirejs_pack/data/jsrepository.json` —
    upstream `repository/jsrepository.json` verbatim

The Apache-2.0 license is compatible with TraceFabric's own Apache-2.0
license. Attribution is preserved in the LICENSE and SOURCE.md files
inside the pack.

--------------------------------------------------------------------------------

## License boundaries summary

| Path                                               | License    |
| -------------------------------------------------- | ---------- |
| Repository root (TraceFabric source)               | Apache-2.0 |
| `logic-engine/signals/wappalyzer_pack/`            | GPL-3.0    |
| `logic-engine/signals/retirejs_pack/`              | Apache-2.0 |
| `logic-engine/signals/local_biz_pack/`             | Apache-2.0 |
| `logic-engine/signals/scripts/`                    | Apache-2.0 |

Future curated signatures landing in `local_biz_pack/` are TraceFabric
copyright and inherit the project's Apache-2.0 license. They MUST NOT
be copied verbatim from `wappalyzer_pack/`.
