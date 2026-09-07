import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CashFlowDrawer } from "../components/cash/CashFlowDrawer";
import CashFlowTable, { initialCashFlowCriteria } from "../components/cash/CashFlowTable";
import type { CashFlow, CashFlowDetail, CashFlowSummary } from "../components/cash/CashFlows.types";
import type { CashItem } from "../components/cash/CashItems.types";
import { apiFetch } from "../features/apiClient";
import { CashProvider } from "../features/cash/hooks";

vi.mock("../features/apiClient", async (original) => ({ ...await original<typeof import("../features/apiClient")>(), apiFetch: vi.fn() }));

const http = vi.mocked(apiFetch);
const accountA = "b0965e94-cd68-49a2-bac3-0038422e8204";
const accountB = "5e626f51-ec2e-4128-a35d-d54f1b5f7e0a";
const categoryId = "9d830b6c-2747-437b-a4b8-f8b2641a840e";
const flowId = "80f737c2-16c4-4c2c-9caa-3dd3b7f6ce48";
const itemId = "113c719a-14b5-46fc-a14c-ff63bb7e0cb2";
const templateId = "238e47dd-9e68-4084-b2e3-b6cb23f9cd90";

const rowsPage = <T,>(rows: T[], pageSize = 50) => ({ rows, pagination: { page: 1, page_size: pageSize, total: rows.length } });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const flow = (changes: Partial<CashFlow> = {}): CashFlow => ({
  id: flowId, version: 7, occurred_on: "2026-01-05", kind: "receipt", amount: "125.50",
  from_account: null, to_account: { id: accountA, name: "合成现金账户" }, category: { id: categoryId, name: "合成往来类型", group: "turnover" },
  project: null, person_name: null, content: "合成手工收款", source_kind: "manual", task: null,
  income_amount: "125.50", expense_amount: null, account_running_balance: null,
  remark: null, created_by_account: "TEST_OPERATOR", created_by_name: "合成经办人", created_at: "2026-01-05T01:00:00Z", updated_at: "2026-01-05T01:00:00Z", ...changes,
});
const detail = (value = flow()): CashFlowDetail => ({
  flow: value, task: value.task, allocations: [], allocation_count: 0, allocations_has_more: false,
  delete_impact: { flow_version: value.version, task_count: 0, item_count: 0, settlement_count: 0, source_owned_item_count: 0, source_correction_required: false, tasks: [], items: [], preview_truncated: false },
});
const summary = (): CashFlowSummary => ({
  period: { date_from: "2026-01-01", date_to: "2026-09-07" },
  filtered_totals: { flow_count: 1, income_amount: "125.50", expense_amount: "0.00", transfer_amount: "42.35" },
  account_balances: [
    { account_id: accountA, account_name: "合成现金账户", opening_date: "2026-01-01", coverage_state: "complete", coverage_start: "2026-01-01", opening_balance: "50.00", balance_at_coverage_start: "50.00", period_inflow: "125.50", period_outflow: "42.35", ending_balance: "133.15" },
    { account_id: accountB, account_name: "尚未起算合成账户", opening_date: "2027-01-01", coverage_state: "not_started", coverage_start: null, opening_balance: null, balance_at_coverage_start: null, period_inflow: null, period_outflow: null, ending_balance: null },
  ],
});

