import type { BackgroundJob } from "../backgroundJobs/types";
import type { ImportPreviewAuditCounts } from "../imports/types";

export type EtcBatchStatus = "unsubmitted" | "submitted";

export type EtcInvoiceStatus = EtcBatchStatus;

export type EtcInvoice = {
  id: string;
  invoiceNumber: string;
  issueDate: string;
  passageStartDate: string | null;
  passageEndDate: string | null;
  plateNumber: string;
  sellerName: string;
  buyerName: string;
  amountWithoutTax: string;
  taxAmount: string;
  totalAmount: string;
  status: EtcInvoiceStatus;
  hasPdf: boolean;
  hasXml: boolean;
};

export type EtcInvoiceCounts = {
  unsubmitted: number;
  submitted: number;
};

export type EtcPlateSummary = {
  plateNumber: string;
  invoiceCount: number;
  totalAmount: string;
};

export type EtcBatchSummary = {
  id: string;
  etcBatchId: string;
  externalBatchId: string;
  status: EtcBatchStatus;
  sourceType: string;
  invoiceCount: number;
  totalAmount: string;
  taxAmount: string;
  issueStartDate: string | null;
  issueEndDate: string | null;
  passageStartDate: string | null;
  passageEndDate: string | null;
  plateCount: number;
  plateSummary: EtcPlateSummary[];
  linkedOaRowId: string;
  linkedOaCaseId: string;
  linkedOaApplicant: string;
  linkedOaApplyDate: string;
  linkedOaAmount: string;
  amountDelta: string;
  etcInvoiceCount: number;
  supplementCount: number;
  supplementAmount: string;
  displayCountText: string;
  note: string;
};

export type EtcBatchDetail = EtcBatchSummary & {
  invoiceItems: EtcInvoice[];
};

export type EtcBatchCounts = {
  unsubmitted: number;
  submitted: number;
};

