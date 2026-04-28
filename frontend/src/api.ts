/**
 * api.ts — thin wrapper around the logic-engine REST API.
 * Base URL is proxied through Vite (/api → http://localhost:8000) in dev.
 */

const BASE = import.meta.env.VITE_API_URL ?? "/api";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    throw new Error("Backend offline — start the logic-engine server");
  }

  // Vite returns its SPA index.html (200 OK, text/html) when the proxy target
  // is unreachable. Detect that and surface a friendly message.
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    throw new Error("Backend offline — start the logic-engine server");
  }

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

// ── Leads ─────────────────────────────────────────────────────────────────

export interface ApiLead {
  id: string;
  created_at: string;
  timestamp?: string;
  source_url: string;
  initial_url?: string;
  final_url?: string;
  discovery_source?: string;
  target_industry?: string;
  target_location?: string;
  company_name?: string;
  category?: string;
  phone_number?: string;
  address?: string;
  pipeline_status: string;
  score: number | null;
  is_qualified_lead: boolean | null;
  rejection_reason?: string;
  overall_digital_health?: string;
  heuristic_flags?: unknown;
  deterministic_evidence?: unknown;
  identified_service_gaps?: string[];
  missing_critical_features?: string[];
  crawl_allowed?: boolean;
  crawl_disallowed_reason?: string;
  http_status?: number;
  is_https?: boolean;
  redirect_count?: number;
  content_type?: string;
  page_title?: string;
  provider_provenance?: unknown;
  website_provenance?: unknown;
  robots_txt?: string;
  sitemap_xml?: string;
}

export interface ApiLeadList {
  count: number;
  items: ApiLead[];
}

export function fetchRecentLeads(limit = 50): Promise<ApiLeadList> {
  return apiFetch<ApiLeadList>(`/leads/recent?limit=${limit}`);
}

export function fetchLeadById(id: string): Promise<ApiLead> {
  return apiFetch<ApiLead>(`/leads/${id}`);
}

// ── Runs ───────────────────────────────────────────────────────────────────

export interface ApiRun {
  id: string;
  input_mode: string;
  status: string;
  target_industry?: string;
  target_location?: string;
  direct_url?: string;
  candidate_limit?: number;
  max_pages?: number;
  campaign_type?: string;
  llm_enabled?: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ApiRunList {
  count: number;
  items: ApiRun[];
}

export interface ApiRunLeadList {
  run_id: string;
  count: number;
  items: ApiLead[];
}

export function fetchRecentRuns(limit = 10): Promise<ApiRunList> {
  return apiFetch<ApiRunList>(`/runs?limit=${limit}`);
}

export function fetchRunById(runId: string): Promise<ApiRun> {
  return apiFetch<ApiRun>(`/runs/${runId}`);
}

export function fetchLeadsForRun(runId: string, limit = 50): Promise<ApiRunLeadList> {
  return apiFetch<ApiRunLeadList>(`/runs/${runId}/leads?limit=${limit}`);
}

// ── Run creation ───────────────────────────────────────────────────────────

export interface CreateRunResult {
  run_id: string;
  status: string;
}

export function startDiscoveryRun(payload: {
  industry: string;
  location: string;
  limit: number;
  max_pages?: number;
  campaign_type?: string;
  llm_enabled?: boolean;
}): Promise<CreateRunResult> {
  return apiFetch<CreateRunResult>("/runs/discovery", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function startUrlRun(payload: {
  website: string;
  industry?: string;
  location?: string;
  campaign_type?: string;
  llm_enabled?: boolean;
}): Promise<CreateRunResult> {
  return apiFetch<CreateRunResult>("/runs/url", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
