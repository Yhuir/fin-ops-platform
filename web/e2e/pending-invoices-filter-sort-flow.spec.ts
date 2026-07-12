import { expect, test, type Page, type Request, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
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

function createPendingInvoicesLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/pending-invoices",
    pageKey: "pending-invoices",
    module: "pending-invoices",
  });
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
  test("recovers rows after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-load-failure",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/pending-invoices");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("pending-invoices-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("alert")).toContainText("待找发票加载暂时失败，请刷新后重试。"));
    });
    await expect(page.getByText("待找发票加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下没有待找发票流水。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThanOrEqual(2);

    await recordLatency({
      operationId: "pending-invoices.refresh-after-load-failure",
      visibleLabel: "刷新",
      actionType: "click",
    }, async (mark) => {
      const recoveryResponse = page.waitForResponse((response) =>
        pendingInvoiceRowsRequest(response.request()) && response.status() === 200,
      );
      await page.getByRole("button", { name: "刷新" }).click();
      expect((await mark("apiLatencyMs", recoveryResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /智能工厂设备商/ })).toBeVisible());
    });

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

  test("keeps status filters while applying column filters and amount sorting", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const diagnostics = startPageDiagnostics(page);
    const api = await installDeterministicApiMocks(page, {
      pendingInvoiceFilterSortRows: true,
      sessionMode: "full_access",
    });
    const recordLatency = createPendingInvoicesLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "pending-invoices.open-page-filter-sort",
      visibleLabel: "待找发票",
      actionType: "navigate",
    }, async (mark) => {
      await gotoAndExpectPageReady(page, "/pending-invoices", "pending-invoices-page", { diagnostics });
      await mark("finalSettledLatencyMs", expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号", "智能工厂设备商"]));
    });
    await expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号", "智能工厂设备商"]);
    expect(api.count("GET /api/pending-invoices/rows")).toBeGreaterThan(0);

    let amountAscUrl: URL | undefined;
    await recordLatency({
      operationId: "pending-invoices.sort-amount-ascending",
      visibleLabel: "排序 金额 / 银行账户",
      actionType: "click",
    }, async (mark) => {
      const amountAscRequest = page.waitForRequest((request) => {
        if (!pendingInvoiceRowsRequest(request)) {
          return false;
        }
        const url = new URL(request.url());
        return url.searchParams.get("sort_field") === "amount"
          && url.searchParams.get("sort_direction") === "asc";
      });
      await page.getByRole("button", { name: "排序 金额 / 银行账户" }).click();
      amountAscUrl = new URL((await mark("apiLatencyMs", amountAscRequest)).url());
      await mark("finalSettledLatencyMs", expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号", "智能工厂设备商"]));
    });
    if (!amountAscUrl) {
      throw new Error("missing amount ascending rows request");
    }
    expect(amountAscUrl.searchParams.get("direction")).toBe("expense");
    expect(amountAscUrl.searchParams.get("filter")).toBe("requires_invoice");
    expect(amountAscUrl.searchParams.get("page")).toBe("1");
    expect(amountAscUrl.searchParams.get("page_size")).toBe("50");
    expect(parseColumnFilters(amountAscUrl)).toEqual([
      { field: "status_code", operator: "in", values: ["paid_pending_invoice", "paid_invoiced"] },
    ]);
    let amountDescUrl: URL | undefined;
    await recordLatency({
      operationId: "pending-invoices.sort-amount-descending",
      visibleLabel: "排序 金额 / 银行账户",
      actionType: "click",
    }, async (mark) => {
      const amountDescRequest = page.waitForRequest((request) => {
        if (!pendingInvoiceRowsRequest(request)) {
          return false;
        }
        const url = new URL(request.url());
        return url.searchParams.get("sort_field") === "amount"
          && url.searchParams.get("sort_direction") === "desc";
      });
      await page.getByRole("button", { name: "排序 金额 / 银行账户" }).click();
      amountDescUrl = new URL((await mark("apiLatencyMs", amountDescRequest)).url());
      await mark("finalSettledLatencyMs", expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商", "智能工厂设备商二号"]));
    });
    if (!amountDescUrl) {
      throw new Error("missing amount descending rows request");
    }
    expect(amountDescUrl.searchParams.get("sort_field")).toBe("amount");
    expect(amountDescUrl.searchParams.get("sort_direction")).toBe("desc");

    const applyButton = page.locator(".pending-invoices-column-filter-menu__apply");
    let filteredUrl: URL | undefined;
    await recordLatency({
      operationId: "pending-invoices.apply-counterparty-filter",
      visibleLabel: "筛选 对方户名",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 对方户名" }).click();
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
      if (await applyButton.isVisible({ timeout: 500 }).catch(() => false)) {
        await applyButton.click({ force: true });
      }
      filteredUrl = new URL((await mark("apiLatencyMs", filteredRowsRequest)).url());
      await mark("finalSettledLatencyMs", expect.poll(() => visibleCounterparties(page)).toEqual(["智能工厂设备商二号"]));
    });
    if (!filteredUrl) {
      throw new Error("missing filtered rows request");
    }
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
