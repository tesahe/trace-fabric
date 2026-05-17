#[derive(Debug, Clone)]

// subset of RawLead known at discovery time before HTTP fetch of 
// candidates website.  Before complaicne check, fetch, extract.
pub struct DiscoveredCandidate {
    pub run_id: String,
    pub website_url: String, // known as source url in proto - maybe fix
    pub discovery_source: String,
    pub target_industry: String,
    pub target_location: String,
    pub provider_provenance_json: String,
    pub provider_fsq_id: String,
    pub is_no_website_opportunity: bool, // if business has a website
}
