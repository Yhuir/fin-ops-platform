import { afterEach, expect, test, vi } from 'vitest';
import { downloadPendingInvoiceSelection, fetchPendingInvoiceExportSummary } from '../features/pendingInvoices/api';
import type { FetchPendingInvoiceRowsRequest } from '../features/pendingInvoices/types';
import { pendingAcquisitionFixture } from './pendingInvoiceFixtures';

afterEach(() => vi.unstubAllGlobals());
test('export preview and download retain search, columns and sort while replacing editable scope and dates', async () => {
  const calls: URL[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost'); calls.push(url);
    if (url.pathname.endsWith('/export-summary')) return new Response(JSON.stringify({ row_count: 1,
      source_summary: { expense_rows: 1, income_rows: 0 }, acquisition_summary: pendingAcquisitionFixture([]),
    }), { headers: { 'Content-Type': 'application/json' } });
    return new Response(new Blob(['export']), { headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Content-Disposition': 'attachment; filename="test.xlsx"' } });
  }));
  const query: FetchPendingInvoiceRowsRequest = { direction: 'expense', filter: 'all', page: 4, pageSize: 50,
    keyword: '客户', sortField: 'amount', sortDirection: 'desc', filters: [
      { field: 'status_code', operator: 'in', values: ['paid_invoiced'] },
      { field: 'counterparty_name', operator: 'contains', value: '供应商' },
      { field: 'trade_date', operator: 'between', value: { from: '2026-01-01', to: '2026-02-01' } },
    ],
  };
  const selection = { values: { direction: ['expense'], status_code: ['invoice_not_fully_paid', 'invoice_amount_missing'] }, startDate: '2026-03-01', endDate: '2026-03-31' };
  await fetchPendingInvoiceExportSummary(selection, new AbortController().signal, query);
  await downloadPendingInvoiceSelection(selection, query);
  expect(calls).toHaveLength(2);
  expect(calls[0].search).toBe(calls[1].search);
  expect(calls[0].searchParams.get('keyword')).toBe('客户');
  expect(calls[0].searchParams.get('sort_field')).toBe('amount');
  expect(calls[0].searchParams.get('page')).toBeNull();
  expect(calls[0].searchParams.get('date_from')).toBe('2026-03-01');
  expect(JSON.parse(calls[0].searchParams.get('filters')!)).toEqual([
    { field: 'counterparty_name', operator: 'contains', value: '供应商' },
    { field: 'direction', operator: 'in', values: ['expense'] },
    { field: 'status_code', operator: 'in', values: ['invoice_not_fully_paid', 'invoice_amount_missing'] },
  ]);
});
