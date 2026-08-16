import { useEffect, useMemo, useState } from "react";

import type { PendingInvoiceRelationDetail, PendingInvoiceRelationDetailKind } from "../../features/pendingInvoices/types";
import EntityDetailContent, {
  preparePublicDetailSections,
  type EntityDetailSection,
} from "../common/EntityDetailContent";
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

  const sections = useMemo(
    () => detail ? relationDetailSections(detail, detailKind) : [],
    [detail, detailKind],
  );

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

function relationDetailSections(
  detail: PendingInvoiceRelationDetail,
  kind: PendingInvoiceRelationDetailKind,
) {
  const sections: EntityDetailSection[] = [];
  if (kind === "all" || kind === "oa") {
    detail.relatedOa.forEach((oa, index) => {
      sections.push({
        title: detail.relatedOa.length > 1 ? `OA ${index + 1}` : "基本信息",
        fields: [
          { label: "OA单号", value: oa.formNo },
          { label: "申请人", value: oa.applicant },
          { label: "OA类型", value: oa.applicationType },
          { label: "项目名称", value: oa.projectName },
          { label: "流程状态", value: oa.workflowStatus || oa.status },
        ],
      });
    });
  }
  if (kind === "all" || kind === "bank") {
    const rows = detail.paymentRows.length > 0 ? detail.paymentRows : [detail.transactionSummary];
    rows.forEach((row, index) => {
      sections.push({
        title: rows.length > 1 ? `银行流水 ${index + 1}` : "交易信息",
        fields: [
          { label: "交易时间", value: row.tradeTime },
          { label: "对方户名", value: row.counterpartyName },
          { label: "支出金额", value: row.debitAmount },
        ],
      });
    });
  }
  if (kind === "all" || kind === "invoice") {
    detail.relatedInvoices.forEach((invoice, index) => {
      sections.push({
        title: detail.relatedInvoices.length > 1 ? `发票 ${index + 1}` : "基本信息",
        fields: [
          { label: "发票号码", value: invoice.invoiceNo },
          { label: "数电发票号码", value: invoice.digitalInvoiceNo },
          { label: "发票代码", value: invoice.invoiceCode },
          { label: "开票日期", value: invoice.issueDate },
          { label: "销方名称", value: invoice.sellerName },
          { label: "销方识别号", value: invoice.sellerTaxNo },
          { label: "购买方名称", value: invoice.buyerName },
          { label: "价税合计", value: invoice.totalWithTax },
        ],
      });
    });
  }
  return preparePublicDetailSections(sections);
}
