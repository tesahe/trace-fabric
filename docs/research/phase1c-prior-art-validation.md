# Phase 1c: Prior Art Validation for TraceFabric Sprint 1 Matcher Engine

**Status:** Research complete | **Author:** Rondo (research pass) | **Date:** 2026-04-30

---

## 1. TL;DR — Go, with three concrete adjustments

**Verdict: GO.** The planned architecture (vendor `enthec/webappanalyzer` + `retire.js` JSON, build a `signals/matcher.py` that consumes the raw signature JSON, snapshot tests on fixture HTMLs, wire detections into `heuristic_flags["technologies"]`) is well-trodden ground. Multiple production tools — `rverton/webanalyze` (Go), `chorsley/python-Wappalyzer`, `s0md3v/wappalyzer-next`, `PigeonSec/py-wappalyzer` — implement essentially the matcher we're planning, and at least one public dev.to writeup ([dapdev, Feb 2026](https://dev.to/dapdev/build-a-sales-lead-qualification-tool-with-technology-detection-34k3)) walks through exactly the "Wappalyzer + tiered weights for B2B lead scoring" pattern we're building toward.

**Three adjustments to the plan:**

1. **Roll our own matcher, don't vendor `py-wappalyzer` or `wappalyzer-next`.** Both are GPL-3.0; vendoring their Python *code* taints `logic-engine`. Vendoring just the enthec **JSON data** is much safer (see §5 GPL note). Our matcher is ~300 lines — building it cleanly is faster than ripping GPL out of someone else's package and lets us drop the `js`/`dom`/`probe`/`xhr`/`dns` pattern types we can't evaluate anyway.
2. **Pre-compile a per-signature-type pattern index, not a per-technology loop.** This is what `rverton/webanalyze` does and what makes it fast at scale. Iterating ~700 sigs × every header/script for every lead is fine; iterating naïvely with one `re.search` call per (sig, field) pair is 20× slower. Use `re.compile` once at startup, group by signal type, and run one pass per field type.
3. **Hard-suppress a small false-positive blocklist on day one.** Cloudflare, jQuery, Google Analytics, and Bootstrap regex patterns are notorious for bleeding ([wappalyzer #2898](https://github.com/wappalyzer/wappalyzer/issues/2898), [Verneaut lab writeup](https://lab.julienverneaut.com/wappalyzer/) showing 1,929 spurious detections from injected fake signatures). Either downgrade their confidence by 50 or require a corroborating signal (e.g., Cloudflare only fires when both a script *and* a header match).

---

## 2. Existing Python matcher implementations

| Repo | Stars | Last activity | License | Notes |
|------|-------|---------------|---------|-------|
| [`chorsley/python-Wappalyzer`](https://github.com/chorsley/python-Wappalyzer) | 322 | **Archived Apr 2024** | GPL-3.0 | Battle-tested. `Wappalyzer.latest(update=False).analyze_with_versions_and_categories(WebPage)`. Clean API, but archived and uses old apps.json schema — not enthec-compatible out of the box. Useful as a *reference implementation*, not a dependency. |
| [`s0md3v/wappalyzer-next`](https://github.com/s0md3v/wappalyzer-next) | 368 | **Apr 28, 2026 (active)** | GPL-3.0 | Three modes: fast (single GET), balanced (multi-asset + DNS), full (Selenium + actual Wappalyzer extension). Runs Firefox via geckodriver in full mode — heavy. CLI-first, library exposes `analyze(url, scan_type, threads, cookie)`. Open issues #27, #29 are regex/version-extraction bugs — instructive about edge cases to test. |
| [`PigeonSec/py-wappalyzer`](https://github.com/PigeonSec/py-wappalyzer) | 1 | New (3 commits) | unspecified | Uses enthec sigs. Built around HAR ingestion via Patchright. Does pattern matching over URL/HTML/scripts/headers/cookies/meta/DNS/cert issuer. Tiny, simple — useful as a *reading reference* but the API (HAR-centric) doesn't fit our `RawLead` dict shape. |
| [`rverton/webanalyze`](https://github.com/rverton/webanalyze) (Go, not Python — but the architecture transfers cleanly) | n/a | Active | MIT | The cleanest matcher architecture we found. Pre-compiles per-signal regex sets (`HTMLRegex`, `ScriptRegex`, `URLRegex`, `HeaderRegex`, `CookieRegex`, `MetaRegex`) on each `App` struct, splits patterns on `\;` to extract version metadata, then runs one pass per artifact type via `FindInHeaders()`-style functions. Already loads enthec sigs. **Steal this architecture wholesale.** |
| [`tylerpuig/wapalyzer-core`](https://github.com/tylerpuig/wapalyzer-core) | small | recent | unspecified | JS, fork of removed wappalyzer-core. Exports `Wappalyzer` class with `setTechnologies / setCategories / analyze / resolve` — the `resolve()` step is where `implies` cascading happens. Worth borrowing the resolve-step concept. |

**For retire.js specifically:**

- [`FallibleInc/retirejslib`](https://github.com/FallibleInc/retirejslib) — Apache-2.0 Python port. Stale (latest visible activity references jQuery 1.6 era). 52 stars. **Don't take a runtime dep**; cannibalize the matcher logic and pin our own copy of `jsrepository.json`.
- [`stamparm/DSJS`](https://github.com/stamparm/DSJS) ("Damn Small JS Scanner") — sub-100-line retire.js port. Excellent reference for how minimal this can be.

**Bottom line for §2:** No clean, MIT/BSD-licensed, actively-maintained, enthec-native Python matcher exists. That validates building our own.

---

## 3. Lead-scoring projects using Wappalyzer-style fingerprinting

The most directly relevant prior art:

- **[dev.to "Build a Sales Lead Qualification Tool with Technology Detection"](https://dev.to/dapdev/build-a-sales-lead-qualification-tool-with-technology-detection-34k3)** (Feb 2026). Uses a `TechDetectClient` API wrapper, applies a Python dictionary-based scoring config, tiers leads as Hot ≥60 / Warm 35–59 / Cold 15–34 / Disqualified <15. Sample weights they used: Shopify 30, Shopify Plus 25, Recharge 15, Stripe/Klaviyo/Gorgias 10 each, GA/Hotjar/Yotpo 5–8 each. **This is the exact pattern we're building**, just with our own matcher behind it instead of a paid API. Our YAML weights file should follow this shape.
- **[saber.app "Composite Signal Score" glossary](https://www.saber.app/glossary/composite-signal-score)** — multi-signal scoring framework: firmographic + behavioral + intent + technographic, all summed. Rule-based for transparency until you have 500+ leads/month, then ML. Maps cleanly to our planned ensemble (heuristic flags + tech detections + later validation signals).
- **[prospeo.io "Technographic Data for Lead Scoring 2026 Guide"](https://prospeo.io/s/technographic-data-for-lead-scoring)** — argues tech-stack signals are stronger predictors of buying behavior than firmographic-only scoring. Validates the upgrade path.
- **No open-source project we found** ships the *exact* "Wappalyzer + custom local-biz overlay + YAML weights" combo. The `unifygtm` and `clay.com` writeups describe this in commercial waterfall-enrichment products, but no OSS reference implementation. Translation: nobody will hand us a runnable repo to clone, but everybody agrees the architecture is sound.

---

## 4. Architectural patterns — recommendations

### 4.1 Engine structure: per-signal-type pipeline (not per-pack, not async)

**Recommended:** Iterate the *artifacts* (headers, scripts, html, etc.) once each, and within each iteration walk the pre-compiled signature index for that artifact type. This is what `webanalyze` does and what scales linearly. Per-pack (one detector per signature pack) is cleaner conceptually but doubles work since enthec and retire.js largely operate on the same artifact (scriptSrc). Async is overkill — at our scale (one lead at a time, ~700 sigs, ~50 scripts per page), this is a sub-100ms operation if regexes are pre-compiled.

```
load_packs() -> {field_type: [(sig_id, compiled_regex, version_tmpl, confidence, tech_meta), ...]}
match(raw_lead) -> for each field in raw_lead, walk the index for that field, collect Detections
resolve(detections) -> apply 'implies' cascading, dedupe, downgrade flagged FP families
```

### 4.2 Confidence propagation

The enthec schema annotates patterns inline: `"example-([0-9.]+)\\.js\\;confidence:50\\;version:\\1"`. Wappalyzer's own behavior is that **a technology fires only when total accumulated confidence ≥ 100** across all matching patterns. We should preserve this: each `Detection` carries `match_confidence` (parsed from the sig), and the resolver sums per-tech before emitting. This gives us a free knob — if a tech matches with confidence 50 only, we can either drop it or pass it downstream as "weak signal" and let YAML weights decide. **Do that.** Don't drop sub-100 detections at the matcher; surface them with a flag.

`implies` cascading is non-trivial — see [tylerpuig/wapalyzer-core](https://github.com/tylerpuig/wapalyzer-core)'s `resolve()` step. Implies can themselves carry confidence (`"implies": "PHP\\;confidence:50"`). For Sprint 1, implement a single-level implies pass; skip multi-hop cascading until we hit a real case that needs it.

### 4.3 Update cadence for vendored sigs

**Pin and snapshot.** Don't auto-pull. The enthec repo updates regularly (dec 2025 was the last published reference; it's actively maintained as the de-facto Wappalyzer successor since [Wappalyzer went private Aug 2023](https://github.com/enthec/webappanalyzer)). Pattern to copy:

- Git submodule or vendored `signatures/enthec-vYYYYMMDD/` directory.
- Quarterly bump as a deliberate PR. Run snapshot regression tests against the 10 fixture HTMLs; review diff.
- A GitHub Action that opens a PR weekly with the diff is fine *as a notification*, but don't auto-merge.

Same model for retire.js's `jsrepository.json`.

---

## 5. Gotchas to avoid

1. **Static-HTML-only loses meaningful coverage on JS-heavy sites.** The community consensus ([SEOmator alternatives review](https://seomator.com/blog/wappalyzer-alternatives), Wappalyzer extension docs) is that the browser-extension mode catches React/Vue/Next.js/dynamically-injected widgets that static HTML misses. There's no clean public benchmark, but informal estimates put Wappalyzer's overall accuracy at ~94% in browser mode and "obviously lower" in static mode. **Mitigation:** for our local-biz target segment (Squarespace/Shopify/WordPress/Wix/HubSpot/Calendly/Mailchimp/Stripe), the relevant signatures live in static HTML, headers, and script src URLs — exactly what reqwest gives us. We should document this explicitly: "TraceFabric matches the ~70% of signatures that don't require JS runtime; the missed 30% is mostly JS frameworks our ICP doesn't care about."

2. **Schema fields we cannot evaluate — skip at load time, don't fail.** When parsing enthec JSON, drop these pattern types entirely: `js` (requires page execution context), `dom` (needs rendered DOM), `xhr` (needs request observation), `probe` (active probe), `dns` (separate lookup), `certIssuer` (TLS cert inspection — our scraper might add later, for Sprint 1 skip). Keep: `headers`, `cookies`, `meta`, `scriptSrc`, `scripts`, `html`, `text`, `css`, `url`, `robots`. Filtering at load time also means our ~700 signature filter shrinks naturally to whatever subset has any usable patterns.

3. **Catastrophic regex backtracking is real.** Wappalyzer signatures are community-contributed and not RE2-safe. Python's `re` engine will hang on pathological inputs ([Frederickson's blog post](https://www.benfrederickson.com/python-catastrophic-regular-expressions-and-the-gil/) is the canonical horror story — single regex pinning a CPU and blocking the GIL across an entire process). **Mitigation:** wrap each `re.search` in a per-pattern timeout (use `signal.alarm` on Linux, or run matching in a `concurrent.futures` thread pool with a 2-sec budget per signature), or — better — switch to [`google-re2`](https://pypi.org/project/google-re2/) for a guaranteed linear-time engine. We'll need to verify enthec patterns compile under RE2; some won't (lookbehinds aren't supported), in which case fall back to `re` for those few with a logged warning.

4. **Notorious false-positive families.** From [issue #2898](https://github.com/wappalyzer/wappalyzer/issues/2898) and the [Verneaut lab](https://lab.julienverneaut.com/wappalyzer/) writeup which spoofed 1,929 fake detections by injecting matching strings: Cloudflare (often fires from any `cf-*` cookie/header echoed by other CDNs), jQuery (matches inline mentions in comments and unrelated scripts), Google Analytics (any `gtag` mention, even in a tutorial blog post), generic CDN signatures, and meta-tag generators. **Mitigation:** require corroborating signals for the worst offenders (e.g., Cloudflare needs both header *and* asset URL; Google Analytics needs script src *and* a `G-` measurement ID). Alternatively, downgrade their confidence to 50 in our config overlay so they need a second signal to fire.

5. **GPL-3.0 license trap.** Vendoring enthec's *JSON pattern data* into a closed-source product is the gray area. The FSF's "mere aggregation" doctrine ([GPL FAQ](https://www.gnu.org/licenses/old-licenses/gpl-2.0-faq.en.html), [LWN article](https://lwn.net/Articles/417852/)) generally treats data files that the program merely reads as aggregation, not derivation — which is the reading every Wappalyzer-based commercial product (BuiltWith, Wappalyzer Inc., SimilarTech, etc.) implicitly relies on. **However**, vendoring the *Python source code* of `python-Wappalyzer` or `wappalyzer-next` (both GPL-3.0) into `logic-engine` would arguably make `logic-engine` a derivative work and trigger copyleft. **Action:** (a) write our own matcher; (b) keep the enthec JSON in a separately-licensed `signatures/enthec/` directory with their LICENSE preserved; (c) note this in `NOTICE.md`; (d) if there's any doubt, get a one-line legal sanity check before commercial launch. retire.js is Apache-2.0 — clean, no concern.

6. **Fixture HTMLs need to be real, not synthetic.** Snapshot tests built from `curl --user-agent "Mozilla/..."` of real Squarespace/Shopify/etc. landing pages will catch regressions that hand-crafted minimal HTMLs miss. Commit the fixtures gzipped to keep repo size sane.

7. **The `implies` graph can loop.** Some technology pairs imply each other (rare but documented). Implement cycle detection in the resolver or cap depth at 3.

---

## 6. Sprint 1 plan adjustments

| # | Original plan | Adjustment | Why |
|---|---------------|------------|-----|
| 1 | "Vendor `enthec/webappanalyzer` and use as-is" | Vendor the JSON only; **filter at load time** to drop `js`, `dom`, `xhr`, `probe`, `dns` patterns. Your ~700 number will likely shrink to ~500 useful sigs. | We can't evaluate JS-runtime patterns, no point shipping them. |
| 2 | "~700 filtered signatures" | Don't pre-filter the JSON files themselves. Filter at runtime by category whitelist. Keeps quarterly upstream syncs trivial (no merge conflicts on filtered files). | Vendoring discipline. |
| 3 | "Build `signals/matcher.py`" | Add `signals/matcher_resolver.py` as a separate concern: matcher emits raw `Detection[]`, resolver applies `implies` cascading, dedupe, FP-family suppression, confidence aggregation. | Single-responsibility; resolver is where most bugs will live; testing them separately is cleaner. |
| 4 | "Snapshot regression tests with ~10 fixture HTMLs" | Make it 12: add a CDN-only page (Cloudflare-fronted but no other tech) and a "kitchen-sink" page (WordPress + WooCommerce + Stripe + Mailchimp + Cloudflare) to catch FP and `implies` cascading bugs. | Both bug families need explicit test coverage. |
| 5 | "Wire into `gatekeeper.py` so detections land in `heuristic_flags["technologies"]`" | Same, plus emit `heuristic_flags["technology_match_count"]` and `heuristic_flags["technology_low_confidence"]` for downstream YAML weights to consume. | Sub-100-confidence detections shouldn't be invisible to scoring; let weights decide. |
| 6 | (not in plan) | Add `signals/patterns_safety.py` — wraps regex execution with a 2s per-signature timeout via `concurrent.futures`. Or use `google-re2` and document the 1–2% of patterns that fall back to `re`. | Catastrophic backtracking will eventually pin a worker. Cheaper to prevent now than debug at 3am. |
| 7 | (not in plan) | Add a `signatures/NOTICE.md` capturing enthec GPL-3.0 + retire.js Apache-2.0 attribution and our "JSON data as mere aggregation" reading. | Cheap insurance for commercial launch. |
| 8 | (not in plan) | Add a `false_positive_blocklist.yaml` config that the resolver consults — start with Cloudflare, jQuery, Google Analytics, Bootstrap requiring corroboration. | Day-one mitigation for known FP families. |

**Estimated impact:** adds maybe 4–6 hours to Sprint 1 (resolver split, regex safety wrapper, two extra fixtures, blocklist config). Saves us from the predictable rebuild in Sprint 3 when we discover Cloudflare on every lead.

---

## Sources cited inline

- [enthec/webappanalyzer](https://github.com/enthec/webappanalyzer) — fork, GPL-3.0, actively maintained successor to Wappalyzer
- [chorsley/python-Wappalyzer](https://github.com/chorsley/python-Wappalyzer) — archived Apr 2024
- [s0md3v/wappalyzer-next](https://github.com/s0md3v/wappalyzer-next) — active 2026
- [PigeonSec/py-wappalyzer](https://github.com/PigeonSec/py-wappalyzer) — enthec-based, HAR-centric
- [rverton/webanalyze](https://github.com/rverton/webanalyze) — Go reference architecture
- [tylerpuig/wapalyzer-core](https://github.com/tylerpuig/wapalyzer-core) — wappalyzer-core community fork
- [FallibleInc/retirejslib](https://github.com/FallibleInc/retirejslib) — stale Apache-2.0 Python port
- [stamparm/DSJS](https://github.com/stamparm/DSJS) — minimal retire.js reference
- [dev.to dapdev tech-detection lead-qual writeup](https://dev.to/dapdev/build-a-sales-lead-qualification-tool-with-technology-detection-34k3) — closest prior-art to our target
- [saber.app composite signal score](https://www.saber.app/glossary/composite-signal-score) — multi-signal scoring framework
- [prospeo.io technographic 2026 guide](https://prospeo.io/s/technographic-data-for-lead-scoring) — technographic-as-predictor argument
- [Verneaut lab on Wappalyzer reliability](https://lab.julienverneaut.com/wappalyzer/) — 1,929 spoofed detections demo
- [Wappalyzer issue #2898](https://github.com/wappalyzer/wappalyzer/issues/2898) — Cloudflare false positive case
- [Frederickson on catastrophic regex + GIL](https://www.benfrederickson.com/python-catastrophic-regular-expressions-and-the-gil/) — Python regex hang horror
- [GNU GPL FAQ](https://www.gnu.org/licenses/old-licenses/gpl-2.0-faq.en.html), [LWN "mere aggregation" article](https://lwn.net/Articles/417852/) — GPL aggregation vs derivation
- [google-re2 PyPI](https://pypi.org/project/google-re2/) — RE2 Python bindings for safe regex
- [SEOmator Wappalyzer alternatives 2026](https://seomator.com/blog/wappalyzer-alternatives) — accuracy claim source
