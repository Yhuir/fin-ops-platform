import { expect, test } from './fixtures/strictTest';
import { expectNoUnexpectedSuccessUiErrors } from './fixtures/successAssertions';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off' });

test('production grouped rules preserve persisted contract and discard local edits without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/*', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto('/fin-ops/input-invoice-usage');
  await expect(page.getByRole('region', { name: '进项发票使用分类' })).toHaveAttribute('aria-busy', 'false');
  const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/input-invoice-usage/payment-status-rules'));
  if (await page.getByRole('button', { name: '更多页面操作' }).isVisible()) await page.getByRole('button', { name: '更多页面操作' }).click();
  await page.getByRole('button', { name: '发票与支付状态规则设置' }).click();
  const payload = await (await response).json();
  for (const rule of payload.rules) {
    expect(rule).not.toHaveProperty('priority');
    expect(typeof rule.conditions.hasBank).toBe('boolean');
    expect(rule.conditions).not.toHaveProperty('fullyMatched');
    expect(rule.conditions).not.toHaveProperty('invoiceOaAmountMatched');
  }
  const drawer = page.getByRole('dialog', { name: '发票与支付状态规则设置' });
  await expect(drawer.getByRole('columnheader')).toHaveText(['付款状态', '启用', '规则', 'OA 申请人', '是否有流水', '发票 VS 流水', '发票净额（正数票+负数票）', '操作']);
  await expect(drawer.getByRole('checkbox')).toHaveCount(payload.rules.length);
  await expect(drawer.getByRole('button', { name: /复制|重新加载|上移|下移/ })).toHaveCount(0);
  await expect(drawer.locator('[data-slot="select-indicator"]')).toHaveCount(0);
  for (const [hasBank, group] of [[true, 'paid'], [false, 'unpaid']] as const) {
    await expect(drawer.locator(`.payment-rule-group--${group}`)).toHaveCount(payload.rules.filter((r: { conditions: { hasBank: boolean } }) => r.conditions.hasBank === hasBank).length);
  }
  for (const width of [1920, 1440, 1024]) {
    await page.setViewportSize({ width, height: 1080 });
    expect(await drawer.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    await expect(drawer.getByRole('button', { name: '保存', exact: true })).toBeDisabled();
    await page.screenshot({ path: info.outputPath(`production-payment-rules-${width}.png`), animations: 'disabled' });
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  const firstCheckbox = drawer.getByRole('checkbox').first();
  const wasChecked = await firstCheckbox.isChecked();
  await drawer.locator('[data-slot="checkbox"]').first().click();
  await expect(firstCheckbox).toBeChecked({ checked: !wasChecked });
  await drawer.getByRole('button', { name: '还原', exact: true }).click();
  await expect(firstCheckbox).toBeChecked({ checked: wasChecked });
  await drawer.getByRole('button', { name: '关闭支付状态规则抽屉' }).click();
  await expect(drawer).toHaveCount(0);
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  await info.attach('production-payment-rule-contract', { body: JSON.stringify({ version: payload.version, rules: payload.rules.length, writes: writes.length, errors }), contentType: 'application/json' });
});
