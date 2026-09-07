import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import CashBooks, { initialCashBooksCriteria } from "../components/cash/CashBooks";
import { cashQueryString } from "../features/cash/api";

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
const projects = { rows: [{ id: "project-a", name: "历史项目甲" }, { id: "project-b", name: "历史项目乙" }], pagination: { ...pagination, total: 2 } };
const ticketReport = { rows: [], pagination: { ...pagination, total: 0 }, summary: { provided_amount: "0.00", used_amount: "0.00", offset_amount: "0.00", available_source_amount: "0.00", receivable_amount: "0.00", cash_received_amount: "0.00" } };
const lastParams = (path: string) => mocks.query.mock.calls.filter(([url]) => url === path).at(-1)![1] as Record<string, unknown>;
beforeEach(() => {
  mocks.query.mockReset(); mocks.reload.mockReset();
  mocks.query.mockImplementation((path: string | null) => result(path === "/reports/turnover" ? turnover : path === "/reports/project-options" ? projects : path === "/reports/ticket-payments" ? ticketReport : path === "/settings/categories" ? { rows: [{ id: "category-a", name: "借款" }, { id: "category-b", name: "费用" }], pagination: { ...pagination, total: 2 } } : path === "/reports/personal" ? { rows: [], summary: personalSummary, pagination: { ...pagination, total: 0 } } : null));
});

