import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import OaManualSearchImportTable from "../components/settings/OaManualSearchImportTable";
import AppSidebar from "../components/shell/AppSidebar";
import { AppChromeProvider, useAppChrome } from "../contexts/AppChromeContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { AppHealthStatus } from "../features/appHealth/types";

const searchRows = [
  {
    row_id: "oa-exp-1981",
    oa_no: "1981",
    applicant: "陈雄兵",
    application_date: "2025-12-23",
    form_type: "expense_claim",
    form_type_label: "日常报销",
    status: "completed",
    status_label: "已完成",
    project_name: "大理卷烟厂动力车间中水处理系统升级改造项目",
    reason: "去大理检修中水系统餐费",
    amount: "135.00",
    attachment_file_count: 2,
    importable_invoice_count: 1,
    unrecognized_attachment_count: 1,
    import_status: "not_imported",
    imported_at: null,
    can_import: true,
    disabled_reason: "",
    items: [
      {
        date: "2025-12-23",
        amount: "135.00",
        content: "餐费",
        project_name: "大理卷烟厂动力车间中水处理系统升级改造项目",
        reason: "去大理检修中水系统餐费",
        attachment_file_count: 2,
        importable_invoice_count: 1,
      },
    ],
  },
  {
    row_id: "oa-pay-2001",
    oa_no: "2001",
    applicant: "吴云江",
    application_date: "2025-12-24",
    form_type: "payment_request",
    form_type_label: "支付申请",
    status: "in_progress",
    status_label: "进行中",
    project_name: "调试服务",
    reason: "设备调试服务费",
    amount: "282.00",
    attachment_file_count: 1,
    importable_invoice_count: 0,
    unrecognized_attachment_count: 1,
    import_status: "not_imported",
    imported_at: null,
    can_import: false,
    disabled_reason: "流程未完成",
    items: [],
  },
  {
    row_id: "oa-exp-2002",
    oa_no: "2002",
    applicant: "李欣",
    application_date: "2025-12-25",
    form_type: "expense_claim",
    form_type_label: "日常报销",
    status: "in_progress",
    status_label: "进行中",
    project_name: "设备检修",
    reason: "差旅报销",
    amount: "88.00",
    attachment_file_count: 1,
    importable_invoice_count: 0,
    unrecognized_attachment_count: 1,
    import_status: "not_imported",
    imported_at: null,
    can_import: false,
    disabled_reason: "流程未完成",
    items: [],
  },
  {
    row_id: "oa-pay-2003",
    oa_no: "2003",
    applicant: "赵璇",
    application_date: "2025-12-26",
    form_type: "payment_request",
    form_type_label: "支付申请",
    status: "completed",
    status_label: "已完成",
    project_name: "设备采购",
    reason: "设备采购款",
    amount: "560.00",
    attachment_file_count: 1,
    importable_invoice_count: 0,
    unrecognized_attachment_count: 1,
    import_status: "not_imported",
    imported_at: null,
    can_import: false,
    disabled_reason: "未识别到可导入发票",
    items: [],
  },
];

const healthyStatus: AppHealthStatus = {
  level: "ok",
  reason: "系统正常",
  details: [],
  blocksMutations: false,
  sources: {
    session: "authenticated",
    backgroundJobs: "idle",
    importProgress: "idle",
    oaSync: "idle",
    workbench: "ready",
  },
};

const loadingSession: SessionContextValue = {
  status: "loading",
  refresh: () => undefined,
};

function SidebarStatusHarness() {
  const { workbenchStatus } = useAppChrome();
  return (
    <AppSidebar
      embedded={false}
      isCompact={false}
      mobileOpen={false}
      expanded={false}
      healthStatus={healthyStatus}
      workbenchStatus={workbenchStatus}
      onCloseMobile={() => undefined}
      onToggleExpanded={() => undefined}
    />
  );
}

function renderTable({ withSidebar = false }: { withSidebar?: boolean } = {}) {
  return render(
    <AppChromeProvider>
      {withSidebar ? (
        <SessionContext.Provider value={loadingSession}>
          <MemoryRouter>
            <SidebarStatusHarness />
          </MemoryRouter>
        </SessionContext.Provider>
      ) : null}
      <OaManualSearchImportTable />
    </AppChromeProvider>,
  );
}

