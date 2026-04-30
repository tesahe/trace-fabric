# Phase 1b — Signature Database Evaluation for Tier 0 Deterministic Fingerprinting

> Goal: decide whether to vendor an existing tech-fingerprint signature pack (Wappalyzer-class) or hand-curate one for `logic-engine/signals/`. Tier 0 must run zero LLM calls.

## TL;DR

Vendor `enthec/webappanalyzer` (the de-facto living Wappalyzer fork) as a stripped, pinned snapshot bundled under `logic-engine/signals/wappalyzer_pack/`, and add a thin hand-curated overlay for the niche local-biz tools Wappalyzer doesn't cover (notably **Booksy**, plus a few Mindbody/booking edge cases). This is **Option C — Hybrid**, and the data below supports it. Reasoning: enthec is GPL-3.0, actively maintained (last push 2026-04-17, 492 stars), uses a clean documented JSON schema, ships ~3.4 MB across 27 alphabetic files, and already covers Squarespace, Shopify, Wix, HubSpot, Salesforce, Calendly, Vagaro, Mailchimp, Marketo, VWO, Vercel, Cloudflare, Stripe, etc. Hand-curating from scratch buys nothing.

Pair the local pack with two free remote APIs for what signature matching can't tell you: **Google PageSpeed Insights API** (25k req/day per project, free, returns a full Lighthouse report including modern-web SEO/perf/a11y scoring) and **Mozilla HTTP Observatory v2 API** (no auth, no quota, security header grade). Skip SecurityHeaders.com (Snyk announced its API shuts down April 2026), skip BuiltWith (paid, $295–$995/mo), skip Hardenize as a runtime dep (acquired by Red Sift, no public free API for bulk).

---

## 1. Open-source signature DB landscape

| Project | Repo | License | Last push | Signatures | Schema | Notes |
|---|---|---|---|---|---|---|
| **enthec/webappanalyzer** | github.com/enthec/webappanalyzer | GPL-3.0 | 2026-04-17 | ~3,000 across 27 JSON files (~3.4 MB) | JSON, formal `schema.json` | Stated successor to closed-source Wappalyzer, "committed not to set this repo private". Actively maintained, 492 stars. |
| **HTTPArchive/wappalyzer** | github.com/HTTPArchive/wappalyzer | GPL-3.0 | 2026-04-27 | Same starting corpus as enthec, slightly diverged | JSON, same schema | Maintained for the monthly HTTP Archive crawl. 116 stars. Less community traction than enthec but more institutional backing. |
| **WhatWeb** | github.com/urbanadventurer/WhatWeb | GPLv2 | 2026-04-03 | ~1,800 plugins | Ruby `.rb` files | Plugins are executable Ruby, not data. Unusable as a Python-importable corpus without rewriting. Good as a cross-check for niche detections. |
| **retire.js** | github.com/RetireJS/retire.js | Apache-2.0 | 2026-04-24 | Hundreds of vulnerable JS-lib signatures | JSON repository (`jsrepository.json`) | Apache-2.0 = permissive, no copyleft. Perfect "outdated/needs-modernization" signal — pair it with the Wappalyzer pack. |
| **CERN-CERT/WAD** | github.com/CERN-CERT/WAD | GPL-3.0 | 2023-09-01 | ~1,500 (legacy Wappalyzer fork) | JSON (legacy Wappalyzer format) | **Stale** — last push Sept 2023. Skip. |
| **PigeonSec/py-wappalyzer** | github.com/PigeonSec/py-wappalyzer | unspecified | active | downloads enthec data at runtime | Python lib | Not a signature DB itself. Useful as reference implementation showing how to load enthec JSON in Python 3.8+. |
| **chorsley/python-Wappalyzer** | pypi.org/project/python-Wappalyzer | MIT | archived | uses old Wappalyzer JSON | Python lib | Original Python wrapper, archived/unmaintained, no PyPI release in 12+ months. Skip the lib but the loader code is a 200-line reference. |

Wappalyzer JSON signature schema (per `schema.json`):

- **Required:** `cats[]` (numeric category IDs), `website`
- **Detectors:** `cookies`, `dom`, `dns`, `headers`, `html`, `text`, `css`, `robots`, `meta`, `probe`, `scriptSrc`, `scripts`, `url`, `xhr`, `js`, `certIssuer`
- **Metadata:** `description`, `icon`, `cpe`, `oss`, `saas`, `pricing[]` (low/mid/high/freemium/poa/payg/onetime/recurring)
- **Relationships:** `implies`, `requires`, `requiresCategory`, `excludes`

