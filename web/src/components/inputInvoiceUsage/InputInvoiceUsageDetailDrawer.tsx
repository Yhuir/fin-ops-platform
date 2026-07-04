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
  layout?: "grid" | "table";
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
  layout = "grid",
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
  const subtitle = detail?.subtitle;
  const sections = detail ? visibleSections(detail.sections) : [];

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
        {layout === "table" ? <DetailTable sections={sections} title={title} /> : (
          sections.map((section) => (
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
          ))
        )}
        {!loading && !error && detail && sections.length === 0 && detail.detailAvailable !== false ? (
          <div className="input-invoice-usage-drawer-alert input-invoice-usage-drawer-alert--info" role="status">暂无更多详情。</div>
        ) : null}
      </div>
    </AppDrawer>
  );
}

function DetailTable({
  sections,
  title,
}: {
  sections: InputInvoiceUsageDetailSection[];
  title: string;
}) {
  if (sections.length === 0) {
    return null;
  }
  return (
    <div className="input-invoice-usage-detail-table-shell">
      <table aria-label={`${title}明细表`} className="input-invoice-usage-detail-table">
        <tbody>
          {sections.map((section) => (
            <TableSection key={section.title} section={section} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableSection({ section }: { section: InputInvoiceUsageDetailSection }) {
  return (
    <>
      <tr className="input-invoice-usage-detail-table__section-row">
        <th colSpan={2} scope="colgroup">{section.title}</th>
      </tr>
      {section.fields.map((field) => (
        <tr key={`${section.title}-${field.label}`}>
          <th scope="row">{field.label}</th>
          <td>{formatDetailValue(field.value)}</td>
        </tr>
      ))}
    </>
  );
}

function visibleSections(sections: InputInvoiceUsageDetailSection[]) {
  return sections
    .map((section) => ({
      ...section,
      fields: isRawDetailSection(section) ? [] : section.fields.filter(isVisibleField),
    }))
    .filter((section) => section.fields.length > 0);
}

function isRawDetailSection(section: InputInvoiceUsageDetailSection) {
  return section.title.includes("原始字段");
}

function isVisibleField(field: InputInvoiceUsageDetailField) {
  const label = field.label.trim();
  if (/^OA\s+\d+$/i.test(label)) {
    return true;
  }
  if (!label || /[A-Za-z_]/.test(label) || /\bID\b/i.test(label)) {
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
