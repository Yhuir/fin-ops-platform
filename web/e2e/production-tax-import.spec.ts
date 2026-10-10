import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

// Explicitly executes the selected real business import; never fabricates or revokes production invoices.
const sourceFile = process.env.FIN_OPS_E2E_TAX_IMPORT_FILE;
const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const apiPath = "/fin-ops-api/api/tax-offset";
test.use({ screenshot: "off", trace: "off", video: "off" });

test("production selected certification file analyzes, commits once and reanalyzes without duplicate writes", async ({ page, baseURL }, info) => {
  test.skip(!enabled || !token || !sourceFile, "Requires explicit production import file and authenticated operator.");
  test.setTimeout(180_000);
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
  const samples: { operation: string; durationMs: number }[] = [];
  let confirms = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === `${apiPath}/certified-import/confirm` && request.method() === "POST") confirms += 1; });
  const listResponse = page.waitForResponse(response => new URL(response.url()).pathname === apiPath);
  await page.goto("/fin-ops/tax-offset");
  const before = await (await listResponse).json();
  await page.getByRole("button", { name: "导入认证记录", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导入认证记录" });
  await expect(drawer.getByRole("button", { name: "识别", exact: true })).toHaveCount(0);
  let started = performance.now();
  const analysisResponse = page.waitForResponse(response => new URL(response.url()).pathname === `${apiPath}/certified-import/preview`);
  await drawer.locator('input[type="file"]').setInputFiles(sourceFile!);
  const response = await analysisResponse;
  expect(response.status()).toBe(200);
  const analysis = await response.json();
  await expect(drawer.getByRole("region", { name: "认证文件统计" })).toBeVisible();
  samples.push({ operation: "file-to-summary", durationMs: performance.now() - started });
  // A source requiring corrections is a business decision, not an automatic production smoke action.
  expect(analysis.summary.blocking_count).toBe(0);
  expect(analysis.summary.conflict_count).toBe(0);
  expect(analysis.summary.recognized_count).toBeGreaterThan(0);
  // This is the first intended import; stop before writing if another operator already imported it.
  expect(analysis.summary.new_count).toBe(analysis.summary.recognized_count);
  expect(analysis.files.every((file: { missing_metadata: string[] }) => file.missing_metadata.length === 0)).toBe(true);
  await expect(drawer.getByRole("button", { name: "确认导入", exact: true })).toBeEnabled();
  const completedResponse = page.waitForResponse(async response => {
    if (!new URL(response.url()).pathname.startsWith(`${apiPath}/certified-import/jobs/`)) return false;
    return (await response.json()).import_job?.status === "succeeded";
  });
  const refreshedResponse = page.waitForResponse(response => new URL(response.url()).pathname === apiPath);
  started = performance.now();
  await drawer.getByRole("button", { name: "确认导入", exact: true }).click();
  const job = (await (await completedResponse).json()).import_job;
  await expect(drawer.getByRole("status").filter({ hasText: "导入完成" })).toBeVisible();
  samples.push({ operation: "confirm-to-completed", durationMs: performance.now() - started });
  const after = await (await refreshedResponse).json();
  expect(after.inventory_statistics).toEqual(before.inventory_statistics);
  expect(confirms).toBe(1);
  const batch = job.result_payload.batch;
  expect(batch.new_record_count + batch.corrected_record_count + batch.linked_record_count + batch.duplicate_count).toBe(analysis.summary.recognized_count);
  expect(after.summary.certified.count - before.summary.certified.count).toBe(batch.matched_record_count);
  const historyResponse = page.waitForResponse(response => new URL(response.url()).pathname === `${apiPath}/certified-imports`);
  await drawer.getByRole("button", { name: "历史批次", exact: true }).click();
  const history = await (await historyResponse).json();
  expect(history.batches.some((item: { id: string }) => item.id === batch.id)).toBe(true);
  const repeatedResponse = page.waitForResponse(response => new URL(response.url()).pathname === `${apiPath}/certified-import/preview`);
  started = performance.now();
  await drawer.locator('input[type="file"]').setInputFiles(sourceFile!);
  const repeated = await (await repeatedResponse).json();
  samples.push({ operation: "repeat-file-analysis", durationMs: performance.now() - started });
  expect(repeated.summary.new_count).toBe(0);
  expect(repeated.summary.relink_count).toBe(0);
  expect(repeated.summary.conflict_count).toBe(0);
  expect(repeated.summary.duplicate_count).toBe(repeated.summary.recognized_count);
  expect(confirms).toBe(1);
  await expectNoUnexpectedSuccessUiErrors(page);
  await info.attach("production-tax-import-result", { body: JSON.stringify({ samples, analysis: analysis.summary, batch, repeat: repeated.summary,
    certifiedBefore: before.summary.certified.count, certifiedAfter: after.summary.certified.count, confirms }), contentType: "application/json" });
});
