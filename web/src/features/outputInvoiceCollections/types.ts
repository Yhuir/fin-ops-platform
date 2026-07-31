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

export type OutputInvoiceCollectionWorkflow = { kind: "export" } | null;

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
  relationKind?: "bank" | "invoice";
  scopeKey?: string;
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
  relationStatus?: "linked" | "unlinked";
  relationSource?: string;
  detailAvailable: boolean;
};

export type OutputInvoiceCollectionRelatedInvoiceSummary = {
  id: string;
  displayNo: string;
  invoiceNo: string;
  invoiceCode: string;
  digitalInvoiceNo: string;
  invoiceDate: string;
  buyerName: string;
  buyerTaxNo: string;
  totalWithTax: string;
  taxableItemName: string;
  relationId?: string;
  relationMode?: string;
  relationCaseId?: string;
  relationStatus?: "linked" | "unlinked";
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

export type OutputInvoiceCollectionRow = {
  id: string;
  invoiceId: string;
  invoiceIdentityKey?: string;
  invoice: OutputInvoiceCollectionInvoiceSummary;
  collectionStatus: OutputInvoiceCollectionStatus;
  bank: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionBankSummary>;
  invoiceRelations: OutputInvoiceCollectionRelationSummary<OutputInvoiceCollectionRelatedInvoiceSummary>;
};

export type OutputInvoiceCollectionStatistics = {
  invoiceCount?: number;
  linkedIncomeBankInvoiceCount?: number;
  collectedInvoiceCount?: number;
  unlinkedBankInvoiceCount?: number;
  uncollectedInvoiceCount?: number;
  redInvoiceCount?: number;
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
  };
  statistics?: OutputInvoiceCollectionStatistics;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  filterConfig: OutputInvoiceCollectionFilterFieldConfig[];
  filterOptions: Array<OutputInvoiceCollectionFilterFieldConfig & {
    options: OutputInvoiceCollectionFilterOption[];
  }>;
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
};

export type OutputInvoiceCollectionExportPreview = {
  fileName: string;
  rowCount: number;
  scopeLabel: string;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
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
