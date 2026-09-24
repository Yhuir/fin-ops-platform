import { afterEach, expect, test, vi } from 'vitest';
import { fetchInputInvoiceUsageRows } from '../features/inputInvoiceUsage/api';
import { fetchOutputInvoiceCollectionRows } from '../features/outputInvoiceCollections/api';
import { mapPendingInvoiceRow } from '../features/pendingInvoices/api';

const bank = { id: 'interest', parent_row_id: 'loan', amount: '1497.22', original_amount: '1001497.22', counterpartyName: '贷款户' };
const parts = [{ id: 'interest', category_code: 'interest', category_label: '利息', category_path: ['费用', '利息'], amount: '1497.22' }];
const query = { page: 1, pageSize: 20, keyword: '', invoiceDateFrom: '', invoiceDateTo: '', month: '', filters: [], sortField: '', sortDirection: '' as const };
afterEach(() => vi.unstubAllGlobals());

test.each([
  ['input', fetchInputInvoiceUsageRows],
  ['output', fetchOutputInvoiceCollectionRows],
] as const)('%s preserves business amount and reads parent display aggregate without summing child identities', async (_name, fetchRows) => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ rows: [{ id: 'invoice', invoice: {}, bank: {
    primary: bank, summaries: [bank, { ...bank, id: 'principal', amount: '1000000.00' }],
    original_amount: '1001497.22', original_transaction_count: 1, bank_split_parts: parts,
    relationCount: 2, receivedTotal: '1497.22',
  } }] }), { status: 200 })));
  const response = await fetchRows(query);
  expect(response.rows[0].bank.originalAmount).toBe('1001497.22');
  expect(response.rows[0].bank.originalTransactionCount).toBe(1);
  expect(response.rows[0].bank.primary?.amount).toBe('1497.22');
  expect(response.rows[0].bank.primary?.originalAmount).toBe('1001497.22');
  expect(response.rows[0].bank.bankSplitParts).toEqual(parts);
});

test('pending invoice mapping keeps invoice paid total distinct from original bank display', () => {
  const row = mapPendingInvoiceRow({ id: 'row', bank_transaction: bank, bank_transactions: {
    primary: bank, original_amount: '1001497.22', original_transaction_count: 1,
    bank_split_parts: parts, payment_summary: { paid_total: '1497.22' },
  }, invoice_acquisition_status: { code: 'paid_invoiced', label: '已支付已开票', primary_action: 'none' } });
  expect(row.bankTransaction.originalAmount).toBe('1001497.22');
  expect(row.bankTransaction.amount).toBe('1497.22');
  expect(row.bankTransactions.originalAmount).toBe('1001497.22');
  expect(row.bankTransactions.paymentSummary?.paidTotal).toBe('1497.22');
  expect(row.bankTransactions.bankSplitParts).toEqual(parts);
});
