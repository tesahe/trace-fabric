# Architecture

## What this document answers

How is TraceFabric built — what services exist, where the language and IPC boundaries fall, how the deterministic signal layer is structured, and which design choices are deliberate engineering commitments versus incidental implementation detail.

For *why* the evaluation cascade is staged the way it is, see [EVALUATION_STRATEGY.md](./EVALUATION_STRATEGY.md). This doc covers the build, not the thesis.

## Two services, one warehouse

TraceFabric is split into two long-running services that share a single Postgres warehouse:

- **`scraper-engine` (Rust).** Async ingestion. Discovers candidates, fetches homepages, parses `robots.txt`, enforces rate limits, and emits a typed `RawLead` payload. Built on `tokio` for the async runtime, `sqlx` for compile-time-checked queries, `governor` for token-bucket rate limiting, and `reqwest` for HTTP. Source layout under `scraper-engine/src/`: `discovery.rs`, `compliance.rs`, `extract.rs`, `transport.rs`, `types.rs`, `main.rs`.
- **`logic-engine` (Python).** FastAPI service. Receives `RawLead` payloads, runs Tier 0 deterministic evaluation, dispatches Tier 1 constrained LLM validation, and enqueues Tier 2 structured extraction (via Instructor). Source layout under `logic-engine/`: `main.py`, `receiver.py`, `lead_processor.py`, `gatekeeper.py`, `deterministic_evaluator.py`, `tier1_router.py`, `tier2_orchestrator.py`, `campaigns.py`, `database.py`, `schemas.py`.

The split is not arbitrary. Phase 1 — high-concurrency network I/O, strict memory safety, predictable tail latency under load — is what Rust earns. Phase 2 — XGBoost, `instructor`, the LLM SDK ecosystem, fast iteration on heuristic logic — is where Python's library surface pays for itself. The IPC boundary between them is the seam where one language hands off to the other, and it is deliberately narrow.

A single `RawLead` Protobuf schema lives under `proto/lead_v1.proto` and is the only shared contract between services. Rust generates bindings via `build.rs`; Python generates `lead_v1_pb2.py`. The proto file is the source of truth.

## The IPC contract: Protobuf over ZeroMQ

Internal data flow between `scraper-engine` and `logic-engine` is **Protobuf over ZeroMQ**. REST/HTTP is forbidden for internal communication — this is a hard architectural rule from `CLAUDE.md`.

The reasoning is concrete:

- **Typed boundary.** The proto schema is checked at compile time on the Rust side and at message-parse time on the Python side. Adding a field, renaming one, or changing a type surfaces immediately rather than at runtime against a JSON string.
- **No HTTP overhead.** ZeroMQ is a transport, not a protocol stack. There is no TLS handshake, no header parsing, no routing layer between the two processes.
- **No JSON in the hot path.** Every Phase 1 lead crosses this boundary. Parsing JSON for tens of thousands of leads is wasted CPU; binary deserialization into native structs is not.
- **Push/pull semantics.** ZeroMQ's PUSH/PULL pattern lets the Rust side fire and forget while the Python receiver pulls at its own pace. Backpressure is handled by ZeroMQ, not by an HTTP retry loop.

The operator-facing console talks to `logic-engine` over HTTP — that is the only HTTP boundary in the system. Everything internal stays binary.

## No-Drop persistence at the database layer

The "No-Drop" data mandate — every lead, including rejected ones, must be persisted — is enforced **at the database layer**, not at a single service. Both `scraper-engine` and `logic-engine` are direct Postgres writers.

- **`scraper-engine`** writes `rejected_compliance` rows itself when `robots.txt` disallows fetch. These rows never cross the ZeroMQ boundary because there is nothing for Phase 2 to evaluate. The Rust side persists them so the warehouse still records the exclusion.
- **`logic-engine`** writes every Tier 0, Tier 1, and Tier 2 outcome — `rejected_tier0`, `rejected_tier1`, `tier1_passed_pending_tier2` (weak label), and the eventual `tier2_complete` UPDATE.

