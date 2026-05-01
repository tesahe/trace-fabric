# Data Model

## What this document answers

What does TraceFabric persist for every lead, and how does the schema enforce the No-Drop mandate so that rejected leads, weak labels, and fully enriched records all live as first-class rows in the same warehouse?

For *why* the cascade is staged the way it is, see [EVALUATION_STRATEGY.md](./EVALUATION_STRATEGY.md). For *how* the services that write these rows are wired, see [ARCHITECTURE.md](./ARCHITECTURE.md). This document covers the data layer.

## The lead warehouse philosophy

PostgreSQL is the single source of truth. Both `scraper-engine` (Rust) and `logic-engine` (Python) write directly to the same `leads` table — there is no service that owns persistence on behalf of the others. The schema is shaped by one commitment: **every lead becomes a row, no matter which gate rejected it**. A compliance exclusion is a row. A Tier 0 rejection is a row. A Tier 1 "not a real business" outcome is a row. A Tier 1 pass that never reaches Tier 2 is a row.

Rejected leads are not log lines — they are training data. Hard negatives feed the data flywheel and inform any future student-model that needs to learn the boundary between qualified and junk. This is why the schema does not have a "successful_leads" table and a "rejection_log" table; one table holds every outcome, with `pipeline_status` as the discriminator.

## The `leads` table

Defined as `ScoredLeadModel` in `logic-engine/database.py`. The columns group into six concerns: identity, discovery provenance, fetch metadata, durable crawl artifacts, deterministic workflow state, and qualification outputs.

```sql
-- identity / routing
id                          text primary key
timestamp                   text
run_id                      text                       -- nullable for now
source_url                  text not null
initial_url                 text
final_url                   text

-- discovery / provenance / compliance
discovery_source            text
target_industry             text
target_location             text
crawl_allowed               boolean
crawl_disallowed_reason     text
is_no_website_opportunity   boolean default false
provider_fsq_id             text
provider_provenance         jsonb default '{}'
website_provenance          jsonb default '{}'
location_confidence         float
category_confidence         float

-- website-derived business fields
company_name                text
category                    text
phone_number                text
address                     text

-- fetch metadata
http_status                 integer
is_https                    boolean
redirect_count              integer
fetch_duration_ms           integer
response_size_bytes         integer
content_type                text
page_title                  text
manifest_url                text

-- durable crawl artifacts
raw_html                    text
text_content                text
response_headers            jsonb default '[]'
anchor_hrefs                jsonb default '[]'
script_srcs                 jsonb default '[]'
stylesheet_hrefs            jsonb default '[]'
robots_txt                  jsonb default '{}'
sitemap_xml                 jsonb default '{}'

-- deterministic / workflow state
pipeline_status             text default 'discovered'
score                       float default 0.0
heuristic_flags             jsonb default '{}'
deterministic_evidence      jsonb default '{}'

-- qualification outputs
is_qualified_lead           boolean default false
has_booking_widget          boolean
is_mobile_optimized         boolean
has_clear_contact_info      boolean
overall_digital_health      text
rejection_reason            text
identified_service_gaps     jsonb default '[]'
missing_critical_features   jsonb default '[]'

-- later-stage LLM state
llm_output                  jsonb default '{}'
full_llm_payload            jsonb default '{}'
llm_processing_cost         float default 0.0

created_at                  timestamptz default now()
updated_at                  timestamptz default now()
```

A few column choices worth surfacing:

**`id` is a `text` primary key**, not a serial integer. The Rust scraper assigns the ID at ingestion time so that the row identity is stable from the very first write — no "renumber on insert" race between services.

**`pipeline_status` is a plain `text` column**, not a Postgres `ENUM` type. The set of values is small and well-defined (covered below), but keeping it as text means adding a new status in a future sprint is a one-line change in Python rather than an `ALTER TYPE` migration. The values are validated in code, not at the database boundary.

**Crawl artifacts are stored verbatim** (`raw_html`, `response_headers`, `script_srcs`, etc.). This is deliberate scope: the warehouse is also the fixture store. Replaying a Tier 0 evaluation against a year-old crawl uses the same code path as a fresh ingestion.

**`deterministic_evidence` and `heuristic_flags` are separate JSON columns.** `deterministic_evidence` holds the structured outputs of `evaluate_lead` (booking presence, contact signal, mobile-readiness flags). `heuristic_flags` holds the diagnostic surface — what the gates noticed, why a rejection fired, and the Sprint 1 `technologies` array.

## The `pipeline_status` enum

