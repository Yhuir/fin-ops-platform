import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { installMockApiFetch } from "./apiMock";
import { renderAppAt } from "./renderHelpers";
import { waitForOperationFreshness } from "../features/operationBarrier/api";

vi.mock("../features/operationBarrier/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../features/operationBarrier/api")>();
  return {
    ...actual,
    waitForOperationFreshness: vi.fn(async (targets: Array<{ readModelKey: string; scopeKey: string }>) => {
      const target = targets[0] ?? { readModelKey: "pending_invoice", scopeKey: "all" };
      throw new actual.OperationBarrierTimeoutError(
        `操作同步等待超时，待处理发票（${target.scopeKey}）仍在同步，请稍后刷新后重试。`,
        {
          status: "refreshing",
          fresh: false,
          targets: [],
          blockedTargets: [],
          refreshingTargets: [{
            readModelKey: target.readModelKey,
            scopeType: target.readModelKey,
            scopeKey: target.scopeKey,
            status: "refreshing",
            fresh: false,
            blocking: false,
            rawStatus: "dirty",
          }],
        },
      );
    }),
  };
});

function pendingInvoiceRow(direction: "expense" | "income") {
  const isIncome = direction === "income";
  return {
    id: isIncome ? "income-timeout-row" : "expense-timeout-row",
    bank_transaction: {
      id: isIncome ? "income-timeout-row" : "expense-timeout-row",
      counterparty_name: isIncome ? "收入客户" : "支出供应商",
      trade_time: "2026-06-18T10:00:00+08:00",
      booked_date: "2026-06-18",
      debit_amount: isIncome ? "0.00" : "1200.00",
      credit_amount: isIncome ? "1200.00" : "0.00",
      balance: "1200.00",
      currency: "人民币元",
      bank_name: "建设银行",
      bank_short_name: "建行",
      account_name: "测试账户",
      account_last4: "8106",
      summary: isIncome ? "服务收款" : "采购付款",
      remark: "",
      statement_serial_no: isIncome ? "income-timeout-stmt" : "expense-timeout-stmt",
      enterprise_serial_no: isIncome ? "income-timeout-ent" : "expense-timeout-ent",
      effective_tag_code: isIncome ? "service_income" : "fee",
      effective_tag_label: isIncome ? "服务收入" : "手续费",
      effective_tag_primary_label: isIncome ? "收入" : "费用",
      effective_tag_sub_label: isIncome ? "服务收入" : "手续费",
      effective_tag_label_path: isIncome ? ["收入", "服务收入"] : ["费用", "手续费"],
    },
    invoice_acquisition_status: {
      code: isIncome ? "income_pending_invoice" : "paid_pending_invoice",
      label: isIncome ? "收入待开票" : "已支付待开票",
      reason: "规则刷新超时回归测试",
      severity: "warning",
      primary_action: "view_rules",
      matched_rule: {
        source: isIncome ? "pending_output_invoice_tag_groups" : "pending_invoice_tag_groups",
        group: "requires_invoice",
        tag_code: isIncome ? "service_income" : "fee",
        tag_label: isIncome ? "服务收入" : "手续费",
      },
    },
    input_invoices: { primary: null, relation_count: 0, has_multiple: false, summaries: [], payment_summary: null },
    invoices: [],
    oa: { primary: null, relation_count: 0, has_multiple: false, detail_available: false, summaries: [] },
    can_create_invoice: !isIncome,
    available_actions: ["view_rules"],
  };
}

