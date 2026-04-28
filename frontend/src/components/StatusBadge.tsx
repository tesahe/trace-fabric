import type { LeadStatus } from "../types";

export function StatusBadge({ status }: { status: LeadStatus }) {
  return (
    <span className={`status status--${status}`}>
      <span className="status__dot" />
      <span>{status}</span>
    </span>
  );
}
