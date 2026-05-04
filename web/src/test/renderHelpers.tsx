import { render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";

import App from "../app/App";
import MuiProviders from "../app/MuiProviders";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { MonthProvider } from "../contexts/MonthContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";

const defaultSession: SessionPayload = {
  allowed: true,
  userId: 1,
  username: "TESTFULL001",
  nickName: "测试全权限",
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
  const navigate = useNavigate();

  return (
    <>
      <button
        type="button"
        onClick={() => navigate("/", { state: { workbenchHeaderIntent: { type: "open_search" } } })}
      >
        关联台搜索
      </button>
      <ReconciliationWorkbenchPage />
    </>
  );
}

export function renderWorkbenchPage() {
  return render(
    <MemoryRouter>
      <MuiProviders>
        <AppChromeProvider>
          <MonthProvider>
            <SessionContext.Provider value={staticWorkbenchSession}>
              <WorkbenchPageHarness />
            </SessionContext.Provider>
          </MonthProvider>
        </AppChromeProvider>
      </MuiProviders>
    </MemoryRouter>,
  );
}
