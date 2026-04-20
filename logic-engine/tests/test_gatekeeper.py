from gatekeeper import HeuristicScanner, get_ruleset_for_campaign


def test_gatekeeper_rejects_low_word_count():
    html = "<html><body><p>Hello world.</p></body></html>"

    scanner = HeuristicScanner(
        html,
        get_ruleset_for_campaign("website_modernization"),
    )
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_low_word_count"
    assert flags["word_count"] < scanner.MIN_WORD_COUNT


def test_gatekeeper_rejects_parked_domain():
    html = "<html><body>" + ("this domain is for sale " * 30) + "</body></html>"

    scanner = HeuristicScanner(
        html,
        get_ruleset_for_campaign("website_modernization"),
    )
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_parked_domain"
    assert flags["parked_domain"] is True


def test_gatekeeper_rejects_campaign_mismatch_for_shopify():
    html = (
        "<html><body>"
        + ("word " * 200)
        + '<script src="https://cdn.shopify.com/s/files/1/theme.js"></script>'
        + "</body></html>"
    )

    scanner = HeuristicScanner(
        html,
        get_ruleset_for_campaign("website_modernization"),
    )
    passed, flags, status = scanner.run_all_checks()

    assert passed is False
    assert status == "rejected_heuristic_campaign_mismatch"
    assert "shopify" in flags["rejection_signature"].lower()


def test_gatekeeper_passes_valid_business_html():
    html = (
        "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        "<body>"
        + ("We are a local HVAC company serving Portland with installation, repair, maintenance, and emergency service. " * 20)
        + "</body></html>"
    )

    scanner = HeuristicScanner(
        html,
        get_ruleset_for_campaign("website_modernization"),
    )
    passed, flags, status = scanner.run_all_checks()

    assert passed is True
    assert status == "pending_tier_1"
    assert flags["campaign"] == "website_modernization"
