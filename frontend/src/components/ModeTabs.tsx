import type { InputMode } from "../types";

const TABS: { mode: InputMode; label: string; secondary?: boolean }[] = [
  { mode: "discover", label: "Discover Leads" },
  { mode: "url", label: "Evaluate URL" },
  { mode: "replay", label: "Replay", secondary: true },
];

export function ModeTabs({ value, onChange }: { value: InputMode; onChange: (m: InputMode) => void }) {
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
