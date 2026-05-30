from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ServiceGaps(BaseModel):
    has_online_booking: bool = Field(
        default=False,
        description="True if the business allows customers to book or purchase directly on the website, waitlist, or forms.",
    )
    is_mobile_optimized: bool = Field(
        default=False,
        description="True if the website is clearly structured with mobile responsiveness in mind.",
    )
    has_clear_contact_info: bool = Field(
        default=False,
        description="True if phone numbers, emails, or physical addresses are easily accessible.",
    )
    outdated_indicators: list[str] = Field(
        default_factory=list,
        description="Specific reasons the site appears outdated.",
    )
    missing_critical_features: list[str] = Field(
        default_factory=list,
        description="Features standard to this industry that are noticeably absent.",
    )


class BusinessProfile(BaseModel):
    business_name: str | None = Field(
        default=None,
        description="The formal name of the business as extracted from the page.",
    )
    category: str | None = Field(default=None)
    phone_number: str | None = Field(default=None)
    address: str | None = Field(default=None)
    website_url: str | None = Field(default=None)


class Tier2EnrichmentOutput(BaseModel):
    business_profile: BusinessProfile
    service_gaps: ServiceGaps
    niche_attributes: dict[str, Any] = Field(default_factory=dict)
    operator_summary: str = Field(
        description="A concise UI-safe summary of the business and the extracted opportunities."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0.",
    )


class LeadExtraction(BaseModel):
    """Legacy alias retained for compatibility with older imports/tests."""

    business_name: str | None = Field(default=None)
    confidence_score: float = Field(ge=0.0, le=1.0)
    service_gaps: ServiceGaps
    overall_digital_health: str
    is_qualified_lead: bool
    rejection_reason: str | None = Field(default=None)
