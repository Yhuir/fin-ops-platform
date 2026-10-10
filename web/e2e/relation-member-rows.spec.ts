import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks, inputInvoiceUsageRowsPayload, oaPendingPaymentRowsPayload, pendingInvoiceRowsPayload, outputInvoiceCollectionRowsPayload } from './fixtures/apiMocks';
import { pendingAcquisitionFixture } from '../src/test/pendingInvoiceFixtures';

type Kind = 'invoice' | 'oa' | 'bank';
function payloadFor(name: string): any {
  const copies = (source: any, fields: (n: number) => any) => [0, 1, 2].map(n => ({ ...source, ...fields(n), relationCaseId: `case-${n}`, relation_case_id: `case-${n}` }));
  if (name === 'input-invoice-usage') {
    const payload: any = inputInvoiceUsageRowsPayload(false, false, true); const row = payload.rows[0];
    row.invoice_relations = { relation_count: 3, summaries: copies(row.invoice, n => ({ id: `invoice-${n}`, display_no: `INVOICE-${n}`, digital_invoice_no: `INVOICE-${n}`, invoice_date: '2026-05-02', total_with_tax: `${n + 1}10.00` })) };
    row.invoice = row.invoice_relations.summaries[0];
    row.oa = { ...row.oa, relation_count: 3, summaries: copies(row.oa.primary, n => ({ id: `oa-${n}`, applicant: `申请人${n}`, amount: `${n + 1}20.00` })) };
    row.oa.primary = row.oa.summaries[0];
    row.bank = { ...row.bank, original_transaction_count: 3, relation_count: 3, summaries: copies(row.bank.primary, n => ({ id: `bank-${n}`, counterparty_name: `流水对方${n}`, original_amount: `${n + 1}30.00` })) };
    row.bank.primary = row.bank.summaries[0]; return payload;
  }
  if (name === 'oa-pending-payments') {
    const payload: any = oaPendingPaymentRowsPayload(); const row = payload.rows[0];
    row.oa.relationCount = 3; row.oa.summaries = copies(row.oa, n => ({ oaId: `oa-${n}`, applicantName: `申请人${n}`, amount: `${n + 1}20.00`, workflowStatus: 'completed' }));
    row.invoice.relationCount = 3; row.invoice.summaries = copies(row.invoice, n => ({ invoiceId: `invoice-${n}`, digitalInvoiceNo: `INVOICE-${n}`, totalWithTax: `${n + 1}10.00` }));
    row.bankTransaction.relationCount = row.bankTransaction.original_transaction_count = 3;
    row.bankTransaction.summaries = copies(row.bankTransaction, n => ({ bankTransactionId: `bank-${n}`, counterpartyName: `流水对方${n}`, original_amount: `${n + 1}30.00` })); return payload;
  }
  if (name === 'pending-invoices') {
    const payload: any = pendingInvoiceRowsPayload(true); const row = payload.rows[0];
    row.input_invoices.relation_count = 3; row.input_invoices.summaries = copies(row.input_invoices.primary, n => ({ id: `invoice-${n}`, digital_invoice_no: `INVOICE-${n}`, total_with_tax: `${n + 1}10.00` }));
    row.oa.relation_count = 3; row.oa.summaries = copies(row.oa.primary, n => ({ id: `oa-${n}`, applicant: `申请人${n}`, workflow_status: 'completed', amount: `${n + 1}20.00` }));
    row.bank_transactions = { relation_count: 3, original_transaction_count: 3, has_multiple: true, summaries: copies(row.bank_transaction, n => ({ id: `bank-${n}`, counterparty_name: `流水对方${n}`, original_amount: `${n + 1}30.00` })) };
    payload.acquisition_summary = pendingAcquisitionFixture(payload.rows);
    return payload;
  }
  return outputInvoiceCollectionRowsPayload();
}

