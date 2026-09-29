import { readXlsxText } from './fixtures/xlsx';
import { readFile } from "node:fs/promises";

import { expect, test, type Page, type Download, type TestInfo } from "./fixtures/strictTest";

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

function mutationCalls(calls: string[]) {
  return calls.filter((entry) => /^(POST|PUT|PATCH|DELETE) /.test(entry));
}

function durableWriteCalls(calls: string[]) {
  const readLikePosts = new Set([
    "POST /api/input-invoice-usage/oa-reverse/preview",
    "POST /api/operation-barrier/status",
  ]);
  return mutationCalls(calls).filter((entry) => !readLikePosts.has(entry));
}

function createInputInvoiceUsageLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/input-invoice-usage",
    pageKey: "input-invoice-usage",
    module: "input-invoice-usage",
  });
}

function waitForInputInvoiceUsageRows(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/rows");
  });
}

test("search keeps a single focus frame and usable controls at desktop and narrow widths", async ({ page }, testInfo) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/input-invoice-usage");
  const search = page.getByRole("searchbox", { name: "进项发票使用情况搜索" });
  const form = page.getByRole("search");
  const group = form.locator(".search-field__group");
  await expect(search).toBeVisible();
  await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();

  for (const width of [1440, 1280, 768]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("heading", { name: "进项发票使用情况", exact: true }).click();
    await expect(search).toHaveCSS("border-top-width", "0px");
    await expect(search).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await search.click();
    await expect(search).toBeFocused();
    await expect(group).toHaveAttribute("data-focus-within", "true");
    await expect(search).toHaveCSS("border-top-width", "0px");
    await expect(search).not.toHaveCSS("box-shadow", /0px 0px 0px 3px/);

    const readsBeforeTyping = api.calls.filter((call) => call.startsWith("GET /api/input-invoice-usage/rows")).length;
    await search.fill("中文供应商 OA 12345678901234567890");
    const clear = form.getByRole("button", { name: "清除查询" });
    await expect(clear).toBeVisible();
    const geometry = await group.evaluate((element) => {
      const input = element.querySelector("input")!;
      const icon = element.querySelector("svg")!;
      const clearButton = element.querySelector("button")!;
      return {
        input: input.getBoundingClientRect().toJSON(),
        icon: icon.getBoundingClientRect().toJSON(),
        clear: clearButton.getBoundingClientRect().toJSON(),
        group: element.getBoundingClientRect().toJSON(),
      };
    });
    expect(geometry.input.left).toBeGreaterThanOrEqual(geometry.icon.right - 1);
    expect(geometry.input.right).toBeLessThanOrEqual(geometry.clear.left + 1);
    expect(geometry.clear.right).toBeLessThanOrEqual(geometry.group.right);
    expect(geometry.input.width).toBeGreaterThan(80);
    const formBox = await form.boundingBox();
    expect(formBox!.x).toBeGreaterThanOrEqual(0);
    expect(formBox!.x + formBox!.width).toBeLessThanOrEqual(width);
    expect(api.calls.filter((call) => call.startsWith("GET /api/input-invoice-usage/rows")).length).toBe(readsBeforeTyping);
    await page.screenshot({ path: testInfo.outputPath(`search-${width}.png`) });
    await clear.click();
    await expect(search).toHaveValue("");
  }

  await search.fill("浏览器进项供应商");
  const responsePromise = waitForInputInvoiceUsageRows(page);
  await search.press("Enter");
  const response = await responsePromise;
  expect(new URL(response.url()).searchParams.get("keyword")).toBe("浏览器进项供应商");
  expect(new URL(response.url()).searchParams.get("page")).toBe("1");
  expect(response.ok()).toBeTruthy();
  await search.press("Tab");
  await expect(form.getByRole("button", { name: "查询", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(search).toBeFocused();
  await expect(search).toHaveCSS("border-top-width", "0px");
  const clearResponsePromise = waitForInputInvoiceUsageRows(page);
  await form.getByRole("button", { name: "清除查询" }).click();
  const clearResponse = await clearResponsePromise;
  expect(new URL(clearResponse.url()).searchParams.has("keyword")).toBe(false);
  await expect(search).toHaveValue("");
});

function waitForInputInvoiceUsageExportPreview(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export-summary");
  });
}

function waitForInputInvoiceUsageExport(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export");
  });
}

function waitForInputInvoiceUsagePaymentRules(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/payment-status-rules");
  });
}

function waitForInputInvoiceUsagePaymentRulesSave(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "PUT" && url.pathname.endsWith("/api/input-invoice-usage/payment-status-rules");
  });
}

function waitForInputInvoiceUsageOaReversePreview(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "POST" && url.pathname.endsWith("/api/input-invoice-usage/oa-reverse/preview");
  });
}

