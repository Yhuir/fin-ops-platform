import { expect, test, type Page } from "./fixtures/strictTest";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function geometry(page: Page) {
  return page.locator('.etc-batch-rail, .etc-status-segmented, .etc-batch-pagination').evaluateAll(elements => elements.map(el => {
    const r = el.getBoundingClientRect(); return [r.x, r.y, r.width, r.height];
  }));
}
function expectStable(actual: number[][], baseline: number[][]) {
  actual.forEach((rect, i) => rect.forEach((value, axis) => expect(Math.abs(value - baseline[i][axis]), JSON.stringify({ i, axis, actual, baseline })).toBeLessThanOrEqual(1)));
}

for (const width of [1600, 1280, 960, 390]) {
  test(`ETC rail preserves geometry and complete content through empty, loading and populated states at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const api = await installDeterministicApiMocks(page, { sessionMode: "admin", etcTicketInitialBusinessBatchStatus: "manually_marked_submitted", etcTicketBusinessBatchTotal: 9 });
    let release: (() => void) | undefined;
    let hold = true;
    await page.route('**/api/etc/business-batches?**', async route => {
      if (new URL(route.request().url()).searchParams.get('bucket') !== 'submitted') return route.fallback();
      if (hold) await new Promise<void>(resolve => { release = resolve; });
      await route.fallback();
    });
    await page.goto('/etc-tickets');
    const rail = page.getByRole('region', { name: 'ETC批次列表区' });
    const status = page.getByRole('radiogroup', { name: 'ETC批次状态' });
    await expect(status.getByRole('radio', { name: '未提交 0批' })).toBeEnabled();
    await expect(rail.getByText('无匹配批次。')).toHaveCount(0);
    const baseline = await geometry(page);
    await status.getByRole('radio', { name: '已提交 9批' }).click();
    await expect(rail.locator('.etc-batch-scroll')).toHaveAttribute('aria-busy', 'true');
    await expect(rail.locator('.etc-batch-row')).toHaveCount(0);
    await expect(rail.getByText('加载中。')).toHaveCount(0);
    expectStable(await geometry(page), baseline);
    await expect.poll(() => Boolean(release)).toBe(true); hold = false; release!();
    await expect(rail.locator('.etc-batch-row')).toHaveCount(9);
    await expect(rail.locator('.etc-batch-scroll')).toHaveAttribute('aria-busy', 'false');
    await expect(status.getByRole('radio', { name: '已提交 9批' })).toBeEnabled();
    expectStable(await geometry(page), baseline);
    // Exercise wrapping with realistic cross-year titles and large summary text without changing business state.
    await rail.locator('.etc-row-title strong').evaluateAll(nodes => nodes.forEach(node => { node.textContent = '2025年12月–2026年1月 ETC发票'; }));
    await rail.locator('.etc-batch-fields span').evaluateAll(nodes => nodes.forEach(node => { node.textContent = '9999 张 · 123456789.12 元'; }));
    const clips = await rail.locator('.etc-batch-row').evaluateAll(rows => rows.map(row => {
      const bounds = row.getBoundingClientRect();
      return Array.from(row.querySelectorAll('.etc-row-title, .etc-batch-fields, .etc-icon-action')).some(child => {
        const r = child.getBoundingClientRect(); return r.bottom > bounds.bottom + 1 || r.right > bounds.right + 1;
      });
    }));
    expect(clips).toEqual(Array(9).fill(false));
    const last = rail.locator('.etc-batch-row').last(); await last.scrollIntoViewIfNeeded();
    const lastBox = await last.boundingBox(); const footerBox = await rail.locator('.etc-batch-pagination').boundingBox();
    expect(lastBox!.y + lastBox!.height).toBeLessThanOrEqual(footerBox!.y);
    const first = rail.locator('.etc-list-row-button').first(); await first.scrollIntoViewIfNeeded();
    await expect(first).toHaveAttribute('aria-current', 'true');
    const before = api.count('GET /api/etc/business-batches/etc-business-e2e-001');
    await first.click(); expect(api.count('GET /api/etc/business-batches/etc-business-e2e-001')).toBe(before);
    await page.screenshot({ path: testInfo.outputPath(`etc-rail-${width}.png`), animations: 'disabled' });
    for (const name of ['暂存 0批', '未提交 0批']) {
      await status.getByRole('radio', { name }).click();
      await expect(status.getByRole('radio', { name })).toBeEnabled();
      await expect(rail.locator('.etc-batch-row')).toHaveCount(0);
      expectStable(await geometry(page), baseline);
      await expect(rail.getByText('无匹配批次。')).toHaveCount(0);
    }
  });
}

test('ETC list errors remain visible inside the scroll area without moving controls', async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  let fail = true;
  await page.route('**/api/etc/business-batches?**', route => fail
    ? route.fulfill({ status: 503, json: { error: 'etc_list_unavailable', message: '批次列表暂不可用，请刷新重试。' } })
    : route.fallback());
  await page.goto('/etc-tickets');
  const rail = page.getByRole('region', { name: 'ETC批次列表区' });
  await expect(rail.getByText('批次列表暂不可用，请刷新重试。')).toBeVisible();
  const baseline = await geometry(page);
  fail = false;
  await page.getByRole('button', { name: '重试读取', exact: true }).click();
  await expect(rail.locator('.etc-batch-row')).toHaveCount(1);
  await expect(rail.getByText('批次列表暂不可用，请刷新重试。')).toHaveCount(0);
  expectStable(await geometry(page), baseline);
});