type Write = { path: string; method: string; body: Record<string, unknown>; init: RequestInit };
function installHttp(options: { write?: (write: Write) => Response | Promise<Response>; getDetail?: () => CashFlowDetail; list?: (url: URL) => { rows: CashFlow[]; pagination: { total: number; page: number; page_size: number }; summary: CashFlowSummary } } = {}) {
  const writes: Write[] = [];
  http.mockImplementation(async (url, init = {}) => {
    const parsed = new URL(url, "http://cash-test.invalid");
    const path = parsed.pathname;
    expect(path.startsWith("/api/cash/")).toBe(true);
    if (init.method && init.method !== "GET") {
      expect(typeof init.body).toBe("string");
      const write = { path, method: init.method, body: JSON.parse(String(init.body)) as Record<string, unknown>, init };
      writes.push(write);
      if (!options.write) throw new Error(`Unexpected cash write ${path}`);
      return options.write(write);
    }
    if (path === "/api/cash/settings/accounts") return json(rowsPage([
      { id: accountA, version: 1, name: "合成现金账户", kind: "cash", opening_date: "2026-01-01", opening_amount: "50.00", enabled: true, remark: null },
      { id: accountB, version: 1, name: "合成储蓄账户", kind: "savings", opening_date: "2026-01-01", opening_amount: "0.00", enabled: true, remark: null },
    ], Number(parsed.searchParams.get("page_size"))));
    if (path === "/api/cash/settings/categories") return json(rowsPage([{ id: categoryId, version: 1, name: "合成往来类型", group: "turnover", enabled: true, remark: null }], Number(parsed.searchParams.get("page_size"))));
    if (path === "/api/cash/reports/project-options") return json(rowsPage([{ id: "project-a", name: "合成历史项目甲" }, { id: "project-b", name: "合成历史项目乙" }]));
    if (path === "/api/cash/items" || path === "/api/cash/settlements") return json(rowsPage([], 20));
    if (path === `/api/cash/flows/${flowId}`) return json(options.getDetail ? options.getDetail() : detail());
    if (path === "/api/cash/flows") return json(options.list ? options.list(parsed) : { ...rowsPage([flow()]), summary: summary() });
    throw new Error(`Unexpected cash GET ${url}`);
  });
  return writes;
}

function created(body: Record<string, unknown>) {
  return json({ flow: { ...body, source_kind: "manual", task_occurrence_id: null, project_name_snapshot: null, version: 1, created_by_account: "TEST_OPERATOR", created_by_name: null, created_at: "2026-09-07T01:00:00Z", updated_at: "2026-09-07T01:00:00Z" }, related_items: [], origin_items: [], allocations: [], version: 1 }, 201);
}

function DrawerHarness(props: Omit<ComponentProps<typeof CashFlowDrawer>, "open" | "onClose">) {
  const [open, setOpen] = useState(true);
  return <CashProvider>{open ? <CashFlowDrawer {...props} open onClose={() => setOpen(false)} /> : <p>现金抽屉已关闭</p>}</CashProvider>;
}
async function select(user: ReturnType<typeof userEvent.setup>, label: string, option: string) {
  const trigger = await screen.findByLabelText(label, { selector: "button" });
  await waitFor(() => expect(trigger).toBeEnabled());
  await user.click(trigger);
  await user.click(await screen.findByRole("option", { name: option, exact: true }));
}
async function inputCash(user: ReturnType<typeof userEvent.setup>, amount = "125.5") {
  await user.type(screen.getByRole("textbox", { name: "金额（元）" }), amount);
  await user.type(screen.getByRole("textbox", { name: "用途" }), "真实控件合成收付");
}

beforeEach(() => http.mockReset());
afterEach(cleanup);

