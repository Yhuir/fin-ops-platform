import { pendingAcquisitionFixture } from '../src/test/pendingInvoiceFixtures';
import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks, inputInvoiceUsageRowsPayload, oaPendingPaymentRowsPayload, outputInvoiceCollectionRowsPayload, pendingInvoiceRowsPayload } from './fixtures/apiMocks';

const pages = [['input-invoice-usage', 10], ['oa-pending-payments', 4], ['pending-invoices', 9], ['output-invoice-collections', 8]] as const;
type PageName = typeof pages[number][0];
type RelationKind = 'invoice' | 'oa' | 'bank';

function sharedMembersPayload(name: PageName): any {
  const copies = (source: any, fields: (n: number) => any) => [0, 1].map(n => ({
    ...source, ...fields(n), relationCaseId: `shared-case-${n}`, relation_case_id: `shared-case-${n}`,
  }));
  if (name === 'input-invoice-usage') {
    const payload: any = inputInvoiceUsageRowsPayload(); const row = payload.rows[0];
    row.invoice_relations = { relation_count: 2, has_multiple: true, detail_mode: 'list', summaries: copies(row.invoice, n => ({
      id: n === 0 ? row.invoice.id : 'shared-input-invoice-2', display_no: `SHARED-INVOICE-${n}`, digital_invoice_no: `SHARED-INVOICE-${n}`,
      invoice_date: '2026-05-02', total_with_tax: `${n + 1}10.00`, taxRate: row.invoice.tax_rate, taxAmount: row.invoice.tax_amount, amount: row.invoice.amount_without_tax,
    })) };
    row.invoice = row.invoice_relations.summaries[0];
    row.oa = { ...row.oa, relation_count: 2, has_multiple: true, summaries: copies(row.oa.primary, n => ({
      id: n === 0 ? row.oa.primary.id : 'shared-input-oa-2', applicant: `SHARED申请人${n}`, amount: `${n + 1}20.00`,
    })) };
    row.oa.primary = row.oa.summaries[0];
    row.bank = { ...row.bank, original_transaction_count: 2, relation_count: 2, has_multiple: true, summaries: copies(row.bank.primary, n => ({
      id: n === 0 ? row.bank.primary.id : 'shared-input-bank-2', counterparty_name: `SHARED流水成员${n}`,
      amount: `${n + 1}30.00`, original_amount: `${n + 1}30.00`,
    })) };
    row.bank.primary = row.bank.summaries[0]; return payload;
  }
  if (name === 'oa-pending-payments') {
    const payload: any = oaPendingPaymentRowsPayload(); const row = payload.rows[0];
    row.oa.summaries = copies(row.oa, n => ({
      oaId: n === 0 ? row.oa.id : 'shared-payment-oa-2', applicantName: `SHARED申请人${n}`, amount: `${n + 1}20.00`, workflowStatus: 'completed',
    }));
    row.oa.relationCount = 2; row.oa.hasMultiple = true;
    row.bankTransaction.summaries = copies(row.bankTransaction, n => ({
      bankTransactionId: n === 0 ? row.bankTransaction.primaryBankTransactionId : 'shared-payment-bank-2',
      counterpartyName: `SHARED流水成员${n}`, amount: `${n + 1}30.00`, original_amount: `${n + 1}30.00`,
    }));
    row.bankTransaction.relationCount = row.bankTransaction.original_transaction_count = 2;
    row.bankTransaction.hasMultiple = true; row.bankTransaction.nonOutflowRelationEdges = [];
    row.invoice.summaries = copies(row.invoice, n => ({
      invoiceId: n === 0 ? row.invoice.primaryInvoiceId : 'shared-payment-invoice-2', digitalInvoiceNo: `SHARED-INVOICE-${n}`, totalWithTax: `${n + 1}10.00`,
    }));
    row.invoice.relationCount = 2; row.invoice.hasMultiple = true; return payload;
  }
  if (name === 'pending-invoices') {
    const payload: any = pendingInvoiceRowsPayload(true); const row = payload.rows[0];
    row.input_invoices = { ...row.input_invoices, relation_count: 2, has_multiple: true, summaries: copies(row.input_invoices.primary, n => ({
      id: n === 0 ? row.input_invoices.primary.id : 'shared-pending-invoice-2', digital_invoice_no: `SHARED-INVOICE-${n}`, total_with_tax: `${n + 1}10.00`,
    })) };
    row.input_invoices.primary = row.input_invoices.summaries[0];
    row.oa = { ...row.oa, relation_count: 2, has_multiple: true, summaries: copies(row.oa.primary, n => ({
      id: n === 0 ? row.oa.primary.id : 'shared-pending-oa-2', applicant: `SHARED申请人${n}`, workflow_status: 'completed', amount: `${n + 1}20.00`,
    })) };
    row.oa.primary = row.oa.summaries[0];
    row.bank_transactions = { relation_count: 2, original_transaction_count: 2, has_multiple: true, summaries: copies(row.bank_transaction, n => ({
      id: n === 0 ? row.bank_transaction.id : 'shared-pending-bank-2', counterparty_name: `SHARED流水成员${n}`,
      amount: `${n + 1}30.00`, original_amount: `${n + 1}30.00`,
    })) };
    row.bank_transaction = row.bank_transactions.summaries[0];
    payload.acquisition_summary = pendingAcquisitionFixture(payload.rows); return payload;
  }
  const payload: any = outputInvoiceCollectionRowsPayload(); const row = payload.rows[0];
  row.bank = { ...row.bank, original_transaction_count: 2, relation_count: 2, has_multiple: true, summaries: copies(row.bank.primary, n => ({
    id: n === 0 ? row.bank.primary.bank_transaction_id : 'shared-output-bank-2',
    bank_transaction_id: n === 0 ? row.bank.primary.bank_transaction_id : 'shared-output-bank-2',
    counterparty_name: `SHARED流水成员${n}`, amount: `${n + 1}30.00`, original_amount: `${n + 1}30.00`,
  })) };
  row.bank.primary = row.bank.summaries[0]; row.invoice_relations.summaries[0].memberRow.bankTransactions = row.bank;
  return payload;
}