Five values are written in production today. Each has exactly one writer.

**`rejected_compliance`.** Written by `scraper-engine` when `robots.txt` disallows the path. The lead never crosses the ZeroMQ boundary. The row carries the URL, discovery provenance, `crawl_allowed=false`, `crawl_disallowed_reason`, and an empty `heuristic_flags`. Terminal.

**`rejected_tier0`.** Written by `logic-engine` when `HeuristicScanner.run_all_checks()` fails a universal gate (word-count threshold, parked-domain phrase, builder regex, viewport check). The row carries full crawl artifacts, a populated `heuristic_flags` describing which gate fired, and `score=0.0`. Terminal. Note: in current code the actual status string is whichever rejection reason `HeuristicScanner` returns (e.g. `rejected_parked_domain`, `rejected_builder_squarespace`); this document treats those as the `rejected_tier0` family for the lifecycle view.

**`rejected_tier1`.** Written by `logic-engine` when the constrained Tier 1 LLM call returns `is_real_local_business=false`. The row carries full crawl artifacts, the deterministic evaluation, and `heuristic_flags` extended with `tier1_reason` and `tier1_confidence`. The literal string in code is `rejected_tier1_not_a_business`. Terminal.

**`tier1_passed_pending_tier2`.** Written by `logic-engine` after Tier 0 and Tier 1 both pass. The row carries the full deterministic evaluation, `score`, `is_qualified_lead`, and the populated `heuristic_flags` and `deterministic_evidence` columns. **Non-terminal** — this is the only state in the system that a future `UPDATE` will move forward. Carries a weak label.

**`tier2_complete`.** Written by the Tier 2 worker as an `UPDATE` to an existing `tier1_passed_pending_tier2` row. Populates `llm_output`, `full_llm_payload`, `llm_processing_cost`, and the typed extraction fields (`overall_digital_health`, `identified_service_gaps`, `missing_critical_features`). Terminal. Carries a strong label.

The state machine is visualized in [data-lifecycle.md](./data-lifecycle.md). Four of the five values are insert paths; only `tier2_complete` is reached via UPDATE.

## Run scoping with `run_id`

Every lead carries an optional `run_id` foreign-key-style reference to a row in `evaluation_runs`. A **run** is one explicit operator-initiated invocation: a niche+location query, a direct URL submission, or a fixture replay. The `evaluation_runs` table records the input mode, campaign type, candidate limit, LLM-enabled flag, and timestamps for that invocation.

Run scoping matters for three concrete reasons:

- **Fixture replay.** A run can be re-executed against a fresh database to verify that the deterministic evaluation produces identical outputs over time. The `run_id` lets us isolate "what did run X produce?" from the rest of the warehouse.
- **Dataset export.** Training data exports filter `WHERE run_id IN (...)` to scope a dataset to specific evaluation campaigns rather than the full warehouse.
- **Cost attribution.** `llm_processing_cost` summed per `run_id` answers "what did this campaign spend?" without a separate billing table.

`run_id` is currently nullable — a transitional state while the IDs propagate through the older code paths. New writes always set it.

## The `heuristic_flags` JSON column

`heuristic_flags` is the diagnostic surface for any deterministic gate that touched the lead. Pre-Sprint-1, it held three families of data:

- **Gate-rejection reasons.** `{"reason": "parked_domain"}`, `{"reason": "rejected_builder_squarespace"}`, etc. For Tier 0 rejections, the `heuristic_flags` is what tells the operator *why*.
- **`evaluate_lead` heuristic surface.** Missing-feature lists, outdated markers, the components that fed the score formula.
- **Tier 1 metadata.** When Tier 1 rejects, `tier1_reason` and `tier1_confidence` are merged in.

Sprint 1 added a fourth family: a `technologies` array. When `signals_v2_enabled` is `True`, the matcher runs against the `RawLead` payload and emits `Detection` objects, which are serialized into `heuristic_flags["technologies"]` as a list of plain dicts. The matcher is wrapped in `try/except` — if it crashes, `technologies` is simply absent from `heuristic_flags`, and downstream code treats absence as "no detections."

## Detection JSON shape

Each entry in the `technologies` array is a serialized `Detection` dataclass (defined in `logic-engine/signals/detection.py`). Every field is part of an audit trail:

