import { useEffect, useState } from "react";

import type { PendingInvoiceRelationDetail } from "../../features/pendingInvoices/types";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRelationDrawerProps = {
  open: boolean;
  transactionId: string | null;
  loadDetail: (transactionId: string) => Promise<PendingInvoiceRelationDetail>;
  onOpenInvoicePicker: (transactionId: string) => void;
  onClose: () => void;
};

function formatMoney(value: string) {
  const parsed = Number(String(value ?? "").replace(/,/g, ""));
  return Number.isFinite(parsed) ? parsed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value || "-";
}

function RelationStatusChip({ status }: { status?: string }) {
  if (status !== "candidate") {
    return null;
  }
  return <span className="pending-invoices-tag pending-invoices-tag--candidate">候选</span>;
}

export default function PendingInvoiceRelationDrawer({
  open,
  transactionId,
  loadDetail,
  onOpenInvoicePicker,
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
          setError(reason instanceof Error ? reason.message : "关系明细加载失败");
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

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭关系明细抽屉"
      footer={transactionId && detail?.availableActions.includes("attach_existing_invoice") ? (
        <button className="pending-invoices-button pending-invoices-button--primary" onClick={() => onOpenInvoicePicker(transactionId)} type="button">
          选择已有发票
        </button>
      ) : null}
      onClose={onClose}
      open={open}
      subtitle={detail?.transactionSummary.counterpartyName ?? transactionId ?? undefined}
      title="关系与支付明细"
    >
      {loading ? <LoadingMessage label="正在加载关系明细" text="正在加载关系明细" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {detail ? (
        <>
          <section className="pending-invoice-metric-grid" aria-label="支付汇总">
            <Metric label="已付合计" value={formatMoney(detail.paidTotal)} />
            <Metric label="发票合计" value={formatMoney(detail.invoiceTotal)} />
            <Metric label="待付金额" value={formatMoney(detail.remainingAmount)} />
            <Metric label="支付差额" value={formatMoney(detail.differenceAmount)} />
          </section>
          <section className="pending-invoice-panel" aria-labelledby="pending-invoice-related-invoices-title">
            <h3 className="pending-invoice-panel__title" id="pending-invoice-related-invoices-title">已关联发票</h3>
            <table aria-label="已关联发票" className="pending-invoice-simple-table">
              <thead>
                <tr>
                  <th scope="col">号码</th>
                  <th scope="col">对方</th>
                  <th scope="col">开票日期</th>
                  <th className="pending-invoice-simple-table__amount" scope="col">价税合计</th>
                  <th scope="col">状态</th>
                </tr>
              </thead>
              <tbody>
                {detail.relatedInvoices.length === 0 ? (
                  <tr><td colSpan={5}>暂无关联发票。</td></tr>
                ) : detail.relatedInvoices.map((invoice) => (
                  <tr key={invoice.id || invoice.digitalInvoiceNo || invoice.invoiceNo}>
                    <td>{invoice.digitalInvoiceNo || invoice.invoiceNo || "-"}</td>
                    <td>{invoice.sellerName || invoice.buyerName || "-"}</td>
                    <td>{invoice.issueDate || "-"}</td>
                    <td className="pending-invoice-simple-table__amount">{formatMoney(invoice.totalWithTax)}</td>
                    <td><RelationStatusChip status={invoice.relationStatus} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="pending-invoice-panel" aria-labelledby="pending-invoice-related-oa-title">
            <h3 className="pending-invoice-panel__title" id="pending-invoice-related-oa-title">已关联 OA</h3>
            <table aria-label="已关联 OA" className="pending-invoice-simple-table">
              <thead>
                <tr>
                  <th scope="col">申请人</th>
                  <th scope="col">类型</th>
                  <th scope="col">项目</th>
                  <th scope="col">关系</th>
                  <th scope="col">状态</th>
                </tr>
              </thead>
              <tbody>
                {detail.relatedOa.length === 0 ? (
                  <tr><td colSpan={5}>暂无关联 OA。</td></tr>
                ) : detail.relatedOa.map((oa) => (
                  <tr key={oa.id || oa.relationCaseId || `${oa.applicant}-${oa.projectName}`}>
                    <td>{oa.applicant || "-"}</td>
                    <td>{oa.applicationType || "-"}</td>
                    <td>{oa.projectName || "-"}</td>
                    <td>{oa.relationCaseId || "-"}</td>
                    <td><RelationStatusChip status={oa.relationStatus} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="pending-invoice-panel">
            <table aria-label="历史支付流水" className="pending-invoice-simple-table">
              <thead>
                <tr>
                  <th scope="col">支付日期</th>
                  <th scope="col">对方</th>
                  <th className="pending-invoice-simple-table__amount" scope="col">金额</th>
                  <th scope="col">关系</th>
                  <th scope="col">状态</th>
                </tr>
              </thead>
              <tbody>
                {detail.paymentRows.length === 0 ? (
                  <tr>
                    <td colSpan={5}>暂无历史支付。</td>
                  </tr>
                ) : detail.paymentRows.map((row) => (
                  <tr key={row.id || row.relationCaseId}>
                    <td>{row.tradeTime || "-"}</td>
                    <td>{row.counterpartyName || "-"}</td>
                    <td className="pending-invoice-simple-table__amount">{formatMoney(row.debitAmount)}</td>
                    <td>{row.relationCaseId || "-"}</td>
                    <td><RelationStatusChip status={row.relationStatus} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : null}
    </PendingInvoiceDrawerFrame>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="pending-invoice-metric">
      <div className="pending-invoice-metric__label">{label}</div>
      <div className="pending-invoice-metric__value">{value}</div>
    </div>
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
