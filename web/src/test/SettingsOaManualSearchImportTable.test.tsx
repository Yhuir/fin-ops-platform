import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import OaManualSearchImportTable from "../components/settings/OaManualSearchImportTable";
import AppSidebar from "../components/shell/AppSidebar";
import { AppChromeProvider, useAppChrome } from "../contexts/AppChromeContext";
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

const oaManualBarrierTargets = [
  { read_model_key: "workbench", scope_key: "2025-12" },
  { read_model_key: "workbench_relation", scope_key: "2025-12" },
  { read_model_key: "invoice_lifecycle", scope_key: "2025-12" },
];

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
        <MemoryRouter>
          <SidebarStatusHarness />
        </MemoryRouter>
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
    operation_barrier_targets: oaManualBarrierTargets,
  }));
}

function installFetchMock({ manualImportResponse }: { manualImportResponse?: Promise<Response> } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    if (url.pathname === "/api/workbench/settings/oa/manual-search") {
      return new Response(JSON.stringify({
        rows: searchRows,
        total: 2,
        page: Number(url.searchParams.get("page") ?? 0),
        page_size: Number(url.searchParams.get("page_size") ?? 20),
      }));
    }
    if (url.pathname === "/api/workbench/settings/oa/manual-search/refresh-attachments") {
      expect(init?.method).toBe("POST");
      return new Response(JSON.stringify({
        rows: [
          {
            row_id: "oa-exp-1981",
            attachment_file_count: 2,
            importable_invoice_count: 2,
            unrecognized_attachment_count: 0,
          },
        ],
        errors: [],
        operation_barrier_targets: oaManualBarrierTargets,
      }));
    }
    if (url.pathname === "/api/workbench/settings/oa/manual-imports") {
      expect(init?.method).toBe("POST");
      return manualImportResponse ?? successfulImportResponse();
    }
    if (url.pathname === "/api/operation-barrier/status") {
      expect(init?.method).toBe("POST");
      return new Response(JSON.stringify({
        status: "fresh",
        fresh: true,
        targets: oaManualBarrierTargets.map((target) => ({
          ...target,
          scope_type: target.read_model_key,
          status: "fresh",
          fresh: true,
          blocking: false,
          raw_status: "fresh",
        })),
        blocked_targets: [],
        refreshing_targets: [],
      }));
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
  test("searches OA rows with native table semantics and no DataGrid surface", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderTable();

    expect(screen.getByRole("heading", { name: "OA全量搜索导入" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "OA全量搜索导入结果" })).toBeInTheDocument();
    expect(document.querySelector(".MuiDataGrid-root")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索关键字"), "陈雄兵");
    await user.type(screen.getByLabelText("开始日期"), "2025-12-01");
    await user.type(screen.getByLabelText("结束日期"), "2025-12-31");
    await user.click(screen.getByRole("button", { name: "搜索" }));

    const completedRow = await screen.findByRole("row", { name: /1981.*陈雄兵/ });
    expect(completedRow).toBeInTheDocument();
    expect(within(completedRow).getByText("1981")).toBeInTheDocument();
    expect(screen.getByRole("row", { name: /2001.*吴云江/ })).toBeInTheDocument();
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

    const completedRow = await screen.findByRole("row", { name: /1981.*陈雄兵/ });
    const inProgressRow = screen.getByRole("row", { name: /2001.*吴云江/ });
    expect(within(inProgressRow).getByLabelText("选择 OA oa-pay-2001")).toBeDisabled();
    expect(inProgressRow).toHaveTextContent("流程未完成");

    await user.click(within(completedRow).getByLabelText("选择 OA oa-exp-1981"));
    expect(screen.getByText("已选 1 个OA")).toBeInTheDocument();
    expect(screen.getByText("金额合计 ¥135.00")).toBeInTheDocument();
    expect(screen.getByText("预计发票 1 张")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "展开 OA oa-exp-1981 明细" }));
    expect(await screen.findByText("餐费")).toBeInTheDocument();
    expect(screen.getByText("明细可识别发票")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "刷新 OA oa-exp-1981 附件解析" }));
    expect(await screen.findByText("预计发票 2 张")).toBeInTheDocument();
    expect(completedRow).toHaveTextContent("2");
    expect(completedRow).toHaveTextContent("0");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/operation-barrier/status",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ targets: oaManualBarrierTargets }),
      }),
    );

    await user.click(screen.getByRole("button", { name: "导入已选OA项" }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workbench/settings/oa/manual-imports",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ row_ids: ["oa-exp-1981"], actor_id: "settings_manual_import" }),
      }),
    );
    expect(await screen.findByText("已导入")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input) === "/api/operation-barrier/status")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "清空选择" }));
    expect(screen.getByText("已选 0 个OA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "导入已选OA项" })).toBeDisabled();
  });

  test("keeps staged OA import progress out of the global shell status mark", async () => {
    const user = userEvent.setup();
    const importDeferred = deferredResponse();
    installFetchMock({ manualImportResponse: importDeferred.promise });
    renderTable({ withSidebar: true });

    await user.click(screen.getByRole("button", { name: "搜索" }));
    const completedRow = await screen.findByRole("row", { name: /1981.*陈雄兵/ });
    await user.click(within(completedRow).getByLabelText("选择 OA oa-exp-1981"));
    await user.click(screen.getByRole("button", { name: "导入已选OA项" }));

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
    expect(within(screen.getByRole("row", { name: /2001.*吴云江/ })).getByLabelText("选择 OA oa-pay-2001")).not.toBeChecked();
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
