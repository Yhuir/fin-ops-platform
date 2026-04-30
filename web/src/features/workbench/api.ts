import type {
  WorkbenchActionVariant,
  WorkbenchCandidateGroup,
  WorkbenchData,
  WorkbenchDetailField,
  IgnoredWorkbenchData,
  BankAccountMapping,
  WorkbenchPaneRows,
  WorkbenchRecord,
  WorkbenchRecordType,
  WorkbenchProjectSetting,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetResult,
  WorkbenchSummary,
  WorkbenchOaStatus,
  WorkbenchColumnLayouts,
  WorkbenchOaImportOption,
} from "./types";

export type WorkbenchBootstrapProgress = {
  label: string;
  loadedBytes: number;
  totalBytes: number;
  percent: number | null;
  indeterminate: boolean;
};

type ApiRelation = {
  code: string;
  label: string;
  tone: string;
};

type ApiWorkbenchRow = {
  id: string;
  type: WorkbenchRecordType;
  source_kind?: string | null;
  case_id?: string | null;
  handled_exception?: boolean | null;
  applicant?: string | null;
  project_name?: string | null;
  apply_type?: string | null;
  amount?: string | null;
  counterparty_name?: string | null;
  reason?: string | null;
  oa_bank_relation?: ApiRelation | null;
  trade_time?: string | null;
  direction?: string | null;
  debit_amount?: string | null;
  credit_amount?: string | null;
  payment_account_label?: string | null;
  invoice_relation?: ApiRelation | null;
  pay_receive_time?: string | null;
  remark?: string | null;
  repayment_date?: string | null;
  seller_tax_no?: string | null;
  seller_name?: string | null;
  buyer_tax_no?: string | null;
  buyer_name?: string | null;
  invoice_code?: string | null;
  invoice_no?: string | null;
  digital_invoice_no?: string | null;
  issue_date?: string | null;
  tax_rate?: string | null;
  tax_amount?: string | null;
  total_with_tax?: string | null;
  invoice_type?: string | null;
  invoice_bank_relation?: ApiRelation | null;
  available_actions?: string[];
  summary_fields?: Record<string, string>;
  detail_fields?: Record<string, string>;
  tags?: string[];
  cost_excluded?: boolean | null;
};

type ApiWorkbenchPayload = {
  month: string;
  oa_status?: {
    code?: string;
    message?: string;
  };
  summary: {
    oa_count: number;
    bank_count: number;
    invoice_count: number;
    paired_count: number;
    open_count: number;
    exception_count: number;
  };
  paired: {
    groups: ApiWorkbenchGroup[];
  };
  open: {
    groups: ApiWorkbenchGroup[];
  };
};

type ApiIgnoredWorkbenchPayload = {
  month: string;
  rows: ApiWorkbenchRow[];
};

type ApiWorkbenchSettings = {
  projects: {
    active: Array<{
      id: string;
      project_code: string;
      project_name: string;
      project_status: "active" | "completed";
      source?: "oa" | "manual" | null;
      department_name?: string | null;
      owner_name?: string | null;
    }>;
    completed: Array<{
      id: string;
      project_code: string;
      project_name: string;
      project_status: "active" | "completed";
      source?: "oa" | "manual" | null;
      department_name?: string | null;
      owner_name?: string | null;
    }>;
    completed_project_ids: string[];
  };
  bank_account_mappings: Array<{
    id: string;
    last4: string;
    bank_name: string;
    short_name?: string | null;
  }>;
  access_control?: {
    allowed_usernames?: string[];
    readonly_export_usernames?: string[];
    admin_usernames?: string[];
    full_access_usernames?: string[];
  };
  workbench_column_layouts?: Partial<WorkbenchColumnLayouts>;
  oa_retention?: {
    cutoff_date?: string;
  };
  oa_import?: {
    form_types?: string[];
    selected_form_types?: string[];
    statuses?: string[];
    selected_statuses?: string[];
    available_form_types?: ApiWorkbenchSettingsOption[];
    available_statuses?: ApiWorkbenchSettingsOption[];
  };
  oa_invoice_offset?: {
    applicant_names?: string[];
  };
};

