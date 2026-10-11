import { mkdir, writeFile } from "node:fs/promises";
import { expect, test } from "./fixtures/strictTest";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: "off", trace: "off", video: "off" });

test("production ETC workspace reads real batches and switches stages without writes or API I/O", async ({ page, baseURL }, testInfo) => {
  test.skip(!enabled, "Explicit production admin smoke is required.");
  expect(token, "Production token must be loaded through the repository wrapper").toBeTruthy();
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
  const writes: string[] = [];
  const reads: string[] = [];
  await page.route("**/fin-ops-api/**", async route => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(route.request().method())) {
      writes.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
      return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  page.on("request", request => {
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path.includes("/api/etc/")) reads.push(path);
  });
  const buckets = ["unsubmitted", "staged", "submitted"] as const;
  const apiSamples: Array<{ endpoint: string; ms: number; rows: number }> = [];
  for (const bucket of buckets) {
    const endpoint = `/fin-ops-api/api/etc/business-batches?bucket=${bucket}&page=1&page_size=50`;
    const start = Date.now();
    const response = await page.request.get(endpoint);
    expect(response.status()).toBe(200);
    const envelope = await response.json();
    expect(envelope.ok).toBe(true);
    expect(envelope.error).toBeNull();
    const payload = envelope.data;
    expect(payload.counts).toEqual(expect.objectContaining({ unsubmitted: expect.any(Number), staged: expect.any(Number), submitted: expect.any(Number) }));
    expect(payload.pagination.page).toBe(1);
    expect(Array.isArray(payload.items)).toBe(true);
    apiSamples.push({ endpoint, ms: Date.now() - start, rows: payload.items.length });
  }
  const populated = apiSamples.findIndex(sample => sample.rows > 0);
  expect(populated, "Real production batch required for workspace verification").toBeGreaterThanOrEqual(0);
  const bucket = buckets[populated];
  await page.goto("/fin-ops/etc-tickets");
  const rail = page.getByRole("region", { name: "ETC批次列表区" });
  if (bucket !== "unsubmitted") await rail.getByRole("radio", { name: new RegExp(bucket === "staged" ? "暂存" : "已提交") }).click();
  const selected = rail.locator('.etc-list-row-button[aria-current="true"]');
  await expect(selected).toHaveCount(1);
  await expect(page.locator(".etc-task-identity")).toBeVisible();
  const batchId = (await selected.locator("xpath=..").getAttribute("data-testid"))!.replace("etc-batch-row-", "");
  const importHref = await page.getByRole("link", { name: "导入发票", exact: true }).getAttribute("href");
  const taskId = new URL(importHref!, baseURL).searchParams.get("etc_task");
  expect(taskId).toBeTruthy();
  const detailSamples: Array<{ endpoint: string; ms: number }> = [];
  for (const endpoint of [
    `/fin-ops-api/api/etc/business-batches/${encodeURIComponent(batchId)}`,
    `/fin-ops-api/api/etc/reconciliation-tasks/${encodeURIComponent(taskId!)}`,
  ]) {
    for (let sample = 0; sample < 5; sample++) {
      const start = Date.now();
      const response = await page.request.get(endpoint);
      expect(response.status()).toBe(200);
      expect(await response.json()).toEqual(expect.any(Object));
      detailSamples.push({ endpoint, ms: Date.now() - start });
    }
  }
  const stages = page.getByRole("list", { name: "批次生命周期" });
  await expect(stages.getByRole("button")).toHaveCount(4);
  const offset = reads.length;
  const stageSamples: number[] = [];
  for (let round = 0; round < 5; round++) {
    for (const button of await stages.getByRole("button").all()) {
      const start = Date.now();
      await button.click();
      await expect(button).toHaveAttribute("aria-pressed", "true");
      stageSamples.push(Date.now() - start);
    }
  }
  expect(reads.slice(offset)).toEqual([]);
  const extraEtcReads = reads.slice(offset).length;
  expect(writes).toEqual([]);
  await expect(selected).toHaveCount(1);
  await page.getByRole("link", { name: "导入发票", exact: true }).click();
  const target = new URL(page.url());
  expect(target.searchParams.get("batch")).toBe(batchId);
  const requestedTask = target.searchParams.get("etc_task");
  expect(requestedTask).toBeTruthy();
  const taskSelect = page.getByLabel("ETC对账任务", { exact: true });
  await expect(taskSelect).toBeDisabled();
  await expect.poll(async () => (await taskSelect.inputValue()) === requestedTask
    || await page.getByText("当前批次的核对任务不可导入，请返回 ETC 批次核对状态。").isVisible()).toBe(true);
  await page.getByRole("button", { name: "返回 ETC 批次", exact: true }).click();
  await expect(rail.locator(`[data-testid="etc-batch-row-${batchId}"] .etc-list-row-button`)).toHaveAttribute("aria-current", "true");
  expect(writes).toEqual([]);
  const visualDir = process.env.FIN_OPS_ETC_VISUAL_DIR;
  if (visualDir) {
    await mkdir(visualDir, { recursive: true });
    await page.screenshot({ path: `${visualDir}/production-workspace.png`, fullPage: true });
  }
  const sorted = [...stageSamples].sort((a, b) => a - b);
  const report = { batchId, bucket, apiSamples, detailSamples, stageSamples, stageP95Ms: sorted[Math.ceil(sorted.length * .95) - 1], extraEtcReads, importReturnRestored: true, writes: writes.length };
  expect(report.stageP95Ms).toBeLessThan(1000);
  await testInfo.attach("production-etc-verification", { body: JSON.stringify(report), contentType: "application/json" });
  if (visualDir) await writeFile(`${visualDir}/production-verification.json`, JSON.stringify(report, null, 2));
});
