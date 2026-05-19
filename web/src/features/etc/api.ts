import { readOATokenCookie } from "../session/api";
import { mapBackgroundJob, type ApiBackgroundJob } from "../backgroundJobs/api";
import { apiUrl } from "../../app/runtime";
import type { ImportPreviewAuditCounts } from "../imports/types";
import type {
  EtcBusinessBatchAuditEvent,
  EtcBusinessBatchDetail,
  EtcBusinessBatchImportAttempt,
  EtcBusinessBatchListPayload,
  EtcBusinessBatchQuery,
  EtcBusinessBatchReasonedPayload,
  EtcBusinessBatchStatus,
  EtcBusinessBatchSummary,
  EtcBusinessBatchVersionedPayload,
  EtcBatchDetail,
  EtcBatchListPayload,
  EtcBatchQuery,
  EtcBatchStatus,
  EtcBatchSummary,
  EtcCreateBusinessBatchPayload,
  EtcImportConfirmResult,
  EtcImportItem,
  EtcImportPreviewResult,
  EtcImportSummary,
  EtcReconciliationBlockingIssue,
  EtcReconciliationFilterPreview,
  EtcInvoice,
  EtcInvoiceStatus,
  EtcInvoiceListPayload,
  EtcInvoiceQuery,
  EtcManualOaStatusPayload,
  EtcOaDraftPayload,
  EtcPatchReconciliationItemPayload,
  EtcReadyReconciliationTasksPayload,
  EtcReconciliationTask,
  EtcReconciliationTaskListPayload,
  EtcReconciliationTaskSummary,
  EtcUnavailableReconciliationTaskSummary,
  EtcSourceFile,
  EtcTicketRootTextEntry,
} from "./types";

type ApiEtcInvoice = {
  id: string;
  invoice_number?: string;
  invoiceNumber?: string;
  issue_date?: string;
  issueDate?: string;
  passage_start_date?: string | null;
  passageStartDate?: string | null;
  passage_end_date?: string | null;
  passageEndDate?: string | null;
  plate_number?: string | null;
  plateNumber?: string | null;
  seller_name?: string | null;
  sellerName?: string | null;
  buyer_name?: string | null;
  buyerName?: string | null;
  amount_without_tax?: string | number | null;
  amountWithoutTax?: string | number | null;
  tax_amount?: string | number | null;
  taxAmount?: string | number | null;
  total_amount?: string | number | null;
  totalAmount?: string | number | null;
  status: EtcInvoiceStatus;
  has_pdf?: boolean | null;
  hasPdf?: boolean | null;
  has_xml?: boolean | null;
  hasXml?: boolean | null;
};

type ApiEtcInvoicePayload = {
  counts?: {
    unsubmitted?: number;
    submitted?: number;
  };
  items?: ApiEtcInvoice[];
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  };
};

type ApiEtcPlateSummary = {
  plate_number?: string | null;
  plateNumber?: string | null;
  invoice_count?: number | null;
  invoiceCount?: number | null;
  total_amount?: string | number | null;
  totalAmount?: string | number | null;
};

type ApiEtcBatch = {
  id?: string;
  batch_id?: string;
  batchId?: string;
  etc_batch_id?: string;
  etcBatchId?: string;
  external_batch_id?: string;
  externalBatchId?: string;
  status?: EtcBatchStatus | EtcBusinessBatchStatus;
  source_type?: string | null;
  sourceType?: string | null;
  invoice_count?: number | null;
  invoiceCount?: number | null;
  total_amount?: string | number | null;
  totalAmount?: string | number | null;
  tax_amount?: string | number | null;
  taxAmount?: string | number | null;
  issue_start_date?: string | null;
  issueStartDate?: string | null;
  issue_end_date?: string | null;
  issueEndDate?: string | null;
  passage_start_date?: string | null;
  passageStartDate?: string | null;
  passage_end_date?: string | null;
  passageEndDate?: string | null;
  plate_count?: number | null;
  plateCount?: number | null;
  plate_summary?: ApiEtcPlateSummary[] | Record<string, unknown> | null;
  plateSummary?: ApiEtcPlateSummary[] | Record<string, unknown> | null;
  linked_oa_row_id?: string | null;
  linkedOaRowId?: string | null;
  linked_oa_case_id?: string | null;
  linkedOaCaseId?: string | null;
  linked_oa_applicant?: string | null;
  linkedOaApplicant?: string | null;
  linked_oa_apply_date?: string | null;
  linkedOaApplyDate?: string | null;
  linked_oa_amount?: string | number | null;
  linkedOaAmount?: string | number | null;
  amount_delta?: string | number | null;
  amountDelta?: string | number | null;
  etc_invoice_count?: number | null;
  etcInvoiceCount?: number | null;
  supplement_count?: number | null;
  supplementCount?: number | null;
  supplement_amount?: string | number | null;
  supplementAmount?: string | number | null;
  display_count_text?: string | null;
  displayCountText?: string | null;
  note?: string | null;
  invoice_items?: ApiEtcInvoice[];
  invoiceItems?: ApiEtcInvoice[];
  items?: ApiEtcInvoice[];
  summary?: ApiEtcBatch | null;
};

type ApiEtcBatchPayload = {
  counts?: {
    unsubmitted?: number;
    submitted?: number;
  };
  items?: ApiEtcBatch[];
  batches?: ApiEtcBatch[];
  pagination?: {
    page?: number;
    page_size?: number;
    pageSize?: number;
    total?: number;
  };
};

type ApiEnvelope<T> = {
  ok?: boolean;
  data?: T | null;
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  } | string | null;
  requestId?: string;
};

type ApiEtcBusinessBatchImportAttempt = {
  attemptId?: string;
  attempt_id?: string;
  importBatchId?: string;
  import_batch_id?: string;
  status?: string;
  imported?: number | null;
  duplicatesSkipped?: number | null;
  duplicates_skipped?: number | null;
  attachmentsCompleted?: number | null;
  attachments_completed?: number | null;
  failed?: number | null;
  createdAt?: string | null;
  created_at?: string | null;
};

type ApiEtcBusinessBatchAuditEvent = {
  eventId?: string;
  event_id?: string;
  eventType?: string;
  event_type?: string;
  beforeStatus?: string;
  before_status?: string;
  afterStatus?: string;
  after_status?: string;
  reason?: string | null;
  createdAt?: string | null;
  created_at?: string | null;
};

type ApiEtcBusinessBatch = ApiEtcBatch & {
  businessBatchId?: string;
  business_batch_id?: string;
  taskId?: string;
  task_id?: string;
  version?: number;
  ownerUserId?: string | null;
  owner_user_id?: string | null;
  ownerOrgId?: string | null;
  owner_org_id?: string | null;
  importBatchIds?: string[] | null;
  import_batch_ids?: string[] | null;
  submissionBatchId?: string | null;
  submission_batch_id?: string | null;
  externalEtcBatchId?: string | null;
  external_etc_batch_id?: string | null;
  oaDraftId?: string | null;
  oa_draft_id?: string | null;
  oaDraftUrl?: string | null;
  oa_draft_url?: string | null;
  oaRowId?: string | null;
  oa_row_id?: string | null;
  oaProcessStatus?: string | null;
  oa_process_status?: string | null;
  oaDetectionStatus?: string | null;
  oa_detection_status?: string | null;
  oaDetectionReason?: string | null;
  oa_detection_reason?: string | null;
  oaDetectionError?: string | null;
  oa_detection_error?: string | null;
  oaDetectionStartedAt?: string | null;
  oa_detection_started_at?: string | null;
  oaDetectionNextRunAt?: string | null;
  oa_detection_next_run_at?: string | null;
  oaDetectionDeadlineAt?: string | null;
  oa_detection_deadline_at?: string | null;
  oaDetectionFinalRetryUntil?: string | null;
  oa_detection_final_retry_until?: string | null;
  oaDetectionAttempts?: number | null;
  oa_detection_attempts?: number | null;
  invoiceSummary?: {
    count?: number | null;
    amount?: string | number | null;
  } | null;
  invoice_summary?: {
    count?: number | null;
    amount?: string | number | null;
  } | null;
  invoiceIds?: string[] | null;
  invoice_ids?: string[] | null;
  importAttempts?: ApiEtcBusinessBatchImportAttempt[] | null;
  import_attempts?: ApiEtcBusinessBatchImportAttempt[] | null;
  auditEvents?: ApiEtcBusinessBatchAuditEvent[] | null;
  audit_events?: ApiEtcBusinessBatchAuditEvent[] | null;
  createdAt?: string | null;
  created_at?: string | null;
  updatedAt?: string | null;
  updated_at?: string | null;
};

