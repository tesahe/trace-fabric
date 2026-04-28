export type LeadStatus = "running" | "persisted" | "rejected" | "skipped" | "failed";
export type StageState = "pending" | "running" | "done" | "skipped" | "rejected" | "failed";
export type TierState = "skipped" | "passed" | "failed" | "running" | "pending";
export type RunMode = "discover" | "url" | "replay";

export interface EvidenceSignal {
  key: string;
  label: string;
  ok: boolean;
  detail?: string;
}

export interface PipelineStage {
  key:
    | "discovered"
    | "compliance"
    | "heuristic"
    | "deterministic"
    | "tier1"
    | "tier2"
    | "persisted";
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

export interface Lead {
  id: string;
  index: number;
  host: string;
  url: string;
  title?: string;
  niche: string;
  location: string;
  runId: string;
  runType: RunMode;
  mode: "live" | "replay";
  status: LeadStatus;
  score: number | null;
  evidence: EvidenceSignal[];
  decisionReason: string;
  totalMs: number | null;
  pipeline: PipelineStage[];
  tier1: TierResult;
  tier2: TierResult;
  qualification?: "qualified" | "unqualified" | "needs-review";
  persistedAt?: string;
  schemaVersion?: string;
  pipelineVersion?: string;
  gitSha?: string;
  fixtureId?: string;
  finalOutput?: Record<string, unknown>;
}
