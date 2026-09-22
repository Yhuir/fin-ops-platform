import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CashConfigurationSelect } from "../components/cash/CashFlowSelectors";
import { cashRequest, CashRequestError } from "../features/cash/api";
import { CashProvider } from "../features/cash/hooks";

vi.mock("../features/cash/api", async original => ({ ...await original<typeof import("../features/cash/api")>(), cashRequest: vi.fn() }));
const request = vi.mocked(cashRequest);
const category = { id: "first", name: "办公支出", group: "payment", enabled: true };
const page = (rows: object[], number = 1, total = rows.length) => ({ rows, pagination: { page: number, page_size: 100, total } });
afterEach(cleanup);
beforeEach(() => request.mockReset());

function SelectForm({ initial = "", original, group = "payment", changed = () => {}, submit = () => {} }: {
  initial?: string; original?: typeof category; group?: string; changed?: (value: string, reference: unknown) => void; submit?: () => void;
}) {
  const [value, setValue] = useState(initial);
  return <form onSubmit={event => { event.preventDefault(); submit(); }}>
    <CashConfigurationSelect name="categories" label="费用分类" value={value} selected={original} group={group} required onChange={(next, row) => { setValue(next); changed(next, row); }} />
    <button type="submit">提交</button>
  </form>;
}

describe("现金费用类型单列分组", () => {
  it("单列组标题不可选，跨页保留已选类型和真实组别，搜索有界防抖", async () => {
    const user = userEvent.setup(); const changed = vi.fn();
    request.mockImplementation(async path => {
      const params = new URL(path, "http://test").searchParams;
      expect(params.get("page_size")).toBe("100");
      expect(params.get("groups")).toBe('["payment","turnover"]');
      return params.get("page") === "2" ? page([{ id: "second", name: "归还借款", group: "turnover", enabled: true }], 2, 101)
        : page([category, { id: "third", name: "往来归还", group: "turnover", enabled: true }], 1, 101);
    });
    render(<CashProvider><SelectForm changed={changed} /></CashProvider>);
    await user.click(screen.getByLabelText("费用分类", { selector: "button" }));
    const list = await screen.findByRole("listbox");
    expect(within(list).getByRole("group", { name: "支出" })).toBeInTheDocument();
    expect(within(list).getByRole("group", { name: "往来（收付均可）" })).toBeInTheDocument();
    expect(within(list).queryByRole("option", { name: "支出", exact: true })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "办公支出" }));
    expect(changed).toHaveBeenLastCalledWith("first", expect.objectContaining({ name: "办公支出", group: "payment" }));
    await user.click(screen.getByLabelText("费用分类", { selector: "button" }));
    await user.click(screen.getByRole("button", { name: "下一页" }));
    await screen.findByRole("option", { name: "归还借款" });
    expect(screen.getByRole("option", { name: "办公支出" })).toHaveAttribute("aria-selected", "true");
    expect(request.mock.calls.some(([path]) => path.includes("category_id"))).toBe(false);
    const before = request.mock.calls.length;
    await user.type(screen.getByRole("textbox", { name: "搜索费用分类" }), "报销");
    expect(request.mock.calls.length).toBe(before);
    await waitFor(() => expect(request.mock.calls.length).toBe(before + 1));
    const params = new URL(request.mock.calls.at(-1)![0], "http://test").searchParams;
    expect(params.get("keyword")).toBe("报销"); expect(params.get("page")).toBe("1");
  });

  it("仅ID的停用默认分类精确读取一次，保留真实标题但不能用于新增", async () => {
    const user = userEvent.setup(); const submit = vi.fn();
    request.mockImplementation(async path => path.includes("category_id=default")
      ? page([{ ...category, id: "default", name: "已停用默认", enabled: false }]) : page([category]));
    render(<CashProvider><SelectForm initial="default" submit={submit} /></CashProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("所选费用类型已停用");
    expect(screen.getByLabelText("费用分类", { selector: "button" })).toHaveTextContent("已停用默认");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(submit).not.toHaveBeenCalled();
    await user.click(screen.getByLabelText("费用分类", { selector: "button" }));
    await user.click(screen.getByRole("option", { name: "办公支出" }));
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(submit).toHaveBeenCalledOnce();
    expect(request.mock.calls.filter(([path]) => path.includes("category_id"))).toHaveLength(1);
  });

  it("编辑原分类包含元数据时不额外请求，允许保留停用原值", async () => {
    const user = userEvent.setup(); const submit = vi.fn(); request.mockResolvedValue(page([]));
    render(<CashProvider><SelectForm initial="first" original={{ ...category, enabled: false }} submit={submit} /></CashProvider>);
    await waitFor(() => expect(request).toHaveBeenCalledOnce());
    expect(screen.getByLabelText("费用分类", { selector: "button" })).toHaveTextContent("办公支出（原值）");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(submit).toHaveBeenCalledOnce();
    expect(request.mock.calls.some(([path]) => path.includes("category_id"))).toBe(false);
  });

  it("精确读取失败可重读，不存在时明确反馈，不猜分类", async () => {
    const user = userEvent.setup(); let fail = true;
    request.mockImplementation(async path => {
      if (path.includes("category_id")) {
        if (fail) throw new CashRequestError(503, "cash_storage_unavailable", "分类读取失败");
        return page([]);
      }
      return page([category]);
    });
    render(<CashProvider><SelectForm initial="missing" /></CashProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("分类读取失败");
    fail = false;
    await user.click(screen.getByRole("button", { name: "重新读取所选费用类型" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("所选费用类型不存在");
    expect(screen.getByLabelText("费用分类", { selector: "button" })).toHaveTextContent("请选择");
  });

  it("切换方向后取消旧精确查询，其迟到结果不能成为新方向原值", async () => {
    let resolve!: (value: unknown) => void; let oldSignal: AbortSignal | undefined;
    request.mockImplementation(async (path, options) => {
      if (path.includes("category_id=old")) {
        oldSignal = options?.signal;
        return new Promise(done => { resolve = done; });
      }
      return page([]);
    });
    const view = render(<CashProvider><CashConfigurationSelect name="categories" label="费用分类" value="old" group="payment" onChange={vi.fn()} /></CashProvider>);
    await waitFor(() => expect(resolve).toBeDefined());
    view.rerender(<CashProvider><CashConfigurationSelect name="categories" label="费用分类" value="" group="receipt" onChange={vi.fn()} /></CashProvider>);
    expect(oldSignal?.aborted).toBe(true);
    await act(async () => resolve(page([{ ...category, id: "old", name: "旧方向迟到分类" }])));
    expect(screen.queryByText("旧方向迟到分类")).not.toBeInTheDocument();
    expect(new URL(request.mock.calls.at(-1)![0], "http://test").searchParams.get("groups")).toBe('["receipt","turnover"]');
  });
});
