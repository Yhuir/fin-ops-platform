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
  WorkbenchSummary,
} from "./types";

type ApiRelation = {
  code: string;
  label: string;
  tone: string;
};

type ApiWorkbenchRow = {
  id: string;
  type: WorkbenchRecordType;
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
  issue_date?: string | null;
  tax_rate?: string | null;
  tax_amount?: string | null;
  total_with_tax?: string | null;
  invoice_type?: string | null;
  invoice_bank_relation?: ApiRelation | null;
  available_actions?: string[];
  summary_fields?: Record<string, string>;
  detail_fields?: Record<string, string>;
};

type ApiWorkbenchPayload = {
  month: string;
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
      department_name?: string | null;
      owner_name?: string | null;
    }>;
    completed: Array<{
      id: string;
      project_code: string;
      project_name: string;
      project_status: "active" | "completed";
      department_name?: string | null;
      owner_name?: string | null;
    }>;
    completed_project_ids: string[];
  };
  bank_account_mappings: Array<{
    id: string;
    last4: string;
    bank_name: string;
  }>;
  access_control?: {
    allowed_usernames?: string[];
  };
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
  updated_rows: Array<{ id: string }>;
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
};

function toDisplayValue(value: string | null | undefined, fallback = "--") {
  return value && value.trim().length > 0 ? value : fallback;
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
    return toDisplayValue(row.debit_amount ?? row.credit_amount);
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
    return {
      applicant: toDisplayValue(row.applicant),
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

  return {
    sellerTaxId: toDisplayValue(row.seller_tax_no),
    sellerName: toDisplayValue(row.seller_name),
    buyerTaxId: toDisplayValue(row.buyer_tax_no),
    buyerName: toDisplayValue(row.buyer_name),
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
      label,
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

function mapRow(row: ApiWorkbenchRow): WorkbenchRecord {
  return {
    id: row.id,
    caseId: row.case_id ?? undefined,
    recordType: row.type,
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

function mapProjectSetting(project: ApiWorkbenchSettings["projects"]["active"][number]): WorkbenchProjectSetting {
  return {
    id: project.id,
    projectCode: project.project_code,
    projectName: project.project_name,
    projectStatus: project.project_status,
    departmentName: project.department_name,
    ownerName: project.owner_name,
  };
}

function mapWorkbenchSettings(payload: ApiWorkbenchSettings): WorkbenchSettings {
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
    })),
    accessControl: {
      allowedUsernames: (payload.access_control?.allowed_usernames ?? [])
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

export async function fetchWorkbench(month: string, signal?: AbortSignal): Promise<WorkbenchData> {
  const payload = await requestJson<ApiWorkbenchPayload>(`/api/workbench?month=${month}`, {
    method: "GET",
    signal,
  });

  return {
    month: payload.month,
    summary: mapSummary(payload.summary),
    paired: {
      groups: payload.paired.groups.map(mapGroup),
    },
    open: {
      groups: payload.open.groups.map(mapGroup),
    },
  };
}

export async function fetchIgnoredWorkbenchRows(month: string, signal?: AbortSignal): Promise<IgnoredWorkbenchData> {
  const payload = await requestJson<ApiIgnoredWorkbenchPayload>(`/api/workbench/ignored?month=${month}`, {
    method: "GET",
    signal,
  });

  return {
    month: payload.month,
    rows: payload.rows.map(mapRow),
  };
}

export async function fetchWorkbenchSettings(signal?: AbortSignal): Promise<WorkbenchSettings> {
  const payload = await requestJson<ApiWorkbenchSettings>("/api/workbench/settings", {
    method: "GET",
    signal,
  });
  return mapWorkbenchSettings(payload);
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
      })),
      allowed_usernames: settings.allowedUsernames,
    }),
  });
  return mapWorkbenchSettings(payload);
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