for (const [name, columns] of pages) {
  test(`${name}: native members retain grouping, details and type switching without prefetch`, async ({ page }, info) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' }); const payload = sharedMembersPayload(name);
    const sourceReads: string[] = []; let rowReads = 0;
    page.on('request', request => {
      const path = new URL(request.url()).pathname;
      if (/\/(?:source-detail|relation-details?|detail)$/.test(path)) sourceReads.push(path);
      if (path === `/api/${name}/rows`) rowReads++;
    });
    await page.route(`**/api/${name}/rows**`, route => route.fulfill({ json: payload }));
    await page.route(`**/api/${name}/invoices/*/detail`, route => {
      const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/').at(-2)!);
      return route.fulfill({ json: { detail_available: true, sections: [{
        title: '发票信息', document_id: id, document_kind: 'invoice',
        invoice_navigation: { polarity: '蓝字', counterpartyName: '测试购方', totalWithTax: '210.00', invoiceDate: '2026-05-02' },
        fields: [{ label: '发票号码', value: id }],
      }] } });
    });
    await page.setViewportSize({ width: 1440, height: 900 }); await page.goto(`/${name}`);
    const countButton = (kind: RelationKind) => page.locator('.relation-count-button').filter({ hasText: kind === 'invoice' ? /张/ : kind === 'oa' ? /条/ : /笔/ }).first();
    const trigger = countButton('invoice'); await expect(trigger).toBeVisible(); await page.waitForLoadState('networkidle');
    const original = trigger.locator('xpath=ancestor::tr'); const table = original.locator('xpath=ancestor::table');
    const originalCells = await original.locator('th,td').allTextContents(); const initialRows = await table.locator('tbody > tr').count();
    const initialReads = rowReads; expect(initialReads).toBeGreaterThan(0);
    await trigger.click(); const groupId = await original.getAttribute('data-relation-group'); expect(groupId).toBeTruthy();
    const members = page.locator(`tr[data-relation-group="${groupId}"]`);
    await expect(members).toHaveCount(2); await expect(table.locator('tbody > tr')).toHaveCount(initialRows + 1);
    await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0); await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect.poll(() => members.locator('.relation-motion-clip').evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
    for (const member of await members.all()) await expect(member.locator('th,td')).toHaveCount(columns);
    const geometry = await members.evaluateAll(rows => rows.map(row => [...row.children].map(cell => ({ x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width }))));
    expect(geometry[1]).toEqual(geometry[0]);
    // The first member remains the original row, without an aggregate row above it.
    expect(await members.first().locator('th,td').allTextContents()).toEqual(originalCells);
    await page.mouse.move(5, 5); await trigger.evaluate(node => (node as HTMLElement).blur());
    await expect.poll(() => members.evaluateAll(rows => rows.flatMap(row => [...row.children].map(cell => getComputedStyle(cell).backgroundColor))))
      .toEqual(Array(columns * 2).fill('rgb(244, 247, 251)'));
    const presentation = await members.evaluateAll(rows => rows.map(row => ({ group: row.getAttribute('data-relation-group'),
      line: getComputedStyle(row.firstElementChild!).backgroundImage, lineWidth: getComputedStyle(row.firstElementChild!).backgroundSize,
    })));
    for (const member of presentation) { expect(member.group).toBe(groupId); expect(member.line).toContain('rgb(158, 181, 219)'); expect(member.lineWidth).toBe('3px 100%'); }
    expect(sourceReads).toEqual([]); expect(rowReads).toBe(initialReads);
    await page.screenshot({ path: info.outputPath(`${name}-expanded.png`), animations: 'disabled' });
    const invoiceId = name === 'input-invoice-usage' ? payload.rows[0].invoice_relations.summaries[1].id
      : name === 'oa-pending-payments' ? payload.rows[0].invoice.summaries[1].invoiceId
      : name === 'pending-invoices' ? payload.rows[0].input_invoices.summaries[1].id : payload.rows[0].invoice_relations.summaries[1].id;
    await members.nth(1).getByRole('button', { name: /(?:查看发票 .* 详情|发票详情 .*)/ }).click();
    const drawer = page.getByRole('dialog'); await expect(drawer).toBeVisible(); await expect(drawer.getByText(invoiceId, { exact: true })).toBeVisible();
    await expect(drawer.getByRole('tablist', { name: '单据导航' })).toHaveCount(0);
    expect(sourceReads).toEqual([`/api/${name}/invoices/${invoiceId}/detail`]);
    await drawer.getByRole('button', { name: '关闭详情抽屉' }).click(); await expect(drawer).toHaveCount(0);
    await expect(members).toHaveCount(2); await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    for (const kind of name === 'output-invoice-collections' ? ['bank'] as const : ['bank', 'oa'] as const) {
      await countButton(kind).click(); await expect(members).toHaveCount(2); await expect(countButton(kind)).toHaveAttribute('aria-expanded', 'true');
      await expect(trigger).toHaveAttribute('aria-expanded', 'false'); await expect(members.nth(1)).toContainText(kind === 'bank' ? 'SHARED流水成员1' : 'SHARED申请人1');
    }
    await trigger.click(); await expect(trigger).toHaveAttribute('aria-expanded', 'true'); await page.emulateMedia({ reducedMotion: 'reduce' });
    await trigger.click(); await expect(members).toHaveCount(0); await expect(table.locator('tbody > tr')).toHaveCount(initialRows);
    await trigger.click(); await expect(members).toHaveCount(2);
    expect(await members.locator('.relation-motion-clip').evaluateAll(nodes => nodes.flatMap(node => node.getAnimations()).length)).toBe(0);
    await trigger.click(); await expect(members).toHaveCount(0); expect(sourceReads).toHaveLength(1);
    expect(rowReads).toBe(initialReads);
  });
}

