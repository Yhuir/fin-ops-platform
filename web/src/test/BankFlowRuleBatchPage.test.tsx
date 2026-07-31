import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionAccessTier, SessionPayload } from "../features/session/api";
import BankFlowRuleBatchPage from "../pages/BankFlowRuleBatchPage";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const tagSelectionPayload = {
  version: 3,
  bank_auto_tag_rules_version: 7,
  active_tags: [
    { code: "fee", label: "手续费", output_primary_label: "费用", output_sub_label: "手续费", status: "active" },
    { code: "salary", label: "工资", output_primary_label: "人工成本", output_sub_label: "工资", status: "active" },
    { code: "holiday_bonus", label: "过节费", output_primary_label: "福利", output_sub_label: "过节费", status: "active" },
    { code: "internal_transfer", label: "内部往来款", output_primary_label: "往来", output_sub_label: "内部往来款", status: "active" },
    {
      code: "external_borrow_out",
      label: "借出款",
      output_primary_label: "外部往来款付款",
      output_sub_label: "借出款",
      output_third_label: "公司往来",
      category_third_label: "公司往来",
      turnover_family: "company",
      status: "active",
    },
    { code: "custom_no_sub", label: "其他免OA", output_primary_label: "其他免OA", output_sub_label: "", status: "active" },
  ],
  rules: [
    { tag_code: "fee", requires_oa: false, requires_invoice: false },
    { tag_code: "salary", requires_oa: false, requires_invoice: false },
    { tag_code: "holiday_bonus", requires_oa: false, requires_invoice: false },
    { tag_code: "internal_transfer", requires_oa: false, requires_invoice: false },
    { tag_code: "external_borrow_out", requires_oa: true, requires_invoice: true },
    { tag_code: "custom_no_sub", requires_oa: true, requires_invoice: true },
  ],
};

