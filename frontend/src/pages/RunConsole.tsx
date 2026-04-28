import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { ModeTabs } from "../components/ModeTabs";
import { Panel } from "../components/Panel";
import type { RunMode } from "../types";
import {
  startDiscoveryRun,
  startUrlRun,
  fetchRunById,
  fetchLeadsForRun,
} from "../api";
import type { ApiLead, ApiRun } from "../api";

const POLL_INTERVAL_MS = 2500;

// Only real run modes — replay removed until backend fixture API is wired
const SUPPORTED_MODES: RunMode[] = ["discover", "url"];

export function RunConsole() {
  const [params, setParams] = useSearchParams();
  const rawMode = params.get("mode") as RunMode;
  const initialMode: RunMode = SUPPORTED_MODES.includes(rawMode) ? rawMode : "discover";
  const [mode, setMode] = useState<RunMode>(initialMode);

  // Form fields
  const [niche, setNiche] = useState("wedding photographers");
  const [location, setLocation] = useState("Austin, TX");
  const [maxSites, setMaxSites] = useState(10);
  const [siteUrl, setSiteUrl] = useState("");

  // Runtime state
  const [run, setRun] = useState<ApiRun | null>(null);
  const [leads, setLeads] = useState<ApiLead[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  function changeMode(m: RunMode) {
    // Drop replay if it somehow arrives (e.g. stale URL param)
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
      setLeads(leadsData.items);
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
    setLeads([]);
    setSelectedId(null);

    try {
      let result: { run_id: string; status: string };

      if (mode === "discover") {
        result = await startDiscoveryRun({
          industry: niche,
          location,
          limit: maxSites,
        });
      } else {
        // url mode
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
    const persisted = leads.filter((l) => l.pipeline_status === "persisted").length;
    const rejected = leads.filter((l) => l.pipeline_status === "rejected").length;
    const skipped = leads.filter((l) => l.pipeline_status === "skipped").length;
    const failed = leads.filter((l) => l.pipeline_status === "failed").length;
    return { discovered: leads.length, rejected, skipped, failed, persisted };
  }, [leads]);

  const selectedLead = leads.find((l) => l.id === selectedId) || null;

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
            <span className={`status status--${isRunning ? "running" : run.status === "completed" ? "persisted" : "failed"}`}>
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
          <div className="dense-table-wrap">
            <table className="dense-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Site / Company</th>
                  <th className="col-status">Status</th>
                  <th className="col-score">Score</th>
                  <th>Qualified</th>
                </tr>
              </thead>
              <tbody>
                {leads.map((l, i) => (
                  <tr
                    key={l.id}
                    className={selectedId === l.id ? "row--selected" : ""}
                    onClick={() => setSelectedId(selectedId === l.id ? null : l.id)}
                  >
                    <td className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>{i + 1}</td>
                    <td>
                      <span className="site">{l.company_name || l.source_url}</span>
                      {l.company_name && (
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{l.source_url}</div>
                      )}
                    </td>
                    <td>
                      <span className={`status status--${l.pipeline_status}`}>
                        <span className="status__dot" />
                        <span>{l.pipeline_status}</span>
                      </span>
                    </td>
                    <td className={`col-score tabular ${l.pipeline_status === "persisted" ? "score-bold" : ""}`}>
                      {l.score == null ? "—" : l.score.toFixed(2)}
                    </td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      {l.is_qualified_lead == null ? "—" : l.is_qualified_lead ? "✓" : "✗"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedLead && (
          <div className="detail" style={{ marginTop: 16 }}>
            <div className="detail__header">
              <div className="detail__title-row">
                <div className="detail__hostname">{selectedLead.company_name || selectedLead.source_url}</div>
                <button
                  style={{ marginLeft: "auto", background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", fontSize: 18 }}
                  onClick={() => setSelectedId(null)}
                >×</button>
              </div>
              <div className="identity__url">{selectedLead.source_url}</div>
            </div>
            {selectedLead.rejection_reason && (
              <div style={{ padding: "8px 0", fontSize: 13, color: "var(--text-muted)" }}>
                Rejection reason: <span className="mono">{selectedLead.rejection_reason}</span>
              </div>
            )}
            {selectedLead.identified_service_gaps && selectedLead.identified_service_gaps.length > 0 && (
              <div style={{ paddingTop: 8 }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>service gaps</div>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                  {selectedLead.identified_service_gaps.map((g, i) => <li key={i}>{g}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
