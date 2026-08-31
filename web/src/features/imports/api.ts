import type {
  ImportFilePreviewOverride,
  ActiveImportSession,
  ImportBatchType,
  ImportPreviewAuditCounts,
  ImportPreviewDuplicateGroup,
  ImportReviewRowsPage,
  ImportSessionPayload,
  ImportTemplate,
  ManualBankTransactionEntryBatchPreview,
  ManualBankTransactionEntryValues,
  ManualInvoiceEntryBatchPreview,
  ManualInvoiceEntryValues,
  MatchingRunSummary,
} from "./types";
import { mapBackgroundJob, type ApiBackgroundJob } from "../backgroundJobs/api";
import { ApiClientError, apiRequestJson } from "../apiClient";

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
  header_signature?: string | null;
  mapping_candidates?: Array<{ key: string; label: string }>;
  mapping_fields?: Array<{ key: string; label: string; selected?: string | null; required?: boolean }>;
  field_mapping?: Record<string, string>;
  mapping_source?: "auto" | "manual" | "saved" | null;
  duplicate_file_name?: string | null;
  source_control?: {
    status?: "not_applicable" | "unavailable" | "verified" | "mismatch";
    computed_row_count?: number;
    declared_row_count?: number | null;
    computed_debit_total?: string | null;
    declared_debit_total?: string | null;
    computed_credit_total?: string | null;
    declared_credit_total?: string | null;
    mismatch_fields?: string[];
  } | null;
  row_results?: Array<{
    id: string;
    row_no: number;
    source_record_type: string;
    decision: "created" | "status_updated" | "duplicate_skipped" | "suspected_duplicate" | "error";
    decision_reason: string;
    linked_object_type?: string | null;
    linked_object_id?: string | null;
    identity_kind?: string | null;
    account_no?: string | null;
    account?: string | null;
    trade_time?: string | null;
    pay_receive_time?: string | null;
    txn_date?: string | null;
    direction?: string | null;
    txn_direction?: string | null;
    amount?: string | number | null;
    counterparty_name?: string | null;
    counterparty_name_raw?: string | null;
    invoice_no?: string | null;
    invoice_date?: string | null;
    seller_name?: string | null;
    buyer_name?: string | null;
    tax_amount?: string | number | null;
    total_with_tax?: string | number | null;
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
    decision?: "created" | "status_updated" | "duplicate_skipped" | "suspected_duplicate" | "error" | string | null;
    decision_reason?: string | null;
    linked_object_type?: string | null;
    linked_object_id?: string | null;
    identity_kind?: string | null;
    account_no?: string | null;
    account?: string | null;
    trade_time?: string | null;
    pay_receive_time?: string | null;
    txn_date?: string | null;
    direction?: string | null;
    txn_direction?: string | null;
    amount?: string | number | null;
    counterparty_name?: string | null;
    counterparty_name_raw?: string | null;
    invoice_no?: string | null;
    invoice_date?: string | null;
    seller_name?: string | null;
    buyer_name?: string | null;
    tax_amount?: string | number | null;
    total_with_tax?: string | number | null;
  }>;
};

type ApiImportSessionPayload = {
  job?: ApiBackgroundJob;
  affected_scope_keys?: unknown;
  affectedScopeKeys?: unknown;
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

type ApiManualInvoiceEntryValues = {
  invoice_direction?: string;
  invoice_nature?: string;
  seller_name?: string;
  seller_tax_no?: string;
  buyer_name?: string;
  buyer_tax_no?: string;
  invoice_number?: string;
  invoice_code?: string;
  invoice_date?: string;
  net_amount?: string;
  tax_rate?: string;
  tax_amount?: string;
  total_with_tax?: string;
};

type ApiManualBankTransactionEntryValues = {
  bank_mapping_id?: string;
  bank_name?: string;
  bank_short_name?: string;
  last4?: string;
  account_no?: string;
  account_name?: string;
  direction?: string;
  amount?: string;
  balance?: string;
  trade_time?: string;
  currency?: string;
  counterparty_name?: string;
  counterparty_account_no?: string;
  counterparty_bank_name?: string;
  summary?: string;
  remark?: string;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  return apiRequestJson<T>(url, init);
}

export function resolveImportApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiClientError) {
    const payload = error.payload && typeof error.payload === "object"
      ? error.payload as { error?: unknown; code?: unknown; message?: unknown; requestId?: unknown }
      : null;
    if (error.code === "preview_stale" || payload?.error === "preview_stale" || payload?.code === "preview_stale") {
      return "预览后数据已变化，请重新预览后再确认。";
    }
    const message = typeof payload?.message === "string" && payload.message.trim()
      ? payload.message.trim()
      : error.message.trim() || fallback;
    const requestId = typeof payload?.requestId === "string" ? payload.requestId.trim() : "";
    return requestId ? `${message}（请求编号：${requestId}）` : message;
  }
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

