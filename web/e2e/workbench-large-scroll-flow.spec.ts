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
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-064")).toHaveCount(0);
    await expect(openZone.getByRole("button", { name: "加载更多" })).toHaveCount(0);
    expect(api.count("GET /api/workbench/groups")).toBe(0);

    await openZone.getByRole("button", { name: "筛选 申请人" }).click();
    const applicantFilter = page.getByRole("dialog", { name: "筛选 申请人" });
    await expect(applicantFilter.getByRole("checkbox", { name: "大数据申请人064" })).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-064")).toHaveCount(0);
    expect(api.count("GET /api/workbench/filter-options")).toBe(1);
    await page.keyboard.press("Escape");

    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-large-202603-099")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(1);

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

    await targetGroup.getByRole("row", { name: /长列表供应商155/ }).click();
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await expect(openZone.getByText(/带入/)).toHaveCount(0);
    await targetGroup.getByRole("button", { name: "查看银行流水 长列表供应商155有限公司 详情" }).click();
    const detailDrawer = page.getByRole("dialog", { name: "银行流水详情" });
    await expect(detailDrawer.getByText("银行流水详情", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("第155组银行流水详情")).toBeVisible();
    await expectVisibleAndUncovered(detailDrawer.getByRole("button", { name: "关闭详情抽屉" }), "detail drawer close button");
    await detailDrawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(detailDrawer).toHaveCount(0);
    await expect(page.locator(".finance-drawer__content")).toHaveCount(0);
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await openZone.getByRole("button", { name: "清空搜索" }).click();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-001")).toBeVisible();
    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect(page.getByTestId("candidate-group-unpaired-row:iv-large-202603-066")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    await page.getByTestId("candidate-group-unpaired-row:oa-large-202603-064").getByRole("cell").first().click();
    await page.getByTestId("candidate-group-unpaired-row:iv-large-202603-066").getByRole("cell").first().click();
    await expect(openZone.getByText("已选 3")).toBeVisible();
    const confirmButton = openZone.getByRole("button", { name: "确认关联" });
    await expect(confirmButton).toBeEnabled();
    await expectVisibleAndUncovered(confirmButton, "open zone confirm button after filtering");
    await expect(openZone.getByText("已选 3")).toBeVisible();
    await expect(openZone.getByText(/带入/)).toHaveCount(0);
    await expect(confirmButton).toBeEnabled();

    const bankFooter = page.getByTestId("pane-scrollbar-unpaired-bank");
    const bankHeader = page.getByTestId("pane-scroll-head-unpaired-bank");
    const bankRow = page.getByTestId("candidate-scroll-unpaired-row:bk-large-202603-065-bank");
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

    await expect(openZone.getByRole("alert")).toContainText("自动加载下一页失败，请重试。");
    expect(api.count("GET /api/workbench/groups")).toBe(1);
    await page.waitForTimeout(500);
    expect(api.count("GET /api/workbench/groups")).toBe(1);

    await openZone.getByRole("button", { name: "重试自动加载" }).click();
    await expect(page.getByTestId("candidate-group-unpaired-row:oa-large-202603-064")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBe(2);
    await expect(openZone.getByRole("alert")).toHaveCount(0);
  });
});
