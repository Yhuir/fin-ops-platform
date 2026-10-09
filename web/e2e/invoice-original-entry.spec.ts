import { Buffer } from 'node:buffer';
import { expect, test } from './fixtures/strictTest';
import { installDeterministicApiMocks } from './fixtures/apiMocks';

test('manual entry requires an original and sends its exact bytes without inventing missing values', async ({ page }) => {
  await installDeterministicApiMocks(page, {sessionMode: "user"});
  await page.route('**/imports/invoices/manual/recognize', route => route.fulfill({
    json: { values: { invoice_direction: 'input', invoice_nature: 'blue',
      invoice_number: '26532000000000000001', invoice_date: '2026-09-24',
      seller_name: '原件销方', seller_tax_no: 'SELLER', buyer_name: '原件购方', buyer_tax_no: 'BUYER',
      net_amount: '', tax_rate: '', tax_amount: '', total_with_tax: '113.00',
      invoice_kind: '电子发票（增值税专用发票）' } },
  }));
  let submitted: {invoices: Record<string, unknown>[]} | null = null;
  await page.route('**/imports/invoices/manual/preview', async route => {
    submitted = route.request().postDataJSON();
    await route.fulfill({ status: 400, json: { error: 'manual_invoice_source_conflict', message: '录入属性与原件不一致。' } });
  });
  await page.goto('/imports/invoices');
  await page.getByRole('button', { name: '发票录入', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: '发票录入' });
  await drawer.getByRole('button', { name: '预览', exact: true }).click();
  await expect(drawer.getByRole('alert')).toContainText('请上传发票原件');
  await drawer.getByText('上传识别', { exact: true }).click();
  const original = Buffer.from('exact-original-bytes');
  await page.getByRole('dialog', {name: '上传并识别发票'}).locator('input[type=file]').setInputFiles({ name: 'original.pdf', mimeType: 'application/pdf', buffer: original });
  await expect(drawer.getByLabel('发票号码')).toHaveValue('26532000000000000001');
  await expect(drawer.getByLabel('发票票种')).toHaveValue('电子发票（增值税专用发票）');
  await expect(drawer.getByLabel('不含税价格')).toHaveValue('');
  await expect(drawer.getByLabel('税额', { exact: true })).toHaveValue('');
  await drawer.getByRole('button', { name: '预览', exact: true }).click();
  await drawer.getByRole('button', { name: '保存信息', exact: true }).click();
  await drawer.getByRole('button', { name: '录入发票池', exact: true }).click();
  await expect(drawer.getByRole('alert')).toContainText('录入属性与原件不一致');
  expect(submitted).not.toBeNull();
  expect(submitted!.invoices[0]).toMatchObject({ source_file_name: 'original.pdf',
    source_file_content: original.toString('base64'), net_amount: '', tax_rate: '', tax_amount: '' });
  await expect(drawer).toBeVisible();
});
