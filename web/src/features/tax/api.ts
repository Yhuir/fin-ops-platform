import { apiFetch, apiRequestJson } from "../apiClient";
import { formatMoney } from "../money";
import type { TaxCertificationQuery, TaxCertificationResult, TaxImportHistoryQuery, TaxImportHistory, TaxCertificationFilters, TaxImportCorrection,
  TaxCertifiedImportConfirmResult, TaxCertifiedImportConfirmedResult, TaxCertifiedImportJob,
  TaxCertifiedImportPreviewFile, TaxCertifiedImportPreviewResult, TaxCertifiedImportPreviewRow } from "./types";

export async function fetchTaxCertifications(query: TaxCertificationQuery, signal?: AbortSignal): Promise<TaxCertificationResult> {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => { if (value !== undefined && value !== "") params.set(key, String(value)); });
  const result = await apiRequestJson<TaxCertificationResult>(`/api/tax-offset?${params}`, { signal });
  const statistics = result.inventory_statistics;
  const fields = ["input_invoice_count", "special_invoice_count", "general_invoice_count", "toll_invoice_count",
    "other_invoice_count", "unclassified_invoice_count"] as const;
  if (!statistics || fields.some(field => !Number.isSafeInteger(statistics[field]) || statistics[field] < 0)
    || statistics.input_invoice_count !== statistics.special_invoice_count + statistics.general_invoice_count
      + statistics.toll_invoice_count + statistics.other_invoice_count + statistics.unclassified_invoice_count) {
    throw new Error("进项发票统计数据不完整或数量不一致，请重试。");
  }
  return result;
}

export async function exportTaxCertifications(filters: TaxCertificationFilters, fields: string[]) {
  const response = await apiFetch("/api/tax-offset/export", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filters, fields }),
  });
  if (!response.ok) {
    const payload = await response.json() as { message?: string; error?: { message?: string } };
    throw new Error(payload.error?.message ?? payload.message ?? "导出失败");
  }
  if (!response.headers.get("Content-Type")?.includes("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")) {
    throw new Error("导出文件格式错误");
  }
  return { blob: await response.blob(), fileName: "专票清单.xlsx" };
}

type ApiTaxCertifiedImportPreviewRow = {
  id: string;
  month: string | null;
  buyer_tax_no: string | null;
  row_status: TaxCertifiedImportPreviewRow["rowStatus"];
  match_status: TaxCertifiedImportPreviewRow["matchStatus"];
  unique_key: string | null;
  expected_version?: number | null;
  dedupe_status: TaxCertifiedImportPreviewRow["dedupeStatus"];
  error_message?: string | null;
  blocking: boolean;
  digital_invoice_no?: string | null;
  invoice_code?: string | null;
  invoice_no?: string | null;
  issue_date?: string | null;
  seller_tax_no?: string | null;
  seller_name?: string | null;
  tax_amount?: string | null;
  deductible_tax_amount?: string | null;
  selection_status?: string | null;
  invoice_status?: string | null;
  selection_time?: string | null;
  source_file_name: string;
  source_row_number: number;
};

type ApiTaxCertifiedImportPreviewFile = {
  id: string;
  file_name: string;
  month: string;
  recognized_count: number;
  invalid_count: number;
  ignored_count: number;
  matched_invoice_count: number;
  outside_invoices_count: number;
  conflict_count: number;
  duplicate_count: number;
  rows: ApiTaxCertifiedImportPreviewRow[];
};

type ApiTaxCertifiedImportPreviewPayload = {
  session: {
    id: string;
    imported_by: string;
    file_count: number;
    status: string;
  };
  files: ApiTaxCertifiedImportPreviewFile[];
  summary: {
    blocking_count: number;
    recognized_count: number;
    invalid_count: number;
  ignored_count: number;
    matched_invoice_count: number;
    outside_invoices_count: number;
    conflict_count: number;
    duplicate_count: number;
  };
};

type ApiTaxCertifiedImportBatch = {
  id: string;
  session_id: string;
  imported_by: string;
  file_count: number;
  months: string[];
  persisted_record_count: number;
};

type ApiTaxCertifiedImportJob = {
  import_job_id: string;
  tenant_id?: string;
  import_type: string;
  import_session_id?: string | null;
  source_file_id?: string | null;
  status: string;
  stage: string;
  priority?: string;
  attempt_count?: number;
  max_attempts?: number;
  last_error?: string | null;
  trace_id?: string | null;
  result_payload?: Record<string, unknown>;
};

type ApiTaxCertifiedImportConfirmPayload = {
  status: "queued";
  import_job: ApiTaxCertifiedImportJob;
};

type ApiTaxCertifiedImportJobPayload = {
  import_job: ApiTaxCertifiedImportJob;
};

function mapPreviewRow(row: ApiTaxCertifiedImportPreviewRow): TaxCertifiedImportPreviewRow {
  return {
    id: row.id,
    month: row.month,
    buyerTaxNo: row.buyer_tax_no,
    rowStatus: row.row_status,
    matchStatus: row.match_status,
    uniqueKey: row.unique_key,
    expectedVersion: row.expected_version ?? null,
    dedupeStatus: row.dedupe_status,
    errorMessage: row.error_message ?? null,
    blocking: row.blocking,
    digitalInvoiceNo: row.digital_invoice_no ?? null,
    invoiceCode: row.invoice_code ?? null,
    invoiceNo: row.invoice_no ?? null,
    issueDate: row.issue_date ?? null,
    sellerTaxNo: row.seller_tax_no ?? null,
    sellerName: row.seller_name ?? null,
    taxAmount: row.tax_amount == null ? null : formatMoney(row.tax_amount),
    deductibleTaxAmount: row.deductible_tax_amount == null ? null : formatMoney(row.deductible_tax_amount),
    selectionStatus: row.selection_status ?? null,
    invoiceStatus: row.invoice_status ?? null,
    selectionTime: row.selection_time ?? null,
    sourceFileName: row.source_file_name,
    sourceRowNumber: row.source_row_number,
  };
}

