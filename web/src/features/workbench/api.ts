import type {
  WorkbenchExceptionAction,
  WorkbenchExceptionApplyPayload,
  WorkbenchExceptionApplyResult,
  WorkbenchExceptionCandidateEvidence,
  WorkbenchExceptionPreview,
  WorkbenchExceptionPreviewPayload,
  WorkbenchExceptionWarning,
} from "./exceptionTypes";
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
  WorkbenchRelationMode,
  WorkbenchRelationPreview,
  WorkbenchProjectSetting,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
  WorkbenchSettingsDataResetResult,
  WorkbenchSummary,
  WorkbenchOaStatus,
  WorkbenchColumnLayouts,
  WorkbenchAmountCheck,
  WorkbenchOaImportOption,
  WorkbenchOaSyncStatus,
  WorkbenchInvoiceInventory,
  WorkbenchSourceKind,
  WorkbenchGroupType,
  WorkbenchGroupsPageQuery,
  WorkbenchGroupsPageResult,
  WorkbenchInitialPageResult,
  WorkbenchReadModelStatus,
  WorkbenchZoneId,
  WorkbenchZonePageInfo,
  OaManualAttachmentRefreshResult,
  OaManualImportList,
  OaManualImportResult,
  OaManualSearchFilters,
  OaManualSearchItem,
  OaManualSearchResult,
  OaManualSearchRow,
} from "./types";
import { apiUrl } from "../../app/runtime";
import { countWorkbenchGroupsRows } from "./groupDisplayModel";
import { mapBankTransactionTagDictionary } from "../pendingInvoices/api";
import { readOATokenCookie } from "../session/api";
import type { BankTransactionTagDictionary, PendingInvoiceTagGroups } from "../pendingInvoices/types";

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
  source_kind?: WorkbenchSourceKind | null;
  case_id?: string | null;
  exception_case_id?: string | null;
  handled_exception?: boolean | null;
  applicant?: string | null;
  project_name?: string | null;
  project_name_display?: string | null;
  project_names?: string[] | null;
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
  category_code?: string | null;
  category_label?: string | null;
  category_path?: string[] | null;
  category_source?: string | null;
  bank_text_fields?: Array<{
    label?: string | null;
    value?: string | null;
  }> | null;
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
  summary_fields?: Record<string, unknown>;
  detail_fields?: Record<string, unknown>;
  tags?: string[];
  relation_note?: string | null;
  relation_amount_check?: ApiWorkbenchRelationAmountCheck | null;
  cost_excluded?: boolean | null;
  special_metadata?: Record<string, unknown> | null;
};