describe("现金实际录入 HTTP 字段", () => {
  it("跨列总选择超限保留菜单草稿、已应用条件和当前结果，不发送新 HTTP", async () => {
    const user = userEvent.setup(); installHttp(); const onCriteriaChange = vi.fn();
    const initial = initialCashFlowCriteria();
    initial.account_ids = Array.from({ length: 50 }, (_, i) => `00000000-0000-0000-0000-${String(i).padStart(12, "0")}`);
    initial.project_ids = Array.from({ length: 50 }, (_, i) => `p${i}`);
    render(<CashProvider><CashFlowTable initialCriteria={initial} onCriteriaChange={onCriteriaChange} /></CashProvider>);
    await screen.findByText("合成手工收款");
    await user.click(screen.getByRole("button", { name: "筛选来源" }));
    const popup = await screen.findByRole("dialog", { name: "筛选来源" });
    await user.click(within(popup).getByRole("checkbox", { name: "手动录入" }));
    const requests = http.mock.calls.length;
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    expect(within(popup).getByRole("alert")).toHaveTextContent("全部条件最多选择 100 项");
    expect(within(popup).getByRole("checkbox", { name: "手动录入" })).toBeChecked();
    expect(http.mock.calls).toHaveLength(requests);
    expect(onCriteriaChange.mock.calls.at(-1)![0]).toEqual(initial);
    expect(screen.getByText("合成手工收款")).toBeInTheDocument();
    await user.click(within(popup).getByRole("button", { name: "清空" }));
    expect(within(popup).queryByRole("alert")).not.toBeInTheDocument();
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "筛选来源" })).not.toBeInTheDocument());
    expect(http.mock.calls).toHaveLength(requests);
  });

  it("顶部查询达到 3501 字节时保留查询草稿和上次成功的流水，不发送 HTTP", async () => {
    const user = userEvent.setup(); installHttp(); const onCriteriaChange = vi.fn();
    render(<CashProvider><CashFlowTable onCriteriaChange={onCriteriaChange} /></CashProvider>);
    await screen.findByText("合成手工收款"); const criteria = onCriteriaChange.mock.calls.at(-1)![0];
    const requests = http.mock.calls.length;
    const query = new URL(http.mock.calls.find(([url]) => url.startsWith("/api/cash/flows?"))![0], "http://test").searchParams;
    query.set("keyword", "");
    const keyword = "x".repeat(3501 - query.toString().length); query.set("keyword", keyword);
    expect(query.toString()).toHaveLength(3501);
    fireEvent.change(screen.getByRole("textbox", { name: "搜索流水" }), { target: { value: keyword } });
    await user.click(screen.getByRole("button", { name: "查询", exact: true }));
    expect(screen.getByRole("alert")).toHaveTextContent("筛选条件过长");
    expect(screen.getByRole("textbox", { name: "搜索流水" })).toHaveValue(keyword);
    expect(screen.getByText("合成手工收款")).toBeInTheDocument();
    expect(onCriteriaChange.mock.calls.at(-1)![0]).toEqual(criteria);
    expect(http.mock.calls).toHaveLength(requests);
  });

  it("手工保存十进制字符串，503 后保留草稿并以相同 UUID 重试一次", async () => {
    const user = userEvent.setup(); let attempts = 0;
    const writes = installHttp({ write: ({ body }) => ++attempts === 1 ? json({ error: "cash_storage_unavailable", message: "现金服务暂不可用，请核对提交结果。" }, 503) : created(body) });
    render(<DrawerHarness kind="receipt" />);
    await select(user, "收款账户", "合成现金账户"); await select(user, "费用分类", "合成往来类型"); await inputCash(user);
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("现金服务暂不可用");
    expect(screen.getByRole("textbox", { name: "金额（元）" })).toHaveValue("125.5");
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ path: "/api/cash/flows", method: "POST", body: { amount: "125.50", kind: "receipt", from_account_id: null, to_account_id: accountA, category_id: categoryId, project_mode: "selection", oa_project_id: null, related_items: [], origin_items: [], allocations: [] } });
    expect(writes[0].body.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(writes[0].body).not.toHaveProperty("source_kind");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await screen.findByText("现金抽屉已关闭");
    expect(writes).toHaveLength(2); expect(writes[1].body).toEqual(writes[0].body);
    expect(writes[1].init.cache).toBe("no-store");
  });

  it.each(["300.00", null])("任务目标 %s 使用原子 confirm/new_flow，不把目标当本次金额", async (planned) => {
    const user = userEvent.setup();
    const writes = installHttp({ write: ({ body }) => json({ occurrence: { template_id: templateId, month: "2026-09", version: 2 }, flow: body.new_flow, version: 2 }) });
    render(<DrawerHarness task={{ template_id: templateId, month: "2026-09", expected_version: null, expected_template_version: 4, planned_amount: planned, kind: "payment", title: "合成任务", instructions: "本月已保存说明", default_account_id: accountA, default_category_id: categoryId }} />);
    expect(screen.getByRole("textbox", { name: "金额（元）" })).toHaveValue("");
    await waitFor(() => expect(screen.getByLabelText("付款账户", { selector: "button" })).toBeEnabled());
    await inputCash(user, "20.01");
    if (planned === null) await user.type(screen.getByRole("textbox", { name: "本月计划金额" }), "300");
    await user.click(screen.getByRole("button", { name: "保存并确认任务" }));
    await screen.findByText("现金抽屉已关闭");
    expect(writes).toHaveLength(1);
    expect(writes[0]).toMatchObject({ path: "/api/cash/task-occurrences/confirm", body: { template_id: templateId, month: "2026-09", expected_version: null, expected_template_version: 4, mode: "new_flow", new_flow: { amount: "20.01", kind: "payment", from_account_id: accountA, to_account_id: null, category_id: categoryId } } });
    if (planned === null) expect(writes[0].body.planned_amount).toBe("300.00");
    else expect(writes[0].body).not.toHaveProperty("planned_amount");
    expect(writes.some((write) => write.path === "/api/cash/flows")).toBe(false);
    expect(http.mock.calls.some(([url]) => url.includes("/tasks"))).toBe(false);
  });

  it("历史事项只读沿用项目并提交事项版本，全程不请求 OA 选择器", async () => {
    const user = userEvent.setup(); const writes = installHttp({ write: ({ body }) => created(body) });
    const item: CashItem = { id: itemId, version: 9, type: "loan", origin_date: "2026-01-01", original_amount: "100.00", is_opening: true, obligation_direction: "receivable", ledger_group: "company", counterparty: "合成往来对象", oa_project_id: "507f1f77bcf86cd799439011", project_name_snapshot: "合成已结束项目", origin_flow_id: null, origin_mode: null, bill_label_id: null, bill_month: null, ticket_provider: null, ticket_provided_on: null, ticket_description: null, related_obligation_id: null, ticket_source_id: null, content: "合成历史未结", remark: null };
    render(<DrawerHarness kind="receipt" existingItem={item} settlementKind="cash_repayment" />);
    expect(screen.getByText("合成已结束项目")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "选择项目" })).not.toBeInTheDocument();
    await select(user, "收款账户", "合成现金账户"); await select(user, "费用分类", "合成往来类型"); await inputCash(user, "17.30");
    await user.type(screen.getByRole("textbox", { name: "本次处理金额" }), "17.30");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await screen.findByText("现金抽屉已关闭");
    expect(writes[0].body).toMatchObject({ project_mode: "existing_item", project_item_id: itemId, expected_project_item_version: 9, amount: "17.30", allocations: [{ item_id: itemId, target_is_new: false, expected_item_version: 9, kind: "cash_repayment", amount: "17.30" }] });
    expect(writes[0].body).not.toHaveProperty("oa_project_id");
    expect(writes[0].body).not.toHaveProperty("related_items");
    expect(http.mock.calls.some(([url]) => url.includes("/projects"))).toBe(false);
  });

  it("内部转账只提交一笔、分类为空、不产生事项；同账户不能提交", async () => {
    const user = userEvent.setup(); const writes = installHttp({ write: ({ body }) => created(body) });
    render(<DrawerHarness kind="transfer" />);
    expect(screen.queryByLabelText("费用分类")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "新增借款 / 代付" })).not.toBeInTheDocument();
    await select(user, "付款账户", "合成现金账户"); await select(user, "收款账户", "合成现金账户"); await inputCash(user, "42.35");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("两个账户必须不同"); expect(writes).toHaveLength(0);
    await select(user, "收款账户", "合成储蓄账户");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    await screen.findByText("现金抽屉已关闭");
    expect(writes).toHaveLength(1);
    expect(writes[0].body).toMatchObject({ kind: "transfer", category_id: null, amount: "42.35", from_account_id: accountA, to_account_id: accountB, related_items: [], origin_items: [], allocations: [] });
    expect(http.mock.calls.some(([url]) => url.includes("/settings/categories"))).toBe(false);
  });
});

