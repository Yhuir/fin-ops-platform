import { apiRequestJson } from "../apiClient";

export type OperationHistoryItem = {
  item_key: string;
  type: string;
  title: string;
  secondary?: string | null;
  amount?: string | number | null;
  date?: string | null;
  before_status: string;
  after_status: string;
};

export type OperationHistoryOperation = {
  operation_key: string;
  event_id?: string | null;
  request_id?: string | null;
  trace_id?: string | null;
  object_id?: string | null;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_account?: string | null;
  page_key?: string | null;
  action_label: string;
  object_type?: string | null;
  started_at: string;
  completed_at?: string | null;
  occurred_at: string;
  outcome: string;
  reason?: string | null;
  items?: OperationHistoryItem[];
};

export type OperationHistoryActor = {
  actor_id: string;
  actor_name?: string | null;
  actor_account?: string | null;
};

export type OperationHistoryFilters = {
  search?: string;
  actorId?: string;
  pageKey?: string;
  dateFrom?: string;
  dateTo?: string;
};

export async function fetchOperationHistory(
  filters: OperationHistoryFilters,
  cursor?: string | null,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ limit: "50" });
  if (filters.search) query.set("search", filters.search);
  if (filters.actorId) query.set("actor_id", filters.actorId);
  if (filters.pageKey) query.set("page_key", filters.pageKey);
  if (filters.dateFrom) query.set("date_from", filters.dateFrom);
  if (filters.dateTo) query.set("date_to", filters.dateTo);
  if (cursor) query.set("cursor", cursor);
  return apiRequestJson<{ rows: OperationHistoryOperation[]; next_cursor: string | null; limit: number }>(
    `/api/operations/history?${query.toString()}`,
    { method: "GET", signal },
  );
}

export async function fetchOperationHistoryActors(signal?: AbortSignal) {
  return apiRequestJson<{ rows: OperationHistoryActor[] }>(
    "/api/operations/history/actors",
    { method: "GET", signal },
  );
}

export async function fetchOperationHistoryDetail(operationKey: string, signal?: AbortSignal) {
  return apiRequestJson<{ operation: OperationHistoryOperation }>(
    `/api/operations/history/${encodeURIComponent(operationKey)}`,
    { method: "GET", signal },
  );
}