const listPayload = {
  summary: {
    draft_count: 3,
    submitted_count: 1,
    withdrawn_count: 1,
    conflict_count: 0,
    stale_count: 0,
    total_row_count: 18,
    draft_row_count: 9,
    submitted_row_count: 8,
    withdrawn_row_count: 1,
    total_amount: "26006.00",
    categories: [
      { code: "fee", label: "手续费", primary_label: "费用", sub_label: "手续费", total: 2, draft: 1, submitted: 0, withdrawn: 1, conflict: 0, stale: 0, total_row_count: 3, draft_row_count: 2, submitted_row_count: 0, withdrawn_row_count: 1, total_amount: "106.00" },
      { code: "salary", label: "工资", primary_label: "人工成本", sub_label: "工资", total: 1, draft: 0, submitted: 1, withdrawn: 0, conflict: 0, stale: 0, total_row_count: 8, draft_row_count: 0, submitted_row_count: 8, withdrawn_row_count: 0, total_amount: "20000.00" },
      { code: "holiday_bonus", label: "过节费", primary_label: "福利", sub_label: "过节费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_row_count: 5, draft_row_count: 5, submitted_row_count: 0, withdrawn_row_count: 0, total_amount: "5000.00" },
      { code: "internal_transfer", label: "内部往来款", primary_label: "往来", sub_label: "内部往来款", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_row_count: 2, draft_row_count: 2, submitted_row_count: 0, withdrawn_row_count: 0, total_amount: "1000.00" },
    ],
  },
  batches: [
    {
      batch_id: "batch-draft-fee",
      batch_type: "fee",
      batch_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
      scope_month: "2026-05",
      account_key: "ccb:8106",
      bank_name: "建设银行",
      account_last4: "8106",
      status: "draft",
      status_bucket: "unsubmitted",
      row_count: 2,
      total_amount: "88.00",
      tag_counts: { fee: 2 },
      direction_counts: { expense: 2 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
      version: 1,
    },
    {
      batch_id: "batch-draft-holiday",
      batch_type: "holiday_bonus",
      batch_label: "过节费",
      category_primary_label: "福利",
      category_sub_label: "过节费",
      category_label_path: ["福利", "过节费"],
      scope_month: "2026-05",
      account_key: "boc:7001",
      bank_name: "中国银行",
      account_last4: "7001",
      status: "draft",
      status_bucket: "unsubmitted",
      row_count: 5,
      total_amount: "5000.00",
      tag_counts: { holiday_bonus: 5 },
      direction_counts: { expense: 5 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
      version: 1,
    },
    {
      batch_id: "batch-submitted-salary",
      batch_type: "salary",
      batch_label: "工资",
      category_primary_label: "人工成本",
      category_sub_label: "工资",
      category_label_path: ["人工成本", "工资"],
      scope_month: "2026-05",
      account_key: "icbc:6386",
      bank_name: "工商银行",
      account_last4: "6386",
      status: "submitted",
      status_bucket: "submitted",
      row_count: 8,
      total_amount: "20000.00",
      tag_counts: { salary: 8 },
      direction_counts: { expense: 8 },
      can_submit: false,
      can_withdraw: true,
      submitted_by: "finance-user",
      submitted_at: "2026-05-10T09:30:00",
      version: 2,
    },
    {
      batch_id: "batch-conflict-transfer",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      category_primary_label: "往来",
      category_sub_label: "内部往来款",
      category_label_path: ["往来", "内部往来款"],
      scope_month: "2026-05",
      account_key: "",
      bank_name: "多账户",
      account_last4: "",
      status: "conflict",
      status_bucket: "unsubmitted",
      row_count: 3,
      total_amount: "30000.00",
      tag_counts: { internal_transfer: 3 },
      direction_counts: { income: 1, expense: 2 },
      conflict_reason: "内部往来存在多解，不能自动形成可提交批次。",
      can_submit: false,
      can_withdraw: false,
      blocked_reason: "内部往来存在多解，不能自动形成可提交批次。",
      version: 1,
    },
    {
      batch_id: "batch-draft-transfer",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      category_primary_label: "往来",
      category_sub_label: "内部往来款",
      category_label_path: ["往来", "内部往来款"],
      scope_month: "2026-05",
      account_key: "",
      bank_name: "多账户",
      account_last4: "",
      status: "draft",
      status_bucket: "unsubmitted",
      row_count: 2,
      total_amount: "1000.00",
      tag_counts: { internal_transfer: 2 },
      direction_counts: { income: 1, expense: 1 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
      version: 1,
    },
    {
      batch_id: "batch-withdrawn-fee",
      batch_type: "fee",
      batch_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
      scope_month: "2026-05",
      account_key: "ccb:8106",
      bank_name: "建设银行",
      account_last4: "8106",
      status: "withdrawn",
      status_bucket: "withdrawn",
      row_count: 1,
      total_amount: "18.00",
      tag_counts: { fee: 1 },
      direction_counts: { expense: 1 },
      can_submit: false,
      can_withdraw: false,
      withdrawn_by: "finance-user",
      withdrawn_at: "2026-05-11T10:30:00",
      version: 3,
    },
  ],
};

const feeDetailPayload = {
  batch: listPayload.batches[0],
  tag_counts: { fee: 1 },
  direction_counts: { expense: 1 },
  rows: [
    {
      transaction_id: "bank-row-001",
      trade_time: "2026-05-03 10:20:00",
      counterparty_name: "建设银行",
      direction: "expense",
      direction_label: "支",
      amount: "8.80",
      bank_name: "建设银行",
      account_last4: "8106",
      account_key: "ccb:8106",
      summary: "网银手续费",
      purpose: "结算",
      remark: "月结",
      category_code: "fee",
      category_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
      category_source: "auto",
    },
  ],
};

const conflictTransferDetailPayload = {
  batch: listPayload.batches[3],
  tag_counts: { internal_transfer: 3 },
  direction_counts: { income: 1, expense: 2 },
  rows: [
    {
      transaction_id: "transfer-row-occupied",
      trade_time: "2026-05-04 15:30:42",
      counterparty_name: "云南溯源科技有限公司",
      direction: "income",
      direction_label: "收",
      amount: "30000.00",
      bank_name: "光大银行",
      account_last4: "8826",
      account_key: "ceb:8826",
      summary: "本公司账户",
      purpose: "",
      remark: "",
      category_code: "internal_transfer",
      category_label: "内部往来款",
      category_primary_label: "往来",
      category_sub_label: "内部往来款",
      category_label_path: ["往来", "内部往来款"],
      category_source: "auto",
      relation_status: "linked",
      relation_case_ids: ["case-active-001"],
      linked_oa_count: 1,
      linked_invoice_count: 0,
    },
  ],
};

const bankFlowRuleBatchSourceFiles = [
  "src/pages/BankFlowRuleBatchPage.tsx",
  "src/features/bankFlowRuleBatches/components.tsx",
  "src/features/bankFlowRuleBatches/viewModel.ts",
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

const fullAccessSessionPayload: SessionPayload = {
  allowed: true,
  user: {
    userId: "test-user",
    username: "finance-user",
    nickname: "财务用户",
    displayName: "财务用户",
    deptId: "finance",
    deptName: "财务部",
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

function sessionValue(accessTier: SessionAccessTier = "full_access"): SessionContextValue {
  return {
    status: "authenticated",
    session: {
      ...fullAccessSessionPayload,
      accessTier,
      canMutateData: accessTier === "full_access" || accessTier === "admin",
      canAdminAccess: accessTier === "admin",
    },
    refresh: () => undefined,
  };
}

function renderPage(accessTier: SessionAccessTier = "full_access") {
  return render(
    <GlobalOperationOverlayProvider>
      <SessionContext.Provider value={sessionValue(accessTier)}>
        <PageRuntimeProvider value={{ pageKey: "bank-flow-rule-batches", active: true, activationGeneration: 0 }}>
          <BankFlowRuleBatchPage />
        </PageRuntimeProvider>
      </SessionContext.Provider>
    </GlobalOperationOverlayProvider>,
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

type MockBankFlowRuleBatch = {
  status?: string | null;
  status_bucket?: string | null;
  statusBucket?: string | null;
  can_withdraw?: boolean | null;
  canWithdraw?: boolean | null;
};

function batchesForBucket<T extends { batches: MockBankFlowRuleBatch[] }>(payload: T, bucket: string | null) {
  return bucket && bucket !== "all"
    ? payload.batches.filter((batch) => (batch.status_bucket ?? batch.statusBucket) === bucket)
    : payload.batches;
}

function positiveParam(params: URLSearchParams, name: string, fallback: number) {
  const value = Number(params.get(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function slicePage<T>(rows: T[], page: number, pageSize: number) {
  const start = (page - 1) * pageSize;
  return rows.slice(start, start + pageSize);
}

function withPagination<T extends { batches: MockBankFlowRuleBatch[] }>(payload: T, url: URL) {
  const filteredBatches = batchesForBucket(payload, url.searchParams.get("bucket")).filter((batch) => {
    const status = String(batch.status ?? "");
    const bucket = String(batch.status_bucket ?? batch.statusBucket ?? "");
    const canWithdraw = batch.can_withdraw === true || batch.canWithdraw === true;
    return status === "draft"
      || (status === "unsubmitted" && bucket === "unsubmitted")
      || status === "submitted"
      || status === "withdrawn"
      || (status === "stale" && (bucket === "submitted" || canWithdraw));
  });
  const page = positiveParam(url.searchParams, "page", 1);
  const pageSize = positiveParam(url.searchParams, "page_size", 200);
  return {
    ...payload,
    batches: slicePage(filteredBatches, page, pageSize),
    pagination: { page, page_size: pageSize, pageSize, total: filteredBatches.length },
  };
}

function largeListPayload(total = 205) {
  return {
    summary: {
      draft_count: total,
      submitted_count: 0,
      withdrawn_count: 0,
      conflict_count: 0,
      stale_count: 0,
      total_row_count: total,
      draft_row_count: total,
      submitted_row_count: 0,
      withdrawn_row_count: 0,
      total_amount: total.toFixed(2),
      categories: [
        { code: "fee", label: "手续费", primary_label: "费用", sub_label: "手续费", total, draft: total, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_row_count: total, draft_row_count: total, submitted_row_count: 0, withdrawn_row_count: 0, total_amount: total.toFixed(2) },
      ],
    },
    batches: Array.from({ length: total }, (_, index) => ({
      batch_id: `batch-large-${index.toString().padStart(3, "0")}`,
      batch_type: "fee",
      batch_label: "手续费",
      category_primary_label: "费用",
      category_sub_label: "手续费",
      category_label_path: ["费用", "手续费"],
      scope_month: "2026-05",
      account_key: `ccb:${index.toString().padStart(4, "0")}`,
      bank_name: "建设银行",
      account_last4: index.toString().padStart(4, "0"),
      status: "draft",
      status_bucket: "unsubmitted",
      row_count: 1,
      total_amount: "1.00",
      tag_counts: { fee: 1 },
      direction_counts: { expense: 1 },
      can_submit: true,
      can_withdraw: false,
      blocked_reason: "",
      version: 1,
    })),
  };
}

function installFetchMock(
  payload = listPayload,
  options: {
    listFailuresBeforeSuccess?: number;
    tagSelection?: Record<string, unknown>;
  } = {},
) {
  let listFailuresRemaining = options.listFailuresBeforeSuccess ?? 0;
  const tagSelection = options.tagSelection ?? tagSelectionPayload;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/bank-flow-rule-batches/tag-rules" && (!init?.method || init.method === "GET")) {
      return jsonResponse(tagSelection);
    }
    if (url.pathname === "/api/bank-flow-rule-batches/tag-rules" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body ?? "{}"));
      return jsonResponse({ ...tagSelection, version: 4, rules: body.rules ?? [] });
    }
    if (url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET")) {
      if (listFailuresRemaining > 0) {
        listFailuresRemaining -= 1;
        return jsonResponse({
          error: "no_oa_bank_batch_temporarily_unavailable",
          message: "流水规则批次加载暂时失败，请刷新后重试。",
        }, 503);
      }
      return jsonResponse(withPagination(payload, url));
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee") {
      return jsonResponse(feeDetailPayload);
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-holiday") {
      return jsonResponse({ batch: payload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-submitted-salary") {
      return jsonResponse({ batch: payload.batches[2], tag_counts: { salary: 8 }, direction_counts: { expense: 8 }, rows: [] });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-conflict-transfer") {
      return jsonResponse(conflictTransferDetailPayload);
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-transfer") {
      return jsonResponse({ batch: payload.batches[4], tag_counts: { internal_transfer: 2 }, direction_counts: { income: 1, expense: 1 }, rows: [] });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-withdrawn-fee") {
      return jsonResponse({ batch: payload.batches[5], tag_counts: { fee: 1 }, direction_counts: { expense: 1 }, rows: [] });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-transfer/submit") {
      return jsonResponse({
        batch: payload.batches[4],
        affected_months: ["2026-05"],
        results: [],
      });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/submit-selection") {
      return jsonResponse({
        batch: payload.batches[0],
        affected_months: ["2026-05"],
        results: [],
      });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/batch-submitted-salary/withdraw") {
      return jsonResponse({
        batch: payload.batches[2],
        affected_months: ["2026-05"],
        results: [],
      });
    }
    if (url.pathname === "/api/bank-flow-rule-batches/reset-submitted") {
      return jsonResponse({
        affected_months: ["2026-05"],
        results: [{ batch_id: "batch-submitted-salary", status: "withdrawn" }],
      });
    }
    if (url.pathname === "/api/operation-barrier/status") {
      return jsonResponse({ status: "fresh", fresh: true, targets: [], blocked_targets: [], refreshing_targets: [] });
    }
    return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function operationBarrierRequests(fetchMock: ReturnType<typeof installFetchMock>) {
  return fetchMock.mock.calls
    .filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/operation-barrier/status" && (init?.method ?? "GET").toUpperCase() === "POST";
    })
    .map(([, init]) => JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("BankFlowRuleBatchPage", () => {
  test("targets project primitives for page shell, rails, transaction table, overlays, and feedback", () => {
    const sourceByPath = Object.fromEntries(bankFlowRuleBatchSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = bankFlowRuleBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = bankFlowRuleBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = bankFlowRuleBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|(?<!App)Drawer\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton/.test(source)
        ? [path]
        : [];
    });
    const pageSource = sourceByPath["src/pages/BankFlowRuleBatchPage.tsx"];
    const primitiveSource = `${pageSource}\n${sourceByPath["src/features/bankFlowRuleBatches/components.tsx"]}`;
    const missingPrimitiveTargets = [
      pageSource.includes("PageScaffold") ? null : "BankFlowRuleBatchPage.tsx should keep PageScaffold",
      pageSource.includes("StatePanel") ? null : "BankFlowRuleBatchPage.tsx should keep StatePanel for loading/empty/error states",
      pageSource.includes("AppDrawer")
        ? null
        : "Tag management should use AppDrawer",
      /AppDialog|no-oa-bank-batch.*dialog|bank-flow-rule-batches.*dialog/.test(pageSource)
        ? null
        : "Withdraw confirmation should use AppDialog or a project dialog class",
      /finance-table|no-oa-bank-batch.*table|bank-flow-rule-batches.*table/.test(pageSource)
        ? null
        : "Transaction details should use a project dense table class",
      /no-oa-bank-batch.*rail|bank-flow-rule-batches.*rail/.test(primitiveSource)
        ? null
        : "Main and child label rails should use project rail classes",
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

  test("removes the legacy tag drawer shell after adopting AppDrawer", () => {
    const pageSource = readWebSource("src/pages/BankFlowRuleBatchPage.tsx");

    expect(pageSource).toContain('import AppDrawer from "../components/common/AppDrawer"');
    expect(pageSource).toContain('width="min(960px, 92vw)"');
    expect(pageSource).not.toContain("bank-flow-rule-batches-drawer-shell");
    expect(pageSource).not.toContain("bank-flow-rule-batches-drawer__close");
    expect(pageSource).not.toMatch(/<aside[^>]+bank-flow-rule-batches-drawer/);
  });

  test("keeps premium compact rails, transaction table, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const filterRule = cssRule(styles, ".bank-flow-rule-batches-filter");
    const buttonRule = cssRule(styles, ".bank-flow-rule-batches-button");
    const segmentRule = cssRule(styles, ".bank-flow-rule-batches-segment__button");
    const inputRule = cssRule(styles, ".bank-flow-rule-batches-field input");
    const railRule = cssRule(styles, ".bank-flow-rule-batches-rail");
    const railItemRule = cssRule(styles, ".bank-flow-rule-batches-rail__item");
    const transactionRule = cssRule(styles, ".bank-flow-rule-batches-transactions");
    const transactionListRule = cssRule(styles, ".bank-flow-rule-batches-transactions__list");
    const batchRule = cssRule(styles, ".bank-flow-rule-batches-batch");
    const selectedBatchRule = cssRule(styles, ".bank-flow-rule-batches-batch--selected");
    const tableWrapRule = cssRule(styles, ".bank-flow-rule-batches-table-wrap");
    const tableCellRule = cssRule(styles, ".bank-flow-rule-batches-table th,\\n.bank-flow-rule-batches-table td");
    const tableHeadRule = cssRule(styles, ".bank-flow-rule-batches-table th");
    const amountRule = cssRule(styles, ".bank-flow-rule-batches-table .bank-flow-rule-batches-table__amount");
    const tagRule = cssRule(styles, ".bank-flow-rule-batches-status,\\n.bank-flow-rule-batches-tag");
    const bankTagsRule = cssRule(styles, ".bank-flow-rule-batches-bank-tags,\\n.bank-flow-rule-batches-relation-cell");
    const bankDetailTagRule = cssRule(styles, ".bank-flow-rule-batches-tag--bank-detail");
    const drawerGridWrapRule = cssRule(styles, ".bank-flow-rule-batches-drawer__grid-wrap");
    const drawerGridRule = cssRule(styles, ".bank-flow-rule-batches-drawer__grid");
    const drawerDirectionColRule = cssRule(styles, ".bank-flow-rule-batches-drawer__direction-col");
    const drawerGridCellRule = cssRule(styles, ".bank-flow-rule-batches-drawer__grid th,\\n.bank-flow-rule-batches-drawer__grid td");
    const drawerCheckColRule = cssRule(styles, ".bank-flow-rule-batches-drawer__check-col");
    const textareaRule = cssRule(styles, ".bank-flow-rule-batches-dialog__field textarea");
    const paginationButtonRule = cssRule(styles, ".bank-flow-rule-batches-pagination__button");
    const toastRule = cssRule(styles, ".bank-flow-rule-batches-toast");
    const toastButtonRule = cssRule(styles, ".bank-flow-rule-batches-toast button");

    expect(filterRule).toContain("grid-template-columns");
    expect(filterRule).toContain("align-items: end");
    expect(buttonRule).toContain("var(--motion-fast)");
    expect(segmentRule).toContain("var(--motion-fast)");
    expect(inputRule).toContain("var(--motion-fast)");
    expect(railItemRule).toContain("var(--motion-fast)");
    expect(batchRule).toContain("var(--motion-fast)");
    expect(tableCellRule).toContain("var(--motion-fast)");
    expect(textareaRule).toContain("var(--motion-fast)");
    expect(paginationButtonRule).toContain("var(--motion-fast)");
    expect(toastButtonRule).toContain("var(--motion-fast)");

    expect(railRule).toContain("border-radius: var(--fp-radius-sm)");
    expect(transactionRule).toContain("border-radius: var(--fp-radius-sm)");
    expect(transactionListRule).toContain("max-height: calc(100vh - 214px)");
    expect(selectedBatchRule).toContain("inset 3px 0 0 var(--fp-primary)");
    expect(tableWrapRule).toContain("border-radius: var(--fp-radius-sm)");
    expect(tableHeadRule).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(amountRule).toContain("text-align: right");
    expect(tagRule).toContain("min-height: var(--fp-tag-height-table)");
    expect(tagRule).toContain("background: var(--fp-surface-muted)");
    expect(bankTagsRule).toContain("flex-wrap: wrap");
    expect(bankDetailTagRule).toContain("var(--fp-primary)");
    expect(drawerGridWrapRule).toContain("overflow: auto");
    expect(drawerGridRule).toContain("border-collapse: collapse");
    expect(drawerGridRule).toContain("min-width: 620px");
    expect(drawerDirectionColRule).toContain("width: 76px");
    expect(drawerGridCellRule).toContain("white-space: nowrap");
    expect(drawerCheckColRule).toContain("width: 64px");
    expect(paginationButtonRule).toContain("width: 30px");
    expect(paginationButtonRule).toContain("height: 30px");
    expect(toastRule).toContain("box-shadow: var(--fp-shadow-popover)");
    expect(tagRule).not.toContain("--fp-bg-muted");
    expect(toastRule).not.toContain("--fp-shadow-lg");
  });

  test("renders tag management and compact main/sub/transaction layout without account search or debug fields", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "流水规则批量处理" })).toBeInTheDocument();
    await waitFor(() => {
      const firstGet = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET");
      });
      expect(firstGet).toBeTruthy();
      const url = new URL(typeof firstGet?.[0] === "string" ? firstGet[0] : firstGet?.[0] instanceof URL ? firstGet[0].toString() : firstGet?.[0].url ?? "", "http://localhost");
      expect(url.searchParams.get("page")).toBe("1");
      expect(url.searchParams.get("page_size")).toBe("50");
    });
    expect(screen.getByRole("button", { name: "流水规则标签管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("月份")).toBeInTheDocument();
    expect(screen.queryByLabelText("银行账户")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("精确账户键，如 建设银行:8106")).not.toBeInTheDocument();

    const primaryRegion = screen.getByRole("region", { name: "主标签" });
    await waitFor(() => {
      expect(within(primaryRegion).getByRole("button", { name: "费用 1批 · 2条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByRole("group", { name: "流水规则批次分页" })).toHaveTextContent("1-3 / 3");
    expect(within(primaryRegion).getByRole("button", { name: "福利 1批 · 5条" })).toBeInTheDocument();
    expect(within(primaryRegion).queryByRole("button", { name: /外部往来款付款/ })).not.toBeInTheDocument();
    expect(within(primaryRegion).queryByRole("button", { name: /其他免OA/ })).not.toBeInTheDocument();

    const subRegion = screen.getByRole("region", { name: "子标签" });
    await waitFor(() => {
      expect(within(subRegion).getByRole("button", { name: "手续费 1批 · 2条" })).toHaveAttribute("aria-pressed", "true");
    });

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(within(transactionRegion).getByText("建设银行8106")).toBeInTheDocument();
    expect(await within(transactionRegion).findByText("网银手续费")).toBeInTheDocument();
    const detailGet = fetchMock.mock.calls.find(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee";
    });
    expect(detailGet).toBeTruthy();
    expect(new URL(String(detailGet?.[0]), "http://localhost").searchParams.get("scope_month")).toBe("2026-05");
    const bankTagGroup = within(transactionRegion).getByLabelText("银行明细标签 bank-row-001");
    expect(within(bankTagGroup).getByText("费用")).toBeInTheDocument();
    expect(within(bankTagGroup).getByText("手续费")).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "建设银行8106全选" })).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "选择流水 bank-row-001" })).toBeInTheDocument();
    expect(within(transactionRegion).queryByText("分类来源")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("自动")).not.toBeInTheDocument();
  });

  test("read-export users can view batches but cannot submit, withdraw, or save tag scope", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage("read_export_only");

    expect(await screen.findByRole("heading", { name: "流水规则批量处理" })).toBeInTheDocument();
    expect(screen.getByText("当前账号仅支持查看和导出，不能提交、撤回或保存流水规则批次。")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交批次" })).not.toBeInTheDocument();

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    const rowCheckbox = await within(transactionRegion).findByRole("checkbox", { name: "选择流水 bank-row-001" });
    expect(rowCheckbox).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "流水规则标签管理" }));
    const drawer = await screen.findByRole("dialog", { name: "流水规则标签管理" });
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).toBeDisabled();
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要发票" })).toBeDisabled();
    expect(within(drawer).getByRole("button", { name: "保存" })).toBeDisabled();

    expect(fetchMock.mock.calls.some(([, init]) => ["POST", "PUT", "PATCH", "DELETE"].includes(String(init?.method ?? "GET")))).toBe(false);
  });

  test("recovers after a transient bank flow rule batch list failure when refreshed", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock(listPayload, { listFailuresBeforeSuccess: 1 });
    renderPage();

    expect(await screen.findByRole("heading", { name: "流水规则批量处理" })).toBeInTheDocument();
    expect(await screen.findByText("流水规则批次加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    expect(screen.queryByText("当前标签下暂无流水")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "刷新" }));

    await waitFor(() => {
      expect(screen.queryByText("流水规则批次加载暂时失败，请刷新后重试。")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "未提交 3" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "费用 1批 · 2条" })).toBeInTheDocument();
    });
    expect(await screen.findByText("网银手续费")).toBeInTheDocument();

    const listRequests = fetchMock.mock.calls.filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET");
    });
    expect(listRequests.length).toBeGreaterThanOrEqual(2);
  });

  test("uses backend pagination for bank flow rule first-screen batches", async () => {
    const user = userEvent.setup();
    const payload = largeListPayload();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET")) {
        return jsonResponse(withPagination(payload, url));
      }
      const detailMatch = url.pathname.match(/^\/api\/bank-flow-rule-batches\/(batch-large-\d{3})$/);
      if (detailMatch) {
        const batch = payload.batches.find((item) => item.batch_id === detailMatch[1]) ?? payload.batches[0];
        return jsonResponse({
          batch,
          tag_counts: { fee: 1 },
          direction_counts: { expense: 1 },
          rows: [{
            transaction_id: `row-${batch.batch_id}`,
            trade_time: "2026-05-03 10:20:00",
            counterparty_name: "建设银行",
            direction: "expense",
            direction_label: "支",
            amount: "1.00",
            bank_name: batch.bank_name,
            account_last4: batch.account_last4,
            account_key: batch.account_key,
            summary: "网银手续费",
            purpose: "结算",
            remark: "月结",
            category_code: "fee",
            category_label: "手续费",
            category_primary_label: "费用",
            category_sub_label: "手续费",
            category_label_path: ["费用", "手续费"],
            category_source: "auto",
          }],
        });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await waitFor(() => {
      expect(within(screen.getByRole("group", { name: "流水规则批次分页" })).getByText("1-50 / 205")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "费用 205批 · 205条" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "手续费 205批 · 205条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByText("建设银行0000")).toBeInTheDocument();
    expect(screen.queryByText("建设银行0204")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "流水规则批次分页下一页" }));

    await waitFor(() => {
      expect(within(screen.getByRole("group", { name: "流水规则批次分页" })).getByText("51-100 / 205")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "费用 205批 · 205条" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "手续费 205批 · 205条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getAllByText("建设银行0050").length).toBeGreaterThan(0);
    expect(screen.queryByText("建设银行0000")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches"
        && url.searchParams.get("page") === "2"
        && url.searchParams.get("page_size") === "50";
    })).toBe(true);
  }, 30_000);

  test("hides exception batches while omitting default audit metadata", async () => {
    installFetchMock();
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "往来 1批 · 2条" }));

    expect(screen.queryByText("内部往来存在多解，不能自动形成可提交批次。")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "已提交 1" }));
    expect(await screen.findByText("人工成本")).toBeInTheDocument();
    expect(screen.queryByText(/提交人：finance-user/)).not.toBeInTheDocument();
    expect(screen.queryByText(/版本：2/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "历史 1" }));
    expect(await screen.findByText("费用")).toBeInTheDocument();
    expect(screen.queryByText(/撤回人：finance-user/)).not.toBeInTheDocument();
    expect(screen.queryByText(/版本：3/)).not.toBeInTheDocument();
  });

  test("clears hidden selected rows when changing label scope", async () => {
    installFetchMock();
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "福利 1批 · 5条" }));

    expect(screen.queryByText("已选 1 条")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交批次" })).toBeDisabled();
  });

  test("main and child label rails support keyboard activation", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    const welfareMain = await screen.findByRole("button", { name: "福利 1批 · 5条" });
    welfareMain.focus();
    await user.keyboard("{Enter}");

    const holidayChild = await screen.findByRole("button", { name: "过节费 1批 · 5条" });
    holidayChild.focus();
    await user.keyboard(" ");

    await waitFor(() => expect(holidayChild).toHaveAttribute("aria-pressed", "true"));
  });

  test("saves drawer tag requirement rules from compact grid", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "流水规则标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "流水规则标签管理" });
    expect(within(drawer).queryByText("版本 3")).not.toBeInTheDocument();
    expect(within(drawer).getByRole("columnheader", { name: "收支类型" })).toBeInTheDocument();
    expect(within(drawer).getByRole("columnheader", { name: "流水主标签" })).toBeInTheDocument();
    expect(within(drawer).getByRole("columnheader", { name: "流水子标签" })).toBeInTheDocument();
    expect(within(drawer).getByText("费用")).toBeInTheDocument();
    expect(within(drawer).getByText("手续费")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "全选" })).not.toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "清空" })).not.toBeInTheDocument();

    const feeRequiresOa = within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要OA" });
    const feeRequiresInvoice = within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要发票" });
    const salaryRequiresInvoice = within(drawer).getByRole("checkbox", { name: "人工成本 / 工资 需要发票" });
    expect(feeRequiresOa).not.toBeChecked();
    expect(feeRequiresInvoice).not.toBeChecked();
    await user.click(feeRequiresOa);
    await user.click(salaryRequiresInvoice);
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/tag-rules",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            expected_version: 3,
            rules: [
              { tag_code: "fee", requires_oa: true, requires_invoice: false },
              { tag_code: "salary", requires_oa: false, requires_invoice: true },
              { tag_code: "holiday_bonus", requires_oa: false, requires_invoice: false },
              { tag_code: "internal_transfer", requires_oa: false, requires_invoice: false },
              { tag_code: "external_borrow_out", requires_oa: true, requires_invoice: true },
              { tag_code: "custom_no_sub", requires_oa: true, requires_invoice: true },
            ],
          }),
        }),
      );
    });
    expect(operationBarrierRequests(fetchMock)).toHaveLength(0);
    expect(await screen.findByText("流水规则已保存")).toBeInTheDocument();
  });

  test("groups tag drawer direction and main label cells with shared main-label background", async () => {
    const user = userEvent.setup();
    installFetchMock(listPayload, {
      tagSelection: {
        ...tagSelectionPayload,
        active_tags: [
          { code: "fee", label: "手续费", direction: "支出", output_primary_label: "费用", output_sub_label: "手续费", status: "active" },
          { code: "repair_fee", label: "修理费", direction: "outflow", output_primary_label: "费用", output_sub_label: "修理费", status: "active" },
          { code: "salary", label: "工资", direction: "expense", output_primary_label: "人工成本", output_sub_label: "工资", status: "active" },
          { code: "project_income", label: "工程款收入", direction: "收入", output_primary_label: "工程款收入", output_sub_label: "", status: "active" },
        ],
        rules: [
          { tag_code: "fee", requires_oa: false, requires_invoice: false },
          { tag_code: "repair_fee", requires_oa: true, requires_invoice: true },
          { tag_code: "salary", requires_oa: false, requires_invoice: false },
          { tag_code: "project_income", requires_oa: false, requires_invoice: true },
        ],
      },
    });
    renderPage();

    await user.click(await screen.findByRole("button", { name: "流水规则标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "流水规则标签管理" });

    expect(within(drawer).getAllByText("支出")).toHaveLength(1);
    expect(within(drawer).getAllByText("收入")).toHaveLength(1);
    expect(within(drawer).getAllByText("费用")).toHaveLength(1);
    expect(within(drawer).getByText("支出").closest("td")).toHaveAttribute("rowspan", "3");
    expect(within(drawer).getByText("收入").closest("td")).toHaveAttribute("rowspan", "1");
    expect(within(drawer).getByText("费用").closest("td")).toHaveAttribute("rowspan", "2");

    const feeRow = within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要OA" }).closest("tr") as HTMLTableRowElement;
    const repairRow = within(drawer).getByRole("checkbox", { name: "费用 / 修理费 需要OA" }).closest("tr") as HTMLTableRowElement;
    const salaryRow = within(drawer).getByRole("checkbox", { name: "人工成本 / 工资 需要OA" }).closest("tr") as HTMLTableRowElement;
    const feeBackground = feeRow.style.getPropertyValue("--bank-flow-rule-batches-drawer-group-bg");

    expect(feeBackground).toBeTruthy();
    expect(repairRow.style.getPropertyValue("--bank-flow-rule-batches-drawer-group-bg")).toBe(feeBackground);
    expect(salaryRow.style.getPropertyValue("--bank-flow-rule-batches-drawer-group-bg")).not.toBe(feeBackground);
  });

  test("opening tag drawer refetches the latest bank flow rule tag selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await screen.findByText("网银手续费");
    const callsBeforeOpen = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches/tag-rules";
    }).length;

    await user.click(screen.getByRole("button", { name: "流水规则标签管理" }));

    await waitFor(() => {
      const callsAfterOpen = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches/tag-rules";
      }).length;
      expect(callsAfterOpen).toBeGreaterThan(callsBeforeOpen);
    });
  });

  test("does not update an open tag drawer from cross-page events", async () => {
    const user = userEvent.setup();
    let currentSelection = tagSelectionPayload;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules" && (!init?.method || init.method === "GET")) {
        return jsonResponse(currentSelection);
      }
      if (url.pathname === "/api/bank-flow-rule-batches") {
        return jsonResponse({ ...listPayload, batches: batchesForBucket(listPayload, url.searchParams.get("bucket")) });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "流水规则标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "流水规则标签管理" });
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).toBeInTheDocument();

    currentSelection = {
      ...tagSelectionPayload,
      bank_auto_tag_rules_version: 8,
      active_tags: tagSelectionPayload.active_tags.map((tag) => (
        tag.code === "fee"
          ? { ...tag, label: "银行手续费规则", output_primary_label: "银行费用", output_sub_label: "手续费自动规则" }
          : tag
      )),
    };
    act(() => {
      window.dispatchEvent(new CustomEvent("bankAutoTagRulesUpdated", { detail: { version: 8 } }));
    });

    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费 需要OA" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("checkbox", { name: "银行费用 / 手续费自动规则 需要OA" })).not.toBeInTheDocument();
  });

  test("drawer shows only bank auto rule main and child labels for external turnover tags", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "流水规则标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "流水规则标签管理" });

    expect(within(drawer).getByText("外部往来款付款")).toBeInTheDocument();
    expect(within(drawer).getByText("借出款")).toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: "外部往来款付款 / 借出款 需要OA" })).toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: "外部往来款付款 / 借出款 需要发票" })).toBeInTheDocument();
    expect(within(drawer).queryByText("个人往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("公司往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("银行往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("业务往来")).not.toBeInTheDocument();
  });

  test("submits only the selected transaction rows", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();
    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
    await user.click(screen.getByRole("button", { name: "提交批次" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/submit-selection",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
        }),
      );
    });
  });

  test("submits selected rows and reconciles through the current page GET without operation barrier", async () => {
    const user = userEvent.setup();
    const nextFeeBatch = {
      ...listPayload.batches[0],
      batch_id: "batch-draft-fee-next",
      account_key: "ceb:8826",
      bank_name: "光大银行",
      account_last4: "8826",
      total_amount: "44.00",
    };
    const payload = {
      ...listPayload,
      summary: {
        ...listPayload.summary,
        draft_count: 4,
        categories: listPayload.summary.categories.map((category) => (
          category.code === "fee"
            ? { ...category, total: 3, draft: 2, total_row_count: 5, draft_row_count: 4, total_amount: "150.00" }
            : category
        )),
      },
      batches: [listPayload.batches[0], nextFeeBatch, ...listPayload.batches.slice(1)],
    };
    let listRequestCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET")) {
        listRequestCount += 1;
        return jsonResponse(withPagination(payload, url));
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee-next") {
        return jsonResponse({ batch: nextFeeBatch, tag_counts: { fee: 1 }, direction_counts: { expense: 1 }, rows: [] });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/submit-selection") {
        return jsonResponse({
          batch: { ...listPayload.batches[0], status: "submitted", status_bucket: "submitted", version: 2 },
          affected_months: ["2026-05"],
          results: [{ batch_id: "batch-selected-fee", status: "submitted" }],
        });
      }
      if (url.pathname === "/api/operation-barrier/status") {
        throw new Error("bank flow mutation must not call operation barrier");
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
    const listRequestsBeforeSubmit = listRequestCount;
    await user.click(screen.getByRole("button", { name: "提交批次" }));

    expect(await screen.findByText("选中流水已提交")).toBeInTheDocument();
    await waitFor(() => {
      expect(listRequestCount).toBeGreaterThan(listRequestsBeforeSubmit);
    });
    expect(operationBarrierRequests(fetchMock)).toHaveLength(0);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee-next";
    })).toBe(false);
  });

  test("keeps draft row selection available when legacy read model rows omit can_submit", async () => {
    const legacyDraftBatch = { ...listPayload.batches[0] };
    delete (legacyDraftBatch as Partial<typeof legacyDraftBatch>).can_submit;
    const fetchMock = installFetchMock({
      ...listPayload,
      batches: [legacyDraftBatch, ...listPayload.batches.slice(1)],
    });
    const user = userEvent.setup();

    renderPage();

    const rowCheckbox = await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" });
    expect(rowCheckbox).toBeEnabled();

    await user.click(rowCheckbox);
    await user.click(screen.getByRole("button", { name: "提交批次" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/submit-selection",
        expect.objectContaining({
          body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
          method: "POST",
        }),
      );
    });
  });

  test("keeps ordinary unsubmitted rows selectable when legacy read model uses unsubmitted status", async () => {
    const legacyUnsubmittedBatch = {
      ...listPayload.batches[0],
      status: "unsubmitted",
      status_bucket: "unsubmitted",
    };
    const fetchMock = installFetchMock({
      ...listPayload,
      batches: [legacyUnsubmittedBatch, ...listPayload.batches.slice(1)],
    });
    const user = userEvent.setup();

    renderPage();

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    const rowCheckbox = await within(transactionRegion).findByRole("checkbox", { name: "选择流水 bank-row-001" });
    expect(rowCheckbox).toBeEnabled();

    await user.click(rowCheckbox);
    await user.click(screen.getByRole("button", { name: "提交批次" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/submit-selection",
        expect.objectContaining({
          body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
          method: "POST",
        }),
      );
    });
  });

  test("filters unsubmitted stale batches out of the main list", async () => {
    const staleUnsubmittedBatch = {
      ...listPayload.batches[0],
      bank_name: "",
      status: "stale",
      status_bucket: "unsubmitted",
      can_submit: false,
      blocked_reason: "源流水或分类已变化，需要复核后处理。",
    };
    installFetchMock({
      ...listPayload,
      summary: {
        ...listPayload.summary,
        draft_count: 1,
        stale_count: 1,
        categories: listPayload.summary.categories.map((category) => (
          category.code === "fee"
            ? { ...category, total: 1, draft: 0, total_row_count: 1, draft_row_count: 0 }
            : category
        )),
      },
      batches: [staleUnsubmittedBatch, ...listPayload.batches.slice(1)],
    });

    renderPage();

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    await within(transactionRegion).findByText("中国银行7001");
    expect(within(transactionRegion).queryByText("多账户8106")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("需复核")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("源流水或分类已变化，需要复核后处理。")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByRole("checkbox", { name: "选择流水 bank-row-001" })).not.toBeInTheDocument();
  });

  test("prevents selecting rows from another bank before clearing the current bank region", async () => {
    const secondFeeBatch = {
      ...listPayload.batches[0],
      batch_id: "batch-draft-fee-boc",
      account_key: "boc:7001",
      bank_name: "中国银行",
      account_last4: "7001",
      total_amount: "18.80",
    };
    const payload = {
      ...listPayload,
      batches: [listPayload.batches[0], secondFeeBatch],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches") {
        return jsonResponse({ ...payload, batches: batchesForBucket(payload, url.searchParams.get("bucket")) });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee-boc") {
        return jsonResponse({
          batch: secondFeeBatch,
          tag_counts: { fee: 1 },
          direction_counts: { expense: 1 },
          rows: [{ ...feeDetailPayload.rows[0], transaction_id: "bank-row-002", account_key: "boc:7001", bank_name: "中国银行", account_last4: "7001" }],
        });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/submit-selection") {
        return jsonResponse({ affected_case_ids: [], affected_months: ["2026-05"] });
      }
      if (url.pathname === "/api/operation-barrier/status") {
        return jsonResponse({ status: "fresh", fresh: true, targets: [], blocked_targets: [], refreshing_targets: [] });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
    await user.click(await screen.findByRole("button", { name: "查看中国银行7001流水" }));
    await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-002" }));

    expect(await screen.findByText("请先清空当前选择，再选择其他流水。")).toBeInTheDocument();
    expect(screen.getByText("已选 1 条")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择流水 bank-row-002" })).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "提交批次" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/submit-selection",
        expect.objectContaining({
          body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
          method: "POST",
        }),
      );
    });
  });

  test("switches to submitted bucket and withdraws a submitted batch", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "已提交 1" }));
    await user.click(await screen.findByRole("button", { name: "人工成本 1批 · 8条" }));
    await user.click(await screen.findByRole("button", { name: "工资 1批 · 8条" }));
    await user.click(await screen.findByRole("button", { name: "撤回批次" }));
    await user.type(screen.getByLabelText("撤回原因"), "金额复核");
    await user.click(screen.getByRole("button", { name: "确认撤回" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/batch-submitted-salary/withdraw",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ expected_version: 2, reason: "金额复核" }),
        }),
      );
    });
  });

  test("resets all submitted flow rule batches from the page", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "已提交 1" }));
    await user.click(await screen.findByRole("button", { name: "重置全部已提交" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/reset-submitted",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ reason: "流水规则批量处理：全部已提交批次重新过规则" }),
        }),
      );
    });
    expect(await screen.findByText("已重置 1 个已提交批次")).toBeInTheDocument();
    await waitFor(() => {
      const resetCallIndex = fetchMock.mock.calls.findIndex(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches/reset-submitted";
      });
      expect(resetCallIndex).toBeGreaterThanOrEqual(0);
      expect(fetchMock.mock.calls.slice(resetCallIndex + 1).some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches"
          && (!init?.method || init.method === "GET")
          && url.searchParams.get("bucket") === "unsubmitted"
          && url.searchParams.get("page") === "1";
      })).toBe(true);
    });
  });

  test("presents relation-backed stale batches as submitted without review prompts", async () => {
    const user = userEvent.setup();
    const payload = {
      ...listPayload,
      batches: listPayload.batches.map((batch) => (
        batch.batch_id === "batch-submitted-salary"
          ? {
            ...batch,
            status: "stale",
            status_bucket: "submitted",
            blocked_reason: "源流水或分类已变化，需要复核后处理。",
            can_submit: false,
            can_withdraw: true,
          }
          : batch
      )),
    };
    installFetchMock(payload);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "已提交 1" }));
    await user.click(await screen.findByRole("button", { name: "人工成本 1批 · 8条" }));
    await user.click(await screen.findByRole("button", { name: "工资 1批 · 8条" }));

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(within(transactionRegion).getByText("已提交")).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("button", { name: "撤回批次" })).toBeInTheDocument();
    expect(within(transactionRegion).queryByText("需复核")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("分类已变更，需复核")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("源流水或分类已变化，需要复核后处理。")).not.toBeInTheDocument();
  });

  test("shows withdrawn history as read-only", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "历史 1" }));
    await user.click(await screen.findByRole("button", { name: "费用 1批 · 1条" }));
    await user.click(await screen.findByRole("button", { name: "手续费 1批 · 1条" }));

    expect(await screen.findByText("1 条 · 合计 18.00")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "提交批次" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "撤回批次" })).not.toBeInTheDocument();
  });

  test("submits internal transfer draft batches through the batch endpoint", async () => {
    const user = userEvent.setup();
    const nextTransferBatch = {
      ...listPayload.batches[4],
      batch_id: "batch-draft-transfer-next",
      account_key: "ceb:8826",
      bank_name: "光大银行",
      account_last4: "8826",
      total_amount: "2000.00",
    };
    const payloadWithNextTransfer = {
      ...listPayload,
      summary: {
        ...listPayload.summary,
        draft_count: 4,
        categories: listPayload.summary.categories.map((category) => (
          category.code === "internal_transfer"
            ? { ...category, total: 2, draft: 2, total_row_count: 4, draft_row_count: 4, total_amount: "3000.00" }
            : category
        )),
      },
      batches: [...listPayload.batches, nextTransferBatch],
    };
    const fetchMock = installFetchMock(payloadWithNextTransfer);
    renderPage();
    await user.click(await screen.findByRole("button", { name: "往来 2批 · 4条" }));
    await user.click(await screen.findByRole("button", { name: "内部往来款 2批 · 4条" }));
    await user.click((await screen.findAllByRole("button", { name: "提交内部往来批次" }))[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/bank-flow-rule-batches/batch-draft-transfer/submit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({ expected_version: 1, scope_month: "2026-05", note: "" }),
        }),
      );
    });
    await waitFor(() => {
      expect(screen.queryByText("正在加载流水明细")).not.toBeInTheDocument();
    });
    await waitFor(() => {
      const submitCallIndex = fetchMock.mock.calls.findIndex(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches/batch-draft-transfer/submit";
      });
      expect(submitCallIndex).toBeGreaterThanOrEqual(0);
      expect(fetchMock.mock.calls.slice(submitCallIndex + 1).some(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET");
      })).toBe(true);
    });
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/bank-flow-rule-batches/batch-draft-transfer-next";
    })).toBe(false);
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/bank-flow-rule-batches/submit-selection",
      expect.anything(),
    );
    expect(operationBarrierRequests(fetchMock)).toHaveLength(0);
  });

  test("does not render eligible tag labels with no live candidate", async () => {
    installFetchMock(listPayload, {
      tagSelection: {
        ...tagSelectionPayload,
        active_tags: [
          ...tagSelectionPayload.active_tags,
          {
            code: "ghost_live_candidate",
            label: "幽灵候选",
            output_primary_label: "幽灵分组",
            output_sub_label: "幽灵候选",
            status: "active",
          },
        ],
        rules: [
          ...tagSelectionPayload.rules,
          {
            tag_code: "ghost_live_candidate",
            requires_oa: false,
            requires_invoice: false,
          },
        ],
      },
    });

    renderPage();

    await screen.findByText("网银手续费");
    expect(screen.queryByRole("button", { name: /幽灵分组/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /幽灵候选/ })).not.toBeInTheDocument();
  });

  test("does not expose internal transfer conflicts in the main list", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "往来 1批 · 2条" }));
    await user.click(await screen.findByRole("button", { name: "内部往来款 1批 · 2条" }));

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(await within(transactionRegion).findByText("多账户")).toBeInTheDocument();
    expect(within(transactionRegion).queryByText("内部往来存在多解，不能自动形成可提交批次。")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("云南溯源科技有限公司")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("关联 case-active-001")).not.toBeInTheDocument();
  });

  test("loads the canonical list once without background polling", async () => {
    let listCallCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/bank-flow-rule-batches/tag-rules") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches" && (!init?.method || init.method === "GET")) {
        listCallCount += 1;
        return jsonResponse({
          ...listPayload,
          batches: batchesForBucket(listPayload, url.searchParams.get("bucket")),
        });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-draft-holiday") {
        return jsonResponse({ batch: listPayload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
      }
      if (url.pathname === "/api/bank-flow-rule-batches/batch-conflict-transfer") {
        return jsonResponse({ batch: listPayload.batches[3], tag_counts: { internal_transfer: 3 }, direction_counts: { income: 1, expense: 2 }, rows: [] });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByRole("heading", { name: "流水规则批量处理" })).toBeInTheDocument();
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 1_100));
    });
    expect(listCallCount).toBe(1);
  });

  test("sidebar exposes the bank flow rule batch entry", () => {
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];

    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "流水规则批量处理",
          to: "/bank-flow-rule-batches",
        }),
      ]),
    );
    });
  });

  test("rejects an internal transfer candidate without a month scope", async () => {
    const user = userEvent.setup();
    const payloadWithoutScope = {
      ...listPayload,
      batches: listPayload.batches.map((batch) => (
        batch.batch_id === "batch-draft-transfer"
          ? { ...batch, scope_month: undefined }
          : batch
      )),
    };
    const fetchMock = installFetchMock(payloadWithoutScope);
    renderPage();
    await user.click(await screen.findByRole("button", { name: "往来 1批 · 2条" }));
    await user.click(await screen.findByRole("button", { name: "内部往来款 1批 · 2条" }));
    await user.click(await screen.findByRole("button", { name: "提交内部往来批次" }));

    expect(await screen.findByText("流水规则候选月份缺失，请刷新列表后重试")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input, init]) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url,
        "http://localhost",
      );
      return url.pathname.endsWith("/submit") && init?.method === "POST";
    })).toBe(false);
  });
