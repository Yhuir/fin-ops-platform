import { useCallback, useState } from "react";
import FilteredExportDrawer from "../common/FilteredExportDrawer";
import { fetchPendingInvoiceExportSummary, downloadPendingInvoiceExport } from "../../features/pendingInvoices/api";
import type { FetchPendingInvoiceRowsRequest } from "../../features/pendingInvoices/types";

export default function PendingInvoiceExportDrawer({ onClose, query }: {
  onClose: () => void; query: FetchPendingInvoiceRowsRequest;
}) {
  const [scope] = useState(() => structuredClone(query));
  const loadSummary = useCallback((signal: AbortSignal) => fetchPendingInvoiceExportSummary(scope, signal), [scope]);
  const download = useCallback(() => downloadPendingInvoiceExport(scope), [scope]);
  return <FilteredExportDrawer title="导出待找发票" unit="笔流水" onClose={onClose} loadSummary={loadSummary} download={download} />;
}
