import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { expect, test } from "./fixtures/strictTest";

const productionAdminSmokeEnabled = process.env.FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE === "1";
const adminToken = process.env.FIN_OPS_E2E_ADMIN_TOKEN ?? "";
const appHealthDashboardPath = "/api/operations/app-health-dashboard";

function cookieDomain(baseUrl: string) {
  return new URL(baseUrl).hostname;
}

test.use({ screenshot: "off", trace: "off", video: "off" });

test.describe("production admin AppHealth smoke", () => {
  test.skip(!productionAdminSmokeEnabled, "Set FIN_OPS_E2E_PRODUCTION_ADMIN_SMOKE=1 to run the production admin AppHealth smoke.");
  test.skip(!adminToken, "Set FIN_OPS_E2E_ADMIN_TOKEN to a real admin OA Admin-Token value.");

  test("shared task drawer repeatedly dismisses without writes or unrelated page reads", async ({ page, baseURL }, testInfo) => {
    const writes: string[] = [];
    const reads: string[] = [];
    page.on("request", request => {
      const path = new URL(request.url()).pathname;
      if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) writes.push(path);
      if (request.method() === "GET") reads.push(path);
    });
    await page.context().addCookies([{ name: "Admin-Token", value: adminToken,
      domain: cookieDomain(baseURL ?? "https://www.yn-sourcing.com"), path: "/", secure: true, sameSite: "Lax" }]);
    await page.goto("/fin-ops/imports/invoices", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "发票导入", exact: true })).toBeVisible();
    const jobsResponse = await page.request.get("/fin-ops-api/api/background-jobs/active");
    expect(jobsResponse.status()).toBe(200);
    const payload = await jobsResponse.json();
    expect(payload.jobs.filter((job: { job_id: string; status: string }) => job.job_id.startsWith("import:") && job.status === "succeeded")).toEqual([]);
    const samples: Array<{ openMs: number; closeMs: number }> = [];
    for (let index = 0; index < 10; index++) {
      await page.locator(".app-sidebar-brand-mark").click();
      await expect(page.getByRole("dialog", { name: "全局运行状态" })).toBeVisible();
      const readOffset = reads.length;
      const opened = Date.now();
      await page.getByRole("dialog", { name: "全局运行状态" }).getByRole("button", { name: "查看待处理任务", exact: true }).click();
      const drawer = page.getByRole("dialog", { name: "共享导入任务", exact: true });
      await expect(drawer.getByRole("button", { name: "刷新任务", exact: true })).toBeEnabled();
      await expect(page.getByRole("dialog")).toHaveCount(1);
      const openMs = Date.now() - opened;
      const closed = Date.now();
      if (index % 3 === 0) await drawer.getByRole("button", { name: "关闭抽屉", exact: true }).click();
      else if (index % 3 === 1) await page.keyboard.press("Escape");
      else await page.locator(".finance-drawer__backdrop").click({ position: { x: 4, y: 4 } });
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(page.locator(".app-sidebar-brand-mark")).toBeFocused();
      samples.push({ openMs, closeMs: Date.now() - closed });
      const taskReads = reads.slice(readOffset).filter(path => /\/imports\/jobs$/.test(path));
      expect(taskReads).toHaveLength(1);
      expect(reads.slice(readOffset).filter(path => /\/(workbench|bank-details|cost-statistics|pending-invoices)\//.test(path))).toEqual([]);
    }
    await page.reload();
    await page.locator(".app-sidebar-brand-mark").click();
    await expect(page.getByRole("button", { name: "导入完成。", exact: true })).toHaveCount(0);
    expect(writes).toEqual([]);
    await testInfo.attach("production-import-drawer-latency", { body: JSON.stringify({ samples, mutatingRequests: writes.length }), contentType: "application/json" });
  });

  test("opens the admin-only AppHealth dashboard without browser errors or mutating requests", async ({ page, baseURL }) => {
    const mutatingRequests: string[] = [];
    const dashboardStatuses: number[] = [];

    page.on("request", (request) => {
      if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
        mutatingRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
    });
    page.on("response", (response) => {
      if (new URL(response.url()).pathname.endsWith(appHealthDashboardPath)) {
        dashboardStatuses.push(response.status());
      }
    });

    await page.context().addCookies([
      {
        name: "Admin-Token",
        value: adminToken,
        domain: cookieDomain(baseURL ?? "https://www.yn-sourcing.com"),
        path: "/",
        secure: true,
        sameSite: "Lax",
      },
    ]);

    await page.goto("/fin-ops/operations/app-health", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "数据与导入" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-recent-imports")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toHaveCount(0);
    await expect(page.getByTestId("app-health-runtime")).toHaveCount(0);

    const dashboardResponse = await page.request.get("/fin-ops-api/api/operations/app-health-dashboard");
    expect(dashboardResponse.status()).toBe(200);
    const inventory = (await dashboardResponse.json()).data_inventory;
    const counts = Object.fromEntries(inventory.invoice.sources.map((source: { key: string; count: number; supplementary_count: number }) => [source.key, source]));
    expect(counts.input_invoice.count + counts.output_invoice.count).toBe(inventory.invoice.total_count);
    expect(counts.manual.count + counts.oa_attachment.supplementary_count).toBe(inventory.invoice.total_count);
    await expect(page.getByLabel("发票统计")).not.toContainText("统计未闭合");
    const visualDirectory = process.env.FIN_OPS_VISUAL_OUTPUT_DIR;
    if (visualDirectory) {
      await mkdir(visualDirectory, { recursive: true });
      await page.screenshot({ path: join(visualDirectory, "production-desktop.png"), fullPage: true });
    }
    await page.getByRole("button", { name: "导入历史", exact: true }).click();
    const historyDrawer = page.getByRole("dialog", { name: "导入历史", exact: true });
    await expect(historyDrawer.getByRole("grid", { name: "导入历史记录" })).toBeVisible();
    await historyDrawer.getByRole("combobox", { name: "类型", exact: true }).selectOption("bank_transaction");
    await historyDrawer.getByRole("combobox", { name: "状态", exact: true }).selectOption("succeeded");
    await historyDrawer.getByLabel("每页").selectOption("100");
    const filteredRead = page.waitForResponse(response => response.url().includes("/api/operations/import-history?") && response.url().includes("status=succeeded"));
    await historyDrawer.getByRole("button", { name: "查询", exact: true }).click();
    const filteredResponse = await filteredRead;
    expect(filteredResponse.status()).toBe(200);
    const filtered = await filteredResponse.json();
    expect(filtered.pagination.page_size).toBe(100);
    expect(filtered.rows.length).toBeGreaterThan(0);
    for (const row of filtered.rows) { expect(row.batch_type).toBe("bank_transaction"); expect(row.status).toBe("succeeded"); }
    const first = filtered.rows[0];
    const detailRead = page.waitForResponse(response => response.url().endsWith(`/api/operations/import-history/${encodeURIComponent(first.batch_id)}`));
    await historyDrawer.getByRole("button", { name: `查看 ${first.source_name}`, exact: true }).first().click();
    const detailResponse = await detailRead;
    expect(detailResponse.status()).toBe(200);
    expect((await detailResponse.json()).row.batch_id).toBe(first.batch_id);
    await expect(historyDrawer.getByRole("heading", { name: first.source_name, exact: true })).toBeVisible();
    if (visualDirectory) await page.screenshot({ path: join(visualDirectory, "production-detail.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(historyDrawer.getByRole("heading", { name: first.source_name, exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    if (visualDirectory) await page.screenshot({ path: join(visualDirectory, "production-mobile-detail.png") });
    await historyDrawer.getByRole("button", { name: "返回列表", exact: true }).click();
    await expect(historyDrawer.getByRole("combobox", { name: "状态", exact: true })).toHaveValue("succeeded");
    expect((await historyDrawer.getByLabel("开始日期").boundingBox())!.width).toBeGreaterThan(240);
    await historyDrawer.getByRole("button", { name: "关闭导入历史", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "导入历史", exact: true })).toBeFocused();
    if (visualDirectory) await page.screenshot({ path: join(visualDirectory, "production-mobile.png"), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 720 });

    await page.getByRole("button", { name: "导入任务", exact: true }).click();
    const taskList = page.getByRole("grid", { name: "待处理导入任务" });
    await expect(taskList).toBeVisible();
    const detailButton = taskList.getByRole("button", { name: "查看详情" }).first();
    if (await detailButton.count()) {
      await detailButton.click();
      await expect(page.getByRole("heading", { name: "导入任务详情" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "当前文件与导入证据" })).toBeVisible();
      await expect(page.getByText("任务编号：", { exact: false })).toBeVisible();
      const preview = page.getByRole("button", { name: "查看发票导入预览", exact: true });
      if (await preview.count()) {
        await preview.click();
        const taskDrawer = page.getByRole("dialog", { name: "处理导入任务", exact: true });
        await expect(taskDrawer.getByText("已恢复指定导入任务，请核对预览。")).toBeVisible();
        await expect(taskDrawer.getByRole("heading", { name: "导入统计", exact: true })).toBeVisible();
        await expect(taskDrawer.getByText("Import session belongs to another user.", { exact: true })).toHaveCount(0);
      }
    }


    for (const [route, heading] of [
      ["bank-transactions", "银行流水导入"],
      ["invoices", "发票导入"],
    ]) {
      await page.goto(`/fin-ops/imports/${route}`, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
    }

    const bodyText = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
    expect(
      /缺少 OA 登录态|请返回 OA 系统重新登录|会话校验失败|没有权限访问|当前账号没有管理员权限，不能查看 数据与导入。/.test(bodyText),
      bodyText.slice(0, 200),
    ).toBe(false);
    expect(bodyText.includes("正在加载页面") && bodyText.length < 80, bodyText.slice(0, 200)).toBe(false);
    expect(dashboardStatuses).toContain(200);
    expect(mutatingRequests, `Production admin AppHealth smoke must stay read-only: ${mutatingRequests.join(", ")}`).toEqual([]);
  });
});
