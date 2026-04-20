use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use std::env;

use reqwest::Client;
use std::time::Duration;
use std::time::Instant;


// tracing
use tracing::{debug, error, info};
use tracing_subscriber::EnvFilter;

use governor::{Quota, RateLimiter};
use std::num::NonZeroU32;
use std::sync::Arc;

use tokio::sync::mpsc;

use serde::Deserialize;

use scraper::{Html, Selector};
use url::Url;

// ==========================================
// SERPER API STRUCTS
// ==========================================

#[derive(Deserialize, Debug)]
pub struct SerperResponse {
    pub places: Vec<SerperPlace>,
}

#[derive(Deserialize, Debug)]
pub struct SerperPlace {
    pub title: String,
    pub address: String,
    // website is an option 
    pub website: Option<String>,
    #[serde(rename = "phoneNumber")]
    pub phone_number: Option<String>,
    pub rating: Option<f32>,
    #[serde(rename = "ratingCount")]
    pub rating_count: Option<u32>,


    pub latitude: Option<f64>,
    pub longitude: Option<f64>,
    pub category: Option<String>,
    #[serde(rename = "placeId")]
    pub place_id: Option<String>,
    #[serde(rename = "cid")]
    pub customer_id: Option<String>,
}

// organized into mod modules for Protobuf structs
pub mod schema {
    include!(concat!(env!("OUT_DIR") ,"/tracefabric.rs"));
}

fn parse_selector(selector: &str) -> Selector {
    Selector::parse(selector).expect("valid CSS selector")
}

fn extract_page_title(document: &Html) -> String {
    let selector = parse_selector("title");
    document
        .select(&selector)
        .next()
        .map(|element| element.text().collect::<Vec<_>>().join(" ").trim().to_string())
        .unwrap_or_default()
}

