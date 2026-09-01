import { Buffer } from "node:buffer";

import { expect, test, type Locator, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { currentBusinessMonth } from "../src/features/dateTime";

function statCard(page: Page, label: string) {
  return page.locator(".tax-summary-band__metric").filter({ hasText: label });
}

function createTaxOffsetLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/tax-offset",
    pageKey: "tax-offset",
    module: "tax-offset",
  });
}

function waitForTaxOffset(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/tax-offset");
  });
}

function waitForTaxOffsetCalculate(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" && url.pathname.endsWith("/api/tax-offset/calculate");
  });
}

function waitForTaxOffsetPlanSave(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" && url.pathname.endsWith("/api/tax-offset/plans");
  });
}

function waitForCertifiedImportPreview(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/tax-offset/certified-import/preview")
      && response.request().method() === "POST",
  );
}

function waitForCertifiedImportConfirm(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/tax-offset/certified-import/confirm")
      && response.request().method() === "POST",
  );
}

async function expectVisibleAndUncovered(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  await locator.scrollIntoViewIfNeeded();
  const result = await locator.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const x = Math.min(Math.max(rect.left + rect.width / 2, 0), window.innerWidth - 1);
    const y = Math.min(Math.max(rect.top + rect.height / 2, 0), window.innerHeight - 1);
    const topElement = document.elementFromPoint(x, y);
    return {
      height: rect.height,
      inViewport: rect.width > 0
        && rect.height > 0
        && rect.bottom > 0
        && rect.right > 0
        && rect.top < window.innerHeight
        && rect.left < window.innerWidth,
      isUncovered: topElement === element || Boolean(topElement && (element.contains(topElement) || topElement.contains(element))),
      topElement: topElement?.tagName ?? null,
      width: rect.width,
      x,
      y,
    };
  });
  expect(result.inViewport, `${label} should be inside the viewport: ${JSON.stringify(result)}`).toBe(true);
  expect(result.isUncovered, `${label} should not be covered: ${JSON.stringify(result)}`).toBe(true);
}

async function expectHorizontalScroll(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  await locator.scrollIntoViewIfNeeded();
  const result = await locator.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return {
      clientWidth: element.clientWidth,
      scrollLeft: element.scrollLeft,
      scrollWidth: element.scrollWidth,
    };
  });
  expect(result.scrollWidth, `${label} should overflow horizontally: ${JSON.stringify(result)}`).toBeGreaterThan(result.clientWidth);
  expect(result.scrollLeft, `${label} should scroll horizontally: ${JSON.stringify(result)}`).toBeGreaterThan(0);
}

function startStrictBrowserErrorCapture(
  page: Page,
  options: { allowedConsoleErrors?: RegExp[] } = {},
) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (options.allowedConsoleErrors?.some((pattern) => pattern.test(text))) {
        return;
      }
      errors.push(`console.error: ${text}`);
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

