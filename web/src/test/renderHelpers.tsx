import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "../app/App";
import MuiProviders from "../app/MuiProviders";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { MonthProvider } from "../contexts/MonthContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";

const defaultSession: SessionPayload = {
  allowed: true,
  user: {
    userId: "1",
    username: "TESTFULL001",
    nickname: "测试全权限",
    displayName: "测试全权限",
    deptId: null,
    deptName: null,
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

const staticWorkbenchSession: SessionContextValue = {
  status: "authenticated",
  session: defaultSession,
  refresh: () => undefined,
};

export function renderAppAt(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

function WorkbenchPageHarness() {
  return <ReconciliationWorkbenchPage />;
}

export function renderWorkbenchPage() {
  return render(
    <MemoryRouter>
      <MuiProviders>
        <AppChromeProvider>
          <MonthProvider>
            <SessionContext.Provider value={staticWorkbenchSession}>
              <PageSessionStateProvider>
                <WorkbenchPageHarness />
              </PageSessionStateProvider>
            </SessionContext.Provider>
          </MonthProvider>
        </AppChromeProvider>
      </MuiProviders>
    </MemoryRouter>,
  );
}