type ApiWorkbenchSettingsOption =
  | string
  | number
  | {
    value?: string | number | null;
    code?: string | number | null;
    id?: string | number | null;
    label?: string | null;
    name?: string | null;
    text?: string | null;
  };

type ApiWorkbenchGroup = {
  group_id: string;
  group_type: "auto_closed" | "manual_confirmed" | "candidate";
  match_confidence: "high" | "medium" | "low";
  reason: string;
  oa_rows: ApiWorkbenchRow[];
  bank_rows: ApiWorkbenchRow[];
  invoice_rows: ApiWorkbenchRow[];
};

type ApiWorkbenchActionResult = {
  success: boolean;
  action: string;
  month: string;
  affected_row_ids: string[];
  case_id?: string;
  updated_rows?: Array<{ id: string }>;
  message: string;
};

type ConfirmLinkPayload = {
  month: string;
  rowIds: string[];
  caseId?: string;
};

type MarkExceptionPayload = {
  month: string;
  rowId: string;
  exceptionCode: string;
  comment?: string;
};

type CancelLinkPayload = {
  month: string;
  rowId: string;
  comment?: string;
};

type UpdateBankExceptionPayload = {
  month: string;
  rowId: string;
  relationCode: string;
  relationLabel: string;
  comment?: string;
};

type OaBankExceptionPayload = {
  month: string;
  rowIds: string[];
  exceptionCode: string;
  exceptionLabel: string;
  comment?: string;
};

type IgnoreRowPayload = {
  month: string;
  rowId: string;
  comment?: string;
};

type UnignoreRowPayload = {
  month: string;
  rowId: string;
};

type CancelExceptionPayload = {
  month: string;
  rowIds: string[];
  comment?: string;
};

type WorkbenchSettingsUpdatePayload = {
  completedProjectIds: string[];
  bankAccountMappings: BankAccountMapping[];
  allowedUsernames: string[];
  readonlyExportUsernames: string[];
  adminUsernames: string[];
  workbenchColumnLayouts: WorkbenchColumnLayouts;
  oaRetention: {
    cutoffDate: string;
  };
  oaImport: {
    formTypes: string[];
    statuses: string[];
  };
  oaInvoiceOffset?: {
    applicantNames: string[];
  };
};

type ApiWorkbenchSettingsDataResetResult = {
  action: WorkbenchSettingsDataResetAction;
  status: string;
  cleared_collections?: string[];
  deleted_counts?: Record<string, number>;
  protected_targets?: string[];
  rebuild_status?: string;
  message?: string;
};

type WorkbenchSettingsDataResetPayload = {
  action: WorkbenchSettingsDataResetAction;
  oaPassword: string;
};

type ApiWorkbenchSettingsProjectMutationResult = {
  settings: ApiWorkbenchSettings;
};

type ApiWorkbenchSettingsProjectSyncResult = {
  settings: ApiWorkbenchSettings;
};

type WorkbenchSettingsProjectCreatePayload = {
  actorId: string;
  projectCode: string;
  projectName: string;
};

function toDisplayValue(value: string | null | undefined, fallback = "--") {
  return value && value.trim().length > 0 ? value : fallback;
}

function firstNonPlaceholderDisplayValue(...values: Array<string | null | undefined>) {
  for (const value of values) {
    const displayValue = toDisplayValue(value, "");
    if (displayValue && displayValue !== "--" && displayValue !== "—") {
      return displayValue;
    }
  }
  return undefined;
}

function rowRelation(row: ApiWorkbenchRow) {
  if (row.type === "oa") {
    return row.oa_bank_relation;
  }
  if (row.type === "bank") {
    return row.invoice_relation;
  }
  return row.invoice_bank_relation;
}

