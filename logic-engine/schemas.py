from pydantic import BaseModel, Field
from typing import List, Optional



class ServiceGaps(BaseModel):
    has_online_booking: bool = Field(
        description="True if the business allows customers to book or purchase directly on the website, waitlist, or forms."
    )
    is_mobile_optimized: bool = Field(
        description="True if the website is clearly structured with mobile responsiveness in mind."
    )
    has_clear_contact_info: bool = Field(
        description="True if phone numbers, emails, or physical addresses are easily accessible."
    )
    outdated_indicators: List[str] = Field(
        default_factory=list,
        description="Specific reasons the site appears outdated (e.g., 'Copyright 2014', 'Flash elements', 'Broken images'). Return an empty list if modern."
    )
    missing_critical_features: List[str] = Field(
        default_factory=list,
        description="Features standard to this industry that are noticeably absent (e.g., 'No menu PDF', 'No pricing table')."
    )

class LeadExtraction(BaseModel):
    business_name: Optional[str] = Field(
        default=None, 
        description="The formal name of the business as extracted from the page."
    )
    confidence_score: float = Field(
        ge=0.0, le=1.0, 
        description="Your confidence from 0.0 to 1.0 that this page represents a legitimate, operational business."
    )
    service_gaps: ServiceGaps = Field(
        description="Detailed breakdown of digital presence deficiencies."
    )
    overall_digital_health: str = Field(
        description="A one-sentence summary of the business's digital footprint. E.g., 'Strong local presence but critically missing e-commerce capabilities.'"
    )
    is_qualified_lead: bool = Field(
        description="Set to True ONLY IF significant service gaps exist where we can definitively provide technical value."
    )
    rejection_reason: Optional[str] = Field(
        default=None,
        description="If is_qualified_lead is False, provide the exact reason why (e.g., 'Site is highly optimized', 'Business appears closed')."
    )
