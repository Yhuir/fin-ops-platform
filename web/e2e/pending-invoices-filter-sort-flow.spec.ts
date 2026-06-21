import { expect, test, type Page, type Request } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { gotoAndExpectPageReady, startPageDiagnostics } from "./fixtures/pageReady";

function startStrictBrowserErrorCapture(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
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

function pendingInvoiceRowsRequest(request: Request) {
  const url = new URL(request.url());
  return request.method() === "GET" && url.pathname.endsWith("/api/pending-invoices/rows");
}

function parseColumnFilters(url: URL) {
  const raw = url.searchParams.get("filters") ?? "[]";
  const parsed = JSON.parse(raw) as Array<{ field: string; operator: string; values?: string[] }>;
  return parsed;
}

async function visibleCounterparties(page: Page) {
  return page.locator(".pending-invoices-counterparty-name").allTextContents();
}

test.describe("pending invoices filter and sort browser flow", () => {
  test("recovers rows after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/pending-invoices");
    await expect(page.getByTestId("pending-invoices-page")).toBeVisible();
    await expect(page.getByRole("alert")).toContainText("待找发票加载暂时失败，请刷新后重试。");
    await expect(page.getByText("待找发票加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下没有待找发票流水。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThanOrEqual(2);

    const recoveryResponse = page.waitForResponse((response) =>
      pendingInvoiceRowsRequest(response.request()) && response.status() === 200,
    );
    await page.getByRole("button", { name: "刷新" }).click();
    expect((await recoveryResponse).status()).toBe(200);

    await expect(page.getByText("待找发票加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByText("待找发票加载失败，请点击刷新重试。")).toHaveCount(0);
    const recoveredRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await expect(recoveredRow).toBeVisible();
    await expect(recoveredRow.getByText("已支付待开票")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeEnabled();
    await expect(page.locator(".pending-invoices-pagination-range")).toHaveText("1-1 / 1");
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThanOrEqual(3);
    expect(browserErrors.filter((error) => !error.includes("status of 503"))).toEqual([]);
  });

  test("keeps status filters while applying column filters and amount sorting", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceFilterSortRows: true,
      sessionMode: "full_access",
    });

    await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
    await expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号", "智能工厂设备商"]);
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(0);

    const amountAscRequest = page.waitForRequest((request) => {
      if (!pendingInvoiceRowsRequest(request)) {
        return false;
      }
      const url = new URL(request.url());
      return url.searchParams.get("sort_field") === "amount"
        && url.searchParams.get("sort_direction") === "asc";
    });
    await page.getByRole("button", { name: "排序 金额 / 银行账户" }).click();
    const amountAscUrl = new URL((await amountAscRequest).url());
    expect(amountAscUrl.searchParams.get("direction")).toBe("expense");
    expect(amountAscUrl.searchParams.get("filter")).toBe("requires_invoice");
    expect(amountAscUrl.searchParams.get("page")).toBe("1");
    expect(amountAscUrl.searchParams.get("page_size")).toBe("50");
    expect(parseColumnFilters(amountAscUrl)).toEqual([
      { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
    ]);
    await expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号", "智能工厂设备商"]);

    const amountDescRequest = page.waitForRequest((request) => {
      if (!pendingInvoiceRowsRequest(request)) {
        return false;
      }
      const url = new URL(request.url());
      return url.searchParams.get("sort_field") === "amount"
        && url.searchParams.get("sort_direction") === "desc";
    });
    await page.getByRole("button", { name: "排序 金额 / 银行账户" }).click();
    const amountDescUrl = new URL((await amountDescRequest).url());
    expect(amountDescUrl.searchParams.get("sort_field")).toBe("amount");
    expect(amountDescUrl.searchParams.get("sort_direction")).toBe("desc");
    await expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商", "智能工厂设备商二号"]);

    await page.getByRole("button", { name: "筛选 对方户名 / 时间" }).click();
    const filteredRowsRequest = page.waitForRequest((request) => {
      if (!pendingInvoiceRowsRequest(request)) {
        return false;
      }
      const url = new URL(request.url());
      const filters = parseColumnFilters(url);
      return filters.some((filter) => (
        filter.field === "counterparty_name"
        && filter.operator === "in"
        && filter.values?.includes("智能工厂设备商二号")
      ));
    });
    await page.locator(".pending-invoices-column-filter-menu__option").filter({ hasText: "对方户名：智能工厂设备商二号" }).click();
    const applyButton = page.locator(".pending-invoices-column-filter-menu__apply");
    if (await applyButton.isVisible({ timeout: 500 }).catch(() => false)) {
      await applyButton.click({ force: true });
    }
    const filteredUrl = new URL((await filteredRowsRequest).url());
    expect(filteredUrl.searchParams.get("direction")).toBe("expense");
    expect(filteredUrl.searchParams.get("filter")).toBe("requires_invoice");
    expect(filteredUrl.searchParams.get("sort_field")).toBe("amount");
    expect(filteredUrl.searchParams.get("sort_direction")).toBe("desc");
    expect(parseColumnFilters(filteredUrl)).toEqual(expect.arrayContaining([
      { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
      { field: "counterparty_name", operator: "in", values: ["智能工厂设备商二号"] },
    ]));
    await expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号"]);
    await expect(page.locator(".pending-invoices-pagination-range")).toHaveText("1-1 / 1");
    expect(browserErrors).toEqual([]);
    diagnostics.dispose();
  });
});
