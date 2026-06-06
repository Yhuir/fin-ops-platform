import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { type ReactNode } from "react";

import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import {
  buildPageSessionStorageKey,
  createStoredPayload,
} from "../contexts/pageSessionStorage";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import { usePageScrollSession } from "../hooks/usePageScrollSession";

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
        {children}
      </PageSessionStateProvider>
    </SessionContext.Provider>
  );
}

function ScrollDemo() {
  const scrollRef = usePageScrollSession<HTMLDivElement>({
    pageKey: "demo-page",
    scrollKey: "main-table",
    ttlMs: 60_000,
    debounceMs: 0,
  });

  return (
    <div>
      <div
        ref={scrollRef}
        data-testid="scroll-target"
        style={{ height: 80, overflow: "auto", width: 120 }}
      >
        <div style={{ height: 400, width: 400 }}>content</div>
      </div>
      <button type="button">focusable</button>
    </div>
  );
}

function keyFor() {
  return buildPageSessionStorageKey({
    userScope: "101",
    pageKey: "demo-page",
    stateKey: "scroll.main-table",
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  window.sessionStorage.clear();
});

describe("usePageScrollSession", () => {
  test("saves and restores element scroll offsets", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<ScrollDemo />, { wrapper: Harness });
    const target = screen.getByTestId("scroll-target");

    act(() => {
      target.scrollTop = 120;
      target.scrollLeft = 48;
      target.dispatchEvent(new Event("scroll"));
    });
    await user.click(screen.getByRole("button", { name: "focusable" }));

    expect(window.sessionStorage.getItem(keyFor())).toContain('"top":120');
    expect(window.sessionStorage.getItem(keyFor())).toContain('"left":48');

    unmount();
    render(<ScrollDemo />, { wrapper: Harness });

    const restoredTarget = screen.getByTestId("scroll-target");
    expect(restoredTarget.scrollTop).toBe(120);
    expect(restoredTarget.scrollLeft).toBe(48);
  });

  test("ignores invalid stored scroll payloads", () => {
    window.sessionStorage.setItem(
      keyFor(),
      JSON.stringify(createStoredPayload({
        version: 1,
        ttlMs: 60_000,
        value: { top: "bad", left: 10 },
      })),
    );

    render(<ScrollDemo />, { wrapper: Harness });

    const target = screen.getByTestId("scroll-target");
    expect(target.scrollTop).toBe(0);
    expect(target.scrollLeft).toBe(0);
    expect(window.sessionStorage.getItem(keyFor())).toBeNull();
  });
});