There is no single chokepoint that owns "the persistence step." Each service writes the rows it is responsible for. This means a service crash, a queue stall, or an LLM timeout cannot drop leads silently — the row is committed before the next stage is invoked. The full set of state transitions is visualized in [data-lifecycle.md](./data-lifecycle.md).

## Inside `logic-engine`

`logic-engine` is a FastAPI process with a long-running ZeroMQ receiver attached. The runtime shape:

**`main.py`** boots FastAPI, wires routes from `api_routes.py`, and starts the receiver task at startup.

**`receiver.py`** is the ZeroMQ pull loop. It deserializes `RawLead` Protobuf messages and hands each one to the lead processor. The loop is a single async task — there is no thread-per-message fan-out. Concurrency comes from the receiver yielding between awaits, not from parallelism inside the process.

**`lead_processor.py`** owns the per-lead pipeline:

1. `HeuristicScanner.run_all_checks()` — universal Tier 0 gates (word count threshold, parked-domain phrase scan, per-campaign rejection signatures, custom evaluators).
2. `evaluate_lead()` (in `deterministic_evaluator.py`) — BeautifulSoup-driven heuristic evaluator producing the canonical `evaluation` dict (DOM presence checks, anchor scanning, text scanning, score formula).
3. `Matcher.match()` (Sprint 1, behind feature flag) — the deterministic signal engine described below.
4. Tier 1 dispatch via `tier1_router.py` for leads that survive Tier 0.
5. Tier 2 enqueue via `tier2_orchestrator.py` for leads that pass Tier 1.
6. Persist through `database.py`.

**`campaigns.py`** holds `RuntimeConfig`, including the `signals_v2_enabled` feature flag. **`gatekeeper.py`** holds the universal heuristic checks. **`schemas.py`** defines the Pydantic models that round-trip through the API and the DB.

The receiver loop, the lead processor, and the persistence layer are intentionally separable — the lead processor's pure helpers (see "The `lead_evaluation.py` extraction" below) can be exercised without a database or a ZeroMQ socket, which is what makes the integration tests cheap.

## The `signals/` package (Sprint 1)

Sprint 1 introduced a deterministic technology-fingerprint engine under `logic-engine/signals/`. It consumes the rich `RawLead` payload that the Rust scraper was already emitting (`script_srcs`, `stylesheet_hrefs`, `response_headers`, `robots_txt.body`, `meta` tags, structured data inside `raw_html`) and produces high-precision per-URL technology detections.

Module-by-module:

