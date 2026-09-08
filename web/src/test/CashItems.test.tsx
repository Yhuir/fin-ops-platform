import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { CashItemDetail, CashItemEditor, CashItemPicker, CashSettlementEditor, CashSettlementTable } from "../components/cash/CashItems";
import { cashAmount, cashMoneyInput, settlementVersions, type CashItem, type CashSettlement } from "../components/cash/CashItems.types";

const mocks = vi.hoisted(() => ({ query: vi.fn(), run: vi.fn(), reload: vi.fn() }));
vi.mock("../features/cash/hooks", () => ({
  useCashQuery: (path: string | null, params?: unknown) => mocks.query(path, params),
  useCashMutation: () => ({ run: mocks.run, busy: false, error: null, clearError: vi.fn() }),
}));
const pagination = { page: 1, page_size: 20, total: 1 };
const target: CashItem = {
  id: "00000000-0000-4000-8000-000000000001", version: 7, type: "loan", origin_date: "2026-01-01", original_amount: "12000.00", is_opening: false,
  obligation_direction: "receivable", ledger_group: "personal", counterparty: "测试人员", oa_project_id: null, project_name_snapshot: null, project: null,
  origin_flow_id: null, origin_mode: null, bill_label_id: null, bill_month: null, ticket_provider: null, ticket_provided_on: null, ticket_description: null,
  related_obligation_id: null, ticket_source_id: null, content: "历史真实借款", remark: null, selectable: true, remaining_obligation_amount: "9000.00",
  category_id: null, category: null,
};
const settlement: CashSettlement = {
  id: "00000000-0000-4000-8000-000000000020", version: 4, kind: "ticket_use", occurred_on: "2026-08-01", amount: "3000.00", remark: "实际用于支付",
  item_id: null, item_version: null, item_content: null, source_item_id: "00000000-0000-4000-8000-000000000003", source_item_version: 9,
  source_item_content: "测试票据", flow_id: null, flow_version: null, flow_source_kind: null, task: null,
  category_id: null, category: null,
};
function result(data: unknown, options = {}) { return { data, loading: false, error: null, reload: mocks.reload, ...options }; }

beforeEach(() => {
  mocks.query.mockReset(); mocks.run.mockReset(); mocks.reload.mockReset(); mocks.run.mockResolvedValue({ version: 1 });
  mocks.query.mockImplementation((path: string | null) => result(path === null ? null : { rows: [], pagination: { ...pagination, total: 0 } }));
});

describe("cash amount presentation", () => {
  test("preserves exact large decimal strings and distinguishes unknown from zero", () => {
    expect(cashAmount("9007199254740993.12")).toBe("9,007,199,254,740,993.12");
    expect(cashAmount(null)).toBe("—"); expect(cashAmount("0.00")).toBe("0.00");
    expect(cashAmount("-2500.5")).toBe("-2,500.50");
    expect(() => cashAmount(undefined as unknown as string)).toThrow();
  });
  test("normalizes explicit positive user amounts without rounding or guessing", () => {
    expect(cashMoneyInput(" 0012.3 ")).toBe("12.30");
    for (const value of ["", "0", "0.00", "-2.00", "1.001", "1e3", "1,000.00"]) expect(() => cashMoneyInput(value)).toThrow();
  });
  test("carries exact versions of all referenced objects without duplicated item IDs", () => {
    expect(settlementVersions({ ...settlement, item_id: settlement.source_item_id, item_version: 9 })).toEqual({ items: [{ id: settlement.source_item_id, version: 9 }], flows: [], occurrences: [] });
  });
});

