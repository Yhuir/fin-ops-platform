import type {
  ImportFilePreviewOverride,
  ImportBatchType,
  ImportPreviewAuditCounts,
  ImportPreviewDuplicateGroup,
  ImportSessionPayload,
  ImportTemplate,
  MatchingRunSummary,
} from "./types";
import { mapBackgroundJob, type ApiBackgroundJob } from "../backgroundJobs/api";
import { readOATokenCookie } from "../session/api";
import { apiUrl } from "../../app/runtime";

type ApiImportFile = {
  id: string;
  file_name: string;
  template_code?: string | null;
  batch_type?: "input_invoice" | "output_invoice" | "bank_transaction" | null;
  status: string;
  message: string;
  row_count: number;
  success_count: number;
  error_count: number;
  duplicate_count: number;
  suspected_duplicate_count: number;
  updated_count: number;
  audit?: ApiImportPreviewAuditCounts | null;
  preview_batch_id?: string | null;
  batch_id?: string | null;
  stored_file_path?: string | null;
  override_template_code?: string | null;
  override_batch_type?: "input_invoice" | "output_invoice" | "bank_transaction" | null;
  selected_bank_mapping_id?: string | null;
  selected_bank_name?: string | null;
  selected_bank_short_name?: string | null;
  selected_bank_last4?: string | null;
  detected_bank_name?: string | null;
  detected_last4?: string | null;
  bank_selection_conflict?: boolean;
  conflict_message?: string | null;
  row_results?: Array<{
    id: string;
    row_no: number;
    source_record_type: string;
    decision: "created" | "status_updated" | "duplicate_skipped" | "suspected_duplicate" | "error";
    decision_reason: string;
  }>;
};

type ApiImportPreviewAuditCounts = {
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

type ApiImportPreviewDuplicateGroup = {
  identity_key?: string;
  record_type?: string;
  duplicate_type?: string;
  rows?: Array<{
    file_id?: string;
    file_name?: string;
    row_no?: number;
  }>;
};

type ApiImportSessionPayload = {
  job?: ApiBackgroundJob;
  session: {
    id: string;
    imported_by: string;
    file_count: number;
    status: string;
    created_at: string;
    audit?: ApiImportPreviewAuditCounts | null;
  };
  files: ApiImportFile[];
  duplicate_groups?: ApiImportPreviewDuplicateGroup[];
  matching_run?: {
    id: string;
    triggered_by: string;
    result_count: number;
    automatic_count: number;
    suggested_count: number;
    manual_review_count: number;
  };
};

type ApiImportTemplatesPayload = {
  templates: Array<{
    template_code: string;
    label: string;
    file_extensions: string[];
    record_type: "invoice" | "bank_transaction";
    allowed_batch_types: Array<"input_invoice" | "output_invoice" | "bank_transaction">;
    required_headers: string[];
  }>;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(apiUrl(url), {
    ...init,
    headers,
    credentials: init.credentials ?? "include",
  });
  const payload = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(typeof payload === "object" && payload ? JSON.stringify(payload) : "request failed");
  }
  return payload;
}

export function resolveImportApiErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof Error)) {
    return fallback;
  }
  const raw = error.message?.trim();
  if (!raw) {
    return fallback;
  }
  try {
    const payload = JSON.parse(raw) as { error?: unknown; code?: unknown; message?: unknown };
    if (payload?.error === "preview_stale" || payload?.code === "preview_stale") {
      return "预览后数据已变化，请重新预览后再确认。";
    }
    if (typeof payload?.message === "string" && payload.message.trim()) {
      return payload.message.trim();
    }
  } catch {
    // Fall back to the raw Error message when the payload is not JSON.
  }
  return raw;
}

