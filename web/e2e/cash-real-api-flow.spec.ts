import { expect, test, setCheckbox, type Page } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

// Independent of the mocked visual suite. All HTTP responses, including cash,
// come from the loopback Application/CashRuntime and the disposable PostgreSQL DB.
const enabled = process.env.FIN_OPS_CASH_REAL_E2E === "1";
test.use({ screenshot: "off", trace: "off", video: "off" });

test.describe("cash browser -> real HTTP -> PostgreSQL", () => {
  test.skip(!enabled, "Run python3 -m tests.test_cash_http_integration --browser-e2e with a disposable cash DSN.");

  test("manually enters two flows, applies header multi-select and removes both cash contributions", async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    page.setDefaultTimeout(15_000);
    if (!baseURL || new URL(baseURL).hostname !== "127.0.0.1" || process.env.FIN_OPS_CASH_REAL_TOKEN !== "test-suite-oa-token") {
      throw new Error("Real cash write E2E requires the explicit loopback test fixture; production is forbidden.");
    }
    const account = JSON.parse(process.env.FIN_OPS_CASH_REAL_ACCOUNT!) as { id: string; name: string };
    const category = JSON.parse(process.env.FIN_OPS_CASH_REAL_CATEGORY!) as { id: string; name: string };
    const token = process.env.FIN_OPS_CASH_REAL_TOKEN;
    await page.context().setExtraHTTPHeaders({ Authorization: `Bearer ${token}` });
    await page.context().addCookies([{ name: "Admin-Token", value: token, domain: "127.0.0.1", path: "/", sameSite: "Lax" }]);
    await page.clock.setFixedTime(new Date("2026-09-07T08:00:00.000Z"));

    const secondAccountResponse = await page.request.post("/api/cash/settings/accounts", { data: {
      id: crypto.randomUUID(), name: "合成真实链账户乙", kind: "savings", opening_date: "2026-01-01", opening_amount: "0.00",
    } });
    expect(secondAccountResponse.status()).toBe(201);
    const secondAccount = (await secondAccountResponse.json()).account as { id: string; name: string };
    const secondCategoryResponse = await page.request.post("/api/cash/settings/categories", { data: {
      id: crypto.randomUUID(), name: "合成真实链收入乙", group: "receipt",
    } });
    expect(secondCategoryResponse.status()).toBe(201);
    const secondCategory = (await secondCategoryResponse.json()).category as { id: string; name: string };

    const reads: URL[] = [];
    page.on("response", response => {
      if (new URL(response.url()).pathname === "/api/cash/flows" && response.request().method() === "GET" && response.status() === 200) reads.push(new URL(response.url()));
    });
    await page.goto("/cash?section=flows");
    const grid = page.getByRole("grid", { name: "现金流水明细" });
    await expect(grid).toBeVisible();
    await expect.poll(() => reads.length).toBeGreaterThan(0);
    expect(reads[0].searchParams.get("time_scope")).toBe("all");
    expect(reads[0].searchParams.has("date_from")).toBe(false);
    await page.getByRole("button", { name: /时间范围$/ }).click();
    await page.getByRole("option", { name: "自定义", exact: true }).click();
    await page.getByLabel("起始日期", { exact: true }).fill("2026-09-01");
    await page.getByLabel("截止日期", { exact: true }).fill("2026-09-30");
    await page.getByRole("button", { name: "查询", exact: true }).click();
    const firstId = await enterReceipt(page, account.name, category.name, "100.00", "合成真实链收入甲");
    const secondId = await enterReceipt(page, secondAccount.name, secondCategory.name, "40.00", "合成真实链收入乙");

    async function applyColumn(label: string, names: string[], field: string, values: string[]) {
      await grid.getByRole("button", { name: `筛选${label}`, exact: true }).click();
      const popup = page.getByRole("dialog", { name: `筛选${label}`, exact: true });
      await expect(popup).toBeVisible();
      for (const name of names) await setCheckbox(popup.getByRole("checkbox", { name, exact: true }));
      const before = reads.length;
      const applied = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === "/api/cash/flows" && url.searchParams.has(field) && response.status() === 200;
      });
      await popup.getByRole("button", { name: "应用", exact: true }).click();
      const response = await applied;
      expect(response.headers()["cache-control"]).toContain("no-store");
      expect(JSON.parse(new URL(response.url()).searchParams.get(field)!)).toEqual(values);
      await expect(popup).toHaveCount(0);
      await expect(grid).toContainText("合成真实链收入甲");
      await expect(grid).toContainText("合成真实链收入乙");
      expect(reads.length - before).toBe(1);
      return response.json();
    }
    await applyColumn("账户", [account.name, secondAccount.name], "account_ids", [account.id, secondAccount.id]);
    const filtered = await applyColumn("分类", [category.name, secondCategory.name], "category_ids", [category.id, secondCategory.id]);
    expect(filtered.pagination.total).toBe(2);
    expect(filtered.summary.filtered_totals).toEqual({ flow_count: 2, income_amount: "140.00", expense_amount: "0.00", transfer_amount: "0.00" });
    expect(filtered.rows.every((row: { account_running_balance: string | null }) => row.account_running_balance === null)).toBe(true);
    await expect(page.locator(".cash-summary")).toContainText("收入 140.00");

    for (const [id, content, remaining] of [[firstId, "合成真实链收入甲", "40.00"], [secondId, "合成真实链收入乙", "0.00"]]) {
      await grid.getByRole("row").filter({ hasText: content }).getByRole("button", { name: "详情", exact: true }).click();
      const detail = page.getByRole("dialog", { name: "现金流水详情" });
      await detail.getByRole("button", { name: "删除", exact: true }).click();
      const deletion = page.getByRole("dialog", { name: "删除现金流水" });
      const removed = page.waitForResponse(response => new URL(response.url()).pathname === `/api/cash/flows/${id}/delete`);
      await deletion.getByRole("button", { name: "确认删除", exact: true }).click();
      expect((await removed).status()).toBe(200);
      await expect(deletion.getByRole("status")).toHaveText("现金流水已删除");
      await deletion.getByRole("button", { name: "关闭抽屉", exact: true }).click();
      await expect(deletion).toHaveCount(0);
      await expectNoUnexpectedSuccessUiErrors(page);
      await expect(grid).not.toContainText(content);
      await expect(page.locator(".cash-summary")).toContainText(`收入 ${remaining}`);
      const missing = await page.request.get(`/api/cash/flows/${id}`);
      expect(missing.status()).toBe(404);
    }
    const final = await page.request.get("/api/cash/flows?date_from=2026-09-01&date_to=2026-09-30");
    expect(final.status()).toBe(200);
    const finalBody = await final.json();
    expect(finalBody.pagination.total).toBe(0);
    expect(finalBody.summary.filtered_totals.income_amount).toBe("0.00");
    expect(finalBody.summary.account_balances.map((row: { ending_balance: string }) => row.ending_balance).sort()).toEqual(["0.00", "1000.00"]);
    await page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "现金账目", exact: true }).click();
    await expect(page.getByRole("grid", { name: "往来账总表" })).toContainText("当前条件下暂无记录");
    const beforeReentry = reads.length;
    await page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "现金流水", exact: true }).click();
    await expect.poll(() => reads.length).toBeGreaterThan(beforeReentry);
    expect(reads[beforeReentry].searchParams.get("time_scope")).toBe("all");
    expect(reads[beforeReentry].searchParams.has("date_from")).toBe(false);
    expect(JSON.parse(reads[beforeReentry].searchParams.get("account_ids")!)).toEqual([account.id, secondAccount.id]);
    const beforeReload = reads.length;
    await page.reload();
    await expect.poll(() => reads.length).toBeGreaterThan(beforeReload);
    expect(reads[beforeReload].searchParams.get("time_scope")).toBe("all");
  });

  test("existing loan origin backfill uses fixed context, returns to detail and reverses without deleting the loan", async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    if (!baseURL || new URL(baseURL).hostname !== "127.0.0.1" || process.env.FIN_OPS_CASH_REAL_TOKEN !== "test-suite-oa-token") throw new Error("Origin backfill requires isolated loopback cash fixture.");
    const token = process.env.FIN_OPS_CASH_REAL_TOKEN;
    const account = JSON.parse(process.env.FIN_OPS_CASH_REAL_ACCOUNT!) as { id: string; name: string };
    const category = JSON.parse(process.env.FIN_OPS_CASH_REAL_CATEGORY!) as { id: string; name: string };
    await page.context().setExtraHTTPHeaders({ Authorization: `Bearer ${token}` });
    await page.context().addCookies([{ name: "Admin-Token", value: token, domain: "127.0.0.1", path: "/", sameSite: "Lax" }]);
    await page.clock.setFixedTime(new Date("2026-09-07T08:00:00.000Z"));
    const created = await page.request.post("/api/cash/items", { data: { id: crypto.randomUUID(), type: "loan", origin_date: "2026-09-03", original_amount: "15.00", content: "合成来源补录借款", oa_project_id: null, counterparty: "合成公司", ledger_group: "company", obligation_direction: "receivable" } });
    expect(created.status()).toBe(201); const item = (await created.json()).item;
    await page.goto("/cash?section=accounts");
    await page.getByRole("button", { name: "事项管理", exact: true }).click();
    await page.getByRole("row").filter({ hasText: "合成来源补录借款" }).getByRole("button", { name: "选择", exact: true }).click();
    const detail = page.getByRole("dialog", { name: "事项详情", exact: true });
    await detail.getByRole("button", { name: "补记这笔借款的原始收付", exact: true }).click();
    const entry = page.getByRole("dialog", { name: "新增现金流水", exact: true });
    await expect(entry.getByLabel("实际发生日", { exact: true })).toBeDisabled();
    await expect(entry.getByLabel("实际发生日", { exact: true })).toHaveValue("2026-09-03");
    await expect(entry.getByRole("radio")).toHaveCount(0);
    await expect(entry.getByRole("button", { name: "选择项目", exact: true })).toHaveCount(0);
    await entry.getByRole("button", { name: /付款账户$/ }).click(); await page.getByRole("option", { name: account.name, exact: true }).click();
    await entry.getByRole("button", { name: /费用分类$/ }).click(); await page.getByRole("option", { name: category.name, exact: true }).click();
    const saving = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/flows" && response.request().method() === "POST");
    await entry.getByRole("button", { name: "保存", exact: true }).click();
    const response = await saving; expect(response.status()).toBe(201); const flow = (await response.json()).flow;
    await expect(entry.getByRole("status")).toHaveText("现金流水已保存");
    await entry.getByRole("button", { name: "关闭抽屉", exact: true }).click();
    await expect(detail).toBeVisible();
    await expect(detail.getByRole("button", { name: "补记这笔借款的原始收付", exact: true })).toHaveCount(0);
    const linked = await page.request.get(`/api/cash/items/${item.id}`); const linkedItem = await linked.json();
    expect(linkedItem.item.origin_flow_id).toBe(flow.id); expect(linkedItem.item.original_amount).toBe("15.00");
    expect(linkedItem.amounts.remaining_obligation_amount).toBe("15.00");
    await detail.getByRole("button", { name: "来源流水 / 纠错", exact: true }).click();
    await page.getByRole("dialog", { name: "现金流水详情", exact: true }).getByRole("button", { name: "删除", exact: true }).click();
    const removal = page.waitForResponse(result => new URL(result.url()).pathname === `/api/cash/flows/${flow.id}/delete`);
    await page.getByRole("dialog", { name: "删除现金流水", exact: true }).getByRole("button", { name: "确认删除", exact: true }).click();
    expect((await removal).status()).toBe(200);
    const restored = await page.request.get(`/api/cash/items/${item.id}`); expect(restored.status()).toBe(200); const old = await restored.json();
    expect(old.item.origin_flow_id).toBeNull(); expect(old.item.original_amount).toBe("15.00");
    expect(old.amounts.remaining_obligation_amount).toBe("15.00");
    const cleanup = await page.request.post(`/api/cash/items/${item.id}/remove`, { data: { expected_version: old.item.version } });
    expect(cleanup.status()).toBe(200);
    expect((await page.request.get(`/api/cash/flows/${flow.id}`)).status()).toBe(404);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("personal opening, task advance, classified noncash adjustment and old pending tickets form one real chain", async ({ page, baseURL }) => {
    test.setTimeout(180_000);
    if (!baseURL || new URL(baseURL).hostname !== "127.0.0.1" || process.env.FIN_OPS_CASH_REAL_TOKEN !== "test-suite-oa-token") throw new Error("Real cash write E2E requires the loopback test fixture.");
    const token = process.env.FIN_OPS_CASH_REAL_TOKEN;
    const account = JSON.parse(process.env.FIN_OPS_CASH_REAL_ACCOUNT!) as { id: string; name: string };
    const category = JSON.parse(process.env.FIN_OPS_CASH_REAL_CATEGORY!) as { id: string; name: string };
    await page.context().setExtraHTTPHeaders({ Authorization: `Bearer ${token}` });
    await page.context().addCookies([{ name: "Admin-Token", value: token, domain: "127.0.0.1", path: "/", sameSite: "Lax" }]);
    await page.clock.setFixedTime(new Date("2026-09-07T08:00:00.000Z"));
    await page.goto("/cash?section=settings");
    await page.getByRole("button", { name: "设置起算日期", exact: true }).click();
    const setting = page.getByRole("dialog", { name: "设置个人账起算" });
    await setting.getByLabel("个人账起算日期").fill("2026-01-01");
    await setting.getByRole("textbox", { name: "个人专账归属人" }).fill("真实浏览器合成人员");
    await setting.getByRole("button", { name: "保存起算", exact: true }).click();
    await expect(setting.getByRole("status")).toHaveText("操作已完成");
    await setting.getByRole("button", { name: "关闭抽屉", exact: true }).click();
    await expect(setting).toHaveCount(0); await expectNoUnexpectedSuccessUiErrors(page);
    await page.getByRole("button", { name: "登记期初未结", exact: true }).click();
    const opening = page.getByRole("dialog", { name: "新建事项" });
    await expect(opening.getByRole("textbox", { name: "往来对象" })).toHaveValue("真实浏览器合成人员");
    await expect(opening.getByLabel("起算日期", { exact: false })).toHaveValue("2026-01-01");
    await opening.getByRole("textbox", { name: "期初未结金额" }).fill("500.00");
    await opening.getByRole("textbox", { name: "事项内容" }).fill("无本期动作的合成旧欠款");
    const openingSaved = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/items" && response.request().method() === "POST");
    await opening.getByRole("button", { name: "保存事项", exact: true }).click();
    const openingResponse = await openingSaved; expect(openingResponse.status()).toBe(201);
    const oldItem = (await openingResponse.json()).item;
    await expect(opening.getByRole("status")).toHaveText("事项已保存");
    await opening.getByRole("button", { name: "关闭抽屉", exact: true }).click();
    await expect(opening).toHaveCount(0); await expectNoUnexpectedSuccessUiErrors(page);

    const taskResponse = await page.request.post("/api/cash/tasks", { data: { id: crypto.randomUUID(), title: "合成信用卡代付任务", kind: "payment", execution_day: 5, remind_days: 2, effective_from_month: "2026-09", default_amount: "100.00", default_account_id: account.id, default_category_id: category.id } });
    expect(taskResponse.status()).toBe(201);
    await page.goto("/cash?section=tasks");
    await page.getByRole("row").filter({ hasText: "合成信用卡代付任务" }).getByRole("button", { name: "已付 / 已还", exact: true }).click();
    const task = page.getByRole("dialog", { name: "办理任务 · 合成信用卡代付任务" });
    await task.getByRole("textbox", { name: "金额（元）" }).fill("100.00");
    await task.getByRole("textbox", { name: "内容说明", exact: true }).fill("合成明确个人代付");
    await task.getByRole("button", { name: "新增借款 / 代付", exact: true }).click();
    await task.getByRole("button", { name: /账簿分类$/ }).click();
    await page.getByRole("option", { name: "个人借款 / 代付", exact: true }).click();
    await expect(task.getByRole("textbox", { name: "往来对象" })).toHaveValue("真实浏览器合成人员");
    const confirmed = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/task-occurrences/confirm");
    await task.getByRole("button", { name: "保存并确认任务", exact: true }).click();
    const confirmedResponse = await confirmed; expect(confirmedResponse.status()).toBe(200);
    const confirmedBody = await confirmedResponse.json(); expect(confirmedBody.flow.source_kind).toBe("monthly_task");
    await expect(task.getByRole("status")).toHaveText("现金流水已保存");
    await task.getByRole("button", { name: "关闭抽屉", exact: true }).click();
    await expect(task).toHaveCount(0); await expectNoUnexpectedSuccessUiErrors(page);
    const personalResponse = await page.request.get("/api/cash/reports/personal?year=2026");
    const personal = await personalResponse.json(); expect(personal.summary.remaining_obligation_amount).toBe("600.00");
    expect(personal.summary.month_principal_totals[8].principal_amount).toBe("100.00");

    await page.goto("/cash?section=accounts");
    await page.getByRole("button", { name: /往来账视图$/ }).click(); await page.getByRole("option", { name: "截至期末未结事项", exact: true }).click();
    const unsettled = page.getByRole("grid", { name: "截至期末未结事项" });
    await expect(unsettled).toContainText("无本期动作的合成旧欠款");
    await unsettled.getByRole("row").filter({ hasText: "无本期动作的合成旧欠款" }).getByRole("button", { name: "详情 / 办理", exact: true }).click();
    const detail = page.getByRole("dialog", { name: "事项详情" });
    await detail.getByRole("button", { name: "无票 / 其他冲抵", exact: true }).click();
    await detail.getByRole("textbox", { name: "本次处理金额" }).fill("50.00");
    await detail.getByRole("textbox", { name: "用途 / 说明" }).fill("合成已明确非现金调整");
    await detail.getByRole("button", { name: /无来源调整分类$/ }).click(); await page.getByRole("option", { name: category.name, exact: true }).click();
    const adjusted = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/settlements" && response.request().method() === "POST");
    await detail.getByRole("button", { name: "保存处理", exact: true }).click();
    expect((await adjusted).status()).toBe(201);
    await expect(detail.locator(".cash-facts")).toContainText("450.00"); await expectNoUnexpectedSuccessUiErrors(page);
    const current = await (await page.request.get(`/api/cash/items/${oldItem.id}`)).json();
    expect(current.amounts.remaining_obligation_amount).toBe("450.00");
    await detail.getByRole("button", { name: "关闭抽屉" }).click();
    await expect(unsettled).toContainText("450.00");

    await unsettled.getByRole("row").filter({ hasText: "无本期动作的合成旧欠款" }).getByRole("button", { name: "详情 / 办理", exact: true }).click();
    await detail.getByRole("button", { name: "登记实际收付", exact: true }).click();
    const repayment = page.getByRole("dialog", { name: "新增现金流水" });
    await repayment.getByRole("textbox", { name: "金额（元）" }).fill("25.00");
    await repayment.getByRole("textbox", { name: "内容说明", exact: true }).fill("合成旧借款实际现金归还");
    await repayment.getByRole("button", { name: /收款账户$/ }).click(); await page.getByRole("option", { name: account.name, exact: true }).click();
    await repayment.getByRole("button", { name: /费用分类$/ }).click(); await page.getByRole("option", { name: category.name, exact: true }).click();
    await repayment.getByRole("textbox", { name: "本次处理金额" }).fill("25.00");
    const repaid = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/flows" && response.request().method() === "POST");
    await repayment.getByRole("button", { name: "保存", exact: true }).click();
    const repaidResponse = await repaid; expect(repaidResponse.status(), await repaidResponse.text()).toBe(201);
    const repaidBody = await repaidResponse.json();
    expect(repaidBody.allocations).toEqual([expect.objectContaining({ item_id: oldItem.id, kind: "cash_repayment", amount: "25.00" })]);
    await expect(repayment.getByRole("status")).toHaveText("现金流水已保存");
    await repayment.getByRole("button", { name: "关闭抽屉", exact: true }).click();
    await expect(repayment).toHaveCount(0); await expectNoUnexpectedSuccessUiErrors(page);
    await expect(unsettled).toContainText("425.00");
    const afterRepayment = await (await page.request.get(`/api/cash/items/${oldItem.id}`)).json();
    expect(afterRepayment.amounts.remaining_obligation_amount).toBe("425.00");

    const ticketResponse = await page.request.post("/api/cash/items", { data: { id: crypto.randomUUID(), type: "ticket_source", origin_date: "2025-12-20", original_amount: "80.00", ticket_provider: "合成公司经办人", ticket_provided_on: "2025-12-20", ticket_description: "合成旧年票据", content: "合成旧年待回款票据" } });
    expect(ticketResponse.status()).toBe(201); const ticketItem = (await ticketResponse.json()).item;
    const receivableResponse = await page.request.post("/api/cash/items", { data: { id: crypto.randomUUID(), type: "company_receivable", origin_date: "2025-12-20", original_amount: "80.00", ledger_group: "company", obligation_direction: "receivable", counterparty: "合成公司", ticket_source_id: ticketItem.id, expected_related_versions: { items: [{ id: ticketItem.id, version: ticketItem.version }] }, content: "明确旧年公司应收" } });
    expect(receivableResponse.status(), await receivableResponse.text()).toBe(201);
    const allTickets = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === "/api/cash/reports/ticket-payments" && url.searchParams.get("time_scope") === "all" && response.status() === 200;
    });
    await page.getByRole("tab", { name: "有票支付", exact: true }).click();
    const allTicketResponse = await allTickets;
    expect((await allTicketResponse.json()).rows).toEqual(expect.arrayContaining([expect.objectContaining({ id: ticketItem.id, ticket_provided_on: "2025-12-20" })]));
    await expect(page.getByRole("grid", { name: "有票支付", exact: true })).toContainText("合成旧年待回款票据");
    await page.getByRole("button", { name: /有票支付视图$/ }).click(); await page.getByRole("option", { name: "待回款", exact: true }).click();
    const tickets = page.getByRole("grid", { name: "有票支付", exact: true });
    await expect(tickets).toContainText("合成旧年待回款票据");
    await expect(tickets.getByRole("columnheader", { name: "非现金结清", exact: true })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});

