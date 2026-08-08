import { apiRequestJson } from "../apiClient";

export type OperationHistoryEvent = {
  id: string;
  event_type: string;
  actor_id?: string | null;
  actor_name?: string | null;
  action?: string | null;
  page_key?: string | null;
  operation_location?: string | null;
  object_type?: string | null;
  object_id?: string | null;
  occurred_at: string;
  outcome: string;
  reason?: string | null;
  request_id?: string | null;
  payload: {
    before?: unknown;
    after?: unknown;
    metadata?: Record<string, unknown>;
    summary?: string;
  };
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
  return apiRequestJson<{ rows: OperationHistoryEvent[]; next_cursor: string | null; limit: number }>(
    `/api/operations/audit-events?${query.toString()}`,
    { method: "GET", signal },
  );
}

export async function fetchOperationHistoryEvent(eventId: string, signal?: AbortSignal) {
  return apiRequestJson<{ event: OperationHistoryEvent }>(
    `/api/operations/audit-events/${encodeURIComponent(eventId)}`,
    { method: "GET", signal },
  );
}
