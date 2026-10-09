import { expect, test, type Locator, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function startStrictBrowserErrorCapture(page: Page, options: { allowedConsoleErrors?: RegExp[] } = {}) {
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

function responsePathMatches(responseUrl: string, pathname: string) {
  return new URL(responseUrl).pathname === pathname;
}

function waitForTurnoverLedger(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/turnover-ledger");
  });
}

function createTurnoverLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/turnover-ledger",
    pageKey: "turnover-ledger",
    module: "turnover-ledger",
  });
}

function responseFor(method: string, pathname: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === method && new URL(response.url()).pathname.endsWith(pathname);
}

async function clickCheckbox(checkbox: Locator) {
  const control = checkbox
    .locator("xpath=ancestor::*[descendant::*[@data-slot='checkbox-control']][1]")
    .locator("[data-slot='checkbox-control']");
  await (await control.count() ? control : checkbox).click();
}

const turnoverFlowLabels = {
  expense: "云南建设有限公司 2026-05-03 10:00:00 支出 1000.00",
  income: "云南建设有限公司 2026-05-02 10:00:00 收入 1000.00",
} as const;

test.describe("turnover ledger browser flow", () => {
  test("keeps inline chips, column alignment and the nearby breakdown usable across widths", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "user", turnoverCostFanout: true });
    let reads = 0;
    page.on("request", request => { if (new URL(request.url()).pathname.endsWith("/api/turnover-ledger")) reads += 1; });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/turnover-ledger");
    const expand = page.getByRole("button", { name: "展开 云南建设有限公司 流水明细", exact: true });
    await expect(expand).toBeVisible();
    const initialReads = reads;
    const start = performance.now();
    await expand.click();
    const flows = page.getByRole("grid", { name: "云南建设有限公司的银行流水" });
    await expect(flows).toBeVisible();
    const expandMs = performance.now() - start;
    expect(await flows.locator("xpath=..").evaluate(el => el.scrollHeight <= el.clientHeight + 1)).toBe(true);
    await expect(flows.locator("thead th").first()).toHaveCSS("position", "static");
    const firstRow = flows.locator("tbody tr").first();
    const trigger = page.getByRole("button", { name: "查看分类明细" });
    for (const width of [1920, 1440, 960]) {
      await page.setViewportSize({ width, height: 1080 });
      const geometry = await firstRow.evaluate(row => {
        const label = row.querySelector(".finance-truncated-text")!;
        const chip = row.querySelector(".turnover-flow-chip")!;
        const a = label.getBoundingClientRect(); const b = chip.getBoundingClientRect();
        const table = row.closest("table")!;
        const selection = table.querySelector('thead [data-column-role="selection"]')!.getBoundingClientRect();
        const checkbox = row.querySelector('[data-slot="checkbox-control"]')!.getBoundingClientRect();
        return {
          selectionCenter: selection.x + selection.width / 2, checkboxCenter: checkbox.x + checkbox.width / 2,
          labelCenter: a.y + a.height / 2, chipCenter: b.y + b.height / 2,
          chipWidth: b.width,
          align: ["date", "amount", "status", "action"].map(role => [
            getComputedStyle(table.querySelector(`thead [data-column-role="${role}"]`)!).textAlign,
            getComputedStyle(row.querySelector(`[data-column-role="${role}"]`)!).textAlign,
          ]),
          headBackground: getComputedStyle(table.querySelector("thead th")!).backgroundColor,
          rowBackground: getComputedStyle(row).backgroundColor,
        };
      });
      expect(Math.abs(geometry.labelCenter - geometry.chipCenter)).toBeLessThanOrEqual(2);
      expect(geometry.chipWidth).toBeGreaterThan(35);
      expect(Math.abs(geometry.selectionCenter - geometry.checkboxCenter)).toBeLessThanOrEqual(2);
      expect(geometry.align).toEqual([["center", "center"], ["right", "right"], ["center", "center"], ["center", "center"]]);
      expect(geometry.headBackground).not.toBe(geometry.rowBackground);
      const metric = (await page.getByTestId("turnover-summary-collected").boundingBox())!;
      const button = (await trigger.boundingBox())!;
      expect(button.x - metric.x - metric.width).toBeGreaterThanOrEqual(0);
      expect(button.x - metric.x - metric.width).toBeLessThanOrEqual(40);
      expect(await page.locator("body").evaluate(body => body.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`turnover-layout-${width}.png`), fullPage: true, animations: "disabled" });
      await trigger.click();
      const dialog = page.getByRole("dialog", { name: "往来款分类明细" });
      await expect(dialog).toContainText("当前搜索及结算条件下的四类往来统计");
      const box = (await dialog.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(width);
      await page.screenshot({ path: testInfo.outputPath(`turnover-breakdown-${width}.png`), fullPage: true, animations: "disabled" });
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
      await expect(trigger).toBeFocused();
    }
    await page.setViewportSize({ width: 1440, height: 1080 });
    await firstRow.locator(".finance-truncated-text").focus();
    await expect(page.getByRole("tooltip")).toContainText("外部往来款");
    await page.keyboard.press("Escape");
    await clickCheckbox(firstRow.getByRole("checkbox"));
    await expect(firstRow).toHaveClass(/turnover-flow-selected/);
    await clickCheckbox(firstRow.getByRole("checkbox"));
    await expect(firstRow).not.toHaveClass(/turnover-flow-selected/);
    await trigger.click();
    await page.getByRole("heading", { name: "外部往来款" }).click();
    await expect(page.getByRole("dialog", { name: "往来款分类明细" })).not.toBeVisible();
    await trigger.click();
    await trigger.click();
    await expect(page.getByRole("dialog", { name: "往来款分类明细" })).not.toBeVisible();
    expect(reads).toBe(initialReads);
    await testInfo.attach("turnover-layout-metrics", { body: JSON.stringify({ expandMs, additionalLedgerReads: reads - initialReads }), contentType: "application/json" });
  });

  test("keeps the header and pagination visible while only ledger rows scroll", async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "user", turnoverLedgerTotal: 121 });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/turnover-ledger");
    await expect(page.getByText("分页往来方 001")).toBeVisible();
    const scroller = page.locator(".turnover-register-scroll");
    const header = page.locator(".turnover-register > thead");
    const firstRow = page.locator(".turnover-register > tbody > tr").first();
    const footer = page.locator(".turnover-register-footer");
    let reads = 0;
    page.on("request", request => { if (new URL(request.url()).pathname.endsWith("/api/turnover-ledger")) reads += 1; });
    const measurements = [];
    for (const size of [20, 50, 100]) {
      if (size !== 20) {
        await page.getByRole("button", { name: /每页对象数/ }).click();
        await page.getByRole("option", { name: `每页 ${size} 个` }).click();
        await expect(page.getByText(`显示 1-${size} / 121`)).toBeVisible();
        await expect.poll(() => scroller.evaluate(el => el.scrollTop)).toBe(0);
      }
      const readsBeforeScroll = reads;
      // Measure a sticky cell: the thead's own box still moves in native tables.
      const cell = header.locator("th").first();
      const headBefore = (await cell.boundingBox())!;
      const rowBefore = (await firstRow.boundingBox())!;
      const footerBefore = (await footer.boundingBox())!;
      const start = performance.now();
      await scroller.evaluate(el => { el.scrollTop = 400; });
      await expect.poll(() => scroller.evaluate(el => el.scrollTop)).toBe(400);
      const headAfter = (await cell.boundingBox())!;
      expect(Math.abs(headAfter.y - headBefore.y)).toBeLessThanOrEqual(1);
      expect(rowBefore.y - (await firstRow.boundingBox())!.y).toBeGreaterThan(390);
      expect((await footer.boundingBox())!.y).toBe(footerBefore.y);
      expect(footerBefore.y + footerBefore.height).toBeLessThanOrEqual(900);
      expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)).toBe(true);
      expect(reads).toBe(readsBeforeScroll);
      measurements.push({ pageSize: size, scrollObservationMs: performance.now() - start });
    }
    await page.screenshot({ path: "../outputs/turnover-sticky-local.png", animations: "disabled" });
    await page.getByRole("button", { name: "下一页" }).click();
    await expect(page.getByText("分页往来方 101")).toBeVisible();
    await expect.poll(() => scroller.evaluate(el => el.scrollTop)).toBe(0);
    await page.setViewportSize({ width: 960, height: 640 });
    await expect.poll(async () => { const box = (await footer.boundingBox())!; return box.y + box.height; }).toBeLessThanOrEqual(640);
    await scroller.evaluate(el => { el.scrollLeft = 200; });
    const align = await page.locator(".turnover-register").evaluate(table => {
      const th = table.querySelector("thead th")!.getBoundingClientRect();
      const td = table.querySelector("tbody th")!.getBoundingClientRect();
      return Math.abs(th.x - td.x) < 1 && Math.abs(th.width - td.width) < 1;
    });
    expect(align).toBe(true);
    await page.evaluate(() => { document.documentElement.style.zoom = "1.25"; });
    await footer.getByRole("button", { name: /每页对象数/ }).click();
    await expect(page.getByRole("option", { name: "每页 20 个" })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.screenshot({ path: "../outputs/turnover-sticky-zoom.png", fullPage: true, animations: "disabled" });
    await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
    await page.setViewportSize({ width: 390, height: 500 });
    expect(await scroller.evaluate(el => el.clientHeight)).toBeGreaterThanOrEqual(150);
    await footer.getByRole("button", { name: /每页对象数/ }).click();
    await expect(page.getByRole("option", { name: "每页 20 个" })).toBeVisible();
    await page.keyboard.press("Escape");
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/turnover-ledger?embedded=oa");
    await expect(page.getByText("分页往来方 001")).toBeVisible();
    await expect(page.locator(".app-shell")).toHaveClass(/embedded-shell/);
    const embeddedHeader = (await header.locator("th").first().boundingBox())!;
    await scroller.evaluate(el => { el.scrollTop = 300; });
    await expect.poll(() => scroller.evaluate(el => el.scrollTop)).toBe(300);
    expect(Math.abs((await header.locator("th").first().boundingBox())!.y - embeddedHeader.y)).toBeLessThanOrEqual(1);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)).toBe(true);
    await page.screenshot({ path: "../outputs/turnover-sticky-embedded.png", animations: "disabled" });
    await testInfo.attach("turnover-scroll-measurements", { body: JSON.stringify(measurements), contentType: "application/json" });
  });

  test("reaches all turnover groups after the first 100", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, {
      sessionMode: "user",
      turnoverLedgerTotal: 121,
    });

    await page.goto("/turnover-ledger");
    await expect(page.getByText("分页往来方 001")).toBeVisible();
    await expect(page.getByText("显示 1-20 / 121")).toBeVisible();
    await page.getByRole("button", { name: /每页对象数/ }).click();
    await page.getByRole("option", { name: "每页 50 个" }).click();
    await expect(page.getByText("显示 1-50 / 121")).toBeVisible();

    const secondPageResponse = waitForTurnoverLedger(page);
    await page.getByRole("button", { name: "下一页" }).click();
    const secondPageUrl = new URL((await secondPageResponse).url());
    expect(secondPageUrl.searchParams.get("page")).toBe("2");
    expect(secondPageUrl.searchParams.get("page_size")).toBe("50");
    await expect(page.getByText("分页往来方 051")).toBeVisible();
    await expect(page.getByText("分页往来方 001")).toHaveCount(0);
    await expect(page.getByText("显示 51-100 / 121")).toBeVisible();

    const thirdPageResponse = waitForTurnoverLedger(page);
    await page.getByRole("button", { name: "下一页" }).click();
    const thirdPageUrl = new URL((await thirdPageResponse).url());
    expect(thirdPageUrl.searchParams.get("page")).toBe("3");
    await expect(page.getByText("分页往来方 121")).toBeVisible();
    await expect(page.getByText("显示 101-121 / 121")).toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test("recovers grouped ledger after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      turnoverLedgerFailuresBeforeSuccess: 2,
    });
    const recordLatency = createTurnoverLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "turnover-ledger.open-page-load-failure",
      visibleLabel: "外部往来款",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/turnover-ledger");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("turnover-ledger-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible();
    await expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("暂无往来款台账")).toHaveCount(0);
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `turnover-ledger.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新台账",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForTurnoverLedger(page);
        await page.getByRole("button", { name: "重试读取" }).click();
        const response = await mark("apiLatencyMs", responsePromise);
        recovered = response.status() === 200;
        if (recovered) {
          await mark("finalSettledLatencyMs", expect(page.getByRole("table", { name: "外部往来款台账" })).toBeVisible());
        } else {
          await mark("firstVisibleResponseLatencyMs", expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toBeVisible());
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("往来款台账加载暂时失败，请刷新后重试。")).toHaveCount(0);
    const table = page.getByRole("table", { name: "外部往来款台账" });
    await expect(table).toBeVisible();
    await expect(table.getByText("云南建设有限公司")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toHaveCount(0);
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThanOrEqual(3);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves turnover tag selection and reloads the ledger through page access", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
    });
    const recordLatency = createTurnoverLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "turnover-ledger.open-page-tag-selection",
      visibleLabel: "外部往来款",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/turnover-ledger");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("turnover-ledger-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible();
    const ledgerLoadsBeforeSave = api.count("GET /api/turnover-ledger");

    const drawer = page.getByRole("dialog", { name: "外部往来款标签设置" });
    await recordLatency({
      operationId: "turnover-ledger.open-tag-selection",
      visibleLabel: "外部往来款标签设置",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "外部往来款标签设置" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByLabel("外部往来款付款")).toBeChecked());
    });
    await expect(drawer.getByLabel("外部往来款付款")).toBeChecked();
    await expect(drawer.getByLabel("外部往来款收款")).toBeChecked();

    await recordLatency({
      operationId: "turnover-ledger.uncheck-income-tag",
      visibleLabel: "外部往来款收款",
      actionType: "uncheck",
    }, async (mark) => {
      await clickCheckbox(drawer.getByLabel("外部往来款收款"));
      await mark("finalSettledLatencyMs", expect(drawer.getByLabel("外部往来款收款")).not.toBeChecked());
    });
    await recordLatency({
      operationId: "turnover-ledger.save-tag-selection",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(responseFor("PUT", "/api/turnover-ledger/tag-selection"));
      const reloadResponse = waitForTurnoverLedger(page);
      await drawer.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("外部往来款标签设置已保存")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    await expect(page.getByText("外部往来款标签设置已保存")).toBeVisible();
    await expect(drawer).toBeVisible();
    await drawer.getByRole("button", { name: "关闭外部往来款标签设置" }).click();
    await expect(drawer).toHaveCount(0);
    expect(api.lastBody("PUT /api/turnover-ledger/tag-selection")).toEqual({
      expected_version: 1,
      selected_tag_codes: ["external_turnover_payment"],
    });
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThan(ledgerLoadsBeforeSave);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("saves relation extra details and reloads only the visible turnover ledger", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
    });
    const recordLatency = createTurnoverLatencyRecorder(page, testInfo);

    await page.goto("/turnover-ledger");
    await expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible();
    const table = page.getByRole("table", { name: "外部往来款台账" });
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
    const expenseRow = table.getByRole("checkbox", { name: `选择流水 ${turnoverFlowLabels.expense}` }).locator("xpath=ancestor::tr[1]");
    await expect(expenseRow).toContainText("外部往来款付款");
    await expect(expenseRow).toContainText("归还借款");

    const drawer = page.getByRole("dialog", { name: "编辑流水补充信息" });
    await recordLatency({
      operationId: "turnover-ledger.open-relation-extra",
      visibleLabel: "编辑流水补充信息",
      actionType: "click",
    }, async (mark) => {
      const detailResponse = page.waitForResponse(responseFor(
        "GET",
        "/api/turnover-ledger/relations/turnover_rel_e2e_expense",
      ));
      await table.getByRole("button", { name: `编辑流水 ${turnoverFlowLabels.expense}` }).click();
      expect((await mark("apiLatencyMs", detailResponse)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "保存补充信息" })).toBeDisabled());
    });
    await expect(drawer.getByText("2026-05-03 10:00:00")).toBeVisible();
    expect(api.count("GET /api/turnover-ledger/relations/turnover_rel_e2e_expense/extra")).toBe(0);

    await drawer.getByLabel("利率值").fill("0.070000");
    await expect(drawer.getByRole("button", { name: "保存补充信息" })).toBeEnabled();
    const ledgerLoadsBeforeSave = api.count("GET /api/turnover-ledger");
    await recordLatency({
      operationId: "turnover-ledger.save-relation-extra",
      visibleLabel: "保存补充信息",
      actionType: "click",
    }, async (mark) => {
      const saveResponse = page.waitForResponse(responseFor(
        "PUT",
        "/api/turnover-ledger/relations/turnover_rel_e2e_expense/extra",
      ));
      const reloadResponse = waitForTurnoverLedger(page);
      await drawer.getByRole("button", { name: "保存补充信息" }).click();
      expect((await mark("apiLatencyMs", saveResponse)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("补充信息已保存")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    expect(api.count("PUT /api/turnover-ledger/relations/turnover_rel_e2e_expense/extra")).toBe(1);
    expect(api.lastBody("PUT /api/turnover-ledger/relations/turnover_rel_e2e_expense/extra")).toMatchObject({
      interest_rate_value: "0.070000",
      expected_versions: {
        "turnover_relation_extra:turnover_rel_e2e_expense": "2026-06-17T09:00:00+08:00",
      },
    });
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThan(ledgerLoadsBeforeSave);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("keeps B active when delayed A requests finish and saves only B", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    const putRequests: Array<{ path: string; body: Record<string, unknown> }> = [];
    let delayedExpenseRequestsFinished = 0;

    await page.route("**/api/turnover-ledger/relations/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const method = request.method();
      const relationMatch = path.match(/^\/api\/turnover-ledger\/relations\/(turnover_rel_e2e_(?:expense|income))(\/extra)?$/);
      if (!relationMatch) {
        await route.fallback();
        return;
      }
      const relationId = relationMatch[1];
      if (method === "PUT") {
        putRequests.push({ path, body: JSON.parse(request.postData() ?? "{}") as Record<string, unknown> });
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            relation_id: relationId,
            extra: {
              relation_id: relationId,
              ...putRequests.at(-1)?.body,
              updated_at: "2026-06-17T09:30:00+08:00",
              updated_by: "TESTFULL001",
            },
          }),
        });
        return;
      }
      if (relationId === "turnover_rel_e2e_expense") {
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
      try {
        await route.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            relation: {
              relation_id: relationId,
              status: "confirmed",
              status_label: "流水",
              bank_account_labels: [],
              bank_account_display_labels: [],
            },
            bank_rows: [],
            extra: {
              relation_id: relationId,
              interest_rate_type: "annual",
              interest_rate_value: relationId.endsWith("income") ? "0.050000" : "0.060000",
              interest_paid_amount: "10.00",
              interest_paid_date: "2026-05-05",
              interest_payment_method: "转账",
              note: relationId.endsWith("income") ? "B 的浏览器补充信息" : "A 的过期浏览器补充信息",
              updated_at: relationId.endsWith("income")
                ? "2026-06-17T09:10:00+08:00"
                : "2026-06-17T09:00:00+08:00",
            },
            audit_history: [],
          }),
        });
      } catch {
        // The browser may cancel A after B becomes active; correctness must not depend on a late response being delivered.
      } finally {
        if (relationId === "turnover_rel_e2e_expense") {
          delayedExpenseRequestsFinished += 1;
        }
      }
    });

    await page.goto("/turnover-ledger");
    const table = page.getByRole("table", { name: "外部往来款台账" });
    await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
    await table.getByRole("button", { name: `编辑流水 ${turnoverFlowLabels.expense}` }).click();
    const drawer = page.getByRole("dialog", { name: "编辑流水补充信息" });
    await expect(drawer).toBeVisible();

    await table.getByRole("button", { name: `编辑流水 ${turnoverFlowLabels.income}`, includeHidden: true }).evaluate((button) => {
      (button as HTMLButtonElement).click();
    });
    await expect(drawer.getByLabel("备注")).toHaveValue("B 的浏览器补充信息");
    await expect.poll(() => delayedExpenseRequestsFinished).toBe(1);
    await expect(drawer.getByLabel("备注")).toHaveValue("B 的浏览器补充信息");

    await drawer.getByLabel("备注").fill("只保存浏览器 B");
    await drawer.getByRole("button", { name: "保存补充信息" }).click();
    await expect(page.getByText("补充信息已保存")).toBeVisible();

    expect(putRequests).toEqual([{
      path: "/api/turnover-ledger/relations/turnover_rel_e2e_income/extra",
      body: expect.objectContaining({
        note: "只保存浏览器 B",
        expected_versions: {
          "turnover_relation_extra:turnover_rel_e2e_income": "2026-06-17T09:10:00+08:00",
        },
      }),
    }]);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });

  test("confirms and withdraws a manual turnover closure through page-access convergence", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "user",
      turnoverCostFanout: true,
    });
    const recordLatency = createTurnoverLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "turnover-ledger.open-page",
      visibleLabel: "外部往来款",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/turnover-ledger");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("turnover-ledger-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible());
    });
    await expect(page.getByRole("heading", { name: "外部往来款" })).toBeVisible();

    const table = page.getByRole("table", { name: "外部往来款台账" });
    await expect(table).toBeVisible();
    await recordLatency({
      operationId: "turnover-ledger.expand-group",
      visibleLabel: "展开 云南建设有限公司 流水明细",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
      const expenseRow = table.getByRole("checkbox", { name: `选择流水 ${turnoverFlowLabels.expense}` }).locator("xpath=ancestor::tr[1]");
      await mark("finalSettledLatencyMs", expect(expenseRow).toContainText("外部往来款付款"));
      await expect(expenseRow).toContainText("归还借款");
      await expect(expenseRow.locator(".turnover-flow-chip")).toHaveText("已还款");
      await expect(expenseRow).not.toContainText("往来标记：");
      await expect(table.getByRole("columnheader", { name: "流水标签" })).toBeVisible();
      await page.screenshot({ path: "../outputs/turnover-ledger-expanded.png", fullPage: true, animations: "disabled" });
    });

    await recordLatency({
      operationId: "turnover-ledger.select-expense-row",
      visibleLabel: `选择流水 ${turnoverFlowLabels.expense}`,
      actionType: "check",
    }, async (mark) => {
      await clickCheckbox(table.getByRole("checkbox", { name: `选择流水 ${turnoverFlowLabels.expense}` }));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 1 笔")).toBeVisible());
    });
    await recordLatency({
      operationId: "turnover-ledger.select-income-row",
      visibleLabel: `选择流水 ${turnoverFlowLabels.income}`,
      actionType: "check",
    }, async (mark) => {
      await clickCheckbox(table.getByRole("checkbox", { name: `选择流水 ${turnoverFlowLabels.income}` }));
      await mark("finalSettledLatencyMs", expect(page.getByText("已选 2 笔")).toBeVisible());
    });
    await expect(page.getByText("已选 2 笔")).toBeVisible();
    await expect(page.getByRole("button", { name: "确认闭环" })).toBeEnabled();

    const drawer = page.getByRole("dialog", { name: "确认外部往来闭环" });
    await recordLatency({
      operationId: "turnover-ledger.open-closure-confirm",
      visibleLabel: "确认闭环",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "确认闭环" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByTestId("turnover-closure-delta")).toHaveText("0.00"));
    });
    await expect(drawer.getByText("turnover-bank-expense-1000")).toHaveCount(0);
    await expect(drawer.getByText("turnover-bank-income-1000")).toHaveCount(0);
    await expect(drawer.getByText("收入", { exact: true })).toBeVisible();
    await expect(drawer.getByText("支出", { exact: true })).toBeVisible();
    await expect(drawer.getByTestId("turnover-closure-delta")).toHaveText("0.00");
    await page.screenshot({ path: "../outputs/turnover-ledger-confirm.png", fullPage: true, animations: "disabled" });
    await recordLatency({
      operationId: "turnover-ledger.confirm-manual-closure",
      visibleLabel: "确定",
      actionType: "click",
    }, async (mark) => {
      const confirmResponse = page.waitForResponse(responseFor("POST", "/api/turnover-ledger/closures/confirm"));
      const reloadResponse = waitForTurnoverLedger(page);
      await drawer.getByRole("button", { name: "确认闭环" }).click();
      await mark("apiLatencyMs", confirmResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("外部往来闭环已确认")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    await expect(page.getByText("外部往来闭环已确认")).toBeVisible();
    await expect(page.getByRole("heading", { name: "操作失败" })).toHaveCount(0);
    await expect(page.getByText("银行流水状态已变化，请刷新后重试。")).toHaveCount(0);
    expect(api.count("POST /api/turnover-ledger/closures/confirm")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    await expect(table.getByText("已结清").first()).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);

    await expect(drawer).toBeVisible();
    await drawer.getByRole("button", { name: "关闭确认外部往来闭环" }).click();
    await expect(drawer).toBeHidden();
    const costExplorerResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && responsePathMatches(response.url(), "/api/cost-statistics/explorer")
      && response.status() === 200);
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.open-after-turnover-closure",
      visibleLabel: "成本",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("link", { name: "成本" }).click();
      await mark("apiLatencyMs", costExplorerResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "成本" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("radio", { name: "按项目" })).toBeVisible());
    });
    const costPayload = await (await costExplorerResponse).json() as Record<string, unknown>;
    expect(costPayload).not.toHaveProperty("read_model_status");
    expect(costPayload).not.toHaveProperty("refresh_enqueued");
    await recordLatency({
      route: "/cost-statistics",
      pageKey: "cost-statistics",
      module: "cost-statistics",
      operationId: "cost-statistics.verify-project-view-after-turnover-closure",
      visibleLabel: "按项目统计",
      actionType: "read",
    }, async (mark) => {
      await mark("finalSettledLatencyMs", expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible());
    });
    await expect(page.getByRole("button", { name: /外部往来闭环成本项目/ })).toHaveCount(0);
    await expect(page.getByText("浏览器 e2e 归还借款")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);

    await recordLatency({
      operationId: "turnover-ledger.reopen-after-cost-fanout",
      visibleLabel: "外部往来款",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/turnover-ledger");
      await mark("finalSettledLatencyMs", expect(page.getByTestId("turnover-ledger-page")).toBeVisible());
    });
    await expect(table).toBeVisible();
    await recordLatency({
      operationId: "turnover-ledger.expand-closed-group",
      visibleLabel: "展开 云南建设有限公司 流水明细",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "展开 云南建设有限公司 流水明细" }).click();
      await mark("finalSettledLatencyMs", expect(table.getByText("已结清").first()).toBeVisible());
    });
    const ledgerLoadsBeforeWithdraw = api.count("GET /api/turnover-ledger");
    await recordLatency({
      operationId: "turnover-ledger.select-closed-row",
      visibleLabel: `选择流水 ${turnoverFlowLabels.expense}`,
      actionType: "check",
    }, async (mark) => {
      await clickCheckbox(table.getByRole("checkbox", { name: `选择流水 ${turnoverFlowLabels.expense}` }));
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "撤回闭环" })).toBeEnabled());
    });
    await expect(page.getByRole("button", { name: "撤回闭环" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "确认闭环" })).toHaveCount(0);
    await recordLatency({
      operationId: "turnover-ledger.withdraw-manual-closure",
      visibleLabel: "撤回闭环",
      actionType: "click",
    }, async (mark) => {
      const withdrawResponse = page.waitForResponse(responseFor("POST", "/api/turnover-ledger/closures/withdraw"));
      const reloadResponse = waitForTurnoverLedger(page);
      await page.getByRole("button", { name: "撤回闭环" }).click();
      const withdrawDrawer = page.getByRole("dialog", { name: "撤回外部往来闭环" });
      await expect(withdrawDrawer.getByRole("row")).toHaveCount(3);
      await withdrawDrawer.getByRole("button", { name: "确认撤回" }).click();
      await mark("apiLatencyMs", withdrawResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByText("外部往来闭环已撤回")).toBeVisible());
      await mark("finalSettledLatencyMs", reloadResponse);
    });

    await expect(page.getByText("外部往来闭环已撤回")).toBeVisible();
    expect(api.count("POST /api/turnover-ledger/closures/withdraw")).toBe(1);
    expect(api.count("POST /api/operation-barrier/status")).toBe(0);
    expect(api.count("GET /api/turnover-ledger")).toBeGreaterThan(ledgerLoadsBeforeWithdraw);
    await expect(table.getByText("已结清")).toHaveCount(0);
    await expect(table.getByText("未闭环")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(browserErrors).toEqual([]);
  });
});
