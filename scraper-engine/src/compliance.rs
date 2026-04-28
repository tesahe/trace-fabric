use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

use reqwest::Client;
use reqwest::header::{CONTENT_TYPE, LOCATION};
use tokio::net::lookup_host;
use url::Url;

use crate::schema;

const MAX_FETCH_BYTES: usize = 2_000_000;
const MAX_REDIRECTS: usize = 5;

pub struct FetchPageResult {
    pub final_url: String,
    pub status: i32,
    pub is_https: bool,
    pub redirect_count: i32,
    pub content_type: String,
    pub response_headers: Vec<schema::Header>,
    pub body: String,
}

// TODO: implement this, intentionally partial
pub fn robots_txt_disallows_homepage(body: &str) -> bool {
    let mut applies_to_tracefabric = false;

    for raw_line in body.lines() {
        let line = raw_line.split('#').next().unwrap_or("").trim();
        if line.is_empty() {
            continue;
        }

        let lower = line.to_ascii_lowercase();

        if let Some(value) = lower.strip_prefix("user-agent:") {
            let agent = value.trim();
            applies_to_tracefabric = agent == "*" || agent == "tracefabric";
            continue;
        }

        if applies_to_tracefabric {
            if let Some(value) = lower.strip_prefix("disallow:") {
                let path = value.trim();
                if path == "/" {
                    return true;
                }
            }
        }
    }

    false
}

pub fn evaluate_crawl_eligibility(robots_txt: Option<&schema::RootFile>) -> (bool, String) {
    match robots_txt {
        Some(file) if file.exists && robots_txt_disallows_homepage(&file.body) => {
            (false, "robots_txt_disallow_all".to_string())
        }
        _ => (true, String::new()),
    }
}

fn is_disallowed_ipv4(ip: Ipv4Addr) -> bool {
    let [a, b, _, _] = ip.octets();

    ip.is_private()
        || ip.is_loopback()
        || ip.is_link_local()
        || ip.is_broadcast()
        || ip.is_documentation()
        || ip.is_unspecified()
        || ip.is_multicast()
        || (a == 100 && (64..=127).contains(&b))
        || (a == 198 && (b == 18 || b == 19))
        || a >= 240
}

fn is_disallowed_ipv6(ip: Ipv6Addr) -> bool {
    let first_segment = ip.segments()[0];

    ip.is_loopback()
        || ip.is_unspecified()
        || ip.is_multicast()
        || ip.is_unique_local()
        || ((first_segment & 0xffc0) == 0xfe80)
        || (ip.segments()[0] == 0x2001 && ip.segments()[1] == 0x0db8)
}

fn is_disallowed_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ipv4) => is_disallowed_ipv4(ipv4),
        IpAddr::V6(ipv6) => is_disallowed_ipv6(ipv6),
    }
}

fn is_disallowed_hostname(host: &str) -> bool {
    let lower = host.trim().to_ascii_lowercase();

    lower == "localhost"
        || lower.ends_with(".localhost")
        || lower.ends_with(".local")
        || lower == "metadata.google.internal"
}

pub async fn assert_url_is_safe_for_fetch(raw_url: &str) -> Result<Url, String> {
    let parsed = Url::parse(raw_url.trim()).map_err(|e| format!("invalid_url: {e}"))?;

    match parsed.scheme() {
        "http" | "https" => {}
        other => return Err(format!("unsupported_scheme: {other}")),
    }

    let host = parsed
        .host_str()
        .ok_or_else(|| "missing_host".to_string())?;

    if is_disallowed_hostname(host) {
        return Err(format!("disallowed_hostname: {host}"));
    }

    if let Ok(ip) = host.parse::<IpAddr>() {
        if is_disallowed_ip(ip) {
            return Err(format!("disallowed_ip: {ip}"));
        }
        return Ok(parsed);
    }

    let port = parsed.port_or_known_default().unwrap_or(80);
    let resolved = lookup_host((host, port))
        .await
        .map_err(|e| format!("dns_resolution_failed: {e}"))?;

    let mut saw_any_address = false;

    for socket_addr in resolved {
        saw_any_address = true;
        if is_disallowed_ip(socket_addr.ip()) {
            return Err(format!("resolved_to_disallowed_ip: {}", socket_addr.ip()));
        }
    }

    if !saw_any_address {
        return Err("dns_resolution_returned_no_addresses".to_string());
    }

    Ok(parsed)
}

fn is_supported_primary_content_type(content_type: &str) -> bool {
    let lower = content_type.to_ascii_lowercase();

    lower.starts_with("text/html") || lower.starts_with("application/xhtml+xml")
}

async fn read_response_body_with_limit(
    mut response: reqwest::Response,
    max_bytes: usize,
) -> Result<String, String> {
    let mut bytes = Vec::new();

    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|e| format!("body_read_failed: {e}"))?
    {
        if bytes.len() + chunk.len() > max_bytes {
            return Err(format!("response_body_too_large: max_bytes={max_bytes}"));
        }

        bytes.extend_from_slice(&chunk);
    }

    Ok(String::from_utf8_lossy(&bytes).to_string())
}

pub async fn fetch_page_with_limits(
    client: &Client,
    initial_url: &str,
) -> Result<FetchPageResult, String> {
    let mut current_url = assert_url_is_safe_for_fetch(initial_url).await?;
    let mut redirect_count = 0usize;

    loop {
        let response = client
            .get(current_url.clone())
            .send()
            .await
            .map_err(|e| format!("request_failed: {e}"))?;

        let status = response.status();

        if status.is_redirection() {
            if redirect_count >= MAX_REDIRECTS {
                return Err(format!("too_many_redirects: max_redirects={MAX_REDIRECTS}"));
            }

            let location = response
                .headers()
                .get(LOCATION)
                .and_then(|v| v.to_str().ok())
                .ok_or_else(|| "redirect_missing_location".to_string())?;

            let next_url = current_url
                .join(location)
                .map_err(|e| format!("invalid_redirect_location: {e}"))?;

            current_url = assert_url_is_safe_for_fetch(next_url.as_str()).await?;
            redirect_count += 1;
            continue;
        }

        let status_code = status.as_u16() as i32;
        let final_url = response.url().to_string();
        let is_https = response.url().scheme() == "https";

        let content_type = response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|v| v.to_str().ok())
            .unwrap_or("")
            .to_string();

        if !is_supported_primary_content_type(&content_type) {
            return Err(format!("unsupported_content_type: {content_type}"));
        }

        let response_headers = response
            .headers()
            .iter()
            .map(|(key, value)| schema::Header {
                key: key.as_str().to_string(),
                value: value.to_str().unwrap_or("").to_string(),
            })
            .collect::<Vec<_>>();

        let body = read_response_body_with_limit(response, MAX_FETCH_BYTES).await?;

        return Ok(FetchPageResult {
            final_url,
            status: status_code,
            is_https,
            redirect_count: redirect_count as i32,
            content_type,
            response_headers,
            body,
        });
    }
}

pub async fn fetch_root_file(
    client: &Client,
    base_url: &str,
    path: &str,
) -> Option<schema::RootFile> {
    let base = assert_url_is_safe_for_fetch(base_url).await.ok()?;
    let joined = base.join(path).ok()?;

    let response = client.get(joined.clone()).send().await.ok()?;

    let status = response.status().as_u16() as i32;
    let content_type = response
        .headers()
        .get(CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    let body = read_response_body_with_limit(response, 250_000)
        .await
        .ok()?;

    Some(schema::RootFile {
        path: path.to_string(),
        http_status: status,
        exists: status >= 200 && status < 300,
        content_type,
        body,
    })
}
