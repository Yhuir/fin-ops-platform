import { expect, test } from "./fixtures/strictTest";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ trace: "off", video: "off" });

test("production turnover register filters, details and exports use canonical facts without business writes", async ({ page }, testInfo) => {
  test.skip(!enabled || !token, "Requires explicit production verification and admin token.");
  test.setTimeout(180_000);
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: "www.yn-sourcing.com", path: "/", secure: true, sameSite: "Lax" }]);
  const writes: string[] = [];
  await page.route("**/fin-ops-api/**", async (route) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort("blockedbyclient");
    } else await route.continue();
  });
  await page.setViewportSize({ width: 1536, height: 1024 });
  const initial = page.waitForResponse((response) => new URL(response.url()).pathname === "/fin-ops-api/api/turnover-ledger");
  await page.goto("/fin-ops/turnover-ledger");
  const response = await initial;
  expect(response.status()).toBe(200);
  const payload = await response.json();
  expect(payload.pagination.page_size).toBe(20);
  expect(payload.statistics.group_count).toBe(payload.pagination.total);
  const register = page.getByRole("table", { name: "外部往来款台账" });
  await expect(register).toBeVisible();
  expect(payload.groups.length).toBeGreaterThan(0);
  expect(await page.locator("body").evaluate((body) => body.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "../outputs/production-turnover-collapsed.png", fullPage: true, animations: "disabled" });
  const group = payload.groups.find((item: { flow_rows: unknown[] }) => item.flow_rows.length > 0);
  expect(group).toBeDefined();
  await page.getByRole("button", { name: `展开 ${group.counterparty_name} 流水明细`, exact: true }).click();
  const flows = page.getByRole("grid", { name: `${group.counterparty_name}的银行流水`, exact: true });
  await expect(flows.getByRole("checkbox")).toHaveCount(group.flow_rows.length);
  await page.screenshot({ path: "../outputs/production-turnover-expanded.png", fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: `查看${group.counterparty_name}详情`, exact: true }).click();
  const details = page.getByRole("dialog", { name: group.counterparty_name, exact: true });
  await expect(details.getByRole("button", { name: "查看流水", exact: true })).toHaveCount(group.flow_rows.length);
  await details.getByRole("button", { name: "关闭往来对象详情" }).click();
  await page.getByRole("searchbox", { name: "搜索往来对象" }).fill(group.counterparty_name);
  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === "/fin-ops-api/api/turnover-ledger" && url.searchParams.get("query") === group.counterparty_name;
  });
  await page.getByRole("button", { name: "查询", exact: true }).click();
  const filtered = await (await filteredResponse).json();
  expect(filtered.groups.every((item: { counterparty_name: string }) => item.counterparty_name.includes(group.counterparty_name))).toBe(true);
  const previewResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/fin-ops-api/api/turnover-ledger/export-preview");
  await page.getByRole("button", { name: "下载表格" }).click();
  const preview = await previewResponse;
  expect(new URL(preview.url()).searchParams.get("query")).toBe(group.counterparty_name);
  const previewPayload = await preview.json();
  expect(previewPayload.totals.row_count).toBeGreaterThan(0);
  const timings: number[] = [];
  for (let index = 0; index < 12; index += 1) {
    const start = performance.now();
    const probe = await page.request.get("/fin-ops-api/api/turnover-ledger?view=grouped&page_size=20");
    expect(probe.status()).toBe(200);
    const body = await probe.json();
    expect(body.statistics.group_count).toBe(payload.statistics.group_count);
    timings.push(performance.now() - start);
  }
  timings.sort((a, b) => a - b);
  const report = { sample_count: timings.length, group_count: payload.statistics.group_count, transaction_count: payload.statistics.filtered_transaction_count,
    p50_ms: timings[5], p95_ms: timings[11], p99_ms: timings[11], samples_ms: timings };
  await testInfo.attach("production-turnover-performance", { body: JSON.stringify(report, null, 2), contentType: "application/json" });
  expect(report.p95_ms).toBeLessThanOrEqual(1000);
  expect(report.p99_ms).toBeLessThanOrEqual(2000);
  expect(writes).toEqual([]);
});
