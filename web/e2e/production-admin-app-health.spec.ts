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
