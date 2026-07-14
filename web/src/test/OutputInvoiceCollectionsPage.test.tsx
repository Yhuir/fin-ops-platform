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
  "src/components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer.tsx",
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
      oa: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
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
      invoiceRelations: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
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
      oa: {
        relationCount: 0,
        hasMultiple: false,
        detailMode: "none",
        summaries: [],
      },
      bankTransactions: {
        primaryBankTransactionId: "bank-output-candidate-001",
        counterpartyName: "候选回款客户",
        tradeTime: "2026-05-05 11:20:00",
        amount: "12345.67",
        direction: "inflow",
        directionLabel: "收入",
        bankName: "建设银行",
        accountLast4: "8106",
        summary: "候选回款流水",
        remark: "",
        relationCount: 1,
        relationStatus: "candidate",
        relationCaseId: "candidate:output-bank-001",
        hasMultiple: false,
        detailMode: "single",
        summaries: [
          {
            bankTransactionId: "bank-output-candidate-001",
            counterpartyName: "候选回款客户",
            tradeTime: "2026-05-05 11:20:00",
            amount: "12345.67",
            direction: "inflow",
            directionLabel: "收入",
            bankName: "建设银行",
            accountLast4: "8106",
            summary: "候选回款流水",
            remark: "",
            relationStatus: "candidate",
            relationCaseId: "candidate:output-bank-001",
          },
        ],
      },
      invoiceRelations: {
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
  summary: {
    invoiceCount: 20,
    totalWithTax: "0.00",
    collectedAmount: "5000.00",
    pendingAmount: "7345.67",
    pendingCollectionCount: 1,
    partialCollectionCount: 1,
    receiptPendingCount: 1,
  },
  filterConfig: [],
  readModelStatus: "fresh",
  generatedAt: "2026-05-24T00:00:00Z",
  sourceVersion: "output-invoice-collections:v1",
};

function installOutputInvoiceCollectionsFetch(options: { operationBarrierDelay?: Promise<void>; rowsPayloadOverride?: unknown | ((url: URL) => unknown) } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/output-invoice-collections/rows") {
      const override = options.rowsPayloadOverride;
      return jsonResponse(typeof override === "function" ? override(url) : override ?? rowsPayload);
    }
    if (
      url.pathname === "/api/operations/app-health/page-audit"
      && url.searchParams.get("page") === "output-invoice-collections"
    ) {
      return jsonResponse({
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: {
          database_snapshot: true,
          snapshot_consistency: "repeatable_read_read_only",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v9",
        },
        summary: {
          blocking_issue_sample_count: 0,
          issue_sample_count: 0,
        },
        issues: [],
      });
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
          bankTransactionId: "bank-001",
          canCreateFormalReceipt: true,
        },
      });
    }
    if (url.pathname === "/api/output-invoice-collections/invoices/out-001/detail") {
      return jsonResponse({
        id: "out-001",
        invoiceNo: "0001",
        buyerName: "云南客户科技有限公司",
        sourceLinks: { invoiceId: "out-001", relationCaseId: "case-hidden" },
      });
    }
    if (url.pathname === "/api/output-invoice-collections/bank-transactions/bank-001/detail") {
      return jsonResponse({ id: "bank-001", counterpartyName: "云南客户科技有限公司", amount: "5000.00" });
    }
    if (url.pathname.startsWith("/api/output-invoice-collections/rows/") && url.pathname.endsWith("/relation-details")) {
      const kind = url.searchParams.get("kind") ?? "bank";
      const invoiceSummaries = [
        { invoiceId: "out-primary", digitalInvoiceNo: "XSFP-MULTI-PRIMARY", buyerName: "多发票客户", totalWithTax: "300.00", relationCaseId: "case-hidden-primary" },
        { invoiceId: "out-related-a", invoiceNo: "XSFP-MULTI-A", buyerName: "多发票客户", totalWithTax: "100.00", relationCaseId: "case-hidden-a" },
        { invoiceId: "out-related-b", invoiceNo: "XSFP-MULTI-B", buyerName: "多发票客户", totalWithTax: "200.00", relationCaseId: "case-hidden-b" },
      ];
      return jsonResponse({
        rowId: url.pathname.split("/")[4],
        invoiceId: "out-001",
        kind,
        detailAvailable: true,
        relationCount: kind === "invoice" ? 3 : 2,
        hasMultiple: true,
        sourceAvailable: true,
        summaries: kind === "invoice" ? invoiceSummaries : [
          kind === "oa"
            ? { oaId: "oa-output-a", applicantName: "OA申请人甲", amount: "100.00" }
            : { bankTransactionId: "bank-output-a", counterpartyName: "多流水客户", amount: "100.00" },
          kind === "oa"
            ? { oaId: "oa-output-b", applicantName: "OA申请人乙", amount: "200.00" }
            : { bankTransactionId: "bank-output-b", counterpartyName: "多流水客户", amount: "200.00" },
        ],
        relations: [{ caseId: "case-output-multi", rowIds: ["oa-output-a", "bank-output-a", "out-related-a"] }],
      });
    }
    if (url.pathname === "/api/output-invoice-collections/receipt-settings") {
      if (init?.method === "PUT") {
        return jsonResponse({ settings: { prefix: "SK", resetPeriod: "monthly", version: 2 } });
      }
      return jsonResponse({ settings: { prefix: "SK", resetPeriod: "monthly", version: 1 } });
    }
    if (url.pathname === "/api/operation-barrier/status") {
      await options.operationBarrierDelay;
      return jsonResponse({
        status: "fresh",
        fresh: true,
        targets: [
          {
            read_model_key: "output_invoice_collection",
            scope_type: "output_invoice_collection",
            scope_key: "all",
            status: "fresh",
            fresh: true,
            blocking: false,
            raw_status: "fresh",
          },
        ],
        blocked_targets: [],
        refreshing_targets: [],
      });
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
      return jsonResponse({
        ok: true,
        read_model_scope_keys: ["2026-05"],
        freshness_targets: [{ read_model_key: "output_invoice_collection", scope_key: "2026-05" }],
      });
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

function operationBarrierRequests(fetchMock: ReturnType<typeof installOutputInvoiceCollectionsFetch>) {
  return fetchMock.mock.calls.filter(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/operation-barrier/status";
  });
}

