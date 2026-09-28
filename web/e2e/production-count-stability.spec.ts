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
    const selector = '.app-segments [role="radio"], .invoice-count-segments [role="tab"]';
    const controls=page.locator(selector);
    await expect(controls.first().locator('.stable-count')).toContainText(/\d/);
    const records=[];
    for(const index of [1,0]) {
      const target=controls.nth(index);
      await target.scrollIntoViewIfNeeded();
      await target.focus();
      const activeSelector=path==='oa-pending-payments' ? selector : '.app-segments:first-of-type [role="radio"], .invoice-count-segments:first-of-type [role="tab"]';
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
