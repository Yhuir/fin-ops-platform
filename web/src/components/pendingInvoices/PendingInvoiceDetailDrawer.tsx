import { Button } from "@heroui/react";
import { useEffect, useState } from "react";

import type {
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceOaPrintLayout,
} from "../../features/pendingInvoices/types";
import EntityDetailContent, { preparePublicDetailSections } from "../common/EntityDetailContent";
import {
  FinanceTable,
  FinanceTableBody,
  FinanceTableCell,
  FinanceTableColumn,
  FinanceTableHeader,
  FinanceTableRow,
} from "../common/FinanceTable";
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
  oa: "OA 详情",
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

  const title = target ? fallbackTitles[target.kind] : "详情";
  const sections = detail && !detail.oaPrintLayout ? preparePublicDetailSections(detail.sections) : [];
  const footer = target?.kind === "oa" && detail?.oaPrintLayout ? (
    <div className="pending-invoice-drawer-actions">
      <Button
        className="pending-invoices-button pending-invoices-button--primary"
        onPress={() => {
          if (typeof window !== "undefined" && typeof window.print === "function") {
            window.print();
          }
        }}
        size="sm"
        variant="primary"
      >
        {detail.oaPrintLayout.downloadLabel || "打印下载"}
      </Button>
    </div>
  ) : undefined;
  const body = (
    <div className="pending-invoice-detail-body">
      {detail?.oaPrintLayout && !loading && !error ? <OaPrintLayout layout={detail.oaPrintLayout} /> : (
        <EntityDetailContent
          detailAvailable={detail?.detailAvailable}
          error={error}
          loading={loading}
          sections={sections}
          unavailableReason={detail?.unavailableReason}
        />
      )}
    </div>
  );

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭详情抽屉"
      footer={footer}
      onClose={onClose}
      open={open}
      title={title}
      width="min(800px, 100vw)"
    >
      {body}
    </PendingInvoiceDrawerFrame>
  );
}

function OaPrintLayout({ layout }: { layout: PendingInvoiceOaPrintLayout }) {
  const fields = preparePublicDetailSections([{ title: "打印信息", fields: layout.fields }])[0]?.fields ?? [];
  return (
    <section className="pending-invoice-print-layout">
      <h2 className="pending-invoice-print-layout__title">{layout.formTitle}</h2>
      <FinanceTable ariaLabel={`${layout.formTitle}明细`} className="pending-invoice-print-table" minWidth={520}>
        <FinanceTableHeader>
          <FinanceTableColumn id="field" isRowHeader columnRole="identity">字段</FinanceTableColumn>
          <FinanceTableColumn id="value" columnRole="description">内容</FinanceTableColumn>
        </FinanceTableHeader>
        <FinanceTableBody>
          {fields.map((field) => (
            <FinanceTableRow id={field.label} key={field.label}>
              <FinanceTableCell columnRole="identity">{field.label}</FinanceTableCell>
              <FinanceTableCell columnRole="description">{formatValue(field.value)}</FinanceTableCell>
            </FinanceTableRow>
          ))}
        </FinanceTableBody>
      </FinanceTable>
      {layout.approvals.length > 0 ? (
        <section className="pending-invoice-print-table__approval-cell">
          <h3 className="pending-invoice-print-table__section">申请提交/审批意见及评论</h3>
          <div className="pending-invoice-print-approvals">
            {layout.approvals.map((approval, index) => (
              <section className="pending-invoice-print-approval" key={`${approval.title}-${index}`}>
                <h3>{approval.title}</h3>
                {approval.lines.map((line) => <p key={line}>{line}</p>)}
                {approval.signature ? <p className="pending-invoice-print-approval__signature">{approval.signature}</p> : null}
              </section>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}

function formatValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}
