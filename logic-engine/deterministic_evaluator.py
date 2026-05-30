from datetime import datetime
from urllib.parse import urlparse


CURRENT_YEAR = datetime.now().year


def evaluate_lead(*, lead_data: dict, campaign_type: str, target_industry: str, heuristic_flags: dict) -> dict:
    page_title = lead_data.get("page_title", "") or ""
    anchor_hrefs = lead_data.get("anchor_hrefs", []) or []
    robots_txt = lead_data.get("robots_txt") or {}
    sitemap_xml = lead_data.get("sitemap_xml") or {}
    source_url = lead_data.get("source_url", "") or ""

    crawl_allowed = lead_data.get("crawl_allowed")
    crawl_disallowed_reason = lead_data.get("crawl_disallowed_reason", "") or ""
    is_no_website_opportunity = bool(lead_data.get("is_no_website_opportunity", False))
    discovery_source = lead_data.get("discovery_source", "") or ""

    # Read Rust-extracted signals directly — no HTML re-parsing
    has_viewport = bool(lead_data.get("has_viewport", False))
    has_form = bool(lead_data.get("has_form", False))
    has_tel = bool(lead_data.get("has_tel_link", False))
    has_mailto = bool(lead_data.get("has_mailto_link", False))
    has_contact_page = bool(lead_data.get("has_contact_page", False))
    has_booking = bool(lead_data.get("has_booking_signal", False))
    has_cta = bool(lead_data.get("has_cta_signal", False))
    has_hours = bool(lead_data.get("has_hours_signal", False))
    has_reviews = bool(lead_data.get("has_reviews_signal", False))
    is_parked = bool(lead_data.get("is_parked_domain", False))
    copyright_year = int(lead_data.get("copyright_year", 0) or 0)

    # Privacy still requires anchor scan — no dedicated proto signal
    has_privacy = any(
        "privacy" in f"{x.get('label', '')} {x.get('url', '')}".lower()
        for x in anchor_hrefs
    )

    has_phone_signal = bool((lead_data.get("phone_number") or "").strip()) or has_tel
    has_address_signal = bool((lead_data.get("address") or "").strip())
    source_host = urlparse(source_url).netloc.lower()
    directory_like = any(token in source_host for token in ["yelp.", "facebook.", "instagram.", "tripadvisor."])

    if is_no_website_opportunity:
        return {
            "pipeline_status": "excluded_no_website_opportunity",
            "score": 0.0,
            "is_qualified_lead": False,
            "has_booking_widget": False,
            "is_mobile_optimized": False,
            "has_clear_contact_info": False,
            "overall_digital_health": "Discovery-only opportunity without a canonical website. Excluded from website evaluator.",
            "rejection_reason": "no_website_opportunity",
            "identified_service_gaps": [],
            "missing_critical_features": [],
            "heuristic_flags": {
                **heuristic_flags,
                "campaign_type": campaign_type,
                "target_industry": target_industry,
                "is_real_business_deterministic": False,
            },
            "deterministic_evidence": {
                "source_host": source_host,
                "discovery_source": discovery_source,
                "crawl_allowed": crawl_allowed,
                "crawl_disallowed_reason": crawl_disallowed_reason,
                "is_no_website_opportunity": True,
            },
        }

    if crawl_allowed is False:
        return {
            "pipeline_status": "excluded_crawl_disallowed",
            "score": 0.0,
            "is_qualified_lead": False,
            "has_booking_widget": False,
            "is_mobile_optimized": False,
            "has_clear_contact_info": False,
            "overall_digital_health": "Website excluded from deterministic evaluation because crawl was not allowed.",
            "rejection_reason": crawl_disallowed_reason or "crawl_disallowed",
            "identified_service_gaps": [],
            "missing_critical_features": [],
            "heuristic_flags": {
                **heuristic_flags,
                "campaign_type": campaign_type,
                "target_industry": target_industry,
                "is_real_business_deterministic": False,
            },
            "deterministic_evidence": {
                "source_host": source_host,
                "discovery_source": discovery_source,
                "crawl_allowed": False,
                "crawl_disallowed_reason": crawl_disallowed_reason,
                "is_no_website_opportunity": False,
            },
        }

    if is_parked:
        return {
            "pipeline_status": "rejected_parked_domain",
            "score": 0.0,
            "is_qualified_lead": False,
            "has_booking_widget": False,
            "is_mobile_optimized": False,
            "has_clear_contact_info": False,
            "overall_digital_health": "Domain appears to be parked or for sale.",
            "rejection_reason": "parked_domain",
            "identified_service_gaps": [],
            "missing_critical_features": [],
            "heuristic_flags": {
                **heuristic_flags,
                "campaign_type": campaign_type,
                "target_industry": target_industry,
                "is_real_business_deterministic": False,
            },
            "deterministic_evidence": {
                "source_host": source_host,
                "discovery_source": discovery_source,
                "crawl_allowed": crawl_allowed,
                "is_parked_domain": True,
            },
        }

    outdated = []
    if not has_viewport:
        outdated.append("missing_mobile_viewport")
    if not page_title.strip():
        outdated.append("missing_page_title")
    if copyright_year > 0 and copyright_year <= CURRENT_YEAR - 3:
        outdated.append(f"stale_copyright_{copyright_year}")

    missing = []
    if campaign_type == "website_modernization":
        if not has_viewport:
            missing.append("mobile_responsive_design")
        if not has_form:
            missing.append("contact_form")
        if not has_cta:
            missing.append("clear_primary_cta")
        if not has_privacy:
            missing.append("privacy_policy")
    elif campaign_type == "voice_ai_agent":
        if not has_phone_signal:
            missing.append("phone_conversion_flow")
        if not has_booking:
            missing.append("appointment_capture")
        if not has_hours:
            missing.append("published_hours")
    elif campaign_type == "smma":
        social_count = sum(
            1
            for x in anchor_hrefs
            if any(
                domain in x.get("url", "")
                for domain in [
                    "facebook.com",
                    "instagram.com",
                    "linkedin.com",
                    "youtube.com",
                    "pinterest.com",
                    "tiktok.com",
                ]
            )
        )
        if social_count == 0:
            missing.append("social_presence_links")
        if not has_reviews:
            missing.append("social_proof")
        if not has_cta:
            missing.append("campaign_landing_cta")

    is_real_business = not directory_like and (has_phone_signal or has_address_signal or has_contact_page)
    is_qualified_lead = is_real_business and (len(missing) > 0 or len(outdated) >= 2)

    return {
        "pipeline_status": "qualified_deterministic" if is_qualified_lead else "rejected_deterministic",
        "score": round(min(1.0, 0.35 + (0.12 * len(missing)) + (0.10 * len(outdated))), 4),
        "is_qualified_lead": is_qualified_lead,
        "has_booking_widget": has_booking,
        "is_mobile_optimized": has_viewport,
        "has_clear_contact_info": has_phone_signal or has_mailto or has_contact_page,
        "overall_digital_health": (
            "Real local business with actionable deterministic gaps."
            if is_qualified_lead
            else "Either not enough business evidence or not enough campaign-relevant gaps."
        ),
        "rejection_reason": None if is_qualified_lead else "deterministic_gate_reject",
        "identified_service_gaps": outdated,
        "missing_critical_features": missing,
        "heuristic_flags": {
            **heuristic_flags,
            "campaign_type": campaign_type,
            "target_industry": target_industry,
            "is_real_business_deterministic": is_real_business,
        },
        "deterministic_evidence": {
            "source_host": source_host,
            "discovery_source": discovery_source,
            "crawl_allowed": crawl_allowed,
            "crawl_disallowed_reason": crawl_disallowed_reason,
            "is_no_website_opportunity": False,
            "robots_txt_accessible": bool(robots_txt.get("exists")),
            "sitemap_xml_accessible": bool(sitemap_xml.get("exists")),
            "has_contact_page": has_contact_page,
            "has_privacy_policy": has_privacy,
            "has_contact_form": has_form,
            "has_cta": has_cta,
            "has_booking_widget": has_booking,
            "has_hours_signal": has_hours,
            "has_reviews_signal": has_reviews,
        },
    }
