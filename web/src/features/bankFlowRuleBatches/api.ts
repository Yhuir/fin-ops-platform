import type {
  BankFlowRuleBatch,
  BankFlowRuleBatchDetail,
  BankFlowRuleBatchDetailRow,
  BankFlowRuleBatchesPageInfo,
  BankFlowRuleBatchReadModelStatus,
  ReadModelOperationBarrierTarget,
  BankFlowRuleBatchTagDefinition,
  BankFlowRuleBatchTagRule,
  BankFlowRuleBatchTagSelection,
  BankFlowRuleBatchMutationResult,
  BankFlowRuleBatchesRequest,
  BankFlowRuleBatchesResponse,
  BankFlowRuleBatchCountMap,
  BankFlowRuleBatchSummary,
  SaveBankFlowRuleBatchTagSelectionRequest,
  SubmitBankFlowRuleBatchesRequest,
  SubmitBankFlowRuleBatchRequest,
  SubmitBankFlowRuleBatchSelectionRequest,
  WithdrawBankFlowRuleBatchRequest,
  ResetSubmittedBankFlowRuleBatchesRequest,
} from "./types";
import { apiRequestJson } from "../apiClient";

type ApiBankFlowRuleBatch = {
  batch_id?: string | null;
  batchId?: string | null;
  batch_type?: string | null;
  batchType?: string | null;
  batch_label?: string | null;
  batchLabel?: string | null;
  scope_month?: string | null;
  scopeMonth?: string | null;
  account_key?: string | null;
  accountKey?: string | null;
  bank_name?: string | null;
  bankName?: string | null;
  account_last4?: string | null;
  accountLast4?: string | null;
  status?: string | null;
  status_bucket?: string | null;
  statusBucket?: string | null;
  row_count?: number | null;
  rowCount?: number | null;
  total_amount?: string | null;
  totalAmount?: string | null;
  submitted_by?: string | null;
  submittedBy?: string | null;
  submitted_at?: string | null;
  submittedAt?: string | null;
  withdrawn_by?: string | null;
  withdrawnBy?: string | null;
  withdrawn_at?: string | null;
  withdrawnAt?: string | null;
  conflict_reason?: string | null;
  conflictReason?: string | null;
  blocked_reason?: string | null;
  blockedReason?: string | null;
  tag_counts?: Record<string, unknown> | null;
  tagCounts?: Record<string, unknown> | null;
  direction_counts?: Record<string, unknown> | null;
  directionCounts?: Record<string, unknown> | null;
  can_submit?: boolean | null;
  canSubmit?: boolean | null;
  can_withdraw?: boolean | null;
  canWithdraw?: boolean | null;
  version?: number | null;
  category_primary_label?: string | null;
  categoryPrimaryLabel?: string | null;
  category_sub_label?: string | null;
  categorySubLabel?: string | null;
  category_label_path?: unknown[] | null;
  categoryLabelPath?: unknown[] | null;
};

type ApiBankFlowRuleBatchSummary = {
  draft_count?: number | null;
  draftCount?: number | null;
  submitted_count?: number | null;
  submittedCount?: number | null;
  withdrawn_count?: number | null;
  withdrawnCount?: number | null;
  conflict_count?: number | null;
  conflictCount?: number | null;
  stale_count?: number | null;
  staleCount?: number | null;
  total_row_count?: number | null;
  totalRowCount?: number | null;
  draft_row_count?: number | null;
  draftRowCount?: number | null;
  submitted_row_count?: number | null;
  submittedRowCount?: number | null;
  withdrawn_row_count?: number | null;
  withdrawnRowCount?: number | null;
  total_amount?: string | null;
  totalAmount?: string | null;
  categories?: ApiBankFlowRuleBatchSummaryCategory[];
};

type ApiBankFlowRuleBatchSummaryCategory = {
  code?: string | null;
  label?: string | null;
  total?: number | null;
  draft?: number | null;
  submitted?: number | null;
  withdrawn?: number | null;
  conflict?: number | null;
  stale?: number | null;
  total_row_count?: number | null;
  totalRowCount?: number | null;
  draft_row_count?: number | null;
  draftRowCount?: number | null;
  submitted_row_count?: number | null;
  submittedRowCount?: number | null;
  withdrawn_row_count?: number | null;
  withdrawnRowCount?: number | null;
  total_amount?: string | null;
  totalAmount?: string | null;
  primary_label?: string | null;
  primaryLabel?: string | null;
  sub_label?: string | null;
  subLabel?: string | null;
  label_path?: unknown[] | null;
  labelPath?: unknown[] | null;
};