function rowActionVariant(row: ApiWorkbenchRow): WorkbenchActionVariant {
  if (row.type === "bank") {
    if (!row.available_actions || row.available_actions.length === 0 || row.available_actions.every((action) => action === "detail")) {
      return "detail-only";
    }
    return "bank-review";
  }
  if (row.available_actions?.includes("confirm_link") || row.available_actions?.includes("mark_exception")) {
    return "confirm-exception";
  }
  return "detail-only";
}

function rowLabel(row: ApiWorkbenchRow) {
  if (row.type === "oa") {
    return toDisplayValue(row.apply_type, "OA");
  }
  if (row.type === "bank") {
    return row.debit_amount ? "支取" : "收入";
  }
  return row.invoice_type?.includes("销") ? "销项票" : "进项票";
}

function rowAmount(row: ApiWorkbenchRow) {
  if (row.type === "bank") {
    return resolveBankAmount(row);
  }
  return toDisplayValue(row.amount);
}

function rowCounterparty(row: ApiWorkbenchRow) {
  if (row.type === "invoice") {
    return toDisplayValue(row.buyer_name ?? row.seller_name);
  }
  return toDisplayValue(row.counterparty_name);
}

function mapTableValues(row: ApiWorkbenchRow): Record<string, string> {
  const relationLabel = rowRelation(row)?.label ?? "待处理";

  if (row.type === "oa") {
    const detailFields = row.detail_fields ?? {};
    return {
      applicant: toDisplayValue(row.applicant),
      applicationTime: toDisplayValue(
        detailFields["审批完成时间"] ?? detailFields["申请日期"] ?? detailFields["创建时间"],
      ),
      projectName: toDisplayValue(row.project_name),
      applicationType: toDisplayValue(row.apply_type),
      amount: toDisplayValue(row.amount),
      counterparty: toDisplayValue(row.counterparty_name),
      reason: toDisplayValue(row.reason),
      reconciliationStatus: relationLabel,
    };
  }

  if (row.type === "bank") {
    const direction = resolveBankDirection(row);
    return {
      transactionTime: toDisplayValue(row.trade_time),
      direction,
      amount: resolveBankAmount(row),
      debitAmount: toDisplayValue(row.debit_amount),
      creditAmount: toDisplayValue(row.credit_amount),
      counterparty: toDisplayValue(row.counterparty_name),
      paymentAccount: toDisplayValue(row.payment_account_label),
      invoiceRelationStatus: relationLabel,
      paymentOrReceiptTime: toDisplayValue(row.pay_receive_time),
      note: toDisplayValue(row.remark),
      loanRepaymentDate: toDisplayValue(row.repayment_date),
    };
  }

  const detailFields = row.detail_fields ?? {};
  return {
    sellerTaxId: toDisplayValue(row.seller_tax_no),
    sellerName: toDisplayValue(row.seller_name),
    buyerTaxId: toDisplayValue(row.buyer_tax_no),
    buyerName: toDisplayValue(row.buyer_name),
    invoiceCode: toDisplayValue(firstNonPlaceholderDisplayValue(detailFields["发票代码"], row.invoice_code)),
    invoiceNo: toDisplayValue(firstNonPlaceholderDisplayValue(
      detailFields["发票号码"],
      row.invoice_no,
      detailFields["数电发票号码"],
      row.digital_invoice_no,
    )),
    digitalInvoiceNo: toDisplayValue(firstNonPlaceholderDisplayValue(detailFields["数电发票号码"], row.digital_invoice_no)),
    issueDate: toDisplayValue(row.issue_date),
    amount: toDisplayValue(row.amount),
    taxRate: toDisplayValue(row.tax_rate),
    taxAmount: toDisplayValue(row.tax_amount),
    grossAmount: toDisplayValue(row.total_with_tax),
    invoiceType: toDisplayValue(row.invoice_type),
  };
}

function mapDetailFields(detailFields?: Record<string, string>): WorkbenchDetailField[] {
  if (!detailFields) {
    return [];
  }

  return Object.entries(detailFields)
    .filter(([label]) => label !== "资金方向")
    .map(([label, value]) => ({
      label: label === "和发票关联情况" ? "和发票OA关联情况" : label,
      value: toDisplayValue(value, "—"),
    }));
}

