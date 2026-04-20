CREATE TABLE leads (
    id UUID PRIMARY KEY,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    company_name TEXT,
    category TEXT,
    source_url TEXT NOT NULL,
    initial_url TEXT,
    final_url TEXT,

    phone_number TEXT,
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    rating REAL,
    rating_count INTEGER,

    place_id TEXT,
    customer_id TEXT,

    http_status INTEGER,
    is_https BOOLEAN,
    redirect_count INTEGER,
    fetch_duration_ms INTEGER,
    response_size_bytes INTEGER,
    content_type TEXT,
    page_title TEXT,
    manifest_url TEXT,

    raw_html TEXT,
    text_content TEXT,

    response_headers JSONB NOT NULL DEFAULT '[]'::jsonb,
    anchor_hrefs JSONB NOT NULL DEFAULT '[]'::jsonb,
    script_srcs JSONB NOT NULL DEFAULT '[]'::jsonb,
    stylesheet_hrefs JSONB NOT NULL DEFAULT '[]'::jsonb,
    robots_txt JSONB NOT NULL DEFAULT '{}'::jsonb,
    sitemap_xml JSONB NOT NULL DEFAULT '{}'::jsonb,

    pipeline_status TEXT NOT NULL DEFAULT 'fetched',
    score REAL NOT NULL DEFAULT 0.0,
    heuristic_flags JSONB NOT NULL DEFAULT '{}'::jsonb,
    deterministic_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    external_enrichments JSONB NOT NULL DEFAULT '{}'::jsonb,
    offer_type TEXT,
    target_industry TEXT,

    is_qualified_lead BOOLEAN NOT NULL DEFAULT FALSE,
    has_booking_widget BOOLEAN,
    is_mobile_optimized BOOLEAN,
    has_clear_contact_info BOOLEAN,
    overall_digital_health TEXT,
    rejection_reason TEXT,
    identified_service_gaps JSONB NOT NULL DEFAULT '[]'::jsonb,
    missing_critical_features JSONB NOT NULL DEFAULT '[]'::jsonb,
    llm_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    full_llm_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_processing_cost REAL NOT NULL DEFAULT 0.0
);
