import { readFileSync } from "node:fs";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { lazy, type ComponentType, type ReactNode, useEffect, useState } from "react";
import { Link, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";

import PageRouteHost from "../app/PageRouteHost";
import {
  appPageRoutes,
  isSidebarDisclosureItem,
  sidebarGroups,
  type AppPageRoute,
} from "../app/pageRegistry";
import { usePageActivation } from "../contexts/PageRuntimeContext";

function Harness({
  children,
  initialPath = "/a",
}: {
  children: ReactNode;
  initialPath?: string;
}) {
  return (
    <MemoryRouter initialEntries={[initialPath]}>
      {children}
    </MemoryRouter>
  );
}

function createRoute(path: string, pageKey: string, Component: AppPageRoute["component"]): AppPageRoute {
  return {
    path,
    pageKey,
    component: Component,
    preload: () => Promise.resolve(),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("PageRouteHost", () => {
  test("does not gate route switching behind animation timers", () => {
    const source = readFileSync("src/app/PageRouteHost.tsx", "utf8");

    expect(source).not.toMatch(/\bsetTimeout\b/);
    expect(source).not.toMatch(/\bsetInterval\b/);
    expect(source).not.toMatch(/\brequestAnimationFrame\b/);
    expect(source).not.toMatch(/\bstartTransition\b/);
    expect(source).not.toMatch(/\bAnimatePresence\b/);
    expect(source).not.toMatch(/transitionend/i);
  });

  test("updates the page title and moves route focus to the main region", async () => {
    function CostPage() {
      return <p>成本页面</p>;
    }

    render(
      <MemoryRouter initialEntries={["/cost-statistics"]}>
        <main id="main-content" tabIndex={-1}>
          <PageRouteHost routes={[createRoute("/cost-statistics", "cost-statistics", CostPage)]} />
        </main>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(document.title).toBe("成本统计 · 财务运营平台");
      expect(document.activeElement).toBe(screen.getByRole("main"));
    });
  });

  test("unmounts the previous page and mounts the next route immediately", async () => {
    const user = userEvent.setup();
    const mountCounts = { a: 0, b: 0 };
    const unmountCounts = { a: 0, b: 0 };

    function PageA() {
      const [count, setCount] = useState(0);
      const activation = usePageActivation("page-a");
      useEffect(() => {
        mountCounts.a += 1;
        return () => {
          unmountCounts.a += 1;
        };
      }, []);
      return (
        <section data-testid="page-a">
          <p data-testid="page-a-active">{String(activation.active)}</p>
          <p data-testid="page-a-count">{count}</p>
          <button type="button" onClick={() => setCount((current) => current + 1)}>increment a</button>
          <Link to="/b">to b</Link>
        </section>
      );
    }

    function PageB() {
      useEffect(() => {
        mountCounts.b += 1;
        return () => {
          unmountCounts.b += 1;
        };
      }, []);
      return (
        <section data-testid="page-b">
          <Link to="/a">to a</Link>
        </section>
      );
    }

    const routes = [
      createRoute("/a", "page-a", PageA),
      createRoute("/b", "page-b", PageB),
    ];

    render(<PageRouteHost routes={routes} />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "increment a" }));
    expect(screen.getByTestId("page-a-count")).toHaveTextContent("1");
    expect(screen.getByTestId("page-a-active")).toHaveTextContent("true");

    await user.click(screen.getByRole("link", { name: "to b" }));

    expect(screen.queryByTestId("page-a")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-b")).toBeInTheDocument();
    expect(mountCounts).toEqual({ a: 1, b: 1 });
    expect(unmountCounts).toEqual({ a: 1, b: 0 });

    await user.click(screen.getByRole("link", { name: "to a" }));

    expect(screen.getByTestId("page-a-count")).toHaveTextContent("0");
    expect(mountCounts).toEqual({ a: 2, b: 1 });
    expect(unmountCounts).toEqual({ a: 1, b: 1 });
  });

  test("redirects unknown paths to the root route", async () => {
    function RootPage() {
      return <p>root route</p>;
    }

    render(<PageRouteHost routes={[createRoute("/", "root", RootPage)]} />, {
      wrapper: ({ children }) => <Harness initialPath="/missing">{children}</Harness>,
    });

    expect(await screen.findByText("root route")).toBeInTheDocument();
  });

  test("renders lazy routes with a lightweight fallback", async () => {
    const user = userEvent.setup();
    let resolveLazyPage: ((module: { default: ComponentType }) => void) | null = null;
    const LazyPage = lazy(() => new Promise<{ default: ComponentType }>((resolve) => {
      resolveLazyPage = resolve;
    }));

    function PageA() {
      return <Link to="/lazy">to lazy</Link>;
    }

    function PageB() {
      return <p>lazy page loaded</p>;
    }

    const routes = [
      createRoute("/a", "page-a", PageA),
      createRoute("/lazy", "lazy-page", LazyPage),
    ];

    render(<PageRouteHost routes={routes} />, { wrapper: Harness });

    expect(screen.queryByText("lazy page loaded")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "to lazy" }));

    expect(screen.getByTestId("page-route-loading-lazy-page")).toBeInTheDocument();
    await act(async () => {
      resolveLazyPage?.({ default: PageB });
    });

    expect(await screen.findByText("lazy page loaded")).toBeInTheDocument();
  });

  test("keeps app registry focused on route chunks and sidebar preload", () => {
    const routeByPath = new Map(appPageRoutes.map((route) => [route.path, route]));
    const sidebarItems = sidebarGroups.flatMap((group) => group.items.flatMap((item) => (
      isSidebarDisclosureItem(item) ? item.children : [item]
    )));
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    const systemItems = sidebarGroups.find((group) => group.title === "系统操作")?.items ?? [];

    expect(appPageRoutes).toHaveLength(18);
    expect(appPageRoutes.map((route) => route.path)).toEqual([
      "/",
      "/cost-statistics",
      "/bank-details",
      "/oa-pending-payments",
      "/bank-flow-rule-batches",
      "/batch-accounting",
      "/turnover-ledger",
      "/etc-tickets",
      "/tax-offset",
      "/pending-invoices",
      "/input-invoice-usage",
      "/output-invoice-collections",
      "/settings",
      "/operations/app-health",
      "/operations/history",
      "/imports/bank-transactions",
      "/imports/invoices",
      "/imports/etc-invoices",
    ]);
    expect(financeItems).toHaveLength(12);
    expect(systemItems).toHaveLength(4);
    expect(new Set(appPageRoutes.map((route) => route.pageKey))).toHaveLength(appPageRoutes.length);
    expect(sidebarItems.every((item) => routeByPath.has(item.to))).toBe(true);
    expect(sidebarItems.every((item) => typeof item.preload === "function")).toBe(true);
    expect(appPageRoutes.every((route) => typeof route.preload === "function")).toBe(true);
    expect(appPageRoutes.every((route) => (
      Object.keys(route).every((key) => ["path", "pageKey", "component", "preload", "end", "requiresAdmin"].includes(key))
    ))).toBe(true);
  });

  test("keeps every registered page behind the shared activation boundary", () => {
    const pageOwners = [
      "src/pages/ReconciliationWorkbenchPage.tsx",
      "src/pages/CostStatisticsPage.tsx",
      "src/pages/BankDetailsPage.tsx",
      "src/pages/OaPendingPaymentsPage.tsx",
      "src/pages/BankFlowRuleBatchPage.tsx",
      "src/pages/BatchAccountingPage.tsx",
      "src/pages/TurnoverLedgerPage.tsx",
      "src/pages/EtcTicketManagementPage.tsx",
      "src/pages/TaxOffsetPage.tsx",
      "src/pages/PendingInvoicesPage.tsx",
      "src/pages/InputInvoiceUsagePage.tsx",
      "src/pages/OaPendingPaymentsPage.tsx",
      "src/pages/OutputInvoiceCollectionsPage.tsx",
      "src/pages/InputInvoiceUsagePage.tsx",
      "src/pages/OutputInvoiceCollectionsPage.tsx",
      "src/pages/SettingsPage.tsx",
      "src/pages/AppHealthOperationsPage.tsx",
      "src/pages/OperationHistoryPage.tsx",
      "src/components/imports/ImportWorkflowPage.tsx",
    ];

    expect(appPageRoutes).toHaveLength(18);
    for (const path of pageOwners) {
      expect(readFileSync(path, "utf8"), path).toContain("useOptionalPageActivation");
    }
  });

  test("leaves only the current route content after navigation", async () => {
    const user = userEvent.setup();

    function PageA() {
      return <Link to="/b">to b</Link>;
    }

    function PageB() {
      return <p>page b</p>;
    }

    render(<PageRouteHost routes={[createRoute("/a", "page-a", PageA), createRoute("/b", "page-b", PageB)]} />, {
      wrapper: Harness,
    });

    await user.click(screen.getByRole("link", { name: "to b" }));

    await waitFor(() => {
      expect(screen.getByText("page b")).toBeInTheDocument();
    });
    expect(screen.queryByRole("link", { name: "to b" })).not.toBeInTheDocument();
  });

  test("does not reload the current business page on focus, visibility, or BFCache events", () => {
    const loadCurrentPage = vi.fn();

    function PageA() {
      const activation = usePageActivation("page-a");
      useEffect(() => {
        if (activation.active) {
          loadCurrentPage(activation.activationGeneration);
        }
      }, [activation.active, activation.activationGeneration]);
      return (
        <section>
          <span data-testid="page-active">{String(activation.active)}</span>
          <span data-testid="page-generation">{activation.activationGeneration}</span>
        </section>
      );
    }

    render(<PageRouteHost routes={[createRoute("/a", "page-a", PageA)]} />, { wrapper: Harness });
    expect(loadCurrentPage).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("page-active")).toHaveTextContent("true");
    expect(screen.getByTestId("page-generation")).toHaveTextContent("1");

    act(() => {
      window.dispatchEvent(new Event("blur"));
      document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("focus"));
      const pageShowEvent = new Event("pageshow") as PageTransitionEvent;
      Object.defineProperty(pageShowEvent, "persisted", { value: true });
      window.dispatchEvent(pageShowEvent);
    });

    expect(loadCurrentPage).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("page-active")).toHaveTextContent("true");
    expect(screen.getByTestId("page-generation")).toHaveTextContent("1");
  });

  test("keeps deleted cross-page business refresh channels out of production pages", () => {
    const sourcePaths = [
      "src/pages/ReconciliationWorkbenchPage.tsx",
      "src/pages/CostStatisticsPage.tsx",
      "src/pages/BankDetailsPage.tsx",
      "src/pages/BankFlowRuleBatchPage.tsx",
      "src/pages/BatchAccountingPage.tsx",
      "src/pages/TurnoverLedgerPage.tsx",
      "src/pages/EtcTicketManagementPage.tsx",
      "src/pages/TaxOffsetPage.tsx",
      "src/pages/PendingInvoicesPage.tsx",
    ];
    for (const path of sourcePaths) {
      const source = readFileSync(path, "utf8");
      expect(source, path).not.toContain("domainEvents");
      expect(source, path).not.toContain("useActiveFinanceDomainEvent");
      expect(source, path).not.toContain("finops:bank-transaction-tags-updated");
      expect(source, path).not.toMatch(/\bBroadcastChannel\b/);
    }
  });

});
