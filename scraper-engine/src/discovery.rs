use std::collections::HashSet;
use tokio::sync::mpsc;
use tracing::{debug, info};
use url::Url;
use crate::cli::{DiscoverArgs, UrlArgs};
use crate::types::{AppResult, DiscoveredCandidate};

// This file STRICTLY uses Brave API to find URLs and queue them.
// No scraping is done in discovery.rs


const DISCOVERY_HOST_DENYLIST: &[&str] = &[
    "angi.com",
    "angieslist.com",
    "bbb.org",
    "birdeye.com",
    "chamberofcommerce.com",
    "facebook.com",
    "foursquare.com",
    "healthgrades.com",
    "homeadvisor.com",
    "houzz.com",
    "instagram.com",
    "mapquest.com",
    "manta.com",
    "nextdoor.com",
    "opencare.com",
    "superpages.com",
    "thumbtack.com",
    "tripadvisor.com",
    "webmd.com",
    "yellowpages.com",
    "yelp.com",
    "zocdoc.com",
];

const DISCOVERY_PATH_DENYLIST: &[&str] = &[
    "/search",
    "/find",
    "/directory",
    "/directories",
    "/listing",
    "/listings",
    "/profile",
    "/profiles",
    "/providers",
    "/business",
    "/biz",
];

/// Parses a raw Brave Search API JSON response body and extracts (url, title, description) tuples.
/// Uses raw serde_json::Value extraction — intentionally avoids typed structs to minimize
/// coupling to the transient Brave provider payload schema.
pub fn extract_brave_web_candidates(body: &str) -> Vec<(String, String, String)> {
    let parsed: serde_json::Value = match serde_json::from_str(body) {
        Ok(value) => value,
        Err(_) => return vec![],
    };

    let mut candidates = Vec::new();

    let results = parsed
        .get("web")
        .and_then(|web| web.get("results"))
        .and_then(|results| results.as_array());

    let Some(results) = results else {
        return candidates;
    };

    for item in results {
        let url = item
            .get("url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();

        let title = item
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();

        let description = item
            .get("description")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .trim()
            .to_string();

        if !url.is_empty() {
            candidates.push((url, title, description));
        }
    }

    candidates
}

pub fn brave_more_results_available(body: &str) -> bool {
    let parsed: serde_json::Value = match serde_json::from_str(body) {
        Ok(value) => value,
        Err(_) => return false,
    };

    parsed
        .get("query")
        .and_then(|query| query.get("more_results_available"))
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
}

pub fn canonical_domain_key(raw_url: &str) -> Option<String> {
    let parsed = Url::parse(raw_url.trim()).ok()?;
    let host = parsed.host_str()?.to_ascii_lowercase();
    Some(host.trim_start_matches("www.").to_string())
}

pub fn normalize_canonical_website_url(raw_url: &str) -> Option<String> {
    let mut parsed = Url::parse(raw_url.trim()).ok()?;

    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return None;
    }

    parsed.set_fragment(None);
    parsed.set_query(None);

    let host = parsed.host_str()?.to_ascii_lowercase();
    if is_disallowed_discovery_host(&host) {
        return None;
    }

    let path = parsed.path().to_ascii_lowercase();
    if is_disallowed_discovery_path(&path) {
        return None;
    }

    Some(parsed.to_string().trim_end_matches('/').to_string())
}

fn is_disallowed_discovery_host(host: &str) -> bool {
    let normalized_host = host.trim_start_matches("www.");
    DISCOVERY_HOST_DENYLIST.iter().any(|blocked| {
        normalized_host == *blocked || normalized_host.ends_with(&format!(".{blocked}"))
    })
}

fn is_disallowed_discovery_path(path: &str) -> bool {
    if path.is_empty() || path == "/" {
        return false;
    }

    DISCOVERY_PATH_DENYLIST
        .iter()
        .any(|blocked| path == *blocked || path.starts_with(&format!("{blocked}/")))
}



