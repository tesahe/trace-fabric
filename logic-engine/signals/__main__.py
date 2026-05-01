"""CLI entry point for ad-hoc matcher testing.

Usage (run from the ``logic-engine/`` directory; the parent dir name has
a hyphen so it's not a valid Python package):

    python -m signals --html /path/to/file.html [--url https://...]
    python -m signals --html /path/to/file.html --json

Reads an HTML file off disk (and optionally a URL), synthesizes a minimal
RawLead-shaped dict, runs the matcher, and prints detections to stdout.

Use ``--json`` for machine-readable output, otherwise the default is a
short human summary.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from .matcher import Matcher
from .raw_lead_builder import build_raw_lead_from_html
from .regex_safe import backend


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m logic_engine.signals",
        description="Run the TraceFabric matcher engine against a local HTML file.",
    )
    p.add_argument(
        "--html",
        required=True,
        type=Path,
        help="Path to an HTML file to scan.",
    )
    p.add_argument(
        "--url",
        default="",
        help="Optional URL to attribute to the synthesized lead (used for url/ patterns).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit detections as a JSON array instead of the default human summary.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable INFO-level logging on stderr.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    if args.verbose:
        print(f"[regex backend] {backend()}", file=sys.stderr)

    if not args.html.exists():
        print(f"error: HTML file not found: {args.html}", file=sys.stderr)
        return 2

    lead = build_raw_lead_from_html(args.html, args.url)
    matcher = Matcher()
    detections = matcher.match(lead)

    if args.json:
        json.dump([asdict(d) for d in detections], sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        if not detections:
            print("(no detections)")
            return 0
        print(f"{len(detections)} detection(s):")
        for d in detections:
            version = f" v{d.version}" if d.version else ""
            print(
                f"  [{d.pack:9}] {d.name}{version}  "
                f"(conf={d.confidence}, source={d.source.value}, "
                f"field={d.matched_field})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
