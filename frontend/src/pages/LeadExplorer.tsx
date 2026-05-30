import { useEffect, useMemo, useState } from "react";
import { fetchRecentLeads } from "../api";
import type { ApiLead } from "../api";
import { adaptRunLeadList } from "../adapters";
import type { Lead } from "../types";
import { ResultsTable } from "../components/ResultsTable";
import { DetailDrawer } from "../components/DetailDrawer";
import { PageHeader } from "../components/PageHeader";

export function LeadExplorer() {
  const [rawLeads, setRawLeads] = useState<ApiLead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string>("any");

  // Adapt raw API leads → rich Lead[] for ResultsTable / DetailDrawer.
  const leads = useMemo(() => adaptRunLeadList(rawLeads), [rawLeads]);

  // Apply search + status filters on the adapted leads (camelCase fields).
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return leads.filter((l) => {
      if (status !== "any" && l.pipelineStatus !== status) return false;
      if (!q) return true;
      return (
        l.sourceHost.toLowerCase().includes(q) ||
        (l.companyName?.toLowerCase().includes(q) ?? false) ||
        l.targetIndustry.toLowerCase().includes(q)
      );
    });
  }, [leads, search, status]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchRecentLeads(50)
      .then((data) => {
        if (!cancelled) {
          setRawLeads(data.items);  // ← unwrap ApiLeadList
          setError(null);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function clearAll() {
    setSearch("");
    setStatus("any");
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
              placeholder="hostname, company, niche"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="form-field">
            <label className="form-field__label">Status</label>
            <select
              className="form-field__select"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="any">any</option>
              <option value="qualified_deterministic">qualified (deterministic)</option>
              <option value="rejected_deterministic">rejected (deterministic)</option>
              <option value="excluded_crawl_disallowed">excluded (crawl blocked)</option>
              <option value="excluded_no_website_opportunity">excluded (no site)</option>
              <option value="rejected_parked_domain">rejected (parked domain)</option>
              <option value="rejected_compliance">rejected (compliance)</option>
              <option value="tier1_rejected">tier 1 rejected</option>
              <option value="tier1_passed">tier 1 passed</option>
              <option value="tier2_queued">tier 2 queued</option>
              <option value="tier2_complete">tier 2 complete</option>
              <option value="failed">failed</option>
            </select>
          </div>
          <button className="filter-bar__clear" onClick={clearAll}>clear all</button>
        </div>

        {loading && <div className="empty-state">Loading leads…</div>}
        {error && (
          <div className="empty-state" style={{ color: "var(--color-danger, #f66)" }}>
            Error: {error}
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="result-count">
              {filtered.length} records · showing 1–{Math.min(filtered.length, 50)}
            </div>
            <ResultsTable
              leads={filtered.slice(0, 50)}
              selectedId={selectedLead?.id ?? null}
              onSelect={setSelectedLead}
            />
          </>
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
