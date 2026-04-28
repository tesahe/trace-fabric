import { Fragment } from "react";

export function KeyValueGrid({ rows }: { rows: { k: string; v: React.ReactNode }[] }) {
  return (
    <div className="kv">
      {rows.map((r, i) => (
        <Fragment key={`${r.k}-${i}`}>
          <div className="kv__k">{r.k}</div>
          <div className="kv__v">{r.v}</div>
        </Fragment>
      ))}
    </div>
  );
}
