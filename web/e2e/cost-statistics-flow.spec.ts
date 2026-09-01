import { expect, test, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

function waitForExplorer(page: Page, predicate: (url: URL) => boolean) {
  return page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === "GET"
      && url.pathname.endsWith("/api/cost-statistics/explorer")
      && predicate(url);
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    const now = Date.now();
    sessionStorage.setItem("finops:pageSession:v1:e2e-user:cost-statistics:explorerState", JSON.stringify({
      version: 5,
      updatedAt: now,
      expiresAt: now + 60 * 60 * 1000,
      value: {
        viewMode: "project",
        projectScopeMode: "all",
        projectScopeYear: "2026",
        projectScopeMonth: "2026-03",
        bankAccountScopeMode: "all",
        bankAccountScopeYear: "2026",
        bankAccountScopeMonth: "2026-03",
        expenseTypeScopeMode: "month",
        expenseTypeScopeYear: "2026",
        expenseTypeScopeMonth: "2026-03",
        bankFlowScopeMode: "month",
        bankFlowScopeYear: "2026",
        bankFlowScopeMonth: "2026-03",
      },
    }));
  });
});

test.describe("cost statistics browser flow", () => {
  test("exposes three project-cost views and two bank-flow views", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const switcher = page.getByRole("group", { name: "成本统计视图切换" });
    await expect(switcher.getByText("项目成本")).toBeVisible();
    const views = switcher.getByRole("radiogroup", { name: "项目成本统计视图" });
    await expect(views.getByRole("radio")).toHaveCount(3);
    await expect(views.getByRole("radio", { name: "按项目" })).toBeVisible();
    await expect(views.getByRole("radio", { name: "按费用类型" })).toBeVisible();
    await expect(views.getByRole("radio", { name: "按银行账户" })).toBeVisible();
    await expect(switcher.getByText("银行流水")).toBeVisible();
    const bankFlowViews = switcher.getByRole("radiogroup", { name: "银行流水统计视图" });
    await expect(bankFlowViews.getByRole("radio")).toHaveCount(2);
    await expect(bankFlowViews.getByRole("radio", { name: "按标签" })).toBeVisible();
    await expect(bankFlowViews.getByRole("radio", { name: "按时间" })).toBeVisible();
    await expect(page.getByText("成本归因")).toHaveCount(0);
  });

  test("shows signed raw flows by time and drills from tags to bank rows", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    const timeResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "time");
    await page.getByRole("radio", { name: "按时间" }).click();
    await timeResponse;
    const timeGrid = page.getByRole("grid", { name: "按时间银行流水表" });
    await expect(timeGrid).toBeVisible();
    await expect(timeGrid.getByText("收", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "按时间统计" }).locator("..")).not.toContainText("净支出");

    const tagRootResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "bank_tag");
    await page.getByRole("radio", { name: "按标签" }).click();
    await tagRootResponse;
    const subTagResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "bank_tag"
      && url.searchParams.get("bank_tag_primary_label") === "项目开销"
    ));
    await page.getByRole("option", { name: "选择主标签 项目开销" }).click();
    await subTagResponse;
    const tagRowsResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "bank_tag"
      && url.searchParams.get("bank_tag_primary_label") === "项目开销"
      && url.searchParams.get("bank_tag_sub_label") === "设备材料"
    ));
    await page.getByRole("option", { name: "选择子标签 设备材料" }).click();
    await tagRowsResponse;
    await expect(page.getByRole("grid", { name: "按标签银行流水表" })).toContainText("PLC 模块采购");
  });

  test("keeps time pagination visible and scrolls only the current twenty rows", async ({ page }) => {
    await installDeterministicApiMocks(page, {
      sessionMode: "user",
      costStatisticsLargeDataset: true,
    });

    await page.goto("/cost-statistics");
    const timeResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "time");
    await page.getByRole("radio", { name: "按时间" }).click();
    await timeResponse;

    const timeGrid = page.getByRole("grid", { name: "按时间银行流水表" });
    await expect(timeGrid.getByRole("row")).toHaveCount(21);
    const pagination = page.getByRole("navigation", { name: "pagination" });
    const nextPage = pagination.getByRole("button", { name: "下一页" });
    await expect(pagination).toBeVisible();
    await expect(page.getByText(/第 1 \/ \d+ 页/)).toBeVisible();
    await expect(nextPage).toBeVisible();
    for (const viewport of [
      { width: 1728, height: 921 },
      { width: 1440, height: 900 },
      { width: 1280, height: 800 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(viewport);
      const paginationBox = await pagination.boundingBox();
      expect(paginationBox).not.toBeNull();
      expect((paginationBox?.y ?? 0) + (paginationBox?.height ?? 0)).toBeLessThanOrEqual(viewport.height);
    }

    const scrollSurface = timeGrid.locator(
      "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' finance-table__scroll ')][1]",
    );
    const beforeScroll = await scrollSurface.evaluate((element) => ({
      clientHeight: element.clientHeight,
      scrollHeight: element.scrollHeight,
    }));
    expect(beforeScroll.scrollHeight).toBeGreaterThan(beforeScroll.clientHeight);
    const pageScrollBefore = await page.evaluate(() => window.scrollY);
    await scrollSurface.evaluate((element) => {
      element.scrollTop = Math.min(240, element.scrollHeight - element.clientHeight);
    });
    await expect.poll(() => scrollSurface.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(pageScrollBefore);

    const nextPageResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "time"
      && url.searchParams.get("cursor") === "mock:20"
    ));
    await nextPage.click();
    await nextPageResponse;
    await expect(page.getByText(/第 2 \/ \d+ 页/)).toBeVisible();
    await expect(timeGrid.getByRole("row")).toHaveCount(21);
    await expect.poll(() => scrollSurface.evaluate((element) => element.scrollTop)).toBe(0);
  });

  test("drills from project through expense type to OA cost detail", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();

    const expenseTypesResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "project"
      && url.searchParams.get("project_name") === "云南溯源科技"
    ));
    await page.getByRole("option", { name: "选择项目名 云南溯源科技" }).click();
    await expenseTypesResponse;

    const rowsResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "project"
      && url.searchParams.get("project_name") === "云南溯源科技"
      && url.searchParams.get("expense_type") === "设备货款及材料费"
    ));
    await page.getByRole("option", { name: "选择费用类型 设备货款及材料费" }).click();
    await rowsResponse;

    const grid = page.getByRole("grid", { name: "项目成本明细表" });
    await expect(grid).toBeVisible();
    await expect(grid).toContainText("PLC 模块采购");
    await grid.getByRole("button", { name: /查看OA 成本归集 云南溯源科技 2026-03-10/ }).click();
    const drawer = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await expect(drawer).toContainText("浏览器成本统计明细");
    await expect(drawer).toContainText("工商银行 账户 0001");
  });

  test("drills from bank account through project to the same cost population", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    const accountListResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "bank_account");
    await page.getByRole("radio", { name: "按银行账户" }).click();
    await accountListResponse;
    await expect(page.getByRole("heading", { name: "按银行账户统计" })).toBeVisible();

    const projectListResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "bank_account"
      && url.searchParams.get("bank_account_label") === "工商银行 账户 0001"
    ));
    await page.getByRole("option", { name: "选择银行账户 工商银行 账户 0001" }).click();
    await projectListResponse;

    const rowsResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "bank_account"
      && url.searchParams.get("bank_account_label") === "工商银行 账户 0001"
      && url.searchParams.get("project_name") === "云南溯源科技"
    ));
    await page.getByRole("option", { name: "选择项目 云南溯源科技" }).click();
    await rowsResponse;

    const grid = page.getByRole("grid", { name: "银行账户项目成本明细表" });
    await expect(grid).toBeVisible();
    await expect(grid).toContainText("PLC 模块采购");
  });

  test("keeps expense-type analysis as an independent drill-down", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    const expenseListResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "expense_type");
    await page.getByRole("radio", { name: "按费用类型" }).click();
    await expenseListResponse;

    const rowsResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "expense_type"
      && url.searchParams.get("expense_type") === "设备货款及材料费"
    ));
    await page.getByRole("option", { name: "选择费用类型 设备货款及材料费" }).click();
    await rowsResponse;
    await expect(page.getByRole("grid", { name: "按费用类型成本明细表" })).toContainText("云南溯源科技");
  });

  test("previews bank-flow and bank-account exports", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    await page.getByRole("button", { name: "导出中心" }).click();
    const dialog = page.getByRole("dialog", { name: "导出中心" });
    await expect(dialog).toBeVisible();
    const tabs = dialog.getByRole("tablist", { name: "导出视图切换" });
    await expect(tabs.getByRole("button")).toHaveCount(5);
    await tabs.getByRole("button", { name: "按时间" }).click();
    const flowPreviewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/cost-statistics/export-preview")
        && url.searchParams.get("view") === "time";
    });
    await dialog.getByRole("button", { name: "仅预览" }).click();
    await flowPreviewResponse;
    await expect(dialog.getByText(/预计导出 \d+ 条银行流水/)).toBeVisible();
    await expect(dialog.getByText(/支出/).first()).toBeVisible();
    await expect(dialog.getByText(/收入/).first()).toBeVisible();
    await expect(dialog.getByText(/净支出/)).toHaveCount(0);

    await tabs.getByRole("button", { name: "按银行账户" }).click();

    const previewResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return response.request().method() === "GET"
        && url.pathname.endsWith("/api/cost-statistics/export-preview")
        && url.searchParams.get("view") === "bank_account";
    });
    await dialog.getByRole("button", { name: "仅预览" }).click();
    const previewUrl = new URL((await previewResponse).url());
    expect(previewUrl.searchParams.has("bank_account_label")).toBe(true);
    await expect(dialog.getByText(/预计导出 \d+ 条成本明细/)).toBeVisible();
    await expect(dialog.getByRole("grid", { name: "导出预览表" })).toContainText("银行账户");
  });

  test("saves no-OA rules and refreshes the affected cost explorer", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
    const explorerCallsBeforeSave = api.count("GET /api/cost-statistics/explorer");
    await page.getByRole("button", { name: "无 OA 成本范围" }).click();
    const drawer = page.getByRole("dialog", { name: "无 OA 成本范围" });
    await drawer.getByRole("button", { name: "新增虚拟项目" }).click();
    await drawer.getByRole("textbox", { name: "虚拟项目名称" }).fill("云南溯源无 OA 分类");
    await drawer.getByText("材料费", { exact: true }).click();
    await drawer.getByRole("button", { name: "保存" }).click();

    await expect(drawer).toBeHidden();
    expect(api.count("PUT /api/cost-statistics/no-oa-rules")).toBe(1);
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(explorerCallsBeforeSave);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