function deferredResponse() {
  let resolve!: (value: Response) => void;
  const promise = new Promise<Response>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

function successfulImportResponse() {
  return new Response(JSON.stringify({
    imported: ["oa-exp-1981"],
    already_imported: [],
    failed: [],
    rows: [
      {
        ...searchRows[0],
        import_status: "imported",
        imported_at: "2026-05-18T10:00:00+08:00",
        importable_invoice_count: 2,
        unrecognized_attachment_count: 0,
      },
    ],
  }));
}

function installFetchMock({
  manualImportResponse,
  refreshStatusSequence,
  exactRefreshResponseRows,
  exactRefreshResponseTotal,
}: {
  manualImportResponse?: Promise<Response>;
  refreshStatusSequence?: Array<Record<string, unknown>>;
  exactRefreshResponseRows?: Array<Record<string, unknown>>;
  exactRefreshResponseTotal?: number;
} = {}) {
  let refreshStatusIndex = 0;
  let requestedRefreshRowId = "oa-exp-1981";
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/workbench/settings/oa/manual-search") {
      const exactRowId = url.searchParams.get("q");
      const exactRow = searchRows.find((row) => row.row_id === exactRowId);
      const responseRows = exactRow
        ? exactRefreshResponseRows ?? [{
          ...exactRow,
          attachment_file_count: 2,
          importable_invoice_count: 2,
          unrecognized_attachment_count: 0,
          items: exactRow.items.map((item) => ({
            ...item,
            importable_invoice_count: 2,
          })),
        }]
        : searchRows;
      return new Response(JSON.stringify({
        rows: responseRows,
        total: exactRow && exactRefreshResponseTotal !== undefined
          ? exactRefreshResponseTotal
          : responseRows.length,
        page: Number(url.searchParams.get("page") ?? 0),
        page_size: Number(url.searchParams.get("page_size") ?? 20),
      }));
    }
    if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments") {
      expect(init?.method).toBe("POST");
      const body = JSON.parse(String(init?.body)) as { row_ids: string[] };
      requestedRefreshRowId = body.row_ids[0];
      return new Response(JSON.stringify({
        event_id: "refresh-event-1",
        status: "queued",
        row_ids: [requestedRefreshRowId],
        affected_scope_keys: ["2025-12"],
      }), { status: 202 });
    }
    if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments/refresh-event-1") {
      expect(init?.method).toBe("GET");
      const defaultStatus = {
        event_id: "refresh-event-1",
        status: "done",
        row_ids: [requestedRefreshRowId],
        affected_scope_keys: ["2025-12"],
        result: {
          rows: [
            {
              row_id: requestedRefreshRowId,
              attachment_file_count: 2,
              importable_invoice_count: 2,
              unrecognized_attachment_count: 0,
            },
          ],
          errors: [],
          promotion_summary: { affected_invoice_count: 1 },
        },
      };
      const status = refreshStatusSequence?.[
        Math.min(refreshStatusIndex, refreshStatusSequence.length - 1)
      ] ?? defaultStatus;
      refreshStatusIndex += 1;
      return new Response(JSON.stringify(status));
    }
    if (url.pathname === "/api/workbench/settings/oa/manual-imports") {
      expect(init?.method).toBe("POST");
      return manualImportResponse ?? successfulImportResponse();
    }
    throw new Error(`Unhandled fetch ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("OaManualSearchImportTable", () => {
  test("searches OA rows with the shared HeroUI table and no DataGrid surface", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    expect(screen.getByRole("heading", { name: "OA全量搜索导入" })).toBeInTheDocument();
    expect(screen.getByRole("grid", { name: "OA全量搜索导入结果" })).toBeInTheDocument();
    expect(document.querySelector(".MuiDataGrid-root")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索关键字"), "陈雄兵");
    await user.type(screen.getByLabelText("开始日期"), "2025-12-01");
    await user.type(screen.getByLabelText("结束日期"), "2025-12-31");
    await user.click(screen.getByRole("button", { name: "搜索" }));

    const completedRow = await screen.findByRole("row", { name: "1981" });
    expect(completedRow).toBeInTheDocument();
    expect(within(completedRow).getByText("1981")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: "2001" })).toBeInTheDocument();
    const searchCall = fetchMock.mock.calls.find(([input]) => String(input).startsWith("/api/workbench/settings/oa/manual-search?"));
    expect(searchCall).toBeTruthy();
    const url = new URL(String(searchCall?.[0]), "http://localhost");
    expect(url.searchParams.get("q")).toBe("陈雄兵");
    expect(url.searchParams.get("form_types")).toBe("payment_request,expense_claim");
    expect(url.searchParams.get("statuses")).toBe("completed,in_progress");
    expect(url.searchParams.get("date_from")).toBe("2025-12-01");
    expect(url.searchParams.get("date_to")).toBe("2025-12-31");
  });

  test("selects importable rows, expands details, refreshes attachments, imports, and clears selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));

    const completedRow = await screen.findByRole("row", { name: "1981" });
    const inProgressRow = screen.getByRole("row", { name: "2001" });
    expect(within(inProgressRow).getByLabelText("选择 OA 2001")).toBeDisabled();
    expect(within(inProgressRow).getByLabelText("刷新 OA 2001 附件解析")).toBeDisabled();
    expect(inProgressRow).toHaveTextContent("流程未完成");

    await user.click(within(completedRow).getByLabelText("选择 OA 1981"));
    expect(screen.getByText("已选 1 个OA")).toBeInTheDocument();
    expect(screen.getByText("金额合计 ¥135.00")).toBeInTheDocument();
    expect(screen.getByText("预计发票 1 张")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "展开 OA 1981 明细" }));
    expect(await screen.findByText("餐费")).toBeInTheDocument();
    expect(screen.getByText("明细可识别发票")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "刷新 OA 1981 附件解析" }));
    expect(await screen.findByText("预计发票 2 张")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("OA 附件刷新完成");
    expect(completedRow).toHaveTextContent("2");
    expect(completedRow).toHaveTextContent("0");
    expect(screen.getByRole("row", { name: "2025-12-23" })).toHaveTextContent("2");
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/operation-barrier/status")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "导入已选OA项" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/oa/manual-imports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ row_ids: ["oa-exp-1981"], actor_id: "settings_manual_import" }),
      }),
    );
    expect(await screen.findByText("已导入")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/operation-barrier/status")).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "清空选择" }));
    expect(screen.getByText("已选 0 个OA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入已选OA项" })).toBeDisabled();
  });

  test("refreshes an in-progress expense claim without enabling formal import", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));

    const inProgressExpenseRow = await screen.findByRole("row", { name: "2002" });
    expect(within(inProgressExpenseRow).getByLabelText("选择 OA 2002")).toBeDisabled();
    const refreshButton = within(inProgressExpenseRow).getByLabelText("刷新 OA 2002 附件解析");
    expect(refreshButton).toBeEnabled();

    await user.click(refreshButton);

    expect(await screen.findByText("附件已解析，待 OA 完成后进入统一发票池")).toBeInTheDocument();
    expect(screen.getByText("已选 0 个OA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入已选OA项" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/oa/manual-search/refresh-attachments",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ row_ids: ["oa-exp-2002"] }),
      }),
    );
    const exactReadCall = fetchMock.mock.calls.find(([input]) => (
      String(input).includes("/api/workbench/settings/oa/manual-search?")
      && String(input).includes("q=oa-exp-2002")
    ));
    expect(exactReadCall).toBeTruthy();
    const exactReadUrl = new URL(String(exactReadCall?.[0]), "http://localhost");
    expect(exactReadUrl.searchParams.get("form_types")).toBe("expense_claim");
    expect(exactReadUrl.searchParams.get("statuses")).toBe("completed,in_progress");
    expect(exactReadUrl.searchParams.get("page_size")).toBe("2");
  });

  test("preserves attachment refresh for a completed payment request", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));

    const completedPaymentRow = await screen.findByRole("row", { name: "2003" });
    const refreshButton = within(completedPaymentRow).getByLabelText("刷新 OA 2003 附件解析");
    expect(refreshButton).toBeEnabled();

    await user.click(refreshButton);

    expect(await screen.findByText("OA 附件刷新完成")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/oa/manual-search/refresh-attachments",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ row_ids: ["oa-pay-2003"] }),
      }),
    );
    const exactReadCall = fetchMock.mock.calls.find(([input]) => (
      String(input).includes("/api/workbench/settings/oa/manual-search?")
      && String(input).includes("q=oa-pay-2003")
    ));
    expect(exactReadCall).toBeTruthy();
    const exactReadUrl = new URL(String(exactReadCall?.[0]), "http://localhost");
    expect(exactReadUrl.searchParams.get("form_types")).toBe("payment_request");
    expect(exactReadUrl.searchParams.get("statuses")).toBe("completed,in_progress");
  });

  test.each([
    ["missing", [], 0],
    ["duplicate", [searchRows[0], searchRows[0]], 2],
    ["reported as non-unique", [searchRows[0]], 2],
  ])("fails closed when the exact refresh read is %s", async (
    _caseName,
    exactRefreshResponseRows,
    exactRefreshResponseTotal,
  ) => {
    const user = userEvent.setup();
    installFetchMock({ exactRefreshResponseRows, exactRefreshResponseTotal });
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    await user.click(await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "OA 附件刷新完成，但无法读取最新 OA 明细",
    );
  });

  test("polls processing refreshes to completion without allowing a second submission", async () => {
    const user = userEvent.setup();
    const doneStatus = {
      event_id: "refresh-event-1",
      status: "done",
      row_ids: ["oa-exp-1981"],
      affected_scope_keys: ["2025-12"],
      result: {
        rows: [{
          row_id: "oa-exp-1981",
          attachment_file_count: 2,
          importable_invoice_count: 2,
          unrecognized_attachment_count: 0,
        }],
        errors: [],
        promotion_summary: { affected_invoice_count: 1 },
      },
    };
    const fetchMock = installFetchMock({
      refreshStatusSequence: [{
        event_id: "refresh-event-1",
        status: "processing",
        row_ids: ["oa-exp-1981"],
        affected_scope_keys: ["2025-12"],
      }, doneStatus],
    });
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    await user.click(within(await screen.findByRole("row", { name: "1981" })).getByLabelText("选择 OA 1981"));
    const refreshButton = await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" });
    const importButton = screen.getByRole("button", { name: "导入已选OA项" });
    await user.click(refreshButton);

    expect(await screen.findByText("正在重新解析 OA 附件")).toBeInTheDocument();
    expect(refreshButton).toBeDisabled();
    expect(importButton).toBeDisabled();
    await user.click(refreshButton);
    await user.click(importButton);
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/api/workbench/settings/oa/manual-imports"
    ))).toHaveLength(0);
    expect(await screen.findByText("OA 附件刷新完成", {}, { timeout: 2_500 })).toBeInTheDocument();
    expect(importButton).toBeEnabled();
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/api/workbench/settings/oa/manual-search/refresh-attachments"
    ))).toHaveLength(1);
  });

  test("stops observing a pending refresh at the client deadline without marking the task failed", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock({
      refreshStatusSequence: [{
        event_id: "refresh-event-1",
        status: "pending",
        row_ids: ["oa-exp-1981"],
        affected_scope_keys: ["2025-12"],
      }],
    });
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    const refreshButton = await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" });
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(refreshButton);
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByRole("status")).toHaveTextContent("等待 OA 附件解析");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });

    expect(screen.getByRole("status")).toHaveTextContent("OA 附件解析仍在后台进行");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(refreshButton).toBeEnabled();
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/api/workbench/settings/oa/manual-search/refresh-attachments"
    ))).toHaveLength(1);
    const statusCallCount = fetchMock.mock.calls.filter(([input]) => (
      String(input).includes("/refresh-attachments/refresh-event-1")
    )).length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input).includes("/refresh-attachments/refresh-event-1")
    ))).toHaveLength(statusCallCount);
  });

  test("times out a hung refresh status request and restores the refresh action", async () => {
    const user = userEvent.setup();
    let statusSignal: AbortSignal | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/workbench/settings/oa/manual-search") {
        return new Response(JSON.stringify({ rows: searchRows, total: 2, page: 0, page_size: 20 }));
      }
      if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments") {
        return new Response(JSON.stringify({
          event_id: "refresh-event-1",
          status: "queued",
          row_ids: ["oa-exp-1981"],
          affected_scope_keys: ["2025-12"],
        }), { status: 202 });
      }
      if (url.pathname.endsWith("/refresh-attachments/refresh-event-1")) {
        statusSignal = init?.signal ?? null;
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("timed out", "AbortError"));
          }, { once: true });
        });
      }
      throw new Error(`Unhandled fetch ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    const refreshButton = await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" });
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(refreshButton);
      await Promise.resolve();
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(15_000);
    });

    expect(statusSignal?.aborted).toBe(true);
    expect(screen.getByRole("alert")).toHaveTextContent("OA 附件刷新状态查询超时");
    expect(refreshButton).toBeEnabled();
  });

  test("keeps existing counts and shows the durable failure reason", async () => {
    const user = userEvent.setup();
    installFetchMock({
      refreshStatusSequence: [{
        event_id: "refresh-event-1",
        status: "failed",
        row_ids: ["oa-exp-1981"],
        affected_scope_keys: ["2025-12"],
        error: "OCR 推理失败",
      }],
    });
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    const completedRow = await screen.findByRole("row", { name: "1981" });
    await user.click(within(completedRow).getByLabelText("刷新 OA 1981 附件解析"));

    expect(await screen.findByRole("alert")).toHaveTextContent("OCR 推理失败");
    expect(completedRow).toHaveTextContent("1");
  });

  test("aborts an in-flight refresh request when the component unmounts", async () => {
    const user = userEvent.setup();
    const postDeferred = deferredResponse();
    let refreshSignal: AbortSignal | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/workbench/settings/oa/manual-search") {
        return new Response(JSON.stringify({ rows: searchRows, total: 2, page: 0, page_size: 20 }));
      }
      if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments") {
        refreshSignal = init?.signal ?? null;
        return new Promise<Response>((resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          }, { once: true });
          void postDeferred.promise.then(resolve);
        });
      }
      throw new Error(`Unhandled fetch ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    await user.click(await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" }));
    view.unmount();

    expect(refreshSignal?.aborted).toBe(true);
    postDeferred.resolve(new Response(JSON.stringify({
      event_id: "refresh-event-1",
      status: "queued",
      row_ids: ["oa-exp-1981"],
      affected_scope_keys: ["2025-12"],
    }), { status: 202 }));
    await Promise.resolve();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("refresh-event-1"))).toBe(false);
  });

  test("aborts an in-flight refresh status request when the component unmounts", async () => {
    const user = userEvent.setup();
    let statusSignal: AbortSignal | null = null;
    let markStatusStarted!: () => void;
    const statusStarted = new Promise<void>((resolve) => {
      markStatusStarted = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === "/api/workbench/settings/oa/manual-search") {
        return new Response(JSON.stringify({ rows: searchRows, total: 2, page: 0, page_size: 20 }));
      }
      if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments") {
        return new Response(JSON.stringify({
          event_id: "refresh-event-1",
          status: "queued",
          row_ids: ["oa-exp-1981"],
          affected_scope_keys: ["2025-12"],
        }), { status: 202 });
      }
      if (url.pathname.endsWith("/refresh-attachments/refresh-event-1")) {
        statusSignal = init?.signal ?? null;
        markStatusStarted();
        return new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          }, { once: true });
        });
      }
      throw new Error(`Unhandled fetch ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const view = renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    await user.click(await screen.findByRole("button", { name: "刷新 OA 1981 附件解析" }));
    await statusStarted;
    view.unmount();

    expect(statusSignal?.aborted).toBe(true);
  });

  test("keeps staged OA import progress out of the global shell status mark", async () => {
    const user = userEvent.setup();
    const importDeferred = deferredResponse();
    const fetchMock = installFetchMock({ manualImportResponse: importDeferred.promise });
    renderTable({ withSidebar: true });

    await user.click(screen.getByRole("button", { name: "搜索" }));
    const completedRow = await screen.findByRole("row", { name: "1981" });
    await user.click(within(completedRow).getByLabelText("选择 OA 1981"));
    await user.click(screen.getByRole("button", { name: "导入已选OA项" }));

    const refreshButton = within(completedRow).getByLabelText("刷新 OA 1981 附件解析");
    expect(refreshButton).toBeDisabled();
    await user.click(refreshButton);
    expect(fetchMock.mock.calls.filter(([input]) => (
      String(input) === "/api/workbench/settings/oa/manual-search/refresh-attachments"
    ))).toHaveLength(0);

    await waitFor(() => {
      expect(screen.queryByRole("status", { name: "OA导入 10%：准备导入已选 OA" })).not.toBeInTheDocument();
      expect(screen.queryByRole("status", { name: "OA导入 35%：解析 OA 附件发票" })).not.toBeInTheDocument();
    });

    importDeferred.resolve(successfulImportResponse());

    await waitFor(() => {
      expect(screen.queryByRole("status", { name: "OA导入 100%：导入完成" })).not.toBeInTheDocument();
    });
    expect(await screen.findByText("已导入")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(screen.queryByRole("status", { name: "OA导入 100%：导入完成" })).not.toBeInTheDocument();
      },
      { timeout: 2000 },
    );
  });

  test("selects all current-page importable rows only", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderTable();

    await user.click(screen.getByRole("button", { name: "搜索" }));
    await user.click(await screen.findByLabelText("选择当前页可导入OA"));

    expect(screen.getByText("已选 1 个OA")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: "2001" })).getByLabelText("选择 OA 2001")).not.toBeChecked();
  });

  test("does not broaden search when all status filters are cleared", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    await user.click(screen.getByLabelText("搜索已完成"));
    await user.click(screen.getByLabelText("搜索进行中"));
    await user.click(screen.getByRole("button", { name: "搜索" }));

    expect(screen.getByText("至少选择一个表单类型和一个流程状态")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
