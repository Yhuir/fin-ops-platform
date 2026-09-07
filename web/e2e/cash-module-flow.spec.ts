import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import type { CashFlow } from "../src/components/cash/CashFlows.types";

// Synthetic HTTP fixtures only. This file exercises real App Shell/HeroUI code,
// not PostgreSQL transactions or any production financial data.
const account = { id: "10000000-0000-4000-8000-000000000001", name: "合成现金账户", kind: "cash", opening_date: "2026-01-01", opening_amount: "50000.00", enabled: true, remark: null, version: 1 };
const category = { id: "10000000-0000-4000-8000-000000000002", name: "合成往来分类", group: "turnover", enabled: true, remark: null, version: 1 };
const principalId = "20000000-0000-4000-8000-000000000001";
const repaymentId = "20000000-0000-4000-8000-000000000002";
const itemId = "30000000-0000-4000-8000-000000000001";
const fixedNow = "2026-09-07T08:00:00.000Z";
function flow(id: string, kind: "receipt" | "payment", amount: string, content: string, day = "2026-09-01"): CashFlow {
  return { id, version: 1, occurred_on: day, kind, amount, from_account: kind === "payment" ? account : null, to_account: kind === "receipt" ? account : null, category,
    project: null, person_name: "合成测试人员", content, source_kind: "manual", task: null,
    income_amount: kind === "receipt" ? amount : null, expense_amount: kind === "payment" ? amount : null,
    account_running_balance: null, remark: null, created_by_account: "E2E-CASH", created_by_name: "合成测试", created_at: fixedNow, updated_at: fixedNow };
}
function totals(repaid: boolean) { return { principal_amount: "15000.00", opening_adjustment_amount: "0.00", repayment_amount: repaid ? "3000.00" : "0.00", reimbursement_received_amount: "0.00", ticket_offset_amount: "0.00", non_ticket_offset_amount: "0.00", real_expense_amount: "0.00", cash_received_amount: repaid ? "3000.00" : "0.00", cash_paid_amount: "12000.00", remaining_obligation_amount: { receivable: repaid ? "12000.00" : "15000.00", payable: "0.00" } }; }
async function installCashFixtures(page: Page, options: { firstCreateFailure?: boolean; denseFlows?: boolean } = {}) {
  const ordinary = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const calls: { method: string; path: string; query: string }[] = []; const submitted: Record<string, unknown>[] = [];
  const flows = options.denseFlows ? Array.from({ length: 51 }, (_, index) => flow(`20000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`, "receipt", "999999999999.99", `第${index + 1}笔合成流水：超长中文用途说明用于验证换行、滚动和最后一行完整显示`)) : [flow(principalId, "payment", "12000.00", "合成个人借出"), flow(repaymentId, "receipt", "3000.00", "合成现金归还", "2026-09-02")];
  let forbidden = false; let failCreate = options.firstCreateFailure ?? false;
  const paginate = (rows: unknown[], url: URL) => {
    const pageNumber = Number(url.searchParams.get("page") ?? "1"); const pageSize = Number(url.searchParams.get("page_size") ?? "50");
    return { rows: rows.slice((pageNumber - 1) * pageSize, pageNumber * pageSize), pagination: { page: pageNumber, page_size: pageSize, total: rows.length } };
  };
  await page.route("**/api/cash/**", async route => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname.slice("/api/cash".length); const method = request.method();
    calls.push({ method, path, query: url.search });
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
    if (forbidden) return json({ error: "cash_access_denied", message: "当前账号不可使用现金账。" }, 403);
    if (method === "POST" && path === "/flows") {
      const body = request.postDataJSON() as Record<string, unknown>; submitted.push(body);
      if (failCreate) { failCreate = false; return json({ error: "cash_busy", message: "合成测试：现金暂忙，请核实后重试。" }, 503); }
      expect(body).toMatchObject({ project_mode: "selection", kind: "receipt", amount: "88.60", oa_project_id: null, to_account_id: account.id, category_id: category.id });
      expect(body).not.toHaveProperty("actor"); expect(body).not.toHaveProperty("source_kind");
      const row = flow(String(body.id), "receipt", String(body.amount), String(body.content), String(body.occurred_on)); flows.unshift(row);
      return json({ flow: row, version: 1, related_items: [], origin_items: [], allocations: [] }, 201);
    }
    const deletedId = path.match(/^\/flows\/([^/]+)\/delete$/)?.[1];
    if (method === "POST" && deletedId) {
      expect(request.postDataJSON()).toMatchObject({ expected_version: 1 });
      const index = flows.findIndex(row => row.id === deletedId); expect(index).toBeGreaterThanOrEqual(0); flows.splice(index, 1);
      return json({ id: deletedId, deleted: true, already_deleted: false, affected_counts: { tasks: 0, items: deletedId === repaymentId ? 1 : 0, settlements: deletedId === repaymentId ? 1 : 0 }, affected_items: [], affected_tasks: [], affected_preview_truncated: false });
    }
    if (method !== "GET") throw new Error(`Unexpected synthetic cash write: ${method} ${path}`);
    if (path === "/reports/turnover") {
      const base = { row_kind: "principal", occurred_on: "2026-09-01", item_id: itemId, counterparty: "合成测试人员", project: null, category, content: "合成个人借出", state: "partial", original_amount: "12000.00", repayment_amount: null, reimbursement_received_amount: null, ticket_offset_amount: null, non_ticket_offset_amount: null, real_expense_amount: null, cash_received_amount: null, cash_paid_amount: "12000.00", remaining_after_event: "12000.00", flow_id: principalId, settlement_id: null, expense_item_id: null, ticket_collection_state: null, remark: null };
      let rows = [{ ...base, row_id: "company", ledger_group: "company", personal_variant: null, content: "合成公司往来", original_amount: "1000.00", cash_paid_amount: null, flow_id: null, remaining_after_event: "1000.00" }, { ...base, row_id: "external", ledger_group: "external_person", personal_variant: null, content: "合成外部往来", original_amount: "2000.00", cash_paid_amount: null, flow_id: null, remaining_after_event: "2000.00" }, { ...base, row_id: "personal-principal", ledger_group: "personal", personal_variant: "principal" }];
      if (flows.some(row => row.id === repaymentId)) rows.push({ ...base, row_id: "personal-repayment", row_kind: "settlement", ledger_group: "personal", personal_variant: "settlement", occurred_on: "2026-09-02", content: "合成现金归还", original_amount: null, cash_paid_amount: null, cash_received_amount: "3000.00", repayment_amount: "3000.00", remaining_after_event: "9000.00", flow_id: repaymentId } as typeof rows[number]);
      const ledger = url.searchParams.get("ledger_group"); const variant = url.searchParams.get("personal_variant");
      if (ledger) rows = rows.filter(row => row.ledger_group === ledger); if (variant) rows = rows.filter(row => row.personal_variant === variant);
      return json({ ...paginate(rows, url), summary: { ...totals(flows.some(row => row.id === repaymentId)), event_count: rows.length } });
    }
    if (path === "/flows") {
      let rows = flows;
      for (const key of ["kind", "source"] as const) { const value = url.searchParams.get(key); if (value) rows = rows.filter(row => (key === "source" ? row.source_kind : row.kind) === value); }
      const keyword = url.searchParams.get("keyword"); if (keyword) rows = rows.filter(row => row.content.includes(keyword));
      return json({ ...paginate(rows, url), summary: { period: { date_from: url.searchParams.get("date_from") ?? "2026-01-01", date_to: url.searchParams.get("date_to") ?? "2026-12-31" }, filtered_totals: { flow_count: rows.length, income_amount: "3000.00", expense_amount: "12000.00", transfer_amount: "0.00" }, account_balances: [{ account_id: account.id, account_name: account.name, opening_date: "2026-01-01", coverage_state: "complete", coverage_start: "2026-01-01", opening_balance: "50000.00", balance_at_coverage_start: "50000.00", period_inflow: "3000.00", period_outflow: "12000.00", ending_balance: "41000.00" }] } });
    }
    const detailId = path.match(/^\/flows\/([^/]+)$/)?.[1];
    if (detailId) {
      const row = flows.find(item => item.id === detailId); if (!row) return json({ error: "cash_not_found", message: "现金记录已删除。" }, 404);
      return json({ flow: row, allocations: [], allocation_count: 0, allocations_has_more: false, task: null, delete_impact: { flow_version: row.version, task_count: 0, item_count: detailId === repaymentId ? 1 : 0, settlement_count: detailId === repaymentId ? 1 : 0, source_owned_item_count: 0, source_correction_required: false, tasks: [], items: [], preview_truncated: false } });
    }
    if (path === "/items" || path === "/settlements" || path === "/reports/project-options") return json({ ...paginate([], url), ...(path === "/settlements" ? { summary: { amounts_by_kind: [] } } : {}) });
    if (path === "/settings/accounts") return json(paginate([account], url));
    if (path === "/settings/categories") return json(paginate([category], url));
    if (path === "/settings/bill-labels") return json(paginate([], url));
    if (path === "/settings/personal-opening") return json({ opening_date: null, version: 1 });
    if (path === "/settings/project-selection") return json({ allowed_stage_codes: ["implementation"], configured: true, version: 1 });
    if (path === "/projects") return json({ rows: [{ id: "610000000000000000000001", code: "E2E-001", name: "合成实施项目", stage_code: "implementation", stage_name: "实施", selectable: true, unavailable_reason: null }, { id: "610000000000000000000002", code: "E2E-002", name: "合成结束项目", stage_code: "end", stage_name: "已结束", selectable: false, unavailable_reason: "ended" }], stages: [{ code: "implementation", name: "实施" }, { code: "end", name: "已结束" }], total: 2, page: 1, page_size: 50, read_at: fixedNow, configured: true, selection_settings_version: 1 });
    if (path === "/reports/ticket-payments") return json({ ...paginate([], url), summary: { provided_amount: "0.00", used_amount: "0.00", offset_amount: "0.00", available_source_amount: "0.00", receivable_amount: "0.00", cash_received_amount: "0.00" } });
    if (path === "/reports/personal") return json({ ...paginate([], url), summary: { coverage: { state: "unconfigured", opening_date: null, coverage_start: null }, opening_obligation_amount: null, opening_adjustment_amount: null, new_principal_amount: null, cash_repayment_amount: null, ticket_offset_amount: null, non_ticket_offset_amount: null, remaining_obligation_amount: null } });
    if (path === "/task-occurrences") return json({ ...paginate([], url), summary: { task_count: 0, counts_by_state: { pending: 0, partial: 0, completed: 0 }, receipt_actual_amount: "0.00", payment_actual_amount: "0.00" } });
    if (path === "/tasks") return json(paginate([], url));
    throw new Error(`Unhandled synthetic cash query: ${path}`);
  });
  return { ordinary, submitted, count: (method: string, path: string) => calls.filter(row => row.method === method && row.path === path).length, calls, forbid: () => { forbidden = true; } };
}

