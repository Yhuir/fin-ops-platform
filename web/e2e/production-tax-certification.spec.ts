import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
const apiPath = "/fin-ops-api/api/tax-offset";
test.use({ screenshot: "off", trace: "off", video: "off" });

test("production certification query, filters, import records and export remain read only", async ({ page, baseURL }, info) => {
  test.skip(!enabled || !token, "Requires production read-only verification and local token.");
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
  const writes: string[] = []; const samples: { operation: string; durationMs: number }[] = [];
  await page.route("**/*", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !(request.method() === "POST" && path === `${apiPath}/export`)) {
      writes.push(`${request.method()} ${path}`); return route.abort("blockedbyclient");
    }
    return route.continue();
  });
  const initial = page.waitForResponse(response => new URL(response.url()).pathname === apiPath);
  let started = performance.now(); await page.goto("/fin-ops/tax-offset");
  const response = await initial; expect(response.status()).toBe(200);
  const payload = await response.json();
  expect(Array.isArray(payload.rows)).toBe(true); expect(payload.export_fields.filter((field: { default_selected: boolean }) => field.default_selected)).toHaveLength(8);
  await expect(page.getByRole("grid", { name: "专票认证明细" })).toBeVisible();
  await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
  samples.push({ operation: "list-open", durationMs: performance.now() - started });
  const filtered = page.waitForResponse(response => new URL(response.url()).pathname === apiPath && new URL(response.url()).searchParams.get("status") === "certified");
  started = performance.now(); await page.getByRole("button", { name: /认证状态/ }).click();
    await page.getByRole("option", { name: "已认证", exact: true }).click();
  expect((await filtered).status()).toBe(200); await expect(page.getByLabel("未认证统计")).toHaveCount(0);
  samples.push({ operation: "status-filter", durationMs: performance.now() - started });
  const restore = page.waitForResponse(response => new URL(response.url()).pathname === apiPath && new URL(response.url()).searchParams.get("status") === "all");
  await page.getByRole("button", { name: /认证状态/ }).click(); await page.getByRole("option", { name: "全部", exact: true }).click(); await restore;
  const records = page.waitForResponse(response => new URL(response.url()).pathname === `${apiPath}/certified-imports`);
  started = performance.now(); await page.locator(".tax-certification-page").getByRole("button", { name: "导入认证记录", exact: true }).click();
  expect((await records).status()).toBe(200); const importer = page.getByRole("dialog", { name: "导入认证记录" });
  await expect(importer.getByRole("button", { name: "确认导入" })).toBeDisabled();
  samples.push({ operation: "import-records-open", durationMs: performance.now() - started });
  await page.keyboard.press("Escape"); await expect(importer).toHaveCount(0);
  if (payload.total === 0) {
    await expect(page.getByRole("button", { name: "导出专票清单", exact: true })).toBeDisabled();
  } else {
  await page.getByRole("button", { name: "导出专票清单", exact: true }).click(); const exporter = page.getByRole("dialog", { name: "导出专票清单" });
  await expect(exporter.getByRole("checkbox", { checked: true })).toHaveCount(8);
  const fileResponse = page.waitForResponse(response => new URL(response.url()).pathname === `${apiPath}/export`);
  const download = page.waitForEvent("download"); started = performance.now(); await exporter.getByRole("button", { name: "导出专票清单" }).click();
  expect((await fileResponse).status()).toBe(200); expect((await download).suggestedFilename()).toBe("专票清单.xlsx");
  await expect(exporter.getByRole("status")).toContainText("已导出");
  samples.push({ operation: "export-default-fields", durationMs: performance.now() - started });
  await page.keyboard.press("Escape"); await expect(exporter).toHaveCount(0);
  }
  await expectNoUnexpectedSuccessUiErrors(page); expect(writes).toEqual([]);
  await info.attach("tax-certification-readonly-performance", { body: JSON.stringify({ samples, writes: writes.length }), contentType: "application/json" });
});
