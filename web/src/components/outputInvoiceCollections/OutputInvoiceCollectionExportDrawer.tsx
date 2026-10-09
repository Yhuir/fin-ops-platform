import { useCallback, useState } from "react";
import FilteredExportDrawer from "../common/FilteredExportDrawer";
import { fetchOutputInvoiceCollectionExportSummary, downloadOutputInvoiceCollectionExport } from "../../features/outputInvoiceCollections/api";
import type { OutputInvoiceCollectionQuery } from "../../features/outputInvoiceCollections/types";

export default function OutputInvoiceCollectionExportDrawer({ onClose, query }: {
  onClose: () => void; query: OutputInvoiceCollectionQuery;
}) {
  const [scope] = useState(() => structuredClone(query));
  const loadSummary = useCallback((signal: AbortSignal) => fetchOutputInvoiceCollectionExportSummary(scope, signal), [scope]);
  const download = useCallback(() => downloadOutputInvoiceCollectionExport(scope), [scope]);
  return <FilteredExportDrawer title="导出销项发票" unit="张销项发票" onClose={onClose} loadSummary={loadSummary} download={download} />;
}
