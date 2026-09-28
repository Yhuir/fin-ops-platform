import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

for (const route of ['oa-pending-payments', 'output-invoice-collections', 'pending-invoices']) {
  test(`${route} query controls align and remain usable at desktop and narrow widths`, async ({ page }, info) => {
    await installDeterministicApiMocks(page, { sessionMode: 'user' });
    await page.goto(`/${route}`);
    await expect(page.locator('.finance-table__scroll').first()).toBeVisible();
    if (route === 'oa-pending-payments') {
      await expect(page.getByRole('radio', { name: /^已关联流水/ })).toBeVisible();
      await expect(page.getByRole('radio', { name: /^未关联流水/ })).toBeVisible();
      await expect(page.getByTestId('oa-pending-payments-table-frame').getByRole('search')).toHaveCount(0);
    }
    if (route === 'pending-invoices') await expect(page.getByText(/^当前范围 .*笔流水/)).toHaveCount(0);
    for (const width of [1800, 1280, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      if (route === 'oa-pending-payments') {
        // Stress count-label width without changing query or business state.
        await page.getByRole('radiogroup', { name: '支付流水' }).locator('.app-segments__label').evaluateAll(labels => labels.forEach(label => {
          label.textContent = label.textContent!.replace(/\d+条/, '99999条');
        }));
      }
      const toolbar = page.locator(route === 'pending-invoices' ? '.pending-invoices-toolbar' : `.${route}-query`);
      const toolbarBox = await toolbar.boundingBox();
      expect(toolbarBox!.x).toBeGreaterThanOrEqual(0);
      expect(toolbarBox!.x + toolbarBox!.width).toBeLessThanOrEqual(width);
      expect(await toolbar.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
      const search = toolbar.getByRole('search');
      await expect(search.getByRole('button', { name: '查询' })).toBeInViewport();
      const searchBox = await search.boundingBox();
      expect(searchBox!.x + searchBox!.width).toBeLessThanOrEqual(width);
      expect(searchBox!.x).toBeGreaterThanOrEqual(0);
      if (route !== 'pending-invoices') {
        const boxes = await toolbar.locator('.business-period-picker, .query-search__field, .query-search > button').evaluateAll(elements => elements.map(el => {
          const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, height: r.height, right: r.right };
        }));
        for (const box of boxes) expect(Math.abs(box.height - 46)).toBeLessThanOrEqual(1);
        expect(Math.abs(boxes[1].y - boxes[2].y)).toBeLessThanOrEqual(1);
        if (width === 1800) {
          expect(Math.abs(boxes[0].y - boxes[1].y)).toBeLessThanOrEqual(1);
          expect(boxes[0].right).toBeLessThanOrEqual(boxes[1].x);
          const segments = toolbar.getByRole(route === 'oa-pending-payments' ? 'radiogroup' : 'tablist');
          const segmentBox = await segments.boundingBox();
          expect(Math.abs(segmentBox!.y - boxes[0].y)).toBeLessThanOrEqual(1);
          expect(Math.abs(segmentBox!.height - boxes[0].height)).toBeLessThanOrEqual(1);
        }
      }
      await page.screenshot({ path: info.outputPath(`${route}-${width}.png`), animations: 'disabled' });
    }
  });
}

test('OA toolbar preserves payment and month filters when searching and clearing', async ({ page }) => {
  const api = await installDeterministicApiMocks(page, { sessionMode: 'user' });
  await page.goto('/oa-pending-payments');
  await expect(page.locator('.finance-table__scroll')).toBeVisible();
  const nextRows = () => page.waitForResponse(r => new URL(r.url()).pathname === '/api/oa-pending-payments/rows');
  let response = nextRows();
  await page.getByRole('radio', { name: /^已关联流水/ }).click();
  await (await response).finished();
  await page.getByRole('button', { name: 'OA月份筛选：年月' }).click();
  response = nextRows();
  await page.getByRole('dialog', { name: 'OA月份筛选选择器' }).getByRole('button', { name: '四月', exact: true }).click();
  const monthUrl = new URL((await response).url());
  const month = monthUrl.searchParams.get('month');
  const search = page.getByRole('search');
  const before = api.count('GET /api/oa-pending-payments/rows');
  await search.getByRole('searchbox').fill('付款申请人');
  expect(api.count('GET /api/oa-pending-payments/rows')).toBe(before);
  response = nextRows();
  await search.getByRole('searchbox').press('Enter');
  let url = new URL((await response).url());
  expect(url.searchParams.get('keyword')).toBe('付款申请人');
  expect(url.searchParams.get('month')).toBe(month);
  expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual([{ field: 'payment_status', operator: 'in', values: ['paid'] }]);
  expect(url.searchParams.get('page')).toBe('1');
  response = nextRows();
  await search.getByRole('button', { name: '清除查询' }).click();
  url = new URL((await response).url());
  expect(url.searchParams.has('keyword')).toBe(false);
  expect(url.searchParams.get('month')).toBe(month);
  expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))[0].values).toEqual(['paid']);
  expect(api.count('GET /api/oa-pending-payments/rows') - before).toBe(2);
});