describe("cash item and settlement interaction", () => {
  test("personal opening takes explicit owner and opening date instead of company and today", async () => {
    render(<CashItemEditor initialType="loan" opening personalContext={{ counterparty: "测试个人", opening_date: "2026-01-01" }} onClose={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: "往来对象" })).toHaveValue("测试个人");
    expect(screen.getByLabelText("起算日期 *")).toHaveValue("2026-01-01");
    await userEvent.type(screen.getByRole("textbox", { name: "期初未结金额" }), "123");
    await userEvent.type(screen.getByRole("textbox", { name: "事项内容" }), "期初欠款");
    await userEvent.click(screen.getByRole("button", { name: "保存事项" }));
    expect(mocks.run).toHaveBeenCalledWith("/items", expect.objectContaining({ ledger_group: "personal", counterparty: "测试个人", origin_date: "2026-01-01" }), "POST");
  });
  test("shows error and retries without manufacturing an empty item", async () => {
    mocks.query.mockReturnValue(result(null, { error: { message: "事项已删除" } }));
    render(<CashItemDetail itemId={target.id} onClose={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("事项已删除");
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "重新读取" })); expect(mocks.reload).toHaveBeenCalledOnce();
  });
  test("new opening item sends explicit obligation fields and does not query OA until requested", async () => {
    const close = vi.fn(); render(<CashItemEditor initialType="loan" opening onClose={close} />);
    await userEvent.type(screen.getByRole("textbox", { name: "期初未结金额" }), "12000");
    await userEvent.type(screen.getByRole("textbox", { name: "往来对象" }), "测试公司");
    await userEvent.type(screen.getByRole("textbox", { name: "事项内容" }), "已存在的旧未结");
    await userEvent.click(screen.getByRole("button", { name: "保存事项" }));
    await waitFor(() => expect(mocks.run).toHaveBeenCalledOnce());
    expect(mocks.run).toHaveBeenCalledWith("/items", expect.objectContaining({ is_opening: true, original_amount: "12000.00", ledger_group: "company", obligation_direction: "receivable", oa_project_id: null, ticket_provider: null }), "POST");
    expect(mocks.query.mock.calls.some(([path]) => path === "/projects")).toBe(false); expect(close).toHaveBeenCalledOnce();
  });
  test("invalid amount preserves the form and does not send a command", async () => {
    render(<CashItemEditor onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: "原始金额" }), "1.001");
    await userEvent.type(screen.getByRole("textbox", { name: "往来对象" }), "测试对象");
    await userEvent.type(screen.getByRole("textbox", { name: "事项内容" }), "测试事项");
    await userEvent.click(screen.getByRole("button", { name: "保存事项" }));
    expect(screen.getByRole("alert")).toHaveTextContent("最多两位小数"); expect(mocks.run).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "原始金额" })).toHaveValue("1.001");
  });
  test("unsaved item edits require an explicit discard and do not write", async () => {
    const close = vi.fn(); render(<CashItemEditor onClose={close} />);
    await userEvent.type(screen.getByRole("textbox", { name: "事项内容" }), "未保存内容");
    await userEvent.click(screen.getByRole("button", { name: "取消", exact: true }));
    expect(close).not.toHaveBeenCalled(); expect(screen.getByRole("alert")).toHaveTextContent("未保存的事项内容");
    await userEvent.click(screen.getByRole("button", { name: "继续填写" })); expect(screen.getByRole("textbox", { name: "事项内容" })).toHaveValue("未保存内容");
    await userEvent.click(screen.getByRole("button", { name: "取消", exact: true })); await userEvent.click(screen.getByRole("button", { name: "放弃并关闭" }));
    expect(close).toHaveBeenCalledOnce(); expect(mocks.run).not.toHaveBeenCalled();
  });
  test("a failed write keeps user input and does not claim success", async () => {
    mocks.run.mockResolvedValue(null);
    const close = vi.fn(); render(<CashItemEditor item={target} onClose={close} />);
    await userEvent.type(screen.getByRole("textbox", { name: "备注" }), "保留此更正输入");
    await userEvent.click(screen.getByRole("button", { name: "保存事项" }));
    expect(mocks.run).toHaveBeenCalledOnce(); expect(close).not.toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "备注" })).toHaveValue("保留此更正输入");
  });
  test("editing preserves the originally opened version instead of silently rebasing a stale draft", async () => {
    const close = vi.fn(); const view = render(<CashItemEditor item={target} onClose={close} />);
    await userEvent.type(screen.getByRole("textbox", { name: "备注" }), "旧版本上的更正");
    view.rerender(<CashItemEditor item={{ ...target, version: 8 }} onClose={close} />);
    await userEvent.click(screen.getByRole("button", { name: "保存事项" }));
    expect(mocks.run).toHaveBeenCalledWith(`/items/${target.id}`, expect.objectContaining({ expected_version: 7 }), "PUT");
  });
  test("ticket use changes to offset on the original ID, preserving usage and both item versions", async () => {
    mocks.query.mockImplementation((path: string | null) => result(path === "/items" ? { rows: [target], pagination } : null));
    render(<CashSettlementEditor settlement={settlement} initialKind="ticket_use" onClose={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /处理类型$/ }));
    await userEvent.click(screen.getByRole("option", { name: "票据抵债" }));
    await userEvent.click(screen.getByRole("button", { name: "选择目标" }));
    await userEvent.click(within(screen.getByRole("grid", { name: "选择目标事项" })).getByRole("button", { name: "选择" }));
    await userEvent.click(screen.getByRole("button", { name: "保存处理" }));
    await waitFor(() => expect(mocks.run).toHaveBeenCalledOnce());
    expect(mocks.run).toHaveBeenCalledWith(`/settlements/${settlement.id}`, expect.objectContaining({ kind: "ticket_offset", item_id: target.id, source_item_id: settlement.source_item_id, amount: "3000.00", expected_version: 4, expected_related_versions: { items: [{ id: settlement.source_item_id, version: 9 }, { id: target.id, version: 7 }], flows: [], occurrences: [] } }), "PUT");
    expect(mocks.query.mock.calls.some(([path]) => path === "/flows")).toBe(false);
  });
  test("noncash adjustment requires an explicit target and explanation without cash", async () => {
    mocks.query.mockImplementation((path: string | null) => result(path === "/settings/categories" ? { rows: [{ id: "adjustment-category", name: "明确调整", group: "turnover" }], pagination } : null));
    render(<CashSettlementEditor target={target} initialKind="non_ticket_offset" onClose={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: "本次处理金额" }), "2500");
    await userEvent.type(screen.getByRole("textbox", { name: "用途 / 说明" }), "已确认的非现金冲抵");
    await userEvent.click(screen.getByRole("button", { name: "保存处理" }));
    expect(mocks.run).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /无来源调整分类$/ }));
    await userEvent.click(screen.getByRole("option", { name: "明确调整" }));
    await userEvent.click(screen.getByRole("button", { name: "保存处理" }));
    expect(mocks.run).toHaveBeenCalledWith("/settlements", expect.objectContaining({ kind: "non_ticket_offset", amount: "2500.00", item_id: target.id, expected_item_version: 7, source_item_id: null, flow_id: null, category_id: "adjustment-category" }), "POST");
  });
  test("removing an erroneous association uses its versions, not the cash delete route", async () => {
    const cashRow = { ...settlement, kind: "cash_repayment" as const, item_id: target.id, item_version: 7, item_content: target.content, source_item_id: null, source_item_version: null, source_item_content: null, flow_id: "00000000-0000-4000-8000-000000000099", flow_version: 8 };
    mocks.query.mockReturnValue(result({ rows: [cashRow], pagination }));
    render(<CashSettlementTable params={{ item_id: target.id }} />);
    await userEvent.click(screen.getByRole("button", { name: "撤销关联" }));
    expect(screen.getByRole("alert")).toHaveTextContent("实际现金保留");
    await userEvent.click(screen.getByRole("button", { name: "确认撤销错误关联" }));
    expect(mocks.run).toHaveBeenCalledWith(`/settlements/${cashRow.id}/remove`, { expected_version: 4, expected_related_versions: { items: [{ id: target.id, version: 7 }], flows: [{ id: cashRow.flow_id, version: 8 }], occurrences: [] } }, "POST");
  });
  test("a disabled selector candidate cannot be selected and search is server-scoped", async () => {
    mocks.query.mockReturnValue(result({ rows: [{ ...target, selectable: false }], pagination }));
    const select = vi.fn(); render(<CashItemPicker label="选择义务" params={{ purpose: "settlement_target", settlement_kind: "ticket_offset" }} onSelect={select} />);
    expect(screen.getByRole("button", { name: "选择" })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox", { name: "选择义务" }), "另一个项目");
    await userEvent.click(screen.getByRole("button", { name: "查询" }));
    expect(mocks.query).toHaveBeenLastCalledWith("/items", expect.objectContaining({ keyword: "另一个项目", page: 1, purpose: "settlement_target" })); expect(select).not.toHaveBeenCalled();
  });
});
