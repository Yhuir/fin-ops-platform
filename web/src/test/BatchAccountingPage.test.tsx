import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { sidebarGroups } from "../components/shell/sidebarItems";
import BatchAccountingPage from "../pages/BatchAccountingPage";
import { expectCustomEventDetailContaining } from "./eventAssertions";

const batchAccountingSourceFiles = [
  "src/pages/BatchAccountingPage.tsx",
] as const;

const unsubmittedPayload = {
  summary: {
    unsubmitted_count: 2,
    submitted_count: 1,
  },
  bank_rows: [
    {
      id: "bank-row-001",
      trade_time: "2026-01-07 15:54:00",
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

function renderPage() {
  return render(<BatchAccountingPage />);
}

function installFetchMock() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    if (url.pathname === "/api/batch-accounting" && (!init?.method || init.method === "GET")) {
      const bucket = url.searchParams.get("bucket");
      const bankYear = url.searchParams.get("bank_year");
      const oaYear = url.searchParams.get("oa_year");
      const payload = bucket === "submitted"
        ? submittedPayload
        : {
          ...unsubmittedPayload,
          summary: {
            ...unsubmittedPayload.summary,
            unsubmitted_count: bankYear === "2026" ? unsubmittedPayload.bank_rows.length : 0,
          },
          bank_rows: bankYear === "2026" ? unsubmittedPayload.bank_rows : [],
          oa_rows: oaYear === "2025" ? oa2025Rows : unsubmittedPayload.oa_rows,
        };
      return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
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

  test("renders controls, bank list, and selectable OA table for unsubmitted rows", async () => {
    installFetchMock();
    renderPage();

    expect(await screen.findByRole("heading", { name: "日常报销批量账务管理" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "未提交 2" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "已提交 1" })).toBeInTheDocument();
    expect(screen.queryByLabelText("年份")).not.toBeInTheDocument();
    expect(screen.getByLabelText("流水年份")).toHaveValue(2026);
    expect(screen.getByLabelText("OA年份")).toHaveValue(2026);
    expect(screen.getByRole("button", { name: "刷新" })).toBeInTheDocument();

    const bankList = screen.getByRole("region", { name: "批量账务流水" });
    expect(within(bankList).getAllByRole("button")).toHaveLength(2);
    expect(within(bankList).queryByRole("table")).not.toBeInTheDocument();
    expect(within(bankList).getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");

    const oaTable = screen.getByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByRole("checkbox", { name: "选择 刘晨 2026-01-06" })).toBeInTheDocument();
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("2026-01-06")).toBeInTheDocument();
    expect(within(oaTable).getByText("品牌广告投放；市场活动项目")).toBeInTheDocument();
    expect(within(oaTable).getByText("700.00")).toBeInTheDocument();
    expect(within(oaTable).getByText("1月日常报销，包含广告素材制作和渠道投放费用")).toBeInTheDocument();
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

  test("shows the page error fallback when batch accounting data fails to load", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ message: "批量账务数据加载失败" }, 500));
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("批量账务数据加载失败")).toBeInTheDocument();
  });

  test("updates selected totals, requires notes for mismatches, and submits matching OA rows without a note", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
      renderPage();

      await screen.findByRole("heading", { name: "日常报销批量账务管理" });
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
      expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();
      expect(screen.getByText("差额 500.00")).toBeInTheDocument();
      expect(screen.getByLabelText("差额说明")).toBeInTheDocument();
      expect(screen.getByText("金额不一致时必须填写，提交后视为人工差额闭环。")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeDisabled();

      await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
      expect(screen.getByText("已选 OA 2 项")).toBeInTheDocument();
      expect(screen.getByText("已选 OA 金额 1,200.00")).toBeInTheDocument();
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
              oa_year: "2026",
              bank_row_id: "bank-row-001",
              oa_row_ids: ["oa-exp-1001", "oa-exp-1002"],
              expected_version: 1,
              note: "",
            }),
          }),
        );
      });
      expect(await screen.findByText("已关联批量账务流水与 2 项 OA。")).toBeInTheDocument();
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-01"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("submits mismatched OA rows only when difference note is non-empty after trimming", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
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
        oa_year: "2026",
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

    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    expect(screen.getByLabelText("差额说明")).toHaveValue("财务确认差额闭环");

    await user.click(screen.getByRole("button", { name: /批量账务集中处理.*800.00.*2026-01-08 09:00:00.*支出.*招行 1888/ }));
    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));

    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("clears difference note when switching submitted and unsubmitted buckets", async () => {
    const user = userEvent.setup();
    installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    expect(screen.getByLabelText("差额说明")).toHaveValue("财务确认差额闭环");

    await user.click(screen.getByRole("button", { name: "已提交 1" }));
    await screen.findByRole("table", { name: "已关联OA项" });
    await user.click(screen.getByRole("button", { name: /^未提交/ }));
    await screen.findByRole("table", { name: "可关联OA项" });
    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));

    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("clears difference note when OA selection changes", async () => {
    const user = userEvent.setup();
    installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    await user.type(screen.getByLabelText("差额说明"), "财务确认差额闭环");
    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    expect(screen.queryByLabelText("差额说明")).not.toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "选择 王青 2026-01-07" }));
    expect(screen.getByLabelText("差额说明")).toHaveValue("");
  });

  test("keeps selected bank and OA rows when changing only the OA year", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();

    renderPage();
    await screen.findByRole("heading", { name: "日常报销批量账务管理" });

    await user.click(screen.getByRole("checkbox", { name: "选择 刘晨 2026-01-06" }));
    expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();

    const oaYearInput = screen.getByLabelText("OA年份");
    await user.clear(oaYearInput);
    await user.type(oaYearInput, "2025");

    const oaTable = await screen.findByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByText("陈雄兵")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /批量账务集中处理.*1,200.00.*2026-01-07 15:54:00.*支出.*建行 8106/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("已选 OA 1 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 700.00")).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "选择 陈雄兵 2025-12-23" }));
    expect(screen.getByText("已选 OA 2 项")).toBeInTheDocument();
    expect(screen.getByText("已选 OA 金额 1,200.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "关联OA项与流水" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "关联OA项与流水" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/batch-accounting/submit",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            bank_year: "2026",
            oa_year: "2025",
            bank_row_id: "bank-row-001",
            oa_row_ids: ["oa-exp-1001", "oa-exp-1981"],
            expected_version: 1,
            note: "",
          }),
        }),
      );
    });
  });

  test("filters right side OA rows across applicant, project, amount, and reason", async () => {
    const user = userEvent.setup();
    installFetchMock();
    renderPage();

    const oaTable = await screen.findByRole("table", { name: "可关联OA项" });
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索OA内容"), "上海客户");
    expect(within(oaTable).queryByText("刘晨")).not.toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).getByText("王青")).toBeInTheDocument();

    await user.type(screen.getByLabelText("搜索OA内容"), "700.00");
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).queryByText("王青")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "清空搜索" }));
    await user.type(screen.getByLabelText("搜索OA内容"), "品牌广告");
    expect(within(oaTable).getByText("刘晨")).toBeInTheDocument();
    expect(within(oaTable).queryByText("王青")).not.toBeInTheDocument();
  });

  test("renders submitted bucket as read-only associated OA and withdraws with a reason", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock();
    const relationListener = vi.fn();
    window.addEventListener("workbenchRelationUpdated", relationListener);

    try {
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
      expectCustomEventDetailContaining(relationListener, { affectedMonths: ["2026-02"] });
    } finally {
      window.removeEventListener("workbenchRelationUpdated", relationListener);
    }
  });

  test("sidebar exposes the batch accounting entry near no OA bank batches", () => {
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
