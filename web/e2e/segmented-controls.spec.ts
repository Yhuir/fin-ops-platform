import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

// UI-SEG-01..04: docs/dev/segmented-controls.md. Synthetic API only.
test("continuous native controls keep one cost view, no reselection read, and contained narrow geometry", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  const reads: string[] = [];
  page.on("request", request => { if (request.url().includes("/cost-statistics/explorer")) reads.push(request.url()); });
  await page.goto("/cost-statistics");
  await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
  const views = page.getByRole("group", { name: "成本统计视图切换", exact: true });
  await expect(views.getByRole("radio", { checked: true })).toHaveCount(1);
  const before = reads.length;
  await page.getByRole("radio", { name: "按项目", exact: true }).click();
  expect(reads.length).toBe(before);
  await page.getByRole("radio", { name: "按时间", exact: true }).click();
  await expect(page.getByRole("heading", { name: "按时间统计" })).toBeVisible();
  await expect(views.getByRole("radio", { checked: true })).toHaveCount(1);
  await expect(views.locator('[data-slot="tabs-indicator"]')).toHaveCount(1);
  const indicator = await views.locator('[data-slot="tabs-indicator"]').evaluate(el => ({ background: getComputedStyle(el).backgroundColor, shadow: getComputedStyle(el).boxShadow, height: el.getBoundingClientRect().height }));
  expect(indicator.background).toBe("rgb(232, 240, 255)"); expect(indicator.shadow).toBe("none"); expect(indicator.height).toBe(36);
  for (const width of [1600, 960, 390]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`segments-cost-${width}.png`), animations: "disabled" });
  }
});

test("dynamic native invoice tabs preserve drafts by ID and keyboard selection without requests", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.goto("/imports/invoices");
  await page.getByRole("button", { name: "发票录入", exact: true }).click();
  const drawer = page.getByRole("dialog");
  await drawer.getByRole("textbox", { name: "销方名称", exact: true }).fill("草稿一");
  await drawer.getByRole("button", { name: "添加发票" }).click();
  await drawer.getByRole("textbox", { name: "销方名称", exact: true }).fill("草稿二");
  let writes = 0; page.on("request", request => { if (request.method() !== "GET") writes++; });
  const first = drawer.getByRole("tab", { name: "新发票1", exact: true });
  await first.click();
  await expect(drawer.getByRole("textbox", { name: "销方名称", exact: true })).toHaveValue("草稿一");
  await first.press("ArrowRight");
  await expect(drawer.getByRole("tab", { name: "新发票2", exact: true })).toHaveAttribute("aria-selected", "true");
  await expect(drawer.getByRole("textbox", { name: "销方名称", exact: true })).toHaveValue("草稿二");
  expect(writes).toBe(0);
});

test("date granularity changes only its panel until an actual date is chosen", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.goto("/cost-statistics");
  await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
  const requests: string[] = [];
  page.on("request", request => { if (request.url().includes("/cost-statistics/explorer")) requests.push(request.url()); });
  await page.getByRole("button", { name: /成本统计时间范围：年月/ }).click();
  const group = page.getByRole("radiogroup", { name: /粒度$/ });
  await group.getByRole("radio", { name: "按月" }).click();
  await expect(group.getByRole("radio", { name: "按月" })).toHaveAttribute("aria-checked", "true");
  expect(requests).toHaveLength(0);
});
