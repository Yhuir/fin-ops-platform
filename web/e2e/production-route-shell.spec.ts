import { expect, test } from "./fixtures/strictTest";

const productionSmokeEnabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const oaToken = process.env.FIN_OPS_E2E_OA_TOKEN ?? "";

const routePaths = [
  "/fin-ops/",
  "/fin-ops/bank-details",
  "/fin-ops/pending-invoices",
  "/fin-ops/input-invoice-usage",
  "/fin-ops/oa-pending-payments",
  "/fin-ops/output-invoice-collections",
  "/fin-ops/tax-offset",
  "/fin-ops/cost-statistics",
  "/fin-ops/bank-flow-rule-batches",
  "/fin-ops/batch-accounting",
  "/fin-ops/turnover-ledger",
  "/fin-ops/etc-tickets",
  "/fin-ops/imports/bank-transactions",
  "/fin-ops/imports/invoices",
  "/fin-ops/imports/etc-invoices",
  "/fin-ops/settings",
] as const;

function cookieDomain(baseUrl: string) {
  return new URL(baseUrl).hostname;
}

test.use({ screenshot: "off", trace: "off", video: "off" });

test.describe("production route shell smoke", () => {
  test.skip(!productionSmokeEnabled, "Set FIN_OPS_E2E_PRODUCTION_SMOKE=1 to run the production route-shell smoke.");
  test.skip(!oaToken, "Set FIN_OPS_E2E_OA_TOKEN to a real OA Admin-Token value.");

  test("business navigation and import shortcuts preserve real production pages", async ({ page, baseURL }, info) => {
    test.setTimeout(120_000);
    const writes: string[] = [];
    await page.route("**/*", async route => {
      if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
        writes.push(new URL(route.request().url()).pathname);
        await route.abort("blockedbyclient");
      } else await route.continue();
    });
    await page.context().addCookies([{ name: "Admin-Token", value: oaToken, domain: cookieDomain(baseURL!), path: "/", secure: true, sameSite: "Lax" }]);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/fin-ops/bank-details");
    const nav = page.getByRole("navigation", { name: "主导航" });
    await expect(nav).toBeVisible();
    await expect(nav.locator('.app-sidebar-group').first().locator('.app-sidebar-list > li > .app-sidebar-link .app-sidebar-link-label-text, .app-sidebar-list > li > .app-sidebar-disclosure .app-sidebar-disclosure-trigger .app-sidebar-link-label-text')).toHaveText([
      "关联台", "成本", "银行明细", "OA付款情况", "流水待找发票", "进项发票使用情况", "销项发票收款情况", "专票认证情况", "外部往来款", "流水规则批量处理", "ETC票据管理", "现金账",
    ]);
    const measurements: Array<{ width: number; route: string; elapsedMs: number }> = [];
    for (const width of [1920, 1440, 1024]) {
      await page.setViewportSize({ width, height: 1080 });
      for (const entry of [
        { path: "/bank-details", button: "导入流水", back: "返回银行明细" },
        { path: "/input-invoice-usage", button: "导入进项发票", back: "返回进项发票" },
        { path: "/output-invoice-collections", button: "导入销项发票", back: "返回销项发票" },
      ]) {
        const start = Date.now();
        await nav.getByRole("link", { name: entry.path === "/bank-details" ? "银行明细" : entry.path === "/input-invoice-usage" ? "进项发票使用情况" : "销项发票收款情况", exact: true }).click();
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        const button = page.getByRole("button", { name: entry.button, exact: true });
        await expect(button).toBeVisible();
        measurements.push({ width, route: entry.path, elapsedMs: Date.now() - start });
        await page.screenshot({ path: info.outputPath(`production-${entry.path.slice(1)}-${width}.png`), animations: "disabled" });
        await button.click();
        await expect(page.getByRole("button", { name: entry.back })).toBeVisible();
        await page.reload();
        await expect(page.getByRole("button", { name: entry.back })).toBeVisible();
        await page.getByRole("button", { name: entry.back }).click();
        await expect(page).toHaveURL(new RegExp(`/fin-ops${entry.path}$`));
      }
    }
    expect(writes).toEqual([]);
    await info.attach("production-import-navigation-latency", { body: JSON.stringify(measurements), contentType: "application/json" });
  });

  test("opens core routes without session gate, hidden browser errors, or mutating requests", async ({ page, baseURL }) => {
    const mutatingRequests: string[] = [];
    await page.route("**/*", async route => {
      const request = route.request();
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method())) {
        mutatingRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    await page.context().addCookies([
      {
        name: "Admin-Token",
        value: oaToken,
        domain: cookieDomain(baseURL ?? "https://www.yn-sourcing.com"),
        path: "/",
        secure: true,
        sameSite: "Lax",
      },
    ]);

    const routeResults: Array<{ path: string; blockedSession: boolean; stillLoading: boolean }> = [];
    for (const path of routePaths) {
      await page.goto(path, { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
      if (path === "/fin-ops/batch-accounting") {
        await expect(page).toHaveURL(/\/settings\?section=batch-accounting/);
        await expect(page.getByRole("heading", { name: "设置", exact: true })).toBeVisible();
        await expect(page.getByRole("grid", { name: "批量账务历史记录" })).toBeVisible();
      }
      await page.waitForTimeout(1_500);
      await expect(page.locator('.app-shell-progress-stack, .background-progress-block')).toHaveCount(0);
      await expect(page.getByRole('button', { name: '选择流水子项', exact: true })).toHaveCount(0);
      const bodyText = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
      const blockedSession = /缺少 OA 登录态|请返回 OA 系统重新登录|会话校验失败|没有权限访问|OA 会话已失效|登录状态已过期/.test(bodyText);
      const stillLoading = bodyText.includes("正在加载页面") && bodyText.length < 80;
      routeResults.push({ path, blockedSession, stillLoading });
    }

    const failedRoutes = routeResults.filter((result) => result.blockedSession || result.stillLoading);
    expect(failedRoutes, JSON.stringify(failedRoutes, null, 2)).toEqual([]);
    expect(mutatingRequests, `Production route-shell smoke must stay read-only: ${mutatingRequests.join(", ")}`).toEqual([]);
  });
});
