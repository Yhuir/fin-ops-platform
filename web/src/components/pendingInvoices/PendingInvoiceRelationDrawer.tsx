import { useEffect, useState } from "react";

import type { PendingInvoiceRelationDetail, PendingInvoiceRelationDetailKind } from "../../features/pendingInvoices/types";
import { formatMoney } from "../../features/money";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
import PendingInvoiceDrawerFrame from "./PendingInvoiceDrawerFrame";

type PendingInvoiceRelationDrawerProps = {
  open: boolean;
  transactionId: string | null;
  detailKind?: PendingInvoiceRelationDetailKind;
  loadDetail: (transactionId: string) => Promise<PendingInvoiceRelationDetail>;
  onClose: () => void;
};

function RelationStatusChip({ status }: { status?: string }) {
  if (!status) {
    return null;
  }
  const paired = status.trim().toLowerCase() === "linked";
  return (
    <span className={`pending-invoices-tag pending-invoices-tag--${paired ? "linked" : "unlinked"}`}>
      {paired ? "已配对" : "未配对"}
    </span>
  );
}

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
      onClose={onClose}
      open={open}
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
          {detailKind === "all" || detailKind === "invoice" ? <section className="pending-invoice-panel" aria-labelledby="pending-invoice-related-invoices-title">
            <h3 className="pending-invoice-panel__title" id="pending-invoice-related-invoices-title">已关联发票</h3>
            <FinanceTable ariaLabel="已关联发票" className="pending-invoice-simple-table" minWidth={720}>
              <FinanceTableHeader>
                <FinanceTableColumn id="number" isRowHeader columnRole="identity">号码</FinanceTableColumn>
                <FinanceTableColumn id="counterparty" columnRole="identity">对方</FinanceTableColumn>
                <FinanceTableColumn id="date" columnRole="date">开票日期</FinanceTableColumn>
                <FinanceTableColumn id="amount" columnRole="amount">价税合计</FinanceTableColumn>
                <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {detail.relatedInvoices.length === 0 ? (
                  <FinanceTableRow id="empty"><FinanceTableCell columnRole="identity">暂无关联发票。</FinanceTableCell><FinanceTableCell columnRole="identity">-</FinanceTableCell><FinanceTableCell columnRole="date">-</FinanceTableCell><FinanceTableCell columnRole="amount">-</FinanceTableCell><FinanceTableCell columnRole="status">-</FinanceTableCell></FinanceTableRow>
                ) : detail.relatedInvoices.map((invoice) => (
                  <FinanceTableRow id={invoice.id || invoice.digitalInvoiceNo || invoice.invoiceNo} key={invoice.id || invoice.digitalInvoiceNo || invoice.invoiceNo}>
                    <FinanceTableCell columnRole="identity">{invoice.digitalInvoiceNo || invoice.invoiceNo || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{invoice.sellerName || invoice.buyerName || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="date">{invoice.issueDate || "-"}</FinanceTableCell>
                    <FinanceTableCell className="pending-invoice-simple-table__amount" columnRole="amount">{formatMoney(invoice.totalWithTax)}</FinanceTableCell>
                    <FinanceTableCell columnRole="status"><RelationStatusChip status={invoice.relationStatus} /></FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </section> : null}
          {detailKind === "all" || detailKind === "oa" ? <section className="pending-invoice-panel" aria-labelledby="pending-invoice-related-oa-title">
            <h3 className="pending-invoice-panel__title" id="pending-invoice-related-oa-title">已关联 OA</h3>
            <FinanceTable ariaLabel="已关联 OA" className="pending-invoice-simple-table" minWidth={620}>
              <FinanceTableHeader>
                <FinanceTableColumn id="applicant" isRowHeader columnRole="identity">申请人</FinanceTableColumn>
                <FinanceTableColumn id="type" columnRole="description">类型</FinanceTableColumn>
                <FinanceTableColumn id="project" columnRole="description">项目</FinanceTableColumn>
                <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {detail.relatedOa.length === 0 ? (
                  <FinanceTableRow id="empty"><FinanceTableCell columnRole="identity">暂无关联 OA。</FinanceTableCell><FinanceTableCell columnRole="description">-</FinanceTableCell><FinanceTableCell columnRole="description">-</FinanceTableCell><FinanceTableCell columnRole="status">-</FinanceTableCell></FinanceTableRow>
                ) : detail.relatedOa.map((oa) => (
                  <FinanceTableRow id={oa.id || oa.relationCaseId || `${oa.applicant}-${oa.projectName}`} key={oa.id || oa.relationCaseId || `${oa.applicant}-${oa.projectName}`}>
                    <FinanceTableCell columnRole="identity">{oa.applicant || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="description">{oa.applicationType || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="description">{oa.projectName || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="status"><RelationStatusChip status={oa.relationStatus} /></FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </section> : null}
          {detailKind === "all" || detailKind === "bank" ? <section className="pending-invoice-panel">
            <FinanceTable ariaLabel="历史支付流水" className="pending-invoice-simple-table" minWidth={620}>
              <FinanceTableHeader>
                <FinanceTableColumn id="date" isRowHeader columnRole="date">支付日期</FinanceTableColumn>
                <FinanceTableColumn id="counterparty" columnRole="identity">对方</FinanceTableColumn>
                <FinanceTableColumn id="amount" columnRole="amount">金额</FinanceTableColumn>
                <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
              </FinanceTableHeader>
              <FinanceTableBody>
                {detail.paymentRows.length === 0 ? (
                  <FinanceTableRow id="empty"><FinanceTableCell columnRole="date">暂无历史支付。</FinanceTableCell><FinanceTableCell columnRole="identity">-</FinanceTableCell><FinanceTableCell columnRole="amount">-</FinanceTableCell><FinanceTableCell columnRole="status">-</FinanceTableCell></FinanceTableRow>
                ) : detail.paymentRows.map((row) => (
                  <FinanceTableRow id={row.id || row.relationCaseId} key={row.id || row.relationCaseId}>
                    <FinanceTableCell columnRole="date">{row.tradeTime || "-"}</FinanceTableCell>
                    <FinanceTableCell columnRole="identity">{row.counterpartyName || "-"}</FinanceTableCell>
                    <FinanceTableCell className="pending-invoice-simple-table__amount" columnRole="amount">{formatMoney(row.debitAmount)}</FinanceTableCell>
                    <FinanceTableCell columnRole="status"><RelationStatusChip status={row.relationStatus} /></FinanceTableCell>
                  </FinanceTableRow>
                ))}
              </FinanceTableBody>
            </FinanceTable>
          </section> : null}
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
