// ── Backend-mirrored status types ─────────────────────────────────────────

// Matches pipeline_status values from deterministic_evaluator.py
export type PipelineStatus =
  | "qualified_deterministic"
  | "rejected_deterministic"
  | "excluded_no_website_opportunity"
  | "excluded_crawl_disallowed"
  | "running"   // UI-only: lead is live in-progress
  | "failed";   // UI-only: fetch or process error

// Matches status field on EvaluationRunModel
export type RunStatus = "queued" | "running" | "completed" | "failed";

// Matches input_mode field on EvaluationRunModel ("replay" is UI-only)
export type InputMode = "discover" | "url" | "replay";

// ── UI-only visualization types ────────────────────────────────────────────

export type StageState = "pending" | "running" | "done" | "skipped" | "rejected" | "failed";
export type TierState  = "skipped" | "passed"  | "failed" | "running" | "pending";

export interface PipelineStage {
  key: "discovered" | "compliance" | "heuristic" | "deterministic" | "tier1" | "tier2" | "persisted";
  label: string;
  state: StageState;
  value?: string;
  reason?: string;
  meta?: Record<string, string | number>;
}

export interface TierResult {
  state: TierState;
  reason?: string;
  promptVersion?: string;
  model?: string;
  latencyMs?: number;
  tokens?: { in: number; out: number };
  rationale?: string;
  raw?: unknown;
  output?: Record<string, unknown>;
}

// UI display helper — built from DeterministicEvidence in components
export interface EvidenceSignal {
  key: string;
  label: string;
  ok: boolean;
  detail?: string;
}

// ── Backend-mirrored data interfaces ──────────────────────────────────────

// Mirrors deterministic_evidence dict from deterministic_evaluator.py
export interface DeterministicEvidence {
  source_host?: string;
  discovery_source?: string;
  crawl_allowed?: boolean;
  crawl_disallowed_reason?: string;
  is_no_website_opportunity?: boolean;
  robots_txt_accessible?: boolean;
  sitemap_xml_accessible?: boolean;
  has_contact_page?: boolean;
  has_privacy_policy?: boolean;
  has_contact_form?: boolean;
  has_cta?: boolean;
  has_booking_widget?: boolean;
  has_hours_signal?: boolean;
  has_reviews_signal?: boolean;
}

// Mirrors heuristic_flags dict from deterministic_evaluator.py
export interface HeuristicFlags {
  campaign_type?: string;
  target_industry?: string;
  is_real_business_deterministic?: boolean;
  word_count?: number;
  rejection_signature?: string;
  parked_domain?: boolean;
}

// Mirrors ScoredLeadModel / lead API responses
export interface Lead {
  // Identity
  id: string;
  index: number;                          // UI-only: position in list
  runId: string;                          // FK → EvaluationRunModel.id
  inputMode: InputMode;                   // mirrors run's input_mode
  mode: "live" | "replay";               // UI-only

  // Source
  sourceUrl: string;                      // source_url
  sourceHost: string;                     // derived from source_url
  pageTitle?: string;                     // page_title
  companyName?: string;                   // company_name

  // Classification
  targetIndustry: string;                 // target_industry
  targetLocation: string;                 // target_location

  // Evaluation results
  pipelineStatus: PipelineStatus;         // pipeline_status
  score: number | null;
  isQualifiedLead: boolean | null;        // is_qualified_lead
  rejectionReason?: string;              // rejection_reason
  overallDigitalHealth?: string;         // overall_digital_health

  // Evidence
  deterministicEvidence: DeterministicEvidence;   // deterministic_evidence
  heuristicFlags: HeuristicFlags;                 // heuristic_flags
  identifiedServiceGaps: string[];               // identified_service_gaps
  missingCriticalFeatures: string[];             // missing_critical_features

  // UI-only derived fields
  pipeline: PipelineStage[];
  tier1: TierResult;
  tier2: TierResult;
  totalMs: number | null;

  // Timestamps
  createdAt: string;                      // created_at

  // Replay-only
  fixtureId?: string;
}

// Mirrors EvaluationRunModel / RunSummaryResponse
export interface Run {
  id: string;
  inputMode: InputMode;                   // input_mode
  status: RunStatus;
  targetIndustry?: string;               // target_industry
  targetLocation?: string;               // target_location
  directUrl?: string;                    // direct_url
  candidateLimit?: number;               // candidate_limit
  maxPages?: number;                     // max_pages
  campaignType: string;                  // campaign_type
  llmEnabled: boolean;                   // llm_enabled
  createdAt: string;                     // created_at
  updatedAt?: string;                    // updated_at
}
