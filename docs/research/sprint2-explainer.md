# Sprint 2 Explainer — Scoring + Curation + Remote APIs + JSON-LD

> What Sprint 2 added on top of Sprint 1's matcher engine: the layer that turns detections into actual scoring decisions per prompt.

---

## What Sprint 2 delivers

Five things, all behind feature flags so production behavior is unchanged unless you flip them:

1. **Schema.org JSON-LD parser** (Stream D) — already merged in `d94317b` before the agent was killed at the limit; survived two retries
2. **30+ hand-curated local-biz signatures** (Stream B) — Booksy, Mindbody, Toast, ServiceTitan, BirdEye, Podium, Boulevard, Phorest, Jobber, Housecall Pro, etc.
3. **PSI + Mozilla Observatory remote API wrappers** (Stream C) — async, cached, wrap all errors
4. **Weighted scorer + per-campaign / per-industry YAML weights** (Stream A) — the headline deliverable that turns matcher detections into score signal
5. **Pipeline integration** — `apply_scoring_v2()` in `lead_evaluation.py` lands `score_v2` + `score_v2_breakdown` (audit trail) into the existing `heuristic_flags` JSON column

**Total:** 7 commits, ~2,600 LOC added (scorer + sigs + remote APIs + tests + 3 YAML configs + this doc), test count goes from 46 → 118 (+72 new tests), all green in ~2s.

---

## How a lead actually scores now (with both flags on)

Run sequence per lead:

```
Rust scraper → ZMQ → Python receiver →
  HeuristicScanner.run_all_checks()       [unchanged]
  evaluate_lead()                          [unchanged — produces existing evaluation]
  Matcher.match(lead_payload)              [Sprint 1 — local detections + structured_data]
    ├─ regex_safe matches per artifact type
    ├─ structured_data.extract_local_business_signals(raw_html)
    ├─ resolver applies implies/requires/excludes
    └─ blocklist applies suppress/downgrade/corroboration
  detections → heuristic_flags["technologies"]   [Sprint 1]

  IF TRACEFAB_SCORING_V2=1:
    apply_scoring_v2(evaluation, detections, runtime_config)
    └─ scoring.score_lead(detections, existing_signals, campaign, industry, location, weight_configs)
        ├─ load campaigns/<campaign>.yaml
        ├─ rejection-gate check (universal + per-industry)
        ├─ accumulate baseline + weighted contributions per signal
        ├─ per-region multiplier on raw score
        ├─ clamp + normalize to [0, 1]
        └─ produce ScoreResult with full audit trail
    → heuristic_flags["score_v2"]            (final 0..1 score)
    → heuristic_flags["score_v2_breakdown"]  (list of ScoreContribution dicts)

  persist to ScoredLeadModel
```

Important: **the existing `score` and `is_qualified_lead` fields are unchanged** under Sprint 2. The new score lives alongside, in the JSON column. A follow-up sprint will cut the production path over once the new score is validated against benchmark URLs.

---

## Why this design solves the per-prompt question we discussed

The same WordPress site evaluated under two prompts:

### Prompt: `plumbers in San Francisco`, campaign=`website_modernization`
- Discovery (Rust): pulled SF plumbing sites
- Matcher (Python): detects WordPress, jQuery 3.7.0, Stripe (no ServiceTitan)
- Scorer:
  - baseline 0.30
  - WordPress weight +15 → +0.15
  - no_viewport (existing signal) +25 → +0.25
  - per-industry plumbing: ServiceTitan not detected, no industry adjustment
  - per-region high_cost_metros (San Francisco match): multiplier 1.2
  - raw: (0.30 + 0.15 + 0.25) * 1.2 = 0.84
  - normalized: 0.84
  - threshold 0.55 → **is_qualified_v2 = True**
  - audit trail: 5 ScoreContribution entries

### Same site, different prompt: `painters in Baton Rouge`, campaign=`website_modernization`
- Discovery: would not have surfaced this site (different niche+location)
- But IF it did:
  - baseline 0.30 + WordPress +0.15 + no_viewport +0.25 = 0.70
  - per-industry painting: no Jobber/Housecall Pro detected, no adjustment
  - per-region: Baton Rouge not in high_cost_metros, no multiplier
  - raw: 0.70 → normalized 0.70
  - threshold 0.55 → **is_qualified_v2 = True**

Both are qualified, but SF gets a higher score because of the metro multiplier. If the painter site had a Houzz Pro account or Jobber subscription, the per-industry painting weights would adjust differently than they would for a plumber.