fn extract_text_content(document: &Html) -> String {
    document
        .root_element()
        .text()
        .collect::<Vec<_>>()
        .join(" ")
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

fn resolve_url(base_url: &str, raw_url: &str) -> Option<String> {
    if raw_url.is_empty() {
        return None;
    }

    let base = Url::parse(base_url).ok()?;
    base.join(raw_url).ok().map(|u| u.to_string())

}

fn is_internal_url(base_url: &str, candidate_url: &str) -> bool {
    let base = Url::parse(base_url).ok();
    let candidate = Url::parse(candidate_url).ok();

    match (base, candidate) {
        (Some(base), Some(candidate)) => base.domain() == candidate.domain(),
        _ => false,
    }
}

fn extract_anchor_hrefs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
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

fn extract_script_srcs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
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

fn extract_stylesheet_hrefs(document: &Html, base_url: &str) -> Vec<schema::UrlArtifact> {
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

fn extract_manifest_url(document: &Html, base_url: &str) -> String {
    let selector = parse_selector(r#"link[rel="manifest"][href]"#);
    
    document
        .select(&selector)
        .next()
        .and_then(|el| el.value().attr("href"))
        .and_then(|href| resolve_url(base_url, href))
        .unwrap_or_default()
}

async fn fetch_root_file(
    client: &Client,
    base_url: &str,
    path: &str,
) -> Option<schema::RootFile> {
    let base = Url::parse(base_url).ok()?;
    let joined = base.join(path).ok()?;

    let response = client.get(joined.clone()).send().await.ok()?;

    let status = response.status().as_u16() as i32;
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_string();

    let body = response.text().await.unwrap_or_default();

    Some(schema::RootFile {
        path: path.to_string(),
        http_status: status,
        exists: status >= 200 && status < 300,
        content_type,
        body,
    })
}







#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    /*
    Main Function
    Creates an asynchronous channel with a buffer/capacity of 500 URLs.

    
    
    */

    
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

    let http_client = Client::builder()
        .timeout(Duration::from_secs(10))
        .user_agent("TraceFabric/0.1 (research crawler)") // ethics: self-identify
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

    // This is our BACKPRESSURE => If scrapers get behind, this channel fills up
    // to 500 and Serper will be paused until the scrapers catch up.
    // Serper - Google Maps API Wrapper


    // tx - transmitter
    // rx - receiver
    // mpsc - multi-producer, single-consumer

    // Establish Bounding Channel

    let (tx, mut rx) = mpsc::channel::<SerperPlace>(500);


    // Discovery needs to run in the background
    // It will populate the channel with URLs
    // Clone sender (transmitter) to hand it to other task

    let discovery_tx = tx.clone();

    // Server Discovery Task
    tokio::spawn( async move {
        info!("Stage 1 (Serper Discovery) background task started");

        //MOCK Serper.dev integration for now
        let serper_key = env::var("SERPER_API_KEY").expect("SERPER_API_KEY must be set");
        let client = Client::new();

        let search_query_json = serde_json::json!({
            "q": "HVAC In Portland, OR",
            "gl": "us",
        });
        info!("Querying Serper.dev Places API");



        //  Fetch Serper API

        let response = client.post("https://google.serper.dev/places")
            .header("X-API-KEY", serper_key)
            .header("Content-Type", "application/json")
            .json(&search_query_json)
            .send()
            .await;

        match response {
            Ok(resp) => {
                //  Deserialize via serde into SerperResponse struct
                if let Ok(serper_data) = resp.json::<SerperResponse>().await {
                
                    info!("Serper API returned {} places", serper_data.places.len());

                    // Push URLS into pipeline

                    //TODO This is where I have to back and edit
                    // NEED to Figure out exactly what we want in the struct
                    // WHAT we are targeting, WHAT is important
                    // WHAT we are able to get from Serper.dev
                    // Currently have website, address, title, HTML?
                    for place in serper_data.places {
                        // If they have a website, queue it

                        if let Some(ref website_url) = place.website {
                            debug!(company = %place.title, url = %website_url, "Discovered lead. Queuing for scraping.");
                            
                            // Push URL into pipeline
                            if let Err(e) = discovery_tx.send(place).await {
                                error!(error = %e, "Failed to send URL to pipeline");
                                break;
                            }
                        } else {
                            // On Google but have no website!

                            info!(company = %place.title, "SERVICE GAP: No Website listed on Google Maps");

                            //TODO: Add to "Service Gap" table in DB
                            // TODO add functionality for this; This is a very important feature
                        }
                    }


                } else {
                    error!("Failed to deserialize Serper JSON response");
                }


            } 
            Err(e) => error!("Failed to to connect to Serper API: {}", e),
        }


            
        info!("Discovery task finished queuing URLs.");



        //MOCK Yelp API integration NEXT


    });

    // Ingestion Stage
    // Scraper Consumer Task here
    // Governor for rate limiting
    
    // While loop to listen to channel indefinitely.

    // Init ZEROMQ Sockets here later

    // drop master sender
    drop(tx);

    let mut scraper_tasks = tokio::task::JoinSet::new();

    while let Some(place) = rx.recv().await {
        // Wakes up when Discovery pushes a URL
        // Clones (limiter, zmq context)

        // 1. Clone global so new thread can use for each URL
        let limiter = rate_limiter.clone();
        let worker_client = http_client.clone();

        // 2. Dedicating spawn scraping task for this specific URL
        let url = place.website.clone().unwrap();
        let initial_url = url.clone();
        let fetch_started = Instant::now();


        scraper_tasks.spawn(async move {

            debug!(url = %url, "Requesting rate limiter token...");

            // 2.1. Await Rate Limiter
            limiter.until_ready().await;
            info!(url = %url, "Token acquired. Fetching...");

            //reqwest HTTP GET to the website
            match worker_client.get(&url).send().await {
                Ok(response) => {

                    // 1. fetch metadata

                    let fetch_duration_ms = fetch_started.elapsed().as_millis() as i32;

                    let status = response.status().as_u16() as i32;
                    let final_url = response.url().to_string();
                    let is_https = response.url().scheme() == "https";

                    let content_type = response
                        .headers()
                        .get(reqwest::header::CONTENT_TYPE)
                        .and_then(|v| v.to_str().ok())
                        .unwrap_or("")
                        .to_string();

                    let response_headers: Vec<schema::Header> = response
                        .headers()
                        .iter()
                        .map(|(key, value)| schema::Header {
                            key: key.as_str().to_string(),
                            value: value.to_str().unwrap_or("").to_string(),
                        })
                        .collect();


                    // 2. fetch body content

                    let html_body = response.text().await.unwrap_or_default();
                    let response_size_bytes = html_body.len() as i32;


                    let (page_title, text_content, anchor_hrefs, script_srcs, stylesheet_hrefs, manifest_url) = {
                        // 3. document parsing

                        let document = Html::parse_document(&html_body);

                    // 4. homepage extraction helpers

                        let page_title = extract_page_title(&document);
                        let text_content = extract_text_content(&document);
                        let anchor_hrefs = extract_anchor_hrefs(&document, &final_url);
                        let script_srcs = extract_script_srcs(&document, &final_url);
                        let stylesheet_hrefs = extract_stylesheet_hrefs(&document, &final_url);
                        let manifest_url = extract_manifest_url(&document, &final_url);

                        (
                            page_title,
                            text_content,
                            anchor_hrefs,
                            script_srcs,
                            stylesheet_hrefs,
                            manifest_url,
                        )
                    };


                    // 5. root file fetch helpers
                    let robots_txt = fetch_root_file(&worker_client, &final_url, "/robots.txt").await;
                    let sitemap_xml = fetch_root_file(&worker_client, &final_url, "/sitemap.xml").await;





                    
                    info!(url = %initial_url,
                        final_url = %final_url,
                        status = %status, 
                        bytes = response_size_bytes, 
                        fetch_duration_ms = fetch_duration_ms,
                        "Fetched successfully"
                    );

                    // 6. Serialize into Protobuf, build payload
                    let _payload = schema::RawLead { // remove underscore once zmq setup
                        id: uuid::Uuid::new_v4().to_string(),
                        timestamp: chrono::Utc::now().to_rfc3339(),

                        company_name: place.title,
                        category: place.category.unwrap_or_default(),
                        source_url: initial_url.clone(),
                        initial_url: initial_url.clone(),
                        final_url,

                        phone_number: place.phone_number.unwrap_or_default(),
                        address: place.address,
                        latitude: place.latitude.unwrap_or(0.0),
                        longitude: place.longitude.unwrap_or(0.0),
                        rating: place.rating.unwrap_or(0.0),
                        rating_count: place.rating_count.unwrap_or(0) as i32,

                        http_status: status,
                        is_https,
                        redirect_count: 0,
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

                        place_id: place.place_id.unwrap_or_default(),
                        customer_id: place.customer_id.unwrap_or_default(),
                    };


                    // 

                    // Send over ZeroMQ
                    // zmq_socket.send(payload.encode_to_vec()), 0).unwrap();


                }
                Err(e) => {
                    error!(url = %initial_url, error = %e, "Failed to fetch");
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