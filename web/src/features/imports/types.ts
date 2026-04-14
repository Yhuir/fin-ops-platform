export type ImportBatchType = "input_invoice" | "output_invoice" | "bank_transaction";

export type ImportFileStatus =
  | "preview_ready"
  | "preview_ready_with_errors"
  | "unrecognized_template"
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
};

export type ImportRowResult = {
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
  previewBatchId?: string | null;
  batchId?: string | null;
  storedFilePath?: string | null;
  overrideTemplateCode?: string | null;
  overrideBatchType?: ImportBatchType | null;
  selectedBankName?: string | null;
  rowResults: ImportRowResult[];
};

export type ImportFilePreviewOverride = {
  fileName?: string;
  templateCode?: string | null;
  batchType?: ImportBatchType | null;
  bankName?: string | null;
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
  matchingRun?: MatchingRunSummary;
};
