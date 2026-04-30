#!/usr/bin/env python3
"""Filter the enthec/webappanalyzer signature pack down to lead-qualification categories.

Reads a fresh upstream clone of `enthec/webappanalyzer` and writes a filtered
copy of the per-letter technology JSON files plus a filtered `categories.json`
into the destination directory. Only signatures whose `cats` field intersects
the category allowlist below are retained.

This script is intentionally dependency-free (stdlib only) so it can be re-run
in any Python 3.10+ environment without touching `requirements.txt`.

Usage:
    python3 filter_wappalyzer.py \
        --source /tmp/wappalyzer-source \
        --output ../wappalyzer_pack/data/

The script is idempotent: it overwrites the output directory contents on each
run. Use `--dry-run` to preview stats without writing files.
"""

from __future__ import annotations

import argparse
import json
import string
import sys
from pathlib import Path
from typing import Any

# --- Category allowlist ------------------------------------------------------
#
# Category IDs are sourced from upstream `src/categories.json`. The list below
# was hand-picked for the local-business lead qualification use case.
#
# Required by the Sprint 1 brief:
#   1   CMS
#   6   Ecommerce
#   10  Analytics
#   32  Marketing automation
#   41  Payment processors
#   51  Page builders
#   52  Live chat
#   53  CRM
#   72  Appointment scheduling
#   74  A/B Testing
#   93  Reservations & delivery   (brief said "88" but upstream id is 93;
#                                  88 upstream is "Hosting" — not what we want)
#
# Brief also asked for "Salon & spa" but no such top-level category exists
# upstream. Salon/spa-specific platforms (Booksy, Mindbody, Vagaro, etc.) live
# under category 72 (Appointment scheduling). Curated local-biz signatures
# will live in `local_biz_pack/` in a later sprint.
#
# Additional categories kept for direct local-biz lead-qual relevance:
#   42  Tag managers          - GTM/Segment presence implies marketing maturity
#   54  SEO                   - Yoast, RankMath, etc. signal SEO investment
#   58  User onboarding       - Intercom Tours, Userpilot, etc.
#   67  Cookie compliance     - GDPR/CCPA banners signal compliance maturity
#   73  Surveys               - Typeform, SurveyMonkey, customer feedback
#   75  Email                 - Mailchimp, Klaviyo (often dual-purpose)
#   90  Reviews               - Yotpo, Trustpilot, Google Reviews widgets
#   97  Customer data platform
#   98  Cart abandonment
#   100 Shopify apps          - High-signal for ecom local biz
#   104 Ticket booking        - Eventbrite, Tixly (event/venue verticals)
#   110 Form builders         - Typeform, JotForm, Wufoo (lead capture)
#   111 Fundraising & donations - non-profit local-biz lead vector
#
ALLOWLIST_CATEGORY_IDS: set[int] = {
    1,    # CMS
    6,    # Ecommerce
    10,   # Analytics
    32,   # Marketing automation
    41,   # Payment processors
    42,   # Tag managers
    51,   # Page builders
    52,   # Live chat
    53,   # CRM
    54,   # SEO
    58,   # User onboarding
    67,   # Cookie compliance
    72,   # Appointment scheduling
    73,   # Surveys
    74,   # A/B Testing
    75,   # Email
    90,   # Reviews
    93,   # Reservations & delivery
    97,   # Customer data platform
    98,   # Cart abandonment
    100,  # Shopify apps
    104,  # Ticket booking
    110,  # Form builders
    111,  # Fundraising & donations
}


# --- Helpers ----------------------------------------------------------------

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: Any) -> int:
    """Write JSON with stable formatting. Returns bytes written."""
    payload = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write(payload)
        fh.write("\n")
    return path.stat().st_size


def technology_files(src_tech_dir: Path) -> list[Path]:
    """Return per-letter technology JSON files in upstream layout (a.json..z.json + _.json)."""
    candidates = []
    for name in list(string.ascii_lowercase) + ["_"]:
        candidate = src_tech_dir / f"{name}.json"
        if candidate.exists():
            candidates.append(candidate)
    return candidates


def filter_signatures(
    techs: dict[str, Any],
    keep_cats: set[int],
) -> dict[str, Any]:
    """Return only entries whose `cats` intersects keep_cats."""
    kept: dict[str, Any] = {}
    for name, sig in techs.items():
        cats = sig.get("cats") or []
        if any(int(c) in keep_cats for c in cats):
            kept[name] = sig
    return kept