type ApiEtcBusinessBatchPayload = {
  counts?: {
    active?: number;
    submitted?: number;
    unsubmitted?: number;
  };
  items?: ApiEtcBusinessBatch[];
  businessBatches?: ApiEtcBusinessBatch[];
  business_batches?: ApiEtcBusinessBatch[];
  pagination?: {
    page?: number;
    page_size?: number;
    pageSize?: number;
    total?: number;
  };
};

type ApiEtcBusinessBatchSinglePayload =
  | ApiEtcBusinessBatch
  | {
    businessBatch?: ApiEtcBusinessBatch | null;
    item?: ApiEtcBusinessBatch | null;
    detail?: ApiEtcBusinessBatch | null;
  };

type ApiEtcImportSummary = {
  job?: ApiBackgroundJob;
  sessionId?: string;
  session_id?: string;
  summary?: {
    imported?: number;
    duplicatesSkipped?: number;
    duplicates_skipped?: number;
    attachmentsCompleted?: number;
    attachments_completed?: number;
    failed?: number;
  };
  imported?: number;
  duplicatesSkipped?: number;
  duplicates_skipped?: number;
  attachmentsCompleted?: number;
  attachments_completed?: number;
  failed?: number;
  audit?: ApiEtcImportAuditCounts | null;
  importAudit?: ApiEtcImportAuditCounts | null;
  import_audit?: ApiEtcImportAuditCounts | null;
  reconciliationFilter?: ApiEtcReconciliationFilterPreview | null;
  reconciliation_filter?: ApiEtcReconciliationFilterPreview | null;
  items?: ApiEtcImportItem[];
};

type ApiEtcReconciliationFilterPreview = {
  taskId?: string;
  task_id?: string;
  taskVersion?: number;
  task_version?: number;
  confirmedItemSetHash?: string;
  confirmed_item_set_hash?: string;
  allowedInvoiceNumbers?: string[];
  allowed_invoice_numbers?: string[];
  blockingIssues?: ApiEtcReconciliationBlockingIssue[];
  blocking_issues?: ApiEtcReconciliationBlockingIssue[];
};

type ApiEtcReconciliationBlockingIssue = {
  error?: string;
  requirementId?: string;
  requirement_id?: string;
  transactionAt?: string;
  transaction_at?: string;
  transactionDate?: string;
  transaction_date?: string;
  amount?: string | number;
  vehiclePlate?: string | null;
  vehicle_plate?: string | null;
  invoiceCount?: number | null;
  invoice_count?: number | null;
  dateWindowStart?: string;
  date_window_start?: string;
  dateWindowEnd?: string;
  date_window_end?: string;
};

type ApiEtcImportAuditCounts = {
  original_count?: number;
  unique_count?: number;
  duplicate_count?: number;
  duplicate_in_file_count?: number;
  duplicate_across_files_count?: number;
  existing_duplicate_count?: number;
  importable_count?: number;
  update_count?: number;
  merge_count?: number;
  suspected_duplicate_count?: number;
  error_count?: number;
  confirmable_count?: number;
  skipped_count?: number;
};

type ApiEtcImportItem = {
  invoiceNumber?: string;
  invoice_number?: string;
  fileName?: string;
  file_name?: string;
  status?: string;
  reason?: string;
  message?: string;
  filterStatus?: string;
  filter_status?: string;
  requirementId?: string | null;
  requirement_id?: string | null;
};

type ApiEtcOaDraftPayload = {
  batchId?: string;
  batch_id?: string;
  etcBatchId?: string;
  etc_batch_id?: string;
  oaDraftId?: string;
  oa_draft_id?: string;
  oaDraftUrl?: string;
  oa_draft_url?: string;
};

type ApiEtcReconciliationTask = {
  taskId?: string;
  task_id?: string;
  status?: string;
  version?: number;
  title?: string;
  periodStart?: string | null;
  period_start?: string | null;
  periodEnd?: string | null;
  period_end?: string | null;
  statementPeriodStart?: string | null;
  statement_period_start?: string | null;
  statementPeriodEnd?: string | null;
  statement_period_end?: string | null;
  approvedDelta?: string | number | null;
  approved_delta?: string | number | null;
  approvedDeltaNote?: string | null;
  approved_delta_note?: string | null;
  cardLast4?: string | null;
  card_last4?: string | null;
  oaTotalAmount?: string | number | null;
  oa_total_amount?: string | number | null;
  etcInvoiceAmount?: string | number | null;
  etc_invoice_amount?: string | number | null;
  supplementAmount?: string | number | null;
  supplement_amount?: string | number | null;
  etcInvoiceCount?: number | null;
  etc_invoice_count?: number | null;
  supplementCount?: number | null;
  supplement_count?: number | null;
  canConfirm?: boolean | null;
  can_confirm?: boolean | null;
  confirmable?: boolean | null;
  vehiclePlates?: string[] | null;
  vehicle_plates?: string[] | null;
  confirmedItemSetHash?: string | null;
  confirmed_item_set_hash?: string | null;
  importBatchId?: string | null;
  import_batch_id?: string | null;
  etcBatchId?: string | null;
  etc_batch_id?: string | null;
  hasImportedInvoices?: boolean | null;
  has_imported_invoices?: boolean | null;
  importedInvoiceCount?: number | null;
  imported_invoice_count?: number | null;
  importedInvoiceAmount?: string | number | null;
  imported_invoice_amount?: string | number | null;
  oaDraftBatchId?: string | null;
  oa_draft_batch_id?: string | null;
  oaDraftStatus?: string | null;
  oa_draft_status?: string | null;
  submittedConfirmedAt?: string | null;
  submitted_confirmed_at?: string | null;
  creditCardItems?: ApiEtcCreditCardItem[];
  credit_card_items?: ApiEtcCreditCardItem[];
  ticketRootItems?: ApiEtcTicketRootItem[];
  ticket_root_items?: ApiEtcTicketRootItem[];
  supplementEvidences?: ApiEtcSupplementEvidence[];
  supplement_evidences?: ApiEtcSupplementEvidence[];
  reconciledItems?: ApiEtcReconciledItem[];
  reconciled_items?: ApiEtcReconciledItem[];
  sourceFiles?: ApiEtcSourceFile[];
  source_files?: ApiEtcSourceFile[];
  parseIssues?: ApiEtcParseIssue[];
  parse_issues?: ApiEtcParseIssue[];
  importBlockers?: ApiEtcImportBlocker[];
  import_blockers?: ApiEtcImportBlocker[];
};

type ApiEtcImportBlocker = {
  code?: string;
  message?: string;
};

type ApiEtcReconciledItem = {
  itemId?: string;
  item_id?: string;
  creditCardItemId?: string;
  credit_card_item_id?: string;
  ticketRootItemIds?: string[];
  ticket_root_item_ids?: string[];
  supplementEvidenceIds?: string[];
  supplement_evidence_ids?: string[];
  resolution?: string;
  note?: string | null;
  claimAmount?: string | number | null;
  claim_amount?: string | number | null;
  evidenceAmount?: string | number | null;
  evidence_amount?: string | number | null;
  amountDelta?: string | number | null;
  amount_delta?: string | number | null;
  amountDeltaNote?: string | null;
  amount_delta_note?: string | null;
};

type ApiEtcCreditCardItem = {
  itemId?: string;
  item_id?: string;
  transactionDate?: string;
  transaction_date?: string;
  postingDate?: string;
  posting_date?: string;
  cardLast4?: string;
  card_last4?: string;
  description?: string;
  amount?: string | number | null;
  settlementAmount?: string | number | null;
  settlement_amount?: string | number | null;
  isEtcCandidate?: boolean | null;
  is_etc_candidate?: boolean | null;
  candidateReason?: string | null;
  candidate_reason?: string | null;
  recommendationStatus?: string;
  recommendation_status?: string;
  manualResolution?: string;
  manual_resolution?: string;
  manualResolutionReason?: string | null;
  manual_resolution_reason?: string | null;
  reviewNote?: string | null;
  review_note?: string | null;
};

