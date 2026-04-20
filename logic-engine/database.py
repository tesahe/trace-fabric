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

class ScoredLeadModel(Base):
    """
    Canonical source of truth for a fetched lead and its later evaluation state.
    """
    __tablename__ = "leads"

    # --- IDENTITY / DISCOVERY ---
    id: Mapped[str] = mapped_column(String, primary_key=True)
    company_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_url: Mapped[str] = mapped_column(String)
    initial_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    final_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    timestamp: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Source traceability
    place_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    customer_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Discovery metadata
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Fetch metadata
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_https: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    redirect_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetch_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    page_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Raw artifacts
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_headers: Mapped[list] = mapped_column(JSON, default=list)
    anchor_hrefs: Mapped[list] = mapped_column(JSON, default=list)
    script_srcs: Mapped[list] = mapped_column(JSON, default=list)
    stylesheet_hrefs: Mapped[list] = mapped_column(JSON, default=list)
    robots_txt: Mapped[dict] = mapped_column(JSON, default=dict)
    sitemap_xml: Mapped[dict] = mapped_column(JSON, default=dict)

    # Pipeline / evaluation state
    pipeline_status: Mapped[str] = mapped_column(String, default="fetched")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    heuristic_flags: Mapped[dict] = mapped_column(JSON, default=dict)
    deterministic_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    external_enrichments: Mapped[dict] = mapped_column(JSON, default=dict)
    campaign_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_industry: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Tier 2 / LLM evaluation
    is_qualified_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    has_booking_widget: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_mobile_optimized: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_clear_contact_info: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    overall_digital_health: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    identified_service_gaps: Mapped[list] = mapped_column(JSON, default=list)
    missing_critical_features: Mapped[list] = mapped_column(JSON, default=list)
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
