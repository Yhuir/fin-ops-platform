import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

const numbers = ['2653400000097888906', '2653400000097888907'];
function invoiceSections() {
  return numbers.flatMap((number, index) => {
    const metadata = {document_id: `invoice-${index}`, document_kind: 'invoice', document_title: `${index ? '红字' : '蓝字'} · ${number}`};
    return [
      {title: '发票信息', fields: [{label: '数电发票号码', value: number}, {label: '开票日期', value: '2026-07-15'}, {label: '发票票种', value: '数电发票（普通发票）'}], ...metadata},
      {title: '购销双方', fields: [{label: '销方名称', value: '测试供应商有限公司'}, {label: '销方识别号', value: '915300000000000001'}, {label: '购买方名称', value: '测试科技有限公司'}, {label: '购买方识别号', value: '915300000000000002'}], ...metadata},
      {title: '金额与税额', fields: [{label: '不含税金额', value: index ? '-2079.21' : '2079.21'}, {label: '税额', value: index ? '-20.79' : '20.79'}, {label: '价税合计', value: index ? '-2100.00' : '2100.00'}], ...metadata},
      {title: '业务信息', fields: [{label: '备注', value: '完整备注可换行。'.repeat(20)}], ...metadata},
    ];
  });
}

test('full invoice navigation, compact left-aligned values and one reachable scroll area', async ({page}, info) => {
  await installDeterministicApiMocks(page, {sessionMode: 'user'});
  await page.route('**/api/output-invoice-collections/rows/*/relation-details*', route => route.fulfill({json: {kind: 'invoice', sections: invoiceSections()}}));
  await page.goto('/output-invoice-collections');
  const trigger = page.getByRole('button', {name: '红蓝票 · 2'}).first();
  await trigger.click();
  const drawer = page.getByRole('dialog', {name: '发票详情', exact: true});
  await expect(drawer.getByRole('navigation', {name: '单据导航'})).toBeVisible();
  for (const width of [1440, 1024, 480]) {
    await page.setViewportSize({width, height: 800});
    const nav = drawer.getByRole('navigation');
    for (const [index, number] of numbers.entries()) {
      const button = nav.getByRole('button', {name: `${index ? '红字' : '蓝字'} · ${number}`, exact: true});
      await button.scrollIntoViewIfNeeded();
      await expect(button).toBeVisible();
      expect(await button.evaluate(el => el.scrollWidth <= el.clientWidth && getComputedStyle(el).textOverflow !== 'ellipsis')).toBe(true);
    }
    const expand = nav.getByRole('button', {name: '展开全部', exact: true});
    if (await expand.count()) await expand.click();
    await expect(drawer.locator('.entity-detail-document__body:visible')).toHaveCount(2);
    const amount = drawer.locator('.entity-detail-row__amount').first();
    await expect(amount).toHaveCSS('text-align', 'left');
    const scroll = drawer.locator('.finance-drawer__body');
    await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
    expect(await scroll.evaluate(el => el.scrollTop > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 2)).toBe(true);
    expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({animations: "disabled", path: info.outputPath(`invoices-${width}.png`)});
    await scroll.evaluate(el => { el.scrollTop = 0; });
    await page.screenshot({animations: "disabled", path: info.outputPath(`invoices-top-${width}.png`)});
  }
  await drawer.getByRole('button', {name: '关闭详情抽屉'}).click();
  await expect(drawer).toBeHidden();
  // React Aria restores grid focus to the originating cell and its first control.
  await expect.poll(() => trigger.evaluate(el => el.closest("td")?.contains(document.activeElement))).toBe(true);
});

test('bank source opens without split IO and aligns dates, money and account fields', async ({page}, info) => {
  await installDeterministicApiMocks(page, {sessionMode: 'user'});
  let splitReads = 0;
  page.on('request', request => { if (/\/splits(?:\?|$)/.test(request.url())) splitReads++; });
  await page.route('**/api/bank-transactions/*/source-detail', route => route.fulfill({json: {detail_available: true, sections: [
    {title: '交易信息', document_id: 'bank', document_kind: 'bank', bank_transaction_id: 'bank', fields: [{label: '交易日期', value: '2026-09-24'}, {label: '支出金额', value: '2725.00'}, {label: '余额', value: '33645.36'}]},
    {title: '账户信息', document_id: 'bank', document_kind: 'bank', bank_transaction_id: 'bank', fields: [{label: '账号', value: '15990259060093'}, {label: '对方户名', value: '测试设备有限公司'}]},
  ]}}));
  await page.goto('/bank-details');
  await page.getByRole('button', {name: /^查看银行流水.*详情$/}).first().click();
  const drawer = page.getByRole('dialog', {name: '银行流水详情'});
  await expect(drawer.getByText('33645.36')).toBeVisible();
  for (const width of [1440, 480]) {
    await page.setViewportSize({width, height: 800});
    const x = await drawer.locator('.entity-detail-table td').evaluateAll(cells => cells.map(cell => cell.getBoundingClientRect().x));
    expect(Math.max(...x) - Math.min(...x)).toBeLessThan(2);
    expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({animations: "disabled", path: info.outputPath(`bank-${width}.png`)});
  }
  expect(splitReads).toBe(0);
  await expect(drawer.getByRole('button', {name: '流水子项拆分'})).toBeVisible();
});