type ApiEtcTicketRootItem = {
  itemId?: string;
  item_id?: string;
  sourceFileId?: string;
  source_file_id?: string;
  ticketFileId?: string;
  ticket_file_id?: string;
  vehiclePlate?: string;
  vehicle_plate?: string;
  transactionAt?: string;
  transaction_at?: string;
  amount?: string | number | null;
  entryStation?: string;
  entry_station?: string;
  exitStation?: string;
  exit_station?: string;
  invoiceCount?: number | null;
  invoice_count?: number | null;
  recommendationStatus?: string;
  recommendation_status?: string;
  linkedCreditCardItemIds?: string[];
  linked_credit_card_item_ids?: string[];
};

type ApiEtcSupplementEvidence = {
  evidenceId?: string;
  evidence_id?: string;
  sourceName?: string;
  source_name?: string;
  evidenceKind?: string;
  evidence_kind?: string;
  amount?: string | number | null;
  paidAt?: string | null;
  paid_at?: string | null;
  merchantName?: string | null;
  merchant_name?: string | null;
  tags?: string[];
  includeInEtcZipCheck?: boolean | null;
  include_in_etc_zip_check?: boolean | null;
  includeInOaSubmission?: boolean | null;
  include_in_oa_submission?: boolean | null;
  includeInWorkbench?: boolean | null;
  include_in_workbench?: boolean | null;
};

type ApiEtcParseIssue = {
  issueId?: string;
  issue_id?: string;
  fileId?: string | null;
  file_id?: string | null;
  sourceKind?: string | null;
  source_kind?: string | null;
  originalName?: string | null;
  original_name?: string | null;
  severity?: string;
  message?: string;
  sourcePage?: number | null;
  source_page?: number | null;
  sourceLine?: number | null;
  source_line?: number | null;
  extractionMethod?: string | null;
  extraction_method?: string | null;
  fieldName?: string | null;
  field_name?: string | null;
};

type ApiEtcSourceFile = {
  fileId?: string;
  file_id?: string;
  sourceKind?: string;
  source_kind?: string;
  originalName?: string;
  original_name?: string;
  contentType?: string;
  content_type?: string;
  hasBlockingIssue?: boolean | null;
  has_blocking_issue?: boolean | null;
};

type ApiEtcReconciliationTasksPayload = {
  tasks?: ApiEtcReconciliationTask[];
  unavailableTasks?: ApiEtcReconciliationTask[];
  unavailable_tasks?: ApiEtcReconciliationTask[];
};

type EtcRequestInit = RequestInit & {
  timeoutMs?: number;
};

export class EtcApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(message: string, options: { status: number; code?: string; details?: unknown }) {
    super(message);
    this.name = "EtcApiError";
    this.status = options.status;
    this.code = options.code ?? "";
    this.details = options.details;
  }
}

const DEFAULT_ETC_REQUEST_TIMEOUT_MS = 60_000;
const FAST_ETC_MUTATION_TIMEOUT_MS = 15_000;

function withAuthHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

function uniqueUrls(urls: string[]) {
  return urls.filter((url, index) => urls.indexOf(url) === index);
}

function requestUrlCandidates(path: string) {
  const trimmed = String(path).trim();
  const primaryUrl = apiUrl(trimmed);
  if (/^https?:\/\//i.test(trimmed)) {
    return [primaryUrl];
  }
  const withLeadingSlash = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  if (withLeadingSlash.startsWith("/api/") || withLeadingSlash.startsWith("/imports/")) {
    return uniqueUrls([primaryUrl, withLeadingSlash, `/fin-ops-api${withLeadingSlash}`]);
  }
  return [primaryUrl];
}

function htmlResponseError(url: string, response: Response, body: string) {
  const snippet = body.replace(/\s+/g, " ").slice(0, 120);
  return new Error(`ETC 接口返回了 HTML 页面：${response.status} ${url}。请检查 fin-ops 后端代理路径或服务器部署配置。${snippet ? ` 响应片段：${snippet}` : ""}`);
}

function responseError(response: Response, code: string, message: string, details?: unknown) {
  return new EtcApiError(message, { status: response.status, code, details });
}

function requestTimeoutSignal(parentSignal: AbortSignal | null | undefined, timeoutMs: number) {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const abortFromParent = () => {
    controller.abort(parentSignal?.reason);
  };
  if (parentSignal?.aborted) {
    abortFromParent();
  } else {
    parentSignal?.addEventListener("abort", abortFromParent, { once: true });
  }
  return {
    signal: controller.signal,
    get timedOut() {
      return timedOut;
    },
    cleanup() {
      window.clearTimeout(timeoutId);
      parentSignal?.removeEventListener("abort", abortFromParent);
    },
  };
}

async function requestJson<T>(url: string, init: EtcRequestInit = {}): Promise<T> {
  let lastHtmlError: Error | null = null;
  const candidates = requestUrlCandidates(url);
  const timeoutMs = Number.isFinite(init.timeoutMs) && Number(init.timeoutMs) > 0
    ? Number(init.timeoutMs)
    : DEFAULT_ETC_REQUEST_TIMEOUT_MS;
  const requestSignal = requestTimeoutSignal(init.signal, timeoutMs);
  const { timeoutMs: _timeoutMs, ...fetchInit } = init;
  try {
    for (const candidateUrl of candidates) {
      const response = await fetch(candidateUrl, {
        ...fetchInit,
        signal: requestSignal.signal,
        headers: withAuthHeaders(init.headers),
        credentials: init.credentials ?? "include",
      });
      const rawText = await response.text();
      const trimmedText = rawText.trim();
      let payload = {} as T;
      if (trimmedText.length > 0) {
        try {
          payload = JSON.parse(trimmedText) as T;
        } catch (error) {
          const contentType = response.headers.get("Content-Type") ?? "";
          const looksLikeHtml = trimmedText.startsWith("<") || contentType.toLowerCase().includes("text/html");
          if (looksLikeHtml) {
            lastHtmlError = htmlResponseError(candidateUrl, response, trimmedText);
            continue;
          }
          throw new Error("ETC 接口返回了无效 JSON。");
        }
      }
      if (!response.ok) {
        const errorPayload = payload as { message?: unknown; error?: unknown };
        const message = typeof errorPayload.message === "string" ? errorPayload.message : "";
        if (errorPayload.error === "preview_stale") {
          throw responseError(response, "preview_stale", "预览后数据已变化，请重新预览后再确认。");
        }
        if (errorPayload.error === "stale_reconciliation_task_preview") {
          throw responseError(response, "stale_reconciliation_task_preview", "对账任务已更新，请重新预览 ETC zip 后再确认导入。");
        }
        if (errorPayload.error && typeof errorPayload.error === "object" && "message" in errorPayload.error) {
          const envelope = errorPayload.error as { code?: unknown; message?: unknown; details?: unknown };
          const envelopeMessage = envelope.message;
          if (typeof envelopeMessage === "string" && envelopeMessage.trim()) {
            throw responseError(
              response,
              typeof envelope.code === "string" ? envelope.code : "",
              envelopeMessage,
              envelope.details,
            );
          }
        }
        if (message) {
          throw responseError(response, "", message);
        }
        if (typeof errorPayload.error === "string" && errorPayload.error.trim()) {
          throw responseError(response, errorPayload.error, errorPayload.error);
        }
        throw responseError(response, "", message || trimmedText || "ETC API request failed");
      }
      return payload;
    }
    if (lastHtmlError) {
      throw lastHtmlError;
    }
    throw new Error("ETC API request failed");
  } catch (error) {
    if (requestSignal.timedOut) {
      throw new Error("ETC API 请求超时，请确认后端服务状态后重试。");
    }
    throw error;
  } finally {
    requestSignal.cleanup();
  }
}

function unwrapEnvelope<T>(payload: T | ApiEnvelope<T>): T {
  if (payload && typeof payload === "object" && "ok" in payload && "data" in payload) {
    const envelope = payload as ApiEnvelope<T>;
    if (envelope.ok === false) {
      const error = envelope.error;
      if (error && typeof error === "object" && typeof error.message === "string") {
        throw new EtcApiError(error.message, {
          status: 0,
          code: typeof error.code === "string" ? error.code : "",
          details: error.details,
        });
      }
      if (typeof error === "string" && error.trim()) {
        throw new Error(error);
      }
      throw new Error("ETC API request failed");
    }
    return (envelope.data ?? {}) as T;
  }
  return payload as T;
}

