# Local-biz signature schema

Curated signatures in `local_biz_pack/` follow the
[Wappalyzer technology fingerprint schema](https://github.com/enthec/webappanalyzer/blob/main/schema.json),
the same schema used by `wappalyzer_pack/`. This keeps the matcher engine
(Check-in 2) uniform across vendored and curated packs.

## Top-level shape

Each signature is keyed by display name. Example:

```json
{
  "Booksy": {
    "cats": [72],
    "...": "..."
  }
}
```

## Fields

| Field              | Type                     | Notes                                                                                      |
| ------------------ | ------------------------ | ------------------------------------------------------------------------------------------ |
| `cats`             | `int[]`                  | Required. Category IDs from `wappalyzer_pack/data/categories.json` (or local extensions).  |
| `description`      | `string`                 | One-sentence platform description.                                                         |
| `website`          | `string`                 | Vendor homepage URL.                                                                       |
| `icon`             | `string`                 | Icon filename (we don't bundle icons; field is informational).                             |
| `pricing`          | `string[]`               | Any of `low`, `mid`, `high`, `freemium`, `recurring`, `onetime`, `payg`, `poa`.            |
| `saas`             | `bool`                   | Hosted SaaS offering.                                                                      |
| `oss`              | `bool`                   | Open-source.                                                                               |
| `implies`          | `string` or `string[]`   | Other technologies whose presence is implied. Optional confidence: `"jQuery\\;confidence:50"`. |
| `requires`         | `string` or `string[]`   | Hard prerequisites. Signature only fires if listed techs also matched.                     |
| `requiresCategory` | `int` or `int[]`         | Hard prerequisite category presence.                                                       |
| `excludes`         | `string` or `string[]`   | Mutually exclusive technologies (suppress if matched).                                     |
| `scriptSrc`        | `string` or `string[]`   | Regex(es) matched against `<script src="...">` URLs.                                       |
| `scripts`          | `string` or `string[]`   | Regex(es) matched against inline script bodies.                                            |
| `html`             | `string` or `string[]`   | Regex(es) matched against full HTML.                                                       |
| `text`             | `string` or `string[]`   | Regex(es) matched against rendered/visible text.                                           |
| `dom`              | `object` or `string[]`   | CSS selectors with optional attribute/text checks (see DOM section).                       |
| `css`              | `string` or `string[]`   | Regex(es) matched against stylesheet contents.                                             |
| `headers`          | `object`                 | Map of HTTP header name -> regex pattern.                                                  |
| `cookies`          | `object`                 | Map of cookie name -> regex pattern matched against the cookie value.                      |
| `meta`             | `object`                 | Map of `<meta name="...">` -> regex pattern matched against `content`.                     |
| `dns`              | `object`                 | Map of DNS record type -> pattern (e.g. `"MX": "\\.googlemail\\.com"`).                    |
| `robots`           | `string` or `string[]`   | Regex(es) matched against `/robots.txt`.                                                   |
| `url`              | `string` or `string[]`   | Regex(es) matched against the page URL.                                                    |
| `js`               | `object`                 | Map of JS global expression -> expected value regex (runtime check; usually unused).       |
| `xhr`              | `string` or `string[]`   | Regex(es) matched against XHR/fetch hostnames.                                             |

## Pattern annotation syntax

Wappalyzer extends regex strings with semicolon-separated annotations:

```
<regex>\;version:\1\;confidence:50
```

- `version:` extracts a version string. `\1` references the first capture
  group in the regex; literal versions like `version:18` also work.
- `confidence:` overrides the default 100% match confidence (0-100).
- Multiple annotations are chained with `\;`.

Example:

```json
{
  "scriptSrc": "stripe\\.com/v3/?\\;version:3\\;confidence:90"
}
```

## DOM matchers

`dom` accepts either an array of CSS selectors (presence-only match) or an
object keyed by selector with attribute / text / property checks:

```json
{
  "dom": {
    "link[rel='stylesheet'][href*='booksy']": {
      "attributes": {
        "href": "booksy\\.com/widget\\;version:\\1"
      }
    }
  }
}
```

## Worked example: Booksy

A future curator adding Booksy to `local_biz_pack/data/booksy.json` would
write:

```json
{
  "Booksy": {
    "cats": [72],
    "description": "Booksy is an appointment booking and customer-management platform widely used by salons, barbershops, and personal-care providers.",
    "website": "https://booksy.com",
    "saas": true,
    "pricing": ["mid", "recurring"],
    "icon": "Booksy.svg",
    "implies": ["jQuery\\;confidence:30"],
    "scriptSrc": [
      "booksy\\.com/widget",
      "cdn\\.booksy\\.com",
      "static\\.booksy\\.com/.+\\.js\\;version:\\1"
    ],
    "html": [
      "<iframe[^>]+booksy\\.com[^>]+>",
      "<a[^>]+href=\"https?://(?:[a-z0-9-]+\\.)?booksy\\.com/[^\"]*\""
    ],
    "dom": {
      "a[href*='booksy.com/book']": {
        "attributes": {
          "href": "booksy\\.com/book/(?<slug>[a-z0-9_-]+)"
        }
      }
    },
    "url": "booksy\\.com",
    "meta": {
      "generator": "[Bb]ooksy"
    }
  }
}
```

## Adding a new signature: checklist

1. Pick or create a category id. Reuse an existing wappalyzer category
   when possible to keep matcher behaviour uniform across packs.
2. Aim for 2-3 independent signal types (e.g. `scriptSrc` + `html` + `url`)
   to keep false positives down.
3. Anchor regexes (`\\b...\\b`, escape dots) — Wappalyzer treats every
   pattern as case-insensitive but does not auto-anchor.
4. Set `confidence` below 100 on weaker signals so the matcher can
   tier them.
5. Add a one-line `description` and the vendor's `website`.
6. Run the matcher engine (Check-in 2) test suite locally before
   committing.
