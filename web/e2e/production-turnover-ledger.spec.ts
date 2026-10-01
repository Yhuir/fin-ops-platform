import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ trace: "off", video: "off" });

test("production turnover register filters, details and exports use canonical facts without business writes", async ({ page }, testInfo) => {
  test.skip(!enabled || !token, "Requires explicit production verification and admin token.");
  test.setTimeout(180_000);
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: "www.yn-sourcing.com", path: "/", secure: true, sameSite: "Lax" }]);
  let ledgerReads = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === "/fin-ops-api/api/turnover-ledger") ledgerReads += 1; });
  const writes: string[] = [];
  await page.route("**/fin-ops-api/**", async (route) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort("blockedbyclient");
    } else await route.continue();
  });
  await page.setViewportSize({ width: 1536, height: 1024 });
  const initial = page.waitForResponse((response) => new URL(response.url()).pathname === "/fin-ops-api/api/turnover-ledger");
  const firstVisibleStart = performance.now();
  await page.goto("/fin-ops/turnover-ledger");
  const response = await initial;
  expect(response.status()).toBe(200);
  const payload = await response.json();
  expect(payload.pagination.page_size).toBe(20);
  expect(payload.statistics.group_count).toBe(payload.pagination.total);
  const register = page.getByRole("table", { name: "外部往来款台账" });
  await expect(register).toBeVisible();
  const firstVisibleMs = performance.now() - firstVisibleStart;
  expect(payload.groups.length).toBeGreaterThan(0);
  for (const group of payload.groups) {
    for (const row of group.flow_rows) {
      const labels: Record<string, string> = { pending_collection: "待收款", collected: "已收款", pending_repayment: "待还款", repaid: "已还款" };
      expect(row.turnover_action_label).toBe(labels[row.turnover_action_type] ?? (row.turnover_action_type ? "标记无效" : "未设置"));
    }
  }
  expect(await page.locator("body").evaluate((body) => body.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "../outputs/production-turnover-collapsed.png", fullPage: true, animations: "disabled" });
  const group = payload.groups.find((item: { flow_rows: unknown[] }) => item.flow_rows.length > 0);
  expect(group).toBeDefined();
  const beforeExpandReads = ledgerReads;
  const expandStart = performance.now();
  await page.getByRole("button", { name: `展开 ${group.counterparty_name} 流水明细`, exact: true }).click();
  const flows = page.getByRole("grid", { name: `${group.counterparty_name}的银行流水`, exact: true });
  await expect(flows.getByRole("checkbox")).toHaveCount(group.flow_rows.length);
  const expandMs = performance.now() - expandStart;
  await expect(flows.locator(".turnover-flow-chip")).toHaveCount(group.flow_rows.length);
  await expect(flows).not.toContainText("往来标记：");
  const trigger = page.getByRole("button", { name: "查看分类明细" });
  const popoverSamples: number[] = [];
  for (const width of [1920, 1440, 960]) {
    await page.setViewportSize({ width, height: 1080 });
    const aligned = await flows.evaluate(table => {
      const row = table.querySelector("tbody tr")!;
      const roles = ["date", "amount", "status", "action"];
      return roles.every(role => getComputedStyle(table.querySelector(`thead [data-column-role="${role}"]`)!).textAlign === getComputedStyle(row.querySelector(`[data-column-role="${role}"]`)!).textAlign);
    });
    expect(aligned).toBe(true);
    const inline = await flows.locator(".turnover-flow-label").first().evaluate(label => {
      const text = label.querySelector(".finance-truncated-text")!.getBoundingClientRect();
      const chip = label.querySelector(".turnover-flow-chip")!.getBoundingClientRect();
      return Math.abs(text.y + text.height / 2 - chip.y - chip.height / 2) <= 2;
    });
    expect(inline).toBe(true);
    const metricBox = (await page.getByTestId("turnover-summary-collected").boundingBox())!;
    const buttonBox = (await trigger.boundingBox())!;
    expect(buttonBox.x - metricBox.x - metricBox.width).toBeGreaterThanOrEqual(0);
    expect(buttonBox.x - metricBox.x - metricBox.width).toBeLessThanOrEqual(40);
    await page.screenshot({ path: testInfo.outputPath(`production-turnover-${width}.png`), fullPage: true, animations: "disabled" });
    const start = performance.now();
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "往来款分类明细" });
    await expect(dialog).toBeVisible();
    popoverSamples.push(performance.now() - start);
    for (const family of payload.family_summaries) {
      const row = dialog.getByRole("row").filter({ has: page.getByRole("rowheader", { name: family.label, exact: true }) });
      for (const key of ["pending_repayment_amount", "pending_collection_amount", "repaid_amount", "collected_amount"]) {
        const formatted = Number(family[key]).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        await expect(row).toContainText(formatted);
      }
    }
    await page.screenshot({ path: testInfo.outputPath(`production-turnover-breakdown-${width}.png`), fullPage: true, animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(trigger).toBeFocused();
  }
  expect(ledgerReads).toBe(beforeExpandReads);
  await testInfo.attach("production-turnover-ui", { body: JSON.stringify({ firstVisibleMs, expandMs, popoverSamples, additionalLedgerReads: ledgerReads - beforeExpandReads }), contentType: "application/json" });
  await page.setViewportSize({ width: 1536, height: 1024 });

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
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "确认下载", exact: true }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  expect(await download.failure()).toBeNull();

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
  await expectNoUnexpectedSuccessUiErrors(page);
});

