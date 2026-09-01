import type { BackgroundJob } from "../backgroundJobs/types";
import type { ImportPreviewAuditCounts } from "../imports/types";

export type EtcBusinessBatchStatus =
  | "draft"
  | "reviewing"
  | "ready_for_import"
  | "importing"
  | "imported"
  | "import_failed"
  | "import_partial_failed"
  | "oa_draft_creating"
  | "oa_draft_failed"
  | "oa_confirmation_pending"
  | "oa_submitted"
  | "not_submitted"
  | "manually_marked_submitted"
  | "manually_marked_not_submitted"
  | "migration_conflict"
  | "business_batch_invariant_broken"
  | "closed"
  | "deleted"
  | "superseded";

export type EtcInvoiceStatus = "unsubmitted" | "submitted";

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

export type EtcBusinessBatchBucket = "unsubmitted" | "staged" | "submitted";

export type EtcInvoiceQuery = {
  status?: EtcInvoiceStatus;
  month?: string;
  plate?: string;
  keyword?: string;
  importBatchId?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type EtcInvoiceListPayload = {
  counts: EtcInvoiceCounts;
  items: EtcInvoice[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcBusinessBatchCounts = {
  unsubmitted: number;
  staged: number;
  submitted: number;
};

export type EtcPageStatistics = {
  inputInvoiceCount?: number;
  invoiceCount?: number;
};

export type EtcBusinessBatchQuery = {
  bucket?: EtcBusinessBatchBucket;
  status?: EtcBusinessBatchStatus;
  month?: string;
  plate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type EtcBusinessBatchInvoiceSummary = {
  count: number;
  amount: string;
};

export type EtcBusinessBatchImportAttempt = {
  attemptId: string;
  importBatchId: string;
  status: string;
  imported: number;
  duplicatesSkipped: number;
  attachmentsCompleted: number;
  failed: number;
  createdAt: string;
};

export type EtcBusinessBatchAuditEvent = {
  eventId: string;
  eventType: string;
  beforeStatus: string;
  afterStatus: string;
  reason: string;
  createdAt: string;
};

export type EtcCreateOaDraftAction = {
  enabled: boolean;
  code: string;
  message: string;
};

export type EtcBusinessBatchAmountBreakdown = {
  reportedAmount: string;
  oaAmount: string;
  etcInvoiceAmount: string;
  gapAmount: string;
  gapReason: string;
};

export type EtcBusinessBatchSummary = {
  businessBatchId: string;
  taskId: string;
  title: string;
  status: EtcBusinessBatchStatus;
  version: number;
  scopeMonth: string;
  ownerUserId: string;
  ownerOrgId: string;
  importBatchIds: string[];
  submissionBatchId: string;
  externalEtcBatchId: string;
  oaDraftId: string;
  oaDraftUrl: string;
  oaRowId: string;
  oaProcessStatus: string;
  invoiceSummary: EtcBusinessBatchInvoiceSummary;
  invoiceDateStart?: string;
  invoiceDateEnd?: string;
  amountBreakdown: EtcBusinessBatchAmountBreakdown;
  createOaDraftAction: EtcCreateOaDraftAction;
  createdAt: string;
  updatedAt: string;
};

export type EtcBusinessBatchDetail = EtcBusinessBatchSummary & {
  invoiceIds: string[];
  importAttempts: EtcBusinessBatchImportAttempt[];
  auditEvents: EtcBusinessBatchAuditEvent[];
  invoiceItems: EtcInvoice[];
};

export type EtcBusinessBatchListPayload = {
  counts: EtcBusinessBatchCounts;
  items: EtcBusinessBatchSummary[];
  statistics?: EtcPageStatistics;
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcCreateBusinessBatchPayload = {
  taskId?: string;
  title?: string;
  idempotencyKey?: string;
};

export type EtcBusinessBatchVersionedPayload = {
  expectedVersion?: number;
  idempotencyKey?: string;
};

export type EtcBusinessBatchReasonedPayload = EtcBusinessBatchVersionedPayload & {
  reason: string;
};

export type EtcManualOaStatusPayload = {
  decision: "submitted" | "not_submitted";
  reason: string;
  expectedVersion?: number;
  candidateOaRowId?: string;
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
  requirementIds: string[];
  invoiceNumbers: string[];
  fileNames?: string[];
  transactionAt?: string;
  transactionDate?: string;
  amount?: string;
  vehiclePlate?: string | null;
  invoiceCount?: number | null;
  matchedInvoiceCount?: number | null;
  missingInvoiceCount?: number | null;
  dateWindowStart?: string;
  dateWindowEnd?: string;
  resolutionHint?: string;
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
  audit: ImportPreviewAuditCounts;
  importAudit: ImportPreviewAuditCounts;
  reconciliationFilter?: EtcReconciliationFilterPreview;
  items: EtcImportItem[];
};

export type EtcImportConfirmResult = {
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

export type EtcReconciledItem = {
  itemId: string;
  creditCardItemId: string;
  ticketRootItemIds: string[];
  supplementEvidenceIds: string[];
  resolution: string;
  note: string;
  claimAmount: string;
  evidenceAmount: string;
  amountDelta: string;
  amountDeltaNote: string;
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
  reconciledItems: EtcReconciledItem[];
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
