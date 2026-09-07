import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CashSettings, { CashProjectSettings, initialCashSettingsCriteria } from "../components/cash/CashSettings";
import { CashRequestError, cashRequest } from "../features/cash/api";
import { CashProvider } from "../features/cash/hooks";

vi.mock("../features/cash/api", async (original) => ({ ...await original<typeof import("../features/cash/api")>(), cashRequest: vi.fn() }));
vi.mock("../components/cash/CashItems", () => ({ CashItemEditor: () => <div>期初未结编辑器</div> }));

const request = vi.mocked(cashRequest);
const page = <T,>(rows: T[]) => ({ rows, pagination: { page: 1, page_size: 50, total: rows.length } });

function installProjects({ allowed = ["doing"], configured = true, failure = false } = {}) {
  let codes = [...allowed];
  let version = 4;
  let isConfigured = configured;
  request.mockImplementation(async (path, options = {}) => {
    if (path === "/settings/project-selection" && options.method === "PUT") {
      if (failure) throw new CashRequestError(409, "cash_version_conflict", "设置已被其他操作更改，请重新读取。");
      const body = options.body as { allowed_stage_codes: string[]; expected_version: number };
      expect(body.expected_version).toBe(version);
      codes = [...body.allowed_stage_codes]; version += 1; isConfigured = true;
      return { allowed_stage_codes: codes, version, configured: isConfigured, changed: true };
    }
    if (path === "/settings/project-selection") return { allowed_stage_codes: codes, version, configured: isConfigured };
    if (path.startsWith("/projects?")) return {
      rows: [
        { id: "test-a", code: "T1", name: "合成实施项目", stage_code: "doing", stage_name: "实施阶段", selectable: codes.includes("doing"), unavailable_reason: codes.includes("doing") ? null : "stage_not_allowed" },
        { id: "test-end", code: null, name: "合成结束项目", stage_code: "end", stage_name: "已结束", selectable: false, unavailable_reason: "ended" },
      ],
      stages: [{ code: "doing", name: "实施阶段" }, { code: "0", name: "未中标" }, { code: "end", name: "已结束" }],
      total: 2, page: 1, page_size: 50, read_at: "2026-09-07T01:00:00Z", selection_settings_version: version, configured: isConfigured,
    };
    throw new Error(`Unexpected cash test request: ${path}`);
  });
}

afterEach(cleanup);
beforeEach(() => request.mockReset());

