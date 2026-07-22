import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ComponentType, type ReactNode } from "react";
import { Link, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";

import PageRouteHost from "../app/PageRouteHost";
import type { AppPageRoute } from "../app/pageRegistry";
import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import { FINANCE_DOMAIN_EVENTS, emitFinanceDomainEvent } from "../features/domainEvents";
import type { SessionPayload } from "../features/session/api";
import { useActiveFinanceDomainEvent } from "../hooks/useActiveFinanceDomainEvent";

const defaultSessionPayload: SessionPayload = {
  allowed: true,
  user: {
    userId: "101",
    username: "liuji",
    nickname: "刘际涛",
    displayName: "刘际涛",
    deptId: "88",
    deptName: "财务部",
    avatar: null,
  },
  roles: ["finance"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

const session: SessionContextValue = {
  status: "authenticated",
  session: defaultSessionPayload,
  refresh: () => undefined,
};

function Harness({ children }: { children: ReactNode }) {
  return (
    <SessionContext.Provider value={session}>
      <PageSessionStateProvider>
        <MemoryRouter initialEntries={["/a"]}>
          {children}
        </MemoryRouter>
      </PageSessionStateProvider>
    </SessionContext.Provider>
  );
}

function createRoute(path: string, pageKey: string, Component: ComponentType): AppPageRoute {
  return {
    path,
    pageKey,
    component: Component,
    preload: () => Promise.resolve(),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("useActiveFinanceDomainEvent", () => {
  test("defers the latest event while a mounted page is hidden and handles it once when visible", async () => {
    const handler = vi.fn();

    function Page() {
      useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, handler);
      return <div>page</div>;
    }

    const { rerender } = render(
      <PageRuntimeProvider value={{ pageKey: "workbench", active: false, activationGeneration: 1 }}>
        <Page />
      </PageRuntimeProvider>,
    );

    act(() => {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, { action: "hidden-first" });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.workbenchRelationUpdated, { action: "hidden-latest" });
    });
    expect(handler).not.toHaveBeenCalled();

    rerender(
      <PageRuntimeProvider value={{ pageKey: "workbench", active: true, activationGeneration: 2 }}>
        <Page />
      </PageRuntimeProvider>,
    );

    await waitFor(() => expect(handler).toHaveBeenCalledTimes(1));
    expect(handler.mock.calls[0][0].detail.action).toBe("hidden-latest");
  });

  test("handles events while mounted and does not replay events after route unmount", async () => {
    const user = userEvent.setup();
    const handler = vi.fn();

    function PageA() {
      useActiveFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, handler);
      return <Link to="/b">to b</Link>;
    }

    function PageB() {
      return <Link to="/a">to a</Link>;
    }

    render(
      <PageRouteHost
        routes={[
          createRoute("/a", "page-a", PageA),
          createRoute("/b", "page-b", PageB),
        ]}
      />,
      { wrapper: Harness },
    );

    act(() => {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, { action: "active" });
    });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler.mock.calls[0][0].detail.action).toBe("active");

    await user.click(screen.getByRole("link", { name: "to b" }));

    act(() => {
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, { action: "inactive-1" });
      emitFinanceDomainEvent(FINANCE_DOMAIN_EVENTS.bankTransactionCategoryUpdated, { action: "inactive-2" });
    });

    expect(handler).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("link", { name: "to a" }));

    await waitFor(() => expect(screen.getByRole("link", { name: "to b" })).toBeInTheDocument());
    expect(handler).toHaveBeenCalledTimes(1);
  });
});