- **`signals/detection.py`** — the `Detection` dataclass (`frozen=True`, hashable). Every field is part of an audit trail: `name`, `pack`, `categories`, `confidence`, `version`, `source` (a `MatchSource` enum: `SCRIPT_SRC`, `HTML`, `CSS`, `HEADERS`, `COOKIES`, `META`, `URL`, `ROBOTS`, `TEXT`, `IMPLIED`, `REQUIRED`), `matched_field`, `matched_value`, `pattern_id`, plus upstream metadata (`cpe`, `pricing`, `saas`, `oss`, `website`). `to_dict()` serializes for the Postgres JSON column.
- **`signals/regex_safe.py`** — ReDoS-safe regex wrapper. Primary backend is google-re2 (linear time, immune to catastrophic backtracking); fallback is the stdlib `re` module wrapped in a `ThreadPoolExecutor` with a 100ms per-call timeout. The fallback fires per-pattern when re2 rejects a regex (lookbehind, lookahead, backreferences). Also parses Wappalyzer pattern annotations like `regex\;version:\1\;confidence:50` at compile time.
- **`signals/loader.py`** — three pack loaders. Reads JSON from disk, drops unsupported pattern types (`js`, `dom`, `xhr`, `probe`, `certIssuer` — the matcher does not run a browser), and pre-compiles regex sets per `(technology × pattern_type)`. Loaders: `load_wappalyzer_pack`, `load_retirejs_pack`, `load_local_biz_pack`.
- **`signals/resolver.py`** — applies the implies/requires/excludes detection graph: drops detections whose tech is excluded by another match, drops detections whose required dependency is missing, emits additional `IMPLIED` detections at a confidence cap of 50, and dedupes by `(name, pack)` keeping the highest-confidence occurrence. Runs as fixed-point iteration up to five passes so transitively implied techs surface.
- **`signals/matcher.py`** — the public engine. `Matcher().match(raw_lead_dict)` returns `list[Detection]`. Internally, it iterates `MatchSource` types and, for each, builds the haystack string once and runs every loaded technology's patterns of that source type against it. This is the `rverton/webanalyze` Go pattern: one pass per artifact type, not one pass per pattern, which avoids rebuilding the haystack three thousand times per lead.
- **`signals/blocklist.py`** — applies `false_positive_blocklist.yaml`. Three behaviors: **suppress** (drop a detection by `(name, pack)`), **downgrade** (cap confidence when matched only via specific sources — Cloudflare on headers alone, Google Analytics on script_src alone), and **require corroboration** (drop unless at least one other tech survives — jQuery, Bootstrap).
- **`signals/raw_lead_builder.py`** — converts an HTML file path plus URL into a `RawLead`-shaped dict. Used by the CLI and the test suite, so test inputs match production inputs.
- **`signals/__main__.py`** — `python -m signals --html file.html --url https://...` for offline runs against arbitrary HTML.

Total: roughly 1,500 LOC of Python, six engine modules plus a CLI.

## Vendored signature packs and the GPL boundary

Three signature packs ship with the engine:

- **enthec/webappanalyzer** — pinned to commit `c2855b4`, filtered to 24 categories relevant to local-business lead qualification. After filtering: 4,193 → 2,961 technologies. Licensed **GPL-3.0**.
- **RetireJS/retire.js** — 70 outdated/vulnerable JS library detectors. Licensed **Apache-2.0**.
- **`local_biz_pack/`** — placeholder for hand-curated signatures (Booksy, Mindbody, Toast, ServiceTitan, BirdEye, Podium). Currently empty, ready for sprint-by-sprint curation. TraceFabric-owned.

License hygiene is enforced by directory layout. The GPL-3.0 corpus is isolated under `signals/wappalyzer_pack/` and contains **only** JSON data files plus `LICENSE` and `SOURCE.md`. No Python code lives inside that directory. The matcher engine reads the data through a loader that lives outside the boundary, so no GPL'd code is linked into the engine itself. A repo-root `NOTICE.md` documents the boundary explicitly. Apache-2.0 (RetireJS) and TraceFabric's own code stay in separate directories with their own attributions.

The boundary is auditable: a reviewer can verify it by listing the contents of `wappalyzer_pack/` and confirming there are no `.py` files. That explicit physical separation is the architectural commitment.

## Feature flag deployment pattern

The signals engine ships **default-off**. `RuntimeConfig.signals_v2_enabled` (in `campaigns.py`) is sourced from the environment variable `TRACEFAB_SIGNALS_V2`, defaulting to `False`. With the flag off, the pipeline runs exactly as it did before Sprint 1 — same code path, same outputs, zero behavior change at merge.

`lead_processor.py` instantiates the `Matcher` singleton **conditionally at module import time**. If the flag is on, the packs load once per process and the singleton is reused per lead. If the flag is off, no instantiation occurs and the import is essentially free. This is the pattern: feature gates that can be flipped per environment without redeploying code, and that incur zero cost in the off state.

The same pattern will be reused for future tier expansions — Sprint 2's per-campaign YAML weights, Sprint 5's XGBoost ensemble, and any other additive scoring layer can ship dark, run dark in production for validation, and flip on per environment when ready.

## Reliability contract: the matcher cannot break a lead