function mapPreviewFile(file: ApiTaxCertifiedImportPreviewFile): TaxCertifiedImportPreviewFile {
  return {
    id: file.id,
    fileName: file.file_name,
    month: file.month,
    recognizedCount: file.recognized_count,
    invalidCount: file.invalid_count,
    ignoredCount: file.ignored_count,
    matchedInvoiceCount: file.matched_invoice_count,
    outsideInvoicesCount: file.outside_invoices_count,
    conflictCount: file.conflict_count,
    duplicateCount: file.duplicate_count,
    rows: file.rows.map(mapPreviewRow),
  };
}

function mapCertifiedImportBatch(batch: ApiTaxCertifiedImportBatch): TaxCertifiedImportConfirmedResult {
  return {
    status: "confirmed",
    batchId: batch.id,
    sessionId: batch.session_id,
    importedBy: batch.imported_by,
    fileCount: batch.file_count,
    months: batch.months,
    persistedRecordCount: batch.persisted_record_count,
  };
}

function isApiTaxCertifiedImportBatch(value: unknown): value is ApiTaxCertifiedImportBatch {
  if (!value || typeof value !== "object") {
    return false;
  }
  const candidate = value as Partial<ApiTaxCertifiedImportBatch>;
  return (
    typeof candidate.id === "string"
    && typeof candidate.session_id === "string"
    && typeof candidate.imported_by === "string"
    && typeof candidate.file_count === "number"
    && Array.isArray(candidate.months)
    && candidate.months.every((item) => typeof item === "string")
    && typeof candidate.persisted_record_count === "number"
  );
}

function mapImportJob(job: ApiTaxCertifiedImportJob): TaxCertifiedImportJob {
  return {
    importJobId: job.import_job_id,
    tenantId: job.tenant_id,
    importType: job.import_type,
    importSessionId: job.import_session_id ?? null,
    sourceFileId: job.source_file_id ?? null,
    status: job.status,
    stage: job.stage,
    priority: job.priority,
    attemptCount: job.attempt_count,
    maxAttempts: job.max_attempts,
    lastError: job.last_error ?? null,
    traceId: job.trace_id ?? null,
    resultPayload: job.result_payload,
  };
}

export async function previewTaxCertifiedImport(params: {
  importedBy: string;
  files: File[];
  month?: string;
  buyerTaxNo?: string;
}): Promise<TaxCertifiedImportPreviewResult> {
  const formData = new FormData();
  formData.append("imported_by", params.importedBy);
  if (params.month) formData.append("month", params.month);
  if (params.buyerTaxNo) formData.append("buyer_tax_no", params.buyerTaxNo);
  for (const file of params.files) {
    formData.append("files", file);
  }
  const payload = await apiRequestJson<ApiTaxCertifiedImportPreviewPayload>("/api/tax-offset/certified-import/preview", {
    method: "POST",
    body: formData,
  });

  return {
    sessionId: payload.session.id,
    importedBy: payload.session.imported_by,
    fileCount: payload.session.file_count,
    status: payload.session.status,
    files: payload.files.map(mapPreviewFile),
    summary: {
      blockingCount: payload.summary.blocking_count,
      recognizedCount: payload.summary.recognized_count,
      invalidCount: payload.summary.invalid_count,
      ignoredCount: payload.summary.ignored_count,
      matchedInvoiceCount: payload.summary.matched_invoice_count,
      outsideInvoicesCount: payload.summary.outside_invoices_count,
      conflictCount: payload.summary.conflict_count,
      duplicateCount: payload.summary.duplicate_count,
    },
  };
}

export async function confirmTaxCertifiedImport(sessionId: string, corrections: TaxImportCorrection[] = []): Promise<TaxCertifiedImportConfirmResult> {
  const payload = await apiRequestJson<ApiTaxCertifiedImportConfirmPayload>("/api/tax-offset/certified-import/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      corrections,
    }),
  });

  if (payload.status !== "queued" || !payload.import_job) {
    throw new Error("认证导入未返回后台任务");
  }
  return { status: "queued", importJob: mapImportJob(payload.import_job) };
}

export async function fetchTaxCertifiedImportJob(importJobId: string): Promise<TaxCertifiedImportJob> {
  const payload = await apiRequestJson<ApiTaxCertifiedImportJobPayload>(
    `/api/tax-offset/certified-import/jobs/${encodeURIComponent(importJobId)}`,
    { method: "GET" },
  );
  return mapImportJob(payload.import_job);
}

export function taxCertifiedImportConfirmedFromJob(job: TaxCertifiedImportJob): TaxCertifiedImportConfirmedResult | null {
  const batch = job.resultPayload?.batch;
  if (!isApiTaxCertifiedImportBatch(batch)) {
    return null;
  }
  return mapCertifiedImportBatch(batch);
}

export async function fetchTaxCertifiedImportBatches(query: TaxImportHistoryQuery, signal?: AbortSignal): Promise<TaxImportHistory> {
  const params = new URLSearchParams(Object.entries(query).map(([key, value]) => [key, String(value)]));
  return apiRequestJson<TaxImportHistory>(`/api/tax-offset/certified-imports?${params}`, { signal });
}
export async function revokeTaxCertifiedImportBatch(id: string, expectedVersion: number) {
  return apiRequestJson(`/api/tax-offset/certified-imports/${encodeURIComponent(id)}/revoke`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ expected_version: expectedVersion }),
  });
}