function rulesPayload(direction: "expense" | "income") {
  const isIncome = direction === "income";
  return {
    version: isIncome ? 12 : 7,
    direction,
    permissions: { can_save: true },
    bank_transaction_tags: {
      version: 4,
      tags: [
        { code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" },
        { code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" },
        { code: "service_income", label: "服务收入", status: "active", output_primary_label: "收入", output_sub_label: "服务收入" },
        { code: "cash", label: "现金", status: "active", output_primary_label: "收入", output_sub_label: "现金" },
      ],
    },
    groups: isIncome
      ? {
        requires_invoice: { tag_codes: ["service_income"], tags: [{ code: "service_income", label: "服务收入", status: "active", output_primary_label: "收入", output_sub_label: "服务收入" }] },
        no_invoice_required: { tag_codes: [], tags: [] },
        cash_income: { tag_codes: ["cash"], tags: [{ code: "cash", label: "现金", status: "active", output_primary_label: "收入", output_sub_label: "现金" }] },
      }
      : {
        requires_invoice: { tag_codes: ["fee"], tags: [{ code: "fee", label: "手续费", status: "active", output_primary_label: "费用", output_sub_label: "手续费" }] },
        bank_statement_as_invoice: { tag_codes: [], tags: [] },
        no_invoice_required: { tag_codes: ["salary"], tags: [{ code: "salary", label: "工资", status: "active", output_primary_label: "薪酬", output_sub_label: "工资" }] },
      },
  };
}

function installPendingInvoiceRulesSaveFetch() {
  const baseFetch = installMockApiFetch();
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    if (url.pathname === "/api/pending-invoices/rows") {
      const direction = (url.searchParams.get("direction") === "income" ? "income" : "expense") as "expense" | "income";
      const rows = [pendingInvoiceRow(direction)];
      return new Response(JSON.stringify({
        direction,
        filter: url.searchParams.get("filter") ?? "all",
        rows,
        pagination: { page: 1, page_size: 50, total: rows.length },
        summary: {
          total_rows: rows.length,
          missing_invoice_rows: rows.length,
          create_invoice_available_rows: direction === "expense" ? rows.length : 0,
          source_summary: {
            bank_transaction_rows: rows.length,
            expense_rows: direction === "expense" ? rows.length : 0,
            income_rows: direction === "income" ? rows.length : 0,
            current_direction_rows: rows.length,
            excluded_direction_rows: 0,
          },
        },
        tag_dictionary: { version: 4, tags: [] },
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/filter-options") {
      return new Response(JSON.stringify({ fields: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    if (url.pathname === "/api/pending-invoices/rules") {
      const direction = (url.searchParams.get("direction") === "income" ? "income" : "expense") as "expense" | "income";
      return new Response(JSON.stringify({
        ...rulesPayload(direction),
        ...(method === "PUT" ? { version: direction === "income" ? 13 : 8 } : {}),
      }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return baseFetch(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function pendingInvoiceRulesPutRequests(fetchMock: ReturnType<typeof installPendingInvoiceRulesSaveFetch>) {
  return fetchMock.mock.calls.filter(([input, init]) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url, "http://localhost");
    return url.pathname === "/api/pending-invoices/rules" && (init?.method ?? "GET").toUpperCase() === "PUT";
  });
}

async function saveRules(buttonName: string, title: string) {
  const user = userEvent.setup();
  const page = await screen.findByTestId("pending-invoices-page", undefined, { timeout: 10_000 });
  await user.click(within(page).getByRole("button", { name: buttonName }));
  expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "保存规则" }));

  expect(await screen.findByText("规则已保存。")).toBeInTheDocument();
  expect(screen.queryByRole("dialog", { name: "全局操作进度" })).not.toBeInTheDocument();
  expect(screen.queryByText(/操作同步等待超时/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "关闭规则抽屉" }));
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("pending invoice rule save convergence", () => {
  test("saves expense and income rules without a write-time freshness barrier", async () => {
    const fetchMock = installPendingInvoiceRulesSaveFetch();
    renderAppAt("/pending-invoices");

    await saveRules("支出待找发票规则设置", "支出待找发票规则设置");
    await waitFor(() => {
      expect(pendingInvoiceRulesPutRequests(fetchMock)).toHaveLength(1);
    });
    expect(waitForOperationFreshness).not.toHaveBeenCalled();

    await saveRules("收入待找发票规则设置", "收入待找发票规则设置");
    await waitFor(() => {
      expect(pendingInvoiceRulesPutRequests(fetchMock)).toHaveLength(2);
    });
    expect(waitForOperationFreshness).not.toHaveBeenCalled();
  }, 30_000);
});