The matcher invocation in `lead_processor.py` is wrapped in `try/except`. Any exception — a malformed pack, a runaway regex, a parser bug, an out-of-memory in the resolver — is caught, logged, and swallowed. The pipeline returns the existing pre-Sprint-1 evaluation untouched.

This is a deliberate contract: **new code shouldn't take down the production scoring path**. Sprint 1's matcher adds metadata to `heuristic_flags["technologies"]`, but it does not yet drive any score, qualification decision, or pipeline status. If it crashes, the lead still scores, still qualifies or rejects, still persists. The blast radius of a matcher bug is bounded to "this lead is missing detection metadata," not "this lead is lost."

The contract is verified by an integration test that injects a deliberately broken matcher and asserts the lead still flows through to persistence.

## The `lead_evaluation.py` extraction

A small architectural refactor accompanied Sprint 1: `build_lead_evaluation()` and `apply_signals_v2()` were extracted as **pure helpers** out of `lead_processor.py` into `lead_evaluation.py`. Pure here means no database session, no ZeroMQ socket, no FastAPI request — just `(raw_lead_dict) -> evaluation_dict`.

The reason is testability. The integration test suite needs to assert that the feature flag works (off, on, exception swallowing, no-tech default), and asserting that against a function that requires a live Postgres connection is expensive and flaky. With the helpers extracted, integration tests run in milliseconds against in-memory dicts. The production path imports the same helpers, so the tests prove behavior the production code actually exhibits.

Small refactor, architecturally meaningful: the line between "the pipeline" and "the persistence layer" is now a clean function boundary.

## Frontend boundary

`frontend/` is a Vite + React + TypeScript operator console. It talks to `logic-engine` over HTTP via routes defined in `api_routes.py`. This is the **only HTTP boundary in the system** — operator-facing, not internal data flow. Submitting a niche+location, browsing scored leads, and inspecting the per-detection audit trail all happen over this channel.

The console is intentionally outside the No-Drop loop. Internal data flow (Rust to Python) stays binary; operator interactions (human to Python) stay HTTP. The two channels do not overlap.

## Test coverage

Sprint 1 ships with **46 tests across 4 modules** plus **4 integration tests**, all green in roughly one second.

The test suite is itself an architectural artifact, not just a quality gate:

- **Snapshot fixtures.** Twelve real-world HTML fixtures under `signals/tests/fixtures/raw_html/` covering positive controls (WordPress, Squarespace, Shopify, Wix, HubSpot, Calendly, Mailchimp, Stripe, kitchen_sink) and negative controls (cloudflare_only, parked_domain, static_brochure). Each has an expected JSON file with `must_detect` and `must_not_detect` assertions. A fixture is a public commitment: "this HTML must produce these detections, and must not produce these detections, on every commit."
- **Resolver tests.** Exercise the implies / requires / excludes graph in isolation against synthesized detection sets.
- **`regex_safe` tests.** Cover backend selection (re2 vs stdlib fallback), the 100ms timeout, and ReDoS-shaped patterns that would hang stdlib `re`.
- **Blocklist tests.** Cover suppress, downgrade, and require-corroboration paths against curated input sets.
- **Integration tests.** Four tests proving the feature flag contract end to end: flag off (no detections in output), flag on (detections present), exception swallowing (broken matcher does not break the pipeline), no-tech default (HTML with no recognizable signatures produces an empty list, not an error).

The fixture set documents the engine's behavior more precisely than prose can. A reviewer who wants to know "what does the matcher actually claim to detect on a Squarespace site?" can read `squarespace_minimal.html` and its expected JSON instead of reading the matcher source.

## Related diagrams

- [System Context](../README.md#architecture) — recruiter-friendly zoom-out of the same system.
- [Evaluation Cascade](./evaluation-cascade.md) — decision-flow view of the cascade.
- [Pipeline Sequence](./pipeline-sequence.md) — time-ordered behavior of one lead's traversal.
- [Data Lifecycle](./data-lifecycle.md) — `pipeline_status` transitions and label strengths.
