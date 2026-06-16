import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import {
  buildPageSessionStorageKey,
  createStoredPayload,
} from "../contexts/pageSessionStorage";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const inputInvoiceUsageSourceFiles = [
  "src/pages/InputInvoiceUsagePage.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx",
  "src/components/inputInvoiceUsage/ExpandableCellText.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx",
  "src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx",
  "src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx",
  "src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx",
] as const;

function readWebSource(path: string) {
  return readFileSync(resolve(path), "utf8");
}

function cssRule(source: string, selector: string) {
  const normalizedSelector = selector.replace(/\\n/g, "\n");
  const escapedSelector = normalizedSelector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

const rowsPayload = {
  rows: [
    {
      id: "usage-row-001",
      invoice: {
        id: "invoice-001",
        displayNo: "SD-INV-2026-0001",
        invoiceNo: "0001",
        invoiceCode: "5300",
        digitalInvoiceNo: "SD-INV-2026-0001",
        issueDate: "2026-05-02",
        sellerName: "云南长文本供应商科技发展有限公司第一分公司",
        sellerTaxNo: "91530100MA6KTEST01",
        totalWithTax: "12345.67",
        amountWithoutTax: "11646.86",
        taxRate: "6%",
        taxAmount: "698.81",
        specificBusinessType: "企业管理咨询",
        taxableItemName: "很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮",
      },
      paymentStatus: {
        code: "pending",
        label: "待处理",
        reason: "规则不能自动闭环，需要财务复核后处理",
      },
      oa: {
        primary: {
          id: "oa-001",
          applicant: "樊祖芳",
          applicationType: "支付申请",
          projectName: "云南省内项目名称很长很长需要换行显示并可展开",
          detailAvailable: true,
        },
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [],
      },
      bank: {
        primary: {
          id: "bank-001",
          counterpartyName: "云南银行交易对方户名很长很长需要换行显示",
          tradeTime: "2026-05-03 10:30:00",
          amount: "12345.67",
          directionLabel: "outflow",
          bankName: "交通银行",
          accountLast4: "3847",
          summary: "项目付款摘要内容很长很长用于验证折叠展示",
          remark: "备注内容很长很长用于验证摘要备注列的展开控制",
          detailAvailable: true,
        },
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [],
      },
    },
  ],
  pagination: {
    page: 1,
    pageSize: 20,
    total: 51,
  },
  filterConfig: [],
};

function installInputInvoiceUsageFetch(
  payload: unknown = rowsPayload,
  options: { exportDownloadResponse?: (url: URL) => Response } = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/input-invoice-usage/rows") {
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname.startsWith("/api/input-invoice-usage/rows/") && url.pathname.endsWith("/relation-details")) {
      const kind = url.searchParams.get("kind") ?? "oa";
      const title = kind === "bank" ? "银行流水关联明细" : kind === "invoice" ? "发票关联明细" : "OA关联明细";
      const sectionTitle = kind === "bank" ? "银行流水 1" : kind === "invoice" ? "发票 1" : "OA 1";
      const fieldLabel = kind === "bank" ? "对方户名" : kind === "invoice" ? "发票号码" : "申请人";
      const fieldValue = kind === "bank" ? "云南银行交易对方户名很长很长需要换行显示" : kind === "invoice" ? "SD-INV-2026-0001" : "刘际涛";
      return new Response(JSON.stringify({
        rowId: decodeURIComponent(url.pathname.split("/").at(-2) ?? ""),
        invoiceId: "invoice-001",
        kind,
        title,
        relationCount: 2,
        hasMultiple: true,
        sections: [
          {
            title: sectionTitle,
            fields: [
              { label: fieldLabel, value: fieldValue },
              { label: "金额", value: "100.00" },
            ],
          },
        ],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/invoices/invoice-001/detail") {
      return new Response(JSON.stringify({
        id: "invoice-001",
        invoiceNo: "0001",
        digitalInvoiceNo: "SD-INV-2026-0001",
        invoiceDate: "2026-05-02",
        sellerName: "云南长文本供应商科技发展有限公司第一分公司",
        totalWithTax: "12345.67",
        amount: "11646.86",
        taxRate: "6%",
        taxAmount: "698.81",
        taxableItemName: "很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/filter-options") {
      return new Response(JSON.stringify({
        fields: [
          {
            field: "seller_name",
            label: "销方名称",
            mode: "enum_multi",
            sortable: true,
            operators: ["in", "contains"],
            options: [{ value: "云南长文本供应商科技发展有限公司第一分公司", label: "云南长文本供应商科技发展有限公司第一分公司", count: 1 }],
          },
          {
            field: "payment_status",
            label: "支付状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "pending", label: "待处理", count: 1 }],
          },
          {
            field: "oa_applicant",
            label: "OA申请人",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "樊祖芳", label: "樊祖芳", count: 1 }],
          },
          {
            field: "oa_application_type",
            label: "类型",
            mode: "enum_multi",
            sortable: true,
            operators: ["in", "equals"],
            options: [{ value: "支付申请", label: "支付申请", count: 1 }],
          },
          {
            field: "oa_project_name",
            label: "项目名称",
            mode: "enum_multi",
            sortable: true,
            operators: ["in", "contains"],
            options: [{ value: "云南省内项目名称很长很长需要换行显示并可展开", label: "云南省内项目名称很长很长需要换行显示并可展开", count: 1 }],
          },
          {
            field: "bank_counterparty_name",
            label: "对方户名",
            mode: "enum_multi",
            sortable: true,
            operators: ["in", "contains"],
            options: [{ value: "云南银行交易对方户名很长很长需要换行显示", label: "云南银行交易对方户名很长很长需要换行显示", count: 1 }],
          },
          {
            field: "bank_account",
            label: "银行账户",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "交通银行 3847", label: "交通银行 3847", count: 1 }],
          },
          {
            field: "bank_direction",
            label: "收支",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "outflow", label: "支出", count: 1 }],
          },
        ],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/export-preview") {
      return new Response(JSON.stringify({
        file_name: "进项发票使用情况-2026-05-31.xlsx",
        row_count: 1,
        scope_label: "当前筛选",
        columns: ["序号", "发票号码", "销方名称"],
        sample_rows: [{ "序号": 1, "发票号码": "SD-INV-2026-0001", "销方名称": "云南长文本供应商科技发展有限公司第一分公司" }],
        readModelStatus: "fresh",
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/export") {
      if (options.exportDownloadResponse) {
        return options.exportDownloadResponse(url);
      }
      return new Response(new Blob(["xlsx"], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), {
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": "attachment; filename*=UTF-8''%E8%BF%9B%E9%A1%B9.xlsx",
        },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/oa-reverse/preview") {
      return new Response(JSON.stringify({
        previewId: "oa_reverse_preview_page",
        previewHash: "preview-page-hash",
        targetApplicantCode: "chen_xiuyun",
        targetApplicantName: "陈秀云",
        targetApplicants: [{ code: "chen_xiuyun", name: "陈秀云" }],
        invoiceCount: 1,
        totalWithTax: "88.00",
        invoiceRows: [{
          invoiceId: "invoice-001",
          invoiceNo: "SD-INV-2026-0001",
          displayNo: "SD-INV-2026-0001",
          sellerName: "云南长文本供应商科技发展有限公司第一分公司",
          invoiceDate: "2026-05-02",
          totalWithTax: "88.00",
          paymentStatus: { label: "待处理" },
        }],
        groups: [{
          targetApplicantCode: "chen_xiuyun",
          targetApplicantName: "陈秀云",
          invoiceCount: 1,
          totalWithTax: "88.00",
          candidateInvoiceIds: ["invoice-001"],
          invoiceRows: [{
            invoiceId: "invoice-001",
            invoiceNo: "SD-INV-2026-0001",
            displayNo: "SD-INV-2026-0001",
            sellerName: "云南长文本供应商科技发展有限公司第一分公司",
            invoiceDate: "2026-05-02",
            totalWithTax: "88.00",
            paymentStatus: { label: "待处理" },
          }],
        }],
        canCreateDraft: true,
        nextAction: "create_oa_draft",
        permissions: { canCreateDraft: true },
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/oa-reverse/oa-draft") {
      return new Response(JSON.stringify({
        batchId: "oa_reverse_batch_page",
        version: 2,
        status: "oa_draft_created",
        invoiceIds: ["invoice-001"],
        selectedInvoiceIds: ["invoice-001"],
        totalWithTax: "88.00",
        targetApplicantCode: "chen_xiuyun",
        targetApplicantName: "陈秀云",
        invoiceRows: [],
        oaDraftUrl: "https://oa.example.test/draft/page",
        canConfirmSubmission: true,
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.pathname === "/api/input-invoice-usage/oa-reverse/submitted-history") {
      return new Response(JSON.stringify({
        items: [{
          targetApplicantName: "陈秀云",
          submittedAt: "2026-06-10T10:30:00+08:00",
          totalWithTax: "88.00",
          invoiceCount: 1,
          invoices: [{
            invoiceNo: "SD-INV-2026-0001",
            invoiceDate: "2026-05-02",
            sellerName: "云南长文本供应商科技发展有限公司第一分公司",
            totalWithTax: "88.00",
          }],
        }],
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function rowsRequests(fetchMock: ReturnType<typeof installInputInvoiceUsageFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/input-invoice-usage/rows");
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.sessionStorage.clear();
});

describe("Input invoice usage page", () => {
  test("targets project primitives for page shell, dense table, and workflow drawers", () => {
    const forbiddenMuiImports = inputInvoiceUsageSourceFiles.flatMap((path) => {
      const source = readWebSource(path);
      const hasMuiImport = /from ["']@mui\/|import\s+[^;]*@mui\//.test(source);
      return hasMuiImport ? [path] : [];
    });
    const forbiddenMuiSelectors = inputInvoiceUsageSourceFiles.flatMap((path) => {
      const source = readWebSource(path);
      const hasMuiSelector = /\.Mui[A-Z][A-Za-z-]*/.test(source);
      return hasMuiSelector ? [path] : [];
    });
    const sourceByPath = Object.fromEntries(inputInvoiceUsageSourceFiles.map((path) => [path, readWebSource(path)]));
    const missingPrimitiveTargets = [
      sourceByPath["src/pages/InputInvoiceUsagePage.tsx"].includes("PageScaffold") ? null : "InputInvoiceUsagePage.tsx should keep PageScaffold or equivalent project shell",
      sourceByPath["src/pages/InputInvoiceUsagePage.tsx"].includes("PageToolbar") ? null : "InputInvoiceUsagePage.tsx should use PageToolbar or equivalent project toolbar",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx"].includes("FinanceTable")
        || sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx"].includes("input-invoice-usage-table-shell")
        ? null
        : "InputInvoiceUsageTable.tsx should use FinanceTable or the project dense table shell",
      sourceByPath["src/components/inputInvoiceUsage/ExpandableCellText.tsx"].includes("lucide-react")
        || sourceByPath["src/components/inputInvoiceUsage/ExpandableCellText.tsx"].includes("expandable-cell-text")
        ? null
        : "ExpandableCellText.tsx should use project/lucide controls instead of MUI icons",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemcheckbox\"")
        && sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemradio\"")
        ? null
        : "InputInvoiceUsageFilterMenu.tsx should preserve checkbox/radio menu semantics",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageDetailDrawer.tsx should use AppDrawer for the right drawer shape",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageExportDrawer.tsx should use AppDrawer for the right drawer shape",
      sourceByPath["src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx"].includes("AppDrawer") ? null : "PaymentStatusRulesDrawer.tsx should use AppDrawer for the right drawer shape",
      sourceByPath["src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx"].includes("AppDrawer") ? null : "OaReverseWorkspaceDrawer.tsx should use AppDrawer for the right drawer shape",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      missingPrimitiveTargets: [],
    });
  });

  test("keeps premium compact table, drawer, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const tableFrame = cssRule(styles, ".input-invoice-usage-table-frame");
    const tableShell = cssRule(styles, ".input-invoice-usage-table-shell");
    const button = cssRule(styles, ".input-invoice-usage-button");
    const tableAction = cssRule(styles, ".input-invoice-usage-table-action,\\n.input-invoice-usage-expandable-cell-text__button");
    const drawerBody = cssRule(styles, ".input-invoice-usage-drawer-body");
    const detailSection = cssRule(styles, ".input-invoice-usage-detail-section,\\n.input-invoice-usage-export-summary,\\n.input-invoice-usage-export-sample");
    const filterTrigger = cssRule(styles, ".input-invoice-usage-filter-menu__trigger");
    const groupInvoice = cssRule(styles, ".input-invoice-usage-table-group-header--invoice");
    const groupPayment = cssRule(styles, ".input-invoice-usage-table-group-header--payment,\\n.input-invoice-usage-table-cell--payment");
    const groupOa = cssRule(styles, ".input-invoice-usage-table-group-header--oa");
    const groupBank = cssRule(styles, ".input-invoice-usage-table-group-header--bank");
    const stickyGroupHeader = cssRule(styles, ".input-invoice-usage-table thead tr:first-child th");
    const stickySubHeader = cssRule(styles, ".input-invoice-usage-table thead tr:nth-child(2) th");
    const strongSeparator = cssRule(styles, ".input-invoice-usage-table-cell--strong-separator");
    const compositeFilter = cssRule(styles, ".input-invoice-usage-filter-menu__panel--composite");

    expect(tableFrame).toContain("border-radius: var(--fp-radius-sm)");
    expect(tableShell).toContain("max-height: calc(100vh - 150px)");
    expect(tableShell).toContain("min-height: 360px");
    expect(button).toContain("var(--motion-fast)");
    expect(button).toContain("var(--ease-out-quart)");
    expect(tableAction).toContain("var(--motion-fast)");
    expect(drawerBody).toContain("gap: var(--fp-space-3)");
    expect(detailSection).toContain("border-radius: var(--fp-radius-sm)");
    expect(detailSection).toContain("padding: var(--fp-space-3)");
    expect(filterTrigger).toContain("var(--motion-fast)");
    expect(groupInvoice).toContain("color-mix(in srgb, var(--fp-success-soft)");
    expect(groupPayment).toContain("color-mix(in srgb, var(--fp-warning-soft)");
    expect(groupOa).toContain("color-mix(in srgb, var(--fp-info-soft)");
    expect(groupBank).toContain("color-mix(in srgb, var(--fp-primary-soft)");
    expect(stickyGroupHeader).toContain("position: sticky");
    expect(stickyGroupHeader).toContain("top: 0");
    expect(stickySubHeader).toContain("position: sticky");
    expect(stickySubHeader).toContain("top: 38px");
    expect(strongSeparator).toContain("border-left: 2px solid");
    expect(compositeFilter).toContain("grid-template-columns: repeat(2, minmax(160px, 1fr))");
  });

  test("uses a standard empty state while read model refresh details stay hidden", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/input-invoice-usage/rows") {
        return new Response(JSON.stringify({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
        }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/api/input-invoice-usage/filter-options") {
        return new Response(JSON.stringify({ fields: [], read_model_status: "refreshing" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    expect(await within(page).findByText("当前条件下暂无记录。")).toBeInTheDocument();
    expect(within(page).queryByText("进项发票使用情况读模型正在刷新，完成后页面会自动重新加载。")).not.toBeInTheDocument();
  });

  test("unmounts the page while away and retries after route remount", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/input-invoice-usage/rows") {
        return new Response(JSON.stringify({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
        }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.pathname === "/api/input-invoice-usage/filter-options") {
        return new Response(JSON.stringify({ fields: [], read_model_status: "refreshing" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/input-invoice-usage");
    const page = await screen.findByTestId("input-invoice-usage-page");
    expect(await within(page).findByText("当前条件下暂无记录。")).toBeInTheDocument();
    expect(rowsRequests(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByTestId("input-invoice-usage-page")).not.toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(rowsRequests(fetchMock)).toHaveLength(1);

    vi.useRealTimers();
    fireEvent.click(screen.getByRole("link", { name: "进项发票使用情况" }));
    expect(await screen.findByTestId("input-invoice-usage-page")).toBeInTheDocument();

    expect(rowsRequests(fetchMock).length).toBeGreaterThan(1);
  });

  test("adds sidebar route and renders the project dense table contract", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "进项发票使用情况", to: "/input-invoice-usage" }),
      ]),
    );

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    const initialRowsRequest = rowsRequests(fetchMock)[0];
    expect(initialRowsRequest.searchParams.get("page")).toBe("1");
    expect(initialRowsRequest.searchParams.get("page_size")).toBe("20");
    expect(within(page).getByRole("heading", { name: "进项发票使用情况" })).toBeInTheDocument();
    expect(within(page).queryByText("以进项发票为主对象反查支付状态、OA 和银行流水。")).not.toBeInTheDocument();
    expect(within(page).queryByText("关键字")).not.toBeInTheDocument();
    expect(within(page).queryByRole("grid")).not.toBeInTheDocument();
    expect(await within(page).findByRole("table", { name: "进项发票使用情况表" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "以发票反提 OA" })).toHaveClass("input-invoice-usage-button--accent");
    expect(within(page).queryByRole("button", { name: "刷新" })).not.toBeInTheDocument();
    expect(Array.from((within(page).getByLabelText("每页行数") as HTMLSelectElement).options).map((option) => option.value)).toEqual(["20", "50", "100"]);

    const headerRows = within(page).getAllByRole("row").slice(0, 2);
    for (const label of ["进项发票", "支付状态", "OA", "流水"]) {
      expect(within(headerRows[0]).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of [
      "发票号码",
      "销方名称",
      "价税合计",
      "不含税/税率税额",
      "货物或应税劳务名称",
      "支付状态",
      "OA申请人",
      "项目名称",
      "对方户名",
      "金额",
      "摘要/备注",
    ]) {
      expect(within(headerRows[1]).getAllByText(label)).toHaveLength(1);
    }
    expect(within(headerRows[1]).getByRole("button", { name: "按开票日期排序" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 销方名称" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 支付状态" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 OA申请人" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 项目名称" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 对方户名" })).toBeInTheDocument();
    expect(within(headerRows[1]).getByRole("button", { name: "筛选 金额" })).toBeInTheDocument();
    const bodyRows = within(page).getAllByRole("row").slice(2);
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("对方户名"))).toBe(false);
    const firstBodyRow = bodyRows[0];
    const firstRowCells = firstBodyRow.querySelectorAll("td");

    expect(await within(page).findByText("SD-INV-2026-0001")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("12,345.67")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("11,646.86 6% (698.81)")).toBeInTheDocument();
    expect(within(firstRowCells[3] as HTMLElement).getByText("很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮")).toBeInTheDocument();
    expect(within(page).getByText("2026-05-02")).toBeInTheDocument();
    const invoiceDetailButton = within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 详情" });
    expect(invoiceDetailButton).toBeInTheDocument();
    const invoiceCell = firstRowCells[0];
    expect(invoiceCell).toBeTruthy();
    expect(within(invoiceCell as HTMLElement).queryByText("详情")).not.toBeInTheDocument();
    const oaCell = firstRowCells[5] as HTMLElement;
    expect(within(oaCell).getByText("樊祖芳")).toBeInTheDocument();
    expect(within(oaCell).getByRole("button", { name: "查看OA 樊祖芳 详情" })).toBeInTheDocument();
    expect(within(oaCell).queryByText("详情")).not.toBeInTheDocument();
    expect(within(page).queryByText("规则不能自动闭环，需要财务复核后处理")).not.toBeInTheDocument();
    expect(within(page).getByText("2026-05-03 10:30:00")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看流水 云南银行交易对方户名很长很长需要换行显示 详情" })).toBeInTheDocument();
    expect(within(page).queryByText(/outflow/)).not.toBeInTheDocument();
    expect(within(page).getByText("支出")).toBeInTheDocument();
    expect(within(page).getByText("交通银行 3847")).toBeInTheDocument();
    expect(within(page).getByText("待处理").closest(".input-invoice-usage-payment-cell")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "按开票日期排序" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("sort_field")).toBe("invoice_date");
      expect(request?.searchParams.get("sort_direction")).toBe("asc");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 销方名称" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /云南长文本供应商科技发展有限公司第一分公司/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "seller_name", operator: "in", values: ["云南长文本供应商科技发展有限公司第一分公司"] });
    });

    await user.click(within(page).getByRole("button", { name: "筛选 OA申请人" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /樊祖芳/ }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /支付申请/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "oa_applicant", operator: "in", values: ["樊祖芳"] });
      expect(filters).toContainEqual({ field: "oa_application_type", operator: "in", values: ["支付申请"] });
    });

    await user.click(within(page).getByRole("button", { name: "筛选 金额" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /交通银行 3847/ }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /支出/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "bank_account", operator: "in", values: ["交通银行 3847"] });
      expect(filters).toContainEqual({ field: "bank_direction", operator: "in", values: ["outflow"] });
    });

    await user.click(within(page).getByRole("button", { name: /展开.*货物或应税劳务名称/ }));
    expect(within(page).getByRole("button", { name: /收起.*货物或应税劳务名称/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("page")).toBe("2");
    });

    await user.click(within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 详情" }));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "发票详情" })).toBeInTheDocument();
    });
  });

  test("shows relation totals with +N entry points for multi OA, bank, and invoice relations", async () => {
    const user = userEvent.setup();
    const multiRowsPayload = {
      ...rowsPayload,
      rows: [
        {
          ...rowsPayload.rows[0],
          id: "usage-row-multi",
          invoice: {
            ...rowsPayload.rows[0].invoice,
            totalWithTax: "100.00",
            amountWithoutTax: "94.34",
            taxAmount: "5.66",
          },
          oa: {
            primary: {
              id: "oa-multi-a",
              applicant: "刘际涛",
              applicationType: "支付申请",
              projectName: "昭通卷烟厂2025年度信息化不可预见维护采购项目",
              amount: "100.00",
              detailAvailable: true,
            },
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              {
                id: "oa-multi-a",
                applicant: "刘际涛",
                applicationType: "支付申请",
                projectName: "昭通卷烟厂2025年度信息化不可预见维护采购项目",
                amount: "40.00",
                detailAvailable: true,
              },
              {
                id: "oa-multi-b",
                applicant: "张三",
                applicationType: "支付申请",
                projectName: "红塔集团2025年度信息化维护采购项目",
                amount: "60.00",
                detailAvailable: true,
              },
            ],
          },
          bank: {
            primary: {
              ...rowsPayload.rows[0].bank.primary,
              id: "bank-multi-a",
              amount: "100.00",
            },
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              {
                ...rowsPayload.rows[0].bank.primary,
                id: "bank-multi-a",
                amount: "40.00",
              },
              {
                ...rowsPayload.rows[0].bank.primary,
                id: "bank-multi-b",
                amount: "60.00",
              },
            ],
          },
          invoiceRelations: {
            primary: {
              id: "invoice-001",
              displayNo: "SD-INV-2026-0001",
              invoiceNo: "0001",
              invoiceCode: "5300",
              digitalInvoiceNo: "SD-INV-2026-0001",
              invoiceDate: "2026-05-02",
              sellerName: "云南长文本供应商科技发展有限公司第一分公司",
              sellerTaxNo: "91530100MA6KTEST01",
              totalWithTax: "40.00",
              taxableItemName: "维护服务",
            },
            totalWithTax: "100.00",
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              {
                id: "invoice-001",
                displayNo: "SD-INV-2026-0001",
                invoiceNo: "0001",
                invoiceCode: "5300",
                digitalInvoiceNo: "SD-INV-2026-0001",
                invoiceDate: "2026-05-02",
                sellerName: "云南长文本供应商科技发展有限公司第一分公司",
                sellerTaxNo: "91530100MA6KTEST01",
                totalWithTax: "40.00",
                taxableItemName: "维护服务",
              },
              {
                id: "invoice-002",
                displayNo: "SD-INV-2026-0002",
                invoiceNo: "0002",
                invoiceCode: "5300",
                digitalInvoiceNo: "SD-INV-2026-0002",
                invoiceDate: "2026-05-03",
                sellerName: "云南长文本供应商科技发展有限公司第一分公司",
                sellerTaxNo: "91530100MA6KTEST01",
                totalWithTax: "60.00",
                taxableItemName: "维护服务",
              },
            ],
          },
        },
      ],
      pagination: {
        ...rowsPayload.pagination,
        total: 1,
      },
    };
    const fetchMock = installInputInvoiceUsageFetch(multiRowsPayload);

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await within(page).findByRole("table", { name: "进项发票使用情况表" });
    const firstBodyRow = within(page).getAllByRole("row").slice(2)[0];
    const firstRowCells = firstBodyRow.querySelectorAll("td");
    expect(within(firstRowCells[2] as HTMLElement).getByText("100.00")).toBeInTheDocument();
    expect(within(firstRowCells[5] as HTMLElement).getByText("合计 100.00")).toBeInTheDocument();
    expect(within(firstRowCells[8] as HTMLElement).getByText("100.00")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "查看OA 刘际涛 详情" })).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "查看刘际涛关联OA 2 条" }));
    const oaDrawer = await screen.findByRole("dialog", { name: "OA关联明细" });
    expect(within(oaDrawer).getByText("刘际涛")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看云南银行交易对方户名很长很长需要换行显示关联流水 2 条" }));
    const bankDrawer = await screen.findByRole("dialog", { name: "银行流水关联明细" });
    expect(within(bankDrawer).getByText("银行流水 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 关联发票 2 张" }));
    const invoiceDrawer = await screen.findByRole("dialog", { name: "发票关联明细" });
    expect(within(invoiceDrawer).getByText("发票 1")).toBeInTheDocument();

    const relationRequests = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
      .filter((url) => url.pathname === "/api/input-invoice-usage/rows/usage-row-multi/relation-details");
    expect(relationRequests.map((url) => url.searchParams.get("kind"))).toEqual(["oa", "bank", "invoice"]);
  });

  test("opens OA reverse workspace with one-step draft creation and submitted history tabs", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await within(page).findByRole("table", { name: "进项发票使用情况表" });
    await user.click(within(page).getByRole("button", { name: "以发票反提 OA" }));

    expect(await screen.findByRole("tab", { name: "待处理" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "已提交" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "创建 OA 草稿" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "创建本地批次" })).not.toBeInTheDocument();
    expect(screen.queryByText("尚未创建本地批次。")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/input-invoice-usage/oa-reverse/oa-draft";
    })).toBe(true));
    const confirmDialog = await screen.findByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute("href", "https://oa.example.test/draft/page");

    await user.click(screen.getByRole("tab", { name: "已提交" }));
    expect(await screen.findByText("陈秀云")).toBeInTheDocument();
    expect(screen.getAllByText("SD-INV-2026-0001").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("oa_reverse_batch_page")).not.toBeInTheDocument();
  });

  test("restores column filters and sort from table session state", async () => {
    const fetchMock = installInputInvoiceUsageFetch();
    const storageKey = buildPageSessionStorageKey({
      userScope: "101",
      pageKey: "input-invoice-usage",
      stateKey: "query",
    });
    window.sessionStorage.setItem(storageKey, JSON.stringify(createStoredPayload({
      version: 1,
      ttlMs: 24 * 60 * 60 * 1000,
      now: Date.now(),
      value: {
        page: 1,
        pageSize: 20,
        keyword: "",
        invoiceDateFrom: "",
        invoiceDateTo: "",
        month: "",
        filters: [{ field: "payment_status", operator: "in", values: ["pending"] }],
        sortField: "invoice_no",
        sortDirection: "asc",
        activeWorkflow: null,
        detailTarget: null,
      },
    })));

    renderAuthenticatedAppAt("/input-invoice-usage");

    await screen.findByTestId("input-invoice-usage-page");
    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(0);
    });
    const request = rowsRequests(fetchMock)[0];
    expect(JSON.parse(decodeURIComponent(request.searchParams.get("filters") ?? "[]"))).toEqual([
      { field: "payment_status", operator: "in", values: ["pending"] },
    ]);
    expect(request.searchParams.get("sort_field")).toBe("invoice_no");
    expect(request.searchParams.get("sort_direction")).toBe("asc");
  });

  test("loads export preview and downloads the current filtered result set", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:input-invoice-usage-export"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));

    expect(await screen.findByText("预计导出 1 行")).toBeInTheDocument();
    expect(screen.getAllByText("SD-INV-2026-0001").length).toBeGreaterThanOrEqual(1);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/input-invoice-usage/export-preview";
    })).toBe(true);

    await user.click(screen.getByRole("button", { name: "下载导出" }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/input-invoice-usage/export";
      })).toBe(true);
    });
    expect(URL.createObjectURL).toHaveBeenCalled();
  });

  test("shows backend export row-limit messages inside the export drawer", async () => {
    const user = userEvent.setup();
    installInputInvoiceUsageFetch(rowsPayload, {
      exportDownloadResponse: () => new Response(JSON.stringify({
        error: "input_invoice_usage_export_row_limit_exceeded",
        message: "进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。",
        details: { total: 20001, limit: 20000 },
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      }),
    });

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await user.click(within(page).getByRole("button", { name: "筛选内容导出" }));

    expect(await screen.findByText("预计导出 1 行")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下载导出" }));

    expect(await screen.findByText("进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。")).toBeInTheDocument();
    expect(screen.queryByText("已生成 进项.xlsx")).not.toBeInTheDocument();
  });
});
