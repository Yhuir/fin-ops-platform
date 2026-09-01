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

async function readCategoryMenuMetrics(menu: Locator) {
  return menu.evaluate(async (element) => {
    const panel = element.closest(".bank-category-filter-panel");
    await Promise.allSettled(panel?.getAnimations({ subtree: true }).map((animation) => animation.finished) ?? []);
    const rect = element.getBoundingClientRect();
    const styles = getComputedStyle(element);
    const primaryLabel = element.querySelector<HTMLElement>(".bank-category-filter-primary-row .bank-category-filter-label");
    const childLabel = element.querySelector<HTMLElement>(".bank-category-filter-child-row .bank-category-filter-label");
    const count = element.querySelector<HTMLElement>(".bank-category-filter-count");
    const row = element.querySelector<HTMLElement>(".bank-category-filter-row");
    const groups = Array.from(element.querySelectorAll<HTMLElement>(".bank-category-filter-group"));
    return {
      childFontSize: childLabel ? Number.parseFloat(getComputedStyle(childLabel).fontSize) : 0,
      columns: styles.columnCount,
      countFontSize: count ? Number.parseFloat(getComputedStyle(count).fontSize) : 0,
      groupCount: groups.length,
      groupsWithinViewport: groups.every((group) => {
        const groupRect = group.getBoundingClientRect();
        return groupRect.left >= 0
          && groupRect.right <= window.innerWidth
          && groupRect.top >= 0
          && groupRect.bottom <= window.innerHeight;
      }),
      hasInternalVerticalScroll: element.scrollHeight > element.clientHeight + 1,
      overflowY: styles.overflowY,
      primaryFontSize: primaryLabel ? Number.parseFloat(getComputedStyle(primaryLabel).fontSize) : 0,
      rect: {
        bottom: rect.bottom,
        height: rect.height,
        left: rect.left,
        right: rect.right,
        top: rect.top,
        width: rect.width,
      },
      rowHeight: row?.getBoundingClientRect().height ?? 0,
      withinViewport: rect.left >= 0 && rect.right <= window.innerWidth && rect.top >= 0 && rect.bottom <= window.innerHeight,
    };
  });
}

test.describe("bank details large table and overlay browser flow", () => {
  test("keeps long rows, horizontal scroll, filters, export menu, and category popover usable on desktop and narrow viewports", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 820 });
    await installDeterministicApiMocks(page, {
      bankDetailsClassificationMode: "unmatched",
      bankDetailsDenseCategoryMenu: true,
      bankDetailsLargeDataset: true,
      sessionMode: "user",
    });

    await page.goto("/bank-details");
    await expect(page.getByTestId("bank-details-page")).toBeVisible();
    await expect(page.getByText("1-100 / 120")).toBeVisible();
    await expect(page.getByRole("row", { name: /长字段浏览器供应商120有限公司/ })).toBeVisible();

    const tableContainer = page.locator(".bank-transaction-table-container");
    const tableScroll = page.locator(".bank-transaction-table .finance-table__scroll");
    await scrollToTableBottom(tableScroll);
    await expectVisibleAndUncovered(page.getByLabel("下一页"), "desktop next-page button");
    await expectVisibleAndUncovered(page.getByRole("button", { name: "导出" }), "desktop export button");

    await tableScroll.evaluate((element) => {
      element.scrollTop = 0;
    });
    await page.getByRole("button", { name: /标签筛选/ }).click();
    const filterMenu = page.getByRole("listbox", { name: "银行明细标签筛选" });
    await expect(filterMenu).toBeVisible();
    await expect(filterMenu.getByRole("option", { name: /设备款 119/ })).toBeVisible();
    const desktopMenuMetrics = await readCategoryMenuMetrics(filterMenu);
    expect(desktopMenuMetrics).toMatchObject({
      childFontSize: 13,
      columns: "4",
      countFontSize: 12,
      groupsWithinViewport: true,
      hasInternalVerticalScroll: false,
      overflowY: "visible",
      primaryFontSize: 14,
      withinViewport: true,
    });
    expect(desktopMenuMetrics.groupCount).toBeGreaterThanOrEqual(10);
    expect(desktopMenuMetrics.rowHeight).toBeGreaterThanOrEqual(31.5);

    const menuBox = await filterMenu.boundingBox();
    const tableBox = await tableContainer.boundingBox();
    expect(menuBox).not.toBeNull();
    expect(tableBox).not.toBeNull();
    const outsidePoint = await page.evaluate(({ menu, table }) => {
      const candidates = [
        { x: table.x + 4, y: table.y + table.height / 2 },
        { x: table.x + table.width - 4, y: table.y + table.height / 2 },
        { x: table.x + table.width / 2, y: table.y + 4 },
        { x: table.x + table.width / 2, y: table.y + table.height - 4 },
      ];
      return candidates.find((point) => (
        point.x >= 0
          && point.x < window.innerWidth
          && point.y >= 0
          && point.y < window.innerHeight
          && !(point.x >= menu.x && point.x <= menu.x + menu.width && point.y >= menu.y && point.y <= menu.y + menu.height)
      )) ?? null;
    }, { menu: menuBox!, table: tableBox! });
    expect(outsidePoint).not.toBeNull();
    await page.mouse.move(outsidePoint!.x, outsidePoint!.y);
    await tableScroll.evaluate((element) => {
      element.scrollTop = 520;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expect.poll(() => tableScroll.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    await expect(filterMenu).toBeVisible();
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
    await expect(exportMenu).toBeHidden();

    await scrollTableHorizontally(tableScroll);
    await expectVisibleAndUncovered(page.getByRole("columnheader", { name: "备注/附言/客户附言" }), "narrow rightmost table column");

    await page.getByRole("button", { name: /标签筛选/ }).click();
    const narrowFilterMenu = page.getByRole("listbox", { name: "银行明细标签筛选" });
    await expect(narrowFilterMenu).toBeVisible();
    await expect(narrowFilterMenu.getByRole("option", { name: /设备款 119/ })).toBeVisible();
    const narrowMenuMetrics = await readCategoryMenuMetrics(narrowFilterMenu);
    expect(narrowMenuMetrics.columns).toBe("auto");
    expect(narrowMenuMetrics.hasInternalVerticalScroll).toBe(true);
    expect(narrowMenuMetrics.withinViewport, JSON.stringify(narrowMenuMetrics)).toBe(true);
  });
});
