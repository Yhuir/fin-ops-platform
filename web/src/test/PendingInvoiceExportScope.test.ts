import { afterEach, expect, test, vi } from 'vitest';
import { downloadPendingInvoiceExport, fetchPendingInvoiceExportSummary } from '../features/pendingInvoices/api';
import type { FetchPendingInvoiceRowsRequest } from '../features/pendingInvoices/types';

afterEach(() => vi.unstubAllGlobals());
test('summary and download preserve direction, statuses, columns, dates and sort across pagination', async () => {
  const calls: URL[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost'); calls.push(url);
    if (url.pathname.endsWith('/export-summary')) return Response.json({ row_count: 1 });
    return new Response(new Blob(['export']), { headers: { 'X-Export-Count': '1', 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Content-Disposition': 'attachment; filename="test.xlsx"' } });
  }));
  const query: FetchPendingInvoiceRowsRequest = { direction: 'expense', filter: 'all', page: 4, pageSize: 50,
    keyword: '客户', sortField: 'amount', sortDirection: 'desc', filters: [
      { field: 'status_code', operator: 'in', values: ['paid_invoiced'] },
      { field: 'counterparty_name', operator: 'contains', value: '供应商' },
      { field: 'trade_date', operator: 'between', value: { from: '2026-01-01', to: '2026-02-01' } },
    ],
  };
  await fetchPendingInvoiceExportSummary(query, new AbortController().signal);
  await downloadPendingInvoiceExport(query);
  expect(calls).toHaveLength(2);
  expect(calls[0].search).toBe(calls[1].search);
  expect(calls[0].searchParams.get('keyword')).toBe('客户');
  expect(calls[0].searchParams.get('sort_field')).toBe('amount');
  expect(calls[0].searchParams.get('page')).toBeNull();
  expect(calls[0].searchParams.get('date_from')).toBeNull();
  expect(calls[0].searchParams.get('direction')).toBe('expense');
  expect(JSON.parse(calls[0].searchParams.get('filters')!)).toEqual(query.filters);
});
