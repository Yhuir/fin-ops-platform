import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

export type OutputInvoiceCollectionDetailTarget = {
  kind: "invoice" | "bank" | "relationList";
  id: string;
  rowId?: string;
};

export type OutputInvoiceCollectionDetailField = {
  label: string;
  value: string | number | null | undefined;
};

export type OutputInvoiceCollectionDetailSection = {
  title: string;
  fields: OutputInvoiceCollectionDetailField[];
};

export type OutputInvoiceCollectionDetailPayload = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: OutputInvoiceCollectionDetailSection[];
};

type OutputInvoiceCollectionDetailDrawerProps = {
  open: boolean;
  target: OutputInvoiceCollectionDetailTarget | null;
  loadDetail: (target: OutputInvoiceCollectionDetailTarget) => Promise<OutputInvoiceCollectionDetailPayload>;
  onClose: () => void;
};

const fallbackTitles: Record<OutputInvoiceCollectionDetailTarget["kind"], string> = {
  invoice: "发票详情",
  bank: "银行流水详情",
  relationList: "关联明细",
};

export default function OutputInvoiceCollectionDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
}: OutputInvoiceCollectionDetailDrawerProps) {
  const [detail, setDetail] = useState<OutputInvoiceCollectionDetailPayload | null>(null);
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
  const subtitle = detail?.subtitle ?? target?.id;

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭详情抽屉"
      onClose={onClose}
      open={open}
      subtitle={subtitle ? (
        <>
          <span>{title}</span>
          <span>{subtitle}</span>
        </>
      ) : title}
      title="销项发票收款情况详情"
      width={720}
    >
      <div className="output-invoice-collection-drawer__body">
        {loading ? (
          <div aria-label="正在加载详情">
            <StatePanel compact tone="loading" title="正在加载完整详情" />
          </div>
        ) : null}
        {error ? <StatePanel compact tone="error">{error}</StatePanel> : null}
        {detail?.detailAvailable === false ? (
          <StatePanel compact tone="info" title="关联详情不可用">
            {detail.unavailableReason ?? "后端未返回可展示的完整关联详情。"}
          </StatePanel>
        ) : null}
        {detail?.sections.map((section) => (
          <section className="output-invoice-collection-detail-card" key={section.title}>
            <h3>{section.title}</h3>
            <div className="output-invoice-collection-detail-grid">
              {section.fields.map((field) => (
                <div className="output-invoice-collection-detail-field" key={`${section.title}-${field.label}`}>
                  <span className="output-invoice-collection-detail-field__label">{field.label}</span>
                  <span className="output-invoice-collection-detail-field__value">{formatDetailValue(field.value)}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
        {!loading && !error && detail && detail.sections.length === 0 && detail.detailAvailable !== false ? (
          <StatePanel compact tone="info">暂无更多详情。</StatePanel>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function formatDetailValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