type ApiWorkbenchPayload = {
  month: string;
  oa_status?: {
    code?: string;
    message?: string;
  };
  invoice_inventory?: ApiWorkbenchInvoiceInventory;
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

type ApiWorkbenchSummaryPayload = {
  month: string;
  scope_key?: string;
  generated_at?: string | null;
  read_model_status?: WorkbenchReadModelStatus;
  oa_status?: ApiWorkbenchPayload["oa_status"];
  invoice_inventory?: ApiWorkbenchInvoiceInventory;
  summary: ApiWorkbenchPayload["summary"];
};

type ApiWorkbenchGroupsPayload = {
  month: string;
  scope_key?: string;
  zone: WorkbenchZoneId;
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
  read_model_status?: WorkbenchReadModelStatus;
  groups: ApiWorkbenchGroup[];
};

type ApiWorkbenchInvoiceInventory = {
  system_total?: number | null;
  manual_import_total?: number | null;
  workbench_visible_total?: number | null;
  hidden_submitted_etc_total?: number | null;
  extra_etc_total?: number | null;
  etc_summary_batch_count?: number | null;
  oa_attachment_total?: number | null;
};

type ApiWorkbenchOaSyncStatus = {
  status?: string;
  message?: string;
  dirty_scopes?: unknown[];
  dirtyScopes?: unknown[];
  changed_scopes?: unknown[];
  changedScopes?: unknown[];
  last_seen_change_at?: string | null;
  lastSeenChangeAt?: string | null;
  last_synced_at?: string | null;
  lastSyncedAt?: string | null;
  lag_seconds?: number | null;
  lagSeconds?: number | null;
  failed_event_count?: number | null;
  failedEventCount?: number | null;
  version?: number | null;
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
  bank_transaction_tags?: Parameters<typeof mapBankTransactionTagDictionary>[0];
  pending_invoice_tag_groups?: {
    version?: number | string | null;
    groups?: Record<string, { tag_codes?: unknown[] | null } | unknown[] | null> | null;
    requires_invoice?: unknown[];
    bank_statement_as_invoice?: unknown[];
    no_invoice_required?: unknown[];
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
  group_type: "auto_closed" | "manual_confirmed" | "candidate" | "source_linked" | "processed_exception" | "open_exception" | (string & {});
  match_confidence: "high" | "medium" | "low";
  reason: string;
  relation_mode?: string | null;
  display_mode?: string | null;
  default_collapsed?: boolean | null;
  summary_row?: ApiWorkbenchRow | null;
  row_counts?: Partial<Record<WorkbenchRecordType, number | string | null>> | null;
  collapsed_rows?: Partial<Record<WorkbenchRecordType, ApiWorkbenchRow[]>> | null;
  collapsed_row_counts?: Partial<Record<WorkbenchRecordType, number | string | null>> | null;
  oa_rows: ApiWorkbenchRow[];
  bank_rows: ApiWorkbenchRow[];
  invoice_rows: ApiWorkbenchRow[];
  can_withdraw?: boolean;
  relation_note?: string | null;
  amount_check?: ApiWorkbenchRelationAmountCheck | null;
  special_metadata?: Record<string, unknown> | null;
  processed_exception_summary?: Record<string, unknown> | null;
};

type ApiWorkbenchRelationAmountCheck = {
  status?: string | null;
  direction?: string | null;
  bank_amount?: string | number | null;
  bankAmount?: string | number | null;
  oa_amount?: string | number | null;
  oaAmount?: string | number | null;
  amount_delta?: string | number | null;
  amountDelta?: string | number | null;
  requires_note?: boolean | null;
  requiresNote?: boolean | null;
};

const WORKBENCH_EXCEPTION_APPLY_TIMEOUT_MS = 12_000;

type ApiWorkbenchAmountSummary = {
  before?: {
    oa_total?: string | null;
    bank_total?: string | null;
    invoice_total?: string | null;
  };
  after?: {
    oa_total?: string | null;
    bank_total?: string | null;
    invoice_total?: string | null;
  };
  status?: "matched" | "mismatch" | "unknown";
  direction?: "payment" | "receipt" | "unknown";
  mismatch_fields?: string[];
};

type ApiWorkbenchRelationPreview = {
  operation?: "confirm_link" | "withdraw_link";
  can_submit?: boolean;
  requires_note?: boolean;
  message?: string;
  before?: {
    groups?: ApiWorkbenchGroup[];
  };
  after?: {
    groups?: ApiWorkbenchGroup[];
  };
  amount_summary?: ApiWorkbenchAmountSummary;
};

type ApiWorkbenchActionResult = {
  success: boolean;
  action: string;
  month: string;
  affected_row_ids: string[];
  case_id?: string;
  exception_case_id?: string;
  exception_case_ids?: string[];
  updated_rows?: Array<{ id: string }>;
  affectedMonths?: unknown[];
  affected_months?: unknown[];
  changedScopes?: unknown[];
  changed_scopes?: unknown[];
  message: string;
};

type ApiWorkbenchExceptionScenario = {
  business_line?: string;
  businessLine?: string;
  scenario_code?: string;
  scenarioCode?: string;
  scenario_label?: string;
  scenarioLabel?: string;
  confidence?: string;
  required_objects?: unknown[];
  requiredObjects?: unknown[];
  amount_relation?: string;
  amountRelation?: string;
};

type ApiWorkbenchExceptionAmountSummary = {
  oa_total?: unknown;
  oaTotal?: unknown;
  bank_expense_total?: unknown;
  bankExpenseTotal?: unknown;
  bank_income_total?: unknown;
  bankIncomeTotal?: unknown;
  input_invoice_total?: unknown;
  inputInvoiceTotal?: unknown;
  output_invoice_total?: unknown;
  outputInvoiceTotal?: unknown;
  relation?: unknown;
  expense_relation?: unknown;
  expenseRelation?: unknown;
  income_relation?: unknown;
  incomeRelation?: unknown;
};

type ApiWorkbenchExceptionAction = {
  action_code?: string;
  actionCode?: string;
  label?: string;
  result_status?: string;
  resultStatus?: string;
  required_fields?: unknown[];
  requiredFields?: unknown[];
  description?: string;
};

type ApiWorkbenchExceptionWarning = {
  code?: string;
  severity?: string;
  message?: string;
  label?: string;
};

type ApiWorkbenchExceptionCandidateEvidence = {
  id?: string;
  label?: string;
  detail?: string;
  metadata?: Record<string, unknown>;
};

type ApiWorkbenchExceptionPreview = {
  rule_version?: string;
  ruleVersion?: string;
  scenario?: ApiWorkbenchExceptionScenario;
  amount_summary?: ApiWorkbenchExceptionAmountSummary;
  amountSummary?: ApiWorkbenchExceptionAmountSummary;
  automatic_actions?: ApiWorkbenchExceptionAction[];
  automaticActions?: ApiWorkbenchExceptionAction[];
  available_actions?: ApiWorkbenchExceptionAction[];
  availableActions?: ApiWorkbenchExceptionAction[];
  warnings?: ApiWorkbenchExceptionWarning[];
  workflow_projection?: Record<string, unknown>;
  workflowProjection?: Record<string, unknown>;
  candidate_evidence?: ApiWorkbenchExceptionCandidateEvidence[];
  candidateEvidence?: ApiWorkbenchExceptionCandidateEvidence[];
  can_apply?: boolean;
  canApply?: boolean;
};

type ApiWorkbenchExceptionApplyResult = {
  success?: boolean;
  case?: Record<string, unknown> | null;
  pair_relation?: Record<string, unknown> | null;
  pairRelation?: Record<string, unknown> | null;
  updated_rows?: Array<Record<string, unknown>>;
  updatedRows?: Array<Record<string, unknown>>;
  affected_row_ids?: unknown[];
  affectedRowIds?: unknown[];
  workbench_refresh_required?: boolean;
  workbenchRefreshRequired?: boolean;
  message?: string;
};

type ConfirmLinkPayload = {
  month: string;
  rowIds: string[];
  caseId?: string;
  note?: string;
};

type WithdrawLinkPayload = {
  month: string;
  rowIds: string[];
  note?: string;
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

type ConfirmPersonalAdvanceRepaymentPayload = {
  month: string;
  rowIds: string[];
  note?: string;
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

type ConfirmCashPassThroughPayload = {
  month: string;
  rowIds: string[];
  cashAmount?: string;
  note?: string;
};

type ConfirmCashTicketPurchasePayload = {
  month: string;
  rowIds: string[];
  cashAmount: string;
  ticketCostAmount: string;
  projectId?: string;
  projectName?: string;
  expenseType?: string;
  expenseContent?: string;
  note?: string;
};

type CancelCashSpecialPayload = {
  month: string;
  rowIds: string[];
  note?: string;
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
  bankTransactionTags?: BankTransactionTagDictionary;
  pendingInvoiceTagGroups?: PendingInvoiceTagGroups;
};

type ApiWorkbenchSettingsDataResetResult = {
  action: WorkbenchSettingsDataResetAction;
  status: string;
  job_id?: string;
  cleared_collections?: string[];
  deleted_counts?: Record<string, number>;
  protected_targets?: string[];
  rebuild_status?: string;
  message?: string;
};

type ApiWorkbenchSettingsDataResetJob = {
  job_id?: string;
  action?: WorkbenchSettingsDataResetAction;
  status?: string;
  phase?: string;
  message?: string;
  current?: number;
  total?: number;
  percent?: number;
  result?: ApiWorkbenchSettingsDataResetResult | null;
  error?: string | null;
};

type ApiWorkbenchSettingsDataResetJobResponse = {
  job?: ApiWorkbenchSettingsDataResetJob | null;
};

type WorkbenchSettingsDataResetPayload = {
  action: WorkbenchSettingsDataResetAction;
  oaPassword: string;
  onProgress?: (job: WorkbenchSettingsDataResetJob) => void;
  pollIntervalMs?: number;
};

type ApiWorkbenchSettingsProjectMutationResult = {
  settings: ApiWorkbenchSettings;
};

type ApiWorkbenchSettingsProjectSyncResult = {
  settings: ApiWorkbenchSettings;
};

type ApiOaManualSearchItem = {
  date?: string | null;
  amount?: string | null;
  content?: string | null;
  project_name?: string | null;
  reason?: string | null;
  attachment_file_count?: number | null;
  importable_invoice_count?: number | null;
};

type ApiOaManualSearchRow = {
  row_id?: string | null;
  oa_no?: string | null;
  applicant?: string | null;
  application_date?: string | null;
  form_type?: string | null;
  form_type_label?: string | null;
  status?: string | null;
  status_label?: string | null;
  project_name?: string | null;
  reason?: string | null;
  amount?: string | null;
  attachment_file_count?: number | null;
  importable_invoice_count?: number | null;
  unrecognized_attachment_count?: number | null;
  import_status?: string | null;
  imported_at?: string | null;
  can_import?: boolean | null;
  disabled_reason?: string | null;
  items?: ApiOaManualSearchItem[] | null;
};

type ApiOaManualSearchResult = {
  rows?: ApiOaManualSearchRow[] | null;
  total?: number | null;
  page?: number | null;
  page_size?: number | null;
};

type ApiOaManualAttachmentRefreshResult = {
  rows?: Array<{
    row_id?: string | null;
    attachment_file_count?: number | null;
    importable_invoice_count?: number | null;
    unrecognized_attachment_count?: number | null;
  }> | null;
  errors?: Array<Record<string, unknown>> | null;
};

type ApiOaManualImportResult = {
  imported?: string[] | null;
  already_imported?: string[] | null;
  failed?: Array<Record<string, unknown>> | null;
  rows?: ApiOaManualSearchRow[] | null;
};

type ApiOaManualImportList = {
  row_ids?: string[] | null;
  entries?: Array<{
    row_id?: string | null;
    actor_id?: string | null;
    imported_at?: string | null;
    source?: string | null;
    audit?: Record<string, unknown> | null;
  }> | null;
};

type WorkbenchSettingsProjectCreatePayload = {
  actorId: string;
  projectCode: string;
  projectName: string;
};

function toDisplayValue(value: unknown, fallback = "--") {
  if (typeof value === "string") {
    return value.trim().length > 0 ? value : fallback;
  }
  if (value === null || value === undefined) {
    return fallback;
  }
  return String(value);
}

function toWorkbenchAmountDisplayValue(value: unknown, fallback = "--") {
  const displayValue = toDisplayValue(value, fallback);
  if (displayValue === fallback || displayValue === "--" || displayValue === "—") {
    return displayValue;
  }
  const normalizedGrouping = displayValue.replace(/,/g, "");
  if (!/^-?\d+(\.\d+)?$/.test(normalizedGrouping)) {
    return displayValue;
  }
  const [integerPart, decimalPart] = normalizedGrouping.split(".");
  if (decimalPart === undefined) {
    return integerPart;
  }
  const trimmedDecimal = decimalPart.replace(/0+$/, "");
  return trimmedDecimal ? `${integerPart}.${trimmedDecimal}` : integerPart;
}

function toBankAmountDisplayValue(value: unknown, fallback = "--") {
  return toWorkbenchAmountDisplayValue(value, fallback);
}

function toWorkbenchDateTimeDisplayValue(value: unknown, fallback = "--") {
  const displayValue = toDisplayValue(value, fallback);
  if (displayValue === fallback || displayValue === "--" || displayValue === "—") {
    return displayValue;
  }
  const normalizedValue = displayValue.trim();
  const isoDateTimeMatch = normalizedValue.match(
    /^(\d{4}-\d{2}-\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$/,
  );
  if (isoDateTimeMatch) {
    return `${isoDateTimeMatch[1]} ${isoDateTimeMatch[2]}`;
  }
  return normalizedValue;
}

function firstNonPlaceholderDisplayValue(...values: unknown[]) {
  for (const value of values) {
    const displayValue = toDisplayValue(value, "");
    if (displayValue && displayValue !== "--" && displayValue !== "—") {
      return displayValue;
    }
  }
  return undefined;
}

function mapRelationAmountCheck(value: ApiWorkbenchRelationAmountCheck | null | undefined): WorkbenchAmountCheck | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }

  return {
    status: toDisplayValue(value.status, "unknown") as WorkbenchAmountCheck["status"],
    direction: toDisplayValue(value.direction, "unknown") as WorkbenchAmountCheck["direction"],
    bankAmount: toDisplayValue(value.bank_amount ?? value.bankAmount),
    oaAmount: toDisplayValue(value.oa_amount ?? value.oaAmount),
    amountDelta: toDisplayValue(value.amount_delta ?? value.amountDelta),
    requiresNote: value.requires_note === true || value.requiresNote === true,
  };
}

function mapProcessedExceptionSummary(value: unknown) {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const payload = value as Record<string, unknown>;
  const scenario = payload.scenario && typeof payload.scenario === "object"
    ? payload.scenario as Record<string, unknown>
    : undefined;
  const resolution = payload.resolution && typeof payload.resolution === "object"
    ? payload.resolution as Record<string, unknown>
    : undefined;
  const displayTags = Array.isArray(payload.display_tags)
    ? payload.display_tags.map((item) => String(item).trim()).filter(Boolean)
    : undefined;
  return {
    scenario,
    resolution,
    detailNote: toDisplayValue(payload.detail_note ?? payload.detailNote, "") || undefined,
    displayTags,
  };
}

function toDetailDisplayValue(value: unknown) {
  if (typeof value === "string") {
    return toDisplayValue(value, "—");
  }
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function mapOaDetailSearchValues(detailFields: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(detailFields).map(([label, value]) => [`__detail:${label}`, toDetailDisplayValue(value)]),
  );
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

function isNoOaSummaryRow(row: ApiWorkbenchRow) {
  return row.source_kind === "no_oa_bank_batch_summary";
}

function hasNoOaSourceBatchId(row: ApiWorkbenchRow) {
  const sourceBatchId = row.special_metadata?.source_batch_id;
  return typeof sourceBatchId === "string" && sourceBatchId.trim().length > 0;
}

function normalizeRowAvailableActions(row: ApiWorkbenchRow) {
  const actions = row.available_actions ?? [];
  if (!isNoOaSummaryRow(row)) {
    return actions;
  }
  if (!hasNoOaSourceBatchId(row)) {
    return actions.filter((action) => action === "detail");
  }
  return actions.includes("withdraw_no_oa_batch")
    ? actions
    : [...actions, "withdraw_no_oa_batch"];
}

function groupHasNoOaWithdrawAction(group: ApiWorkbenchGroup) {
  return group.summary_row ? normalizeRowAvailableActions(group.summary_row).includes("withdraw_no_oa_batch") : false;
}

function mapGroupType(groupType: ApiWorkbenchGroup["group_type"]): WorkbenchGroupType {
  const normalizedGroupType = String(groupType);
  if (
    normalizedGroupType === "auto_closed"
    || normalizedGroupType === "manual_confirmed"
    || normalizedGroupType === "candidate"
  ) {
    return normalizedGroupType as WorkbenchGroupType;
  }
  return "candidate";
}

function rowActionVariant(row: ApiWorkbenchRow, availableActions: string[]): WorkbenchActionVariant {
  if (row.type === "bank") {
    if (availableActions.length === 0 || availableActions.every((action) => action === "detail")) {
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
  if (row.source_kind === "no_oa_bank_batch_summary") {
    return "免OA批次";
  }
  if (row.type === "bank") {
    return row.debit_amount ? "支取" : "收入";
  }
  if (row.source_kind === "etc_invoice_summary") {
    return "ETC批次";
  }
  if (row.source_kind === "etc_invoice" || row.tags?.includes("ETC")) {
    return "ETC票";
  }
  if (row.source_kind === "oa_attachment_invoice") {
    return "OA附件";
  }
  if (row.source_kind === "oa_attachment_payment_receipt") {
    return "付款凭证";
  }
  if (row.source_kind === "oa_attachment_unknown") {
    return "未识别附件";
  }
  return row.invoice_type?.includes("销") ? "销项票" : "进项票";
}

function rowAmount(row: ApiWorkbenchRow) {
  if (row.type === "bank") {
    return resolveBankAmount(row);
  }
  return toWorkbenchAmountDisplayValue(row.amount);
}

function rowCounterparty(row: ApiWorkbenchRow) {
  if (row.type === "invoice") {
    return toDisplayValue(row.buyer_name ?? row.seller_name);
  }
  return toDisplayValue(row.counterparty_name);
}

const visibleBankTextFieldLabels = new Set(["摘要", "备注", "用途", "交易用途", "客户附言"]);

function mapBankTextFields(row: ApiWorkbenchRow) {
  if (!Array.isArray(row.bank_text_fields)) {
    return [];
  }

  const seenLabels = new Set<string>();
  return row.bank_text_fields
    .map((field) => ({
      label: String(field?.label ?? "").trim(),
      value: String(field?.value ?? "").trim(),
    }))
    .filter((field) => {
      if (!field.label || !field.value || !visibleBankTextFieldLabels.has(field.label)) {
        return false;
      }
      if (seenLabels.has(field.label)) {
        return false;
      }
      seenLabels.add(field.label);
      return true;
    });
}

function formatBankTextFieldsForNote(row: ApiWorkbenchRow) {
  const fields = mapBankTextFields(row);
  if (fields.length === 0) {
    return toDisplayValue(row.remark);
  }
  return fields.map((field) => `${field.label}：${field.value}`).join("\n");
}

function mapTableValues(row: ApiWorkbenchRow): Record<string, string> {
  const relationLabel = rowRelation(row)?.label ?? "待处理";

  if (row.type === "oa") {
    const detailFields = row.detail_fields ?? {};
    const summaryFields = row.summary_fields ?? {};
    return {
      applicant: toDisplayValue(row.applicant),
      applicationTime: toWorkbenchDateTimeDisplayValue(
        detailFields["审批完成时间"]
          ?? detailFields["申请日期"]
          ?? detailFields["创建时间"]
          ?? summaryFields["审批完成时间"]
          ?? summaryFields["申请日期"]
          ?? summaryFields["创建时间"],
      ),
      projectName: toDisplayValue(row.project_name_display ?? row.project_name),
      applicationType: toDisplayValue(row.apply_type),
      amount: toWorkbenchAmountDisplayValue(row.amount),
      counterparty: toDisplayValue(row.counterparty_name),
      reason: toDisplayValue(row.reason),
      reconciliationStatus: relationLabel,
      ...mapOaDetailSearchValues(detailFields),
    };
  }

  if (row.type === "bank") {
    const direction = resolveBankDirection(row);
    return {
      transactionTime: toWorkbenchDateTimeDisplayValue(row.trade_time),
      direction,
      amount: resolveBankAmount(row),
      debitAmount: toBankAmountDisplayValue(row.debit_amount),
      creditAmount: toBankAmountDisplayValue(row.credit_amount),
      counterparty: toDisplayValue(row.counterparty_name),
      paymentAccount: toDisplayValue(row.payment_account_label),
      invoiceRelationStatus: relationLabel,
      paymentOrReceiptTime: toWorkbenchDateTimeDisplayValue(row.pay_receive_time),
      note: formatBankTextFieldsForNote(row),
      loanRepaymentDate: toDisplayValue(row.repayment_date),
    };
  }

  const detailFields = row.detail_fields ?? {};
  const summaryFields = row.summary_fields ?? {};
  return {
    sellerTaxId: toDisplayValue(row.seller_tax_no),
    sellerName: toDisplayValue(row.seller_name),
    buyerTaxId: toDisplayValue(row.buyer_tax_no),
    buyerName: toDisplayValue(row.buyer_name),
    invoiceCode: toDisplayValue(firstNonPlaceholderDisplayValue(detailFields["发票代码"], row.invoice_code, summaryFields["发票代码"])),
    invoiceNo: toDisplayValue(firstNonPlaceholderDisplayValue(
      detailFields["发票号码"],
      row.invoice_no,
      detailFields["数电发票号码"],
      row.digital_invoice_no,
      summaryFields["发票号码"],
      summaryFields["数电发票号码"],
    )),
    digitalInvoiceNo: toDisplayValue(firstNonPlaceholderDisplayValue(
      detailFields["数电发票号码"],
      row.digital_invoice_no,
      summaryFields["数电发票号码"],
    )),
    issueDate: toWorkbenchDateTimeDisplayValue(row.issue_date),
    amount: toWorkbenchAmountDisplayValue(row.amount),
    taxRate: toDisplayValue(row.tax_rate),
    taxAmount: toWorkbenchAmountDisplayValue(row.tax_amount),
    grossAmount: toWorkbenchAmountDisplayValue(row.total_with_tax),
    invoiceType: toDisplayValue(row.invoice_type),
  };
}

function mapDetailFields(detailFields?: Record<string, unknown>): WorkbenchDetailField[] {
  if (!detailFields) {
    return [];
  }

  const seenLabels = new Set<string>();
  return Object.entries(detailFields)
    .filter(([label]) => label !== "资金方向")
    .map(([label, value]) => ({
      label: normalizeDetailFieldLabel(label),
      value: toDetailDisplayValue(value),
    }))
    .filter((field) => {
      if (seenLabels.has(field.label)) {
        return false;
      }
      seenLabels.add(field.label);
      return true;
    });
}

function normalizeDetailFieldLabel(label: string) {
  const normalizedLabels: Record<string, string> = {
    和发票关联情况: "和发票OA关联情况",
    derived_from_oa_id: "来源OA单号",
    source_oa_id: "来源OA单号",
    source_oa_row_id: "来源OA单号",
    source_expense_row_index: "来源OA明细行号",
    source_expense_item_id: "来源付款项ID",
    source_attachment_name: "来源附件文件名",
    attachment_name: "来源附件文件名",
    source_attachment_key: "来源附件Key",
  };
  return normalizedLabels[label] ?? label;
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
  const debitAmount = toBankAmountDisplayValue(row.debit_amount, "");
  if (debitAmount !== "") {
    return debitAmount;
  }
  const creditAmount = toBankAmountDisplayValue(row.credit_amount, "");
  if (creditAmount !== "") {
    return creditAmount;
  }
  return "--";
}

function mapRow(row: ApiWorkbenchRow): WorkbenchRecord {
  const availableActions = normalizeRowAvailableActions(row);
  return {
    id: row.id,
    caseId: row.case_id ?? undefined,
    exceptionCaseId: row.exception_case_id ?? undefined,
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
    actionVariant: rowActionVariant(row, availableActions),
    availableActions,
    tags: Array.isArray(row.tags) ? row.tags.map((tag) => String(tag).trim()).filter(Boolean) : [],
    categoryCode: toDisplayValue(row.category_code, "") || undefined,
    categoryLabel: toDisplayValue(row.category_label, "") || undefined,
    categoryPath: Array.isArray(row.category_path) ? row.category_path.map((item) => String(item).trim()).filter(Boolean) : undefined,
    categorySource: toDisplayValue(row.category_source, "") || undefined,
    bankTextFields: row.type === "bank" ? mapBankTextFields(row) : undefined,
    relationNote: toDisplayValue(row.relation_note, "") || undefined,
    relationAmountCheck: mapRelationAmountCheck(row.relation_amount_check),
    specialMetadata: row.special_metadata && typeof row.special_metadata === "object" ? row.special_metadata : undefined,
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
  const summaryRow = group.summary_row ? mapRow(group.summary_row) : undefined;
  const rowCounts = mapPaneRowCounts(group.row_counts);
  const collapsedRowCounts = mapPaneRowCounts(group.collapsed_row_counts);
  const collapsedRows = group.collapsed_rows && typeof group.collapsed_rows === "object"
    ? {
      oa: (group.collapsed_rows.oa ?? []).map(mapRow),
      bank: (group.collapsed_rows.bank ?? []).map(mapRow),
      invoice: (group.collapsed_rows.invoice ?? []).map(mapRow),
    }
    : undefined;
  return {
    id: group.group_id,
    groupType: mapGroupType(group.group_type),
    matchConfidence: group.match_confidence,
    reason: group.reason,
    relationMode: typeof group.relation_mode === "string" && group.relation_mode.trim()
      ? group.relation_mode.trim() as WorkbenchRelationMode
      : undefined,
    displayMode: typeof group.display_mode === "string" && group.display_mode.trim()
      ? group.display_mode.trim()
      : undefined,
    defaultCollapsed: group.default_collapsed === true ? true : undefined,
    summaryRow,
    rows: {
      oa: group.oa_rows.map(mapRow),
      bank: group.bank_rows.map(mapRow),
      invoice: group.invoice_rows.map(mapRow),
    },
    rowCounts,
    collapsedRows,
    collapsedRowCounts,
    relationNote: toDisplayValue(group.relation_note, "") || undefined,
    amountCheck: mapRelationAmountCheck(group.amount_check),
    specialMetadata: group.special_metadata && typeof group.special_metadata === "object" ? group.special_metadata : undefined,
    processedExceptionSummary: mapProcessedExceptionSummary(group.processed_exception_summary),
    canWithdraw: Boolean(
      group.can_withdraw
      || groupHasNoOaWithdrawAction(group),
    ),
  };
}

function mapPaneRowCounts(counts: ApiWorkbenchGroup["row_counts"]): WorkbenchCandidateGroup["rowCounts"] | undefined {
  if (!counts || typeof counts !== "object") {
    return undefined;
  }
  const mapped: WorkbenchCandidateGroup["rowCounts"] = {};
  (["oa", "bank", "invoice"] as WorkbenchRecordType[]).forEach((paneId) => {
    const count = Number(counts[paneId]);
    if (Number.isFinite(count) && count >= 0) {
      mapped[paneId] = count;
    }
  });
  return Object.keys(mapped).length > 0 ? mapped : undefined;
}

function mapAmountTotals(totals: ApiWorkbenchAmountSummary["before"] | undefined) {
  return {
    oaTotal: toDisplayValue(totals?.oa_total, "-"),
    bankTotal: toDisplayValue(totals?.bank_total, "-"),
    invoiceTotal: toDisplayValue(totals?.invoice_total, "-"),
  };
}

function mapRelationPreview(payload: ApiWorkbenchRelationPreview): WorkbenchRelationPreview {
  const amountSummary = payload.amount_summary ?? {};
  const hasAmountSummary = Boolean(payload.amount_summary);
  return {
    operation: payload.operation === "withdraw_link" ? "withdraw_link" : "confirm_link",
    canSubmit: payload.can_submit !== false,
    requiresNote: Boolean(payload.requires_note),
    message: String(payload.message ?? "").trim(),
    before: {
      groups: (payload.before?.groups ?? []).map(mapGroup),
    },
    after: {
      groups: (payload.after?.groups ?? []).map(mapGroup),
    },
    amountSummary: {
      before: mapAmountTotals(amountSummary.before),
      after: mapAmountTotals(amountSummary.after),
      status: hasAmountSummary
        ? amountSummary.status === "mismatch" || amountSummary.status === "unknown" ? amountSummary.status : "matched"
        : "unknown",
      direction: hasAmountSummary
        ? amountSummary.direction === "receipt" || amountSummary.direction === "unknown" ? amountSummary.direction : "payment"
        : "unknown",
      mismatchFields: (amountSummary.mismatch_fields ?? []).map((field) => String(field)),
    },
  };
}

function cleanWorkbenchExceptionStringList(value: unknown[] | undefined) {
  return (value ?? [])
    .map((item) => String(item).trim())
    .filter(Boolean);
}

function camelizeKey(key: string) {
  return key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase());
}

function camelizeUnknown(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(camelizeUnknown);
  }
  if (!value || typeof value !== "object") {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value).map(([key, entryValue]) => [camelizeKey(key), camelizeUnknown(entryValue)]),
  );
}

function mapWorkbenchExceptionAction(action: ApiWorkbenchExceptionAction): WorkbenchExceptionAction {
  const mapped: WorkbenchExceptionAction = {
    actionCode: String(action.actionCode ?? action.action_code ?? "").trim(),
    label: String(action.label ?? action.actionCode ?? action.action_code ?? "").trim(),
    resultStatus: String(action.resultStatus ?? action.result_status ?? "open").trim() || "open",
    requiredFields: cleanWorkbenchExceptionStringList(action.requiredFields ?? action.required_fields),
  };
  if (typeof action.description === "string" && action.description.trim()) {
    mapped.description = action.description.trim();
  }
  return mapped;
}

function mapWorkbenchExceptionWarning(warning: ApiWorkbenchExceptionWarning): WorkbenchExceptionWarning {
  return {
    code: String(warning.code ?? "").trim(),
    severity: String(warning.severity ?? "warning").trim() || "warning",
    message: String(warning.message ?? warning.label ?? "").trim(),
  };
}

function mapWorkbenchExceptionEvidence(
  evidence: ApiWorkbenchExceptionCandidateEvidence,
): WorkbenchExceptionCandidateEvidence {
  const mapped: WorkbenchExceptionCandidateEvidence = {
    id: typeof evidence.id === "string" && evidence.id.trim() ? evidence.id.trim() : undefined,
    label: String(evidence.label ?? evidence.id ?? "候选证据").trim(),
  };
  if (typeof evidence.detail === "string" && evidence.detail.trim()) {
    mapped.detail = evidence.detail.trim();
  }
  if (evidence.metadata && typeof evidence.metadata === "object") {
    mapped.metadata = camelizeUnknown(evidence.metadata) as Record<string, unknown>;
  }
  return mapped;
}

function mapWorkbenchExceptionPreview(payload: ApiWorkbenchExceptionPreview): WorkbenchExceptionPreview {
  const scenario = payload.scenario ?? {};
  const amountSummary = payload.amountSummary ?? payload.amount_summary ?? {};
  const requiredObjects = cleanWorkbenchExceptionStringList(scenario.requiredObjects ?? scenario.required_objects);
  const mappedScenario = {
    businessLine: String(scenario.businessLine ?? scenario.business_line ?? "").trim(),
    scenarioCode: String(scenario.scenarioCode ?? scenario.scenario_code ?? "").trim(),
    scenarioLabel: String(scenario.scenarioLabel ?? scenario.scenario_label ?? "").trim(),
  };
  if (typeof scenario.confidence === "string" && scenario.confidence.trim()) {
    Object.assign(mappedScenario, { confidence: scenario.confidence.trim() });
  }
  if (requiredObjects.length > 0) {
    Object.assign(mappedScenario, { requiredObjects });
  }
  if (typeof (scenario.amountRelation ?? scenario.amount_relation) === "string") {
    Object.assign(mappedScenario, { amountRelation: String(scenario.amountRelation ?? scenario.amount_relation).trim() });
  }
  const businessLine = mappedScenario.businessLine;
  const relationValue =
    amountSummary.relation
    ?? (businessLine === "income" ? amountSummary.incomeRelation ?? amountSummary.income_relation : undefined)
    ?? (businessLine === "expense" ? amountSummary.expenseRelation ?? amountSummary.expense_relation : undefined)
    ?? amountSummary.expenseRelation
    ?? amountSummary.expense_relation
    ?? amountSummary.incomeRelation
    ?? amountSummary.income_relation;
  return {
    ruleVersion: String(payload.ruleVersion ?? payload.rule_version ?? "").trim(),
    scenario: mappedScenario,
    amountSummary: {
      oaTotal: toDisplayValue(amountSummary.oaTotal ?? amountSummary.oa_total, "0.00"),
      bankExpenseTotal: toDisplayValue(amountSummary.bankExpenseTotal ?? amountSummary.bank_expense_total, "0.00"),
      bankIncomeTotal: toDisplayValue(amountSummary.bankIncomeTotal ?? amountSummary.bank_income_total, "0.00"),
      inputInvoiceTotal: toDisplayValue(amountSummary.inputInvoiceTotal ?? amountSummary.input_invoice_total, "0.00"),
      outputInvoiceTotal: toDisplayValue(amountSummary.outputInvoiceTotal ?? amountSummary.output_invoice_total, "0.00"),
      relation: toDisplayValue(relationValue, "unknown"),
    },
    automaticActions: (payload.automaticActions ?? payload.automatic_actions ?? []).map(mapWorkbenchExceptionAction),
    availableActions: (payload.availableActions ?? payload.available_actions ?? []).map(mapWorkbenchExceptionAction),
    warnings: (payload.warnings ?? []).map(mapWorkbenchExceptionWarning),
    workflowProjection: camelizeUnknown(payload.workflowProjection ?? payload.workflow_projection ?? {}) as Record<string, unknown>,
    candidateEvidence: (payload.candidateEvidence ?? payload.candidate_evidence ?? []).map(mapWorkbenchExceptionEvidence),
    canApply: payload.canApply ?? payload.can_apply ?? true,
  };
}

function mapWorkbenchExceptionApplyResult(
  payload: ApiWorkbenchExceptionApplyResult,
): WorkbenchExceptionApplyResult {
  return {
    success: payload.success === true,
    case: payload.case ?? null,
    pairRelation: payload.pairRelation ?? payload.pair_relation ?? null,
    updatedRows: payload.updatedRows ?? payload.updated_rows ?? [],
    affectedRowIds: (payload.affectedRowIds ?? payload.affected_row_ids ?? []).map((rowId) => String(rowId)),
    workbenchRefreshRequired: payload.workbenchRefreshRequired ?? payload.workbench_refresh_required ?? false,
    message: typeof payload.message === "string" && payload.message.trim() ? payload.message.trim() : undefined,
  };
}

function mapSummary(
  summary: ApiWorkbenchPayload["summary"],
  pairedGroups: WorkbenchCandidateGroup[],
): WorkbenchSummary {
  return {
    oaCount: summary.oa_count,
    bankCount: summary.bank_count,
    invoiceCount: summary.invoice_count,
    pairedCount: countWorkbenchGroupsRows(pairedGroups),
    openCount: summary.open_count,
    exceptionCount: summary.exception_count,
    totalCount: summary.oa_count + summary.bank_count + summary.invoice_count,
  };
}

function mapSummaryCounts(summary: ApiWorkbenchPayload["summary"]): WorkbenchSummary {
  const oaCount = toCount(summary.oa_count);
  const bankCount = toCount(summary.bank_count);
  const invoiceCount = toCount(summary.invoice_count);
  return {
    oaCount,
    bankCount,
    invoiceCount,
    pairedCount: toCount(summary.paired_count),
    openCount: toCount(summary.open_count),
    exceptionCount: toCount(summary.exception_count),
    totalCount: oaCount + bankCount + invoiceCount,
  };
}

function mapReadModelStatus(value: unknown): WorkbenchReadModelStatus {
  return String(value ?? "fresh").trim() as WorkbenchReadModelStatus || "fresh";
}

function mapWorkbenchZonePage(payload: ApiWorkbenchGroupsPayload): WorkbenchZonePageInfo {
  return {
    zone: payload.zone,
    page: toCount(payload.page) || 1,
    pageSize: toCount(payload.page_size) || 50,
    total: toCount(payload.total),
    hasMore: payload.has_more === true,
    readModelStatus: mapReadModelStatus(payload.read_model_status),
  };
}

function mapInventoryCount(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapInvoiceInventory(inventory?: ApiWorkbenchInvoiceInventory): WorkbenchInvoiceInventory {
  return {
    systemTotal: mapInventoryCount(inventory?.system_total),
    manualImportTotal: mapInventoryCount(inventory?.manual_import_total),
    workbenchVisibleTotal: mapInventoryCount(inventory?.workbench_visible_total),
    hiddenSubmittedEtcTotal: mapInventoryCount(inventory?.hidden_submitted_etc_total),
    extraEtcTotal: mapInventoryCount(inventory?.extra_etc_total),
    etcSummaryBatchCount: mapInventoryCount(inventory?.etc_summary_batch_count),
    oaAttachmentTotal: mapInventoryCount(inventory?.oa_attachment_total),
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

function cleanSettingsStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];
}

function mapPendingInvoiceTagGroups(value: ApiWorkbenchSettings["pending_invoice_tag_groups"]): PendingInvoiceTagGroups {
  const groups = value?.groups;
  if (groups && typeof groups === "object") {
    const codesFor = (groupId: string) => {
      const group = groups[groupId];
      if (Array.isArray(group)) {
        return cleanSettingsStringList(group);
      }
      if (group && typeof group === "object" && "tag_codes" in group) {
        return cleanSettingsStringList(group.tag_codes);
      }
      return [];
    };
    return {
      requiresInvoice: codesFor("requires_invoice"),
      bankStatementAsInvoice: codesFor("bank_statement_as_invoice"),
      noInvoiceRequired: codesFor("no_invoice_required"),
    };
  }
  return {
    requiresInvoice: cleanSettingsStringList(value?.requires_invoice),
    bankStatementAsInvoice: cleanSettingsStringList(value?.bank_statement_as_invoice),
    noInvoiceRequired: cleanSettingsStringList(value?.no_invoice_required),
  };
}

function serializeBankTransactionTags(value: BankTransactionTagDictionary | undefined) {
  if (!value) {
    return undefined;
  }
  return {
    version: value.version,
    definitions: value.tags.map((tag) => ({
      code: tag.code,
      label: tag.label,
      path: tag.path,
      status: tag.status,
      source: tag.source,
    })),
  };
}

function serializePendingInvoiceTagGroups(value: PendingInvoiceTagGroups | undefined) {
  if (!value) {
    return undefined;
  }
  return {
    groups: {
      requires_invoice: { tag_codes: value.requiresInvoice },
      bank_statement_as_invoice: { tag_codes: value.bankStatementAsInvoice },
      no_invoice_required: { tag_codes: value.noInvoiceRequired },
    },
  };
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
    bankTransactionTags: mapBankTransactionTagDictionary(payload.bank_transaction_tags) ?? { version: 0, tags: [] },
    pendingInvoiceTagGroups: mapPendingInvoiceTagGroups(payload.pending_invoice_tag_groups),
  };
}

function toCount(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function mapOaManualSearchItem(item: ApiOaManualSearchItem): OaManualSearchItem {
  return {
    date: toDisplayValue(item.date),
    amount: toDisplayValue(item.amount),
    content: toDisplayValue(item.content),
    projectName: toDisplayValue(item.project_name),
    reason: toDisplayValue(item.reason),
    attachmentFileCount: toCount(item.attachment_file_count),
    importableInvoiceCount: toCount(item.importable_invoice_count),
  };
}

function mapOaManualSearchRow(row: ApiOaManualSearchRow): OaManualSearchRow {
  return {
    rowId: toDisplayValue(row.row_id, ""),
    oaNo: toDisplayValue(row.oa_no),
    applicant: toDisplayValue(row.applicant),
    applicationDate: toDisplayValue(row.application_date),
    formType: toDisplayValue(row.form_type, ""),
    formTypeLabel: toDisplayValue(row.form_type_label),
    status: toDisplayValue(row.status, ""),
    statusLabel: toDisplayValue(row.status_label),
    projectName: toDisplayValue(row.project_name),
    reason: toDisplayValue(row.reason),
    amount: toDisplayValue(row.amount, "0.00"),
    attachmentFileCount: toCount(row.attachment_file_count),
    importableInvoiceCount: toCount(row.importable_invoice_count),
    unrecognizedAttachmentCount: toCount(row.unrecognized_attachment_count),
    importStatus: toDisplayValue(row.import_status, "not_imported"),
    importedAt: row.imported_at ?? null,
    canImport: row.can_import === true,
    disabledReason: toDisplayValue(row.disabled_reason, ""),
    items: Array.isArray(row.items) ? row.items.map(mapOaManualSearchItem) : [],
  };
}

function mapOaManualSearchResult(payload: ApiOaManualSearchResult): OaManualSearchResult {
  return {
    rows: (payload.rows ?? []).map(mapOaManualSearchRow).filter((row) => row.rowId.length > 0),
    total: toCount(payload.total),
    page: toCount(payload.page),
    pageSize: toCount(payload.page_size),
  };
}

function buildManualSearchQuery(filters: OaManualSearchFilters) {
  const params = new URLSearchParams();
  const query = String(filters.query ?? "").trim();
  if (query) {
    params.set("q", query);
  }
  if (filters.formTypes && filters.formTypes.length > 0) {
    params.set("form_types", filters.formTypes.join(","));
  }
  if (filters.statuses && filters.statuses.length > 0) {
    params.set("statuses", filters.statuses.join(","));
  }
  if (filters.dateFrom) {
    params.set("date_from", filters.dateFrom);
  }
  if (filters.dateTo) {
    params.set("date_to", filters.dateTo);
  }
  params.set("page", String(filters.page ?? 0));
  params.set("page_size", String(filters.pageSize ?? 20));
  return params.toString();
}

const WORKBENCH_API_ERROR_MESSAGES: Record<string, string> = {
  unknown_bank_transaction_tag: "待找发票筛选引用了不存在的银行明细标签，请刷新后重新选择。",
  archived_bank_transaction_tag: "该银行明细标签已停用，不能用于新的待找发票筛选。",
  duplicate_pending_invoice_tag_mapping: "同一个银行明细标签不能同时归入多个待找发票筛选。",
  bank_transaction_tag_in_use_by_pending_invoice_filter: "该银行明细标签仍被待找发票筛选使用，请先从待找发票筛选中移除。",
  bank_transaction_tags_version_conflict: "银行明细标签已被其他页面更新，请刷新后重新保存。",
};

function resolveWorkbenchApiErrorMessage(payload: unknown, rawText: string) {
  if (payload && typeof payload === "object") {
    const errorCode = String((payload as { error?: unknown }).error ?? "").trim();
    if (errorCode && WORKBENCH_API_ERROR_MESSAGES[errorCode]) {
      return WORKBENCH_API_ERROR_MESSAGES[errorCode];
    }
    const message = String((payload as { message?: unknown }).message ?? "").trim();
    if (message) {
      return message;
    }
    if (errorCode) {
      return errorCode;
    }
  }
  return rawText.trim() || "request failed";
}

function withWorkbenchAuthHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(apiUrl(url), {
    ...init,
    credentials: init.credentials ?? "include",
    headers: withWorkbenchAuthHeaders(init.headers),
  });
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
    throw new Error(resolveWorkbenchApiErrorMessage(payload, rawText));
  }
  return ((payload ?? {}) as T);
}

async function requestJsonWithTimeout<T>(url: string, init: RequestInit = {}, timeoutMs: number) {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await requestJson<T>(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (
      (error instanceof DOMException && error.name === "AbortError")
      || (error instanceof Error && error.name === "AbortError")
    ) {
      throw new Error("异常处理提交超时");
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
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

    xhr.open("GET", apiUrl(url), true);
    xhr.withCredentials = true;
    for (const [key, value] of withWorkbenchAuthHeaders()) {
      xhr.setRequestHeader(key, value);
    }
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

function cleanOaSyncScopeList(value: unknown[] | undefined) {
  return Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : [];
}

export async function fetchWorkbenchOaSyncStatus(signal?: AbortSignal): Promise<WorkbenchOaSyncStatus> {
  const payload = await requestJson<ApiWorkbenchOaSyncStatus>("/api/oa-sync/status", { method: "GET", signal });
  const status = String(payload.status ?? "synced").trim() || "synced";
  return {
    status,
    message: String(payload.message ?? (status === "refreshing" ? "OA 正在同步" : "OA 已同步")).trim(),
    dirtyScopes: cleanOaSyncScopeList(payload.dirtyScopes ?? payload.dirty_scopes),
    changedScopes: cleanOaSyncScopeList(payload.changedScopes ?? payload.changed_scopes),
    lastSeenChangeAt: payload.lastSeenChangeAt ?? payload.last_seen_change_at ?? null,
    lastSyncedAt: payload.lastSyncedAt ?? payload.last_synced_at ?? null,
    lagSeconds: typeof payload.lagSeconds === "number"
      ? payload.lagSeconds
      : typeof payload.lag_seconds === "number"
        ? payload.lag_seconds
        : null,
    failedEventCount: typeof payload.failedEventCount === "number"
      ? payload.failedEventCount
      : typeof payload.failed_event_count === "number"
        ? payload.failed_event_count
        : 0,
    version: typeof payload.version === "number" ? payload.version : null,
  };
}

function workbenchGroupsUrl(
  month: string,
  zone: WorkbenchZoneId,
  page: number,
  pageSize: number,
  query: WorkbenchGroupsPageQuery = {},
) {
  const params = new URLSearchParams({
    month,
    zone,
    page: String(page),
    page_size: String(pageSize),
  });
  const search = String(query.search ?? "").trim();
  const status = String(query.status ?? "").trim();
  const sourceKind = String(query.sourceKind ?? "").trim();
  const sort = String(query.sort ?? "").trim();
  const detailLevel = query.detailLevel === "full" ? "full" : query.detailLevel === "summary" ? "summary" : "";
  if (search) {
    params.set("search", search);
  }
  if (status) {
    params.set("status", status);
  }
  if (sourceKind) {
    params.set("source_kind", sourceKind);
  }
  if (sort) {
    params.set("sort", sort);
  }
  if (detailLevel) {
    params.set("detail_level", detailLevel);
  }
  return `/api/workbench/groups?${params.toString()}`;
}

export async function fetchWorkbenchGroupsPage(
  month: string,
  zone: WorkbenchZoneId,
  page: number,
  pageSize = 50,
  signal?: AbortSignal,
  query: WorkbenchGroupsPageQuery = {},
): Promise<WorkbenchGroupsPageResult> {
  const payload = await requestJson<ApiWorkbenchGroupsPayload>(workbenchGroupsUrl(month, zone, page, pageSize, query), {
    method: "GET",
    signal,
  });
  return {
    zone: payload.zone,
    groups: payload.groups.map(mapGroup),
    page: mapWorkbenchZonePage(payload),
  };
}

export async function fetchWorkbenchGroupDetail(
  month: string,
  zone: WorkbenchZoneId,
  groupId: string,
  signal?: AbortSignal,
): Promise<WorkbenchCandidateGroup> {
  const params = new URLSearchParams({
    month,
    zone,
    group_id: groupId,
  });
  const payload = await requestJson<{
    group: ApiWorkbenchGroup;
  }>(`/api/workbench/groups/detail?${params.toString()}`, {
    method: "GET",
    signal,
  });
  return mapGroup(payload.group);
}

export async function fetchWorkbenchInitialPage(
  month: string,
  signal?: AbortSignal,
  onProgress?: (progress: WorkbenchBootstrapProgress) => void,
  zoneQueries: Partial<Record<WorkbenchZoneId, WorkbenchGroupsPageQuery>> = {},
): Promise<WorkbenchInitialPageResult> {
  onProgress?.({
    label: "加载工作台汇总",
    loadedBytes: 0,
    totalBytes: 0,
    percent: 20,
    indeterminate: false,
  });
  const summary = await requestJson<ApiWorkbenchSummaryPayload>(`/api/workbench/summary?month=${month}`, {
    method: "GET",
    signal,
  });
  onProgress?.({
    label: "加载首屏候选组",
    loadedBytes: 0,
    totalBytes: 0,
    percent: 55,
    indeterminate: false,
  });
  const [pairedPage, openPage] = await Promise.all([
    fetchWorkbenchGroupsPage(month, "paired", 1, 50, signal, { ...zoneQueries.paired, detailLevel: "summary" }),
    fetchWorkbenchGroupsPage(month, "open", 1, 50, signal, { ...zoneQueries.open, detailLevel: "summary" }),
  ]);
  onProgress?.({
    label: "关联台数据已加载完成",
    loadedBytes: 0,
    totalBytes: 0,
    percent: 100,
    indeterminate: false,
  });

  return {
    data: {
      month: summary.month,
      oaStatus: mapOaStatus(summary.oa_status),
      summary: mapSummaryCounts(summary.summary),
      invoiceInventory: mapInvoiceInventory(summary.invoice_inventory),
      paired: {
        groups: pairedPage.groups,
      },
      open: {
        groups: openPage.groups,
      },
    },
    pages: {
      paired: pairedPage.page,
      open: openPage.page,
    },
  };
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

  const pairedGroups = payload.paired.groups.map(mapGroup);
  const openGroups = payload.open.groups.map(mapGroup);

  return {
    month: payload.month,
    oaStatus: mapOaStatus(payload.oa_status),
    summary: mapSummary(payload.summary, pairedGroups),
    invoiceInventory: mapInvoiceInventory(payload.invoice_inventory),
    paired: {
      groups: pairedGroups,
    },
    open: {
      groups: openGroups,
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

function clampPercent(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
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
      bank_transaction_tags: serializeBankTransactionTags(settings.bankTransactionTags),
      pending_invoice_tag_groups: serializePendingInvoiceTagGroups(settings.pendingInvoiceTagGroups),
    }),
  });
  return mapWorkbenchSettings(payload);
}

export async function searchManualOaImports(
  filters: OaManualSearchFilters,
  signal?: AbortSignal,
): Promise<OaManualSearchResult> {
  const query = buildManualSearchQuery(filters);
  const payload = await requestJson<ApiOaManualSearchResult>(
    `/api/workbench/settings/oa/manual-search?${query}`,
    { method: "GET", signal },
  );
  return mapOaManualSearchResult(payload);
}

export async function refreshManualOaImportAttachments(
  rowIds: string[],
): Promise<OaManualAttachmentRefreshResult> {
  const payload = await requestJson<ApiOaManualAttachmentRefreshResult>(
    "/api/workbench/settings/oa/manual-search/refresh-attachments",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ row_ids: rowIds }),
    },
  );
  return {
    rows: (payload.rows ?? []).map((row) => ({
      rowId: toDisplayValue(row.row_id, ""),
      attachmentFileCount: toCount(row.attachment_file_count),
      importableInvoiceCount: toCount(row.importable_invoice_count),
      unrecognizedAttachmentCount: toCount(row.unrecognized_attachment_count),
    })).filter((row) => row.rowId.length > 0),
    errors: payload.errors ?? [],
  };
}

export async function importManualOaRows(rowIds: string[]): Promise<OaManualImportResult> {
  const payload = await requestJson<ApiOaManualImportResult>(
    "/api/workbench/settings/oa/manual-imports",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        row_ids: rowIds,
        actor_id: "settings_manual_import",
      }),
    },
  );
  return {
    imported: (payload.imported ?? []).map((rowId) => String(rowId)),
    alreadyImported: (payload.already_imported ?? []).map((rowId) => String(rowId)),
    failed: payload.failed ?? [],
    rows: (payload.rows ?? []).map(mapOaManualSearchRow).filter((row) => row.rowId.length > 0),
  };
}

