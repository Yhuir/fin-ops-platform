export type InputInvoiceUsageSortDirection = "asc" | "desc";

export type InputInvoiceUsageFilterOperator =
  | "contains"
  | "equals"
  | "in"
  | "between";

export type InputInvoiceUsageFilter = {
  field: string;
  operator: InputInvoiceUsageFilterOperator;
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
};

export type InputInvoiceUsageQuery = {
  page: number;
  pageSize: number;
  keyword: string;
  invoiceDateFrom: string;
  invoiceDateTo: string;
  month: string;
  filters: InputInvoiceUsageFilter[];
  sortField: string;
  sortDirection: InputInvoiceUsageSortDirection | "";
  activeWorkflow: "oaReverse" | "paymentRules" | null;
  detailTarget: InputInvoiceUsageDetailTarget | null;
};

export type InputInvoiceUsageDetailTarget = {
  kind: "invoice" | "bank" | "oa" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: "oa" | "bank";
};

export type InputInvoiceUsageInvoiceSummary = {
  id: string;
  displayNo: string;
  invoiceNo: string;
  invoiceCode: string;
  digitalInvoiceNo: string;
  issueDate: string;
  sellerName: string;
  sellerTaxNo: string;
  totalWithTax: string;
  amountWithoutTax: string;
  taxRate: string;
  taxAmount: string;
  specificBusinessType: string;
  taxableItemName: string;
};

export type InputInvoiceUsagePaymentStatus = {
  code: string;
  label: string;
  reason: string;
};

export type InputInvoiceUsageOaSummary = {
  id: string;
  applicant: string;
  applicationType: string;
  projectName: string;
  detailAvailable: boolean;
};

export type InputInvoiceUsageBankSummary = {
  id: string;
  counterpartyName: string;
  tradeTime: string;
  amount: string;
  directionLabel: string;
  bankName: string;
  accountLast4: string;
  summary: string;
  remark: string;
  detailAvailable: boolean;
};

export type InputInvoiceUsageRelationSummary<T> = {
  primary: T | null;
  relationCount: number;
  hasMultiple: boolean;
  detailMode: "none" | "single" | "list";
  summaries: T[];
};

export type InputInvoiceUsageRow = {
  id: string;
  invoice: InputInvoiceUsageInvoiceSummary;
  paymentStatus: InputInvoiceUsagePaymentStatus;
  oa: InputInvoiceUsageRelationSummary<InputInvoiceUsageOaSummary>;
  bank: InputInvoiceUsageRelationSummary<InputInvoiceUsageBankSummary>;
};

export type InputInvoiceUsageRowsResponse = {
  rows: InputInvoiceUsageRow[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  filterConfig: InputInvoiceUsageFilterFieldConfig[];
  readModelStatus?: string;
  readModelScopeKey?: string;
};

export type InputInvoiceUsageFilterFieldConfig = {
  field: string;
  label: string;
  mode: "text" | "enum_single" | "enum_multi" | "date" | "money";
  sortable: boolean;
  operators: InputInvoiceUsageFilterOperator[];
};

export type InputInvoiceUsageFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type InputInvoiceUsageFilterOptionsResponse = {
  fields: Array<InputInvoiceUsageFilterFieldConfig & {
    options: InputInvoiceUsageFilterOption[];
  }>;
  readModelStatus?: string;
  readModelScopeKey?: string;
};

export type InputInvoiceUsageDetailResponse = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: Array<{
    title: string;
    fields: Array<{ label: string; value: string | number | null | undefined }>;
  }>;
};

export type InputInvoiceUsagePaymentStatusRulesResponse = {
  version?: string;
  readOnly?: boolean;
  rules: Array<{
    id?: string;
    code?: string;
    label: string;
    description: string;
    priority: number;
  }>;
  pendingDirections: Array<{ code?: string; label: string }>;
};

export type InputInvoiceUsageOaReversePreviewRequest = {
  source?: "currentFilters" | "explicitSelection";
  filters: InputInvoiceUsageFilter[];
  selectedInvoiceIds: string[];
};

export type InputInvoiceUsageOaReversePreviewResponse = {
  previewId?: string;
  source?: string;
  invoiceCount: number;
  totalWithTax: string;
  groups: Array<{
    targetApplicantCode?: string | null;
    targetApplicantName: string;
    invoiceCount: number;
    totalWithTax: string;
    candidateInvoiceIds?: string[];
    rejectedInvoices?: Array<{
      invoiceId: string;
      invoiceNumber?: string | null;
      reasonCode?: string | null;
      reason: string;
    }>;
  }>;
  warnings?: string[];
  canCreateDraft?: boolean;
  nextAction?: string;
};
