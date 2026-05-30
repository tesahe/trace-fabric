from types import SimpleNamespace

from gatekeeper import HeuristicScanner, get_ruleset_for_campaign


def make_gatekeeper_lead(
    *,
    word_count: int = 200,
    is_parked_domain: bool = False,
    has_viewport: bool = True,
    script_srcs: list | None = None,
    stylesheet_hrefs: list | None = None,
):
    def make_url(url: str):
        return SimpleNamespace(url=url, is_internal=False, label="")

    return SimpleNamespace(
        word_count=word_count,
        is_parked_domain=is_parked_domain,
        has_viewport=has_viewport,
        script_srcs=[make_url(u) for u in (script_srcs or [])],
        stylesheet_hrefs=[make_url(u) for u in (stylesheet_hrefs or [])],
    )


def test_gatekeeper_rejects_low_word_count():
    lead = make_gatekeeper_lead(word_count=3)

    scanner = HeuristicScanner(lead, get_ruleset_for_campaign("website_modernization"))
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_low_word_count"
    assert flags["word_count"] < scanner.MIN_WORD_COUNT


def test_gatekeeper_rejects_parked_domain():
    lead = make_gatekeeper_lead(is_parked_domain=True)

    scanner = HeuristicScanner(lead, get_ruleset_for_campaign("website_modernization"))
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_parked_domain"
    assert flags["parked_domain"] is True


def test_gatekeeper_rejects_campaign_mismatch_for_shopify():
    lead = make_gatekeeper_lead(
        script_srcs=["https://cdn.shopify.com/s/files/1/theme.js"],
    )

    scanner = HeuristicScanner(lead, get_ruleset_for_campaign("website_modernization"))
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_campaign_mismatch"
    assert "shopify" in flags["rejection_signature"].lower()


def test_gatekeeper_passes_valid_business_html():
    lead = make_gatekeeper_lead(
        word_count=200,
        is_parked_domain=False,
        has_viewport=True,
    )

    scanner = HeuristicScanner(lead, get_ruleset_for_campaign("website_modernization"))
    passed, flags, status = scanner.run_all_checks()

    assert passed is True
    assert status == "pending_tier_1"
    assert flags["campaign"] == "website_modernization"
