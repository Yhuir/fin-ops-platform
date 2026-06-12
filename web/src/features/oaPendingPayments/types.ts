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
  primaryOaId?: string;
  applicantName: string;
  applicationType: string;
  projectName: string;
  applicationTime: string;
  amount: string;
  detailAvailable: boolean;
  relationCount?: number;
  relationStatus?: string;
  relationSource?: string;
  hasMultiple?: boolean;
  detailMode?: "none" | "single" | "list";
  summaries?: OaPendingPaymentOaRelationSummary[];
};

export type OaPendingPaymentOaRelationSummary = {
  oaId?: string;
  applicantName?: string;
  applicationType?: string;
  projectName?: string;
  applicationTime?: string;
  amount?: string;
  month?: string;
  workflowNo?: string;
  reason?: string;
  counterpartyName?: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
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
  accountNo?: string;
  accountLast4?: string;
  bankAccount?: string;
  direction?: string;
  directionLabel?: string;
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
  amount?: string;
  paidTotal?: string;
  relationStatus?: string;
  relationSource?: string;
  relationCount: number;
  hasMultiple: boolean;
  detailMode?: "none" | "single" | "list";
  summaries?: OaPendingPaymentBankTransactionSummary[];
};

export type OaPendingPaymentBankTransactionSummary = {
  bankTransactionId?: string | null;
  bankName?: string;
  accountNo?: string;
  accountLast4?: string;
  bankAccount?: string;
  direction?: string;
  directionLabel?: string;
  tradeTime?: string;
  amount?: string;
  counterpartyName?: string;
  summary?: string;
  remark?: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
};

export type OaPendingPaymentInvoiceSummary = {
  invoiceId?: string | null;
  digitalInvoiceNo?: string;
  sellerName?: string;
  invoiceDate?: string;
  totalWithTax?: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
};

export type OaPendingPaymentInvoice = {
  primaryInvoiceId?: string | null;
  digitalInvoiceNo: string;
  sellerName: string;
  invoiceDate: string;
  totalWithTax: string;
  relationStatus?: string;
  relationSource?: string;
  relationCount: number;
  hasMultiple: boolean;
  detailMode?: "none" | "single" | "list";
  summaries?: OaPendingPaymentInvoiceSummary[];
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
  read_model_stale_reasons?: string[];
  read_model_scope_key?: string;
  sourceVersions?: Record<string, unknown>;
  source_versions?: Record<string, unknown>;
};

export type OaPendingPaymentFilterOptionsResponse = {
  fields: Array<OaPendingPaymentFieldConfig & { options?: OaPendingPaymentFilterOption[] }>;
  readModelStatus?: string;
  read_model_status?: string;
  read_model_stale_reasons?: string[];
  read_model_scope_key?: string;
  sourceVersions?: Record<string, unknown>;
  source_versions?: Record<string, unknown>;
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
  relationKind?: "oa" | "bank" | "invoice";
};

export type OaPendingPaymentDetailResponse = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: Array<{ title: string; fields: Array<{ label: string; value: string | number | null | undefined }> }>;
};
