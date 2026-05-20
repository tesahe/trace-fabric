use regex::Regex;
use scraper::{Html, Selector};
use url::Url;
use serde_json;

use crate::schema;

use std::collections::HashSet;

pub fn parse_selector(selector: &str) -> Selector {
    Selector::parse(selector).expect("valid CSS selector")
}


// Relevant page signals for:
    // 1. business compatibility signals
    // 2. real website signals
pub struct PageSignals {
    pub word_count: i32,
    pub has_viewport: bool,
    pub has_form: bool,
    pub has_tel_link: bool,
    pub has_mailto_link: bool,
    pub is_parked_domain: bool,
    pub outbound_domain_count: i32,
    pub schema_org_business_type: String,
    pub email_address: String,
    pub meta_description: String,
    pub social_linkedin: String,
    pub social_facebook: String,
    pub social_instagram: String,
    pub copyright_year: i32,
    pub has_booking_signal: bool,
    pub has_cta_signal: bool,
    pub has_hours_signal: bool,
    pub has_reviews_signal: bool,
    pub has_contact_page: bool,
}

// extract page signals from scraped url
pub fn extract_page_signals(
    document: &Html,
    text_content: &str,
    anchor_hrefs: &[schema::UrlArtifact], 
) -> PageSignals {

    
    let lower = text_content.to_ascii_lowercase();

    let mut has_tel_link = false;
    let mut has_mailto_link = false;
    let mut email_address = String::new();

    // boolean - .next() through iterator, bool viewport and form
    let has_viewport = document
        .select(&parse_selector(r#"meta[name="viewport"]"#))
        .next()
        .is_some();

    let has_form = document
        .select(&parse_selector("form"))
        .next()
        .is_some();

    
    for el in document.select(&parse_selector("a[href]")) {
        let Some(href) = el.value().attr("href") else {
            continue;
        };
        let lower_href = href.to_ascii_lowercase();

        if lower_href.starts_with("tel:") { // check - is it always tel consistently 
            has_tel_link = true;
        }

        if lower_href.starts_with("mailto:") {
            has_mailto_link = true;
            if email_address.is_empty() {
                let extracted = href["mailto:".len()..]
                    .split('?')
                    .next()
                    .unwrap_or("")
                    .to_string();
                if extracted.contains("@") {
                    email_address = extracted;
                }
            }
        }

    }
    if email_address.is_empty() {
        if let Ok(re) = Regex::new(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}") {
            if let Some(m) = re.find(text_content) {
                email_address = m.as_str().to_string();
            }
        }
    }

    // rudimentary parked domain check 
    let is_parked_domain = [
        "this domain is for sale",
        "buy this domain",
        "parked free",
        "under construction",
        "coming soon",
    ]
    .iter()
    .any( |phrase| lower.contains(phrase));

    // hashSet only stores unique values
    let outbound_domains: HashSet<String> = anchor_hrefs
        .iter()
        .filter( |a| !a.is_internal)
        .filter_map(|a| {
            Url::parse(&a.url)
                .ok()?
                .host_str()
                .map( |h| h.to_ascii_lowercase())
        })
        .collect();
    let outbound_domain_count = outbound_domains.len().min(i32::MAX as usize) as i32;

    let schema_org_business_type = extract_schema_org_business_type(document);

    let meta_description = document
        .select(&parse_selector(r#"meta[name="description"]"#))
        .next()
        .and_then( |el| el.value().attr("content"))
        .map(normalize_whitespace)
        .unwrap_or_default();
    
    let social_linkedin = extract_social_link(anchor_hrefs, "linkedin.com");
    let social_facebook = extract_social_link(anchor_hrefs, "facebook.com");
    let social_instagram = extract_social_link(anchor_hrefs, "instagram.com");

    let copyright_year = Regex::new(r"(?i)(?:copyright|©)\s*(20\d{2})")
        .ok()
        .and_then( |re| re.captures(text_content))
        .and_then( |caps| caps.get(1))
        .and_then( |m| m.as_str().parse::<i32>().ok())
        .unwrap_or(0);


    // VERY basic lists to be expanded
    // ADD MORE KEYWORDS AND PHRASES BASED ON DATA


    let has_booking_signal = ["book now", "schedule", "reserve", "appointment", "calendly"]
        .iter()
        .any( |t| lower.contains(t));


    let has_cta_signal = ["free estimate", "request quote", "contact us", "call now"]
        .iter()
        .any(|t| lower.contains(t));

    let has_hours_signal = lower.contains("hours") || lower.contains("open today");

    let has_reviews_signal = ["testimonial", "testimonials", "review", "reviews"]
        .iter()
        .any(|t| lower.contains(t));

    let has_contact_page = anchor_hrefs.iter().any(|a| {
        let combined = format!(
            "{} {}",
            a.url.to_ascii_lowercase(),
            a.label.to_ascii_lowercase()
        );
        combined.contains("contact")
    });

    let word_count = text_content
        .split_whitespace()
        .count()
        .min(i32::MAX as usize) as i32;



    PageSignals {
        word_count,
        has_viewport,
        has_form,
        has_tel_link,
        has_mailto_link,
        is_parked_domain,
        outbound_domain_count,
        schema_org_business_type,
        email_address,
        meta_description,
        social_linkedin,
        social_facebook,
        social_instagram,
        copyright_year,
        has_booking_signal,
        has_cta_signal,
        has_hours_signal,
        has_reviews_signal,
        has_contact_page,
    }
}

fn extract_schema_org_business_type(document: &Html) -> String {
    let selector = parse_selector(r#"script[type="application/ld+json"]"#);
    for el in document.select(&selector) {
        let text = el.text().collect::<String>();
        let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) else {
            continue;
        };
        let items: Vec<&serde_json::Value> = match value.as_array() {
            Some(arr) => arr.iter().collect(),
            None => vec![&value],
        };
        for item in items {
            if let Some(t) = item.get("@type").and_then(|v| v.as_str()) {
                return t.to_string();
            }
        }
    }
    String::new()

}

fn extract_social_link(anchor_hrefs: &[schema::UrlArtifact], domain: &str) -> String {
    anchor_hrefs
        .iter()
        .find(|a| a.url.contains(domain))
        .map(|a| a.url.clone())
        .unwrap_or_default()
}


pub fn extract_page_title(document: &Html) -> String {
    let selector = parse_selector("title");
    document
        .select(&selector)
        .next()
        .map(|element| {
            element
                .text()
                .collect::<Vec<_>>()
                .join(" ")
                .trim()
                .to_string()
        })
        .unwrap_or_default()
}

pub fn extract_text_content(document: &Html) -> String {
    let exclude_selector = parse_selector("script, style, noscript");
    let excluded_ids: HashSet<_> = document
        .select(&exclude_selector)
        .map(|el| el.id())
        .collect();

    document
        .select(&parse_selector("body"))
        .next()
        .map(|body| {
            body.descendants()
                .filter_map(|node| {
                    let text = node.value().as_text()?;
                    if node
                        .ancestors()
                        .any(|ancestor| excluded_ids.contains(&ancestor.id()))
                    {
                        return None;
                    }
                    let trimmed = text.trim();
                    if trimmed.is_empty() {
                        None
                    } else {
                        Some(trimmed.to_string())
                    }
                })
                .collect::<Vec<_>>()
                .join(" ")
        })
        .unwrap_or_default()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}


pub fn extract_phone_number(document: &Html, text_content: &str) -> String {
    let anchor_selector = parse_selector("a[href]");
    for el in document.select(&anchor_selector) {
        if let Some(href) = el.value().attr("href") {
            if href.to_ascii_lowercase().starts_with("tel:") {
                let cleaned = clean_phone_candidate(href);
                if !cleaned.is_empty() {
                    return cleaned;
                }
            }
        }
    }

    let phone_re = Regex::new(
        r"(?x)
        (?:\+?1[\s\-.]?)?
        (?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}
        ",
    )
    .expect("valid phone regex");

    phone_re
        .find(text_content)
        .map(|m| clean_phone_candidate(m.as_str()))
        .unwrap_or_default()
}

pub fn extract_company_name(document: &Html, page_title: &str) -> String {
    let og_site_name = parse_selector(r#"meta[property="og:site_name"]"#);
    if let Some(el) = document.select(&og_site_name).next() {
        if let Some(content) = el.value().attr("content") {
            let value = normalize_whitespace(content);
            if looks_like_company_name_candidate(&value) {
                return value;
            }
        }
    }

    let app_name = parse_selector(r#"meta[name="application-name"]"#);
    if let Some(el) = document.select(&app_name).next() {
        if let Some(content) = el.value().attr("content") {
            let value = normalize_whitespace(content);
            if looks_like_company_name_candidate(&value) {
                return value;
            }
        }
    }

    let img_selector = parse_selector("img[alt]");
    for el in document.select(&img_selector) {
        if let Some(alt) = el.value().attr("alt") {
            let value = normalize_whitespace(alt);
            let lower = value.to_ascii_lowercase();

            if looks_like_company_name_candidate(&value) && !lower.contains("logo") {
                return value;
            }
        }
    }

    let h1_selector = parse_selector("h1");
    if let Some(el) = document.select(&h1_selector).next() {
        let value = normalize_whitespace(&el.text().collect::<Vec<_>>().join(" "));
        if looks_like_company_name_candidate(&value) {
            return value;
        }
    }

    let normalized_title = normalize_whitespace(page_title);
    if normalized_title.is_empty() {
        return String::new();
    }

    let title_head = normalized_title
        .split(['|', '-', '—', ':'])
        .next()
        .map(normalize_whitespace)
        .unwrap_or_default();

    if looks_like_company_name_candidate(&title_head) {
        title_head
    } else {
        String::new()
    }
}

pub fn normalize_whitespace(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .trim()
        .to_string()
}

pub fn looks_like_company_name_candidate(value: &str) -> bool {
    let normalized = normalize_whitespace(value);
    let lower = normalized.to_ascii_lowercase();

    if normalized.len() < 3 || normalized.len() > 80 {
        return false;
    }

    if looks_like_generic_title(&normalized) {
        return false;
    }

    if [
        "call us",
        "contact us",
        "request service",
        "book now",
        "learn more",
        "read more",
        "click here",
        "home",
        "welcome",
    ]
    .iter()
    .any(|token| lower == *token || lower.contains(token))
    {
        return false;
    }

    if normalized.matches(' ').count() > 8 {
        return false;
    }

    if normalized.chars().filter(|c| c.is_ascii_digit()).count() >= 4 {
        return false;
    }

    true
}

pub fn clean_phone_candidate(raw_value: &str) -> String {
    let normalized = raw_value
        .trim()
        .trim_start_matches("tel:")
        .split(';')
        .next()
        .unwrap_or("")
        .split('?')
        .next()
        .unwrap_or("")
        .trim();

    let digits_only = normalized
        .chars()
        .filter(|c| c.is_ascii_digit())
        .collect::<String>();

    if digits_only.len() == 11 && digits_only.starts_with('1') {
        return digits_only[1..].to_string();
    }

    if digits_only.len() == 10 {
        return digits_only;
    }

    String::new()
}

pub fn looks_like_generic_title(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();
    [
        "home",
        "welcome",
        "index",
        "untitled",
        "untitled document",
        "new page",
        "page not found",
        "404",
        "403",
        "error",
    ]

    .iter()
    .any(|token| lower == *token || lower.starts_with(&format!("{token} |")))
}

pub fn looks_like_postal_address(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();

    let has_street_number = Regex::new(r"\b\d{1,6}\b")
        .expect("valid street number regex")
        .is_match(value);

    let has_street_type = Regex::new(
        r"(?i)\b(st|street|ave|avenue|rd|road|blvd|boulevard|dr|drive|ln|lane|ct|court|way|pkwy|parkway|pl|place)\b",
    )
    .expect("valid street type regex")
    .is_match(value);

    let has_city_state_zip = Regex::new(r"(?i)\b[a-z .'-]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?\b")
        .expect("valid city/state/zip regex")
        .is_match(value);

    let contains_bad_tokens = [
        "copyright",
        "all rights reserved",
        "call us",
        "request service",
        "contact us",
        "license",
    ]
    .iter()
    .any(|token| lower.contains(token));


    ((has_street_number && has_street_type) || has_city_state_zip) && !contains_bad_tokens
}

pub fn extract_address(document: &Html) -> String {
    let address_selector = parse_selector("address");
    for el in document.select(&address_selector) {
        let value = normalize_whitespace(&el.text().collect::<Vec<_>>().join(" "));
        if !value.is_empty() && looks_like_postal_address(&value) {
            return value;
        }
    }

    let fallback_selectors = [
        "footer",
        ".footer",
        "#footer",
        ".contact",
        "#contact",
        ".contact-us",
        ".location",
        ".locations",
        ".address",
        "[itemprop='address']",
    ];

    for selector in fallback_selectors {
        let parsed_selector = parse_selector(selector);

        for el in document.select(&parsed_selector) {
            let value = normalize_whitespace(&el.text().collect::<Vec<_>>().join(" "));
            if !value.is_empty() && looks_like_postal_address(&value) {
                return value;
            }
        }
    }

    String::new()
}

pub fn infer_category_from_text(text_content: &str) -> String {
    let lower = text_content.to_ascii_lowercase();

    let keyword_groups = [
        (
            "hvac",
            &["hvac", "heating", "cooling", "air conditioning", "furnace"][..],
        ),
        (
            "plumbing",
            &["plumb", "plumbing", "water heater", "drain cleaning"][..],
        ),
        (
            "dentist",
            &["dentist", "dental", "teeth cleaning", "orthodontic"][..],
        ),
        (
            "auto_detailing",
            &[
                "auto detailing",
                "ceramic coating",
                "paint correction",
                "car detail",
            ][..],
        ),
        (
            "roofing",
            &["roofing", "roofer", "roof repair", "roof replacement"][..],
        ),
        (
            "landscaping",
            &["landscaping", "lawn care", "hardscape", "irrigation"][..],
        ),
    ];

    for (category, keywords) in keyword_groups {
        if keywords.iter().any(|keyword| lower.contains(keyword)) {
            return category.to_string();
        }
    }

    String::new()
}

pub fn build_website_provenance_json(
    company_name: &str,
    company_name_source_url: &str,
    category: &str,
    category_source_url: &str,
    phone_number: &str,
    phone_number_source_url: &str,
    address: &str,
    address_source_url: &str,
) -> String {
    serde_json::json!({
        "company_name": if company_name.is_empty() {
            serde_json::Value::Null
        } else {
            serde_json::json!({
                "source_class": "website_extracted",
                "confidence": "medium",
                "source_url": company_name_source_url
            })
        },
        "category": if category.is_empty() {
            serde_json::Value::Null
        } else {
            serde_json::json!({
                "source_class": "derived_internal",
                "derived_from": "website_text",
                "confidence": "medium",
                "source_url": category_source_url
            })
        },
        "phone_number": if phone_number.is_empty() {
            serde_json::Value::Null
        } else {
            serde_json::json!({
                "source_class": "website_extracted",
                "confidence": "medium",
                "source_url": phone_number_source_url
            })
        },
        "address": if address.is_empty() {
            serde_json::Value::Null
        } else {
            serde_json::json!({
                "source_class": "website_extracted",
                "confidence": "high",
                "source_url": address_source_url
            })
        }
    })
    .to_string()
}

pub fn resolve_url(base_url: &str, raw_url: &str) -> Option<String> {
    if raw_url.is_empty() {
        return None;
    }

    let base = Url::parse(base_url).ok()?;
    base.join(raw_url).ok().map(|u| u.to_string())
}

pub fn is_internal_url(base_url: &str, candidate_url: &str) -> bool {
    let base = Url::parse(base_url).ok();
    let candidate = Url::parse(candidate_url).ok();

    match (base, candidate) {
        (Some(base), Some(candidate)) => base.domain() == candidate.domain(),
        _ => false,
    }
}

pub fn extract_anchor_hrefs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
    let selector = parse_selector("a[href]");

    document
        .select(&selector)
        .filter_map(|el| {
            let raw_href = el.value().attr("href")?;
            let resolved = resolve_url(base_url, raw_href)?;
            let label = el.text().collect::<Vec<_>>().join(" ").trim().to_string();

            Some(schema::UrlArtifact {
                url: resolved.clone(),
                is_internal: is_internal_url(base_url, &resolved),
                label,
            })
        })
        .collect()
}

pub fn extract_script_srcs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
    let selector = parse_selector("script[src]");

    document
        .select(&selector)
        .filter_map(|el| {
            let raw_src = el.value().attr("src")?;
            let resolved = resolve_url(base_url, raw_src)?;

            Some(schema::UrlArtifact {
                url: resolved.clone(),
                is_internal: is_internal_url(base_url, &resolved),
                label: String::new(),
            })
        })
        .collect()
}

pub fn extract_stylesheet_hrefs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
    let selector = parse_selector(r#"link[rel="stylesheet"][href]"#);

    document
        .select(&selector)
        .filter_map(|el| {
            let raw_href = el.value().attr("href")?;
            let resolved = resolve_url(base_url, raw_href)?;

            Some(schema::UrlArtifact {
                url: resolved.clone(),
                is_internal: is_internal_url(base_url, &resolved),
                label: String::new(),
            })
        })
        .collect()
}

pub fn extract_manifest_url(document: &Html, base_url: &str) -> String {
    let selector = parse_selector(r#"link[rel="manifest"][href]"#);

    document
        .select(&selector)
        .next()
        .and_then(|el| el.value().attr("href"))
        .and_then(|href| resolve_url(base_url, href))
        .unwrap_or_default()
}

fn normalize_link_target(raw_url: &str) -> Option<String> {
    let mut parsed = Url::parse(raw_url).ok()?;

    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return None;
    }

    parsed.set_fragment(None);
    parsed.set_query(None);

    Some(parsed.to_string().trim_end_matches('/').to_string())
}

fn internal_link_priority_score(path: &str, label: &str) -> i32 {
    let joined = format!("{path} {label}");

    if [
        "privacy", "terms", "policy", "login", "sign in", "signin", "account", "cart", "checkout",
        "careers", "jobs", "blog", "news", "article", "tag/", "/feed",
    ]
    .iter()
    .any(|token| joined.contains(token))
    {
        return -1;
    }

    let mut score = 0;

    if joined.contains("contact") {
        score += 100;
    }
    if joined.contains("about") || joined.contains("our story") || joined.contains("company") {
        score += 80;
    }
    if joined.contains("service") || joined.contains("repair") || joined.contains("install") {
        score += 70;
    }
    if joined.contains("location") || joined.contains("areas") || joined.contains("service-area") {
        score += 60;
    }
    if joined.contains("team") || joined.contains("staff") {
        score += 40;
    }
    if joined.contains("faq") || joined.contains("financing") {
        score += 20;
    }

    score
}

pub fn select_priority_internal_links(
    base_url: &str,
    links: &[schema::UrlArtifact],
    max_links: usize,
) -> Vec<String> {
    let base = Url::parse(base_url).ok();
    let mut seen = HashSet::new();
    let mut scored_links: Vec<(i32, String)> = Vec::new();

    for link in links {
        if !link.is_internal {
            continue;
        }

        let Some(normalized_url) = normalize_link_target(&link.url) else {
            continue;
        };

        let Ok(parsed) = Url::parse(&normalized_url) else {
            continue;
        };

        let path = parsed.path().trim().to_ascii_lowercase();
        let label = normalize_whitespace(&link.label).to_ascii_lowercase();

        if path.is_empty() || path == "/" {
            continue;
        }

        if let Some(base_url) = &base {
            if parsed.domain() != base_url.domain() {
                continue;
            }

            let base_path = base_url.path().trim_end_matches('/');
            let candidate_path = parsed.path().trim_end_matches('/');

            if candidate_path == base_path {
                continue;
            }
        }

        let score = internal_link_priority_score(&path, &label);
        if score <= 0 {
            continue;
        }

        if seen.insert(normalized_url.clone()) {
            scored_links.push((score, normalized_url));
        }
    }

    scored_links.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));

    scored_links
        .into_iter()
        .take(max_links)
        .map(|(_, url)| url)
        .collect()
}

/*
Testing Suite
All functions pure sync - takes a value and returns.

    - Happy path - correct HTML, expected output
    - Missing/empty path - missign tag - returns empty string/false
    - Noise / edge case - 

*/

#[cfg(test)]
mod tests {
    use super::*;
    use scraper::Html;

    fn parse(html: &str) -> Html {
        Html::parse_document(html)
    }

    // ── clean_phone_candidate ──────────────────────────────────────────────

    #[test]
    fn clean_phone_us_10_digit() {
        assert_eq!(clean_phone_candidate("tel:5031234567"), "5031234567");
    }

    #[test]
    fn clean_phone_strips_country_code() {
        assert_eq!(clean_phone_candidate("tel:15031234567"), "5031234567");
    }

    #[test]
    fn clean_phone_strips_plus_prefix() {
        assert_eq!(clean_phone_candidate("tel:+15031234567"), "5031234567");
    }

    #[test]
    fn clean_phone_strips_query_string() {
        assert_eq!(clean_phone_candidate("tel:5031234567?ref=header"), "5031234567");
    }

    #[test]
    fn clean_phone_strips_semicolon_params() {
        assert_eq!(clean_phone_candidate("tel:5031234567;phone-context=+1"), "5031234567");
    }

    #[test]
    fn clean_phone_returns_empty_for_short() {
        assert_eq!(clean_phone_candidate("tel:12345"), "");
    }

    #[test]
    fn clean_phone_returns_empty_for_empty() {
        assert_eq!(clean_phone_candidate(""), "");
    }

    // ── looks_like_postal_address ──────────────────────────────────────────

    #[test]
    fn postal_accepts_street_number_and_type() {
        assert!(looks_like_postal_address("123 Main St"));
    }

    #[test]
    fn postal_accepts_city_state_zip() {
        assert!(looks_like_postal_address("Portland, OR 97201"));
    }

    #[test]
    fn postal_accepts_full_address() {
        assert!(looks_like_postal_address("123 Oak Avenue, Portland, OR 97201"));
    }

    #[test]
    fn postal_rejects_copyright_with_street_number() {
        // Verifies the operator precedence fix — bad tokens must block both branches
        assert!(!looks_like_postal_address(
            "Copyright 2020 All Rights Reserved 123 Main St"
        ));
    }

    #[test]
    fn postal_rejects_copyright_with_city_state_zip() {
        assert!(!looks_like_postal_address(
            "© 2021 Company. All Rights Reserved. Portland, OR 97201"
        ));
    }

    #[test]
    fn postal_rejects_license_text() {
        assert!(!looks_like_postal_address(
            "License #CCB 123456 Oak Ave Suite 100"
        ));
    }

    #[test]
    fn postal_rejects_empty() {
        assert!(!looks_like_postal_address(""));
    }

    #[test]
    fn postal_rejects_plain_sentence() {
        assert!(!looks_like_postal_address("Call us today for a free estimate"));
    }

    // ── looks_like_company_name_candidate ──────────────────────────────────

    #[test]
    fn company_name_accepts_valid() {
        assert!(looks_like_company_name_candidate("Portland Plumbing Co"));
    }

    #[test]
    fn company_name_rejects_too_short() {
        assert!(!looks_like_company_name_candidate("AB"));
    }

    #[test]
    fn company_name_rejects_too_long() {
        let long = "A".repeat(81);
        assert!(!looks_like_company_name_candidate(&long));
    }

    #[test]
    fn company_name_rejects_too_many_words() {
        assert!(!looks_like_company_name_candidate(
            "one two three four five six seven eight nine ten"
        ));
    }

    #[test]
    fn company_name_rejects_mostly_digits() {
        assert!(!looks_like_company_name_candidate("1234 5678 abcd"));
    }

    #[test]
    fn company_name_rejects_cta_phrases() {
        assert!(!looks_like_company_name_candidate("Call Us"));
        assert!(!looks_like_company_name_candidate("Contact Us"));
        assert!(!looks_like_company_name_candidate("Book Now"));
    }

    // ── extract_page_title ─────────────────────────────────────────────────

    #[test]
    fn page_title_extracted() {
        let doc = parse("<html><head><title>Portland Plumbing Co</title></head></html>");
        assert_eq!(extract_page_title(&doc), "Portland Plumbing Co");
    }

    #[test]
    fn page_title_empty_when_absent() {
        let doc = parse("<html><head></head></html>");
        assert_eq!(extract_page_title(&doc), "");
    }

    #[test]
    fn page_title_trimmed() {
        let doc = parse("<html><head><title>  Acme Corp  </title></head></html>");
        assert_eq!(extract_page_title(&doc), "Acme Corp");
    }

    // ── extract_text_content ───────────────────────────────────────────────

    #[test]
    fn text_content_excludes_script() {
        let doc = parse(
            r#"<html><body><p>Hello world</p><script>var x = "injected";</script></body></html>"#,
        );
        let text = extract_text_content(&doc);
        assert!(text.contains("Hello world"));
        assert!(!text.contains("injected"));
    }

    #[test]
    fn text_content_excludes_style() {
        let doc = parse(
            r#"<html><body><p>Real content</p><style>.foo { color: red; }</style></body></html>"#,
        );
        let text = extract_text_content(&doc);
        assert!(text.contains("Real content"));
        assert!(!text.contains("color"));
    }

    #[test]
    fn text_content_normalizes_whitespace() {
        let doc = parse("<html><body><p>Hello   World</p></body></html>");
        assert_eq!(extract_text_content(&doc), "Hello World");
    }

    #[test]
    fn text_content_empty_body() {
        let doc = parse("<html><body></body></html>");
        assert_eq!(extract_text_content(&doc), "");
    }

    // ── extract_phone_number ───────────────────────────────────────────────

    #[test]
    fn phone_from_tel_link() {
        let doc = parse(
            r#"<html><body><a href="tel:+15031234567">Call Us</a></body></html>"#,
        );
        let text = extract_text_content(&doc);
        assert_eq!(extract_phone_number(&doc, &text), "5031234567");
    }

    #[test]
    fn phone_from_text_regex_fallback() {
        let doc = parse("<html><body><p>Call us at 503-123-4567 today.</p></body></html>");
        let text = extract_text_content(&doc);
        assert_eq!(extract_phone_number(&doc, &text), "5031234567");
    }

    #[test]
    fn phone_tel_link_takes_priority_over_text() {
        let doc = parse(
            r#"<html><body><a href="tel:5031234567">Call</a><p>Also call 4041111111</p></body></html>"#,
        );
        let text = extract_text_content(&doc);
        assert_eq!(extract_phone_number(&doc, &text), "5031234567");
    }

    #[test]
    fn phone_empty_when_absent() {
        let doc = parse("<html><body><p>No contact info here.</p></body></html>");
        let text = extract_text_content(&doc);
        assert_eq!(extract_phone_number(&doc, &text), "");
    }

    // ── infer_category_from_text ───────────────────────────────────────────

    #[test]
    fn category_hvac() {
        assert_eq!(
            infer_category_from_text("We specialize in hvac installation and repair"),
            "hvac"
        );
    }

    #[test]
    fn category_plumbing() {
        assert_eq!(
            infer_category_from_text("Expert plumbing services for your home"),
            "plumbing"
        );
    }

    #[test]
    fn category_empty_for_unrecognized() {
        assert_eq!(infer_category_from_text("We sell artisanal cheese"), "");
    }

    #[test]
    fn category_case_insensitive() {
        assert_eq!(infer_category_from_text("HVAC Services in Portland"), "hvac");
    }

    // ── extract_page_signals ───────────────────────────────────────────────

    #[test]
    fn signals_has_viewport() {
        let doc = parse(
            r#"<html><head><meta name="viewport" content="width=device-width"></head><body></body></html>"#,
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert!(extract_page_signals(&doc, &text, &hrefs).has_viewport);
    }

    #[test]
    fn signals_no_viewport() {
        let doc = parse("<html><head></head><body></body></html>");
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert!(!extract_page_signals(&doc, &text, &hrefs).has_viewport);
    }

    #[test]
    fn signals_email_from_mailto() {
        let doc = parse(
            r#"<html><body><a href="mailto:info@example.com">Email us</a></body></html>"#,
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        let signals = extract_page_signals(&doc, &text, &hrefs);
        assert_eq!(signals.email_address, "info@example.com");
        assert!(signals.has_mailto_link);
    }

    #[test]
    fn signals_parked_domain_detected() {
        let doc = parse(
            "<html><body><p>This domain is for sale. Buy this domain today.</p></body></html>",
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert!(extract_page_signals(&doc, &text, &hrefs).is_parked_domain);
    }

    #[test]
    fn signals_schema_org_type_extracted() {
        let doc = parse(
            r#"<html><head>
                <script type="application/ld+json">
                {"@type": "Plumber", "name": "Portland Plumbing Co"}
                </script>
            </head><body></body></html>"#,
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert_eq!(
            extract_page_signals(&doc, &text, &hrefs).schema_org_business_type,
            "Plumber"
        );
    }

    #[test]
    fn signals_social_links_extracted() {
        let doc = parse(
            r#"<html><body>
                <a href="https://facebook.com/mypage">Facebook</a>
                <a href="https://instagram.com/myprofile">Instagram</a>
            </body></html>"#,
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        let signals = extract_page_signals(&doc, &text, &hrefs);
        assert_eq!(signals.social_facebook, "https://facebook.com/mypage");
        assert_eq!(signals.social_instagram, "https://instagram.com/myprofile");
        assert_eq!(signals.social_linkedin, "");
    }

    #[test]
    fn signals_copyright_year() {
        let doc = parse("<html><body><p>© 2019 Portland Plumbing Co.</p></body></html>");
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert_eq!(
            extract_page_signals(&doc, &text, &hrefs).copyright_year,
            2019
        );
    }

    #[test]
    fn signals_word_count() {
        let doc = parse("<html><body><p>one two three four five</p></body></html>");
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert_eq!(extract_page_signals(&doc, &text, &hrefs).word_count, 5);
    }

    #[test]
    fn signals_contact_page_from_anchor() {
        let doc = parse(
            r#"<html><body><a href="/contact-us">Contact Us</a></body></html>"#,
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert!(extract_page_signals(&doc, &text, &hrefs).has_contact_page);
    }

    #[test]
    fn signals_booking_detected() {
        let doc = parse(
            "<html><body><p>Book now online or schedule an appointment today.</p></body></html>",
        );
        let text = extract_text_content(&doc);
        let hrefs = extract_anchor_hrefs(&doc, "https://example.com");
        assert!(extract_page_signals(&doc, &text, &hrefs).has_booking_signal);
    }

    // ── is_internal_url ────────────────────────────────────────────────────

    #[test]
    fn internal_url_same_domain() {
        assert!(is_internal_url(
            "https://example.com",
            "https://example.com/about"
        ));
    }

    #[test]
    fn internal_url_different_domain() {
        assert!(!is_internal_url(
            "https://example.com",
            "https://other.com/page"
        ));
    }

    #[test]
    fn internal_url_subdomain_is_external() {
        assert!(!is_internal_url(
            "https://example.com",
            "https://sub.example.com/page"
        ));
    }
}
