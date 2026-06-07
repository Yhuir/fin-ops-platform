import { render } from "@testing-library/react";
import { Link, MemoryRouter } from "react-router-dom";

import App from "../app/App";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { ImportProgressProvider } from "../contexts/ImportProgressContext";
import { ImportWorkflowDraftProvider } from "../contexts/ImportWorkflowDraftContext";
import { MonthProvider } from "../contexts/MonthContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import AppRouter from "../app/router";

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

const defaultAuthenticatedAppSession: SessionPayload = {
  ...defaultSession,
  user: {
    ...defaultSession.user,
    userId: "101",
    username: "liuji",
    nickname: "刘际涛",
    displayName: "刘际涛",
    deptId: "88",
    deptName: "财务部",
  },
  roles: ["finance"],
};

export function renderAppAt(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

type AuthenticatedAppSessionOverride = Partial<Omit<SessionPayload, "user">> & {
  user?: Partial<SessionPayload["user"]>;
};

function createAuthenticatedSession(override: AuthenticatedAppSessionOverride = {}): SessionPayload {
  return {
    ...defaultAuthenticatedAppSession,
    ...override,
    user: {
      ...defaultAuthenticatedAppSession.user,
      ...override.user,
    },
  };
}

export function renderAuthenticatedAppAt(
  pathname: string,
  options: { session?: AuthenticatedAppSessionOverride } = {},
) {
  const session = createAuthenticatedSession(options.session);
  const sessionContext: SessionContextValue = {
    status: "authenticated",
    session,
    refresh: () => undefined,
  };
  return render(
    <MemoryRouter
      initialEntries={[pathname]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <MonthProvider>
        <ImportProgressProvider>
          <SessionContext.Provider value={sessionContext}>
            <PageSessionStateProvider>
              <ImportWorkflowDraftProvider>
                <AppChromeProvider initialShellHeaderMounted>
                  <nav aria-label="测试导航">
                    <Link to="/settings">设置</Link>
                    <Link to="/imports/invoices">发票导入</Link>
                    <Link to="/imports/bank-transactions">银行流水导入</Link>
                    <Link to="/imports/etc-invoices">ETC发票导入</Link>
                    <Link to="/bank-details">银行明细</Link>
                    <Link to="/input-invoice-usage">进项发票使用情况</Link>
                    <Link to="/output-invoice-collections">销项发票收款情况</Link>
                    <Link to="/no-oa-bank-batches">免OA流水批量处理</Link>
                  </nav>
                  <main>
                    <AppRouter />
                  </main>
                </AppChromeProvider>
              </ImportWorkflowDraftProvider>
            </PageSessionStateProvider>
          </SessionContext.Provider>
        </ImportProgressProvider>
      </MonthProvider>
    </MemoryRouter>,
  );
}
