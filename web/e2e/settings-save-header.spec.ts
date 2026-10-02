import { expect, test, type Page } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

async function geometry(page: Page) {
  return page.evaluate(() => {
    const rect = (selector: string) => {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing layout element: ${selector}`);
      const { x, y, width, height } = element.getBoundingClientRect();
      return { x, y, width, height };
    };
    return { header: rect('.settings-content-header'), tabs: rect('.settings-tabs [role=tablist]'), button: rect('.settings-primary-save') };
  });
}

test("all settings save actions share a stable desktop header and switching does not fetch", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "admin" });
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/workbench/settings')) requests.push(request.url()); });
  await page.goto('/settings');
  await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeVisible();
  // Visit each panel once so initial requests and lazy modules have settled.
  const tabs = ['银行账户', 'OA导入设置', 'OA申请人凭据', '访问账户', '数据重置'];
  for (const name of tabs) await page.getByRole('tab', { name, exact: true }).click();
  const initialRequests = requests.length;
  for (const width of [1920, 1440, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.getByRole('tab', { name: '银行账户', exact: true }).click();
    const baseline = await geometry(page);
    for (const [index, name] of tabs.entries()) {
      await page.getByRole('tab', { name, exact: true }).click();
      const header = page.getByRole('group', { name: '当前设置操作' });
      if (name === '数据重置') {
        await expect(header.getByRole('button')).toHaveCount(0);
        expect((await page.locator('.settings-tabs [role=tablist]').boundingBox())?.y).toBe(baseline.tabs.y);
      } else {
        const current = await geometry(page);
        expect(current).toEqual(baseline);
        await expect(page.getByRole('tabpanel').getByRole('button', { name: /^保存/ })).toHaveCount(0);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`settings-${width}-${index}.png`) });
    }
  }
  expect(requests.length).toBe(initialRequests);
});

test("credential failure preserves drafts; pending and feedback never move the form; switching retains ownership", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  let finish: (() => void) | undefined;
  let writes = 0;
  let fail = true;
  await page.route('**/api/workbench/settings/oa-applicant-credentials/header_test', async route => {
    expect(route.request().method()).toBe('PUT');
    writes += 1;
    expect(route.request().postDataJSON()).toMatchObject({ targetApplicantName: '测试申请人', oaUsername: 'header_test', password: 'test-only-password' });
    await new Promise<void>(resolve => { finish = resolve; });
    if (fail) return route.fulfill({ status: 400, json: { error: 'invalid_credentials', message: '测试凭据被拒绝' } });
    return route.fulfill({ json: { credential: { targetApplicantName: '测试申请人', targetApplicantCode: 'header_test', oaUsername: 'header_test', hasCredential: true, credentialStatus: 'configured' } } });
  });
  await page.goto('/settings');
  await page.getByRole('tab', { name: 'OA申请人凭据', exact: true }).click();
  await page.getByLabel('目标 OA 申请人', { exact: true }).fill('测试申请人');
  await page.getByLabel('申请人账号标识', { exact: true }).fill('header_test');
  await page.getByLabel('OA 登录账号', { exact: true }).fill('header_test');
  const password = page.getByLabel('OA 登录密码', { exact: true });
  await password.fill('test-only-password');
  const before = await geometry(page);
  const formBefore = await page.locator('.settings-credentials-form').boundingBox();
  await page.getByRole('button', { name: '保存凭据', exact: true }).click();
  await expect(password).toBeDisabled();
  expect(await geometry(page)).toEqual(before);
  await expect.poll(() => writes).toBe(1);
  finish!();
  await expect(page.getByRole('alert')).toContainText('OA 申请人凭据保存失败：操作失败，请稍后重试。');
  await expect(password).toHaveValue('test-only-password');
  expect(await page.locator('.settings-credentials-form').boundingBox()).toEqual(formBefore);
  expect(await geometry(page)).toEqual(before);
  await page.screenshot({ path: testInfo.outputPath('credential-failure.png') });
  fail = false;
  await page.getByRole('button', { name: '保存凭据', exact: true }).click();
  await expect.poll(() => writes).toBe(2);
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  finish!();
  await expect(page.getByText('已保存 OA 申请人凭据。', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '保存设置', exact: true })).toBeEnabled();
  await page.getByRole('tab', { name: 'OA申请人凭据', exact: true }).click();
  await expectNoUnexpectedSuccessUiErrors(page);
  await expect(password).toHaveValue('');
  await expect(page.getByLabel('申请人账号标识', { exact: true })).toHaveValue('header_test');
  await expect(page.getByRole('button', { name: '保存凭据', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '关闭设置反馈' }).click();
  await expect(page.locator('.settings-save-feedback')).toHaveCount(0);
});

test("ordinary save freezes its two draft panels, keeps errors and saves the exact draft on retry", async ({ page }) => {
  await installDeterministicApiMocks(page, { sessionMode: 'admin' });
  let finish: (() => void) | undefined;
  let writes = 0;
  let savedSettings: Record<string, unknown> & { oa_import: Record<string, unknown> };
  await page.route('**/api/workbench/settings', async route => {
    if (route.request().method() !== 'POST') return route.fallback();
    writes += 1;
    const body = route.request().postDataJSON();
    expect(body.oa_retention.cutoff_date).toBe('2026-02-01');
    expect(body).not.toHaveProperty('accounts');
    expect(body).not.toHaveProperty('oa_applicant_credentials');
    if (writes === 1) {
      await new Promise<void>(resolve => { finish = resolve; });
      return route.fulfill({ status: 400, json: { error: 'invalid_settings', message: '测试设置被拒绝' } });
    }
    savedSettings = { ...savedSettings, ...body, oa_import: { ...savedSettings.oa_import, ...body.oa_import } };
    return route.fulfill({ json: savedSettings });
  });
  const initialSettings = page.waitForResponse(response => new URL(response.url()).pathname === '/api/workbench/settings' && response.request().method() === 'GET');
  await page.goto('/settings');
  savedSettings = await (await initialSettings).json();
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await page.getByLabel('OA导入起始日期').fill('2026-02-01');
  const before = await geometry(page);
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByLabel('OA导入起始日期')).toBeDisabled();
  expect(await geometry(page)).toEqual(before);
  await page.getByRole('tab', { name: '银行账户', exact: true }).click();
  await expect(page.getByLabel('银行名称', { exact: true })).toBeDisabled();
  await expect.poll(() => writes).toBe(1);
  finish!();
  await expect(page.getByRole('alert')).toContainText('保存设置失败：操作失败，请稍后重试。');
  await page.getByRole('tab', { name: 'OA导入设置', exact: true }).click();
  await expect(page.getByLabel('OA导入起始日期')).toHaveValue('2026-02-01');
  expect(await geometry(page)).toEqual(before);
  await page.getByRole('button', { name: '保存设置', exact: true }).click();
  await expect(page.getByText('已保存银行账户与 OA 导入设置。', { exact: true })).toBeVisible();
  await expect(page.getByText('有未保存修改', { exact: true })).toHaveCount(0);
  expect(writes).toBe(2);
  await expectNoUnexpectedSuccessUiErrors(page);
});