- **`name`** — canonical technology name, e.g. `"WordPress"`, `"Stripe"`.
- **`pack`** — which signature pack the detection came from: `"wappalyzer"`, `"retirejs"`, or `"local_biz"`.
- **`categories`** — tuple of category IDs from the upstream pack.
- **`confidence`** — integer 0-100, scoped to the detection itself, not to the lead.
- **`version`** — extracted version string when the pattern captured one (e.g. `"6.4.2"`), else null.
- **`source`** — a `MatchSource` enum value indicating which artifact type the match landed in.
- **`matched_field`** — locator like `"meta[generator]"` or `"script_srcs[2].url"` pointing at the exact field that matched.
- **`matched_value`** — the matched string itself, truncated to about 200 characters.
- **`pattern_id`** — signature ID plus pattern index, so any score is traceable to the regex that produced it.
- **`cpe`**, **`pricing`**, **`saas`**, **`oss`**, **`website`** — upstream metadata carried through unchanged.

The `matched_field`, `matched_value`, and `pattern_id` triple is the explainability story made concrete. When a future scoring layer says "this lead scored 0.78," the row contains the literal evidence that produced the score, traceable back to the regex that fired. See [EVALUATION_STRATEGY.md](./EVALUATION_STRATEGY.md) for the explainability thesis.

## The `MatchSource` enum

Per-source attribution matters because the same technology can have very different precision depending on where it matched. `MatchSource` values:

- **`script_src`** — matched in a `<script src=...>` URL.
- **`html`** — matched in raw HTML body text.
- **`css`** — matched in a `<link rel="stylesheet" href=...>` URL.
- **`headers`** — matched in an HTTP response header.
- **`cookies`** — matched in a `Set-Cookie` value.
- **`meta`** — matched in a `<meta name=... content=...>` tag.
- **`url`** — matched in the final URL itself.
- **`robots`** — matched in `robots.txt` body.
- **`text`** — matched in extracted page text.
- **`implied`** — synthetic detection emitted by the resolver via the `implies` graph (e.g. WordPress implies PHP).
- **`required`** — synthetic detection emitted via the `requires` graph.

The blocklist consumes this field directly: Cloudflare matched only via `headers` is downgraded to confidence 30 because `cf-ray` alone is too generic; Google Analytics matched only via `script_src` is downgraded because the GA snippet is on roughly 70% of all sites. Without per-source attribution, those rules cannot be expressed.

## Why JSON, not a separate detections table

The `technologies` array could be a normalized `detections` child table with one row per `Detection`. Today it is not. The reasoning is shape-stability, not denial.

Sprint 1's job was to **produce** detections and store them. Sprint 2 introduces YAML-driven per-campaign weights that **consume** them. Until those weight queries exist, every consumer of the detections array reads it as a whole — render the audit trail in the operator console, export the row for fixture replay, count detections for diagnostics. None of those workloads benefit from a normalized table.

The migration trigger is concrete: when Sprint 2's weighted-sum queries become hot ("for every lead in the run, sum weights over detections matching campaign X"), the array becomes a normalized table with `detection_id`, `lead_id`, `name`, `pack`, `confidence`, `source`, plus indexes on `(lead_id, name)` and `(name, pack)`. Storing as JSON now keeps the schema flexible while detection shape is still evolving — `pricing` was added late in Sprint 1, the next pack might add another field, and shipping schema migrations on every iteration is the wrong tradeoff this early.

## What does not persist

The warehouse stores **structural markers and audit trails**, not raw page bytes intended for downstream parsing. Specifically:

- **No DOM trees.** The Rust scraper extracts what Phase 2 needs and discards the rest. Anchor hrefs, script srcs, stylesheet hrefs, response headers, and meta tags persist as structured arrays. The full DOM tree never reaches Postgres.
- **No re-fetched response bodies.** `robots.txt` and `sitemap_xml` are fetched once at crawl time and the bodies persist in those JSON columns. Subsequent stages never re-fetch the page.
- **No PII beyond what the page publishes.** The scraper extracts publicly-visible business contact fields (`company_name`, `phone_number`, `address`) from the page and persists those. It does not enrich them from third-party people-data sources, and it does not retain user-level identifiers from the operator.

This aligns with the README's Data Minimization commitment: only structural markers required for economic-viability analysis are kept. `raw_html` and `text_content` *are* persisted today as a tradeoff for fixture replay, but those are first-party crawl artifacts of public pages, not enriched personal data.

## Query patterns

The shapes that matter operationally:

**Filter by status.** Every dashboard query starts here.

```sql
SELECT id, source_url, score
FROM leads
WHERE pipeline_status = 'tier1_passed_pending_tier2'
ORDER BY score DESC
LIMIT 50;
```

**Filter by run.** Every replay or export.

