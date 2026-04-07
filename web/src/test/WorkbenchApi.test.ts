import { afterEach, describe, expect, test, vi } from "vitest";

import { fetchWorkbench } from "../features/workbench/api";

describe("workbench api bank amount mapping", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("maps inflow bank rows into the unified amount column from credit_amount", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          month: "2026-03",
          summary: {
            oa_count: 0,
            bank_count: 1,
            invoice_count: 0,
            paired_count: 0,
            open_count: 1,
            exception_count: 0,
          },
          paired: { groups: [] },
          open: {
            groups: [
              {
                group_id: "CASE-202603-900",
                group_type: "candidate",
                match_confidence: "medium",
                reason: "收入流水待确认",
                oa_rows: [],
                bank_rows: [
                  {
                    id: "bk-income-001",
                    type: "bank",
                    trade_time: "2026-03-20 16:05:40",
                    direction: "收入",
                    debit_amount: "",
                    credit_amount: "6,000.00",
                    counterparty_name: "云南溯源科技有限公司",
                    payment_account_label: "建设银行 8106",
                    invoice_relation: { code: "manual_review", label: "待人工核查", tone: "danger" },
                    pay_receive_time: "2026-03-20 16:05:40",
                    remark: "收入待核查",
                    repayment_date: "",
                    available_actions: ["detail"],
                  },
                ],
                invoice_rows: [],
              },
            ],
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    const payload = await fetchWorkbench("2026-03");
    const bankRow = payload.open.groups[0].rows.bank[0];

    expect(bankRow.tableValues.amount).toBe("6,000.00");
    expect(bankRow.amount).toBe("6,000.00");
    expect(bankRow.tableValues.direction).toBe("收入");
  });
});
