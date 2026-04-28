import { Link, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

export function PageHeader({ pageLabel }: { pageLabel: string }) {
  const loc = useLocation();
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    return (localStorage.getItem("tf-theme") as "light" | "dark") || "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("tf-theme", theme);
  }, [theme]);

  const otherRoute = loc.pathname.startsWith("/leads") ? "/run" : "/leads";
  const otherLabel = otherRoute === "/run" ? "Run Console" : "Lead Explorer";

  return (
    <header className="page-header">
      <div className="page-header__title">
        <span className="page-header__brand">TraceFabric</span>
        <span className="page-header__sep">/</span>
        <span>{pageLabel}</span>
      </div>
      <div className="page-header__right">
        <Link to={otherRoute}>{otherLabel}</Link>
        <span className="env-badge">env: local</span>
        <button
          className="theme-toggle"
          onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          title="Toggle theme"
        >
          {theme === "light" ? "dark" : "light"}
        </button>
      </div>
    </header>
  );
}
