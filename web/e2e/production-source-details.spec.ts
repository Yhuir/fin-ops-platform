import { expect, test, type Locator } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 900 } });

test('production shared source drawers preserve complete records across pages without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(300_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: number[] = [], metrics: object[] = [], requests: string[] = [];
  page.on('request', request => {if (request.url().includes('/fin-ops-api/') && !['/fin-ops-api/api/app-health', '/fin-ops-api/api/background-jobs/active'].includes(new URL(request.url()).pathname)) requests.push(request.url());});
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => { if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(response.status()); });
  const inspect = async (button: Locator, sample: string) => {
    await expect(button).toBeVisible({ timeout: 25_000 });
    await page.waitForLoadState('networkidle');
    const readsBefore = requests.length;
    const started = Date.now();
    const pending = page.waitForResponse(response => {
      const path = new URL(response.url()).pathname;
      return response.request().method() === 'GET' && path.includes('/fin-ops-api/') && (/\/[^/]*(?:detail|details)$/.test(path) || /\/workbench\/rows\/[^/]+$/.test(path));
    }, { timeout: 25_000 });
    await button.click();
    const response = await pending;
    expect(response.status()).toBe(200);
    const payload = await response.json();
    const sections = payload.row ? payload.row.source_sections : payload.sections;
    expect(Array.isArray(sections)).toBe(true);
    expect(sections.length).toBeGreaterThan(0);
    const drawer = page.locator('[role="dialog"].source-detail-drawer');
    const expectedTitle = sample === 'oa' || sample.endsWith('-oa') ? 'OA详情'
      : sample.includes('invoice') ? '发票详情' : '银行流水详情';
    await expect(drawer.getByRole('heading', { name: expectedTitle, exact: true })).toBeVisible();
    await expect(drawer.locator('.entity-detail-table').first()).toBeVisible();
    const firstPaintMs = Date.now() - started;
    type SourceSection = {document_id: string; document_kind: string; bank_labels?: string[]; fields: {label: string}[]};
    const documents = new Map<string, SourceSection[]>();
    for (const section of sections as SourceSection[]) {
      const key = `${section.document_kind}:${section.document_id}`;
      if (!documents.has(key)) documents.set(key, []);
      documents.get(key)!.push(section);
    }
    const ids = new Set(documents.keys());
    expect(ids.size).toBe(1);
    expect(requests.length).toBe(readsBefore + 1);
    await expect(drawer.getByRole('tablist')).toHaveCount(0);
    const expectedLabels: string[] = [];
    for (const documentSections of documents.values()) {
      const bankSection = documentSections.find(section => section.bank_labels !== undefined);
      if (documentSections[0].document_kind === 'bank') {
        expect(bankSection).toBeTruthy();
        const cell = drawer.getByRole('rowheader', {name: '流水标签', exact: true}).locator('..');
        for (const label of bankSection!.bank_labels!) await expect(cell).toContainText(label);
      }
      const actual = await drawer.locator('.entity-detail-table th[scope="row"]').allTextContents();
      const expected = documentSections.flatMap(section => [
        ...(section.bank_labels !== undefined ? ['流水标签'] : []),
        ...section.fields.map(field => field.label),
      ]);
      expect(actual).toEqual(expected);
      expectedLabels.push(...expected);
      for (const label of expected) expect(label).not.toMatch(/^(?:id|source_|row_|case_|normalized_|raw_|状态$)/i);
    }
    expect(await drawer.innerText()).not.toContain('\uFFFD');
    const money = drawer.locator('.entity-detail-row__amount');
    for (let i = 0; i < await money.count(); i++) await expect(money.nth(i)).toHaveCSS('text-align', 'left');
    for (const width of [1440, 480]) {
      await page.setViewportSize({ width, height: 900 });
      const scroll = drawer.locator('.finance-drawer__body');
      await expect(scroll).toHaveCSS('padding-left', width === 480 ? '16px' : '24px');
      expect(await drawer.locator('.entity-detail-table').first().evaluate(el => {
        const body = el.closest('.finance-drawer__body')!;
        return el.getBoundingClientRect().left - body.getBoundingClientRect().left;
      })).toBeLessThanOrEqual((width === 480 ? 16 : 24) + 1);
      expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
      expect(await scroll.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 2)).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ animations: "disabled", path: info.outputPath(`${sample}-${width}.png`) });
    }
    metrics.push({ sample, documents: ids.size, fields: expectedLabels.length, firstPaintMs });
    await drawer.getByRole('button', { name: /关闭.*抽屉|关闭详情/ }).click();
    await expect(drawer).toBeHidden();
    await page.setViewportSize({ width: 1440, height: 900 });
  };
  const inspectExpanded = async (kind: 'invoice' | 'oa' | 'bank', sample: string) => {
    const trigger = page.locator('.relation-count-button').filter({hasText: kind === 'invoice' ? /张/ : kind === 'oa' ? /条/ : /笔/}).first();
    if (!await trigger.count()) { metrics.push({sample, availability:'no multi-member group on current page'}); return; }
    await page.waitForLoadState('networkidle');
    const readsBefore = requests.length;
    const count = Number((await trigger.innerText()).match(/\d+/)![0]);
    await trigger.click();
    const members = page.locator('tr[data-relation-group]');
    await expect(members).toHaveCount(count);
    expect(requests.length).toBe(readsBefore);
    await inspect(members.nth(1).getByRole('button', {name: kind === 'invoice' ? /(?:查看发票 .* 详情|发票详情 .*)/
      : kind === 'oa' ? /(?:查看 ?OA .*详情|OA详情 .*)/ : /(?:查看银行流水 .*详情|查看流水 .*详情|流水详情 .*)/}), sample);
    await expect(members).toHaveCount(count);
    await trigger.click();
    await expect(members).toHaveCount(0);
    expect(requests.length).toBe(readsBefore + 1);
  };
  await page.goto('/fin-ops/bank-details');
  await inspect(page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first(), 'bank');
  await page.goto('/fin-ops/output-invoice-collections');
  await inspectExpanded('invoice', 'output-related-invoice');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'output-invoice');
  await page.goto('/fin-ops/input-invoice-usage');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'input-invoice');
  await inspectExpanded('oa', 'input-related-oa');
  await inspectExpanded('bank', 'input-related-bank');
  await page.goto('/fin-ops/oa-pending-payments');
  await inspect(page.getByRole('button', { name: /^查看 OA .*详情$/ }).first(), 'oa');
  await inspectExpanded('oa', 'oa-pending-related-oa');
  await inspectExpanded('bank', 'oa-pending-related-bank');
  await page.goto('/fin-ops/pending-invoices');
  await inspect(page.getByRole('button', { name: /^流水详情 / }).first(), 'pending-bank');
  await page.goto('/fin-ops/');
  await inspect(page.getByRole('button', { name: /^查看OA .*详情$/ }).first(), 'workbench-oa');
  await inspect(page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first(), 'workbench-bank');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'workbench-invoice');
  await page.goto('/fin-ops/cost-statistics');
  await page.getByRole('radio', { name: '按时间', exact: true }).click();
  await inspect(page.getByRole('grid', { name: '按时间银行流水表' }).getByRole('button', { name: /^查看银行流水 / }).first(), 'cost-bank');
  expect(writes).toEqual([]); expect(failures).toEqual([]);
  await info.attach('production-source-details', { body: JSON.stringify(metrics, null, 2), contentType: 'application/json' });
});
