import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { CashFilterPopover, CashSortMenu, CashTextFilter } from "../components/cash/CashFilters";
import { CashConfigurationFilter, CashConfigurationSelect, CashHistoricalProjectFilter } from "../components/cash/CashFlowSelectors";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTableRow } from "../components/common/FinanceTable";

const options = [{ value: "a", label: "账户甲" }, { value: "b", label: "账户乙" }, { value: null, label: "无账户" }];
const candidateQuery = vi.hoisted(() => vi.fn());
vi.mock("../features/cash/hooks", () => ({ useCashQuery: (path: string | null, params: unknown) => candidateQuery(path, params) }));
beforeEach(() => {
  candidateQuery.mockReset();
  candidateQuery.mockImplementation((path: string | null, params: { page: number; page_size: number; keyword: string }) => {
    const rows = Array.from({ length: params.page_size }, (_, index) => {
      const number = (params.page - 1) * params.page_size + index + 1;
      return { id: `candidate-${number}`, name: `选项${number}`, label: `选项${number}`, bank_name: "合成银行" };
    });
    return { data: path ? { rows, pagination: { page: params.page, page_size: params.page_size, total: params.page_size * 2 } } : null, loading: false, error: null, reload: vi.fn() };
  });
});
afterEach(() => vi.useRealTimers());
describe("现金录入配置选择", () => {
  test.each(["accounts", "categories", "bill-labels"] as const)("%s only requests enabled candidates and preserves the original saved value", async name => {
    const user = userEvent.setup();
    render(<CashConfigurationSelect name={name} label="录入配置" value="saved-value" selected={{ id: "saved-value", name: "已保存配置" }} group={name === "categories" ? "receipt" : undefined} onChange={vi.fn()} />);
    expect(candidateQuery).toHaveBeenLastCalledWith(`/settings/${name}`, expect.objectContaining({
      enabled: true, page: 1, page_size: 100, keyword: "", groups: name === "categories" ? ["receipt", "turnover"] : undefined,
    }));
    const trigger = screen.getByLabelText("录入配置", { selector: "button" });
    expect(trigger).toHaveTextContent("已保存配置（原值）");
    await user.click(trigger);
    expect(screen.getByRole("option", { name: "已保存配置（原值）", exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "全部录入配置" })).not.toBeInTheDocument();
  });

  test("empty enabled candidates retain the setup guidance", () => {
    candidateQuery.mockReturnValue({ data: { rows: [], pagination: { page: 1, page_size: 100, total: 0 } }, loading: false, error: null, reload: vi.fn() });
    render(<CashConfigurationSelect name="accounts" label="账户" value="" onChange={vi.fn()} />);
    expect(screen.getByText("暂无启用的账户，请在基础设置中添加。")).toBeInTheDocument();
  });
});
describe("现金原生筛选浮层", () => {
  test.each(["categories", "bill-labels", "projects"] as const)("%s reserves one slot for null so select-all on a full candidate page can apply", async kind => {
    const apply = vi.fn(); const user = userEvent.setup();
    render(kind === "projects"
      ? <CashHistoricalProjectFilter label="候选" value={[]} onApply={apply} scope={{ date_from: "2026-01-01", date_to: "2026-12-31" }} />
      : <CashConfigurationFilter name={kind} label="候选" value={[]} onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选候选" }));
    const popup = await screen.findByRole("dialog", { name: "筛选候选" });
    expect(within(popup).getAllByRole("checkbox")).toHaveLength(50);
    expect(candidateQuery.mock.calls.filter(([path]) => path !== null).at(-1)?.[1]).toMatchObject({ page_size: 49, page: 1 });
    expect(within(popup).getByText("显示 1-49 / 98")).toBeInTheDocument();
    await user.click(within(popup).getByRole("button", { name: "全选本页" }));
    expect(within(popup).getByRole("button", { name: "应用" })).toBeEnabled();
    expect(within(popup).queryByRole("alert")).not.toBeInTheDocument();
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(apply).toHaveBeenCalledOnce();
    expect(apply.mock.calls[0][0]).toHaveLength(50);
    expect(apply.mock.calls[0][0]).toEqual([null, ...Array.from({ length: 49 }, (_, index) => `candidate-${index + 1}`)]);
  });

  test("account candidates still use all 50 resource slots without an invented null option", async () => {
    const apply = vi.fn(); const user = userEvent.setup();
    render(<CashConfigurationFilter name="accounts" label="账户" value={[]} onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    expect(screen.getAllByRole("checkbox")).toHaveLength(50);
    expect(candidateQuery.mock.calls.filter(([path]) => path !== null).at(-1)?.[1]).toMatchObject({ page_size: 50 });
    await user.click(screen.getByRole("button", { name: "全选本页" }));
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(apply.mock.calls[0][0]).toHaveLength(50);
    expect(apply.mock.calls[0][0]).not.toContain(null);
  });

  test("opening and quickly paging does not later reset page; a changed search resets after debounce", () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    render(<CashHistoricalProjectFilter label="项目" value={[]} onApply={vi.fn()} scope={{ date_from: "2026-01-01", date_to: "2026-12-31" }} />);
    fireEvent.click(screen.getByRole("button", { name: "筛选项目" }));
    fireEvent.click(screen.getByText("下一页"));
    const latest = () => candidateQuery.mock.calls.filter(([path]) => path !== null).at(-1)![1];
    expect(latest()).toMatchObject({ page: 2, page_size: 49, keyword: "" });
    act(() => vi.advanceTimersByTime(300));
    expect(latest()).toMatchObject({ page: 2, keyword: "" });
    expect(screen.getByText("显示 50-98 / 98")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "搜索项目选项" }), { target: { value: "新项目" } });
    expect(latest()).toMatchObject({ page: 2, keyword: "" });
    act(() => vi.advanceTimersByTime(250));
    expect(latest()).toMatchObject({ page: 1, keyword: "新项目" });
    fireEvent.click(screen.getByText("下一页"));
    act(() => vi.advanceTimersByTime(300));
    expect(latest()).toMatchObject({ page: 2, keyword: "新项目" });
  });

  test("owner rejects an over-limit combined query without closing the draft, which can be corrected", async () => {
    const apply = vi.fn().mockReturnValueOnce("全部条件最多选择 100 项。").mockReturnValueOnce(null);
    const user = userEvent.setup();
    render(<CashFilterPopover label="账户" value={["a"]} options={options} onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    await user.click(screen.getByRole("checkbox", { name: "账户乙" }));
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(screen.getByRole("dialog", { name: "筛选账户" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("全部条件最多选择 100 项");
    expect(screen.getByRole("checkbox", { name: "账户乙" })).toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "账户乙" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(apply).toHaveBeenLastCalledWith(["a"], [options[0]]);
  });

  test("text filter keeps an invalid combined query draft open and clears its error on edit", async () => {
    const apply = vi.fn().mockReturnValueOnce("筛选条件过长，请减少选择项。").mockReturnValueOnce(null);
    const user = userEvent.setup();
    render(<CashTextFilter label="人员" value="原姓名" onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选人员" }));
    const input = screen.getByRole("textbox", { name: "人员精确名称" });
    await user.type(input, "较长的草稿");
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(screen.getByRole("alert")).toHaveTextContent("筛选条件过长");
    expect(input).toHaveValue("原姓名较长的草稿");
    expect(screen.getByRole("dialog", { name: "筛选人员" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "清空" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(apply).toHaveBeenLastCalledWith("");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("draft selection is cancelled by Escape; a new open restores applied values", async () => {
    const apply = vi.fn(); const user = userEvent.setup();
    render(<CashFilterPopover label="账户" value={["a"]} options={options} onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    await user.click(screen.getByRole("checkbox", { name: "账户乙" }));
    expect(apply).not.toHaveBeenCalled();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "筛选账户" })).toHaveFocus());
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    expect(screen.getByRole("checkbox", { name: "账户甲" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "账户乙" })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: "无账户" }));
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(apply).toHaveBeenCalledTimes(1); expect(apply).toHaveBeenCalledWith(["a", null], [options[0], options[2]]);
  });
  test("empty selection explicitly removes restrictions and paged select-all is bounded to current candidates", async () => {
    const apply = vi.fn(); const user = userEvent.setup();
    render(<CashFilterPopover label="账户" value={[]} options={options} onApply={apply} page={1} total={120} onPageChange={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    await user.click(screen.getByRole("button", { name: "全选本页" }));
    expect(screen.getAllByRole("checkbox").every(input => (input as HTMLInputElement).checked)).toBe(true);
    await user.click(screen.getByRole("button", { name: "清空" }));
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(apply).toHaveBeenCalledTimes(1); expect(apply).toHaveBeenCalledWith([], []);
  });
  test("column checkbox does not inherit table row selection or trigger column sorting", async () => {
    const apply = vi.fn(), sort = vi.fn(); const user = userEvent.setup();
    render(<FinanceTable ariaLabel="表格" onSortChange={sort}><FinanceTableHeader><FinanceTableColumn id="name" isRowHeader allowsSorting>名称<CashFilterPopover column label="名称" value={[]} options={options} onApply={apply} /></FinanceTableColumn></FinanceTableHeader><FinanceTableBody><FinanceTableRow id="a"><FinanceTableCell>甲</FinanceTableCell></FinanceTableRow></FinanceTableBody></FinanceTable>);
    await user.click(screen.getByRole("button", { name: "筛选名称" }));
    await user.click(screen.getByRole("checkbox", { name: "账户乙" }));
    await user.click(screen.getByRole("button", { name: "应用" }));
    expect(apply).toHaveBeenCalledOnce(); expect(sort).not.toHaveBeenCalled();
    expect(within(screen.getByRole("grid")).getByRole("rowheader")).toHaveTextContent("甲");
  });
  test("candidate errors are explicit and do not apply invented options", async () => {
    const retry = vi.fn(), apply = vi.fn(); const user = userEvent.setup();
    render(<CashFilterPopover label="账户" value={[]} options={[]} error="读取失败" onReload={retry} onApply={apply} />);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    expect(screen.getByRole("alert")).toHaveTextContent("读取失败");
    expect(screen.getByRole("button", { name: "全选" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重新读取" }));
    expect(retry).toHaveBeenCalledOnce(); expect(apply).not.toHaveBeenCalled();
  });
  test("other-sort menu combines field and direction in a single selection", async () => {
    const change = vi.fn(); const user = userEvent.setup();
    render(<CashSortMenu sort="amount" order="desc" options={[{ value: "amount", label: "原始金额" }]} onChange={change} />);
    await user.click(screen.getByRole("button", { name: "其他排序" }));
    expect(screen.getByRole("button", { name: "原始金额 · 降序 ↓" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "原始金额 · 升序 ↑" }));
    expect(change).toHaveBeenCalledTimes(1); expect(change).toHaveBeenCalledWith("amount", "asc");
  });
});
