import { useCallback, useState } from "react";
import FilteredExportDrawer from "../common/FilteredExportDrawer";
import { fetchOaPendingPaymentExportSummary, downloadOaPendingPaymentExport } from "../../features/oaPendingPayments/api";
import type { OaPendingPaymentQuery } from "../../features/oaPendingPayments/types";

export default function OaPendingPaymentExportDrawer({ onClose, query }: {
  onClose: () => void; query: OaPendingPaymentQuery;
}) {
  const [scope] = useState(() => structuredClone(query));
  const loadSummary = useCallback((signal: AbortSignal) => fetchOaPendingPaymentExportSummary(scope, signal), [scope]);
  const download = useCallback(() => downloadOaPendingPaymentExport(scope), [scope]);
  return <FilteredExportDrawer title="导出 OA" unit="条 OA" onClose={onClose} loadSummary={loadSummary} download={download} />;
}
