import { expect, test, type Locator } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

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

async function scrollPaneHorizontally(scrollbar: Locator) {
  await expect(scrollbar).toBeVisible();
  const scrollState = await scrollbar.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return {
      clientWidth: element.clientWidth,
      scrollLeft: element.scrollLeft,
      scrollWidth: element.scrollWidth,
    };
  });
  expect(scrollState.scrollWidth).toBeGreaterThanOrEqual(scrollState.clientWidth);
  return scrollState.scrollLeft;
}

test.describe("workbench large dataset browser flow", () => {
  test("shows grouped bank, applicant, and project filters without overlapping long labels", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });
    await page.goto("/");

    const zone = page.getByTestId("zone-unpaired");
    await expect(zone).toBeVisible();

    await zone.getByRole("button", { name: "筛选 金额" }).click();
    const bankMenu = page.getByRole("dialog", { name: "筛选 金额" });
    await expect(bankMenu.getByText("收支方向", { exact: true })).toBeVisible();
    await expect(bankMenu.getByText("银行账户", { exact: true })).toBeVisible();
    await expect(bankMenu.getByText("流水标签", { exact: true })).toBeVisible();
    await expect(bankMenu.getByRole("checkbox", { name: "建设银行 1102" })).toBeVisible();
    const bankTag = bankMenu.getByRole("checkbox", { name: "成本 / 设备款" });
    await bankTag.scrollIntoViewIfNeeded();
    await expect(bankTag).toBeVisible();
    await expect(bankMenu.getByText(/未识别银行|未识别账户/)).toHaveCount(0);
    await page.keyboard.press("Escape");

    await zone.getByRole("button", { name: "筛选 申请人" }).click();
    const applicantMenu = page.getByRole("dialog", { name: "筛选 申请人" });
    await expect(applicantMenu.getByText("OA 类型", { exact: true })).toBeVisible();
    await expect(applicantMenu.getByText("流程状态", { exact: true })).toBeVisible();
    await expect(applicantMenu.getByText("申请人", { exact: true })).toBeVisible();
    await expect(applicantMenu.getByRole("checkbox", { name: "支付申请" })).toBeVisible();
    await expect(applicantMenu.getByRole("checkbox", { name: "已完成" })).toBeVisible();
    await page.keyboard.press("Escape");

    await zone.getByRole("button", { name: "筛选 项目名称" }).click();
    const projectMenu = page.getByRole("dialog", { name: "筛选 项目名称" });
    await expect(projectMenu.getByText("OA 费用类型", { exact: true })).toBeVisible();
    await expect(projectMenu.getByText("项目名称", { exact: true })).toBeVisible();
    await expect(projectMenu.getByRole("checkbox", { name: "固定资产" })).toBeVisible();
    const geometry = await projectMenu.evaluate((element) => {
      const popover = element.closest(".column-filter-popover");
      const options = Array.from(element.querySelectorAll<HTMLElement>(".column-filter-option"));
      const rects = options.map((option) => option.getBoundingClientRect());
      return {
        width: popover?.getBoundingClientRect().width ?? 0,
        maxHeight: Math.max(...rects.map((rect) => rect.height)),
        minHeight: Math.min(...rects.map((rect) => rect.height)),
        overlaps: rects.some((rect, index) => index > 0 && rect.top < rects[index - 1].bottom - 0.5),
      };
    });
    expect(geometry.width).toBeGreaterThanOrEqual(400);
    expect(geometry.minHeight).toBeGreaterThanOrEqual(27.5);
    expect(geometry.maxHeight).toBeGreaterThan(36);
    expect(geometry.overlaps).toBe(false);
  });

  test("keeps narrow-screen overflow inside the workbench panes", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "关联台" })).toBeVisible();
    await expect(page.getByTestId("zone-unpaired")).toBeVisible();

    const documentSize = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(documentSize.scrollWidth).toBeLessThanOrEqual(documentSize.clientWidth + 1);
    await expect(page.getByTestId("pane-scrollbar-unpaired-bank")).toBeHidden();

    const firstGroup = page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001");
    const oaPane = await firstGroup.locator('[data-pane-id="oa"]').first().boundingBox();
    const bankPane = await firstGroup.locator('[data-pane-id="bank"]').first().boundingBox();
    const invoicePane = await firstGroup.locator('[data-pane-id="invoice"]').first().boundingBox();
    expect(oaPane).not.toBeNull();
    expect(bankPane).not.toBeNull();
    expect(invoicePane).not.toBeNull();
    expect(oaPane!.y).toBeLessThan(bankPane!.y);
    expect(bankPane!.y).toBeLessThan(invoicePane!.y);
  });

  test("keeps automatic pagination, full search, tri-pane scroll, detail drawer, and selection controls usable", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const groupRequestUrls: URL[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (request.method() === "GET" && url.pathname === "/api/workbench/groups") {
        groupRequestUrls.push(url);
      }
    });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-013")).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: "加载更多" })).toHaveCount(0);
    expect(api.count("GET /api/workbench")).toBeGreaterThan(0);
    expect(api.count("GET /api/workbench/groups")).toBe(0);

    await openZone.getByRole("button", { name: "筛选 申请人" }).click();
    const applicantFilter = page.getByRole("dialog", { name: "筛选 申请人" });
    await expect(applicantFilter.getByRole("checkbox", { name: "大数据申请人064" })).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-013")).toHaveCount(0);
    expect(api.count("GET /api/workbench/filter-options")).toBe(1);
    await page.keyboard.press("Escape");

    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect.poll(() => api.count("GET /api/workbench/groups")).toBe(1);
    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-large-202603-030")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    expect(groupRequestUrls[0]?.searchParams.get("cursor")).toBeTruthy();
    expect(groupRequestUrls[0]?.searchParams.has("page")).toBe(false);
    expect(groupRequestUrls[1]?.searchParams.get("cursor")).toBeTruthy();
    expect(groupRequestUrls[1]?.searchParams.has("page")).toBe(false);

    const pairedSearch = page.getByRole("searchbox", { name: "搜索已配对区域" });
    const unpairedSearch = openZone.getByRole("searchbox", { name: "搜索未配对区域" });
    await expect(pairedSearch).toBeVisible();
    await expect(unpairedSearch).toBeVisible();
    await unpairedSearch.fill("长列表供应商155");
    const targetGroup = page.getByTestId("candidate-group-unpaired-row:bk-large-202603-155");
    await expect(targetGroup).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toHaveCount(0);
    await expect(targetGroup.locator("mark.search-hit", { hasText: "长列表供应商155" })).toBeVisible();
    await expect(pairedSearch).toHaveValue("");
    await expect.poll(() => api.count("GET /api/workbench/groups")).toBe(3);
    expect(groupRequestUrls[2]?.searchParams.get("search")).toBe("长列表供应商155");
    expect(groupRequestUrls[2]?.searchParams.has("cursor")).toBe(false);

    await targetGroup.getByRole("row", { name: /长列表供应商155/ }).click();
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await expect(openZone.getByText(/带入/)).toHaveCount(0);
    await targetGroup.getByRole("button", { name: "查看银行流水 长列表供应商155有限公司 详情" }).click();
    const detailDrawer = page.getByRole("dialog", { name: "银行流水详情" });
    await expect(detailDrawer.getByText("银行流水详情", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("账户明细编号-交易流水号", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("BK-LARGE-155", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("大数据场景", { exact: true })).toHaveCount(0);
    await expect(detailDrawer.getByText("第155组银行流水详情", { exact: true })).toHaveCount(0);
    await expectVisibleAndUncovered(detailDrawer.getByRole("button", { name: "关闭详情抽屉" }), "detail drawer close button");
    await detailDrawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(detailDrawer).toHaveCount(0);
    await expect(page.locator(".finance-drawer__content")).toHaveCount(0);
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await openZone.getByRole("button", { name: "清空搜索" }).click();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();
    await expect.poll(() => api.count("GET /api/workbench/groups")).toBe(4);
    expect(groupRequestUrls[3]?.searchParams.has("search")).toBe(false);
    expect(groupRequestUrls[3]?.searchParams.has("cursor")).toBe(false);
    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-large-202603-012")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(5);
    expect(groupRequestUrls[4]?.searchParams.get("cursor")).toBeTruthy();
    expect(groupRequestUrls[4]?.searchParams.has("page")).toBe(false);
    await page.getByTestId("candidate-group-unpaired-row:oa-large-202603-013").getByRole("cell").first().click();
    await page.getByTestId("candidate-group-unpaired-row:iv-large-202603-012").getByRole("cell").first().click();
    await expect(openZone.getByText("已选 3")).toBeVisible();
    const confirmButton = openZone.getByRole("button", { name: "确认关联" });
    await expect(confirmButton).toBeEnabled();
    await expectVisibleAndUncovered(confirmButton, "open zone confirm button after filtering");
    await expect(openZone.getByText("已选 3")).toBeVisible();
    await expect(openZone.getByText(/带入/)).toHaveCount(0);
    await expect(confirmButton).toBeEnabled();

    const bankFooter = page.getByTestId("pane-scrollbar-unpaired-bank");
    const bankHeader = page.getByTestId("pane-scroll-head-unpaired-bank");
    const bankRow = page.getByTestId("candidate-scroll-unpaired-row:bk-large-202603-014-bank");
    await scrollPaneHorizontally(bankFooter);
    await expect.poll(() => bankHeader.evaluate(
      (element) => element.scrollWidth - element.clientWidth - element.scrollLeft,
    )).toBe(0);
    await expect.poll(() => bankRow.evaluate(
      (element) => element.scrollWidth - element.clientWidth - element.scrollLeft,
    )).toBe(0);
    await expectVisibleAndUncovered(confirmButton, "open zone confirm button after horizontal scroll");
  });

  test("stops automatic retries after a page failure and resumes only when the user retries", async ({ page }) => {
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchGroupsFailuresBeforeSuccess: 1,
      workbenchLargeDataset: true,
    });

    await page.goto("/");
    const openZone = page.getByTestId("zone-unpaired");
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();
    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });

    await expect(openZone.getByRole("alert")).toContainText("关联台服务暂时不可用，请稍后重试。");
    expect(api.count("GET /api/workbench/groups")).toBe(1);
    await page.waitForTimeout(500);
    expect(api.count("GET /api/workbench/groups")).toBe(1);

    await openZone.getByRole("button", { name: "重试自动加载" }).click();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-013")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    await expect(openZone.getByRole("alert")).toHaveCount(0);
  });
});
