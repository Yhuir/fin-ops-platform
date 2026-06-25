import type { OperationBarrierTarget } from "../operationBarrier/api";

export type OutputInvoiceCollectionSortDirection = "asc" | "desc";

export type OutputInvoiceCollectionFilterOperator =
  | "contains"
  | "equals"
  | "in"
  | "between";

export type OutputInvoiceCollectionFilter = {
  field: string;
  operator: OutputInvoiceCollectionFilterOperator;
  value?: string | string[] | [string, string] | { min?: string; max?: string } | null;
  values?: string[];
};

export type OutputInvoiceCollectionWorkflow =
  | { kind: "statusRules" }
  | { kind: "export" }
  | { kind: "collectionStatus"; rowId: string }
  | { kind: "redRelation"; rowId: string }
  | { kind: "receiptHistory"; invoiceId: string; rowId: string }
  | { kind: "receiptPreview"; rowId: string }
  | { kind: "receiptSettings" }
  | null;

export type OutputInvoiceCollectionMutationResponse = {
  readModelScopeKeys: string[];
  freshnessTargets: OperationBarrierTarget[];
  operationBarrierTargets: OperationBarrierTarget[];
  raw: unknown;
};

export type OutputInvoiceCollectionQuery = {
  page: number;
  pageSize: number;
  keyword: string;
  invoiceDateFrom: string;
  invoiceDateTo: string;
  month: string;
  filters: OutputInvoiceCollectionFilter[];
  sortField: string;
  sortDirection: OutputInvoiceCollectionSortDirection | "";
  activeWorkflow: OutputInvoiceCollectionWorkflow;
  detailTarget: OutputInvoiceCollectionDetailTarget | null;
};

export type OutputInvoiceCollectionDetailTarget = {
  kind: "invoice" | "bank" | "relationList";
  id: string;
  rowId?: string;
  relationKind?: "oa" | "bank" | "invoice" | "red_invoice" | "receipt";
};

export type OutputInvoiceCollectionInvoiceSummary = {
  id: string;
  displayNo: string;
  invoiceNo: string;
  invoiceCode: string;
  digitalInvoiceNo: string;
  issueDate: string;
  buyerName: string;
  buyerTaxNo: string;
  sellerName: string;
  sellerTaxNo: string;
  totalWithTax: string;
  amountWithoutTax: string;
  taxRate: string;
  taxAmount: string;
  specificBusinessType: string;
  taxableItemName: string;
};

export type OutputInvoiceCollectionStatus = {
  code: string;
  label: string;
  reason: string;
  collectedAmount: string;
  pendingAmount: string;
  severity?: "success" | "warning" | "error" | "info" | string;
  matchedRuleId?: string;
  manualOverride?: {
    id?: string;
    statusCode?: string;
    expectedCollectionDate?: string | null;
    note?: string;
    version?: number;
  } | null;
  expectedCollectionDate?: string | null;
  reminder?: {
    id?: string;
    remindAt?: string;
    channel?: string;
    note?: string;
    status?: string;
  } | null;
};

export type OutputInvoiceCollectionBankSummary = {
  id: string;
  counterpartyName: string;
  tradeTime: string;
  amount: string;
  direction: string;
  directionLabel: string;
  bankName: string;
  accountLast4: string;
  summary: string;
  remark: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
  detailAvailable: boolean;
};

export type OutputInvoiceCollectionOaSummary = {
  id: string;
  applicantName: string;
  applicationType: string;
  projectName: string;
  amount: string;
  status: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
  detailAvailable: boolean;
};

export type OutputInvoiceCollectionRelatedInvoiceSummary = {
  id: string;
  invoiceNo: string;
  invoiceCode: string;
  digitalInvoiceNo: string;
  invoiceDate: string;
  buyerName: string;
  buyerTaxNo: string;
  totalWithTax: string;
  taxableItemName: string;
  relationCaseId?: string;
  relationStatus?: string;
  relationSource?: string;
};

export type OutputInvoiceCollectionRelationSummary<T> = {
  primary: T | null;
  relationCount: number;
  hasMultiple: boolean;
  receivedTotal?: string;
  totalWithTax?: string;
  detailMode: "none" | "single" | "list";
  summaries: T[];
};

export type OutputInvoiceCollectionRedInvoiceSummary = {
  id: string;
  relationId?: string;
  invoiceNo: string;
  invoiceDate: string;
  buyerName: string;
  totalWithTax: string;
  relationType: string;
  reason: string;
  evidence?: string;
  confidence?: string;
  source?: string;
};

export type OutputInvoiceCollectionReceiptSummary = {
  status: string;
  label: string;
  reason: string;
  previewAvailable: boolean;
  sourceAvailable: boolean;
  latestReceipt?: {
    id?: string;
    receiptNo?: string;
    amount?: string;
    status?: string;
    createdAt?: string;
  } | null;
};

