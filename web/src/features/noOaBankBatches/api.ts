import type {
  NoOaBankBatch,
  NoOaBankBatchDetail,
  NoOaBankBatchDetailRow,
  NoOaBankBatchMutationResult,
  NoOaBankBatchesRequest,
  NoOaBankBatchesResponse,
  NoOaBankBatchSummary,
  SubmitNoOaBankBatchesRequest,
  SubmitNoOaBankBatchRequest,
  WithdrawNoOaBankBatchRequest,
} from "./types";

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
  summary?: string | null;
  purpose?: string | null;
  remark?: string | null;
  note?: string | null;
  category_source?: string | null;
  categorySource?: string | null;
};

type ApiNoOaBankBatchDetail = {
  batch?: ApiNoOaBankBatch;
  rows?: ApiNoOaBankBatchDetailRow[];
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
  const response = await fetch(url, init);
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  if (trimmedText && looksLikeHtml(trimmedText)) {
    throw new Error(
      `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务已启动，并通过支持 /api 代理的前端开发服务访问。`,
    );
  }

  let payload = {} as T;
  if (trimmedText) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch {
      throw new Error(
        contentType
          ? `接口 ${url} 返回的不是合法 JSON：${contentType}`
          : `接口 ${url} 返回的不是合法 JSON。`,
      );
    }
  }
  if (!response.ok) {
    throw new Error(extractErrorMessage(payload) || trimmedText || "request failed");
  }
  return payload;
}

function looksLikeHtml(rawText: string) {
  const trimmedText = rawText.trim();
  return /^<!doctype\s+html/i.test(trimmedText) || /^<html[\s>]/i.test(trimmedText);
}

function extractErrorMessage(payload: unknown) {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    return typeof message === "string" ? message : "";
  }
  return "";
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
    rowCount: numberValue(batch.row_count ?? batch.rowCount),
    totalAmount: text(batch.total_amount ?? batch.totalAmount, "0.00"),
    submittedBy: text(batch.submitted_by ?? batch.submittedBy),
    submittedAt: text(batch.submitted_at ?? batch.submittedAt) || null,
    withdrawnBy: text(batch.withdrawn_by ?? batch.withdrawnBy),
    withdrawnAt: text(batch.withdrawn_at ?? batch.withdrawnAt) || null,
    conflictReason: text(batch.conflict_reason ?? batch.conflictReason),
    version: nullableNumberValue(batch.version),
  };
}

function mapSummary(summary: ApiNoOaBankBatchSummary = {}): NoOaBankBatchSummary {
  return {
    draftCount: numberValue(summary.draft_count ?? summary.draftCount),
    submittedCount: numberValue(summary.submitted_count ?? summary.submittedCount),
    withdrawnCount: numberValue(summary.withdrawn_count ?? summary.withdrawnCount),
    conflictCount: numberValue(summary.conflict_count ?? summary.conflictCount),
    totalAmount: text(summary.total_amount ?? summary.totalAmount, "0.00"),
  };
}

function mapDetailRow(row: ApiNoOaBankBatchDetailRow = {}): NoOaBankBatchDetailRow {
  return {
    transactionId: text(row.transaction_id ?? row.transactionId ?? row.id),
    tradeTime: text(row.trade_time ?? row.tradeTime),
    counterpartyName: text(row.counterparty_name ?? row.counterpartyName),
    direction: text(row.direction),
    directionLabel: text(row.direction_label ?? row.directionLabel),
    amount: text(row.amount, "0.00"),
    summary: text(row.summary),
    purpose: text(row.purpose),
    remark: text(row.remark ?? row.note),
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
