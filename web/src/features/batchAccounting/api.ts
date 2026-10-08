import { apiRequestJson } from "../apiClient";
import type { BatchAccountingHistoryDetail, BatchAccountingHistoryResponse } from "./types";

export function fetchBatchAccountingHistory({ bankYear, page, pageSize, signal }: {
  bankYear: string; page: number; pageSize: number; signal?: AbortSignal;
}) {
  const params = new URLSearchParams({ bank_year: bankYear, page: String(page), page_size: String(pageSize) });
  return apiRequestJson<BatchAccountingHistoryResponse>(`/api/batch-accounting?${params}`, { method: "GET", signal });
}

export function fetchBatchAccountingHistoryDetail(relationId: string, signal?: AbortSignal) {
  return apiRequestJson<BatchAccountingHistoryDetail>(`/api/batch-accounting/relations/${encodeURIComponent(relationId)}`, { method: "GET", signal });
}