```sql
SELECT pipeline_status, count(*)
FROM leads
WHERE run_id = $1
GROUP BY pipeline_status;
```

**JSON path queries on `technologies`.** Recruiter-friendly demonstration of the audit trail:

```sql
SELECT id, source_url, heuristic_flags->'technologies' AS techs
FROM leads
WHERE heuristic_flags ? 'technologies'
ORDER BY created_at DESC
LIMIT 5;
```

```sql
SELECT id, source_url
FROM leads
WHERE heuristic_flags->'technologies' @> '[{"name": "WordPress"}]';
```

The columns that earn an index in production are `pipeline_status`, `run_id`, `source_url` (uniqueness sanity check), and `created_at` (recent-leads dashboards). The `heuristic_flags` column will earn a GIN index once the Sprint 2 weighted-sum query lands and JSON path lookups become hot — until then, the table is small enough that a sequential scan is faster than the GIN write amplification cost.

## Future schema evolution

The schema will grow along three predictable axes:

- **Normalized `detections` table.** Triggered by Sprint 2's per-campaign weighted-sum queries. Expected columns: `lead_id`, `name`, `pack`, `confidence`, `source`, `version`, `pattern_id`. The JSON column stays as the source-of-truth audit trail; the table is a query optimization.
- **Tier 2 budget tracking.** A `tier2_priority` column on `leads` and a `daily_llm_budget_usd` row in a runtime-config table. Sprint 2 work; the priority score is computed today but not yet persisted.
- **`audit_events` table.** When traceability needs grow beyond "what did the matcher detect" to "what decisions were made about this lead and when," an append-only events table becomes the right shape. Each row: `lead_id`, `event_type`, `actor_service`, `payload_json`, `created_at`. Out of scope until the operator console needs a per-lead timeline view.

None of these changes are blocking. The current shape supports every workload through Sprint 2's first phase.

## Example row

A lead in `tier1_passed_pending_tier2` state, with Sprint 1 detections present (truncated for readability):

```json
{
  "id": "lead_01HX...",
  "run_id": "run_2025_05_01_modernization_brooklyn",
  "source_url": "https://example-blog.com/",
  "final_url": "https://example-blog.com/",
  "discovery_source": "foursquare",
  "target_industry": "salon",
  "target_location": "Brooklyn, NY",
  "crawl_allowed": true,
  "company_name": "Example Salon",
  "phone_number": "+1-555-0100",
  "http_status": 200,
  "is_https": true,
  "page_title": "Example Salon - Brooklyn",
  "pipeline_status": "tier1_passed_pending_tier2",
  "score": 0.71,
  "is_qualified_lead": true,
  "has_booking_widget": false,
  "is_mobile_optimized": true,
  "has_clear_contact_info": true,
  "deterministic_evidence": {
    "viewport_present": true,
    "form_present": false,
    "tel_link_present": true,
    "stale_copyright": false
  },
  "heuristic_flags": {
    "missing_features": ["online_booking", "service_pricing"],
    "outdated_markers": [],
    "tier1_confidence": 0.88,
    "technologies": [
      {
        "name": "WordPress",
        "pack": "wappalyzer",
        "categories": [1],
        "confidence": 100,
        "version": "6.4.2",
        "source": "meta",
        "matched_field": "meta[generator]",
        "matched_value": "WordPress 6.4.2",
        "pattern_id": "WordPress::meta::0",
        "saas": false,
        "oss": true
      },
      {
        "name": "Contact Form 7",
        "pack": "wappalyzer",
        "categories": [110],
        "confidence": 100,
        "version": "5.8.4",
        "source": "script_src",
        "matched_field": "script_srcs[1].url",
        "matched_value": "...contact-form-7/.../index.js?ver=5.8.4",
        "pattern_id": "ContactForm7::script_src::0"
      }
    ]
  },
  "llm_output": {},
  "llm_processing_cost": 0.0,
  "created_at": "2026-05-01T14:22:31Z"
}
```

The `llm_output` and `full_llm_payload` columns sit empty until the Tier 2 worker pulls this row, runs the structured extraction, and updates the row to `tier2_complete`.

## Related diagrams

- [Data Lifecycle](./data-lifecycle.md) — `pipeline_status` transitions visualized.
- [Evaluation Cascade](./evaluation-cascade.md) — decision flow that produces these writes.
- [Pipeline Sequence](./pipeline-sequence.md) — time-ordered behavior of writes.
- [System Context](../README.md#architecture) — recruiter-friendly zoom-out.
