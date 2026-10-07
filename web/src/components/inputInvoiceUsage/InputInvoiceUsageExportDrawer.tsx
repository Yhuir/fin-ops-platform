import { useCallback } from 'react';
import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { fetchInputInvoiceUsageExportSummary, downloadInputInvoiceUsageSelection } from '../../features/inputInvoiceUsage/api';
import type { InputInvoiceUsageQuery } from '../../features/inputInvoiceUsage/types';
import type { ExportSelection } from '../../features/exports/types';
import { calendarMonthRange } from '../../features/dateTime';

export default function InputInvoiceUsageExportDrawer({ open, onClose, query }: {
  open: boolean; onClose: () => void; query: InputInvoiceUsageQuery;
}) {
  const loadSummary = useCallback((selection: ExportSelection, signal: AbortSignal) => fetchInputInvoiceUsageExportSummary(selection, signal, query), [query]);
  const download = useCallback((selection: ExportSelection) => downloadInputInvoiceUsageSelection(selection, query), [query]);
  const dates = calendarMonthRange(query.month);
  const values: Record<string, string[]> = {};
  for (const filter of query.filters) {
    if (['relation_status', 'payment_status'].includes(filter.field)) {
      if (filter.operator === 'in' && filter.values) values[filter.field] = filter.values;
      else if (filter.operator === 'equals' && typeof filter.value === 'string') values[filter.field] = [filter.value];
    }
  }
  return open ? <FilteredExportDrawer title="导出进项发票" unit="张" onClose={onClose} loadSummary={loadSummary} download={download}
    initialSelection={{ values, startDate: query.invoiceDateFrom || dates.from, endDate: query.invoiceDateTo || dates.to }} /> : null;
}
