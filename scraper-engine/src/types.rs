#[derive(Debug, Clone)]
pub struct DiscoveredCandidate {
    pub run_id: String,
    pub website_url: String,
    pub discovery_source: String,
    pub target_industry: String,
    pub target_location: String,
    pub provider_provenance_json: String,
    pub provider_fsq_id: String,
    pub is_no_website_opportunity: bool,
}