describe("现金项目选择设置", () => {
  it("项目阶段多选只改变列表，保留配置草稿且不提交顶部关键词", async () => {
    const user = userEvent.setup(); installProjects();
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    await user.click(await screen.findByRole("checkbox", { name: "实施阶段" }));
    await user.type(screen.getByRole("textbox", { name: "项目关键词" }), "未查询内容");
    const before = request.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "筛选项目阶段" }));
    const popup = await screen.findByRole("dialog", { name: "筛选项目阶段" });
    await user.click(within(popup).getByRole("checkbox", { name: "实施阶段" }));
    await user.click(within(popup).getByRole("checkbox", { name: "阶段缺失" }));
    expect(request.mock.calls.length).toBe(before);
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await waitFor(() => expect(request.mock.calls.length).toBe(before + 1));
    const params = new URL(request.mock.calls.at(-1)![0], "http://test").searchParams;
    expect(JSON.parse(params.get("stage_codes")!)).toEqual(["doing", null]);
    expect(params.has("keyword")).toBe(false);
    expect(screen.getByRole("checkbox", { name: "实施阶段" })).not.toBeChecked();
    expect(screen.getByText("未保存")).toBeInTheDocument();
    expect(request.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(false);
    await user.click(screen.getByRole("button", { name: "重置", exact: true }));
    expect(screen.getByRole("textbox", { name: "项目关键词" })).toHaveValue("");
    expect(screen.getByText("未保存")).toBeInTheDocument();
    expect(new URL(request.mock.calls.at(-1)![0], "http://test").searchParams.has("stage_codes")).toBe(false);
  });

  it("重新筛选期间保留阶段配置区和表头，读取未完成不能保存", async () => {
    const user = userEvent.setup(); installProjects();
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    await user.click(await screen.findByRole("checkbox", { name: "实施阶段" }));
    request.mockImplementation(() => new Promise(() => {}));
    await user.click(screen.getByRole("button", { name: "筛选新增资格" }));
    const popup = await screen.findByRole("dialog", { name: "筛选新增资格" });
    await user.click(within(popup).getByRole("checkbox", { name: "可选", exact: true }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(screen.getByRole("checkbox", { name: "实施阶段" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存选择" })).toBeDisabled();
    expect(screen.getByRole("columnheader", { name: /真实阶段/ })).toBeInTheDocument();
    expect(screen.getByText("正在读取 OA 项目…")).toBeInTheDocument();
  });

  it("阶段草稿不写入，结束禁选，全空保存后仍显示全部项目", async () => {
    const user = userEvent.setup(); installProjects();
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    const implementation = await screen.findByRole("checkbox", { name: "实施阶段" });
    expect(implementation).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "已结束（不允许新增）" })).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: "未中标" })).not.toBeDisabled();
    await user.click(implementation);
    expect(request.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(0);
    expect(screen.getByText("未保存")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /合成实施项目/ })).getByText("可选")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "保存选择" }));
    await screen.findByText("当前不允许任何项目");
    expect(request).toHaveBeenCalledWith("/settings/project-selection", expect.objectContaining({ method: "PUT", body: { expected_version: 4, allowed_stage_codes: [] } }));
    expect(screen.getByText("合成结束项目")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /合成实施项目/ })).getByText("不可选")).toBeInTheDocument();
  });

  it("撤销只还原草稿；刷新 OA 不会提交或覆盖未保存选择", async () => {
    const user = userEvent.setup(); installProjects();
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    await user.click(await screen.findByRole("checkbox", { name: "实施阶段" }));
    await user.click(screen.getByRole("button", { name: "刷新 OA 资料" }));
    expect(await screen.findByRole("checkbox", { name: "实施阶段" })).not.toBeChecked();
    expect(screen.getByText("未保存")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤销更改" }));
    expect(screen.getByRole("checkbox", { name: "实施阶段" })).toBeChecked();
    expect(request.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(0);
  });

  it("保存冲突保留草稿，不换新版本自动覆盖", async () => {
    const user = userEvent.setup(); installProjects({ failure: true });
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    await user.click(await screen.findByRole("checkbox", { name: "实施阶段" }));
    await user.click(screen.getByRole("button", { name: "保存选择" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("设置已被其他操作更改");
    expect(screen.getByRole("checkbox", { name: "实施阶段" })).not.toBeChecked();
    expect(screen.getByText("未保存")).toBeInTheDocument();
    expect(request.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
  });

  it("首次配置依据 configured 而非非空集合或版本号", async () => {
    installProjects({ allowed: [], configured: false });
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    expect(await screen.findByText("尚未设置，请明确保存允许范围")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存选择" })).toBeEnabled();
  });

  it("关键词只在查询后发出，错误不伪装空项目", async () => {
    const user = userEvent.setup(); installProjects();
    render(<CashProvider><CashProjectSettings /></CashProvider>);
    await screen.findByText("合成实施项目");
    const before = request.mock.calls.length;
    await user.type(screen.getByRole("textbox", { name: "项目关键词" }), "关键字");
    expect(request.mock.calls.length).toBe(before);
    request.mockImplementation(async (path) => { if (path.startsWith("/projects?")) throw new CashRequestError(503, "cash_dependency_unavailable", "OA 项目读取失败。"); return { allowed_stage_codes: ["doing"], configured: true, version: 4 }; });
    await user.click(screen.getByRole("button", { name: "查询项目" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("OA 项目读取失败");
    expect(screen.queryByText("没有匹配项目。历史现金记录不受本页选择范围影响。")).not.toBeInTheDocument();
  });
});

describe("现金配置表单", () => {
  const account = { id: "7da9bed9-86e7-4093-bd23-fec143c918fb", version: 2, name: "合成测试账户", kind: "cash", opening_date: "2026-01-01", opening_amount: "0.00", enabled: true, remark: null };
  function installAccounts() {
    request.mockImplementation(async (path, options = {}) => {
      if (options.method === "PUT") return { account: { ...account, version: 3 }, version: 3, changed: true };
      if (path.startsWith("/settings/accounts")) return page([account]);
      if (path === "/settings/personal-opening") return { opening_date: null, version: 4 };
      throw new Error(`Unexpected test request ${path}`);
    });
  }
  it("新增账户期初与类型要求明确填写，不提供信用卡或假零", async () => {
    const user = userEvent.setup(); installAccounts();
    render(<CashProvider><CashSettings /></CashProvider>);
    await screen.findByText("合成测试账户");
    await user.click(screen.getByRole("button", { name: "新增账户" }));
    expect(screen.getByRole("textbox", { name: "确认期初金额" })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: "确认期初金额" })).toBeRequired();
    await user.click(screen.getByRole("button", { name: "保存账户" }));
    expect(request.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
    expect(screen.queryByText("信用卡账户")).not.toBeInTheDocument();
  });

  it("期初更正明确确认并携带原版本；成功关闭抽屉", async () => {
    const user = userEvent.setup(); installAccounts();
    render(<CashProvider><CashSettings /></CashProvider>);
    await screen.findByText("合成测试账户");
    await user.click(screen.getByRole("button", { name: "编辑", exact: true }));
    const amount = screen.getByRole("textbox", { name: "确认期初金额" });
    await user.clear(amount); await user.type(amount, "125.50");
    expect(screen.getByRole("button", { name: "保存账户" })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "确认更正期初，后续余额将重新计算" }));
    await user.click(screen.getByRole("button", { name: "保存账户" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith(`/settings/accounts/${account.id}`, expect.objectContaining({ method: "PUT", body: expect.objectContaining({ expected_version: 2, opening_amount: "125.50" }) })));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "确认期初金额" })).not.toBeInTheDocument());
  });

  it("关闭已编辑账户先确认，继续编辑保留草稿，放弃不写入", async () => {
    const user = userEvent.setup(); installAccounts();
    render(<CashProvider><CashSettings /></CashProvider>);
    await screen.findByText("合成测试账户");
    await user.click(screen.getByRole("button", { name: "编辑", exact: true }));
    await user.type(screen.getByRole("textbox", { name: "说明" }), "尚未保存的用途");
    await user.click(screen.getByRole("button", { name: "取消", exact: true }));
    await user.click(await screen.findByRole("button", { name: "继续编辑" }));
    expect(screen.getByRole("textbox", { name: "说明" })).toHaveValue("尚未保存的用途");
    await user.click(screen.getByRole("button", { name: "取消", exact: true }));
    await user.click(await screen.findByRole("button", { name: "放弃修改" }));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "说明" })).not.toBeInTheDocument());
    expect(request.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(false);
  });

  it("只读办理说明不调用 OA 写入，也不把参考事项伪装任务", async () => {
    const user = userEvent.setup(); installAccounts();
    render(<CashProvider><CashSettings /></CashProvider>);
    await screen.findByText("合成测试账户");
    const count = request.mock.calls.length;
    await user.click(screen.getByRole("tab", { name: "支付办理说明" }));
    expect(screen.getByText("个人信用卡还款")).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "办理说明关键词" }), "信用卡");
    await user.click(screen.getByRole("button", { name: "查看说明" }));
    expect(screen.getByText(/不是受管现金账户互转/)).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "个人信用卡还款" })).toHaveTextContent("不是受管现金账户互转");
    expect(document.querySelector(".cash-guide-detail")).toBeNull();
    expect(request.mock.calls.length).toBe(count);
  });

  it("账户状态两项为不限，名称原生排序与完整重置不改变配置", async () => {
    const user = userEvent.setup(); installAccounts();
    render(<CashProvider><CashSettings /></CashProvider>);
    await screen.findByText("合成测试账户");
    await user.click(screen.getByRole("button", { name: "筛选账户状态" }));
    let popup = await screen.findByRole("dialog", { name: "筛选账户状态" });
    await user.click(within(popup).getByRole("checkbox", { name: "停用" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await user.click(screen.getByRole("columnheader", { name: /账户名称/ }));
    let params = new URL(request.mock.calls.at(-1)![0], "http://test").searchParams;
    expect(params.get("enabled")).toBe("false");
    expect(params.get("order")).toBe("desc");
    await user.click(screen.getByRole("button", { name: "筛选账户状态" }));
    popup = await screen.findByRole("dialog", { name: "筛选账户状态" });
    await user.click(within(popup).getByRole("button", { name: "全选", exact: true }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    params = new URL(request.mock.calls.at(-1)![0], "http://test").searchParams;
    expect(params.has("enabled")).toBe(false);
    await user.click(screen.getByRole("button", { name: "重置", exact: true }));
    expect(new URL(request.mock.calls.at(-1)![0], "http://test").searchParams.get("order")).toBe("asc");
    expect(request.mock.calls.some(([, options]) => options?.method)).toBe(false);
  });

  it("费用类型按适用范围集合查询，不逐字读取，失败仍保留表头", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(page([]));
    const criteria = initialCashSettingsCriteria(); criteria.tab = "categories";
    render(<CashProvider><CashSettings initialCriteria={criteria} /></CashProvider>);
    await screen.findByText(/暂无匹配费用类型/);
    await user.type(screen.getByRole("textbox", { name: "费用类型名称" }), "尚未查询");
    const before = request.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "筛选适用范围" }));
    const popup = await screen.findByRole("dialog", { name: "筛选适用范围" });
    await user.click(within(popup).getByRole("checkbox", { name: "收入", exact: true }));
    await user.click(within(popup).getByRole("checkbox", { name: "往来（收付均可）" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await waitFor(() => expect(request.mock.calls.length).toBe(before + 1));
    const params = new URL(request.mock.calls.at(-1)![0], "http://test").searchParams;
    expect(params.get("groups")).toBe('["receipt","turnover"]');
    expect(params.has("keyword")).toBe(false);
    request.mockRejectedValue(new CashRequestError(503, "cash_dependency_unavailable", "配置读取暂不可用"));
    await user.click(screen.getByRole("button", { name: "刷新", exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("配置读取暂不可用");
    expect(screen.getByRole("columnheader", { name: /适用范围/ })).toBeInTheDocument();
    expect(screen.queryByText(/暂无匹配费用类型/)).not.toBeInTheDocument();
  });
});
