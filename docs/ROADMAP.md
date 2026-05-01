# Roadmap

## What this document is

A phased plan for TraceFabric with explicit exit criteria per phase, a status snapshot as of Q2 2026, and the open decisions that gate the next milestones. Phases are tracked against the five-line roadmap in the [README](../README.md#roadmap) and expanded here so the criteria are inspectable rather than aspirational. The document is updated as work lands.

## Status snapshot

Phase 1 (Rust ingestion plus Protobuf-over-ZeroMQ IPC) is done. Phase 2 (deterministic evaluation and signals) is in progress: Sprint 1 — the `signals_v2` matcher infrastructure — has shipped behind a feature flag, Sprint 2 (per-campaign YAML weights, `local_biz` pack curation, PageSpeed Insights and Mozilla Observatory integrations) is the next active body of work, and Sprint 3 (benchmark validation, weight tuning, default-on promotion) closes the phase. Phase 3 (Tier 1 plus Tier 2 LLM cascade) is partially scaffolded — `lead_processor.py` already wires a constrained Tier 1 call and an Instructor-based Tier 2 extraction path, but the full cost-gated cascade is pending Phase 2 closure. Phases 4 and 5 are planned and gated on the dataset that Phase 4 itself produces.

The most concrete current gate is the **labeled benchmark URL set** (20 good plus 20 bad). Sprint 2 work that does not depend on labels can proceed; the tuning pass that closes Sprint 3 cannot run until those labels land.

## Phase 1: Rust ingestion plus IPC bridge

**Status.** Done.

**Scope.** The Rust `scraper-engine` was built as the ingestion-only half of the pipeline: dynamic discovery via Serper and Google Places, async crawl on `tokio` with `reqwest`, `governor`-based token-bucket rate limiting, hardcoded ethical headers, robots.txt parsing with disallowed-site recording, and `sqlx` compile-time-checked `No-Drop` persistence to PostgreSQL. The IPC contract — Protobuf `RawLead` over ZeroMQ — was specified, latency-spiked, and wired end-to-end with the Python receiver, so every downstream phase consumes the same typed payload.

**Exit criteria.**

- **Compile-time-checked persistence.** `sqlx` queries validated against the live schema; failed inserts surface at build time, not at runtime.
- **Robots.txt compliance is structural, not advisory.** Disallowed URLs are recorded as `rejected_compliance` and never fetched. Documented in the [Ethics](../README.md#ethics) section.
- **Rate-limited concurrent crawl.** Token-bucket via `governor`; per-host concurrency bounded; no host can be starved or hammered by misconfiguration.
- **Protobuf-over-ZeroMQ contract proven.** A latency spike between Rust and Python committed (`chore(ipc): complete zmq latency spike between rust and python`) and the production receiver path lives in `logic-engine`.
- **Identifying User-Agent.** `TraceFabric/1.0 (+https://github.com/tesahe/trace-fabric)` on every request.

**Out-of-scope (deferred).** No HTML rendering or headless browser execution. No JavaScript-rendered DOM extraction — the scraper sends the static HTML, response headers, robots, sitemap, and a small structured set of derived fields. No retry-on-failure with backoff state machines beyond what `reqwest` and `governor` provide; richer crawl orchestration is deferred to a later operations milestone.

## Phase 2: Deterministic evaluation plus signals

**Status.** In progress. Sprint 1 done, Sprint 2 next, Sprint 3 closes the phase.

**Scope.** Phase 2 owns everything that runs **before** an LLM token is spent: universal heuristic gates, DOM-based evaluation, the `signals_v2` deterministic technology matcher, per-campaign weighting, and free third-party signal integrations. The objective is that every lead reaching Tier 1 has already cleared a high-precision deterministic floor, and every rejection carries an audit trail back to the field and pattern that produced it.

**Exit criteria.**

- **`signals_v2` is the default code path** — feature flag retired, all production traffic runs the matcher.
- **Per-campaign YAML weights** drive the score formula; the prior `0.35 + 0.12*missing + 0.10*outdated` heuristic is replaced.
- **Free signal integrations live** — Google PageSpeed Insights and Mozilla Observatory feed Tier 0.
- **Local-biz signature pack curated** — at least 30 hand-curated entries covering booking platforms, restaurant POS, salon software, contractor CRMs, and review widgets.
- **Benchmark precision/recall measured** against the 20-good plus 20-bad labeled URL set, with results documented and weights tuned against them.

**Out-of-scope (deferred to later phases).** No XGBoost — Phase 5. No CI gate that blocks regressions — Phase 4. No frontend "why this lead scored 0.78" waterfall view; it is unblocked by Phase 2 closure but not gated within it.

### Sprint 1: `signals_v2` matcher infrastructure

**Status.** Done (PR #19 merged).

**Scope.** Build the matcher infrastructure that consumes the rich `RawLead` payload — `script_srcs`, `stylesheet_hrefs`, `response_headers`, `robots_txt`, `sitemap_xml`, `<meta name="generator">`, structured data inside `raw_html` — and produces high-precision per-URL technology detections, behind a feature flag so production behavior is unchanged. Vendored signature packs (`enthec/webappanalyzer` filtered to 24 local-biz-relevant categories, `RetireJS/retire.js`, and an empty `local_biz` placeholder), a regex-safe wrapper (google-re2 primary, stdlib `re` fallback with a 100ms thread timeout), the implies/requires/excludes resolver, a curated false-positive blocklist, and 46 tests across snapshot fixtures, resolver behaviour, regex safety, and integration. Extracted `build_lead_evaluation()` into `lead_evaluation.py` so integration tests can run database-free.

**Exit criteria.**

- **Feature flag wired.** `RuntimeConfig.signals_v2_enabled`, sourced from `TRACEFAB_SIGNALS_V2`, default `False`.
- **Detections persist as additive metadata.** `evaluation["heuristic_flags"]["technologies"]` populated when the flag is on; existing `score`, `is_qualified_lead`, `pipeline_status` fields untouched.
- **Matcher cannot break a lead.** Try/except contract: any matcher exception is logged and the pipeline returns the existing evaluation.
- **License hygiene.** GPL-3.0 corpus isolated under `signals/wappalyzer_pack/` (JSON + LICENSE + SOURCE.md only, no Python); `NOTICE.md` at repo root documents the boundary.
- **Auditable detections.** Each `Detection` carries `pack`, `confidence`, `version`, `source`, `matched_field`, `matched_value`, `pattern_id`.
- **46 tests green** in roughly one second.

**Out-of-scope (Sprint 1).** Detections are stored, not yet scored. The score formula is unchanged — Sprint 2 picks that up.

### Sprint 2: YAML weights, `local_biz` curation, signal integrations

**Status.** Planned, ready to start.

**Scope.** Turn detections into score signal. Introduce `logic-engine/campaigns/*.weights.yml` files that map detected technologies to per-campaign weights, with a typed loader and a scoring upgrade that consumes both the detections and the additional signals listed below. Curate the `local_biz` pack to roughly 30 to 50 hand-written signatures across booking (Booksy, Mindbody, Vagaro), restaurant POS (Toast, ChowNow), salon (Boulevard, Phorest), contractor CRM (ServiceTitan, Housecall Pro, Jobber), and review widgets (BirdEye, Podium). Wire two free third-party signal sources as async background fetchers:

- **Google PageSpeed Insights** — Core Web Vitals, performance, accessibility scores; free 25k requests per day.
- **Mozilla Observatory** — security headers grade A+ to F; free, no-auth.

A Schema.org JSON-LD parser is in scope as a distinct extractor since it needs JSON-LD-specific logic outside the Wappalyzer matcher.

**Exit criteria.**

- **YAML weight schema documented**, with a typed loader and a per-campaign weights file checked in for at least the `website_modernization` campaign.
- **Score formula consumes detections and weights.** The old hardcoded formula path is removed or feature-flagged off.
- **PageSpeed Insights fetcher** runs async, persists into `heuristic_flags`, retries on transient failures, never blocks the main evaluation.
- **Mozilla Observatory fetcher** ditto.
- **`local_biz` pack** has at least 30 entries with fixtures and expected JSON.
- **JSON-LD parser** lifts at least `LocalBusiness`, `Organization`, `Restaurant`, and `Service` schemas into structured fields on the evaluation.

**Out-of-scope (Sprint 2).** Tuning of the weights. Sprint 2 lands the *mechanism*; Sprint 3 lands the *numbers*.

### Sprint 3: Benchmark validation and weight tuning

**Status.** Planned, gated on the labeled benchmark set.

**Scope.** Run the full Phase 2 pipeline against the 20-good plus 20-bad labeled URL set. Measure precision, recall, and per-signal lift. Tune the YAML weights. Promote `signals_v2` from feature-flagged to default-on and remove the legacy code path. Document the precision/recall numbers per campaign so Phase 3's cost-gated cascade has calibrated input.

**Exit criteria.**

- **Precision and recall measured** per campaign on the labeled set, with results checked in under `docs/` or a sibling `benchmarks/` location.
- **Weights tuned** to maximise precision at a defined recall floor (the floor is set during Sprint 3, not pre-committed).
- **`TRACEFAB_SIGNALS_V2` flag retired.** All production traffic runs `signals_v2`.
- **Legacy formula removed** from `evaluate_lead`.

**Out-of-scope (Sprint 3).** Frontend display of the scoring waterfall — that work is unblocked once detections drive the score, but is tracked separately and is not a gating criterion for Phase 2 closure.

## Phase 3: Tier 1 plus Tier 2 LLM cascade

**Status.** Partially scaffolded. `lead_processor.py` wires a Tier 1 constrained call (validated end-to-end against Gemini 2.5 Flash Lite in commit `e481990`) and a Tier 2 Instructor-based structured extraction path (commit `82db52c`) is integrated into the orchestrator (`91eb1f0`). The full cost-gated cascade — priority queue, budget gate, async Tier 2 dispatch — is pending Phase 2 closure so the deterministic input is calibrated.

**Scope.** Tier 1 answers a single yes/no question — "is this a real local business in the target niche?" — against a tight schema. Tier 2 runs only on Tier 1 survivors that win a priority and budget auction, and produces the structured business record via Instructor-driven JSON schema enforcement. Both tiers persist evidence and reasoning back into the `ScoredLeadModel` row so every decision is auditable.

**Exit criteria.**

- **Tier 1 schema locked.** Constrained yes/no plus a small structured rationale; Pydantic-validated; deterministic temperature.
- **Tier 2 dispatch is cost-gated.** A documented priority and budget gate (the Tier 2 dispatch pattern lives in operator memory and the [Evaluation Strategy](./EVALUATION_STRATEGY.md)) — only candidates that earn the spend reach Tier 2.
- **No-Drop holds across both tiers.** Rejected and excluded leads persist with their `pipeline_status` and the evidence that produced the decision.
- **End-to-end demo flow.** A single operator-triggered run executes Phase 1 ingestion, Phase 2 deterministic evaluation, Tier 1, and Tier 2 (when budget allows), with the result visible in the operator console.

**Out-of-scope.** Self-hosted models — TraceFabric stays on a hosted frontier provider plus a hosted lite-tier for Tier 1 until Phase 5's dataset is large enough to justify a student model. No multi-LLM ensembling at Tier 1 or Tier 2 — one model per tier, deterministically.

## Phase 4: Gatekeeper-Eval CI gate, OpenTelemetry, dataset export

**Status.** Planned.

**Scope.** Three pieces that turn TraceFabric from a working pipeline into a maintained one.

- **Gatekeeper-Eval CI gate.** Every PR runs the full Phase 2 pipeline against the labeled benchmark URL set. Precision below the locked floor blocks the merge. This is the mechanism that makes the project rules' Gatekeeper-Eval requirement enforceable rather than aspirational.
- **OpenTelemetry tracing.** Span coverage across `scraper-engine`, the ZeroMQ bridge, the FastAPI `logic-engine`, and the Tier 1 and Tier 2 LLM calls. Trace IDs propagate end-to-end. This satisfies the project rules' observability SOP.
- **Teacher-label dataset export pipeline.** A scheduled export of `ScoredLeadModel` rows — qualified, rejected, and excluded — into a parquet or JSONL dataset suitable for downstream model training, with PII boundaries enforced at export time.

**Exit criteria.**

- **CI gate blocks regressions.** A PR that drops precision on the benchmark set below the floor cannot be merged into `main`.
- **Trace ID end-to-end.** A single trace ID can be followed from `scraper-engine` ingestion through Tier 2 persistence in a tracing UI.
- **Dataset export tested.** A scheduled job produces a versioned, immutable export; row counts match the source-of-truth query within a defined tolerance.

**Out-of-scope.** Active learning loops — Phase 5 prerequisite, not a Phase 4 deliverable. Public dataset release — the export targets internal training only.

## Phase 5: XGBoost ensemble scoring

**Status.** Planned, gated on dataset accumulation.

**Scope.** Replace the heuristic and YAML-weighted score formula with a learned XGBoost ensemble that consumes the deterministic detections, the third-party signal scores, and the Tier 1 rationale embeddings as features. Deploy the model behind a feature flag with shadow scoring against the heuristic baseline, then promote once shadow precision matches or exceeds the heuristic on the benchmark set.

**Exit criteria.**

- **Minimum 500 teacher-labeled rows** accumulated through the Phase 4 export pipeline. This is a hard prerequisite — training before this threshold overfits to the benchmark.
- **XGBoost model trained, versioned, and persisted** with the feature schema checked in.
- **Shadow scoring lives** alongside the YAML-weighted score for at least one full evaluation cycle.
- **Promoted to primary** after meeting or exceeding heuristic precision on the held-out benchmark set.

**Out-of-scope.** Online learning — the model is retrained offline on snapshot exports, not updated in-flight. Multi-model ensembling beyond a single XGBoost head — that is a future possibility, not a Phase 5 deliverable.

## Open decisions and dependencies

**Tier priority for Sprint 2.** Defaulted to S-tier signatures first per the prior-art recommendations, but may be re-prioritised once the benchmark URLs reveal which detection families actually predict outcomes. Decision-owner: project lead, revisited after the labeled set lands.

**Benchmark URL validation set (20 good plus 20 bad).** Gates the tuning step that closes Sprint 3 and, transitively, the locked precision floor used by the Phase 4 CI gate. Sprint 2's mechanism work (YAML schema, weight loader, signal integrations, `local_biz` curation) is independent of this and can proceed without the labels. Sprint 3's tuning pass cannot.

## Out of scope (project-level)

The following are deliberately not on any phase of the roadmap and are not planned to be added:

- **Hosted multi-tenant SaaS.** TraceFabric is a portfolio artifact, not a product launch. There is no hosted demo, no published SDK, no support model — the [README's Project Status](../README.md#project-status) section is the source of truth for this framing.
- **Public REST or GraphQL API.** The internal IPC contract is Protobuf-over-ZeroMQ by mandate. A public API would require a separate transport layer and an authentication and quota story that the project has not committed to building.
- **Mobile app.** The operator console is a desktop-first Vite plus React surface. No mobile target.
- **Paid distribution or licensing.** The repository is Apache 2.0 and stays that way.

## Reading the roadmap

The phases are a planning aid and a way to communicate scope, not a delivery contract. Sprint priorities inside Phase 2 may re-order once the benchmark URLs land and the actual lift per signal is measurable. The exit criteria are the load-bearing part — they are what "done" means and what reviewers should hold the project to. If a criterion changes, the change is recorded here in the same edit that ships it, alongside an ADR in `docs/DECISIONS.md` if the change crosses a phase boundary.

## Related documents

- [Architecture](./ARCHITECTURE.md) — current system build
- [Evaluation Strategy](./EVALUATION_STRATEGY.md) — strategic framing each phase ladders into
- [Evaluation Cascade](./evaluation-cascade.md) — visual of the cascade Phase 2 and Phase 3 build
- [Data Lifecycle](./data-lifecycle.md) — how the No-Drop mandate produces the dataset Phase 5 is gated on
- [Pipeline Sequence](./pipeline-sequence.md) — interaction diagram across the services Phase 1 stood up
