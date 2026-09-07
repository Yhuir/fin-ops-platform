import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import CashBooks from "../components/cash/CashBooks";

const mocks = vi.hoisted(() => ({ query: vi.fn(), reload: vi.fn() }));
vi.mock("../features/cash/hooks", () => ({ useCashQuery: (path: string | null, params: unknown) => mocks.query(path, params), useCashMutation: () => ({ run: vi.fn(), busy: false, error: null, clearError: vi.fn() }) }));
vi.mock("../components/cash/CashFlowDrawer", () => ({ CashFlowDrawer: () => <p>统一现金录入</p> }));
const pagination = { page: 1, page_size: 50, total: 3 };
const rowBase = { row_kind: "principal", ledger_group: "personal", personal_variant: "principal", occurred_on: "2026-01-01", item_id: "item-a", counterparty: "测试人员", project: null, content: "实际借款", state: "partial", original_amount: "12000.00", repayment_amount: null, reimbursement_received_amount: null, ticket_offset_amount: null, non_ticket_offset_amount: null, real_expense_amount: null, cash_received_amount: null, cash_paid_amount: "12000.00", remaining_after_event: "12000.00", flow_id: "flow-a", settlement_id: null, expense_item_id: null, category: { id: "category-a", name: "借款", group: "turnover" }, remark: null, ticket_collection_state: null };
const turnover = {
  rows: [{ ...rowBase, row_id: "principal-a" }, { ...rowBase, row_id: "settlement-b", row_kind: "settlement", personal_variant: "settlement", occurred_on: "2026-01-02", content: "第一次归还", original_amount: null, repayment_amount: "3000.00", cash_received_amount: "3000.00", cash_paid_amount: null, remaining_after_event: "9000.00" }, { ...rowBase, row_id: "settlement-c", row_kind: "settlement", personal_variant: "settlement", occurred_on: "2026-01-03", content: "第二次归还", original_amount: null, repayment_amount: "2500.00", cash_received_amount: "2500.00", cash_paid_amount: null, remaining_after_event: "6500.00" }], pagination,
  summary: { cash_received_amount: "5500.00", cash_paid_amount: "12000.00", non_ticket_offset_amount: "0.00", repayment_amount: "5500.00", reimbursement_received_amount: "0.00", real_expense_amount: "0.00", ticket_offset_amount: "0.00", remaining_obligation_amount: { receivable: "6500.00", payable: "0.00" } },
};
const personalSummary = { coverage: { state: "unconfigured", opening_date: null, coverage_start: null }, opening_obligation_amount: null, opening_adjustment_amount: null, new_principal_amount: null, cash_repayment_amount: null, ticket_offset_amount: null, non_ticket_offset_amount: null, remaining_obligation_amount: null };
function result(data: unknown, options = {}) { return { data, loading: false, error: null, reload: mocks.reload, ...options }; }
beforeEach(() => {
  mocks.query.mockReset(); mocks.reload.mockReset();
  mocks.query.mockImplementation((path: string | null) => result(path === "/reports/turnover" ? turnover : path === "/reports/personal" ? { rows: [], summary: personalSummary, pagination: { ...pagination, total: 0 } } : null));
});

describe("cash books", () => {
  test("defaults to the 17-column total, preserving each event's remaining balance and row category", () => {
    render(<CashBooks />);
    const table = screen.getByRole("grid", { name: "往来账总表" });
    expect(within(table).getAllByRole("columnheader")).toHaveLength(17);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(rows[0]).toHaveClass("cash-row--personal-principal"); expect(rows[1]).toHaveClass("cash-row--personal-settlement");
    expect(within(rows[0]).getAllByRole("gridcell")[13]).toHaveTextContent("12,000.00");
    expect(within(rows[1]).getAllByRole("gridcell")[13]).toHaveTextContent("9,000.00");
    expect(within(rows[2]).getAllByRole("gridcell")[13]).toHaveTextContent("6,500.00");
    expect(new Set(mocks.query.mock.calls.filter(([path]) => path !== null).map(([path]) => path))).toEqual(new Set(["/reports/turnover"]));
    expect(screen.queryByText(/行色：/)).not.toBeInTheDocument();
  });
  test("classification switch filters server-side and never just filters the current page", async () => {
    render(<CashBooks />);
    await userEvent.click(screen.getByRole("button", { name: "个人归还 / 冲抵" }));
    expect(mocks.query.mock.calls).toContainEqual(["/reports/turnover", expect.objectContaining({ ledger_group: "personal", personal_variant: "settlement", page: 1, page_size: 50 })]);
  });
  test("error does not display stale successful totals or a made-up zero", () => {
    mocks.query.mockImplementation((path: string | null) => result(path === "/reports/turnover" ? turnover : null, path === "/reports/turnover" ? { error: { message: "现金查询超时" } } : {}));
    render(<CashBooks />);
    expect(screen.getByRole("alert")).toHaveTextContent("现金查询超时");
    expect(within(screen.getByRole("grid", { name: "往来账总表" })).getAllByRole("columnheader")).toHaveLength(17);
    expect(screen.queryByText("实际借款")).not.toBeInTheDocument();
    expect(screen.queryByText("5,500.00")).not.toBeInTheDocument();
  });
  test("books contain only three ledgers and no duplicate generic cash entry", () => {
    render(<CashBooks />);
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.queryByRole("tab", { name: "现金流水" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增流水" })).not.toBeInTheDocument();
  });
  test("personal unconfigured coverage remains unknown and only fetches the active view", async () => {
    render(<CashBooks />);
    await userEvent.click(screen.getByRole("tab", { name: "个人专账" }));
    expect(screen.getByText(/个人账起算未配置/)).toBeInTheDocument();
    expect(screen.queryByText("0.00")).not.toBeInTheDocument();
    expect(mocks.query.mock.calls).toContainEqual(["/reports/personal", expect.objectContaining({ view: "matrix", page_size: 50 })]);
    await userEvent.click(screen.getByLabelText("个人专账视图", { selector: "button" }));
    await userEvent.click(screen.getByRole("option", { name: "无票报销冲抵" }));
    expect(mocks.query.mock.calls).toContainEqual(["/reports/personal", expect.objectContaining({ view: "non_ticket_offsets" })]);
    expect(mocks.query.mock.calls.some(([path]) => path === "/projects")).toBe(false);
  });
  test("date search keeps sensitive keyword in local query state, not browser location", async () => {
    const location = window.location.href; render(<CashBooks />);
    await userEvent.type(screen.getByRole("textbox", { name: "关键词" }), "测试私密内容");
    await userEvent.click(screen.getByRole("button", { name: "查询", exact: true }));
    expect(mocks.query.mock.calls).toContainEqual(["/reports/turnover", expect.objectContaining({ keyword: "测试私密内容", page: 1 })]);
    expect(window.location.href).toBe(location);
  });
});
