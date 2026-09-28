import { expect, test } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

// UI-SEG-01..04: docs/ui.md. Synthetic API only.
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
  expect(indicator.background).toBe("rgb(29, 78, 216)"); expect(indicator.shadow).toBe("none"); expect(indicator.height).toBe(36);
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


// All four presentation owners must expose the same high-contrast selection.
async function expectSelectedContrast(control: import("@playwright/test").Locator) {
  await expect(control).toHaveCSS("color", "rgb(255, 255, 255)");
  const indicator = control.locator('[data-slot="tabs-indicator"]');
  if (await indicator.count()) await expect(indicator).toHaveCSS("background-color", "rgb(29, 78, 216)");
  else await expect(control).toHaveCSS("background-color", "rgb(29, 78, 216)");
  const colors = await control.evaluate(el => Array.from(el.querySelectorAll("span, small, strong, svg")).filter(x => x.textContent?.trim() || x.tagName.toLowerCase() === "svg").map(x => getComputedStyle(x).color));
  expect(colors.every(color => color === "rgb(255, 255, 255)")).toBe(true);
}

for (const path of ["input-invoice-usage", "output-invoice-collections", "pending-invoices", "oa-pending-payments", "etc-tickets", "batch-accounting", "bank-flow-rule-batches", "turnover-ledger", "cost-statistics", "settings"]) {
  test(`high contrast selection and neutral siblings: ${path}`, async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.goto(`/${path}`);
    const controls = page.locator('.app-segments [data-selected="true"], .invoice-count-segments [data-selected="true"]');
    await expect(controls.first()).toBeVisible();
    for (const control of await controls.all()) await expectSelectedContrast(control);
    const sibling = page.locator('.app-segments [role="radio"]:not([data-selected="true"]), .app-segments [role="tab"]:not([data-selected="true"]), .invoice-count-segments [role="tab"]:not([data-selected="true"])').first();
    await expect(sibling).toHaveCSS("color", "rgb(71, 85, 105)");
    await sibling.hover();
    await expect(sibling).toHaveCSS("color", "rgb(71, 85, 105)");
    await page.screenshot({ path: testInfo.outputPath(`contrast-${path}.png`), animations: "disabled" });
  });
}

test("period selection distinguishes browsing from applied date and retains visible focus", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  await page.goto("/cost-statistics");
  await expect(page.getByRole("heading", { name: "按项目统计" })).toBeVisible();
  const picker = page.getByRole("group", { name: "成本统计时间范围", exact: true });
  const all = picker.getByRole("button", { name: "全部", exact: true });
  await expectSelectedContrast(all);
  const trigger = page.getByRole("button", { name: /成本统计时间范围：/ });
  await trigger.click();
  const mode = page.getByRole("radiogroup", { name: /粒度$/ });
  await mode.getByRole("radio", { name: "按月" }).click();
  await expectSelectedContrast(mode.getByRole("radio", { checked: true }));
  const dialog = page.getByRole("dialog", { name: "成本统计时间范围选择器" });
  const year = dialog.locator('[data-browsed="true"]');
  await expect(year).toHaveAttribute("aria-pressed", "false");
  await expect(year).not.toHaveCSS("background-color", "rgb(29, 78, 216)");
  await expectSelectedContrast(all);
  await dialog.getByRole("button", { name: "一月", exact: true }).click();
  await expectSelectedContrast(trigger);
  await expect(all).toHaveAttribute("aria-pressed", "false");
  await trigger.click();
  await expectSelectedContrast(dialog.getByRole("button", { name: "一月", exact: true }));
  await page.keyboard.press("Escape");
  await trigger.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveCSS("outline-color", "rgb(255, 255, 255)");
  await page.screenshot({ path: testInfo.outputPath("contrast-period-focus.png"), animations: "disabled" });
});

test("reverse OA tabs keep high contrast during hover and keyboard switching", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/input-invoice-usage");
  await page.getByRole("button", { name: "以发票反提 OA", exact: true }).click();
  const tabs = page.getByRole("tablist", { name: "反提 OA 状态" });
  for (const name of ["待处理", "暂存", "已提交"]) {
    const tab = tabs.getByRole("tab", { name, exact: true });
    await tab.click(); await tab.hover();
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expectSelectedContrast(tab);
  }
  await tabs.getByRole("tab", { name: "已提交", exact: true }).press("ArrowLeft");
  const focused = tabs.getByRole("tab", { name: "暂存", exact: true });
  await expect(focused).toBeFocused();
  await expect(focused).toHaveCSS("outline-style", "solid");
  await page.screenshot({ path: testInfo.outputPath("contrast-reverse-tabs.png"), animations: "disabled" });
});
