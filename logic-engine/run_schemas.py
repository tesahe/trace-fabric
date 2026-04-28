from typing import Optional
from pydantic import BaseModel, Field, HttpUrl



class CreateDiscoveryRunRequest(BaseModel):
    industry: str = Field(min_length=1)
    location: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=50)
    max_pages: int = Field(default=1, ge=1, le=10)
    campaign_type: str = Field(default="website_modernization")
    llm_enabled: bool = Field(default=False)


class CreateUrlRunRequest(BaseModel):
    website: HttpUrl
    campaign_type: str = Field(default="website_modernization")
    llm_enabled: bool = Field(default=False)
    industry: Optional[str] = None
    location: Optional[str] = None


class RunSummaryResponse(BaseModel):
    id: str
    input_mode: str
    status: str
    target_industry: Optional[str] = None
    target_location: Optional[str] = None
    direct_url: Optional[str] = None
    candidate_limit: Optional[int] = None
    max_pages: Optional[int] = None
    campaign_type: str
    llm_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None  