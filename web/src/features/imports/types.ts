import type { BackgroundJob } from "../backgroundJobs/types";

export type ImportBatchType = "input_invoice" | "output_invoice" | "bank_transaction";

export type ImportFileStatus =
  | "preview_ready"
  | "preview_ready_with_errors"
  | "unrecognized_template"
  | "duplicate_file"
  | "source_control_mismatch"
  | "confirmed"
  | "skipped"
  | "reverted";

export type ImportRowDecision =
  | "created"
  | "status_updated"
  | "duplicate_skipped"
  | "suspected_duplicate"
  | "error";

export type ImportSessionSummary = {
  id: string;
  importedBy: string;
  fileCount: number;
  status: string;
  createdAt: string;
  audit?: ImportPreviewAuditCounts;
};

export type ActiveImportSession = {
  sessionId: string;
  importedBy: string;
  fileCount: number;
  batchType?: ImportBatchType | null;
  createdAt: string;
  updatedAt: string;
  status: "awaiting_confirmation" | "preview_failed" | "failed" | string;
  jobId?: string | null;
  jobStage?: string | null;
  error?: string | null;
};

export type ImportPreviewAuditCounts = {
  originalCount: number;
  uniqueCount: number;
  duplicateCount: number;
  duplicateInFileCount: number;
  duplicateAcrossFilesCount: number;
  existingDuplicateCount: number;
  importableCount: number;
  updateCount: number;
  mergeCount: number;
  suspectedDuplicateCount: number;
  errorCount: number;
  confirmableCount: number;
  skippedCount: number;
};

export type ImportPreviewDetailRow = {
  decision?: ImportRowDecision | string | null;
  decisionReason?: string | null;
  linkedObjectType?: string | null;
  linkedObjectId?: string | null;
  identityKind?: string | null;
  accountNo?: string | null;
  tradeTime?: string | null;
  direction?: string | null;
  amount?: string | null;
  counterpartyName?: string | null;
  invoiceNo?: string | null;
  invoiceDate?: string | null;
  sellerName?: string | null;
  buyerName?: string | null;
  taxAmount?: string | null;
  totalWithTax?: string | null;
};

export type ImportReviewRowsPage = {
  rows: Array<ImportPreviewDetailRow & {
    id: string;
    fileId: string;
    fileName: string;
    rowNo: number;
    duplicateType?: string;
    recordType?: string;
  }>;
  total: number;
  offset: number;
  limit: number;
  hasMore: boolean;
};

export type ImportPreviewDuplicateGroup = {
  identityKey: string;
  recordType: string;
  duplicateType: string;
  rows: Array<ImportPreviewDetailRow & {
    fileId: string;
    fileName: string;
    rowNo: number;
  }>;
};

export type ImportRowResult = ImportPreviewDetailRow & {
  id: string;
  rowNo: number;
  sourceRecordType: string;
  decision: ImportRowDecision;
  decisionReason: string;
};

export type ImportFilePreview = {
  id: string;
  fileName: string;
  templateCode?: string | null;
  batchType?: ImportBatchType | null;
  status: ImportFileStatus;
  message: string;
  rowCount: number;
  successCount: number;
  errorCount: number;
  duplicateCount: number;
  suspectedDuplicateCount: number;
  updatedCount: number;
  audit?: ImportPreviewAuditCounts;
  previewBatchId?: string | null;
  batchId?: string | null;
  storedFilePath?: string | null;
  overrideTemplateCode?: string | null;
  overrideBatchType?: ImportBatchType | null;
  selectedBankMappingId?: string | null;
  selectedBankName?: string | null;
  selectedBankShortName?: string | null;
  selectedBankLast4?: string | null;
  detectedBankName?: string | null;
  detectedLast4?: string | null;
  bankSelectionConflict?: boolean;
  conflictMessage?: string | null;
  headerSignature?: string | null;
  mappingCandidates: Array<{ key: string; label: string }>;
  mappingFields: Array<{ key: string; label: string; selected?: string | null; required: boolean }>;
  fieldMapping: Record<string, string>;
  mappingSource?: "auto" | "manual" | "saved" | null;
  duplicateFileName?: string | null;
  sourceControl?: ImportSourceControlEvidence | null;
  rowResults: ImportRowResult[];
};

export type ImportSourceControlEvidence = {
  status: "not_applicable" | "unavailable" | "verified" | "mismatch";
  computedRowCount: number;
  declaredRowCount?: number | null;
  computedDebitTotal?: string | null;
  declaredDebitTotal?: string | null;
  computedCreditTotal?: string | null;
  declaredCreditTotal?: string | null;
  mismatchFields: string[];
};

export type ImportFilePreviewOverride = {
  fileName?: string;
  templateCode?: string | null;
  batchType?: ImportBatchType | null;
  bankMappingId?: string | null;
  bankName?: string | null;
  bankShortName?: string | null;
  last4?: string | null;
  fieldMapping?: Record<string, string>;
};

export type ImportTemplate = {
  templateCode: string;
  label: string;
  fileExtensions: string[];
  recordType: "invoice" | "bank_transaction";
  allowedBatchTypes: ImportBatchType[];
  requiredHeaders: string[];
};

export type MatchingRunSummary = {
  id: string;
  triggeredBy: string;
  resultCount: number;
  automaticCount: number;
  suggestedCount: number;
  manualReviewCount: number;
};

export type ImportSessionPayload = {
  session: ImportSessionSummary;
  files: ImportFilePreview[];
  duplicateGroups: ImportPreviewDuplicateGroup[];
  matchingRun?: MatchingRunSummary;
  job?: BackgroundJob;
  affectedScopeKeys: string[];
};

export type ManualInvoiceDirection = "input" | "output";
export type ManualInvoiceNature = "blue" | "red";

export type ManualInvoiceEntryValues = {
  invoiceDirection: ManualInvoiceDirection;
  invoiceNature: ManualInvoiceNature;
  sellerName: string;
  sellerTaxNo: string;
  buyerName: string;
  buyerTaxNo: string;
  invoiceNumber: string;
  invoiceCode: string;
  invoiceDate: string;
  netAmount: string;
  taxRate: string;
  taxAmount: string;
  totalWithTax: string;
};

export type ManualInvoiceEntryBatchPreview = {
  values: ManualInvoiceEntryValues[];
  fileIds: string[];
  importSession: ImportSessionPayload;
};
