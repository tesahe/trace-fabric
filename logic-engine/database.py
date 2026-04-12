import os
from dotenv import load_dotenv
from typing import Optional, List



from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, JSON, Boolean, Integer, Text





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
    The canonical source of truth for a processed lead.
    Adheres to the 'No-Drop Ontology', preserving all raw and inferred intelligence.
    """
    __tablename__ = "scored_leads"
    # --- INGESTION PLANE (Serper / Tier 0) ---
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_url: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float) # XGBoost / Initial Score
    company_name: Mapped[str] = mapped_column(String)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Heavy payload
    timestamp: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Enrichment Fields
    phone_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rating_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- PIPELINE STATUS PLANE ---
    pipeline_status: Mapped[str] = mapped_column(String, default="pending")
    heuristic_flags: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- COGNITIVE PLANE (Tier 2 LLM Extraction) ---
    # Boolean Checkboxes mapping directly to Pydantic
    is_qualified_lead: Mapped[bool] = mapped_column(Boolean, default=False)
    has_booking_widget: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_mobile_optimized: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    has_clear_contact_info: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Textual Intelligence
    overall_digital_health: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Structured Findings
    identified_service_gaps: Mapped[list] = mapped_column(JSON, default=list) # outdated_indicators
    missing_critical_features: Mapped[list] = mapped_column(JSON, default=list) # new list from schema

    # The 'Safe-Haven' column (No-Drop Strategy)
    # Store the entire raw LeadExtraction JSON dump here!
    full_llm_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    # Financial Tracking
    llm_processing_cost: Mapped[float] = mapped_column(Float, default=0.0)