export async function fetchManualOaImports(): Promise<OaManualImportList> {
  const payload = await requestJson<ApiOaManualImportList>(
    "/api/workbench/settings/oa/manual-imports",
    { method: "GET" },
  );
  return {
    rowIds: (payload.row_ids ?? []).map((rowId) => String(rowId)),
    entries: (payload.entries ?? []).map((entry) => ({
      rowId: toDisplayValue(entry.row_id, ""),
      actorId: entry.actor_id ?? undefined,
      importedAt: entry.imported_at ?? null,
      source: entry.source ?? undefined,
      audit: entry.audit ?? undefined,
    })).filter((entry) => entry.rowId.length > 0),
  };
}

export async function removeManualOaImport(rowId: string): Promise<{ removed: boolean; rowId: string }> {
  const payload = await requestJson<{ removed?: boolean; row_id?: string | null }>(
    `/api/workbench/settings/oa/manual-imports/${encodeURIComponent(rowId)}`,
    { method: "DELETE" },
  );
  return {
    removed: payload.removed === true,
    rowId: toDisplayValue(payload.row_id, rowId),
  };
}

function mapDataResetResult(result: ApiWorkbenchSettingsDataResetResult): WorkbenchSettingsDataResetResult {
  return {
    action: result.action,
    status: result.status,
    jobId: result.job_id,
    clearedCollections: result.cleared_collections ?? [],
    deletedCounts: result.deleted_counts ?? {},
    protectedTargets: result.protected_targets ?? [],
    rebuildStatus: result.rebuild_status ?? "unknown",
    message: result.message ?? "数据重置已完成。",
  };
}

