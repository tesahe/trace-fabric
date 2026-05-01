"""Synthesize a RawLead-shape dict from a local HTML file + optional context.

Both the CLI (``python -m signals``) and the test suite share this code so
they exercise the matcher through the same input shape. In production the
Rust scraper produces this dict directly from its protobuf; this helper
just simulates that step for ad-hoc / fixture use.

Public API:

    build_raw_lead_from_html(
        html_path: Path,
        url: str = "",
        synthetic_headers: Optional[list[dict]] = None,
        robots_body: Optional[str] = None,
    ) -> dict

``synthetic_headers`` lets tests inject Set-Cookie / X-Powered-By / Server
lines so header / cookie / DNS-style patterns can be exercised against
fixtures that are otherwise pure HTML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def _empty_link() -> dict:
    return {"path": "", "http_status": 0, "exists": False, "content_type": "", "body": ""}


def build_raw_lead_from_html(
    html_path: Path,
    url: str = "",
    synthetic_headers: Optional[list[dict]] = None,
    robots_body: Optional[str] = None,
) -> dict:
    """Read an HTML file off disk and produce a RawLead dict.

    ``synthetic_headers`` is a list of ``{"key": ..., "value": ...}`` dicts
    matching the matcher's expected ``response_headers`` shape. They are
    injected verbatim — useful for testing header / cookie / DNS-header
    patterns without spinning up an HTTP layer.

    ``robots_body`` populates ``robots_txt.body`` with ``exists=True`` so
    robots-source patterns become testable too.
    """
    from bs4 import BeautifulSoup

    html = html_path.read_text(encoding="utf-8", errors="replace")

    script_srcs: list[dict] = []
    stylesheet_hrefs: list[dict] = []
    text_content = ""
    page_title = ""

    try:
        soup = BeautifulSoup(html, "lxml")
        for s in soup.find_all("script", src=True):
            script_srcs.append({"url": s.get("src", ""), "is_internal": False, "label": ""})
        for l in soup.find_all("link", rel=True):
            rels = l.get("rel") or []
            if "stylesheet" in rels and l.get("href"):
                stylesheet_hrefs.append(
                    {"url": l.get("href", ""), "is_internal": False, "label": ""}
                )
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()
        text_content = soup.get_text(separator=" ", strip=True)
    except Exception:
        pass

    response_headers: list[dict] = []
    if synthetic_headers:
        for h in synthetic_headers:
            if isinstance(h, dict) and "key" in h and "value" in h:
                response_headers.append({"key": str(h["key"]), "value": str(h["value"])})

    robots = _empty_link()
    if robots_body is not None:
        robots = {
            "path": "/robots.txt",
            "http_status": 200,
            "exists": True,
            "content_type": "text/plain",
            "body": robots_body,
        }

    return {
        "raw_html": html,
        "text_content": text_content,
        "page_title": page_title,
        "anchor_hrefs": [],
        "script_srcs": script_srcs,
        "stylesheet_hrefs": stylesheet_hrefs,
        "response_headers": response_headers,
        "robots_txt": robots,
        "sitemap_xml": _empty_link(),
        "manifest_url": "",
        "source_url": url,
        "final_url": url,
    }
