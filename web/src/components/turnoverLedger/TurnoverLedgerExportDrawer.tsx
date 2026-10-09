import { useCallback } from "react";
import FilteredExportDrawer from "../common/FilteredExportDrawer";
import { downloadTurnoverLedgerExport, fetchTurnoverLedgerExportSummary } from "../../features/turnoverLedger/api";
import type { FetchTurnoverLedgerRequest } from "../../features/turnoverLedger/types";

export default function TurnoverLedgerExportDrawer({ query, onClose }: {
  query: Pick<FetchTurnoverLedgerRequest, "family" | "query" | "settlementStatus">;
  onClose: () => void;
}) {
  const loadSummary = useCallback((signal: AbortSignal) => fetchTurnoverLedgerExportSummary({ ...query, signal }), [query]);
  const download = useCallback(() => downloadTurnoverLedgerExport(query), [query]);
  return <FilteredExportDrawer title="下载往来款台账" unit="个往来对象" loadSummary={loadSummary} download={download} onClose={onClose} />;
}