function mapDataResetJob(payload: ApiWorkbenchSettingsDataResetJob): WorkbenchSettingsDataResetJob {
  const result = payload.result ? mapDataResetResult(payload.result) : null;
  return {
    jobId: String(payload.job_id ?? result?.jobId ?? ""),
    action: payload.action ?? result?.action ?? "reset_bank_transactions",
    status: payload.status ?? result?.status ?? "unknown",
    phase: payload.phase ?? "",
    message: payload.message ?? result?.message ?? "",
    current: typeof payload.current === "number" && Number.isFinite(payload.current) ? payload.current : 0,
    total: typeof payload.total === "number" && Number.isFinite(payload.total) ? payload.total : 0,
    percent: clampPercent(payload.percent),
    result,
    error: payload.error ?? null,
  };
}

function isDataResetJobTerminal(status: string) {
  return ["completed", "failed", "error", "cancelled", "canceled"].includes(status);
}

function wait(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function fetchWorkbenchSettingsDataResetJob(jobId: string): Promise<WorkbenchSettingsDataResetJob> {
  const payload = await requestJson<ApiWorkbenchSettingsDataResetJobResponse>(
    `/api/workbench/settings/data-reset/jobs/${encodeURIComponent(jobId)}`,
  );
  return mapDataResetJob(payload.job ?? {});
}

export async function fetchActiveWorkbenchSettingsDataResetJob(): Promise<WorkbenchSettingsDataResetJob | null> {
  const payload = await requestJson<ApiWorkbenchSettingsDataResetJobResponse>(
    "/api/workbench/settings/data-reset/jobs/active",
  );
  return payload.job ? mapDataResetJob(payload.job) : null;
}

async function waitForWorkbenchSettingsDataResetJob(
  initialJob: WorkbenchSettingsDataResetJob,
  payload: Pick<WorkbenchSettingsDataResetPayload, "onProgress" | "pollIntervalMs">,
): Promise<WorkbenchSettingsDataResetResult> {
  payload.onProgress?.(initialJob);

  let job = initialJob;
  const pollIntervalMs = Math.max(100, payload.pollIntervalMs ?? 800);
  while (!isDataResetJobTerminal(job.status)) {
    await wait(pollIntervalMs);
    job = await fetchWorkbenchSettingsDataResetJob(job.jobId);
    payload.onProgress?.(job);
  }

  if (job.status === "completed") {
    return job.result ?? {
      action: job.action,
      status: job.status,
      jobId: job.jobId,
      clearedCollections: [],
      deletedCounts: {},
      protectedTargets: [],
      rebuildStatus: "unknown",
      message: job.message || "数据重置已完成。",
    };
  }

  throw new Error(job.error || job.message || "数据重置失败，请稍后重试。");
}

export async function resumeWorkbenchSettingsDataResetJob(
  job: WorkbenchSettingsDataResetJob,
  payload: Pick<WorkbenchSettingsDataResetPayload, "onProgress" | "pollIntervalMs"> = {},
): Promise<WorkbenchSettingsDataResetResult> {
  return waitForWorkbenchSettingsDataResetJob(job, payload);
}

export async function resetWorkbenchSettingsData(
  payload: WorkbenchSettingsDataResetPayload,
): Promise<WorkbenchSettingsDataResetResult> {
  const createdPayload = await requestJson<ApiWorkbenchSettingsDataResetJobResponse>("/api/workbench/settings/data-reset/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      action: payload.action,
      oa_password: payload.oaPassword,
    }),
  });
  const createdJob = mapDataResetJob(createdPayload.job ?? {});
  return waitForWorkbenchSettingsDataResetJob(createdJob, payload);
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
  const requestBody: {
    month: string;
    row_ids: string[];
    case_id?: string;
    note?: string;
  } = {
    month: payload.month,
    row_ids: payload.rowIds,
    case_id: payload.caseId,
  };
  if (payload.note?.trim()) {
    requestBody.note = payload.note.trim();
  }
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/confirm-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });
}

