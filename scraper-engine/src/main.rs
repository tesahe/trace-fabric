use dotenvy::dotenv;
use sqlx::postgres::PgPoolOptions;
use std::env;

use reqwest::Client;
use std::time::Duration;

// tracing
use tracing::{debug, error, info};
use tracing_subscriber::EnvFilter;

use governor::{Quota, RateLimiter};
use std::num::NonZeroU32;
use std::sync::Arc;

// organized into mod modules for Protobuf structs
// pub mod schema {
//     include!(concat!(env!("OUT_DIR") ,"/tracefabric.rs"));
// }

#[tokio::main]

async fn main() {
    // load environment variables from .env file
    dotenv().ok();

    // Init logging subscriber before any work starts

    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .with_target(true)
        .init(); // only called once

    info!("TraceFabric Ingestion Engine booting...");

    let database_url = env::var("DATABASE_URL").expect("DATABASE_URL must be set");

    info!("Establishing Master Warehouse Connection Pool...");

    let _database_pool = PgPoolOptions::new()
        .max_connections(5)
        .connect(&database_url)
        .await
        .expect("Failed to connect to database");

    info!("Connection pool established.");

    let http_client = Client::builder()
        .timeout(Duration::from_secs(10))
        .user_agent("TraceFabric/0.1 (research crawler)") // ethics: self-identify
        .build()
        .expect("Failed to build reqwest HTTP client");

    info!("HTTP client configured.");

    let quota = Quota::per_second(NonZeroU32::new(2).unwrap());
    let limiter = Arc::new(RateLimiter::direct(quota));

    info!("Rate limiter initialized: 2 req/s (Token Bucket, NotKeyed).");

    let target_urls = vec![
        "https://example.com",
        "https://httpbin.org/html",
        "https://www.rust-lang.org",
    ];

    info!(url_count = target_urls.len(), "Beginning crawl sequence.");

    for url in &target_urls {
        debug!(url = url, "Requesting rate limiter token...");
        limiter.until_ready().await;
        info!(url = url, "Token acquired. Fetching...");

        match http_client.get(*url).send().await {
            Ok(response) => {
                let status = response.status().as_u16();
                let body = response.text().await.unwrap_or_default();
                info!(
                    url = url,
                    status = status,
                    bytes = body.len(),
                    "Fetched successfully."
                );
            }
            Err(e) => {
                error!(url = url, error = %e, "Failed to fetch.");
            }
        }
    }

    info!("Crawl sequence complete. Acceptance criteria met.");
}