function waitForInputInvoiceUsageRelationDetails(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname.endsWith("/api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")
      && url.searchParams.get("kind") === "oa";
  });
}

function waitForInputInvoiceUsageOaDraft(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/input-invoice-usage/oa-reverse/oa-draft")
      && response.request().method() === "POST",
  );
}

function waitForInputInvoiceUsageManualStatus(page: Page) {
  return page.waitForResponse((response) =>
    response.url().includes("/api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status")
      && response.request().method() === "POST",
  );
}

function decodedFilters(url: URL) {
  const raw = url.searchParams.get("filters");
  if (!raw) {
    return [];
  }
  return JSON.parse(decodeURIComponent(raw)) as Array<{ field?: string; operator?: string; values?: string[] }>;
}

test.describe("input invoice usage browser flow", () => {
  test("administrator saves reverse-OA prefill while runtime payee stays canonical", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    const loadResponse = page.waitForResponse((response) =>
      response.request().method() === "GET"
      && new URL(response.url()).pathname === "/api/workbench/settings/oa-draft-prefill/input-invoice-usage",
    );
    await page.getByRole("button", { name: "OA 草稿预填管理" }).click();
    await loadResponse;

    const drawer = page.getByRole("dialog", { name: "OA 草稿预填管理" });
    await expect(drawer.getByLabel("收款方")).toHaveValue("按所选发票销方自动填充");
    await expect(drawer.getByLabel("收款方")).toBeDisabled();
    await drawer.getByLabel("开户行").fill("招商银行");
    const saveResponse = page.waitForResponse((response) =>
      response.request().method() === "PUT"
      && new URL(response.url()).pathname === "/api/workbench/settings/oa-draft-prefill/input-invoice-usage",
    );
    await drawer.getByRole("button", { name: "保存" }).click();
    await saveResponse;

    const body = api.lastBody("PUT /api/workbench/settings/oa-draft-prefill/input-invoice-usage") as {
      configuration?: { bank?: string; payee?: string; reason_template?: string };
    };
    expect(body.configuration?.bank).toBe("招商银行");
    expect(body.configuration?.payee).toBe("");
    expect(body.configuration?.reason_template).not.toContain("batch_id");
    await expect(drawer.getByText("已保存。")).toBeVisible();
    expect(browserErrors).toEqual([]);
  });

  test("recovers rows after a transient load failure when refreshed", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRowsFailuresBeforeSuccess: 2,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-load-failure",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      await page.goto("/input-invoice-usage");
      await mark("firstVisibleResponseLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("进项发票使用情况加载暂时失败，请刷新后重试。")).toBeVisible());
    });
    await expect(page.getByText("进项发票使用情况加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("当前条件下没有进项发票使用记录。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      await recordLatency({
        operationId: `input-invoice-usage.refresh-after-load-failure.${attempt + 1}`,
        visibleLabel: "刷新",
        actionType: "click",
      }, async (mark) => {
        const responsePromise = waitForInputInvoiceUsageRows(page);
        await page.getByRole("button", { name: "刷新" }).click();
        recovered = (await mark("apiLatencyMs", responsePromise)).status() === 200;
        if (recovered) {
          await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /SD-INV-E2E-0001/ })).toBeVisible());
        } else {
          await mark("firstVisibleResponseLatencyMs", expect(page.getByText("进项发票使用情况加载暂时失败，请刷新后重试。")).toBeVisible());
        }
      });
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("进项发票使用情况加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByText("进项发票使用情况加载失败，请点击刷新重试。")).toHaveCount(0);
    const recoveredRow = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(recoveredRow).toBeVisible();
    await expect(recoveredRow.getByText("待处理")).toBeVisible();
    await expect(page.getByText("第 1 / 1 页")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeEnabled();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(3);
    expect(browserErrors).toEqual([]);
  });

  test("keeps filter, sort, and page-size controls synchronized with fresh rows", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageFilterSortRows: true,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    let initialRowsResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageRows>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.open-page-filter-sort",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const initialRowsPromise = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      initialRowsResponse = await mark("apiLatencyMs", initialRowsPromise);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    if (!initialRowsResponse) {
      throw new Error("missing initial input invoice rows response");
    }
    const initialRowsUrl = new URL(initialRowsResponse.url());
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();
    await expect(page.getByText("第 1 / 2 页")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0001")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0099")).toHaveCount(0);
    expect(initialRowsUrl.searchParams.get("page")).toBe("1");
    expect(initialRowsUrl.searchParams.get("page_size")).toBe("20");
    expect(initialRowsUrl.searchParams.has("filters")).toBe(false);
    expect(initialRowsUrl.searchParams.has("sort_field")).toBe(false);

    const compositeMenu = page.getByRole("menu", { name: "OA / OA申请人组合筛选" });
    await page.getByRole("button", { name: "筛选 OA / OA申请人" }).click();
    const applicantOption = compositeMenu
      .locator("label.input-invoice-usage-filter-menu__item")
      .filter({ hasText: /陈秀云 \d+/ });
    await expect(applicantOption).toBeVisible();
    const applicantRowsPromise = waitForInputInvoiceUsageRows(page);
    await applicantOption.click();
    const applicantRowsUrl = new URL((await applicantRowsPromise).url());
    expect(decodedFilters(applicantRowsUrl)).toEqual([
      { field: "oa_applicant", operator: "in", values: ["陈秀云"] },
    ]);
    const clearApplicantRowsPromise = waitForInputInvoiceUsageRows(page);
    await applicantOption.click();
    expect(new URL((await clearApplicantRowsPromise).url()).searchParams.has("filters")).toBe(false);
    await page.keyboard.press("Escape");
    await expect(compositeMenu).toHaveCount(0);

    const sellerMenu = page.getByRole("menu", { name: "销方名称筛选与排序" });
    await recordLatency({
      operationId: "input-invoice-usage.open-seller-filter",
      visibleLabel: "筛选 销方名称",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "筛选 销方名称" }).click();
      await mark("finalSettledLatencyMs", expect(
        sellerMenu.locator("label.input-invoice-usage-filter-menu__item").filter({ hasText: /页外供应商 1/ }),
      ).toBeVisible());
    });

    let filteredRowsResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageRows>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.apply-seller-filter",
      visibleLabel: "页外供应商 1",
      actionType: "click",
    }, async (mark) => {
      const filteredRowsPromise = waitForInputInvoiceUsageRows(page);
      await sellerMenu.locator("label.input-invoice-usage-filter-menu__item").filter({ hasText: /页外供应商 1/ }).click();
      filteredRowsResponse = await mark("apiLatencyMs", filteredRowsPromise);
      await mark("finalSettledLatencyMs", expect(page.getByText("第 1 / 1 页")).toBeVisible());
    });
    if (!filteredRowsResponse) {
      throw new Error("missing filtered input invoice rows response");
    }
    const filteredRowsUrl = new URL(filteredRowsResponse.url());
    const filters = decodedFilters(filteredRowsUrl);
    await expect(page.getByText("第 1 / 1 页")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0099")).toBeVisible();
    await expect(page.getByText("页外供应商").first()).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0001")).toHaveCount(0);
    expect(filteredRowsUrl.searchParams.get("page")).toBe("1");
    expect(filteredRowsUrl.searchParams.get("page_size")).toBe("20");
    expect(filters).toEqual([
      { field: "seller_name", operator: "in", values: ["页外供应商"] },
    ]);

    let clearedRowsResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageRows>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.clear-seller-filter",
      visibleLabel: "清空",
      actionType: "click",
    }, async (mark) => {
      const clearedRowsPromise = waitForInputInvoiceUsageRows(page);
      const clearSellerFilter = sellerMenu.getByRole("menuitem", { name: "清空" });
      await clearSellerFilter.click();
      clearedRowsResponse = await mark("apiLatencyMs", clearedRowsPromise);
      await mark("finalSettledLatencyMs", expect(page.getByText("第 1 / 2 页")).toBeVisible());
    });
    if (!clearedRowsResponse) {
      throw new Error("missing cleared input invoice rows response");
    }
    const clearedRowsUrl = new URL(clearedRowsResponse.url());
    await expect(page.getByText("第 1 / 2 页")).toBeVisible();
    expect(clearedRowsUrl.searchParams.has("filters")).toBe(false);
    await page.keyboard.press("Escape");

    let sortedRowsResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageRows>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.sort-invoice-date",
      visibleLabel: "按开票日期排序",
      actionType: "click",
    }, async (mark) => {
      const sortedRowsPromise = waitForInputInvoiceUsageRows(page);
      await page.getByRole("button", { name: "按开票日期排序" }).click();
      sortedRowsResponse = await mark("apiLatencyMs", sortedRowsPromise);
      await mark("finalSettledLatencyMs", expect(page.locator("tbody tr").first()).toContainText("SD-INV-E2E-0099"));
    });
    if (!sortedRowsResponse) {
      throw new Error("missing sorted input invoice rows response");
    }
    const sortedRowsUrl = new URL(sortedRowsResponse.url());
    await expect(page.locator("tbody tr").first()).toContainText("SD-INV-E2E-0099");
    expect(sortedRowsUrl.searchParams.get("sort_field")).toBe("invoice_date");
    expect(sortedRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    let pageSizeRowsResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageRows>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.change-page-size-50",
      visibleLabel: "每页行数",
      actionType: "select",
    }, async (mark) => {
      const pageSizeRowsPromise = waitForInputInvoiceUsageRows(page);
      await page.getByRole("button", { name: /每页行数/ }).click();
      await page.getByRole("option", { name: "50", exact: true }).click();
      pageSizeRowsResponse = await mark("apiLatencyMs", pageSizeRowsPromise);
      await mark("finalSettledLatencyMs", expect(page.getByText("第 1 / 1 页")).toBeVisible());
    });
    if (!pageSizeRowsResponse) {
      throw new Error("missing page-size input invoice rows response");
    }
    const pageSizeRowsUrl = new URL(pageSizeRowsResponse.url());
    await expect(page.getByText("第 1 / 1 页")).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(23);
    expect(pageSizeRowsUrl.searchParams.get("page")).toBe("1");
    expect(pageSizeRowsUrl.searchParams.get("page_size")).toBe("50");
    expect(pageSizeRowsUrl.searchParams.get("sort_field")).toBe("invoice_date");
    expect(pageSizeRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(4);
    expect(api.count("GET /api/input-invoice-usage/filter-options")).toBe(0);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("refreshes current rows after page-authorized payment status rules are saved", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsagePaymentRulesSaveFlow: true,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-payment-rules-save",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const initialRowsPromise = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      expect((await mark("apiLatencyMs", initialRowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();
    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toContainText("待付款（自动识别有oa无流水）");

    const rulesDrawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
    await recordLatency({
      operationId: "input-invoice-usage.open-payment-rules-page-authorized",
      visibleLabel: "发票与支付状态规则设置",
      actionType: "click",
    }, async (mark) => {
      const rulesResponse = waitForInputInvoiceUsagePaymentRules(page);
      await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
      expect((await mark("apiLatencyMs", rulesResponse)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(rulesDrawer).toBeVisible());
    });
    await expect(rulesDrawer).toBeVisible();
    await expect(rulesDrawer.getByText(/版本\s*1/)).toHaveCount(0);
    await expect(rulesDrawer.getByRole("button", { name: "保存", exact: true })).toBeDisabled();

    await recordLatency({
      operationId: "input-invoice-usage.edit-payment-rule-label",
      visibleLabel: "支付状态",
      actionType: "fill",
    }, async (mark) => {
      await rulesDrawer.getByRole("textbox", { name: "支付状态" }).first().fill("待付款（规则保存后刷新）");
      await mark("finalSettledLatencyMs", expect(rulesDrawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled());
    });
    await expect(rulesDrawer.getByRole("button", { name: "保存", exact: true })).toBeEnabled();

    await recordLatency({
      operationId: "input-invoice-usage.save-payment-rules",
      visibleLabel: "保存",
      actionType: "click",
    }, async (mark) => {
      const saveResponsePromise = waitForInputInvoiceUsagePaymentRulesSave(page);
      const refreshedRowsPromise = waitForInputInvoiceUsageRows(page);
      await rulesDrawer.getByRole("button", { name: "保存", exact: true }).click();
      expect((await mark("apiLatencyMs", saveResponsePromise)).status()).toBe(200);
      expect((await refreshedRowsPromise).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(row).toContainText("待付款（规则保存后刷新）"));
    });

    const saveBody = api.lastBody("PUT /api/input-invoice-usage/payment-status-rules") as {
      expectedVersion?: unknown;
      idempotencyKey?: unknown;
      rules?: Array<{ id?: string; label?: string }>;
    };
    expect(saveBody.expectedVersion).toBe(1);
    expect(String(saveBody.idempotencyKey ?? "")).toMatch(/^input-invoice-usage-payment-rules-save:/);
    expect(saveBody.rules?.find((rule) => rule.id === "waiting_payment")?.label).toBe("待付款（规则保存后刷新）");

    await expect(rulesDrawer.getByText("规则已保存。")).toBeVisible();
    await expect(rulesDrawer.getByText(/版本\s*2/)).toHaveCount(0);
    await expect(row).toContainText("待付款（规则保存后刷新）");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(2);
    expect(api.count("PUT /api/input-invoice-usage/payment-status-rules")).toBe(1);
    expect(durableWriteCalls(api.calls)).toEqual(["PUT /api/input-invoice-usage/payment-status-rules"]);
    expect(browserErrors).toEqual([]);
  });

  test("opens +N canonical relation details without mutations", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRelationDetailList: true,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-relation-detail-fresh",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsResponse = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      expect((await mark("apiLatencyMs", rowsResponse)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();
    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("合计 188.00")).toBeVisible();

    const detailDrawer = page.getByRole("dialog", { name: "OA详情" });
    await recordLatency({
      operationId: "input-invoice-usage.open-relation-detail-fresh",
      visibleLabel: "查看陈秀云关联OA 2 条",
      actionType: "click",
    }, async (mark) => {
      const detailResponsePromise = waitForInputInvoiceUsageRelationDetails(page);
      await row.getByRole("button", { name: "查看陈秀云关联OA 2 条" }).click();
      expect((await mark("apiLatencyMs", detailResponsePromise)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(detailDrawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(detailDrawer.getByRole("tab", {name: "1 陈秀云 · 88.00"})).toBeVisible());
    });
    await expect(detailDrawer).toBeVisible();
    await expect(detailDrawer.getByText("关联概况")).toHaveCount(0);
    await expect(detailDrawer.getByText("关系数量")).toHaveCount(0);
    await expect(detailDrawer.getByText("是否多条")).toHaveCount(0);
    await expect(detailDrawer.getByText("关联摘要")).toHaveCount(0);
    await expect(detailDrawer.getByRole("tab", {name: "1 陈秀云 · 88.00"})).toBeVisible();
    await expect(detailDrawer.getByText("陈秀云", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("88.00", { exact: true })).toBeVisible();
    await detailDrawer.getByRole("tab", {name: "2 刘际涛 · 100.00"}).click();
    await expect(detailDrawer.getByText("陈秀云", {exact: true})).toHaveCount(0);
    await expect(detailDrawer.getByRole("tabpanel")).toHaveCount(1);
    await expect(detailDrawer.getByText("刘际涛", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("100.00", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("详情暂不可用")).toHaveCount(0);
    await expect(detailDrawer.getByText("正在加载完整详情")).toHaveCount(0);
    await expect(detailDrawer.getByText("input_invoice_usage_relation_detail")).toHaveCount(0);

    expect(api.count("GET /api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")).toBe(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("downloads current filtered rows without paginating the export", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-export-download",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsResponsePromise = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      expect((await mark("apiLatencyMs", rowsResponsePromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();
    await recordLatency({
      operationId: "input-invoice-usage.search-before-export",
      visibleLabel: "查询",
      actionType: "click",
    }, async (mark) => {
      const rowsResponsePromise = waitForInputInvoiceUsageRows(page);
      await page.getByLabel("进项发票使用情况搜索").fill("浏览器进项供应商");
      await page.getByRole("button", { name: "查询", exact: true }).click();
      expect((await mark("apiLatencyMs", rowsResponsePromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByRole("row", { name: /SD-INV-E2E-0001/ })).toBeVisible());
    });
    await expect(page.getByRole("row", { name: /SD-INV-E2E-0001/ })).toBeVisible();

    let previewResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageExportPreview>> | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.open-export-preview",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForInputInvoiceUsageExportPreview(page);
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      previewResponse = await mark("apiLatencyMs", previewResponsePromise);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("dialog", { name: "导出进项发票" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "导出进项发票" }).getByText("导出 1 张")).toBeVisible());
    });
    if (!previewResponse) {
      throw new Error("missing input invoice usage export preview response");
    }
    const previewUrl = new URL(previewResponse.url());
    expect(previewResponse.status()).toBe(200);
    expect(previewUrl.searchParams.get("keyword")).toBeNull();
    expect(previewUrl.searchParams.has("page")).toBe(false);
    expect(previewUrl.searchParams.has("page_size")).toBe(false);

    const drawer = page.getByRole("dialog", { name: "导出进项发票" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("导出 1 张")).toBeVisible();

    let exportResponse: Awaited<ReturnType<typeof waitForInputInvoiceUsageExport>> | undefined;
    let download: Download | undefined;
    await recordLatency({
      operationId: "input-invoice-usage.download-export",
      visibleLabel: "下载 Excel",
      actionType: "click",
    }, async (mark) => {
      const exportResponsePromise = waitForInputInvoiceUsageExport(page);
      const downloadPromise = page.waitForEvent("download");
      await drawer.getByRole("button", { name: "下载 Excel" }).click();
      exportResponse = await mark("apiLatencyMs", exportResponsePromise);
      download = await mark("finalSettledLatencyMs", downloadPromise);
    });
    if (!exportResponse || !download) {
      throw new Error("missing input invoice usage export download response");
    }
    const exportUrl = new URL(exportResponse.url());
    expect(exportResponse.status()).toBe(200);
    expect(exportUrl.searchParams.get("keyword")).toBeNull();
    expect(exportUrl.searchParams.has("page")).toBe(false);
    expect(exportUrl.searchParams.has("page_size")).toBe(false);
    expect(download.suggestedFilename()).toBe("input-invoice-usage.xlsx");

    const downloadPath = testInfo.outputPath("input-invoice-usage.xlsx");
    await download.saveAs(downloadPath);
    const downloadedText = await readXlsxText(downloadPath);
    expect(downloadedText).toContain("SD-INV-E2E-0001");
    expect(downloadedText).toContain("浏览器进项供应商");
    expect(api.count("GET /api/input-invoice-usage/export-summary")).toBe(2);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("shows row-limit feedback instead of downloading an oversized export", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 400 \(Bad Request\)/],
    });
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageExportRowLimitError: true,
      sessionMode: "user",
    });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-export-row-limit",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const rowsResponsePromise = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      expect((await mark("apiLatencyMs", rowsResponsePromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    const drawer = page.getByRole("dialog", { name: "导出进项发票" });
    await recordLatency({
      operationId: "input-invoice-usage.open-export-preview-row-limit",
      visibleLabel: "筛选内容导出",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForInputInvoiceUsageExportPreview(page);
      await page.getByRole("button", { name: "筛选内容导出" }).click();
      expect((await mark("apiLatencyMs", previewResponsePromise)).status()).toBe(400);
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("alert")).toContainText("进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。"));
    });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("alert")).toContainText("进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。");
    await expect(drawer.getByRole("button", { name: "下载 Excel" })).toBeDisabled();

    expect(api.count("GET /api/input-invoice-usage/export-summary")).toBe(2);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(0);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("creates an OA reverse draft from a selected invoice subset and records submitted history", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });
    const recordLatency = createInputInvoiceUsageLatencyRecorder(page, testInfo);

    await recordLatency({
      operationId: "input-invoice-usage.open-page-oa-reverse-draft",
      visibleLabel: "进项发票使用情况",
      actionType: "navigate",
    }, async (mark) => {
      const initialRowsPromise = waitForInputInvoiceUsageRows(page);
      await page.goto("/input-invoice-usage");
      expect((await mark("apiLatencyMs", initialRowsPromise)).status()).toBe(200);
      await mark("finalSettledLatencyMs", expect(page.getByTestId("input-invoice-usage-page")).toBeVisible());
    });
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "进项发票使用情况" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "进项发票使用情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("浏览器进项供应商").first()).toBeVisible();
    await expect(row.getByText("待处理")).toBeVisible();

    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await recordLatency({
      operationId: "input-invoice-usage.open-oa-reverse-draft",
      visibleLabel: "以发票反提 OA",
      actionType: "click",
    }, async (mark) => {
      const previewResponsePromise = waitForInputInvoiceUsageOaReversePreview(page);
      await page.getByRole("button", { name: "以发票反提 OA" }).click();
      expect((await mark("apiLatencyMs", previewResponsePromise)).status()).toBe(200);
      await mark("firstVisibleResponseLatencyMs", expect(workflow).toBeVisible());
      await mark("finalSettledLatencyMs", expect(workflow.getByRole("grid", { name: "反提 OA 候选发票清单" })).toBeVisible());
    });
    await expect(workflow).toBeVisible();
    await expect(page.getByRole("tab", { name: "待处理", exact: true })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("grid", { name: "反提 OA 候选发票清单" })).toBeVisible();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).not.toBeChecked();
    await workflow.getByRole("button", { name: "选择本页" }).click();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).toBeChecked();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-002")).toBeChecked();

    await recordLatency({
      operationId: "input-invoice-usage.unselect-oa-reverse-candidate",
      visibleLabel: "选择候选发票 SD-INV-E2E-002",
      actionType: "click",
    }, async (mark) => {
      const candidateCheckbox = workflow.getByRole("checkbox", { name: "选择候选发票 SD-INV-E2E-002" });
      await candidateCheckbox.locator("xpath=ancestor::label").click();
      await expect(candidateCheckbox).not.toBeChecked();
      await mark("finalSettledLatencyMs", expect(workflow.getByText("已选 1 张", { exact: true }).last()).toBeVisible());
    });
    await expect(workflow.getByText("已选 1 张", { exact: true }).last()).toBeVisible();

    let requestBody: { invoiceIds?: string[] } | undefined;
    let subsetPreviewResponseStatus: number | undefined;
    let draftResponseStatus: number | undefined;
    const confirmDialog = page.getByRole("dialog", { name: "OA 草稿提交确认" });
    const rowsCountBeforeDraft = api.count("GET /api/input-invoice-usage/rows");
    await recordLatency({
      operationId: "input-invoice-usage.create-oa-reverse-draft",
      visibleLabel: "创建 OA 草稿",
      actionType: "click",
    }, async (mark) => {
      const subsetPreviewRequest = page.waitForRequest((request) =>
        request.url().includes("/api/input-invoice-usage/oa-reverse/preview")
          && request.method() === "POST"
          && (request.postData() ?? "").includes("input-oa-invoice-e2e-001"),
      );
      const subsetPreviewResponse = waitForInputInvoiceUsageOaReversePreview(page);
      const draftResponse = waitForInputInvoiceUsageOaDraft(page);
      await workflow.getByRole("button", { name: "创建 OA 草稿" }).click();

      requestBody = JSON.parse((await subsetPreviewRequest).postData() ?? "{}") as { invoiceIds?: string[] };
      subsetPreviewResponseStatus = (await subsetPreviewResponse).status();
      draftResponseStatus = (await mark("apiLatencyMs", draftResponse)).status();
      await mark("finalSettledLatencyMs", expect(confirmDialog).toBeVisible());
    });
    if (!requestBody) {
      throw new Error("missing OA reverse subset preview request body");
    }
    expect(requestBody.invoiceIds).toEqual(["input-oa-invoice-e2e-001"]);
    expect(subsetPreviewResponseStatus).toBe(200);
    expect(draftResponseStatus).toBe(200);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/preview")).toBeGreaterThanOrEqual(2);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(1);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBe(rowsCountBeforeDraft);

    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute(
      "href",
      "https://oa.example.test/draft/input-e2e",
    );
    await expectNoUnexpectedSuccessUiErrors(page);

    let manualStatusResponseStatus: number | undefined;
    const rowsCountBeforeManualStatus = api.count("GET /api/input-invoice-usage/rows");
    await recordLatency({
      operationId: "input-invoice-usage.confirm-oa-reverse-submitted",
      visibleLabel: "我已在OA系统提交该草稿 OA正在进行中",
      actionType: "click",
    }, async (mark) => {
      const manualStatusResponse = waitForInputInvoiceUsageManualStatus(page);
      await confirmDialog.getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ }).click();
      manualStatusResponseStatus = (await mark("apiLatencyMs", manualStatusResponse)).status();
      await mark("finalSettledLatencyMs", expect(page.getByRole("tab", { name: "已提交" })).toHaveAttribute("aria-selected", "true"));
    });
    expect(manualStatusResponseStatus).toBe(200);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBe(rowsCountBeforeManualStatus + 1);

    await expect(page.getByLabel("以发票反提 OA 提示").getByText("已进入已提交历史。")).toBeVisible();
    await expect(page.getByRole("tab", { name: "已提交" })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("grid", { name: "陈秀云已提交发票" })).toBeVisible();
    await expect(workflow.getByText("SD-INV-E2E-001")).toBeVisible();
    await expect(workflow.getByText("浏览器进项供应商一")).toBeVisible();
    await expect(workflow.getByText("input-oa-reverse-batch-e2e-001")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBe(rowsCountBeforeDraft + 1);
    expect(api.count("GET /api/input-invoice-usage/oa-reverse/submitted-history")).toBeGreaterThanOrEqual(1);
    expect(browserErrors).toEqual([]);
  });
});