function numberOrZero(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapAuditCounts(payload?: ApiEtcImportAuditCounts | null): ImportPreviewAuditCounts | undefined {
  if (!payload) {
    return undefined;
  }
  return {
    originalCount: numberOrZero(payload.original_count),
    uniqueCount: numberOrZero(payload.unique_count),
    duplicateCount: numberOrZero(payload.duplicate_count),
    duplicateInFileCount: numberOrZero(payload.duplicate_in_file_count),
    duplicateAcrossFilesCount: numberOrZero(payload.duplicate_across_files_count),
    existingDuplicateCount: numberOrZero(payload.existing_duplicate_count),
    importableCount: numberOrZero(payload.importable_count),
    updateCount: numberOrZero(payload.update_count),
    mergeCount: numberOrZero(payload.merge_count),
    suspectedDuplicateCount: numberOrZero(payload.suspected_duplicate_count),
    errorCount: numberOrZero(payload.error_count),
    confirmableCount: numberOrZero(payload.confirmable_count),
    skippedCount: numberOrZero(payload.skipped_count),
  };
}

function normalizeMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "0.00";
  }
  return String(value);
}

function mapInvoice(invoice: ApiEtcInvoice): EtcInvoice {
  return {
    id: invoice.id,
    invoiceNumber: invoice.invoiceNumber ?? invoice.invoice_number ?? "",
    issueDate: invoice.issueDate ?? invoice.issue_date ?? "",
    passageStartDate: invoice.passageStartDate ?? invoice.passage_start_date ?? null,
    passageEndDate: invoice.passageEndDate ?? invoice.passage_end_date ?? null,
    plateNumber: invoice.plateNumber ?? invoice.plate_number ?? "",
    sellerName: invoice.sellerName ?? invoice.seller_name ?? "",
    buyerName: invoice.buyerName ?? invoice.buyer_name ?? "",
    amountWithoutTax: normalizeMoney(invoice.amountWithoutTax ?? invoice.amount_without_tax),
    taxAmount: normalizeMoney(invoice.taxAmount ?? invoice.tax_amount),
    totalAmount: normalizeMoney(invoice.totalAmount ?? invoice.total_amount),
    status: invoice.status,
    hasPdf: Boolean(invoice.hasPdf ?? invoice.has_pdf),
    hasXml: Boolean(invoice.hasXml ?? invoice.has_xml),
  };
}

function mapPlateSummary(input: ApiEtcBatch["plate_summary"] | ApiEtcBatch["plateSummary"]) {
  if (Array.isArray(input)) {
    return input.map((item) => ({
      plateNumber: item.plateNumber ?? item.plate_number ?? "",
      invoiceCount: item.invoiceCount ?? item.invoice_count ?? 0,
      totalAmount: normalizeMoney(item.totalAmount ?? item.total_amount),
    }));
  }
  if (input && typeof input === "object") {
    return Object.entries(input).map(([plateNumber, value]) => {
      if (value && typeof value === "object") {
        const item = value as ApiEtcPlateSummary;
        return {
          plateNumber,
          invoiceCount: item.invoiceCount ?? item.invoice_count ?? 0,
          totalAmount: normalizeMoney(item.totalAmount ?? item.total_amount),
        };
      }
      return {
        plateNumber,
        invoiceCount: 0,
        totalAmount: normalizeMoney(typeof value === "number" || typeof value === "string" ? value : undefined),
      };
    });
  }
  return [];
}

function mapBatchSummary(batch: ApiEtcBatch): EtcBatchSummary {
  const id = batch.id ?? batch.batchId ?? batch.batch_id ?? "";
  const etcBatchId = batch.etcBatchId ?? batch.etc_batch_id ?? batch.externalBatchId ?? batch.external_batch_id ?? id;
  const plateSummary = mapPlateSummary(batch.plateSummary ?? batch.plate_summary);
  return {
    id,
    etcBatchId,
    externalBatchId: batch.externalBatchId ?? batch.external_batch_id ?? etcBatchId,
    status: (batch.status ?? "unsubmitted") as EtcBatchStatus,
    sourceType: batch.sourceType ?? batch.source_type ?? "",
    invoiceCount: batch.invoiceCount ?? batch.invoice_count ?? 0,
    totalAmount: normalizeMoney(batch.totalAmount ?? batch.total_amount),
    taxAmount: normalizeMoney(batch.taxAmount ?? batch.tax_amount),
    issueStartDate: batch.issueStartDate ?? batch.issue_start_date ?? null,
    issueEndDate: batch.issueEndDate ?? batch.issue_end_date ?? null,
    passageStartDate: batch.passageStartDate ?? batch.passage_start_date ?? null,
    passageEndDate: batch.passageEndDate ?? batch.passage_end_date ?? null,
    plateCount: batch.plateCount ?? batch.plate_count ?? plateSummary.length,
    plateSummary,
    linkedOaRowId: batch.linkedOaRowId ?? batch.linked_oa_row_id ?? "",
    linkedOaCaseId: batch.linkedOaCaseId ?? batch.linked_oa_case_id ?? "",
    linkedOaApplicant: batch.linkedOaApplicant ?? batch.linked_oa_applicant ?? "",
    linkedOaApplyDate: batch.linkedOaApplyDate ?? batch.linked_oa_apply_date ?? "",
    linkedOaAmount: normalizeMoney(batch.linkedOaAmount ?? batch.linked_oa_amount),
    amountDelta: normalizeMoney(batch.amountDelta ?? batch.amount_delta),
    etcInvoiceCount: batch.etcInvoiceCount ?? batch.etc_invoice_count ?? batch.invoiceCount ?? batch.invoice_count ?? 0,
    supplementCount: batch.supplementCount ?? batch.supplement_count ?? 0,
    supplementAmount: normalizeMoney(batch.supplementAmount ?? batch.supplement_amount),
    displayCountText:
      batch.displayCountText
      ?? batch.display_count_text
      ?? `ETC票 ${batch.etcInvoiceCount ?? batch.etc_invoice_count ?? batch.invoiceCount ?? batch.invoice_count ?? 0} + 补充凭证 ${batch.supplementCount ?? batch.supplement_count ?? 0}`,
    note: batch.note ?? "",
  };
}

function mapBatchDetail(batch: ApiEtcBatch): EtcBatchDetail {
  const summary = batch.summary && typeof batch.summary === "object" ? batch.summary : {};
  const batchWithSummary = {
    ...batch,
    ...summary,
  };
  return {
    ...mapBatchSummary(batchWithSummary),
    invoiceItems: (batch.invoiceItems ?? batch.invoice_items ?? batch.items ?? []).map(mapInvoice),
  };
}

function stringArray(value: string[] | null | undefined): string[] {
  return Array.isArray(value) ? value.filter((item) => typeof item === "string" && item.trim()) : [];
}

function mapBusinessBatchImportAttempt(attempt: ApiEtcBusinessBatchImportAttempt): EtcBusinessBatchImportAttempt {
  return {
    attemptId: attempt.attemptId ?? attempt.attempt_id ?? "",
    importBatchId: attempt.importBatchId ?? attempt.import_batch_id ?? "",
    status: attempt.status ?? "",
    imported: attempt.imported ?? 0,
    duplicatesSkipped: attempt.duplicatesSkipped ?? attempt.duplicates_skipped ?? 0,
    attachmentsCompleted: attempt.attachmentsCompleted ?? attempt.attachments_completed ?? 0,
    failed: attempt.failed ?? 0,
    createdAt: attempt.createdAt ?? attempt.created_at ?? "",
  };
}

function mapBusinessBatchAuditEvent(event: ApiEtcBusinessBatchAuditEvent): EtcBusinessBatchAuditEvent {
  return {
    eventId: event.eventId ?? event.event_id ?? "",
    eventType: event.eventType ?? event.event_type ?? "",
    beforeStatus: event.beforeStatus ?? event.before_status ?? "",
    afterStatus: event.afterStatus ?? event.after_status ?? "",
    reason: event.reason ?? "",
    createdAt: event.createdAt ?? event.created_at ?? "",
  };
}

