import { BrowserRouter, NavLink } from "react-router-dom";

import SessionGate from "../components/auth/SessionGate";
import WorkbenchHeaderControls from "../components/workbench/WorkbenchHeaderControls";
import { AppChromeProvider, useAppChrome } from "../contexts/AppChromeContext";
import { ImportProgressProvider, useImportProgress } from "../contexts/ImportProgressContext";
import { MonthProvider } from "../contexts/MonthContext";
import { SessionProvider } from "../contexts/SessionContext";
import AppRouter from "./router";
import { APP_BASE_PATH, isOaEmbeddedMode } from "./runtime";
import "./styles.css";

function HeaderStatusIndicator({ level, reason }: { level: "ok" | "pending" | "error"; reason: string }) {
  return (
    <div
      aria-label={reason}
      aria-live="polite"
      className={`global-status-indicator ${level}`}
      data-status-reason={reason}
      role="status"
      title={reason}
    >
      <span className="global-status-dot" aria-hidden="true" />
    </div>
  );
}

function AppShell() {
  const { workbenchHeaderActions, workbenchStatus } = useAppChrome();
  const { progress } = useImportProgress();
  const embedded = isOaEmbeddedMode();

  return (
    <div className={`app-shell${embedded ? " embedded-shell" : ""}`}>
      <header className={`global-header${embedded ? " embedded-header" : ""}`}>
        <div className="global-header-main">
          <div className="global-heading-block">
            <div className="eyebrow">溯源办公系统</div>
            <div className="global-title">财务运营平台</div>
          </div>
          {workbenchStatus ? <HeaderStatusIndicator level={workbenchStatus.level} reason={workbenchStatus.reason} /> : null}
        </div>
        <div className="header-actions">
          {workbenchHeaderActions ? (
            <WorkbenchHeaderControls
              canMutateData={workbenchHeaderActions.canMutateData}
              className="shell"
              onOpenImport={workbenchHeaderActions.onOpenImport}
              onOpenSearch={workbenchHeaderActions.onOpenSearch}
              onOpenSettings={workbenchHeaderActions.onOpenSettings}
            />
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
          {progress ? (
            <div className={`global-progress-chip ${progress.tone}`} aria-live="polite">
              <span className="global-progress-label">进度</span>
              <strong>{progress.label}</strong>
            </div>
          ) : null}
        </div>
      </header>
      <main className={`page-body${embedded ? " embedded" : ""}`}>
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
            <AppChromeProvider initialShellHeaderMounted>
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
