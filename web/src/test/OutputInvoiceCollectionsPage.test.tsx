import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const outputInvoiceCollectionsSourceFiles = [
  "src/pages/OutputInvoiceCollectionsPage.tsx",
  "src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx",
  "src/components/outputInvoiceCollections/OutputInvoiceCollectionFilterMenu.tsx",
  "src/components/outputInvoiceCollections/ExpandableCellText.tsx",
  "src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx",
  "src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx",
  "src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx",
  "src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx",
  "src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx",
  "src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx",
  "src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx",
] as const;

const rowsPayload = {
  rows: [
    {
      id: "output-collection-row-001",
      invoiceId: "out-001",
      invoiceIdentityKey: "id:out-001",
      invoice: {
        id: "out-001",
        displayNo: "XSFP-2026-0001",
        invoiceNo: "0001",
        invoiceCode: "5300",
        digitalInvoiceNo: "XSFP-2026-0001",
        invoiceDate: "2026-05-02",
        issueDate: "2026-05-02",
        buyerName: "云南客户科技有限公司",
        buyerTaxNo: "91530100BUYER01",
        sellerName: "云南溯源科技有限公司",
        sellerTaxNo: "91530000SELLER01",
        totalWithTax: "12345.67",
        amountWithoutTax: "11646.86",
        taxRate: "6%",
        taxAmount: "698.81",
        specificBusinessType: "信息技术服务",
        taxableItemName: "很长很长的销项发票货物或应税劳务名称用于验证展开按钮",
      },
      collectionStatus: {
        code: "partial_collected",
        label: "待收款，已收部分款",
        reason: "存在收入流水，但收入流水合计小于发票价税合计。",
        collectedAmount: "5000.00",
        pendingAmount: "7345.67",
        manualOverride: {
          id: "override-001",
          statusCode: "pending_red_invoice",
          expectedCollectionDate: "2026-06-20",
          note: "人工确认待冲红",
          version: 2,
        },
        expectedCollectionDate: "2026-06-20",
        reminder: {
          id: "reminder-001",
          remindAt: "2026-06-15T09:00:00+08:00",
          channel: "oa",
          note: "到期提醒",
          status: "active",
        },
      },
      bankTransactions: {
        primaryBankTransactionId: "bank-001",
        counterpartyName: "云南客户科技有限公司",
        tradeTime: "2026-05-03 10:30:00",
        amount: "5000.00",
        direction: "inflow",
        directionLabel: "收入",
        bankName: "建设银行",
        accountLast4: "8106",
        summary: "客户回款摘要内容很长很长用于验证折叠展示",
        remark: "银行备注",
        relationCount: 1,
        hasMultiple: false,
        detailMode: "single",
        summaries: [
          {
            bankTransactionId: "bank-001",
            counterpartyName: "云南客户科技有限公司",
            tradeTime: "2026-05-03 10:30:00",
            amount: "5000.00",
            direction: "inflow",
            directionLabel: "收入",
            bankName: "建设银行",
            accountLast4: "8106",
            summary: "客户回款摘要内容很长很长用于验证折叠展示",
            remark: "银行备注",
          },
        ],
      },
      redInvoiceRelation: {
        relationCount: 2,
        hasMultiple: true,
        detailMode: "list",
        summaries: [
          {
            relatedInvoiceId: "out-red-auto",
            invoiceNo: "AUTO-RED",
            evidence: "同购方、同金额、正负方向相反。",
            confidence: "auto_high",
            source: "auto",
          },
          {
            relationId: "relation-manual-001",
            relatedInvoiceId: "out-red-manual",
            invoiceNo: "MANUAL-RED",
            evidence: "客户邮件确认红冲",
            confidence: "manual_confirmed",
            source: "manual",
          },
        ],
      },
      receipt: {
        status: "pending",
        label: "待出收据",
        reason: "可基于收入流水生成 Sheet7 预览；第一阶段不保存正式收据。",
        previewAvailable: true,
        sourceAvailable: true,
      },
    },
    {
      id: "output-collection-row-002",
      invoiceId: "out-red-candidate",
      invoiceIdentityKey: "id:out-red-candidate",
      invoice: {
        id: "out-red-candidate",
        displayNo: "XSFP-2026-RED",
        invoiceNo: "RED-0001",
        invoiceCode: "5300",
        digitalInvoiceNo: "XSFP-2026-RED",
        invoiceDate: "2026-05-04",
        issueDate: "2026-05-04",
        buyerName: "云南客户科技有限公司",
        buyerTaxNo: "91530100BUYER01",
        sellerName: "云南溯源科技有限公司",
        sellerTaxNo: "91530000SELLER01",
        totalWithTax: "-12345.67",
        amountWithoutTax: "-11646.86",
        taxRate: "6%",
        taxAmount: "-698.81",
        specificBusinessType: "信息技术服务",
        taxableItemName: "红字信息技术服务",
      },
      collectionStatus: {
        code: "pending_collection",
        label: "待收款",
        reason: "候选发票",
        collectedAmount: "0.00",
        pendingAmount: "-12345.67",
      },
      bankTransactions: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
      },
      redInvoiceRelation: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
      },
      receipt: {
        status: "not_required",
        label: "无需收据",
        reason: "候选发票",
        previewAvailable: false,
        sourceAvailable: true,
      },
    },
  ],
  pagination: {
    page: 1,
    pageSize: 20,
    total: 51,
  },
  filterConfig: [],
  readModelStatus: "live_query",
  generatedAt: "2026-05-24T00:00:00Z",
  sourceVersion: "output-invoice-collections:v1",
};

function installOutputInvoiceCollectionsFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/output-invoice-collections/rows") {
      return jsonResponse(rowsPayload);
    }
    if (url.pathname === "/api/output-invoice-collections/filter-options") {
      return jsonResponse({
        fields: [
          {
            field: "invoice_no",
            label: "发票号码",
            mode: "text",
            sortable: true,
            operators: ["contains", "equals"],
            options: [],
          },
          {
            field: "total_with_tax",
            label: "价税合计",
            mode: "money",
            sortable: true,
            operators: ["between", "equals"],
            options: [],
          },
          {
            field: "invoice_date",
            label: "开票日期",
            mode: "date",
            sortable: true,
            operators: ["between", "equals"],
            options: [],
          },
          {
            field: "collection_status",
            label: "收款状态",
            mode: "enum_multi",
            sortable: true,
            operators: ["in"],
            options: [{ value: "partial_collected", label: "待收款，已收部分款", count: 1 }],
          },
        ],
      });
    }
    if (url.pathname === "/api/output-invoice-collections/status-rules") {
      return jsonResponse({
        version: "sheet6-static-v1",
        readOnly: true,
        rules: [
          {
            id: "partial_collected",
            label: "待收款，已收部分款",
            description: "收入流水金额小于销项发票金额",
            recognitionMode: "自动识别",
            requiredFacts: ["销项发票", "收入流水"],
            workbenchRequirement: "关联台能证明已收部分流水",
            priority: 4,
          },
          {
            id: "pending_red_invoice",
            label: "待冲红",
            description: "人工确认未来需要冲红",
            recognitionMode: "手动标记",
            requiredFacts: ["销项发票"],
            workbenchRequirement: "人工确认",
            priority: 6,
          },
        ],
        manualStatusOptions: [
          { code: "pending_collection", label: "待收款", severity: "warning" },
          { code: "pending_red_invoice", label: "待冲红", severity: "warning" },
        ],
        permissions: { can_save: true, can_admin: true },
      });
    }
    if (url.pathname === "/api/output-invoice-collections/receipts/history") {
      return jsonResponse({
        invoiceId: "out-001",
        sourceAvailable: true,
        sourceName: "formal_receipt_lifecycle",
        receipts: [
          {
            id: "receipt-issued-001",
            receiptNo: "SK2026050001",
            amount: "5000.00",
            createdAt: "2026-05-03T10:40:00+08:00",
            status: "issued",
          },
          {
            id: "receipt-voided-001",
            receiptNo: "SK2026050000",
            amount: "5000.00",
            createdAt: "2026-05-02T10:40:00+08:00",
            voidedAt: "2026-05-03T09:00:00+08:00",
            voidReason: "信息有误",
            status: "voided",
          },
        ],
      });
    }
    if (url.pathname === "/api/output-invoice-collections/receipt-preview") {
      return jsonResponse({
        canPreview: true,
        selectedBankTransactionId: "bank-001",
        candidates: [],
        receipt: {
          templateVersion: "sheet7-static-v1",
          companyName: "云南溯源科技有限公司",
          title: "收 据",
          date: "2026-05-03",
          dateParts: { year: "2026", month: "05", day: "03" },
          payerName: "云南客户科技有限公司",
          summary: "信息技术服务",
          amount: "5000.00",
          amountUppercase: "人民币伍仟元整",
          remark: "销项发票 XSFP-2026-0001",
          bankName: "建设银行",
          canCreateFormalReceipt: false,
        },
      });
    }
    if (url.pathname === "/api/output-invoice-collections/invoices/out-001/detail") {
      return jsonResponse({ id: "out-001", invoiceNo: "0001", buyerName: "云南客户科技有限公司" });
    }
    if (url.pathname === "/api/output-invoice-collections/bank-transactions/bank-001/detail") {
      return jsonResponse({ id: "bank-001", counterpartyName: "云南客户科技有限公司", amount: "5000.00" });
    }
    if (url.pathname === "/api/output-invoice-collections/receipt-settings") {
      if (init?.method === "PUT") {
        return jsonResponse({ settings: { prefix: "SK", resetPeriod: "monthly", version: 2 } });
      }
      return jsonResponse({ settings: { prefix: "SK", resetPeriod: "monthly", version: 1 } });
    }
    if (
      url.pathname === "/api/output-invoice-collections/rows/output-collection-row-001/collection-status"
      || url.pathname === "/api/output-invoice-collections/rows/output-collection-row-001/collection-reminder"
      || url.pathname === "/api/output-invoice-collections/rows/output-collection-row-001/red-invoice-relations"
      || url.pathname === "/api/output-invoice-collections/rows/output-collection-row-001/receipts"
      || url.pathname === "/api/output-invoice-collections/receipts/receipt-issued-001/void"
      || url.pathname === "/api/output-invoice-collections/receipts/receipt-voided-001/reissue"
      || url.pathname === "/api/output-invoice-collections/red-invoice-relations/relation-manual-001"
      || url.pathname === "/api/output-invoice-collections/rows/output-collection-row-001/collection-reminder/reminder-001"
    ) {
      return jsonResponse({ ok: true });
    }
    return jsonResponse({});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function rowsRequests(fetchMock: ReturnType<typeof installOutputInvoiceCollectionsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/output-invoice-collections/rows");
}

