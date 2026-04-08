// const IP_ADDRESS: &str = "127.0.0.1:5555"; 
use prost::Message;
use std::time::Instant;

// organized into mod modules for Protobuf structs
pub mod schema {
    include!(concat!(env!("OUT_DIR") ,"/tracefabric.rs"));
}

fn main() {

    println!("Starting Rust ZeroMQ PUSH node...");

    let context = zmq::Context::new();
    let publisher = context.socket(zmq::PUSH).unwrap();

    publisher.bind("tcp://127.0.0.1:5555").expect("Failed to bind socket");

    println!("Bound to tcp://127.0.0.1:5555. Waiting 3 seconds for Python to connect...");
    std::thread::sleep(std::time::Duration::from_secs(3));



    
    // println!("Testing TraceFabric Protobuf Ingestion Pipeline");
    // // dummy test HTML
    let dummy_html = String::from("<html><body><h1>Acme Crop</h1><p>Contact us at 555-0100</p></body></html>");

    // Instantiate a RawLead struct
    let dummy_lead = schema::RawLead {
        id: String::from("lead_999_xyz"),
        source_url: String::from("https://example.com/acme-corp"),
        company_name: String::from("Acme Corp"),
        raw_html: dummy_html,
        timestamp: String::from("2026-04-07T12:00:00Z"),
    };

    // Instantiate a LeadBatch struct
    let batch = schema::LeadBatch {
        leads: vec![dummy_lead],
    };

    println!("Blasting 1000 messages...");
    let start_time = Instant::now();

    for _ in 0..1000 {
        //encode protobuf struct to byte array vec of u8
        let mut byte_buffer = Vec::new();
        batch.encode(&mut byte_buffer).unwrap();

        // send bytes to python over ZeroMQ
        publisher.send(&byte_buffer, 0).unwrap();
    }


    println!("Rust finished sending 1,000 messages in {:?}", start_time.elapsed());
}