function resolveBankDirection(row: ApiWorkbenchRow) {
  const normalizedDirection = toDisplayValue(row.direction, "");
  if (normalizedDirection === "支出" || normalizedDirection === "收入") {
    return normalizedDirection;
  }
  if (toDisplayValue(row.debit_amount, "") !== "") {
    return "支出";
  }
  if (toDisplayValue(row.credit_amount, "") !== "") {
    return "收入";
  }
  return "未识别";
}

function resolveBankAmount(row: ApiWorkbenchRow) {
  const debitAmount = toDisplayValue(row.debit_amount, "");
  if (debitAmount !== "") {
    return debitAmount;
  }
  const creditAmount = toDisplayValue(row.credit_amount, "");
  if (creditAmount !== "") {
    return creditAmount;
  }
  return "--";
}

function mapRow(row: ApiWorkbenchRow): WorkbenchRecord {
  return {
    id: row.id,
    caseId: row.case_id ?? undefined,
    recordType: row.type,
    sourceKind: row.source_kind ?? undefined,
    label: rowLabel(row),
    status: rowRelation(row)?.label ?? "待处理",
    statusCode: rowRelation(row)?.code ?? "pending",
    statusTone: rowRelation(row)?.tone ?? "warn",
    exceptionHandled: Boolean(row.handled_exception),
    amount: rowAmount(row),
    counterparty: rowCounterparty(row),
    tableValues: mapTableValues(row),
    detailFields: mapDetailFields(row.detail_fields),
    actionVariant: rowActionVariant(row),
    availableActions: row.available_actions ?? [],
    tags: Array.isArray(row.tags) ? row.tags.map((tag) => String(tag).trim()).filter(Boolean) : [],
  };
}

function mapPaneRows(panes: Record<WorkbenchRecordType, ApiWorkbenchRow[]>): WorkbenchPaneRows {
  return {
    oa: panes.oa.map(mapRow),
    bank: panes.bank.map(mapRow),
    invoice: panes.invoice.map(mapRow),
  };
}

function mapGroup(group: ApiWorkbenchGroup): WorkbenchCandidateGroup {
  return {
    id: group.group_id,
    groupType: group.group_type,
    matchConfidence: group.match_confidence,
    reason: group.reason,
    rows: {
      oa: group.oa_rows.map(mapRow),
      bank: group.bank_rows.map(mapRow),
      invoice: group.invoice_rows.map(mapRow),
    },
  };
}

function mapSummary(summary: ApiWorkbenchPayload["summary"]): WorkbenchSummary {
  return {
    oaCount: summary.oa_count,
    bankCount: summary.bank_count,
    invoiceCount: summary.invoice_count,
    pairedCount: summary.paired_count,
    openCount: summary.open_count,
    exceptionCount: summary.exception_count,
    totalCount: summary.oa_count + summary.bank_count + summary.invoice_count,
  };
}

function mapOaStatus(oaStatus?: ApiWorkbenchPayload["oa_status"]): WorkbenchOaStatus {
  const code = String(oaStatus?.code ?? "ready").trim();
  const message = String(oaStatus?.message ?? "OA 已同步").trim();
  return {
    code: code === "idle" || code === "loading" || code === "ready" || code === "error" ? code : "ready",
    message: message || "OA 已同步",
  };
}

function mapProjectSetting(project: ApiWorkbenchSettings["projects"]["active"][number]): WorkbenchProjectSetting {
  return {
    id: project.id,
    projectCode: project.project_code,
    projectName: project.project_name,
    projectStatus: project.project_status,
    source: project.source === "manual" ? "manual" : "oa",
    departmentName: project.department_name,
    ownerName: project.owner_name,
  };
}

