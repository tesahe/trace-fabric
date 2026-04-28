import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { KeyValueGrid } from "../components/KeyValueGrid";
import { JsonBlock } from "../components/JsonBlock";
import { fetchLeadById } from "../api";
import type { ApiLead } from "../api";

export function LeadDetail() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<ApiLead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    fetchLeadById(id)
      .then((data) => setLead(data))
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="app">
      <PageHeader pageLabel="Lead Detail" />
      <main className="app-main" style={{ paddingTop: 16 }}>
        <div className="detail">
          {loading && <div className="empty-state">Loading…</div>}

          {error && (
            <div className="empty-state" style={{ color: "var(--color-danger, #f66)" }}>
              Error: {error}.{" "}
              <Link to="/leads">Back to Lead Explorer</Link>
            </div>
          )}

          {!loading && !error && !lead && (
            <div className="empty-state">
              No record found for id <span className="mono">{id}</span>.{" "}
              <Link to="/leads">Back to Lead Explorer</Link>
            </div>
          )}

          {lead && (
            <>
              <div className="detail__header">
                <div className="breadcrumb">
                  <Link to="/leads">Lead Explorer</Link> /{" "}
                  <span className="mono">{lead.company_name || lead.source_url}</span>
                </div>
                <div className="detail__title-row">
                  <div className="detail__hostname">{lead.company_name || lead.source_url}</div>
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <StatusBadge status={lead.pipeline_status as never} />
                    <span className="mono tabular" style={{ fontSize: 14 }}>
                      score {lead.score == null ? "—" : lead.score.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="identity__url">{lead.source_url}</div>
                <div className="detail__meta-row">
                  <span>id: {lead.id}</span>
                  <span>qualified: {lead.is_qualified_lead == null ? "—" : lead.is_qualified_lead ? "yes" : "no"}</span>
                  {lead.created_at && <span>created: {new Date(lead.created_at).toLocaleString()}</span>}
                </div>
              </div>

              <section className="detail-section">
                <h3 className="detail-section__title">Discovery context</h3>
                <KeyValueGrid
                  rows={[
                    { k: "niche", v: lead.target_industry || "—" },
                    { k: "location", v: lead.target_location || "—" },
                    { k: "discovery source", v: lead.discovery_source || "—" },
                    { k: "initial url", v: lead.initial_url || "—" },
                    { k: "final url", v: lead.final_url || "—" },
                  ]}
                />
              </section>

              <section className="detail-section">
                <h3 className="detail-section__title">Transport</h3>
                <KeyValueGrid
                  rows={[
                    { k: "http status", v: lead.http_status != null ? String(lead.http_status) : "—" },
                    { k: "https", v: lead.is_https != null ? (lead.is_https ? "yes" : "no") : "—" },
                    { k: "redirects", v: lead.redirect_count != null ? String(lead.redirect_count) : "—" },
                    { k: "content type", v: lead.content_type || "—" },
                    { k: "page title", v: lead.page_title || "—" },
                    { k: "crawl allowed", v: lead.crawl_allowed != null ? (lead.crawl_allowed ? "yes" : "no") : "—" },
                    { k: "crawl blocked reason", v: lead.crawl_disallowed_reason || "—" },
                  ]}
                />
              </section>

              <section className="detail-section">
                <h3 className="detail-section__title">Pipeline result</h3>
                <KeyValueGrid
                  rows={[
                    { k: "pipeline status", v: lead.pipeline_status },
                    { k: "rejection reason", v: lead.rejection_reason || "—" },
                    { k: "overall digital health", v: lead.overall_digital_health || "—" },
                  ]}
                />
              </section>

              {lead.deterministic_evidence != null && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Deterministic evidence</h3>
                  <JsonBlock value={lead.deterministic_evidence} />
                </section>
              )}

              {lead.heuristic_flags != null && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Heuristic flags</h3>
                  <JsonBlock value={lead.heuristic_flags} />
                </section>
              )}

              {lead.identified_service_gaps && lead.identified_service_gaps.length > 0 && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Identified service gaps</h3>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                    {lead.identified_service_gaps.map((g, i) => <li key={i}>{g}</li>)}
                  </ul>
                </section>
              )}

              {lead.missing_critical_features && lead.missing_critical_features.length > 0 && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Missing critical features</h3>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                    {lead.missing_critical_features.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </section>
              )}

              <section className="detail-section">
                <h3 className="detail-section__title">Contact</h3>
                <KeyValueGrid
                  rows={[
                    { k: "company", v: lead.company_name || "—" },
                    { k: "category", v: lead.category || "—" },
                    { k: "phone", v: lead.phone_number || "—" },
                    { k: "address", v: lead.address || "—" },
                  ]}
                />
              </section>

              {lead.provider_provenance != null && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Provider provenance</h3>
                  <JsonBlock value={lead.provider_provenance} />
                </section>
              )}

              {lead.website_provenance != null && (
                <section className="detail-section">
                  <h3 className="detail-section__title">Website provenance</h3>
                  <JsonBlock value={lead.website_provenance} />
                </section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
