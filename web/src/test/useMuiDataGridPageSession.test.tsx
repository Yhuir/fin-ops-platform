import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { type ReactNode } from "react";
import type { GridRowSelectionModel } from "@mui/x-data-grid";

import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import { useMuiDataGridPageSession } from "../hooks/useMuiDataGridPageSession";
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

function GridSessionDemo({
  columnsVersion = "v1",
  validRowIds,
}: {
  columnsVersion?: string;
  validRowIds?: Array<string | number>;
}) {
  const gridSession = useMuiDataGridPageSession({
    pageKey: "demo-page",
    gridKey: "main",
    columnsVersion,
    validRowIds,
    defaultPaginationModel: { page: 0, pageSize: 25 },
    debounceMs: 0,
  });

  const selectedIds = Array.from(gridSession.rowSelectionModel.ids).join(",");

  return (
    <div>
      <p data-testid="pagination">{`${gridSession.paginationModel.page}:${gridSession.paginationModel.pageSize}`}</p>
      <p data-testid="sort">{gridSession.sortModel.map((item) => `${item.field}:${item.sort}`).join(",")}</p>
      <p data-testid="filter">{gridSession.filterModel.items.map((item) => `${item.field}:${item.value}`).join(",")}</p>
      <p data-testid="visibility">{JSON.stringify(gridSession.columnVisibilityModel)}</p>
      <p data-testid="selection">{selectedIds}</p>
      <p data-testid="widths">{JSON.stringify(gridSession.columnWidths)}</p>
      <button type="button" onClick={() => gridSession.onPaginationModelChange({ page: 2, pageSize: 50 })}>page</button>
      <button type="button" onClick={() => gridSession.onSortModelChange([{ field: "amount", sort: "desc" }])}>sort</button>
      <button type="button" onClick={() => gridSession.onFilterModelChange({ items: [{ id: 1, field: "name", operator: "contains", value: "云南" }] })}>filter</button>
      <button type="button" onClick={() => gridSession.onColumnVisibilityModelChange({ amount: false })}>visibility</button>
      <button
        type="button"
        onClick={() => gridSession.onRowSelectionModelChange({ type: "include", ids: new Set(["row-1", "missing"]) } as GridRowSelectionModel)}
      >
        select
      </button>
      <button type="button" onClick={() => gridSession.setColumnWidths({ amount: 180 })}>widths</button>
    </div>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  window.sessionStorage.clear();
});

describe("useMuiDataGridPageSession", () => {
  test("saves and restores controlled DataGrid models", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<GridSessionDemo />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "page" }));
    await user.click(screen.getByRole("button", { name: "sort" }));
    await user.click(screen.getByRole("button", { name: "filter" }));
    await user.click(screen.getByRole("button", { name: "visibility" }));
    await user.click(screen.getByRole("button", { name: "widths" }));
    unmount();

    render(<GridSessionDemo />, { wrapper: Harness });

    expect(screen.getByTestId("pagination")).toHaveTextContent("2:50");
    expect(screen.getByTestId("sort")).toHaveTextContent("amount:desc");
    expect(screen.getByTestId("filter")).toHaveTextContent("name:云南");
    expect(screen.getByTestId("visibility")).toHaveTextContent('"amount":false');
    expect(screen.getByTestId("widths")).toHaveTextContent('"amount":180');
  });

  test("filters restored row selection ids against current rows", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<GridSessionDemo validRowIds={["row-1"]} />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "select" }));
    unmount();
    render(<GridSessionDemo validRowIds={["row-1"]} />, { wrapper: Harness });

    expect(screen.getByTestId("selection")).toHaveTextContent("row-1");
    expect(screen.getByTestId("selection")).not.toHaveTextContent("missing");
  });

  test("drops saved grid state when columns version changes", async () => {
    const user = userEvent.setup();
    const { unmount } = render(<GridSessionDemo columnsVersion="v1" />, { wrapper: Harness });

    await user.click(screen.getByRole("button", { name: "page" }));
    unmount();
    render(<GridSessionDemo columnsVersion="v2" />, { wrapper: Harness });

    expect(screen.getByTestId("pagination")).toHaveTextContent("0:25");
  });
});

