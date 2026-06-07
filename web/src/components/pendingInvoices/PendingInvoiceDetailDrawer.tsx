import { useEffect, useState } from "react";

import AppDialog from "../common/AppDialog";
import type {
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceOaPrintLayout,
} from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceDetailDrawerProps = {
  open: boolean;
  target: PendingInvoiceObjectDetailTarget | null;
  loadDetail: (target: PendingInvoiceObjectDetailTarget) => Promise<PendingInvoiceObjectDetail>;
  onClose: () => void;
};

const fallbackTitles: Record<PendingInvoiceObjectDetailTarget["kind"], string> = {
  bankTransaction: "流水详情",
  invoice: "发票详情",
  oa: "OA详情",
};

export default function PendingInvoiceDetailDrawer({
  open,
  target,
  loadDetail,
  onClose,
}: PendingInvoiceDetailDrawerProps) {
  const [detail, setDetail] = useState<PendingInvoiceObjectDetail | null>(null);
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

  const title = detail?.title || (target ? fallbackTitles[target.kind] : "详情");
  const body = (
    <div className="pending-invoice-detail-body">
      {loading ? <LoadingMessage label="正在加载详情" text="正在加载完整详情" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {detail?.detailAvailable === false ? (
        <StatusMessage tone="info">{detail.unavailableReason || "后端未返回可展示的完整详情。"}</StatusMessage>
      ) : null}
      {detail?.oaPrintLayout ? <OaPrintLayout layout={detail.oaPrintLayout} /> : null}
      {!detail?.oaPrintLayout ? detail?.sections.map((section) => (
        <section className="pending-invoice-panel" key={section.title}>
          <h3 className="pending-invoice-panel__title">{section.title}</h3>
          <div className="pending-invoice-field-grid">
            {section.fields.map((field) => (
              <div className="pending-invoice-field" key={`${section.title}-${field.label}`}>
                <div className="pending-invoice-field__label">{field.label}</div>
                <div className="pending-invoice-field__value">{formatValue(field.value)}</div>
              </div>
            ))}
          </div>
        </section>
      )) : null}
      {!loading && !error && detail && detail.sections.length === 0 && detail.detailAvailable !== false && !detail.oaPrintLayout ? (
        <StatusMessage tone="info">暂无更多详情。</StatusMessage>
      ) : null}
    </div>
  );

  if (target?.kind === "oa") {
    return (
      <AppDialog
        actions={(
          <>
            <button
              className="pending-invoices-button pending-invoices-button--primary"
              onClick={() => {
                if (typeof window !== "undefined" && typeof window.print === "function") {
                  window.print();
                }
              }}
              type="button"
            >
              {detail?.oaPrintLayout?.downloadLabel || "打印下载"}
            </button>
            <button aria-label="关闭详情抽屉" className="pending-invoices-button" onClick={onClose} type="button">关闭</button>
          </>
        )}
        maxWidth="xl"
        onClose={onClose}
        open={open}
        title={title}
      >
        {body}
      </AppDialog>
    );
  }

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭详情抽屉"
      onClose={onClose}
      open={open}
      subtitle={detail?.subtitle || target?.id}
      title={title}
    >
      {body}
    </PendingInvoiceDrawerFrame>
  );
}

function OaPrintLayout({ layout }: { layout: PendingInvoiceOaPrintLayout }) {
  return (
    <section className="pending-invoice-print-layout">
      <h2 className="pending-invoice-print-layout__title">{layout.formTitle}</h2>
      <table className="pending-invoice-print-table">
        <tbody>
          {layout.fields.map((field) => (
            <tr key={field.label}>
              <th scope="row">{field.label}</th>
              <td>{formatValue(field.value)}</td>
            </tr>
          ))}
          {layout.approvals.length > 0 ? (
            <>
              <tr>
                <td className="pending-invoice-print-table__section" colSpan={2}>
                  申请提交/审批意见及评论
                </td>
              </tr>
              <tr>
                <td className="pending-invoice-print-table__approval-cell" colSpan={2}>
                  <div className="pending-invoice-print-approvals">
                    {layout.approvals.map((approval, index) => (
                      <section className="pending-invoice-print-approval" key={`${approval.title}-${index}`}>
                        <h3>{approval.title}</h3>
                        {approval.lines.map((line) => (
                          <p key={line}>{line}</p>
                        ))}
                        {approval.signature ? <p className="pending-invoice-print-approval__signature">{approval.signature}</p> : null}
                      </section>
                    ))}
                  </div>
                </td>
              </tr>
            </>
          ) : null}
        </tbody>
      </table>
    </section>
  );
}

function LoadingMessage({ label, text }: { label: string; text: string }) {
  return (
    <div aria-label={label} className="pending-invoice-status-message" role="status">
      <span aria-hidden="true" className="pending-invoice-spinner" />
      <span>{text}</span>
    </div>
  );
}

function StatusMessage({ children, tone }: { children: string; tone: "danger" | "success" | "info" }) {
  return (
    <div className={`pending-invoice-status-message pending-invoice-status-message--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      {children}
    </div>
  );
}

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