// Calls Brave Search API, paginates, filters, and queues URLs
pub async fn queue_discovery_candidates(
    args: DiscoverArgs,
    discovery_tx: mpsc::Sender<DiscoveredCandidate>,
    brave_api_key: String,
    http_client: reqwest::Client,
) -> AppResult<()> {
    info!("Stage 1 (Brave discovery) background task started");

    let discovery_query = format!("{} in {}", args.industry, args.location);
    let discovery_limit = args.limit;
    let discovery_max_pages = args.max_pages.clamp(1, 10);
    let discovery_fetch_target = discovery_limit
        .saturating_mul(discovery_max_pages)
        .clamp(20, discovery_max_pages.saturating_mul(20));

    info!(
        query = %discovery_query,
        limit = discovery_limit,
        max_pages = discovery_max_pages,
        fetch_target = discovery_fetch_target,
        run_id = %args.run_id,
        "Querying Brave web search for candidate websites"
    );

    let mut seen_domains: HashSet<String> = HashSet::new();
    let mut queued_count = 0usize;
    let mut skipped_non_canonical = 0usize;
    let mut skipped_duplicate = 0usize;
    let mut raw_results = 0usize;
    let mut page_index = 0usize;
    let mut remaining_target = discovery_fetch_target;
    let mut pages_fetched = 0usize;

    while queued_count < discovery_limit
        && remaining_target > 0
        && page_index < discovery_max_pages
        && page_index <= 9
    {
        let page_count = remaining_target.min(20);
        let discovery_count = page_count.to_string();
        let offset = page_index.to_string();

        let response = http_client
            .get("https://api.search.brave.com/res/v1/web/search")
            .header("Accept", "application/json")
            .header("X-Subscription-Token", &brave_api_key)
            .query(&[
                ("q", discovery_query.as_str()),
                ("count", discovery_count.as_str()),
                ("offset", offset.as_str()),
                ("country", "us"),
                ("search_lang", "en"),
            ])
            .send()
            .await;

        let (results, more_results_available) = match response {
            Ok(resp) => {
                let status = resp.status();
                let body = resp.text().await.unwrap_or_default();

                if !status.is_success() {
                    return Err(format!(
                        "Brave Search API returned non-success status: {} body={}",
                        status, body
                    )
                    .into());
                }

                let results = extract_brave_web_candidates(&body);
                let more_results_available = brave_more_results_available(&body);

                if results.is_empty() {
                    info!(page = page_index, "Brave response contained no web results");
                    break;
                }

                info!(
                    page = page_index,
                    page_results = results.len(),
                    page_count = page_count,
                    more_results_available = more_results_available,
                    "Brave API returned paginated web results"
                );

                (results, more_results_available)
            }
            Err(e) => {
                return Err(format!("Failed to connect to Brave Search API: {}", e).into());
            }
        };

        pages_fetched += 1;
        raw_results += results.len();

        for (result_url, result_title, result_description) in results {
            if queued_count >= discovery_limit {
                info!(
                    queued = queued_count,
                    limit = discovery_limit,
                    "Discovery limit reached"
                );
                break;
            }

            let Some(normalized_website) = normalize_canonical_website_url(&result_url) else {
                skipped_non_canonical += 1;
                debug!(url = %result_url, "Skipping non-canonical or invalid website URL");
                continue;
            };

            let Some(domain_key) = canonical_domain_key(&normalized_website) else {
                skipped_non_canonical += 1;
                debug!(url = %normalized_website, "Skipping candidate without canonical domain key");
                continue;
            };

            if seen_domains.contains(&domain_key) {
                skipped_duplicate += 1;
                debug!(url = %normalized_website, domain = %domain_key, "Skipping duplicate discovered website domain");
                continue;
            }

            seen_domains.insert(domain_key.clone());

            let candidate = DiscoveredCandidate {
                run_id: args.run_id.clone(),
                website_url: normalized_website.clone(),
                discovery_source: "brave".to_string(),
                target_industry: args.industry.clone(),
                target_location: args.location.clone(),
                provider_provenance_json: serde_json::json!({
                    "provider": "brave",
                    "query": discovery_query,
                    "transient_only": true,
                    "provider_payload_stored": false,
                    "page": page_index,
                    "domain_key": domain_key
                })
                .to_string(),
                provider_fsq_id: String::new(),
                is_no_website_opportunity: false,
            };

            debug!(
                title = %result_title,
                url = %candidate.website_url,
                description = %result_description,
                run_id = %candidate.run_id,
                "Brave discovered candidate website"
            );

            if let Err(e) = discovery_tx.send(candidate).await {
                return Err(
                    format!("Failed to send discovered candidate to pipeline: {}", e).into(),
                );
            }

            queued_count += 1;
        }

        remaining_target = remaining_target.saturating_sub(page_count);
        if !more_results_available {
            break;
        }

        page_index += 1;
    }

    info!(
        queued = queued_count,
        raw_results = raw_results,
        skipped_non_canonical = skipped_non_canonical,
        skipped_duplicate = skipped_duplicate,
        limit = discovery_limit,
        max_pages = discovery_max_pages,
        fetch_target = discovery_fetch_target,
        pages_fetched = pages_fetched,
        run_id = %args.run_id,
        "Discovery filtering summary"
    );

    info!("Discovery task finished queuing URLs.");
    Ok(())
}

// Strictly for queueing a set URL inputted.
pub async fn queue_direct_url_candidate(
    args: UrlArgs,
    tx: mpsc::Sender<DiscoveredCandidate>,
) -> AppResult<()> {
    let normalized_website = normalize_canonical_website_url(&args.website)
        .ok_or_else(|| format!("Invalid or non-canonical website URL: {}", args.website))?;

    let candidate = DiscoveredCandidate {
        run_id: args.run_id.clone(),
        website_url: normalized_website.clone(),
        discovery_source: "direct_url".to_string(),
        target_industry: args.industry.clone(),
        target_location: args.location.clone(),
        provider_provenance_json: serde_json::json!({
            "provider": "direct_url",
            "input_website": args.website,
            "normalized_website": normalized_website,
            "transient_only": true,
            "provider_payload_stored": false,
        })
        .to_string(),
        provider_fsq_id: String::new(),
        is_no_website_opportunity: false,
    };

    info!(
        url = %candidate.website_url,
        run_id = %candidate.run_id,
        "Queued direct URL candidate"
    );

    tx.send(candidate)
        .await
        .map_err(|e| format!("Failed to queue direct URL candidate: {}", e).into())
}
