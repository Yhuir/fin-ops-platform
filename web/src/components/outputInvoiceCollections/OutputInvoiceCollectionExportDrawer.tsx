import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { useCallback } from 'react';
import type { ExportSelection } from '../../features/exports/types';
import type { OutputInvoiceCollectionQuery } from '../../features/outputInvoiceCollections/types';
import { fetchOutputInvoiceCollectionExportSummary, downloadOutputInvoiceCollectionSelection } from '../../features/outputInvoiceCollections/api';
type Query = Pick<OutputInvoiceCollectionQuery, 'page' | 'pageSize' | 'keyword' | 'month' | 'invoiceDateFrom' | 'invoiceDateTo' | 'filters' | 'sortField' | 'sortDirection'>;
export default function OutputInvoiceCollectionExportDrawer({ open, onClose, query }: { open: boolean; onClose: () => void; query: Query }) {
  const loadSummary = useCallback((selection: ExportSelection, signal: AbortSignal) => fetchOutputInvoiceCollectionExportSummary(selection, signal, query), [query]);
  const download = useCallback((selection: ExportSelection) => downloadOutputInvoiceCollectionSelection(selection, query), [query]);
  const status = query.filters.find(filter => filter.field === 'collection_status');
  return open ? <FilteredExportDrawer title="导出销项发票" unit="张" onClose={onClose} loadSummary={loadSummary} download={download}
    initialSelection={{ values: status?.values ? { collection_status: status.values } : {}, startDate: query.invoiceDateFrom, endDate: query.invoiceDateTo }} /> : null;
}
