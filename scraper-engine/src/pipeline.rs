use std::sync::Arc;
use std::sync::mpsc::Sender;
use std::time::Instant;

use scraper::Html;
use tracing::{debug, error, info};

use scraper_engine::compliance::{evaluate_crawl_eligibility, fetch_page_with_limits, fetch_root_file};
use scraper_engine::extract::{
    build_website_provenance_json, extract_address, extract_anchor_hrefs, extract_company_name,
    extract_manifest_url, extract_page_title, extract_phone_number, extract_script_srcs,
    extract_stylesheet_hrefs, extract_text_content, infer_category_from_text,
    select_priority_internal_links, extract_page_signals,
};
use scraper_engine::schema;
use scraper_engine::types::{AppRateLimiter, DiscoveredCandidate};

pub async fn process_candidate(
    candidate: DiscoveredCandidate,
    http_client: reqwest::Client,
    rate_limiter:Arc<AppRateLimiter>,
    zmq_tx: Sender<schema::RawLead>,
) {
    let initial_url = candidate.website_url.clone();
    let fetch_started = Instant::now();
    debug!(url = %initial_url, "Requesting rate limiter token...");

    rate_limiter.until_ready().await;
    info!(url = %initial_url, "Token acquired. Starting compliance check...");

    let robots_txt: Option<schema::RootFile> 
        = fetch_root_file(&http_client, &initial_url, "/robots.txt").await;
    let (crawl_allowed, crawl_disallowed_reason) =
        evaluate_crawl_eligibility(robots_txt.as_ref());

    if !crawl_allowed {
        let payload = schema::RawLead {
            id: uuid::Uuid::new_v4().to_string(),
            timestamp: chrono::Utc::now().to_rfc3339(),
            run_id: candidate.run_id.clone(),

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
            fetch_duration_ms: fetch_started.elapsed().as_millis().min(i32::MAX as u128) as i32,
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

            word_count: 0,
            has_viewport: false,
            has_form: false,
            has_tel_link: false,
            has_mailto_link: false,
            is_parked_domain: false,
            outbound_domain_count: 0,
            schema_org_business_type: String::new(),
            email_address: String::new(),
            meta_description: String::new(),
            social_linkedin: String::new(),
            social_facebook: String::new(),
            social_instagram: String::new(),
            copyright_year: 0,
            has_booking_signal: false,
            has_cta_signal: false,
            has_hours_signal: false,
            has_reviews_signal: false,
            has_contact_page: false,

        };

        info!(
            url = &initial_url,
            reason = &payload.crawl_disallowed_reason,
            "Skipping homepage due to compliance gate."
        );

        if let Err(e) = zmq_tx.send(payload) {
            error!(url = %initial_url, error = %e, "Failed to queue lead for ZMQ sender");
        }
        return;
    }

    info!(url = &initial_url, "Compliance check passed. Fetching homepage...");

    match fetch_page_with_limits(&http_client, &initial_url).await {
        Ok(fetch_result) => {
            let fetch_duration_ms = fetch_started.elapsed().as_millis().min(i32::MAX as u128) as i32;

            let status = fetch_result.status;
            let final_url = fetch_result.final_url;
            let is_https = fetch_result.is_https;
            let redirect_count = fetch_result.redirect_count;
            let content_type = fetch_result.content_type;
            let response_headers = fetch_result.response_headers;
            let html_body = fetch_result.body;
            let response_size_bytes = html_body.len().min(i32::MAX as usize) as i32;

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
                page_signals,
            ) = {
                let document = Html::parse_document(html_body.as_str());

                let text_content = extract_text_content(&document);

                let anchor_hrefs = extract_anchor_hrefs(&document, final_url.as_str());
                let page_signals = extract_page_signals(&document, &text_content, &anchor_hrefs);
                let script_srcs = extract_script_srcs(&document, final_url.as_str());
                let stylesheet_hrefs =
                    extract_stylesheet_hrefs(&document, final_url.as_str());
                let manifest_url = extract_manifest_url(&document, final_url.as_str());

                let page_title = extract_page_title(&document);
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
                    page_signals,
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
                rate_limiter.until_ready().await;

                match fetch_page_with_limits(&http_client, supporting_url.as_str()).await {
                    Ok(supporting_result) => {
                        let supporting_body = supporting_result.body;

                        let (
                            _supporting_page_title,
                            _supporting_text_content,
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

            let sitemap_xml: Option<schema::RootFile> =
                fetch_root_file(&http_client, final_url.as_str(), "/sitemap.xml").await;

            let payload = schema::RawLead {
                id: uuid::Uuid::new_v4().to_string(),
                timestamp: chrono::Utc::now().to_rfc3339(),
                run_id: candidate.run_id.clone(),

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

                word_count: page_signals.word_count,
                has_viewport: page_signals.has_viewport,
                has_form: page_signals.has_form,
                has_tel_link: page_signals.has_tel_link,
                has_mailto_link: page_signals.has_mailto_link,
                is_parked_domain: page_signals.is_parked_domain,
                outbound_domain_count: page_signals.outbound_domain_count,
                schema_org_business_type: page_signals.schema_org_business_type,
                email_address: page_signals.email_address,
                meta_description: page_signals.meta_description,
                social_linkedin: page_signals.social_linkedin,
                social_facebook: page_signals.social_facebook,
                social_instagram: page_signals.social_instagram,
                copyright_year: page_signals.copyright_year,
                has_booking_signal: page_signals.has_booking_signal,
                has_cta_signal: page_signals.has_cta_signal,
                has_hours_signal: page_signals.has_hours_signal,
                has_reviews_signal: page_signals.has_reviews_signal,
                has_contact_page: page_signals.has_contact_page,
            };

            if let Err(e) = zmq_tx.send(payload) {
                error!(url = %initial_url, error = %e, "Failed to queue lead for ZMQ sender");
            }
            //TODO add call to drop(tx) somewhere here., after while loop ends
        }

        Err(e) => {
            error!(url = %initial_url, error = %e, "Failed to fetch within safety limits");
        }
    }
}