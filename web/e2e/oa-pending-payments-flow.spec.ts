import { expect, test, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";

function filtersFromRequest(requestUrl: string) {
  const value = new URL(requestUrl).searchParams.get("filters") ?? "[]";
  return JSON.parse(decodeURIComponent(value)) as Array<{
    field: string;
    operator: string;
    values?: string[];
  }>;
}

async function expectMenuInsideViewport(page: Page, name: string) {
  const menu = page.getByRole("menu", { name });
  await expect(menu).toBeVisible();
  const panel = page.locator(".oa-pending-payments-column-filter__panel").filter({ has: menu });
  const actions = panel.locator(".oa-pending-payments-column-filter__actions");
  await expect(actions).toBeVisible();
  await expect(actions.getByRole("button", { name: "应用筛选" })).toBeInViewport();
  const box = await panel.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  if (!box || !viewport) {
    return;
  }
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);
}

function waitForOaPendingPaymentRows(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/oa-pending-payments/rows");
  });
}

function createOaPendingLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    module: "oa-pending-payments",
  });
}

test.describe("OA pending payments browser flow", () => {
  test("recovers rows after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      oaPendingPaymentRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    await expect(page.getByText("OA 待付款核对加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("OA 待付款核对加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("暂无 OA 待付款核对数据")).toHaveCount(0);
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `oa-pending-payments.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新 OA 待付款核对",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForOaPendingPaymentRows(page);
        await page.getByRole("button", { name: "刷新 OA 待付款核对" }).click();
        const response = await mark("apiLatencyMs", responsePromise);
        recovered = response.status() === 200;
        if (recovered) {
          await mark(
            "finalSettledLatencyMs",
            expect(page.getByRole("row", { name: /浏览器付款申请人/ })).toBeVisible(),
          );
        } else {
          await mark(
            "firstVisibleResponseLatencyMs",
            expect(page.getByText("OA 待付款核对加载失败，请点击刷新重试。")).toBeVisible(),
          );
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("OA 待付款核对加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByText("OA 待付款核对加载失败，请点击刷新重试。")).toHaveCount(0);
    const recoveredRow = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(recoveredRow).toBeVisible();
    await expect(recoveredRow).toContainText("浏览器待付款项目");
    await expect(recoveredRow).toContainText("已支付");
    await expect(page.getByText("1-1 / 1")).toBeVisible();
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(3);
  });

  test("filters, sorts, and opens OA, bank, invoice, and rules drawers", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createOaPendingLatencyRecorder(page, testInfo);

    await page.goto("/oa-pending-payments");
    await expect(page.getByTestId("oa-pending-payments-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "OA 待付款核对" })).toBeVisible();
    await expect(page.getByRole("table", { name: "OA待付款核对表格" })).toBeVisible();

    const row = page.getByRole("row", { name: /浏览器付款申请人/ });
    await expect(row).toBeVisible();
    const tableShellSize = await page.getByTestId("oa-pending-payments-table-shell").evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(tableShellSize.scrollWidth).toBeLessThanOrEqual(tableShellSize.clientWidth + 1);
    await expect(row).toContainText("浏览器待付款项目");
    await expect(row).toContainText("已支付");
    await expect(row).toContainText("浏览器待付款供应商");
    await expect(row).toContainText("INV-PAY-E2E-001");
    await expect(row).toContainText("建设银行 1234");
    await expect(row).toContainText("8000.00");
    await expect(row).toContainText("12000.00");
    expect(api.count("GET /api/oa-pending-payments/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/oa-pending-payments/filter-options")).toBe(0);

    const searchRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("keyword") === "浏览器付款申请人";
    });
    await page.getByLabel("搜索OA待付款核对").fill("浏览器付款申请人");
    await recordLatency({
      operationId: "oa-pending-payments.search-query",
      visibleLabel: "查询",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "查询" }).click();
      await mark("apiLatencyMs", searchRequest);
      await mark("finalSettledLatencyMs", expect(row).toBeVisible());
    });
    expect(new URL((await searchRequest).url()).searchParams.get("page_size")).toBe("20");

    await recordLatency({
      operationId: "oa-pending-payments.open-payment-status-filter",
      visibleLabel: "筛选 支付状态",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 支付状态" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("menu", { name: "支付状态筛选" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("menuitemcheckbox", { name: "支付状态：已支付 1" })).toBeVisible());
    });
    await expectMenuInsideViewport(page, "支付状态筛选");
    await page.getByRole("menuitemcheckbox", { name: "支付状态：已支付 1" }).click();
    const filterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && (url.searchParams.get("filters") ?? "").includes("paid");
    });
    await recordLatency({
      operationId: "oa-pending-payments.apply-payment-status-filter",
      visibleLabel: "应用筛选",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "应用筛选" }).click();
      await mark("apiLatencyMs", filterRequest);
      await mark("finalSettledLatencyMs", expect(row).toBeVisible());
    });
    expect(filtersFromRequest((await filterRequest).url())).toContainEqual({
      field: "payment_status",
      operator: "in",
      values: ["paid"],
    });

    await recordLatency({
      operationId: "oa-pending-payments.open-project-filter",
      visibleLabel: "筛选 项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 项目" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("menu", { name: "项目筛选" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("menuitemcheckbox", { name: "项目名称：浏览器待付款项目 1" })).toBeVisible());
    });
    await expectMenuInsideViewport(page, "项目筛选");
    await page.getByRole("menuitemcheckbox", { name: "项目名称：浏览器待付款项目 1" }).click();
    const projectFilterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && (url.searchParams.get("filters") ?? "").includes("oa_project_name");
    });
    await recordLatency({
      operationId: "oa-pending-payments.apply-project-filter",
      visibleLabel: "应用筛选",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "应用筛选" }).click();
      await mark("apiLatencyMs", projectFilterRequest);
      await mark("finalSettledLatencyMs", expect(row).toBeVisible());
    });
    expect(filtersFromRequest((await projectFilterRequest).url())).toContainEqual({
      field: "oa_project_name",
      operator: "in",
      values: ["浏览器待付款项目"],
    });

    const sortRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && url.searchParams.get("sort_field") === "bank_trade_time";
    });
    await recordLatency({
      operationId: "oa-pending-payments.sort-bank-trade-time",
      visibleLabel: "交易时间 排序",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "交易时间 排序" }).click();
      await mark("apiLatencyMs", sortRequest);
      await mark("finalSettledLatencyMs", expect(row).toBeVisible());
    });
    expect(new URL((await sortRequest).url()).searchParams.get("sort_direction")).toBe("desc");

    await recordLatency({
      operationId: "oa-pending-payments.open-seller-filter",
      visibleLabel: "筛选 发票方",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 发票方" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("menu", { name: "发票方筛选" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("menuitemcheckbox", { name: "发票方：浏览器待付款供应商 1" })).toBeVisible());
    });
    await expectMenuInsideViewport(page, "发票方筛选");
    await page.getByRole("menuitemcheckbox", { name: "发票方：浏览器待付款供应商 1" }).click();
    const sellerFilterRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/oa-pending-payments/rows")
        && (url.searchParams.get("filters") ?? "").includes("seller_name");
    });
    await recordLatency({
      operationId: "oa-pending-payments.apply-seller-filter",
      visibleLabel: "应用筛选",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "应用筛选" }).click();
      await mark("apiLatencyMs", sellerFilterRequest);
      await mark("finalSettledLatencyMs", expect(row).toBeVisible());
    });
    expect(filtersFromRequest((await sellerFilterRequest).url())).toContainEqual({
      field: "seller_name",
      operator: "in",
      values: ["浏览器待付款供应商"],
    });

    await recordLatency({
      operationId: "oa-pending-payments.open-oa-detail",
      visibleLabel: "查看 OA 浏览器付款申请人 详情",
      actionType: "click",
    }, async (mark) => {
      const detailResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/oa/oa-payment-e2e-001/detail"),
      );
      await row.getByRole("button", { name: "查看 OA 浏览器付款申请人 详情" }).click();
      await mark("apiLatencyMs", detailResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "OA详情" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("浏览器待付款项目").last()).toBeVisible());
    });
    await expect(page.getByText("浏览器待付款项目").last()).toBeVisible();
    await recordLatency({
      operationId: "oa-pending-payments.close-oa-detail",
      visibleLabel: "关闭详情抽屉",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭详情抽屉" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "OA详情" })).toHaveCount(0));
    });
    await expect(page.getByRole("heading", { name: "OA详情" })).toHaveCount(0);

    await recordLatency({
      operationId: "oa-pending-payments.open-bank-detail",
      visibleLabel: "查看流水 浏览器付款申请人 详情",
      actionType: "click",
    }, async (mark) => {
      const detailResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/bank-transactions/bank-payment-e2e-001/detail"),
      );
      await row.getByRole("button", { name: "查看流水 浏览器付款申请人 详情" }).click();
      await mark("apiLatencyMs", detailResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "支出流水详情" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("8000.00").last()).toBeVisible());
    });
    await expect(page.getByText("支出银行")).toBeVisible();
    await expect(page.getByText("8000.00").last()).toBeVisible();
    await recordLatency({
      operationId: "oa-pending-payments.close-bank-detail",
      visibleLabel: "关闭详情抽屉",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭详情抽屉" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "支出流水详情" })).toHaveCount(0));
    });
    await expect(page.getByRole("heading", { name: "支出流水详情" })).toHaveCount(0);

    await recordLatency({
      operationId: "oa-pending-payments.open-invoice-detail",
      visibleLabel: "查看发票 浏览器付款申请人 详情",
      actionType: "click",
    }, async (mark) => {
      const detailResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/oa-pending-payments/invoices/invoice-payment-e2e-001/detail"),
      );
      await row.getByRole("button", { name: "查看发票 浏览器付款申请人 详情" }).click();
      await mark("apiLatencyMs", detailResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "发票详情" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("INV-PAY-E2E-001").last()).toBeVisible());
    });
    await expect(page.getByText("进项发票方名称")).toBeVisible();
    await expect(page.getByText("INV-PAY-E2E-001").last()).toBeVisible();
    await recordLatency({
      operationId: "oa-pending-payments.close-invoice-detail",
      visibleLabel: "关闭详情抽屉",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "关闭详情抽屉" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "发票详情" })).toHaveCount(0));
    });
    await expect(page.getByRole("heading", { name: "发票详情" })).toHaveCount(0);

    await recordLatency({
      operationId: "oa-pending-payments.open-pending-invoice-rules",
      visibleLabel: "支出流水无需开票规则设置",
      actionType: "click",
    }, async (mark) => {
      const rulesResponse = page.waitForResponse((response) =>
        response.request().method() === "GET"
        && new URL(response.url()).pathname.endsWith("/api/pending-invoices/rules"),
      );
      await page.getByRole("button", { name: "支出流水无需开票规则设置" }).click();
      await mark("apiLatencyMs", rulesResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "支出流水无需开票规则设置" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "支出流水无需开票规则设置" })).toBeVisible());
    });
    expect(api.count("GET /api/pending-invoices/rules")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/oa/oa-payment-e2e-001/detail")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/bank-transactions/bank-payment-e2e-001/detail")).toBe(1);
    expect(api.count("GET /api/oa-pending-payments/invoices/invoice-payment-e2e-001/detail")).toBe(1);
  });

  test("keeps column filter actions visible in compact viewports without mutation requests", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const mutationRequests: string[] = [];
    page.on("request", (request) => {
      if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method())) {
        mutationRequests.push(`${request.method()} ${new URL(request.url()).pathname}`);
      }
    });

    for (const viewport of [{ width: 1024, height: 420 }, { width: 1024, height: 608 }]) {
      await page.setViewportSize(viewport);
      await page.goto("/oa-pending-payments");
      const trigger = page.getByRole("button", { name: "筛选 支付状态" });
      await expect(trigger).toBeVisible();
      await page.evaluate(() => {
        const state = window as Window & { __oaPendingFilterFirstWidth?: number };
        delete state.__oaPendingFilterFirstWidth;
        const observer = new MutationObserver(() => {
          const panel = document.querySelector<HTMLElement>(".oa-pending-payments-column-filter__panel");
          if (!panel) {
            return;
          }
          state.__oaPendingFilterFirstWidth = Number.parseFloat(getComputedStyle(panel).width);
          observer.disconnect();
        });
        observer.observe(document.body, { childList: true, subtree: true });
      });

      await trigger.focus();
      await page.keyboard.press("Enter");
      await expectMenuInsideViewport(page, "支付状态筛选");
      const firstWidth = await page.evaluate(() =>
        (window as Window & { __oaPendingFilterFirstWidth?: number }).__oaPendingFilterFirstWidth);
      expect(firstWidth).toBeGreaterThanOrEqual(239);
      expect(firstWidth).toBeLessThanOrEqual(321);

      await page.keyboard.press("Escape");
      await expect(page.getByRole("menu", { name: "支付状态筛选" })).toHaveCount(0);
      await expect(trigger).toBeFocused();
    }

    expect(mutationRequests).toEqual([]);
  });
});
