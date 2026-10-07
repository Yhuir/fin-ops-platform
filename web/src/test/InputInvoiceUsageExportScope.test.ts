import { afterEach, expect, test, vi } from 'vitest';
import { downloadInputInvoiceUsageSelection, fetchInputInvoiceUsageExportSummary } from '../features/inputInvoiceUsage/api';
import type { InputInvoiceUsageQuery } from '../features/inputInvoiceUsage/types';

const query: InputInvoiceUsageQuery = {
  page: 3, pageSize: 20, keyword: '工程发票', month: '2026-04', invoiceDateFrom: '', invoiceDateTo: '',
  filters: [{ field: 'usage_status', operator: 'in', values: ['used'] }, { field: 'oa_relation', operator: 'in', values: ['linked'] },
    { field: 'payment_status', operator: 'in', values: ['paid'] }],
  sortField: 'invoice_date', sortDirection: 'desc', activeWorkflow: null, detailTarget: null,
};
afterEach(() => vi.unstubAllGlobals());
test('export preview and download inherit search, date and independent filters with editable payment selection', async () => {
  const requests: URL[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost'); requests.push(url);
    return url.pathname.endsWith('export-summary')
      ? new Response(JSON.stringify({ row_count: 2, filter_options: { relation_status: [], payment_status: [] } }), { status: 200 })
      : new Response('xlsx', { status: 200, headers: { 'Content-Disposition': 'attachment; filename="invoices.xlsx"' } });
  }));
  const selection = { startDate: '2026-04-01', endDate: '2026-04-30', values: { payment_status: ['paid_equal'] } };
  expect((await fetchInputInvoiceUsageExportSummary(selection, new AbortController().signal, query)).rowCount).toBe(2);
  expect((await downloadInputInvoiceUsageSelection(selection, query)).fileName).toBe('invoices.xlsx');
  expect(requests).toHaveLength(2);
  for (const url of requests) {
    expect(url.searchParams.get('keyword')).toBe('工程发票');
    expect(url.searchParams.get('invoice_date_from')).toBe('2026-04-01');
    expect(url.searchParams.get('invoice_date_to')).toBe('2026-04-30');
    expect(url.searchParams.has('month')).toBe(false);
    expect(url.searchParams.get('sort_field')).toBe('invoice_date');
    expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual([
      ...query.filters.slice(0, 2), { field: 'payment_status', operator: 'in', values: ['paid_equal'] },
    ]);
  }
});
test('a failed export preview remains an error instead of reporting a successful zero', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ message: '导出范围读取失败' }), { status: 503 })));
  await expect(fetchInputInvoiceUsageExportSummary({ values: {}, startDate: '', endDate: '' }, new AbortController().signal, query)).rejects.toThrow();
});
