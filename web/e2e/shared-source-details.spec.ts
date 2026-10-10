import { pendingAcquisitionFixture } from '../src/test/pendingInvoiceFixtures';
import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks, oaPendingPaymentRowsPayload, pendingInvoiceRowsPayload, inputInvoiceUsageRowsPayload } from './fixtures/apiMocks';

for (const route of ['input-invoice-usage', 'oa-pending-payments', 'pending-invoices', 'output-invoice-collections']) {
  test(`${route}: counts expand the full relationship in the row with no detail IO`, async ({page}, info) => {
    const api = await installDeterministicApiMocks(page, {sessionMode:'user', inputInvoiceUsageRelationDetailList:true});
    if (route === 'input-invoice-usage') {
      const payload = inputInvoiceUsageRowsPayload(false,false,true);
      const row: any = payload.rows[0];
      row.bank.summaries = [{...row.bank.primary}];
      await page.route('**/api/input-invoice-usage/rows**', call=>call.fulfill({json:payload}));
    }
    if (route === 'oa-pending-payments') {
      const payload = oaPendingPaymentRowsPayload();
      const row: any = payload.rows[0];
      row.oa.summaries = [
        {...row.oa,oaId:row.oa.id,relationCaseId:'e2e-case'},
        {...row.oa,oaId:'oa-payment-e2e-002',applicantName:'关联申请人',amount:'3000.00',relationCaseId:'e2e-case'},
      ];
      row.oa.relationCount = 2;
      row.bankTransaction.summaries = [{...row.bankTransaction,bankTransactionId:row.bankTransaction.primaryBankTransactionId,relationCaseId:'e2e-case'}];
      row.bankTransaction.nonOutflowRelationEdges = [];
      row.invoice.summaries = [{...row.invoice,invoiceId:row.invoice.primaryInvoiceId,relationCaseId:'e2e-case'}];
      await page.route('**/api/oa-pending-payments/rows**', call=>call.fulfill({json:payload}));
    }
    if (route === 'pending-invoices') {
      const payload = pendingInvoiceRowsPayload(true);
      const row: any = payload.rows[0];
      const oa = row.oa.primary;
      row.oa.summaries = [oa,{...oa,id:'oa-o-202603-002',applicant:'关联申请人'}];
      row.oa.relation_count = 2;
      row.oa.has_multiple = true;
      row.bank_transactions = {original_transaction_count:1,relation_count:1,summaries:[{...row.bank_transaction,original_amount:'58000.00'}]};
      await page.route('**/api/pending-invoices/rows**', call=>call.fulfill({json:{...payload,acquisition_summary:pendingAcquisitionFixture(payload.rows as any[])}}));
    }
    const sourceReads: string[] = [];
    page.on('request', request => {
      if (/\/(?:relation-details?|detail)(?:\?|$)/.test(new URL(request.url()).pathname)) sourceReads.push(request.url());
    });
    await page.setViewportSize({width:1440,height:900});
    await page.goto(`/${route}`);
    const trigger = page.locator('.relation-count-button').first();
    await expect(trigger).toBeVisible();
    const row = trigger.locator('xpath=ancestor::tr');
    const allTriggers = row.locator('.relation-count-button');
    const initialRows = api.calls.filter(call=>call.startsWith(`GET /api/${route}/rows`)).length;
    await trigger.click();
    const expansion = page.getByRole('region',{name:'配对关系',exact:true});
    await expect(expansion).toBeVisible();
    await expect(expansion.getByText('关系摘要不完整，请重新查询后查看。')).toHaveCount(0);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(trigger).toHaveAttribute('aria-expanded','true');
    const motion = page.locator('.relation-expansion-motion');
    const durations = await motion.evaluate(node=>node.getAnimations().map(animation=>animation.effect!.getTiming().duration));
    // The live browser observes the native slide; timing details are attached for inspection.
    await info.attach('motion-duration',{body:JSON.stringify(durations),contentType:'application/json'});
    await expect.poll(()=>motion.evaluate(node=>node.getAnimations().length)).toBe(0);
    await page.mouse.move(5, 5);
    await trigger.evaluate(button => (button as HTMLElement).blur());
    const groupId = await row.getAttribute('data-relation-group');
    expect(groupId).toBeTruthy();
    const groupRows = page.locator('tr[data-relation-group]');
    await expect(groupRows).toHaveCount(2);
    await expect.poll(() => groupRows.evaluateAll(rows => rows.flatMap(row => [...row.children].map(cell => getComputedStyle(cell).backgroundColor))))
      .toEqual(Array(await groupRows.locator('th,td').count()).fill('rgb(244, 247, 251)'));
    const presentation = await groupRows.evaluateAll(rows => rows.map(row => ({
      group: row.getAttribute('data-relation-group'),
      cells: [...row.children].map(cell => ({
        background: getComputedStyle(cell).backgroundColor,
        line: getComputedStyle(cell).backgroundImage,
        lineWidth: getComputedStyle(cell).backgroundSize,
      })),
    })));
    await info.attach('relation-group-style', { body: JSON.stringify(presentation), contentType: 'application/json' });
    for (const item of presentation) {
      expect(item.group).toBe(groupId);
      expect(item.cells.map(cell => cell.background)).toEqual(Array(item.cells.length).fill('rgb(244, 247, 251)'));
      expect(item.cells[0].line).toContain('rgb(158, 181, 219)');
      expect(item.cells[0].lineWidth).toBe('3px 100%');
    }
    expect(await expansion.evaluate(node => getComputedStyle(node).backgroundColor)).toBe('rgb(244, 247, 251)');
    await expect(expansion.locator('li')).toHaveCount(await expansion.locator('.relation-expansion__detail').count());
    expect(sourceReads).toEqual([]);
    expect(api.calls.filter(call=>call.startsWith(`GET /api/${route}/rows`)).length).toBe(initialRows);
    expect(await expansion.evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBe(true);
    await page.screenshot({path:info.outputPath(`${route}-expanded.png`),animations:'disabled'});
    const sourceButton = expansion.getByRole('button',{name:/详情$/}).first();
    await sourceButton.click();
    const drawer = page.getByRole('dialog');
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole('tablist',{name:'单据导航'})).toHaveCount(0);
    expect(sourceReads).toHaveLength(1);
    await drawer.getByRole('button',{name:'关闭详情抽屉'}).click();
    await expect(expansion).toBeVisible();
    if (await allTriggers.count()>1) {
      await allTriggers.nth(1).click();
      await expect(expansion).toHaveCount(0);
      await allTriggers.nth(1).click();
      await expect(page.getByRole('region',{name:'配对关系'})).toHaveCount(1);
    }
    await page.emulateMedia({reducedMotion:'reduce'});
    await page.getByRole('region',{name:'配对关系'}).getByRole('button',{name:'收起',exact:true}).click();
    await expect(page.getByRole('region',{name:'配对关系'})).toHaveCount(0);
    await expect(page.locator('tr[data-relation-group]')).toHaveCount(0);
    expect(sourceReads).toHaveLength(1);
  });
}

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

