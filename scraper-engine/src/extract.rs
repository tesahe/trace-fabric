use regex::Regex;
use scraper::{Html, Selector};
use url::Url;

use crate::schema;

use std::collections::HashSet;

pub fn parse_selector(selector: &str) -> Selector {
    Selector::parse(selector).expect("valid CSS selector")
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
    document
        .root_element()
        .text()
        .collect::<Vec<_>>()
        .join(" ")
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
        "hvac company",
        "heating and cooling",
        "air conditioning",
        "portland hvac",
        "home",
        "welcome", // temp for initial test
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

    (has_street_number && has_street_type) || has_city_state_zip && !contains_bad_tokens
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
