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
  | { kind: "receiptHistory"; invoiceId: string; rowId: string }
  | { kind: "receiptPreview"; rowId: string }
  | null;

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
  relationKind?: "bank" | "red_invoice" | "receipt";
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
  detailAvailable: boolean;
};

export type OutputInvoiceCollectionRelationSummary<T> = {
  primary: T | null;
  relationCount: number;
  hasMultiple: boolean;
  detailMode: "none" | "single" | "list";
  summaries: T[];
};

export type OutputInvoiceCollectionRedInvoiceSummary = {
  id: string;
  invoiceNo: string;
  invoiceDate: string;
  buyerName: string;
  totalWithTax: string;
  relationType: string;
  reason: string;
};

export type OutputInvoiceCollectionReceiptSummary = {
  status: string;
  label: string;
  reason: string;
  previewAvailable: boolean;
  sourceAvailable: boolean;
};

export type OutputInvoiceCollectionRow = {
  id: string;
  invoiceId: string;
  invoice: OutputInvoiceCollectionInvoiceSummary;
  collectionStatus: OutputInvoiceCollectionStatus;
  bank: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionBankSummary>;
  redInvoice: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionRedInvoiceSummary>;
  receipt: OutputInvoiceCollectionReceiptSummary;
};

export type OutputInvoiceCollectionRowsResponse = {
  rows: OutputInvoiceCollectionRow[];
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
  futureWriteBoundary?: Record<string, string>;
};

export type OutputInvoiceReceiptHistoryResponse = {
  invoiceId: string;
  sourceAvailable: boolean;
  sourceName?: string;
  receipts: Array<{
    receiptId?: string;
    receiptNo?: string;
    amount?: string;
    issuedAt?: string;
    status?: string;
  }>;
  message?: string;
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