test.describe("tax offset browser flow", () => {
  for (const scenario of [
    {
      sessionMode: "forbidden",
      heading: "无权访问财务运营平台",
      message: "当前 OA 账号未开通访问权限，请联系管理员处理。",
    },
    {
      sessionMode: "expired",
      heading: "OA 会话已失效",
      message: null,
    },
  ] as const) {
    test(`blocks ${scenario.sessionMode} sessions before tax offset protected APIs load`, async ({ page }, testInfo) => {
      const api = await installDeterministicApiMocks(page, { sessionMode: scenario.sessionMode });
      const recordLatency = createTaxOffsetLatencyRecorder(page, testInfo);

      await recordLatency({
        operationId: `tax-offset.open-page-${scenario.sessionMode}`,
        visibleLabel: scenario.heading,
        actionType: "navigate",
      }, async (mark) => {
        await page.goto("/tax-offset");
        await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: scenario.heading })).toBeVisible());
      });

      await expect(page.getByRole("heading", { name: scenario.heading })).toBeVisible();
      if (scenario.message) {
        await expect(page.getByText(scenario.message)).toBeVisible();
      }
      await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toHaveCount(0);
      expect(api.count("GET /api/tax-offset")).toBe(0);
      expect(api.count("POST /api/tax-offset/calculate")).toBe(0);
      expect(api.count("POST /api/tax-offset/plans")).toBe(0);
      expect(api.count("POST /api/tax-offset/certified-import/preview")).toBe(0);
      expect(api.count("POST /api/tax-offset/certified-import/confirm")).toBe(0);
    });
  }

  test("shows tax offset write controls for admin users without requiring admin-only pages", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
    const recordLatency = createTaxOffsetLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "tax-offset.open-page-admin",
      visibleLabel: "税金抵扣计划与试算",
      actionType: "navigate",
    }, async (mark) => {
      const response = waitForTaxOffset(page);
      await page.goto("/tax-offset");
      expect((await mark("apiLatencyMs", response)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(page.getByRole("button", { name: "已认证发票导入" })).toBeVisible();
    await expect(page.getByRole("button", { name: "保存计划" })).toBeEnabled();

    const dialog = page.getByRole("dialog", { name: "已认证发票导入" });
    await recordLatency({
      operationId: "tax-offset.open-certified-import-dialog-admin",
      visibleLabel: "已认证发票导入",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "已认证发票导入" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(dialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(dialog.getByText("当前页面暂不可导入已认证发票。")).toHaveCount(0));
    });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("当前页面暂不可导入已认证发票。")).toHaveCount(0);

    expect(api.count("POST /api/tax-offset/plans")).toBe(0);
    expect(api.count("POST /api/tax-offset/certified-import/preview")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("keeps large tax tables searchable, sortable, filterable, and horizontally scrollable on narrow screens", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      taxOffsetLargeDataset: true,
    });
    const recordLatency = createTaxOffsetLatencyRecorder(page, testInfo);

    await page.setViewportSize({ width: 390, height: 820 });
    await recordLatency({
      operationId: "tax-offset.open-page-large-dataset",
      visibleLabel: "税金抵扣计划与试算",
      actionType: "navigate",
    }, async (mark) => {
      const response = waitForTaxOffset(page);
      await page.goto("/tax-offset");
      expect((await mark("apiLatencyMs", response)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible());
    });

    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(statCard(page, "销项税额").getByText("41600.00")).toBeVisible();
    await expect(page.getByText("销项票 81", { exact: true })).toBeVisible();
    await expectVisibleAndUncovered(page.getByRole("button", { name: "已认证发票导入" }), "certified import button");
    await expectVisibleAndUncovered(page.getByRole("button", { name: "保存计划" }), "save tax plan button");

    const outputPanel = page.locator(".tax-panel").filter({ hasText: "销项票开票情况" });
    const inputPanel = page.locator(".tax-panel").filter({ hasText: "进项票认证计划" });
    const inputGrid = page.getByRole("grid", { name: "进项票认证计划" });
    await expect(outputPanel.getByText("共 81 条")).toBeVisible();
    await expect(inputPanel.getByText("已选 2 / 92")).toBeVisible();

    const sharedScrollbar = page.locator(".tax-layout-scrollbar");
    await expectHorizontalScroll(sharedScrollbar, "shared tax table scrollbar");
    await expectVisibleAndUncovered(outputPanel.getByRole("columnheader", { name: "金额（税率）" }), "output table amount-rate column");
    await expectVisibleAndUncovered(inputPanel.getByRole("columnheader", { name: "金额（税率）" }), "input table amount-rate column");

    await recordLatency({
      operationId: "tax-offset.open-input-search",
      visibleLabel: "搜索 进项票认证计划",
      actionType: "click",
    }, async (mark) => {
      await inputPanel.getByRole("button", { name: "搜索 进项票认证计划" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("searchbox", { name: "搜索 进项票认证计划" })).toBeVisible());
    });
    await recordLatency({
      operationId: "tax-offset.filter-input-search",
      visibleLabel: "搜索 进项票认证计划",
      actionType: "fill",
    }, async (mark) => {
      await page.getByRole("searchbox", { name: "搜索 进项票认证计划" }).fill("超长供应商-089");
      await mark("finalSettledLatencyMs", expect(inputPanel.getByRole("row", { name: /1129900089/ })).toBeVisible());
    });
    await expect(inputPanel.getByRole("row", { name: /1129900089/ })).toBeVisible();
    await expect(inputPanel.getByText("已选 0 / 1（共 92）")).toBeVisible();

    await recordLatency({
      operationId: "tax-offset.clear-input-search",
      visibleLabel: "清空搜索 进项票认证计划",
      actionType: "click",
    }, async (mark) => {
      await inputPanel.getByRole("button", { name: "清空搜索 进项票认证计划" }).click();
      await mark("finalSettledLatencyMs", expect(inputPanel.getByText("已选 2 / 92")).toBeVisible());
    });
    await expect(inputPanel.getByText("已选 2 / 92")).toBeVisible();
    await recordLatency({
      operationId: "tax-offset.close-input-search",
      visibleLabel: "收起搜索 进项票认证计划",
      actionType: "click",
    }, async (mark) => {
      await inputPanel.getByRole("button", { name: "收起搜索 进项票认证计划" }).click();
      await mark("finalSettledLatencyMs", expect(page.getByRole("searchbox", { name: "搜索 进项票认证计划" })).toHaveCount(0));
    });
    await recordLatency({
      operationId: "tax-offset.sort-input-time-ascending",
      visibleLabel: "进项票认证计划按时间降序",
      actionType: "click",
    }, async (mark) => {
      await inputPanel.getByRole("button", { name: "进项票认证计划按时间降序" }).click();
      await mark("finalSettledLatencyMs", expect(inputPanel.getByRole("button", { name: "进项票认证计划按时间升序" })).toBeVisible());
    });
    await expect(inputPanel.getByRole("button", { name: "进项票认证计划按时间升序" })).toBeVisible();

    await inputGrid.evaluate((grid) => grid.scrollIntoView({ block: "start", inline: "nearest" }));
    const inputCounterpartyFilter = inputGrid
      .getByRole("columnheader", { name: /对方名称/ })
      .getByRole("button", { name: "筛选 对方名称" });
    await expectVisibleAndUncovered(inputCounterpartyFilter, "input tax counterparty filter");
    const counterpartyFilterDialog = page.getByRole("dialog", { name: "筛选 对方名称" });
    await recordLatency({
      operationId: "tax-offset.open-input-counterparty-filter",
      visibleLabel: "筛选 对方名称",
      actionType: "click",
    }, async (mark) => {
      await inputCounterpartyFilter.click();
      await mark("firstVisibleResponseLatencyMs", expect(counterpartyFilterDialog).toBeVisible());
    });
    await expect(counterpartyFilterDialog).toBeVisible();
    await recordLatency({
      operationId: "tax-offset.apply-input-counterparty-filter",
      visibleLabel: "进项超长供应商-003-筛选滚动验证",
      actionType: "click",
    }, async (mark) => {
      await counterpartyFilterDialog
        .getByText("进项超长供应商-003-筛选滚动验证", { exact: true })
        .click();
      await mark("finalSettledLatencyMs", expect(inputPanel.getByRole("row", { name: /1129900003/ })).toBeVisible());
    });
    await expect(inputPanel.getByRole("row", { name: /1129900003/ })).toBeVisible();
    await expect(inputPanel.getByText("已选 0 / 1（共 92）")).toBeVisible();

    expect(api.count("GET /api/tax-offset")).toBeGreaterThan(0);
    expect(api.count("POST /api/tax-offset/plans")).toBe(0);
    expect(browserErrors).toEqual([]);
  });

  test("shows a version conflict instead of a false save success when canonical facts changed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 409 \(Conflict\)/],
    });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      taxOffsetPlanSaveConflict: true,
    });
    const recordLatency = createTaxOffsetLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "tax-offset.open-page-plan-conflict",
      visibleLabel: "税金抵扣计划与试算",
      actionType: "navigate",
    }, async (mark) => {
      const response = waitForTaxOffset(page);
      await page.goto("/tax-offset");
      expect((await mark("apiLatencyMs", response)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(statCard(page, "计划进项税额").getByText("18240.00")).toBeVisible();

    await recordLatency({
      operationId: "tax-offset.toggle-input-plan-before-conflict",
      visibleLabel: "进项计划 11203491",
      actionType: "click",
    }, async (mark) => {
      const calculateResponse = waitForTaxOffsetCalculate(page);
      await page.getByRole("row", { name: /11203491/ }).locator(".checkbox__control").click();
      expect((await mark("apiLatencyMs", calculateResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(statCard(page, "计划进项税额").getByText("12480.00")).toBeVisible());
    });
    await expect(statCard(page, "计划进项税额").getByText("12480.00")).toBeVisible();

    const fetchCountBeforeSave = api.count("GET /api/tax-offset");
    await recordLatency({
      operationId: "tax-offset.save-plan-conflict",
      visibleLabel: "保存计划",
      actionType: "click",
    }, async (mark) => {
      const conflictResponse = waitForTaxOffsetPlanSave(page);
      await page.getByRole("button", { name: "保存计划" }).click();
      expect((await mark("apiLatencyMs", conflictResponse)).status()).toBe(409);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("税金抵扣数据已变化，请刷新后重新保存。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "保存计划" })).toBeEnabled());
    });

    await expect(page.getByText("税金抵扣数据已变化，请刷新后重新保存。")).toBeVisible();
    await expect(page.getByText("已保存本月税金抵扣计划。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "保存计划" })).toBeEnabled();

    expect(api.count("POST /api/tax-offset/plans")).toBe(1);
    expect(api.count("GET /api/tax-offset")).toBe(fetchCountBeforeSave);
    expect(browserErrors).toEqual([]);
  });

  test("recalculates and saves a tax plan, then imports certified invoices in the page modal", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createTaxOffsetLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "tax-offset.open-page-happy-path",
      visibleLabel: "税金抵扣计划与试算",
      actionType: "navigate",
    }, async (mark) => {
      const response = waitForTaxOffset(page);
      await page.goto("/tax-offset");
      expect((await mark("apiLatencyMs", response)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "税金抵扣计划与试算" })).toBeVisible();
    await expect(statCard(page, "销项税额").getByText("41600.00")).toBeVisible();
    await expect(statCard(page, "计划进项税额").getByText("18240.00")).toBeVisible();
    await expect(page.getByRole("grid", { name: "销项票开票情况" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项票认证计划" })).toBeVisible();

    await recordLatency({
      operationId: "tax-offset.toggle-input-plan-happy-path",
      visibleLabel: "进项计划 11203491",
      actionType: "click",
    }, async (mark) => {
      const calculateResponse = waitForTaxOffsetCalculate(page);
      await page.getByRole("row", { name: /11203491/ }).locator(".checkbox__control").click();
      expect((await mark("apiLatencyMs", calculateResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(statCard(page, "计划进项税额").getByText("12480.00")).toBeVisible());
    });
    await expect(statCard(page, "计划进项税额").getByText("12480.00")).toBeVisible();
    await expect(statCard(page, "本月应纳税额").getByText("29120.00")).toBeVisible();
    expect(api.count("POST /api/tax-offset/calculate")).toBe(1);

    await recordLatency({
      operationId: "tax-offset.save-plan-happy-path",
      visibleLabel: "保存计划",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = waitForTaxOffsetPlanSave(page);
      await page.getByRole("button", { name: "保存计划" }).click();
      expect((await mark("apiLatencyMs", saveResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByText("已保存本月税金抵扣计划。")).toBeVisible());
    });
    await expect(page.getByText("已保存本月税金抵扣计划。")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("POST /api/tax-offset/plans")).toBe(1);

    const dialog = page.getByRole("dialog", { name: "已认证发票导入" });
    await recordLatency({
      operationId: "tax-offset.open-certified-import-dialog-happy-path",
      visibleLabel: "已认证发票导入",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "已认证发票导入" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(dialog).toBeVisible());
    });
    await expect(dialog).toBeVisible();
    await recordLatency({
      operationId: "tax-offset.select-certified-import-file",
      visibleLabel: "选择已认证发票文件",
      actionType: "upload",
    }, async (mark) => {
      await dialog.locator('input[type="file"]').setInputFiles({
        name: "2026年3月 进项认证结果.xlsx",
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: Buffer.from("tax-certified-import-e2e"),
      });
      await mark("finalSettledLatencyMs", expect(dialog.getByText(`已选择 1 个文件，当前页面月份为 ${currentBusinessMonth()}。确认导入后会刷新当前税金抵扣页。`)).toBeVisible());
    });
    await expect(dialog.getByText(`已选择 1 个文件，当前页面月份为 ${currentBusinessMonth()}。确认导入后会刷新当前税金抵扣页。`)).toBeVisible();

    await recordLatency({
      operationId: "tax-offset.preview-certified-import",
      visibleLabel: "预览识别结果",
      actionType: "click",
    }, async (mark) => {
      const previewResponse = waitForCertifiedImportPreview(page);
      await dialog.getByRole("button", { name: "预览识别结果" }).click();
      expect((await mark("apiLatencyMs", previewResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(dialog.getByRole("region", { name: "已认证发票预览结果" })).toBeVisible());
    });
    await expect(dialog.getByRole("region", { name: "已认证发票预览结果" })).toBeVisible();
    await expect(dialog.getByText("识别记录 2 条")).toBeVisible();
    await expect(dialog.getByText("匹配计划 1 条").first()).toBeVisible();
    await expect(dialog.getByRole("grid", { name: "2026年3月 进项认证结果.xlsx 行级预览结果" })).toBeVisible();
    await expect(dialog.getByText("高速通行服务商")).toBeVisible();
    expect(api.count("POST /api/tax-offset/certified-import/preview")).toBe(1);

    const taxOffsetFetchCountBeforeConfirm = api.count("GET /api/tax-offset");
    await recordLatency({
      operationId: "tax-offset.confirm-certified-import",
      visibleLabel: "确认导入",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = waitForCertifiedImportConfirm(page);
      await dialog.getByRole("button", { name: "确认导入" }).click();
      expect((await mark("apiLatencyMs", confirmResponse)).status()).toBe(200);
      await expect.poll(() => api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetFetchCountBeforeConfirm);
      await mark("finalSettledLatencyMs", expect(page.getByText("已导入 2 条已认证记录，并已刷新当前税金抵扣页面。")).toBeVisible());
    });
    await expect.poll(() => api.count("POST /api/tax-offset/certified-import/confirm")).toBe(1);
    await expect.poll(() => api.count("GET /api/tax-offset")).toBeGreaterThan(taxOffsetFetchCountBeforeConfirm);
    await expect(page.getByText("已导入 2 条已认证记录，并已刷新当前税金抵扣页面。")).toBeVisible();
    await expect(statCard(page, "已认证结果进项税额").getByText("14080.00")).toBeVisible();
    await expect(page.getByRole("complementary", { name: "已认证结果" }).getByText("高速通行服务商")).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
