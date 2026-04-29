import type { PipelineStatus } from "../types";

export function StatusBadge({ status }: { status: PipelineStatus }) {
  return (
    <span className={`status status--${status}`}>
      <span className="status__dot" />
      <span>{status}</span>
    </span>
  );
}
