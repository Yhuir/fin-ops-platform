import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

const numbers = ['2653400000097888906', '2653400000097888907'];
function invoiceSections() {
  return numbers.flatMap((number, index) => {
    const metadata = {document_id: `invoice-${index}`, document_kind: 'invoice', invoice_navigation: {polarity: index ? '红字' : '蓝字', counterpartyName: '测试科技有限公司', totalWithTax: index ? '-2100.00' : '2100.00', totalWithTaxInferred: index === 1, invoiceDate: '2026-07-15', invoiceNo: number}, document_title: `${index ? '红字' : '蓝字'} · 测试科技有限公司 · ${index ? '-' : ''}2100.00`};
    return [
      {title: '发票信息', fields: [{label: '数电发票号码', value: number}, {label: '开票日期', value: '2026-07-15'}, {label: '发票票种', value: '数电发票（普通发票）'}], ...metadata},
      {title: '购销双方', fields: [{label: '销方名称', value: '测试供应商有限公司'}, {label: '销方识别号', value: '915300000000000001'}, {label: '购买方名称', value: '测试科技有限公司'}, {label: '购买方识别号', value: '915300000000000002'}], ...metadata},
      {title: '金额与税额', fields: [{label: '不含税金额', value: index ? '-2079.21' : '2079.21'}, {label: '税率', value: index ? '1%' : '无法确定'}, {label: '税额', value: index ? '-20.79' : '20.79'}, {label: '价税合计', value: index ? '-2100.00（推算）' : '2100.00'}], ...metadata},
      {title: '业务信息', fields: [{label: '备注', value: '完整备注可换行。'.repeat(20)}], ...metadata},
    ];
  });
}

