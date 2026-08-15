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
};

export default function CostEntryDetailDrawer({ open, rowKind, detail, loading, error, onClose, onRetry }: Props) {
  const allocationView = rowKind === "oa_allocation";
  const title = allocationView ? "OA 成本归集明细" : "银行流水详情";
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
        {!loading && !error && detail ? <CostEntryDetailPanel detail={detail} /> : null}
      </div>
    </AppDrawer>
  );
}
