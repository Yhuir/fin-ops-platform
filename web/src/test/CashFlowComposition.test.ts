import { describe, expect, test } from "vitest";
import { flowCompositionPayload, newFlowPart } from "../components/cash/CashFlowComposition";
import type { CashItem } from "../components/cash/CashItems.types";

describe("cash composite entry", () => {
  test("plain cash explicitly creates no inferred loans or expenses", () => {
    expect(flowCompositionPayload([], "2026-09-07", null, "receipt")).toEqual({ related_items: [], origin_items: [], allocations: [] });
  });
  test("preserves stable identities and exact amounts across retries", () => {
    const expense = { ...newFlowPart("expense", "payment"), amount: "1234567890123456.78", content: "实际材料费", category: "payment-category" };
    const first = flowCompositionPayload([expense], "2026-09-07", "project-a", "payment");
    expect(flowCompositionPayload([expense], "2026-09-07", "project-a", "payment")).toEqual(first);
    expect(first.related_items[0]).toMatchObject({ id: expense.id, original_amount: "1234567890123456.78", oa_project_id: "project-a", category_id: "payment-category" });
    expect(first.allocations).toEqual([]);
  });
  test("existing-item cash allocation carries real target version and does not recreate obligation", () => {
    const item = { id: "real-item", version: 7, type: "loan" } as CashItem;
    const part = { ...newFlowPart("settlement", "receipt", item), amount: "10.50" };
    const result = flowCompositionPayload([part], "2026-09-07", "historical-project", "receipt");
    expect(result.related_items).toEqual([]); expect(result.origin_items).toEqual([]);
    expect(result.allocations).toEqual([{ id: part.id, item_id: item.id, expected_item_version: 7, target_is_new: false, kind: "cash_repayment", amount: "10.50" }]);
  });
  test.each(["", "0", "-2", "1.001", "1e2"])("does not round or invent invalid amount %s", amount => {
    expect(() => flowCompositionPayload([{ ...newFlowPart("expense", "payment"), amount, content: "费用" }], "2026-09-07", null, "payment")).toThrow();
  });
  test("does not create a new expense on a refund receipt", () => {
    expect(() => flowCompositionPayload([{ ...newFlowPart("expense", "receipt"), amount: "3", content: "退款" }], "2026-09-07", null, "receipt")).toThrow("请选择已有费用");
  });
  test("requires explicit loan classification and paired bill fields", () => {
    const loan = { ...newFlowPart("loan", "payment"), amount: "1", content: "代付" };
    expect(() => flowCompositionPayload([loan], "2026-09-07", null, "payment")).toThrow("账簿分类");
    expect(() => flowCompositionPayload([{ ...loan, counterparty: "对方", group: "personal", direction: "receivable", billLabel: "bill" }], "2026-09-07", null, "payment")).toThrow("同时填写");
  });
  test("personal loans cannot use the payable direction", () => {
    const loan = { ...newFlowPart("loan", "payment"), amount: "10", content: "代付", counterparty: "个人", group: "personal", direction: "payable" };
    expect(() => flowCompositionPayload([loan], "2026-09-07", null, "payment")).toThrow("只能登记对方应归还");
  });
  test("links an expense to an explicitly selected same-flow loan without another payment", () => {
    const loan = { ...newFlowPart("loan", "payment"), amount: "10", content: "借款", counterparty: "公司", group: "company", direction: "receivable" };
    const expense = { ...newFlowPart("expense", "payment"), amount: "10", content: "费用", category: "payment-category", relatedLoanId: loan.id };
    const result = flowCompositionPayload([expense, loan], "2026-09-07", null, "payment");
    expect(result.related_items[0]).toMatchObject({ related_obligation_id: loan.id });
    expect(result.allocations).toEqual([]);
    expect(() => flowCompositionPayload([expense], "2026-09-07", null, "payment")).toThrow("已被移除");
  });
  test("noncash expense classification is explicit, not inferred from content", () => {
    expect(() => flowCompositionPayload([{ ...newFlowPart("expense", "payment"), amount: "3", content: "材料费用" }], "2026-09-07", null, "payment")).toThrow("费用类型");
  });
});
