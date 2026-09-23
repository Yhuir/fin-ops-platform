import { fetchBankSplits, getBankTransactionSplitsBatch, saveBankSplits } from '../features/bankSplits/api';
import { ApiClientError } from '../features/apiClient';

const payload = { transaction_id: 'bank/1', canonical_transaction_id: 'canonical-1', amount: '100.00', direction: 'expense', version: 0, category_code: 'fee', parts: [], tag_definitions: [], can_edit: true };

test('reads full split fact using encoded bank identity and request abort signal', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json(payload)); vi.stubGlobal('fetch', fetch);
  const signal = new AbortController().signal;
  expect(await fetchBankSplits('bank/1', signal)).toEqual(payload);
  expect(String(fetch.mock.calls[0][0])).toContain('/api/bank-transactions/bank%2F1/splits');
  expect(fetch.mock.calls[0][1].signal).toBe(signal);
});

test('submits decimal strings, stable IDs, and version without introducing parent category', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ ...payload, version: 1, changed: true, affected_months: ['2026-09'] })); vi.stubGlobal('fetch', fetch);
  const request = { version: 0, parts: [{ id: 'existing', category_code: 'fee', amount: '0.10' }, { category_code: 'fee', amount: '99.90' }] };
  const response = await saveBankSplits('bank/1', request);
  expect(fetch.mock.calls[0][1].method).toBe('PUT');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual(request);
  expect(response.version).toBe(1);
});

test('preserves conflict status and performs no alternate endpoint retry', async () => {
  const fetch = vi.fn().mockResolvedValue(Response.json({ error: 'split_version_conflict', message: '流水已被修改' }, { status: 409 })); vi.stubGlobal('fetch', fetch);
  await expect(saveBankSplits('bank-1', { version: 1, parts: [] })).rejects.toMatchObject({ status: 409, code: 'split_version_conflict', message: '流水已被修改' });
  expect(fetch).toHaveBeenCalledOnce();
});

test('rejects invalid detail response instead of silently treating it as unsplit', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ amount: '100.00' })));
  await expect(fetchBankSplits('bank-1')).rejects.toThrow('流水拆分详情格式错误');
});

test('permission failure remains visible', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: 'forbidden', message: '无操作权限' }, { status: 403 })));
  await expect(fetchBankSplits('bank-1')).rejects.toBeInstanceOf(ApiClientError);
});


test('batch reads preserve requested identities and order in a single request', async () => {
  const second = { ...payload, transaction_id: 'bank-2', canonical_transaction_id: 'canonical-2' };
  const fetch = vi.fn().mockResolvedValue(Response.json({ rows: [second, payload] })); vi.stubGlobal('fetch', fetch);
  expect(await getBankTransactionSplitsBatch(['bank-2', 'bank/1'])).toEqual([second, payload]);
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch.mock.calls[0][1].method).toBe('POST');
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ transaction_ids: ['bank-2', 'bank/1'] });
});

test('batch rejects missing identities rather than rendering incomplete parent facts', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ rows: [payload] })));
  await expect(getBankTransactionSplitsBatch(['bank-1', 'bank-2'])).rejects.toThrow('批量流水拆分详情不完整');
});
