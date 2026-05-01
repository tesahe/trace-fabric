# wappalyzer_pack provenance

## Upstream

- **Project:** [enthec/webappanalyzer](https://github.com/enthec/webappanalyzer)
- **License:** GPL-3.0 (see `LICENSE` in this directory)
- **Snapshot commit:** `c2855b4652b4a205c55a7fa7cbf6f02d0d6dd82b`
- **Snapshot date:** 2026-04-17 (upstream commit timestamp)
- **Vendored on:** 2026-04-30

## Filter run (this snapshot)

- Categories kept: 24 of 108
- Signatures kept: 4193 of 7518 (retention: 55.8%)
- Output size: ~1.7 MB across 27 per-letter JSON files plus
  `categories.json` (2.3 KB) and `groups.json`
- Missing allowlisted category ids: none

## How this pack is produced

1. Clone the upstream repo:
   ```
   git clone --depth=1 https://github.com/enthec/webappanalyzer.git /tmp/wappalyzer-source
   ```
2. Run the filter script from this repo:
   ```
   python3 logic-engine/signals/scripts/filter_wappalyzer.py \
       --source /tmp/wappalyzer-source \
       --output logic-engine/signals/wappalyzer_pack/data/
   ```
3. Commit the regenerated `data/` directory and update the **Snapshot
   commit** + **Snapshot date** fields above.

The filter is idempotent and the only authoritative way to (re)build
this pack — never hand-edit files under `data/`.

## Categories retained

The matcher only cares about technologies that signal
local-business buying intent or operational maturity. The full kept set
is documented in `data/categories.json` and reproduced here for review:

| ID  | Name                       | Why we kept it                                         |
| --- | -------------------------- | ------------------------------------------------------ |
| 1   | CMS                        | Required (brief)                                        |
| 6   | Ecommerce                  | Required (brief)                                        |
| 10  | Analytics                  | Required (brief)                                        |
| 32  | Marketing automation       | Required (brief)                                        |
| 41  | Payment processors         | Required (brief)                                        |
| 42  | Tag managers               | GTM/Segment presence implies marketing maturity         |
| 51  | Page builders              | Required (brief)                                        |
| 52  | Live chat                  | Required (brief)                                        |
| 53  | CRM                        | Required (brief)                                        |
| 54  | SEO                        | Yoast / RankMath etc. signal SEO investment             |
| 58  | User onboarding            | Intercom Tours, Userpilot, etc.                         |
| 67  | Cookie compliance          | GDPR/CCPA banners signal compliance maturity            |
| 72  | Appointment scheduling     | Required (brief); covers most salon/spa platforms       |
| 73  | Surveys                    | Typeform / SurveyMonkey – customer feedback             |
| 74  | A/B Testing                | Required (brief)                                        |
| 75  | Email                      | Mailchimp / Klaviyo (often dual-purpose w/ marketing)   |
| 90  | Reviews                    | Yotpo / Trustpilot widgets                              |
| 93  | Reservations & delivery    | Required (brief said "88" — see "Brief substitutions") |
| 97  | Customer data platform     | Segment / mParticle                                     |
| 98  | Cart abandonment           | Ecom recovery tooling                                   |
| 100 | Shopify apps               | High-signal for Shopify-hosted local biz                |
| 104 | Ticket booking             | Eventbrite / Tixly (events / venue verticals)           |
| 110 | Form builders              | Typeform / JotForm / Wufoo (lead capture)               |
| 111 | Fundraising & donations    | Non-profit local-biz lead vector                        |

## Brief substitutions

- The Sprint 1 brief listed **"Reservations and delivery (88)"**. Upstream
  category id `88` is actually **Hosting**. The category labelled
  *"Reservations & delivery"* upstream is id `93`, so we kept `93`.
- The brief asked for a **"Salon & spa"** category. No such category
  exists upstream. Salon/spa SaaS (Booksy, Mindbody, Vagaro,
  GlossGenius, Boulevard, etc.) live under `72` *Appointment
  scheduling*. We kept `72` and will supplement vertical-specific
  coverage via curated entries in `local_biz_pack/` in a later sprint.