function statusRulesRequests(fetchMock: ReturnType<typeof installOutputInvoiceCollectionsFetch>) {
  return fetchMock.mock.calls
    .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
    .filter((url) => url.pathname === "/api/output-invoice-collections/status-rules");
}

function deferred<T = void>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
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
      sourceByPath["src/components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer.tsx"].includes("AppDrawer") ? null : "Export drawer should use AppDrawer",
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
    const queryMonthTrigger = cssRule(styles, ".output-invoice-collections-field .month-picker-trigger");
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
    const detailDrawerHeader = cssRule(styles, ".output-invoice-collection-drawer .finance-drawer__header");
    const detailDrawerTitle = cssRule(styles, ".output-invoice-collection-drawer .finance-drawer__title");
    const detailDrawerBody = cssRule(styles, ".output-invoice-collection-drawer .finance-drawer__body");
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
    expect(queryMonthTrigger).toContain("min-height: 34px");
    expect(tableShell).toContain("min-height: 640px");
    expect(tableShell).toContain("max-height: calc(200vh - 428px)");
    expect(table).toContain("min-width: 1240px");
    expect(table).not.toContain("min-width: 1680px");
    expect(tableCells).toContain("transition: background-color var(--motion-fast)");
    expect(tableAction).toContain("var(--motion-fast)");
    expect(tableActionIcon).toContain("width: 26px");
    expect(tableActionIcon).toContain("padding: 0");
    expect(sortButton).toContain("var(--motion-fast)");
    expect(paginationButton).toContain("var(--motion-fast)");
    expect(detailDrawerHeader).toContain("padding: 10px var(--fp-space-4)");
    expect(detailDrawerTitle).toContain("font-size: var(--fp-text-subtitle)");
    expect(detailDrawerBody).toContain("padding: var(--fp-space-3) var(--fp-space-4)");
    expect(drawerButton).toContain("var(--motion-fast)");
    expect(drawerFields).toContain("var(--motion-fast)");
    expect(groupInvoice).toContain("color-mix(in srgb, var(--fp-success-soft)");
    expect(groupStatus).toContain("color-mix(in srgb, var(--fp-warning-soft)");
    expect(groupBank).toContain("color-mix(in srgb, var(--fp-primary-soft)");
    expect(groupReceipt).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(outputGroupRules).not.toMatch(/#f6fbf8|#f5f9ff|#f8fafc|#fbfdfc|#f1faff|#f8fbff|#fbfcfd|rgba\(14,\s*165,\s*233,\s*0\.10\)/);
  });

  test("shows a refreshing state instead of a true empty state while read model details stay hidden", async () => {
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
    expect(await within(page).findByText("销项发票收款情况数据正在刷新")).toBeInTheDocument();
    expect(within(page).getByText("当前数据仍在刷新或等待后台任务完成，请稍后重试。")).toBeInTheDocument();
    expect(within(page).queryByText("当前条件下暂无记录。")).not.toBeInTheDocument();
    expect(within(page).queryByText("销项发票收款情况读模型正在刷新，完成后页面会自动重新加载。")).not.toBeInTheDocument();
  });

  test("treats stale filter options as non-fresh instead of showing a fresh empty state", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/output-invoice-collections/rows") {
        return jsonResponse({
          rows: [],
          pagination: { page: 1, pageSize: 20, total: 0 },
          filterConfig: [],
          read_model_status: "fresh",
          readModelStatus: "fresh",
        });
      }
      if (url.pathname === "/api/output-invoice-collections/filter-options") {
        return jsonResponse({ fields: [], read_model_status: "stale", readModelStatus: "stale" }, 202);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    expect(await within(page).findByText("销项发票收款情况数据正在刷新")).toBeInTheDocument();
    expect(within(page).queryByText("当前条件下暂无记录。")).not.toBeInTheDocument();
    expect(within(page).queryByText("当前条件下没有销项发票收款记录。")).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
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
    expect(await within(page).findByText("销项发票收款情况数据正在刷新")).toBeInTheDocument();
    expect(within(page).queryByText("当前条件下暂无记录。")).not.toBeInTheDocument();
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

  test("keeps title invoice count stable when filters change", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch({
      rowsPayloadOverride: (url) => {
        const filtered = Boolean(url.searchParams.get("keyword"));
        return {
          ...rowsPayload,
          pagination: { ...rowsPayload.pagination, total: filtered ? 6 : 20 },
          summary: { ...rowsPayload.summary, invoiceCount: filtered ? 6 : 20 },
        };
      },
    });

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    expect(within(page).getByLabelText("销项发票数量统计")).toHaveTextContent("销项票 20");

    await user.type(within(page).getByLabelText("搜索销项发票收款情况"), "已收");
    await user.click(within(page).getByRole("button", { name: "查询" }));
    await waitFor(() => expect(rowsRequests(fetchMock).some((url) => url.searchParams.get("keyword") === "已收")).toBe(true));
    expect(within(page).getByLabelText("销项发票数量统计")).toHaveTextContent("销项票 20");
  });

  test("admin can run title audit icon and see data relation freshness result", async () => {
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch();

    renderAuthenticatedAppAt("/output-invoice-collections", { session: { canAdminAccess: true } });

    const page = await screen.findByTestId("output-invoice-collections-page");
    const auditButton = await within(page).findByRole("button", { name: "Audit 销项发票收款情况" });
    await user.click(auditButton);

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/api/operations/app-health/page-audit?page=output-invoice-collections"))).toBe(true);
    });
    const status = await within(page).findByText(/Audit 通过/);
    expect(status).toHaveTextContent("已登记 App 内部合同一致");
    expect(status).toHaveTextContent("已登记配对证明一致");
    expect(status).toHaveTextContent("Fresh");
  });

  test("adds sidebar route and renders grouped project table layout with real export entry", async () => {
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
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(0));
    const initialRowsRequest = rowsRequests(fetchMock)[0];
    expect(initialRowsRequest.searchParams.get("page")).toBe("1");
    expect(initialRowsRequest.searchParams.get("page_size")).toBe("20");
    expect(initialRowsRequest.searchParams.get("month")).toBeNull();
    expect(within(page).getByRole("heading", { name: "销项发票收款情况" })).toBeInTheDocument();
    expect(within(page).getByLabelText("销项发票数量统计")).toHaveTextContent("销项票 20");
    expect(within(page).getByRole("button", { name: "销项发票月份" })).toHaveTextContent("全部发票");
    expect(within(page).queryByText("以销项发票为主对象查看收款状态、收入流水和收据预览。")).not.toBeInTheDocument();
    const refreshButton = within(page).getByRole("button", { name: "刷新" });
    expect(refreshButton).toBeInTheDocument();
    expect(within(page).queryByText("关键字")).not.toBeInTheDocument();
    expect(within(page).queryByLabelText("收款状态")).not.toBeInTheDocument();
    for (const label of ["销项发票数", "待收款金额", "已收金额", "待出收据数"]) {
      expect(within(page).queryByText(label)).not.toBeInTheDocument();
    }
    expect(within(page).getByRole("button", { name: "筛选内容导出" })).toBeInTheDocument();
    expect(Array.from((within(page).getByLabelText("每页行数") as HTMLSelectElement).options).map((option) => option.value)).toEqual(["20", "50", "100"]);
    expect(await within(page).findByText("XSFP-2026-0001")).toBeInTheDocument();
    expect(statusRulesRequests(fetchMock)).toHaveLength(0);

    const rowsBeforeRefresh = rowsRequests(fetchMock).length;
    await user.click(refreshButton);
    await waitFor(() => expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeRefresh));

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
    await user.click(within(page).getByRole("button", { name: "销项发票月份" }));
    await user.click(await screen.findByRole("radio", { name: "2026" }));
    await user.click(screen.getByRole("radio", { name: "五月" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("month")).toBe("2026-05");
    });
    expect(within(page).getByRole("button", { name: "销项发票月份" })).toHaveTextContent("2026年5月");

    await user.click(within(page).getByRole("button", { name: "销项发票月份" }));
    await user.click(await screen.findByRole("radio", { name: "全部发票" }));
    await waitFor(() => {
      const request = rowsRequests(fetchMock).at(-1);
      expect(request?.searchParams.get("month")).toBeNull();
    });
    expect(within(page).getByRole("button", { name: "销项发票月份" })).toHaveTextContent("全部发票");

    expect(within(page).getByRole("table", { name: "销项发票收款情况表" })).toBeInTheDocument();

    const headerRows = within(page).getAllByRole("row").slice(0, 2);
    for (const label of ["销项发票", "收款状态", "OA", "收入流水", "收据"]) {
      expect(within(headerRows[0]).getByRole("columnheader", { name: label })).toBeInTheDocument();
    }
    for (const label of [
      "发票号码",
      "购方",
      "价税合计",
      "业务/货物劳务",
      "收款状态",
      "OA申请人",
      "项目名称",
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
    expect(within(page).getAllByText("建设银行 8106").length).toBeGreaterThan(0);
    expect(
      within(page).getAllByText("待收款，已收部分款")
        .some((element) => element.closest(".output-invoice-collection-status-cell")),
    ).toBe(true);
    const candidateCollectionRow = bodyRows.find((row) => within(row).queryByText("XSFP-2026-RED"));
    expect(candidateCollectionRow).toBeDefined();
    expect(within(candidateCollectionRow as HTMLElement).getByText("候选回款客户")).toBeInTheDocument();
    expect(within(candidateCollectionRow as HTMLElement).queryByText("候选")).not.toBeInTheDocument();
    expect(within(candidateCollectionRow as HTMLElement).getByText("待收款")).toBeInTheDocument();
    expect(within(page).queryByText("存在收入流水，但收入流水合计小于发票价税合计。")).not.toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看发票 XSFP-2026-0001 详情" })).toBeInTheDocument();
    expect(within(page).getByRole("button", { name: "查看流水 云南客户科技有限公司 详情" })).toBeInTheDocument();
    expect(within(page).queryByRole("button", { name: "详情" })).not.toBeInTheDocument();
    expect(within(page).getAllByRole("button", { name: "已出收据" }).length).toBeGreaterThan(0);
    expect(within(page).getAllByRole("button", { name: "待出收据" }).length).toBeGreaterThan(0);

    await user.click(within(page).getByRole("button", { name: "查看发票 XSFP-2026-0001 详情" }));
    expect(await screen.findByRole("heading", { name: "销项发票详情" })).toBeInTheDocument();
    expect(screen.getByText("购买方名称")).toBeInTheDocument();
    expect(screen.getAllByText("云南客户科技有限公司").length).toBeGreaterThan(0);
    expect(screen.queryByText("out-001")).not.toBeInTheDocument();
    expect(screen.queryByText("invoiceId")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "销项发票详情" })).not.toBeInTheDocument());

    await user.click(within(page).getByRole("button", { name: "查看流水 云南客户科技有限公司 详情" }));
    expect(await screen.findByRole("heading", { name: "流水详情" })).toBeInTheDocument();
    expect(screen.getByText("对方户名")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "流水详情" })).not.toBeInTheDocument());

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

  test("shows invoice aggregate with +N entry point for multi output invoice relations", async () => {
    const user = userEvent.setup();
    const multiRowsPayload = {
      ...rowsPayload,
      rows: [
        {
          ...rowsPayload.rows[0],
          id: "output-collection-row-multi",
          invoice: {
            ...rowsPayload.rows[0].invoice,
            displayNo: "XSFP-MULTI-PRIMARY",
            invoiceNo: "MULTI-PRIMARY",
            buyerName: "多发票客户",
            taxableItemName: "多发票服务",
          },
          oa: {
            primaryOaId: "oa-output-a",
            applicantName: "OA申请人甲",
            applicationType: "付款申请",
            projectName: "OA项目甲",
            amount: "300.00",
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              { oaId: "oa-output-a", applicantName: "OA申请人甲", applicationType: "付款申请", projectName: "OA项目甲", amount: "100.00" },
              { oaId: "oa-output-b", applicantName: "OA申请人乙", applicationType: "付款申请", projectName: "OA项目乙", amount: "200.00" },
            ],
          },
          bankTransactions: {
            primaryBankTransactionId: "bank-output-a",
            counterpartyName: "多流水客户",
            tradeTime: "2026-05-03 10:30:00",
            amount: "100.00",
            receivedTotal: "300.00",
            direction: "inflow",
            directionLabel: "收入",
            bankName: "建设银行",
            accountLast4: "8106",
            summary: "多流水摘要甲",
            remark: "",
            relationCount: 2,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              { bankTransactionId: "bank-output-a", counterpartyName: "多流水客户", amount: "100.00", direction: "inflow", directionLabel: "收入" },
              { bankTransactionId: "bank-output-b", counterpartyName: "多流水客户", amount: "200.00", direction: "inflow", directionLabel: "收入" },
            ],
          },
          invoiceRelations: {
            primaryInvoiceId: "out-primary",
            invoiceNo: "MULTI-PRIMARY",
            digitalInvoiceNo: "XSFP-MULTI-PRIMARY",
            buyerName: "多发票客户",
            totalWithTax: "600.00",
            taxableItemName: "多发票服务",
            relationCount: 3,
            hasMultiple: true,
            detailMode: "list",
            summaries: [
              { invoiceId: "out-primary", digitalInvoiceNo: "XSFP-MULTI-PRIMARY", buyerName: "多发票客户", totalWithTax: "300.00" },
              { invoiceId: "out-related-a", invoiceNo: "XSFP-MULTI-A", buyerName: "多发票客户", totalWithTax: "100.00" },
              { invoiceId: "out-related-b", invoiceNo: "XSFP-MULTI-B", buyerName: "多发票客户", totalWithTax: "200.00" },
            ],
          },
        },
      ],
      pagination: { page: 1, pageSize: 20, total: 1 },
    };
    const fetchMock = installOutputInvoiceCollectionsFetch({ rowsPayloadOverride: multiRowsPayload });

    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    await within(page).findByRole("table", { name: "销项发票收款情况表" });
    expect(within(page).getByRole("button", { name: "查看关联发票 3 张" })).toHaveTextContent("+2");
    expect(within(page).getByRole("button", { name: "查看关联OA 2 条" })).toHaveTextContent("+1");
    expect(within(page).getByRole("button", { name: "查看关联流水 2 条" })).toHaveTextContent("+1");
    expect(within(page).getByText("XSFP-MULTI-PRIMARY")).toBeInTheDocument();
    expect(within(page).getByText("600.00")).toBeInTheDocument();
    expect(within(page).getByText("3 张合计")).toBeInTheDocument();
    expect(within(page).getByText("多发票客户")).toBeInTheDocument();
    expect(within(page).queryByText("OA申请人甲")).not.toBeInTheDocument();
    expect(within(page).queryByText("多流水摘要甲")).not.toBeInTheDocument();

    await user.click(within(page).getByRole("button", { name: "查看关联OA 2 条" }));
    expect(await screen.findByRole("heading", { name: "OA详情" })).toBeInTheDocument();
    expect(screen.getByText("申请 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看关联流水 2 条" }));
    expect(await screen.findByRole("heading", { name: "流水详情" })).toBeInTheDocument();
    expect(screen.getByText("流水 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "关闭详情抽屉" }));

    await user.click(within(page).getByRole("button", { name: "查看关联发票 3 张" }));
    expect(await screen.findByRole("heading", { name: "销项发票详情" })).toBeInTheDocument();
    expect(screen.getByText("发票 1")).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText(/XSFP-MULTI-PRIMARY/).length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText(/XSFP-MULTI-A/)).toBeInTheDocument();
    expect(screen.getByText(/XSFP-MULTI-B/)).toBeInTheDocument();
    expect(screen.getAllByText("购买方").length).toBeGreaterThan(0);
    expect(screen.getAllByText("多发票客户").length).toBeGreaterThan(0);
    expect(screen.queryByText("invoiceId")).not.toBeInTheDocument();
    expect(screen.queryByText("buyerName")).not.toBeInTheDocument();
    expect(screen.queryByText("relationCaseId")).not.toBeInTheDocument();
    expect(screen.queryByText("case-output-multi")).not.toBeInTheDocument();
    expect(screen.queryByText(/"buyerName"/)).not.toBeInTheDocument();

    const relationRequests = fetchMock.mock.calls
      .map(([input]) => new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost"))
      .filter((url) => url.pathname === "/api/output-invoice-collections/rows/output-collection-row-multi/relation-details");
    expect(relationRequests.map((url) => url.searchParams.get("kind"))).toEqual(["oa", "bank", "invoice"]);
  });

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

  test("waits for output invoice collection barrier before reloading after red relation confirm", async () => {
    const barrier = deferred();
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch({ operationBarrierDelay: barrier.promise });
    renderAuthenticatedAppAt("/output-invoice-collections");

    const page = await screen.findByTestId("output-invoice-collections-page");
    await within(page).findByText("XSFP-2026-0001");
    await user.click(within(page).getAllByRole("button", { name: "红蓝票" })[0]);
    expect(await screen.findByLabelText("红蓝票关系")).toBeInTheDocument();
    await user.type(screen.getByLabelText("搜索关联发票"), "RED");
    await user.click(await screen.findByRole("radio", { name: /XSFP-2026-RED/ }));
    await user.type(screen.getByLabelText("确认依据"), "客户邮件确认红冲");
    const rowsBeforeMutation = rowsRequests(fetchMock).length;

    await user.click(screen.getByRole("button", { name: "确认关系" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/rows/output-collection-row-001/red-invoice-relations"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => expect(operationBarrierRequests(fetchMock)).toHaveLength(1));
    const [, barrierInit] = operationBarrierRequests(fetchMock)[0];
    expect(JSON.parse(String(barrierInit?.body))).toEqual({
      targets: [{ read_model_key: "output_invoice_collection", scope_key: "2026-05" }],
    });
    expect(rowsRequests(fetchMock)).toHaveLength(rowsBeforeMutation);

    barrier.resolve();

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeMutation);
    });
  }, 45000);

  test("waits for output invoice collection barrier target returned by receipt creation", async () => {
    const barrier = deferred();
    const user = userEvent.setup();
    const fetchMock = installOutputInvoiceCollectionsFetch({ operationBarrierDelay: barrier.promise });
    renderAuthenticatedAppAt("/output-invoice-collections", { session: { canAdminAccess: true } });

    const page = await screen.findByTestId("output-invoice-collections-page");
    await within(page).findByText("XSFP-2026-0001");
    await user.click(within(page).getAllByRole("button", { name: "待出收据" })[0]);
    expect(await screen.findByLabelText("待出收据预览")).toBeInTheDocument();
    const rowsBeforeMutation = rowsRequests(fetchMock).length;

    await user.click(screen.getByRole("button", { name: "创建正式收据" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/api/output-invoice-collections/rows/output-collection-row-001/receipts"),
        expect.objectContaining({ method: "POST" }),
      );
    });
    await waitFor(() => expect(operationBarrierRequests(fetchMock)).toHaveLength(1));
    const [, barrierInit] = operationBarrierRequests(fetchMock)[0];
    expect(JSON.parse(String(barrierInit?.body))).toEqual({
      targets: [{ read_model_key: "output_invoice_collection", scope_key: "2026-05" }],
    });
    expect(rowsRequests(fetchMock)).toHaveLength(rowsBeforeMutation);

    barrier.resolve();

    await waitFor(() => {
      expect(rowsRequests(fetchMock).length).toBeGreaterThan(rowsBeforeMutation);
    });
  }, 45000);
});
