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
  started = performance.now(); await page.getByRole("radio", { name: "已认证", exact: true }).click();
  expect((await filtered).status()).toBe(200); await expect(page.getByLabel("未认证统计")).toContainText("0 张");
  samples.push({ operation: "status-filter", durationMs: performance.now() - started });
  const restore = page.waitForResponse(response => new URL(response.url()).pathname === apiPath && new URL(response.url()).searchParams.get("status") === "all");
  await page.getByRole("radio", { name: "全部", exact: true }).click(); await restore;
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

test("production certification filters, fixed header and real export preserve query scope", async ({ page }, info) => {
  test.skip(!enabled || !token, "Explicit production smoke and admin session required.");
  test.setTimeout(120_000);
  const writes: string[] = [];
  await page.route("**/*", async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (!["GET", "HEAD", "OPTIONS"].includes(request.method()) && !(request.method() === "POST" && path === "/fin-ops-api/api/tax-offset/export")) {
      writes.push(path); await route.abort();
    } else await route.continue();
  });
  await page.context().addCookies([{ name: "Admin-Token", value: token!, domain: "www.yn-sourcing.com", path: "/", secure: true, sameSite: "Lax" }]);
  await page.setViewportSize({ width: 1440, height: 900 });
  const responseFor = (key?: string, value?: string) => page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === "/fin-ops-api/api/tax-offset" && (!key || url.searchParams.get(key) === value);
  });
  const initialResponse = responseFor();
  const start = Date.now();
  await page.goto("/fin-ops/tax-offset");
  const initial = await (await initialResponse).json();
  expect(initial.total).toBeGreaterThan(0);
  await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
  const initialMs = Date.now() - start;
  await expect(page.getByRole("grid", { name: "专票认证明细" })).toBeVisible();
  const scroll = page.locator(".tax-certification-results .finance-table__scroll");
  const header = page.getByRole("columnheader", { name: "销方名称" });
  const originalY = (await header.boundingBox())!.y;
  await scroll.evaluate(element => { element.scrollTop = 300; });
  expect((await header.boundingBox())!.y).toBeCloseTo(originalY, 0);
  const sizes = [];
  for (const width of [1440, 1280, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    const height = (await page.locator(".tax-certification-toolbar").boundingBox())!.height;
    sizes.push({ width, toolbarHeight: height });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`production-tax-${width}.png`), animations: "disabled" });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const [label, prefix] of [["开票月份", "issue"], ["勾选月份", "selection"]]) {
    await page.getByRole("button", { name: `${label}：年月` }).click();
    let response = responseFor(`${prefix}_year`, "2026");
    await page.getByRole("button", { name: "2026年", exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
    await page.getByRole("button", { name: `${label}：2026年` }).click();
    await page.getByRole("radio", { name: "按月", exact: true }).click();
    response = responseFor(`${prefix}_month`, "2026-03");
    await page.getByRole("button", { name: "三月", exact: true }).click();
    const monthResponse = await response;
    expect(monthResponse.status()).toBe(200);
    expect(new URL(monthResponse.url()).searchParams.has(`${prefix}_year`)).toBe(false);
    await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
    response = responseFor();
    await page.getByRole("group", { name: label, exact: true }).getByRole("button", { name: "全部", exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
  }
  for (const [name, status] of [["已认证", "certified"], ["未认证", "uncertified"], ["全部", "all"]]) {
    const response = responseFor("status", status);
    await page.getByRole("radio", { name, exact: true }).click();
    const payload = await (await response).json();
    expect(payload.summary.certified.count + payload.summary.uncertified.count).toBe(payload.total);
    expect(payload.rows.every((row: { certification_status: string }) => status === "all" || row.certification_status === status)).toBe(true);
    await expect(page.locator(".tax-certification-results")).toHaveAttribute("aria-busy", "false");
  }
  const invoice = initial.rows[0];
  const search = invoice.digital_invoice_no || invoice.invoice_no;
  await page.getByRole("searchbox", { name: "搜索专票" }).fill(search);
  const filteredResponse = responseFor("search", search);
  await page.locator(".tax-certification-page").getByRole("button", { name: "查询", exact: true }).click();
  const filtered = await (await filteredResponse).json();
  expect(filtered.rows.some((row: { id: string }) => row.id === invoice.id)).toBe(true);
  await page.getByRole("button", { name: "导出专票清单", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "导出专票清单" });
  const exportResponse = page.waitForResponse(response => new URL(response.url()).pathname === "/fin-ops-api/api/tax-offset/export");
  const download = page.waitForEvent("download");
  await drawer.getByRole("button", { name: "导出专票清单", exact: true }).click();
  const exported = await exportResponse;
  expect(exported.status()).toBe(200);
  expect(exported.request().postDataJSON().filters.search).toBe(search);
  expect(exported.headers()["content-type"]).toContain("spreadsheetml");
  expect((await exported.body()).length).toBeGreaterThan(1000);
  await (await download).delete();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await page.getByRole("button", { name: "导入认证记录", exact: true }).click();
  const imports = page.getByRole("dialog", { name: "导入认证记录" });
  await expect(imports.getByRole("region", { name: "待核对记录" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(imports).toHaveCount(0);
  expect(writes).toEqual([]);
  await info.attach("production-tax-measurements", { body: JSON.stringify({ initialMs, sizes, readOnlyBusinessData: true, exportVerified: true }), contentType: "application/json" });
});
