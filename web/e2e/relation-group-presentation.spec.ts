import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks, inputInvoiceUsageRowsPayload } from './fixtures/apiMocks';

function groupedPayload() {
  const payload = inputInvoiceUsageRowsPayload(false, false, true);
  const first: any = payload.rows[0];
  first.invoice_relations = {
    primary: { ...first.invoice }, relation_count: 3, has_multiple: true, detail_mode: 'list', total_with_tax: '188.00',
    summaries: [first.invoice, { ...first.invoice, id: 'extra-1', display_no: 'SD-INV-EXTRA-1', digital_invoice_no: 'SD-INV-EXTRA-1', total_with_tax: '-20.00' },
      { ...first.invoice, id: 'extra-2', display_no: 'SD-INV-EXTRA-2', digital_invoice_no: 'SD-INV-EXTRA-2', total_with_tax: '120.00' }]
      .map(invoice => ({ ...invoice, invoice_id: invoice.id, invoice_date: invoice.issue_date })),
  };
  const second = structuredClone(first);
  second.id = 'second-parent';
  second.invoice.id = 'second-invoice';
  second.invoice.display_no = second.invoice.digital_invoice_no = 'SD-INV-SECOND';
  second.invoice_relations.primary = { ...second.invoice };
  second.invoice_relations.summaries = second.invoice_relations.summaries.map((invoice: any, index: number) => ({
    ...invoice, id: index === 0 ? second.invoice.id : `second-${index}`, invoice_id: index === 0 ? second.invoice.id : `second-${index}`,
    display_no: index === 0 ? 'SD-INV-SECOND' : `SD-INV-SECOND-${index}`, digital_invoice_no: index === 0 ? 'SD-INV-SECOND' : `SD-INV-SECOND-${index}`,
  }));
  payload.rows.push(second);
  payload.pagination.total = payload.rows.length;
  return payload;
}

test('invoice groups persist after pointer leaves, retain ten columns, and share one view across parents', async ({ page }, info) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: 'user' });
  const payload = groupedPayload();
  await page.route('**/api/input-invoice-usage/rows**', route => route.fulfill({ json: payload }));
  await page.goto('/input-invoice-usage');
  const table = page.getByRole('table', { name: '进项发票使用情况表' });
  const first = table.getByRole('button', { name: '查看发票 SD-INV-E2E-0001 关联发票 3 张' });
  const second = table.getByRole('button', { name: '查看发票 SD-INV-SECOND 关联发票 3 张' });
  const parent = first.locator('xpath=ancestor::tr');
  const before = await parent.boundingBox();
  const requests = api.calls.length;
  await first.click();
  await expect(table.locator('tr[data-relation-group]')).toHaveCount(3);
  await page.mouse.move(5, 5);
  await first.evaluate(button => (button as HTMLElement).blur());
  const after = await parent.boundingBox();
  expect(after!.x).toBe(before!.x);
  expect(after!.width).toBe(before!.width);
  for (const row of await table.locator('tr[data-relation-group]').all()) {
    await expect(row.locator('th,td')).toHaveCount(10);
    expect(await row.locator('th,td').evaluateAll(cells => cells.map(cell => getComputedStyle(cell).backgroundColor)))
      .toEqual(Array(10).fill('rgb(244, 247, 251)'));
    expect(await row.locator('th,td').first().evaluate(cell => getComputedStyle(cell).backgroundImage)).toContain('rgb(158, 181, 219)');
  }
  expect(await second.locator('xpath=ancestor::tr').getAttribute('data-relation-group')).toBeNull();
  await expect(table.getByText('-20.00', { exact: true })).toBeVisible();
  expect(api.calls.length).toBe(requests);
  for (const width of [1920, 1440, 1024]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.screenshot({ path: info.outputPath(`invoice-group-${width}.png`), animations: 'disabled' });
  }
  await parent.getByRole('button', { name: /关联OA/ }).click();
  await expect(table.locator('tr[data-relation-group]')).toHaveCount(2);
  await expect(page.getByRole('region', { name: '配对关系', exact: true })).toBeVisible();
  await expect(first).toHaveAttribute('aria-expanded', 'false');
  await second.click();
  await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0);
  await expect(table.locator('tr[data-relation-group]')).toHaveCount(3);
  expect(await parent.getAttribute('data-relation-group')).toBeNull();
  await second.click();
  await expect(table.locator('tr[data-relation-group]')).toHaveCount(0);
  await first.click();
  await page.getByRole('searchbox').fill('浏览器');
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/input-invoice-usage/rows' && new URL(response.url()).searchParams.get('keyword') === '浏览器');
  await page.getByRole('button', { name: '查询', exact: true }).click();
  expect((await refreshed).status()).toBe(200);
  await expect(table.locator('tr[data-relation-group]')).toHaveCount(0);
  await expect(first).toHaveAttribute('aria-expanded', 'false');
});

test('source group survives a rapid close and reopen without losing its parent or leaking onto ordinary rows', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.route('**/api/input-invoice-usage/rows**', route => route.fulfill({ json: groupedPayload() }));
  await page.goto('/input-invoice-usage');
  const sourceButtons = page.getByRole('button', { name: /关联OA/ });
  await sourceButtons.first().click();
  await sourceButtons.first().click();
  await sourceButtons.nth(1).click();
  const motion = page.locator('.relation-expansion-motion');
  await expect.poll(() => motion.evaluate(node => node.getAnimations().length)).toBe(0);
  await expect(page.locator('tr[data-relation-group]')).toHaveCount(2);
  const groups = await page.locator('tr[data-relation-group]').evaluateAll(rows => rows.map(row => row.getAttribute('data-relation-group')));
  expect(groups).toEqual(['second-parent', 'second-parent']);
  await page.getByRole('region', { name: '配对关系', exact: true }).getByRole('button', { name: '收起', exact: true }).click();
  await expect(page.locator('tr[data-relation-group]')).toHaveCount(0);
  await expect(sourceButtons.nth(1)).toBeFocused();
});
