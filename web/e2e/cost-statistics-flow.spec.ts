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
      version: 6,
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
        costTagScopeMode: "month",
        costTagScopeYear: "2026",
        costTagScopeMonth: "2026-03",
        bankFlowScopeMode: "month",
        bankFlowScopeYear: "2026",
        bankFlowScopeMonth: "2026-03",
      },
    }));
  });
});

test.describe("cost statistics browser flow", () => {
  test("opens every view in all time and resets a chosen month after reload", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });
    const first = waitForExplorer(page, url => url.searchParams.get("scope") === "all");
    await page.goto("/cost-statistics");
    await first;
    for (const name of ["按项目", "按银行账户", "按成本标签", "按标签", "按时间"]) {
      await page.getByRole("radio", { name, exact: true }).click();
      await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
    }
    await page.getByRole("button", { name: "银行流水时间范围：年月" }).click();
    const picker = page.getByRole("dialog", { name: "银行流水时间范围选择器" });
    await picker.getByRole("radio", { name: "按月", exact: true }).click();
    const month = waitForExplorer(page, url => url.searchParams.get("scope") === "2026-03");
    await picker.getByRole("button", { name: "三月", exact: true }).click();
    await month;
    const refreshed = waitForExplorer(page, url => url.searchParams.get("scope") === "2026-03");
    await page.getByRole("button", { name: "刷新成本统计" }).click();
    await refreshed;
    await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "false");
    await page.getByRole("button", { name: "导出中心" }).click();
    const dialog = page.getByRole("dialog", { name: "导出中心" });
    await expect(dialog.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
    await dialog.getByRole("button", { name: "关闭导出中心" }).click();
    const reset = waitForExplorer(page, url => url.searchParams.get("scope") === "all");
    await page.reload(); await reset;
    await expect(page.getByRole("button", { name: "全部", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test("exposes three project-cost views and two bank-flow views", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    await expect(page.getByRole("heading", { name: "成本统计" })).toBeVisible();
    const switcher = page.getByRole("group", { name: "成本统计视图切换" });
    await expect(switcher.getByText("项目成本")).toBeVisible();
    const views = switcher.getByRole("radiogroup", { name: "项目成本统计视图" });
    await expect(views.getByRole("radio")).toHaveCount(3);
    await expect(views.getByRole("radio", { name: "按项目" })).toBeVisible();
    await expect(views.getByRole("radio", { name: "按成本标签" })).toBeVisible();
    await expect(views.getByRole("radio", { name: "按银行账户" })).toBeVisible();
    await expect(switcher.getByText("银行流水")).toBeVisible();
    const bankFlowViews = switcher.getByRole("radiogroup", { name: "银行流水统计视图" });
    await expect(bankFlowViews.getByRole("radio")).toHaveCount(2);
    await expect(bankFlowViews.getByRole("radio", { name: "按标签" })).toBeVisible();
    await expect(bankFlowViews.getByRole("radio", { name: "按时间" })).toBeVisible();
    await expect(page.getByText("成本归因")).toHaveCount(0);
    await expect(page.getByText(/^依次选择/)).toHaveCount(0);
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
    await expect(page.getByText("依次选择主标签和子标签")).toHaveCount(0);
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

  test("drills from project through bank tags to OA cost detail", async ({ page }) => {
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
      && url.searchParams.get("bank_tag_primary_key") === "primary:项目开销"
    ));
    await page.getByRole("option", { name: "选择成本主标签 项目开销" }).click();
    await rowsResponse;

    await page.getByRole("option", { name: "选择成本子标签 设备材料" }).click();
    const grid = page.getByRole("grid", { name: "成本明细表" });
    await expect(grid).toBeVisible();
    await expect(grid).toContainText("PLC 模块采购");
    await grid.getByRole("button", { name: /查看成本明细 云南溯源科技 2026-03-10/ }).click();
    const drawer = page.getByRole("dialog", { name: "OA 成本归集明细" });
    await expect(drawer).toContainText("浏览器成本统计明细");
    await expect(drawer).toContainText("工商银行 账户 0001");
  });

  test("drills from bank account through project and tags to the same cost population", async ({ page }) => {
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
    await page.getByRole("option", { name: "选择项目名 云南溯源科技" }).click();
    await rowsResponse;

    await page.getByRole("option", { name: "选择成本主标签 项目开销" }).click();
    await page.getByRole("option", { name: "选择成本子标签 设备材料" }).click();
    const grid = page.getByRole("grid", { name: "成本明细表" });
    await expect(grid).toBeVisible();
    await expect(grid).toContainText("PLC 模块采购");
  });

  test("keeps bank-tag analysis as an independent drill-down", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: "user" });

    await page.goto("/cost-statistics");
    const expenseListResponse = waitForExplorer(page, (url) => url.searchParams.get("view") === "cost_tag");
    await page.getByRole("radio", { name: "按成本标签" }).click();
    await expenseListResponse;

    const rowsResponse = waitForExplorer(page, (url) => (
      url.searchParams.get("view") === "cost_tag"
      && url.searchParams.get("bank_tag_primary_key") === "primary:项目开销"
    ));
    await page.getByRole("option", { name: "选择成本主标签 项目开销" }).click();
    await rowsResponse;
    await page.getByRole("option", { name: "选择成本子标签 设备材料" }).click();
    await expect(page.getByRole("grid", { name: "成本明细表" })).toContainText("云南溯源科技");
  });

  test("export drawer counts independent bank and cost selections without preview", async ({ page }) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto('/cost-statistics');
    await page.getByRole('button', {name:'导出中心'}).click();
    const drawer = page.getByRole('dialog', {name:'导出中心'});
    await expect(drawer.getByRole('button', {name:'导出',exact:true})).toBeEnabled();
    await expect.poll(async () => {
      const box = await drawer.boundingBox();
      const viewport = page.viewportSize()!;
      return Boolean(box && Math.abs(box.y) <= 1 && Math.abs(box.height - viewport.height) <= 1
        && Math.abs(box.x + box.width - viewport.width) <= 1 && Math.abs(box.width - Math.min(1280, viewport.width)) <= 1);
    }).toBe(true);
    await expect(drawer.getByText("项目成本", {exact:true})).toBeVisible();
    await expect(drawer.getByText("银行流水", {exact:true})).toBeVisible();
    const groups = await drawer.locator('.export-center-toolbar .app-segments').evaluateAll(nodes => nodes.map(node => { const r=node.getBoundingClientRect(); return {y:r.y,height:r.height}; }));
    const period = await drawer.locator('.business-period-picker').boundingBox();
    for (const group of groups) {
      expect(Math.abs(group.height - period!.height)).toBeLessThanOrEqual(1);
      expect(Math.abs(group.y - period!.y)).toBeLessThanOrEqual(1);
    }
    await expect(drawer.getByText('按月算')).toHaveCount(0);
    const tabs=drawer;
    await tabs.getByRole('radio',{name:'按时间'}).click();
    await expect(drawer.getByText(/导出 \d+ 笔/)).toBeVisible();
    await tabs.getByRole('radio',{name:'按银行账户'}).click();
    await expect(drawer.getByText(/导出 \d+ 条成本明细/)).toBeVisible();
    await page.setViewportSize({width: 760,height:900});
    await expect.poll(async () => { const box = await drawer.boundingBox(); return box ? box.width <= 760 : false; }).toBe(true);
    await expect(drawer.getByRole('grid')).toHaveCount(0);
    await expect(drawer.getByRole('button',{name:'仅预览'})).toHaveCount(0);
  });

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 760, height: 640 }]) {
    test(`export lists scroll independently without toolbar overlap at ${viewport.width}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      const api = await installDeterministicApiMocks(page, { sessionMode: "user", costStatisticsLongExportLists: true });
      await page.goto("/cost-statistics");
      await page.getByRole("button", { name: "导出中心" }).click();
      const drawer = page.getByRole("dialog", { name: "导出中心" });
      const projects = drawer.getByRole("region", { name: "项目列表", exact: true });
      const tags = drawer.getByRole("region", { name: "成本主标签列表", exact: true });
      await expect.poll(() => projects.getByRole("checkbox").count()).toBeGreaterThanOrEqual(60);
      await expect.poll(() => tags.getByRole("checkbox").count()).toBeGreaterThanOrEqual(30);
      await expect(drawer.getByRole("button", { name: "导出", exact: true })).toBeEnabled();
      await expect.poll(async () => {
        const box = await drawer.boundingBox();
        return box ? Math.abs(box.x + box.width - viewport.width) : Infinity;
      }).toBeLessThan(0.01);
      const toolbar = drawer.locator(".export-center-toolbar");
      const toolbarBefore = await toolbar.boundingBox();
      const footer = drawer.locator(".finance-drawer__footer");
      const footerBefore = await footer.boundingBox();
      const calls = api.count("POST /api/cost-statistics/export-summary");
      const position = (locator: typeof projects) => locator.evaluate(node => node.scrollTop);
      await projects.hover();
      await page.mouse.wheel(0, 600);
      await expect.poll(() => position(projects)).toBeGreaterThan(0);
      expect(await position(tags)).toBe(0);
      const projectScroll = await position(projects);
      await tags.hover();
      await page.mouse.wheel(0, 500);
      await expect.poll(() => position(tags)).toBeGreaterThan(0);
      expect(await position(projects)).toBe(projectScroll);
      expect(await toolbar.boundingBox()).toEqual(toolbarBefore);
      expect(await footer.boundingBox()).toEqual(footerBefore);
      expect(await drawer.locator(".finance-drawer__body").evaluate(node => node.scrollTop)).toBe(0);
      expect(api.count("POST /api/cost-statistics/export-summary")).toBe(calls);
      // Actual hit testing catches checkbox/content leaking over the toolbar, including its top gap.
      expect(await toolbar.evaluate(node => {
        const r = node.getBoundingClientRect();
        return [r.top - 4, r.top + 4, r.bottom - 4].every(y => {
          const hit = document.elementFromPoint(r.left + 40, y);
          return !hit?.closest(".export-center-list");
        });
      })).toBe(true);
      const tagScroll = await position(tags);
      await drawer.getByRole("textbox", { name: "搜索项目", exact: true }).fill("项目 60");
      await expect(projects.getByRole("checkbox")).toHaveCount(1);
      expect(await position(projects)).toBe(0);
      expect(await position(tags)).toBe(tagScroll);
      await drawer.getByRole("textbox", { name: "搜索项目", exact: true }).fill("");
      await projects.focus();
      await page.keyboard.press("End");
      await expect.poll(async () => projects.evaluate(node => node.scrollHeight - node.clientHeight - node.scrollTop)).toBeLessThan(2);
      await projects.getByText("滚动验证项目 60", { exact: true }).click();
      const afterSelection = await position(projects);
      await expect.poll(() => api.count("POST /api/cost-statistics/export-summary")).toBeGreaterThan(calls);
      await expect(drawer.getByRole("button", { name: "导出", exact: true })).toBeEnabled();
      expect(await position(projects)).toBe(afterSelection);
      await page.mouse.wheel(0, 1000);
      expect(await drawer.locator(".finance-drawer__body").evaluate(node => node.scrollTop)).toBe(0);
      expect(await page.evaluate(() => window.scrollY)).toBe(0);
      await drawer.getByRole("radio", { name: "按银行账户" }).click();
      expect(await drawer.getByRole("region", { name: "项目（可选）列表" }).evaluate(node => node.scrollTop)).toBe(0);
      await drawer.getByRole("button", { name: "关闭导出中心" }).click();
      await expect(drawer).toBeHidden();
      await expectNoUnexpectedSuccessUiErrors(page);
    });
  }

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

    await expect.poll(() => api.count("PUT /api/cost-statistics/no-oa-rules")).toBe(1);
    await expect(drawer.getByRole("button", { name: "云南溯源无 OA 分类 1 个标签" })).toBeVisible();
    await drawer.getByRole("button", { name: "关闭抽屉" }).click();
    await expect(drawer).toBeHidden();
    expect(api.count("PUT /api/cost-statistics/no-oa-rules")).toBe(1);
    expect(api.count("GET /api/cost-statistics/explorer")).toBeGreaterThan(explorerCallsBeforeSave);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
