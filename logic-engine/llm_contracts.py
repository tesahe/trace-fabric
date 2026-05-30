from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


INPUT_PAYLOAD_VERSION = "lead_eval_context.v1"
TIER1_PROMPT_VERSION = "tier1_gate.v1"
TIER1_SCHEMA_VERSION = "tier1_gate_output.v1"
TIER2_PROMPT_VERSION = "tier2_enrichment.v1"
TIER2_SCHEMA_VERSION = "tier2_enrichment_output.v1"
DEFAULT_PROVIDER = "gemini"

MAX_TEXT_SNIPPET_CHARS = 4000
MAX_HTML_SNIPPET_CHARS = 12000


class LlmLeadIdentity(BaseModel):
    lead_id: str = ""
    run_id: str = ""
    source_url: str = ""
    initial_url: str = ""
    final_url: str = ""
    timestamp: str = ""


class LlmBusinessContext(BaseModel):
    campaign_type: str = ""
    target_industry: str = ""
    target_location: str = ""
    discovery_source: str = ""
    company_name: str = ""
    category: str = ""
    phone_number: str = ""
    address: str = ""


class LlmSnippets(BaseModel):
    text_excerpt: str = ""
    html_excerpt: str = ""
    page_title: str = ""


class LeadEvalContext(BaseModel):
    input_payload_version: str = INPUT_PAYLOAD_VERSION
    lead: LlmLeadIdentity
    business: LlmBusinessContext
    pipeline_status: str = ""
    is_qualified_lead: bool = False
    score: float = 0.0
    score_v2: float | None = None
    score_v2_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_evidence: dict[str, Any] = Field(default_factory=dict)
    heuristic_flags: dict[str, Any] = Field(default_factory=dict)
    technologies: list[dict[str, Any]] = Field(default_factory=list)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    provider_provenance: dict[str, Any] = Field(default_factory=dict)
    website_provenance: dict[str, Any] = Field(default_factory=dict)
    robots_txt: dict[str, Any] = Field(default_factory=dict)
    sitemap_xml: dict[str, Any] = Field(default_factory=dict)
    response_headers: list[dict[str, Any]] = Field(default_factory=list)
    anchor_hrefs: list[dict[str, Any]] = Field(default_factory=list)
    snippets: LlmSnippets


def _bounded_str(value: Any, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= limit:
        return value
    return value[:limit]


def build_lead_eval_context(
    *,
    lead_payload: dict[str, Any],
    evaluation: dict[str, Any],
    campaign_type: str,
    target_industry: str,
) -> LeadEvalContext:
    flags = evaluation.get("heuristic_flags") or {}
    technologies = flags.get("technologies")
    structured_data = flags.get("structured_data")

    return LeadEvalContext(
        lead=LlmLeadIdentity(
            lead_id=str(lead_payload.get("id") or ""),
            run_id=str(lead_payload.get("run_id") or ""),
            source_url=str(lead_payload.get("source_url") or ""),
            initial_url=str(lead_payload.get("initial_url") or ""),
            final_url=str(lead_payload.get("final_url") or ""),
            timestamp=str(lead_payload.get("timestamp") or ""),
        ),
        business=LlmBusinessContext(
            campaign_type=campaign_type,
            target_industry=str(target_industry or ""),
            target_location=str(lead_payload.get("target_location") or ""),
            discovery_source=str(lead_payload.get("discovery_source") or ""),
            company_name=str(lead_payload.get("company_name") or ""),
            category=str(lead_payload.get("category") or ""),
            phone_number=str(lead_payload.get("phone_number") or ""),
            address=str(lead_payload.get("address") or ""),
        ),
        pipeline_status=str(evaluation.get("pipeline_status") or ""),
        is_qualified_lead=bool(evaluation.get("is_qualified_lead", False)),
        score=float(evaluation.get("score") or 0.0),
        score_v2=flags.get("score_v2"),
        score_v2_breakdown=list(flags.get("score_v2_breakdown") or []),
        deterministic_evidence=dict(evaluation.get("deterministic_evidence") or {}),
        heuristic_flags=dict(flags),
        technologies=list(technologies or []),
        structured_data=dict(structured_data or {}),
        provider_provenance=dict(lead_payload.get("provider_provenance") or {}),
        website_provenance=dict(lead_payload.get("website_provenance") or {}),
        robots_txt=dict(lead_payload.get("robots_txt") or {}),
        sitemap_xml=dict(lead_payload.get("sitemap_xml") or {}),
        response_headers=list(lead_payload.get("response_headers") or []),
        anchor_hrefs=list(lead_payload.get("anchor_hrefs") or []),
        snippets=LlmSnippets(
            text_excerpt=_bounded_str(lead_payload.get("text_content"), MAX_TEXT_SNIPPET_CHARS),
            html_excerpt=_bounded_str(lead_payload.get("raw_html"), MAX_HTML_SNIPPET_CHARS),
            page_title=str(lead_payload.get("page_title") or ""),
        ),
    )
