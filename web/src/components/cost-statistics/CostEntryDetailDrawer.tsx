import { Button } from "@heroui/react";

import type { CostEntryDetail, CostExplorerEntryRow } from "../../features/cost-statistics/types";
import AppDrawer from "../common/AppDrawer";
import CostEntryDetailPanel from "./CostEntryDetailPanel";

type Props = {
  open: boolean;
  rowKind: CostExplorerEntryRow["rowKind"] | null;
  detail: CostEntryDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetry: () => void;
  onAdjust?: (caseId: string) => void;
};

export default function CostEntryDetailDrawer({ open, rowKind, detail, loading, error, onClose, onRetry, onAdjust }: Props) {
  const allocationView = rowKind !== "bank_transaction";
  const title = rowKind === "manual_allocation" ? "人工成本明细" : allocationView ? "OA 成本归集明细" : "银行流水详情";
  return (
    <AppDrawer
      ariaBusy={loading}
      className="cost-transaction-detail-drawer"
      closeLabel={`关闭${title}`}
      onClose={onClose}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      <div className="cost-transaction-detail-drawer__body">
        {loading ? (
          <div aria-label={`${title}加载中`} className="cost-detail-loading" role="status">
            <span /><span /><span /><span /><span />
          </div>
        ) : null}
        {!loading && error ? (
          <div className="cost-detail-error" role="alert">
            <span>{error}</span>
            <Button onPress={onRetry} size="sm" variant="secondary">重试</Button>
          </div>
        ) : null}
        {!loading && !error && detail ? <>
          <CostEntryDetailPanel detail={detail} />
          {detail.kind !== "bank_transaction" && onAdjust ? <Button size="sm" variant="secondary" onPress={() => onAdjust(detail.reconciliation.relationCaseId)}>调整分配</Button> : null}
        </> : null}
      </div>
    </AppDrawer>
  );
}