export async function previewWorkbenchConfirmLink(payload: ConfirmLinkPayload): Promise<WorkbenchRelationPreview> {
  const result = await requestJson<ApiWorkbenchRelationPreview>("/api/workbench/actions/confirm-link/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      case_id: payload.caseId,
    }),
  });
  return mapRelationPreview(result);
}

export async function previewWorkbenchWithdrawLink(payload: WithdrawLinkPayload): Promise<WorkbenchRelationPreview> {
  const result = await requestJson<ApiWorkbenchRelationPreview>("/api/workbench/actions/withdraw-link/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
    }),
  });
  return mapRelationPreview(result);
}

export async function previewWorkbenchException(
  payload: WorkbenchExceptionPreviewPayload,
): Promise<WorkbenchExceptionPreview> {
  const result = await requestJson<ApiWorkbenchExceptionPreview>("/api/workbench/exception/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
    }),
  });
  return mapWorkbenchExceptionPreview(result);
}

export async function applyWorkbenchException(
  payload: WorkbenchExceptionApplyPayload,
): Promise<WorkbenchExceptionApplyResult> {
  const result = await requestJsonWithTimeout<ApiWorkbenchExceptionApplyResult>(
    "/api/workbench/exception/apply",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        month: payload.month,
        row_ids: payload.rowIds,
        scenario_code: payload.scenarioCode,
        action_code: payload.actionCode,
        payload: payload.payload,
      }),
    },
    WORKBENCH_EXCEPTION_APPLY_TIMEOUT_MS,
  );
  return mapWorkbenchExceptionApplyResult(result);
}

