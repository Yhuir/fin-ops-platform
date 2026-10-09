import { afterEach, expect, test, vi } from 'vitest';
import { downloadInputInvoiceUsageExport, fetchInputInvoiceUsageExportSummary } from '../features/inputInvoiceUsage/api';
import type { InputInvoiceUsageQuery } from '../features/inputInvoiceUsage/types';

const query: InputInvoiceUsageQuery = {
  page: 3, pageSize: 20, keyword: '工程发票', month: '2026-04', invoiceDateFrom: '', invoiceDateTo: '',
  filters: [{ field: 'usage_status', operator: 'in', values: ['used'] }, { field: 'oa_relation', operator: 'in', values: ['linked'] },
    { field: 'payment_status', operator: 'in', values: ['paid'] }],
  sortField: 'invoice_date', sortDirection: 'desc', activeWorkflow: null, detailTarget: null,
};
afterEach(() => vi.unstubAllGlobals());
test('summary and download preserve every active filter, date and sort across pagination', async () => {
  const requests: URL[] = [];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost'); requests.push(url);
    return url.pathname.endsWith('export-summary')
      ? new Response(JSON.stringify({ row_count: 2, filter_options: { relation_status: [], payment_status: [] } }), { status: 200 })
      : new Response('xlsx', { status: 200, headers: { 'X-Export-Count': '2', 'Content-Disposition': 'attachment; filename="invoices.xlsx"' } });
  }));
  expect((await fetchInputInvoiceUsageExportSummary(query, new AbortController().signal)).rowCount).toBe(2);
  expect((await downloadInputInvoiceUsageExport(query)).fileName).toBe('invoices.xlsx');
  expect(requests).toHaveLength(2);
  for (const url of requests) {
    expect(url.searchParams.get('keyword')).toBe('工程发票');
    expect(url.searchParams.get('invoice_date_from')).toBeNull();
    expect(url.searchParams.get('invoice_date_to')).toBeNull();
    expect(url.searchParams.get('month')).toBe('2026-04');
    expect(url.searchParams.has('page')).toBe(false);
    expect(url.searchParams.has('page_size')).toBe(false);
    expect(url.searchParams.get('sort_field')).toBe('invoice_date');
    expect(JSON.parse(decodeURIComponent(url.searchParams.get('filters')!))).toEqual(query.filters);
  }
});
test('a failed export preview remains an error instead of reporting a successful zero', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ message: '导出范围读取失败' }), { status: 503 })));
  await expect(fetchInputInvoiceUsageExportSummary(query, new AbortController().signal)).rejects.toThrow();
});
