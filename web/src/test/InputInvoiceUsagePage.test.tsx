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
    options: [{ value: "unclassified", label: "待处理", count: 1 }],
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
  classification: {
    all: { id: "all", label: "全部发票", count: 1 }, used: { id: "used", label: "已使用", count: 1 }, unused: { id: "unused", label: "待使用", count: 0 },
    groups: [{ id: "paid", label: "已付款", tone: "paid", count: 0, children: [{ id: "category:paid", label: "发票＝付款", count: 0 }] },
      { id: "unpaid", label: "未付款", tone: "unpaid", count: 0, children: [] }],
  },
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
        code: "unclassified",
        label: "待处理",
        reason: "拆分流水的付款用途尚未明确",
      },
      oa: {
        primaryOaId: "oa-001",
        applicantName: "樊祖芳",
        applicationType: "支付申请",
        projectName: "云南省内项目名称很长很长需要换行显示并可展开",
        amount: "12345.67",
        detailAvailable: true,
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [{
          oaId: "oa-001",
          applicantName: "樊祖芳",
          applicationType: "支付申请",
          workflowStatus: "completed",
          projectName: "云南省内项目名称很长很长需要换行显示并可展开",
          amount: "12345.67",
          detailAvailable: true,
        }],
      },
      bank: {
        primary: {
          id: "bank-001",
          counterpartyName: "云南银行交易对方户名很长很长需要换行显示",
          tradeTime: "2026-05-03 10:30:00",
          amount: "12345.67",
          directionLabel: "outflow",
          bankName: "交通银行",
          bankShortName: "交行",
          accountLast4: "3847",
          summary: "项目付款摘要内容很长很长用于验证折叠展示",
          remark: "备注内容很长很长用于验证摘要备注列的展开控制",
          detailAvailable: true,
          original_amount: "12345.67",
          netAmount: "12345.67",
          netDirectionLabel: "净支出",
          original_transaction_count: 1,
        },
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [],
        original_amount: "12345.67",
        netAmount: "12345.67",
        netDirectionLabel: "净支出",
        original_transaction_count: 1,
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
    unclassifiedCount: 1,
  },
  statistics: {
    invoice_count: 787,
    completed_oa_count: 415,
    in_progress_oa_count: 18,
    expense_transaction_count: 1043,
    income_transaction_count: 159,
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
    if (url.pathname === "/api/input-invoice-usage/export-summary") {
      return new Response(JSON.stringify({
        file_name: "进项发票使用情况-2026-05-31.xlsx",
        row_count: 1,
        filter_options: { relation_status: [{value: "no_oa",label:"未关联 OA",count:1}], payment_status: [{value:"unclassified",label:"待核对",count:1}] },
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
  test.each([false, true])("流水金额区不显示用途标签，显示业务净额和账户：拆分=%s", async (split) => {
    const parts = split ? [
      { id: "principal", category_code: "repayment", category_label: "归还借款", category_path: ["外部往来款付款", "归还借款", "银行往来"], amount: "1000000.00" },
      { id: "interest", category_code: "interest", category_label: "利息", category_path: ["费用", "利息"], amount: "1497.22" },
    ] : [];
    installInputInvoiceUsageFetch({ ...rowsPayload, rows: rowsPayload.rows.map((row) => ({
      ...row,
      bank: {
        ...row.bank,
        original_amount: "1001497.22",
        netAmount: "1001497.22",
        netDirectionLabel: "净支出",
        bank_split_parts: parts,
        primary: { ...row.bank.primary, amount: "1497.22", bank_split_parts: parts },
      },
    })) });
    renderAuthenticatedAppAt("/input-invoice-usage");
    const table = await screen.findByRole("table", { name: "进项发票使用情况表" });
    const invoiceRow = within(table).getByRole("row", { name: /SD-INV-2026-0001/ });
    const amountCell = invoiceRow.querySelectorAll("th, td")[8] as HTMLElement;
    expect(within(amountCell).getByText("1001497.22")).toBeVisible();
    expect(within(amountCell).getByText("净支出")).toBeVisible();
    expect(amountCell).toHaveTextContent("交行");
    expect(amountCell).toHaveTextContent("3847");
    expect(within(amountCell).queryByText("1497.22")).not.toBeInTheDocument();
    expect(within(amountCell).queryByText(/归还借款|费用|利息/)).not.toBeInTheDocument();
    expect(within(amountCell).queryByRole("button", { name: /拆分金额/ })).not.toBeInTheDocument();
  });

  test.each([
    [{ bankShortName: "平安", bankName: "平安银行", accountLast4: "0093", bankAccount: "平安银行 0093" }, "平安0093"],
    [{ bankShortName: "", bankName: "平安银行", accountLast4: "0093", bankAccount: "平安银行 0093" }, "平安银行0093"],
    [{ bankShortName: "", bankName: "", accountLast4: "", bankAccount: "" }, "—"],
  ])("账户展示使用真实简称、保留前导零且不猜缺失信息：%j", async (account, expected) => {
    installInputInvoiceUsageFetch({ ...rowsPayload, rows: rowsPayload.rows.map((row) => ({
      ...row, bank: { ...row.bank, primary: { ...row.bank.primary, ...account } },
    })) });
    renderAuthenticatedAppAt("/input-invoice-usage");
    const table = await screen.findByRole("table", { name: "进项发票使用情况表" });
    const invoiceRow = within(table).getByRole("row", { name: /SD-INV-2026-0001/ });
    const accountValue = invoiceRow.querySelector(".input-invoice-usage-bank-tag-row .bank-account-value");
    expect(accountValue?.textContent?.replace(/\s/g, "")).toBe(expected);
  });

  test.each([
    ["0.00", "0.00", "收支相抵"],
    ["123.45", "123.45", "净收入"],
    ["", "—", "方向未知"],
  ])("流水主金额保留服务端净额和缺失语义：%s", async (netAmount, displayedAmount, netDirectionLabel) => {
    installInputInvoiceUsageFetch({ ...rowsPayload, rows: rowsPayload.rows.map((row) => ({
      ...row,
      bank: {
        ...row.bank,
        netAmount,
        netDirectionLabel,
      },
    })) });
    renderAuthenticatedAppAt("/input-invoice-usage");
    const table = await screen.findByRole("table", { name: "进项发票使用情况表" });
    const invoiceRow = within(table).getByRole("row", { name: /SD-INV-2026-0001/ });
    const amountCell = invoiceRow.querySelectorAll("th, td")[8] as HTMLElement;
    expect(amountCell.querySelector(".input-invoice-usage-bank-amount-line")?.textContent).toBe(displayedAmount);
    const metadata = amountCell.querySelector(".input-invoice-usage-bank-tag-row") as HTMLElement;
    expect(within(metadata).getByText(netDirectionLabel)).toBeVisible();
    expect(metadata.querySelector(".bank-account-value")).toHaveTextContent("3847");
  });

  test.each(["13%", "多税率", "—"])("金额列仅显示价税合计和服务端税率结论：%s", async (taxRate) => {
    installInputInvoiceUsageFetch({ ...rowsPayload, rows: rowsPayload.rows.map((row) => ({
      ...row, invoice: { ...row.invoice, taxRate },
    })) });
    renderAuthenticatedAppAt("/input-invoice-usage");
    const table = await screen.findByRole("table", { name: "进项发票使用情况表" });
    expect(within(table).getByRole("columnheader", { name: "价税合计/税率" })).toBeVisible();
    const invoiceRow = within(table).getByRole("row", { name: /SD-INV-2026-0001/ });
    const amountCell = within(invoiceRow).getByRole("cell", { name: `12345.67 ${taxRate}` });
    expect(amountCell).toHaveTextContent(`12345.67${taxRate}`);
    expect(within(amountCell).getByText(taxRate)).toHaveClass("input-invoice-usage-cell-secondary");
    expect(within(amountCell).queryByText(/11646.86|698.81/)).not.toBeInTheDocument();
    expect(within(table).queryByText("不含税/税率税额")).not.toBeInTheDocument();
  });

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
      sourceByPath["src/pages/InputInvoiceUsagePage.tsx"].includes("QuerySearch") ? null : "InputInvoiceUsagePage.tsx should use project QuerySearch",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx"].includes("FinanceTable")
        || sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageTable.tsx"].includes("input-invoice-usage-table-shell")
        ? null
        : "InputInvoiceUsageTable.tsx should use FinanceTable or the project dense table shell",
      sourceByPath["src/components/inputInvoiceUsage/ExpandableCellText.tsx"].includes("lucide-react")
        || sourceByPath["src/components/inputInvoiceUsage/ExpandableCellText.tsx"].includes("expandable-cell-text")
        ? null
        : "ExpandableCellText.tsx should use project/lucide controls instead of MUI icons",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("Checkbox.Control")
        && sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageFilterMenu.tsx"].includes("role=\"menuitemradio\"")
        ? null
        : "InputInvoiceUsageFilterMenu.tsx should use HeroUI Checkbox and preserve radio menu semantics",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx"].includes("AppDrawer") ? null : "InputInvoiceUsageDetailDrawer.tsx should use AppDrawer for the right drawer shape",
      sourceByPath["src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx"].includes("FilteredExportDrawer") ? null : "InputInvoiceUsageExportDrawer.tsx should use AppDrawer for the right drawer shape",
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
    const tableFrame = cssRule(styles, ".finance-page-table-frame");
    const tableShell = cssRule(styles, ".input-invoice-usage-table-shell");
    const table = cssRule(styles, ".input-invoice-usage-table .finance-table__content");
    const containedScroll = cssRule(styles, ".finance-table--contained .finance-table__scroll");
    const button = cssRule(styles, ".input-invoice-usage-button");
    const tableAction = cssRule(styles, ".input-invoice-usage-table-action,\\n.input-invoice-usage-expandable-cell-text__button");
    const drawerBody = cssRule(styles, ".input-invoice-usage-drawer-body");
    const detailSection = cssRule(styles, ".entity-detail-section");
    const filterTrigger = cssRule(styles, ".input-invoice-usage-filter-menu__trigger");
    const dataCell = cssRule(styles, ".input-invoice-usage-table-cell");
    const stickyHeader = cssRule(styles, ".input-invoice-usage-table-head");
    const strongSeparator = cssRule(styles, ".input-invoice-usage-table-cell--strong-separator");
    const compositeFilter = cssRule(styles, ".input-invoice-usage-filter-menu__panel--composite");

    expect(tableFrame).not.toContain("border-radius");
    expect(tableFrame).toContain("flex: 1 1 0");
    expect(tableFrame).toContain("min-height: 240px");
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
    expect(detailSection).toContain("padding: 0");
    expect(styles).toMatch(/\.entity-detail-section \+ \.entity-detail-section\s*{[^}]*margin-top:\s*16px/s);
    expect(filterTrigger).toContain("var(--motion-fast)");
    expect(dataCell).toContain("background: var(--fp-surface)");
    expect(styles).not.toMatch(/\.input-invoice-usage-table-cell--payment\s*\{[^}]*background:/s);
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
    const emptyTable = within(page).getByRole("table", { name: "进项发票使用情况表" });
    const emptyCells = emptyTable.querySelectorAll("tbody td");
    expect(emptyCells).toHaveLength(1);
    expect(emptyCells[0]).toHaveAttribute("colspan", "10");
    expect(emptyCells[0]).toHaveTextContent("当前条件下没有进项发票使用记录。");
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
    expect(await within(page).findByRole("table", { name: "进项发票使用情况表" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "OA 草稿预填管理" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "以发票反提 OA" })).toHaveClass("button--primary");
    expect(within(page).queryByRole("button", { name: "刷新", exact: true })).not.toBeInTheDocument();
    const refreshButton = within(page).getByRole("button", { name: "查询", exact: true });
    expect(within(page).getByLabelText("每页行数")).toHaveTextContent("20");

    const rowsBeforeRefresh = rowsRequests(fetchMock).length;
    await user.type(within(page).getByRole("searchbox"), "核对");
    await user.click(refreshButton);
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeRefresh));

    const table = within(page).getByRole("table", { name: "进项发票使用情况表" });
    const headerRows = table.querySelectorAll("thead > tr");
    expect(headerRows).toHaveLength(2);
    const groupHeaders = Array.from(headerRows[0].querySelectorAll("th"));
    expect(groupHeaders.map((header) => header.textContent)).toEqual(["进项发票", "支付状态", "OA", "流水"]);
    expect(groupHeaders.map((header) => header.colSpan)).toEqual([4, 1, 2, 3]);
    expect(groupHeaders[1]).toHaveAttribute("rowspan", "2");
    expect(groupHeaders[1]).toHaveAttribute("scope", "col");
    for (const header of [groupHeaders[0], groupHeaders[2], groupHeaders[3]]) {
      expect(header).toHaveAttribute("scope", "colgroup");
    }
    const headerRow = headerRows[1] as HTMLElement;
    expect(within(headerRow).getAllByRole("columnheader")).toHaveLength(9);
    expect(table.querySelectorAll("colgroup > col")).toHaveLength(10);
    expect(Array.from(table.querySelectorAll("colgroup"), group => group.children.length)).toEqual([4, 1, 2, 3]);
    expect(within(headerRow).getByRole("button", { name: "按开票日期排序" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 销方名称" })).toBeInTheDocument();
    expect(within(headerRow).queryByRole("button", { name: "筛选 支付状态" })).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "进项发票使用分类" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 申请人/类型" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 项目名称" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 对方户名" })).toBeInTheDocument();
    expect(within(headerRow).getByRole("button", { name: "筛选 金额" })).toBeInTheDocument();
    const bodyRows = Array.from(table.querySelectorAll("tbody > tr")) as HTMLElement[];
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("对方户名"))).toBe(false);
    const firstBodyRow = bodyRows[0];
    const firstRowCells = firstBodyRow.querySelectorAll("th, td");
    expect(firstRowCells).toHaveLength(10);
    expect(within(firstBodyRow).getAllByRole("rowheader")).toHaveLength(1);
    expect(firstRowCells[0]).toHaveAttribute("scope", "row");

    expect(await within(page).findByText("SD-INV-2026-0001")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("12345.67")).toBeInTheDocument();
    expect(within(firstRowCells[2] as HTMLElement).getByText("6%")).toBeInTheDocument();
    expect(within(firstRowCells[3] as HTMLElement).getByText("很长很长的货物或应税劳务名称用于验证两行截断后出现展开按钮")).toBeInTheDocument();
    expect(within(page).getByText("2026-05-02")).toBeInTheDocument();
    const invoiceDetailButton = within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 详情" });
    expect(invoiceDetailButton).toBeInTheDocument();
    const invoiceCell = firstRowCells[0];
    expect(invoiceCell).toBeTruthy();
    expect(within(invoiceCell as HTMLElement).queryByText("详情")).not.toBeInTheDocument();
    const oaCell = firstRowCells[5] as HTMLElement;
    expect(within(oaCell).getByText("樊祖芳")).toBeInTheDocument();
    expect(within(oaCell).queryByLabelText(/OA流程状态/)).not.toBeInTheDocument();
    expect(within(oaCell).queryByText("状态未知")).not.toBeInTheDocument();
    expect(within(oaCell).getByRole("button", { name: "查看OA 樊祖芳 详情" })).toBeInTheDocument();
    expect(within(oaCell).queryByText("详情")).not.toBeInTheDocument();
    expect(within(page).getByText("拆分流水的付款用途尚未明确")).toBeVisible();
    expect(within(page).getByText("2026-05-03 10:30:00")).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看流水 云南银行交易对方户名很长很长需要换行显示 详情" })).toBeInTheDocument();
    expect(within(page).queryByText(/outflow/)).not.toBeInTheDocument();
    expect(within(page).getByText("净支出")).toBeInTheDocument();
    const bankAmountCell = firstRowCells[8] as HTMLElement;
    expect(bankAmountCell.querySelector(".input-invoice-usage-bank-amount-line")).toHaveTextContent(/^12345\.67$/);
    const bankMetadata = bankAmountCell.querySelector(".input-invoice-usage-bank-tag-row") as HTMLElement;
    expect(within(bankMetadata).getByText("净支出")).toBeInTheDocument();
    expect(bankMetadata.querySelector(".bank-account-value")).toHaveTextContent("交行");
    expect(bankMetadata.querySelector(".bank-account-value")).not.toHaveTextContent("交通银行");
    expect(bankMetadata.querySelector(".bank-account-value")).toHaveTextContent("3847");
    expect(bankMetadata.querySelector(".input-invoice-usage-bank-tag")).toBeNull();
    expect(within(table).getByText("待处理").closest(".input-invoice-usage-payment-cell")).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "按开票日期排序" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("sort_field")).toBe("invoice_date");
      expect(request?.searchParams.get("sort_direction")).toBe("asc");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 销方名称" }));
    await user.click(await screen.findByRole("checkbox", { name: /云南长文本供应商科技发展有限公司第一分公司/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "seller_name", operator: "in", values: ["云南长文本供应商科技发展有限公司第一分公司"] });
    });
    await user.keyboard("{Escape}");

    await user.click(within(page).getByRole("button", { name: "筛选 申请人/类型" }));
    await user.click(await screen.findByRole("checkbox", { name: /樊祖芳/ }));
    await user.click(await screen.findByRole("checkbox", { name: /支付申请/ }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toContainEqual({ field: "oa_applicant", operator: "in", values: ["樊祖芳"] });
      expect(filters).toContainEqual({ field: "oa_application_type", operator: "in", values: ["支付申请"] });
    });
    await user.keyboard("{Escape}");

    await user.click(within(page).getByRole("button", { name: "筛选 金额" }));
    await user.click(await screen.findByRole("checkbox", { name: /交通银行 3847/ }));
    await user.click(await screen.findByRole("checkbox", { name: /支出/ }));
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

  test("shows net payment while removing the obsolete amount category", async () => {
    const row = structuredClone(rowsPayload.rows[0]);
    row.bank.original_amount = "1085.00";
    row.bank.netAmount = "1015.00";
    row.bank.netDirectionLabel = "净支出";
    installInputInvoiceUsageFetch({ ...rowsPayload, rows: [row] });
    renderAuthenticatedAppAt("/input-invoice-usage");
    expect(await screen.findByText("1015.00")).toBeInTheDocument();
    expect(screen.getByText("净支出")).toBeInTheDocument();
    expect(screen.queryByText("1085.00")).not.toBeInTheDocument();
    expect(screen.getByText(row.paymentStatus.reason)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /金额待核对/ })).not.toBeInTheDocument();
  });

  test("distinguishes paid, unclassified, and waiting-payment status chips by canonical code", async () => {
    const statusRows = [
      { code: "paid", label: "已付款", tone: "success" },
      { code: "unclassified", label: "待处理", tone: "neutral" },
      { code: "waiting_payment", label: "待付款", tone: "warning" },
    ].map((status, index) => ({
      ...rowsPayload.rows[0],
      id: `usage-status-row-${index + 1}`,
      invoice: {
        ...rowsPayload.rows[0].invoice,
        id: `usage-status-invoice-${index + 1}`,
        displayNo: `SD-STATUS-${index + 1}`,
      },
      paymentStatus: {
        code: status.code,
        label: status.label,
        reason: "",
      },
    }));
    installInputInvoiceUsageFetch({
      ...rowsPayload,
      rows: statusRows,
      pagination: { page: 1, pageSize: 20, total: statusRows.length },
    });

    renderAuthenticatedAppAt("/input-invoice-usage");

    const page = await screen.findByTestId("input-invoice-usage-page");
    for (const status of [
      { label: "已付款", tone: "success" },
      { label: "待处理", tone: "neutral" },
      { label: "待付款", tone: "warning" },
    ]) {
      expect(await within(page).findByText(status.label, { selector: ".input-invoice-usage-tag" }))
        .toHaveClass(`input-invoice-usage-tag--${status.tone}`);
    }
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
              original_amount: "100.00",
              netAmount: "100.00",
              netDirectionLabel: "净支出",
              original_transaction_count: 1,
            },
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              {
                ...rowsPayload.rows[0].bank.primary,
                id: "bank-multi-a",
                amount: "40.00",
                original_amount: "40.00",
                netAmount: "40.00",
                netDirectionLabel: "净支出",
                original_transaction_count: 1,
              },
              {
                ...rowsPayload.rows[0].bank.primary,
                id: "bank-multi-b",
                amount: "60.00",
                original_amount: "60.00",
                netAmount: "60.00",
                netDirectionLabel: "净支出",
                original_transaction_count: 1,
              },
            ],
            original_amount: "100.00",
            netAmount: "100.00",
            netDirectionLabel: "净支出",
            original_transaction_count: 2,
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
    const firstBodyRow = page.querySelector(".input-invoice-usage-table tbody > tr") as HTMLElement;
    const firstRowCells = firstBodyRow.querySelectorAll("th, td");
    expect(within(firstRowCells[2] as HTMLElement).getByText("100.00")).toBeInTheDocument();
    expect(within(firstRowCells[5] as HTMLElement).getByText("合计 100.00")).toBeInTheDocument();
    expect(within(firstRowCells[8] as HTMLElement).getByText("100.00")).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "查看OA 刘际涛 详情" })).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "查看刘际涛关联OA 2 条" }));
    const oaDrawer = await screen.findByRole("dialog", { name: "OA详情" });
    expect(within(oaDrawer).getByText("刘际涛")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看云南银行交易对方户名很长很长需要换行显示关联流水 2 条" }));
    const bankDrawer = await screen.findByRole("dialog", { name: "银行流水详情" });
    expect(within(bankDrawer).getByText("银行流水 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看发票 SD-INV-2026-0001 关联发票 2 张" }));
    const invoiceDrawer = await screen.findByRole("dialog", { name: "发票详情" });
    expect(within(invoiceDrawer).getByText("发票 1")).toBeInTheDocument();

    const relationRequests = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
      .filter((url) => url.pathname === "/api/input-invoice-usage/rows/usage-row-multi/relation-details");
    expect(relationRequests.map((url) => url.searchParams.get("kind"))).toEqual(["oa", "bank", "invoice"]);
    expect(relationRequests.map((url) => url.searchParams.get("month"))).toEqual(["2026-05", "2026-05", "2026-05"]);
  });

  test("hierarchy and OA header filter combine without changing other query fields", async () => {
    const user = userEvent.setup();
    const fetchMock = installInputInvoiceUsageFetch();
    renderAuthenticatedAppAt("/input-invoice-usage");
    await user.click(await screen.findByRole("button", { name: "已使用 1 张" }));
    await user.click(screen.getByRole("button", { name: "OA 关联筛选" }));
    await user.click(await screen.findByRole("menuitemradio", { name: "未关联 OA" }));
    await waitFor(() => {
      const query = rowsRequests(fetchMock).at(-1)!;
      expect(JSON.parse(decodeURIComponent(query.searchParams.get("filters")!))).toEqual(expect.arrayContaining([
        { field: "usage_status", operator: "in", values: ["used"] },
        { field: "oa_relation", operator: "in", values: ["unlinked"] },
      ]));
      expect(query.searchParams.get("page")).toBe("1");
    });
    await user.click(screen.getByRole("button", { name: "发票＝付款 0 张" }));
    await waitFor(() => {
      const filters = JSON.parse(decodeURIComponent(rowsRequests(fetchMock).at(-1)!.searchParams.get("filters")!));
      expect(filters).toContainEqual({ field: "payment_status", operator: "in", values: ["paid"] });
      expect(filters).toContainEqual({ field: "oa_relation", operator: "in", values: ["unlinked"] });
    });
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
    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    expect(screen.getByRole("button", { name: "创建 OA 草稿" })).toBeEnabled();
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
    await within(page).findByRole("table", { name: "进项发票使用情况表" });
    const initialRowsRequests = rowsRequests(fetchMock).length;

    await user.click(within(page).getByRole("button", { name: "以发票反提 OA" }));
    await user.click(await screen.findByRole("button", { name: "选择本页" }));
    expect(screen.getByRole("button", { name: "创建 OA 草稿" })).toBeEnabled();

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

  test.each(["unclassified", "pending"])("restores valid payment filters and clears obsolete %s filter", async (status) => {
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
        page: 3,
        pageSize: 20,
        keyword: "",
        invoiceDateFrom: "",
        invoiceDateTo: "",
        month: "",
        filters: [{ field: "payment_status", operator: "in", values: [status] }],
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
    expect(request.searchParams.get("page")).toBe("1");
    expect(JSON.parse(decodeURIComponent(request.searchParams.get("filters") ?? "[]"))).toEqual(status === "pending" ? [] : [
      { field: "payment_status", operator: "in", values: [status] },
      { field: "usage_status", operator: "in", values: ["used"] },
    ]);
    expect(request.searchParams.get("sort_field")).toBe("invoice_no");
    expect(request.searchParams.get("sort_direction")).toBe("asc");
  });

  test.each(["bounds", "column"])("restores all dates before the first request from stored %s filters", async (kind) => {
    const fetchMock = installInputInvoiceUsageFetch();
    const stored = {
      page: 4, pageSize: 50, keyword: "供应商", month: kind === "bounds" ? "2025-12" : "",
      invoiceDateFrom: kind === "bounds" ? "2025-12-01" : "", invoiceDateTo: kind === "bounds" ? "2025-12-31" : "",
      filters: [
        { field: "payment_status", operator: "in", values: ["unclassified"] },
        ...(kind === "column" ? [
          { field: "invoice_date", operator: "equals", value: "2025-12-01" },
          { field: "bank_trade_time", operator: "between", from: "2025-01-01", to: "2025-12-31" },
        ] : []),
      ],
      sortField: "invoice_no", sortDirection: "asc", activeWorkflow: "export",
      detailTarget: { kind: "invoice", id: "old-invoice" },
    };
    window.sessionStorage.setItem(buildPageSessionStorageKey({ userScope: "101", pageKey: "input-invoice-usage", stateKey: "query" }),
      JSON.stringify(createStoredPayload({ version: 1, ttlMs: 60_000, value: stored })));
    renderAuthenticatedAppAt("/input-invoice-usage");
    await screen.findByTestId("input-invoice-usage-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    for (const request of rowsRequests(fetchMock)) {
      for (const field of ["month", "invoice_date_from", "invoice_date_to"]) expect(request.searchParams.has(field)).toBe(false);
      expect(request.searchParams.get("page")).toBe("1");
      expect(request.searchParams.get("page_size")).toBe("50");
      expect(request.searchParams.get("keyword")).toBe("供应商");
      expect(JSON.parse(decodeURIComponent(request.searchParams.get("filters") ?? "[]"))).toEqual([stored.filters[0], { field: "usage_status", operator: "in", values: ["used"] }]);
      expect(request.searchParams.get("sort_direction")).toBe("asc");
    }
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
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

    expect(await screen.findByText("导出 1 张")).toBeInTheDocument();
    expect(screen.getAllByText("SD-INV-2026-0001").length).toBeGreaterThanOrEqual(1);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/input-invoice-usage/export-summary";
    })).toBe(true);

    await user.click(screen.getByRole("button", { name: "下载 Excel" }));
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

    expect(await screen.findByText("导出 1 张")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "下载 Excel" }));

    expect(await screen.findByText("进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。")).toBeInTheDocument();
    expect(screen.queryByText("已生成 进项.xlsx")).not.toBeInTheDocument();
  });
});
