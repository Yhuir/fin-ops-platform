import { Button } from "@heroui/react";
import { useEffect, useState } from "react";

import type {
  PendingInvoiceDetailField,
  PendingInvoiceDetailSection,
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceOaPrintLayout,
} from "../../features/pendingInvoices/types";
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

const detailFieldLabels: Record<string, string> = {
  account_name: "账户名称",
  account_no: "账号",
  account_number: "账号",
  account_last4: "账号尾号",
  amount: "金额",
  application_type: "申请类型",
  applicant: "申请人",
  balance: "余额",
  bank_account: "账号",
  bank_account_no: "账号",
  bank_name: "银行",
  bank_short_name: "银行简称",
  booked_date: "入账日期",
  buyer_name: "购方名称",
  buyer_tax_no: "购方税号",
  counterparty_account_no: "对方账号",
  counterparty_bank_name: "对方开户行",
  counterparty_name: "对方户名",
  credit_amount: "收入金额",
  currency: "币种",
  debit_amount: "支出金额",
  digital_invoice_no: "数电票号码",
  form_no: "单据编号",
  invoice_code: "发票代码",
  invoice_no: "发票号码",
  issue_date: "开票日期",
  payee_account_no: "收款账号",
  payee_bank_name: "收款开户行",
  payee_name: "收款方",
  payment_method: "支付方式",
  project_name: "项目名称",
  reason: "申请事由",
  remark: "备注",
  seller_name: "销方名称",
  seller_tax_no: "销方税号",
  statement_serial_no: "银行流水号",
  status: "状态",
  summary: "摘要",
  tax_amount: "税额",
  total_amount: "金额",
  total_with_tax: "价税合计",
  trade_time: "交易时间",
  voucher_no: "凭证号",
  voucher_type: "凭证类型",
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
  const sections = detail && !detail.oaPrintLayout ? visibleSections(detail.sections) : [];
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
      {loading ? <LoadingMessage label="正在加载详情" text="正在加载完整详情" /> : null}
      {error ? <StatusMessage tone="danger">{error}</StatusMessage> : null}
      {detail?.detailAvailable === false ? (
        <StatusMessage tone="info">{detail.unavailableReason || "后端未返回可展示的完整详情。"}</StatusMessage>
      ) : null}
      {detail?.oaPrintLayout ? <OaPrintLayout layout={detail.oaPrintLayout} /> : null}
      {!detail?.oaPrintLayout ? sections.map((section, sectionIndex) => (
        <section className="pending-invoice-panel" key={`${section.title}-${sectionIndex}`}>
          <h3 className="pending-invoice-panel__title">{section.title}</h3>
          <div className="pending-invoice-field-grid">
            {section.fields.map((field, fieldIndex) => (
              <div className="pending-invoice-field" key={`${section.title}-${field.label}-${fieldIndex}`}>
                <div className="pending-invoice-field__label">{field.label}</div>
                <div className="pending-invoice-field__value">{formatValue(field.value)}</div>
              </div>
            ))}
          </div>
        </section>
      )) : null}
      {!loading && !error && detail && sections.length === 0 && detail.detailAvailable !== false && !detail.oaPrintLayout ? (
        <StatusMessage tone="info">暂无更多详情。</StatusMessage>
      ) : null}
    </div>
  );

  return (
    <PendingInvoiceDrawerFrame
      closeLabel="关闭详情抽屉"
      footer={footer}
      onClose={onClose}
      open={open}
      title={title}
    >
      {body}
    </PendingInvoiceDrawerFrame>
  );
}

function OaPrintLayout({ layout }: { layout: PendingInvoiceOaPrintLayout }) {
  const fields = visibleFields(layout.fields);
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

function visibleSections(sections: PendingInvoiceDetailSection[]) {
  return sections
    .filter((section) => !isRawDetailSection(section.title))
    .map((section) => ({
      ...section,
      title: section.title || "详情",
      fields: visibleFields(section.fields),
    }))
    .filter((section) => section.fields.length > 0);
}

function visibleFields<TField extends PendingInvoiceDetailField>(fields: TField[]) {
  return fields.map(toVisibleField).filter((field): field is TField => field !== null);
}

function toVisibleField<TField extends PendingInvoiceDetailField>(field: TField): TField | null {
  const label = displayLabel(field.label);
  if (!label || looksLikeRawData(field.value)) {
    return null;
  }
  return { ...field, label };
}

function displayLabel(label: string) {
  const trimmed = label.trim();
  const key = normalizedLabel(trimmed);
  if (!trimmed || isInternalLabel(trimmed, key)) {
    return null;
  }
  const translated = detailFieldLabels[key];
  if (translated) {
    return translated;
  }
  return /[A-Za-z_]/.test(trimmed) ? null : trimmed;
}

function normalizedLabel(label: string) {
  return label
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[：:]/g, "")
    .replace(/[\s/-]+/g, "_")
    .replace(/_+/g, "_")
    .toLowerCase();
}

function isInternalLabel(label: string, key: string) {
  return key === "id"
    || key.endsWith("_id")
    || key.startsWith("id_")
    || key.includes("relation_case")
    || key.includes("case_id")
    || key.includes("mongo")
    || key.includes("uuid")
    || /\bID\b/.test(label)
    || /内部标识|内部ID|文档ID/.test(label);
}

function isRawDetailSection(title: string) {
  return /原始字段|内部字段|raw/i.test(title);
}

function looksLikeRawData(value: string | number | null | undefined) {
  if (typeof value !== "string") {
    return false;
  }
  const text = value.trim();
  return (text.startsWith("{") || text.startsWith("[")) && (text.includes("\":") || text.includes("\",\""));
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