function cleanStringList(values: unknown[] | undefined, fallback: string[]) {
  const cleaned = (values ?? [])
    .map((item) => String(item).trim())
    .filter(Boolean);
  return cleaned.length > 0 ? cleaned : fallback;
}

function mapSettingsOption(option: ApiWorkbenchSettingsOption): WorkbenchOaImportOption | null {
  if (typeof option === "string" || typeof option === "number") {
    const value = String(option).trim();
    return value ? { value, label: value } : null;
  }
  if (!option || typeof option !== "object") {
    return null;
  }
  const value = String(option.value ?? option.code ?? option.id ?? "").trim();
  const label = String(option.label ?? option.name ?? option.text ?? value).trim();
  if (!value || !label) {
    return null;
  }
  return { value, label };
}

function normalizeSettingsOptions(
  options: ApiWorkbenchSettingsOption[] | undefined,
  fallback: WorkbenchOaImportOption[],
) {
  const mapped = (options ?? [])
    .map(mapSettingsOption)
    .filter((option): option is WorkbenchOaImportOption => option !== null);
  return mapped.length > 0 ? mapped : fallback;
}

function mapWorkbenchSettings(payload: ApiWorkbenchSettings): WorkbenchSettings {
  const rawLayouts = payload.workbench_column_layouts ?? {};
  const defaultFormTypes = ["payment_request", "expense_claim"];
  const defaultStatuses = ["completed"];
  const defaultAvailableFormTypes = [
    { value: "payment_request", label: "支付申请" },
    { value: "expense_claim", label: "日常报销" },
  ];
  const defaultAvailableStatuses = [
    { value: "completed", label: "已完成" },
    { value: "in_progress", label: "进行中" },
  ];
  const oaImport = payload.oa_import ?? {};
  return {
    projects: {
      active: payload.projects.active.map(mapProjectSetting),
      completed: payload.projects.completed.map(mapProjectSetting),
      completedProjectIds: payload.projects.completed_project_ids,
    },
    bankAccountMappings: payload.bank_account_mappings.map((mapping) => ({
      id: mapping.id,
      last4: mapping.last4,
      bankName: mapping.bank_name,
      shortName: mapping.short_name ?? "",
    })),
    accessControl: {
      allowedUsernames: (payload.access_control?.allowed_usernames ?? [])
        .map((item) => String(item).trim())
        .filter(Boolean),
      readonlyExportUsernames: (payload.access_control?.readonly_export_usernames ?? [])
        .map((item) => String(item).trim())
        .filter(Boolean),
      adminUsernames: (payload.access_control?.admin_usernames ?? [])
        .map((item) => String(item).trim())
        .filter(Boolean),
      fullAccessUsernames: (payload.access_control?.full_access_usernames ?? [])
        .map((item) => String(item).trim())
        .filter(Boolean),
    },
    workbenchColumnLayouts: {
      oa: Array.isArray(rawLayouts.oa) ? rawLayouts.oa.map((item) => String(item)) : [],
      bank: Array.isArray(rawLayouts.bank) ? rawLayouts.bank.map((item) => String(item)) : [],
      invoice: Array.isArray(rawLayouts.invoice) ? rawLayouts.invoice.map((item) => String(item)) : [],
    },
    oaRetention: {
      cutoffDate: payload.oa_retention?.cutoff_date || "2026-01-01",
    },
    oaImport: {
      formTypes: cleanStringList(oaImport.form_types ?? oaImport.selected_form_types, defaultFormTypes),
      statuses: cleanStringList(oaImport.statuses ?? oaImport.selected_statuses, defaultStatuses),
      availableFormTypes: normalizeSettingsOptions(oaImport.available_form_types, defaultAvailableFormTypes),
      availableStatuses: normalizeSettingsOptions(oaImport.available_statuses, defaultAvailableStatuses),
    },
    oaInvoiceOffset: {
      applicantNames: (payload.oa_invoice_offset?.applicant_names ?? [])
        .map((item) => String(item).trim())
        .filter(Boolean),
    },
  };
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const rawText = await response.text();
  let payload: T | null = null;
  if (rawText.trim()) {
    try {
      payload = JSON.parse(rawText) as T;
    } catch {
      if (!response.ok) {
        throw new Error(rawText.trim() || "request failed");
      }
      throw new Error("invalid_json_response");
    }
  }
  if (!response.ok) {
    throw new Error(typeof payload === "object" && payload ? JSON.stringify(payload) : rawText.trim() || "request failed");
  }
  return ((payload ?? {}) as T);
}

function createAbortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function isMockedFetch(value: unknown): value is typeof fetch {
  return typeof value === "function" && ("mock" in value || "getMockName" in value);
}

async function requestJsonWithByteProgress<T>(
  url: string,
  {
    signal,
    onProgress,
  }: {
    signal?: AbortSignal;
    onProgress?: (loadedBytes: number, totalBytes: number) => void;
  } = {},
) {
  if (!onProgress || typeof XMLHttpRequest === "undefined" || isMockedFetch(globalThis.fetch)) {
    return requestJson<T>(url, { method: "GET", signal });
  }

  return new Promise<T>((resolve, reject) => {
    if (signal?.aborted) {
      reject(createAbortError());
      return;
    }

    const xhr = new XMLHttpRequest();
    let settled = false;
    let lastLoadedBytes = 0;
    let lastTotalBytes = 0;

    const finalizeReject = (error: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      reject(error);
    };

    const finalizeResolve = (value: T) => {
      if (settled) {
        return;
      }
      settled = true;
      resolve(value);
    };

    const handleAbort = () => {
      xhr.abort();
      finalizeReject(createAbortError());
    };

    signal?.addEventListener("abort", handleAbort, { once: true });

    xhr.open("GET", url, true);
    xhr.responseType = "text";

    xhr.onprogress = (event) => {
      lastLoadedBytes = event.loaded;
      lastTotalBytes = event.lengthComputable ? event.total : lastTotalBytes;
      onProgress(lastLoadedBytes, lastTotalBytes);
    };

    xhr.onerror = () => {
      signal?.removeEventListener("abort", handleAbort);
      finalizeReject(new Error("request failed"));
    };

    xhr.onabort = () => {
      signal?.removeEventListener("abort", handleAbort);
      finalizeReject(createAbortError());
    };

    xhr.onload = () => {
      signal?.removeEventListener("abort", handleAbort);

      const rawText = xhr.responseText ?? "";
      const contentLengthHeader = xhr.getResponseHeader("Content-Length");
      const headerTotalBytes = contentLengthHeader ? Number.parseInt(contentLengthHeader, 10) : 0;
      const finalLoadedBytes = Math.max(lastLoadedBytes, rawText.length);
      const finalTotalBytes = Math.max(lastTotalBytes, Number.isFinite(headerTotalBytes) ? headerTotalBytes : 0, finalLoadedBytes);
      onProgress(finalLoadedBytes, finalTotalBytes);

      let payload: T | null = null;
      if (rawText.trim()) {
        try {
          payload = JSON.parse(rawText) as T;
        } catch {
          if (xhr.status < 200 || xhr.status >= 300) {
            finalizeReject(new Error(rawText.trim() || "request failed"));
            return;
          }
          finalizeReject(new Error("invalid_json_response"));
          return;
        }
      }

      if (xhr.status < 200 || xhr.status >= 300) {
        finalizeReject(
          new Error(typeof payload === "object" && payload ? JSON.stringify(payload) : rawText.trim() || "request failed"),
        );
        return;
      }

      finalizeResolve((payload ?? {}) as T);
    };

    xhr.send();
  });
}

export async function fetchWorkbench(month: string, signal?: AbortSignal): Promise<WorkbenchData> {
  return fetchWorkbenchWithProgress(month, signal);
}

