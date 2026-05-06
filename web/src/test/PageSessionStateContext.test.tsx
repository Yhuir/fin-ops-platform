import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { type ReactNode, useEffect } from "react";

import {
  PageSessionStateProvider,
  usePageSessionState,
} from "../contexts/PageSessionStateContext";
import {
  buildPageSessionStorageKey,
  createStoredPayload,
} from "../contexts/pageSessionStorage";
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

function Harness({ children, session = createSession() }: { children: ReactNode; session?: SessionContextValue }) {
  return (
    <SessionContext.Provider value={session}>
      <PageSessionStateProvider>
        {children}
      </PageSessionStateProvider>
    </SessionContext.Provider>
  );
}

function DemoState({
  pageKey = "demo",
  stateKey = "field",
  version = 1,
  ttlMs = 60_000,
  validate,
  debounceMs,
}: {
  pageKey?: string;
  stateKey?: string;
  version?: number;
  ttlMs?: number;
  validate?: (value: unknown) => value is string;
  debounceMs?: number;
}) {
  const sessionState = usePageSessionState({
    pageKey,
    stateKey,
    version,
    initialValue: "default",
    ttlMs,
    storage: "session",
    validate,
    debounceMs,
  });

  return (
    <div>
      <p data-testid="value">{sessionState.value}</p>
      <p data-testid="restore-state">{sessionState.restoreState}</p>
      <button type="button" onClick={() => sessionState.setValue("changed")}>set</button>
      <button type="button" onClick={sessionState.reset}>reset</button>
    </div>
  );
}

function keyFor(userScope = "101", pageKey = "demo", stateKey = "field") {
  return buildPageSessionStorageKey({ userScope, pageKey, stateKey });
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("PageSessionStateProvider", () => {
  test("returns the default value when no session value exists", () => {
    render(<DemoState />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("idle");
  });

  test("persists and restores values by page and state key", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<DemoState />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "set" }));
    expect(screen.getByTestId("value")).toHaveTextContent("changed");
    expect(window.sessionStorage.getItem(keyFor())).toContain("changed");

    unmount();
    render(<DemoState />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("changed");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("restored");
  });

  test("reset clears the stored value", async () => {
    const user = userEvent.setup();
    render(<DemoState />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "set" }));
    await user.click(screen.getByRole("button", { name: "reset" }));

    expect(screen.getByTestId("value")).toHaveTextContent("default");
    expect(window.sessionStorage.getItem(keyFor())).toBeNull();
  });

  test("clears expired values on read", () => {
    window.sessionStorage.setItem(
      keyFor(),
      JSON.stringify(createStoredPayload({
        version: 1,
        ttlMs: -1,
        value: "old",
        now: Date.now() - 10_000,
      })),
    );

    render(<DemoState />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("expired");
    expect(window.sessionStorage.getItem(keyFor())).toBeNull();
  });

  test("clears values with mismatched schema version", () => {
    window.sessionStorage.setItem(
      keyFor(),
      JSON.stringify(createStoredPayload({
        version: 99,
        ttlMs: 60_000,
        value: "old",
      })),
    );

    render(<DemoState version={1} />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("invalid");
    expect(window.sessionStorage.getItem(keyFor())).toBeNull();
  });

  test("clears values that fail validation", () => {
    window.sessionStorage.setItem(
      keyFor(),
      JSON.stringify(createStoredPayload({
        version: 1,
        ttlMs: 60_000,
        value: 123,
      })),
    );

    render(<DemoState validate={(value): value is string => typeof value === "string"} />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("invalid");
    expect(window.sessionStorage.getItem(keyFor())).toBeNull();
  });

  test("isolates values by page key and state key", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<DemoState pageKey="page-a" stateKey="state-a" />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "set" }));
    unmount();
    render(<DemoState pageKey="page-b" stateKey="state-a" />, { wrapper: Harness });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
  });

  test("isolates values by user scope", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<DemoState />, {
      wrapper: ({ children }) => <Harness session={createSession("101")}>{children}</Harness>,
    });

    await user.click(screen.getByRole("button", { name: "set" }));
    unmount();
    render(<DemoState />, {
      wrapper: ({ children }) => <Harness session={createSession("202")}>{children}</Harness>,
    });

    expect(screen.getByTestId("value")).toHaveTextContent("default");
  });

  test("falls back to memory when sessionStorage writing fails", async () => {
    const user = userEvent.setup();
    const brokenSessionStorage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(() => {
        throw new Error("quota exceeded");
      }),
      removeItem: vi.fn(),
      key: vi.fn(() => null),
      clear: vi.fn(),
      length: 0,
    } as unknown as Storage;
    vi.stubGlobal("sessionStorage", brokenSessionStorage);
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: brokenSessionStorage,
    });

    render(<DemoState />, { wrapper: Harness });
    await user.click(screen.getByRole("button", { name: "set" }));

    expect(screen.getByTestId("value")).toHaveTextContent("changed");
    expect(screen.getByTestId("restore-state")).toHaveTextContent("unavailable");
  });

  test("debounces sessionStorage writes", async () => {
    vi.useFakeTimers();

    function DebouncedState() {
      const state = usePageSessionState({
        pageKey: "demo",
        stateKey: "debounced",
        version: 1,
        initialValue: "",
        ttlMs: 60_000,
        storage: "session",
        debounceMs: 100,
      });

      useEffect(() => {
        state.setValue("a");
        state.setValue("b");
        state.setValue("c");
      }, []);

      return <p data-testid="value">{state.value}</p>;
    }

    render(<DebouncedState />, { wrapper: Harness });
    expect(screen.getByTestId("value")).toHaveTextContent("c");
    expect(window.sessionStorage.getItem(keyFor("101", "demo", "debounced"))).toBeNull();

    act(() => {
      vi.advanceTimersByTime(100);
    });

    expect(window.sessionStorage.getItem(keyFor("101", "demo", "debounced"))).toContain("c");
  });
});