function numberOrZero(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapAuditCounts(payload?: ApiImportPreviewAuditCounts | null): ImportPreviewAuditCounts | undefined {
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

function mapDuplicateGroups(groups?: ApiImportPreviewDuplicateGroup[]): ImportPreviewDuplicateGroup[] {
  return (groups ?? []).map((group) => ({
    identityKey: group.identity_key ?? "",
    recordType: group.record_type ?? "",
    duplicateType: group.duplicate_type ?? "",
    rows: (group.rows ?? []).map((row) => ({
      fileId: row.file_id ?? "",
      fileName: row.file_name ?? "",
      rowNo: numberOrZero(row.row_no),
    })),
  }));
}

function mapMatchingRun(payload?: ApiImportSessionPayload["matching_run"]): MatchingRunSummary | undefined {
  if (!payload) {
    return undefined;
  }
  return {
    id: payload.id,
    triggeredBy: payload.triggered_by,
    resultCount: payload.result_count,
    automaticCount: payload.automatic_count,
    suggestedCount: payload.suggested_count,
    manualReviewCount: payload.manual_review_count,
  };
}

function mapImportPayload(payload: ApiImportSessionPayload): ImportSessionPayload {
  const sessionAudit = mapAuditCounts(payload.session.audit);
  return {
    session: {
      id: payload.session.id,
      importedBy: payload.session.imported_by,
      fileCount: payload.session.file_count,
      status: payload.session.status,
      createdAt: payload.session.created_at,
      ...(sessionAudit ? { audit: sessionAudit } : {}),
    },
    files: payload.files.map((file) => {
      const audit = mapAuditCounts(file.audit);
      return {
        id: file.id,
        fileName: file.file_name,
        templateCode: file.template_code,
        batchType: file.batch_type,
        status: file.status as ImportSessionPayload["files"][number]["status"],
        message: file.message,
        rowCount: file.row_count,
        successCount: file.success_count,
        errorCount: file.error_count,
        duplicateCount: file.duplicate_count,
        suspectedDuplicateCount: file.suspected_duplicate_count,
        updatedCount: file.updated_count,
        ...(audit ? { audit } : {}),
        previewBatchId: file.preview_batch_id,
        batchId: file.batch_id,
        storedFilePath: file.stored_file_path,
        overrideTemplateCode: file.override_template_code,
        overrideBatchType: file.override_batch_type,
        selectedBankMappingId: file.selected_bank_mapping_id,
        selectedBankName: file.selected_bank_name,
        selectedBankShortName: file.selected_bank_short_name,
        selectedBankLast4: file.selected_bank_last4,
        detectedBankName: file.detected_bank_name,
        detectedLast4: file.detected_last4,
        bankSelectionConflict: file.bank_selection_conflict ?? false,
        conflictMessage: file.conflict_message,
        rowResults: (file.row_results ?? []).map((row) => ({
          id: row.id,
          rowNo: row.row_no,
          sourceRecordType: row.source_record_type,
          decision: row.decision,
          decisionReason: row.decision_reason,
        })),
      };
    }),
    duplicateGroups: mapDuplicateGroups(payload.duplicate_groups),
    matchingRun: mapMatchingRun(payload.matching_run),
    ...(payload.job ? { job: mapBackgroundJob(payload.job) } : {}),
  };
}

function mapImportTemplates(payload: ApiImportTemplatesPayload): ImportTemplate[] {
  return payload.templates.map((template) => ({
    templateCode: template.template_code,
    label: template.label,
    fileExtensions: template.file_extensions,
    recordType: template.record_type,
    allowedBatchTypes: template.allowed_batch_types,
    requiredHeaders: template.required_headers,
  }));
}

export async function previewImportFiles(
  files: File[],
  importedBy = "web_finance_user",
  fileOverrides?: ImportFilePreviewOverride[],
): Promise<ImportSessionPayload> {
  const formData = new FormData();
  formData.append("imported_by", importedBy);
  files.forEach((file) => formData.append("files", file));
  if (fileOverrides && fileOverrides.length > 0) {
    formData.append(
      "file_overrides",
      JSON.stringify(
        fileOverrides.map((override, index) => ({
          file_name: override.fileName ?? files[index]?.name,
          ...(override.templateCode ? { template_code: override.templateCode } : {}),
          ...(override.batchType ? { batch_type: override.batchType } : {}),
          ...(override.bankMappingId ? { bank_mapping_id: override.bankMappingId } : {}),
          ...(override.bankName ? { bank_name: override.bankName } : {}),
          ...(override.bankShortName ? { bank_short_name: override.bankShortName } : {}),
          ...(override.last4 ? { last4: override.last4 } : {}),
        })),
      ),
    );
  }

  const payload = await requestJson<ApiImportSessionPayload>("/imports/files/preview", {
    method: "POST",
    body: formData,
  });
  return mapImportPayload(payload);
}

export async function retryImportFiles(
  sessionId: string,
  selectedFileIds: string[],
  overrides: Record<string, {
    templateCode?: string | null;
    batchType?: ImportBatchType | null;
    bankMappingId?: string | null;
    bankName?: string | null;
    bankShortName?: string | null;
    last4?: string | null;
  }>,
): Promise<ImportSessionPayload> {
  const payload = await requestJson<ApiImportSessionPayload>("/imports/files/retry", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      selected_file_ids: selectedFileIds,
      overrides: Object.fromEntries(
        Object.entries(overrides).map(([fileId, override]) => [
          fileId,
          {
            ...(override.templateCode ? { template_code: override.templateCode } : {}),
            ...(override.batchType ? { batch_type: override.batchType } : {}),
            ...(override.bankMappingId ? { bank_mapping_id: override.bankMappingId } : {}),
            ...(override.bankName ? { bank_name: override.bankName } : {}),
            ...(override.bankShortName ? { bank_short_name: override.bankShortName } : {}),
            ...(override.last4 ? { last4: override.last4 } : {}),
          },
        ]),
      ),
    }),
  });
  return mapImportPayload(payload);
}

export async function confirmImportFiles(
  sessionId: string,
  selectedFileIds: string[],
): Promise<ImportSessionPayload> {
  const payload = await requestJson<ApiImportSessionPayload>("/imports/files/confirm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: sessionId,
      selected_file_ids: selectedFileIds,
    }),
  });
  return mapImportPayload(payload);
}

export async function fetchImportSession(sessionId: string): Promise<ImportSessionPayload> {
  const payload = await requestJson<ApiImportSessionPayload>(`/imports/files/sessions/${sessionId}`, {
    method: "GET",
  });
  return mapImportPayload(payload);
}

export async function fetchImportTemplates(): Promise<ImportTemplate[]> {
  const payload = await requestJson<ApiImportTemplatesPayload>("/imports/templates", {
    method: "GET",
  });
  return mapImportTemplates(payload);
}

export async function revertImportBatch(batchId: string): Promise<void> {
  await requestJson<{ batch: { id: string; status: string } }>(`/imports/batches/${batchId}/revert`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
}
