use url::Url;

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