export type OutputInvoiceCollectionRow = {
  id: string;
  invoiceId: string;
  invoiceIdentityKey?: string;
  invoice: OutputInvoiceCollectionInvoiceSummary;
  collectionStatus: OutputInvoiceCollectionStatus;
  oa: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionOaSummary>;
  bank: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionBankSummary>;
  invoiceRelations: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionRelatedInvoiceSummary>;
  redInvoice: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionRedInvoiceSummary>;
  receipt: OutputInvoiceCollectionReceiptSummary;
};

export type OutputInvoiceCollectionRowsResponse = {
  rows: OutputInvoiceCollectionRow[];
  summary?: {
    invoiceCount: number;
    totalWithTax: string;
    collectedAmount: string;
    pendingAmount: string;
    pendingCollectionCount: number;
    partialCollectionCount: number;
    receiptPendingCount: number;
  };
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  filterConfig: OutputInvoiceCollectionFilterFieldConfig[];
  readModelStatus?: string;
  readModelScopeKey?: string;
  generatedAt?: string;
  sourceVersion?: string;
};

export type OutputInvoiceCollectionFilterFieldConfig = {
  field: string;
  label: string;
  mode: "text" | "enum_single" | "enum_multi" | "date" | "money";
  sortable: boolean;
  operators: OutputInvoiceCollectionFilterOperator[];
};

export type OutputInvoiceCollectionFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type OutputInvoiceCollectionFilterOptionsResponse = {
  fields: Array<OutputInvoiceCollectionFilterFieldConfig & {
    options: OutputInvoiceCollectionFilterOption[];
  }>;
  readModelStatus?: string;
  readModelScopeKey?: string;
};

export type OutputInvoiceCollectionExportPreview = {
  fileName: string;
  rowCount: number;
  scopeLabel: string;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
  readModelStatus?: string;
  message?: string;
};

export type OutputInvoiceCollectionExportDownload = {
  blob: Blob;
  fileName: string;
};

export type OutputInvoiceCollectionDetailResponse = {
  title?: string;
  subtitle?: string;
  detailAvailable?: boolean;
  unavailableReason?: string;
  sections: Array<{
    title: string;
    fields: Array<{ label: string; value: string | number | null | undefined }>;
  }>;
};

export type OutputInvoiceCollectionStatusRulesResponse = {
  version?: string;
  readOnly?: boolean;
  rules: Array<{
    id?: string;
    code?: string;
    label: string;
    description: string;
    recognitionMode?: string;
    requiredFacts?: string[];
    workbenchRequirement?: string;
    priority: number;
  }>;
  manualStatusOptions?: Array<{
    code: string;
    label: string;
    severity?: string;
    matchedRuleId?: string;
  }>;
  permissions?: {
    can_save?: boolean;
    can_admin?: boolean;
  };
  futureWriteBoundary?: Record<string, string>;
};

export type OutputInvoiceReceiptHistoryResponse = {
  invoiceId: string;
  sourceAvailable: boolean;
  sourceName?: string;
  receipts: Array<{
    id?: string;
    receiptNo?: string;
    amount?: string;
    createdAt?: string;
    voidedAt?: string;
    voidReason?: string;
    reissuedFromReceiptId?: string;
    status?: string;
  }>;
  message?: string;
};

export type OutputInvoiceReceiptSettingsResponse = {
  settings: {
    tenantId?: string;
    prefix: string;
    resetPeriod: "monthly" | "yearly" | "none" | string;
    version?: number;
    updatedBy?: string;
    updatedAt?: string;
  };
};

export type OutputInvoiceCollectionStatusUpdateRequest = {
  statusCode?: string;
  expectedCollectionDate?: string;
  note?: string;
  expectedVersion?: number;
};

export type OutputInvoiceCollectionReminderUpdateRequest = {
  remindAt: string;
  channel: string;
  note?: string;
};

export type OutputInvoiceCollectionRedRelationRequest = {
  relatedInvoiceIdentityKey?: string;
  relatedInvoiceId?: string;
  relationType: "red_invoice" | "blue_invoice";
  evidence: string;
  confidence?: string;
};

export type OutputInvoiceReceiptCreateRequest = {
  bankTransactionId?: string;
  selectedBankTransactionId?: string;
  idempotencyKey: string;
};

export type OutputInvoiceReceiptPreviewRequest = {
  rowId: string;
  selectedBankTransactionId?: string;
};

export type OutputInvoiceReceiptPreviewResponse = {
  canPreview: boolean;
  reasonCode?: string;
  reason?: string;
  pendingAmount?: string;
  selectedBankTransactionId?: string;
  candidates: Array<{
    bankTransactionId: string;
    counterpartyName: string;
    tradeTime: string;
    amount: string;
    bankName: string;
    summary?: string;
  }>;
  receipt?: {
    templateVersion: string;
    companyName: string;
    title: string;
    date: string;
    dateParts: { year: string; month: string; day: string };
    payerName: string;
    summary: string;
    amount: string;
    amountUppercase: string;
    remark: string;
    bankName?: string;
    bankTransactionId?: string;
    canCreateFormalReceipt?: boolean;
    nextAction?: string;
  };
  warnings?: string[];
};
