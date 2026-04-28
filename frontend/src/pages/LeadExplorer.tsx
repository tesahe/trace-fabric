import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { fetchRecentLeads } from "../api";
import type { ApiLead } from "../api";

export function LeadExplorer() {
  const nav = useNavigate();
  const [leads, setLeads] = useState<ApiLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("any");
  const [runType, setRunType] = useState<string>("any");

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchRecentLeads(50)
      .then((data) => setLeads(data.items))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return leads.filter((l) => {
      if (search) {
        const q = search.toLowerCase();
        const haystack = [
          l.source_url,
          l.company_name,
          l.target_industry,
          l.target_location,
          l.id,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      if (status !== "any" && l.pipeline_status !== status) return false;
      return true;
    });
  }, [leads, search, status, runType]);

  function clearAll() {
    setSearch("");
    setStatus("any");
    setRunType("any");
  }

  return (
    <div className="app">
      <PageHeader pageLabel="Lead Explorer" />
      <main className="app-main row-gap-4" style={{ paddingTop: 16 }}>
        <div className="filter-bar">
          <div className="form-field form-field--search">
            <label className="form-field__label">Search</label>
            <input
              className="form-field__input"
              placeholder="hostname, company, niche, location, record id"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label className="form-field__label">Status</label>
            <select className="form-field__select" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="any">any</option>
              <option value="persisted">persisted</option>
              <option value="rejected">rejected</option>
              <option value="skipped">skipped</option>
              <option value="failed">failed</option>
            </select>
          </div>
          <button className="filter-bar__clear" onClick={clearAll}>clear all</button>
        </div>

        {loading && <div className="empty-state">Loading leads…</div>}
        {error && <div className="empty-state" style={{ color: "var(--color-danger, #f66)" }}>Error: {error}</div>}

        {!loading && !error && (
          <>
            <div className="result-count">{filtered.length} records · showing 1–{Math.min(filtered.length, 50)}</div>

            <div className="dense-table-wrap">
              <table className="dense-table">
                <thead>
                  <tr>
                    <th>Site / Company</th>
                    <th>Niche / Location</th>
                    <th className="col-status">Status</th>
                    <th className="col-score">Score</th>
                    <th>Qualified</th>
                    <th>Persisted</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.slice(0, 50).map((l) => (
                    <tr key={l.id} onClick={() => nav(`/leads/${l.id}`)}>
                      <td>
                        <span className="site">{l.company_name || l.source_url}</span>
                        {l.company_name && (
                          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{l.source_url}</div>
                        )}
                      </td>
                      <td>
                        <div>{l.target_industry || "—"}</div>
                        <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{l.target_location || "—"}</div>
                      </td>
                      <td><StatusBadge status={l.pipeline_status as never} /></td>
                      <td className={`col-score tabular ${l.pipeline_status === "persisted" ? "score-bold" : ""}`}>
                        {l.score == null ? "—" : l.score.toFixed(2)}
                      </td>
                      <td style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {l.is_qualified_lead == null ? "—" : l.is_qualified_lead ? "✓" : "✗"}
                      </td>
                      <td className="mono" style={{ fontSize: 12, color: "var(--text-muted)" }}>
                        {l.created_at ? relTime(l.created_at) : "—"}
                      </td>
                    </tr>
                  ))}
                  {filtered.length === 0 && (
                    <tr><td colSpan={6}><div className="empty-state">No records match these filters.</div></td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function relTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const m = Math.floor(ms / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
