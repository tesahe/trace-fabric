import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Lead, TierResult } from "../types";
import { StatusBadge } from "./StatusBadge";
import { Timeline } from "./Timeline";
import { KeyValueGrid } from "./KeyValueGrid";
import { JsonBlock } from "./JsonBlock";

function Section({
  title,
  summary,
  defaultOpen = true,
  children,
}: {
  title: string;
  summary?: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="drawer-section">
      <div className="drawer-section__head" onClick={() => setOpen((o) => !o)}>
        <span className="drawer-section__title">{title}</span>
        <span className="drawer-section__summary">{open ? "−" : `${summary ?? ""}  +`}</span>
      </div>
      {open && children}
    </div>
  );
}

function TierBlock({ tier, label }: { tier: TierResult; label: string }) {
  if (tier.state === "skipped" || tier.state === "pending") {
    return (
      <Section
        title={label}
        summary={tier.reason ? `skipped — ${tier.reason}` : "skipped"}
        defaultOpen={false}
      >
        <KeyValueGrid
          rows={[
            { k: "state", v: "skipped" },
            { k: "reason", v: tier.reason || "—" },
          ]}
        />
      </Section>
    );
  }
  return (
    <Section title={label} defaultOpen>
      <KeyValueGrid
        rows={[
          { k: "state", v: tier.state },
          { k: "model", v: tier.model || "—" },
          { k: "prompt", v: tier.promptVersion || "—" },
          { k: "latency", v: tier.latencyMs ? `${tier.latencyMs} ms` : "—" },
          { k: "tokens", v: tier.tokens ? `${tier.tokens.in} in / ${tier.tokens.out} out` : "—" },
          { k: "rationale", v: tier.rationale || "—" },
        ]}
      />
      {tier.output && (
        <div style={{ marginTop: 12 }}>
          <div className="section-title">structured output</div>
          <JsonBlock value={tier.output} />
        </div>
      )}
      {tier.raw != null && !tier.output && (
        <div style={{ marginTop: 12 }}>
          <div className="section-title">raw</div>
          <JsonBlock value={tier.raw} />
        </div>
      )}
    </Section>
  );
}

export function DetailDrawer({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Lead detail">
        <div className="drawer__header">
          <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Lead detail</span>
          <button className="drawer__close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="drawer__body">
          {/* Identity */}
          <div className="drawer-section" style={{ paddingTop: 0 }}>
            <div className="identity__host">{lead.host}</div>
            <div className="identity__url">{lead.url}</div>
            {lead.title && (
              <div style={{ marginTop: 4, color: "var(--text-muted)", fontSize: 12 }}>{lead.title}</div>
            )}
          </div>

          {/* Status & score */}
          <div className="drawer-section" style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <StatusBadge status={lead.status} />
            <span className="mono tabular" style={{ fontSize: 14 }}>
              score {lead.score == null ? "—" : lead.score.toFixed(2)}
            </span>
            {lead.persistedAt && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }} className="mono">
                persisted {new Date(lead.persistedAt).toLocaleTimeString()}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -8 }}>
            {lead.decisionReason}
          </div>

          {/* Timeline */}
          <Section title="Pipeline">
            <Timeline stages={lead.pipeline} />
          </Section>

          {/* Deterministic evidence */}
          <Section title="Deterministic evidence">
            <KeyValueGrid
              rows={lead.evidence.map((e) => ({
                k: e.label,
                v: (
                  <span>
                    <span className={e.ok ? "evidence-ok" : "evidence-bad"}>{e.ok ? "✓" : "✗"}</span>{" "}
                    <span style={{ color: "var(--text-muted)" }}>{e.detail || ""}</span>
                  </span>
                ),
              }))}
            />
          </Section>

          <TierBlock tier={lead.tier1} label="Tier 1 validation" />
          <TierBlock tier={lead.tier2} label="Tier 2 structured extraction" />

          {lead.status === "persisted" && lead.finalOutput && (
            <Section title="Persisted record">
              <KeyValueGrid
                rows={[
                  { k: "id", v: lead.id },
                  { k: "schema", v: lead.schemaVersion || "—" },
                  { k: "qualification", v: lead.qualification || "—" },
                ]}
              />
              <div style={{ marginTop: 12 }}>
                <JsonBlock value={lead.finalOutput} />
              </div>
            </Section>
          )}
        </div>
        <div className="drawer__footer">
          <Link to={`/leads/${lead.id}`} className="btn btn--primary">Open full detail →</Link>
          <button className="btn" onClick={() => navigator.clipboard?.writeText(lead.id)}>Copy id</button>
        </div>
      </aside>
    </>
  );
}