describe("现金读取、更正、删除", () => {
  it("账户多选只在应用后读取一次，不提交日期与搜索草稿，排序保留集合", async () => {
    const user = userEvent.setup(); installHttp();
    render(<CashProvider><CashFlowTable /></CashProvider>);
    await screen.findByText("合成手工收款");
    const listCalls = () => http.mock.calls.filter(([url]) => url.startsWith("/api/cash/flows?"));
    const original = new URL(listCalls()[0][0], "http://test").searchParams;
    fireEvent.change(screen.getByLabelText("起始日期"), { target: { value: "2026-06-01" } });
    await user.type(screen.getByRole("textbox", { name: "搜索流水" }), "未提交草稿");
    const before = listCalls().length;
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    const popup = await screen.findByRole("dialog", { name: "筛选账户" });
    await user.click(await within(popup).findByRole("checkbox", { name: "合成现金账户" }));
    await user.click(within(popup).getByRole("checkbox", { name: "合成储蓄账户" }));
    expect(listCalls()).toHaveLength(before);
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    await waitFor(() => expect(listCalls()).toHaveLength(before + 1));
    let params = new URL(listCalls().at(-1)![0], "http://test").searchParams;
    expect(JSON.parse(params.get("account_ids")!)).toEqual([accountA, accountB]);
    expect(params.has("keyword")).toBe(false); expect(params.get("date_from")).toBe(original.get("date_from"));
    expect(params.get("page")).toBe("1");
    await user.click(screen.getByRole("columnheader", { name: /日期/ }));
    await waitFor(() => expect(new URL(listCalls().at(-1)![0], "http://test").searchParams.get("order")).toBe("asc"));
    params = new URL(listCalls().at(-1)![0], "http://test").searchParams;
    expect(params.get("account_ids")).toBe(JSON.stringify([accountA, accountB]));
    expect(screen.queryByLabelText("排序", { selector: "button" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重置", exact: true }));
    params = new URL(listCalls().at(-1)![0], "http://test").searchParams;
    expect(params.has("account_ids")).toBe(false); expect(params.get("order")).toBe("desc");
    expect(screen.getByRole("textbox", { name: "搜索流水" })).toHaveValue("");
  });

  it("历史项目与未分类按 nullable 集合提交；关闭草稿与来源全选不写业务", async () => {
    const user = userEvent.setup(); const writes = installHttp();
    render(<CashProvider><CashFlowTable itemId={itemId} /></CashProvider>);
    await screen.findByText("合成手工收款");
    await user.click(screen.getByRole("button", { name: "筛选项目" }));
    let popup = await screen.findByRole("dialog", { name: "筛选项目" });
    await user.click(await within(popup).findByRole("checkbox", { name: "合成历史项目甲" }));
    await user.click(within(popup).getByRole("checkbox", { name: "无项目" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    const candidate = new URL(http.mock.calls.find(([url]) => url.startsWith("/api/cash/reports/project-options?"))![0], "http://test").searchParams;
    expect(candidate.get("item_id")).toBe(itemId); expect(candidate.has("date_from")).toBe(false);
    await user.click(screen.getByRole("button", { name: "筛选分类" }));
    popup = await screen.findByRole("dialog", { name: "筛选分类" });
    await user.click(await within(popup).findByRole("checkbox", { name: "未分类" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    let params = new URL(http.mock.calls.filter(([url]) => url.startsWith("/api/cash/flows?")).at(-1)![0], "http://test").searchParams;
    expect(JSON.parse(params.get("project_ids")!)).toEqual(["project-a", null]);
    expect(JSON.parse(params.get("category_ids")!)).toEqual([null]);
    await user.click(screen.getByRole("button", { name: "筛选来源" }));
    popup = await screen.findByRole("dialog", { name: "筛选来源" });
    const before = http.mock.calls.length;
    await user.click(within(popup).getByRole("button", { name: "全选", exact: true }));
    await user.click(within(popup).getByRole("button", { name: "取消" }));
    expect(http.mock.calls).toHaveLength(before);
    await user.click(screen.getByRole("button", { name: "筛选分类" }));
    popup = await screen.findByRole("dialog", { name: "筛选分类" });
    await user.click(within(popup).getByRole("button", { name: "清空" }));
    await user.click(within(popup).getByRole("button", { name: "应用" }));
    params = new URL(http.mock.calls.filter(([url]) => url.startsWith("/api/cash/flows?")).at(-1)![0], "http://test").searchParams;
    expect(params.has("category_ids")).toBe(false); expect(params.has("project_ids")).toBe(true);
    expect(writes).toHaveLength(0);
  });

  it("编辑携带详情读取的初始版本，409 后不自动抬版本覆盖", async () => {
    const user = userEvent.setup(); const writes = installHttp({ write: () => json({ error: "cash_version_conflict", message: "现金版本已改变。" }, 409) });
    render(<DrawerHarness flowId={flowId} />);
    await user.click(await screen.findByRole("button", { name: "编辑", exact: true }));
    const amount = screen.getByRole("textbox", { name: "金额（元）" }); await user.clear(amount); await user.type(amount, "130.2");
    await user.click(screen.getByRole("button", { name: "保存", exact: true }));
    expect(await screen.findByRole("alert")).toHaveTextContent("现金版本已改变");
    expect(writes).toHaveLength(1); expect(writes[0]).toMatchObject({ path: `/api/cash/flows/${flowId}`, method: "PUT", body: { expected_version: 7, amount: "130.20" } });
    expect(writes[0].body).not.toHaveProperty("id"); expect(writes[0].body).not.toHaveProperty("source_kind");
    expect(amount).toHaveValue("130.2");
  });

  it("删除需明确确认，完成后重读当前列表而非逐账簿删除", async () => {
    const user = userEvent.setup(); let deleted = false;
    const writes = installHttp({ write: ({ path, body }) => { expect(path).toBe(`/api/cash/flows/${flowId}/delete`); expect(body.expected_version).toBe(7); deleted = true; return json({ id: flowId, deleted: true, already_deleted: false, affected_counts: { flows: 1, items: 0, settlements: 0, occurrences: 0 } }); }, list: () => ({ ...rowsPage(deleted ? [] : [flow()]), summary: { ...summary(), filtered_totals: { flow_count: deleted ? 0 : 1, income_amount: deleted ? "0.00" : "125.50", expense_amount: "0.00", transfer_amount: "0.00" } } }) });
    render(<CashProvider><CashFlowTable /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "详情", exact: true }));
    await user.click(await screen.findByRole("button", { name: "删除", exact: true }));
    expect(screen.getByText(/影响：0 个任务，0 个事项，0 笔处理/)).toBeInTheDocument(); expect(writes).toHaveLength(0);
    await screen.findByText("本笔现金没有来源事项。");
    await user.click(screen.getByRole("button", { name: "确认删除" }));
    await screen.findByText(/该范围内没有现金流水/);
    expect(screen.queryByText("合成手工收款")).not.toBeInTheDocument();
    expect(writes).toHaveLength(1);
    expect(http.mock.calls.filter(([url, init]) => url.startsWith("/api/cash/flows?") && init?.method === "GET").length).toBeGreaterThan(1);
    expect(screen.getByText(/操作已保存/)).toBeInTheDocument();
  });

  it("账户汇总采用嵌套 DTO，未覆盖期间的 null 不显示成 0", async () => {
    const user = userEvent.setup(); installHttp();
    render(<CashProvider><CashFlowTable /></CashProvider>);
    expect(await screen.findByText("筛选合计：收入 125.50")).toBeInTheDocument();
    expect(screen.getByText("内部转账 42.35")).toBeInTheDocument();
    const before = http.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "账户期间余额" }));
    expect(screen.getByRole("dialog", { name: "账户期间余额" })).toBeInTheDocument();
    const table = screen.getByRole("grid", { name: "账户期间余额" });
    expect(within(table).getByText("133.15")).toBeInTheDocument();
    const unknown = within(table).getByRole("row", { name: /尚未起算合成账户/ });
    expect(within(unknown).getByText("尚未起算，余额未知")).toBeInTheDocument();
    expect(within(unknown).getAllByText("—")).toHaveLength(5);
    expect(within(unknown).queryByText("0.00")).not.toBeInTheDocument();
    expect(http.mock.calls.length).toBe(before);
  });

  it("独立流水限定期间、筛选包含停用账户；录入只请求启用账户", async () => {
    const user = userEvent.setup(); installHttp();
    const mounted = render(<CashProvider><CashFlowTable /></CashProvider>);
    await screen.findByText("合成手工收款");
    let urls = http.mock.calls.map(([url]) => new URL(url, "http://cash-test.invalid"));
    const list = urls.find(url => url.pathname === "/api/cash/flows")!;
    expect(list.searchParams.get("date_from")).toMatch(/^\d{4}-01-01$/);
    expect(list.searchParams.get("date_to")).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(urls.some(url => url.pathname.endsWith("/settings/accounts"))).toBe(false);
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    await screen.findByRole("checkbox", { name: "合成储蓄账户" });
    urls = http.mock.calls.map(([url]) => new URL(url, "http://cash-test.invalid"));
    expect(urls.find(url => url.pathname.endsWith("/settings/accounts"))!.searchParams.has("enabled")).toBe(false);
    mounted.unmount(); http.mockClear();
    render(<DrawerHarness kind="receipt" />);
    await waitFor(() => expect(http.mock.calls.some(([url]) => url.includes("/settings/accounts") && new URL(url, "http://cash-test.invalid").searchParams.get("enabled") === "true")).toBe(true));
  });

  it.each([{ itemId }, { taskOccurrenceId: templateId }])("父对象 %s 默认全历史分页，仍只有一个现金查询入口", async props => {
    installHttp();
    render(<CashProvider><CashFlowTable {...props} /></CashProvider>);
    await screen.findByText("合成手工收款");
    const url = new URL(http.mock.calls.find(([url]) => url.startsWith("/api/cash/flows?"))![0], "http://cash-test.invalid");
    expect(url.searchParams.has("date_from")).toBe(false); expect(url.searchParams.has("date_to")).toBe(false);
    expect(url.searchParams.get("page_size")).toBe("50");
    expect(url.searchParams.get("item_id") || url.searchParams.get("task_occurrence_id")).toBe("itemId" in props ? itemId : templateId);
    expect(screen.queryByRole("button", { name: "新增流水" })).not.toBeInTheDocument();
  });

  it("删除末页最后一行后退至有效页，不重复删除命令", async () => {
    const user = userEvent.setup(); let deleted = false;
    const writes = installHttp({
      write: () => { deleted = true; return json({ id: flowId, deleted: true, already_deleted: false, affected_counts: { tasks: 0, items: 0, settlements: 0 } }); },
      list: url => {
        const page = Number(url.searchParams.get("page"));
        return { rows: deleted && page === 2 ? [] : [flow({ content: deleted ? "前一页现金" : "末页现金" })],
          pagination: { page, page_size: 50, total: deleted ? 50 : 51 }, summary: summary() };
      },
    });
    render(<CashProvider><CashFlowTable initialCriteria={{ ...initialCashFlowCriteria(), page: 2 }} /></CashProvider>);
    await user.click(await screen.findByRole("button", { name: "详情", exact: true }));
    await user.click(await screen.findByRole("button", { name: "删除", exact: true }));
    await screen.findByText("本笔现金没有来源事项。");
    await user.click(screen.getByRole("button", { name: "确认删除" }));
    await screen.findByText("前一页现金");
    expect(writes).toHaveLength(1);
    expect(http.mock.calls.filter(([url]) => url.startsWith("/api/cash/flows?")).map(([url]) => new URL(url, "http://cash-test.invalid").searchParams.get("page"))).toEqual(["2", "2", "1"]);
  });

  it("恢复跨页历史账户名称仅用于显示，不污染现金查询字段", async () => {
    const user = userEvent.setup(); installHttp();
    render(<CashProvider><CashFlowTable initialCriteria={{ ...initialCashFlowCriteria(), account_ids: ["historical-account"], selected: { account_ids: [{ value: "historical-account", label: "历史账户" }] } }} /></CashProvider>);
    await screen.findByText("合成手工收款");
    expect(screen.getByRole("button", { name: "筛选账户" })).toHaveAttribute("data-active", "true");
    await user.click(screen.getByRole("button", { name: "筛选账户" }));
    const popup = await screen.findByRole("dialog", { name: "筛选账户" });
    await user.click(within(popup).getByText("查看已选项"));
    expect(within(popup).getByText("历史账户")).toBeVisible();
    const url = new URL(http.mock.calls.find(([url]) => url.startsWith("/api/cash/flows?"))![0], "http://cash-test.invalid");
    expect(url.searchParams.get("account_ids")).toBe('["historical-account"]');
    expect(url.searchParams.has("selected")).toBe(false); expect(url.search).not.toContain("历史账户");
  });
});
