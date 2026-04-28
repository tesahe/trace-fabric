import type { PipelineStage, StageState } from "../types";

function nodeClass(state: StageState): string {
  return `timeline-step__node timeline-step__node--${state}`;
}

function connectorClass(state: StageState): string {
  if (state === "rejected" || state === "failed") return "timeline-step__connector timeline-step__connector--rejected";
  if (state === "skipped") return "timeline-step__connector timeline-step__connector--dotted";
  if (state === "done") return "timeline-step__connector timeline-step__connector--solid";
  return "timeline-step__connector";
}

function shortValue(stage: PipelineStage): string {
  if (stage.value) return stage.value;
  switch (stage.state) {
    case "skipped": return "skip";
    case "rejected": return "rej";
    case "failed": return "fail";
    case "running": return "…";
    case "pending": return "—";
    default: return "ok";
  }
}

export function Timeline({ stages, expanded = false }: { stages: PipelineStage[]; expanded?: boolean }) {
  return (
    <div className={`timeline ${expanded ? "timeline--expanded" : "timeline--compact"}`}>
      {stages.map((s) => (
        <div key={s.key} className="timeline-step" title={s.reason || s.label}>
          <div className={connectorClass(s.state)} />
          <div className={nodeClass(s.state)} />
          <div className="timeline-step__label">{s.label}</div>
          <div className="timeline-step__value">{shortValue(s)}</div>
          {expanded && s.reason && (
            <div className="timeline-step__meta">{s.reason}</div>
          )}
          {expanded && s.meta && (
            <div className="timeline-step__meta">
              {Object.entries(s.meta).map(([k, v]) => (
                <div key={k}>
                  {k}: {String(v)}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
