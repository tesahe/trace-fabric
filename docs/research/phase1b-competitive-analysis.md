# TraceFabric — Phase 1b Competitive Analysis

**Scope:** Deterministic-signal extraction across lead-scraping / lead-qualification tools that target local businesses. Goal: confirm where the field invests, where it punts to LLMs, and where TraceFabric's "audited deterministic + LLM cascade" angle fits.

**Date:** 2026-04-30
**Sources hit:** 14 (cited inline)

---

## 1. Competitive Landscape Summary

The space splits into four archetypes:

1. **Local-business map scrapers** (MapiLeads, Outscraper, Lead Scrape, Local Scraper, Apify Compass actor, Maps Leads) — input is niche+location, they pull GMB/Google Maps + walk the website for emails, phones, socials. **Signal layer is shallow:** business card + scraped contact details. Tech-stack detection is shallow when present at all. Cheap-to-build, race-to-the-bottom pricing (Apify B2B Lead Scraper is $3.90 / 1k results — [apify.com/junipr/b2b-lead-scraper](https://apify.com/junipr/b2b-lead-scraper)).
2. **B2B contact databases with enrichment layer** (Apollo.io, Cognism, ZoomInfo, Ocean.io) — they own a contact graph, then bolt on technographic + intent. Intent comes from third-party feeds (Bombora, LeadSift). Technographics are licensed or proprietary crawls, never per-request live. ([apollo.io/product/buying-intent](https://www.apollo.io/product/buying-intent), [cognism.com/blog/what-are-technographics](https://www.cognism.com/blog/what-are-technographics)).
3. **Workflow orchestrators / waterfalls** (Clay.com, Persana AI, PhantomBuster) — don't own data, they route requests through 75-150 third-party providers and let users glue together GPT calls in between. Clay explicitly markets "scrape company data + pass to ChatGPT" ([clay.com/waterfall-enrichment](https://www.clay.com/waterfall-enrichment), [persana.ai](https://persana.ai/)).
4. **Audit / agency-style tools** (GoHighLevel Prospecting, Website Grader, "AI website audit" Apify actors) — closest semantic neighbors to TraceFabric. GHL generates a marketing-audit PDF per local business covering listings, reviews, online presence gaps ([help.gohighlevel.com](https://help.gohighlevel.com/support/solutions/articles/48001231875-how-to-generate-leads-using-the-highlevel-prospecting-tool)). Quality of signal extraction is thin and the report is the product, not raw scored leads.

**Dominant model:** Hybrid leaning AI-black-box. Persana, Clay, and Apollo openly market "AI lead scoring" with no public scoring rubric. Cognism and Apollo own the deterministic firmographic/technographic layer but it's *their* graph, not extracted live per-URL. Nobody in the surveyed field markets "audited, reproducible, deterministic-first scoring at the per-URL level" — that gap is real.

---

## 2. Signal Taxonomy Table

Cells: `D` = deterministic regex/header/parse; `LLM` = AI-inferred; `3P` = bought from third party; `–` = not offered.

| Signal | MapiLeads | Apollo | Clay | Outscraper | Apify actors | PhantomBuster | Cognism | Ocean.io | Persana | Lead Scrape | GHL | Wappalyzer (lib) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GMB / Maps profile (name, addr, hours, rating, reviews) | D | – | D-via-actor | D | D | D | – | – | D | D | D | – |
| Email harvest (info@, contact@) | D | 3P | D-via-actor | D | D | D | 3P | – | 3P | D | D | – |
| Phone validation | D | 3P | 3P | D | D | – | D (mobile-verified) | – | 3P | D (98% bounce) | – | – |
| Social presence (FB/IG/LI/TT) | D | – | D | D | D | D | – | D | – | D | D | – |
| Tech stack detection | shallow | 3P (own DB) | 3P | – | D (live, B2B Lead Scraper) | – | 3P (own DB) | 3P | 3P | D (shallow) | – | **D (3000+ regex sigs)** |
| Domain age / WHOIS | – | – | possible-via-script | – | possible | – | – | – | – | – | – | – |
| Page speed / CWV | – | – | possible-via-script | – | possible | – | – | – | – | – | partial | – |
| Mobile-friendly | – | – | possible-via-script | – | possible | – | – | – | – | – | partial | – |
| SSL / HTTPS posture | – | – | possible | – | possible | – | – | – | – | – | – | – |
| Schema.org / structured data | – | – | – | – | – | – | – | – | – | – | – | – |
| Outdated JS / vulnerable libs | – | – | – | – | – | – | – | – | – | – | – | partial (Retire.js separately) |
| Active hiring | – | LLM/3P | 3P | – | – | – | 3P (signals) | – | LLM | – | – | – |
| Funding events | – | LLM/3P | 3P | – | – | – | 3P | – | LLM | – | – | – |
| Buying intent (topic) | – | 3P (Bombora/LeadSift) | 3P | – | – | LLM | 3P (Bombora) | – | LLM | – | – | – |
| Reviews semantic summary | LLM ("Smart Reviews") | – | LLM | – | – | – | – | – | LLM | – | – | – |
| Lookalike scoring | – | D-vector | – | – | – | – | – | **D (20 filters)** | – | – | – | – |
| Marketing audit PDF | – | – | – | – | – | – | – | – | – | – | D-template | – |
| Custom scoring rubric (audited) | – | opaque | user-built | – | – | – | opaque | – | opaque | – | template | – |

Key observations:
- **Domain age, page speed, mobile-friendly, SSL grade, schema markup, vulnerable JS** — **nobody** in the lead-tool field surfaces these as first-class signals. They sit in the SEO-audit world ([thrillxdesign.com](https://thrillxdesign.com/the-ultimate-website-audit-checklist/), [website.grader.com](https://website.grader.com/)) but aren't wired into a lead-scoring pipeline.
- **Tech-stack detection** is the only deterministic signal everyone agrees matters — and most of them buy or license it rather than running it live per-request.
- Clay and Apify let users *script* deterministic checks but ship nothing curated by default ([clay.com/waterfall-enrichment](https://www.clay.com/waterfall-enrichment), [use-apify.com/docs/best-apify-actors/best-lead-generation-actors](https://use-apify.com/docs/best-apify-actors/best-lead-generation-actors)).

---

## 3. Deterministic-Only Signal Field — Deep Dive

What's actually cheap and reliable to extract per-URL, with no LLM tokens:

**Header / response layer:**
- `Server`, `X-Powered-By`, `Set-Cookie` patterns → CMS, framework, hosting
- HTTP status, redirect chain → site health
- TLS cert issuer + expiry → trust signal
- HTTP/2 / HTTP/3 support → modernity proxy

**HTML / DOM layer:**
- `<meta generator>` → CMS confirmation
- `<script src=…>` paths → JS framework, analytics, chat widget, booking widget
- `<link rel=…>` → favicons, sitemap, manifest (PWA)
- Schema.org JSON-LD blocks → LocalBusiness, Restaurant, Service offerings
- Open Graph + Twitter card presence → marketing maturity
- Form fields + `action` URLs → CRM/lead-capture tool fingerprint
- Embedded social handles (regex `instagram\.com/[\w.]+`) → social presence depth

**Behavioral / external layer (still deterministic):**
- WHOIS lookup → domain age, registrar, expiry runway ([whois.whoisxmlapi.com/domain-age-checker](https://whois.whoisxmlapi.com/domain-age-checker))
- DNS records → MX provider (Google Workspace vs hosted), SPF/DKIM presence (email maturity), CAA records
- PageSpeed Insights API → Core Web Vitals (free, deterministic given URL)
- Mobile-friendly test → Google's free API
- robots.txt + sitemap.xml → SEO posture
- HTTPS-only redirect → security posture

**Content-derived (regex-only, no LLM):**
- Phone number extraction (libphonenumber)
- Email harvesting (RFC patterns)
- Address extraction (postal patterns + city/state lists)
- Booking-link detection (Calendly, Square, OpenTable URLs)
- Payment-processor fingerprint (Stripe, Square, PayPal script srcs)

The Wappalyzer fingerprint format — "categories, cookies, dom, js, headers, html, scripts, scriptSrc, meta, implies" — is the canonical schema for this whole layer ([github.com/enthec/webappanalyzer](https://github.com/enthec/webappanalyzer)). Treat it as the de facto standard.

**Cost-per-URL (rough order):** WHOIS ~$0.0001, PSI ~free, fetch + parse + signature match ~$0.0005 in compute. **Total deterministic Tier 0 < $0.001 per URL.** A Gemini Flash call to the same content is ~$0.005-0.02. That's a 5-20x cost gap that nobody is currently exploiting as a marketed product.

---

## 4. Signature DB Landscape

**Wappalyzer (original)** — went private August 2023. The pre-private MIT-licensed snapshot lives at [github.com/dochne/wappalyzer](https://github.com/dochne/wappalyzer) and [github.com/Lissy93/wapalyzer](https://github.com/Lissy93/wapalyzer). Useful as a baseline but freezing in time.

**Enthec/webappanalyzer** — actively-maintained fork, **GPLv3 licensed**, explicit commitment never to privatize ([github.com/enthec/webappanalyzer](https://github.com/enthec/webappanalyzer)). 3000+ technology signatures organized as JSON regex bundles in `src/technologies/[a-z].json`. Same fingerprint structure as the original. **GPLv3 is the gotcha** — vendoring it forces TraceFabric (or at least the sig-matching component) to be GPLv3 too. If TraceFabric is closed-source SaaS this is workable (no distribution = no GPL trigger), but if you ship a CLI or self-hosted edition, GPL contamination is a real concern.

**Implementations to vendor (not rebuild):**
- [projectdiscovery/wappalyzergo](https://github.com/projectdiscovery/wappalyzergo) — high-perf Go port, MIT, used by ProjectDiscovery security tools
- [PigeonSec/py-wappalyzer](https://github.com/PigeonSec/py-wappalyzer) — Python lib using enthec sigs, parses HAR files (great for your Rust scraper → Python evaluator flow)
- [rverton/webanalyze](https://pkg.go.dev/github.com/rverton/webanalyze) — Go port, used widely
- Wappalyzer-next CLI — Python CLI on enthec sigs

**BuiltWith** — 250M+ websites in their DB, free API is rate-limited to 1 req/sec and only returns category counts ([api.builtwith.com/free-api](https://api.builtwith.com/free-api)). Paid tiers are credit-based; bulk lookups burn credits fast ([kb.builtwith.com](https://kb.builtwith.com/general-questions/plans-and-pricing-explained/)). Not viable for live per-request use unless you cache aggressively. Useful for *cohort* lookups ("all Shopify stores in Austin") but that's a different product.

**Retire.js** — manually-maintained JSON of vulnerable JS library signatures ([github.com/retirejs/retire.js](https://github.com/RetireJS/retire.js/), `repository/jsrepository.json`). Apache 2.0. Detects by URL, filename, content, or hash. Vendor this directly for the "outdated JS" signal — nobody in the lead-tool space surfaces it and it's a strong "this site is decaying" indicator.

**Other open alternatives:** Stackcrawler ($9/mo, paid), urlscan.io (free for non-commercial, has its own fingerprint engine). No serious permissive-license alternative to Wappalyzer's coverage exists — the GPLv3 enthec fork is effectively the only game in town.

**Recommendation:** Vendor Enthec sigs in a process-isolated component (Python evaluator subprocess, AGPL/GPL boundary clean), keep TraceFabric core MIT/proprietary. Layer Retire.js sigs alongside. Add custom curated sigs for local-business-specific tools (booking systems, POS systems, restaurant CMSes) where Wappalyzer is weak.

---

## 5. Differentiation Angle

**The gap:** Every competitor either (a) sells a contact graph with opaque scoring (Apollo, Cognism), (b) sells raw scraped business cards with no scoring (Outscraper, MapiLeads, Lead Scrape), or (c) sells a workflow canvas where the user has to build their own scoring (Clay, Persana). **No one ships a curated, audited, deterministic-first scoring pipeline that runs live per-URL and exposes the rubric.**

**TraceFabric's defensible play — three claims, in priority order:**

1. **"Audited deterministic Tier 0 → LLM cascade only when needed"** — every score has a reproducible trace (which signature matched, which header value, which regex hit). Competitors hide this. This matters for agencies that need to *justify* a lead score to a client.
2. **"Local-business signal coverage that generic tech-stack DBs miss"** — booking systems, restaurant POS, salon software, contractor CRMs. Wappalyzer is strong on dev tooling, weak on local-biz SaaS. Curate this gap.
3. **"5-20x cheaper at scale than LLM-first scorers"** — concrete unit-economics story for users running 10k+ URLs/month. Persana and Clay burn tokens on every lead; TraceFabric only spends tokens when deterministic signals are inconclusive.

**Risks to flag:**
- Clay can imitate this in a week if they ship a "deterministic block library" — they have the user base and the canvas.
- Apollo could turn on per-URL live scoring if they wanted; they're holding back because contact-DB margins are better.
- The "audited rubric" angle only matters to buyers who care about explainability — agencies, RegTech-adjacent verticals. Mass-market SDRs don't care.

**Build-don't-vendor calls:**
- Build: curated local-biz SaaS sigs, the deterministic scoring engine, the audit-trail UI.
- Vendor: Enthec Wappalyzer sigs (process-isolated for license hygiene), Retire.js sigs, Google PSI/Mobile-Friendly APIs, libphonenumber, public WHOIS.

---

## Sources

1. [mapileads.com](https://mapileads.com/)
2. [apollo.io/product/buying-intent](https://www.apollo.io/product/buying-intent)
3. [cognism.com — what are technographics](https://www.cognism.com/blog/what-are-technographics)
4. [cognism.com/signal-data](https://www.cognism.com/signal-data)
5. [clay.com/waterfall-enrichment](https://www.clay.com/waterfall-enrichment)
6. [outscraper.com/google-maps-scraper](https://outscraper.com/google-maps-scraper/)
7. [apify.com/junipr/b2b-lead-scraper](https://apify.com/junipr/b2b-lead-scraper)
8. [use-apify.com — best lead generation actors](https://use-apify.com/docs/best-apify-actors/best-lead-generation-actors)
9. [phantombuster — Data Scraping Crawler](https://support.phantombuster.com/hc/en-us/articles/26971188404370-How-to-use-the-Data-Scraping-Crawler)
10. [ocean.io/api](https://www.ocean.io/api)
11. [persana.ai — lead enrichment](https://persana.ai/blogs/what-is-lead-enrichment-in-sales)
12. [leadscrape.com](https://www.leadscrape.com/)
13. [help.gohighlevel.com — Prospecting Tool](https://help.gohighlevel.com/support/solutions/articles/48001231875-how-to-generate-leads-using-the-highlevel-prospecting-tool)
14. [github.com/enthec/webappanalyzer](https://github.com/enthec/webappanalyzer)
15. [github.com/RetireJS/retire.js](https://github.com/RetireJS/retire.js/)
16. [api.builtwith.com/free-api](https://api.builtwith.com/free-api)
17. [kb.builtwith.com — plans](https://kb.builtwith.com/general-questions/plans-and-pricing-explained/)
18. [github.com/projectdiscovery/wappalyzergo](https://github.com/projectdiscovery/wappalyzergo)
19. [github.com/dochne/wappalyzer (pre-private snapshot)](https://github.com/dochne/wappalyzer)
20. [galadon.com — Wappalyzer alternatives](https://galadon.com/wappalyzer-alternatives)