test('bank source opens without split IO and aligns dates, money and account fields', async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' }); let splitReads = 0;
  page.on('request', request => { if (/\/splits(?:\?|$)/.test(request.url())) splitReads++; });
  await page.route('**/api/bank-transactions/*/source-detail', route => route.fulfill({ json: { detail_available: true, sections: [
    { title: '交易信息', document_id: 'bank', document_kind: 'bank', bank_transaction_id: 'bank', fields: [{ label: '交易日期', value: '2026-09-24' }, { label: '支出金额', value: '2725.00' }, { label: '余额', value: '33645.36' }] },
    { title: '账户信息', document_id: 'bank', document_kind: 'bank', bank_transaction_id: 'bank', fields: [{ label: '账号', value: '15990259060093' }, { label: '对方户名', value: '测试设备有限公司' }] },
  ] } }));
  await page.goto('/bank-details'); await page.getByRole('button', { name: /^查看银行流水.*详情$/ }).first().click();
  const drawer = page.getByRole('dialog', { name: '银行流水详情' }); await expect(drawer.getByText('33645.36')).toBeVisible();
  for (const width of [1440, 480]) {
    await page.setViewportSize({ width, height: 800 });
    const x = await drawer.locator('.entity-detail-table td').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().x));
    expect(Math.max(...x) - Math.min(...x)).toBeLessThan(2); expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({ animations: 'disabled', path: info.outputPath(`bank-${width}.png`) });
  }
  expect(splitReads).toBe(0); await expect(drawer.getByRole('button', { name: '流水子项拆分' })).toBeVisible();
});

