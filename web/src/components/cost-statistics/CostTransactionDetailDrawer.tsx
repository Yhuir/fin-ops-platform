import { Button } from "@heroui/react";

import type { CostTransactionDetail } from "../../features/cost-statistics/types";
import AppDrawer from "../common/AppDrawer";
import CostTransactionDetailPanel from "./CostTransactionDetailPanel";

type CostTransactionDetailDrawerProps = {
  open: boolean;
  detail: CostTransactionDetail["transaction"] | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
  onRetry: () => void;
};

export default function CostTransactionDetailDrawer({
  open,
  detail,
  loading,
  error,
  onClose,
  onRetry,
}: CostTransactionDetailDrawerProps) {
  return (
    <AppDrawer
      ariaBusy={loading}
      className="cost-transaction-detail-drawer"
      closeLabel="关闭流水详情"
      onClose={onClose}
      open={open}
      title="流水详情"
      width={560}
    >
      <div className="cost-transaction-detail-drawer__body">
        {loading ? (
          <div aria-label="流水详情加载中" className="cost-detail-loading" role="status">
            <span />
            <span />
            <span />
            <span />
            <span />
          </div>
        ) : null}
        {!loading && error ? (
          <div className="cost-detail-error" role="alert">
            <span>{error}</span>
            <Button onPress={onRetry} size="sm" variant="secondary">
              重试
            </Button>
          </div>
        ) : null}
        {!loading && !error && detail ? <CostTransactionDetailPanel detail={detail} /> : null}
      </div>
    </AppDrawer>
  );
}
