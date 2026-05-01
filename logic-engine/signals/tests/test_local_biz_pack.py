"""Coverage for the Sprint 2 curated local-business signature pack."""

from __future__ import annotations

import pytest

from signals.matcher import Matcher


# ---- Synthetic fixtures ----------------------------------------------------


def _lead_with_html(html: str, url: str = "") -> dict:
    return {
        "raw_html": html,
        "text_content": "",
        "page_title": "",
        "anchor_hrefs": [],
        "script_srcs": [],
        "stylesheet_hrefs": [],
        "response_headers": [],
        "robots_txt": {"path": "", "http_status": 0, "exists": False, "content_type": "", "body": ""},
        "sitemap_xml": {"path": "", "http_status": 0, "exists": False, "content_type": "", "body": ""},
        "manifest_url": "",
        "source_url": url,
        "final_url": url,
    }


def _lead_with_script(script_url: str, url: str = "") -> dict:
    """Build a lead whose only script_srcs entry is the test URL."""
    lead = _lead_with_html(f'<html><head><script src="{script_url}"></script></head><body></body></html>', url=url)
    lead["script_srcs"] = [{"url": script_url, "is_internal": False, "label": ""}]
    return lead


SIG_FIXTURES = [
    # (signature name, sample script_src URL we expect to fire it)
    ("Booksy", "https://booksy.com/widget/code.js"),
    ("Mindbody", "https://widgets.mindbodyonline.com/javascripts/healcode.js"),
    ("Vagaro", "https://www.vagaro.com/12345/widget.js"),
    ("Schedulicity", "https://www.schedulicity.com/widgets/embed.js"),
    ("Setmore", "https://my.setmore.com/webapp/setmore.js"),
    ("10to8", "https://10to8static-eu.s3.amazonaws.com/widget.js"),
    ("Square Appointments", "https://squareup.com/appointments/buyer/widget/loader.js"),
    ("Acuity Scheduling", "https://embed.acuityscheduling.com/js/embed.js"),
    ("Toast Online Ordering", "https://cdn.toasttab.com/widgets/order.js"),
    ("ChowNow", "https://cdn.chownow.com/widget.js"),
    ("Square for Restaurants", "https://squareup.com/online-ordering/widget.js"),
    ("Resy", "https://widgets.resy.com/button.js"),
    ("OpenTable", "https://www.opentable.com/widget/reservation/loader?rid=1234"),
    ("BentoBox", "https://cdn.getbento.com/main.js"),
    ("Boulevard", "https://cdn.boulevard.io/widget.js"),
    ("Phorest", "https://cdn.phorest.com/widget.js"),
    ("Rosy Salon Software", "https://book.rosysalonsoftware.com/widget.js"),
    ("Mangomint", "https://cdn.mangomint.com/widget.js"),
    ("ServiceTitan", "https://leadform.cdn.servicetitan.com/loader.js"),
    ("Housecall Pro", "https://book.housecallpro.com/widget.js"),
    ("Jobber", "https://cdn.getjobber.com/work-request.js"),
    ("FieldEdge", "https://app.fieldedge.com/widget.js"),
    ("Workiz", "https://cdn.workiz.com/booking.js"),
    ("BirdEye", "https://cdn.birdeye.com/reviews.js"),
    ("Podium", "https://connect.podium.com/widget.js"),
    ("NiceJob", "https://widget.nicejobcdn.com/embed.js"),
    ("Trustpilot", "https://widget.trustpilot.com/bootstrap/v5/tp.widget.bootstrap.min.js"),
]


@pytest.mark.parametrize("expected_name,script_url", SIG_FIXTURES)
def test_local_biz_sig_fires_on_script_src(matcher: Matcher, expected_name: str, script_url: str):
    """Each curated sig fires when its canonical embed/loader URL is present."""
    lead = _lead_with_script(script_url)
    detections = matcher.match(lead)
    names = {(d.name, d.pack) for d in detections}
    assert (expected_name, "local_biz") in names, (
        f"{expected_name} should fire on script_src={script_url}; "
        f"got: {sorted(n for n, p in names if p == 'local_biz')}"
    )


def test_unrelated_script_does_not_trip_local_biz_sigs(matcher: Matcher):
    """A non-vendor script URL should fire ZERO local_biz detections."""
    lead = _lead_with_script("https://example.com/normal.js")
    detections = matcher.match(lead)
    local_biz_hits = [d.name for d in detections if d.pack == "local_biz"]
    assert local_biz_hits == [], f"unexpected local_biz hits: {local_biz_hits}"


def test_pack_loaded_count(matcher: Matcher):
    """Sanity: at least 25 local_biz sigs are wired up (we shipped 27)."""
    local_biz = [t for t in matcher._techs_list if t.pack == "local_biz"]
    assert len(local_biz) >= 25, f"only {len(local_biz)} local_biz techs loaded"
