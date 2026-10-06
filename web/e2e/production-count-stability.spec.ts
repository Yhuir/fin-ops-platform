import { writeFile } from 'node:fs/promises';
import { expect, test } from './fixtures/strictTest';

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_COUNTS === '1';
const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
test.use({ screenshot:'off', trace:'off', video:'off', viewport:{width:1440,height:1000}, reducedMotion:'reduce' });

for (const path of ['oa-pending-payments','input-invoice-usage','output-invoice-collections','pending-invoices','etc-tickets','batch-accounting','bank-flow-rule-batches']) {
  test(`production read-only count stability: ${path}`, async ({page}, info) => {
    test.skip(!enabled || !token, 'Explicit production count verification and local admin token are required.');
    await page.context().addCookies([{name:'Admin-Token',value:token!,domain:'www.yn-sourcing.com',path:'/',secure:true,sameSite:'Lax'}]);
    const writes:string[]=[];
    const failures:string[]=[];
    page.on('request',r=>{if(['POST','PUT','PATCH','DELETE'].includes(r.method()))writes.push(`${r.method()} ${new URL(r.url()).pathname}`);});
    page.on('response',r=>{if(r.url().includes('/fin-ops-api/') && r.status()>=400)failures.push(`${r.status()} ${new URL(r.url()).pathname}`);});
    await page.goto(`/fin-ops/${path}`);
    const selector = '.app-segments [role="radio"], .invoice-count-segments [role="tab"], .table-classification button';
    const controls=page.locator(selector);
    await expect(controls.first().locator('.stable-count')).toContainText(/\d/, { timeout: 30_000 });
    const records=[];
    for(const index of [1,0]) {
      const target=controls.nth(index);
      await target.scrollIntoViewIfNeeded();
      await target.focus();
      const activeSelector=path==='oa-pending-payments' ? selector : '.app-segments:first-of-type [role="radio"], .invoice-count-segments:first-of-type [role="tab"], .table-classification button';
      // Sample the actual controls each animation frame while the real network request runs.
      const since=await page.evaluate(()=>performance.now());
      const sampling=page.evaluate(async (selector)=>{
        const frames:{at:number; controls:{text:string; width:number; height:number; x:number; y:number}[]}[]=[];
        const start=performance.now();
        while(performance.now()-start<1800){
          frames.push({at:performance.now()-start,controls:Array.from(document.querySelectorAll(selector)).map(e=>{const r=e.getBoundingClientRect();return {text:e.textContent??'',width:r.width,height:r.height,x:r.x,y:r.y};})});
          await new Promise(requestAnimationFrame);
        }
        return frames;
      },activeSelector);
      await target.click();
      const frames=await sampling;
      expect(frames.length).toBeGreaterThan(10);
      const initial=frames[0].controls;
      for(const frame of frames){
        expect(frame.controls.map(x=>x.text).join('')).not.toMatch(/[—…]/);
        // Direction-specific option sets may legitimately differ; the first toggle row stays fixed.
        const limit=path==='pending-invoices'?3:initial.length;
        expect(frame.controls.slice(0,limit).map(({width,height})=>({width,height}))).toEqual(initial.slice(0,limit).map(({width,height})=>({width,height})));
      }
      const requests=await page.evaluate(since=>performance.getEntriesByType('resource').filter(e=>e.startTime>=since && e.name.includes('/fin-ops-api/')).map(e=>({path:new URL(e.name).pathname,ms:Math.round(e.duration)})), since);
      records.push({index,frameCount:frames.length,first:initial,last:frames.at(-1)?.controls,requests});
    }
    expect(writes).toEqual([]);
    expect(failures).toEqual([]);
    await info.attach('production-count-measurements',{body:JSON.stringify(records,null,2),contentType:'application/json'});
    await page.screenshot({path:info.outputPath(`${path}.png`)});
  });
}

