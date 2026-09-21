import { expect, test } from "./fixtures/strictTest";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN ?? "";
test.use({ screenshot: "off", trace: "off", video: "off" });

// Read-only production checks: no business payload, cookie, or screenshot is recorded.
test("ordinary date filters start in all time and preserve only same-visit selections", async ({ page, baseURL }) => {
  test.skip(!enabled || !token, "Requires explicit production mode and token wrapper.");
  test.setTimeout(240_000);
  const blockedWrites: string[] = [];
  await page.context().addCookies([{ name: "Admin-Token", value: token,
    domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
  await page.route("**/*", async route => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
      blockedWrites.push(new URL(route.request().url()).pathname);
      await route.abort("blockedbyclient"); return;
    }
    await route.continue();
  });
  const results: { path: string; status: number; milliseconds: number }[] = [];
  const entries = [
    ["/", "/api/workbench/groups", "month", "all"],
    ["/bank-details", "/api/bank-details/transactions", "date_from", ""],
    ["/oa-pending-payments", "/api/oa-pending-payments/rows", "month", ""],
    ["/input-invoice-usage", "/api/input-invoice-usage/rows", "month", ""],
    ["/output-invoice-collections", "/api/output-invoice-collections/rows", "month", ""],
    ["/bank-flow-rule-batches", "/api/bank-flow-rule-batches", "month", ""],
    ["/batch-accounting", "/api/batch-accounting", "bank_year", "all"],
    ["/cost-statistics", "/api/cost-statistics/explorer", "scope", "all"],
    ["/cash?section=flows", "/api/cash/flows", "time_scope", "all"],
    ["/cash?section=accounts", "/api/cash/reports/turnover", "time_scope", "all"],
  ];
  for (const [path, endpoint, key, value] of entries) {
    const started = performance.now();
    const incoming = page.waitForResponse(response => new URL(response.url()).pathname.endsWith(endpoint)
      && response.request().method() === "GET");
    await page.goto(`/fin-ops${path}`, { waitUntil: "domcontentloaded" });
    const response = await incoming;
    expect(response.status(), path).toBe(200);
    const params = new URL(response.url()).searchParams;
    expect(params.get(key) ?? "", path).toBe(value);
    for (const date of ["date_from", "date_to", "invoice_date_from", "invoice_date_to"]) {
      expect(params.get(date) ?? "", `${path}: ${date}`).toBe("");
    }
    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    if (["/", "/bank-details", "/oa-pending-payments", "/output-invoice-collections", "/bank-flow-rule-batches", "/batch-accounting", "/cost-statistics"].includes(path)) {
      const all = page.getByRole("button", { name: "全部", exact: true });
      await expect(all.first()).toBeVisible();
      for (const button of await all.all()) await expect(button).toHaveAttribute("aria-pressed", "true");
    }
    results.push({ path, status: response.status(), milliseconds: Math.round(performance.now() - started) });
  }
  await page.goto("/fin-ops/bank-details");
  const pickerTrigger = page.getByRole("button", { name: "银行明细时间范围：年月" });
  await pickerTrigger.click();
  const picker = page.getByRole("dialog", { name: "银行明细时间范围选择器" });
  await picker.getByRole("button", { name: "按月", exact: true }).click();
  const chosen = page.waitForResponse(response => new URL(response.url()).pathname.endsWith("/api/bank-details/transactions")
    && Boolean(new URL(response.url()).searchParams.get("date_from")));
  await picker.getByRole("button", { name: "一月", exact: true }).click();
  const monthResponse = await chosen;
  const selectedMonth = new URL(monthResponse.url()).searchParams.get("date_from");
  const refresh = page.waitForResponse(response => new URL(response.url()).pathname.endsWith("/api/bank-details/transactions")
    && new URL(response.url()).searchParams.get("date_from") === selectedMonth);
  await page.getByRole("button", { name: "刷新银行明细" }).click(); await refresh;
  await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "false");
  await page.getByRole("navigation", { name: "主导航" }).getByRole("link", { name: "成本统计", exact: true }).click();
  await page.goBack();
  await expect(page.getByRole("button", { name: "银行明细时间范围：年月" })).toBeVisible();
  await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.goForward();
  await expect(page.getByRole("heading", { name: "成本统计", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(blockedWrites).toEqual([]);
  console.log("DATE_DEFAULTS_READONLY", JSON.stringify({ results, blockedWrites: blockedWrites.length }));
});
