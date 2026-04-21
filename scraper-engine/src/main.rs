mod compliance;
mod discovery;
mod extract;
mod transport;
mod types;


use compliance::{evaluate_crawl_eligibility, fetch_page_with_limits, fetch_root_file};




use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use std::env;

use reqwest::Client;
use std::time::Duration;
use std::time::Instant;
use std::sync::Mutex;
use std::sync::Arc;
use std::num::NonZeroU32;
use std::collections::HashSet;

use zmq::Context;

// tracing
use tracing::{debug, error, info};
use tracing_subscriber::EnvFilter;

use governor::{Quota, RateLimiter};

use tokio::sync::mpsc;

use scraper::Html;

use types::DiscoveredCandidate;
use discovery::{
    brave_more_results_available, canonical_domain_key, extract_brave_web_candidates,
    normalize_canonical_website_url,
};

use extract::{
    build_website_provenance_json, extract_address, extract_anchor_hrefs, extract_company_name,
    extract_manifest_url, extract_page_title, extract_phone_number, extract_script_srcs,
    extract_stylesheet_hrefs, extract_text_content, infer_category_from_text,
    select_priority_internal_links,
};

use transport::send_lead_batch;

// organized into mod modules for Protobuf structs
pub mod schema {
    include!(concat!(env!("OUT_DIR"), "/tracefabric.rs"));
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // ==========================================
    // START OF GLOBAL INITIALIZATION
    // ==========================================

    // 1. Load environment variables from .env file
    dotenv().ok();

    // 2. Init logging subscriber before any work starts
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .with_target(true)
        .init(); // only called once
    info!("TraceFabric Ingestion Engine booting...");

    // 3. Establish Database Pool
    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL must be set");
    info!("Establishing Master Warehouse Connection Pool...");

    let _database_pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to connect to database");
    info!("Connection pool established.");

    // 4. Build HTTP Client
    // 4. Build HTTP Client
    let http_client = Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .user_agent("TraceFabric/0.1 (research crawler)")
        .build()
        .expect("Failed to build reqwest HTTP client");

    info!("HTTP client configured.");


    // 5. Init Rate Limiter
    let quota = Quota::per_second(NonZeroU32::new(2).unwrap());
    let rate_limiter = Arc::new(RateLimiter::direct(quota));

    info!("Rate limiter initialized: 2 req/s (Token Bucket, NotKeyed).");

    // ==========================================
    // END OF GLOBAL INITIALIZATION
    // ==========================================


    // ==========================================
    // STAGE 2: DISCOVERY PIPELINE (PRODUCER)
    // ==========================================

    // Backpressure: if scrapers get behind, channel fills to 500 and discovery pauses.
    // tx - transmitter / rx - receiver / mpsc - multi-producer, single-consumer
    let (tx, mut rx) = mpsc::channel::<DiscoveredCandidate>(500);

    let discovery_tx = tx.clone();

    let target_industry = env::var("TARGET_INDUSTRY")
        .unwrap_or_else(|_| "HVAC".to_string());
    let target_location = env::var("TARGET_LOCATION")
        .unwrap_or_else(|_| "Portland, OR".to_string());

    let discovery_query = format!("{} in {}", target_industry, target_location);


    let discovery_limit: usize = env::var("DISCOVERY_LIMIT")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(3);

    let discovery_max_pages: usize = env::var("DISCOVERY_MAX_PAGES")
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .map(|v| v.clamp(1, 10))
        .unwrap_or(1);

    // Discovery Task
    tokio::spawn(async move {
        info!("Stage 1 (Brave discovery) background task started");

        let brave_api_key = env::var("BRAVE_API_KEY").expect("BRAVE_API_KEY must be set");
        let client = Client::new();

        let discovery_fetch_target = discovery_limit
            .saturating_mul(discovery_max_pages)
            .clamp(20, discovery_max_pages.saturating_mul(20));

        info!(
            query = %discovery_query,
            limit = discovery_limit,
            max_pages = discovery_max_pages,
            fetch_target = discovery_fetch_target,
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

            let response = client
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
                        error!(
                            status = %status,
                            page = page_index,
                            body = %body,
                            "Brave Search API returned non-success status"
                        );
                        return;
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
                    error!(page = page_index, error = %e, "Failed to connect to Brave Search API");
                    return;
                }
            };

            pages_fetched += 1;
            raw_results += results.len();

            for (result_url, result_title, result_description) in results {
                if queued_count >= discovery_limit {
                    info!(queued = queued_count, limit = discovery_limit, "Discovery limit reached");
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
                    website_url: normalized_website.clone(),
                        discovery_source: "brave".to_string(),
                    target_industry: target_industry.clone(),
                    target_location: target_location.clone(),
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
                    "Brave discovered candidate website"
                );

                if let Err(e) = discovery_tx.send(candidate).await {
                    error!(error = %e, "Failed to send discovered candidate to pipeline");
                    break;
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
            "Discovery filtering summary"
        );

        info!("Discovery task finished queuing URLs.");
    });

