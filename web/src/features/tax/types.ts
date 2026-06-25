import type { OperationBarrierTarget } from "../operationBarrier/api";

export type TaxInvoiceRecord = {
  id: string;
  invoiceNo: string;
  invoiceType: string;
  flowType?: "input" | "output";
  counterparty: string;
  issueDate: string;
  taxRate: string;
  amount: string;
  taxAmount: string;
  statusLabel?: string;
  isLocked?: boolean;
  isSelectable?: boolean;
};

export type TaxCertifiedInvoiceRecord = TaxInvoiceRecord & {
  matchedInputId: string | null;
};

export type TaxSummary = {
  outputTax: string;
  certifiedInputTax: string;
  plannedInputTax: string;
  inputTax: string;
  deductibleTax: string;
  resultLabel: string;
  resultAmount: string;
};

export type TaxMonthData = {
  outputInvoices: TaxInvoiceRecord[];
  inputPlanInvoices: TaxInvoiceRecord[];
  certifiedMatchedInvoices: TaxCertifiedInvoiceRecord[];
  certifiedOutsidePlanInvoices: TaxCertifiedInvoiceRecord[];
  lockedCertifiedInputIds: string[];
  defaultSelectedOutputIds: string[];
  defaultSelectedInputIds: string[];
  summary: TaxSummary;
  readModelStatus?: "fresh" | "refreshing" | "stale" | string;
  readModelScopeKey?: string;
  readModelGeneratedAt?: string | null;
  readModelStaleReasons?: string[];
  sourceVersions?: Record<string, unknown>;
};

export type TaxCertifiedImportPreviewRow = {
  id: string;
  month: string;
  rowStatus: "recognized" | "invalid" | string;
  matchStatus: "matched_plan" | "outside_plan" | "unknown" | string;
  matchedPlanId: string | null;
  dedupeStatus: "new" | "duplicate" | "not_applicable" | string;
  errorMessage: string | null;
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
  month: string;
  recognizedCount: number;
  invalidCount: number;
  matchedPlanCount: number;
  outsidePlanCount: number;
  rows: TaxCertifiedImportPreviewRow[];
};

export type TaxCertifiedImportPreviewResult = {
  sessionId: string;
  importedBy: string;
  fileCount: number;
  status: string;
  files: TaxCertifiedImportPreviewFile[];
  summary: {
    recognizedCount: number;
    invalidCount: number;
    matchedPlanCount: number;
    outsidePlanCount: number;
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

export type TaxCertifiedImportConfirmResult =
  | TaxCertifiedImportConfirmedResult
  | TaxCertifiedImportQueuedResult;

export type TaxOffsetPlanSaveResult = {
  status: "saved";
  readModelScopeKeys: string[];
  freshnessTargets: OperationBarrierTarget[];
  operationBarrierTargets: OperationBarrierTarget[];
  plan: {
    id: string;
    month: string;
    selectedOutputIds: string[];
    selectedInputIds: string[];
    summary: TaxSummary;
    readModelScopeKey?: string;
    sourceVersions?: Record<string, unknown>;
    updatedAt?: string;
  };
};
