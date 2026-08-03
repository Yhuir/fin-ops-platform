import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import { GlobalOperationOverlayProvider } from "../contexts/GlobalOperationOverlayContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { SessionPayload } from "../features/session/api";
import BatchAccountingPage from "../pages/BatchAccountingPage";

const batchAccountingSourceFiles = [
  "src/pages/BatchAccountingPage.tsx",
] as const;

const defaultSession: SessionPayload = {
  allowed: true,
  user: {
    userId: "1",
    username: "TESTFULL001",
    nickname: "测试全权限",
    displayName: "测试全权限",
    deptId: null,
    deptName: null,
    avatar: null,
  },
  roles: ["fin_ops_user"],
  permissions: ["finops:app:view"],
  accessTier: "full_access",
  canAccessApp: true,
  canMutateData: true,
  canAdminAccess: false,
};

const staticSession: SessionContextValue = {
  status: "authenticated",
  session: defaultSession,
  refresh: () => undefined,
};

const unsubmittedPayload = {
  summary: {
    unsubmitted_count: 2,
    submitted_count: 1,
  },
  bank_rows: [
    {
      id: "bank-row-001",
      trade_time: "2026-01-07T15:54:00+08",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "1200.00",
      bank_name: "建行",
      account_last4: "8106",
      relation_id: "",
      version: 1,
    },
    {
      id: "bank-row-002",
      trade_time: "2026-01-08 09:00:00",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "800.00",
      bank_name: "招行",
      account_last4: "1888",
      relation_id: "",
      version: 1,
    },
  ],
  oa_rows: [
    {
      id: "oa-exp-1001",
      applicant: "刘晨",
      apply_time: "2026-01-06",
      project_name: "品牌广告投放；市场活动项目",
      amount: "700.00",
      reason: "1月日常报销，包含广告素材制作和渠道投放费用",
      linked_invoice_row_ids: ["oa-att-inv-1001-01"],
    },
    {
      id: "oa-exp-1002",
      applicant: "王青",
      apply_time: "2026-01-07",
      project_name: "客户拜访差旅报销",
      amount: "500.00",
      reason: "上海客户拜访交通与餐费",
      linked_invoice_row_ids: [],
    },
  ],
};

const submittedPayload = {
  summary: {
    unsubmitted_count: 1,
    submitted_count: 2,
  },
  bank_rows: [
    {
      id: "bank-row-submitted-001",
      trade_time: "2026-02-10 12:30:00",
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "900.00",
      bank_name: "建行",
      account_last4: "8106",
      relation_id: "CASE-202602-001",
      version: 2,
    },
  ],
  oa_rows: [
    {
      id: "oa-exp-2001",
      applicant: "陈敏",
      apply_time: "2026-02-08",
      project_name: "办公室耗材采购",
      amount: "850.00",
      reason: "2月行政耗材日常报销",
      linked_invoice_row_ids: ["oa-att-inv-2001-01"],
    },
  ],
  relations_by_bank_row_id: {
    "bank-row-submitted-001": {
      relation_id: "CASE-202602-001",
      relation: {
        relation_id: "CASE-202602-001",
        note: "财务确认差额闭环",
        amount_check: {
          status: "mismatch",
          direction: "expense",
          bank_amount: "900.00",
          oa_amount: "850.00",
          amount_delta: "50.00",
          requires_note: true,
        },
      },
      oa_rows: [
        {
          id: "oa-exp-2001",
          applicant: "陈敏",
          apply_time: "2026-02-08",
          project_name: "办公室耗材采购",
          amount: "850.00",
          reason: "2月行政耗材日常报销",
          linked_invoice_row_ids: ["oa-att-inv-2001-01"],
        },
      ],
      invoice_rows: [
        {
          id: "oa-att-inv-2001-01",
          type: "invoice",
        },
      ],
    },
  },
};