type ApiBankFlowRuleBatchTagDefinition = {
  code?: string | null;
  label?: string | null;
  path?: unknown[] | null;
  source?: string | null;
  status?: string | null;
  direction?: string | null;
  output_primary_label?: string | null;
  outputPrimaryLabel?: string | null;
  output_sub_label?: string | null;
  outputSubLabel?: string | null;
};

type ApiBankFlowRuleBatchTagRule = {
  tag_code?: string | null;
  tagCode?: string | null;
  code?: string | null;
  requires_oa?: unknown;
  requiresOa?: unknown;
  requires_invoice?: unknown;
  requiresInvoice?: unknown;
};

type ApiBankFlowRuleBatchTagSelection = {
  version?: number | null;
  bank_auto_tag_rules_version?: number | null;
  bankAutoTagRulesVersion?: number | null;
  active_tags?: ApiBankFlowRuleBatchTagDefinition[] | null;
  activeTags?: ApiBankFlowRuleBatchTagDefinition[] | null;
  rules?: ApiBankFlowRuleBatchTagRule[] | null;
  requirements_by_tag_code?: Record<string, ApiBankFlowRuleBatchTagRule> | null;
  requirementsByTagCode?: Record<string, ApiBankFlowRuleBatchTagRule> | null;
  eligibility_changed?: boolean | null;
  eligibilityChanged?: boolean | null;
  eligibility_changed_tag_codes?: unknown[] | null;
  eligibilityChangedTagCodes?: unknown[] | null;
  affected_months?: unknown[] | null;
  affectedMonths?: unknown[] | null;
  affected_scope_keys?: unknown[] | null;
  affectedScopeKeys?: unknown[] | null;
  read_model_scope_keys?: unknown[] | null;
  readModelScopeKeys?: unknown[] | null;
  freshness_targets?: unknown;
  freshnessTargets?: unknown;
  operation_barrier_targets?: unknown;
  operationBarrierTargets?: unknown;
  refresh_enqueued?: boolean | null;
  refreshEnqueued?: boolean | null;
};

type ApiBankFlowRuleBatchesResponse = {
  summary?: ApiBankFlowRuleBatchSummary;
  batches?: ApiBankFlowRuleBatch[];
  pagination?: ApiBankFlowRuleBatchesPageInfo | null;
  read_model_status?: string | null;
  readModelStatus?: string | null;
  read_model_version?: string | null;
  readModelVersion?: string | null;
  read_model_stale_reasons?: unknown[] | null;
  readModelStaleReasons?: unknown[] | null;
};

type ApiBankFlowRuleBatchesPageInfo = {
  page?: number | null;
  page_size?: number | null;
  pageSize?: number | null;
  total?: number | null;
};

type ApiBankFlowRuleBatchDetailRow = {
  transaction_id?: string | null;
  transactionId?: string | null;
  id?: string | null;
  trade_time?: string | null;
  tradeTime?: string | null;
  counterparty_name?: string | null;
  counterpartyName?: string | null;
  direction?: string | null;
  direction_label?: string | null;
  directionLabel?: string | null;
  amount?: string | null;
  bank_name?: string | null;
  bankName?: string | null;
  account_last4?: string | null;
  accountLast4?: string | null;
  account_key?: string | null;
  accountKey?: string | null;
  summary?: string | null;
  purpose?: string | null;
  remark?: string | null;
  note?: string | null;
  category_code?: string | null;
  categoryCode?: string | null;
  category_label?: string | null;
  categoryLabel?: string | null;
  category_primary_label?: string | null;
  categoryPrimaryLabel?: string | null;
  category_sub_label?: string | null;
  categorySubLabel?: string | null;
  category_label_path?: unknown[] | null;
  categoryLabelPath?: unknown[] | null;
  category_source?: string | null;
  categorySource?: string | null;
  relation_status?: string | null;
  relationStatus?: string | null;
  relation_case_ids?: unknown[] | null;
  relationCaseIds?: unknown[] | null;
  linked_oa_count?: number | null;
  linkedOaCount?: number | null;
  linked_invoice_count?: number | null;
  linkedInvoiceCount?: number | null;
};

