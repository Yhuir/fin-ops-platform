import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import EntityDetailContent, { preparePublicDetailSections } from "../common/EntityDetailContent";
import type {
  OutputInvoiceCollectionDetailResponse,
  OutputInvoiceCollectionDetailTarget,
} from "../../features/outputInvoiceCollections/types";

type OutputInvoiceCollectionDetailDrawerProps = {
  open: boolean;
  target: OutputInvoiceCollectionDetailTarget | null;
  loadDetail: (target: OutputInvoiceCollectionDetailTarget) => Promise<OutputInvoiceCollectionDetailResponse>;
  onClose: () => void;
};

export default function OutputInvoiceCollectionDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
}: OutputInvoiceCollectionDetailDrawerProps) {
  const [detail, setDetail] = useState<OutputInvoiceCollectionDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !target) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return undefined;
    }

    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    loadDetail(target)
      .then((payload) => {
        if (active) {
          setDetail(payload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "详情加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [loadDetail, open, target]);

  const title = detail?.title ?? drawerTitle(target);
  const sections = detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭详情抽屉"
      onClose={onClose}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      <div className="output-invoice-collection-drawer__body">
        <EntityDetailContent
          detailAvailable={detail?.detailAvailable}
          error={error}
          loading={loading}
          sections={sections}
          unavailableReason={detail?.unavailableReason}
        />
      </div>
    </AppDrawer>
  );
}

function drawerTitle(target: OutputInvoiceCollectionDetailTarget | null) {
  if (target?.kind === "bank" || target?.relationKind === "bank") {
    return "流水详情";
  }
  return "销项发票详情";
}
