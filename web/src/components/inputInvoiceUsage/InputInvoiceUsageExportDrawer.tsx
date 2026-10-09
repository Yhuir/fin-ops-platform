import { useCallback, useState } from "react";
import FilteredExportDrawer from "../common/FilteredExportDrawer";
import { fetchInputInvoiceUsageExportSummary, downloadInputInvoiceUsageExport } from "../../features/inputInvoiceUsage/api";
import type { InputInvoiceUsageQuery } from "../../features/inputInvoiceUsage/types";

export default function InputInvoiceUsageExportDrawer({ onClose, query }: {
  onClose: () => void; query: InputInvoiceUsageQuery;
}) {
  const [scope] = useState(() => structuredClone(query));
  const loadSummary = useCallback((signal: AbortSignal) => fetchInputInvoiceUsageExportSummary(scope, signal), [scope]);
  const download = useCallback(() => downloadInputInvoiceUsageExport(scope), [scope]);
  return <FilteredExportDrawer title="导出进项发票" unit="张进项发票" onClose={onClose} loadSummary={loadSummary} download={download} />;
}
