# Phase 1b — Recommendations Synthesis

> Concrete answers to decisions #3 and #4 from `phase1-recon.md`, grounded in `phase1b-competitive-analysis.md` and `phase1b-signature-db-evaluation.md`. Read this if you don't have time to read the full research docs.

## Context

Phase 1 recon flagged four open decisions before Phase 2 starts. While Tee was traveling, I executed two parallel research streams:

1. **Competitive landscape** — what 11 lead-tool competitors actually do for deterministic signal extraction (`phase1b-competitive-analysis.md`)
2. **Signature DB evaluation** — open + commercial signature databases for tech fingerprinting (`phase1b-signature-db-evaluation.md`)

This doc is the synthesis. Tier priority (#1) and labeled URL set (#2) are still pending Tee's input — out of scope for this doc.

---

## Headline finding from competitive research

**Nobody in the surveyed field markets "audited, reproducible, deterministic-first scoring at the per-URL level."** The space is dominated by:

- Contact databases with opaque scoring (Apollo, Cognism, ZoomInfo)
- Raw scrape dumps with no scoring (Outscraper, MapiLeads, Lead Scrape)
- Workflow canvases that punt scoring to the user (Clay, Persana, PhantomBuster)
- Agency audit-PDF generators (GoHighLevel, Website Grader)

**The gap is real and TraceFabric's positioning fits it directly.** This finding strengthens the case for the auditable-rubric direction across both decisions below.

Concrete unit-economics angle worth noting: **deterministic Tier 0 costs ~$0.001/URL vs LLM-first scorers at ~$0.005-0.02/URL**. That 5-20x gap is a real story for buyers running 10k+ URLs/month.

---

## Decision #3 — Signature pack source

### Recommendation: **Hybrid (Option C from the recon doc)**

Three components, in order of effort:

#### Component A: Vendor `enthec/webappanalyzer` (filtered)
- GPL-3.0, last push 2026-04-17, ~3,000 signatures, formal `schema.json`
- Filter to ~700 signatures whose categories intersect our use case (CMS, ecommerce, analytics, marketing automation, payment processors, page builders, live chat, CRM, appointment scheduling)
- Strip the 2,300 signatures we don't need (devops, security tools, IoT, etc.) → 3.4 MB → ~600 KB
- Pin to a snapshot, monthly auto-PR refresh via GitHub Action, human reviews diff
- **License hygiene:** keep the signature data isolated under `logic-engine/signals/wappalyzer_pack/`, ship enthec's `LICENSE` verbatim, link to source in README. Conservative posture treats data as separate from code; for closed-source SaaS the SaaS-loophole means no GPL distribution event triggers (confirm with counsel before any self-hosted shipping).

#### Component B: Vendor `retire.js` signatures (Apache-2.0)
- 4.1k stars, last push 2026-04-24, no GPL constraints
- Detects outdated/vulnerable JS libraries → strong "this site is decaying" signal that **no competitor surfaces** as a lead-quality marker
- Drop alongside Wappalyzer pack as `logic-engine/signals/retirejs_pack/`

#### Component C: Curate local-biz overlay (the differentiation)
- Wappalyzer is **strong on dev tooling, weak on local-biz SaaS**
- Confirmed gaps: **Booksy, Mindbody** (the signature DB research verified these are missing or weak)
- Curate ~30-50 signatures from scratch covering:
  - Booking systems: Booksy, Mindbody, Vagaro, Schedulicity, Square Appointments (verify), Setmore, Acuity (verify), 10to8
  - Restaurant POS / ordering: Toast Online Ordering, ChowNow, Square for Restaurants, Resy (front of house signals), OpenTable widgets
  - Salon / spa software: Boulevard, Phorest, Rosy, Mangomint
  - Contractor CRMs: ServiceTitan, Housecall Pro, Jobber, FieldEdge
  - Local marketing tools: BirdEye widget, Podium widget, NiceJob review widget
- Store as `logic-engine/signals/local_biz_pack/*.json` using the same Wappalyzer schema (so the same matcher engine handles all three packs)

#### Component D: Free remote APIs to plug in (orthogonal axes)
- **Google PageSpeed Insights v5** — 25k req/day per GCP project, full Lighthouse JSON. Free CWV, perf, SEO, accessibility scoring.
- **Mozilla Observatory v2** — no auth, 1 scan/host/min, A+→F security grade (HSTS, CSP, etc.)
- These run async after Tier 0 fingerprint match; results merge into `deterministic_evidence`

#### What to skip
- **BuiltWith** — $295-995/mo, free tier returns only category counts. Skip until paying customers.
- **SecurityHeaders.com API** — Snyk shutting down April 2026.
- **Hardenize** — no public free programmatic endpoint post-Red Sift acquisition.
- **CERN-CERT/wad** — last push Sept 2023, dead.
- **Building from scratch (Option B in recon)** — ruled out. 3,000+ signature-weeks of curation when 80% of value is already in `enthec`. Reserve curation effort for the local-biz overlay where Wappalyzer is genuinely thin.

### Why hybrid, not pure-vendor or pure-curate

- Pure-vendor (enthec only): comprehensive day-one but misses the local-biz layer that's our differentiation. Also, the GPL surface is bigger than necessary.
- Pure-curate (Option B): weeks of work to reach 700 sigs, fragile, reinventing.
- Hybrid: 80% comprehensive coverage from enthec, 100% relevance for our niche from the local-biz overlay, license risk minimized by isolating GPL'd component.

### Implementation sketch

```
logic-engine/
  signals/
    wappalyzer_pack/         # vendored, GPL'd, isolated
      LICENSE                # enthec's GPL-3.0
      filter_script.py       # one-time + scheduled refresh
      data/[a-z].json        # filtered signatures
    retirejs_pack/           # vendored, Apache-2.0
      LICENSE
      data/jsrepository.json
    local_biz_pack/          # our curation, MIT
      booking.json
      restaurant_pos.json
      salon_spa.json
      contractor_crm.json
      review_widgets.json
    matcher.py               # shared engine, reads all three packs
    remote_apis/
      psi.py                 # PageSpeed Insights wrapper
      observatory.py         # Mozilla Observatory wrapper
```

`matcher.detect(raw_lead) → list[Detection]` is the public API. Each `Detection` carries `(name, category, source_pack, signature_id, confidence, matched_field, matched_value)` so every score is traceable — that's the audit trail that nobody else ships.

---

## Decision #4 — Weights source

### Recommendation: **YAML now, XGBoost later (parallel, not replacement)**

#### Why YAML first

1. **No labels yet.** XGBoost needs a teacher-labeled training set. Tee's "20 good + 20 bad" benchmark hasn't been collected, and even when it lands, that's a precision/recall validation set, not a training set. XGBoost typically wants 500+ rows minimum. We're 1-2 months from having that.
2. **The auditable-rubric IS the differentiation** per competitive research. Persana, Clay, Apollo all use opaque scoring. A YAML rubric you can show a client ("here's why this lead scored 0.78, with the 6 signals that contributed") is the moat.
3. **Lower regression risk.** YAML weights are reviewable in PR, easy to roll back, easy to tune per campaign. ML drift is invisible.
4. **Existing roadmap aligns.** Project Phase 5 already plans XGBoost integration after teacher-label dataset saturates. YAML is the bridge that fills the next 2-3 months.

#### Recommended structure

```yaml
# logic-engine/campaigns/website_modernization.weights.yml
version: 1
campaign: website_modernization
required_signals:
  is_real_business: 1.0          # binary gate, must pass
weights:
  # Signal name (matches matcher.detect output)
  : weight (sum need not = 1.0)
  cms.wordpress: 0.15            # WordPress + outdated = prime modernization target
  signal.outdated_jquery: 0.20   # via Retire.js
  signal.no_mobile_viewport: 0.25
  signal.no_https: 0.20
  signal.poor_psi_mobile: 0.15   # via PSI
  signal.stale_copyright_3y: 0.10
  signal.no_schema_markup: 0.05
  # ...
ceilings:
  total_score: 1.0               # cap
gates:
  reject_if:
    - signal.is_parked_domain
    - signal.builder_squarespace_modern  # already on a modern stack
```

Per-campaign YAML files. Loaded at startup. Each signal is documented and traceable. Adding a new signal = add a row. Tweaking a weight = edit a number. Diff lives in git.

#### Migration path to XGBoost

Once we have ≥500 teacher-labeled rows (Tier 2 outputs serve as the labels per the No-Drop strategy):

1. Train XGBoost on the same `signal_name → value` features the YAML rubric uses
2. Ship XGBoost output as a **parallel signal** alongside the YAML score, not as a replacement
3. Compare YAML score vs XGBoost score per lead, log disagreement
4. After 2-3 weeks of comparison, decide: blend (e.g., 0.7 * YAML + 0.3 * XGBoost), promote XGBoost, or keep YAML if it's still winning
5. **Never drop the YAML rubric entirely** — it's the explainability layer for client-facing scoring

This preserves the audit story even after XGBoost is live: every lead gets a YAML rubric breakdown AND an XGBoost score, and the discrepancy itself is a useful signal for QA.

#### Why not "just XGBoost when we have labels"

The competitive research is clear: opaque scoring is what everyone else does. The moment TraceFabric becomes a black-box scorer, we lose the agency-friendly differentiation. The YAML rubric stays as the user-facing artifact even when XGBoost is the production scorer — XGBoost just becomes one input.

---

## What we still need from Tee (decisions #1 and #2)

1. **Tier priority confirm** for Phase 2 signal modules (default: S-tier first per recon doc)
2. **20 known-good + 20 known-bad URLs** for the validation benchmark (Tee said this comes later)

Phase 2 implementation can begin on signature pack vendoring + matcher engine + YAML weights schema in parallel — all of which is decision-independent. The labeled benchmark and tier confirm only block the *last mile* of Phase 2 (validation + tuning).

---

## Suggested Phase 2 starter scope (for when Tee greenlights)

**Sprint 1 (1-2 days):**
- Vendor enthec sigs with filter script
- Vendor retire.js sigs
- Build `signals/matcher.py` that reads both packs and returns `Detection[]` against a `RawLead` dict
- Wire matcher into `gatekeeper.py` so detections land in `heuristic_flags["technologies"]`
- Snapshot regression tests with ~10 fixture HTMLs (Squarespace, Shopify, WordPress, HubSpot, Calendly, Mailchimp, Stripe, Cloudflare)

**Sprint 2 (2-3 days):**
- Curate first 30 local-biz signatures (Booksy, Mindbody, Vagaro, Toast, Square Appointments, ServiceTitan, Housecall Pro, BirdEye widget, Podium widget, etc.)
- Wire PSI + Observatory remote APIs as background fetchers
- Define YAML weight schema and migrate the existing `deterministic_evaluator.py` scoring formula into it
- One YAML file per existing campaign (`website_modernization`, `voice_ai_agent`, `smma`)

**Sprint 3 (1 day):**
- Run full pipeline against Tee's 20-good / 20-bad benchmark when delivered
- Tune YAML weights based on precision/recall per signal
- Document tuning rationale per change

Ship as one PR per sprint, all behind a `signals_v2` feature flag in `runtime.py` so the existing pipeline is untouched until we explicitly cut over.

---

*Synthesis written 2026-04-30 from the two research docs in this folder. Recommendations are mine; final calls are Tee's.*
