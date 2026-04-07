import { BrowserRouter, NavLink } from "react-router-dom";

import SessionGate from "../components/auth/SessionGate";
import { AppChromeProvider, useAppChrome } from "../contexts/AppChromeContext";
import { ImportProgressProvider, useImportProgress } from "../contexts/ImportProgressContext";
import { MonthProvider } from "../contexts/MonthContext";
import { SessionProvider } from "../contexts/SessionContext";
import AppRouter from "./router";
import { APP_BASE_PATH, isOaEmbeddedMode } from "./runtime";
import "./styles.css";

function AppShell() {
  const { isWorkbenchFocusMode } = useAppChrome();
  const { progress } = useImportProgress();
  const embedded = isOaEmbeddedMode();

  return (
    <div className={`app-shell${embedded ? " embedded-shell" : ""}`}>
      {!isWorkbenchFocusMode && !embedded ? (
        <header className="global-header">
          <div>
            <div className="eyebrow">Workbench V2 Web Foundation</div>
            <div className="global-title">财务工作台正式前端工程</div>
          </div>
          <div className="header-actions">
            {progress ? (
              <div className={`global-progress-chip ${progress.tone}`} aria-live="polite">
                <span className="global-progress-label">进度</span>
                <strong>{progress.label}</strong>
              </div>
            ) : null}
            <nav className="nav-links" aria-label="主导航">
              <NavLink
                to="/"
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                end
              >
                关联台
              </NavLink>
              <NavLink
                to="/tax-offset"
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              >
                税金抵扣
              </NavLink>
              <NavLink
                to="/cost-statistics"
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
              >
                成本统计
              </NavLink>
            </nav>
          </div>
        </header>
      ) : null}
      <main
        className={`page-body${isWorkbenchFocusMode ? " focus-mode" : ""}${embedded ? " embedded" : ""}`}
      >
        <AppRouter />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter
      basename={APP_BASE_PATH === "/" ? undefined : APP_BASE_PATH}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <MonthProvider>
        <ImportProgressProvider>
          <SessionProvider>
            <AppChromeProvider>
              <SessionGate>
                <AppShell />
              </SessionGate>
            </AppChromeProvider>
          </SessionProvider>
        </ImportProgressProvider>
      </MonthProvider>
    </BrowserRouter>
  );
}