type ApiBankFlowRuleBatchDetail = {
  batch?: ApiBankFlowRuleBatch;
  rows?: ApiBankFlowRuleBatchDetailRow[];
  tag_counts?: Record<string, unknown> | null;
  tagCounts?: Record<string, unknown> | null;
  direction_counts?: Record<string, unknown> | null;
  directionCounts?: Record<string, unknown> | null;
};

type ApiBankFlowRuleBatchMutationResult = {
  batch?: ApiBankFlowRuleBatch | null;
  affected_months?: string[];
  affectedMonths?: string[];
  affected_scope_keys?: string[];
  affectedScopeKeys?: string[];
  read_model_scope_keys?: string[];
  readModelScopeKeys?: string[];
  freshness_targets?: unknown;
  freshnessTargets?: unknown;
  operation_barrier_targets?: unknown;
  operationBarrierTargets?: unknown;
  results?: Array<Record<string, unknown>>;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  return apiRequestJson<T>(url, init);
}

function text(value: string | null | undefined, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : 0;
}

function positiveNumberValue(value: number | null | undefined, fallback: number) {
  const number = numberValue(value);
  return number > 0 ? number : fallback;
}

function nullableNumberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : null;
}

function stringList(value: string[] | undefined) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function unknownStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function booleanValue(value: unknown) {
  return value === true || value === 1 || value === "1" || value === "true";
}

function normalizeReadModelStatus(value: string | null | undefined): BankFlowRuleBatchReadModelStatus {
  return value === "fresh"
    || value === "refreshing"
    || value === "stale"
    || value === "schema_mismatch"
    || value === "missing"
    ? value
    : "refreshing";
}