test('full invoice navigation, compact left-aligned values and one reachable scroll area', async ({page}, info) => {
  await installDeterministicApiMocks(page, {sessionMode: 'user'});
  let detailReads = 0;
  await page.route('**/api/output-invoice-collections/rows/*/relation-details*', route => {detailReads++; return route.fulfill({json: {kind: 'invoice', sections: invoiceSections()}});});
  await page.goto('/output-invoice-collections');
  const trigger = page.getByRole('button', {name: '红蓝票 · 2'}).first();
  await trigger.click();
  const drawer = page.getByRole('dialog', {name: '发票详情', exact: true});
  await expect(drawer.getByRole('tablist', {name: '单据导航'})).toBeVisible();
  for (const width of [1440, 1024, 480]) {
    await page.setViewportSize({width, height: 800});
    await expect.poll(() => drawer.getByRole('tab', {selected: true}).evaluate(el => {
      const tab = el.getBoundingClientRect(), nav = el.closest('[role=tablist]')!.getBoundingClientRect();
      return tab.left >= nav.left-1 && tab.right <= nav.right+1;
    })).toBe(true);
    const nav = drawer.getByRole('tablist');
    for (const [index, number] of numbers.entries()) {
      const tab = nav.getByRole('tab').nth(index);
      await tab.click();
      await expect(tab).toHaveAttribute('aria-selected', 'true');
      await expect(drawer.getByRole('cell', {name: number, exact: true})).toBeVisible();
      await expect(drawer.getByRole('cell', {name: numbers[1-index], exact: true})).toHaveCount(0);
      await expect(drawer.getByRole('tabpanel')).toHaveCount(1);
      await expect(drawer.getByRole('cell', {name: index ? '-2100.00（推算）' : '无法确定', exact: true})).toBeVisible();
      expect(await tab.evaluate(el => el.scrollWidth <= el.clientWidth && getComputedStyle(el).textOverflow !== 'ellipsis')).toBe(true);
    }
    await expect(drawer.locator('.entity-detail-row__amount').first()).toHaveCSS('text-align', 'left');
    const scroll = drawer.locator('.finance-drawer__body');
    await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
    expect(await scroll.evaluate(el => el.scrollTop > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 2)).toBe(true);
    await expect(nav).toHaveCSS("position", "static");
    expect(await nav.evaluate(el => el.getBoundingClientRect().top < el.closest(".finance-drawer__body")!.getBoundingClientRect().top)).toBe(true);
    expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.screenshot({animations: "disabled", path: info.outputPath(`invoices-bottom-${width}.png`)});
    await nav.getByRole('tab').first().click();
    expect(await nav.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({animations: "disabled", path: info.outputPath(`invoices-top-${width}.png`)});
  }
  await page.setViewportSize({width: 1440, height: 900});
  await page.evaluate(() => {document.documentElement.style.zoom = '1.25';});
  expect(await drawer.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
  await page.screenshot({animations: 'disabled', path: info.outputPath('invoices-125-percent.png')});
  await page.evaluate(() => {document.documentElement.style.zoom = '';});
  expect(detailReads).toBe(1);
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

for (const kind of ['oa', 'bank'] as const) {
  test(`${kind} multi-document navigation preserves complete names, active fields and keyboard selection`, async ({page}, info) => {
    await installDeterministicApiMocks(page, {sessionMode: 'user'});
    const titles = kind === 'oa' ? ['张三 · 8000.00', '李四 · 0.00', '张三 · 8000.00']
      : ['云南某某设备供应与技术服务有限公司 · 10000.00', '收款公司 · 0.00', '另一家公司 · 500.00'];
    let reads = 0;
    const sections = titles.map((title, index) => ({document_id: `${kind}-${index}`, document_kind: kind, document_title: title,
      title: kind === 'oa' ? '申请信息' : '交易信息', fields: [{label: '备注', value: `单据 ${index+1} 原文`}, {label: '金额', value: String(index)}]}));
    await page.route(kind === 'oa' ? '**/api/oa-pending-payments/oa/*/detail' : '**/api/bank-transactions/*/source-detail', route => {
      reads++; return route.fulfill({json: {detail_available: true, sections}});
    });
    await page.goto(kind === 'oa' ? '/oa-pending-payments' : '/bank-details');
    await page.getByRole('button', {name: kind === 'oa' ? /^查看 OA .*详情$/ : /^查看银行流水.*详情$/}).first().click();
    const drawer = page.getByRole('dialog', {name: kind === 'oa' ? 'OA详情' : '银行流水详情', exact: true});
    const tabs = drawer.getByRole('tab');
    await expect(tabs).toHaveCount(3);
    for (let index = 0; index < 3; index++) {
      await tabs.nth(index).click();
      await expect(tabs.nth(index)).toHaveText(`${index+1}${titles[index]}`);
      await expect(drawer.getByRole('cell', {name: `单据 ${index+1} 原文`, exact: true})).toBeVisible();
      await expect(drawer.getByRole('tabpanel')).toHaveCount(1);
      await expect(drawer.getByRole('cell', {name: /单据 \d 原文/})).toHaveCount(1);
    }
    await tabs.first().focus();
    await page.keyboard.press('ArrowRight');
    await expect(tabs.nth(1)).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true');
    expect(reads).toBe(1);
    for (const width of [1440,480]) {
      await page.setViewportSize({width, height: 800});
      await tabs.first().click();
      if (width === 1440) expect(await drawer.getByRole('tablist').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await tabs.first().evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      await page.screenshot({animations: 'disabled', path: info.outputPath(`${kind}-${width}.png`)});
    }
  });
}

for (const count of [1, 3, 4, 10]) {
  test(`invoice grid shows all ${count} choices without horizontal scroll or selection reflow`, async ({page}, info) => {
    await installDeterministicApiMocks(page, {sessionMode: 'user'});
    const sections = Array.from({length: count}, (_, index) => ({...invoiceSections()[0], document_id: `grid-${index}`,
      invoice_navigation: {polarity: index % 2 ? '红字' : '蓝字', counterpartyName: index === 2 ? '成都智领趋势科技有限公司及其他超长项目技术服务供应商名称完整展示' : '成都智领趋势科技有限公司',
        totalWithTax: index % 2 ? '-182400.005' : '182400.00', invoiceDate: '2026-05-21', invoiceNo: `26532000008093027${index}`},
      fields: [{label: '发票号码', value: `26532000008093027${index}`}]}));
    let reads = 0;
    await page.route('**/api/output-invoice-collections/rows/*/relation-details*', route => {reads++; return route.fulfill({json: {kind: 'invoice', sections}});});
    await page.goto('/output-invoice-collections');
    await page.getByRole('button', {name: '红蓝票 · 2'}).first().click();
    const drawer = page.getByRole('dialog', {name: '发票详情', exact: true});
    await expect(drawer.getByRole('table')).toBeVisible();
    if (count === 1) { await expect(drawer.getByRole('tablist')).toHaveCount(0); return; }
    const nav = drawer.getByRole('tablist');
    await expect(nav.getByRole('tab')).toHaveCount(count);
    for (const width of [1440, 1024]) {
      await page.setViewportSize({width, height: 900});
      expect(await nav.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      const positions = () => nav.getByRole('tab').evaluateAll(tabs => tabs.map(tab => ({height: tab.getBoundingClientRect().height, top: (tab as HTMLElement).offsetTop, left: (tab as HTMLElement).offsetLeft, width: (tab as HTMLElement).offsetWidth})));
      const before = await positions();
      expect(before[0].top).toBe(before[1].top);
      if (count > 2) expect(before[2].top).toBeGreaterThan(before[0].top);
      await nav.getByRole('tab').last().click();
      expect(await positions()).toEqual(before);
      await expect(drawer.getByRole('cell', {name: `26532000008093027${count-1}`, exact: true})).toBeVisible();
      await drawer.locator('.finance-drawer__body').evaluate(el => {el.scrollTop = 0;});
      await page.screenshot({animations: 'disabled', path: info.outputPath(`grid-${count}-${width}.png`)});
    }
    expect(reads).toBe(1);
  });
}