function stringOrEmpty(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function mapPreviewDetailFields(row: {
  decision?: string | null;
  decision_reason?: string | null;
  linked_object_type?: string | null;
  linked_object_id?: string | null;
  identity_kind?: string | null;
  account_no?: string | null;
  account?: string | null;
  trade_time?: string | null;
  pay_receive_time?: string | null;
  txn_date?: string | null;
  direction?: string | null;
  txn_direction?: string | null;
  amount?: string | number | null;
  counterparty_name?: string | null;
  counterparty_name_raw?: string | null;
  invoice_no?: string | null;
  invoice_date?: string | null;
  seller_name?: string | null;
  buyer_name?: string | null;
  tax_amount?: string | number | null;
  total_with_tax?: string | number | null;
}) {
  return {
    decision: row.decision ?? null,
    decisionReason: row.decision_reason ?? null,
    linkedObjectType: row.linked_object_type ?? null,
    linkedObjectId: row.linked_object_id ?? null,
    identityKind: row.identity_kind ?? null,
    accountNo: row.account_no ?? row.account ?? null,
    tradeTime: row.trade_time ?? row.pay_receive_time ?? row.txn_date ?? null,
    direction: row.direction ?? row.txn_direction ?? null,
    amount: row.amount === null || row.amount === undefined ? null : stringOrEmpty(row.amount),
    counterpartyName: row.counterparty_name ?? row.counterparty_name_raw ?? null,
    invoiceNo: row.invoice_no ?? null,
    invoiceDate: row.invoice_date ?? null,
    sellerName: row.seller_name ?? null,
    buyerName: row.buyer_name ?? null,
    taxAmount: row.tax_amount === null || row.tax_amount === undefined ? null : stringOrEmpty(row.tax_amount),
    totalWithTax: row.total_with_tax === null || row.total_with_tax === undefined
      ? null
      : stringOrEmpty(row.total_with_tax),
  };
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
      ...mapPreviewDetailFields(row),
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
        headerSignature: file.header_signature,
        mappingCandidates: file.mapping_candidates ?? [],
        mappingFields: (file.mapping_fields ?? []).map((field) => ({
          key: field.key,
          label: field.label,
          selected: field.selected,
          required: field.required ?? false,
        })),
        fieldMapping: file.field_mapping ?? {},
        mappingSource: file.mapping_source,
        duplicateFileName: file.duplicate_file_name,
        sourceControl: file.source_control ? {
          status: file.source_control.status ?? "unavailable",
          computedRowCount: numberOrZero(file.source_control.computed_row_count),
          declaredRowCount: file.source_control.declared_row_count,
          computedDebitTotal: file.source_control.computed_debit_total,
          declaredDebitTotal: file.source_control.declared_debit_total,
          computedCreditTotal: file.source_control.computed_credit_total,
          declaredCreditTotal: file.source_control.declared_credit_total,
          mismatchFields: file.source_control.mismatch_fields ?? [],
        } : null,
        rowResults: (file.row_results ?? []).map((row) => ({
          ...mapPreviewDetailFields(row),
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
    affectedScopeKeys: stringList(payload.affected_scope_keys ?? payload.affectedScopeKeys),
  };
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
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

function mapManualInvoiceEntryValues(
  payload: ApiManualInvoiceEntryValues,
): Partial<ManualInvoiceEntryValues> {
  const values: Partial<ManualInvoiceEntryValues> = {};
  const direction = payload.invoice_direction;
  const nature = payload.invoice_nature;
  if (direction === "input" || direction === "output") values.invoiceDirection = direction;
  if (nature === "blue" || nature === "red") values.invoiceNature = nature;
  const fields: Array<[keyof ManualInvoiceEntryValues, unknown]> = [
    ["sellerName", payload.seller_name],
    ["sellerTaxNo", payload.seller_tax_no],
    ["buyerName", payload.buyer_name],
    ["buyerTaxNo", payload.buyer_tax_no],
    ["invoiceNumber", payload.invoice_number],
    ["invoiceCode", payload.invoice_code],
    ["invoiceDate", payload.invoice_date],
    ["netAmount", payload.net_amount],
    ["taxRate", payload.tax_rate],
    ["taxAmount", payload.tax_amount],
    ["totalWithTax", payload.total_with_tax],
  ];
  fields.forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      Object.assign(values, { [key]: String(value) });
    }
  });
  return values;
}

function serializeManualInvoiceEntryValues(values: ManualInvoiceEntryValues) {
  return {
    invoice_direction: values.invoiceDirection,
    invoice_nature: values.invoiceNature,
    seller_name: values.sellerName,
    seller_tax_no: values.sellerTaxNo,
    buyer_name: values.buyerName,
    buyer_tax_no: values.buyerTaxNo,
    invoice_number: values.invoiceNumber,
    invoice_code: values.invoiceCode,
    invoice_date: values.invoiceDate,
    net_amount: values.netAmount,
    tax_rate: values.taxRate,
    tax_amount: values.taxAmount,
    total_with_tax: values.totalWithTax,
  };
}

export async function recognizeManualInvoice(file: File): Promise<Partial<ManualInvoiceEntryValues>> {
  const formData = new FormData();
  formData.append("files", file);
  const payload = await requestJson<{ values?: ApiManualInvoiceEntryValues }>(
    "/imports/invoices/manual/recognize",
    { method: "POST", body: formData },
  );
  return mapManualInvoiceEntryValues(payload.values ?? {});
}

export async function previewManualInvoices(
  values: ManualInvoiceEntryValues[],
): Promise<ManualInvoiceEntryBatchPreview> {
  return previewManualInvoicesAtEndpoint("/imports/invoices/manual/preview", values);
}

export async function previewManualInvoicesAtEndpoint(
  endpoint: string,
  values: ManualInvoiceEntryValues[],
): Promise<ManualInvoiceEntryBatchPreview> {
  const payload = await requestJson<{
    values: ApiManualInvoiceEntryValues[];
    file_ids: string[];
    import_session: ApiImportSessionPayload;
  }>(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ invoices: values.map(serializeManualInvoiceEntryValues) }),
  });
  return {
    values: payload.values.map((item) => mapManualInvoiceEntryValues(item) as ManualInvoiceEntryValues),
    fileIds: payload.file_ids.map(String),
    importSession: mapImportPayload(payload.import_session),
  };
}

