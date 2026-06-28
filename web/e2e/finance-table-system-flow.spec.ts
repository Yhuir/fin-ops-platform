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

    await expect(page.getByRole("heading", { name: "AppHealth 运维状态" })).toBeVisible();
    await expect(page.getByTestId("app-health-data")).toBeVisible();
    await expect(page.getByTestId("app-health-requests")).toBeVisible();
    await expect(page.getByTestId("app-health-runtime")).toBeVisible();
    await expectVisibleAndUncovered(page.getByRole("button", { name: "刷新" }), "AppHealth refresh button");

    const requestTableScroll = page.getByTestId("app-health-requests").locator(".finance-table__scroll");
    await expectHorizontalScroll(requestTableScroll, "request performance table");
    await expectVisibleAndUncovered(page.getByRole("columnheader", { name: "连接 p95" }), "rightmost request-performance column");
    await expect(page.getByRole("row", { name: /\/api\/session\/me/ })).toContainText("45 ms");

    await expect(page.getByRole("columnheader", { name: "Worker" })).toBeVisible();
    await expect(page.getByRole("row", { name: /workbench-read-model/ })).toContainText("1 s");
    await expect(page.getByText("正在加载系统状态。")).toHaveCount(0);
    expect(api.count("GET /api/operations/app-health-dashboard")).toBeGreaterThan(0);
    expect(errors).toEqual([]);
  });
});
