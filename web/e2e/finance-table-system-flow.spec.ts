import { expect, test, type Locator, type Page } from "./fixtures/strictTest";

import { installDeterministicApiMocks } from "./fixtures/apiMocks";

function collectBrowserErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (error) => {
    errors.push(`pageerror: ${error.stack || error.message}`);
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      errors.push(`console.error: ${message.text()}`);
    }
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

test.describe("finance table system browser flow", () => {
  test("keeps shared wide tables horizontally scrollable and operations controls usable on narrow screens", async ({ page }) => {
    const errors = collectBrowserErrors(page);
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });

    await page.setViewportSize({ width: 390, height: 820 });
    await page.goto("/operations/app-health");

    await expect(page.getByRole("heading", { name: "数据与导入" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-recent-imports")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toHaveCount(0);
    await expect(page.getByTestId("app-health-runtime")).toHaveCount(0);
    await expectVisibleAndUncovered(page.getByRole("button", { name: "刷新", exact: true }), "AppHealth refresh button");

    const importTableScroll = page.getByTestId("app-health-recent-imports").locator(".finance-table__scroll");
    expect(await importTableScroll.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expectVisibleAndUncovered(page.getByRole("columnheader", { name: "操作" }), "rightmost import-record column");
    await expectVisibleAndUncovered(page.getByRole("button", { name: "导入历史", exact: true }), "import-history entry");
    await expect(page.getByText("正在加载系统状态。")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);

    await page.goto("/settings");
    await page.getByRole("tab", { name: "OA导入设置", exact: true }).click();
    const oaTable = page.getByRole("grid", { name: "OA全量搜索导入结果" });
    await expectHorizontalScroll(page.locator(".oa-manual-import__table .finance-table__scroll"), "wide OA search table");
    await expectVisibleAndUncovered(oaTable.getByRole("columnheader").last(), "rightmost OA search column");
    expect(errors).toEqual([]);
  });
});
