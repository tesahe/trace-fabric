import type { Lead, TierState } from "../types";
import { StatusBadge } from "./StatusBadge";

function TierCell({ state, reason }: { state: TierState; reason?: string }) {
  if (state === "running") {
    return (
      <span className="tier-cell tier-cell--running" title="running">
        <span className="pulse-pill" />
      </span>
    );
  }
  if (state === "pending") return <span className="tier-cell tier-cell--skip" title="pending">·</span>;
  if (state === "skipped") return <span className="tier-cell tier-cell--skip" title={reason || "skipped"}>–</span>;
  if (state === "passed") return <span className="tier-cell tier-cell--ok" title="passed">✓</span>;
  return <span className="tier-cell tier-cell--bad" title={reason || "failed"}>✗</span>;
}

function EvidenceLine({ lead }: { lead: Lead }) {
  if (lead.status === "running" && lead.score === null) {
    return <span className="evidence-summary">…</span>;
  }
  if (lead.status === "failed") {
    return <span className="evidence-summary evidence-bad">{lead.decisionReason}</span>;
  }
  if (lead.status === "skipped") {
    return <span className="evidence-summary">{lead.decisionReason}</span>;
  }
  const tokens = lead.evidence
    .map((e) => {
      if (e.key === "social") return `social ${e.detail ?? ""}`.trim();
      return `${e.label} ${e.ok ? "✓" : "✗"}`;
    })
    .slice(0, 5);
  if (lead.status === "rejected") {
    return (
      <span className="evidence-summary">
        {tokens.join(", ")} → <span className="evidence-bad">rejected: {lead.decisionReason}</span>
      </span>
    );
  }
  return <span className="evidence-summary">{tokens.join(", ")}</span>;
}

export function ResultsTable({
  leads,
  selectedId,
  onSelect,
  isReplay,
}: {
  leads: Lead[];
  selectedId?: string | null;
  onSelect: (l: Lead) => void;
  isReplay?: boolean;
}) {
  if (leads.length === 0) {
    return (
      <div className="dense-table-wrap">
        {isReplay && <div className="replay-strip" />}
        <div className="empty-state">
          No runs yet. Start a discovery above, evaluate a single URL, or load a replay fixture.
        </div>
      </div>
    );
  }

  return (
    <div className="dense-table-wrap">
      {isReplay && <div className="replay-strip" />}
      <table className="dense-table">
        <thead>
          <tr>
            <th className="col-num">#</th>
            <th>Site</th>
            <th className="col-status">Status</th>
            <th className="col-score">Score</th>
            <th>Evidence</th>
            <th className="col-tier">T1</th>
            <th className="col-tier">T2</th>
            <th>Decision reason</th>
            <th className="col-ms">ms</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((l) => {
            const faint = l.status === "running" || l.status === "rejected" || l.status === "skipped";
            return (
              <tr
                key={l.id}
                className={`${faint ? "row--faint" : ""} ${selectedId === l.id ? "selected" : ""}`}
                onClick={() => onSelect(l)}
              >
                <td className="col-num tabular">{l.index}</td>
                <td>
                  <span className="site">{l.host}</span>
                </td>
                <td className="col-status">
                  <StatusBadge status={l.status} />
                </td>
                <td className={`col-score tabular ${l.status === "persisted" ? "score-bold" : ""}`}>
                  {l.score === null ? "—" : l.score.toFixed(2)}
                </td>
                <td>
                  <EvidenceLine lead={l} />
                </td>
                <td className="col-tier">
                  <TierCell state={l.tier1.state} reason={l.tier1.reason} />
                </td>
                <td className="col-tier">
                  <TierCell state={l.tier2.state} reason={l.tier2.reason} />
                </td>
                <td>
                  <span className="evidence-summary">{l.decisionReason || "…"}</span>
                </td>
                <td className="col-ms tabular">{l.totalMs == null ? "—" : l.totalMs}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
