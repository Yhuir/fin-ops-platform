import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
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
  ]);
  return mutationCalls(calls).filter((entry) => !readLikePosts.has(entry));
}

function waitForInputInvoiceUsageRows(page: Page) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/rows");
  });
}

function decodedFilters(url: URL) {
  const raw = url.searchParams.get("filters");
  if (!raw) {
    return [];
  }
  return JSON.parse(decodeURIComponent(raw)) as Array<{ field?: string; operator?: string; values?: string[] }>;
}

test.describe("input invoice usage browser flow", () => {
  test("recovers rows after a transient load failure when refreshed", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 503/],
    });
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRowsFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByText("进项发票使用情况加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("进项发票使用情况加载失败，请点击刷新重试。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("当前条件下没有进项发票使用记录。")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeDisabled();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      const responsePromise = waitForInputInvoiceUsageRows(page);
      await page.getByRole("button", { name: "刷新" }).click();
      recovered = (await responsePromise).status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("进项发票使用情况加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByText("进项发票使用情况加载失败，请点击刷新重试。")).toHaveCount(0);
    const recoveredRow = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(recoveredRow).toBeVisible();
    await expect(recoveredRow.getByText("待处理")).toBeVisible();
    await expect(page.getByText("1-1 / 1")).toBeVisible();
    await expect(page.getByRole("button", { name: "筛选内容导出" })).toBeEnabled();
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(3);
    expect(browserErrors).toEqual([]);
  });

  test("keeps filter, sort, and page-size controls synchronized with fresh rows", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageFilterSortRows: true,
      sessionMode: "full_access",
    });

    const initialRowsPromise = waitForInputInvoiceUsageRows(page);
    await page.goto("/input-invoice-usage");
    const initialRowsResponse = await initialRowsPromise;
    const initialRowsUrl = new URL(initialRowsResponse.url());
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    await expect(page.getByText("1-20 / 23")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0001")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0099")).toHaveCount(0);
    expect(initialRowsUrl.searchParams.get("page")).toBe("1");
    expect(initialRowsUrl.searchParams.get("page_size")).toBe("20");
    expect(initialRowsUrl.searchParams.has("filters")).toBe(false);
    expect(initialRowsUrl.searchParams.has("sort_field")).toBe(false);

    await page.getByRole("button", { name: "筛选 销方名称" }).click();
    const sellerMenu = page.getByRole("menu", { name: "销方名称筛选与排序" });
    await expect(sellerMenu.getByRole("menuitemcheckbox", { name: /页外供应商 1/ })).toBeVisible();

    const filteredRowsPromise = waitForInputInvoiceUsageRows(page);
    await sellerMenu.getByRole("menuitemcheckbox", { name: /页外供应商 1/ }).click();
    const filteredRowsResponse = await filteredRowsPromise;
    const filteredRowsUrl = new URL(filteredRowsResponse.url());
    const filters = decodedFilters(filteredRowsUrl);
    await expect(page.getByText("1-1 / 1")).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0099")).toBeVisible();
    await expect(page.getByText("页外供应商").first()).toBeVisible();
    await expect(page.getByText("SD-INV-E2E-0001")).toHaveCount(0);
    expect(filteredRowsUrl.searchParams.get("page")).toBe("1");
    expect(filteredRowsUrl.searchParams.get("page_size")).toBe("20");
    expect(filters).toEqual([
      { field: "seller_name", operator: "in", values: ["页外供应商"] },
    ]);

    const clearedRowsPromise = waitForInputInvoiceUsageRows(page);
    await sellerMenu.getByRole("menuitem", { name: "清空" }).click();
    const clearedRowsResponse = await clearedRowsPromise;
    const clearedRowsUrl = new URL(clearedRowsResponse.url());
    await expect(page.getByText("1-20 / 23")).toBeVisible();
    expect(clearedRowsUrl.searchParams.has("filters")).toBe(false);
    await page.keyboard.press("Escape");

    const sortedRowsPromise = waitForInputInvoiceUsageRows(page);
    await page.getByRole("button", { name: "按开票日期排序" }).click();
    const sortedRowsResponse = await sortedRowsPromise;
    const sortedRowsUrl = new URL(sortedRowsResponse.url());
    await expect(page.locator("tbody tr").first()).toContainText("SD-INV-E2E-0099");
    expect(sortedRowsUrl.searchParams.get("sort_field")).toBe("invoice_date");
    expect(sortedRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    const pageSizeRowsPromise = waitForInputInvoiceUsageRows(page);
    await page.getByLabel("每页行数").selectOption("50");
    const pageSizeRowsResponse = await pageSizeRowsPromise;
    const pageSizeRowsUrl = new URL(pageSizeRowsResponse.url());
    await expect(page.getByText("1-23 / 23")).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(23);
    expect(pageSizeRowsUrl.searchParams.get("page")).toBe("1");
    expect(pageSizeRowsUrl.searchParams.get("page_size")).toBe("50");
    expect(pageSizeRowsUrl.searchParams.get("sort_field")).toBe("invoice_date");
    expect(pageSizeRowsUrl.searchParams.get("sort_direction")).toBe("asc");

    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(4);
    expect(api.count("GET /api/input-invoice-usage/filter-options")).toBeGreaterThanOrEqual(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("keeps read-export users on read-only workflows without durable writes", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    await expect(page.getByRole("row", { name: /SD-INV-E2E-0001/ })).toBeVisible();

    const exportPreviewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export-preview");
    });
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    expect((await exportPreviewResponsePromise).status()).toBe(200);
    const exportDrawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(exportDrawer).toBeVisible();
    await expect(exportDrawer.getByRole("button", { name: "下载导出" })).toBeEnabled();
    await exportDrawer.getByRole("button", { name: "关闭进项发票使用情况导出" }).click();

    const rulesResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/payment-status-rules");
    });
    await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
    expect((await rulesResponsePromise).status()).toBe(200);
    const rulesDrawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
    await expect(rulesDrawer).toBeVisible();
    await expect(rulesDrawer.getByText("只读")).toBeVisible();
    await expect(rulesDrawer.getByText("待付款（自动识别有oa无流水）")).toBeVisible();
    await expect(rulesDrawer.getByRole("button", { name: "保存规则" })).toHaveCount(0);
    await expect(rulesDrawer.getByRole("button", { name: "还原" })).toHaveCount(0);
    await expect(rulesDrawer.getByRole("textbox")).toHaveCount(0);
    await rulesDrawer.getByRole("button", { name: "关闭支付状态规则抽屉" }).click();

    const previewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "POST" && url.pathname.endsWith("/api/input-invoice-usage/oa-reverse/preview");
    });
    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const previewResponse = await previewResponsePromise;
    expect(previewResponse.status()).toBe(200);
    const previewPayload = await previewResponse.json() as { can_create_draft?: boolean; canCreateDraft?: boolean };
    expect(previewPayload.can_create_draft ?? previewPayload.canCreateDraft).toBe(false);

    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(workflow).toBeVisible();
    await expect(workflow.getByText("当前账户或预览状态暂不允许创建 OA 草稿。")).toBeVisible();
    await expect(workflow.getByRole("table", { name: "反提 OA 候选发票清单" })).toBeVisible();
    await expect(workflow.getByRole("button", { name: "创建 OA 草稿" })).toBeDisabled();

    expect(api.count("GET /api/input-invoice-usage/export-preview")).toBe(1);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(0);
    expect(api.count("GET /api/input-invoice-usage/payment-status-rules")).toBe(1);
    expect(api.count("PUT /api/input-invoice-usage/payment-status-rules")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/preview")).toBe(1);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/batches")).toBe(0);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status")).toBe(0);
    expect(durableWriteCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("refreshes current rows after full-access payment status rules are saved", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsagePaymentRulesSaveFlow: true,
      sessionMode: "full_access",
    });

    const initialRowsPromise = waitForInputInvoiceUsageRows(page);
    await page.goto("/input-invoice-usage");
    expect((await initialRowsPromise).status()).toBe(200);
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toContainText("待付款（自动识别有oa无流水）");

    await page.getByRole("button", { name: "发票与支付状态规则设置" }).click();
    const rulesDrawer = page.getByRole("dialog", { name: "发票与支付状态规则设置" });
    await expect(rulesDrawer).toBeVisible();
    await expect(rulesDrawer.getByText("版本 1")).toBeVisible();
    await expect(rulesDrawer.getByRole("button", { name: "保存规则" })).toBeDisabled();

    await rulesDrawer.getByRole("textbox", { name: "支付状态" }).first().fill("待付款（规则保存后刷新）");
    await expect(rulesDrawer.getByRole("button", { name: "保存规则" })).toBeEnabled();

    const saveResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "PUT" && url.pathname.endsWith("/api/input-invoice-usage/payment-status-rules");
    });
    const refreshedRowsPromise = waitForInputInvoiceUsageRows(page);
    await rulesDrawer.getByRole("button", { name: "保存规则" }).click();
    const saveResponse = await saveResponsePromise;
    expect(saveResponse.status()).toBe(200);
    expect((await refreshedRowsPromise).status()).toBe(200);

    const saveBody = api.lastBody("PUT /api/input-invoice-usage/payment-status-rules") as {
      expectedVersion?: unknown;
      idempotencyKey?: unknown;
      rules?: Array<{ id?: string; label?: string }>;
    };
    expect(saveBody.expectedVersion).toBe(1);
    expect(String(saveBody.idempotencyKey ?? "")).toMatch(/^input-invoice-usage-payment-rules-save:/);
    expect(saveBody.rules?.find((rule) => rule.id === "waiting_payment")?.label).toBe("待付款（规则保存后刷新）");

    await expect(rulesDrawer.getByText("规则已保存，读模型会按后端返回的刷新状态更新。")).toBeVisible();
    await expect(rulesDrawer.getByText("版本 2")).toBeVisible();
    await expect(row).toContainText("待付款（规则保存后刷新）");
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(2);
    expect(api.count("PUT /api/input-invoice-usage/payment-status-rules")).toBe(1);
    expect(durableWriteCalls(api.calls)).toEqual(["PUT /api/input-invoice-usage/payment-status-rules"]);
    expect(browserErrors).toEqual([]);
  });

  test("shows read model refreshing diagnostics instead of stale rows or a true empty state", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageReadModelStatus: "stale",
      sessionMode: "full_access",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "进项发票使用情况" })).toBeVisible();
    await expect(page.getByText("进项发票使用情况数据正在刷新")).toBeVisible();
    await expect(page.getByText("进项发票使用情况读模型正在刷新，完成后页面会自动重新加载。")).toBeVisible();
    await expect(page.getByText("当前条件下暂无记录。")).toHaveCount(0);
    await expect(page.getByText("当前条件下没有进项发票使用记录。")).toHaveCount(0);
    await expect(page.getByText("SD-INV-E2E-0001")).toHaveCount(0);
    await expect(page.getByText("input_invoice_usage_stale")).toHaveCount(0);
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toHaveCount(0);

    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(1);
    expect(api.count("GET /api/input-invoice-usage/filter-options")).toBeGreaterThanOrEqual(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("shows relation detail refreshing diagnostics instead of loading forever", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRelationDetailReadModelStatus: "stale",
      sessionMode: "full_access",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("合计 188.00")).toBeVisible();

    const detailResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")
        && url.searchParams.get("kind") === "oa";
    });
    await row.getByRole("button", { name: "查看陈秀云关联OA 2 条" }).click();
    const detailResponse = await detailResponsePromise;
    expect(detailResponse.status()).toBe(202);

    const detailDrawer = page.getByRole("dialog", { name: "OA关联明细" });
    await expect(detailDrawer).toBeVisible();
    await expect(detailDrawer.getByText("详情暂不可用")).toBeVisible();
    await expect(detailDrawer.getByText("进项发票使用情况关联明细正在刷新，完成后请重新打开详情。")).toBeVisible();
    await expect(detailDrawer.getByText("正在加载完整详情")).toHaveCount(0);
    await expect(detailDrawer.getByText("刘际涛 100.00")).toHaveCount(0);
    await expect(detailDrawer.getByText("input_invoice_usage_relation_detail_stale")).toHaveCount(0);

    expect(api.count("GET /api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")).toBe(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("opens fresh +N relation details from the row read model without mutations", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageRelationDetailReadModelStatus: "fresh",
      sessionMode: "full_access",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("合计 188.00")).toBeVisible();

    const detailResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")
        && url.searchParams.get("kind") === "oa";
    });
    await row.getByRole("button", { name: "查看陈秀云关联OA 2 条" }).click();
    const detailResponse = await detailResponsePromise;
    expect(detailResponse.status()).toBe(200);

    const detailDrawer = page.getByRole("dialog", { name: "OA关联明细" });
    await expect(detailDrawer).toBeVisible();
    await expect(detailDrawer.getByText("关联概况")).toBeVisible();
    await expect(detailDrawer.getByText("关系数量")).toBeVisible();
    await expect(detailDrawer.getByText("2", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("是否多条")).toBeVisible();
    await expect(detailDrawer.getByText("是", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("关联摘要")).toBeVisible();
    await expect(detailDrawer.getByText("OA 1")).toBeVisible();
    await expect(detailDrawer.getByText("陈秀云 88.00")).toBeVisible();
    await expect(detailDrawer.getByText("OA 2")).toBeVisible();
    await expect(detailDrawer.getByText("刘际涛 100.00")).toBeVisible();
    await expect(detailDrawer.getByText("详情暂不可用")).toHaveCount(0);
    await expect(detailDrawer.getByText("正在加载完整详情")).toHaveCount(0);
    await expect(detailDrawer.getByText("input_invoice_usage_relation_detail")).toHaveCount(0);

    expect(api.count("GET /api/input-invoice-usage/rows/input-usage-row-e2e-001/relation-details")).toBe(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("downloads current filtered rows without paginating the export", async ({ page }, testInfo) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "read_export_only" });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();
    await page.getByLabel("进项发票使用情况搜索").fill("浏览器进项供应商");
    await page.getByRole("button", { name: "查询" }).click();
    await expect(page.getByRole("row", { name: /SD-INV-E2E-0001/ })).toBeVisible();

    const previewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export-preview");
    });
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const previewResponse = await previewResponsePromise;
    const previewUrl = new URL(previewResponse.url());
    expect(previewResponse.status()).toBe(200);
    expect(previewUrl.searchParams.get("keyword")).toBe("浏览器进项供应商");
    expect(previewUrl.searchParams.has("page")).toBe(false);
    expect(previewUrl.searchParams.has("page_size")).toBe(false);

    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("table", { name: "进项发票使用情况导出样例" })).toBeVisible();
    await expect(drawer.getByText("SD-INV-E2E-0001")).toBeVisible();
    await expect(drawer.getByRole("cell", { name: "浏览器进项供应商" }).first()).toBeVisible();
    await expect(drawer.getByText("OA申请人")).toBeVisible();
    await expect(drawer.getByText("关系案例")).toBeVisible();
    await expect(drawer.getByText("CASE-INPUT-E2E-001")).toBeVisible();

    const exportResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export");
    });
    const downloadPromise = page.waitForEvent("download");
    await drawer.getByRole("button", { name: "下载导出" }).click();
    const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);
    const exportUrl = new URL(exportResponse.url());
    expect(exportResponse.status()).toBe(200);
    expect(exportUrl.searchParams.get("keyword")).toBe("浏览器进项供应商");
    expect(exportUrl.searchParams.has("page")).toBe(false);
    expect(exportUrl.searchParams.has("page_size")).toBe(false);
    expect(download.suggestedFilename()).toBe("input-invoice-usage.xlsx");

    const downloadPath = testInfo.outputPath("input-invoice-usage.xlsx");
    await download.saveAs(downloadPath);
    const downloadedText = await readFile(downloadPath, "utf8");
    expect(downloadedText).toContain("SD-INV-E2E-0001");
    expect(downloadedText).toContain("浏览器进项供应商");
    expect(downloadedText).toContain("陈秀云");
    expect(downloadedText).toContain("CASE-INPUT-E2E-001");
    expect(downloadedText).toContain("keyword=浏览器进项供应商");
    expect(downloadedText).toContain("page=");
    expect(downloadedText).toContain("page_size=");
    expect(api.count("GET /api/input-invoice-usage/export-preview")).toBe(1);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(1);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("shows row-limit feedback instead of downloading an oversized export", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page, {
      allowedConsoleErrors: [/Failed to load resource: the server responded with a status of 400 \(Bad Request\)/],
    });
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageExportRowLimitError: true,
      sessionMode: "read_export_only",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("alert")).toContainText("进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。");
    await expect(drawer.getByRole("button", { name: "下载导出" })).toBeDisabled();

    expect(api.count("GET /api/input-invoice-usage/export-preview")).toBe(1);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(0);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("keeps export download disabled while the export read model refreshes", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, {
      inputInvoiceUsageExportReadModelStatus: "stale",
      sessionMode: "read_export_only",
    });

    await page.goto("/input-invoice-usage");
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();

    const previewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/input-invoice-usage/export-preview");
    });
    await page.getByRole("button", { name: "筛选内容导出" }).click();
    const previewResponse = await previewResponsePromise;
    expect(previewResponse.status()).toBe(202);

    const drawer = page.getByRole("dialog", { name: "筛选内容导出" });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByText("导出数据准备中，请稍后再试。")).toBeVisible();
    await expect(drawer.getByRole("button", { name: "下载导出" })).toBeDisabled();
    await expect(drawer.getByText("进项发票使用情况数据正在刷新，请稍后重试导出。")).toHaveCount(0);

    expect(api.count("GET /api/input-invoice-usage/export-preview")).toBe(1);
    expect(api.count("GET /api/input-invoice-usage/export")).toBe(0);
    expect(mutationCalls(api.calls)).toEqual([]);
    expect(browserErrors).toEqual([]);
  });

  test("creates an OA reverse draft from a selected invoice subset and records submitted history", async ({ page }) => {
    const browserErrors = startStrictBrowserErrorCapture(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    const initialRowsPromise = waitForInputInvoiceUsageRows(page);
    await page.goto("/input-invoice-usage");
    expect((await initialRowsPromise).status()).toBe(200);
    await expect(page.getByTestId("input-invoice-usage-page")).toBeVisible();
    await expect(page.getByRole("heading", { name: "进项发票使用情况" })).toBeVisible();
    await expect(page.getByRole("table", { name: "进项发票使用情况表" })).toBeVisible();

    const row = page.getByRole("row", { name: /SD-INV-E2E-0001/ });
    await expect(row).toBeVisible();
    await expect(row.getByText("浏览器进项供应商").first()).toBeVisible();
    await expect(row.getByText("待处理")).toBeVisible();

    await page.getByRole("button", { name: "以发票反提 OA" }).click();
    const workflow = page.getByLabel("以发票反提 OA 工作流", { exact: true });
    await expect(workflow).toBeVisible();
    await expect(page.getByRole("tab", { name: "待处理" })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("table", { name: "反提 OA 候选发票清单" })).toBeVisible();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-001")).toBeChecked();
    await expect(workflow.getByLabel("选择候选发票 SD-INV-E2E-002")).toBeChecked();

    await workflow.getByLabel("选择候选发票 SD-INV-E2E-002").uncheck();
    await expect(workflow.getByText("已选 1 张")).toBeVisible();

    const subsetPreviewRequest = page.waitForRequest((request) =>
      request.url().includes("/api/input-invoice-usage/oa-reverse/preview")
        && request.method() === "POST"
        && (request.postData() ?? "").includes("input-oa-invoice-e2e-001"),
    );
    const subsetPreviewResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/preview")
        && response.request().method() === "POST",
    );
    const draftResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/oa-draft")
        && response.request().method() === "POST",
    );
    const draftRowsRefresh = waitForInputInvoiceUsageRows(page);
    await workflow.getByRole("button", { name: "创建 OA 草稿" }).click();

    const requestBody = JSON.parse((await subsetPreviewRequest).postData() ?? "{}") as { invoiceIds?: string[] };
    expect(requestBody.invoiceIds).toEqual(["input-oa-invoice-e2e-001"]);
    expect((await subsetPreviewResponse).status()).toBe(200);
    expect((await draftResponse).status()).toBe(200);
    expect((await draftRowsRefresh).status()).toBe(200);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/preview")).toBeGreaterThanOrEqual(2);
    expect(api.count("POST /api/input-invoice-usage/oa-reverse/oa-draft")).toBe(1);

    const confirmDialog = page.getByRole("dialog", { name: "OA 草稿提交确认" });
    await expect(confirmDialog).toBeVisible();
    await expect(confirmDialog.getByRole("link", { name: "打开 OA 草稿" })).toHaveAttribute(
      "href",
      "https://oa.example.test/draft/input-e2e",
    );
    await expectNoUnexpectedSuccessUiErrors(page);

    const manualStatusResponse = page.waitForResponse((response) =>
      response.url().includes("/api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status")
        && response.request().method() === "POST",
    );
    const manualStatusRowsRefresh = waitForInputInvoiceUsageRows(page);
    await confirmDialog.getByRole("button", { name: /我已在OA系统提交该草稿\s+OA正在进行中/ }).click();
    expect((await manualStatusResponse).status()).toBe(200);
    expect((await manualStatusRowsRefresh).status()).toBe(200);

    await expect(workflow.getByText("已进入已提交历史。")).toBeVisible();
    await expect(page.getByRole("tab", { name: "已提交" })).toHaveAttribute("aria-selected", "true");
    await expect(workflow.getByRole("table", { name: "陈秀云已提交发票" })).toBeVisible();
    await expect(workflow.getByText("SD-INV-E2E-001")).toBeVisible();
    await expect(workflow.getByText("浏览器进项供应商一")).toBeVisible();
    await expect(workflow.getByText("input-oa-reverse-batch-e2e-001")).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
    expect(api.count("GET /api/input-invoice-usage/rows")).toBeGreaterThanOrEqual(3);
    expect(api.count("GET /api/input-invoice-usage/oa-reverse/submitted-history")).toBeGreaterThanOrEqual(1);
    expect(browserErrors).toEqual([]);
  });
});