export async function fetchWorkbenchWithProgress(
  month: string,
  signal?: AbortSignal,
  onProgress?: (progress: WorkbenchBootstrapProgress) => void,
): Promise<WorkbenchData> {
  const payload = await requestJsonWithByteProgress<ApiWorkbenchPayload>(`/api/workbench?month=${month}`, {
    signal,
    onProgress: onProgress
      ? (loadedBytes, totalBytes) => {
        const resolvedPercent = totalBytes > 0 ? clampPercent((loadedBytes / totalBytes) * 100) : null;
        onProgress({
          label: "读 OA 中",
          loadedBytes,
          totalBytes,
          percent: resolvedPercent,
          indeterminate: totalBytes <= 0,
        });
      }
      : undefined,
  });

  if (onProgress) {
    onProgress({
      label: "关联台数据已加载完成",
      loadedBytes: 0,
      totalBytes: 0,
      percent: 100,
      indeterminate: false,
    });
  }

  return {
    month: payload.month,
    oaStatus: mapOaStatus(payload.oa_status),
    summary: mapSummary(payload.summary),
    paired: {
      groups: payload.paired.groups.map(mapGroup),
    },
    open: {
      groups: payload.open.groups.map(mapGroup),
    },
  };
}

export async function fetchIgnoredWorkbenchRowsWithProgress(
  month: string,
  signal?: AbortSignal,
  onProgress?: (progress: WorkbenchBootstrapProgress) => void,
): Promise<IgnoredWorkbenchData> {
  const payload = await requestJsonWithByteProgress<ApiIgnoredWorkbenchPayload>(`/api/workbench/ignored?month=${month}`, {
    signal,
    onProgress: onProgress
      ? (loadedBytes, totalBytes) => {
        const resolvedPercent = totalBytes > 0 ? clampPercent((loadedBytes / totalBytes) * 100) : null;
        onProgress({
          label: "正在同步已忽略数据",
          loadedBytes,
          totalBytes,
          percent: resolvedPercent,
          indeterminate: totalBytes <= 0,
        });
      }
      : undefined,
  });

  return {
    month: payload.month,
    rows: payload.rows.map(mapRow),
  };
}

export async function fetchWorkbenchSettingsWithProgress(
  signal?: AbortSignal,
  onProgress?: (progress: WorkbenchBootstrapProgress) => void,
): Promise<WorkbenchSettings> {
  const payload = await requestJsonWithByteProgress<ApiWorkbenchSettings>("/api/workbench/settings", {
    signal,
    onProgress: onProgress
      ? (loadedBytes, totalBytes) => {
        const resolvedPercent = totalBytes > 0 ? clampPercent((loadedBytes / totalBytes) * 100) : null;
        onProgress({
          label: "正在同步关联台设置",
          loadedBytes,
          totalBytes,
          percent: resolvedPercent,
          indeterminate: totalBytes <= 0,
        });
      }
      : undefined,
  });
  return mapWorkbenchSettings(payload);
}

export async function fetchIgnoredWorkbenchRows(month: string, signal?: AbortSignal): Promise<IgnoredWorkbenchData> {
  return fetchIgnoredWorkbenchRowsWithProgress(month, signal);
}

export async function fetchWorkbenchSettings(signal?: AbortSignal): Promise<WorkbenchSettings> {
  return fetchWorkbenchSettingsWithProgress(signal);
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.min(100, Math.max(0, Math.round(value)));
}

export async function saveWorkbenchSettings(
  settings: WorkbenchSettingsUpdatePayload,
): Promise<WorkbenchSettings> {
  const payload = await requestJson<ApiWorkbenchSettings>("/api/workbench/settings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      completed_project_ids: settings.completedProjectIds,
      bank_account_mappings: settings.bankAccountMappings.map((mapping) => ({
        id: mapping.id,
        last4: mapping.last4,
        bank_name: mapping.bankName,
        short_name: mapping.shortName,
      })),
      allowed_usernames: settings.allowedUsernames,
      readonly_export_usernames: settings.readonlyExportUsernames,
      admin_usernames: settings.adminUsernames,
      workbench_column_layouts: settings.workbenchColumnLayouts,
      oa_retention: {
        cutoff_date: settings.oaRetention.cutoffDate,
      },
      oa_import: {
        form_types: settings.oaImport.formTypes,
        statuses: settings.oaImport.statuses,
      },
      oa_invoice_offset: {
        applicant_names: settings.oaInvoiceOffset?.applicantNames ?? [],
      },
    }),
  });
  return mapWorkbenchSettings(payload);
}