async function enterReceipt(page: Page, account: string, category: string, amount: string, content: string): Promise<string> {
  await page.getByRole("button", { name: "新增流水", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增现金流水" });
  await dialog.getByLabel("实际发生日", { exact: true }).fill("2026-09-03");
  await dialog.getByRole("textbox", { name: "金额（元）" }).fill(amount);
  await dialog.getByRole("textbox", { name: "内容说明", exact: true }).fill(content);
  await dialog.getByRole("button", { name: /收款账户$/ }).click();
  await page.getByRole("option", { name: account, exact: true }).click();
  await dialog.getByRole("button", { name: /费用分类$/ }).click();
  await page.getByRole("option", { name: category, exact: true }).click();
  const saved = page.waitForResponse(response => new URL(response.url()).pathname === "/api/cash/flows" && response.request().method() === "POST");
  await dialog.getByRole("button", { name: "保存", exact: true }).click();
  const response = await saved;
  expect(response.status()).toBe(201);
  const body = await response.json();
  expect(body.flow.source_kind).toBe("manual");
  await expect(dialog.getByRole("status")).toHaveText("现金流水已保存");
  await dialog.getByRole("button", { name: "关闭抽屉", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("grid", { name: "现金流水明细" })).toContainText(content);
  await expectNoUnexpectedSuccessUiErrors(page);
  return body.flow.id;
}
