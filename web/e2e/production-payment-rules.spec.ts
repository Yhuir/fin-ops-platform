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
  const ruleResponse = await response;
  const payload = await ruleResponse.json();
  for (const rule of payload.rules) {
    expect(rule).not.toHaveProperty('priority');
    expect(typeof rule.conditions.hasBank).toBe('boolean');
    expect(rule.conditions).not.toHaveProperty('fullyMatched');
    expect(rule.conditions).not.toHaveProperty('invoiceOaAmountMatched');
  }
  const drawer = page.getByRole('dialog', { name: '发票与支付状态规则设置' });
  await expect(drawer.getByRole('columnheader')).toHaveText(['付款状态', '顺序', '启用', '规则', 'OA 申请人', '是否有流水', '发票 VS 流水', '发票净额（正数票+负数票）', '操作']);
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
  const ids = () => drawer.locator('.payment-rule-sortable-row').evaluateAll(nodes => nodes.map(node => node.getAttribute('data-key')));
  const savedIds = payload.rules.map((rule: { id: string }) => rule.id);
  const sortableGroup = [true, false].map(hasBank => payload.rules.filter((rule: { conditions: { hasBank: boolean } }) => rule.conditions.hasBank === hasBank)).find(group => group.length > 1);
  if (sortableGroup) {
    const handle = drawer.getByRole('button', { name: new RegExp(`调整规则 ${sortableGroup[1].label} 的顺序，当前第 2 条`) });
    await handle.focus();
    await expect(handle).toBeFocused();
    await page.keyboard.press('Space');
    await expect(handle).toHaveAttribute('aria-pressed', 'true');
    await page.keyboard.press('ArrowUp');
    await page.keyboard.press('Space');
    const expected = [...savedIds];
    const start = expected.indexOf(sortableGroup[0].id);
    [expected[start], expected[start + 1]] = [expected[start + 1], expected[start]];
    await expect.poll(ids).toEqual(expected);
    await drawer.getByRole('button', { name: '还原', exact: true }).click();
    await expect.poll(ids).toEqual(savedIds);
    const source = drawer.getByRole('button', { name: new RegExp(`调整规则 ${sortableGroup[1].label} 的顺序，当前第 2 条`) });
    const target = drawer.getByRole('button', { name: new RegExp(`调整规则 ${sortableGroup[0].label} 的顺序，当前第 1 条`) });
    await source.hover();
    const from = await source.boundingBox(); const to = await target.boundingBox();
    await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
    await page.mouse.down();
    await page.mouse.move(to!.x + to!.width / 2, to!.y + to!.height / 2, { steps: 12 });
    await page.mouse.up();
    await expect.poll(ids).toEqual(expected);
    await drawer.getByRole('button', { name: '还原', exact: true }).click();
    await expect.poll(ids).toEqual(savedIds);
  }
  const firstCheckbox = drawer.getByRole('checkbox').first();
  const wasChecked = await firstCheckbox.isChecked();
  await drawer.locator('[data-slot="checkbox"]').first().click();
  await expect(firstCheckbox).toBeChecked({ checked: !wasChecked });
  await drawer.getByRole('button', { name: '还原', exact: true }).click();
  await expect(firstCheckbox).toBeChecked({ checked: wasChecked });
  await drawer.getByRole('button', { name: '关闭支付状态规则抽屉' }).click();
  await expect(drawer).toHaveCount(0);
  const endpoint = new URL(ruleResponse.url());
  const get = async (path: string, params = new URLSearchParams()) => {
    endpoint.pathname = endpoint.pathname.replace(/\/(payment-status-rules|rows|export-summary|export)$/, `/${path}`);
    endpoint.search = params.toString();
    const result = await page.request.get(endpoint.toString());
    expect(result.status()).toBe(200);
    return result;
  };
  const all = await (await get('rows', new URLSearchParams({ page: '1', page_size: '200' }))).json();
  expect(all.classification.version).toBe(payload.version);
  const categoryChecks: Array<{ parent: string; code: string; rows: number; invoices: number }> = [];
  for (const group of all.classification.groups) {
    expect(group.children.some((child: { id: string }) => child.id === 'category:rule_conflict')).toBe(false);
    for (const child of group.children.filter((item: { count: number }) => item.count > 0)) {
      const code = child.id.slice('category:'.length);
      const filters = JSON.stringify([{ field: 'usage_status', operator: 'in', values: ['used'] }, { field: 'payment_group', operator: 'in', values: [group.id] }, { field: 'payment_status', operator: 'in', values: [code] }]);
      const query = new URLSearchParams({ page: '1', page_size: '200', filters });
      const filtered = await (await get('rows', query)).json();
      expect(filtered.summary.invoiceCount).toBe(child.count);
      for (const row of filtered.rows) {
        expect(row.paymentStatus.code).toBe(code);
        if (code !== 'unclassified') {
          const matched = payload.rules.find((rule: { id: string }) => rule.id === row.paymentStatus.matchedRuleId);
          expect(matched).toBeDefined();
          expect(matched.enabled).toBe(true);
          expect(matched.statusCode).toBe(code);
          expect(matched.conditions.hasBank).toBe(group.id === 'paid');
        }
      }
      const exportSummary = await (await get('export-summary', query)).json();
      expect(exportSummary.row_count).toBe(filtered.summary.invoiceCount);
      categoryChecks.push({ parent: group.id, code, rows: filtered.pagination.total, invoices: filtered.summary.invoiceCount });
    }
  }
  const exported = await get('export', new URLSearchParams({ page: '1', page_size: '200' }));
  expect(exported.headers()['content-type']).toContain('spreadsheetml');
  expect((await exported.body()).subarray(0, 4).toString('hex')).toBe('504b0304');
  await expectNoUnexpectedSuccessUiErrors(page);
  expect(writes).toEqual([]);
  expect(errors).toEqual([]);
  await info.attach('production-payment-rule-contract', { body: JSON.stringify({ version: payload.version, rules: payload.rules.length, writes: writes.length, errors, categoryChecks, exportBytes: (await exported.body()).length }), contentType: 'application/json' });
});
