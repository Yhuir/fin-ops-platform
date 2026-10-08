import { expect, test, type Locator } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 900 } });

test('production shared source drawers preserve complete records across pages without writes', async ({ page }, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(300_000);
  await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
  const writes: string[] = [], failures: number[] = [], metrics: object[] = [], requests: string[] = [];
  page.on('request', request => {if (request.url().includes('/fin-ops-api/') && new URL(request.url()).pathname !== '/fin-ops-api/api/app-health') requests.push(request.url());});
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname); await route.abort('blockedbyclient');
    } else await route.continue();
  });
  page.on('response', response => { if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(response.status()); });
  const inspect = async (button: Locator, sample: string, multiple = false) => {
    await expect(button).toBeVisible({ timeout: 25_000 });
    const started = Date.now();
    const pending = page.waitForResponse(response => {
      const path = new URL(response.url()).pathname;
      return response.request().method() === 'GET' && path.includes('/fin-ops-api/') && (/\/[^/]*(?:detail|details)$/.test(path) || /\/workbench\/rows\/[^/]+$/.test(path));
    });
    await button.click();
    const response = await pending;
    expect(response.status()).toBe(200);
    const payload = await response.json();
    const sections = payload.row ? payload.row.source_sections : payload.sections;
    expect(Array.isArray(sections)).toBe(true);
    expect(sections.length).toBeGreaterThan(0);
    const drawer = page.locator('[role="dialog"].source-detail-drawer');
    const expectedTitle = sample === 'oa' || sample.endsWith('-oa') ? 'OA详情'
      : sample.includes('invoice') || sample === 'red-blue' ? '发票详情' : '银行流水详情';
    await expect(drawer.getByRole('heading', { name: expectedTitle, exact: true })).toBeVisible();
    await expect(drawer.locator('.entity-detail-table').first()).toBeVisible();
    const firstPaintMs = Date.now() - started;
    type SourceSection = {document_id: string; document_kind: string; document_title: string; oa_navigation?: {applicantName: string | null; amount: string | null; applicationDate: string | null; workflowNo: string | null}; invoice_navigation?: {counterpartyName: string | null; totalWithTax: string | null}; bank_navigation?: {counterpartyName: string | null; amount: string | null; direction: string | null; labels: string[]}; bank_labels?: string[]; fields: {label: string}[]};
    const documents = new Map<string, SourceSection[]>();
    for (const section of sections as SourceSection[]) {
      const key = `${section.document_kind}:${section.document_id}`;
      if (!documents.has(key)) documents.set(key, []);
      documents.get(key)!.push(section);
    }
    const ids = new Set(documents.keys());
    if (multiple) expect(ids.size).toBeGreaterThan(1);
    const expectedLabels: string[] = [];
    const switchMs: number[] = [];
    for (const [index, [, documentSections]] of [...documents].entries()) {
      if (ids.size > 1) {
        const nav = drawer.getByRole('tablist', {name: '单据导航'});
        await expect(nav).toBeVisible();
        const tab = nav.getByRole('tab').nth(index);
        const section = documentSections[0];
        if (section.document_kind === 'invoice') {
          expect(section.invoice_navigation).toBeTruthy();
          const summary = section.invoice_navigation!;
          if (summary.counterpartyName) await expect(tab).toContainText(summary.counterpartyName);
          if (summary.totalWithTax) await expect(tab).toContainText(summary.totalWithTax);
          await expect(tab).not.toContainText("尾号");
          expect(await nav.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        } else if (section.document_kind === 'bank') {
          const summary = section.bank_navigation!;
          expect(summary).toBeTruthy();
          expect(Array.isArray(summary.labels)).toBe(true);
          if (summary.counterpartyName) await expect(tab).toContainText(summary.counterpartyName);
          if (summary.amount) await expect(tab).toContainText(summary.amount);
          for (const label of summary.labels) await expect(tab).toContainText(label);
          expect(await nav.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        } else {
          expect(section.oa_navigation).toBeTruthy();
          for (const value of Object.values(section.oa_navigation!)) if (value !== null) await expect(tab).toContainText(value);
          expect(await nav.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
        }
        await tab.click();
        await expect(tab).toHaveAttribute('aria-selected', 'true');
        await expect(drawer.getByRole('tabpanel')).toHaveCount(1);
        expect(await tab.evaluate(el => el.scrollWidth <= el.clientWidth && getComputedStyle(el).textOverflow !== 'ellipsis')).toBe(true);
      } else await expect(drawer.getByRole('tablist')).toHaveCount(0);
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
    if (ids.size > 1) {
      const readsBefore = requests.length;
      for (let index = 0; index < 20; index++) {
        const tab = drawer.getByRole('tab').nth(index % ids.size);
        const elapsed = await tab.evaluate(async el => {
          const started = performance.now();
          (el as HTMLElement).click();
          await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
          return performance.now() - started;
        });
        switchMs.push(elapsed);
        await expect(tab).toHaveAttribute('aria-selected', 'true');
      }
      expect(requests.length).toBe(readsBefore);
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
      })).toBeLessThanOrEqual((width === 480 ? 16 : 24) + (ids.size > 1 ? 18 : 1));
      expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      if (ids.size > 1) await expect.poll(() => drawer.getByRole('tab', {selected: true}).evaluate(el => {
        const tab = el.getBoundingClientRect(), nav = el.closest('[role=tablist]')!.getBoundingClientRect();
        return tab.left >= nav.left - 1 && tab.right <= nav.right + 1;
      })).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
      expect(await scroll.evaluate(el => el.scrollTop + el.clientHeight >= el.scrollHeight - 2)).toBe(true);
      await scroll.evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ animations: "disabled", path: info.outputPath(`${sample}-${width}.png`) });
    }
    metrics.push({ sample, documents: ids.size, fields: expectedLabels.length, firstPaintMs, switchMs, switchP95Ms: switchMs.length ? [...switchMs].sort((a,b)=>a-b)[Math.ceil(switchMs.length*.95)-1] : null });
    await drawer.getByRole('button', { name: /关闭.*抽屉|关闭详情/ }).click();
    await expect(drawer).toBeHidden();
    await page.setViewportSize({ width: 1440, height: 900 });
  };
  await page.goto('/fin-ops/bank-details');
  await inspect(page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first(), 'bank');
  await page.goto('/fin-ops/output-invoice-collections');
  await inspect(page.getByRole('button', { name: /^红蓝票 · / }).first(), 'red-blue', true);
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'output-invoice');
  await page.goto('/fin-ops/input-invoice-usage');
  await inspect(page.getByRole('button', { name: /^查看发票.*详情$/ }).first(), 'input-invoice');
  for (const [pattern, sample] of [[/关联OA (?:[2-9]|\d{2,}) 条$/, 'input-related-oa'], [/关联流水 (?:[2-9]|\d{2,}) 条$/, 'input-related-bank']] as const) {
    const group = page.getByRole('button', {name: pattern}).first();
    if (await group.count()) await inspect(group, sample, true);
  }
  await page.goto('/fin-ops/oa-pending-payments');
  await inspect(page.getByRole('button', { name: /^查看 OA .*详情$/ }).first(), 'oa');
  await page.getByLabel('搜索OA待付款核对').fill('公车');
  const searched = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/oa-pending-payments/rows') && new URL(r.url()).searchParams.get('keyword') === '公车');
  await page.getByRole('button', {name: '查询', exact: true}).click();
  await searched;
  await inspect(page.getByRole('button', {name: /关联OA 9 条$/}), 'oa-pending-related-oa', true);
  await inspect(page.getByRole('button', {name: /关联流水 9 条$/}), 'oa-pending-related-bank', true);
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
