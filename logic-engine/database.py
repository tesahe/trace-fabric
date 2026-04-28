import os
from dotenv import load_dotenv
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, JSON, Boolean, Integer, Text, DateTime, func





# load variables from .env

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# Step by step below

# 1) Establish connection pool, echo=false so it doesn't print every SQL query
engine = create_async_engine(DATABASE_URL, echo=False)

# 2) Create session factory (like a blueprint for sessions)
AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False
)

# 3) Base class for all models
class Base(AsyncAttrs, DeclarativeBase):
    pass


# Database schema definition

class EvaluationRunModel(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    input_mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="queued", nullable=False)

    target_industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_location: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    direct_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidate_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    campaign_type: Mapped[str] = mapped_column(String, nullable=False)
    llm_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[Optional[str]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[str]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ScoredLeadModel(Base):
    """
    Canonical durable lead record centered on first-party website crawl data,
    with explicit discovery provenance and crawl compliance state.
    """
    __tablename__ = "leads"

    # --- identity / routing ---
    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    run_id: Mapped[Optional[str]] = mapped_column(String, nullable=True) # nullable is temp

    source_url: Mapped[str] = mapped_column(String, nullable=False)
    initial_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    final_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- discovery / provenance / compliance ---
    discovery_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_location: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    crawl_allowed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    crawl_disallowed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_no_website_opportunity: Mapped[bool] = mapped_column(Boolean, default=False)

    provider_fsq_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    provider_provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    website_provenance: Mapped[dict] = mapped_column(JSON, default=dict)

    location_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    category_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # --- website-derived business fields only ---
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- fetch metadata ---
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_https: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    redirect_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetch_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- durable website crawl artifacts ---
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_headers: Mapped[list] = mapped_column(JSON, default=list)
    anchor_hrefs: Mapped[list] = mapped_column(JSON, default=list)
    script_srcs: Mapped[list] = mapped_column(JSON, default=list)
    stylesheet_hrefs: Mapped[list] = mapped_column(JSON, default=list)
    robots_txt: Mapped[dict] = mapped_column(JSON, default=dict)
    sitemap_xml: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- deterministic / workflow state ---
    pipeline_status: Mapped[str] = mapped_column(String, default="discovered")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    heuristic_flags: Mapped[dict] = mapped_column(JSON, default=dict)
    deterministic_evidence: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- qualification outputs ---
    is_qualified_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    has_booking_widget: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_mobile_optimized: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_clear_contact_info: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    overall_digital_health: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    identified_service_gaps: Mapped[list] = mapped_column(JSON, default=list)
    missing_critical_features: Mapped[list] = mapped_column(JSON, default=list)

    # --- optional later-stage ML / LLM state ---
    llm_output: Mapped[dict] = mapped_column(JSON, default=dict)
    full_llm_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    llm_processing_cost: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[Optional[str]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[str]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

