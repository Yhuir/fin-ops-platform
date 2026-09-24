import { useEffect, useState } from "react";
import { BrowserRouter, useLocation } from "react-router-dom";

import SessionGate from "../components/auth/SessionGate";
import AppSidebar from "../components/shell/AppSidebar";
import AppTopBar from "../components/shell/AppTopBar";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { AppHealthStatusProvider } from "../contexts/AppHealthStatusContext";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { ImportProgressProvider } from "../contexts/ImportProgressContext";
import { MonthProvider } from "../contexts/MonthContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionProvider } from "../contexts/SessionContext";
import { BackgroundJobProgressProvider } from "../features/backgroundJobs/BackgroundJobProgressProvider";
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
  const embedded = isOaEmbeddedMode();
  const isCompact = useShellMediaQuery("(max-width: 899.95px)");
  const [mobileOpen, setMobileOpen] = useState(false);
  const isBankDetailsRoute = location.pathname === "/bank-details";

  useEffect(() => {
    if (!isCompact) {
      setMobileOpen(false);
    }
  }, [isCompact]);

  return (
    <div className={`app-shell${embedded ? " embedded-shell" : ""}${isBankDetailsRoute ? " app-shell--bank-details" : ""}`}>
      <a className="app-skip-link" href="#main-content">
        跳到主要内容
      </a>
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
        <main className={`page-body${embedded ? " embedded" : ""}`} id="main-content" tabIndex={-1}>
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
              <AppChromeProvider initialShellHeaderMounted>
                <BackgroundJobProgressProvider>
                  <AppHealthStatusProvider>
                    <GlobalOperationOverlayProvider>
                      <AppShell />
                    </GlobalOperationOverlayProvider>
                  </AppHealthStatusProvider>
                </BackgroundJobProgressProvider>
              </AppChromeProvider>
            </PageSessionStateProvider>
          </SessionProvider>
        </ImportProgressProvider>
      </MonthProvider>
    </BrowserRouter>
  );
}