for (const path of ['oa-pending-payments', 'input-invoice-usage', 'pending-invoices']) {
  test(`production hierarchy interaction latency: ${path}`, async ({ page }, info) => {
    test.skip(!enabled || !token, 'Explicit production count verification and local admin token are required.');
    test.setTimeout(240_000);
    await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
    const failures: string[] = [];
    const reads: { path: string; method: string }[] = [];
    page.on('request', request => {
      if (request.url().includes('/fin-ops-api/')) reads.push({ path: new URL(request.url()).pathname, method: request.method() });
    });
    page.on('response', response => { if (response.url().includes('/fin-ops-api/') && response.status() >= 400) failures.push(`${response.status()} ${new URL(response.url()).pathname}`); });
    await page.goto(`/fin-ops/${path}`);
    const scope = path === 'input-invoice-usage'
      ? page.getByRole('tablist', { name: '进项发票关联分类', exact: true })
      : page.getByRole('region', { name: path === 'oa-pending-payments' ? 'OA 核对分类' : '待找发票分类', exact: true });
    const controls = path === 'input-invoice-usage' ? scope.getByRole('tab') : scope.locator('button.table-classification__parent');
    await expect(controls.first().locator('.stable-count')).toContainText(/\d/, { timeout: 30_000 });
    const samples: { feedbackMs: number; completeMs: number; requests: number }[] = [];
    for (let sample = 0; sample < 100; sample++) {
      await expect(page.locator('[data-count-pending="true"]')).toHaveCount(0);
      const selected = await controls.nth(0).getAttribute(path === 'input-invoice-usage' ? 'aria-selected' : 'aria-pressed');
      const target = controls.nth(selected === 'true' ? 1 : 0);
      const before = reads.length;
      await target.evaluate(element => {
        element.addEventListener('pointerdown', () => {
          const start = performance.now();
          element.setAttribute('data-latency-start', String(start));
          const painted = () => {
            if (element.getAttribute('aria-pressed') === 'true' || element.getAttribute('aria-checked') === 'true' || element.getAttribute('aria-selected') === 'true') {
              requestAnimationFrame(() => element.setAttribute('data-latency-ms', String(performance.now() - start)));
            } else requestAnimationFrame(painted);
          };
          element.removeAttribute('data-latency-ms');
          requestAnimationFrame(painted);
        }, { once: true });
      });
      const response = page.waitForResponse(response => new URL(response.url()).pathname === `/fin-ops-api/api/${path}/rows` && response.request().method() === 'GET');
      await target.click();
      expect((await response).status()).toBe(200);
      await expect(target).toHaveAttribute('data-latency-ms', /\d/);
      await expect(page.locator('[data-count-pending="true"]')).toHaveCount(0);
      const result = await target.evaluate(element => ({
        feedbackMs: Number(element.getAttribute('data-latency-ms')),
        completeMs: performance.now() - Number(element.getAttribute('data-latency-start')),
      }));
      samples.push({ ...result, requests: reads.length - before });
    }
    const percentile = (values: number[], fraction: number) => [...values].sort((a, b) => a - b)[Math.ceil(values.length * fraction) - 1];
    const feedback = samples.map(sample => sample.feedbackMs);
    const complete = samples.map(sample => sample.completeMs);
    const report = { path, samples: samples.length, feedback: { p50: percentile(feedback, .5), p95: percentile(feedback, .95), p99: percentile(feedback, .99) },
      complete: { p50: percentile(complete, .5), p95: percentile(complete, .95), p99: percentile(complete, .99) }, requestCounts: samples.map(sample => sample.requests), failures };
    const reportPath = info.outputPath('production-switch-latency.json');
    await writeFile(reportPath, JSON.stringify(report, null, 2));
    await info.attach('production-switch-latency', { path: reportPath, contentType: 'application/json' });
    expect(reads.filter(request => !['GET', 'HEAD', 'OPTIONS'].includes(request.method))).toEqual([]);
    expect(failures).toEqual([]);
    expect(samples.every(sample => sample.requests > 0)).toBe(true);
  });
}
