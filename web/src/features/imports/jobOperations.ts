import { apiRequestJson } from "../apiClient";

export type ImportDisposition = { action: "close" | "discard"; reason: string; note: string; actor_account: string; actor_name: string; handled_at: string };
export type ImportOperationJob = {
  job_id: string; import_type: string; session_id: string | null; created_by: string | null;
  status: string; stage: string; version: number; updated_at: string; file_count?: number; file_name?: string | null;
  affected_domains: string[]; error_code: string | null; last_error?: string | null;
  disposition: ImportDisposition | null; allowed_actions?: Array<"close" | "discard">; continue_route?: string | null;
};
export type ImportJobPage = { rows: ImportOperationJob[]; pagination: { page: number; page_size: number; total: number; has_more: boolean } };
export type ImportJobDetail = {
  job: ImportOperationJob;
  files: Array<{ file_id: string; file_name: string | null; status: string; message: string | null;
    error_count: string | null; suspected_duplicate_count: string | null; preview_batch_id: string | null;
    row_count: number; linked_count: number; identity_match_count: number }>;
  file_pagination: ImportJobPage["pagination"];
};
const root = "/api/imports/jobs";
export function fetchImportJobs(page: number, signal?: AbortSignal) {
  return apiRequestJson<ImportJobPage>(`${root}?page=${page}&page_size=20`, { signal });
}
export function fetchImportJobDetail(id: string, page = 1, signal?: AbortSignal) {
  return apiRequestJson<ImportJobDetail>(`${root}/${encodeURIComponent(id)}?file_page=${page}`, { signal });
}
export function disposeImportJob(job: ImportOperationJob, action: "close" | "discard", reason: string, note: string) {
  return apiRequestJson<{ disposition: ImportDisposition; version: number; status: string; idempotent_replay: boolean }>(
    `${root}/${encodeURIComponent(job.job_id)}/dispose`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: job.version, action, reason, note }) },
    { allowHtmlFallback: false, timeoutMs: 15000, defaultErrorMessage: "任务处理失败，请核实当前结果。" },
  );
}
