import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gatekeeper import HeuristicScanner, WEBSITE_MODERNIZATION_CAMPAIGN

# TEST A: Should FAIL — low word count (parked/blank page)
html_junk = "<html><body><p>Hello world.</p></body></html>"
scanner = HeuristicScanner(html_junk, WEBSITE_MODERNIZATION_CAMPAIGN)
passed, flags, status = scanner.run_all_checks()
print(f"TEST A: passed={passed}, status={status}")
# Expected: passed=False, status=rejected_heuristic_low_word_count

# TEST B: Should FAIL — Shopify CMS signature (wrong campaign fit)
html_shopify = "<html><body>" + ("word " * 200) + '<script src="cdn.shopify.com/s/files/1/theme.js"></script></body></html>'
scanner = HeuristicScanner(html_shopify, WEBSITE_MODERNIZATION_CAMPAIGN)
passed, flags, status = scanner.run_all_checks()
print(f"TEST B: passed={passed}, status={status}")
# Expected: passed=False, status=rejected_heuristic_campaign_mismatch

# TEST C: Should PASS — a basic local business site
html_valid = "<html><head><meta name='viewport' content='width=device-width'></head><body>" + ("We are a local plumbing company serving your area. Call us today for fast service. " * 10) + "</body></html>"
scanner = HeuristicScanner(html_valid, WEBSITE_MODERNIZATION_CAMPAIGN)
passed, flags, status = scanner.run_all_checks()
print(f"TEST C: passed={passed}, status={status}, flags={flags}")
# Expected: passed=True, status=pending_tier_1