function mapManualBankTransactionEntryValues(
  payload: ApiManualBankTransactionEntryValues,
): ManualBankTransactionEntryValues {
  if (payload.direction !== "inflow" && payload.direction !== "outflow") {
    throw new Error("流水预览返回了未知的收支方向。");
  }
  return {
    bankMappingId: stringOrEmpty(payload.bank_mapping_id),
    bankName: stringOrEmpty(payload.bank_name),
    bankShortName: stringOrEmpty(payload.bank_short_name),
    last4: stringOrEmpty(payload.last4),
    accountNo: stringOrEmpty(payload.account_no),
    accountName: stringOrEmpty(payload.account_name),
    direction: payload.direction,
    amount: stringOrEmpty(payload.amount),
    balance: stringOrEmpty(payload.balance),
    tradeTime: stringOrEmpty(payload.trade_time).replace(" ", "T"),
    currency: stringOrEmpty(payload.currency),
    counterpartyName: stringOrEmpty(payload.counterparty_name),
    counterpartyAccountNo: stringOrEmpty(payload.counterparty_account_no),
    counterpartyBankName: stringOrEmpty(payload.counterparty_bank_name),
    summary: stringOrEmpty(payload.summary),
    remark: stringOrEmpty(payload.remark),
  };
}

function serializeManualBankTransactionEntryValues(values: ManualBankTransactionEntryValues) {
  return {
    bank_mapping_id: values.bankMappingId,
    account_no: values.accountNo,
    account_name: values.accountName,
    direction: values.direction,
    amount: values.amount,
    balance: values.balance,
    trade_time: values.tradeTime,
    currency: values.currency,
    counterparty_name: values.counterpartyName,
    counterparty_account_no: values.counterpartyAccountNo,
    counterparty_bank_name: values.counterpartyBankName,
    summary: values.summary,
    remark: values.remark,
  };
}

