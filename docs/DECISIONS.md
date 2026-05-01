# Decisions

## What this document is

This is the architecture decision record (ADR) log for TraceFabric. Each entry captures a single substantive decision — the forces in play, the chosen approach, and the consequences. Decisions are Accepted unless explicitly marked Superseded, and the log is append-only: when a decision is revisited, a new ADR supersedes the old one rather than rewriting history.

## Format

Each entry uses the same five-field template: a short title, a status (Accepted, Superseded by ADR-XXX, or Proposed), a date stamped to the month, a Context paragraph naming the forces that made this a real decision rather than a default, a Decision sentence stating the chosen approach, and a Consequences block listing what the choice enables, costs, and forecloses. ADRs are short by design — the reasoning is meant to be auditable in a single screen.

## ADR-001: Two-language split — Rust ingestion, Python evaluation

**Status:** Accepted

**Context.** Phase 1 is high-concurrency network I/O against thousands of hosts under rate limits and tail-latency budgets. Phase 2 is ML, structured LLM extraction, and rapid iteration on heuristic logic. A single-language stack would have to compromise on one side — either give up Rust's memory safety and predictable concurrency, or give up Python's ML and LLM library surface.

**Decision.** Split the system at the language boundary: Rust `scraper-engine` for ingestion (`tokio`, `sqlx`, `governor`), Python `logic-engine` for evaluation (`FastAPI`, `XGBoost`, `Instructor`).

**Consequences.**

- Two toolchains, two CI pipelines, two deploy artifacts, and one explicit IPC seam to maintain.
- Phase 1 inherits Rust's safety guarantees and predictable tail latency; Phase 2 inherits Python's library ecosystem without caveats.
- Cross-language refactors are expensive — the boundary must be stable, which is why ADR-002 makes the contract typed.

## ADR-002: Protobuf over ZeroMQ for internal IPC; HTTP/REST forbidden internally

**Status:** Accepted

**Context.** Every Phase 1 lead crosses the language boundary. JSON-over-HTTP is the path of least resistance but parses on every message, has no compile-time schema enforcement, and adds TLS, header, and routing overhead the system does not need between two co-located processes. `CLAUDE.md` codifies this as a hard rule.

**Decision.** Internal data flow uses Protobuf messages over ZeroMQ PUSH/PULL sockets. HTTP/REST is reserved for the operator console; it is forbidden between `scraper-engine` and `logic-engine`.

**Consequences.**

- Schema changes surface at compile time on the Rust side and at parse time on the Python side, not as silent JSON drift.
- Binary payloads are less debuggable than JSON — the project pays for that with a `proto/lead_v1.proto` that is the single source of truth and a CLI that can dump messages.
- ZeroMQ handles backpressure natively, so the receiver pulls at its own pace without an HTTP retry loop.

## ADR-003: PostgreSQL as single lead warehouse with No-Drop mandate

**Status:** Accepted

**Context.** A naive pipeline drops leads it deems uninteresting. That is correct for a one-shot scoring system and wrong for a system meant to learn. Rejected leads are exactly the hard negatives a future model needs; throwing them away forecloses the data flywheel before it starts.

**Decision.** Every lead — qualified or rejected, at any tier — becomes a PostgreSQL row. Both `scraper-engine` and `logic-engine` write directly. The No-Drop mandate is enforced at the database layer, not at any single service.

**Consequences.**

- Storage grows with total crawl volume, not just qualified volume — accepted as the cost of the flywheel.
- A service crash, queue stall, or LLM timeout cannot drop leads silently, because each stage commits its row before invoking the next.
- The warehouse becomes the substrate for lookalike modeling, label-leakage audits, and per-stage rejection analysis without an additional logging system.

## ADR-004: Staged Tier 0 → Tier 1 → Tier 2 evaluation cascade

**Status:** Accepted

**Context.** A single frontier-model call per lead works and scales linearly with spend, but it produces opaque scores and pays LLM tokens on obvious junk. The cost ratios across deterministic checks, constrained validation, and full structured extraction span roughly four orders of magnitude.

**Decision.** Evaluate in three tiers: Tier 0 deterministic (zero token cost), Tier 1 constrained LLM yes/no validation (small token cost), Tier 2 structured extraction via Instructor (large token cost). Each tier only sees survivors of the previous tier.

**Consequences.**

- Spend follows signal, not volume — every Tier 0 rejection is a Tier 1 call that never runs, and so on down the cascade.
- Pipeline complexity grows: three stages, three failure modes, three sets of operational metrics.
- Adding evaluation surface area at Tier 0 is effectively free at the margin; adding it at Tier 2 has a budget conversation attached.

## ADR-005: Tier 1 persists before Tier 2 runs (decoupled write-and-run)

**Status:** Accepted