export type EtcBatchQuery = {
  status?: EtcBatchStatus;
  month?: string;
  plate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type EtcInvoiceQuery = EtcBatchQuery;

export type EtcInvoiceListPayload = {
  counts: EtcInvoiceCounts;
  items: EtcInvoice[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcBatchListPayload = {
  counts: EtcBatchCounts;
  items: EtcBatchSummary[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcImportSummary = {
  imported: number;
  duplicatesSkipped: number;
  attachmentsCompleted: number;
  failed: number;
  items: unknown[];
};

export type EtcImportItemStatus =
  | "created"
  | "duplicate_skipped"
  | "attachment_completed"
  | "failed";

export type EtcImportItem = {
  invoiceNumber: string;
  fileName: string;
  status: EtcImportItemStatus | string;
  reason: string;
  filterStatus?: string;
  requirementId?: string | null;
};

export type EtcReconciliationBlockingIssue = {
  error: string;
  requirementId: string;
  transactionAt?: string;
  transactionDate?: string;
  amount?: string;
  vehiclePlate?: string | null;
  invoiceCount?: number | null;
  dateWindowStart?: string;
  dateWindowEnd?: string;
};

export type EtcReconciliationFilterPreview = {
  taskId: string;
  taskVersion: number;
  confirmedItemSetHash: string;
  allowedInvoiceNumbers: string[];
  blockingIssues: EtcReconciliationBlockingIssue[];
};

export type EtcImportPreviewResult = {
  sessionId: string;
  imported: number;
  duplicatesSkipped: number;
  attachmentsCompleted: number;
  failed: number;
  audit?: ImportPreviewAuditCounts;
  importAudit?: ImportPreviewAuditCounts;
  reconciliationFilter?: EtcReconciliationFilterPreview;
  items: EtcImportItem[];
};

export type EtcImportConfirmResult = EtcImportPreviewResult & {
  job?: BackgroundJob;
};

export type EtcOaDraftPayload = {
  batchId: string;
  etcBatchId: string;
  oaDraftId: string;
  oaDraftUrl: string;
};

export type EtcReconciliationTaskStatus =
  | "draft"
  | "reviewing"
  | "ready_for_import"
  | "importing"
  | "imported"
  | "closed";

export type EtcRecommendationStatus =
  | "not_candidate"
  | "suggested_match"
  | "needs_review"
  | "missing_ticket"
  | "extra_ticket"
  | string;

export type EtcManualResolution =
  | "unresolved"
  | "included_etc"
  | "covered_by_supplement"
  | "excluded_non_etc"
  | "excluded_error"
  | "manual_confirmed"
  | string;

export type EtcCreditCardItem = {
  itemId: string;
  transactionDate: string;
  postingDate: string;
  cardLast4: string;
  description: string;
  amount: string;
  settlementAmount: string;
  isEtcCandidate: boolean;
  candidateReason: string;
  recommendationStatus: EtcRecommendationStatus;
  manualResolution: EtcManualResolution;
  manualResolutionReason: string;
  reviewNote: string;
};

export type EtcTicketRootItem = {
  itemId: string;
  sourceFileId: string;
  vehiclePlate: string;
  transactionAt: string;
  amount: string;
  entryStation: string;
  exitStation: string;
  invoiceCount: number;
  recommendationStatus: EtcRecommendationStatus;
  linkedCreditCardItemIds: string[];
};

export type EtcSupplementEvidence = {
  evidenceId: string;
  sourceName: string;
  evidenceKind: string;
  amount: string;
  paidAt: string;
  merchantName: string;
  tags: string[];
  includeInEtcZipCheck: boolean;
  includeInOaSubmission: boolean;
  includeInWorkbench: boolean;
};

export type EtcSourceFile = {
  fileId: string;
  sourceKind: string;
  originalName: string;
  contentType?: string;
  hasBlockingIssue: boolean;
};

export type EtcTicketRootTextEntry = {
  clientId: string;
  text: string;
};

export type EtcParseIssue = {
  issueId: string;
  fileId: string;
  sourceKind: string;
  originalName: string;
  severity: "info" | "warning" | "blocking" | string;
  message: string;
  sourcePage: number | null;
  sourceLine: number | null;
  extractionMethod: string;
  fieldName: string;
};

export type EtcReconciliationTask = {
  taskId: string;
  status: EtcReconciliationTaskStatus;
  version: number;
  title: string;
  periodStart: string | null;
  periodEnd: string | null;
  statementPeriodStart: string | null;
  statementPeriodEnd: string | null;
  approvedDelta: string;
  approvedDeltaNote: string;
  cardLast4: string;
  oaTotalAmount: string;
  etcInvoiceAmount: string;
  supplementAmount: string;
  etcInvoiceCount: number;
  supplementCount: number;
  canConfirm: boolean;
  vehiclePlates: string[];
  confirmedItemSetHash: string;
  importBatchId: string;
  etcBatchId: string;
  hasImportedInvoices: boolean;
  importedInvoiceCount: number;
  importedInvoiceAmount: string;
  oaDraftBatchId: string;
  oaDraftStatus: string;
  submittedConfirmedAt: string;
  creditCardItems: EtcCreditCardItem[];
  ticketRootItems: EtcTicketRootItem[];
  supplementEvidences: EtcSupplementEvidence[];
  sourceFiles: EtcSourceFile[];
  parseIssues: EtcParseIssue[];
};

export type EtcReconciliationTaskSummary = Pick<
  EtcReconciliationTask,
  | "taskId"
  | "status"
  | "version"
  | "title"
  | "periodStart"
  | "periodEnd"
  | "oaTotalAmount"
  | "etcInvoiceCount"
  | "supplementCount"
  | "vehiclePlates"
>;

export type EtcImportBlocker = {
  code: string;
  message: string;
};

export type EtcUnavailableReconciliationTaskSummary = EtcReconciliationTaskSummary & {
  importBlockers: EtcImportBlocker[];
};

export type EtcReadyReconciliationTasksPayload = {
  items: EtcReconciliationTaskSummary[];
  unavailableItems: EtcUnavailableReconciliationTaskSummary[];
};

export type EtcReconciliationTaskListPayload = {
  items: EtcReconciliationTask[];
};

export type EtcCreateReconciliationTaskPayload = {
  title?: string;
};

export type EtcPatchReconciliationItemPayload = {
  action: string;
  manualResolution?: EtcManualResolution;
  note?: string;
  reason?: string;
  supplementEvidenceId?: string;
  [key: string]: unknown;
};