export async function resetWorkbenchSettingsData(
  payload: WorkbenchSettingsDataResetPayload,
): Promise<WorkbenchSettingsDataResetResult> {
  const result = await requestJson<ApiWorkbenchSettingsDataResetResult>("/api/workbench/settings/data-reset", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      action: payload.action,
      oa_password: payload.oaPassword,
    }),
  });
  return {
    action: result.action,
    status: result.status,
    clearedCollections: result.cleared_collections ?? [],
    deletedCounts: result.deleted_counts ?? {},
    protectedTargets: result.protected_targets ?? [],
    rebuildStatus: result.rebuild_status ?? "unknown",
    message: result.message ?? "数据重置已完成。",
  };
}

export async function syncWorkbenchSettingsProjects(actorId: string): Promise<WorkbenchSettings> {
  const payload = await requestJson<ApiWorkbenchSettingsProjectSyncResult>("/api/workbench/settings/projects/sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      actor_id: actorId,
    }),
  });
  return mapWorkbenchSettings(payload.settings);
}

export async function createWorkbenchSettingsProject(
  payload: WorkbenchSettingsProjectCreatePayload,
): Promise<WorkbenchSettings> {
  const result = await requestJson<ApiWorkbenchSettingsProjectMutationResult>("/api/workbench/settings/projects", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      actor_id: payload.actorId,
      project_code: payload.projectCode,
      project_name: payload.projectName,
    }),
  });
  return mapWorkbenchSettings(result.settings);
}

export async function deleteWorkbenchSettingsProject(projectId: string): Promise<WorkbenchSettings> {
  const payload = await requestJson<ApiWorkbenchSettingsProjectMutationResult>(
    `/api/workbench/settings/projects/${encodeURIComponent(projectId)}`,
    {
      method: "DELETE",
    },
  );
  return mapWorkbenchSettings(payload.settings);
}

export async function fetchWorkbenchRowDetail(rowId: string, signal?: AbortSignal): Promise<WorkbenchRecord> {
  const payload = await requestJson<{ row: ApiWorkbenchRow }>(`/api/workbench/rows/${rowId}`, {
    method: "GET",
    signal,
  });
  return mapRow(payload.row);
}

export async function confirmWorkbenchLink(payload: ConfirmLinkPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/confirm-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      case_id: payload.caseId,
    }),
  });
}

export async function markWorkbenchException(payload: MarkExceptionPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/mark-exception", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_id: payload.rowId,
      exception_code: payload.exceptionCode,
      comment: payload.comment,
    }),
  });
}

export async function cancelWorkbenchLink(payload: CancelLinkPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/cancel-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_id: payload.rowId,
      comment: payload.comment,
    }),
  });
}

export async function updateWorkbenchBankException(payload: UpdateBankExceptionPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/update-bank-exception", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_id: payload.rowId,
      relation_code: payload.relationCode,
      relation_label: payload.relationLabel,
      comment: payload.comment,
    }),
  });
}

export async function submitOaBankException(payload: OaBankExceptionPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/oa-bank-exception", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      exception_code: payload.exceptionCode,
      exception_label: payload.exceptionLabel,
      comment: payload.comment,
    }),
  });
}

export async function ignoreWorkbenchRow(payload: IgnoreRowPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/ignore-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_id: payload.rowId,
      comment: payload.comment,
    }),
  });
}

export async function unignoreWorkbenchRow(payload: UnignoreRowPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/unignore-row", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_id: payload.rowId,
    }),
  });
}

export async function cancelWorkbenchException(payload: CancelExceptionPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/cancel-exception", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      comment: payload.comment,
    }),
  });
}
