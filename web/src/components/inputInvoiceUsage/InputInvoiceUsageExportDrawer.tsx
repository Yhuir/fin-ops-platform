import FilteredExportDrawer from '../common/FilteredExportDrawer';
import { fetchInputInvoiceUsageExportSummary, downloadInputInvoiceUsageSelection } from '../../features/inputInvoiceUsage/api';
export default function InputInvoiceUsageExportDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  return open ? <FilteredExportDrawer title="导出进项发票" unit="张" onClose={onClose} loadSummary={fetchInputInvoiceUsageExportSummary} download={downloadInputInvoiceUsageSelection} /> : null;
}
