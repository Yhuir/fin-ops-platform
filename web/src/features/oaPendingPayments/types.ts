export type OaPendingPaymentSortDirection = "asc" | "desc";

export type OaPendingPaymentFilterOperator = "contains" | "equals" | "in" | "between";

export type OaPendingPaymentFilter = {
  field: string;
  operator: OaPendingPaymentFilterOperator;
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
};

export type OaPendingPaymentFieldConfig = {
  field: string;
  label: string;
  mode: "text" | "enum_single" | "enum_multi" | "date" | "money";
  sortable?: boolean;
  operators?: string[];
};

export type OaPendingPaymentFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type OaPendingPaymentOaSummary = {
  id: string;
  applicantName: string;
  applicationType: string;
  projectName: string;
  amount: string;
  detailAvailable: boolean;
};

export type OaPendingPaymentStatus = {
  code: string;
  label: string;
  reason: string;
  severity?: "success" | "warning" | "error" | "info" | string;
};

export type OaPendingPaymentBankTransaction = {
  primaryBankTransactionId?: string | null;
  accountDetailNo: string;
  enterpriseSerialNo: string;
  voucherKind: string;
  voucherNo: string;
  bankName: string;
  accountName: string;
  tradeTime: string;
  debitAmount: string;
  creditAmount: string;
  balance: string;
  currency: string;
  counterpartyName: string;
  counterpartyAccountNo: string;
  counterpartyBankName: string;
  bookedDate: string;
  summary: string;
  remark: string;
  relationCount: number;
  hasMultiple: boolean;
  detailMode?: "none" | "single" | "list";
  summaries?: unknown[];
};

export type OaPendingPaymentInvoice = {
  primaryInvoiceId?: string | null;
  digitalInvoiceNo: string;
  sellerName: string;
  invoiceDate: string;
  totalWithTax: string;
  relationCount: number;
  hasMultiple: boolean;
  detailMode?: "none" | "single" | "list";
  summaries?: unknown[];
};

export type OaPendingPaymentRow = {
  id: string;
  oa: OaPendingPaymentOaSummary;
  paymentStatus: OaPendingPaymentStatus;
  bankTransaction: OaPendingPaymentBankTransaction;
  invoice: OaPendingPaymentInvoice;
};

export type OaPendingPaymentSummary = {
  rowCount: number;
  oaAmountTotal?: string;
  bankPaidTotal?: string;
  statusCounts?: Record<string, number>;
};

export type OaPendingPaymentRowsResponse = {
  rows: OaPendingPaymentRow[];
  pagination: { page: number; pageSize: number; total: number };
  summary: OaPendingPaymentSummary;
  filterConfig: OaPendingPaymentFieldConfig[];
  readModelStatus?: string;
  read_model_status?: string;
};

export type OaPendingPaymentFilterOptionsResponse = {
  fields: Array<OaPendingPaymentFieldConfig & { options?: OaPendingPaymentFilterOption[] }>;
  readModelStatus?: string;
  read_model_status?: string;
};

export type OaPendingPaymentQuery = {
  page: number;
  pageSize: number;
  keyword: string;
  month: string;
  tradeDateFrom: string;
  tradeDateTo: string;
  filters: OaPendingPaymentFilter[];
  sortField: string;
  sortDirection: OaPendingPaymentSortDirection | "";
};

export type OaPendingPaymentDetailTarget = {
  kind: "oa" | "bank" | "invoice" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: "bank" | "invoice";
};

export type OaPendingPaymentDetailResponse = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: Array<{ title: string; fields: Array<{ label: string; value: string | number | null | undefined }> }>;
};
