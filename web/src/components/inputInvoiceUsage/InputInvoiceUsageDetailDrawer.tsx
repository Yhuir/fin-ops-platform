import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";

export type InputInvoiceUsageDetailTarget = {
  kind: "invoice" | "bank" | "oa" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: string;
};

export type InputInvoiceUsageDetailField = {
  label: string;
  value: string | number | null | undefined;
};

export type InputInvoiceUsageDetailSection = {
  title: string;
  fields: InputInvoiceUsageDetailField[];
};

export type InputInvoiceUsageDetailPayload = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: InputInvoiceUsageDetailSection[];
};

type InputInvoiceUsageDetailDrawerProps<TTarget extends InputInvoiceUsageDetailTarget> = {
  open: boolean;
  target: TTarget | null;
  loadDetail: (target: TTarget) => Promise<InputInvoiceUsageDetailPayload>;
  variant?: "temporary" | "persistent";
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
  const subtitle = detail?.subtitle ?? target?.id;

  return (
    <AppDrawer
      className="input-invoice-usage-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      subtitle={subtitle}
      title={title}
      width="min(720px, 100vw)"
      onClose={onClose}
    >
      <div className="input-invoice-usage-drawer-body">
        {loading ? (
          <div className="input-invoice-usage-drawer-loading">
            <span aria-label="正在加载详情" className="input-invoice-usage-drawer-spinner" role="progressbar" />
            <span>正在加载完整详情</span>
          </div>
        ) : null}
        {error ? <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--error" role="alert">{error}</div> : null}
        {detail?.detailAvailable === false ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info" role="status">
            <div className="input-invoice-usage-drawer-alert__title">详情暂不可用</div>
            <div>{detail.unavailableReason ?? "后端未返回可展示的完整详情。"}</div>
          </div>
        ) : null}
        {(detail?.sections ?? []).map((section) => (
          <section className="input-invoice-usage-detail-section" key={section.title}>
            <h3>{section.title}</h3>
            <div className="input-invoice-usage-detail-grid">
              {section.fields.map((field) => (
                <div className="input-invoice-usage-detail-field" key={`${section.title}-${field.label}`}>
                  <div className="input-invoice-usage-detail-field__label">{field.label}</div>
                  <div className="input-invoice-usage-detail-field__value">{formatDetailValue(field.value)}</div>
                </div>
              ))}
            </div>
          </section>
        ))}
        {!loading && !error && detail && (detail.sections ?? []).length === 0 && detail.detailAvailable !== false ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info" role="status">暂无更多详情。</div>
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
