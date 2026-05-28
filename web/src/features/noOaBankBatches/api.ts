import type {
  NoOaBankBatch,
  NoOaBankBatchDetail,
  NoOaBankBatchDetailRow,
  NoOaBankBatchMutationResult,
  NoOaBankBatchesRequest,
  NoOaBankBatchesResponse,
  NoOaBankBatchCountMap,
  NoOaBankBatchSummary,
  SubmitNoOaBankBatchesRequest,
  SubmitNoOaBankBatchRequest,
  WithdrawNoOaBankBatchRequest,
} from "./types";
import { apiRequestJson } from "../apiClient";

type ApiNoOaBankBatch = {
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
};

type ApiNoOaBankBatchSummary = {
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
  total_amount?: string | null;
  totalAmount?: string | null;
  categories?: ApiNoOaBankBatchSummaryCategory[];
};

type ApiNoOaBankBatchSummaryCategory = {
  code?: string | null;
  label?: string | null;
  total?: number | null;
  draft?: number | null;
  submitted?: number | null;
  withdrawn?: number | null;
  conflict?: number | null;
  stale?: number | null;
  total_amount?: string | null;
  totalAmount?: string | null;
};

type ApiNoOaBankBatchesResponse = {
  summary?: ApiNoOaBankBatchSummary;
  batches?: ApiNoOaBankBatch[];
};

type ApiNoOaBankBatchDetailRow = {
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
};

type ApiNoOaBankBatchDetail = {
  batch?: ApiNoOaBankBatch;
  rows?: ApiNoOaBankBatchDetailRow[];
  tag_counts?: Record<string, unknown> | null;
  tagCounts?: Record<string, unknown> | null;
  direction_counts?: Record<string, unknown> | null;
  directionCounts?: Record<string, unknown> | null;
};

type ApiNoOaBankBatchMutationResult = {
  batch?: ApiNoOaBankBatch | null;
  affected_months?: string[];
  affectedMonths?: string[];
  workbench_rebuild_queued?: boolean | null;
  workbenchRebuildQueued?: boolean | null;
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

function nullableNumberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : null;
}

function stringList(value: string[] | undefined) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function countMap(value: Record<string, unknown> | null | undefined): NoOaBankBatchCountMap {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, rawCount]) => [key, Number(rawCount)])
      .filter(([key, count]) => Boolean(key) && Number.isFinite(count)),
  ) as NoOaBankBatchCountMap;
}

function mapBatch(batch: ApiNoOaBankBatch = {}): NoOaBankBatch {
  return {
    batchId: text(batch.batch_id ?? batch.batchId),
    batchType: text(batch.batch_type ?? batch.batchType),
    batchLabel: text(batch.batch_label ?? batch.batchLabel),
    scopeMonth: text(batch.scope_month ?? batch.scopeMonth),
    accountKey: text(batch.account_key ?? batch.accountKey),
    bankName: text(batch.bank_name ?? batch.bankName),
    accountLast4: text(batch.account_last4 ?? batch.accountLast4),
    status: text(batch.status),
    statusBucket: text(batch.status_bucket ?? batch.statusBucket),
    rowCount: numberValue(batch.row_count ?? batch.rowCount),
    totalAmount: text(batch.total_amount ?? batch.totalAmount, "0.00"),
    submittedBy: text(batch.submitted_by ?? batch.submittedBy),
    submittedAt: text(batch.submitted_at ?? batch.submittedAt) || null,
    withdrawnBy: text(batch.withdrawn_by ?? batch.withdrawnBy),
    withdrawnAt: text(batch.withdrawn_at ?? batch.withdrawnAt) || null,
    conflictReason: text(batch.conflict_reason ?? batch.conflictReason),
    blockedReason: text(batch.blocked_reason ?? batch.blockedReason),
    tagCounts: countMap(batch.tag_counts ?? batch.tagCounts),
    directionCounts: countMap(batch.direction_counts ?? batch.directionCounts),
    canSubmit: Boolean(batch.can_submit ?? batch.canSubmit),
    canWithdraw: Boolean(batch.can_withdraw ?? batch.canWithdraw),
    version: nullableNumberValue(batch.version),
  };
}

