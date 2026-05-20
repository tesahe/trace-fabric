mod compliance;
mod discovery;
mod extract;
mod transport;
mod types;
mod cli;
mod pipeline;
mod schema;


use clap::Parser;
use dotenvy::dotenv;
use governor::{Quota, RateLimiter};
use reqwest::Client;
use std::env;
use std::num::NonZeroU32;
use std::sync::Arc;
use std::time::{Duration};
use tokio::sync::mpsc;
use tracing::{error, info};
use tracing_subscriber::EnvFilter;

use discovery::{
    queue_discovery_candidates,
    queue_direct_url_candidate,
};
use types::{DiscoveredCandidate, AppResult};

use transport::run_zmq_sender;
use pipeline::process_candidate;
use cli::{Cli, Command};

#[tokio::main]
async fn main() -> AppResult<()> {
    let cli = Cli::parse();

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
    // (Deprecated: Python backend now handles all persistence)


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

    let zmq_push_addr =
        env::var("ZMQ_PUSH_ADDR").unwrap_or_else(|_| "tcp://127.0.0.1:5555".to_string());

    // ==========================================
    // END OF GLOBAL INITIALIZATION
    // ==========================================

    // ==========================================
    // STAGE 2: DISCOVERY PIPELINE (PRODUCER)
    // ==========================================

    // Backpressure: if scrapers get behind, channel fills to 500 and discovery pauses.
    // tx - transmitter / rx - receiver / mpsc - multi-producer, single-consumer
    let (tx, mut rx) = mpsc::channel::<DiscoveredCandidate>(500);

    match cli.command {
        Command::Discover(args) => {
            let brave_api_key =
                env::var("BRAVE_API_KEY").expect("BRAVE_API_KEY must be set for discover mode");
            let discovery_tx = tx.clone();
            let discovery_client = http_client.clone();

            tokio::spawn(async move {
                if let Err(e) = queue_discovery_candidates(args, discovery_tx, brave_api_key, discovery_client).await
                {
                    error!(error = %e, "Discovery task failed");
                }
            });
        }
        Command::Url(args) => {
            let direct_tx = tx.clone();

            tokio::spawn(async move {
                if let Err(e) = queue_direct_url_candidate(args, direct_tx).await {
                    error!(error = %e, "Direct URL task failed");
                }
            });
        }
    }

    // ==========================================
    // STAGE 3: SCRAPER CONSUMER TASKS
    // ==========================================

    let (zmq_tx, zmq_rx) = std::sync::mpsc::channel::<schema::RawLead>();

    std::thread::spawn(move || run_zmq_sender(zmq_rx, zmq_push_addr));
    info!("ZMQ sender thread spawned");




    // Drop master sender so rx closes when discovery_tx drops
    // NEED this or rx never closes in transport.rs and will silently fail/leak
    drop(tx);

    let mut scraper_tasks = tokio::task::JoinSet::new();

    // will be replaced to jsut call run_zmq_sender and move rx into it

    while let Some(candidate) = rx.recv().await {

        let limiter = rate_limiter.clone();
        let worker_client = http_client.clone();
        let zmq_tx = zmq_tx.clone();

        scraper_tasks.spawn(async move {
            process_candidate(candidate, worker_client, limiter, zmq_tx).await;
        });
    }

    // Drop the original sender so the receiver knows when to stop
    drop(zmq_tx);


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
