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

use tokio::sync::mpsc;

use serde::Deserialize;

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


        scraper_tasks.spawn(async move {

            debug!(url = %url, "Requesting rate limiter token...");

            // 2.1. Await Rate Limiter
            limiter.until_ready().await;
            info!(url = %url, "Token acquired. Fetching...");

            //reqwest HTTP GET to the website
            match worker_client.get(&url).send().await {
                Ok(response) => {
                    let status = response.status().as_u16();
                    let html_body = response.text().await.unwrap_or_default();
                    
                    info!(url = %url, status = %status, bytes = html_body.len(), "Fetched successfully");

                    // TODO 
                    // 3. Serialize into Protobuf
                    let payload = schema::RawLead {
                        id: uuid::Uuid::new_v4().to_string(),
                        source_url: url.clone(),
                        company_name: place.title,
                        raw_html: html_body.clone(),
                        timestamp: chrono::Utc::now().to_rfc3339(),

                        phone_number: place.phone_number.unwrap_or_default(),
                        address: place.address,
                        latitude: place.latitude.unwrap_or(0.0), 
                        longitude: place.longitude.unwrap_or(0.0),

                        rating: place.rating.unwrap_or(0.0),
                        rating_count: place.rating_count.unwrap_or(0) as i32,

                        category: place.category.unwrap_or_default(), 
                        customer_id: place.customer_id.unwrap_or_default(), 
                        place_id: place.place_id.unwrap_or_default(),    
                    };


                    // 

                    // Send over ZeroMQ
                    // zmq_socket.send(payload.encode_to_vec()), 0).unwrap();


                }
                Err(e) => {
                    error!(url = %url, error = %e, "Failed to fetch");
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