test('47 invoice members keep native columns, real slide frames and contained scrolling', async ({ page }, info) => {
  await installDeterministicApiMocks(page, { sessionMode: 'user' }); const payload: any = outputInvoiceCollectionRowsPayload(); const row = payload.rows[0];
  const emptyBank = { relation_count: 0, original_transaction_count: 0, has_multiple: false, received_total: '0.00', detail_mode: 'none', summaries: [] };
  const invoices = Array.from({ length: 47 }, (_, n) => ({
    ...row.invoice, id: n === 0 ? row.invoice.id : `source-invoice-${n}`,
    display_no: `长发票号码-20261011-${n.toString().padStart(12, '0')}`, digital_invoice_no: `长发票号码-20261011-${n.toString().padStart(12, '0')}`,
    invoice_no: `20261011-${n.toString().padStart(12, '0')}`, buyer_name: '云南很长的客户名称用于验证完整配对关系在窄视口下不会挤出原表格区域有限公司',
    issue_date: '2026-10-10', invoice_date: '2026-10-10', amount_without_tax: `${1000 + n}.00`, tax_amount: `${60 + n}.00`, total_with_tax: `${1060 + n * 2}.00`,
    tax_rate: '6%', is_positive_invoice: '是', taxable_item_name: `成员 ${n} 信息技术服务`,
    memberRow: { collectionStatus: { code: 'pending_collection', label: '未收款', collected_amount: '0.00', pending_amount: `${1060 + n * 2}.00`, reason: '未关联收入流水。' }, bankTransactions: emptyBank },
  }));
  row.invoice = { ...invoices[0] }; delete row.invoice.memberRow;
  row.collection_status = invoices[0].memberRow.collectionStatus; row.bank = emptyBank;
  row.invoice_relations = { primary: invoices[0], relation_count: 47, has_multiple: true, total_with_tax: invoices.reduce((sum, invoice) => sum + Number(invoice.total_with_tax), 0).toFixed(2), detail_mode: 'list', summaries: invoices };
  await page.route('**/api/output-invoice-collections/rows**', route => route.fulfill({ json: payload }));
  let detailReads = 0; let rowReads = 0;
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (/\/(?:detail|source-detail)$/.test(path)) detailReads++;
    if (path === '/api/output-invoice-collections/rows') rowReads++;
  });
  await page.setViewportSize({ width: 1280, height: 900 }); await page.goto('/output-invoice-collections');
  const trigger = page.locator('.relation-count-button').filter({ hasText: /47 张/ }); await expect(trigger).toBeVisible();
  const initialReads = rowReads; expect(initialReads).toBeGreaterThan(0);
  const table = trigger.locator('xpath=ancestor::table'); const initialRows = await table.locator('tbody > tr').count();
  // Freeze only product-created WAAPI animations, without creating a replacement animation.
  await page.evaluate(() => {
    const state = window as unknown as { relationSlideAnimations: Animation[] }; state.relationSlideAnimations = [];
    let frame = 0;
    const observer = new MutationObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const animations = document.getAnimations().filter(animation => {
          const effect = animation.effect as KeyframeEffect;
          return effect.target instanceof HTMLElement && effect.target.matches('.relation-motion-clip') && effect.getTiming().duration === 220;
        });
        if (animations.length !== 46 * 8) return;
        state.relationSlideAnimations = animations; animations.forEach(animation => { animation.pause(); animation.currentTime = 0; }); observer.disconnect();
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
  await trigger.click(); const members = page.locator('tr[data-relation-group="output-collection-row-e2e-001"]');
  await expect(members).toHaveCount(47); await expect(table.locator('tbody > tr')).toHaveCount(initialRows + 46);
  for (const member of await members.all()) await expect(member.locator('td')).toHaveCount(8);
  await expect(page.getByRole('region', { name: '配对关系', exact: true })).toHaveCount(0);
  await expect.poll(() => page.evaluate(() => (window as unknown as { relationSlideAnimations: Animation[] }).relationSlideAnimations.length)).toBe(46 * 8);
  await info.attach('native-slide-keyframes', { body: JSON.stringify(await page.evaluate(() =>
    (window as unknown as { relationSlideAnimations: Animation[] }).relationSlideAnimations.slice(0, 8).map(animation => ({
      playState: animation.playState, currentTime: animation.currentTime, keyframes: (animation.effect as KeyframeEffect).getKeyframes(),
    })))), contentType: 'application/json' });
  const clips = members.locator('.relation-motion-clip'); const start = (await clips.first().boundingBox())!.height;
  await page.screenshot({ path: info.outputPath('slide-start.png') });
  await page.evaluate(() => (window as unknown as { relationSlideAnimations: Animation[] }).relationSlideAnimations.forEach(animation => { animation.currentTime = 110; }));
  const middle = (await clips.first().boundingBox())!.height; await page.screenshot({ path: info.outputPath('slide-middle.png') });
  await page.evaluate(() => (window as unknown as { relationSlideAnimations: Animation[] }).relationSlideAnimations.forEach(animation => animation.finish()));
  const end = (await clips.first().boundingBox())!.height;
  await info.attach('native-slide-frames', { body: JSON.stringify({ start, middle, end, duration: 220, nativeCells: 46 * 8 }), contentType: 'application/json' });
  await page.screenshot({ path: info.outputPath('slide-end.png') });
  await expect(members.first().locator('td').nth(2)).toContainText('1060.00');
  await expect(members.last().locator('td').nth(2)).toContainText('1152.00');
  await expect(members.last().locator('td').nth(3)).toContainText('成员 46 信息技术服务');
  const scroll = table.locator('xpath=ancestor::*[contains(concat(" ", normalize-space(@class), " "), " finance-table__scroll ")][1]');
  for (const width of [1280, 1024, 480]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    const bounds = await scroll.evaluate(node => ({ left: node.getBoundingClientRect().left, right: node.getBoundingClientRect().right,
      viewport: window.innerWidth, clientWidth: node.clientWidth, scrollWidth: node.scrollWidth, clientHeight: node.clientHeight, scrollHeight: node.scrollHeight,
    }));
    expect(bounds.left).toBeGreaterThanOrEqual(0); expect(bounds.right).toBeLessThanOrEqual(bounds.viewport + 1);
    expect(bounds.scrollHeight).toBeGreaterThan(bounds.clientHeight); if (width === 480) expect(bounds.scrollWidth).toBeGreaterThan(bounds.clientWidth);
    const columns = await members.evaluateAll(rows => rows.map(row => [...row.children].map(cell => ({
      x: cell.getBoundingClientRect().x, width: cell.getBoundingClientRect().width,
    }))));
    columns.forEach(member => expect(member).toEqual(columns[0]));
    await scroll.evaluate(node => { node.scrollLeft = 0; node.scrollTop = 0; }); await page.screenshot({ path: info.outputPath(`relationship-long-${width}.png`) });
    await scroll.evaluate(node => { node.scrollLeft = node.scrollWidth; node.scrollTop = node.scrollHeight; }); expect(await scroll.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
    await page.screenshot({ path: info.outputPath(`relationship-long-end-${width}.png`) });
  }
  expect(detailReads).toBe(0); expect(rowReads).toBe(initialReads);
  expect(start).toBe(0); expect(middle).toBeGreaterThan(start); expect(middle).toBeLessThan(end);
  await page.emulateMedia({ reducedMotion: 'reduce' }); await scroll.evaluate(node => { node.scrollLeft = 0; node.scrollTop = 0; });
  await trigger.click(); await expect(members).toHaveCount(0); await expect(table.locator('tbody > tr')).toHaveCount(initialRows);
});