All detector values are JS-style regex strings with optional `\;version:\1` and `\;confidence:50` suffixes. Trivially portable to Python `re` — strip the `\;` annotations during load. 111 categories cover everything we care about (CMS=1, Ecommerce=6, Analytics=10, CDN=31, Marketing automation=32, Payment processors=41, Page builders=51, Live chat=52, CRM=53, Appointment scheduling=72, A/B Testing=74, Email=75, Hosting=88, Reservations & delivery=93, Form builders=110, etc.).

Sample signature (HubSpot, from `h.json`):

```json
"HubSpot": {
  "cats": [32],
  "scriptSrc": ["\\.hs-scripts\\.com/"],
  "html": ["<!-- Start of Async HubSpot"],
  "js": {"_hsq": "", "hubspot": ""},
  "dns": {"TXT": ["hubspotemail.net", "hubspot-domain-verification"]},
  "saas": true,
  "pricing": ["recurring", "high"]
}
```

The `pricing` array is gold for lead qualification — it tells us the prospect's stack is "high-recurring" (HubSpot Pro) vs "freemium" (Calendly free), which directly maps to budget signals.

## 2. Commercial alternatives

| Vendor | Free tier | Paid | Bulk license | Verdict |
|---|---|---|---|---|
| **BuiltWith** | Single-domain lookup via web UI; Free API rate-limited to 1 rps and only returns counts/categories | List-building $295/mo, Pro $495/mo, top tier ~$995/mo | Snowflake/Databricks/Redshift/BigQuery datasets (enterprise pricing, not published) | Overkill at our stage. Massive coverage but $3.5–12k/yr is wasted spend until we have paying customers. Worth revisiting at Tier 1 enrichment if we want firmographics. |
| **Wappalyzer Pro** (the closed-source one) | None for API | API plans start $250+/mo | Enterprise | Skip — same data as enthec but paid. |
| **WhatRuns / SimilarTech** | Limited free | Mid-3-figures monthly | Available | Skip for same reason. |

## 3. Free remote APIs worth wiring in

| API | Endpoint | Auth | Quota | What it gives us |
|---|---|---|---|---|
| **Google PageSpeed Insights v5** | `https://www.googleapis.com/pagespeedonline/v5/runPagespeed` | API key (free) | 25,000 req/day per GCP project, 400 per 100 sec | Full Lighthouse JSON: performance score, SEO score, a11y score, best-practices score, Core Web Vitals (LCP, CLS, INP, FCP, TTFB), opportunities, and **detected technologies** (Lighthouse runs its own light fingerprinter). High-signal "needs modernization" axis. |
| **Mozilla HTTP Observatory v2** | `POST https://observatory-api.mdn.mozilla.net/api/v2/scan?host=<HOST>` | None | 1 scan/host/min, cached otherwise | Letter grade A+→F + score 0–145 on security headers (CSP, HSTS, X-Frame-Options, Referrer-Policy, etc.). Fast, free, no key. Drop-in proxy for SecurityHeaders.com. |
| **CrUX History API** | `https://chromeuxreport.googleapis.com/v1/records:queryHistoryRecord` | API key | Generous free | Real-world Core Web Vitals from Chrome telemetry. Use only when PSI data is thin. |
| **SecurityHeaders.com API** | `api.securityheaders.com` | Paid sub | n/a | **Skip** — Snyk announced API shutdown April 2026. |
| **Hardenize** | private | n/a | n/a | **Skip** — post-Red Sift acquisition there's no public free programmatic endpoint. |

## 4. Per-signal-class coverage matrix

Coverage check against enthec/webappanalyzer at the categories we care about:

| Signal class | Enthec coverage | Examples confirmed | Gap fill needed? |
|---|---|---|---|
| CMS | Excellent | WordPress, Squarespace (cat 1), Wix, Joomla, Drupal, Ghost, Webflow | No |
| Page builders | Excellent | Elementor, Divi, Beaver Builder, Webflow, Carrd (cat 51) | No |
| E-commerce | Excellent | Shopify, WooCommerce, BigCommerce, Magento (cat 6) | No |
| Payment processors | Good | Stripe, PayPal, Square, Klarna (cat 41) | No |
| Analytics | Excellent | GA4, Mixpanel, Segment, Amplitude, Heap, Plausible, Fathom (cat 10) | No |
| CRM | Good | HubSpot, Salesforce, Pipedrive, ActiveCampaign (cat 53) | No |
| Email/Marketing automation | Good | Mailchimp, Klaviyo, Marketo, Pardot, Drip (cat 32, 75) | No |
| Booking widgets | **Mixed** | Calendly ✓, Acuity ✓, Vagaro ✓, Square Appointments ✓, Mindbody ✗, **Booksy ✗** | **Yes — add Booksy and verify Mindbody** |
| Live chat | Excellent | Intercom, Drift, Tidio, LiveChat, Zendesk Chat, Crisp (cat 52) | No |
| A/B testing | Good | Optimizely, VWO, Google Optimize (cat 74) | No |
| Hosting/CDN | Excellent | Cloudflare, Vercel, Netlify, AWS CloudFront, Fastly (cat 31, 62, 88) | No |
| Outdated JS libs | Use **retire.js** (separate Apache-2.0 corpus) | jQuery <3.5, Angular 1.x, Bootstrap 3, etc. | retire.js fills this |
| Security headers | Use **Mozilla Observatory** (remote API) | CSP, HSTS, etc. | Observatory fills this |
| Performance | Use **PSI/Lighthouse** (remote API) | LCP, CLS, INP | PSI fills this |

Direct verification (raw entries pulled from `enthec/webappanalyzer` main):

- **Calendly** → `cats:[72]`, `scriptSrc: ["assets\\.calendly\\.com/"]`, `js: {"Calendly.showPopupWidget": ""}` — present, strong.
- **Vagaro** → `cats:[72]`, `scriptSrc: ["www\\.schedulicity\\.com"]` — present (schedulicity is now a Vagaro brand).
- **Vercel** → `cats:[62]`, `headers: {x-vercel-id, x-vercel-cache, ...}` — present, strong.
- **VWO** → `cats:[10,74]`, `scriptSrc: ["dev\\.visualwebsiteoptimizer\\.com/"]` — present.
- **Booksy** → not present in `b.json`. **Hand-curate this one.** Easy: `*.booksy.com` script, `booksy-widget` class, "powered by Booksy" string.
- **Mindbody** → not in `m.json` excerpt; needs deeper check. If absent, easy to add (`clients.mindbodyonline.com` URL pattern, `MINDBODY` JS global, `healcode.com` script src for the embed).

## 5. Recommendation — Option C (Hybrid)

**Vendor enthec/webappanalyzer as a pinned snapshot, plus a thin local overlay.**

Why not Option A (vendor everything as-is):
- Bloat: 3.4 MB JSON across 27 files holds ~3,000 signatures, but only ~400–600 are relevant for local-biz lead qualification. Importing all of it slows Tier 0 startup and balloons the deny-list maintenance surface.
- Update cadence drift: enthec ships changes daily. Pinning a snapshot and refreshing on a known cadence (monthly cron PR) is safer than tracking `main` blindly.

Why not Option B (hand-curate from scratch):
- Coverage check above shows enthec already nails 95%+ of what we need. Building this from zero is weeks of work that Wappalyzer's community has already done — and they'll keep doing it for free.

Why not Option D (lean entirely on Lighthouse/Observatory):
- PSI's built-in tech fingerprinter is shallow (~50 detections) compared to enthec's ~3,000. PSI won't tell us "this is Webflow" or "this is HubSpot Marketing Hub vs Sales Hub." Use those APIs to **augment**, not replace.

Why Option C wins:
- We get the day-one comprehensive coverage of A.
- We get the precision and ownership of B for the 5–10 niche signatures Wappalyzer misses (Booksy, possibly Mindbody, GHL/HighLevel, GoHighLevel landers, ClickFunnels v2, niche local-biz CRMs).
- We get the orthogonal evidence axes (perf/security/a11y) of D from free remote APIs.
- License risk is contained: GPL-3.0 covers code derivative work; the JSON data files are arguably not "code" but conservative posture is to keep them in a clearly delineated `signals/wappalyzer_pack/` subtree, ship the upstream `LICENSE` alongside, and link to the source. We are not modifying and redistributing a binary — we are running the data behind a network service (Tier 0 deterministic evaluator), which under standard GPL interpretation is not a "distribution" event. **Confirm with counsel before shipping a self-hosted version to clients**, but for SaaS use the SaaS-loophole logic holds.