function mapSummary(summary: ApiNoOaBankBatchSummary = {}): NoOaBankBatchSummary {
  return {
    draftCount: numberValue(summary.draft_count ?? summary.draftCount),
    submittedCount: numberValue(summary.submitted_count ?? summary.submittedCount),
    withdrawnCount: numberValue(summary.withdrawn_count ?? summary.withdrawnCount),
    conflictCount: numberValue(summary.conflict_count ?? summary.conflictCount),
    staleCount: numberValue(summary.stale_count ?? summary.staleCount),
    totalAmount: text(summary.total_amount ?? summary.totalAmount, "0.00"),
    categories: Array.isArray(summary.categories) ? summary.categories.map(mapSummaryCategory) : [],
  };
}

function mapSummaryCategory(category: ApiNoOaBankBatchSummaryCategory) {
  return {
    code: text(category.code),
    label: text(category.label),
    total: numberValue(category.total),
    draft: numberValue(category.draft),
    submitted: numberValue(category.submitted),
    withdrawn: numberValue(category.withdrawn),
    conflict: numberValue(category.conflict),
    stale: numberValue(category.stale),
    totalAmount: text(category.total_amount ?? category.totalAmount, "0.00"),
  };
}

function mapDetailRow(row: ApiNoOaBankBatchDetailRow = {}): NoOaBankBatchDetailRow {
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
  };
}

function mapMutationResult(payload: ApiNoOaBankBatchMutationResult): NoOaBankBatchMutationResult {
  return {
    batch: payload.batch ? mapBatch(payload.batch) : null,
    affectedMonths: stringList(payload.affected_months ?? payload.affectedMonths),
    workbenchRebuildQueued: Boolean(payload.workbench_rebuild_queued ?? payload.workbenchRebuildQueued),
    results: Array.isArray(payload.results) ? payload.results : [],
  };
}

export async function fetchNoOaBankBatches({
  month,
  type,
  status,
  bucket,
  accountKey,
  signal,
}: NoOaBankBatchesRequest = {}): Promise<NoOaBankBatchesResponse> {
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
  const query = params.toString();
  const payload = await requestJson<ApiNoOaBankBatchesResponse>(
    `/api/no-oa-bank-batches${query ? `?${query}` : ""}`,
    { method: "GET", signal },
  );
  return {
    summary: mapSummary(payload.summary),
    batches: Array.isArray(payload.batches) ? payload.batches.map(mapBatch) : [],
  };
}

export async function fetchNoOaBankBatchDetail(batchId: string, signal?: AbortSignal): Promise<NoOaBankBatchDetail> {
  const payload = await requestJson<ApiNoOaBankBatchDetail>(
    `/api/no-oa-bank-batches/${encodeURIComponent(batchId)}`,
    { method: "GET", signal },
  );
  return {
    batch: mapBatch(payload.batch),
    rows: Array.isArray(payload.rows) ? payload.rows.map(mapDetailRow) : [],
    tagCounts: countMap(payload.tag_counts ?? payload.tagCounts ?? payload.batch?.tag_counts ?? payload.batch?.tagCounts),
    directionCounts: countMap(payload.direction_counts ?? payload.directionCounts ?? payload.batch?.direction_counts ?? payload.batch?.directionCounts),
  };
}

export async function submitNoOaBankBatch({
  batchId,
  expectedVersion,
  note,
  signal,
}: SubmitNoOaBankBatchRequest): Promise<NoOaBankBatchMutationResult> {
  const payload = await requestJson<ApiNoOaBankBatchMutationResult>(
    `/api/no-oa-bank-batches/${encodeURIComponent(batchId)}/submit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, note: note ?? "" }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function withdrawNoOaBankBatch({
  batchId,
  expectedVersion,
  reason,
  signal,
}: WithdrawNoOaBankBatchRequest): Promise<NoOaBankBatchMutationResult> {
  const payload = await requestJson<ApiNoOaBankBatchMutationResult>(
    `/api/no-oa-bank-batches/${encodeURIComponent(batchId)}/withdraw`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
      signal,
    },
  );
  return mapMutationResult(payload);
}

export async function submitNoOaBankBatches({
  batches,
  signal,
}: SubmitNoOaBankBatchesRequest): Promise<NoOaBankBatchMutationResult> {
  const payload = await requestJson<ApiNoOaBankBatchMutationResult>(
    "/api/no-oa-bank-batches/submit",
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