test.describe("cash module deterministic browser flow", () => {
  test.beforeEach(async ({ page }) => { await page.clock.setFixedTime(new Date(fixedNow)); });

  test("renders all cash subpages, every tab, real table colors and confined wide-table overflow", async ({ page }, testInfo) => {
    await installCashFixtures(page); await page.goto("/cash?section=accounts");
    const navigation = page.getByRole("navigation", { name: "主导航" });
    for (const name of ["现金流水", "现金账目", "每月任务", "基础设置"]) await expect(navigation.getByRole("link", { name, exact: true })).toBeVisible();
    const table = page.getByRole("grid", { name: "往来账总表" }); await expect(table).toBeVisible(); await expect(table.getByRole("columnheader")).toHaveCount(17);
    const colors = await table.locator("tbody tr").evaluateAll(rows => rows.map(row => [...row.querySelectorAll("td,th")].map(cell => getComputedStyle(cell).backgroundColor)));
    expect(colors).toHaveLength(4);
    const rowHeight = (await table.locator("tbody tr").first().boundingBox())!.height;
    expect(rowHeight).toBeGreaterThanOrEqual(44); expect(rowHeight).toBeLessThanOrEqual(45);
    for (const [index, color] of ["rgb(255, 253, 240)", "rgb(239, 246, 255)", "rgb(255, 247, 237)", "rgb(240, 253, 244)"].entries()) expect(colors[index].every(value => value === color)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("cash-desktop-total.png"), fullPage: true });
    await page.getByRole("tab", { name: "有票支付", exact: true }).click(); await expect(page.getByRole("grid", { name: "有票支付", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "个人专账", exact: true }).click(); await expect(page.getByRole("grid", { name: "个人年度还款矩阵" })).toBeVisible();
    for (const [tab, grid] of [["现金归还", "个人现金归还"], ["有票直接冲", "有票直接冲"], ["无票报销冲抵", "无票报销冲抵"]]) { await page.getByRole("button", { name: /个人专账视图$/ }).click(); await page.getByRole("option", { name: tab, exact: true }).click(); await expect(page.getByRole("grid", { name: grid, exact: true })).toBeVisible(); }
    await page.getByRole("link", { name: "现金流水", exact: true }).click(); await expect(page.getByRole("grid", { name: "现金流水明细" })).toBeVisible();
    await navigation.getByRole("link", { name: "每月任务", exact: true }).click(); await expect(page.getByRole("tab", { name: "本月处理" })).toBeVisible();
    await page.getByRole("tab", { name: "任务配置" }).click(); await expect(page.getByRole("grid", { name: "任务模板" })).toBeVisible();
    await navigation.getByRole("link", { name: "基础设置", exact: true }).click(); await expect(page.getByRole("grid", { name: "现金账户", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "费用类型", exact: true }).click(); await expect(page.getByRole("grid", { name: "费用类型", exact: true })).toBeVisible();
    await page.getByRole("tab", { name: "OA 项目与可选阶段" }).click(); await expect(page.getByRole("grid", { name: "OA 项目列表" })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "实施", exact: true })).toBeChecked(); await expect(page.getByRole("checkbox", { name: "已结束（不允许新增）" })).toBeDisabled();
    await page.screenshot({ path: testInfo.outputPath("cash-project-settings.png"), fullPage: true });
    await page.getByRole("tab", { name: "支付办理说明" }).click(); await expect(page.getByRole("grid", { name: "支付办理参考" })).toBeVisible();
    await navigation.getByRole("link", { name: "现金账目", exact: true }).click(); await page.getByRole("tab", { name: "往来账总表", exact: true }).click(); await expect(table).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    const scroll = page.locator(".finance-table__scroll").filter({ has: table }); await expect(scroll).toBeVisible();
    expect(await scroll.evaluate(node => node.scrollWidth > node.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath("cash-narrow-total.png"), fullPage: true });
  });

  test("uses a stable submission ID on explicit retry and deletion rereads the cash pool and report", async ({ page }, testInfo) => {
    const api = await installCashFixtures(page, { firstCreateFailure: true }); await page.goto("/cash?section=accounts"); await expect(page.getByRole("grid", { name: "往来账总表" })).toBeVisible();
    await page.getByRole("link", { name: "现金流水", exact: true }).click(); await expect(page.getByRole("grid", { name: "现金流水明细" })).toBeVisible();
    await page.getByRole("button", { name: "新增流水", exact: true }).click(); await page.getByRole("menuitem", { name: "收入", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "新增现金流水" }); await expect(dialog).toBeVisible();
    await dialog.getByRole("textbox", { name: "金额（元）" }).fill("88.60"); await dialog.getByRole("textbox", { name: "用途", exact: true }).fill("合成新增现金流水");
    await dialog.getByRole("button", { name: /收款账户$/ }).click(); await page.getByRole("option", { name: account.name }).click();
    await dialog.getByRole("button", { name: /费用分类$/ }).click(); await page.getByRole("option", { name: category.name }).click();
    await page.screenshot({ path: testInfo.outputPath("cash-entry-drawer.png"), fullPage: true });
    await dialog.getByRole("button", { name: "保存", exact: true }).click(); await expect(dialog.getByRole("alert")).toContainText("现金暂忙");
    await expect(dialog.getByRole("textbox", { name: "用途", exact: true })).toHaveValue("合成新增现金流水");
    await dialog.getByRole("button", { name: "保存", exact: true }).click(); await expect(dialog).toHaveCount(0);
    expect(api.submitted).toHaveLength(2); expect(api.submitted[0].id).toMatch(/^[0-9a-f-]{36}$/); expect(api.submitted[1].id).toBe(api.submitted[0].id);
    await expect(page.getByRole("grid", { name: "现金流水明细" })).toContainText("合成新增现金流水");
    const beforeFlows = api.count("GET", "/flows");
    await page.getByRole("row").filter({ hasText: "合成现金归还" }).getByRole("button", { name: "详情", exact: true }).click();
    const detail = page.getByRole("dialog", { name: "现金流水详情" }); await expect(detail).toBeVisible(); await detail.getByRole("button", { name: "删除", exact: true }).click();
    const deletion = page.getByRole("dialog", { name: "删除现金流水" }); await expect(deletion.getByText("本笔现金没有来源事项。")).toBeVisible();
    await deletion.getByRole("button", { name: "确认删除", exact: true }).click(); await expect(deletion).toHaveCount(0);
    await expect(page.getByRole("grid", { name: "现金流水明细" })).not.toContainText("合成现金归还"); expect(api.count("GET", "/flows")).toBeGreaterThan(beforeFlows);
    const beforeReport = api.count("GET", "/reports/turnover"); await page.getByRole("link", { name: "现金账目", exact: true }).click();
    await expect(page.getByRole("grid", { name: "往来账总表" })).not.toContainText("合成现金归还"); expect(api.count("GET", "/reports/turnover")).toBeGreaterThan(beforeReport);
    expect(api.count("POST", `/flows/${repaymentId}/delete`)).toBe(1);
  });

  test("ordinary bank navigation does not request or display cash, and a 403 clears the mounted module", async ({ page }) => {
    const api = await installCashFixtures(page); await page.goto("/cash?section=accounts"); await expect(page.getByRole("grid", { name: "往来账总表" })).toBeVisible();
    await page.getByRole("link", { name: "银行明细", exact: true }).click(); await expect(page.getByTestId("bank-details-page")).toBeVisible(); await expect(page.getByRole("grid", { name: "交易流水" })).toBeVisible();
    const cashCalls = api.calls.length; await page.getByRole("grid", { name: "交易流水" }).getByRole("columnheader").first().focus();
    await expect(page.locator("body")).not.toContainText("合成个人借出"); expect(api.calls.length).toBe(cashCalls);
    expect(api.ordinary.count("GET /api/bank-details/transactions")).toBeGreaterThan(0);
    await page.getByRole("link", { name: "现金账目", exact: true }).click(); await expect(page.getByRole("grid", { name: "往来账总表" })).toBeVisible();
    api.forbid(); await page.getByRole("button", { name: "刷新", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("现金账权限已失效"); await expect(page.getByRole("grid", { name: "往来账总表" })).toHaveCount(0); await expect(page.locator("body")).not.toContainText("合成个人借出");
  });

  test("keeps applied filters across cash views, refetches on return, and resets all filters once", async ({ page }) => {
    const api = await installCashFixtures(page);
    let flowResponses = 0;
    page.on("response", response => { if (new URL(response.url()).pathname === "/api/cash/flows" && response.status() === 200) flowResponses += 1; });
    await page.goto("/cash?section=flows");
    const grid = page.getByRole("grid", { name: "现金流水明细" }); await expect(grid).toContainText("合成现金归还");
    await expect(page.getByRole("tab")).toHaveCount(0);
    await page.getByRole("textbox", { name: "搜索流水" }).fill("归还");
    await page.getByRole("button", { name: "查询", exact: true }).click(); await expect(grid).not.toContainText("合成个人借出");
    await page.getByRole("button", { name: /来源$/ }).click(); await page.getByRole("option", { name: "手动录入", exact: true }).click();
    await expect(grid).toContainText("合成现金归还");
    const before = flowResponses;
    await page.getByRole("link", { name: "现金账目", exact: true }).click();
    await page.getByRole("button", { name: "公司", exact: true }).click();
    await page.getByRole("tab", { name: "有票支付", exact: true }).click();
    await page.getByRole("tab", { name: "往来账总表", exact: true }).click();
    await expect(page.getByRole("button", { name: "公司", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("link", { name: "现金流水", exact: true }).click();
    await expect(grid).toContainText("合成现金归还"); await expect(grid).not.toContainText("合成个人借出");
    await expect(page.getByRole("textbox", { name: "搜索流水" })).toHaveValue("归还");
    // Development StrictMode may start an aborted mount GET; only the active request completes.
    expect(flowResponses).toBe(before + 1);
    const resetBefore = api.count("GET", "/flows");
    await page.getByRole("button", { name: "重置", exact: true }).click(); await expect(grid).toContainText("合成个人借出");
    expect(api.count("GET", "/flows")).toBe(resetBefore + 1);
    const url = new URL(`http://test/${api.calls.filter(row => row.path === "/flows").at(-1)!.query}`);
    expect(url.searchParams.has("keyword")).toBe(false); expect(url.searchParams.has("source")).toBe(false);
    expect(page.url()).toMatch(/\/cash\?section=flows$/);
    await page.getByRole("link", { name: "银行明细", exact: true }).click();
    await expect(page.getByRole("grid", { name: "交易流水" })).toBeVisible();
    await expect(page.locator(".cash-workspace")).toHaveCount(0);
    await page.getByRole("link", { name: "现金账目", exact: true }).click();
    await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
  });

  test("compact controls align without accounts, empty state stays below headers, and footer fits the viewport", async ({ page }, testInfo) => {
    await installCashFixtures(page);
    await page.route("**/api/cash/settings/accounts?**", route => route.fulfill({ json: { rows: [], pagination: { page: 1, page_size: 100, total: 0 } } }));
    await page.route("**/api/cash/flows?**", route => route.fulfill({ json: { rows: [], pagination: { page: 1, page_size: 50, total: 0 }, summary: { period: { date_from: "2026-01-01", date_to: "2026-09-07" }, filtered_totals: { income_amount: "0.00", expense_amount: "0.00", transfer_amount: "0.00", flow_count: 0 }, account_balances: [] } } }));
    await page.setViewportSize({ width: 1800, height: 847 }); await page.goto("/cash?section=flows");
    const grid = page.getByRole("grid", { name: "现金流水明细" }); await expect(grid).toContainText("该范围内没有现金流水");
    const geometry = await page.locator(".cash-page").evaluate(root => {
      const controls = [...root.querySelectorAll(".cash-toolbar--compact .select__trigger")].map(node => node.getBoundingClientRect());
      const table = root.querySelector(".cash-main-table")!, header = table.querySelector("thead")!, empty = table.querySelector(".cash-empty")!;
      return { heights: controls.map(rect => rect.height), tops: controls.map(rect => rect.top), headerHeight: header.getBoundingClientRect().height,
        emptyInside: Boolean(empty.closest("tbody")), headerBottom: header.getBoundingClientRect().bottom, emptyTop: empty.getBoundingClientRect().top,
        footerBottom: table.querySelector(".finance-table__footer")!.getBoundingClientRect().bottom, tableHeight: table.getBoundingClientRect().height };
    });
    expect(geometry.heights.every(height => Math.abs(height - 32) < 1)).toBe(true);
    expect(Math.max(...geometry.tops) - Math.min(...geometry.tops)).toBeLessThan(1);
    expect(geometry.headerHeight).toBeGreaterThanOrEqual(35); expect(geometry.headerHeight).toBeLessThanOrEqual(37);
    expect(geometry.emptyInside).toBe(true); expect(geometry.emptyTop).toBeGreaterThanOrEqual(geometry.headerBottom);
    expect(geometry.tableHeight).toBeGreaterThan(500); expect(geometry.footerBottom).toBeLessThanOrEqual(847);
    await page.screenshot({ path: testInfo.outputPath("cash-compact-empty.png") });
    for (const zoom of [1.25, 1.5]) {
      await page.locator("body").evaluate((body, value) => { body.style.zoom = String(value); }, zoom);
      await page.getByRole("button", { name: "新增流水", exact: true }).scrollIntoViewIfNeeded();
      await expect(page.getByRole("button", { name: "新增流水", exact: true })).toBeInViewport();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBe(true);
    }
  });

  test("full pages keep large amounts inside their columns and the last row above the footer", async ({ page }) => {
    await installCashFixtures(page, { denseFlows: true });
    await page.setViewportSize({ width: 1440, height: 900 }); await page.goto("/cash?section=flows");
    const grid = page.getByRole("grid", { name: "现金流水明细" });
    await expect(grid.locator("tbody tr")).toHaveCount(50);
    const amounts = await grid.locator('tbody [data-column-role="amount"]').evaluateAll(cells => cells.map(cell => {
      const range = document.createRange(); range.selectNodeContents(cell);
      const content = range.getBoundingClientRect(), box = cell.getBoundingClientRect();
      return { left: content.left - box.left, right: box.right - content.right };
    }));
    expect(amounts.every(amount => amount.left >= 7 && amount.right >= 7), JSON.stringify(amounts.slice(0, 4))).toBe(true);
    const scroll = page.locator(".finance-table__scroll").filter({ has: grid });
    await scroll.evaluate(node => { node.scrollTop = node.scrollHeight; });
    await expect(grid.getByText(/第50笔合成流水/)).toBeInViewport();
    const last = await grid.locator("tbody tr").last().boundingBox();
    const footer = await page.locator(".cash-main-table .finance-table__footer").boundingBox();
    expect(last!.y + last!.height).toBeLessThanOrEqual(footer!.y + 1);
    expect(footer!.y + footer!.height).toBeLessThanOrEqual(900);
    await page.getByRole("button", { name: "下一页", exact: true }).click();
    await expect(grid.locator("tbody tr")).toHaveCount(1); await expect(grid).toContainText("第51笔合成流水");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBe(true);
  });

  test("rejects malformed cash sections without querying cash and normalizes only the bare route", async ({ page }) => {
    const api = await installCashFixtures(page);
    for (const path of ["/cash?section=wrong", "/cash?section=flows&section=accounts", "/cash?section=flows&keyword=private"]) {
      await page.goto(path); await expect(page.getByRole("alert")).toContainText("现金页面地址不正确");
      expect(api.calls).toHaveLength(0);
    }
    await page.goto("/cash"); await expect(page).toHaveURL(/\/cash\?section=accounts$/);
    await expect(page.getByRole("grid", { name: "往来账总表" })).toContainText("合成个人借出");
  });

  test("account filters page and search inside the popover without moving or closing the toolbar", async ({ page }) => {
    await installCashFixtures(page);
    await page.route("**/api/cash/settings/accounts?**", route => {
      const params = new URL(route.request().url()).searchParams;
      expect(params.has("enabled")).toBe(false);
      const pageNumber = Number(params.get("page")); const keyword = params.get("keyword");
      const rows = keyword || pageNumber === 2 ? [{ ...account, name: "历史停用账户", enabled: false }] : Array.from({ length: 100 }, (_, index) => ({ ...account, id: `10000000-0000-4000-8000-${String(index + 10).padStart(12, "0")}`, name: `合成账户${index}` }));
      return route.fulfill({ json: { rows, pagination: { page: pageNumber, page_size: 100, total: keyword ? 1 : 101 } } });
    });
    await page.goto("/cash?section=flows"); await expect(page.getByRole("grid", { name: "现金流水明细" })).toContainText("合成现金归还");
    const trigger = page.getByRole("button", { name: /账户$/ });
    const before = await trigger.boundingBox(); await trigger.click();
    const popup = page.locator(".cash-select-popover");
    await popup.getByRole("button", { name: "下一页", exact: true }).click();
    await expect(popup.getByRole("option", { name: "历史停用账户", exact: true })).toBeVisible();
    await popup.getByRole("textbox", { name: "搜索账户" }).fill("历史");
    await expect(popup.getByRole("textbox", { name: "搜索账户" })).toHaveValue("历史");
    await expect(popup.getByRole("textbox", { name: "搜索账户" })).toBeFocused();
    await popup.getByRole("option", { name: "历史停用账户", exact: true }).click();
    await expect(trigger).toContainText("历史停用账户");
    const after = await trigger.boundingBox(); expect(after!.y).toBe(before!.y); expect(after!.height).toBe(32);
    await page.getByRole("link", { name: "现金账目", exact: true }).click();
    await page.getByRole("link", { name: "现金流水", exact: true }).click();
    await expect(trigger).toContainText("历史停用账户");
  });
});