function mapBusinessBatchSummary(batch: ApiEtcBusinessBatch): EtcBusinessBatchSummary {
  const legacySummary = mapBatchSummary(batch);
  const invoiceSummary = batch.invoiceSummary ?? batch.invoice_summary;
  const businessBatchId = batch.businessBatchId ?? batch.business_batch_id ?? batch.id ?? batch.batchId ?? batch.batch_id ?? "";
  const externalEtcBatchId =
    batch.externalEtcBatchId
    ?? batch.external_etc_batch_id
    ?? batch.externalBatchId
    ?? batch.external_batch_id
    ?? batch.etcBatchId
    ?? batch.etc_batch_id
    ?? legacySummary.externalBatchId
    ?? "";
  return {
    businessBatchId,
    taskId: batch.taskId ?? batch.task_id ?? "",
    status: (batch.status ?? "draft") as EtcBusinessBatchStatus,
    version: batch.version ?? 0,
    ownerUserId: batch.ownerUserId ?? batch.owner_user_id ?? "",
    ownerOrgId: batch.ownerOrgId ?? batch.owner_org_id ?? "",
    importBatchIds: stringArray(batch.importBatchIds ?? batch.import_batch_ids),
    submissionBatchId: batch.submissionBatchId ?? batch.submission_batch_id ?? "",
    externalEtcBatchId,
    oaDraftId: batch.oaDraftId ?? batch.oa_draft_id ?? "",
    oaDraftUrl: batch.oaDraftUrl ?? batch.oa_draft_url ?? "",
    oaRowId: batch.oaRowId ?? batch.oa_row_id ?? batch.linkedOaRowId ?? batch.linked_oa_row_id ?? "",
    oaProcessStatus: batch.oaProcessStatus ?? batch.oa_process_status ?? "",
    oaDetectionStatus: batch.oaDetectionStatus ?? batch.oa_detection_status ?? "",
    oaDetectionReason: batch.oaDetectionReason ?? batch.oa_detection_reason ?? "",
    oaDetectionError: batch.oaDetectionError ?? batch.oa_detection_error ?? "",
    oaDetectionStartedAt: batch.oaDetectionStartedAt ?? batch.oa_detection_started_at ?? "",
    oaDetectionNextRunAt: batch.oaDetectionNextRunAt ?? batch.oa_detection_next_run_at ?? "",
    oaDetectionDeadlineAt: batch.oaDetectionDeadlineAt ?? batch.oa_detection_deadline_at ?? "",
    oaDetectionFinalRetryUntil: batch.oaDetectionFinalRetryUntil ?? batch.oa_detection_final_retry_until ?? "",
    oaDetectionAttempts: batch.oaDetectionAttempts ?? batch.oa_detection_attempts ?? 0,
    invoiceSummary: {
      count: invoiceSummary?.count ?? batch.invoiceCount ?? batch.invoice_count ?? 0,
      amount: normalizeMoney(invoiceSummary?.amount ?? batch.totalAmount ?? batch.total_amount),
    },
    invoiceIds: stringArray(batch.invoiceIds ?? batch.invoice_ids),
    importAttempts: (batch.importAttempts ?? batch.import_attempts ?? []).map(mapBusinessBatchImportAttempt),
    auditEvents: (batch.auditEvents ?? batch.audit_events ?? []).map(mapBusinessBatchAuditEvent),
    createdAt: batch.createdAt ?? batch.created_at ?? "",
    updatedAt: batch.updatedAt ?? batch.updated_at ?? "",
  };
}

function mapBusinessBatchDetail(batch: ApiEtcBusinessBatch): EtcBusinessBatchDetail {
  const summary = batch.summary && typeof batch.summary === "object" ? batch.summary : {};
  const batchWithSummary = {
    ...batch,
    ...summary,
  };
  return {
    ...mapBusinessBatchSummary(batchWithSummary),
    invoiceItems: (batch.invoiceItems ?? batch.invoice_items ?? batch.items ?? []).map(mapInvoice),
  };
}

function unwrapBusinessBatchPayload(payload: ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>): ApiEtcBusinessBatch {
  const unwrapped = unwrapEnvelope<ApiEtcBusinessBatchSinglePayload>(payload);
  if (unwrapped && typeof unwrapped === "object") {
    const record = unwrapped as {
      businessBatch?: ApiEtcBusinessBatch | null;
      item?: ApiEtcBusinessBatch | null;
      detail?: ApiEtcBusinessBatch | null;
    };
    return record.businessBatch ?? record.item ?? record.detail ?? (unwrapped as ApiEtcBusinessBatch);
  }
  return {} as ApiEtcBusinessBatch;
}

function mapEtcImportItem(item: ApiEtcImportItem): EtcImportItem {
  const mapped: EtcImportItem = {
    invoiceNumber: item.invoiceNumber ?? item.invoice_number ?? "",
    fileName: item.fileName ?? item.file_name ?? "",
    status: item.status ?? "",
    reason: item.reason ?? item.message ?? "",
  };
  const filterStatus = item.filterStatus ?? item.filter_status;
  if (filterStatus) {
    mapped.filterStatus = filterStatus;
  }
  const requirementId = item.requirementId ?? item.requirement_id;
  if (requirementId) {
    mapped.requirementId = requirementId;
  }
  return mapped;
}

function mapEtcReconciliationBlockingIssue(issue: ApiEtcReconciliationBlockingIssue): EtcReconciliationBlockingIssue {
  return {
    error: issue.error ?? "",
    requirementId: issue.requirementId ?? issue.requirement_id ?? "",
    transactionAt: issue.transactionAt ?? issue.transaction_at ?? "",
    transactionDate: issue.transactionDate ?? issue.transaction_date ?? "",
    amount: stringOrEmpty(issue.amount),
    vehiclePlate: issue.vehiclePlate ?? issue.vehicle_plate ?? null,
    invoiceCount: issue.invoiceCount ?? issue.invoice_count ?? null,
    dateWindowStart: issue.dateWindowStart ?? issue.date_window_start ?? "",
    dateWindowEnd: issue.dateWindowEnd ?? issue.date_window_end ?? "",
  };
}

function mapEtcReconciliationFilter(payload?: ApiEtcReconciliationFilterPreview | null): EtcReconciliationFilterPreview | undefined {
  if (!payload) {
    return undefined;
  }
  return {
    taskId: payload.taskId ?? payload.task_id ?? "",
    taskVersion: payload.taskVersion ?? payload.task_version ?? 0,
    confirmedItemSetHash: payload.confirmedItemSetHash ?? payload.confirmed_item_set_hash ?? "",
    allowedInvoiceNumbers: payload.allowedInvoiceNumbers ?? payload.allowed_invoice_numbers ?? [],
    blockingIssues: (payload.blockingIssues ?? payload.blocking_issues ?? []).map(mapEtcReconciliationBlockingIssue),
  };
}

function mapEtcImportResult(payload: ApiEtcImportSummary): EtcImportPreviewResult {
  const summary = payload.summary ?? {};
  const audit = mapAuditCounts(payload.audit);
  const importAudit = mapAuditCounts(payload.importAudit ?? payload.import_audit);
  const reconciliationFilter = mapEtcReconciliationFilter(payload.reconciliationFilter ?? payload.reconciliation_filter);
  return {
    sessionId: payload.sessionId ?? payload.session_id ?? "",
    imported: payload.imported ?? summary.imported ?? 0,
    duplicatesSkipped: payload.duplicatesSkipped ?? payload.duplicates_skipped ?? summary.duplicatesSkipped ?? summary.duplicates_skipped ?? 0,
    attachmentsCompleted:
      payload.attachmentsCompleted
      ?? payload.attachments_completed
      ?? summary.attachmentsCompleted
      ?? summary.attachments_completed
      ?? 0,
    failed: payload.failed ?? summary.failed ?? 0,
    ...(audit ? { audit } : {}),
    ...(importAudit ? { importAudit } : {}),
    ...(reconciliationFilter ? { reconciliationFilter } : {}),
    items: (payload.items ?? []).map(mapEtcImportItem),
  };
}

function mapEtcImportConfirmResult(payload: ApiEtcImportSummary): EtcImportConfirmResult {
  return {
    ...mapEtcImportResult(payload),
    ...(payload.job ? { job: mapBackgroundJob(payload.job) } : {}),
  };
}

function stringOrEmpty(value: string | number | null | undefined) {
  return value === null || value === undefined ? "" : String(value);
}

function mapEtcReconciliationTaskSummary(task: ApiEtcReconciliationTask): EtcReconciliationTaskSummary {
  return {
    taskId: task.taskId ?? task.task_id ?? "",
    status: (task.status ?? "draft") as EtcReconciliationTaskSummary["status"],
    version: task.version ?? 0,
    title: task.title ?? "",
    periodStart: task.periodStart ?? task.period_start ?? null,
    periodEnd: task.periodEnd ?? task.period_end ?? null,
    oaTotalAmount: stringOrEmpty(task.oaTotalAmount ?? task.oa_total_amount),
    etcInvoiceCount: task.etcInvoiceCount ?? task.etc_invoice_count ?? 0,
    supplementCount: task.supplementCount ?? task.supplement_count ?? 0,
    vehiclePlates: task.vehiclePlates ?? task.vehicle_plates ?? [],
  };
}