test('large relationship stays bounded to the viewport and slides through real intermediate frames', async ({page}, info) => {
  await installDeterministicApiMocks(page, {sessionMode:'user'});
  const {outputInvoiceCollectionRowsPayload} = await import('./fixtures/apiMocks');
  const payload = outputInvoiceCollectionRowsPayload();
  const row: any = payload.rows[0];
  row.invoice_relations.relation_count = 47;
  row.relationSources[0] = {kind:'invoice', count:47, members:Array.from({length:47},(_,index)=>({
    id:`source-invoice-${index}`, title:`长发票号码-20261010-${index.toString().padStart(12,'0')}`,
    subtitle:'云南很长的供应商名称用于验证完整配对关系在窄视口下不会挤出表格区域有限公司',
    date:'2026-10-10', amount:index===0?'-12345.67':'12345.67', status:index===0?'红字':'蓝字', detailAvailable:true,
  }))};
  await page.route('**/api/output-invoice-collections/rows**', route=>route.fulfill({json:payload}));
  await page.setViewportSize({width:1280,height:900});
  await page.goto('/output-invoice-collections');
  await page.evaluate(()=>{
    const frames: {height:number;time:number}[] = [];
    (window as any).relationFrames=frames;
    let start: number | undefined;
    const record=(now:number)=>{
      const motion=document.querySelector('.relation-expansion-motion');
      if(motion) {
        start ??= now;
        frames.push({height:motion.getBoundingClientRect().height,time:now-start});
      }
      if(start===undefined || now-start<400) requestAnimationFrame(record);
    };
    requestAnimationFrame(record);
  });
  await page.locator('.relation-count-button').first().click();
  const expansion=page.getByRole('region',{name:'配对关系'});
  await expect(expansion.locator('li')).toHaveCount(48);
  await expect.poll(()=>page.evaluate(()=>(window as any).relationFrames.at(-1)?.time ?? 0)).toBeGreaterThan(300);
  const frames: {height:number;time:number}[]=await page.evaluate(()=>(window as any).relationFrames);
  const fullHeight=frames.at(-1)!.height;
  expect(frames.some(frame=>frame.height>0 && frame.height<fullHeight*.95)).toBe(true);
  await info.attach('native-slide-frames',{body:JSON.stringify(frames),contentType:'application/json'});
  // Pin native keyframes only for repeatable visual capture, then restore the finished slide.
  const motion=page.locator('.relation-expansion-motion');
  for(const [name,time] of [['start',0],['middle',90],['end',220]] as const){
    await motion.evaluate((node,time)=>{
      const animation=node.animate([{height:'0px'},{height:`${node.scrollHeight}px`}],{duration:220,easing:'cubic-bezier(.2,.7,.2,1)',fill:'both'});
      animation.pause(); animation.currentTime=time;
    },time);
    await page.screenshot({path:info.outputPath(`slide-${name}.png`)});
    await motion.evaluate(node=>node.getAnimations().forEach(animation=>animation.cancel()));
  }
  for(const width of [1280,1024,480]) {
    await page.setViewportSize({width,height:900});
    await expect.poll(()=>expansion.evaluate(node=>node.scrollWidth<=node.clientWidth+1)).toBe(true);
    if (width === 480) await expansion.locator('li').first().scrollIntoViewIfNeeded();
    await page.screenshot({path:info.outputPath(`relationship-long-${width}.png`)});
    if (width === 480) {
      await expansion.locator('.relation-expansion__column').last().scrollIntoViewIfNeeded();
      await page.screenshot({path:info.outputPath('relationship-long-480-bank.png')});
    }
  }
  await expansion.getByRole('button',{name:'收起',exact:true}).click();
  await expect(expansion).toHaveCount(0);
});
