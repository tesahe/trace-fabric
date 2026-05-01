# local_biz_pack

Placeholder for ~30-50 hand-curated local-business technology signatures
(Booksy, Mindbody, Vagaro, Toast, Square for Restaurants, ServiceTitan,
Housecall Pro, Jobber, GlossGenius, Boulevard, OpenTable, Resy, etc.).

These verticals are under-represented in the upstream
`enthec/webappanalyzer` corpus, so we maintain our own signatures here.
The aim is to cover the platforms that matter most for TraceFabric's
local-business lead qualification: salon/spa booking, restaurant POS,
home-services dispatch, fitness/wellness scheduling, and
appointment-driven SaaS in general.

## Status

Empty for now. Curated entries land in a later sprint. The matcher engine
(Check-in 2) is built to consume this pack as soon as the JSON files exist.

## Schema

Signatures follow the same JSON schema as
`logic-engine/signals/wappalyzer_pack/`. See `schema.md` in this
directory for fields, pattern syntax, and a fully written-out example.

## License

Curated entries here are TraceFabric copyright, released under the
project's existing Apache-2.0 license. Do **not** copy entries verbatim
from the GPL-3.0 wappalyzer_pack into this directory.

## Layout (target)

```
local_biz_pack/
  data/
    booksy.json          # one file per platform, or grouped by vertical
    mindbody.json
    toast.json
    ...
  categories.json        # extends Wappalyzer category space if needed
```
