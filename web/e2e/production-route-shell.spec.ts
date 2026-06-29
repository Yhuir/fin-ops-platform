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

  test("opens core routes without session gate, hidden browser errors, or mutating requests", async ({ page, baseURL }) => {
    const mutatingRequests: string[] = [];
    page.on("request", (request) => {
      if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
        mutatingRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
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
      await page.waitForTimeout(1_500);
      const bodyText = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
      const blockedSession = /缺少 OA 登录态|请返回 OA 系统重新登录|会话校验失败|没有权限访问/.test(bodyText);
      const stillLoading = bodyText.includes("正在加载页面") && bodyText.length < 80;
      routeResults.push({ path, blockedSession, stillLoading });
    }

    const failedRoutes = routeResults.filter((result) => result.blockedSession || result.stillLoading);
    expect(failedRoutes, JSON.stringify(failedRoutes, null, 2)).toEqual([]);
    expect(mutatingRequests, `Production route-shell smoke must stay read-only: ${mutatingRequests.join(", ")}`).toEqual([]);
  });
});
