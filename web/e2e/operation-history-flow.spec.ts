import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';
import { expectNoUnexpectedSuccessUiErrors } from './fixtures/successAssertions';

const production = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === '1';
if (production) test.use({ screenshot: 'off', trace: 'off', video: 'off' });
const evidencePath = (name: string) => test.info().outputPath(name);
const operation = {
  operation_key: 'request:audit-e2e-request', actor_id: 'YNSYLP005', actor_name: '权限管理员', actor_account: 'YNSYLP005',
  page_key: 'reconciliation-workbench', category: 'business', category_label: '业务处理', action_code: 'workbench.relation.confirm',
  action_label: '确认关联', action_description: '将所选 OA、流水和发票确认关联。', object_type: 'workbench_relation', object_label: '关联关系', object_title: '云南溯源科技有限公司 · 1 条流水、2 张发票',
  started_at: '2026-10-11T01:44:36+08:00', completed_at: '2026-10-11T01:44:37+08:00', occurred_at: '2026-10-11T01:44:37+08:00', outcome: 'success',
  detail: {
    schema_version: 1, source: 'HTTP 请求', target: { kind: 'workbench_relation', title: '云南溯源科技有限公司', fields: [{ label: '涉及流水', value: '1 笔 · 650.00 元' }, { label: '涉及发票', value: '2 张 · 650.00 元' }] },
    artifacts: [], records: [], changes: [{ label: '关联状态', before: '未配对', after: '已配对' }], failure: null, legacy_evidence_missing: false,
    api_calls: [{ method: 'POST', path: '/api/workbench/actions/confirm-link', status_code: 200, request_id: 'audit-e2e-request', duration_ms: 125, parameters: [{ label: '原因', value: '核对后确认关联' }] }], activities: [],
  },
};

async function mockHistory(page: Parameters<typeof installDeterministicApiMocks>[0]) {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  await page.route('**/api/operations/history?*', route => {
    const cursor = new URL(route.request().url()).searchParams.get('cursor');
    return route.fulfill({ json: { rows: [{ ...operation, action_label: cursor ? '撤销关联' : '确认关联', detail: undefined }], next_cursor: cursor ? null : '2026-10-11T01:44:36+08:00|request:page-2', limit: 50 } });
  });
  await page.route('**/api/operations/history/request%3Aaudit-e2e-request', route => route.fulfill({ json: { operation } }));
}

