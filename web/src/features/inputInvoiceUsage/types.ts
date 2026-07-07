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
  activeWorkflow: "oaReverse" | "paymentRules" | "export" | null;
  detailTarget: InputInvoiceUsageDetailTarget | null;
};

export type InputInvoiceUsageDetailTarget = {
  kind: "invoice" | "bank" | "oa" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: "oa" | "bank" | "invoice";
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
  amount: string;
  detailAvailable: boolean;
};

export type InputInvoiceUsageBankSummary = {
  id: string;
  counterpartyName: string;
  tradeTime: string;
  amount: string;
  direction: string;
  directionLabel: string;
  bankName: string;
  accountLast4: string;
  bankAccount: string;
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

export type InputInvoiceUsageInvoiceRelationSummary = {
  id: string;
  displayNo: string;
  invoiceNo: string;
  invoiceCode: string;
  digitalInvoiceNo: string;
  invoiceDate: string;
  sellerName: string;
  sellerTaxNo: string;
  totalWithTax: string;
  taxableItemName: string;
};

export type InputInvoiceUsageInvoiceRelations = InputInvoiceUsageRelationSummary<InputInvoiceUsageInvoiceRelationSummary> & {
  totalWithTax: string;
};

export type InputInvoiceUsageRow = {
  id: string;
  invoice: InputInvoiceUsageInvoiceSummary;
  paymentStatus: InputInvoiceUsagePaymentStatus;
  oa: InputInvoiceUsageRelationSummary<InputInvoiceUsageOaSummary>;
  bank: InputInvoiceUsageRelationSummary<InputInvoiceUsageBankSummary>;
  invoiceRelations: InputInvoiceUsageInvoiceRelations;
};

export type InputInvoiceUsageRowsResponse = {
  rows: InputInvoiceUsageRow[];
  summary?: {
    invoiceCount: number;
    totalWithTax: string;
    matchedOaCount: number;
    matchedBankTransactionCount: number;
    pendingCount: number;
  };
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
  version: number | string | null;
  readOnly: boolean;
  permissions: {
    canSave: boolean;
  };
  rules: InputInvoiceUsagePaymentStatusRule[];
  pendingDirections: InputInvoiceUsagePendingDirection[];
  source?: {
    version?: string;
    updatedAt?: string;
    updatedBy?: string;
  };
};

export type InputInvoiceUsagePaymentStatusRule = {
  id?: string;
  code?: string;
  statusCode?: string;
  label: string;
  description: string;
  reason?: string;
  priority: number;
  enabled?: boolean;
  conditions?: Record<string, unknown>;
  applicantConstraints?: string[];
};

export type InputInvoiceUsagePendingDirection = {
  code?: string;
  label: string;
};

export type SaveInputInvoiceUsagePaymentStatusRulesRequest = {
  expectedVersion: number | string | null;
  idempotencyKey: string;
  rules: InputInvoiceUsagePaymentStatusRule[];
  pendingDirections: InputInvoiceUsagePendingDirection[];
};

export type InputInvoiceUsageOaReversePreviewRequest = {
  source?: "currentFilters" | "explicitSelection";
  filters: InputInvoiceUsageFilter[];
  selectedInvoiceIds: string[];
  targetApplicantCode?: string;
};

export type InputInvoiceUsageOaReversePreviewResponse = {
  previewId?: string;
  previewHash?: string;
  source?: string;
  targetApplicantCode?: string;
  targetApplicantName?: string;
  targetApplicants?: InputInvoiceUsageOaReverseTargetApplicant[];
  invoiceCount: number;
  totalWithTax: string;
  groups: Array<{
    targetApplicantCode?: string | null;
    targetApplicantName: string;
    invoiceCount: number;
    totalWithTax: string;
    invoiceRows?: InputInvoiceUsageOaReverseInvoice[];
    candidateInvoiceIds?: string[];
    candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
    rejectedInvoices?: Array<{
      invoiceId: string;
      invoiceNumber?: string | null;
      displayNo?: string | null;
      sellerName?: string | null;
      issueDate?: string | null;
      totalWithTax?: string | null;
      paymentStatusLabel?: string | null;
      reasonCode?: string | null;
      reason: string;
    }>;
  }>;
  invoiceRows?: InputInvoiceUsageOaReverseInvoice[];
  candidateInvoices?: InputInvoiceUsageOaReverseInvoice[];
  rejectedInvoices?: InputInvoiceUsageOaReverseRejectedInvoice[];
  warnings?: string[];
  canCreateDraft?: boolean;
  nextAction?: string;
  unavailableReason?: string;
  permissions?: {
    canCreateBatch?: boolean;
    canCreateDraft?: boolean;
    canRevoke?: boolean;
    canManualStatus?: boolean;
  };
};

export type InputInvoiceUsageOaReverseTargetApplicant = {
  code: string;
  name: string;
};

export type InputInvoiceUsageOaReverseInvoice = {
  invoiceId: string;
  invoiceNumber: string;
  displayNo: string;
  sellerName: string;
  issueDate: string;
  totalWithTax: string;
  paymentStatusLabel: string;
  targetApplicantName?: string;
  oaRelationStatus?: "linked" | "candidate" | "unlinked" | string;
};

export type InputInvoiceUsageOaReverseRejectedInvoice = {
  invoiceId: string;
  invoiceNumber?: string | null;
  displayNo?: string | null;
  sellerName?: string | null;
  issueDate?: string | null;
  totalWithTax?: string | null;
  paymentStatusLabel?: string | null;
  oaRelationStatus?: "linked" | "candidate" | "unlinked" | string;
  reasonCode?: string | null;
  reason: string;
};

export type InputInvoiceUsageOaReverseBatch = {
  batchId: string;
  version: number;
  status: string;
  invoiceIds: string[];
  selectedInvoiceIds: string[];
  totalWithTax: string;
  previewSummary?: {
    invoiceCount: number;
    totalWithTax: string;
  };
  targetApplicantCode?: string | null;
  targetApplicantName?: string | null;
  invoiceRows: InputInvoiceUsageOaReverseInvoice[];
  invoices: InputInvoiceUsageOaReverseInvoice[];
  rejectedInvoices: InputInvoiceUsageOaReverseRejectedInvoice[];
  oaDraftId?: string | null;
  oaDraftUrl?: string | null;
  oaProcessStatus?: string | null;
  oaDetectionStatus?: string | null;
  nextRunAt?: string | null;
  attempts?: number;
  conflictCandidates?: Array<{ id: string; label: string; reason?: string }>;
  idempotentReplay?: boolean;
  auditEventId?: string | null;
  canCreateDraft?: boolean;
  canConfirmSubmission?: boolean;
  canRevoke?: boolean;
  canRefreshStatus?: boolean;
  canManualStatus?: boolean;
};

export type CreateInputInvoiceUsageOaReverseBatchRequest = {
  previewId: string;
  expectedPreviewHash?: string;
  idempotencyKey: string;
  selectedInvoiceIds?: string[];
  targetApplicantCode?: string | null;
};

export type CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest = {
  previewId: string;
  expectedPreviewHash?: string;
  idempotencyKey: string;
  selectedInvoiceIds: string[];
  targetApplicantCode?: string | null;
};

export type InputInvoiceUsageOaReverseVersionedRequest = {
  expectedVersion: number;
  idempotencyKey?: string;
};

export type RevokeInputInvoiceUsageOaReverseDraftRequest = InputInvoiceUsageOaReverseVersionedRequest & {
  reason: string;
};

export type ManualInputInvoiceUsageOaReverseStatusRequest = InputInvoiceUsageOaReverseVersionedRequest & {
  decision: "submitted" | "not_submitted";
  reason: string;
  candidateOaRowId?: string;
};

export type InputInvoiceUsageOaReverseSubmittedHistoryInvoice = {
  invoiceNo: string;
  invoiceDate: string;
  sellerName: string;
  totalWithTax: string;
};

export type InputInvoiceUsageOaReverseSubmittedHistoryItem = {
  targetApplicantName: string;
  submittedAt: string;
  totalWithTax: string;
  invoiceCount: number;
  invoices: InputInvoiceUsageOaReverseSubmittedHistoryInvoice[];
};

export type InputInvoiceUsageOaReverseSubmittedHistoryResponse = {
  items: InputInvoiceUsageOaReverseSubmittedHistoryItem[];
};

export type InputInvoiceUsageOaReverseStagedDraftsResponse = {
  items: InputInvoiceUsageOaReverseBatch[];
};

export type InputInvoiceUsageExportPreview = {
  fileName: string;
  rowCount: number;
  scopeLabel: string;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
  readModelStatus?: string;
  message?: string;
};

export type InputInvoiceUsageExportDownload = {
  blob: Blob;
  fileName: string;
};
