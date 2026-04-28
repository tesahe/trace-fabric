import type { ReactNode } from "react";

export function Panel({
  title,
  right,
  children,
  bodyClassName,
}: {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  bodyClassName?: string;
}) {
  return (
    <section className="panel">
      {title && (
        <div className="panel__header">
          <span>{title}</span>
          {right}
        </div>
      )}
      <div className={`panel__body ${bodyClassName ?? ""}`}>{children}</div>
    </section>
  );
}