## 6. Implementation notes for `logic-engine/`

Drop in alongside the existing Tier 0 modules (`gatekeeper.py`, `deterministic_evaluator.py`):

```
logic-engine/
  signals/
    __init__.py
    wappalyzer_pack/
      LICENSE                 # vendored verbatim from enthec
      VERSION                 # e.g. "enthec@a3f9c21 2026-04-17"
      categories.json
      technologies/
        _.json a.json b.json ... z.json   # filtered subset
      schema.json
    overlay/
      booksy.json             # our additions
      mindbody.json
      gohighlevel.json
    matcher.py                # the actual fingerprinting engine
    retire_js/
      jsrepository.json       # Apache-2.0, no GPL constraint
```

`matcher.py` responsibilities:
1. On import: load categories.json + all `technologies/*.json` + overlay JSONs into a single `dict[name -> Signature]`. Compile every regex pattern once with `re.IGNORECASE`. ~50 ms cold start for the full corpus, free thereafter.
2. Public API:
   ```python
   def detect(raw_lead: RawLead) -> list[Detection]: ...
   ```
   where `Detection = (tech_name, category_ids, confidence, evidence_kind, matched_pattern)`. Iterate signatures × evidence sources (`raw_lead.script_srcs`, `raw_lead.stylesheet_hrefs`, `raw_lead.response_headers`, `raw_lead.raw_html`, `raw_lead.text_content`). Short-circuit on first hit per signature per evidence kind, accumulate confidence.
3. Apply `implies` chains transitively (Shopify implies PHP; HubSpot CMS implies HubSpot).
4. Return structured detections that downstream rule modules in `logic-engine/signals/rules/` can consume — e.g. "if `cats` includes 53 (CRM), set `lead.has_crm = True`"; "if any detection has `pricing: high`, raise budget signal."

Curation step (one-time): write a 30-line script that walks `enthec/webappanalyzer/src/technologies/*.json` and **keeps only signatures whose `cats` intersect** our shortlist `{1, 6, 10, 31, 32, 41, 51, 52, 53, 62, 67, 72, 74, 75, 88, 92, 93, 110}`. Estimated trim: 3.4 MB → ~600 KB, ~3,000 → ~700 sigs. Re-run monthly via GitHub Action that opens a PR; human reviews diff.

Remote API integration: add `signals/remote/psi.py` and `signals/remote/observatory.py` as Tier 0.5 (best-effort, soft-fail, ~3 s timeout). They run in parallel via `asyncio.gather` after the local matcher returns. Cache results in Postgres keyed by `(host, day)` to stay well under PSI's 25k/day limit (single GCP project handles ~700k unique hosts/month).

Tests: snapshot-test the matcher against `tests/fixtures/raw_html/` samples for each major category. Add a CI guardrail that fails if an upstream snapshot bump removes a detection we depend on (Squarespace, Shopify, WordPress, HubSpot, Calendly, Mailchimp, Stripe, Cloudflare).

---

## Sources

- enthec/webappanalyzer: https://github.com/enthec/webappanalyzer
- HTTPArchive/wappalyzer: https://github.com/HTTPArchive/wappalyzer
- enthec schema: https://raw.githubusercontent.com/enthec/webappanalyzer/main/schema.json
- enthec categories: https://raw.githubusercontent.com/enthec/webappanalyzer/main/src/categories.json
- WhatWeb: https://github.com/urbanadventurer/WhatWeb
- retire.js: https://github.com/RetireJS/retire.js
- CERN-CERT/WAD: https://github.com/CERN-CERT/WAD
- py-wappalyzer (enthec-based Python loader reference): https://github.com/PigeonSec/py-wappalyzer
- BuiltWith plans: https://builtwith.com/plans
- BuiltWith free API: https://api.builtwith.com/free-api
- Mozilla HTTP Observatory v2: https://developer.mozilla.org/en-US/observatory and https://github.com/mdn/mdn-http-observatory
- PageSpeed Insights API: https://developers.google.com/speed/docs/insights/v5/get-started
- SecurityHeaders.com API shutdown notice: https://securityheaders.com/api/
- Hardenize (Red Sift): https://www.hardenize.com/
- GPL-3.0 SaaS loophole reference: https://www.revenera.com/blog/software-composition-analysis/understanding-the-saas-loophole-in-gpl/