function mapEtcUnavailableReconciliationTaskSummary(task: ApiEtcReconciliationTask): EtcUnavailableReconciliationTaskSummary {
  const importBlockers = task.importBlockers ?? task.import_blockers ?? [];
  return {
    ...mapEtcReconciliationTaskSummary(task),
    importBlockers: importBlockers.map((blocker) => ({
      code: blocker.code ?? "",
      message: blocker.message ?? "",
    })).filter((blocker) => blocker.code || blocker.message),
  };
}

function mapCreditCardItem(item: ApiEtcCreditCardItem) {
  return {
    itemId: item.itemId ?? item.item_id ?? "",
    transactionDate: item.transactionDate ?? item.transaction_date ?? "",
    postingDate: item.postingDate ?? item.posting_date ?? "",
    cardLast4: item.cardLast4 ?? item.card_last4 ?? "",
    description: item.description ?? "",
    amount: normalizeMoney(item.amount),
    settlementAmount: normalizeMoney(item.settlementAmount ?? item.settlement_amount),
    isEtcCandidate: Boolean(item.isEtcCandidate ?? item.is_etc_candidate),
    candidateReason: item.candidateReason ?? item.candidate_reason ?? "",
    recommendationStatus: item.recommendationStatus ?? item.recommendation_status ?? "not_candidate",
    manualResolution: item.manualResolution ?? item.manual_resolution ?? "unresolved",
    manualResolutionReason: item.manualResolutionReason ?? item.manual_resolution_reason ?? "",
    reviewNote: item.reviewNote ?? item.review_note ?? "",
  };
}

function mapTicketRootItem(item: ApiEtcTicketRootItem) {
  return {
    itemId: item.itemId ?? item.item_id ?? "",
    sourceFileId: item.sourceFileId ?? item.source_file_id ?? item.ticketFileId ?? item.ticket_file_id ?? "",
    vehiclePlate: item.vehiclePlate ?? item.vehicle_plate ?? "",
    transactionAt: item.transactionAt ?? item.transaction_at ?? "",
    amount: normalizeMoney(item.amount),
    entryStation: item.entryStation ?? item.entry_station ?? "",
    exitStation: item.exitStation ?? item.exit_station ?? "",
    invoiceCount: item.invoiceCount ?? item.invoice_count ?? 0,
    recommendationStatus: item.recommendationStatus ?? item.recommendation_status ?? "unmatched",
    linkedCreditCardItemIds: item.linkedCreditCardItemIds ?? item.linked_credit_card_item_ids ?? [],
  };
}

function mapSupplementEvidence(item: ApiEtcSupplementEvidence) {
  return {
    evidenceId: item.evidenceId ?? item.evidence_id ?? "",
    sourceName: item.sourceName ?? item.source_name ?? "",
    evidenceKind: item.evidenceKind ?? item.evidence_kind ?? "",
    amount: normalizeMoney(item.amount),
    paidAt: item.paidAt ?? item.paid_at ?? "",
    merchantName: item.merchantName ?? item.merchant_name ?? "",
    tags: item.tags ?? [],
    includeInEtcZipCheck: Boolean(item.includeInEtcZipCheck ?? item.include_in_etc_zip_check),
    includeInOaSubmission: item.includeInOaSubmission ?? item.include_in_oa_submission ?? true,
    includeInWorkbench: item.includeInWorkbench ?? item.include_in_workbench ?? true,
  };
}

function mapReconciledItem(item: ApiEtcReconciledItem) {
  return {
    itemId: item.itemId ?? item.item_id ?? "",
    creditCardItemId: item.creditCardItemId ?? item.credit_card_item_id ?? "",
    ticketRootItemIds: item.ticketRootItemIds ?? item.ticket_root_item_ids ?? [],
    supplementEvidenceIds: item.supplementEvidenceIds ?? item.supplement_evidence_ids ?? [],
    resolution: item.resolution ?? "",
    note: item.note ?? "",
    claimAmount: normalizeMoney(item.claimAmount ?? item.claim_amount),
    evidenceAmount: normalizeMoney(item.evidenceAmount ?? item.evidence_amount),
    amountDelta: normalizeMoney(item.amountDelta ?? item.amount_delta),
    amountDeltaNote: item.amountDeltaNote ?? item.amount_delta_note ?? "",
  };
}

function mapSourceFile(file: ApiEtcSourceFile): EtcSourceFile {
  return {
    fileId: file.fileId ?? file.file_id ?? "",
    sourceKind: file.sourceKind ?? file.source_kind ?? "",
    originalName: file.originalName ?? file.original_name ?? "",
    contentType: file.contentType ?? file.content_type ?? "",
    hasBlockingIssue: Boolean(file.hasBlockingIssue ?? file.has_blocking_issue),
  };
}

function mapParseIssue(issue: ApiEtcParseIssue) {
  return {
    issueId: issue.issueId ?? issue.issue_id ?? "",
    fileId: issue.fileId ?? issue.file_id ?? "",
    sourceKind: issue.sourceKind ?? issue.source_kind ?? "",
    originalName: issue.originalName ?? issue.original_name ?? "",
    severity: issue.severity ?? "warning",
    message: issue.message ?? "",
    sourcePage: issue.sourcePage ?? issue.source_page ?? null,
    sourceLine: issue.sourceLine ?? issue.source_line ?? null,
    extractionMethod: issue.extractionMethod ?? issue.extraction_method ?? "",
    fieldName: issue.fieldName ?? issue.field_name ?? "",
  };
}

function mapEtcReconciliationTask(task: ApiEtcReconciliationTask): EtcReconciliationTask {
  return {
    ...mapEtcReconciliationTaskSummary(task),
    statementPeriodStart: task.statementPeriodStart ?? task.statement_period_start ?? null,
    statementPeriodEnd: task.statementPeriodEnd ?? task.statement_period_end ?? null,
    approvedDelta: stringOrEmpty(task.approvedDelta ?? task.approved_delta),
    approvedDeltaNote: task.approvedDeltaNote ?? task.approved_delta_note ?? "",
    cardLast4: task.cardLast4 ?? task.card_last4 ?? "",
    etcInvoiceAmount: normalizeMoney(task.etcInvoiceAmount ?? task.etc_invoice_amount),
    supplementAmount: normalizeMoney(task.supplementAmount ?? task.supplement_amount),
    canConfirm: Boolean(task.canConfirm ?? task.can_confirm ?? task.confirmable),
    confirmedItemSetHash: task.confirmedItemSetHash ?? task.confirmed_item_set_hash ?? "",
    importBatchId: task.importBatchId ?? task.import_batch_id ?? "",
    etcBatchId: task.etcBatchId ?? task.etc_batch_id ?? "",
    hasImportedInvoices: Boolean(task.hasImportedInvoices ?? task.has_imported_invoices),
    importedInvoiceCount: task.importedInvoiceCount ?? task.imported_invoice_count ?? 0,
    importedInvoiceAmount: normalizeMoney(task.importedInvoiceAmount ?? task.imported_invoice_amount),
    oaDraftBatchId: task.oaDraftBatchId ?? task.oa_draft_batch_id ?? "",
    oaDraftStatus: task.oaDraftStatus ?? task.oa_draft_status ?? "",
    submittedConfirmedAt: task.submittedConfirmedAt ?? task.submitted_confirmed_at ?? "",
    creditCardItems: (task.creditCardItems ?? task.credit_card_items ?? []).map(mapCreditCardItem),
    ticketRootItems: (task.ticketRootItems ?? task.ticket_root_items ?? []).map(mapTicketRootItem),
    supplementEvidences: (task.supplementEvidences ?? task.supplement_evidences ?? []).map(mapSupplementEvidence),
    reconciledItems: (task.reconciledItems ?? task.reconciled_items ?? []).map(mapReconciledItem),
    sourceFiles: (task.sourceFiles ?? task.source_files ?? []).map(mapSourceFile),
    parseIssues: (task.parseIssues ?? task.parse_issues ?? []).map(mapParseIssue),
  };
}

