export type TaxCertificationStatus = "all" | "certified" | "uncertified";
export type TaxCertificationFilters = {
  status: TaxCertificationStatus;
  issue_month?: string;
  selection_month?: string;
  search?: string;
  sort_by: "issue_date" | "selection_time";
  sort_direction: "asc" | "desc";
};
export type TaxCertificationQuery = TaxCertificationFilters & { page: number; page_size: number };
export type TaxCertificationRow = {
  id: string;
  digital_invoice_no: string | null;
  invoice_code: string | null;
  invoice_no: string | null;
  seller_name: string | null;
  seller_tax_no: string | null;
  issue_date: string | null;
  amount: string | null;
  tax_amount: string | null;
  certification_status: "certified" | "uncertified";
  selection_time: string | null;
  deductible_tax_amount: string | null;
  tax_period: string | null;
};
export type TaxCertificationTotals = {
  count: number; amount: string | null; tax_amount: string | null;
  missing_amount_count: number; missing_tax_count: number;
};
export type TaxExportField = { key: string; label: string; default_selected: boolean };
export type TaxCertificationResult = {
  unresolved_record_count: number;
  rows: TaxCertificationRow[]; total: number; page: number; page_size: number;
  summary: {
    certified: TaxCertificationTotals & { deductible_tax_amount: string | null; missing_deductible_tax_count: number };
    uncertified: TaxCertificationTotals;
  };
  export_fields: TaxExportField[];
};

export type TaxCertifiedImportPreviewRow = {
  id: string;
  month: string | null;
  buyerTaxNo: string | null;
  rowStatus: "recognized" | "invalid" | "ignored";
  matchStatus: "matched_invoice" | "outside_invoices" | "ambiguous" | "unknown";
  uniqueKey: string | null;
  expectedVersion: number | null;
  dedupeStatus: "new" | "duplicate" | "conflict" | "not_applicable";
  errorMessage: string | null;
  blocking: boolean;
  digitalInvoiceNo: string | null;
  invoiceCode: string | null;
  invoiceNo: string | null;
  issueDate: string | null;
  sellerTaxNo: string | null;
  sellerName: string | null;
  taxAmount: string | null;
  deductibleTaxAmount: string | null;
  selectionStatus: string | null;
  invoiceStatus: string | null;
  selectionTime: string | null;
  sourceFileName: string;
  sourceRowNumber: number;
};

export type TaxCertifiedImportPreviewFile = {
  id: string;
  fileName: string;
  month: string | null;
  recognizedCount: number;
  invalidCount: number;
  ignoredCount: number;
  matchedInvoiceCount: number;
  outsideInvoicesCount: number;
  conflictCount: number;
  duplicateCount: number;
  rows: TaxCertifiedImportPreviewRow[];
};

export type TaxCertifiedImportPreviewResult = {
  sessionId: string;
  importedBy: string;
  fileCount: number;
  status: string;
  files: TaxCertifiedImportPreviewFile[];
  summary: {
    blockingCount: number;
    recognizedCount: number;
    invalidCount: number;
  ignoredCount: number;
    matchedInvoiceCount: number;
    outsideInvoicesCount: number;
  conflictCount: number;
  duplicateCount: number;
  };
};

export type TaxCertifiedImportJob = {
  importJobId: string;
  tenantId?: string;
  importType: string;
  importSessionId?: string | null;
  sourceFileId?: string | null;
  status: string;
  stage: string;
  priority?: string;
  attemptCount?: number;
  maxAttempts?: number;
  lastError?: string | null;
  traceId?: string | null;
  resultPayload?: Record<string, unknown>;
};

export type TaxCertifiedImportConfirmedResult = {
  status: "confirmed";
  batchId: string;
  sessionId: string;
  importedBy: string;
  fileCount: number;
  months: string[];
  persistedRecordCount: number;
};

export type TaxCertifiedImportQueuedResult = {
  status: "queued";
  importJob: TaxCertifiedImportJob;
};

export type TaxCertifiedImportConfirmResult = TaxCertifiedImportQueuedResult;


export type TaxCertifiedImportBatch = {
  id: string; session_id: string; imported_by: string; file_count: number; months: string[];
  persisted_record_count: number; duplicate_count: number; status: "confirmed" | "revoked"; version: number; created_at: string;
};
export type TaxImportCorrection = { unique_key: string; expected_version: number };

export type TaxCertifiedImportRecord = { id: string; unique_key: string; needs_review: boolean; digital_invoice_no: string | null; invoice_no: string | null; seller_name: string | null; matched_invoice_id: string | null; status: string; };

export type TaxImportHistoryQuery = { records_page: number; batches_page: number; page_size: number };
export type TaxImportHistory = TaxImportHistoryQuery & { records: TaxCertifiedImportRecord[]; batches: TaxCertifiedImportBatch[]; records_total: number; batches_total: number };
