import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import MuiProviders from "../app/MuiProviders";
import WorkbenchExceptionModal from "../components/workbench/WorkbenchExceptionModal";
import { PageSessionStateProvider } from "../contexts/PageSessionStateContext";
import { SessionContext, type SessionContextValue } from "../contexts/SessionContext";
import type { WorkbenchExceptionPreview } from "../features/workbench/exceptionTypes";
import type { WorkbenchRecord } from "../features/workbench/types";

const sessionValue: SessionContextValue = {
  status: "authenticated",
  session: {
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
  },
  refresh: () => undefined,
};

describe("WorkbenchExceptionModal", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  test("loads preview on open and renders amount summary, evidence, warnings, actions, and required fields", async () => {
    const user = userEvent.setup();
    let resolvePreview: (response: Response) => void = () => undefined;
    const previewPromise = new Promise<Response>((resolve) => {
      resolvePreview = resolve;
    });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/workbench/exception/preview") {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(JSON.stringify({
          month: "all",
          row_ids: ["oa-1", "bank-1", "invoice-1"],
        }));
        return previewPromise;
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderModal({ rows: defaultRows });

    expect(screen.getByText("正在加载异常预览")).toBeInTheDocument();

    resolvePreview(jsonResponse(expensePreview));

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(within(dialog).getByText("支出")).toBeInTheDocument();
    expect(within(dialog).getByText("OA和支出流水一致，缺进项发票")).toBeInTheDocument();
    expect(within(dialog).getByText("OA合计")).toBeInTheDocument();
    expect(within(dialog).getAllByText("100,000.00").length).toBeGreaterThanOrEqual(2);
    expect(within(dialog).getByText("支出流水合计")).toBeInTheDocument();
    expect(within(dialog).getByText("收入流水合计")).toBeInTheDocument();
    expect(within(dialog).getByText("进项发票合计")).toBeInTheDocument();
    expect(within(dialog).getByText("销项发票合计")).toBeInTheDocument();
    expect(within(dialog).getByText("oa_equals_bank_missing_invoice")).toBeInTheDocument();
    expect(within(dialog).getByText("命中候选分组 CASE-202603-101")).toBeInTheDocument();
    expect(within(dialog).getByText("已存在补票候选，提交前请复核发票归属。")).toBeInTheDocument();
    expect(within(dialog).getByText("系统自动动作")).toBeInTheDocument();
    expect(within(dialog).getByText("人工可选动作")).toBeInTheDocument();
    expect(within(dialog).getByText("处理后闭环")).toBeInTheDocument();
    expect(within(dialog).getByText("进入待处理")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("radio", { name: /追进项发票/ }));

    expect(within(dialog).getByText("必填字段")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("备注")).toBeInTheDocument();
  });

  test("shows preview loading failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ message: "preview backend unavailable" }, 500)));

    renderModal({ rows: defaultRows });

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(within(dialog).getByText("异常预览加载失败")).toBeInTheDocument();
    expect(within(dialog).getByText("preview backend unavailable")).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "提交处理" })).not.toBeInTheDocument();
  });

  test("submits manual OA exemption payload and clears the page session draft after success", async () => {
    const user = userEvent.setup();
    const onApplied = vi.fn();
    const onClose = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/workbench/exception/preview") {
        return jsonResponse(manualOaExemptionPreview);
      }
      if (url.pathname === "/api/workbench/exception/apply") {
        return jsonResponse({
          success: true,
          case: { id: "EXC-1" },
          pair_relation: { id: "REL-1" },
          updated_rows: [{ id: "bank-1" }, { id: "invoice-1" }],
          affected_row_ids: ["bank-1", "invoice-1"],
          workbench_refresh_required: true,
        });
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderModal({
      rows: defaultRows.filter((row) => row.id !== "oa-1"),
      onApplied,
      onClose,
    });

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    await user.click(within(dialog).getByRole("radio", { name: /人工确认免 OA/ }));
    await user.type(within(dialog).getByLabelText("原因代码"), "manual_business_exemption");
    await user.type(within(dialog).getByLabelText("到期日期"), "2026-05-31");
    await user.type(within(dialog).getByLabelText("备注"), "业务确认无需 OA");

    await waitFor(() => {
      expect(sessionStorageKeys().some((key) => key.includes("workbenchExceptionModalDraft"))).toBe(true);
    });

    await user.click(within(dialog).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/exception/apply",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["bank-1", "invoice-1"],
            scenario_code: "expense_bank_invoice_missing_oa",
            action_code: "manual_oa_exempt",
            payload: {
              note: "业务确认无需 OA",
              reason_code: "manual_business_exemption",
              due_date: "2026-05-31",
            },
          }),
        }),
      );
    });
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({
      success: true,
      workbenchRefreshRequired: true,
      affectedRowIds: ["bank-1", "invoice-1"],
    }));
    expect(onClose).toHaveBeenCalled();
    expect(sessionStorageKeys().some((key) => key.includes("workbenchExceptionModalDraft"))).toBe(false);
  });

  test("submits backend automatic action when no manual action is returned", async () => {
    const user = userEvent.setup();
    const onApplied = vi.fn();
    const onClose = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/workbench/exception/preview") {
        return jsonResponse(automaticClosedPreview);
      }
      if (url.pathname === "/api/workbench/exception/apply") {
        return jsonResponse({
          success: true,
          case: { id: "EXC-AUTO-1" },
          pair_relation: { id: "REL-AUTO-1" },
          updated_rows: defaultRows,
          affected_row_ids: ["oa-1", "bank-1", "invoice-1"],
          workbench_refresh_required: true,
        });
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderModal({ rows: defaultRows, onApplied, onClose });

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(within(dialog).getByText("确认支出闭环")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "提交处理" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/workbench/exception/apply",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            month: "all",
            row_ids: ["oa-1", "bank-1", "invoice-1"],
            scenario_code: "expense_all_equal_closed",
            action_code: "confirm_closed",
            payload: {},
          }),
        }),
      );
    });
    expect(onApplied).toHaveBeenCalledWith(expect.objectContaining({
      success: true,
      affectedRowIds: ["oa-1", "bank-1", "invoice-1"],
    }));
    expect(onClose).toHaveBeenCalled();
  });

  test("releases submit state and shows a recoverable error when apply takes too long", async () => {
    const user = userEvent.setup();
    const onApplied = vi.fn();
    const onClose = vi.fn();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
      if (url.pathname === "/api/workbench/exception/preview") {
        return jsonResponse(manualOaExemptionPreview);
      }
      if (url.pathname === "/api/workbench/exception/apply") {
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
        });
      }
      throw new Error(`Unexpected request: ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderModal({
      rows: defaultRows.filter((row) => row.id !== "oa-1"),
      onApplied,
      onClose,
    });

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    await user.click(within(dialog).getByRole("radio", { name: /人工确认免 OA/ }));
    await user.type(within(dialog).getByLabelText("原因代码"), "manual_business_exemption");
    await user.type(within(dialog).getByLabelText("到期日期"), "2026-05-31");
    await user.type(within(dialog).getByLabelText("备注"), "业务确认无需 OA");

    vi.useFakeTimers();
    act(() => {
      fireEvent.click(within(dialog).getByRole("button", { name: "提交处理" }));
    });
    expect(within(dialog).getByRole("button", { name: "提交中..." })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(12_000);
    });

    expect(within(dialog).getByText("异常处理提交超时")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "提交处理" })).toBeEnabled();
    expect(onApplied).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  test("renders income-side OA data anomaly without a misleading closed action button", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(dataAnomalyPreview)));

    renderModal({ rows: defaultRows });

    const dialog = await screen.findByRole("dialog", { name: "统一异常处理" });
    expect(within(dialog).getByText("数据异常")).toBeInTheDocument();
    expect(within(dialog).getByText("收入侧出现 OA 数据异常")).toBeInTheDocument();
    expect(within(dialog).getByText("收入侧不应混入 OA，请修正分类或选择范围。")).toBeInTheDocument();
    expect(within(dialog).getByRole("radio", { name: /修正分类后重判/ })).toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "确认闭环" })).not.toBeInTheDocument();
    expect(within(dialog).queryByText("处理后闭环")).not.toBeInTheDocument();
  });
});

function renderModal({
  rows,
  onApplied = () => undefined,
  onClose = () => undefined,
}: {
  rows: WorkbenchRecord[];
  onApplied?: (result: unknown) => void;
  onClose?: () => void;
}) {
  return render(
    <MuiProviders>
      <SessionContext.Provider value={sessionValue}>
        <PageSessionStateProvider>
          <WorkbenchExceptionModal
            month="all"
            rows={rows}
            onApplied={onApplied}
            onClose={onClose}
          />
        </PageSessionStateProvider>
      </SessionContext.Provider>
    </MuiProviders>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function buildRow(overrides: Partial<WorkbenchRecord>): WorkbenchRecord {
  return {
    id: "row",
    recordType: "oa",
    label: "row",
    status: "待处理",
    statusCode: "pending",
    statusTone: "warn",
    exceptionHandled: false,
    amount: "0.00",
    counterparty: "counterparty",
    tableValues: {},
    detailFields: [],
    actionVariant: "detail-only",
    availableActions: [],
    ...overrides,
  };
}

function sessionStorageKeys() {
  return Array.from({ length: window.sessionStorage.length }, (_, index) => window.sessionStorage.key(index) ?? "");
}

const defaultRows: WorkbenchRecord[] = [
  buildRow({ id: "oa-1", recordType: "oa", amount: "100000.00" }),
  buildRow({ id: "bank-1", recordType: "bank", amount: "100000.00" }),
  buildRow({ id: "invoice-1", recordType: "invoice", amount: "0.00" }),
];

const expensePreview: WorkbenchExceptionPreview = {
  ruleVersion: "exception_rules_v1",
  scenario: {
    businessLine: "expense",
    scenarioCode: "expense_oa_bank_missing_invoice",
    scenarioLabel: "OA和支出流水一致，缺进项发票",
  },
  amountSummary: {
    oaTotal: "100000.00",
    bankExpenseTotal: "100000.00",
    bankIncomeTotal: "0.00",
    inputInvoiceTotal: "0.00",
    outputInvoiceTotal: "0.00",
    relation: "oa_equals_bank_missing_invoice",
  },
  automaticActions: [
    {
      actionCode: "auto_close_when_invoice_arrives",
      label: "补票后自动闭环",
      resultStatus: "closed",
      requiredFields: [],
    },
  ],
  availableActions: [
    {
      actionCode: "wait_input_invoice",
      label: "追进项发票",
      resultStatus: "open",
      requiredFields: ["note"],
    },
  ],
  warnings: [
    {
      code: "candidate_invoice_exists",
      severity: "warning",
      message: "已存在补票候选，提交前请复核发票归属。",
    },
  ],
  workflowProjection: { nextStatus: "open" },
  candidateEvidence: [
    {
      id: "candidate-1",
      label: "命中候选分组 CASE-202603-101",
      detail: "OA 与流水来自同一候选组。",
    },
  ],
  canApply: true,
};

const manualOaExemptionPreview: WorkbenchExceptionPreview = {
  ...expensePreview,
  scenario: {
    businessLine: "expense",
    scenarioCode: "expense_bank_invoice_missing_oa",
    scenarioLabel: "支出流水和进项发票一致，缺 OA",
  },
  automaticActions: [],
  availableActions: [
    {
      actionCode: "manual_oa_exempt",
      label: "人工确认免 OA",
      resultStatus: "closed",
      requiredFields: ["reason_code", "due_date", "note"],
    },
  ],
  candidateEvidence: [],
  warnings: [],
};

const dataAnomalyPreview: WorkbenchExceptionPreview = {
  ...expensePreview,
  scenario: {
    businessLine: "data_anomaly",
    scenarioCode: "income_with_oa_data_anomaly",
    scenarioLabel: "收入侧出现 OA 数据异常",
  },
  amountSummary: {
    oaTotal: "100.00",
    bankExpenseTotal: "0.00",
    bankIncomeTotal: "100.00",
    inputInvoiceTotal: "0.00",
    outputInvoiceTotal: "0.00",
    relation: "income_should_not_have_oa",
  },
  automaticActions: [],
  availableActions: [
    {
      actionCode: "fix_income_oa_classification",
      label: "修正分类后重判",
      resultStatus: "open",
      requiredFields: ["note"],
    },
  ],
  warnings: [
    {
      code: "income_oa_data_anomaly",
      severity: "error",
      message: "收入侧不应混入 OA，请修正分类或选择范围。",
    },
  ],
};

const automaticClosedPreview: WorkbenchExceptionPreview = {
  ...expensePreview,
  scenario: {
    businessLine: "expense",
    scenarioCode: "expense_all_equal_closed",
    scenarioLabel: "OA、流水、发票一致",
  },
  amountSummary: {
    oaTotal: "100000.00",
    bankExpenseTotal: "100000.00",
    bankIncomeTotal: "0.00",
    inputInvoiceTotal: "100000.00",
    outputInvoiceTotal: "0.00",
    relation: "oa_bank_invoice_equal",
  },
  automaticActions: [
    {
      actionCode: "confirm_closed",
      label: "确认支出闭环",
      resultStatus: "closed",
      requiredFields: [],
    },
  ],
  availableActions: [],
  warnings: [],
  candidateEvidence: [],
  canApply: true,
};