export async function fetchReadyEtcReconciliationTasks(signal?: AbortSignal): Promise<EtcReadyReconciliationTasksPayload> {
  const payload = await requestJson<ApiEtcReconciliationTasksPayload>("/api/etc/reconciliation-tasks/ready-for-import", {
    method: "GET",
    signal,
  });
  return {
    items: (payload.tasks ?? []).map(mapEtcReconciliationTaskSummary),
    unavailableItems: (payload.unavailableTasks ?? payload.unavailable_tasks ?? []).map(mapEtcUnavailableReconciliationTaskSummary),
  };
}

export async function fetchEtcReconciliationTasks(signal?: AbortSignal): Promise<EtcReconciliationTaskListPayload> {
  const payload = await requestJson<ApiEtcReconciliationTasksPayload>("/api/etc/reconciliation-tasks", {
    method: "GET",
    signal,
    timeoutMs: 15_000,
  });
  return {
    items: (payload.tasks ?? []).map(mapEtcReconciliationTask),
  };
}

export async function createEtcReconciliationTask(payload: { title?: string } = {}): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>("/api/etc/reconciliation-tasks", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title: payload.title ?? "" }),
  });
  return mapEtcReconciliationTask(task);
}

export async function fetchEtcReconciliationTask(taskId: string, signal?: AbortSignal): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(`/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}`, {
    method: "GET",
    signal,
  });
  return mapEtcReconciliationTask(task);
}

export async function refreshEtcReconciliationMatches(taskId: string): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/refresh-matches`,
    {
      method: "POST",
    },
  );
  return mapEtcReconciliationTask(task);
}

function reconciliationUploadFormData(files: File[], expectedVersion: number, extra?: Record<string, string>) {
  const formData = new FormData();
  formData.append("expectedVersion", String(expectedVersion));
  files.forEach((file) => formData.append("files", file));
  Object.entries(extra ?? {}).forEach(([key, value]) => {
    if (value) {
      formData.append(key, value);
    }
  });
  return formData;
}

async function uploadEtcReconciliationFiles(
  taskId: string,
  endpoint: string,
  files: File[],
  expectedVersion: number,
  extra?: Record<string, string>,
) {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/${endpoint}`,
    {
      method: "POST",
      body: reconciliationUploadFormData(files, expectedVersion, extra),
    },
  );
  return mapEtcReconciliationTask(task);
}

export async function uploadEtcCreditCardStatement(taskId: string, file: File, expectedVersion: number): Promise<EtcReconciliationTask> {
  return uploadEtcReconciliationFiles(taskId, "credit-card-statement", [file], expectedVersion);
}

export async function uploadEtcTicketRootFiles(taskId: string, files: File[], expectedVersion: number): Promise<EtcReconciliationTask> {
  return uploadEtcReconciliationFiles(taskId, "ticket-root-files", files, expectedVersion);
}

export async function uploadEtcTicketRootTexts(
  taskId: string,
  entries: EtcTicketRootTextEntry[],
  expectedVersion: number,
): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/ticket-root-texts`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expectedVersion, entries }),
    },
  );
  return mapEtcReconciliationTask(task);
}

export async function uploadEtcSupplementEvidences(
  taskId: string,
  files: File[],
  expectedVersion: number,
  options: { evidenceKind?: string } = {},
): Promise<EtcReconciliationTask> {
  return uploadEtcReconciliationFiles(
    taskId,
    "supplement-evidences",
    files,
    expectedVersion,
    options.evidenceKind ? { evidenceKind: options.evidenceKind } : undefined,
  );
}

export async function uploadEtcSupplementEvidenceForCard(
  taskId: string,
  cardItemId: string,
  files: File[],
  expectedVersion: number,
  options: { evidenceKind?: string; note?: string } = {},
): Promise<EtcReconciliationTask> {
  const extraFields: Record<string, string> = {};
  if (options.evidenceKind) {
    extraFields.evidenceKind = options.evidenceKind;
  }
  if (options.note) {
    extraFields.note = options.note;
  }
  return uploadEtcReconciliationFiles(
    taskId,
    `supplement-evidences/${encodeURIComponent(cardItemId)}`,
    files,
    expectedVersion,
    extraFields,
  );
}

export async function patchEtcReconciliationItem(
  taskId: string,
  itemId: string,
  expectedVersion: number,
  payload: EtcPatchReconciliationItemPayload,
): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/items/${encodeURIComponent(itemId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expectedVersion, ...payload }),
    },
  );
  return mapEtcReconciliationTask(task);
}

export async function confirmEtcReconciliationTask(
  taskId: string,
  expectedVersion: number,
  options: { confirmedCreditCardItemIds?: string[] } = {},
): Promise<EtcReconciliationTask> {
  const body: { expectedVersion: number; confirmedCreditCardItemIds?: string[] } = { expectedVersion };
  if (options.confirmedCreditCardItemIds) {
    body.confirmedCreditCardItemIds = options.confirmedCreditCardItemIds;
  }
  const task = await requestJson<ApiEtcReconciliationTask>(`/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/confirm`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  return mapEtcReconciliationTask(task);
}

export async function reopenEtcReconciliationTask(taskId: string, expectedVersion: number): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(`/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/reopen`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ expectedVersion }),
  });
  return mapEtcReconciliationTask(task);
}

export async function deleteEtcReconciliationTask(taskId: string, expectedVersion: number): Promise<void> {
  await requestJson(`/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ expectedVersion }),
    timeoutMs: FAST_ETC_MUTATION_TIMEOUT_MS,
  });
}

