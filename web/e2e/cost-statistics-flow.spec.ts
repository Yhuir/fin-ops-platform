import { readFile } from "node:fs/promises";
import { expect, test, type Locator, type Page, type TestInfo } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { createOperationLatencyRecorder, type OperationLatencyRecorder } from "./fixtures/operationLatency";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

type CostExplorerBrowserPayload = {
  summary?: {
    row_count?: number;
    transaction_count?: number;
  };
};

const costTransactionLabels = {
  expense: "查看银行流水 浏览器设备供应商 2026-03-10 21:27:55 10000.00",
  income: "查看银行流水 浏览器回款客户 2026-03-18 10:08:00 8888.00",
  office: "查看银行流水 浏览器办公室出租方 2026-04-02 09:15:08 4800.00",
  travel: "查看银行流水 浏览器航空 2026-03-18 17:02:09 860.00",
  oaExpense: "查看OA 成本归集 云南溯源科技 2026-03-10 21:27:55 10000.00",
} as const;

function requestPath(requestUrl: string) {
  return new URL(requestUrl).pathname;
}

function createCostStatisticsLatencyRecorder(page: Page, testInfo: TestInfo) {
  return createOperationLatencyRecorder(page, testInfo, {
    route: "/cost-statistics",
    pageKey: "cost-statistics",
    module: "cost-statistics",
  });
}

function getResponse(pathnameSuffix: string) {
  return (response: { url(): string; request(): { method(): string } }) =>
    response.request().method() === "GET" && requestPath(response.url()).endsWith(pathnameSuffix);
}

function waitForCostStatisticsExplorer(page: Page, month = "2026-03", projectScope = "active") {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname.endsWith("/api/cost-statistics/explorer")
      && url.searchParams.get("scope") === month
      && url.searchParams.get("project_scope") === projectScope;
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const now = Date.now();
    sessionStorage.setItem("finops:pageSession:v1:e2e-user:cost-statistics:explorerState", JSON.stringify({
      version: 3,
      updatedAt: now,
      expiresAt: now + 60 * 60 * 1000,
      value: {
        viewMode: "time",
        timeScopeMode: "month",
        timeScopeYear: "2026",
        timeScopeMonth: "2026-03",
        projectScopeMode: "all",
        projectScopeYear: "2026",
        projectScopeMonth: "2026-03",
        bankScopeMode: "all",
        bankScopeYear: "2026",
        bankScopeMonth: "2026-03",
        expenseTypeScopeMode: "month",
        expenseTypeScopeYear: "2026",
        expenseTypeScopeMonth: "2026-03",
        bankTagScopeMode: "month",
        bankTagScopeYear: "2026",
        bankTagScopeMonth: "2026-03",
      },
    }));
  });
});

function collectBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console error: ${message.text()}`);
    }
  });
  page.on("dialog", (dialog) => {
    errors.push(`dialog: ${dialog.type()} ${dialog.message()}`);
  });
  page.on("pageerror", (error) => errors.push(`page error: ${error.message}`));
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    if (failure?.errorText === "net::ERR_ABORTED") {
      return;
    }
    errors.push(`request failed: ${request.method()} ${request.url()} ${failure?.errorText ?? ""}`.trim());
  });
  return errors;
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

async function expectInViewport(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  await locator.scrollIntoViewIfNeeded();
  const result = await locator.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      height: rect.height,
      inViewport: rect.width > 0
        && rect.height > 0
        && rect.bottom > 0
        && rect.right > 0
        && rect.top < window.innerHeight
        && rect.left < window.innerWidth,
      width: rect.width,
    };
  });
  expect(result.inViewport, `${label} should be inside the viewport: ${JSON.stringify(result)}`).toBe(true);
}

async function expectVerticalScroll(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  const result = await locator.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return {
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
      scrollTop: element.scrollTop,
    };
  });
  expect(result.scrollHeight, `${label} should overflow vertically: ${JSON.stringify(result)}`).toBeGreaterThan(result.clientHeight);
  expect(result.scrollTop, `${label} should scroll vertically: ${JSON.stringify(result)}`).toBeGreaterThan(0);
}

test.describe("cost statistics browser flow", () => {
  test("saves tag rules without a write-time barrier and reloads the visible cost view", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
    });
    const recordLatency = createCostStatisticsLatencyRecorder(page, testInfo);

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();

    const drawer = page.getByRole("dialog", { name: "成本统计标签规则" });
    await recordLatency({
      operationId: "cost-statistics.open-tag-rules-drawer",
      visibleLabel: "成本统计标签规则",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "成本统计标签规则" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeVisible());
      await mark("finalSettledLatencyMs", expect(drawer.getByRole("button", { name: "保存" })).toBeEnabled());
    });

    const saveResponsePromise = page.waitForResponse((response) =>
      response.request().method() === "PUT"
      && requestPath(response.url()).endsWith("/api/cost-statistics/tag-rules"));
    const explorerResponsePromise = waitForCostStatisticsExplorer(page);
    await recordLatency({
      operationId: "cost-statistics.save-tag-rules",
      visibleLabel: "保存成本统计标签规则",
      actionType: "click",
    }, async (mark) => {
      await drawer.getByRole("button", { name: "保存" }).click();
      await mark("apiLatencyMs", saveResponsePromise);
      await mark("firstVisibleResponseLatencyMs", expect(drawer).toBeHidden());
      await mark("finalSettledLatencyMs", explorerResponsePromise);
    });

    expect(api.count("PUT /api/cost-statistics/tag-rules")).toBe(1);
    expect(api.count("GET /api/operation-barrier/status")).toBe(0);
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("recovers explorer after a transient load failure when refreshed", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      costStatisticsExplorerFailuresBeforeSuccess: 2,
      sessionMode: "full_access",
    });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.locator(".cost-page-header").getByRole("radiogroup", { name: "成本统计视图切换" })).toBeVisible();
    await expect(page.getByText("成本统计数据加载暂时失败，请刷新后重试。")).toBeVisible();
    await expect(page.getByText("当前时间范围没有可用于成本统计的支出流水。")).toHaveCount(0);
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "导出中心" })).toBeDisabled();
    const interactionOverlay = page.getByTestId("cost-statistics-interaction-overlay");
    await expect(interactionOverlay).toBeVisible();
    await expect(page.locator(".cost-analysis-toolbar")).toHaveAttribute("inert", "");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const overlayVisual = await interactionOverlay.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        animationName: style.animationName,
        backdropFilter: style.backdropFilter,
        backgroundColor: style.backgroundColor,
        pointerEvents: style.pointerEvents,
        touchAction: style.touchAction,
      };
    });
    expect(overlayVisual.backgroundColor).toMatch(/0\.2|20%/);
    expect(overlayVisual).toMatchObject({
      animationName: "none",
      backdropFilter: "none",
      pointerEvents: "auto",
      touchAction: "none",
    });
    await expect(page.locator(".cost-lock-status")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(page.locator(".cost-lock-target.is-locked").first()).toHaveCSS("opacity", "0.62");
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThanOrEqual(1);

    let recovered = false;
    for (let attempt = 0; attempt < 3 && !recovered; attempt += 1) {
      const responsePromise = waitForCostStatisticsExplorer(page);
      await page.getByRole("button", { name: "重新检查" }).click();
      recovered = (await responsePromise).status() === 200;
    }
    expect(recovered).toBe(true);

    await expect(page.getByText("成本统计数据加载暂时失败，请刷新后重试。")).toHaveCount(0);
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expect(page.getByRole("button", { name: costTransactionLabels.expense })).toBeVisible();
    await expect(page.getByRole("gridcell", { name: "PLC 模块采购", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "导出中心" })).toBeEnabled();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThanOrEqual(3);
  });

  test("downloads the current time-view cost rows with request filters and cost fields", async ({ page }, testInfo) => {
    const browserErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") {
        browserErrors.push(`console error: ${message.text()}`);
      }
    });
    page.on("pageerror", (error) => browserErrors.push(`page error: ${error.message}`));
    page.on("requestfailed", (request) => {
      const failure = request.failure();
      if (failure?.errorText === "net::ERR_ABORTED") {
        return;
      }
      browserErrors.push(`request failed: ${request.method()} ${request.url()} ${failure?.errorText ?? ""}`.trim());
    });
    const api = await installDeterministicApiMocks(page, {
      costStatisticsExportDownloadSuccess: true,
      sessionMode: "read_export_only",
    });
    const recordLatency = createCostStatisticsLatencyRecorder(page, testInfo);

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expect(page.getByRole("button", { name: "导出中心" })).toBeEnabled();

    const exportDialog = page.getByRole("dialog", { name: "导出中心" });
    await recordLatency({
      operationId: "cost-statistics.open-export-center",
      visibleLabel: "导出中心",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "导出中心" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(exportDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(exportDialog.getByRole("button", { name: "导出", exact: true })).toBeEnabled());
    });
    await expect(exportDialog.getByRole("button", { name: "导出", exact: true })).toBeEnabled();

    const previewResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/cost-statistics/export-preview");
    });
    await recordLatency({
      operationId: "cost-statistics.preview-time-export",
      visibleLabel: "仅预览",
      actionType: "click",
    }, async (mark) => {
      await exportDialog.getByRole("button", { name: "仅预览" }).click();
      await mark("apiLatencyMs", previewResponsePromise);
      await mark(
        "firstVisibleResponseLatencyMs",
        expect(exportDialog.getByRole("grid", { name: "导出预览表" })).toContainText("云南溯源科技"),
      );
      await mark(
        "finalSettledLatencyMs",
        expect(exportDialog.getByRole("grid", { name: "导出预览表" })).toContainText("设备货款及材料费"),
      );
    });
    const previewResponse = await previewResponsePromise;
    const previewUrl = new URL(previewResponse.url());
    expect(previewResponse.status()).toBe(200);
    expect(previewUrl.searchParams.get("view")).toBe("time");
    expect(previewUrl.searchParams.get("month")).toBe("2026-03");
    expect(previewUrl.searchParams.get("project_scope")).toBe("active");
    expect(previewUrl.searchParams.has("page")).toBe(false);
    expect(previewUrl.searchParams.has("page_size")).toBe(false);
    const exportResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET" && url.pathname.endsWith("/api/cost-statistics/export");
    });
    const downloadPromise = page.waitForEvent("download");
    await recordLatency({
      operationId: "cost-statistics.export-time-view",
      visibleLabel: "导出",
      actionType: "click",
    }, async (mark) => {
      await exportDialog.getByRole("button", { name: "导出", exact: true }).click();
      await mark("apiLatencyMs", exportResponsePromise);
      await mark("firstVisibleResponseLatencyMs", expect(exportDialog.getByText("已导出 成本统计_全部期间_按时间统计.xlsx")).toBeVisible());
      await mark("finalSettledLatencyMs", downloadPromise.then(() => undefined));
    });
    const [exportResponse, download] = await Promise.all([exportResponsePromise, downloadPromise]);

    const exportUrl = new URL(exportResponse.url());
    expect(exportResponse.status()).toBe(200);
    expect(exportUrl.searchParams.get("view")).toBe("time");
    expect(exportUrl.searchParams.get("month")).toBe("2026-03");
    expect(exportUrl.searchParams.get("project_scope")).toBe("active");
    expect(exportUrl.searchParams.has("page")).toBe(false);
    expect(exportUrl.searchParams.has("page_size")).toBe(false);
    expect(download.suggestedFilename()).toBe("成本统计_全部期间_按时间统计.xlsx");

    const downloadPath = testInfo.outputPath(download.suggestedFilename());
    await download.saveAs(downloadPath);
    const downloadedText = await readFile(downloadPath, "utf8");
    expect(downloadedText).toContain("时间,项目名称,费用类型,金额,费用内容,资金方向,对方户名,支付账户");
    expect(downloadedText).toContain("cost-txn-e2e-001");
    expect(downloadedText).toContain("cost-income-e2e-001");
    expect(downloadedText).toContain("浏览器客户回款");
    expect(downloadedText).toContain("云南溯源科技");
    expect(downloadedText).toContain("设备货款及材料费");
    expect(downloadedText).toContain("PLC 模块采购");
    expect(downloadedText).toContain("浏览器设备供应商");
    expect(downloadedText).toContain("view=time");
    expect(downloadedText).toContain("month=2026-03");
    expect(downloadedText).toContain("project_scope=active");
    expect(downloadedText).toContain("page=");
    expect(downloadedText).toContain("page_size=");
    expect(api.count("GET /api/cost-statistics/export-preview")).toBe(1);
    expect(api.count("GET /api/cost-statistics/export")).toBe(1);
    expect(browserErrors).toEqual([]);
  });

  test("keeps redesigned view buttons and range controls usable", async ({ page }, testInfo) => {
    const browserErrors = collectBrowserErrors(page);
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createCostStatisticsLatencyRecorder(page, testInfo);

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByText(/以已配对的支出流水为基准/)).toHaveCount(0);
    await expect(page.locator(".cost-page .stat-card")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /项目范围：/ })).toHaveCount(0);
    await expect(page.getByLabel("时间统计方向金额")).toContainText("支出金额");
    await expect(page.getByLabel("收入金额 8888.00")).toBeVisible();
    await expect(page.locator(".cost-direction-amount--income").first()).toHaveCSS("color", /rgb\(/);
    await expect(page.getByRole("button", { name: costTransactionLabels.income })).toBeVisible();
    await page.getByRole("button", { name: costTransactionLabels.income }).click();
    const incomeDetailDialog = page.getByRole("dialog", { name: "银行流水详情" });
    await expect(incomeDetailDialog).toContainText("收入");
    await expect(incomeDetailDialog).toContainText("8888.00");
    await incomeDetailDialog.getByRole("button", { name: "关闭银行流水详情" }).click();

    const refreshResponse = waitForCostStatisticsExplorer(page, "2026-03", "active");
    await recordLatency({
      operationId: "cost-statistics.refresh-time-view",
      visibleLabel: "刷新成本统计",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "刷新成本统计" }).click();
      await mark("apiLatencyMs", refreshResponse);
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: costTransactionLabels.expense })).toBeVisible());
    });
    expect((await refreshResponse).status()).toBe(200);

    const aprilResponse = waitForCostStatisticsExplorer(page, "2026-04", "active");
    const timePicker = page.getByRole("group", { name: "时间统计时间范围" });
    await recordLatency({
      operationId: "cost-statistics.set-time-view-april",
      visibleLabel: "时间统计时间范围：2026年3月 -> 四月",
      actionType: "click",
    }, async (mark) => {
      await timePicker.getByRole("button", { name: "四月" }).click();
      await mark("apiLatencyMs", aprilResponse);
      await mark("firstVisibleResponseLatencyMs", expect(timePicker.getByRole("button", { name: "四月" })).toHaveAttribute("aria-pressed", "true"));
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: costTransactionLabels.office })).toBeVisible());
    });
    expect((await aprilResponse).status()).toBe(200);

    await recordLatency({
      operationId: "cost-statistics.switch-project-view",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按项目" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("group", { name: "项目统计时间范围" }).getByRole("button", { name: "全部" })).toHaveAttribute("aria-pressed", "true"));
    });
    const projectPicker = page.getByRole("dialog", { name: "项目统计时间范围选择器" });
    await recordLatency({
      operationId: "cost-statistics.set-project-view-year",
      visibleLabel: "项目统计时间范围：全部时间 -> 2026年",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "项目统计时间范围：年月" }).click();
      await expect(projectPicker).toBeVisible();
      await projectPicker.getByRole("button", { name: "2026年" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("button", { name: "项目统计时间范围：2026年" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "项目统计时间范围：2026年" })).toBeVisible());
    });

    await recordLatency({
      operationId: "cost-statistics.switch-bank-view",
      visibleLabel: "按银行",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按银行" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "按银行统计" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("group", { name: "银行统计时间范围" }).getByRole("button", { name: "全部" })).toHaveAttribute("aria-pressed", "true"));
    });
    const bankPicker = page.getByRole("dialog", { name: "银行统计时间范围选择器" });
    await recordLatency({
      operationId: "cost-statistics.set-bank-view-april",
      visibleLabel: "银行统计时间范围：全部时间 -> 四月",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "银行统计时间范围：年月" }).click();
      await expect(bankPicker).toBeVisible();
      await bankPicker.getByRole("button", { name: "按月" }).click();
      await bankPicker.getByRole("button", { name: "四月" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("button", { name: "银行统计时间范围：2026年4月" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: /平安银行 账户 8821/ })).toBeVisible());
    });
    await expect(page.getByRole("button", { name: /平安银行 账户 8821/ })).toBeVisible();

    await recordLatency({
      operationId: "cost-statistics.switch-expense-view",
      visibleLabel: "按OA费用类型",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按OA费用类型" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "按OA费用类型统计" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "OA费用类型统计时间范围：2026年3月" })).toBeVisible());
    });
    const expensePicker = page.getByRole("dialog", { name: "OA费用类型统计时间范围选择器" });
    await recordLatency({
      operationId: "cost-statistics.set-expense-view-year",
      visibleLabel: "OA费用类型统计时间范围：2026年3月 -> 2026年",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "OA费用类型统计时间范围：2026年3月" }).click();
      await expect(expensePicker).toBeVisible();
      await expensePicker.getByRole("button", { name: "按年" }).click();
      await expensePicker.getByRole("button", { name: "2026年" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("button", { name: "OA费用类型统计时间范围：2026年" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "OA费用类型统计时间范围：2026年" })).toBeVisible());
    });

    await recordLatency({
      operationId: "cost-statistics.switch-bank-tag-view",
      visibleLabel: "按标签",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按标签" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "按标签统计" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("button", { name: "流水标签统计时间范围：2026年3月" })).toBeVisible());
    });
    await expect(page.getByRole("button", { name: "流水标签统计时间范围：2026年3月" })).toBeVisible();
    await expect(page.getByLabel("标签统计方向金额")).toContainText("支出金额");
    await expect(page.getByLabel("收入金额 8888.00")).toBeVisible();
    await expect(page.getByRole("button", { name: /收入/ }).first()).toBeVisible();
    await recordLatency({
      operationId: "cost-statistics.drilldown-bank-tag",
      visibleLabel: "主标签 / 子标签",
      actionType: "click",
    }, async (mark) => {
      await page
        .locator(".cost-explorer-lane")
        .filter({ has: page.getByRole("heading", { name: "主标签" }) })
        .getByRole("button")
        .first()
        .click();
      await page
        .locator(".cost-explorer-lane")
        .filter({ has: page.getByRole("heading", { name: "子标签" }) })
        .getByRole("button")
        .first()
        .click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("grid", { name: "流水标签对应流水表" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByRole("grid", { name: "流水标签对应流水表" })).toBeVisible());
    });
    const bankTagTransactions = page.getByRole("grid", { name: "流水标签对应流水表" });
    await expect(bankTagTransactions.getByRole("columnheader", { name: "时间" })).toHaveCount(0);
    await expect(bankTagTransactions.locator(".cost-transaction-time-chip").first()).toBeVisible();
    const laneHeights = await page.locator(".cost-explorer-grid.bank-tag > .cost-explorer-lane").evaluateAll((lanes) => (
      lanes.map((lane) => Math.round(lane.getBoundingClientRect().height))
    ));
    expect(Math.max(...laneHeights) - Math.min(...laneHeights)).toBeLessThanOrEqual(1);
    const tableLaneBox = await page.locator(".cost-explorer-lane-table").boundingBox();
    const tableShellBox = await page.locator(".cost-explorer-lane-table .cost-table-shell").boundingBox();
    expect(tableLaneBox).not.toBeNull();
    expect(tableShellBox).not.toBeNull();
    expect(Math.abs(
      (tableLaneBox?.y ?? 0) + (tableLaneBox?.height ?? 0)
      - (tableShellBox?.y ?? 0) - (tableShellBox?.height ?? 0),
    )).toBeLessThanOrEqual(1);
    expect(browserErrors).toEqual([]);
  });

  test("drills into project cost rows and surfaces export row-limit feedback", async ({ page }, testInfo) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "full_access" });
    const recordLatency = createCostStatisticsLatencyRecorder(page, testInfo);

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();
    await expect(page.getByRole("button", { name: costTransactionLabels.travel })).toBeVisible();
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThanOrEqual(1);

    await recordLatency({
      operationId: "cost-statistics.open-project-view",
      visibleLabel: "按项目",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("radio", { name: "按项目" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(page.getByText("云南溯源科技")).toBeVisible());
    });
    await expect(page.getByText("云南溯源科技")).toBeVisible();
    await expect(page.getByText("昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /项目范围：/ })).toHaveCount(0);

    const projectRows = page.getByRole("grid", { name: "项目 OA 成本归集明细表" });
    await recordLatency({
      operationId: "cost-statistics.drilldown-project-expense",
      visibleLabel: "云南溯源科技 / 设备货款及材料费",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: /云南溯源科技/ }).first().click();
      await page.getByRole("button", { name: /设备货款及材料费/ }).click();
      await mark("firstVisibleResponseLatencyMs", expect(projectRows).toBeVisible());
      await mark("finalSettledLatencyMs", expect(projectRows.getByRole("button", { name: costTransactionLabels.oaExpense })).toBeVisible());
    });

    const detailRequest = page.waitForRequest((request) =>
      decodeURIComponent(requestPath(request.url())).endsWith("/api/cost-statistics/allocations/oa:cost-txn-e2e-001"),
    );
    const detailResponse = page.waitForResponse((response) => response.request().method() === "GET"
      && decodeURIComponent(requestPath(response.url())).endsWith("/api/cost-statistics/allocations/oa:cost-txn-e2e-001"));
    const detailDialog = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await recordLatency({
      operationId: "cost-statistics.open-project-transaction-detail",
      visibleLabel: costTransactionLabels.oaExpense,
      actionType: "click",
    }, async (mark) => {
      await projectRows.getByRole("button", { name: costTransactionLabels.oaExpense }).click();
      await mark("apiLatencyMs", detailResponse);
      await mark("firstVisibleResponseLatencyMs", expect(detailDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(detailDialog.getByText("浏览器成本统计明细").first()).toBeVisible());
    });
    expect(new URL((await detailRequest).url()).searchParams.get("project_scope")).toBe("active");
    await expect(detailDialog).toHaveClass(/cost-transaction-detail-drawer/);
    await expect(detailDialog.getByText("PLC 模块采购").first()).toBeVisible();
    await expect(detailDialog.getByText(/查看当前成本流水|展示这条支出流水|用于快速核对|保留原始银行流水/)).toHaveCount(0);
    await recordLatency({
      operationId: "cost-statistics.close-transaction-detail",
      visibleLabel: "关闭OA 成本归集明细",
      actionType: "click",
    }, async (mark) => {
      await detailDialog.getByRole("button", { name: "关闭OA 成本归集明细" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(page.getByRole("dialog", { name: "OA 成本归集明细" })).toHaveCount(0));
      await mark("finalSettledLatencyMs", expect(page.getByRole("dialog", { name: "OA 成本归集明细" })).toHaveCount(0));
    });

    const exportDialog = page.getByRole("dialog", { name: "导出中心" });
    await recordLatency({
      operationId: "cost-statistics.open-project-export-center",
      visibleLabel: "导出中心",
      actionType: "click",
    }, async (mark) => {
      await page.getByRole("button", { name: "导出中心" }).click();
      await mark("firstVisibleResponseLatencyMs", expect(exportDialog).toBeVisible());
      await mark("finalSettledLatencyMs", expect(exportDialog.getByText("项目选择")).toBeVisible());
    });

    const previewRequest = page.waitForRequest((request) => {
      const url = new URL(request.url());
      return url.pathname.endsWith("/api/cost-statistics/export-preview")
        && url.searchParams.get("view") === "project";
    });
    const previewResponse = page.waitForResponse(getResponse("/api/cost-statistics/export-preview"));
    await recordLatency({
      operationId: "cost-statistics.preview-project-export",
      visibleLabel: "仅预览",
      actionType: "click",
    }, async (mark) => {
      await exportDialog.getByRole("button", { name: "仅预览" }).click();
      await mark("apiLatencyMs", previewResponse);
      await mark("firstVisibleResponseLatencyMs", expect(exportDialog.getByRole("grid", { name: "导出预览表" })).toBeVisible());
      await mark("finalSettledLatencyMs", expect(exportDialog.getByText("预计导出 3 条流水")).toBeVisible());
    });
    const previewUrl = new URL((await previewRequest).url());
    expect(previewUrl.searchParams.get("project_scope")).toBe("active");
    expect(previewUrl.searchParams.getAll("project_name")).toContain("云南溯源科技");
    expect(previewUrl.searchParams.getAll("expense_type")).toContain("设备货款及材料费");
    const exportResponse = page.waitForResponse((response) =>
      response.url().includes("/api/cost-statistics/export")
        && response.request().method() === "GET",
    );
    await recordLatency({
      operationId: "cost-statistics.project-export-row-limit",
      visibleLabel: "导出",
      actionType: "click",
    }, async (mark) => {
      await exportDialog.getByRole("button", { name: "导出", exact: true }).click();
      await mark("apiLatencyMs", exportResponse);
      await mark("firstVisibleResponseLatencyMs", expect(exportDialog.getByText("导出结果超过 20000 行，请缩小筛选范围后重试。")).toBeVisible());
      await mark("finalSettledLatencyMs", expect(exportDialog.getByText("导出结果超过 20000 行，请缩小筛选范围后重试。")).toBeVisible());
    });
    expect((await exportResponse).status()).toBe(400);
    expect(api.count("GET /api/cost-statistics/export-preview")).toBe(1);
    expect(api.count("GET /api/cost-statistics/export")).toBe(1);
  });

  test("shows bank and expense-type baselines with drilldown details", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await installDeterministicApiMocks(page, { sessionMode: "full_access" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expect(page.getByRole("grid", { name: "按时间统计表" })).toBeVisible();

    await page.getByRole("radio", { name: "按银行" }).click();
    await expect(page.getByRole("heading", { name: "按银行统计" })).toBeVisible();
    await expect(page.getByRole("group", { name: "银行统计时间范围" }).getByRole("button", { name: "全部" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: /民生银行 账户 9486/ })).toBeVisible();

    await page.getByRole("button", { name: /工商银行 账户 0001/ }).click();
    await page.getByRole("button", { name: /云南溯源科技/ }).first().click();
    const bankRows = page.getByRole("grid", { name: "银行 OA 成本归集明细表" });
    await expect(bankRows).toBeVisible();
    await expect(bankRows).toContainText("PLC 模块采购");
    await expect(bankRows).toContainText("浏览器设备供应商");

    const bankDetailRequest = page.waitForRequest((request) =>
      decodeURIComponent(requestPath(request.url())).endsWith("/api/cost-statistics/allocations/oa:cost-txn-e2e-001"),
    );
    await bankRows.getByRole("button", { name: costTransactionLabels.oaExpense }).click();
    const bankDetailUrl = new URL((await bankDetailRequest).url());
    expect(bankDetailUrl.searchParams.get("project_scope")).toBe("active");
    const bankDetailDialog = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await expect(bankDetailDialog).toBeVisible();
    await expect(bankDetailDialog.getByText("PLC 模块采购").first()).toBeVisible();
    await expect(bankDetailDialog.getByText("浏览器成本统计明细").first()).toBeVisible();
    await bankDetailDialog.getByRole("button", { name: "关闭OA 成本归集明细" }).click();
    await expect(page.getByRole("dialog", { name: "OA 成本归集明细" })).toHaveCount(0);

    await page.getByRole("radio", { name: "按OA费用类型" }).click();
    await expect(page.getByRole("heading", { name: "按OA费用类型统计" })).toBeVisible();
    await expect(page.getByRole("button", { name: "OA费用类型统计时间范围：2026年3月" })).toBeVisible();
    await page.getByRole("button", { name: /设备货款及材料费/ }).first().click();
    const expenseRows = page.getByRole("grid", { name: "按费用类型 OA 成本归集明细表" });
    await expect(expenseRows).toBeVisible();
    await expect(expenseRows).toContainText("云南溯源科技");
    await expect(expenseRows).toContainText("PLC 模块采购");

    const expenseDetailRequest = page.waitForRequest((request) =>
      decodeURIComponent(requestPath(request.url())).endsWith("/api/cost-statistics/allocations/oa:cost-txn-e2e-001"),
    );
    await expenseRows.getByRole("button", { name: costTransactionLabels.oaExpense }).click();
    const expenseDetailUrl = new URL((await expenseDetailRequest).url());
    expect(expenseDetailUrl.searchParams.get("project_scope")).toBe("active");
    const expenseDetailDialog = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await expect(expenseDetailDialog).toBeVisible();
    await expect(expenseDetailDialog.getByText("PLC 模块采购").first()).toBeVisible();
    await expect(expenseDetailDialog.getByText("浏览器成本统计明细").first()).toBeVisible();
    await expenseDetailDialog.getByRole("button", { name: "关闭OA 成本归集明细" }).click();
    await expect(page.getByRole("dialog", { name: "OA 成本归集明细" })).toHaveCount(0);
    expect(browserErrors).toEqual([]);
  });

  test("keeps large cost tables fresh, scrollable, and usable on narrow screens", async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await page.setViewportSize({ width: 390, height: 820 });
    await installDeterministicApiMocks(page, {
      costStatisticsLargeDataset: true,
      sessionMode: "full_access",
    });

    const timeExplorerResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/cost-statistics/explorer")
        && url.searchParams.get("scope") === "2026-03"
        && url.searchParams.get("project_scope") === "active";
    });
    await page.goto("/cost-statistics");
    const timeExplorerPayload = await (await timeExplorerResponsePromise).json() as CostExplorerBrowserPayload;
    expect(timeExplorerPayload.summary?.row_count).toBeGreaterThanOrEqual(120);

    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    await expectVisibleAndUncovered(page.getByRole("button", { name: "导出中心" }), "narrow export center button");
    const timeGrid = page.getByRole("grid", { name: "按时间统计表" });
    await expect(timeGrid).toBeVisible();
    const timeTableScroll = page.locator(".cost-table-section").filter({ has: timeGrid }).locator(".finance-table__scroll").first();
    await timeTableScroll.evaluate((element) => {
      element.scrollTop = element.scrollHeight;
    });
    await expect(timeGrid).toContainText("大型成本流水费用内容 120");

    await expectHorizontalScroll(timeTableScroll, "large time-view cost table");
    await expectInViewport(timeGrid.getByRole("columnheader", { name: "流水摘要" }), "time-view rightmost cost column");
    await expectVerticalScroll(timeTableScroll, "large time-view cost table");

    const projectExplorerResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/cost-statistics/explorer")
        && url.searchParams.get("scope") === "all"
        && url.searchParams.get("project_scope") === "active";
    });
    await page.getByRole("radio", { name: "按项目" }).click();
    const projectExplorerPayload = await (await projectExplorerResponsePromise).json() as CostExplorerBrowserPayload;
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    const largeProject = page.getByRole("button", { name: /大型成本浏览器稳定性项目/ }).first();
    await expectVisibleAndUncovered(largeProject, "large cost project selector");
    await largeProject.click();
    const largeExpenseType = page.getByRole("button", { name: /大型宽表费用类型-1/ }).first();
    await expectVisibleAndUncovered(largeExpenseType, "large cost expense type selector");
    await largeExpenseType.click();

    const projectRows = page.getByRole("grid", { name: "项目 OA 成本归集明细表" });
    await expect(projectRows).toBeVisible();
    await expect(projectRows).toContainText("大型成本流水费用内容");
    await expect(projectRows).toContainText("大型成本浏览器供应商");

    const projectTableScroll = page.locator(".cost-explorer-lane-table").locator(".finance-table__scroll").first();
    await expectHorizontalScroll(projectTableScroll, "large project-drilldown cost table");
    await expectInViewport(page.getByRole("columnheader", { name: "费用内容" }), "project-drilldown rightmost cost column");
    await expectVerticalScroll(projectTableScroll, "large project-drilldown cost table");
    expect(browserErrors).toEqual([]);
  });
});