for (const [name, columns, kinds] of [
  ['input-invoice-usage', 10, ['invoice', 'oa', 'bank']], ['pending-invoices', 9, ['invoice', 'oa', 'bank']],
  ['oa-pending-payments', 4, ['invoice', 'oa', 'bank']], ['output-invoice-collections', 8, ['invoice', 'bank']],
] as const) {
  for (const kind of kinds) test(`${name} ${kind}: native member rows, columns, slide and no new I/O`, async ({ page }, info) => {
    const api = await installDeterministicApiMocks(page, { sessionMode: 'user' });
    const payload = payloadFor(name);
    await page.route(`**/api/${name}/rows**`, route => route.fulfill({ json: payload }));
    await page.goto(`/${name}`);
    const button = page.locator('.relation-count-button').filter({ hasText: kind === 'invoice' ? /张/ : kind === 'oa' ? /条/ : /笔/ }).first();
    await expect(button).toBeVisible(); await page.waitForLoadState('networkidle');
    const count = Number((await button.innerText()).match(/\d+/)![0]);
    const reads = api.calls.length;
    await button.click();
    const rows = page.locator('tr[data-relation-group]');
    await expect(rows).toHaveCount(count);
    await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0);
    await expect(page.locator('.relation-motion-clip').first()).toBeAttached();
    await expect.poll(() => page.locator('.relation-motion-clip').evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
    const geometry = await rows.evaluateAll(items => items.map(row => [...row.children].map(cell => ({ x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width }))));
    expect(geometry[0]).toHaveLength(columns);
    geometry.forEach(member => expect(member).toEqual(geometry[0]));
    for (const row of await rows.all()) await expect(row.locator('th,td')).toHaveCount(columns);
    if (name !== 'output-invoice-collections') {
      for (let n = 0; n < count; n++) await expect(rows.nth(n)).toContainText(kind === 'invoice' ? `INVOICE-${n}` : kind === 'oa' ? `申请人${n}` : `流水对方${n}`);
    }
    expect(api.calls.length).toBe(reads);
    await page.setViewportSize({ width: 1920, height: 1000 });
    await page.mouse.move(5, 5); await button.evaluate(node => (node as HTMLElement).blur());
    if (name === 'input-invoice-usage') {
      const name = rows.first().locator('td').nth(4).locator('.input-invoice-usage-cell-primary');
      expect(await name.evaluate(node => node.getBoundingClientRect().height / parseFloat(getComputedStyle(node).lineHeight))).toBeLessThanOrEqual(2);
    }
    await page.screenshot({ path: info.outputPath(`${name}-${kind}-expanded.png`) });
    await button.click(); await expect(rows).toHaveCount(0);
    expect(api.calls.length).toBe(reads);
    await button.click(); await button.click(); await button.click();
    await expect(button).toHaveAttribute('aria-expanded', 'true');
    await expect(rows).toHaveCount(count);
    await expect.poll(() => page.locator('.relation-motion-clip').evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
    await button.click(); await expect(button).toHaveAttribute('aria-expanded', 'false'); await expect(rows).toHaveCount(0);
  });
}

test('real slide has distinct start/middle/end frames and reduced motion keeps native rows', async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.route('**/api/input-invoice-usage/rows**', route => route.fulfill({ json: payloadFor('input-invoice-usage') }));
  await page.goto('/input-invoice-usage');
  const button = page.locator('.relation-count-button').filter({ hasText: /张/ }).first();
  await button.click();
  const clips = page.locator('.relation-motion-clip');
  // Freeze the native animations for deterministic visual evidence, not a replacement animation.
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => { animation.pause(); animation.currentTime = 0; })));
  const start = await clips.first().boundingBox();
  await page.screenshot({ path: info.outputPath('slide-start.png') });
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => { animation.currentTime = 110; })));
  const mid = await clips.first().boundingBox();
  await page.screenshot({ path: info.outputPath('slide-middle.png') });
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => animation.finish())));
  const end = await clips.first().boundingBox();
  expect(mid!.height).toBeGreaterThan(start!.height); expect(mid!.height).toBeLessThan(end!.height);
  await page.screenshot({ path: info.outputPath('slide-end.png') });
  await button.click();
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => { animation.pause(); animation.currentTime = 0; })));
  const closeStart = await clips.first().boundingBox();
  await page.screenshot({ path: info.outputPath('close-start.png') });
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => { animation.currentTime = 85; })));
  const closeMid = await clips.first().boundingBox();
  expect(closeMid!.height).toBeGreaterThan(0); expect(closeMid!.height).toBeLessThan(closeStart!.height);
  await page.screenshot({ path: info.outputPath('close-middle.png') });
  await clips.evaluateAll(nodes => nodes.forEach(node => node.getAnimations().forEach(animation => animation.finish())));
  await expect(page.locator('tr[data-relation-group]')).toHaveCount(0);
  await page.screenshot({ path: info.outputPath('close-end.png') });
  await page.emulateMedia({ reducedMotion: 'reduce' }); await button.click();
  await expect(page.locator('tr[data-relation-group]')).toHaveCount(3);
  expect(await clips.evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
  await button.click(); await expect(page.locator('tr[data-relation-group]')).toHaveCount(0);
});
