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
  const selected = views.getByRole("radio", { checked: true });
  await expect(selected).toHaveCSS("background-color", "rgb(29, 78, 216)");
  await expect(selected).toHaveCSS("box-shadow", "none");
  await expect(selected).toHaveCSS("height", "40px");
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
  await expect(control).toHaveCSS("background-color", "rgb(29, 78, 216)");
  const colors = await control.evaluate(el => Array.from(el.querySelectorAll("span, small, strong, svg")).filter(x => x.textContent?.trim() || x.tagName.toLowerCase() === "svg").map(x => getComputedStyle(x).color));
  expect(colors.every(color => color === "rgb(255, 255, 255)")).toBe(true);
}

for (const path of ["input-invoice-usage", "output-invoice-collections", "pending-invoices", "oa-pending-payments", "etc-tickets", "batch-accounting", "bank-flow-rule-batches", "turnover-ledger", "cost-statistics", "settings"]) {
  test(`high contrast selection and neutral siblings: ${path}`, async ({ page }, testInfo) => {
    await installDeterministicApiMocks(page, { sessionMode: "admin" });
    await page.goto(`/${path}`);
    if (["input-invoice-usage", "output-invoice-collections", "pending-invoices", "oa-pending-payments"].includes(path)) {
      const panel = page.locator(".invoice-usage-classification, .table-classification");
      const selected = panel.locator('.classification-choice[aria-pressed="true"]').first();
      await expect(selected).toBeVisible();
      await expect(selected).toHaveCSS("box-shadow", /inset/);
      await expect(selected.locator(".classification-choice__check")).toHaveCSS("visibility", "visible");
      const buttons = panel.locator("button.classification-choice");
      const siblingIndex = await buttons.evaluateAll(items => items.findIndex(item => item.getAttribute("aria-pressed") === "false"));
      expect(siblingIndex).toBeGreaterThanOrEqual(0);
      const sibling = buttons.nth(siblingIndex);
      const before = await sibling.evaluate(element => ({ color: getComputedStyle(element).color, background: getComputedStyle(element).backgroundColor }));
      await expect(sibling.locator(".classification-choice__check")).toHaveCSS("visibility", "hidden");
      await sibling.hover();
      await expect(sibling).toHaveCSS("color", before.color); await expect(sibling).toHaveCSS("background-color", before.background);
      await sibling.click(); await expect(sibling).toHaveAttribute("aria-pressed", "true");
      await expect(sibling).toHaveCSS("box-shadow", /inset/); await expect(sibling.locator(".classification-choice__check")).toHaveCSS("visibility", "visible");
      await expect(sibling).toHaveCSS("background-color", before.background);
      await page.screenshot({ path: testInfo.outputPath(`contrast-${path}.png`), animations: "disabled" });
      return;
    }
    const controls = page.locator('.app-segments [data-selected="true"], .invoice-count-segments [data-selected="true"]');
    await expect(controls.first()).toBeVisible();
    for (const control of await controls.all()) {
      if (path === "turnover-ledger") {
        await expect(control).toHaveCSS("color", "rgb(29, 78, 216)");
        await expect(control).toHaveCSS("border-bottom-color", "rgb(29, 78, 216)");
        await expect(control).toHaveCSS("border-bottom-width", "2px");
        await expect(control).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
      } else await expectSelectedContrast(control);
    }
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

for (const path of ['oa-pending-payments', 'input-invoice-usage', 'pending-invoices']) {
  test(`scope and subordinate controls share the result surface: ${path}`, async ({ page }, info) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`/${path}`);
    const classification = page.locator(".invoice-usage-classification, .table-classification");
    const owner = classification.locator("xpath=..");
    await expect(classification).toBeVisible();
    const table = owner.locator('[role="grid"], table[aria-label]').first();
    await expect(table).toBeVisible();
    const panelBox = await classification.boundingBox(); const tableBox = await owner.locator(".finance-table").first().boundingBox();
    expect(tableBox!.y).toBeGreaterThanOrEqual(panelBox!.y + panelBox!.height - 1);
    expect(tableBox!.y - (panelBox!.y + panelBox!.height)).toBeLessThanOrEqual(24);
    const groups = classification.locator('[role="group"]');
    expect(await groups.count()).toBe(2);
    const leaves = classification.locator('.table-classification__leaf, .invoice-usage-classification__child');
    expect(await leaves.count()).toBeGreaterThan(0);
    for (const leaf of await leaves.all()) {
      expect(await leaf.evaluate(element => element.closest('[role="group"]') !== null)).toBe(true);
      await expect(leaf).toHaveCSS("border-radius", "0px");
    }
    for (const width of [1440, 960, 390]) {
      await page.setViewportSize({ width, height: 900 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBe(true);
      await page.screenshot({ path: info.outputPath(`hierarchy-${path}-${width}.png`) });
    }
  });
}

test('unselected boundaries and compact count geometry survive digit changes', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.goto('/oa-pending-payments');
  const group = page.getByRole('group', { name: '已完成 OA', exact: true });
  await group.getByRole('button', { name: /^已完成 OA/ }).click();
  const first = group.locator('.table-classification__leaf').first();
  const second = group.locator('.table-classification__leaf').nth(1);
  await expect(first).toHaveAttribute('aria-pressed', 'false');
  await expect(second).toHaveAttribute('aria-pressed', 'false');
  const firstBox = await first.boundingBox(), secondBox = await second.boundingBox();
  expect(secondBox!.x - (firstBox!.x + firstBox!.width)).toBe(1);
  await expect(first.locator('.classification-choice__check')).toHaveCSS('visibility', 'hidden');
  await expect(second.locator('.classification-choice__check')).toHaveCSS('visibility', 'hidden');
  // Isolate the CSS contract from business counting: exercise the rendered count with wider values.
  const geometry = await first.evaluate(el => {
    const count = el.querySelector('.stable-count')!;
    const label = el.querySelector(':scope > span:not(.stable-count):not(.classification-choice__check)')!;
    return ['0条', '56条', '432条', '123456条'].map(value => {
      count.textContent = value;
      const button = el.getBoundingClientRect(), text = label.getBoundingClientRect(), number = count.getBoundingClientRect();
      return { width: button.width, height: button.height, gap: number.left - text.right,
        centreError: Math.abs((text.left + number.right) / 2 - (button.left + Number.parseFloat(getComputedStyle(el).paddingLeft) + button.right - Number.parseFloat(getComputedStyle(el).paddingRight)) / 2) };
    });
  });
  expect(new Set(geometry.map(x => x.width)).size).toBe(1);
  for (const item of geometry) { expect(item.gap).toBe(8); expect(item.centreError).toBeLessThanOrEqual(1); }
});

test('settings scope tabs retain consistent styling and show only active settings', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  await page.goto('/settings');
  const scope = page.getByRole('tablist', { name: '设置分类' });
  await expect(scope.getByRole('tab')).toHaveText(['银行账户', 'OA导入设置', '访问账户', '数据重置']);
  await expect(scope.getByRole('tab', { selected: true })).toHaveText('银行账户');
  await expect(scope.getByRole('tab', { selected: true })).toHaveCSS('height', '40px');
  await expect(page.getByRole('region', { name: '银行账户映射', exact: true })).toBeVisible();
  await scope.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await expect(scope.getByRole('tab', { selected: true })).toHaveText('OA导入设置');
  await expect(scope.getByRole('tab', { selected: true })).toHaveCSS('height', '40px');
  await expect(page.getByRole('region', { name: 'OA导入设置', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '银行账户映射', exact: true })).toHaveCount(0);
  await expect(scope.getByRole('tab', { name: /项目状态|待找发票筛选|冲账规则/ })).toHaveCount(0);
});