test.describe('operation history interactions', () => {
  test.skip(production, 'Deterministic interaction scenarios use isolated API fixtures.');
  test.use({ viewport: { width: 1440, height: 900 } });

  test('filters compose, cursor pages replace rows, and closing detail preserves the visit', async ({ page }) => {
    await mockHistory(page);
    await page.goto('/operations/history');
    const table = page.getByRole('grid', { name: '操作历史' });
    await expect(table.getByText('确认关联', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '加载更多', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: '下一页', exact: true }).click();
    await expect(table.getByText('撤销关联', { exact: true })).toBeVisible();
    await expect(table.getByText('确认关联', { exact: true })).toHaveCount(0);
    await expect(page.getByText('第 2 页 · 本页 1 条')).toBeVisible();
    await page.getByRole('button', { name: '上一页', exact: true }).click();
    await expect(table.getByText('确认关联', { exact: true })).toBeVisible();
    await page.getByRole('radio', { name: '业务处理', exact: true }).click();
    await page.getByRole('combobox', { name: '页面', exact: true }).fill('关联台');
    await page.getByRole('option', { name: '关联台', exact: true }).click();
    await page.getByRole('button', { name: /操作结果$/ }).click();
    await page.getByRole('option', { name: '成功', exact: true }).click();
    await page.getByRole('button', { name: /操作人$/ }).click();
    await page.getByRole('option', { name: '权限管理员 · YNSYLP005', exact: true }).click();
    await page.getByRole('radio', { name: '近 7 天', exact: true }).click();
    await page.getByRole('searchbox', { name: '搜索操作历史' }).fill('确认');
    const response = page.waitForResponse(r => new URL(r.url()).pathname === '/api/operations/history' && new URL(r.url()).searchParams.get('category') === 'business');
    await page.getByRole('button', { name: '查询', exact: true }).click();
    const query = new URL((await response).url()).searchParams;
    expect(query.get('outcome')).toBe('success'); expect(query.get('page_key')).toBe('reconciliation-workbench'); expect(query.get('actor_id')).toBe('YNSYLP005'); expect(query.get('search')).toBe('确认'); expect(query.has('date_from')).toBe(true); expect(query.has('cursor')).toBe(false);
    await page.getByRole('button', { name: '查看确认关联详情' }).click();
    const drawer = page.getByRole('dialog', { name: '操作详情' });
    await expect(drawer.getByText('/api/workbench/actions/confirm-link')).toBeVisible();
    await expect(table.getByText('/api/workbench/actions/confirm-link')).toHaveCount(0);
    await expect(drawer.getByText('125 ms')).toBeVisible();
    await drawer.getByRole('button', { name: '关闭抽屉' }).click();
    await expect(page.getByRole('searchbox')).toHaveValue('确认');
    await expect(page.getByRole('radio', { name: '业务处理', exact: true })).toHaveAttribute('aria-checked', 'true');
    await page.getByRole('button', { name: /每页显示条数$/ }).click();
    await page.getByRole('option', { name: '200 条/页' }).click();
    await expect(page.getByText('第 1 页 · 本页 1 条')).toBeVisible();
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test('list and detail errors are explicit; missing historical evidence does not invent an API', async ({ page }) => {
    await mockHistory(page);
    let listFailed = true, detailFailed = true;
    await page.route('**/api/operations/history?*', route => listFailed ? route.fulfill({ status: 503, json: { error: 'history_unavailable', message: '历史读取失败' } }) : route.fallback());
    await page.route('**/api/operations/history/request%3Aaudit-e2e-request', route => detailFailed ? route.fulfill({ status: 404, json: { error: 'not_found', message: '操作证据不存在' } }) : route.fulfill({ json: { operation: { ...operation, detail: { ...operation.detail, api_calls: [], target: null, changes: [], legacy_evidence_missing: true } } } }));
    await page.goto('/operations/history');
    await expect(page.getByRole('alert')).toContainText('历史读取失败');
    listFailed = false;
    await page.getByRole('button', { name: '重试读取' }).click();
    await page.getByRole('button', { name: '查看确认关联详情' }).click();
    const drawer = page.getByRole('dialog', { name: '操作详情' });
    await expect(drawer.getByRole('alert')).toContainText('操作证据不存在');
    await expect(drawer.getByText('/api/workbench/actions/confirm-link')).toHaveCount(0);
    detailFailed = false;
    await drawer.getByRole('button', { name: '重试详情' }).click();
    await expect(drawer.getByText('未记录 API 调用信息。')).toBeVisible();
    await expect(drawer.getByText('未保存可核验的对象快照。')).toBeVisible();
    await expect(drawer.getByText(/证据启用之前/)).toHaveCount(0);
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test('Oil UI desktop, narrow, enlarged reading and motion evidence', async ({ page }, info) => {
    await mockHistory(page);
    await page.goto('/operations/history');
    await expect(page.getByRole('button', { name: '查看确认关联详情' })).toBeVisible();
    for (const width of [1920, 1440, 960, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      await expect(page.getByRole('button', { name: '查询', exact: true })).toBeInViewport();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await expect.poll(() => page.locator('.operation-history-query').evaluate(el => {
        const bounds = el.getBoundingClientRect();
        return [...el.querySelectorAll('button, input')].every(control => control.getBoundingClientRect().right <= bounds.right + 1);
      })).toBe(true);
      await page.screenshot({ path: evidencePath(`local-${width}.png`), animations: 'disabled' });
      if (width === 390) {
        await page.getByRole('button', { name: /时间范围$/ }).click();
        await page.getByRole('option', { name: '自定义', exact: true }).click();
        await page.getByLabel('开始日期', { exact: true }).fill('2026-10-01');
        await page.getByLabel('结束日期', { exact: true }).fill('2026-10-11');
        expect((await page.getByLabel('开始日期', { exact: true }).boundingBox())!.width).toBeGreaterThan(125);
        await page.screenshot({ path: evidencePath('local-390-custom.png'), animations: 'disabled' });
        await page.getByRole('button', { name: '重置', exact: true }).click();
        await expect(page.getByRole('button', { name: '查看确认关联详情' })).toBeVisible();
        await page.locator('.operation-history-table-frame .finance-table__scroll').evaluate(el => { el.scrollLeft = el.scrollWidth; });
        await expect(page.getByRole('button', { name: '查看确认关联详情' })).toBeInViewport();
        await page.screenshot({ path: evidencePath('local-390-table-right.png'), animations: 'disabled' });
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole('button', { name: '查看确认关联详情' }).click();
    const drawer = page.getByRole('dialog', { name: '操作详情' });
    await expect(drawer.getByText('API 调用', { exact: true })).toBeVisible();
    await page.screenshot({ path: evidencePath(`local-drawer.png`), animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 1000 });
    await expect(drawer.getByText('/api/workbench/actions/confirm-link')).toBeVisible();
    await page.screenshot({ path: evidencePath(`local-drawer-narrow.png`), animations: 'disabled' });
    await drawer.getByRole('button', { name: '关闭抽屉' }).click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
    await expect(page.getByRole('button', { name: '查询', exact: true })).toBeVisible();
    await page.screenshot({ path: evidencePath(`local-200percent.png`), animations: 'disabled' });
    await page.evaluate(() => { document.documentElement.style.zoom = ''; });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.getByRole('button', { name: '查看确认关联详情' }).click();
    await expect(drawer.getByText('API 调用', { exact: true })).toBeVisible();
    await expect.poll(() => drawer.evaluate(el => el.getAnimations().filter(a => a.playState === 'running').length)).toBe(0);
    await test.info().attach('ui-evidence', { body: JSON.stringify({ viewport: [1920, 1440, 960, 390], enlarged: '200%', source: 'deterministic API fixture', reducedMotion: true, run: info.repeatEachIndex }), contentType: 'application/json' });
    await expectNoUnexpectedSuccessUiErrors(page);
  });

  test('Oil UI motion captures the actual entrance, primary press and category transition', async ({ page }) => {
    await mockHistory(page);
    await page.addInitScript(() => {
      document.addEventListener('animationstart', event => {
        const element = event.target as HTMLElement;
        if (!element.matches('.operation-history-query')) return;
        const animation = element.getAnimations()[0];
        animation.pause(); animation.currentTime = 0;
        (window as typeof window & { historyMotion?: Animation }).historyMotion = animation;
      });
    });
    await page.goto('/operations/history');
    await expect(page.getByRole('button', { name: '查看确认关联详情' })).toBeVisible();
    const capture = async (name: string, duration: number) => {
      await expect.poll(() => page.evaluate(() => Boolean((window as typeof window & { historyMotion?: Animation }).historyMotion))).toBe(true);
      const values = [];
      for (const [phase, time] of [['start', 0], ['middle', duration / 2], ['end', duration]] as const) {
        values.push(await page.evaluate(time => {
          const animation = (window as typeof window & { historyMotion?: Animation }).historyMotion!;
          animation.currentTime = time;
          const target = (animation.effect as KeyframeEffect).target!;
          const style = getComputedStyle(target);
          return { opacity: style.opacity, transform: style.transform, background: style.backgroundColor };
        }, time));
        await page.screenshot({ path: evidencePath(`motion-${name}-${phase}.png`) });
      }
      await page.evaluate(() => {
        const state = window as typeof window & { historyMotion?: Animation };
        state.historyMotion!.finish(); delete state.historyMotion;
      });
      expect(values[0]).not.toEqual(values[1]);
      expect(values[1]).not.toEqual(values[2]);
      await test.info().attach(`motion-${name}`, { body: JSON.stringify({ duration, values }), contentType: 'application/json' });
    };
    await capture('entrance', 220);
    const armTransition = (property: string) => page.evaluate(property => {
      const listener = (event: TransitionEvent) => {
        const target = event.target as HTMLElement;
        if (event.propertyName !== property || !target.closest('.operation-history-query')) return;
        const animation = target.getAnimations().find(item => item instanceof CSSTransition && item.transitionProperty === property)!;
        animation.pause(); animation.currentTime = 0;
        (window as typeof window & { historyMotion?: Animation }).historyMotion = animation;
        document.removeEventListener('transitionrun', listener);
      };
      document.addEventListener('transitionrun', listener);
    }, property);
    await armTransition('transform');
    await page.getByRole('button', { name: '查询', exact: true }).hover();
    await page.mouse.down();
    await capture('primary-press', 80);
    await page.mouse.up();
    await expect(page.getByRole('button', { name: '查看确认关联详情' })).toBeVisible();
    await armTransition('background-color');
    await page.getByRole('radio', { name: '业务处理', exact: true }).click();
    await capture('category', 180);
    await expect(page.getByRole('radio', { name: '业务处理', exact: true })).toHaveAttribute('aria-checked', 'true');
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});

test.describe('production operation history', () => {
  test.skip(!production, 'Production validation is explicitly enabled after release.');
  test.use({ viewport: { width: 1440, height: 1000 } });
  test('readonly history filtering, pagination and real API evidence', async ({ page }) => {
    const token = process.env.FIN_OPS_E2E_ADMIN_TOKEN;
    expect(token).toBeTruthy();
    await page.context().addCookies([{ name: 'Admin-Token', value: token!, domain: 'www.yn-sourcing.com', path: '/', secure: true, sameSite: 'Lax' }]);
    const writes: string[] = [];
    await page.route('**/fin-ops-api/**', route => {
      if (!['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) { writes.push(route.request().method()); return route.abort(); }
      return route.continue();
    });
    await page.goto('/fin-ops/operations/history');
    const table = page.getByRole('grid', { name: '操作历史' });
    await expect(table.getByRole('button', { name: /查看.*详情/ }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: '加载更多' })).toHaveCount(0);
    await page.screenshot({ path: evidencePath(`production-main.png`), animations: 'disabled' });
    await table.getByRole('button', { name: /查看.*详情/ }).first().click();
    const drawer = page.getByRole('dialog', { name: '操作详情' });
    await expect(drawer.getByText('API 调用', { exact: true })).toBeVisible();
    await page.screenshot({ path: evidencePath(`production-drawer.png`), animations: 'disabled' });
    await drawer.getByRole('button', { name: '关闭抽屉' }).click();
    await page.getByRole('radio', { name: 'OA 申请与凭据', exact: true }).click();
    const response = page.waitForResponse(r => r.url().includes('/api/operations/history?') && new URL(r.url()).searchParams.get('category') === 'oa');
    await page.getByRole('button', { name: '查询', exact: true }).click();
    const payload = await (await response).json();
    expect(payload.rows.length).toBeGreaterThan(0);
    expect(payload.rows.every((r: { category: string }) => r.category === 'oa')).toBe(true);
    await table.getByRole('button', { name: /查看.*详情/ }).first().click();
    await expect(drawer.getByText('API 调用', { exact: true })).toBeVisible();
    await expect(drawer.getByText(/password|Authorization|Admin-Token/)).toHaveCount(0);
    await drawer.getByRole('button', { name: '关闭抽屉' }).click();
    await page.getByRole('button', { name: '重置', exact: true }).click();
    await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: '下一页', exact: true }).click();
    await expect(page.getByText(/第 2 页/)).toBeVisible();
    expect(writes).toEqual([]);
    await expectNoUnexpectedSuccessUiErrors(page);
  });
});
