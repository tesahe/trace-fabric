import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ModeTabs } from "../components/ModeTabs";
import { Panel } from "../components/Panel";
import { ResultsTable } from "../components/ResultsTable";
import { DetailDrawer } from "../components/DetailDrawer";
import { adaptRunLeadList } from "../adapters";
import type { InputMode, Lead } from "../types";
import {
  startDiscoveryRun,
  startUrlRun,
  fetchRunById,
  fetchLeadsForRun,
} from "../api";
import type { ApiLead, ApiRun } from "../api";

const POLL_INTERVAL_MS = 2500;
const SUPPORTED_MODES: InputMode[] = ["discover", "url"];

export function RunConsole() {
  const [params, setParams] = useSearchParams();
  const rawMode = params.get("mode") as InputMode;
  const initialMode: InputMode = SUPPORTED_MODES.includes(rawMode) ? rawMode : "discover";
  const [mode, setMode] = useState<InputMode>(initialMode);

  const [niche, setNiche] = useState("wedding photographers");
  const [location, setLocation] = useState("Austin, TX");
  const [maxSites, setMaxSites] = useState(10);
  const [siteUrl, setSiteUrl] = useState("");

  const [run, setRun] = useState<ApiRun | null>(null);
  const [rawLeads, setRawLeads] = useState<ApiLead[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const leads = useMemo(() => adaptRunLeadList(rawLeads), [rawLeads]);

  useEffect(() => {
    setParams((p) => {
      p.set("mode", mode);
      return p;
    });
  }, [mode, setParams]);

  useEffect(() => {
    return () => {
      if (pollRef.current != null) clearInterval(pollRef.current);
    };
  }, []);

  function changeMode(m: InputMode) {
    if (!SUPPORTED_MODES.includes(m)) return;
    setMode(m);
  }

  const pollRun = useCallback(async (runId: string) => {
    try {
      const [runData, leadsData] = await Promise.all([
        fetchRunById(runId),
        fetchLeadsForRun(runId, 50),
      ]);
      setRun(runData);
      setRawLeads(leadsData.items);
      if (runData.status === "completed" || runData.status === "failed") {
        if (pollRef.current != null) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    } catch (err) {
      setError((err as Error).message);
      if (pollRef.current != null) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
  }, []);

  async function startRun() {
    if (pollRef.current != null) clearInterval(pollRef.current);
    pollRef.current = null;
    setSubmitting(true);
    setError(null);
    setRawLeads([]);
    setSelectedLead(null);

    try {
      let result: { run_id: string; status: string };
      if (mode === "discover") {
        result = await startDiscoveryRun({ industry: niche, location, limit: maxSites });
      } else {
        result = await startUrlRun({ website: siteUrl });
      }
      await pollRun(result.run_id);
      pollRef.current = setInterval(() => pollRun(result.run_id), POLL_INTERVAL_MS);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  const isRunning = run != null && (run.status === "running" || run.status === "queued");

  const counters = useMemo(() => {
    const persisted = leads.filter((l) => l.pipelineStatus === "qualified_deterministic").length;
    const rejected = leads.filter((l) => l.pipelineStatus === "rejected_deterministic").length;
    const skipped = leads.filter((l) => l.pipelineStatus.startsWith("excluded_")).length;
    const failed = leads.filter((l) => l.pipelineStatus === "failed").length;
    return { discovered: leads.length, rejected, skipped, failed, persisted };
  }, [leads]);

  return (
    <div className="app">
      <PageHeader pageLabel="Run Console" />
      <main className="app-main row-gap-4" style={{ paddingTop: 16 }}>
        <ModeTabs value={mode} onChange={changeMode} />

        <Panel title={mode === "discover" ? "Discover leads" : "Evaluate URL"}>
          {mode === "discover" && (
            <>
              <div className="form-row">
                <div className="form-field">
                  <label className="form-field__label">Niche</label>
                  <input className="form-field__input" value={niche} onChange={(e) => setNiche(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-field__label">Location</label>
                  <input className="form-field__input" value={location} onChange={(e) => setLocation(e.target.value)} />
                </div>
                <div className="form-field">
                  <label className="form-field__label">Max sites</label>
                  <input
                    className="form-field__input tabular"
                    type="number"
                    min={5}
                    max={25}
                    value={maxSites}
                    onChange={(e) => setMaxSites(Math.max(5, Math.min(25, Number(e.target.value) || 10)))}
                  />
                </div>
                <button className="btn btn--primary" onClick={startRun} disabled={isRunning || submitting}>
                  {submitting ? "Starting…" : isRunning ? "Running…" : "Run discovery"}
                </button>
              </div>
              <div className="form-helper">
                Discovers up to N candidate sites, applies deterministic evidence checks, then routes selected cases to Tier 1 / Tier 2.
              </div>
            </>
          )}

          {mode === "url" && (
            <>
              <div className="form-row form-row--single">
                <div className="form-field">
                  <label className="form-field__label">Site URL</label>
                  <input
                    className="form-field__input mono"
                    placeholder="https://example.com"
                    value={siteUrl}
                    onChange={(e) => setSiteUrl(e.target.value)}
                  />
                </div>
                <button className="btn btn--primary" onClick={startRun} disabled={!siteUrl || isRunning || submitting}>
                  {submitting ? "Starting…" : isRunning ? "Running…" : "Evaluate site"}
                </button>
              </div>
              <div className="form-helper">
                Skips discovery. Runs the full evaluation pipeline on a single known site.
              </div>
            </>
          )}
        </Panel>

        {error && (
          <div className="empty-state" style={{ color: "var(--color-danger, #f66)" }}>
            API error: {error}
          </div>
        )}

        {run && (
          <div className="run-strip">
            <span className="run-strip__id">Run #{run.id.slice(0, 8)}</span>
            <span className="run-strip__sep">·</span>
            <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{run.input_mode}</span>
            <span className="run-strip__sep">·</span>
            <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {run.input_mode === "url"
                ? `url=${run.direct_url}`
                : `niche="${run.target_industry}" loc="${run.target_location}"`}
            </span>
            <span className="run-strip__sep">·</span>
            <span className={`status status--${isRunning ? "running" : run.status === "completed" ? "qualified_deterministic" : "failed"}`}>
              <span className="status__dot" />
              <span>{run.status}</span>
            </span>
            <div className="run-strip__counters">
              <span className="stat-chip"><span className="stat-chip__label">discovered:</span><span className="stat-chip__value">{counters.discovered}</span></span>
              <span className="stat-chip"><span className="stat-chip__label">rejected:</span><span className="stat-chip__value">{counters.rejected}</span></span>
              <span className="stat-chip"><span className="stat-chip__label">persisted:</span><span className="stat-chip__value">{counters.persisted}</span></span>
              <span className="stat-chip"><span className="stat-chip__label">failed:</span><span className="stat-chip__value">{counters.failed}</span></span>
            </div>
          </div>
        )}

        {leads.length > 0 && (
          <ResultsTable
            leads={leads}
            selectedId={selectedLead?.id ?? null}
            onSelect={setSelectedLead}
          />
        )}
      </main>

      {selectedLead && (
        <DetailDrawer
          lead={selectedLead}
          onClose={() => setSelectedLead(null)}
        />
      )}
    </div>
  );
}
