import { useCallback } from 'react';
import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { fetchPendingInvoiceExportSummary, downloadPendingInvoiceSelection } from '../../features/pendingInvoices/api';
import type { FetchPendingInvoiceRowsRequest } from '../../features/pendingInvoices/types';
import type { ExportSelection } from '../../features/exports/types';

export default function PendingInvoiceExportDrawer({ open, onClose, query }: {
  open: boolean; onClose: () => void; query: FetchPendingInvoiceRowsRequest;
}) {
  const loadSummary = useCallback((selection: ExportSelection, signal: AbortSignal) => fetchPendingInvoiceExportSummary(selection, signal, query), [query]);
  const download = useCallback((selection: ExportSelection) => downloadPendingInvoiceSelection(selection, query), [query]);
  const status = query.filters?.find(filter => filter.field === 'status_code');
  const direction = query.filters?.find(filter => filter.field === 'direction');
  const dates = query.filters?.find(filter => filter.field === 'trade_date');
  const directionValues = direction && 'values' in direction
    ? direction.values.filter(value => query.direction === 'all' || value === query.direction)
    : query.direction === 'all' ? undefined : [query.direction];
  return open ? <FilteredExportDrawer title="导出待找发票" unit="笔" onClose={onClose} loadSummary={loadSummary} download={download}
    initialSelection={{ values: {
      ...(directionValues ? { direction: directionValues } : {}),
      ...(status && 'values' in status ? { status_code: status.values } : {}),
    }, startDate: dates && 'value' in dates ? dates.value.from ?? '' : query.dateFrom ?? '',
    endDate: dates && 'value' in dates ? dates.value.to ?? '' : query.dateTo ?? '' }} /> : null;
}