    // ==========================================
    // STAGE 3: SCRAPER CONSUMER TASKS
    // ==========================================

    // Init ZeroMQ PUSH socket once; share via Arc<Mutex<_>> across workers.
    let zmq_context = Context::new();
    let zmq_socket = zmq_context.socket(zmq::PUSH).expect("Failed to create ZMQ PUSH socket");
    zmq_socket
        .connect("tcp://127.0.0.1:5555")
        .expect("Failed to connect ZMQ PUSH socket");

    let zmq_socket = Arc::new(Mutex::new(zmq_socket));

    info!("ZMQ PUSH socket connected to master");

    // Drop master sender so rx closes when discovery_tx drops
    drop(tx);

    let mut scraper_tasks = tokio::task::JoinSet::new();

    while let Some(candidate) = rx.recv().await {
        let limiter = rate_limiter.clone();
        let worker_client = http_client.clone();
        let zmq_socket = zmq_socket.clone();

        let initial_url = candidate.website_url.clone();
        let fetch_started = Instant::now();

        scraper_tasks.spawn(async move {
            debug!(url = %initial_url, "Requesting rate limiter token...");

            limiter.until_ready().await;
            info!(url = %initial_url, "Token acquired. Starting compliance check...");

            let robots_txt = fetch_root_file(&worker_client, &initial_url, "/robots.txt").await;
            let (crawl_allowed, crawl_disallowed_reason) =
                evaluate_crawl_eligibility(robots_txt.as_ref());

            if !crawl_allowed {
                let payload = schema::RawLead {
                    id: uuid::Uuid::new_v4().to_string(),
                    timestamp: chrono::Utc::now().to_rfc3339(),

                    source_url: initial_url.clone(),
                    initial_url: initial_url.clone(),
                    final_url: String::new(),

                    discovery_source: candidate.discovery_source.clone(),
                    target_industry: candidate.target_industry.clone(),
                    target_location: candidate.target_location.clone(),
                    crawl_allowed,
                    crawl_disallowed_reason,
                    is_no_website_opportunity: candidate.is_no_website_opportunity,
                    provider_fsq_id: candidate.provider_fsq_id.clone(),

                    company_name: String::new(),
                    category: String::new(),
                    phone_number: String::new(),
                    address: String::new(),

                    provider_provenance_json: candidate.provider_provenance_json.clone(),
                    website_provenance_json: "{}".to_string(),
                    location_confidence: 0.0,
                    category_confidence: 0.0,

                    http_status: 0,
                    is_https: initial_url.starts_with("https://"),
                    redirect_count: 0,
                    fetch_duration_ms: fetch_started.elapsed().as_millis() as i32,
                    response_size_bytes: 0,
                    content_type: String::new(),

                    response_headers: vec![],

                    raw_html: String::new(),
                    text_content: String::new(),
                    page_title: String::new(),

                    anchor_hrefs: vec![],
                    script_srcs: vec![],
                    stylesheet_hrefs: vec![],

                    robots_txt,
                    sitemap_xml: None,
                    manifest_url: String::new(),
                };

                info!(
                    url = &initial_url,
                    reason = &payload.crawl_disallowed_reason,
                    "Skipping homepage due to compliance gate."
                );

                send_lead_batch(&zmq_socket, payload, &initial_url);
                return;
            }

            info!(url = &initial_url, "Compliance check passed. Fetching homepage...");

            match fetch_page_with_limits(&worker_client, &initial_url).await {
                Ok(fetch_result) => {
                    let fetch_duration_ms = fetch_started.elapsed().as_millis() as i32;

                    let status = fetch_result.status;
                    let final_url = fetch_result.final_url;
                    let is_https = fetch_result.is_https;
                    let redirect_count = fetch_result.redirect_count;
                    let content_type = fetch_result.content_type;
                    let response_headers = fetch_result.response_headers;
                    let html_body = fetch_result.body;
                    let response_size_bytes = html_body.len() as i32;

            let (
                page_title,
                text_content,
                mut company_name,
                mut phone_number,
                mut address,
                mut category,
                anchor_hrefs,
                script_srcs,
                stylesheet_hrefs,
                manifest_url,
            ) = {
                let document = Html::parse_document(html_body.as_str());

                let anchor_hrefs = extract_anchor_hrefs(&document, final_url.as_str());
                let script_srcs = extract_script_srcs(&document, final_url.as_str());
                let stylesheet_hrefs =
                    extract_stylesheet_hrefs(&document, final_url.as_str());
                let manifest_url = extract_manifest_url(&document, final_url.as_str());

                let page_title = extract_page_title(&document);
                let text_content = extract_text_content(&document);
                let company_name = extract_company_name(&document, &page_title);
                let phone_number = extract_phone_number(&document, &text_content);
                let address = extract_address(&document);
                let category = infer_category_from_text(&text_content);

                (
                    page_title,
                    text_content,
                    company_name,
                    phone_number,
                    address,
                    category,
                    anchor_hrefs,
                    script_srcs,
                    stylesheet_hrefs,
                    manifest_url,
                )
            };

            let mut company_name_source_url = if company_name.is_empty() {
                String::new()
            } else {
                final_url.clone()
            };

            let mut phone_number_source_url = if phone_number.is_empty() {
                String::new()
            } else {
                final_url.clone()
            };

            let mut address_source_url = if address.is_empty() {
                String::new()
            } else {
                final_url.clone()
            };

            let mut category_source_url = if category.is_empty() {
                String::new()
            } else {
                final_url.clone()
            };

            let supporting_urls =
                select_priority_internal_links(final_url.as_str(), &anchor_hrefs, 3);

            for supporting_url in &supporting_urls {
                limiter.until_ready().await;

                match fetch_page_with_limits(&worker_client, supporting_url.as_str()).await {
                    Ok(supporting_result) => {
                        let supporting_body = supporting_result.body;

                        let (
                            _supporting_page_title,
                            supporting_text_content,
                            supporting_company_name,
                            supporting_phone_number,
                            supporting_address,
                            supporting_category,
                        ) = {
                            let document = Html::parse_document(supporting_body.as_str());

                            let supporting_page_title = extract_page_title(&document);
                            let supporting_text_content = extract_text_content(&document);
                            let supporting_company_name =
                                extract_company_name(&document, &supporting_page_title);
                            let supporting_phone_number =
                                extract_phone_number(&document, &supporting_text_content);
                            let supporting_address = extract_address(&document);
                            let supporting_category =
                                infer_category_from_text(&supporting_text_content);

                            (
                                supporting_page_title,
                                supporting_text_content,
                                supporting_company_name,
                                supporting_phone_number,
                                supporting_address,
                                supporting_category,
                            )
                        };

                        if company_name.is_empty() && !supporting_company_name.is_empty() {
                            company_name = supporting_company_name;
                            company_name_source_url = supporting_url.clone();
                        }

                        if phone_number.is_empty() && !supporting_phone_number.is_empty() {
                            phone_number = supporting_phone_number;
                            phone_number_source_url = supporting_url.clone();
                        }

                        if address.is_empty() && !supporting_address.is_empty() {
                            address = supporting_address;
                            address_source_url = supporting_url.clone();
                        }

                        if category.is_empty() && !supporting_category.is_empty() {
                            category = supporting_category;
                            category_source_url = supporting_url.clone();
                        }
                    }
                    Err(e) => {
                        debug!(
                            url = %supporting_url,
                            error = %e,
                            "Skipping supporting page during deterministic same-domain crawl"
                        );
                    }
                }
            }

            let website_provenance_json = build_website_provenance_json(
                &company_name,
                &company_name_source_url,
                &category,
                &category_source_url,
                &phone_number,
                &phone_number_source_url,
                &address,
                &address_source_url,
            );

            info!(
                url = %initial_url,
                final_url = %final_url,
                status = %status,
                redirect_count = redirect_count,
                bytes = response_size_bytes,
                fetch_duration_ms = fetch_duration_ms,
                "Fetched successfully"
            );

            let lowered_final_url = final_url.to_ascii_lowercase();
            let lowered_target_location = candidate.target_location.to_ascii_lowercase();

            let location_confidence =
                if lowered_final_url.contains(lowered_target_location.as_str()) {
                    0.8
                } else {
                    0.0
                };

            let category_confidence = if category.is_empty() { 0.0 } else { 0.65 };

            let sitemap_xml =
                fetch_root_file(&worker_client, final_url.as_str(), "/sitemap.xml").await;

            let payload = schema::RawLead {
                id: uuid::Uuid::new_v4().to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),

                source_url: initial_url.clone(),
                initial_url: initial_url.clone(),
                final_url,

                discovery_source: candidate.discovery_source.clone(),
                target_industry: candidate.target_industry.clone(),
                target_location: candidate.target_location.clone(),
                crawl_allowed,
                crawl_disallowed_reason,
                is_no_website_opportunity: candidate.is_no_website_opportunity,
                provider_fsq_id: candidate.provider_fsq_id.clone(),

                company_name,
                category: category.clone(),
                phone_number,
                address,

                provider_provenance_json: candidate.provider_provenance_json.clone(),
                website_provenance_json,
                location_confidence,
                category_confidence,

                http_status: status,
                is_https,
                redirect_count,
                fetch_duration_ms,
                response_size_bytes,
                content_type,
                response_headers,

                raw_html: html_body,
                text_content,
                page_title,

                anchor_hrefs,
                script_srcs,
                stylesheet_hrefs,

                robots_txt,
                sitemap_xml,
                manifest_url,
            };

            send_lead_batch(&zmq_socket, payload, &initial_url);
        }

        Err(e) => {
            error!(url = %initial_url, error = %e, "Failed to fetch within safety limits");
        }
    }
        });
    }

    // Wait for all scraper tasks to finish
    while let Some(res) = scraper_tasks.join_next().await {
        if let Err(e) = res {
            error!("Scraper task panicked: {}", e);
        }
    }

    // Once loop ends, rx is empty => all tx senders have dropped
    info!("Pipeline execution complete.");
    Ok(())
}
