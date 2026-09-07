import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CashTasks, { cashTaskRemaining } from "../components/cash/CashTasks";
import type { CashTaskOccurrence } from "../components/cash/CashTasksTypes";
import { cashTaskIdentity } from "../components/cash/CashTasksTypes";
import { CashRequestError, cashRequest } from "../features/cash/api";
import { CashProvider } from "../features/cash/hooks";

vi.mock("../features/cash/api", async (original) => ({ ...await original<typeof import("../features/cash/api")>(), cashRequest: vi.fn() }));
const drawerTask = vi.hoisted(() => vi.fn());
vi.mock("../components/cash/CashFlowDrawer", () => ({ CashFlowDrawer: ({ task }: { task?: { month: string } }) => { drawerTask(task); return <div role="dialog">现金录入 {task?.month}</div>; } }));

const request = vi.mocked(cashRequest);
const task = (extra: Partial<CashTaskOccurrence> = {}): CashTaskOccurrence => ({
  row_key: "test:2026-09", occurrence_id: null, version: null,
  template_id: "1d839810-f8ef-486a-990a-7844abbb9f7c", template_version: 3,
  month: "2026-09", title: "合成付款任务", kind: "payment", due_on: "2026-09-05", remind_on: "2026-09-03",
  planned_amount: "100.00", actual_amount: "0.00", state: "pending", marked_unpaid: false,
  need_planned_amount: false, is_over_plan: false, over_plan_amount: "0.00", is_overdue: true, is_due: false,
  note: null, flow_count: 0, instructions: null, default_account_id: null, default_category_id: null, ...extra,
});
const result = (rows: CashTaskOccurrence[]) => ({ rows, pagination: { page: 1, page_size: 50, total: rows.length }, summary: { task_count: rows.length, counts_by_state: { pending: rows.filter(r => r.state === "pending").length, partial: rows.filter(r => r.state === "partial").length, completed: rows.filter(r => r.state === "completed").length }, receipt_actual_amount: "0.00", payment_actual_amount: "40.00" } });

afterEach(cleanup);
beforeEach(() => { request.mockReset(); drawerTask.mockReset(); });

describe("任务金额与首次身份", () => {
  it("首次动作带模板版本，已物化月份带月版本", () => {
    expect(cashTaskIdentity(task())).toEqual({ template_id: task().template_id, month: "2026-09", expected_version: null, expected_template_version: 3 });
    expect(cashTaskIdentity(task({ version: 5 }))).toEqual({ template_id: task().template_id, month: "2026-09", expected_version: 5 });
  });
  it("未知目标/核对不显示假零，金额差不损失分位", () => {
    expect(cashTaskRemaining(task({ planned_amount: null }))).toBeNull();
    expect(cashTaskRemaining(task({ kind: "check" }))).toBeNull();
    expect(cashTaskRemaining(task({ planned_amount: "9999999999999999.99", actual_amount: "9999999999999999.98" }))).toBe("0.01");
    expect(cashTaskRemaining(task({ actual_amount: "120.00" }))).toBe("0.00");
  });
});

