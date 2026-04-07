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
    { key: "applicant", label: "申请人", className: "column-compact column-applicant-compact column-content-centered" },
    { key: "projectName", label: "项目名称", className: "column-compact column-project-compact" },
    { key: "amount", label: "金额", kind: "money", className: "column-compact column-money-compact column-money-centered" },
    { key: "counterparty", label: "对方户名", className: "column-compact column-counterparty-compact" },
    { key: "reason", label: "申请事由", className: "column-compact column-reason-compact" },
  ],
  bank: [
    { key: "counterparty", label: "对方户名", className: "column-compact column-counterparty-compact" },
    { key: "amount", label: "金额", kind: "money", className: "column-compact column-money-compact column-money-centered" },
    { key: "note", label: "备注", className: "column-compact column-note-compact" },
    { key: "loanRepaymentDate", label: "还借款日期", className: "column-compact column-date-compact" },
  ],
  invoice: [
    { key: "sellerName", label: "销方名称/识别号", className: "column-compact column-name-compact" },
    { key: "buyerName", label: "购买方名称/识别号", className: "column-compact column-name-compact" },
    { key: "issueDate", label: "开票日期", className: "column-compact column-date-compact" },
    {
      key: "amount",
      label: "金额/税率/税额",
      kind: "money",
      className: "column-compact column-money-compact column-invoice-amount-compact column-money-centered",
    },
    {
      key: "grossAmount",
      label: "价税合计",
      kind: "money",
      className: "column-compact column-money-compact column-invoice-gross-compact column-money-centered",
    },
  ],
};