def filter_categories(
    categories: dict[str, Any],
    keep_cats: set[int],
) -> dict[str, Any]:
    return {
        cid: meta
        for cid, meta in categories.items()
        if int(cid) in keep_cats
    }


def filter_groups(
    groups: dict[str, Any],
    kept_categories: dict[str, Any],
) -> dict[str, Any]:
    """Keep only groups referenced by at least one retained category."""
    referenced: set[int] = set()
    for meta in kept_categories.values():
        for gid in meta.get("groups") or []:
            referenced.add(int(gid))
    return {gid: meta for gid, meta in groups.items() if int(gid) in referenced}


# --- Main -------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Filter enthec/webappanalyzer signatures down to local-biz "
                    "lead qualification categories.",
    )
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Path to a fresh clone of enthec/webappanalyzer.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Destination directory for filtered JSON pack.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute stats without writing output files.",
    )
    args = parser.parse_args()

    src_root: Path = args.source.resolve()
    out_root: Path = args.output.resolve()

    src_categories = src_root / "src" / "categories.json"
    src_groups = src_root / "src" / "groups.json"
    src_techs_dir = src_root / "src" / "technologies"

    if not src_categories.exists():
        print(f"ERROR: missing {src_categories}", file=sys.stderr)
        return 2
    if not src_techs_dir.is_dir():
        print(f"ERROR: missing {src_techs_dir}", file=sys.stderr)
        return 2

    # Load + filter categories
    categories = load_json(src_categories)
    kept_categories = filter_categories(categories, ALLOWLIST_CATEGORY_IDS)
    missing = ALLOWLIST_CATEGORY_IDS - {int(c) for c in kept_categories}
    if missing:
        print(
            f"WARN: allowlisted category IDs not present upstream: "
            f"{sorted(missing)}",
            file=sys.stderr,
        )

    # Optional groups.json
    groups: dict[str, Any] | None = None
    kept_groups: dict[str, Any] | None = None
    if src_groups.exists():
        groups = load_json(src_groups)
        kept_groups = filter_groups(groups, kept_categories)

    # Iterate technology files
    total_in = 0
    total_out = 0
    file_stats: list[tuple[str, int, int, int]] = []  # (name, in, out, bytes)

    for src_file in technology_files(src_techs_dir):
        techs = load_json(src_file)
        kept = filter_signatures(techs, ALLOWLIST_CATEGORY_IDS)
        in_count = len(techs)
        out_count = len(kept)
        total_in += in_count
        total_out += out_count

        out_path = out_root / src_file.name
        if not args.dry_run:
            # Always write so output mirrors upstream layout, even if empty —
            # downstream code can iterate predictably.
            bytes_written = write_json(out_path, kept)
        else:
            bytes_written = len(json.dumps(kept))
        file_stats.append((src_file.name, in_count, out_count, bytes_written))

    # Categories + groups
    cats_path = out_root / "categories.json"
    cats_bytes = 0
    if not args.dry_run:
        cats_bytes = write_json(cats_path, kept_categories)
    if kept_groups is not None and not args.dry_run:
        groups_path = out_root / "groups.json"
        write_json(groups_path, kept_groups)

    # Report
    print("=" * 60)
    print("Wappalyzer signature pack filter")
    print("=" * 60)
    print(f"Source:      {src_root}")
    print(f"Destination: {out_root}")
    print(f"Mode:        {'DRY-RUN' if args.dry_run else 'WRITE'}")
    print()
    print(f"Categories kept: {len(kept_categories)} / {len(categories)}")
    print(f"Categories ids:  {sorted(int(c) for c in kept_categories)}")
    if kept_groups is not None:
        print(f"Groups kept:     {len(kept_groups)}"
              f" / {len(groups) if groups else 0}")
    print()
    print(f"{'file':<10} {'in':>8} {'out':>8} {'bytes':>10}")
    print("-" * 40)
    for name, ic, oc, bw in file_stats:
        print(f"{name:<10} {ic:>8} {oc:>8} {bw:>10}")
    print("-" * 40)
    print(f"{'TOTAL':<10} {total_in:>8} {total_out:>8}")
    print()
    if total_in:
        retention = total_out / total_in * 100
        print(f"Retention: {retention:.1f}% ({total_out}/{total_in})")
    print()
    print(f"categories.json bytes: {cats_bytes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
