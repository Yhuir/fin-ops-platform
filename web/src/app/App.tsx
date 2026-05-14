import { useEffect, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import useMediaQuery from "@mui/material/useMediaQuery";
import { useTheme } from "@mui/material/styles";
import { BrowserRouter } from "react-router-dom";

import SessionGate from "../components/auth/SessionGate";
import AppSidebar from "../components/shell/AppSidebar";
import { collapsedSidebarWidth, expandedSidebarWidth } from "../components/shell/AppSidebar";
import AppTopBar from "../components/shell/AppTopBar";
import BackgroundProgressBlock from "../components/common/BackgroundProgressBlock";
import { AppChromeProvider, useAppChrome } from "../contexts/AppChromeContext";
import { AppHealthStatusProvider, useAppHealthStatus } from "../contexts/AppHealthStatusContext";
import { ImportWorkflowDraftProvider } from "../contexts/ImportWorkflowDraftContext";
import { ImportProgressProvider } from "../contexts/ImportProgressContext";
import { MonthProvider } from "../contexts/MonthContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionProvider } from "../contexts/SessionContext";
import { BackgroundJobProgressProvider, useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import MuiProviders from "./MuiProviders";
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

function AppShell() {
  const { workbenchStatus } = useAppChrome();
  const healthStatus = useAppHealthStatus();
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
  const theme = useTheme();
  const embedded = isOaEmbeddedMode();
  const isCompact = useMediaQuery(theme.breakpoints.down("md"), { noSsr: true });
  const storageKey = embedded ? EMBEDDED_OA_SIDEBAR_STORAGE_KEY : DEFAULT_SIDEBAR_STORAGE_KEY;
  const defaultExpanded = !embedded;
  const [sidebarExpanded, setSidebarExpanded] = useState(() => readPersistedSidebarState(storageKey, defaultExpanded));
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setSidebarExpanded(readPersistedSidebarState(storageKey, defaultExpanded));
  }, [defaultExpanded, storageKey]);

  useEffect(() => {
    if (!isCompact) {
      setMobileOpen(false);
    }
  }, [isCompact]);

  const toggleSidebarExpanded = () => {
    setSidebarExpanded((current) => {
      const next = !current;
      persistSidebarState(storageKey, next);
      return next;
    });
  };

  const sidebarWidth = isCompact ? 0 : sidebarExpanded ? expandedSidebarWidth : collapsedSidebarWidth;

  return (
    <Box className={`app-shell${embedded ? " embedded-shell" : ""}`} sx={{ "--sidebar-width": `${sidebarWidth}px` }}>
      <AppSidebar
        embedded={embedded}
        isCompact={isCompact}
        mobileOpen={mobileOpen}
        expanded={sidebarExpanded}
        healthStatus={healthStatus}
        workbenchStatus={workbenchStatus}
        onCloseMobile={() => setMobileOpen(false)}
        onToggleExpanded={toggleSidebarExpanded}
      />
      <Box className="app-shell-content" component="section">
        <AppTopBar
          embedded={embedded}
          isCompact={isCompact}
          onOpenMobileSidebar={() => setMobileOpen(true)}
        />
        {connectionFailed || primaryJob || operationError ? (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "flex-end",
              gap: 1,
              justifyContent: "flex-end",
              minWidth: 0,
              px: { xs: 2, md: 3 },
              pt: 1,
            }}
          >
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
              <Alert
                severity="error"
                onClose={clearOperationError}
                sx={{ maxWidth: "min(520px, 92vw)", py: 0.25 }}
              >
                {operationError}
              </Alert>
            ) : null}
          </Box>
        ) : null}
        <main className={`page-body${embedded ? " embedded" : ""}`}>
          <SessionGate>
            <AppRouter />
          </SessionGate>
        </main>
      </Box>
    </Box>
  );
}

export default function App() {
  return (
    <BrowserRouter
      basename={APP_BASE_PATH === "/" ? undefined : APP_BASE_PATH}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <MuiProviders>
        <MonthProvider>
          <ImportProgressProvider>
            <SessionProvider>
              <PageSessionStateProvider>
                <ImportWorkflowDraftProvider>
                  <AppChromeProvider initialShellHeaderMounted>
                    <BackgroundJobProgressProvider>
                      <AppHealthStatusProvider>
                        <AppShell />
                      </AppHealthStatusProvider>
                    </BackgroundJobProgressProvider>
                  </AppChromeProvider>
                </ImportWorkflowDraftProvider>
              </PageSessionStateProvider>
            </SessionProvider>
          </ImportProgressProvider>
        </MonthProvider>
      </MuiProviders>
    </BrowserRouter>
  );
}
