import { useEffect, useState } from "react";

import AppDrawer from "../common/AppDrawer";
import StatePanel from "../common/StatePanel";

export type OutputInvoiceCollectionDetailTarget = {
  kind: "invoice" | "bank" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: "oa" | "bank" | "invoice" | "red_invoice" | "receipt";
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

  const title = detail?.title ?? drawerTitle(target);
  const sections = detail ? visibleSections(detail.sections) : [];

  return (
    <AppDrawer
      className="output-invoice-collection-drawer"
      closeLabel="关闭详情抽屉"
      onClose={onClose}
      open={open}
      title={title}
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
        {sections.map((section) => (
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
        {!loading && !error && detail && sections.length === 0 && detail.detailAvailable !== false ? (
          <StatePanel compact tone="info">暂无更多详情。</StatePanel>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function drawerTitle(target: OutputInvoiceCollectionDetailTarget | null) {
  if (target?.kind === "bank" || target?.relationKind === "bank") {
    return "流水详情";
  }
  if (target?.relationKind === "oa") {
    return "OA详情";
  }
  return "销项发票详情";
}

function visibleSections(sections: OutputInvoiceCollectionDetailSection[]) {
  return sections
    .map((section) => ({
      ...section,
      fields: section.fields.filter(isVisibleField),
    }))
    .filter((section) => section.fields.length > 0);
}

function isVisibleField(field: OutputInvoiceCollectionDetailField) {
  const label = field.label.trim();
  if (!label || /[A-Za-z_]/.test(label)) {
    return false;
  }
  return !looksLikeRawData(field.value);
}

function looksLikeRawData(value: string | number | null | undefined) {
  if (typeof value !== "string") {
    return false;
  }
  const text = value.trim();
  return (text.startsWith("{") || text.startsWith("[")) && (text.includes('":') || text.includes('","'));
}

function formatDetailValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