**Context.** If Tier 2 is a precondition for persistence, every queue stall, budget exhaustion, or LLM timeout becomes a data-loss event. That is incompatible with the No-Drop mandate from ADR-003 and erases the weak label that Tier 1 already produced.

**Decision.** Tier 1 always writes its outcome — `tier1_passed_pending_tier2` is a first-class `pipeline_status` and a valid weak label. Tier 2 enriches the existing row asynchronously via UPDATE.

**Consequences.**

- The warehouse holds weak labels alongside strong ones; downstream consumers must read `pipeline_status` to know which is which.
- Tier 2 worker outages, budget caps, and LLM provider incidents become operational dials, not data-loss incidents.
- Re-running Tier 2 against historical Tier 1 survivors is a pure backfill — no re-ingestion required.

## ADR-006: Tier 2 dispatch via priority queue with budget cap (async)

**Status:** Accepted

**Context.** Tier 2 is the most expensive call in the system and the one whose volume should track signal quality, not arrival rate. Synchronous dispatch couples lead throughput to LLM latency and removes any way to cap spend without dropping work.

**Decision.** Tier 2 runs asynchronously through a priority queue. Priority is derived from Tier 0 evidence and Tier 1 confidence; a daily or per-run USD budget gate decides when work is dispatched versus deferred.

**Consequences.**

- Scaling Tier 2 spend up or down is a configuration change, not a code change.
- More moving parts — a queue, a worker pool, a budget accountant — and matching observability surface.
- Best-scored leads earn enrichment first; lower-priority leads remain as weak labels until budget refreshes, which is the correct economic ordering.

## ADR-007: Instructor for structured LLM outputs

**Status:** Accepted

**Context.** Free-form prompting produces strings that downstream code has to parse, validate, and repair. Tier 1 and Tier 2 both consume LLM output as structured records that flow into Postgres columns; a string-cleaning layer between the LLM and the schema is exactly the kind of indeterminism the cascade is designed to avoid.

**Decision.** Use `Instructor` with Pydantic schemas to drive constrained structured generation for both Tier 1 validation and Tier 2 extraction.

**Consequences.**

- The LLM's output shape is the schema's shape, enforced at generation time rather than at parse time.
- Schema drift is a code change with a diff, not a silent prompt regression.
- The team accepts a dependency on a specific structured-output library and the model-compatibility constraints it carries, in exchange for deterministic, parseable output.

## ADR-008: Vendor enthec/webappanalyzer (GPL-3.0) under isolated directory boundary

**Status:** Accepted

**Context.** Building a 3,000-pattern technology fingerprint corpus from scratch is a multi-year effort. `enthec/webappanalyzer` already maintains exactly that corpus, but it ships under GPL-3.0, which is incompatible with linking against TraceFabric's proprietary Python code.

**Decision.** Vendor the pack pinned to commit `c2855b4` and isolate it under `signals/wappalyzer_pack/`. The directory contains only JSON data, `LICENSE`, and `SOURCE.md` — no Python files. The matcher engine reads the data through a loader that lives outside the boundary, and a repo-root `NOTICE.md` documents the arrangement.

**Consequences.**

- The GPL boundary is auditable by directory listing — a reviewer confirms no `.py` files live inside `wappalyzer_pack/`.
- Refreshing the corpus is an explicit PR with a new pinned commit, not an at-runtime fetch.
- The project gains broad coverage across 24 categories curated for local-business qualification, in exchange for ongoing license-hygiene discipline.

## ADR-009: Per-source matching pass (rverton/webanalyze pattern)

**Status:** Accepted

**Context.** A naive matcher loops over ~3,000 patterns and rebuilds the haystack string per pattern, which on a real homepage means recomputing the same joined script-src or header string thousands of times per lead. Profiling against the kitchen-sink fixture confirmed this dominated matcher CPU.

**Decision.** Iterate by `MatchSource` (script_srcs, html, css, headers, cookies, meta, url, robots, text), build the haystack once per source, then run every pattern of that source type against it. Mirrors the `rverton/webanalyze` Go implementation.

**Consequences.**

- Haystack construction cost is paid once per source per lead, not once per pattern.
- The matcher's inner loop is structured around sources, which matches how the resolver and blocklist think about evidence.
- Adding a new source type is a one-line enum extension plus a haystack builder; adding a pattern is a JSON entry.

## ADR-010: Feature flag (`TRACEFAB_SIGNALS_V2`) for new evaluation behavior

**Status:** Accepted

**Context.** Sprint 1 was a substantial rewrite of Tier 0 — six new modules, a vendored corpus, three pack loaders, a resolver graph, a blocklist. Merging it as the default code path would couple "the matcher works" to "the matcher is correct on production traffic," and any regression would require a revert.

**Decision.** Ship `signals/` default-off behind `RuntimeConfig.signals_v2_enabled`, sourced from the env var `TRACEFAB_SIGNALS_V2`. With the flag off, the pipeline runs the pre-Sprint-1 code path unchanged.

