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

async function scrollToTableBottom(pageLocator: Locator) {
  await expect(pageLocator).toBeVisible();
  const scrollTop = await pageLocator.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return element.scrollTop;
  });
  expect(scrollTop).toBeGreaterThan(0);
}

async function scrollTableHorizontally(tableScroll: Locator) {
  await expect(tableScroll).toBeVisible();
  const scrollLeft = await tableScroll.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return element.scrollLeft;
  });
  expect(scrollLeft).toBeGreaterThan(0);
}

test.describe("bank details large table and overlay browser flow", () => {
  test("keeps long rows, horizontal scroll, filters, export menu, and category popover usable on desktop and narrow viewports", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 820 });
    await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "unmatched",
      bankDetailsLargeDataset: true,
      sessionMode: "full_access",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByText("1-100 / 120")).toBeVisible();
    await expect(page.getByRole("row", { name: /长字段浏览器供应商120有限公司/ })).toBeVisible();

    const tableContainer = page.locator(".bank-transaction-table-container");
    await scrollToTableBottom(tableContainer);
    await expectVisibleAndUncovered(page.getByLabel("下一页"), "desktop next-page button");
    await expectVisibleAndUncovered(page.getByRole("button", { name: "导出" }), "desktop export button");

    await page.getByRole("button", { name: /标签筛选/ }).click();
    const filterMenu = page.getByRole("menu", { name: "银行明细标签筛选" });
    await expectVisibleAndUncovered(filterMenu, "desktop category filter menu");
    await expect(filterMenu.getByRole("menuitem", { name: /设备款 119/ })).toBeVisible();
    await page.keyboard.press("Escape");

    const firstRow = page.getByRole("row", { name: /智能工厂设备商/ });
    await firstRow.getByRole("button", { name: "待分类" }).click();
    const categoryMenu = page.getByRole("menu", { name: "待分类主标签" });
    await expectVisibleAndUncovered(categoryMenu, "desktop category assignment menu");
    await expect(categoryMenu.getByRole("menuitem", { name: "外部往来款付款" })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.setViewportSize({ width: 390, height: 820 });
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expectVisibleAndUncovered(page.getByRole("button", { name: "导出" }), "narrow export button");

    await page.getByRole("button", { name: "导出" }).click();
    const exportMenu = page.getByRole("menu", { name: "导出银行明细" });
    await expectVisibleAndUncovered(exportMenu, "narrow export menu");
    await expect(exportMenu.getByRole("menuitem", { name: "导出全部银行" })).toBeVisible();
    await page.keyboard.press("Escape");

    const tableScroll = page.locator(".bank-transaction-table .finance-table__scroll");
    await scrollTableHorizontally(tableScroll);
    await expectVisibleAndUncovered(page.getByRole("columnheader", { name: "备注/附言/客户附言" }), "narrow rightmost table column");

    await page.getByRole("button", { name: /标签筛选/ }).click();
    const narrowFilterMenu = page.getByRole("menu", { name: "银行明细标签筛选" });
    await expectVisibleAndUncovered(narrowFilterMenu, "narrow category filter menu");
    await expect(narrowFilterMenu.getByRole("menuitem", { name: /设备款 119/ })).toBeVisible();
  });
});
