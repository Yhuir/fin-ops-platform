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
  const names = ['银行账户', 'OA导入设置', 'OA申请人凭据', '访问账户', '数据重置'];
  for (const name of names) await page.getByRole('tab', { name, exact: true }).click();
  const samples: { width: number; tab: string; durationMs: number; top: number; right: number | null }[] = [];
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
      await page.screenshot({ path: testInfo.outputPath(`production-settings-${width}-${index}.png`) });
    }
  }
  expect(mutations).toEqual([]);
  expect(reads.length).toBe(readCount);
  writeFileSync(testInfo.outputPath('production-settings-measurements.json'), JSON.stringify({ samples, additionalRequests: reads.length - readCount, mutations }, null, 2));
});
