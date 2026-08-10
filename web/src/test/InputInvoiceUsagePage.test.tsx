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

const inputFilterOptions = [
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
          workflowStatus: "completed",
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
  summary: {
    invoiceCount: 787,
    totalWithTax: "12345.67",
    matchedOaCount: 1,
    matchedBankTransactionCount: 1,
    pendingCount: 1,
  },
  statistics: {
    invoice_count: 787,
    linked_oa_invoice_count: 620,
    linked_bank_invoice_count: 610,
    paid_invoice_count: 500,
    unlinked_oa_invoice_count: 167,
    unlinked_bank_invoice_count: 177,
    unpaid_invoice_count: 287,
    formal_relation_group_count: 490,
    oa_reverse_batch_count: 12,
  },
  filterConfig: [],
  filterOptions: inputFilterOptions,
};

function installInputInvoiceUsageFetch(
  payload: unknown | ((url: URL) => unknown) = rowsPayload,
  options: {
    exportDownloadResponse?: (url: URL) => Response;
  } = {},
) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/input-invoice-usage/rows") {
      const responsePayload = typeof payload === "function" ? payload(url) : payload;
      return new Response(JSON.stringify(responsePayload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (
      url.pathname === "/api/operations/app-health/page-audit"
      && url.searchParams.get("page") === "input-invoice-usage"
    ) {
      return new Response(JSON.stringify({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: {
          database_snapshot: true,
          snapshot_consistency: "repeatable_read_read_only",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v9",
          registered_read_model_keys: [],
        },
        summary: {
          blocking_issue_sample_count: 0,
          issue_sample_count: 0,
        },
        issues: [],
      }), {
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
        fields: inputFilterOptions,
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

function operationBarrierRequests(fetchMock: ReturnType<typeof installInputInvoiceUsageFetch>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/operation-barrier/status";
  });
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
    const table = cssRule(styles, ".input-invoice-usage-table .finance-table__content");
    const containedScroll = cssRule(styles, ".finance-table--contained .finance-table__scroll");
    const button = cssRule(styles, ".input-invoice-usage-button");
    const tableAction = cssRule(styles, ".input-invoice-usage-table-action,\\n.input-invoice-usage-expandable-cell-text__button");
    const drawerBody = cssRule(styles, ".input-invoice-usage-drawer-body");
    const detailSection = cssRule(styles, ".input-invoice-usage-detail-section,\\n.input-invoice-usage-export-summary,\\n.input-invoice-usage-export-sample");
    const filterTrigger = cssRule(styles, ".input-invoice-usage-filter-menu__trigger");
    const paymentCell = cssRule(styles, ".input-invoice-usage-table-cell--payment");
    const stickyHeader = cssRule(styles, ".finance-table__column");
    const strongSeparator = cssRule(styles, ".input-invoice-usage-table-cell--strong-separator");
    const compositeFilter = cssRule(styles, ".input-invoice-usage-filter-menu__panel--composite");

    expect(tableFrame).not.toContain("border-radius");
    expect(tableFrame).toContain("height: clamp(600px, calc(100dvh - 132px), 1080px)");
    expect(tableFrame).toContain("overflow: hidden");
    expect(tableShell).toContain("height: 100%");
    expect(tableShell).toContain("min-height: 0");
    expect(table).toContain("table-layout: fixed");
    expect(containedScroll).toContain("overflow: auto");
    expect(containedScroll).toContain("overscroll-behavior: contain");
    expect(button).toContain("var(--motion-fast)");
    expect(button).toContain("var(--ease-out-quart)");
    expect(tableAction).toContain("var(--motion-fast)");
    expect(drawerBody).toContain("gap: var(--fp-space-3)");
    expect(detailSection).toContain("border-top: 1px solid var(--fp-border)");
    expect(detailSection).toContain("background: transparent");
    expect(filterTrigger).toContain("var(--motion-fast)");
    expect(paymentCell).toContain("color-mix(in srgb, var(--fp-warning-soft)");
    expect(stickyHeader).toContain("position: sticky");
    expect(stickyHeader).toContain("top: 0");
    expect(strongSeparator).toContain("border-left: 2px solid");
    expect(compositeFilter).toContain("grid-template-columns: repeat(2, minmax(160px, 1fr))");
  });

  test("renders a direct empty result without filter-options polling", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/input-invoice-usage/rows") {
        return new Response(JSON.stringify({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          filterOptions: [],
          statistics: {},
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

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    expect(await within(page).findByText("当前条件下没有进项发票使用记录。")).toBeInTheDocument();
    expect(within(page).queryByText("当前条件下暂无记录。")).not.toBeInTheDocument();
    expect(rowsRequests(fetchMock)).toHaveLength(1);
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/api/input-invoice-usage/filter-options")),
    ).toBe(false);
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });
    expect(rowsRequests(fetchMock)).toHaveLength(1);
    vi.useRealTimers();
  });

  test("keeps page-owned statistics stable when filters change without a title-total request", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch((url) => {
      const filtered = Boolean(url.searchParams.get("keyword"));
      return {
        ...rowsPayload,
        pagination: { ...rowsPayload.pagination, total: filtered ? 71 : 787 },
        summary: { ...rowsPayload.summary, invoiceCount: filtered ? 71 : 787 },
      };
    });

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    const initialRowsRequestCount = rowsRequests(fetchMock).length;
    expect(within(page).getByLabelText("进项发票使用情况数据统计")).toHaveTextContent("进项发票787张");

    await user.type(within(page).getByLabelText("进项发票使用情况搜索"), "已支付");
    await user.click(within(page).getByRole("button", { name: "查询" }));
    await waitFor(() => expect(rowsRequests(fetchMock)).toHaveLength(initialRowsRequestCount + 1));
    expect(rowsRequests(fetchMock).at(-1)?.searchParams.get("keyword")).toBe("已支付");
    expect(rowsRequests(fetchMock).every((url) => url.searchParams.get("page_size") !== "1")).toBe(true);
    expect(within(page).getByLabelText("进项发票使用情况数据统计")).toHaveTextContent("进项发票787张");
  });

  test("admin can run title audit icon and see data relation freshness result", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    renderAuthenticatedAppAt("/input-invoice-usage", { session: { canAdminAccess: true } });

    const page = await screen.findByTestId("input-invoice-usage-page");
    const auditButton = await within(page).findByRole("button", { name: "Audit 进项发票使用情况" });
    await user.click(auditButton);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/operations/app-health/page-audit?page=input-invoice-usage"))).toBe(true);
    });
    const status = await within(page).findByText(/Audit 通过/);
    expect(status).toHaveTextContent("已登记 App 内部合同一致");
    expect(status).toHaveTextContent("已登记配对证明一致");
    expect(status).toHaveTextContent("Fresh");
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
    expect(within(page).getByLabelText("进项发票使用情况数据统计")).toHaveTextContent("进项发票787张");
    expect(within(page).queryByText("以进项发票为主对象反查支付状态、OA 和银行流水。")).not.toBeInTheDocument();
    expect(within(page).queryByText("关键字")).not.toBeInTheDocument();
    expect(await within(page).findByRole("grid", { name: "进项发票使用情况表" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "以发票反提 OA" })).toHaveClass("button--primary");
    const refreshButton = within(page).getByRole("button", { name: "刷新" });
    expect(refreshButton).toBeInTheDocument();
    expect(within(page).getByLabelText("每页行数")).toHaveTextContent("20");

    const rowsBeforeRefresh = rowsRequests(fetchMock).length;
    await user.click(refreshButton);
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeRefresh));

    const headerRow = within(page).getAllByRole("row")[0];
    expect(within(headerRow).getAllByRole("columnheader")).toHaveLength(10);
    expect(within(headerRow).getByRole("button", { name: "按开票日期排序" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 销方名称" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 支付状态" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 OA / OA申请人" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 项目名称" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 对方户名" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 金额" })).toBeInTheDocument();
    const bodyRows = within(page).getAllByRole("row").slice(1);
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("对方户名"))).toBe(false);
    const firstBodyRow = bodyRows[0];
    const firstRowCells = firstBodyRow.querySelectorAll("td");

    expect(await within(page).findByText("SD-INV-2026-0001")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("12345.67")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("11646.86 6% (698.81)")).toBeInTheDocument();
    expect(within(firstRowCells[3] as HTMLElement).getByText("很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮")).toBeInTheDocument();
    expect(within(page).getByText("2026-05-02")).toBeInTheDocument();
    const invoiceDetailButton = within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 详情" });
    expect(invoiceDetailButton).toBeInTheDocument();
    const invoiceCell = firstRowCells[0];
    expect(invoiceCell).toBeTruthy();
    expect(within(invoiceCell as HTMLElement).queryByText("详情")).not.toBeInTheDocument();
    const oaCell = firstRowCells[5] as HTMLElement;
    expect(within(oaCell).getByText("樊祖芳")).toBeInTheDocument();
    expect(within(oaCell).getByLabelText("OA流程状态：已完成")).toBeInTheDocument();
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
    await user.keyboard("{Escape}");

    await user.click(within(page).getByRole("button", { name: "筛选 OA / OA申请人" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /樊祖芳/ }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /支付申请/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "oa_applicant", operator: "in", values: ["樊祖芳"] });
      expect(filters).toContainEqual({ field: "oa_application_type", operator: "in", values: ["支付申请"] });
    });
    await user.keyboard("{Escape}");

    await user.click(within(page).getByRole("button", { name: "筛选 金额" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /交通银行 3847/ }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: /支出/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "bank_account", operator: "in", values: ["交通银行 3847"] });
      expect(filters).toContainEqual({ field: "bank_direction", operator: "in", values: ["outflow"] });
    });
    await user.keyboard("{Escape}");

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

  test("clears persisted keyword search and reloads all input invoice usage rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    const searchInput = within(page).getByLabelText("进项发票使用情况搜索");

    await user.type(searchInput, "南华县沙桥镇润华清真饭店");
    await user.click(within(page).getByRole("button", { name: "查询" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("keyword")).toBe("南华县沙桥镇润华清真饭店");
    });

    await user.click(within(page).getByRole("button", { name: "清除查询" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.has("keyword")).toBe(false);
      expect(request?.searchParams.get("page")).toBe("1");
    });
    expect(searchInput).toHaveValue("");
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
    await within(page).findByRole("grid", { name: "进项发票使用情况表" });
    const firstBodyRow = within(page).getAllByRole("row").slice(1)[0];
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
    expect(relationRequests.map((url) => url.searchParams.get("month"))).toEqual(["2026-05", "2026-05", "2026-05"]);
  });

  test("opens OA reverse workspace with one-step draft creation and submitted history tabs", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await within(page).findByRole("grid", { name: "进项发票使用情况表" });
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

    await user.click(within(confirmDialog).getByRole("button", { name: "关闭确认弹窗" }));
    await user.click(screen.getByRole("tab", { name: "已提交" }));
    expect(await screen.findByText("陈秀云")).toBeInTheDocument();
    expect(screen.getAllByText("SD-INV-2026-0001").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("oa_reverse_batch_page")).not.toBeInTheDocument();
  });

  test("does not wait for input invoice usage barrier after OA reverse draft creation", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    await within(page).findByRole("grid", { name: "进项发票使用情况表" });
    const initialRowsRequests = rowsRequests(fetchMock).length;

    await user.click(within(page).getByRole("button", { name: "以发票反提 OA" }));
    expect(await screen.findByRole("button", { name: "创建 OA 草稿" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "创建 OA 草稿" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/input-invoice-usage/oa-reverse/oa-draft";
    })).toBe(true));
    const confirmDialog = await screen.findByRole("dialog", { name: "OA 草稿提交确认" });
    expect(within(confirmDialog).getByRole("link", { name: "打开 OA 草稿" })).toBeInTheDocument();

    await act(async () => undefined);
    expect(operationBarrierRequests(fetchMock)).toHaveLength(0);
    expect(rowsRequests(fetchMock)).toHaveLength(initialRowsRequests);
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
