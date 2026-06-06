import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ComponentType, type ReactNode, useEffect, useState } from "react";
import { Link, MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, test, vi } from "vitest";

import PageKeepAliveHost from "../app/PageKeepAliveHost";
import { appPageRoutes, sidebarGroups, type AppPageRoute } from "../app/pageRegistry";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { useActivePageEvent, usePageActivation } from "../contexts/PageRuntimeContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";

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

function createSession(userId = "101"): SessionContextValue {
  return {
    status: "authenticated",
    session: {
      ...defaultSessionPayload,
      user: {
        ...defaultSessionPayload.user,
        userId,
        username: `user-${userId}`,
      },
    },
    refresh: () => undefined,
  };
}

function Harness({
  children,
  initialPath = "/a",
  session = createSession(),
}: {
  children: ReactNode;
  initialPath?: string;
  session?: SessionContextValue;
}) {
  return (
    <SessionContext.Provider value={session}>
      <PageSessionStateProvider>
        <MemoryRouter initialEntries={[initialPath]}>
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
    keepAlive: true,
    sessionVersion: 1,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("PageKeepAliveHost", () => {
  test("keeps visited page instances mounted and restores them when navigating back", async () => {
    const user = userEvent.setup();
    const mountCounts = { a: 0, b: 0 };

    function PageA() {
      const [count, setCount] = useState(0);
      const activation = usePageActivation("page-a");
      useEffect(() => {
        mountCounts.a += 1;
      }, []);
      return (
        <section>
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
      }, []);
      return <Link to="/a">to a</Link>;
    }

    const routes = [
      createRoute("/a", "page-a", PageA),
      createRoute("/b", "page-b", PageB),
    ];

    render(<PageKeepAliveHost routes={routes} />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "increment a" }));
    expect(screen.getByTestId("page-a-count")).toHaveTextContent("1");
    expect(screen.getByTestId("page-a-active")).toHaveTextContent("true");

    await user.click(screen.getByRole("link", { name: "to b" }));

    expect(screen.getByTestId("page-frame-page-a")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("page-frame-page-b")).toHaveAttribute("aria-hidden", "false");
    expect(screen.getByTestId("page-a-active")).toHaveTextContent("false");

    await user.click(screen.getByRole("link", { name: "to a" }));

    expect(screen.getByTestId("page-a-count")).toHaveTextContent("1");
    expect(screen.getByTestId("page-a-active")).toHaveTextContent("true");
    expect(mountCounts).toEqual({ a: 1, b: 1 });
  });

  test("evicts least recently used pages when the cache limit is reached", async () => {
    const user = userEvent.setup();
    const mountCounts = { a: 0, b: 0, c: 0 };

    function createPage(key: keyof typeof mountCounts, nextPath: string) {
      return function DemoPage() {
        useEffect(() => {
          mountCounts[key] += 1;
        }, []);
        return <Link to={nextPath}>{`to ${nextPath}`}</Link>;
      };
    }

    const routes = [
      createRoute("/a", "page-a", createPage("a", "/b")),
      createRoute("/b", "page-b", createPage("b", "/c")),
      createRoute("/c", "page-c", createPage("c", "/a")),
    ];

    render(<PageKeepAliveHost routes={routes} maxEntries={2} />, { wrapper: Harness });

    await user.click(screen.getByRole("link", { name: "to /b" }));
    await user.click(screen.getByRole("link", { name: "to /c" }));
    expect(screen.queryByTestId("page-frame-page-a")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "to /a" }));

    await waitFor(() => {
      expect(mountCounts.a).toBe(2);
    });
  });

  test("default cache limit keeps every registered app page mounted", async () => {
    const user = userEvent.setup();
    const routes = appPageRoutes.map((route, index) => {
      const PageComponent = () => (
        <div>
          <p>{route.pageKey}</p>
          {index + 1 < appPageRoutes.length ? <Link to={appPageRoutes[index + 1].path}>next route</Link> : null}
        </div>
      );
      return {
        ...route,
        component: PageComponent,
        maxIdleMs: undefined,
      };
    });

    render(<PageKeepAliveHost routes={routes} />, { wrapper: Harness });

    for (let index = 1; index < routes.length; index += 1) {
      await user.click(screen.getByRole("link", { name: "next route" }));
    }

    expect(routes).toHaveLength(17);
    expect(screen.getByTestId(`page-frame-${routes[0].pageKey}`)).toBeInTheDocument();
    expect(screen.getAllByTestId(/^page-frame-/)).toHaveLength(routes.length);
  });

  test("default cache limit evicts only after a twenty-first route is visited", async () => {
    const user = userEvent.setup();
    const routes = Array.from({ length: 21 }, (_, index) => {
      const path = `/demo-${index + 1}`;
      const nextPath = index + 1 < 21 ? `/demo-${index + 2}` : "/demo-21";
      const PageComponent = () => (
        <div>
          <p>{path}</p>
          {index + 1 < 21 ? <Link to={nextPath}>next route</Link> : null}
        </div>
      );
      return createRoute(path, `demo-${index + 1}`, PageComponent);
    });

    render(<PageKeepAliveHost routes={routes} />, {
      wrapper: ({ children }) => <Harness initialPath="/demo-1">{children}</Harness>,
    });

    for (let index = 1; index < routes.length; index += 1) {
      await user.click(screen.getByRole("link", { name: "next route" }));
    }

    expect(screen.queryByTestId("page-frame-demo-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("page-frame-demo-2")).toBeInTheDocument();
    expect(screen.getAllByTestId(/^page-frame-/)).toHaveLength(20);
  });

  test("keeps every sidebar route backed by a keep-alive page registry entry", () => {
    const routeByPath = new Map(appPageRoutes.map((route) => [route.path, route]));
    const sidebarItems = sidebarGroups.flatMap((group) => group.items);

    expect(appPageRoutes).toHaveLength(17);
    expect(appPageRoutes.every((route) => route.keepAlive)).toBe(true);
    expect(new Set(appPageRoutes.map((route) => route.pageKey))).toHaveLength(appPageRoutes.length);
    expect(sidebarItems.every((item) => routeByPath.get(item.to)?.keepAlive === true)).toBe(true);
  });

  test("clears cached pages when the authenticated user scope changes", async () => {
    const user = userEvent.setup();
    const mountCounts = { a: 0 };

    function PageA() {
      useEffect(() => {
        mountCounts.a += 1;
      }, []);
      return <p>page a</p>;
    }

    const routes = [createRoute("/a", "page-a", PageA)];

    function ScopeSwitchHarness() {
      const [userId, setUserId] = useState("101");
      return (
        <SessionContext.Provider value={createSession(userId)}>
          <PageSessionStateProvider>
            <MemoryRouter initialEntries={["/a"]}>
              <button type="button" onClick={() => setUserId("202")}>switch user</button>
              <PageKeepAliveHost routes={routes} />
            </MemoryRouter>
          </PageSessionStateProvider>
        </SessionContext.Provider>
      );
    }

    render(<ScopeSwitchHarness />);
    await user.click(screen.getByRole("button", { name: "switch user" }));

    await waitFor(() => {
      expect(mountCounts.a).toBe(2);
    });
  });

  test("defers page events while inactive and replays the last one when active again", async () => {
    const user = userEvent.setup();
    const handler = vi.fn();

    function PageA() {
      useActivePageEvent("demo-domain-event", handler);
      return <Link to="/b">to b</Link>;
    }

    function PageB() {
      return <Link to="/a">to a</Link>;
    }

    const routes = [
      createRoute("/a", "page-a", PageA),
      createRoute("/b", "page-b", PageB),
    ];

    render(<PageKeepAliveHost routes={routes} />, { wrapper: Harness });
    await user.click(screen.getByRole("link", { name: "to b" }));

    act(() => {
      window.dispatchEvent(new CustomEvent("demo-domain-event", { detail: { source: "test" } }));
    });

    expect(handler).not.toHaveBeenCalled();

    await user.click(screen.getByRole("link", { name: "to a" }));

    await waitFor(() => {
      expect(handler).toHaveBeenCalledTimes(1);
    });
    expect(handler.mock.calls[0][0]).toBeInstanceOf(CustomEvent);
  });
});
