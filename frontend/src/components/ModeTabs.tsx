import type { RunMode } from "../types";

const TABS: { mode: RunMode; label: string; secondary?: boolean }[] = [
  { mode: "discover", label: "Discover Leads" },
  { mode: "url", label: "Evaluate URL" },
  { mode: "replay", label: "Replay", secondary: true },
];

export function ModeTabs({ value, onChange }: { value: RunMode; onChange: (m: RunMode) => void }) {
  return (
    <div className="mode-tabs" role="tablist">
      {TABS.map((t) => (
        <button
          key={t.mode}
          role="tab"
          aria-selected={value === t.mode}
          className="mode-tab"
          onClick={() => onChange(t.mode)}
        >
          {t.secondary && <span className="mode-tab__dot" />}
          {t.label}
        </button>
      ))}
    </div>
  );
}
