import { expect, test, setCheckbox, type Page } from "./fixtures/strictTest";

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
      await expect(deletion).toHaveCount(0);
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
  });
});

async function enterReceipt(page: Page, account: string, category: string, amount: string, content: string): Promise<string> {
  await page.getByRole("button", { name: "新增流水", exact: true }).click();
  await page.getByRole("menuitem", { name: "收入", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "新增现金流水" });
  await dialog.getByLabel("实际发生日", { exact: true }).fill("2026-09-03");
  await dialog.getByRole("textbox", { name: "金额（元）" }).fill(amount);
  await dialog.getByRole("textbox", { name: "用途", exact: true }).fill(content);
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
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("grid", { name: "现金流水明细" })).toContainText(content);
  return body.flow.id;
}
