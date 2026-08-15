import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import {
  default as EntityDetailContent,
  preparePublicDetailSections,
  type EntityDetailField,
  type EntityDetailSection,
} from "../common/EntityDetailContent";

export type InputInvoiceUsageDetailTarget = {
  kind: "invoice" | "bank" | "oa" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: string;
};

export type InputInvoiceUsageDetailField = EntityDetailField;

export type InputInvoiceUsageDetailSection = EntityDetailSection;

export type InputInvoiceUsageDetailPayload = {
  title?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: InputInvoiceUsageDetailSection[];
};

type InputInvoiceUsageDetailDrawerProps<TTarget extends InputInvoiceUsageDetailTarget> = {
  open: boolean;
  target: TTarget | null;
  loadDetail: (target: TTarget) => Promise<InputInvoiceUsageDetailPayload>;
  onClose: () => void;
};

const fallbackTitles: Record<InputInvoiceUsageDetailTarget["kind"], string> = {
  invoice: "发票详情",
  bank: "银行流水详情",
  oa: "OA详情",
  relationList: "关联明细",
};

export default function InputInvoiceUsageDetailDrawer<TTarget extends InputInvoiceUsageDetailTarget>({
  open,
  target,
  loadDetail,
  onClose,
}: InputInvoiceUsageDetailDrawerProps<TTarget>) {
  const [detail, setDetail] = useState<InputInvoiceUsageDetailPayload | null>(null);
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

  const title = detail?.title ?? (target ? fallbackTitles[target.kind] : "详情");
  const sections = detail ? preparePublicDetailSections(detail.sections) : [];

  return (
    <AppDrawer
      className="input-invoice-usage-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      title={title}
      width="min(800px, 100vw)"
      onClose={onClose}
    >
      <div className="input-invoice-usage-drawer-body">
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