test("production payment rule applicants match all OA accounts and support disabled selection", async ({ page }, testInfo) => {
  test.skip(!enabled || !token, "Requires explicit production verification and admin token.");
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: "www.yn-sourcing.com", path: "/", secure: true, sameSite: "Lax" }]);
  const writes: string[] = [];
  let ruleReads = 0;
  await page.route("**/fin-ops-api/**", async (route) => {
    if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort("blockedbyclient");
    } else {
      if (new URL(route.request().url()).pathname.endsWith("/payment-status-rules")) ruleReads += 1;
      await route.continue();
    }
  });
  await page.setViewportSize({ width: 1536, height: 1024 });
  await page.goto("/fin-ops/input-invoice-usage");
  const opener = page.getByRole("button", { name: "发票与支付状态规则设置" });
  await expect(opener).toBeEnabled();
  expect(ruleReads).toBe(0);
  const rulesResponse = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/payment-status-rules"));
  await opener.click();
  const response = await rulesResponse;
  expect(response.status()).toBe(200);
  const policy = await response.json();
  const expected: Array<{ userId: string; name: string; account: string; enabled: boolean; matchName: string }> = [];
  let total = 1;
  for (let pageNum = 1; (pageNum - 1) * 100 < total; pageNum += 1) {
    const oaResponse = await page.request.get(`/oa-api/system/user/list?pageNum=${pageNum}&pageSize=100`, { headers: { Authorization: `Bearer ${token}` } });
    expect(oaResponse.status()).toBe(200);
    const directory = await oaResponse.json();
    expect(directory.code).toBe(200);
    total = directory.total;
    for (const user of directory.rows) {
      if (String(user.delFlag) === "0") expected.push({ userId: String(user.userId), name: user.nickName, account: user.userName,
        enabled: String(user.status) === "0", matchName: user.nickName.replace(/[\s\u200b\ufeff]+/g, "") });
    }
  }
  const byAccount = (a: { account: string }, b: { account: string }) => a.account.localeCompare(b.account);
  expect([...policy.applicantOptions].sort(byAccount)).toEqual([...expected].sort(byAccount));
  expect(new Set(policy.applicantOptions.map((option: { userId: string }) => option.userId)).size).toBe(expected.length);
  const firstDisabled = policy.applicantOptions.findIndex((option: { enabled: boolean }) => !option.enabled);
  if (firstDisabled >= 0) expect(policy.applicantOptions.slice(firstDisabled).every((option: { enabled: boolean }) => !option.enabled)).toBe(true);
  for (const rule of policy.rules) expect(rule.conditions).not.toHaveProperty("applicantName");
  const drawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
  await drawer.getByRole("button", { name: /OA 申请人条件/ }).first().click();
  const selected = policy.rules[0].conditions.applicantNames ?? [];
  const addition = policy.applicantOptions.find((option: { enabled: boolean; matchName: string }) => !option.enabled && !selected.includes(option.matchName));
  expect(addition).toBeTruthy();
  await page.getByRole("searchbox", { name: "搜索申请人姓名或账号" }).fill(addition.account);
  const option = page.getByRole("option", { name: `${addition.name} ${addition.account}`, exact: true });
  await expect(option.getByRole("img", { name: "账号已停用" })).toBeVisible();
  await option.click();
  await page.screenshot({ path: "../outputs/production-payment-rule-applicants-open.png", animations: "disabled" });
  await page.keyboard.press("Escape");
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();
  await page.screenshot({ path: "../outputs/production-payment-rule-applicants.png", animations: "disabled" });
  await drawer.getByRole("button", { name: "还原", exact: true }).click();
  await expect(drawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();
  expect(writes).toEqual([]);
  await expectNoUnexpectedSuccessUiErrors(page);
  await testInfo.attach("production-applicant-directory", { body: JSON.stringify({ version: policy.version, accounts: expected.length, enabled: expected.filter((option) => option.enabled).length, disabled: expected.filter((option) => !option.enabled).length, oa_total: total, business_writes: writes.length }), contentType: "application/json" });
});
