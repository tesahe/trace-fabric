import type { ApiLead, ApiRunLeadList } from "./api";
import type {
  DeterministicEvidence,
  HeuristicFlags,
  InputMode,
  Lead,
  PipelineStage,
  PipelineStatus,
  StageState,
} from "./types";

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
  const persistedState: StageState     = isQualified ? "done"   : "skipped";

  return [
    { key: "discovered",    label: "Discovered",    state: "done",             value: raw.source_url },
    { key: "compliance",    label: "Compliance",    state: complianceState,    reason: ev.crawl_disallowed_reason },
    { key: "heuristic",     label: "Heuristic",     state: heuristicState },
    { key: "deterministic", label: "Deterministic", state: deterministicState, value: raw.overall_digital_health },
    { key: "tier1",         label: "Tier 1 (LLM)", state: "skipped" },
    { key: "tier2",         label: "Tier 2 (LLM)", state: "skipped" },
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

        // UI-only constructed fields
        pipeline: buildPipeline(raw),
        tier1:    { state: "skipped" },
        tier2:    { state: "skipped" },
        totalMs:  null,

        // Timestamp
        createdAt: raw.created_at,    
    };
}

export function adaptRunLeads(result: ApiRunLeadList, inputMode: InputMode = "discover"): Lead[] {
    return result.items.map((item, i) => adaptLead(item, i, result.run_id, inputMode))
}

export function adaptRunLeadList(items: ApiLead[]): Lead[] {
    return items.map((item, i) => adaptLead(item, i));
}

