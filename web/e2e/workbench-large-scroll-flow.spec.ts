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
  const scrollLeft = await scrollbar.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
    element.dispatchEvent(new Event("scroll", { bubbles: true }));
    return element.scrollLeft;
  });
  expect(scrollLeft).toBeGreaterThan(0);
  return scrollLeft;
}

test.describe("workbench large dataset browser flow", () => {
  test("keeps pagination, search, tri-pane scroll, detail drawer, and selection controls usable", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    const api = await installDeterministicApiMocks(page, {
      sessionMode: "full_access",
      workbenchLargeDataset: true,
    });

    await page.goto("/");

    const openZone = page.getByTestId("zone-unpaired");
    await expect(openZone.getByText("已加载 200 / 205")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-case:CASE-LARGE-202603-001")).toBeVisible();

    await openZone.locator(".candidate-grid-body").evaluate((element) => {
      element.scrollTop = element.scrollHeight;
      element.dispatchEvent(new Event("scroll", { bubbles: true }));
    });
    await expectVisibleAndUncovered(openZone.getByRole("button", { name: "加载更多" }), "open zone load-more button");
    await openZone.getByRole("button", { name: "加载更多" }).click();
    await expect(openZone.getByText("已加载 205 / 205")).toBeVisible();
    expect(api.count("GET /api/workbench/groups")).toBeGreaterThanOrEqual(3);

    await openZone.getByRole("button", { name: "搜索 银行流水" }).click();
    await page.getByRole("searchbox", { name: "搜索 银行流水" }).fill("长列表供应商065");
    const targetGroup = page.getByTestId("candidate-group-unpaired-case:CASE-LARGE-202603-065");
    await expect(targetGroup).toBeVisible();
    await expect(openZone.getByText("已加载 1 / 1")).toBeVisible();
    await expect(page.getByTestId("candidate-group-unpaired-case:CASE-LARGE-202603-001")).toHaveCount(0);

    await targetGroup.getByRole("row", { name: /大数据申请人065/ }).click();
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await expect(openZone.getByText("带入 2")).toBeVisible();
    const confirmButton = openZone.getByRole("button", { name: "确认关联" });
    await expect(confirmButton).toBeEnabled();
    await expectVisibleAndUncovered(confirmButton, "open zone confirm button after filtering");

    await targetGroup.getByRole("button", { name: "查看银行流水 长列表供应商065有限公司 详情" }).click();
    const detailDrawer = page.getByRole("dialog", { name: "银行流水详情" });
    await expect(detailDrawer.getByText("银行流水详情", { exact: true })).toBeVisible();
    await expect(detailDrawer.getByText("第65组银行流水详情")).toBeVisible();
    await expectVisibleAndUncovered(detailDrawer.getByRole("button", { name: "关闭详情抽屉" }), "detail drawer close button");
    await detailDrawer.getByRole("button", { name: "关闭详情抽屉" }).click();
    await expect(detailDrawer).toHaveCount(0);
    await expect(page.locator(".finance-drawer__content")).toHaveCount(0);
    await expect(openZone.getByText("已选 1")).toBeVisible();
    await expect(openZone.getByText("带入 2")).toBeVisible();
    await expect(confirmButton).toBeEnabled();

    const bankFooter = page.getByTestId("pane-scrollbar-unpaired-bank");
    const bankHeader = page.getByTestId("pane-scroll-head-unpaired-bank");
    const bankRow = page.getByTestId("candidate-scroll-unpaired-case:CASE-LARGE-202603-065-bank");
    const scrollLeft = await scrollPaneHorizontally(bankFooter);
    await expect.poll(() => bankHeader.evaluate((element) => element.scrollLeft)).toBe(scrollLeft);
    await expect.poll(() => bankRow.evaluate((element) => element.scrollLeft)).toBe(scrollLeft);
    await expectVisibleAndUncovered(confirmButton, "open zone confirm button after horizontal scroll");
  });
});
