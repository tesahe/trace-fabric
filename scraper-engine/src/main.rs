
// organized into mod modules for Protobuf structs
pub mod schema {
    include!(concat!(env!("OUT_DIR") ,"/tracefabric.rs"));
}

fn main() {
    println!("Testing TraceFabric Protobuf Ingestion Pipeline");

    // dummy test HTML
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


    println!("Successfully instantiated Protobuf Message:\n{:#?}", batch);
}