export async function deleteEtcReconciliationTaskImportedInvoices(
  taskId: string,
  expectedVersion: number,
): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/imported-invoices`,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expectedVersion }),
    },
  );
  return mapEtcReconciliationTask(task);
}

export async function deleteEtcReconciliationSourceFile(
  taskId: string,
  fileId: string,
  expectedVersion: number,
): Promise<EtcReconciliationTask> {
  const task = await requestJson<ApiEtcReconciliationTask>(
    `/api/etc/reconciliation-tasks/${encodeURIComponent(taskId)}/source-files/${encodeURIComponent(fileId)}`,
    {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ expectedVersion }),
    },
  );
  return mapEtcReconciliationTask(task);
}

export async function fetchEtcInvoices(query: EtcInvoiceQuery = {}): Promise<EtcInvoiceListPayload> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  if (query.month) {
    params.set("month", query.month);
  }
  if (query.plate) {
    params.set("plate", query.plate);
  }
  if (query.keyword) {
    params.set("keyword", query.keyword);
  }
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 100));

  const payload = await requestJson<ApiEtcInvoicePayload>(`/api/etc/invoices?${params.toString()}`, {
    method: "GET",
    signal: query.signal,
  });
  const items = (payload.items ?? []).map(mapInvoice);
  return {
    counts: {
      unsubmitted: payload.counts?.unsubmitted ?? 0,
      submitted: payload.counts?.submitted ?? 0,
    },
    items,
    pagination: {
      page: payload.pagination?.page ?? query.page ?? 1,
      pageSize: payload.pagination?.page_size ?? query.pageSize ?? 100,
      total: payload.pagination?.total ?? items.length,
    },
  };
}

export async function fetchEtcBusinessBatches(query: EtcBusinessBatchQuery = {}): Promise<EtcBusinessBatchListPayload> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  if (query.month) {
    params.set("month", query.month);
  }
  if (query.plate) {
    params.set("plate", query.plate);
  }
  if (query.keyword) {
    params.set("keyword", query.keyword);
  }
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 100));

  const rawPayload = await requestJson<ApiEtcBusinessBatchPayload | ApiEnvelope<ApiEtcBusinessBatchPayload>>(
    `/api/etc/business-batches?${params.toString()}`,
    {
      method: "GET",
      signal: query.signal,
    },
  );
  const payload = unwrapEnvelope<ApiEtcBusinessBatchPayload>(rawPayload);
  const items = (payload.items ?? payload.businessBatches ?? payload.business_batches ?? []).map(mapBusinessBatchSummary);
  return {
    counts: {
      active: payload.counts?.active ?? payload.counts?.unsubmitted ?? 0,
      submitted: payload.counts?.submitted ?? 0,
    },
    items,
    pagination: {
      page: payload.pagination?.page ?? query.page ?? 1,
      pageSize: payload.pagination?.pageSize ?? payload.pagination?.page_size ?? query.pageSize ?? 100,
      total: payload.pagination?.total ?? items.length,
    },
  };
}

export async function fetchEtcBusinessBatchDetail(businessBatchId: string, signal?: AbortSignal): Promise<EtcBusinessBatchDetail> {
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>(
    `/api/etc/business-batches/${encodeURIComponent(businessBatchId)}`,
    {
      method: "GET",
      signal,
    },
  );
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function createEtcBusinessBatch(payload: EtcCreateBusinessBatchPayload): Promise<EtcBusinessBatchDetail> {
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>("/api/etc/business-batches", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      taskId: payload.taskId,
      ...(payload.idempotencyKey ? { idempotencyKey: payload.idempotencyKey } : {}),
    }),
  });
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function createEtcBusinessBatchOaDraft(
  businessBatchId: string,
  payload: EtcBusinessBatchVersionedPayload = {},
): Promise<EtcBusinessBatchDetail> {
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>(
    `/api/etc/business-batches/${encodeURIComponent(businessBatchId)}/oa-draft`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...(payload.expectedVersion !== undefined ? { expectedVersion: payload.expectedVersion } : {}),
        ...(payload.idempotencyKey ? { idempotencyKey: payload.idempotencyKey } : {}),
      }),
    },
  );
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function revokeEtcBusinessBatchOaDraft(
  businessBatchId: string,
  payload: EtcBusinessBatchReasonedPayload,
): Promise<EtcBusinessBatchDetail> {
  const reason = payload.reason.trim();
  if (!reason) {
    throw new Error("撤销原因不能为空。");
  }
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>(
    `/api/etc/business-batches/${encodeURIComponent(businessBatchId)}/oa-draft/revoke`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...(payload.expectedVersion !== undefined ? { expectedVersion: payload.expectedVersion } : {}),
        reason,
        ...(payload.idempotencyKey ? { idempotencyKey: payload.idempotencyKey } : {}),
      }),
    },
  );
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function refreshEtcBusinessBatchOaStatus(
  businessBatchId: string,
  payload: Pick<EtcBusinessBatchVersionedPayload, "expectedVersion"> = {},
): Promise<EtcBusinessBatchDetail> {
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>(
    `/api/etc/business-batches/${encodeURIComponent(businessBatchId)}/oa-status/refresh`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ...(payload.expectedVersion !== undefined ? { expectedVersion: payload.expectedVersion } : {}),
      }),
    },
  );
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function manualEtcBusinessBatchOaStatus(
  businessBatchId: string,
  payload: EtcManualOaStatusPayload,
): Promise<EtcBusinessBatchDetail> {
  const reason = payload.reason.trim();
  if (!reason) {
    throw new Error("人工处理原因不能为空。");
  }
  const rawPayload = await requestJson<ApiEtcBusinessBatchSinglePayload | ApiEnvelope<ApiEtcBusinessBatchSinglePayload>>(
    `/api/etc/business-batches/${encodeURIComponent(businessBatchId)}/manual-oa-status`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        decision: payload.decision,
        ...(payload.expectedVersion !== undefined ? { expectedVersion: payload.expectedVersion } : {}),
        reason,
        ...(payload.candidateOaRowId ? { candidateOaRowId: payload.candidateOaRowId } : {}),
      }),
    },
  );
  return mapBusinessBatchDetail(unwrapBusinessBatchPayload(rawPayload));
}

export async function deleteEtcBusinessBatch(
  businessBatchId: string,
  payload: EtcBusinessBatchReasonedPayload,
): Promise<void> {
  const reason = payload.reason.trim();
  if (!reason) {
    throw new Error("删除原因不能为空。");
  }
  await requestJson<ApiEnvelope<unknown> | unknown>(`/api/etc/business-batches/${encodeURIComponent(businessBatchId)}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...(payload.expectedVersion !== undefined ? { expectedVersion: payload.expectedVersion } : {}),
      reason,
      ...(payload.idempotencyKey ? { idempotencyKey: payload.idempotencyKey } : {}),
    }),
  });
}

export async function fetchEtcBatches(query: EtcBatchQuery = {}): Promise<EtcBatchListPayload> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  if (query.month) {
    params.set("month", query.month);
  }
  if (query.plate) {
    params.set("plate", query.plate);
  }
  if (query.keyword) {
    params.set("keyword", query.keyword);
  }
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 100));

  const payload = await requestJson<ApiEtcBatchPayload>(`/api/etc/batches?${params.toString()}`, {
    method: "GET",
    signal: query.signal,
  });
  const items = (payload.items ?? payload.batches ?? []).map(mapBatchSummary);
  return {
    counts: {
      unsubmitted: payload.counts?.unsubmitted ?? 0,
      submitted: payload.counts?.submitted ?? 0,
    },
    items,
    pagination: {
      page: payload.pagination?.page ?? query.page ?? 1,
      pageSize: payload.pagination?.pageSize ?? payload.pagination?.page_size ?? query.pageSize ?? 100,
      total: payload.pagination?.total ?? items.length,
    },
  };
}

export async function fetchEtcBatchDetail(batchId: string, signal?: AbortSignal): Promise<EtcBatchDetail> {
  const payload = await requestJson<ApiEtcBatch | { item?: ApiEtcBatch; detail?: ApiEtcBatch }>(
    `/api/etc/batches/${encodeURIComponent(batchId)}`,
    {
      method: "GET",
      signal,
    },
  );
  const batch = "item" in payload || "detail" in payload
    ? (payload.item ?? payload.detail ?? {})
    : payload;
  return mapBatchDetail(batch as ApiEtcBatch);
}

export async function importEtcZipFiles(files: File[], taskId?: string): Promise<EtcImportSummary> {
  return previewEtcZipFiles(files, taskId);
}

export async function previewEtcZipFiles(files: File[], taskId?: string): Promise<EtcImportPreviewResult> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (taskId) {
    formData.append("task_id", taskId);
  }
  const payload = await requestJson<ApiEtcImportSummary>("/api/etc/import/preview", {
    method: "POST",
    body: formData,
  });
  return mapEtcImportResult(payload);
}

export async function confirmEtcImportSession(sessionId: string, taskId?: string): Promise<EtcImportConfirmResult> {
  const payload = await requestJson<ApiEtcImportSummary>("/api/etc/import/confirm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      sessionId,
      ...(taskId ? { taskId } : {}),
    }),
  });
  return mapEtcImportConfirmResult(payload);
}

export async function createEtcOaDraft(invoiceIds: string[]): Promise<EtcOaDraftPayload> {
  const payload = await requestJson<ApiEtcOaDraftPayload>("/api/etc/batches/draft", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ invoiceIds }),
  });
  return {
    batchId: payload.batchId ?? payload.batch_id ?? "",
    etcBatchId: payload.etcBatchId ?? payload.etc_batch_id ?? "",
    oaDraftId: payload.oaDraftId ?? payload.oa_draft_id ?? "",
    oaDraftUrl: payload.oaDraftUrl ?? payload.oa_draft_url ?? "",
  };
}

export async function createEtcOaDraftForBatch(batchId: string): Promise<EtcOaDraftPayload> {
  const payload = await requestJson<ApiEtcOaDraftPayload>(`/api/etc/batches/${encodeURIComponent(batchId)}/draft`, {
    method: "POST",
  });
  return {
    batchId: payload.batchId ?? payload.batch_id ?? batchId,
    etcBatchId: payload.etcBatchId ?? payload.etc_batch_id ?? "",
    oaDraftId: payload.oaDraftId ?? payload.oa_draft_id ?? "",
    oaDraftUrl: payload.oaDraftUrl ?? payload.oa_draft_url ?? "",
  };
}

export async function confirmEtcBatchSubmitted(batchId: string): Promise<void> {
  await requestJson(`/api/etc/batches/${encodeURIComponent(batchId)}/confirm-submitted`, {
    method: "POST",
  });
}

export async function markEtcBatchNotSubmitted(batchId: string): Promise<void> {
  await requestJson(`/api/etc/batches/${encodeURIComponent(batchId)}/mark-not-submitted`, {
    method: "POST",
  });
}

export async function deleteEtcBatch(batchId: string): Promise<void> {
  await requestJson(`/api/etc/batches/${encodeURIComponent(batchId)}`, {
    method: "DELETE",
  });
}

export async function revokeEtcSubmittedInvoices(invoiceIds: string[]): Promise<void> {
  await requestJson("/api/etc/invoices/revoke-submitted", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ invoiceIds }),
  });
}
