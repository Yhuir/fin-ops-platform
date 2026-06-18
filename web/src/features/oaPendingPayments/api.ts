import { apiRequestJson } from "../apiClient";
import type {
  OaPendingPaymentDetailResponse,
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFilter,
  OaPendingPaymentFilterOptionsResponse,
  OaPendingPaymentQuery,
  OaPendingPaymentRowsResponse,
  OaPendingPaymentSortDirection,
  ConfirmOaPendingPaymentPaidRequest,
  ConfirmOaPendingPaymentPaidResponse,
  LinkOaPendingPaymentBankTransactionsRequest,
  LinkOaPendingPaymentBankTransactionsResponse,
  OaPendingPaymentBankCandidateRelationStatus,
  OaPendingPaymentBankCandidatesResponse,
} from "./types";

type FetchRowsRequest = Pick<
  OaPendingPaymentQuery,
  "page" | "pageSize" | "keyword" | "month" | "tradeDateFrom" | "tradeDateTo" | "filters" | "sortField" | "sortDirection" | "viewMode"
> & {
  signal?: AbortSignal;
};

type FetchFilterOptionsRequest = Pick<
  OaPendingPaymentQuery,
  "keyword" | "month" | "tradeDateFrom" | "tradeDateTo" | "filters" | "viewMode"
> & {
  signal?: AbortSignal;
};

export function nextOaPendingPaymentSortDirection(
  currentField: string,
  currentDirection: OaPendingPaymentSortDirection | "",
  field: string,
): OaPendingPaymentSortDirection {
  if (currentField !== field) {
    return "desc";
  }
  return currentDirection === "desc" ? "asc" : "desc";
}

export async function fetchOaPendingPaymentRows(request: FetchRowsRequest): Promise<OaPendingPaymentRowsResponse> {
  const params = new URLSearchParams();
  appendRowsQuery(params, request);
  return apiRequestJson<OaPendingPaymentRowsResponse>(`/api/oa-pending-payments/rows?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
}

export async function fetchOaPendingPaymentFilterOptions(
  request: FetchFilterOptionsRequest,
): Promise<OaPendingPaymentFilterOptionsResponse> {
  const params = new URLSearchParams();
  appendContextQuery(params, request);
  return apiRequestJson<OaPendingPaymentFilterOptionsResponse>(`/api/oa-pending-payments/filter-options?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
}

export async function fetchOaPendingPaymentDetail(
  target: OaPendingPaymentDetailTarget,
): Promise<OaPendingPaymentDetailResponse> {
  if (target.kind === "oa") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(`/api/oa-pending-payments/oa/${encodeURIComponent(target.id)}/detail`);
  }
  if (target.kind === "bank") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(`/api/oa-pending-payments/bank-transactions/${encodeURIComponent(target.id)}/detail`);
  }
  if (target.kind === "invoice") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(`/api/oa-pending-payments/invoices/${encodeURIComponent(target.id)}/detail`);
  }
  const kind = target.relationKind ?? "bank";
  return apiRequestJson<OaPendingPaymentDetailResponse>(
    `/api/oa-pending-payments/rows/${encodeURIComponent(target.rowId ?? target.id)}/relation-details?kind=${encodeURIComponent(kind)}`,
  );
}

export async function confirmOaPendingPaymentPaid(
  request: ConfirmOaPendingPaymentPaidRequest,
): Promise<ConfirmOaPendingPaymentPaidResponse> {
  return apiRequestJson<ConfirmOaPendingPaymentPaidResponse>("/api/oa-pending-payments/confirm-paid", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      oa_row_id: request.oaRowId,
      bank_transaction_id: request.bankTransactionId,
      bank_transaction_ids: request.bankTransactionIds,
      idempotency_key: request.idempotencyKey,
    }),
  });
}

export async function fetchOaPendingPaymentBankCandidates({
  relationStatus = "all",
  keyword = "",
  page = 1,
  pageSize = 100,
  signal,
}: {
  relationStatus?: OaPendingPaymentBankCandidateRelationStatus;
  keyword?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
} = {}): Promise<OaPendingPaymentBankCandidatesResponse> {
  const params = new URLSearchParams();
  params.set("relation_status", relationStatus);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (keyword.trim()) {
    params.set("keyword", keyword.trim());
  }
  return apiRequestJson<OaPendingPaymentBankCandidatesResponse>(`/api/oa-pending-payments/bank-transaction-candidates?${params.toString()}`, {
    method: "GET",
    signal,
  });
}

export async function linkOaPendingPaymentBankTransactions(
  request: LinkOaPendingPaymentBankTransactionsRequest,
): Promise<LinkOaPendingPaymentBankTransactionsResponse> {
  return apiRequestJson<LinkOaPendingPaymentBankTransactionsResponse>("/api/oa-pending-payments/link-bank-transactions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      oa_row_ids: request.oaRowIds,
      bank_transaction_ids: request.bankTransactionIds,
      idempotency_key: request.idempotencyKey,
    }),
  });
}

function appendRowsQuery(params: URLSearchParams, request: FetchRowsRequest) {
  params.set("page", String(request.page));
  params.set("page_size", String(request.pageSize));
  appendContextQuery(params, request);
  if (request.sortField && request.sortDirection) {
    params.set("sort_field", request.sortField);
    params.set("sort_direction", request.sortDirection);
  }
}

function appendContextQuery(params: URLSearchParams, request: FetchFilterOptionsRequest) {
  if (request.keyword.trim()) {
    params.set("keyword", request.keyword.trim());
  }
  if (request.month) {
    params.set("month", request.month);
  }
  if (request.tradeDateFrom) {
    params.set("trade_date_from", request.tradeDateFrom);
  }
  if (request.tradeDateTo) {
    params.set("trade_date_to", request.tradeDateTo);
  }
  if (request.filters.length > 0) {
    params.set("filters", encodeFilters(request.filters));
  }
  params.set("view_mode", request.viewMode);
}

function encodeFilters(filters: OaPendingPaymentFilter[]) {
  return encodeURIComponent(JSON.stringify(filters));
}
