import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { PageRuntimeProvider } from "../contexts/PageRuntimeContext";
import NoOaBankBatchPage from "../pages/NoOaBankBatchPage";
import { expectCustomEventDetailContaining } from "./eventAssertions";
import { renderAuthenticatedAppAt } from "./renderHelpers";

const tagSelectionPayload = {
  version: 3,
  bank_auto_tag_rules_version: 7,
  selected_tag_codes: ["fee", "salary", "holiday_bonus", "internal_transfer"],
  inactive_selected_tag_codes: [],
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
};

const listPayload = {
  summary: {
    draft_count: 2,
    submitted_count: 1,
    withdrawn_count: 1,
    conflict_count: 1,
    stale_count: 0,
    total_amount: "20106.00",
    categories: [
      { code: "fee", label: "手续费", primary_label: "费用", sub_label: "手续费", total: 2, draft: 1, submitted: 0, withdrawn: 1, conflict: 0, stale: 0, total_amount: "106.00" },
      { code: "salary", label: "工资", primary_label: "人工成本", sub_label: "工资", total: 1, draft: 0, submitted: 1, withdrawn: 0, conflict: 0, stale: 0, total_amount: "20000.00" },
      { code: "holiday_bonus", label: "过节费", primary_label: "福利", sub_label: "过节费", total: 1, draft: 1, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: "5000.00" },
      { code: "internal_transfer", label: "内部往来款", primary_label: "往来", sub_label: "内部往来款", total: 1, draft: 0, submitted: 0, withdrawn: 0, conflict: 1, stale: 0, total_amount: "30000.00" },
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

const noOaBankBatchSourceFiles = [
  "src/pages/NoOaBankBatchPage.tsx",
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

function renderPage() {
  return render(
    <GlobalOperationOverlayProvider>
      <PageRuntimeProvider value={{ pageKey: "no-oa-bank-batches", active: true, activationGeneration: 0 }}>
        <NoOaBankBatchPage />
      </PageRuntimeProvider>
    </GlobalOperationOverlayProvider>,
  );
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function batchesForBucket<T extends { batches: Array<{ status_bucket?: string | null; statusBucket?: string | null }> }>(payload: T, bucket: string | null) {
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

function withPagination<T extends { batches: Array<{ status_bucket?: string | null; statusBucket?: string | null }> }>(payload: T, url: URL) {
  const filteredBatches = batchesForBucket(payload, url.searchParams.get("bucket"));
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
      total_amount: total.toFixed(2),
      categories: [
        { code: "fee", label: "手续费", primary_label: "费用", sub_label: "手续费", total, draft: total, submitted: 0, withdrawn: 0, conflict: 0, stale: 0, total_amount: total.toFixed(2) },
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

function installFetchMock(payload = listPayload) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && (!init?.method || init.method === "GET")) {
      return jsonResponse(tagSelectionPayload);
    }
    if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && init?.method === "PUT") {
      const body = JSON.parse(String(init.body ?? "{}"));
      return jsonResponse({ ...tagSelectionPayload, version: 4, selected_tag_codes: body.selected_tag_codes ?? [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
      return jsonResponse(withPagination(payload, url));
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
      return jsonResponse(feeDetailPayload);
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-holiday") {
      return jsonResponse({ batch: payload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-submitted-salary") {
      return jsonResponse({ batch: payload.batches[2], tag_counts: { salary: 8 }, direction_counts: { expense: 8 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-conflict-transfer") {
      return jsonResponse(conflictTransferDetailPayload);
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-transfer") {
      return jsonResponse({ batch: payload.batches[4], tag_counts: { internal_transfer: 2 }, direction_counts: { income: 1, expense: 1 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-withdrawn-fee") {
      return jsonResponse({ batch: payload.batches[5], tag_counts: { fee: 1 }, direction_counts: { expense: 1 }, rows: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-draft-transfer/submit") {
      return jsonResponse({ batch: payload.batches[4], affected_months: ["2026-05"], workbench_rebuild_queued: true, results: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/submit-selection") {
      return jsonResponse({ batch: payload.batches[0], affected_months: ["2026-05"], workbench_rebuild_queued: true, results: [] });
    }
    if (url.pathname === "/api/no-oa-bank-batches/batch-submitted-salary/withdraw") {
      return jsonResponse({ batch: payload.batches[2], affected_months: ["2026-05"], workbench_rebuild_queued: true, results: [] });
    }
    if (url.pathname === "/api/operation-barrier/status") {
      return jsonResponse({ status: "fresh", fresh: true, targets: [], blocked_targets: [], refreshing_targets: [] });
    }
    return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("NoOaBankBatchPage", () => {
  test("targets project primitives for page shell, rails, transaction table, overlays, and feedback", () => {
    const sourceByPath = Object.fromEntries(noOaBankBatchSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = noOaBankBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = noOaBankBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = noOaBankBatchSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /RefreshOutlinedIcon|CloseIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|Drawer\b|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton/.test(source)
        ? [path]
        : [];
    });
    const pageSource = sourceByPath["src/pages/NoOaBankBatchPage.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("PageScaffold") ? null : "NoOaBankBatchPage.tsx should keep PageScaffold",
      pageSource.includes("StatePanel") ? null : "NoOaBankBatchPage.tsx should keep StatePanel for loading/empty/error states",
      /AppDrawer|no-oa-bank-batch.*drawer|no-oa-bank-batches.*drawer/.test(pageSource)
        ? null
        : "Tag management should use AppDrawer or a project drawer class",
      /AppDialog|no-oa-bank-batch.*dialog|no-oa-bank-batches.*dialog/.test(pageSource)
        ? null
        : "Withdraw confirmation should use AppDialog or a project dialog class",
      /finance-table|no-oa-bank-batch.*table|no-oa-bank-batches.*table/.test(pageSource)
        ? null
        : "Transaction details should use a project dense table class",
      /no-oa-bank-batch.*rail|no-oa-bank-batches.*rail/.test(pageSource)
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

  test("keeps premium compact rails, transaction table, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const filterRule = cssRule(styles, ".no-oa-bank-batches-filter");
    const buttonRule = cssRule(styles, ".no-oa-bank-batches-button");
    const segmentRule = cssRule(styles, ".no-oa-bank-batches-segment__button");
    const inputRule = cssRule(styles, ".no-oa-bank-batches-field input");
    const railRule = cssRule(styles, ".no-oa-bank-batches-rail");
    const railItemRule = cssRule(styles, ".no-oa-bank-batches-rail__item");
    const transactionRule = cssRule(styles, ".no-oa-bank-batches-transactions");
    const transactionListRule = cssRule(styles, ".no-oa-bank-batches-transactions__list");
    const batchRule = cssRule(styles, ".no-oa-bank-batches-batch");
    const selectedBatchRule = cssRule(styles, ".no-oa-bank-batches-batch--selected");
    const tableWrapRule = cssRule(styles, ".no-oa-bank-batches-table-wrap");
    const tableCellRule = cssRule(styles, ".no-oa-bank-batches-table th,\\n.no-oa-bank-batches-table td");
    const tableHeadRule = cssRule(styles, ".no-oa-bank-batches-table th");
    const amountRule = cssRule(styles, ".no-oa-bank-batches-table .no-oa-bank-batches-table__amount");
    const tagRule = cssRule(styles, ".no-oa-bank-batches-status,\\n.no-oa-bank-batches-tag");
    const drawerRule = cssRule(styles, ".no-oa-bank-batches-drawer");
    const drawerGroupsRule = cssRule(styles, ".no-oa-bank-batches-drawer__groups");
    const drawerCloseRule = cssRule(styles, ".no-oa-bank-batches-drawer__close");
    const textareaRule = cssRule(styles, ".no-oa-bank-batches-dialog__field textarea");
    const paginationButtonRule = cssRule(styles, ".no-oa-bank-batches-pagination__button");
    const toastRule = cssRule(styles, ".no-oa-bank-batches-toast");
    const toastButtonRule = cssRule(styles, ".no-oa-bank-batches-toast button");

    expect(filterRule).toContain("grid-template-columns");
    expect(filterRule).toContain("align-items: end");
    expect(buttonRule).toContain("var(--motion-fast)");
    expect(segmentRule).toContain("var(--motion-fast)");
    expect(inputRule).toContain("var(--motion-fast)");
    expect(railItemRule).toContain("var(--motion-fast)");
    expect(batchRule).toContain("var(--motion-fast)");
    expect(tableCellRule).toContain("var(--motion-fast)");
    expect(drawerCloseRule).toContain("var(--motion-fast)");
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
    expect(drawerRule).toContain("min(960px, 92vw)");
    expect(drawerRule).toContain("box-shadow: var(--fp-shadow-drawer)");
    expect(drawerGroupsRule).toContain("repeat(auto-fit, minmax(260px, 1fr))");
    expect(paginationButtonRule).toContain("width: 30px");
    expect(paginationButtonRule).toContain("height: 30px");
    expect(toastRule).toContain("box-shadow: var(--fp-shadow-popover)");
    expect(tagRule).not.toContain("--fp-bg-muted");
    expect(drawerRule).not.toContain("--fp-shadow-lg");
    expect(toastRule).not.toContain("--fp-shadow-lg");
  });

  test("renders tag management and compact main/sub/transaction layout without account search or debug fields", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    await waitFor(() => {
      const firstGet = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET");
      });
      expect(firstGet).toBeTruthy();
      const url = new URL(typeof firstGet?.[0] === "string" ? firstGet[0] : firstGet?.[0] instanceof URL ? firstGet[0].toString() : firstGet?.[0].url ?? "", "http://localhost");
      expect(url.searchParams.get("page")).toBe("1");
      expect(url.searchParams.get("page_size")).toBe("200");
    });
    expect(screen.getByRole("button", { name: "免OA流水标签管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 3" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.getByLabelText("月份")).toBeInTheDocument();
    expect(screen.queryByLabelText("银行账户")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("精确账户键，如 建设银行:8106")).not.toBeInTheDocument();

    const primaryRegion = screen.getByRole("region", { name: "主标签" });
    await waitFor(() => {
      expect(within(primaryRegion).getByRole("button", { name: "费用 1批 · 2条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByRole("group", { name: "免OA批次分页" })).toHaveTextContent("1-4 / 4");
    expect(within(primaryRegion).getByRole("button", { name: "福利 1批 · 5条" })).toBeInTheDocument();

    const subRegion = screen.getByRole("region", { name: "子标签" });
    await waitFor(() => {
      expect(within(subRegion).getByRole("button", { name: "手续费 1批 · 2条" })).toHaveAttribute("aria-pressed", "true");
    });

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(within(transactionRegion).getByText("建设银行8106")).toBeInTheDocument();
    expect(await within(transactionRegion).findByText("网银手续费")).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "建设银行8106全选" })).toBeInTheDocument();
    expect(within(transactionRegion).getByRole("checkbox", { name: "选择流水 bank-row-001" })).toBeInTheDocument();
    expect(within(transactionRegion).queryByText("分类来源")).not.toBeInTheDocument();
    expect(within(transactionRegion).queryByText("自动")).not.toBeInTheDocument();
  });

  test("uses backend pagination for no OA first-screen batches", async () => {
    const user = userEvent.setup();
    const payload = largeListPayload();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        return jsonResponse(withPagination(payload, url));
      }
      const detailMatch = url.pathname.match(/^\/api\/no-oa-bank-batches\/(batch-large-\d{3})$/);
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
      expect(within(screen.getByRole("group", { name: "免OA批次分页" })).getByText("1-200 / 205")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "费用 200批 · 200条" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "手续费 200批 · 200条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getByText("建设银行0000")).toBeInTheDocument();
    expect(screen.queryByText("建设银行0204")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "免OA批次分页下一页" }));

    await waitFor(() => {
      expect(within(screen.getByRole("group", { name: "免OA批次分页" })).getByText("201-205 / 205")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "费用 5批 · 5条" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("button", { name: "手续费 5批 · 5条" })).toHaveAttribute("aria-pressed", "true");
    });
    expect(screen.getAllByText("建设银行0200").length).toBeGreaterThan(0);
    expect(screen.queryByText("建设银行0000")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/no-oa-bank-batches"
        && url.searchParams.get("page") === "2"
        && url.searchParams.get("page_size") === "200";
    })).toBe(true);
  });

  test("shows batch blocking reasons without default audit metadata", async () => {
    installFetchMock();
    renderPage();
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "往来 2批 · 5条" }));

    expect(await screen.findByText("内部往来存在多解，不能自动形成可提交批次。")).toBeInTheDocument();

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

  test("saves drawer tag selection with main and child tag toggles", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "免OA流水标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "免OA流水标签管理" });
    expect(within(drawer).queryByText("版本 3")).not.toBeInTheDocument();
    await user.click(within(drawer).getByRole("button", { name: "清空" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用" })).not.toBeChecked();
    await user.click(within(drawer).getByRole("checkbox", { name: "费用" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" })).toBeChecked();
    await user.click(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" }));
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" })).not.toBeChecked();
    await user.click(within(drawer).getByRole("button", { name: "全选" }));
    await user.click(within(drawer).getByRole("button", { name: "保存" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/no-oa-bank-batches/tag-selection",
        expect.objectContaining({
          method: "PUT",
          body: JSON.stringify({
            expected_version: 3,
            selected_tag_codes: ["fee", "salary", "holiday_bonus", "internal_transfer", "external_borrow_out", "custom_no_sub"],
          }),
        }),
      );
    });
    expect(await screen.findByText("免OA流水标签范围已保存")).toBeInTheDocument();
  });

  test("opening tag drawer refetches the latest no OA tag selection", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    await screen.findByText("网银手续费");
    const callsBeforeOpen = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/no-oa-bank-batches/tag-selection";
    }).length;

    await user.click(screen.getByRole("button", { name: "免OA流水标签管理" }));

    await waitFor(() => {
      const callsAfterOpen = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/tag-selection";
      }).length;
      expect(callsAfterOpen).toBeGreaterThan(callsBeforeOpen);
    });
  });

  test("updates open tag drawer labels after bank auto tag rules change", async () => {
    const user = userEvent.setup();
    let currentSelection = tagSelectionPayload;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection" && (!init?.method || init.method === "GET")) {
        return jsonResponse(currentSelection);
      }
      if (url.pathname === "/api/no-oa-bank-batches") {
        return jsonResponse({ ...listPayload, batches: batchesForBucket(listPayload, url.searchParams.get("bucket")) });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderPage();

    await user.click(await screen.findByRole("button", { name: "免OA流水标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "免OA流水标签管理" });
    expect(within(drawer).getByRole("checkbox", { name: "费用 / 手续费" })).toBeInTheDocument();

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

    expect(await within(drawer).findByRole("checkbox", { name: "银行费用 / 手续费自动规则" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("checkbox", { name: "费用 / 手续费" })).not.toBeInTheDocument();
  });

  test("drawer shows only bank auto rule main and child labels for external turnover tags", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "免OA流水标签管理" }));
    const drawer = screen.getByRole("dialog", { name: "免OA流水标签管理" });

    expect(within(drawer).getByRole("checkbox", { name: "外部往来款付款" })).toBeInTheDocument();
    expect(within(drawer).getByRole("checkbox", { name: "外部往来款付款 / 借出款" })).toBeInTheDocument();
    expect(within(drawer).queryByText("个人往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("公司往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("银行往来")).not.toBeInTheDocument();
    expect(within(drawer).queryByText("业务往来")).not.toBeInTheDocument();
  });

  test("submits only the selected transaction rows and dispatches affected months", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("checkbox", { name: "选择流水 bank-row-001" }));
      await user.click(screen.getByRole("button", { name: "提交批次" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/submit-selection",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ transaction_ids: ["bank-row-001"], note: "" }),
          }),
        );
      });
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
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
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches") {
        return jsonResponse({ ...payload, batches: batchesForBucket(payload, url.searchParams.get("bucket")) });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee-boc") {
        return jsonResponse({
          batch: secondFeeBatch,
          tag_counts: { fee: 1 },
          direction_counts: { expense: 1 },
          rows: [{ ...feeDetailPayload.rows[0], transaction_id: "bank-row-002", account_key: "boc:7001", bank_name: "中国银行", account_last4: "7001" }],
        });
      }
      if (url.pathname === "/api/no-oa-bank-batches/submit-selection") {
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
        "/api/no-oa-bank-batches/submit-selection",
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
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "已提交 1" }));
      await user.click(await screen.findByRole("button", { name: "人工成本 1批 · 8条" }));
      await user.click(await screen.findByRole("button", { name: "工资 1批 · 8条" }));
      await user.click(await screen.findByRole("button", { name: "撤回批次" }));
      await user.type(screen.getByLabelText("撤回原因"), "金额复核");
      await user.click(screen.getByRole("button", { name: "确认撤回" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/batch-submitted-salary/withdraw",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ expected_version: 2, reason: "金额复核" }),
          }),
        );
      });
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
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
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();
      await user.click(await screen.findByRole("button", { name: "往来 2批 · 5条" }));
      await user.click(await screen.findByRole("button", { name: "内部往来款 2批 · 5条" }));
      await user.click(await screen.findByRole("button", { name: "提交内部往来批次" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/no-oa-bank-batches/batch-draft-transfer/submit",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ expected_version: 1, note: "" }),
          }),
        );
      });
      expect(fetchMock).not.toHaveBeenCalledWith(
        "/api/no-oa-bank-batches/submit-selection",
        expect.anything(),
      );
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-05"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("shows relation context for internal transfer conflicts", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "往来 2批 · 5条" }));
    await user.click(await screen.findByRole("button", { name: "内部往来款 2批 · 5条" }));

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(await within(transactionRegion).findByText("内部往来存在多解，不能自动形成可提交批次。")).toBeInTheDocument();
    expect(await within(transactionRegion).findByText("云南溯源科技有限公司")).toBeInTheDocument();
    expect(within(transactionRegion).getByText("关联 case-active-001")).toBeInTheDocument();
    expect(within(transactionRegion).getByText("OA 1")).toBeInTheDocument();
    expect(within(transactionRegion).getByText("发票 0")).toBeInTheDocument();
  });

  test("refreshes tag selection, list, and detail cache after bank transaction category updates", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    await screen.findByText("网银手续费");
    const initialDetailCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
    }).length;

    act(() => {
      window.dispatchEvent(new CustomEvent("bankTransactionCategoryUpdated", { detail: { affectedMonths: ["2026-05"] } }));
    });

    await waitFor(() => {
      const tagSelectionCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/tag-selection";
      });
      expect(tagSelectionCalls.length).toBeGreaterThan(1);
    });
    await waitFor(() => {
      const detailCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
      });
      expect(detailCalls.length).toBeGreaterThan(initialDetailCalls);
    });
  });

  test("refreshes tag selection, list, and detail cache after bank auto tag rules update", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    await screen.findByText("网银手续费");
    const initialDetailCalls = fetchMock.mock.calls.filter(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
    }).length;

    act(() => {
      window.dispatchEvent(new CustomEvent("bankAutoTagRulesUpdated", { detail: { version: 8 } }));
    });

    await waitFor(() => {
      const tagSelectionCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/tag-selection";
      });
      expect(tagSelectionCalls.length).toBeGreaterThan(1);
    });
    await waitFor(() => {
      const detailCalls = fetchMock.mock.calls.filter(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/no-oa-bank-batches/batch-draft-fee";
      });
      expect(detailCalls.length).toBeGreaterThan(initialDetailCalls);
    });
  });

  test("shows read model stale state and reloads until the no OA read model is fresh", async () => {
    let listCallCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        listCallCount += 1;
        return jsonResponse({
          ...listPayload,
          batches: batchesForBucket(listPayload, url.searchParams.get("bucket")),
          read_model_status: listCallCount === 1 ? "stale" : "fresh",
          read_model_stale_reasons: listCallCount === 1 ? ["bank_auto_tag_rules_version_mismatch"] : [],
        });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-holiday") {
        return jsonResponse({ batch: listPayload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-conflict-transfer") {
        return jsonResponse({ batch: listPayload.batches[3], tag_counts: { internal_transfer: 3 }, direction_counts: { income: 1, expense: 2 }, rows: [] });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    expect(screen.queryByText("免OA流水读模型待刷新，已显示当前可用数据。")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(listCallCount).toBeGreaterThan(1);
    }, { timeout: 2500 });
    await waitFor(() => {
      expect(screen.queryByText("免OA流水读模型待刷新，已显示当前可用数据。")).not.toBeInTheDocument();
    });
  });

  test("cleans up stale read model retry reload after route unmount", async () => {
    let listCallCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        listCallCount += 1;
        return jsonResponse({
          ...listPayload,
          batches: batchesForBucket(listPayload, url.searchParams.get("bucket")),
          read_model_status: "stale",
          read_model_stale_reasons: ["bank_auto_tag_rules_version_mismatch"],
        });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      return jsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    renderAuthenticatedAppAt("/no-oa-bank-batches");

    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();
    await waitFor(() => {
      expect(listCallCount).toBe(1);
    });

    fireEvent.click(screen.getByRole("link", { name: "设置" }));
    expect(await screen.findByTestId("settings-page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "免OA流水批量处理" })).not.toBeInTheDocument();
    vi.useFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(listCallCount).toBe(1);

    vi.useRealTimers();
    fireEvent.click(screen.getByRole("link", { name: "免OA流水批量处理" }));
    expect(await screen.findByRole("heading", { name: "免OA流水批量处理" })).toBeInTheDocument();

    expect(listCallCount).toBeGreaterThan(1);
  });

  test("keeps visible transaction rows while stale read model polling runs in the background", async () => {
    let listCallCount = 0;
    const secondListStarted = vi.fn();
    let resolveSecondList: ((response: Response) => void) | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/no-oa-bank-batches/tag-selection") {
        return jsonResponse(tagSelectionPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches" && (!init?.method || init.method === "GET")) {
        listCallCount += 1;
        if (listCallCount === 1) {
          return jsonResponse({
            ...listPayload,
            batches: batchesForBucket(listPayload, url.searchParams.get("bucket")),
            read_model_status: "stale",
            read_model_stale_reasons: ["bank_auto_tag_rules_version_mismatch"],
          });
        }
        secondListStarted();
        return new Promise<Response>((resolve) => {
          resolveSecondList = resolve;
        });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-fee") {
        return jsonResponse(feeDetailPayload);
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-draft-holiday") {
        return jsonResponse({ batch: listPayload.batches[1], tag_counts: { holiday_bonus: 5 }, direction_counts: { expense: 5 }, rows: [] });
      }
      if (url.pathname === "/api/no-oa-bank-batches/batch-conflict-transfer") {
        return jsonResponse({ batch: listPayload.batches[3], tag_counts: { internal_transfer: 3 }, direction_counts: { income: 1, expense: 2 }, rows: [] });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    const transactionRegion = screen.getByRole("region", { name: "流水" });
    expect(await within(transactionRegion).findByText("网银手续费")).toBeInTheDocument();

    await waitFor(() => {
      expect(secondListStarted).toHaveBeenCalled();
    }, { timeout: 2500 });

    expect(within(transactionRegion).queryByText("流水加载中")).not.toBeInTheDocument();
    expect(within(transactionRegion).getByText("网银手续费")).toBeInTheDocument();

    act(() => {
      resolveSecondList?.(jsonResponse({
        ...listPayload,
        batches: batchesForBucket(listPayload, "unsubmitted"),
        read_model_status: "fresh",
        read_model_stale_reasons: [],
      }));
    });
    await waitFor(() => {
      expect(screen.queryByText("免OA流水读模型待刷新，已显示当前可用数据。")).not.toBeInTheDocument();
    });
  });

  test("sidebar exposes the no OA bank batch entry", () => {
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];

    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "免OA流水批量处理",
          to: "/no-oa-bank-batches",
        }),
      ]),
    );
  });
});
