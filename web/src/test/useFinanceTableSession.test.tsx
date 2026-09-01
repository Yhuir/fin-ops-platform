import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ReactNode } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import {
  useFinanceTableScrollSession,
  useFinanceTableSession,
} from "../hooks/useFinanceTableSession";

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
  canAccessApp: true,
  canAdminAccess: false,
  allowedPageKeys: ["demo"],
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

function FinanceTableSessionDemo({
  columnsVersion = "v1",
  validRowIds,
}: {
  columnsVersion?: string;
  validRowIds?: Array<string | number>;
}) {
  const tableSession = useFinanceTableSession({
    pageKey: "demo-page",
    tableKey: "main",
    columnsVersion,
    validRowIds,
    defaultPaginationModel: { page: 1, pageSize: 25 },
    debounceMs: 0,
  });

  return (
    <div>
      <p data-testid="pagination">{`${tableSession.paginationModel.page}:${tableSession.paginationModel.pageSize}`}</p>
      <p data-testid="sort">
        {tableSession.sortDescriptor
          ? `${tableSession.sortDescriptor.column}:${tableSession.sortDescriptor.direction}`
          : "none"}
      </p>
      <p data-testid="selection">{Array.from(tableSession.selectedRowIds).join(",")}</p>
      <p data-testid="scroll">{`${tableSession.scrollPosition.top}:${tableSession.scrollPosition.left}`}</p>
      <button type="button" onClick={() => tableSession.onPaginationModelChange({ page: 3, pageSize: 50 })}>
        page
      </button>
      <button
        type="button"
        onClick={() => tableSession.onSortChange({ column: "amount", direction: "descending" })}
      >
        sort
      </button>
      <button type="button" onClick={() => tableSession.onSelectedRowIdsChange(["row-1", "missing"])}>
        select
      </button>
      <button type="button" onClick={() => tableSession.setScrollPosition({ top: 144.4, left: 32.2 })}>
        scroll
      </button>
    </div>
  );
}

function FinanceTableScrollBindingDemo() {
  const tableSession = useFinanceTableSession({
    pageKey: "demo-page",
    tableKey: "scroll-table",
    columnsVersion: "v1",
    debounceMs: 0,
  });
  const scrollBinding = useFinanceTableScrollSession(tableSession);

  return (
    <div>
      <p data-testid="scroll">{`${tableSession.scrollPosition.top}:${tableSession.scrollPosition.left}`}</p>
      <p data-testid="initial-scroll">
        {`${scrollBinding.initialScrollPosition.top}:${scrollBinding.initialScrollPosition.left}`}
      </p>
      <div ref={scrollBinding.scrollRef} data-testid="table-scroll" />
    </div>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("useFinanceTableSession", () => {
  test("saves and restores user-visible table state", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<FinanceTableSessionDemo />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "page" }));
    await user.click(screen.getByRole("button", { name: "sort" }));
    await user.click(screen.getByRole("button", { name: "select" }));
    await user.click(screen.getByRole("button", { name: "scroll" }));
    unmount();

    render(<FinanceTableSessionDemo />, { wrapper: Harness });

    expect(screen.getByTestId("pagination")).toHaveTextContent("3:50");
    expect(screen.getByTestId("sort")).toHaveTextContent("amount:descending");
    expect(screen.getByTestId("selection")).toHaveTextContent("row-1,missing");
    expect(screen.getByTestId("scroll")).toHaveTextContent("144:32");
  });

  test("filters restored row selection ids against current rows", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<FinanceTableSessionDemo validRowIds={["row-1"]} />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "select" }));
    unmount();
    render(<FinanceTableSessionDemo validRowIds={["row-1"]} />, { wrapper: Harness });

    expect(screen.getByTestId("selection")).toHaveTextContent("row-1");
    expect(screen.getByTestId("selection")).not.toHaveTextContent("missing");
  });

  test("drops saved table state when columns version changes", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<FinanceTableSessionDemo columnsVersion="v1" />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "page" }));
    unmount();
    render(<FinanceTableSessionDemo columnsVersion="v2" />, { wrapper: Harness });

    expect(screen.getByTestId("pagination")).toHaveTextContent("1:25");
  });

  test("persists native scroll container position through the scroll binding", async () => {
    render(<FinanceTableScrollBindingDemo />, { wrapper: Harness });

    const scrollContainer = screen.getByTestId("table-scroll");
    Object.defineProperty(scrollContainer, "scrollTop", { configurable: true, value: 72, writable: true });
    Object.defineProperty(scrollContainer, "scrollLeft", { configurable: true, value: 16, writable: true });
    fireEvent.scroll(scrollContainer);

    await waitFor(() => {
      expect(screen.getByTestId("scroll")).toHaveTextContent("72:16");
    });
  });
});
