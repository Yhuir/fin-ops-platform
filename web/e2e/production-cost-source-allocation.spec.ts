import { expect, test } from './fixtures/strictTest';
import { cents } from '../src/features/cost-statistics/sourceAllocation';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot: 'off', trace: 'off', video: 'off', viewport: { width: 1440, height: 1000 } });

test('production pending costs show only unresolved editors and preserve readonly automatic evidence', async ({page}, info) => {
  test.skip(!enabled || !token, 'Requires explicit production read-only verification and local token.');
  test.setTimeout(120_000);
  await page.context().addCookies([{name:'Admin-Token',value:token!,domain:'www.yn-sourcing.com',path:'/',secure:true,sameSite:'Lax'}]);
  const writes: string[] = [];
  await page.route('**/fin-ops-api/**', async route => {
    if (!['GET','HEAD','OPTIONS'].includes(route.request().method())) {
      writes.push(new URL(route.request().url()).pathname);
      await route.abort('blockedbyclient');
    } else await route.continue();
  });
  const response = await page.request.get('/fin-ops-api/api/cost-statistics/manual-allocations?status=pending&page_size=50');
  expect(response.status()).toBe(200);
  const list = await response.json();
  expect(list.items.length).toBe(list.row_count);
  const metrics: object[] = [];
  await page.goto('/fin-ops/cost-statistics');
  await expect(page.getByRole('heading',{name:'成本',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'打开成本人工分配'}).click();
  const drawer = page.getByRole('dialog',{name:'成本人工分配'});
  await expect(drawer.getByRole('radio',{name:`待分配 ${list.counts.pending}`,exact:true})).toBeChecked();
  const headings = drawer.locator('.cost-source-task-heading');
  await expect(headings).toHaveCount(list.items.length);
  for (let index=0;index<list.items.length;index++) {
    await expect(headings.nth(index)).toHaveAttribute('aria-expanded','false');
    const detail = await page.request.get(`/fin-ops-api/api/cost-statistics/manual-allocations/${encodeURIComponent(list.items[index].relation_case_id)}`);
    expect(detail.status()).toBe(200);
    const task = await detail.json();
    const lines = task.source_allocations ? task.source_allocations.cost_lines : [];
    const amounts = new Map<string,bigint>();
    const incomplete = new Set<string>();
    for (const line of lines) {
      amounts.set(line.unit_id,(amounts.get(line.unit_id) ?? 0n)+cents(line.amount)!);
      const source = task.bank_events.find((bank: any)=>bank.transaction_id===line.bank_transaction_id);
      if (!source.trade_time || !source.bank_account_label || !source.bank_tag_code) incomplete.add(line.unit_id);
    }
    const covered = task.units.filter((unit: any)=>task.decision_mode==='automatic' && task.status==='pending'
      && !task.pending_reasons.includes('allocation_stale') && unit.cost_eligible!==false && !incomplete.has(unit.unit_id)
      && cents(unit.oa_original_amount)!-cents(unit.outside_cost_amount)!>0n
      && amounts.get(unit.unit_id)===cents(unit.oa_original_amount)!-cents(unit.outside_cost_amount)!);
    const coverage = {unitIds:new Set<string>(covered.map((unit: any)=>unit.unit_id)),amount:covered.reduce((sum:bigint,unit:any)=>sum+amounts.get(unit.unit_id)!,0n)};
    const expectedEditors = task.units.filter((unit: any)=>!coverage.unitIds.has(unit.unit_id));
    const start = Date.now();
    await headings.nth(index).click();
    const table = drawer.getByRole('table',{name:'成本分配明细',exact:true});
    await expect(table.locator('tbody')).toHaveCount(expectedEditors.length + task.manual_items.length);
    if (task.decision_mode === 'automatic' && !task.pending_reasons.includes('allocation_stale')) {
      for (let unitIndex=0;unitIndex<expectedEditors.length;unitIndex++) {
        if (cents(expectedEditors[unitIndex].oa_original_amount)! > 0n) {
          await expect(table.locator('tbody').nth(unitIndex).getByText('零成本',{exact:true})).toHaveCount(0);
        }
      }
    }
    const readyMs = Date.now() - start;
    const resolved = drawer.locator('.cost-source-resolved');
    if (coverage.unitIds.size) {
      await expect(resolved).not.toHaveAttribute('open');
      await expect(resolved.locator('summary')).toContainText(`已自动确定 ${coverage.unitIds.size} 项`);
      await resolved.locator('summary').click();
      const known = drawer.getByRole('table',{name:'已自动确定的成本明细'});
      await expect(known.getByRole('textbox')).toHaveCount(0);
      await expect(known.locator('tbody tr')).toHaveCount(lines.filter((line: any)=>coverage.unitIds.has(line.unit_id)).length);
      await resolved.locator('summary').click();
    } else await expect(resolved).toHaveCount(0);
    await expect(drawer.getByRole('heading',{name:new RegExp(`OA费用 · ${expectedEditors.length} 项`)})).toBeVisible();
    const evidence = drawer.getByRole('table',{name:'OA 与流水对照',exact:true});
    for (const unit of expectedEditors) await expect(evidence).toContainText(unit.expense_content || unit.oa_apply_type);
    await page.screenshot({path:info.outputPath(`pending-${index}-desktop.png`),animations:'disabled'});
    await page.setViewportSize({width:1024,height:600});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
    await page.screenshot({path:info.outputPath(`pending-${index}-compact.png`),animations:'disabled'});
    await page.setViewportSize({width:1440,height:1000});
    metrics.push({caseId:task.relation_case_id,confirmedUnits:coverage.unitIds.size,editableUnits:expectedEditors.length,confirmedAmountCents:coverage.amount.toString(),readyMs});
    await headings.nth(index).click();
  }
  await drawer.getByRole('button',{name:/关闭/}).click();
  await page.getByRole('button',{name:'打开成本人工分配'}).click();
  for (let index=0;index<list.items.length;index++) await expect(headings.nth(index)).toHaveAttribute('aria-expanded','false');
  expect(writes).toEqual([]);
  await info.attach('production-pending-costs',{body:JSON.stringify(metrics,null,2),contentType:'application/json'});
});
