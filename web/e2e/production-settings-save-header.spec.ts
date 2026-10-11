import { writeFileSync } from 'node:fs';
import { expect, test } from './fixtures/strictTest';
import { expectNoUnexpectedSuccessUiErrors } from './fixtures/successAssertions';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_OA_TOKEN ?? '';
test.use({ trace: 'off', video: 'off' });
test('production settings header keeps all save scopes reachable with no writes or extra reads', async ({ page, baseURL }, testInfo) => {
  test.skip(!enabled || !token, 'Requires the production read-only smoke environment.');
  const mutations: string[] = [];
  const reads: string[] = [];
  await page.route('**/*', async route => {
    const request = route.request();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      mutations.push(request.method());
      return route.abort('blockedbyclient');
    }
    if (new URL(request.url()).pathname.includes('/settings')) reads.push(new URL(request.url()).pathname);
    return route.continue();
  });
  await page.context().addCookies([{ name: 'Admin-Token', value: token,
    domain: new URL(baseURL!).hostname, path: '/', secure: true, sameSite: 'Lax' }]);
  await page.goto('/fin-ops/settings');
  await expect(page.getByRole('group', { name: '当前设置操作' })).toBeVisible();
  const names = ['银行账户', 'OA导入设置', '访问账户', '数据重置'];
  for (const name of names) await page.getByRole('tab', { name, exact: true }).click();
  const samples: { width: number; tab: string; durationMs: number; top: number; right: number | null }[] = [];
  const paintSamples: number[] = [];
  const readCount = reads.length;
  for (const width of [1920, 1440, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole('tab', { name: '银行账户', exact: true }).click();
    const origin = await page.getByRole('tablist', { name: '设置分类' }).boundingBox();
    const buttonOrigin = await page.getByRole('button', { name: '保存设置', exact: true }).boundingBox();
    for (const [index, name] of names.entries()) {
      const start = performance.now();
      await page.getByRole('tab', { name, exact: true }).click();
      await expect(page.getByRole('tabpanel', { name, exact: true })).toBeVisible();
      const durationMs = performance.now() - start;
      const tabs = await page.getByRole('tablist', { name: '设置分类' }).boundingBox();
      expect(tabs).toEqual(origin);
      const button = page.locator('.settings-primary-save');
      let right: number | null = null;
      if (name === '数据重置') {
        await expect(page.getByRole('group', { name: '当前设置操作' }).getByRole('button')).toHaveCount(0);
      } else {
        const bounds = await button.boundingBox();
        expect(bounds).toEqual(buttonOrigin);
        right = bounds!.x + bounds!.width;
      }
      await expect(page.getByRole('tabpanel').getByRole('button', { name: /^保存/ })).toHaveCount(0);
      await expectNoUnexpectedSuccessUiErrors(page);
      samples.push({ width, tab: name, durationMs, top: tabs!.y, right });
      await page.evaluate(async () => {
        await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished));
      });
      await page.screenshot({ path: testInfo.outputPath(`production-settings-${width}-${index}.png`) });
    }
  }
  expect(mutations).toEqual([]);
  expect(reads.length).toBe(readCount);
  // Event to the second animation frame, measured entirely inside the browser.
  // Does not include Playwright transport, screenshot time or transition completion.
  for (let cycle = 0; cycle < 10; cycle += 1) {
    for (const name of names) {
      const duration = await page.evaluate(async label => {
        const tab = Array.from(document.querySelectorAll<HTMLElement>('[role="tab"]')).find(el => el.textContent?.trim() === label);
        if (!tab) throw new Error(`Missing settings tab: ${label}`);
        const start = performance.now();
        tab.click();
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        if (tab.getAttribute('aria-selected') !== 'true') throw new Error('Settings tab did not commit');
        return performance.now() - start;
      }, name);
      paintSamples.push(duration);
    }
  }
  const sorted = [...paintSamples].sort((a, b) => a - b);
  const percentile = (p: number) => sorted[Math.ceil(sorted.length * p) - 1];
  const paintLatency = { n: sorted.length, p50: percentile(.5), p95: percentile(.95), p99: percentile(.99) };
  expect(paintLatency.p95).toBeLessThanOrEqual(100);
  expect(mutations).toEqual([]);
  expect(reads.length).toBe(readCount);
  writeFileSync(testInfo.outputPath('production-settings-measurements.json'), JSON.stringify({ samples, paintSamples, paintLatency, additionalRequests: reads.length - readCount, mutations }, null, 2));
});

test('production settings contains real rows, preserves drafts across history and cancels without persisting', async ({ page, baseURL }, testInfo) => {
  test.skip(!enabled || !token, 'Requires the production read-only smoke environment.');
  const mutations: string[] = [];
  await page.route('**/*', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      mutations.push(route.request().method());
      return route.abort('blockedbyclient');
    }
    return route.continue();
  });
  await page.context().addCookies([{ name: 'Admin-Token', value: token,
    domain: new URL(baseURL!).hostname, path: '/', secure: true, sameSite: 'Lax' }]);
  await page.goto('/fin-ops/settings');
  const savedRow = page.getByRole('textbox', { name: / 银行名称$/ }).first();
  const savedName = await savedRow.inputValue();
  const initialRows = await page.getByRole('textbox', { name: / 银行名称$/ }).count();
  expect(initialRows).toBeGreaterThan(0);
  await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeDisabled();
  await savedRow.fill(`${savedName}草稿`);
  await page.getByLabel('银行名称', { exact: true }).fill('尚未添加的银行');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  const date = page.getByLabel('OA导入起始日期');
  const savedDate = await date.inputValue();
  const draftDate = savedDate === '2026-02-01' ? '2026-02-02' : '2026-02-01';
  await date.fill(draftDate);
  await page.getByRole('tab', { name: '批量账务', exact: true }).click();
  await expect(page.getByRole('grid', { name: '批量账务历史记录' })).toBeVisible();
  await expect(page.locator('.settings-tab-draft')).toHaveCount(2);
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  await expect(savedRow).toHaveValue(`${savedName}草稿`);
  await expect(page.getByLabel('银行名称', { exact: true })).toHaveValue('尚未添加的银行');
  await page.getByRole('button', { name: '取消修改' }).click();
  await expect(savedRow).toHaveValue(savedName);
  await expect(page.getByLabel('银行名称', { exact: true })).toHaveValue('');
  await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeDisabled();
  await expect(page.locator('.settings-tab-draft')).toHaveCount(0);
  for (const width of [1920, 1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    const workspace = await page.locator('.settings-workspace').boundingBox();
    expect(workspace!.width).toBeLessThanOrEqual(1280);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeInViewport();
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished));
    });
    await page.screenshot({ path: testInfo.outputPath(`production-settings-real-${width}.png`) });
  }
  await page.setViewportSize({ width: 1280, height: 1000 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.locator('body').evaluate(el => { el.style.zoom = '2'; });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('production-settings-real-200-percent.png') });
  await page.reload();
  await expect(savedRow).toHaveValue(savedName);
  await expect(page.getByRole('textbox', { name: / 银行名称$/ })).toHaveCount(initialRows);
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await expect(date).toHaveValue(savedDate);
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(mutations).toEqual([]);
  writeFileSync(testInfo.outputPath('production-settings-chain.json'), JSON.stringify({ initialRows, draftsPreserved: true, cancellationRestored: true, persistedSettingsUnchanged: true, mutations }, null, 2));
});