describe("每月任务实际操作", () => {
  it("部分办理不提供未还覆盖；新记一笔将归属月交给同一录入器", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(result([task({ occurrence_id: "month-id", version: 2, state: "partial", actual_amount: "40.00", flow_count: 1 })]));
    render(<CashProvider><CashTasks /></CashProvider>);
    await screen.findByText("合成付款任务");
    expect(screen.queryByRole("button", { name: "未付 / 未还" })).not.toBeInTheDocument();
    expect(screen.getByText("60.00")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "继续办理" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("现金录入 2026-09");
  });

  it("办理采用当月快照默认值，不读取当前模板覆盖历史", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(result([task({ instructions: "该月的办理说明", default_account_id: "historical-account", default_category_id: "historical-category" })]));
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "已付 / 已还" }));
    expect(drawerTask).toHaveBeenLastCalledWith(expect.objectContaining({ instructions: "该月的办理说明", default_account_id: "historical-account", default_category_id: "historical-category" }));
    expect(request.mock.calls.some(([path]) => path.startsWith("/tasks"))).toBe(false);
  });

  it("完成后仍可补记真实收付，超计划不改目标、不再提供未还", async () => {
    const user = userEvent.setup();
    request.mockResolvedValue(result([task({ version: 3, occurrence_id: "persisted", state: "completed", actual_amount: "125.00", is_over_plan: true, over_plan_amount: "25.00", flow_count: 2 })]));
    render(<CashProvider><CashTasks /></CashProvider>);
    expect(await screen.findByText("超出 25.00")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "未付 / 未还" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "补记实际收付" }));
    expect(drawerTask).toHaveBeenLastCalledWith(expect.objectContaining({ planned_amount: "100.00" }));
  });

  it("标记未还只提交意图，不生成现金；首次版本明确", async () => {
    const user = userEvent.setup();
    request.mockImplementation(async (path, options = {}) => options.method === "POST" ? { occurrence: task({ marked_unpaid: true }), version: 1 } : result([task()]));
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "未付 / 未还" }));
    await user.type(screen.getByRole("textbox", { name: "本月说明" }), "等待确认");
    await user.click(screen.getByRole("button", { name: "标记未付 / 未还", exact: true }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("/task-occurrences/mark-unpaid", expect.objectContaining({ method: "POST", body: { ...cashTaskIdentity(task()), note: "等待确认" } })));
    expect(request.mock.calls.some(([path]) => path === "/flows" || path === "/task-occurrences/confirm")).toBe(false);
  });

  it("核对动作不用收款表单，不要求金额", async () => {
    const user = userEvent.setup(); const check = task({ kind: "check", title: "合成核对任务", planned_amount: null, actual_amount: null });
    request.mockImplementation(async (_path, options = {}) => options.method === "POST" ? { occurrence: check, version: 1 } : result([check]));
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "已核对" }));
    expect(screen.queryByRole("textbox", { name: "本月目标金额" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "完成核对" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("/task-occurrences/complete-check", expect.objectContaining({ body: { ...cashTaskIdentity(check), note: null } })));
  });

  it("本月调整失败保留输入，不替换金额或月份", async () => {
    const user = userEvent.setup();
    request.mockImplementation(async (_path, options = {}) => { if (options.method === "POST") throw new CashRequestError(409, "cash_version_conflict", "月份已变化，请重新读取。"); return result([task()]); });
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "调整本月" }));
    const input = screen.getByRole("textbox", { name: "本月目标金额" });
    await user.clear(input); await user.type(input, "125.50");
    await user.click(screen.getByRole("button", { name: "保存本月调整" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("月份已变化");
    expect(input).toHaveValue("125.50");
    expect(request).toHaveBeenCalledWith("/task-occurrences/adjust", expect.objectContaining({ body: { ...cashTaskIdentity(task()), note: null, due_on: "2026-09-05", planned_amount: "125.50" } }));
  });

  it("关联已录显示资格，未知目标需填写，确认不再次创建流水", async () => {
    const user = userEvent.setup(); const row = task({ planned_amount: null, need_planned_amount: true });
    const existing = { id: "9876ab49-de4b-478b-8f31-f6e947a72fd2", version: 7, occurred_on: "2026-09-01", amount: "25.00", content: "合成手工现金", kind: "payment", source_kind: "manual", selectable: true, unavailable_reason: null };
    request.mockImplementation(async (path, options = {}) => {
      if (options.method === "POST") return { occurrence: row, flow: existing, version: 2 };
      if (path.startsWith("/flows?")) return { rows: [existing, { ...existing, id: "blocked", content: "不匹配方向", selectable: false, unavailable_reason: "direction_mismatch" }], pagination: { page: 1, page_size: 50, total: 2 } };
      return result([row]);
    });
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "关联已录" }));
    expect(await screen.findByRole("button", { name: "收付方向不同" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "选择", exact: true }));
    expect(screen.getByRole("button", { name: "确认关联" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "本月目标金额" }), "100.00");
    await user.click(screen.getByRole("button", { name: "确认关联" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("/task-occurrences/confirm", expect.objectContaining({ body: { ...cashTaskIdentity(row), mode: "existing_flow", planned_amount: "100.00", existing_flow: { flow_id: existing.id, expected_flow_version: 7 } } })));
    expect(request.mock.calls.some(([path]) => path === "/flows")).toBe(false);
  });

  it("任务配置没有猜测执行日，输入关键词不会逐字发请求", async () => {
    const user = userEvent.setup();
    request.mockImplementation(async (path) => path.startsWith("/tasks?") ? { rows: [], pagination: { page: 1, page_size: 50, total: 0 } } : result([]));
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(screen.getByRole("tab", { name: "任务配置" }));
    await screen.findByText(/暂无匹配模板/);
    const before = request.mock.calls.length;
    await user.type(screen.getByRole("textbox", { name: "模板关键词" }), "测试任务");
    expect(request.mock.calls.length).toBe(before);
    await user.click(screen.getByRole("button", { name: "新增任务" }));
    expect(screen.getByRole("spinbutton", { name: "每月执行日" })).toHaveValue(null);
    expect(screen.getByRole("spinbutton", { name: "提前提醒天数" })).toHaveValue(null);
    expect(request.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
  });

  it("创建核对模板携带明确日期规则，默认现金字段为 null", async () => {
    const user = userEvent.setup();
    request.mockImplementation(async (path, options = {}) => {
      if (options.method === "POST") return { template: options.body, version: 1, created: true };
      return path.startsWith("/tasks?") ? { rows: [], pagination: { page: 1, page_size: 50, total: 0 } } : result([]);
    });
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(screen.getByRole("tab", { name: "任务配置" }));
    await screen.findByText(/暂无匹配模板/);
    await user.click(screen.getByRole("button", { name: "新增任务" }));
    await user.type(screen.getByRole("textbox", { name: "任务内容" }), "合成核对模板");
    await user.click(screen.getByLabelText("处理类别", { selector: "button" }));
    await user.click(await screen.findByRole("option", { name: "核对与跟进" }));
    await user.type(screen.getByRole("spinbutton", { name: "每月执行日" }), "31");
    await user.type(screen.getByRole("spinbutton", { name: "提前提醒天数" }), "2");
    await user.click(screen.getByRole("button", { name: "保存任务" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("/tasks", expect.objectContaining({ method: "POST", body: expect.objectContaining({
      id: expect.any(String), title: "合成核对模板", kind: "check", execution_day: 31, remind_days: 2, default_amount: null, default_account_id: null, default_category_id: null,
    }) })));
    expect(request.mock.calls.filter(([path, options]) => path === "/tasks" && options?.method === "POST")).toHaveLength(1);
  });

  it("编辑历史已启用模板不将旧生效月作为新的重启参数提交", async () => {
    const user = userEvent.setup();
    const template = { id: "1d839810-f8ef-486a-990a-7844abbb9f7c", version: 6, title: "合成历史核对", kind: "check", execution_day: 5, remind_days: 2, effective_from_month: "2025-01", effective_to_month: null, enabled: true, default_account_id: null, default_category_id: null, default_amount: null, instructions: null };
    request.mockImplementation(async (path, options = {}) => {
      if (options.method === "PUT") return { template, version: 7, changed: true };
      return path.startsWith("/tasks?") ? { rows: [template], pagination: { page: 1, page_size: 50, total: 1 } } : result([]);
    });
    render(<CashProvider><CashTasks /></CashProvider>);
    await user.click(screen.getByRole("tab", { name: "任务配置" }));
    await user.click(await screen.findByRole("button", { name: "编辑 / 启停" }));
    await user.click(screen.getByRole("checkbox", { name: "启用任务" }));
    await user.click(screen.getByRole("button", { name: "保存任务" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith(`/tasks/${template.id}`, expect.objectContaining({ method: "PUT", body: expect.objectContaining({ expected_version: 6, enabled: false }) })));
    const submitted = request.mock.calls.find(([, options]) => options?.method === "PUT")?.[1]?.body as Record<string, unknown>;
    expect(submitted).not.toHaveProperty("effective_from_month");
    expect(submitted).not.toHaveProperty("id");
  });

  it("撤权清除所有任务内容，不保留在页外", async () => {
    request.mockRejectedValue(new CashRequestError(403, "cash_access_denied", "不可使用现金"));
    render(<CashProvider><CashTasks /></CashProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("页面数据已清除");
    expect(screen.queryByRole("tab", { name: "本月处理" })).not.toBeInTheDocument();
  });
});