describe("cash books", () => {
  test("turnover rejects the 101st combined selection without replacing applied criteria", async () => {
    const user = userEvent.setup(); const initial = initialCashBooksCriteria();
    initial.turnover.filters.project_ids = Array.from({ length: 50 }, (_, i) => `p${i}`);
    initial.turnover.filters.category_ids = Array.from({ length: 50 }, (_, i) => `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`);
    render(<CashBooks initialCriteria={initial} />);
    const applied = lastParams("/reports/turnover");
    await user.click(screen.getByRole("button", { name: "筛选处理状态" }));
    const popup = await screen.findByRole("dialog", { name: "筛选处理状态" });
    await user.click(within(popup).getByRole("checkbox", { name: "未结", exact: true }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(within(popup).getByRole("alert")).toHaveTextContent("全部条件最多选择 100 项");
    expect(within(popup).getByRole("checkbox", { name: "未结", exact: true })).toBeChecked();
    expect(lastParams("/reports/turnover")).toEqual(applied);
    expect(screen.getByText("实际借款")).toBeInTheDocument();
  });

  test.each(["tickets", "personal"] as const)("%s keeps applied query and project draft when encoded criteria reach 3501 bytes", async tab => {
    const user = userEvent.setup(); const initial = initialCashBooksCriteria(); initial.tab = tab;
    const ids = Array.from({ length: 17 }, (_, i) => "p".repeat(183) + i);
    const extraId = "z".repeat(tab === "tickets" ? 94 : 122);
    if (tab === "tickets") initial.tickets.filters.project_ids = ids;
    else initial.personal.projects = ids;
    const originalQuery = mocks.query.getMockImplementation()!;
    mocks.query.mockImplementation((path, params) => path === "/reports/project-options" ? result({ rows: [{ id: extraId, name: "另一个历史项目" }], pagination: { page: 1, page_size: 49, total: 1 } }) : originalQuery(path, params));
    render(<CashBooks initialCriteria={initial} />);
    const path = tab === "tickets" ? "/reports/ticket-payments" : "/reports/personal";
    const applied = lastParams(path);
    const encoded = cashQueryString(applied as Parameters<typeof cashQueryString>[0]);
    const next = new URLSearchParams(encoded); next.set("project_ids", JSON.stringify([...ids, extraId]));
    expect(next.toString()).toHaveLength(3501);
    await user.click(screen.getByRole("button", { name: "筛选项目" }));
    const popup = await screen.findByRole("dialog", { name: "筛选项目" });
    await user.click(within(popup).getByRole("checkbox", { name: "另一个历史项目" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(within(popup).getByRole("alert")).toHaveTextContent("筛选条件过长");
    expect(within(popup).getByRole("checkbox", { name: "另一个历史项目" })).toBeChecked();
    expect(lastParams(path)).toEqual(applied);
    await user.click(within(popup).getByRole("button", { name: "清空" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(lastParams(path).project_ids).toEqual([]);
  });

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

  test("project and category filters keep top drafts separate and preserve native sorting", async () => {
    const user = userEvent.setup(); render(<CashBooks />);
    const original = lastParams("/reports/turnover");
    fireEvent.change(screen.getByLabelText("开始日期"), { target: { value: "2026-06-01" } });
    await user.type(screen.getByRole("textbox", { name: "关键词" }), "不应提交");
    await user.click(screen.getByRole("button", { name: "筛选项目" }));
    let popup = await screen.findByRole("dialog", { name: "筛选项目" });
    await user.click(within(popup).getByRole("checkbox", { name: "历史项目甲" }));
    await user.click(within(popup).getByRole("checkbox", { name: "历史项目乙" }));
    expect(lastParams("/reports/turnover")).toEqual(original);
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(lastParams("/reports/turnover")).toMatchObject({ project_ids: ["project-a", "project-b"], date_from: original.date_from, page: 1 });
    expect(lastParams("/reports/turnover").keyword).toBeUndefined();
    await user.click(screen.getByRole("button", { name: "筛选费用类型" }));
    popup = await screen.findByRole("dialog", { name: "筛选费用类型" });
    await user.click(within(popup).getByRole("checkbox", { name: "未分类" }));
    await user.click(within(popup).getByRole("checkbox", { name: "借款" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await user.click(screen.getByRole("columnheader", { name: "日期" }));
    expect(lastParams("/reports/turnover")).toMatchObject({ project_ids: ["project-a", "project-b"], category_ids: [null, "category-a"], sort: "occurred_on", order: "asc" });
    await user.click(screen.getByRole("button", { name: "重置", exact: true }));
    expect(lastParams("/reports/turnover")).toMatchObject({ sort: "occurred_on", order: "desc", page: 1 });
    expect(lastParams("/reports/turnover").project_ids).toBeUndefined();
    expect(lastParams("/reports/turnover").category_ids).toBeUndefined();
    expect(screen.getByRole("textbox", { name: "关键词" })).toHaveValue("");
  });

  test("ticket state multi-select and amount sorting use true displayed columns", async () => {
    const user = userEvent.setup(); render(<CashBooks />);
    await user.click(screen.getByRole("tab", { name: "有票支付" }));
    expect(within(screen.getByRole("grid", { name: "有票支付" })).getAllByRole("columnheader")).toHaveLength(12);
    await user.click(screen.getByRole("button", { name: "筛选使用状态" }));
    const popup = await screen.findByRole("dialog", { name: "筛选使用状态" });
    await user.click(within(popup).getByRole("checkbox", { name: "未使用", exact: true }));
    await user.click(within(popup).getByRole("checkbox", { name: "部分使用" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await user.click(screen.getByRole("columnheader", { name: "提供金额" }));
    expect(lastParams("/reports/ticket-payments")).toMatchObject({ states: ["unused", "partial"], sort: "provided_amount", page: 1 });
    await user.click(screen.getByRole("columnheader", { name: "来源可用" }));
    expect(lastParams("/reports/ticket-payments")).toMatchObject({ states: ["unused", "partial"], sort: "available_source_amount" });
  });

  test("personal matrix drilldown keeps multi-project scope and resets invalid sort across views", async () => {
    const user = userEvent.setup();
    const matrix = { row_key: "bill-a", bill_label: { id: "bill-a", bank_name: "合成银行", label: "合成账单" }, months: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, "0")}`, principal_amount: i === 0 ? "100.00" : null, item_count: i === 0 ? 1 : 0, coverage_state: "complete" })), year_principal_amount: "100.00" };
    mocks.query.mockImplementation((path, params) => result(path === "/reports/personal" ? { rows: params.view === "matrix" ? [matrix] : [], summary: personalSummary, pagination: { ...pagination, total: params.view === "matrix" ? 1 : 0 } } : path === "/reports/project-options" ? projects : path === "/items" ? { rows: [], pagination: { page: 1, page_size: 20, total: 0 } } : null));
    const initial = initialCashBooksCriteria(); initial.tab = "personal"; initial.personal.year = "2026";
    render(<CashBooks initialCriteria={initial} />);
    await user.click(screen.getByRole("button", { name: "筛选项目" }));
    const popup = await screen.findByRole("dialog", { name: "筛选项目" });
    await user.click(within(popup).getByRole("checkbox", { name: "历史项目甲" }));
    await user.click(within(popup).getByRole("checkbox", { name: "历史项目乙" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await user.click(screen.getByRole("columnheader", { name: "全年合计" }));
    expect(lastParams("/reports/personal")).toMatchObject({ project_ids: ["project-a", "project-b"], sort: "year_principal_amount" });
    await user.click(screen.getByRole("button", { name: "合成账单 2026-01 明细" }));
    expect(lastParams("/items")).toMatchObject({ project_ids: ["project-a", "project-b"], bill_label_id: "bill-a", origin_date_from: "2026-01-01", origin_date_to: "2026-01-31", is_opening: false, ledger_group: "personal", type: "loan" });
    const dialog = screen.getByRole("dialog", { name: "2026-01 实际发生本金" });
    await user.click(within(dialog).getByRole("button", { name: "关闭抽屉" }));
    await user.click(screen.getByLabelText("个人专账视图", { selector: "button" }));
    await user.click(screen.getByRole("option", { name: "现金归还" }));
    expect(lastParams("/reports/personal")).toMatchObject({ project_ids: ["project-a", "project-b"], view: "cash_repayments", sort: "occurred_on", order: "desc" });
    await user.click(screen.getByRole("columnheader", { name: "处理金额" }));
    expect(lastParams("/reports/personal").sort).toBe("amount");
    expect(mocks.query.mock.calls.some(([path]) => path === "/projects")).toBe(false);
  });
});