function statusRulesRequests(fetchMock: ReturnType<typeof installOutputInvoiceCollectionsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/output-invoice-collections/status-rules");
}

function readWebSource(path: string) {
  return readFileSync(resolve(__dirname, "..", "..", path), "utf8");
}

function cssRule(source: string, selector: string) {
  const normalizedSelector = selector.replace(/\\n/g, "\n");
  const escapedSelector = normalizedSelector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Output invoice collections page", () => {
  test("targets project primitives for page shell, grouped table, filters and drawers", () => {
    const sourceByPath = Object.fromEntries(outputInvoiceCollectionsSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = outputInvoiceCollectionsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = outputInvoiceCollectionsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = outputInvoiceCollectionsSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /TablePagination|TextField|Skeleton|Chip|IconButton|TableCell|TableRow|TableHead|TableBody|DialogTitle|DialogContent|DialogActions|CircularProgress|FormControlLabel/.test(source) ? [path] : [];
    });
    const missingPrimitiveTargets = [
      sourceByPath["src/pages/OutputInvoiceCollectionsPage.tsx"].includes("PageScaffold") ? null : "OutputInvoiceCollectionsPage.tsx should keep PageScaffold",
      sourceByPath["src/pages/OutputInvoiceCollectionsPage.tsx"].includes("StatePanel") ? null : "OutputInvoiceCollectionsPage.tsx should keep project empty/error state primitives",
      sourceByPath["src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx"].includes("OutputInvoiceCollectionFilterMenu")
        ? null
        : "OutputInvoiceCollectionsTable.tsx should preserve filter menu contract",
      /FinanceTable|output-invoice-collections-table/.test(sourceByPath["src/components/outputInvoiceCollections/OutputInvoiceCollectionsTable.tsx"])
        ? null
        : "OutputInvoiceCollectionsTable.tsx should use a project table primitive or project table class",
      sourceByPath["src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx"].includes("AppDrawer") ? null : "Detail drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/CollectionStatusRulesDrawer.tsx"].includes("AppDrawer") ? null : "Rules drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/CollectionStatusReminderDrawer.tsx"].includes("AppDrawer") ? null : "Status reminder drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/RedInvoiceRelationDrawer.tsx"].includes("AppDrawer") ? null : "Red relation drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx"].includes("AppDrawer") ? null : "Receipt history drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/ReceiptHistoryDrawer.tsx"].includes("AppDialog") ? null : "Receipt history void/reissue confirmations should use AppDialog",
      sourceByPath["src/components/outputInvoiceCollections/ReceiptPreviewDrawer.tsx"].includes("AppDrawer") ? null : "Receipt preview drawer should use AppDrawer",
      sourceByPath["src/components/outputInvoiceCollections/ReceiptSettingsDrawer.tsx"].includes("AppDrawer") ? null : "Receipt settings drawer should use AppDrawer",
    ].filter(Boolean);

    expect({
      forbiddenMuiImports,
      forbiddenMuiSelectors,
      forbiddenLegacySurfaces,
      missingPrimitiveTargets,
    }).toEqual({
      forbiddenMuiImports: [],
      forbiddenMuiSelectors: [],
      forbiddenLegacySurfaces: [],
      missingPrimitiveTargets: [],
    });
  });

  test("keeps premium compact table, token colors, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const pageButton = cssRule(styles, ".output-invoice-collections-button");
    const queryControls = cssRule(styles, ".output-invoice-collections-field input,\n.output-invoice-collections-field select");
    const loading = cssRule(styles, ".output-invoice-collections-loading__bar,\n.output-invoice-collections-loading__panel");
    const filterTrigger = cssRule(styles, ".output-invoice-collection-filter-menu__trigger");
    const filterItem = cssRule(styles, ".output-invoice-collection-filter-menu__item,\n.output-invoice-collection-filter-menu__clear");
    const filterFields = cssRule(styles, ".output-invoice-collection-filter-menu__field input,\n.output-invoice-collection-filter-menu__field select");
    const filterApply = cssRule(styles, ".output-invoice-collection-filter-menu__apply");
    const expandableButton = cssRule(styles, ".output-invoice-collection-expandable-cell-text__button");
    const tableShell = cssRule(styles, ".output-invoice-collections-table-shell");
    const table = cssRule(styles, ".output-invoice-collections-table");
    const tableCells = cssRule(styles, ".output-invoice-collections-table-cell");
    const tableAction = cssRule(styles, ".output-invoice-collections-table-action");
    const tableActionIcon = cssRule(styles, ".output-invoice-collections-table-action--icon");
    const sortButton = cssRule(styles, ".output-invoice-collections-sort-button");
    const paginationButton = cssRule(styles, ".output-invoice-collections-pagination-actions button");
    const drawerButton = cssRule(styles, ".output-invoice-collection-drawer__button");
    const drawerFields = cssRule(styles, ".output-invoice-collection-drawer__field input,\n.output-invoice-collection-drawer__field select,\n.output-invoice-collection-drawer__field textarea");
    const groupInvoice = cssRule(styles, ".output-invoice-collections-table-group-header--invoice");
    const groupStatus = cssRule(styles, ".output-invoice-collections-table-group-header--status,\n.output-invoice-collections-table-cell--status");
    const groupBank = cssRule(styles, ".output-invoice-collections-table-group-header--bank");
    const groupReceipt = cssRule(styles, ".output-invoice-collections-table-group-header--receipt");
    const outputGroupRules = [groupInvoice, groupStatus, groupBank, groupReceipt].join("\n");

    expect(pageButton).toContain("var(--motion-fast)");
    expect(pageButton).toContain("var(--ease-out-quart)");
    expect(queryControls).toContain("var(--motion-fast)");
    expect(loading).toContain("border-radius: var(--fp-radius-sm)");
    expect(filterTrigger).toContain("var(--motion-fast)");
    expect(filterItem).toContain("var(--motion-fast)");
    expect(filterFields).toContain("var(--motion-fast)");
    expect(filterApply).toContain("var(--motion-fast)");
    expect(expandableButton).toContain("var(--motion-fast)");
    expect(tableShell).toContain("min-height: 320px");
    expect(tableShell).toContain("max-height: calc(100vh - 214px)");
    expect(table).toContain("min-width: 1240px");
    expect(table).not.toContain("min-width: 1680px");
    expect(tableCells).toContain("transition: background-color var(--motion-fast)");
    expect(tableAction).toContain("var(--motion-fast)");
    expect(tableActionIcon).toContain("width: 26px");
    expect(tableActionIcon).toContain("padding: 0");
    expect(sortButton).toContain("var(--motion-fast)");
    expect(paginationButton).toContain("var(--motion-fast)");
    expect(drawerButton).toContain("var(--motion-fast)");
    expect(drawerFields).toContain("var(--motion-fast)");
    expect(groupInvoice).toContain("color-mix(in srgb, var(--fp-success-soft)");
    expect(groupStatus).toContain("color-mix(in srgb, var(--fp-warning-soft)");
    expect(groupBank).toContain("color-mix(in srgb, var(--fp-primary-soft)");
    expect(groupReceipt).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(outputGroupRules).not.toMatch(/#f6fbf8|#f5f9ff|#f8fafc|#fbfdfc|#f1faff|#f8fbff|#fbfcfd|rgba\(14,\s*165,\s*233,\s*0\.10\)/);
  });

  test("uses a standard empty state while read model refresh details stay hidden", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/output-invoice-collections/rows") {
        return jsonResponse({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
          readModelStatus: "refreshing",
        }, 202);
      }
      if (url.pathname === "/api/output-invoice-collections/filter-options") {
        return jsonResponse({ fields: [], read_model_status: "refreshing", readModelStatus: "refreshing" }, 202);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(await within(page).findByText("当前条件下暂无记录。")).toBeInTheDocument();
    expect(within(page).queryByText("销项发票收款情况读模型正在刷新，完成后页面会自动重新加载。")).not.toBeInTheDocument();
  });

  test("cleans up read model retry reload after route unmount", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/output-invoice-collections/rows") {
        return jsonResponse({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "refreshing",
          readModelStatus: "refreshing",
        }, 202);
      }
      if (url.pathname === "/api/output-invoice-collections/filter-options") {
        return jsonResponse({ fields: [], read_model_status: "refreshing", readModelStatus: "refreshing" }, 202);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/output-invoice-collections");
    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(await within(page).findByText("当前条件下暂无记录。")).toBeInTheDocument();
    expect(rowsRequests(fetchMock)).toHaveLength(1);

    fireEvent.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByTestId("output-invoice-collections-page")).not.toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(rowsRequests(fetchMock)).toHaveLength(1);

    vi.useRealTimers();
    fireEvent.click(screen.getByRole("link", { name: "销项发票收款情况" }));
    expect(await screen.findByTestId("output-invoice-collections-page")).toBeInTheDocument();

    expect(rowsRequests(fetchMock).length).toBeGreaterThan(1);
  });

  test("adds sidebar route and renders grouped project table layout without fake export", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();

    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];
    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ label: "销项发票收款情况", to: "/output-invoice-collections" }),
      ]),
    );

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(within(page).getByRole("heading", { name: "销项发票收款情况" })).toBeInTheDocument();
    expect(within(page).queryByText("以销项发票为主对象查看收款状态、收入流水和收据预览。")).not.toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "刷新" })).not.toBeInTheDocument();
    expect(within(page).queryByText("关键字")).not.toBeInTheDocument();
    expect(within(page).queryByLabelText("收款状态")).not.toBeInTheDocument();
    for (const label of ["销项发票数", "待收款金额", "已收金额", "待出收据数"]) {
      expect(within(page).queryByText(label)).not.toBeInTheDocument();
    }
    expect(within(page).queryByRole("button", { name: /导出/ })).not.toBeInTheDocument();
    expect(await within(page).findByText("XSFP-2026-0001")).toBeInTheDocument();
    expect(statusRulesRequests(fetchMock)).toHaveLength(0);

    await user.type(within(page).getByRole("searchbox", { name: "搜索销项发票收款情况" }), "客户科技");
    await user.click(within(page).getByRole("button", { name: "查询" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("keyword")).toBe("客户科技");
    });
    await user.clear(within(page).getByRole("searchbox", { name: "搜索销项发票收款情况" }));
    await user.keyboard("{Enter}");
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("keyword")).toBeNull();
    });
    fireEvent.input(within(page).getByLabelText("月份"), { target: { value: "2026-05" } });
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("month")).toBe("2026-05");
    });

    expect(within(page).getByRole("table", { name: "销项发票收款情况表" })).toBeInTheDocument();

    const headerRows = within(page).getAllByRole("row").slice(0, 2);
    for (const label of ["销项发票", "收款状态", "收入流水", "收据"]) {
      expect(within(headerRows[0]).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of [
      "发票号码",
      "购方",
      "价税合计",
      "业务/货物劳务",
      "收款状态",
      "付款方/日期",
      "收款金额",
      "摘要",
      "收据情况",
    ]) {
      expect(within(headerRows[1]).getAllByText(label)).toHaveLength(1);
    }
    expect(within(headerRows[1]).getByText("税额/税率")).toBeInTheDocument();
    expect(within(headerRows[1]).queryByRole("columnheader", { name: "税额/税率" })).not.toBeInTheDocument();
    expect(within(headerRows[1]).queryByText("银行/摘要")).not.toBeInTheDocument();
    const bodyRows = within(page).getAllByRole("row").slice(2);
    expect(bodyRows.some((row) => within(row).queryByText("发票号码"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("付款方/日期"))).toBe(false);
    expect(bodyRows.some((row) => within(row).queryByText("银行/摘要"))).toBe(false);

    expect(within(page).getAllByText("云南客户科技有限公司").length).toBeGreaterThan(0);
    expect(within(page).getByText("698.81 / 6%")).toBeInTheDocument();
    const amountCell = within(page).getByText("5,000.00").closest('[data-column-role="amount"]');
    expect(amountCell).not.toBeNull();
    const amountTags = within(amountCell as HTMLElement).getAllByText(/收入|建设银行 8106/).map((element) => element.textContent);
    expect(amountTags).toEqual(["收入", "建设银行 8106"]);
    expect(within(page).queryByText("建设银行 8106")).toBeInTheDocument();
    expect(
      within(page).getAllByText("待收款，已收部分款")
        .some((element) => element.closest(".output-invoice-collection-status-cell")),
    ).toBe(true);
    expect(within(page).queryByText("存在收入流水，但收入流水合计小于发票价税合计。")).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看发票 XSFP-2026-0001 详情" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看流水 云南客户科技有限公司 详情" })).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(page).getAllByRole("button", { name: "已出收据" }).length).toBeGreaterThan(0);
    expect(within(page).getAllByRole("button", { name: "待出收据" }).length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: /展开.*销项发票货物或应税劳务名称/ }));
    expect(within(page).getByRole("button", { name: /收起.*销项发票货物或应税劳务名称/ })).toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "发票号码 排序" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("sort_field")).toBe("invoice_no");
      expect(request?.searchParams.get("sort_direction")).toBe("asc");
    });

    await user.click(within(page).getByRole("button", { name: "筛选 收款状态" }));
    await user.click(await screen.findByRole("menuitemcheckbox", { name: "待收款，已收部分款 1" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([{ field: "collection_status", operator: "in", values: ["partial_collected"] }]);
    });
    await user.keyboard("{Escape}");

    await user.click(within(page).getByRole("button", { name: "筛选 发票号码" }));
    await user.type(await screen.findByLabelText("发票号码筛选值"), "0001");
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual([
        { field: "collection_status", operator: "in", values: ["partial_collected"] },
        { field: "invoice_no", operator: "contains", value: "0001" },
      ]);
    });

    await user.click(within(page).getByRole("button", { name: "筛选 价税合计" }));
    await user.type(await screen.findByLabelText("价税合计最小值"), "100");
    await user.type(screen.getByLabelText("价税合计最大值"), "200");
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual(expect.arrayContaining([
        { field: "total_with_tax", operator: "between", value: { min: "100", max: "200" } },
      ]));
    });

    await user.click(within(page).getByRole("button", { name: "筛选 开票日期" }));
    await user.type(await screen.findByLabelText("开票日期开始日期"), "2026-05-01");
    await user.type(screen.getByLabelText("开票日期结束日期"), "2026-05-31");
    await user.click(screen.getByRole("button", { name: "应用筛选" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      const filters = JSON.parse(decodeURIComponent(request?.searchParams.get("filters") ?? "[]"));
      expect(filters).toEqual(expect.arrayContaining([
        { field: "invoice_date", operator: "between", value: { min: "2026-05-01", max: "2026-05-31" } },
      ]));
    });

    await user.click(within(page).getByRole("button", { name: "下一页" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("page")).toBe("2");
    });
  }, 30000);

  test("opens the three right-side workflow drawers without reloading the main rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();
    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBe(1));
    expect(statusRulesRequests(fetchMock)).toHaveLength(0);

    await user.click(within(page).getByRole("button", { name: "收款状态规则" }));
    expect(await screen.findByLabelText("收款状态规则")).toBeInTheDocument();
    expect(await screen.findByText("收入流水金额小于销项发票金额")).toBeInTheDocument();
    expect(statusRulesRequests(fetchMock)).toHaveLength(1);
    expect(screen.queryByRole("button", { name: /保存|提交/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭收款状态规则" }));
    await user.click(within(page).getAllByRole("button", { name: "已出收据" })[0]);
    expect(await screen.findByLabelText("已出收据历史")).toBeInTheDocument();
    expect(await screen.findByText("SK2026050001")).toBeInTheDocument();
    expect(screen.queryByText("模拟收据")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "关闭已出收据历史" }));
    await user.click(within(page).getAllByRole("button", { name: "待出收据" })[0]);
    expect(await screen.findByLabelText("待出收据预览")).toBeInTheDocument();
    expect(await screen.findByText("收 据")).toBeInTheDocument();
    expect(screen.getByText(/人民币伍仟元整/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /生成正式收据|保存/ })).not.toBeInTheDocument();

    expect(rowsRequests(fetchMock).length).toBe(1);
  });

  test("closes lifecycle actions from drawers and exposes receipt settings only to admins", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();
    renderAuthenticatedAppAt("/output-invoice-collections", { session: { canAdminAccess: true } });

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(await within(page).findByRole("button", { name: "收据编号设置" })).toBeInTheDocument();

    await user.click(within(page).getAllByRole("button", { name: "状态/提醒" })[0]);
    expect(await screen.findByLabelText("收款状态和提醒")).toBeInTheDocument();
    expect(await screen.findByText("待冲红")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤销手动状态" }));
    await user.click(screen.getByRole("button", { name: "取消提醒" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/rows/output-collection-row-001/collection-status"),
        expect.objectContaining({ method: "PUT" }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/rows/output-collection-row-001/collection-reminder/reminder-001"),
        expect.objectContaining({ method: "DELETE" }),
      );
    });

    await user.click(screen.getByRole("button", { name: "关闭收款状态抽屉" }));
    await user.click(within(page).getAllByRole("button", { name: "红蓝票" })[0]);
    expect(await screen.findByLabelText("红蓝票关系")).toBeInTheDocument();
    expect(screen.getByText(/AUTO-RED/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("搜索关联发票"), "RED");
    await user.click(await screen.findByRole("radio", { name: /XSFP-2026-RED/ }));
    await user.type(screen.getByLabelText("确认依据"), "客户邮件确认红冲");
    await user.click(screen.getByRole("button", { name: "确认关系" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/rows/output-collection-row-001/red-invoice-relations"),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            relatedInvoiceId: "out-red-candidate",
            relatedInvoiceIdentityKey: "id:out-red-candidate",
            relationType: "red_invoice",
            evidence: "客户邮件确认红冲",
            confidence: "manual_confirmed",
          }),
        }),
      );
    });
    await user.click(within(page).getAllByRole("button", { name: "红蓝票" })[0]);
    await user.click(screen.getByRole("button", { name: "撤销人工关系 MANUAL-RED" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/red-invoice-relations/relation-manual-001"),
        expect.objectContaining({ method: "DELETE" }),
      );
    });

    await user.click(screen.getByRole("button", { name: "关闭红蓝票关系抽屉" }));
    await user.click(within(page).getAllByRole("button", { name: "已出收据" })[0]);
    expect(await screen.findByLabelText("已出收据历史")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "作废收据 SK2026050001" }));
    expect(await screen.findByLabelText("作废收据原因")).toBeInTheDocument();
    fireEvent.input(screen.getByLabelText("作废原因"), { target: { value: "客户要求重开抬头" } });
    await user.click(screen.getByRole("button", { name: "确认作废" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/receipts/receipt-issued-001/void"),
        expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "客户要求重开抬头" }) }),
      );
      expect(screen.queryByLabelText("作废收据原因")).not.toBeInTheDocument();
    });
    await user.click(await screen.findByRole("button", { name: "重开收据 SK2026050000" }, undefined, { timeout: 5_000 }));
    expect(await screen.findByLabelText("重开收据原因")).toBeInTheDocument();
    fireEvent.input(screen.getByLabelText("重开原因"), { target: { value: "作废后重新出具" } });
    await user.click(screen.getByRole("button", { name: "确认重开" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/receipts/receipt-voided-001/reissue"),
        expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "作废后重新出具" }) }),
      );
    });
    await waitFor(() => expect(screen.queryByLabelText("重开收据原因")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "关闭已出收据历史" }));
    await user.click(within(page).getByRole("button", { name: "收据编号设置" }));
    expect(await screen.findByLabelText("收据编号设置")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("编号前缀"));
    await user.type(screen.getByLabelText("编号前缀"), "SK");
    await user.click(screen.getByRole("button", { name: "保存收据编号设置" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/receipt-settings"),
        expect.objectContaining({ method: "PUT" }),
      );
    });
  }, 45000);
});
