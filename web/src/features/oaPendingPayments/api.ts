import { apiRequestJson } from "../apiClient";
import type {
  OaPendingPaymentDetailResponse,
  OaPendingPaymentDetailTarget,
  OaPendingPaymentFilter,
  OaPendingPaymentQuery,
  OaPendingPaymentRowsResponse,
  OaPendingPaymentSortDirection,
  WritebackOaPendingPaymentPaidRequest,
  WritebackOaPendingPaymentPaidResponse,
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

type FetchContextRequest = Pick<
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

export async function fetchOaPendingPaymentDetail(
  target: OaPendingPaymentDetailTarget,
): Promise<OaPendingPaymentDetailResponse> {
  const params = new URLSearchParams();
  if (target.scopeKey) {
    params.set("month", target.scopeKey);
  }
  const scopeQuery = params.size > 0 ? `?${params.toString()}` : "";
  if (target.kind === "oa") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(
      `/api/oa-pending-payments/oa/${encodeURIComponent(target.id)}/detail${scopeQuery}`,
    );
  }
  if (target.kind === "bank") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(
      `/api/oa-pending-payments/bank-transactions/${encodeURIComponent(target.id)}/detail${scopeQuery}`,
    );
  }
  if (target.kind === "invoice") {
    return apiRequestJson<OaPendingPaymentDetailResponse>(
      `/api/oa-pending-payments/invoices/${encodeURIComponent(target.id)}/detail${scopeQuery}`,
    );
  }
  const kind = target.relationKind ?? "bank";
  params.set("kind", kind);
  return apiRequestJson<OaPendingPaymentDetailResponse>(
    `/api/oa-pending-payments/rows/${encodeURIComponent(target.rowId ?? target.id)}/relation-details?${params.toString()}`,
  );
}

export async function writebackOaPendingPaymentPaid(
  request: WritebackOaPendingPaymentPaidRequest,
): Promise<WritebackOaPendingPaymentPaidResponse> {
  return apiRequestJson<WritebackOaPendingPaymentPaidResponse>(
    "/api/oa-pending-payments/writeback-paid",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        oa_row_ids: request.oaRowIds,
      }),
    },
  );
}

export async function fetchOaPendingPaymentBankCandidates({
  relationStatus = "all",
  keyword = "",
  oaRowIds = [],
  page = 1,
  pageSize = 100,
  signal,
}: {
  relationStatus?: OaPendingPaymentBankCandidateRelationStatus;
  keyword?: string;
  oaRowIds?: string[];
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
} = {}): Promise<OaPendingPaymentBankCandidatesResponse> {
  const params = new URLSearchParams();
  params.set("relation_status", relationStatus);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  oaRowIds
    .map((rowId) => rowId.trim())
    .filter(Boolean)
    .forEach((rowId) => params.append("oa_row_ids", rowId));
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

function appendContextQuery(params: URLSearchParams, request: FetchContextRequest) {
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
