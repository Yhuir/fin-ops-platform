import { useEffect, useMemo, useState } from "react";

import type { PendingInvoiceRelationDetail, PendingInvoiceRelationDetailKind } from "../../features/pendingInvoices/types";
import EntityDetailContent, { preparePublicDetailSections } from "../common/EntityDetailContent";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRelationDrawerProps = {
  open: boolean;
  transactionId: string | null;
  detailKind?: PendingInvoiceRelationDetailKind;
  loadDetail: (transactionId: string) => Promise<PendingInvoiceRelationDetail>;
  onClose: () => void;
};

const drawerTitles: Record<PendingInvoiceRelationDetailKind, string> = {
  all: "详情",
  bank: "银行流水详情",
  invoice: "发票详情",
  oa: "OA详情",
};

export default function PendingInvoiceRelationDrawer({
  open,
  transactionId,
  detailKind = "all",
  loadDetail,
  onClose,
}: PendingInvoiceRelationDrawerProps) {
  const [detail, setDetail] = useState<PendingInvoiceRelationDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !transactionId) {
      setDetail(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    setDetail(null);
    loadDetail(transactionId)
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
  }, [loadDetail, open, transactionId]);

  const sections = useMemo(() => detail ? preparePublicDetailSections(detail.sections) : [], [detail]);

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭详情抽屉"
      onClose={onClose}
      open={open}
      title={drawerTitles[detailKind]}
      width="min(800px, 100vw)"
    >
      <EntityDetailContent
        emptyMessage="暂无可展示的详情。"
        error={error}
        loading={loading}
        loadingLabel="正在加载详情"
        sections={sections}
      />
    </PendingInvoiceDrawerFrame>
  );
}