export async function previewManualBankTransactions(
  values: ManualBankTransactionEntryValues[],
): Promise<ManualBankTransactionEntryBatchPreview> {
  const payload = await requestJson<{
    values: ApiManualBankTransactionEntryValues[];
    file_ids: string[];
    import_session: ApiImportSessionPayload;
  }>("/imports/bank-transactions/manual/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transactions: values.map(serializeManualBankTransactionEntryValues) }),
  });
  const preview = {
    values: payload.values.map(mapManualBankTransactionEntryValues),
    fileIds: payload.file_ids.map(String),
    importSession: mapImportPayload(payload.import_session),
  };
  const confirmableFileIds = new Set(preview.fileIds);
  const responseIsConsistent = preview.importSession.files.every((file) => (
    file.rowResults.length === 1
    && (file.rowResults[0].decision === "created") === confirmableFileIds.has(file.id)
  ));
  if (!responseIsConsistent) {
    throw new Error("流水预览响应不完整，请重新预览。");
  }
  return preview;
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
          ...(override.fieldMapping && Object.keys(override.fieldMapping).length > 0
            ? { field_mapping: override.fieldMapping }
            : {}),
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
    fieldMapping?: Record<string, string>;
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
            ...(override.fieldMapping && Object.keys(override.fieldMapping).length > 0
              ? { field_mapping: override.fieldMapping }
              : {}),
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

export async function fetchActiveImportSessions(
  mode: "bank_transaction" | "invoice",
): Promise<ActiveImportSession[]> {
  const payload = await requestJson<{
    sessions?: Array<{
      session_id?: string;
      imported_by?: string;
      file_count?: number;
      batch_type?: ImportBatchType | null;
      created_at?: string;
      updated_at?: string;
      status?: string;
      job_id?: string | null;
      job_stage?: string | null;
      error?: string | null;
    }>;
  }>(`/imports/files/sessions?mode=${encodeURIComponent(mode)}`, { method: "GET" });
  return (payload.sessions ?? []).map((session) => ({
    sessionId: stringOrEmpty(session.session_id),
    importedBy: stringOrEmpty(session.imported_by),
    fileCount: numberOrZero(session.file_count),
    batchType: session.batch_type ?? null,
    createdAt: stringOrEmpty(session.created_at),
    updatedAt: stringOrEmpty(session.updated_at),
    status: stringOrEmpty(session.status),
    jobId: session.job_id ?? null,
    jobStage: session.job_stage ?? null,
    error: session.error ?? null,
  }));
}

export async function discardImportSession(sessionId: string): Promise<ImportSessionPayload> {
  const payload = await requestJson<ApiImportSessionPayload>("/imports/files/discard", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId }),
  });
  return mapImportPayload(payload);
}

type ApiImportReviewRowsPage = {
  rows?: Array<{
    file_id?: string;
    file_name?: string;
    row_no?: number;
    duplicate_type?: string;
    record_type?: string;
    decision?: string | null;
    decision_reason?: string | null;
    identity_kind?: string | null;
    account_no?: string | null;
    trade_time?: string | null;
    direction?: string | null;
    amount?: string | number | null;
    counterparty_name?: string | null;
    invoice_no?: string | null;
    invoice_date?: string | null;
    seller_name?: string | null;
    buyer_name?: string | null;
    tax_amount?: string | number | null;
    total_with_tax?: string | number | null;
  }>;
  total?: number;
  offset?: number;
  limit?: number;
  has_more?: boolean;
};

export async function fetchImportReviewRows(
  sessionId: string,
  kind: "duplicates" | "unimported",
  offset: number,
  signal?: AbortSignal,
): Promise<ImportReviewRowsPage> {
  const limit = 100;
  const query = new URLSearchParams({ kind, offset: String(offset), limit: String(limit) });
  const payload = await requestJson<ApiImportReviewRowsPage>(
    `/imports/files/sessions/${encodeURIComponent(sessionId)}/review-rows?${query}`,
    { method: "GET", signal },
  );
  if (!Array.isArray(payload.rows)) {
    throw new Error("导入复核数据响应格式错误，请刷新后重试。");
  }
  const rows = payload.rows.map((row, index) => ({
    ...mapPreviewDetailFields(row),
    id: `${row.file_id ?? "file"}-${row.row_no ?? offset + index}-${index}`,
    fileId: row.file_id ?? "",
    fileName: row.file_name ?? "",
    rowNo: numberOrZero(row.row_no),
    duplicateType: row.duplicate_type,
    recordType: row.record_type,
  }));
  return {
    rows,
    total: numberOrZero(payload.total),
    offset: numberOrZero(payload.offset),
    limit: numberOrZero(payload.limit) || limit,
    hasMore: payload.has_more ?? false,
  };
}

export async function fetchImportTemplates(): Promise<ImportTemplate[]> {
  const payload = await requestJson<ApiImportTemplatesPayload>("/imports/templates", {
    method: "GET",
  });
  return mapImportTemplates(payload);
}