test("unknown OA creation requires verified local release and requesting batches cannot be retried", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const batch = {
    batchId: "failed-oa-batch", version: 4, status: "oa_draft_failed",
    invoiceIds: ["failed-invoice"], totalWithTax: "49.86", targetApplicantName: "陈秀云",
    invoiceRows: [{ invoiceId: "failed-invoice", invoiceNo: "FAILED-INV-1", invoiceDate: "2026-09-01", sellerName: "测试销方", totalWithTax: "49.86" }],
    draftRequestState: "unknown", canRelease: true, canConfirmSubmission: false,
    oaDetectionError: "OA 响应超时",
  };
  await page.route("**/api/input-invoice-usage/oa-reverse/staged-drafts*", (route) => route.fulfill({ json: { items: [batch, { ...batch, batchId: "requesting-oa-batch", draftRequestState: "requesting", canRelease: false }] } }));
  let releaseBody: Record<string, unknown> | undefined;
  await page.route("**/api/input-invoice-usage/oa-reverse/batches/failed-oa-batch/manual-oa-status", async (route) => {
    releaseBody = route.request().postDataJSON();
    await route.fulfill({ json: { ...batch, version: 5, status: "not_submitted", canRelease: false } });
  });
  await page.goto("/input-invoice-usage");
  await page.getByRole("button", { name: "以发票反提 OA" }).click();
  await expect(page.getByRole("grid", { name: "反提 OA 候选发票清单" })).toBeVisible();
  await page.getByRole("tab", { name: "暂存" }).click();
  await expect(page.getByText(/创建结果不明/)).toBeVisible();
  await expect(page.getByText(/不会删除 OA 中的草稿/)).toBeVisible();
  await expect(page.getByText(/OA 创建请求正在处理/)).toBeVisible();
  await expect(page.getByRole("button", { name: "创建 OA 草稿" })).toHaveCount(0);
  const release = page.getByRole("button", { name: "已核实并清理 OA 草稿，解除本地占用" });
  await expect(release).toHaveCount(1);
  expect(releaseBody).toBeUndefined();
  await release.click();
  await expect(page.getByText("已解除本地暂存占用，返回候选后可重新选择发票。")).toBeVisible();
  expect(releaseBody).toMatchObject({ decision: "not_submitted", expectedVersion: 4 });
  expect(String(releaseBody?.reason)).toContain("已到 OA 核实并删除可能存在的草稿");
  expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);
});


