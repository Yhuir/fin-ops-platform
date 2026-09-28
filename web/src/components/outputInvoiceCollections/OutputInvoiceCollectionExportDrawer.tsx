import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { fetchOutputInvoiceCollectionExportSummary, downloadOutputInvoiceCollectionSelection } from '../../features/outputInvoiceCollections/api';
export default function OutputInvoiceCollectionExportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <FilteredExportDrawer title="导出销项发票" unit="张" onClose={onClose} loadSummary={fetchOutputInvoiceCollectionExportSummary} download={downloadOutputInvoiceCollectionSelection} /> : null;
}