**Consequences.**

- The merge of PR #19 is a zero-behavior-change merge; production stays on the old path until the flag is flipped per environment.
- One additional branch in `lead_processor.py` and a conditional Matcher singleton at module import — accepted as the cost of safe rollout.
- The same pattern is reusable for Sprint 2's YAML weights and any future additive scoring layer.

## ADR-011: Detection audit trail as first-class fields

**Status:** Accepted

**Context.** Competitor lead-scoring tools ship a single opaque number. Reconstructing "why did this lead score 0.78?" after the fact requires re-running the matcher against the saved payload, which is brittle and assumes the corpus has not changed. The audit trail must be captured at detection time or it is effectively unrecoverable.

**Decision.** Every `Detection` carries `matched_field`, `matched_value`, and `pattern_id` as required fields, alongside `name`, `pack`, `categories`, `confidence`, `version`, and `source`. The full record serializes via `to_dict()` into the Postgres JSON column.

**Consequences.**

- Every score is traceable to specific patterns and specific bytes of the source HTML — the "receipts" are stored, not regenerated.
- JSON column size grows proportionally with detection count; accepted as the cost of operator-grade and recruiter-grade explainability.
- The future "why this lead scored 0.78" UI is unblocked at the data layer; only the rendering work remains.

## ADR-012: ReDoS protection via google-re2 + stdlib `re` fallback + 100ms timeout

**Status:** Accepted

**Context.** The vendored corpus contains roughly 3,000 patterns authored by many hands, some of which exhibit catastrophic backtracking on adversarial input. A single ReDoS-prone pattern run against a malicious page could pin a worker indefinitely and cascade into queue starvation.

**Decision.** Primary regex backend is google-re2 (linear time, ReDoS-immune by construction). Fallback is stdlib `re` wrapped in a `ThreadPoolExecutor` with a 100ms per-call timeout, used per-pattern when re2 rejects features it does not support (lookbehind, lookahead, backreferences). Case-insensitivity uses inline `(?i)` rather than a flag, after a bug surfaced where `re2.IGNORECASE` did not exist on the Python wrapper and silently degraded every pattern to the fallback path.

**Consequences.**

- Linear-time evaluation is guaranteed for the majority of patterns; the rest are bounded by the timeout.
- Two regex backends and an executor add complexity and one bug to file (`max_workers=1` deadlocked on zombie threads — bumped to 4).
- The fallback path preserves coverage for patterns re2 cannot compile.

## ADR-013: The matcher cannot break a lead (try/except contract)

**Status:** Accepted

**Context.** The matcher is new code touching every lead. A malformed pack entry, a runaway resolver, or a pattern bug in production would, without protection, take down the scoring path for every lead in flight — a regression with a much larger blast radius than the upside of the new metadata.

**Decision.** The `Matcher.match()` invocation in `lead_processor.py` is wrapped in `try/except`. Any exception is logged and swallowed; the pipeline returns the existing pre-Sprint-1 evaluation untouched. An integration test injects a deliberately broken matcher and asserts the lead still flows through to persistence.

**Consequences.**

- The blast radius of any matcher bug is bounded to "this lead is missing detection metadata," not "this lead is lost."
- Failures can be silent in production unless surfaced through logging and metrics — the project accepts this in exchange for production safety, with monitoring as the compensating control.
- The contract makes future refactors of the engine cheaper; experimental matchers can ship behind the same contract.

## ADR-014: Sprint 1 stores detections, does not score them

**Status:** Accepted

**Context.** It would have been tempting to ship Sprint 1 with a new score formula that consumes the detections immediately. That would couple two distinct decisions — "is the matcher correct?" and "are these the right weights?" — into one merge, and would block detection-engine validation on weight tuning.

**Decision.** Sprint 1 writes detections into `heuristic_flags["technologies"]` as additive metadata. The legacy `evaluate_lead` score formula is unchanged. `is_qualified_lead` and `pipeline_status` are computed exactly as they were before Sprint 1. Per-campaign YAML weights ship in Sprint 2.

**Consequences.**

- Detection data accumulates in production rows that do not yet consume it — accepted as the cost of clean separation between detection infrastructure and scoring policy.
- Sprint 2's weight tuning runs against real production detections, not synthetic ones, because the data was being captured all along.
- The matcher can be validated, blocklist-tuned, and corpus-refreshed without touching the scoring path.

## Related documents

- [Architecture](./ARCHITECTURE.md) — how the build implements these decisions
- [Evaluation Strategy](./EVALUATION_STRATEGY.md) — strategic reasoning that motivates several of these
- [Data Model](./DATA_MODEL.md) — the schema shaped by decisions ADR-003, ADR-005, ADR-011
- [Roadmap](./ROADMAP.md) — phasing that reflects these decisions