The matcher is universal. The scorer is prompt-aware. **That's the design.**

---

## ScoreResult / ScoreContribution audit trail (real example)

```python
ScoreResult(
  score=0.84,
  is_qualified=True,
  is_rejected=False,
  rejection_reason=None,
  campaign="website_modernization",
  industry="plumbing",
  region_matches=["high_cost_metros"],
  contributions=[
    ScoreContribution(
      source="baseline",
      weight=0.30,
      reason="campaign baseline score",
      rule_path="score_baseline",
    ),
    ScoreContribution(
      source="detection:WordPress:wappalyzer",
      weight=0.15,
      reason="legacy CMS = modernization opportunity",
      rule_path="weights_universal.detections.WordPress:wappalyzer",
    ),
    ScoreContribution(
      source="signal:no_viewport",
      weight=0.25,
      reason="missing mobile viewport meta tag",
      rule_path="weights_universal.signals_from_existing_evaluator.no_viewport",
    ),
    ScoreContribution(
      source="region:high_cost_metros",
      weight=0.14,  # the bump from multiplier
      reason="region multiplier 1.2 matched location 'san francisco'",
      rule_path="weights_by_region.high_cost_metros.multiplier",
    ),
  ],
)
```

This entire breakdown serializes to the `heuristic_flags["score_v2_breakdown"]` JSON column. SQL-queryable, client-presentable, debuggable.

---

## Files to review before merging

1. `logic-engine/scoring.py` — the scorer logic, especially the rejection-gate ordering and the multiplier-on-running-score behavior
2. `logic-engine/campaigns/website_modernization.yaml` — verify the seeded weights for the 6 industries match your intent (these are educated guesses pre-validation)
3. `logic-engine/lead_evaluation.py` — the `apply_scoring_v2()` integration + try/except contract
4. `logic-engine/signals/local_biz_pack/booking.json` — sanity-check one of the curated sig files for false-positive risk
5. `logic-engine/signals/remote_apis/psi.py` — verify the auth/cache/timeout behavior matches what you want for production rollout

---

## Feature flag matrix

| Flag | Default | What it does |
|---|---|---|
| `TRACEFAB_SIGNALS_V2` | OFF | Sprint 1: matcher runs, detections land in `heuristic_flags["technologies"]` |
| `TRACEFAB_SCORING_V2` | OFF | Sprint 2: scorer runs, `score_v2` + breakdown land in `heuristic_flags` |
| `TRACEFAB_REMOTE_PSI` | OFF | Calls Google PSI per lead, requires `GOOGLE_PSI_API_KEY` env |
| `TRACEFAB_REMOTE_OBSERVATORY` | OFF | Calls Mozilla Observatory per lead, no API key needed |

For the score to actually mean anything you need both `TRACEFAB_SIGNALS_V2=1` AND `TRACEFAB_SCORING_V2=1`. Remote APIs are independent — turn them on per environment based on quota.

---

## What's NOT in Sprint 2 (next-up work)

- **Cutover from legacy `score` to `score_v2`** — both run in parallel today; one follow-up sprint will swap them once validated
- **Validation against benchmark URLs** — pending Tee's 20-good + 20-bad labeled set
- **Auto-tuning** of YAML weights from observed data — manual editing for now
- **XGBoost ensemble** — project Phase 5, much later
- **Frontend display** of the score breakdown waterfall — React side untouched
- **Additional industries** beyond the seeded 6 (plumbing, hvac, painting, dental, salon, restaurant)
- **More local-biz sigs** beyond the 30+ in this sprint

---

## Bug caught and fixed during integration

The agent that built Sprint 2 was killed twice at session limits. Both times right at test-debug. The actual issue: 3 tests in `test_scoring.py` had assertions assuming weights add as raw integers (15 → +15) when the scorer actually treats them as percentage points (15 → +0.15). The percentage-point design is correct (it keeps YAML readable as integers), so the fix was test-side only. All 118 tests now pass.

Also: the region multiplier applies to the entire accumulated raw score (baseline + contributions), not just the contribution it's adjacent to. So `(0.30 baseline + 0.25 contribution) * 1.2 multiplier = 0.66`, not `0.30 + 0.25 * 1.2 = 0.60`. Documented in the test comments so future contributors don't make the same mistake.

---

*Generated as part of Sprint 2. Branch: `feat/sprint-2-scoring-and-curation`.*
