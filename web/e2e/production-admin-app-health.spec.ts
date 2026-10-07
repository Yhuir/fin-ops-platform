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
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toBeVisible();
    await expect(page.getByTestId("app-health-runtime")).toBeVisible();

    await expect(page.getByRole("heading", { name: "导入任务诊断" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "失败", exact: true })).toBeVisible();
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
      /缺少 OA 登录态|请返回 OA 系统重新登录|会话校验失败|没有权限访问|当前账号没有管理员权限，不能查看 AppHealth 运维状态。/.test(bodyText),
      bodyText.slice(0, 200),
    ).toBe(false);
    expect(bodyText.includes("正在加载页面") && bodyText.length < 80, bodyText.slice(0, 200)).toBe(false);
    expect(dashboardStatuses).toContain(200);
    expect(mutatingRequests, `Production admin AppHealth smoke must stay read-only: ${mutatingRequests.join(", ")}`).toEqual([]);
  });
});
