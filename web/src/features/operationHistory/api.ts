import { apiFetch, apiRequestJson } from "../apiClient";

export type OperationHistoryField = {
  label: string;
  value: string;
};

export type OperationHistoryTarget = {
  kind: string;
  title: string;
  fields: OperationHistoryField[];
};

export type OperationHistoryArtifact = {
  artifact_key: string;
  kind: "file";
  title: string;
  media_type?: string | null;
  size_bytes?: number | null;
  preview_url?: string | null;
  availability: "available" | "deleted" | "not_saved";
};

export type OperationHistoryRecord = {
  record_key: string;
  kind: string;
  title: string;
  fields: OperationHistoryField[];
};

export type OperationHistoryChange = {
  label: string;
  before?: string | null;
  after?: string | null;
};

export type OperationHistoryDetail = {
  schema_version: number;
  target?: OperationHistoryTarget | null;
  artifacts: OperationHistoryArtifact[];
  records: OperationHistoryRecord[];
  changes: OperationHistoryChange[];
  failure?: { code?: string | null; message: string } | null;
  legacy_evidence_missing: boolean;
};

export type OperationHistoryOperation = {
  operation_key: string;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_account?: string | null;
  page_key?: string | null;
  action_code: string;
  action_label: string;
  action_description: string;
  object_type?: string | null;
  object_label: string;
  started_at: string;
  completed_at?: string | null;
  occurred_at: string;
  outcome: string;
  reason?: string | null;
  detail?: OperationHistoryDetail;
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

export async function fetchOperationArtifact(previewUrl: string, signal?: AbortSignal) {
  const response = await apiFetch(previewUrl, { method: "GET", signal });
  if (!response.ok) {
    throw new Error("凭证预览加载失败，请稍后重试。");
  }
  return response.blob();
}
