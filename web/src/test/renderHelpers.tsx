import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "../app/App";
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

export function renderWorkbenchPage() {
  return render(
    <MemoryRouter>
      <AppChromeProvider>
        <MonthProvider>
          <SessionContext.Provider value={staticWorkbenchSession}>
            <ReconciliationWorkbenchPage />
          </SessionContext.Provider>
        </MonthProvider>
      </AppChromeProvider>
    </MemoryRouter>,
  );
}
