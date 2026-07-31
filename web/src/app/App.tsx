import { useEffect, useState } from "react";
import { Alert } from "@heroui/react";
import { BrowserRouter, useLocation } from "react-router-dom";

import SessionGate from "../components/auth/SessionGate";
import AppSidebar from "../components/shell/AppSidebar";
import AppTopBar from "../components/shell/AppTopBar";
import BackgroundProgressBlock from "../components/common/BackgroundProgressBlock";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { AppHealthStatusProvider } from "../contexts/AppHealthStatusContext";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { ImportWorkflowDraftProvider } from "../contexts/ImportWorkflowDraftContext";
import { ImportProgressProvider } from "../contexts/ImportProgressContext";
import { MonthProvider } from "../contexts/MonthContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionProvider } from "../contexts/SessionContext";
import { BackgroundJobProgressProvider, useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import AppRouter from "./router";
import { APP_BASE_PATH, isOaEmbeddedMode } from "./runtime";
import "./styles.css";

const DEFAULT_SIDEBAR_STORAGE_KEY = "finOps.sidebar.expanded.default";
const EMBEDDED_OA_SIDEBAR_STORAGE_KEY = "finOps.sidebar.expanded.embeddedOa";

function readPersistedSidebarState(storageKey: string, fallback: boolean) {
  try {
    const persisted = window.localStorage.getItem(storageKey);
    if (persisted === "true") {
      return true;
    }
    if (persisted === "false") {
      return false;
    }
  } catch {
    return fallback;
  }
  return fallback;
}

function persistSidebarState(storageKey: string, expanded: boolean) {
  try {
    window.localStorage.setItem(storageKey, String(expanded));
  } catch {
    // localStorage may be unavailable in restrictive embedded shells.
  }
}

function useShellMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window.matchMedia !== "function") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      setMatches(false);
      return undefined;
    }
    const mediaQuery = window.matchMedia(query);
    const handleChange = () => setMatches(mediaQuery.matches);

    handleChange();
    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [query]);

  return matches;
}

function StatefulAppSidebar({
  embedded,
  isCompact,
  mobileOpen,
  onCloseMobile,
}: {
  embedded: boolean;
  isCompact: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const storageKey = embedded ? EMBEDDED_OA_SIDEBAR_STORAGE_KEY : DEFAULT_SIDEBAR_STORAGE_KEY;
  const defaultExpanded = !embedded;
  const [expanded, setExpanded] = useState(() => readPersistedSidebarState(storageKey, defaultExpanded));

  useEffect(() => {
    setExpanded(readPersistedSidebarState(storageKey, defaultExpanded));
  }, [defaultExpanded, storageKey]);

  const toggleExpanded = () => {
    setExpanded((current) => {
      const next = !current;
      persistSidebarState(storageKey, next);
      return next;
    });
  };

  return (
    <AppSidebar
      embedded={embedded}
      isCompact={isCompact}
      mobileOpen={mobileOpen}
      expanded={expanded}
      onCloseMobile={onCloseMobile}
      onToggleExpanded={toggleExpanded}
    />
  );
}

function AppShell() {
  const location = useLocation();
  const {
    primaryJob,
    extraCount,
    connectionFailed,
    operatingJobId,
    operationError,
    acknowledgeJob,
    retryJob,
    clearOperationError,
  } = useBackgroundJobProgress();
  const embedded = isOaEmbeddedMode();
  const isCompact = useShellMediaQuery("(max-width: 899.95px)");
  const [mobileOpen, setMobileOpen] = useState(false);
  const isBankDetailsRoute = location.pathname === "/bank-details";
  const showProgressStack = !isBankDetailsRoute && (connectionFailed || primaryJob || operationError);

  useEffect(() => {
    if (!isCompact) {
      setMobileOpen(false);
    }
  }, [isCompact]);

  return (
    <div className={`app-shell${embedded ? " embedded-shell" : ""}${isBankDetailsRoute ? " app-shell--bank-details" : ""}`}>
      <StatefulAppSidebar
        embedded={embedded}
        isCompact={isCompact}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <section className="app-shell-content">
        <AppTopBar
          embedded={embedded}
          isCompact={isCompact}
          onOpenMobileSidebar={() => setMobileOpen(true)}
        />
        {showProgressStack ? (
          <div className="app-shell-progress-stack">
            {connectionFailed ? (
              <BackgroundProgressBlock kind="connection_error" />
            ) : primaryJob ? (
              <BackgroundProgressBlock
                kind="job"
                job={primaryJob}
                extraCount={extraCount}
                operating={operatingJobId === primaryJob.jobId}
                onAcknowledge={(jobId) => {
                  acknowledgeJob(jobId).catch(() => undefined);
                }}
                onRetry={(jobId) => {
                  retryJob(jobId).catch(() => undefined);
                }}
              />
            ) : null}
            {operationError ? (
              <Alert className="app-shell-operation-error" role="alert" status="danger">
                <Alert.Indicator />
                <Alert.Content>
                  <Alert.Description>{operationError}</Alert.Description>
                </Alert.Content>
                <button
                  aria-label="关闭后台操作错误"
                  className="app-shell-operation-error__close"
                  type="button"
                  onClick={clearOperationError}
                >
                  ×
                </button>
              </Alert>
            ) : null}
          </div>
        ) : null}
        <main className={`page-body${embedded ? " embedded" : ""}`}>
          <SessionGate>
            <AppRouter />
          </SessionGate>
        </main>
      </section>
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
            <PageSessionStateProvider>
              <ImportWorkflowDraftProvider>
                <AppChromeProvider initialShellHeaderMounted>
                  <BackgroundJobProgressProvider>
                    <AppHealthStatusProvider>
                      <GlobalOperationOverlayProvider>
                        <AppShell />
                      </GlobalOperationOverlayProvider>
                    </AppHealthStatusProvider>
                  </BackgroundJobProgressProvider>
                </AppChromeProvider>
              </ImportWorkflowDraftProvider>
            </PageSessionStateProvider>
          </SessionProvider>
        </ImportProgressProvider>
      </MonthProvider>
    </BrowserRouter>
  );
}
