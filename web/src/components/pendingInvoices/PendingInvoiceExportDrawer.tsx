import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { fetchPendingInvoiceExportSummary, downloadPendingInvoiceSelection } from '../../features/pendingInvoices/api';
export default function PendingInvoiceExportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <FilteredExportDrawer title="导出待找发票" unit="笔" onClose={onClose} loadSummary={fetchPendingInvoiceExportSummary} download={downloadPendingInvoiceSelection} /> : null;
}