test("OA reverse shows full invoice numbers and unlinked-OA scope without extra preview requests", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const numbers = ["00123456789012345678", "26317000003099582123456789012345"];
  let previewRequests = 0;
  await page.route("**/api/input-invoice-usage/oa-reverse/preview", async (route) => {
    previewRequests += 1;
    const body = route.request().postDataJSON();
    const rows = numbers.map((number, index) => ({ invoiceId: `full-number-${index}`, invoiceNo: number,
      invoiceDate: "2026-09-01", sellerName: "完整号码测试销方", totalWithTax: "10.00",
      bankRelationStatus: index === 0 ? "linked" : "unlinked", oaRelationStatus: "unlinked" }));
    const filtered = body.bankRelation === "all" || !body.bankRelation ? rows : rows.filter((row) => row.bankRelationStatus === body.bankRelation);
    await route.fulfill({ json: { previewId: "full-number-preview", previewHash: "full-number-hash",
      targetApplicantCode: "chen_xiuyun", targetApplicantName: "陈秀云", targetApplicants: [{ code: "chen_xiuyun", name: "陈秀云" }],
      invoiceCount: filtered.length, totalWithTax: String(filtered.length * 10),
      relationCounts: { all: 2, linked: 1, unlinked: 1 }, pagination: { page: 1, pageSize: 50, total: filtered.length },
      invoiceRows: filtered, groups: [], rejectedInvoices: [], canCreateDraft: false } });
  });
  await page.goto("/input-invoice-usage");
  await page.getByRole("button", { name: "以发票反提 OA" }).click();
  await expect(page.getByRole("heading", { name: "未关联 OA 的发票" })).toBeVisible();
  const grid = page.getByRole("grid", { name: "反提 OA 候选发票清单" });
  await expect(grid.getByText(numbers[0], { exact: true })).toBeVisible();
  expect(previewRequests).toBe(1);
  for (const [width, zoom] of [[1600, 1], [900, 1], [1100, 1.5]]) {
    // Browser zoom reduces the CSS viewport; CSS zoom on the root distorts fixed overlays.
    await page.setViewportSize({ width: Math.round(width / zoom), height: Math.round(1000 / zoom) });
    for (const number of numbers) {
      const cell = grid.getByText(number, { exact: true });
      await cell.scrollIntoViewIfNeeded();
      const layout = await cell.evaluate((element) => {
        const rect = element.getBoundingClientRect();
        const parent = element.closest("td, [role='rowheader'], [role='gridcell']")!;
        const bounds = parent.getBoundingClientRect();
        const style = getComputedStyle(element);
        const range = document.createRange(); range.selectNodeContents(element);
        return { text: element.textContent, overflow: element.scrollWidth > element.clientWidth + 1,
          ellipsis: style.textOverflow === "ellipsis", contained: rect.left >= bounds.left && rect.right <= bounds.right + 1 && rect.left >= 0 && rect.right <= window.innerWidth,
          glyphsContained: Array.from(range.getClientRects()).every((r) => r.left >= bounds.left && r.right <= bounds.right + 1 && r.top >= bounds.top && r.bottom <= bounds.bottom + 1) };
      });
      expect(layout).toEqual({ text: number, overflow: false, ellipsis: false, contained: true, glyphsContained: true });
    }
    await page.screenshot({ path: testInfo.outputPath(`oa-full-numbers-${width}-${zoom}.png`), fullPage: true });
  }
  expect(previewRequests).toBe(1);
  await page.evaluate(() => { document.documentElement.style.zoom = "1"; });
  await page.setViewportSize({ width: 1600, height: 1000 });
  const filter = page.getByRole("button", { name: /筛选流水关联状态/ });
  for (const label of ["已关联流水", "未关联流水", "全部"]) {
    await filter.click();
    await expect(page.getByRole("option", { name: "全部 2 张", exact: true })).toBeVisible();
    await expect(page.getByRole("option", { name: "已关联流水 1 张", exact: true })).toBeVisible();
    await expect(page.getByRole("option", { name: "未关联流水 1 张", exact: true })).toBeVisible();
    await page.getByRole("option", { name: new RegExp(`^${label} `) }).click();
    await expect(grid.getByRole("checkbox")).toHaveCount(label === "全部" ? 2 : 1);
  }
  expect(previewRequests).toBe(4);
});
