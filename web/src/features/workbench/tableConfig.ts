import type { WorkbenchRecordType } from "./types";

export type WorkbenchColumnKind = "text" | "money" | "status";

export type WorkbenchColumn = {
  key: string;
  label: string;
  kind?: WorkbenchColumnKind;
  className?: string;
};

export const workbenchColumns: Record<WorkbenchRecordType, WorkbenchColumn[]> = {
  oa: [
    { key: "applicant", label: "申请人", className: "column-compact column-applicant-compact" },
    { key: "projectName", label: "项目名称", className: "column-compact column-project-compact" },
    { key: "applicationType", label: "申请类型", className: "column-compact column-type-compact" },
    { key: "amount", label: "金额", kind: "money", className: "column-compact column-money-compact" },
    { key: "counterparty", label: "对方户名", className: "column-compact column-counterparty-compact" },
    { key: "reason", label: "申请事由", className: "column-compact column-reason-compact" },
    {
      key: "reconciliationStatus",
      label: "OA和流水关联情况",
      kind: "status",
      className: "column-compact column-status-compact",
    },
  ],
  bank: [
    { key: "transactionTime", label: "交易时间", className: "column-compact column-datetime-compact" },
    { key: "debitAmount", label: "借方发生额", kind: "money", className: "column-compact column-money-compact" },
    { key: "creditAmount", label: "贷方发生额", kind: "money", className: "column-compact column-money-compact" },
    { key: "counterparty", label: "对方户名", className: "column-compact column-counterparty-compact" },
    { key: "paymentAccount", label: "支付账户", className: "column-compact column-account-compact" },
    {
      key: "invoiceRelationStatus",
      label: "和发票关联情况",
      kind: "status",
      className: "column-compact column-status-compact",
    },
    {
      key: "paymentOrReceiptTime",
      label: "支付/收款时间",
      className: "column-compact column-datetime-compact",
    },
    { key: "note", label: "备注", className: "column-compact column-note-compact" },
    { key: "loanRepaymentDate", label: "还借款日期", className: "column-compact column-date-compact" },
  ],
  invoice: [
    { key: "sellerTaxId", label: "销方识别号", className: "column-compact column-tax-id-compact" },
    { key: "sellerName", label: "销方名称", className: "column-compact column-name-compact" },
    { key: "buyerTaxId", label: "购方识别号", className: "column-compact column-tax-id-compact" },
    { key: "buyerName", label: "购买方名称", className: "column-compact column-name-compact" },
    { key: "issueDate", label: "开票日期", className: "column-compact column-date-compact" },
    { key: "amount", label: "金额", kind: "money", className: "column-compact column-money-compact" },
    { key: "taxRate", label: "税率", className: "column-compact column-rate-compact" },
    { key: "taxAmount", label: "税额", kind: "money", className: "column-compact column-money-compact" },
    { key: "grossAmount", label: "价税合计", kind: "money", className: "column-compact column-money-compact" },
    { key: "invoiceType", label: "发票类型", className: "column-compact column-type-compact" },
  ],
};
