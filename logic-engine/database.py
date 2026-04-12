import os
from dotenv import load_dotenv

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Float, JSON, Boolean, Integer




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
Base = declarative_base()

# Database schema definition
class ScoredLeadModel(Base):
    """
    The canonical source of truth for a processed lead.
    Maps directly to the Master Data Warehouse table.
    """

    __tablename__ = "scored_leads"

    # SERPER COLUMNS 
    # Map types to match Protobuf + XG boost score
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_url: Mapped[str] = mapped_column(String)
    score: Mapped[float] = mapped_column(Float)
    company_name: Mapped[str] = mapped_column(String)
    raw_html: Mapped[str] = mapped_column(String)
    # TEMP because of large size - will be moved to object storage later
    timestamp: Mapped[str] = mapped_column(String)

    # New SERPER Columns
    phone_number: Mapped[str] = mapped_column(String, nullable=True)
    address: Mapped[str] = mapped_column(String, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=True)
    customer_id: Mapped[str] = mapped_column(String, nullable=True)
    place_id: Mapped[str] = mapped_column(String, nullable=True)

    # Sprint 2 

    # Pipeline status as no rows are Dropped

    pipeline_status: Mapped[str] = mapped_column(String, default="pending")


    # Deterministic Layer (Regex, Substring, etc)
    heuristic_flags: Mapped[dict] = mapped_column(JSON, default=dict)


    # Probabilistic Layer (LLM Outputs)
    # Built to mirror Pydantic schema exactly, nullable

    has_booking_widget: Mapped[bool] = mapped_column(Boolean, nullable=True)
    year_founded: Mapped[int] = mapped_column(Integer, nullable=True)
    contact_email: Mapped[str] = mapped_column(String, nullable=True)
    identified_service_gaps: Mapped[list] = mapped_column(JSON, default=list)

    # Financial Tracking
    llm_processing_cost: Mapped[float] = mapped_column(Float, default = 0.0)



