import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Lead, TierResult, DeterministicEvidence, EvidenceSignal } from "../types";
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

function buildEvidenceSignals(ev: DeterministicEvidence): EvidenceSignal[] {
  return [
    { key: "is_https",           label: "HTTPS",           ok: !!ev.crawl_allowed },
    { key: "crawl_allowed",      label: "Crawl allowed",   ok: !!ev.crawl_allowed,       detail: ev.crawl_disallowed_reason },
    { key: "has_contact_page",   label: "Contact page",    ok: !!ev.has_contact_page },
    { key: "has_contact_form",   label: "Contact form",    ok: !!ev.has_contact_form },
    { key: "has_booking_widget", label: "Booking widget",  ok: !!ev.has_booking_widget },
    { key: "has_hours_signal",   label: "Hours signal",    ok: !!ev.has_hours_signal },
    { key: "has_cta",            label: "Clear CTA",       ok: !!ev.has_cta },
    { key: "has_privacy_policy", label: "Privacy policy",  ok: !!ev.has_privacy_policy },
    { key: "has_reviews_signal", label: "Reviews signal",  ok: !!ev.has_reviews_signal },
  ];
}

export function DetailDrawer({ lead, onClose }: { lead: Lead; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const evidenceSignals = buildEvidenceSignals(lead.deterministicEvidence);

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
            <div className="identity__host">{lead.sourceHost}</div>
            <div className="identity__url">{lead.sourceUrl}</div>
            {lead.pageTitle && (
              <div style={{ marginTop: 4, color: "var(--text-muted)", fontSize: 12 }}>{lead.pageTitle}</div>
            )}
          </div>

          {/* Status & score */}
          <div className="drawer-section" style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <StatusBadge status={lead.pipelineStatus} />
            <span className="mono tabular" style={{ fontSize: 14 }}>
              score {lead.score == null ? "—" : lead.score.toFixed(2)}
            </span>
            {lead.createdAt && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }} className="mono">
                {new Date(lead.createdAt).toLocaleTimeString()}
              </span>
            )}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -8 }}>
            {lead.rejectionReason}
          </div>

          {/* Timeline */}
          <Section title="Pipeline">
            <Timeline stages={lead.pipeline} />
          </Section>

          {/* Deterministic evidence */}
          <Section title="Deterministic evidence">
            <KeyValueGrid
              rows={evidenceSignals.map((e) => ({
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

          {/* Raw Rust-extracted signals */}
          <Section title="Web signals" defaultOpen={false}>
            <KeyValueGrid
              rows={[
                { k: "word count",      v: lead.wordCount != null ? String(lead.wordCount) : "—" },
                { k: "mobile viewport", v: lead.hasViewport != null ? (lead.hasViewport ? "yes" : "no") : "—" },
                { k: "tel link",        v: lead.hasTelLink != null ? (lead.hasTelLink ? "yes" : "no") : "—" },
                { k: "mailto link",     v: lead.hasMailtoLink != null ? (lead.hasMailtoLink ? "yes" : "no") : "—" },
                { k: "parked domain",   v: lead.isParkedDomain != null ? (lead.isParkedDomain ? "yes" : "no") : "—" },
                { k: "outbound domains",v: lead.outboundDomainCount != null ? String(lead.outboundDomainCount) : "—" },
                { k: "copyright year",  v: lead.copyrightYear != null ? String(lead.copyrightYear) : "—" },
                { k: "schema.org type", v: lead.schemaOrgBusinessType || "—" },
                { k: "email",           v: lead.emailAddress || "—" },
                { k: "meta description",v: lead.metaDescription || "—" },
                { k: "linkedin",        v: lead.socialLinkedin || "—" },
                { k: "facebook",        v: lead.socialFacebook || "—" },
                { k: "instagram",       v: lead.socialInstagram || "—" },
              ]}
            />
          </Section>

          <TierBlock tier={lead.tier1} label="Tier 1 validation" />
          <TierBlock tier={lead.tier2} label="Tier 2 structured extraction" />

          {lead.pipelineStatus === "qualified_deterministic" && (
            <Section title="Qualification record">
              <KeyValueGrid
                rows={[
                  { k: "id", v: lead.id },
                  { k: "qualified", v: lead.isQualifiedLead ? "yes" : "no" },
                  { k: "digital health", v: lead.overallDigitalHealth || "—" },
                ]}
              />
              {lead.identifiedServiceGaps.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div className="section-title">identified service gaps</div>
                  <JsonBlock value={lead.identifiedServiceGaps} />
                </div>
              )}
              {lead.missingCriticalFeatures.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div className="section-title">missing critical features</div>
                  <JsonBlock value={lead.missingCriticalFeatures} />
                </div>
              )}
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