export async function withdrawWorkbenchLink(payload: WithdrawLinkPayload) {
  const requestBody: {
    month: string;
    row_ids: string[];
    note?: string;
  } = {
    month: payload.month,
    row_ids: payload.rowIds,
  };
  if (payload.note?.trim()) {
    requestBody.note = payload.note.trim();
  }
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/withdraw-link", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
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

export async function confirmWorkbenchPersonalAdvanceRepayment(payload: ConfirmPersonalAdvanceRepaymentPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/confirm-personal-advance-repayment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      note: payload.note,
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

export async function confirmWorkbenchCashPassThrough(payload: ConfirmCashPassThroughPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/confirm-cash-pass-through", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      cash_amount: payload.cashAmount,
      note: payload.note,
    }),
  });
}

export async function confirmWorkbenchCashTicketPurchase(payload: ConfirmCashTicketPurchasePayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/confirm-cash-ticket-purchase", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      cash_amount: payload.cashAmount,
      ticket_cost_amount: payload.ticketCostAmount,
      project_id: payload.projectId,
      project_name: payload.projectName,
      expense_type: payload.expenseType,
      expense_content: payload.expenseContent,
      note: payload.note,
    }),
  });
}

export async function cancelWorkbenchCashSpecial(payload: CancelCashSpecialPayload) {
  return requestJson<ApiWorkbenchActionResult>("/api/workbench/actions/cancel-cash-special", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: payload.month,
      row_ids: payload.rowIds,
      note: payload.note,
    }),
  });
}
