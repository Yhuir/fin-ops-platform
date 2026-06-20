import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

function startStrictBrowserErrorCapture(page: Page, options: { allowExpectedAuthResourceError?: boolean } = {}) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      if (
        options.allowExpectedAuthResourceError
        && message.text().includes("Failed to load resource: the server responded with a status of 401 (Unauthorized)")
      ) {
        return;
      }
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("requestfailed", (request) => {
    const failure = request.failure()?.errorText ?? "";
    if (failure === "net::ERR_ABORTED") {
      return;
    }
    errors.push(`requestfailed: ${request.method()} ${request.url()} ${failure}`.trim());
  });
  page.on("dialog", async (dialog) => {
    errors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
    await dialog.dismiss().catch(() => undefined);
  });
  return errors;
}

test.describe("app shell browser smoke", () => {
  test("renders authenticated admin shell, navigation, and AppHealth dashboard", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/operations/app-health");

    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByRole("link", { name: "关联台" })).toBeVisible();
    await expect(page.getByRole("link", { name: "银行明细" })).toBeVisible();
    await expect(page.getByRole("link", { name: "系统状态" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toBeVisible();
    await expect(page.getByRole("button", { name: "刷新" })).toBeVisible();
    expect(api.count("GET /api/session/me")).toBeGreaterThan(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);
    expect(browserErrors).toEqual([]);
  });

  test("keeps AppHealth dashboard admin-only for read-export users", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    await page.goto("/operations/app-health");

    await expect(page.getByRole("navigation", { name: "主导航" })).toBeVisible();
    await expect(page.getByText("当前账号没有管理员权限，不能查看 AppHealth 运维状态。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("shows session-denied state without rendering the protected dashboard", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "forbidden" });

    await page.goto("/operations/app-health");

    await expect(page.getByRole("heading", { name: "无权访问财务运营平台" })).toBeVisible();
    await expect(page.getByText("当前 OA 账号未开通访问权限，请联系管理员处理。")).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("shows expired session state and does not call protected page APIs", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, { allowExpectedAuthResourceError: true });
    const api = await installDeterministicApiMocks(page, { sessionMode: "expired" });

    await page.goto("/operations/app-health");

    await expect(page.getByRole("heading", { name: "OA 会话已失效" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBe(0);
    expect(browserErrors).toEqual([]);
  });
});
