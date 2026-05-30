import type { ApiLead, ApiRunLeadList } from "./api";
import type {
  DeterministicEvidence,
  HeuristicFlags,
  InputMode,
  Lead,
  PipelineStage,
  PipelineStatus,
  StageState,
  TierResult,
  TierState,
} from "./types";

function tierStageState(tierResult: unknown): StageState {
  if (!tierResult || typeof tierResult !== "object" || !("status" in (tierResult as object))) {
    return "skipped";
  }
  const status = String((tierResult as Record<string, unknown>).status ?? "");
  if (!status || status.includes("skipped")) return "skipped";
  if (status.includes("passed") || status.includes("complete")) return "done";
  if (status.includes("rejected") || status.includes("failed")) return "rejected";
  if (status.includes("queued") || status.includes("running")) return "running";
  return "pending";
}

function adaptTierResult(raw: unknown): TierResult {
  if (!raw || typeof raw !== "object" || !("status" in (raw as object))) {
    return { state: "skipped" };
  }
  const r = raw as Record<string, unknown>;
  const status = String(r.status ?? "");

  let state: TierState;
  if (!status || status.includes("skipped")) state = "skipped";
  else if (status.includes("passed") || status.includes("complete")) state = "passed";
  else if (status.includes("rejected") || status.includes("failed")) state = "failed";
  else if (status.includes("queued") || status.includes("running")) state = "running";
  else state = "pending";

  const normalized = r.normalized_output as Record<string, unknown> | null | undefined;
  const tokens = r.tokens as Record<string, number> | null | undefined;

  return {
    state,
    model: r.model as string | undefined,
    promptVersion: r.prompt_version as string | undefined,
    latencyMs: r.latency_ms as number | undefined,
    tokens: tokens
      ? {
          in: tokens.input_tokens ?? tokens.prompt_tokens ?? 0,
          out: tokens.output_tokens ?? tokens.completion_tokens ?? 0,
        }
      : undefined,
    rationale: normalized?.rationale_short as string | undefined,
    output: normalized ?? undefined,
    raw: r.raw_validated_output,
    reason: r.provider_error
      ? String(
          (r.provider_error as Record<string, unknown>).message
            ?? JSON.stringify(r.provider_error),
        )
      : undefined,
  };
}

function extractHost(url: string): string {
    try {
        return new URL(url).hostname;
    } catch {
        return url;
    }
}

function buildPipeline(raw: ApiLead): PipelineStage[] {
  const s = raw.pipeline_status ?? "";
  const ev = (raw.deterministic_evidence ?? {}) as DeterministicEvidence;

  const crawlOk = ev.crawl_allowed !== false;
  const isExcluded = s.startsWith("excluded_");
  const isQualified = raw.is_qualified_lead === true;

  const complianceState: StageState    = crawlOk    ? "done"    : "rejected";
  const heuristicState: StageState     = isExcluded ? "skipped" : crawlOk ? "done" : "skipped";
  const deterministicState: StageState = isExcluded ? "skipped" : isQualified ? "done" : "rejected";
  const tier1Stage                     = tierStageState(raw.tier1_result);
  const tier2Stage                     = tierStageState(raw.tier2_result);
  const persistedState: StageState     =
    s === "tier2_complete" || s === "qualified_deterministic" ? "done" : "skipped";

  return [
    { key: "discovered",    label: "Discovered",    state: "done",             value: raw.source_url },
    { key: "compliance",    label: "Compliance",    state: complianceState,    reason: ev.crawl_disallowed_reason },
    { key: "heuristic",     label: "Heuristic",     state: heuristicState },
    { key: "deterministic", label: "Deterministic", state: deterministicState, value: raw.overall_digital_health },
    { key: "tier1",         label: "Tier 1 (LLM)",  state: tier1Stage },
    { key: "tier2",         label: "Tier 2 (LLM)",  state: tier2Stage },
    { key: "persisted",     label: "Persisted",     state: persistedState },
  ];
}

export function adaptLead(
    raw:ApiLead,
    index: number,
    runId: string = "",
    inputMode: InputMode = "discover",

): Lead {
    const url = raw.source_url ?? raw.initial_url ?? "";

    return {
        id: raw.id,
        index,
        runId,
        inputMode,
        mode: "live",

        sourceUrl:     url,
        sourceHost:    extractHost(url),
        pageTitle:     raw.page_title,
        companyName:   raw.company_name,

        // Classification
        targetIndustry: raw.target_industry ?? "unknown",
        targetLocation: raw.target_location ?? "unknown",

        // Evaluation results — snake_case → camelCase
        pipelineStatus:       raw.pipeline_status as PipelineStatus,
        score:                raw.score,
        isQualifiedLead:      raw.is_qualified_lead,
        rejectionReason:      raw.rejection_reason,
        overallDigitalHealth: raw.overall_digital_health,

        // Evidence — cast unknown → typed interfaces
        deterministicEvidence: (raw.deterministic_evidence ?? {}) as DeterministicEvidence,
        heuristicFlags:        (raw.heuristic_flags ?? {}) as HeuristicFlags,
        identifiedServiceGaps:  raw.identified_service_gaps  ?? [],
        missingCriticalFeatures: raw.missing_critical_features ?? [],

        // Rust-extracted signal columns (top-level DB fields)
        wordCount:             raw.word_count,
        hasViewport:           raw.has_viewport,
        hasTelLink:            raw.has_tel_link,
        hasMailtoLink:         raw.has_mailto_link,
        isParkedDomain:        raw.is_parked_domain,
        outboundDomainCount:   raw.outbound_domain_count,
        schemaOrgBusinessType: raw.schema_org_business_type,
        emailAddress:          raw.email_address,
        metaDescription:       raw.meta_description,
        socialLinkedin:        raw.social_linkedin,
        socialFacebook:        raw.social_facebook,
        socialInstagram:       raw.social_instagram,
        copyrightYear:         raw.copyright_year,

        // UI-only constructed fields
        pipeline: buildPipeline(raw),
        tier1: adaptTierResult(raw.tier1_result),
        tier2: adaptTierResult(raw.tier2_result),
        totalMs:  null,

        // Timestamp
        createdAt: raw.created_at,    
    };
}

export function adaptRunLeads(result: ApiRunLeadList, inputMode: InputMode = "discover"): Lead[] {
    return result.items.map((item, i) => adaptLead(item, i, result.run_id, inputMode))
}

export function adaptRunLeadList(items: ApiLead[]): Lead[] {
    return items.map((item, i) => adaptLead(item, i, item.run_id ?? ""));
}