function readModelTargets(value: unknown): ReadModelOperationBarrierTarget[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const targets: ReadModelOperationBarrierTarget[] = [];
  const seen = new Set<string>();
  value.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const raw = item as Record<string, unknown>;
    const readModelKey = textValue(raw.read_model_key ?? raw.readModelKey);
    const scopeKey = textValue(raw.scope_key ?? raw.scopeKey);
    const scopeType = textValue(raw.scope_type ?? raw.scopeType);
    if (!readModelKey || !scopeKey) {
      return;
    }
    const key = `${readModelKey}\u0000${scopeKey}\u0000${scopeType}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    targets.push({
      readModelKey,
      scopeKey,
      ...(scopeType ? { scopeType } : {}),
    });
  });
  return targets;
}

function textValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function countMap(value: Record<string, unknown> | null | undefined): BankFlowRuleBatchCountMap {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, rawCount]) => [key, Number(rawCount)])
      .filter(([key, count]) => Boolean(key) && Number.isFinite(count)),
  ) as BankFlowRuleBatchCountMap;
}

function normalizeBatchLifecycle(rawStatus: string, rawStatusBucket: string, rawCanWithdraw: boolean) {
  const relationBackedStale = rawStatus === "stale" && (rawStatusBucket === "submitted" || rawCanWithdraw);
  if (relationBackedStale) {
    return { relationBackedStale, status: "submitted", statusBucket: "submitted" };
  }
  const statusBucket = rawStatusBucket
    || (rawStatus === "submitted" ? "submitted" : rawStatus === "withdrawn" ? "withdrawn" : rawStatus ? "unsubmitted" : "");
  const status = rawStatus === "unsubmitted" && statusBucket === "unsubmitted" ? "draft" : rawStatus;
  return { relationBackedStale, status, statusBucket };
}

function mapBatch(batch: ApiBankFlowRuleBatch = {}): BankFlowRuleBatch {
  const rawStatus = text(batch.status);
  const rawStatusBucket = text(batch.status_bucket ?? batch.statusBucket);
  const rawCanWithdraw = Boolean(batch.can_withdraw ?? batch.canWithdraw);
  const lifecycle = normalizeBatchLifecycle(rawStatus, rawStatusBucket, rawCanWithdraw);
  const legacyDraft = rawStatus === "unsubmitted" && lifecycle.status === "draft" && lifecycle.statusBucket === "unsubmitted";
  const mapped: BankFlowRuleBatch = {
    batchId: text(batch.batch_id ?? batch.batchId),
    batchType: text(batch.batch_type ?? batch.batchType),
    batchLabel: text(batch.batch_label ?? batch.batchLabel),
    scopeMonth: text(batch.scope_month ?? batch.scopeMonth),
    accountKey: text(batch.account_key ?? batch.accountKey),
    bankName: text(batch.bank_name ?? batch.bankName),
    accountLast4: text(batch.account_last4 ?? batch.accountLast4),
    status: lifecycle.status,
    statusBucket: lifecycle.statusBucket,
    rowCount: numberValue(batch.row_count ?? batch.rowCount),
    totalAmount: text(batch.total_amount ?? batch.totalAmount, "0.00"),
    submittedBy: text(batch.submitted_by ?? batch.submittedBy),
    submittedAt: text(batch.submitted_at ?? batch.submittedAt) || null,
    withdrawnBy: text(batch.withdrawn_by ?? batch.withdrawnBy),
    withdrawnAt: text(batch.withdrawn_at ?? batch.withdrawnAt) || null,
    conflictReason: text(batch.conflict_reason ?? batch.conflictReason),
    blockedReason: lifecycle.relationBackedStale ? "" : text(batch.blocked_reason ?? batch.blockedReason),
    tagCounts: countMap(batch.tag_counts ?? batch.tagCounts),
    directionCounts: countMap(batch.direction_counts ?? batch.directionCounts),
    canSubmit: lifecycle.relationBackedStale ? false : legacyDraft ? true : Boolean(batch.can_submit ?? batch.canSubmit),
    canWithdraw: lifecycle.relationBackedStale || rawCanWithdraw,
    version: nullableNumberValue(batch.version),
  };
  const primaryLabel = text(batch.category_primary_label ?? batch.categoryPrimaryLabel);
  const subLabel = text(batch.category_sub_label ?? batch.categorySubLabel);
  const labelPath = unknownStringList(batch.category_label_path ?? batch.categoryLabelPath);
  if (primaryLabel) {
    mapped.categoryPrimaryLabel = primaryLabel;
  }
  if (subLabel) {
    mapped.categorySubLabel = subLabel;
  }
  if (labelPath.length > 0) {
    mapped.categoryLabelPath = labelPath;
  }
  return mapped;
}

function isPublicBatch(batch: BankFlowRuleBatch) {
  return batch.status === "draft" || batch.status === "submitted" || batch.status === "withdrawn";
}

function mapSummary(summary: ApiBankFlowRuleBatchSummary = {}): BankFlowRuleBatchSummary {
  return {
    draftCount: numberValue(summary.draft_count ?? summary.draftCount),
    submittedCount: numberValue(summary.submitted_count ?? summary.submittedCount),
    withdrawnCount: numberValue(summary.withdrawn_count ?? summary.withdrawnCount),
    conflictCount: numberValue(summary.conflict_count ?? summary.conflictCount),
    staleCount: numberValue(summary.stale_count ?? summary.staleCount),
    totalRowCount: numberValue(summary.total_row_count ?? summary.totalRowCount),
    draftRowCount: numberValue(summary.draft_row_count ?? summary.draftRowCount),
    submittedRowCount: numberValue(summary.submitted_row_count ?? summary.submittedRowCount),
    withdrawnRowCount: numberValue(summary.withdrawn_row_count ?? summary.withdrawnRowCount),
    totalAmount: text(summary.total_amount ?? summary.totalAmount, "0.00"),
    categories: Array.isArray(summary.categories) ? summary.categories.map(mapSummaryCategory) : [],
  };
}

function mapPagination(value: ApiBankFlowRuleBatchesPageInfo | null | undefined): BankFlowRuleBatchesPageInfo | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  return {
    page: positiveNumberValue(value.page, 1),
    pageSize: positiveNumberValue(value.page_size ?? value.pageSize, 200),
    total: Math.max(0, numberValue(value.total)),
  };
}

function mapSummaryCategory(category: ApiBankFlowRuleBatchSummaryCategory) {
  const mapped = {
    code: text(category.code),
    label: text(category.label),
    total: numberValue(category.total),
    draft: numberValue(category.draft),
    submitted: numberValue(category.submitted),
    withdrawn: numberValue(category.withdrawn),
    conflict: numberValue(category.conflict),
    stale: numberValue(category.stale),
    totalRowCount: numberValue(category.total_row_count ?? category.totalRowCount),
    draftRowCount: numberValue(category.draft_row_count ?? category.draftRowCount),
    submittedRowCount: numberValue(category.submitted_row_count ?? category.submittedRowCount),
    withdrawnRowCount: numberValue(category.withdrawn_row_count ?? category.withdrawnRowCount),
    totalAmount: text(category.total_amount ?? category.totalAmount, "0.00"),
  };
  const primaryLabel = text(category.primary_label ?? category.primaryLabel);
  const subLabel = text(category.sub_label ?? category.subLabel);
  const labelPath = unknownStringList(category.label_path ?? category.labelPath);
  return {
    ...mapped,
    ...(primaryLabel ? { primaryLabel } : {}),
    ...(subLabel ? { subLabel } : {}),
    ...(labelPath.length > 0 ? { labelPath } : {}),
  };
}

function mapTagDefinition(tag: ApiBankFlowRuleBatchTagDefinition = {}): BankFlowRuleBatchTagDefinition {
  return {
    code: text(tag.code),
    label: text(tag.label),
    path: unknownStringList(tag.path),
    source: text(tag.source),
    status: text(tag.status, "active"),
    direction: text(tag.direction, "any"),
    outputPrimaryLabel: text(tag.output_primary_label ?? tag.outputPrimaryLabel),
    outputSubLabel: text(tag.output_sub_label ?? tag.outputSubLabel),
  };
}

function mapTagRule(rule: ApiBankFlowRuleBatchTagRule = {}): BankFlowRuleBatchTagRule {
  return {
    tagCode: text(rule.tag_code ?? rule.tagCode ?? rule.code),
    requiresOa: booleanValue(rule.requires_oa ?? rule.requiresOa),
    requiresInvoice: booleanValue(rule.requires_invoice ?? rule.requiresInvoice),
  };
}

function mapTagSelection(payload: ApiBankFlowRuleBatchTagSelection = {}): BankFlowRuleBatchTagSelection {
  const activeTags = Array.isArray(payload.active_tags ?? payload.activeTags)
    ? (payload.active_tags ?? payload.activeTags ?? []).map(mapTagDefinition)
    : [];
  const rulesByCode = new Map<string, BankFlowRuleBatchTagRule>();
  if (Array.isArray(payload.rules)) {
    payload.rules.map(mapTagRule).forEach((rule) => {
      if (rule.tagCode) {
        rulesByCode.set(rule.tagCode, rule);
      }
    });
  }
  const requirementsByCode = payload.requirements_by_tag_code ?? payload.requirementsByTagCode;
  if (requirementsByCode && typeof requirementsByCode === "object") {
    Object.entries(requirementsByCode).forEach(([tagCode, rule]) => {
      const rulePayload = rule && typeof rule === "object" ? rule : {};
      rulesByCode.set(tagCode, mapTagRule({ ...rulePayload, tag_code: tagCode }));
    });
  }
  const rules = activeTags.map((tag) => rulesByCode.get(tag.code) ?? {
    tagCode: tag.code,
    requiresOa: true,
    requiresInvoice: true,
  });
  const freshnessTargets = readModelTargets(payload.freshness_targets ?? payload.freshnessTargets);
  const operationTargets = readModelTargets(payload.operation_barrier_targets ?? payload.operationBarrierTargets);
  return {
    version: numberValue(payload.version),
    bankAutoTagRulesVersion: numberValue(payload.bank_auto_tag_rules_version ?? payload.bankAutoTagRulesVersion),
    activeTags,
    rules,
    requirementsByTagCode: Object.fromEntries(rules.map((rule) => [
      rule.tagCode,
      { requiresOa: rule.requiresOa, requiresInvoice: rule.requiresInvoice },
    ])),
    eligibilityChanged: Boolean(payload.eligibility_changed ?? payload.eligibilityChanged),
    eligibilityChangedTagCodes: unknownStringList(
      payload.eligibility_changed_tag_codes ?? payload.eligibilityChangedTagCodes,
    ),
    affectedMonths: unknownStringList(payload.affected_months ?? payload.affectedMonths),
    affectedScopeKeys: unknownStringList(payload.affected_scope_keys ?? payload.affectedScopeKeys),
    readModelScopeKeys: unknownStringList(payload.read_model_scope_keys ?? payload.readModelScopeKeys),
    freshnessTargets,
    operationBarrierTargets: operationTargets.length > 0 ? operationTargets : freshnessTargets,
    refreshEnqueued: Boolean(payload.refresh_enqueued ?? payload.refreshEnqueued),
  };
}

function mapDetailRow(row: ApiBankFlowRuleBatchDetailRow = {}): BankFlowRuleBatchDetailRow {
  const categoryLabelPath = row.category_label_path ?? row.categoryLabelPath;
  return {
    transactionId: text(row.transaction_id ?? row.transactionId ?? row.id),
    tradeTime: text(row.trade_time ?? row.tradeTime),
    counterpartyName: text(row.counterparty_name ?? row.counterpartyName),
    direction: text(row.direction),
    directionLabel: text(row.direction_label ?? row.directionLabel),
    amount: text(row.amount, "0.00"),
    bankName: text(row.bank_name ?? row.bankName),
    accountLast4: text(row.account_last4 ?? row.accountLast4),
    accountKey: text(row.account_key ?? row.accountKey),
    summary: text(row.summary),
    purpose: text(row.purpose),
    remark: text(row.remark ?? row.note),
    categoryCode: text(row.category_code ?? row.categoryCode),
    categoryLabel: text(row.category_label ?? row.categoryLabel),
    categoryPrimaryLabel: text(row.category_primary_label ?? row.categoryPrimaryLabel),
    categorySubLabel: text(row.category_sub_label ?? row.categorySubLabel),
    categoryLabelPath: Array.isArray(categoryLabelPath)
      ? categoryLabelPath.map((item: unknown) => String(item).trim()).filter(Boolean)
      : [],
    categorySource: text(row.category_source ?? row.categorySource),
    relationStatus: text(row.relation_status ?? row.relationStatus, "unlinked"),
    relationCaseIds: unknownStringList(row.relation_case_ids ?? row.relationCaseIds),
    linkedOaCount: numberValue(row.linked_oa_count ?? row.linkedOaCount),
    linkedInvoiceCount: numberValue(row.linked_invoice_count ?? row.linkedInvoiceCount),
  };
}

function mapMutationResult(payload: ApiBankFlowRuleBatchMutationResult): BankFlowRuleBatchMutationResult {
  const affectedScopeKeys = stringList(payload.affected_scope_keys ?? payload.affectedScopeKeys);
  const readModelScopeKeys = stringList(payload.read_model_scope_keys ?? payload.readModelScopeKeys);
  const freshnessTargets = readModelTargets(payload.freshness_targets ?? payload.freshnessTargets);
  const operationTargets = readModelTargets(payload.operation_barrier_targets ?? payload.operationBarrierTargets);
  return {
    batch: payload.batch ? mapBatch(payload.batch) : null,
    affectedMonths: stringList(payload.affected_months ?? payload.affectedMonths),
    affectedScopeKeys,
    readModelScopeKeys,
    freshnessTargets,
    operationBarrierTargets: operationTargets.length > 0 ? operationTargets : freshnessTargets,
    results: Array.isArray(payload.results) ? payload.results : [],
  };
}

export async function fetchBankFlowRuleBatches({
  month,
  type,
  status,
  bucket,
  accountKey,
  page,
  pageSize,
  signal,
}: BankFlowRuleBatchesRequest = {}): Promise<BankFlowRuleBatchesResponse> {
  const params = new URLSearchParams();
  if (month) {
    params.set("month", month);
  }
  if (type && type !== "all") {
    params.set("type", type);
  }
  if (status && status !== "all") {
    params.set("status", status);
  }
  if (bucket && bucket !== "all") {
    params.set("bucket", bucket);
  }
  if (accountKey) {
    params.set("account_key", accountKey);
  }
  if (page !== undefined) {
    params.set("page", String(page));
  }
  if (pageSize !== undefined) {
    params.set("page_size", String(pageSize));
  }
  const query = params.toString();
  const payload = await requestJson<ApiBankFlowRuleBatchesResponse>(
    `/api/bank-flow-rule-batches${query ? `?${query}` : ""}`,
    { method: "GET", signal },
  );
  return {
    summary: mapSummary(payload.summary),
    batches: Array.isArray(payload.batches) ? payload.batches.map(mapBatch).filter(isPublicBatch) : [],
    pagination: mapPagination(payload.pagination),
    readModelStatus: normalizeReadModelStatus(payload.read_model_status ?? payload.readModelStatus),
    readModelVersion: text(payload.read_model_version ?? payload.readModelVersion),
    readModelStaleReasons: unknownStringList(payload.read_model_stale_reasons ?? payload.readModelStaleReasons),
  };
}

export async function fetchBankFlowRuleBatchTagSelection(signal?: AbortSignal): Promise<BankFlowRuleBatchTagSelection> {
  const payload = await requestJson<ApiBankFlowRuleBatchTagSelection>(
    "/api/bank-flow-rule-batches/tag-rules",
    { method: "GET", signal },
  );
  return mapTagSelection(payload);
}

export async function saveBankFlowRuleBatchTagSelection({
  expectedVersion,
  rules,
  signal,
}: SaveBankFlowRuleBatchTagSelectionRequest): Promise<BankFlowRuleBatchTagSelection> {
  const payload = await requestJson<ApiBankFlowRuleBatchTagSelection>(
    "/api/bank-flow-rule-batches/tag-rules",
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_version: expectedVersion,
        rules: rules.map((rule) => ({
          tag_code: rule.tagCode,
          requires_oa: rule.requiresOa,
          requires_invoice: rule.requiresInvoice,
        })),
      }),
      signal,
    },
  );
  return mapTagSelection(payload);
}

export async function fetchBankFlowRuleBatchDetail(batchId: string, signal?: AbortSignal): Promise<BankFlowRuleBatchDetail> {
  const payload = await requestJson<ApiBankFlowRuleBatchDetail>(
    `/api/bank-flow-rule-batches/${encodeURIComponent(batchId)}`,
    { method: "GET", signal },
  );
  return {
    batch: mapBatch(payload.batch),
    rows: Array.isArray(payload.rows) ? payload.rows.map(mapDetailRow) : [],
    tagCounts: countMap(payload.tag_counts ?? payload.tagCounts ?? payload.batch?.tag_counts ?? payload.batch?.tagCounts),
    directionCounts: countMap(payload.direction_counts ?? payload.directionCounts ?? payload.batch?.direction_counts ?? payload.batch?.directionCounts),
  };
}

export async function submitBankFlowRuleBatch({
  batchId,
  expectedVersion,
  note,
  signal,
}: SubmitBankFlowRuleBatchRequest): Promise<BankFlowRuleBatchMutationResult> {
  const payload = await requestJson<ApiBankFlowRuleBatchMutationResult>(
    `/api/bank-flow-rule-batches/${encodeURIComponent(batchId)}/submit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, note: note ?? "" }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function withdrawBankFlowRuleBatch({
  batchId,
  expectedVersion,
  reason,
  signal,
}: WithdrawBankFlowRuleBatchRequest): Promise<BankFlowRuleBatchMutationResult> {
  const payload = await requestJson<ApiBankFlowRuleBatchMutationResult>(
    `/api/bank-flow-rule-batches/${encodeURIComponent(batchId)}/withdraw`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function resetSubmittedBankFlowRuleBatches({
  reason,
  signal,
}: ResetSubmittedBankFlowRuleBatchesRequest = {}): Promise<BankFlowRuleBatchMutationResult> {
  const payload = await requestJson<ApiBankFlowRuleBatchMutationResult>(
    "/api/bank-flow-rule-batches/reset-submitted",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? "" }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function submitBankFlowRuleBatches({
  batches,
  signal,
}: SubmitBankFlowRuleBatchesRequest): Promise<BankFlowRuleBatchMutationResult> {
  const payload = await requestJson<ApiBankFlowRuleBatchMutationResult>(
    "/api/bank-flow-rule-batches/submit",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        batches: batches.map((batch) => ({
          batch_id: batch.batchId,
          expected_version: batch.expectedVersion,
        })),
      }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function submitBankFlowRuleBatchSelection({
  transactionIds,
  note,
  signal,
}: SubmitBankFlowRuleBatchSelectionRequest): Promise<BankFlowRuleBatchMutationResult> {
  const payload = await requestJson<ApiBankFlowRuleBatchMutationResult>(
    "/api/bank-flow-rule-batches/submit-selection",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transaction_ids: transactionIds, note: note ?? "" }),
      signal,
    },
  );
  return mapMutationResult(payload);
}
