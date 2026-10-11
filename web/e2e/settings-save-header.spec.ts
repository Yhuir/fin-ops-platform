import { expect, test, type Page } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test.use({ video: 'on' });

async function geometry(page: Page) {
  return page.evaluate(() => {
    const rect = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing layout element: ${selector}`);
      const { x, y, width, height } = element.getBoundingClientRect();
      return { x, y, width, height };
    };
    return { header: rect('.settings-content-header'), tabs: rect('.settings-tabs [role=tablist]'), button: rect('.settings-primary-save') };
  });
}

test("all settings save actions share a stable desktop header and switching does not fetch", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/workbench/settings')) requests.push(request.url()); });
  await page.goto('/settings');
  await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeVisible();
  // Visit each panel once so initial requests and lazy modules have settled.
  const tabs = ['银行账户', 'OA导入设置', '访问账户', '数据重置'];
  for (const name of tabs) await page.getByRole('tab', { name, exact: true }).click();
  const initialRequests = requests.length;
  for (const width of [1920, 1440, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole('tab', { name: '银行账户', exact: true }).click();
    await expect(page.getByRole('tab', { name: '银行账户', exact: true })).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeVisible();
    const baseline = await geometry(page);
    for (const name of [...tabs, '批量账务']) {
      const bounds = await page.getByRole('tab', { name, exact: true }).boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(baseline.tabs.x);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(baseline.tabs.x + baseline.tabs.width);
    }
    for (const [index, name] of tabs.entries()) {
      await page.getByRole('tab', { name, exact: true }).click();
      await expect(page.getByRole('tab', { name, exact: true })).toHaveAttribute('aria-selected', 'true');
      const header = page.getByRole('group', { name: '当前设置操作' });
      if (name === '数据重置') {
        await expect(header.getByRole('button')).toHaveCount(0);
        expect((await page.locator('.settings-tabs [role=tablist]').boundingBox())?.y).toBe(baseline.tabs.y);
      } else {
        const current = await geometry(page);
        expect(current).toEqual(baseline);
        await expect(page.getByRole('tabpanel').getByRole('button', { name: /^保存/ })).toHaveCount(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.evaluate(async () => {
        await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished));
      });
      await page.screenshot({ path: testInfo.outputPath(`settings-${width}-${index}.png`) });
    }
  }
  expect(requests.length).toBe(initialRequests);
});

test("settings stays contained on narrow screens, supports keyboard navigation and cancels drafts without writes", async ({ page }, testInfo) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  await page.goto('/settings');
  const name = page.getByRole('textbox', { name: / 银行名称$/ }).first();
  const savedName = await name.inputValue();
  await name.fill('云南源采财务运营平台长银行名称草稿');
  await page.getByLabel('银行名称', { exact: true }).fill('尚未添加的银行');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  const date = page.getByLabel('OA导入起始日期');
  const savedDate = await date.inputValue();
  await date.fill('2026-02-01');
  await page.getByRole('tab', { name: '批量账务', exact: true }).click();
  await expect(page.getByRole('grid', { name: '批量账务历史记录' })).toBeVisible();
  await expect(page.locator('.settings-tab-draft')).toHaveCount(2);
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  await expect(name).toHaveValue('云南源采财务运营平台长银行名称草稿');
  for (const width of [1920, 1440, 1280, 900, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole('button', { name: '取消修改' })).toBeInViewport();
    await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeInViewport();
    await page.screenshot({ path: testInfo.outputPath(`settings-draft-${width}.png`) });
  }
  await page.getByRole('button', { name: '取消修改' }).click();
  await expect(name).toHaveValue(savedName);
  await expect(page.getByLabel('银行名称', { exact: true })).toHaveValue('');
  await expect(page.locator('.settings-tab-draft')).toHaveCount(0);
  const bankTab = page.getByRole('tab', { name: '银行账户', exact: true });
  await bankTab.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.getByRole('tab', { name: 'OA导入设置', exact: true })).toBeFocused();
  await expect(date).toHaveValue(savedDate);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  expect(await page.locator('.settings-workspace').evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(api.calls.filter(call => /^(POST|PUT|DELETE)/.test(call))).toEqual([]);
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.locator('body').evaluate(el => { el.style.zoom = '2'; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('settings-200-percent.png') });
});

test("settings no longer loads or exposes applicant credentials", async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: "admin" });
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "保存设置", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "OA申请人凭据" })).toHaveCount(0);
  expect(api.calls.some(call => call.includes("oa-applicant-credentials"))).toBe(false);
});

test("ordinary save freezes its two draft panels, keeps errors and saves the exact draft on retry", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  let finish: (() => void) | undefined;
  let writes = 0;
  let savedSettings: Record<string, unknown> & { oa_import: Record<string, unknown> };
  await page.route('**/api/workbench/settings', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    writes += 1;
    const body = route.request().postDataJSON();
    expect(body.oa_retention.cutoff_date).toBe('2026-02-01');
    expect(body).not.toHaveProperty('accounts');
    expect(body).not.toHaveProperty('oa_applicant_credentials');
    if (writes === 1) {
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ status: 400, json: { error: 'invalid_settings', message: '测试设置被拒绝' } });
    }
    savedSettings = { ...savedSettings, ...body, oa_import: { ...savedSettings.oa_import, ...body.oa_import } };
    return route.fulfill({ json: savedSettings });
  });
  const initialSettings = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workbench/settings' && response.request().method() === 'GET');
  await page.goto('/settings');
  savedSettings = await (await initialSettings).json();
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await page.getByLabel('OA导入起始日期').fill('2026-02-01');
  const before = await geometry(page);
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByLabel('OA导入起始日期')).toBeDisabled();
  expect(await geometry(page)).toEqual(before);
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  await expect(page.getByLabel('银行名称', { exact: true })).toBeDisabled();
  await expect.poll(() => writes).toBe(1);
  finish!();
  await expect(page.getByRole('alert')).toContainText('保存设置失败：操作失败，请稍后重试。');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await expect(page.getByLabel('OA导入起始日期')).toHaveValue('2026-02-01');
  expect(await geometry(page)).toEqual(before);
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByText('已保存银行账户与 OA 导入设置。', { exact: true })).toBeVisible();
  await expect(page.getByText('有未保存修改', { exact: true })).toHaveCount(0);
  expect(writes).toBe(2);
  await expectNoUnexpectedSuccessUiErrors(page);
});