const oa2025Rows = [
  {
    id: "oa-exp-1981",
    applicant: "陈雄兵",
    apply_time: "2025-12-23",
    project_name: "大理卷烟厂动力车间中水处理系统升级改造项目",
    amount: "500.00",
    reason: "日常报销",
    linked_invoice_row_ids: [],
  },
];

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
    <SessionContext.Provider value={staticSession}>
      <GlobalOperationOverlayProvider>
        <BatchAccountingPage />
      </GlobalOperationOverlayProvider>
    </SessionContext.Provider>,
  );
}

function positiveParam(params: URLSearchParams, name: string, fallback: number) {
  const value = Number(params.get(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function slicePage<T>(rows: T[], page: number, pageSize: number) {
  const start = (page - 1) * pageSize;
  return rows.slice(start, start + pageSize);
}

function withPagination<T extends { bank_rows?: unknown[]; oa_rows?: unknown[] }>(payload: T, url: URL): T & { pagination: Record<string, unknown> } {
  const bankRows = Array.isArray(payload.bank_rows) ? payload.bank_rows : [];
  const oaRows = Array.isArray(payload.oa_rows) ? payload.oa_rows : [];
  const bankPage = positiveParam(url.searchParams, "bank_page", 1);
  const bankPageSize = positiveParam(url.searchParams, "bank_page_size", 200);
  const nextPayload = {
    ...payload,
    bank_rows: slicePage(bankRows, bankPage, bankPageSize),
    pagination: {
      bank_rows: { page: bankPage, page_size: bankPageSize, total: bankRows.length },
    } as Record<string, unknown>,
  };
  if (url.searchParams.has("oa_page") || url.searchParams.has("oa_page_size")) {
    const oaPage = positiveParam(url.searchParams, "oa_page", 1);
    const oaPageSize = positiveParam(url.searchParams, "oa_page_size", 200);
    return {
      ...nextPayload,
      oa_rows: slicePage(oaRows, oaPage, oaPageSize),
      pagination: {
        ...nextPayload.pagination,
        oa_rows: { page: oaPage, page_size: oaPageSize, total: oaRows.length },
      },
    };
  }
  return nextPayload;
}

function largeUnsubmittedPayload(total = 205) {
  return {
    summary: {
      unsubmitted_count: total,
      submitted_count: 0,
    },
    bank_rows: Array.from({ length: total }, (_, index) => ({
      id: `bank-large-${index.toString().padStart(3, "0")}`,
      trade_time: `2026-01-${(index % 28 + 1).toString().padStart(2, "0")} 09:00:00`,
      counterparty_name: "批量账务集中处理",
      direction: "expense",
      direction_label: "支出",
      amount: "10.00",
      bank_name: "建行",
      account_last4: index.toString().padStart(4, "0"),
      relation_id: "",
      version: 1,
    })),
    oa_rows: Array.from({ length: total }, (_, index) => ({
      id: `oa-large-${index.toString().padStart(3, "0")}`,
      applicant: `申请人${index.toString().padStart(3, "0")}`,
      apply_time: `2026-01-${(index % 28 + 1).toString().padStart(2, "0")}`,
      project_name: "批量账务分页验证",
      amount: "10.00",
      reason: "日常报销",
      linked_invoice_row_ids: [],
    })),
  };
}

function installFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
      const bucket = url.searchParams.get("bucket");
      const bankYear = url.searchParams.get("bank_year");
      const payload = bucket === "submitted"
        ? submittedPayload
        : {
          ...unsubmittedPayload,
          summary: {
            ...unsubmittedPayload.summary,
            unsubmitted_count: bankYear === "2026" ? unsubmittedPayload.bank_rows.length : 0,
          },
          bank_rows: bankYear === "2026" ? unsubmittedPayload.bank_rows : [],
          oa_rows: [...unsubmittedPayload.oa_rows, ...oa2025Rows],
        };
      const oaSearch = String(url.searchParams.get("oa_search") ?? "").trim().toLowerCase();
      const filteredPayload = oaSearch
        ? {
          ...payload,
          oa_rows: payload.oa_rows.filter((row) => [
            row.applicant,
            row.project_name,
            row.amount,
            row.reason,
          ].some((value) => String(value ?? "").toLowerCase().includes(oaSearch))),
        }
        : payload;
      return new Response(JSON.stringify(withPagination(filteredPayload, url)), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/batch-accounting/submit") {
      return new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-202601-001",
        affected_row_ids: ["bank-row-001", "oa-exp-1001", "oa-exp-1002", "oa-att-inv-1001-01"],
        affected_months: ["2026-01"],
        message: "已关联批量账务流水与 2 项 OA。",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/batch-accounting/CASE-202602-001/withdraw") {
      return new Response(JSON.stringify({
        success: true,
        relation_id: "CASE-202602-001",
        affected_months: ["2026-02"],
        message: "已撤回批量账务关联。",
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ message: `Unhandled ${url.pathname}` }), { status: 404, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function lastSubmitBody(fetchMock: ReturnType<typeof installFetchMock>) {
  const submitCall = fetchMock.mock.calls.find(([input]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/batch-accounting/submit";
  });
  expect(submitCall).toBeTruthy();
  return JSON.parse(String(submitCall?.[1]?.body ?? "{}")) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BatchAccountingPage", () => {
  test("targets project primitives for page shell, bank panel, OA table, overlays, and feedback", () => {
    const sourceByPath = Object.fromEntries(batchAccountingSourceFiles.map((path) => [path, readWebSource(path)]));
    const forbiddenMuiImports = batchAccountingSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /from ["']@mui\/|import\s+[^;]*@mui\//.test(source) ? [path] : [];
    });
    const forbiddenMuiSelectors = batchAccountingSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /\.Mui[A-Z][A-Za-z-]*/.test(source) ? [path] : [];
    });
    const forbiddenLegacySurfaces = batchAccountingSourceFiles.flatMap((path) => {
      const source = sourceByPath[path];
      return /ClearOutlinedIcon|RefreshOutlinedIcon|SearchOutlinedIcon|WarningAmberRoundedIcon|ToggleButton|TextField|TableCell|TableRow|TableHead|TableBody|DialogTitle|DialogContent|DialogActions|Snackbar|Chip|IconButton|Tooltip/.test(source)
        ? [path]
        : [];
    });
    const pageSource = sourceByPath["src/pages/BatchAccountingPage.tsx"];
    const missingPrimitiveTargets = [
      pageSource.includes("PageScaffold") ? null : "BatchAccountingPage.tsx should keep PageScaffold",
      pageSource.includes("StatePanel") ? null : "BatchAccountingPage.tsx should keep StatePanel for loading/empty/error states",
      /FinanceTable|finance-table|batch-accounting.*table/.test(pageSource)
        ? null
        : "OA rows should use FinanceTable or a project/native table class",
      /batch-accounting.*panel|batch-accounting.*list|batch-accounting.*region/.test(pageSource)
        ? null
        : "Bank rows and selection summary should use project panel/list/region classes",
      /AppDialog|batch-accounting.*dialog/.test(pageSource)
        ? null
        : "Withdraw confirmation should use AppDialog or a project dialog class",
      /batch-accounting.*toast|batch-accounting.*feedback|batch-accounting.*notice/.test(pageSource)
        ? null
        : "Mutation feedback should use a project feedback/toast class",
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

  test("keeps premium compact panels, OA table, stable tags, and interaction CSS contracts", () => {
    const styles = readWebSource("src/app/styles.css");
    const layoutRule = cssRule(styles, ".batch-accounting-layout");
    const buttonRule = cssRule(styles, ".batch-accounting-button");
    const segmentRule = cssRule(styles, ".batch-accounting-segment__button");
    const yearFieldRule = cssRule(styles, ".batch-accounting-field--year");
    const inputRule = cssRule(styles, ".batch-accounting-field input,\\n.batch-accounting-field textarea");
    const searchRule = cssRule(styles, ".batch-accounting-search");
    const searchClearRule = cssRule(styles, ".batch-accounting-search__clear");
    const paginationRule = cssRule(styles, ".batch-accounting-pagination");
    const paginationButtonRule = cssRule(styles, ".batch-accounting-pagination__button");
    const bankHeaderRule = cssRule(styles, ".batch-accounting-bank-panel__header");
    const bankHeaderTitleRule = cssRule(styles, ".batch-accounting-bank-panel__header > div:first-child");
    const bankRowRule = cssRule(styles, ".batch-accounting-bank-row");
    const bankRowMainRule = cssRule(styles, ".batch-accounting-bank-row__main");
    const bankRowTitleRule = cssRule(styles, ".batch-accounting-bank-row__title");
    const selectedBankRowRule = cssRule(styles, ".batch-accounting-bank-row--selected,\\n.batch-accounting-bank-row[aria-pressed=\"true\"]");
    const tagRule = cssRule(styles, ".batch-accounting-tag,\\n.batch-accounting-summary-tag");
    const mismatchRule = cssRule(styles, ".batch-accounting-mismatch-warning__trigger");
    const oaToolbarRule = cssRule(styles, ".batch-accounting-oa-panel__toolbar");
    const tableWrapRule = cssRule(styles, ".batch-accounting-oa-table-wrap");
    const tableCellRule = cssRule(styles, ".batch-accounting-oa-table th,\\n.batch-accounting-oa-table td");
    const tableHeadRule = cssRule(styles, ".batch-accounting-oa-table th");
    const amountRule = cssRule(styles, ".batch-accounting-oa-table .batch-accounting-oa-table__amount");
    const checkboxRule = cssRule(styles, ".batch-accounting-checkbox");
    const expandToggleRule = cssRule(styles, ".batch-accounting-expandable__toggle");
    const feedbackCloseRule = cssRule(styles, ".batch-accounting-feedback__close");

    expect(buttonRule).toContain("var(--motion-fast)");
    expect(segmentRule).toContain("var(--motion-fast)");
    expect(inputRule).toContain("var(--motion-fast)");
    expect(searchRule).toContain("var(--motion-fast)");
    expect(searchClearRule).toContain("var(--motion-fast)");
    expect(paginationButtonRule).toContain("var(--motion-fast)");
    expect(bankRowRule).toContain("var(--motion-fast)");
    expect(mismatchRule).toContain("var(--motion-fast)");
    expect(tableCellRule).toContain("var(--motion-fast)");
    expect(checkboxRule).toContain("var(--motion-fast)");
    expect(expandToggleRule).toContain("var(--motion-fast)");
    expect(feedbackCloseRule).toContain("var(--motion-fast)");

    expect(layoutRule).toContain("minmax(360px, clamp(360px, 32vw, 520px))");
    expect(yearFieldRule).toContain("flex: 0 0 128px");
    expect(paginationRule).toContain("flex: 0 0 auto");
    expect(bankHeaderRule).toContain("flex-wrap: wrap");
    expect(bankHeaderTitleRule).toContain("flex: 1 1 220px");
    expect(bankRowMainRule).toContain("grid-template-columns: minmax(0, 1fr) auto");
    expect(bankRowTitleRule).toContain("text-overflow: ellipsis");
    expect(styles).toContain("@media (max-width: 640px)");
    expect(styles).toContain(".batch-accounting-pagination {\n    justify-content: space-between;");
    expect(bankRowRule).toContain("padding: var(--fp-space-2) var(--fp-space-3)");
    expect(selectedBankRowRule).toContain("inset 3px 0 0 var(--fp-primary)");
    expect(tagRule).toContain("min-height: var(--fp-tag-height-table)");
    expect(tagRule).toContain("border-radius: var(--fp-tag-radius-table)");
    expect(tagRule).toContain("text-overflow: ellipsis");
    expect(oaToolbarRule).toContain("padding: var(--fp-space-2) var(--fp-space-3)");
    expect(paginationButtonRule).toContain("width: 30px");
    expect(paginationButtonRule).toContain("height: 30px");
    expect(tableWrapRule).toContain("max-height: calc(100vh - 252px)");
    expect(tableHeadRule).toContain("color-mix(in srgb, var(--fp-surface-muted)");
    expect(amountRule).toContain("text-align: right");
    expect(amountRule).toContain("font-variant-numeric: tabular-nums");
    expect(tagRule).not.toContain("min-height: 22px");
    expect(buttonRule).not.toContain("120ms ease");
    expect(bankRowRule).not.toContain("120ms ease");
    expect(tableCellRule).not.toContain("120ms ease");
  });

  test("renders controls, bank list, and selectable OA table for unsubmitted rows", async () => {
    const fetchMock = installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "日常报销批量账务管理" })).toBeInTheDocument();
    await waitFor(() => {
      const firstGet = fetchMock.mock.calls.find(([input, init]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET");
      });
      expect(firstGet).toBeTruthy();
      const url = new URL(typeof firstGet?.[0] === "string" ? firstGet[0] : firstGet?.[0] instanceof URL ? firstGet[0].toString() : firstGet?.[0].url ?? "", "http://localhost");
      expect(url.searchParams.get("bank_page")).toBe("1");
      expect(url.searchParams.get("bank_page_size")).toBe("200");
      expect(url.searchParams.get("oa_page")).toBe("1");
      expect(url.searchParams.get("oa_page_size")).toBe("200");
      expect(url.searchParams.has("oa_year")).toBe(false);
    });
    expect(screen.getByRole("button", { name: "未提交 2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.queryByLabelText("年份")).not.toBeInTheDocument();
    expect(screen.getByLabelText("流水年份")).toHaveValue(2026);
    expect(screen.queryByLabelText("OA年份")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();

    const bankList = screen.getByRole("region", { name: "批量账务流水" });
    expect(within(bankList).getAllByRole("button", { name: /批量账务集中处理/ })).toHaveLength(2);
    expect(screen.getByRole("group", { name: "批量账务流水分页" })).toHaveTextContent("1-2 / 2");
    expect(screen.getByRole("group", { name: "可关联OA项分页" })).toHaveTextContent("1-3 / 3");
    expect(within(bankList).queryByRole("table")).not.toBeInTheDocument();
    expect(within(bankList).getByText("2026-01-07 15:54:00")).toBeInTheDocument();
    expect(within(bankList).queryByText("2026-01-07T15:54:00+08")).not.toBeInTheDocument();
    expect(within(bankList).getByRole("button", { name: /批量账务集中处理.*1200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const oaTable = screen.getByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByRole("checkbox", { name: "选择 刘晨 2026-01-06" })).toBeInTheDocument();
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("2026-01-06")).toBeInTheDocument();
    expect(within(oaTable).getByText("品牌广告投放；市场活动项目")).toBeInTheDocument();
    expect(within(oaTable).getByText("700.00")).toBeInTheDocument();
    expect(within(oaTable).getByText("1月日常报销，包含广告素材制作和渠道投放费用")).toBeInTheDocument();
  });

  test("uses backend pagination for bank and OA first screens", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
        return jsonResponse(withPagination(largeUnsubmittedPayload(), url));
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    await waitFor(() => {
      expect(within(screen.getByRole("group", { name: "批量账务流水分页" })).getByText("1-200 / 205")).toBeInTheDocument();
      expect(within(screen.getByRole("group", { name: "可关联OA项分页" })).getByText("1-200 / 205")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /批量账务集中处理.*建行 0000/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /批量账务集中处理.*建行 0204/ })).not.toBeInTheDocument();
    expect(screen.getByText("申请人000")).toBeInTheDocument();
    expect(screen.queryByText("申请人204")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "批量账务流水分页下一页" }));
    expect(await screen.findByText("201-205 / 205")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /批量账务集中处理.*建行 0200/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /批量账务集中处理.*建行 0000/ })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "可关联OA项分页下一页" }));
    await waitFor(() => {
      expect(screen.getByText("申请人200")).toBeInTheDocument();
    });
    expect(screen.queryByText("申请人000")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/batch-accounting"
        && url.searchParams.get("bank_page_size") === "200"
        && url.searchParams.get("oa_page_size") === "200";
    })).toBe(true);
  });

  test("shows loading and empty states in the bank and OA regions", async () => {
    let resolveFetch: (response: Response) => void = () => undefined;
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("正在加载流水")).toBeInTheDocument();
    resolveFetch(jsonResponse({
      summary: {
        unsubmitted_count: 0,
        submitted_count: 0,
      },
      bank_rows: [],
      oa_rows: [],
    }));

    expect(await screen.findByText("当前年份暂无批量账务流水")).toBeInTheDocument();
    expect(screen.getByText("暂无可关联 OA")).toBeInTheDocument();
  });

  test("ignores an aborted stale response until the latest search request completes", async () => {
    const user = userEvent.setup();
    const pendingResolvers: Array<(response: Response) => void> = [];
    const requestSignals: Array<AbortSignal | null | undefined> = [];
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      requestSignals.push(init?.signal);
      return new Promise<Response>((resolve) => {
        pendingResolvers.push(resolve);
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("正在加载流水")).toBeInTheDocument();
    await user.type(screen.getByLabelText("搜索OA内容"), "刘");
    await waitFor(() => expect(pendingResolvers).toHaveLength(2));
    expect(requestSignals[0]?.aborted).toBe(true);

    pendingResolvers[0]?.(jsonResponse({
      ...unsubmittedPayload,
      bank_rows: [{
        ...unsubmittedPayload.bank_rows[0],
        id: "bank-stale",
        amount: "111.00",
        bank_name: "旧银行",
        account_last4: "1111",
      }],
    }));
    await waitFor(() => expect(screen.getByText("正在加载流水")).toBeInTheDocument());
    expect(screen.queryByText("旧银行 1111")).not.toBeInTheDocument();

    pendingResolvers[1]?.(jsonResponse({
      ...unsubmittedPayload,
      bank_rows: [{
        ...unsubmittedPayload.bank_rows[0],
        id: "bank-latest",
        amount: "222.00",
        bank_name: "新银行",
        account_last4: "2222",
      }],
    }));

    expect(await screen.findByText("新银行 2222")).toBeInTheDocument();
    expect(screen.queryByText("正在加载流水")).not.toBeInTheDocument();
    expect(screen.queryByText("旧银行 1111")).not.toBeInTheDocument();
  });

  test("shows the page error fallback when batch accounting data fails to load", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ message: "批量账务数据加载失败" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("批量账务数据加载失败")).toBeInTheDocument();
  });

  test("recovers after a transient batch accounting load failure when refreshed", async () => {
    const user = userEvent.setup();
    let batchAccountingGetCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
        batchAccountingGetCount += 1;
        if (batchAccountingGetCount === 1) {
          return jsonResponse({
            error: "batch_accounting_temporarily_unavailable",
            message: "批量账务数据加载暂时失败，请刷新后重试。",
          }, 503);
        }
        return jsonResponse(withPagination(unsubmittedPayload, url));
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("批量账务数据加载暂时失败，请刷新后重试。")).toBeInTheDocument();
    expect(screen.queryByText("当前年份暂无批量账务流水")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "刷新" }));

    expect(await screen.findByRole("button", { name: /批量账务集中处理.*1200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toBeInTheDocument();
    expect(screen.queryByText("批量账务数据加载暂时失败，请刷新后重试。")).not.toBeInTheDocument();
    expect(batchAccountingGetCount).toBe(2);
  });

  test("updates selected totals, requires notes for mismatches, and submits matching OA rows without a note", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();

      await screen.findByRole("heading", { name: "日常报销批量账务管理" });
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
      expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();
      expect(screen.getByText("差额 500.00")).toBeInTheDocument();
      expect(screen.getByLabelText("差额说明")).toBeInTheDocument();
      expect(screen.getByText("金额不一致时必须填写，提交后视为人工差额闭环。")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
      expect(screen.getByText("已选 OA 2 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 1200.00")).toBeInTheDocument();
      expect(screen.getByText("差额 0.00")).toBeInTheDocument();
      expect(screen.queryByLabelText("差额说明")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

      await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/batch-accounting/submit",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({
              bank_year: "2026",
              bank_row_id: "bank-row-001",
              oa_row_ids: ["oa-exp-1001", "oa-exp-1002"],
              expected_version: 1,
              note: "",
            }),
          }),
        );
      });
    expect(await screen.findByText("已关联批量账务流水与 2 项 OA。")).toBeInTheDocument();
  });

  test("submits mismatched OA rows only when difference note is non-empty after trimming", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    const noteInput = screen.getByLabelText("差额说明");
    expect(noteInput.tagName).toBe("INPUT");
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

    await user.type(noteInput, "   ");
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

    await user.type(noteInput, "财务确认差额闭环");
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

    await waitFor(() => {
      expect(lastSubmitBody(fetchMock)).toMatchObject({
        bank_year: "2026",
        bank_row_id: "bank-row-001",
        oa_row_ids: ["oa-exp-1001"],
        expected_version: 1,
        note: "财务确认差额闭环",
      });
    });
  });

  test("clears difference note when switching bank rows", async () => {
    const user = userEvent.setup();
    installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    expect(screen.getByLabelText("差额说明")).toHaveValue("财务确认差额闭环");

    await user.click(screen.getByRole("button", { name: /批量账务集中处理.*800.00.*2026-01-08 09:00:00.*支出.*招行 1888/ }));
    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));

    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("clears difference note when switching submitted and unsubmitted buckets", async () => {
    const user = userEvent.setup();
    installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    expect(screen.getByLabelText("差额说明")).toHaveValue("财务确认差额闭环");

    await user.click(screen.getByRole("button", { name: "已提交 1" }));
    await screen.findByRole("table", { name: "已关联OA项" });
    await user.click(screen.getByRole("button", { name: /^未提交/ }));
    await screen.findByRole("table", { name: "可关联OA项" });
    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));

    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("clears difference note when OA selection changes", async () => {
    const user = userEvent.setup();
    installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    expect(screen.queryByLabelText("差额说明")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("clears cached bank and OA selection when refreshed bank rows disappear", async () => {
    const user = userEvent.setup();
    let getCount = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
        getCount += 1;
        if (getCount === 1) {
          return jsonResponse(unsubmittedPayload);
        }
        return jsonResponse({
          summary: {
            unsubmitted_count: 0,
            submitted_count: 1,
          },
          bank_rows: [],
          oa_rows: unsubmittedPayload.oa_rows,
        });
      }
      return jsonResponse({
        success: true,
        relation_id: "CASE-SHOULD-NOT-SUBMIT",
        affected_months: [],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });
    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "刷新" }));

    expect(await screen.findByText("当前年份暂无批量账务流水")).toBeInTheDocument();
    expect(await screen.findByText("银行流水金额 0.00")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 0 项")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/batch-accounting/submit";
    })).toBe(false);
  });

  test("submits cross-year unpaired daily reimbursement OA without an OA year filter", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();

    const oaTable = await screen.findByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByText("陈雄兵")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /批量账务集中处理.*1200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();

    await user.click(await screen.findByRole("checkbox", { name: "选择 陈雄兵 2025-12-23" }));
    expect(screen.getByText("已选 OA 2 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 1200.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/batch-accounting/submit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            bank_year: "2026",
            bank_row_id: "bank-row-001",
            oa_row_ids: ["oa-exp-1001", "oa-exp-1981"],
            expected_version: 1,
            note: "",
          }),
        }),
      );
    });
  });

  test("reloads the visible page through its normal GET without calling the operation barrier", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
        return jsonResponse(withPagination(unsubmittedPayload, url));
      }
      if (url.pathname === "/api/batch-accounting/submit") {
        return jsonResponse({
          success: true,
          relation_id: "CASE-202601-001",
          affected_months: ["2026-01"],
          message: "已关联批量账务流水与 2 项 OA。",
        });
      }
      return jsonResponse({ message: `Unhandled ${url.pathname}` }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(await screen.findByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    const pageReadsBeforeSubmit = fetchMock.mock.calls.filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET");
    }).length;
    await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

    expect(await screen.findByText("已关联批量账务流水与 2 项 OA。")).toBeInTheDocument();
    expect(screen.queryByText("操作失败")).not.toBeInTheDocument();
    const pageReads = fetchMock.mock.calls.filter(([input, init]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET");
    });
    expect(pageReads).toHaveLength(pageReadsBeforeSubmit + 1);
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      return url.pathname === "/api/operation-barrier/status";
    })).toBe(false);
  });

  test("sends OA search to the server and resets OA pagination", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    renderPage();

    const oaTable = await screen.findByRole("table", { name: "可关联OA项" });
    expect(await within(oaTable).findByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索OA内容"), "上海客户");
    await waitFor(() => {
      expect(within(oaTable).queryByText("刘晨")).not.toBeInTheDocument();
      expect(within(oaTable).getByText("王青")).toBeInTheDocument();
      expect(fetchMock.mock.calls.some(([input]) => {
        const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
        return url.pathname === "/api/batch-accounting"
          && url.searchParams.get("oa_search") === "上海客户"
          && url.searchParams.get("oa_page") === "1";
      })).toBe(true);
    });

    await user.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(await within(oaTable).findByText("刘晨")).toBeInTheDocument();
  });

  test("renders submitted bucket as read-only associated OA and withdraws with a reason", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();
      await user.click(await screen.findByRole("button", { name: "已提交 1" }));

      expect(await screen.findByRole("button", { name: /批量账务集中处理.*900.00.*2026-02-10 12:30:00.*支出.*建行 8106/ })).toBeInTheDocument();
      const associatedTable = screen.getByRole("table", { name: "已关联OA项" });
      expect(within(associatedTable).queryByRole("checkbox")).not.toBeInTheDocument();
      expect(within(associatedTable).getByText("陈敏")).toBeInTheDocument();
      expect(within(associatedTable).getByText("2月行政耗材日常报销")).toBeInTheDocument();
      expect(within(associatedTable).queryByText(/财务确认差额闭环/)).not.toBeInTheDocument();
      expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 850.00")).toBeInTheDocument();
      expect(screen.getByText("差额 50.00")).toBeInTheDocument();
      expect(screen.getByText("金额不一致")).toBeInTheDocument();
      const mismatchIcon = screen.getByRole("button", { name: "查看金额不一致差额说明" });
      await user.hover(mismatchIcon);
      expect(await screen.findByText("差额说明：财务确认差额闭环")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "撤回关联" })).toBeEnabled();

      await user.click(screen.getByRole("button", { name: "撤回关联" }));
      await user.type(screen.getByLabelText("撤回原因"), "选择错误");
      await user.click(screen.getByRole("button", { name: "确认撤回" }));

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          "/api/batch-accounting/CASE-202602-001/withdraw",
          expect.objectContaining({
            method: "POST",
            body: JSON.stringify({ expected_version: 2, reason: "选择错误" }),
          }),
        );
      });
    expect(await screen.findByText("已撤回批量账务关联。")).toBeInTheDocument();
  });

  test("sidebar exposes the batch accounting entry near bank flow rule batches", () => {
    const financeItems = sidebarGroups.find((group) => group.title === "财务业务")?.items ?? [];

    expect(financeItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "批量账务",
          to: "/batch-accounting",
        }),
      ]),
    );
  });
});
