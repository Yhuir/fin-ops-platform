import { apiRequestJson } from "../apiClient";
import type { OperationBarrierTarget } from "../operationBarrier/api";
import type { BackgroundJob, BackgroundJobActivePayload, BackgroundJobStatus } from "./types";

export type ApiBackgroundJob = {
  job_id?: string;
  jobId?: string;
  type?: string;
  label?: string;
  short_label?: string;
  shortLabel?: string;
  status?: string;
  phase?: string;
  current?: number;
  total?: number;
  percent?: number;
  message?: string;
  result_summary?: Record<string, unknown>;
  resultSummary?: Record<string, unknown>;
  source?: Record<string, unknown>;
  retryable?: boolean;
  retry_mode?: string;
  retryMode?: string;
  acknowledgeable?: boolean;
  attention?: boolean;
  superseded_by_job_id?: string | null;
  supersededByJobId?: string | null;
  affected_months?: string[];
  affectedMonths?: string[];
  error?: string | null;
  created_at?: string;
  createdAt?: string;
  updated_at?: string;
  updatedAt?: string;
  finished_at?: string | null;
  finishedAt?: string | null;
};

type ApiBackgroundJobActivePayload = {
  jobs?: ApiBackgroundJob[];
};

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  return apiRequestJson<T>(url, init, {
    defaultErrorMessage: "后台任务操作失败。",
  });
}

function toNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function toBackgroundJobStatus(value: unknown): BackgroundJobStatus {
  const status = typeof value === "string" ? value : "";
  if (
    status === "queued"
    || status === "running"
    || status === "succeeded"
    || status === "partial_success"
    || status === "failed"
    || status === "cancelled"
    || status === "acknowledged"
    || status === "superseded"
  ) {
    return status;
  }
  return "queued";
}

function toStringArray(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function cleanOperationBarrierTargets(value: unknown): OperationBarrierTarget[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const targets: OperationBarrierTarget[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const record = item as Record<string, unknown>;
    const readModelKey = String(record.readModelKey ?? record.read_model_key ?? "").trim();
    const scopeKey = String(record.scopeKey ?? record.scope_key ?? "").trim();
    const scopeType = String(record.scopeType ?? record.scope_type ?? "").trim();
    if (!readModelKey || !scopeKey || scopeKey === "all") {
      continue;
    }
    const target = {
      readModelKey,
      scopeKey,
      ...(scopeType ? { scopeType } : {}),
    };
    if (!targets.some((candidate) =>
      candidate.readModelKey === target.readModelKey
      && candidate.scopeKey === target.scopeKey
      && candidate.scopeType === target.scopeType
    )) {
      targets.push(target);
    }
  }
  return targets;
}

export function mapBackgroundJob(job: ApiBackgroundJob): BackgroundJob {
  const jobId = job.job_id ?? job.jobId ?? "";
  const resultSummary = job.result_summary ?? job.resultSummary ?? {};
  const operationBarrierTargets = cleanOperationBarrierTargets(
    resultSummary.operationBarrierTargets ?? resultSummary.operation_barrier_targets,
  );
  return {
    jobId,
    type: job.type ?? "file_import",
    label: job.label ?? "后台任务",
    shortLabel: job.short_label ?? job.shortLabel ?? job.message ?? job.label ?? "后台任务处理中",
    status: toBackgroundJobStatus(job.status),
    phase: job.phase ?? "",
    current: toNumber(job.current),
    total: toNumber(job.total),
    percent: toNumber(job.percent),
    message: job.message ?? "",
    resultSummary,
    affectedScopeKeys: toStringArray(resultSummary.affectedScopeKeys ?? resultSummary.affected_scope_keys)
      .filter((scopeKey) => scopeKey !== "all"),
    readModelScopeKeys: toStringArray(resultSummary.readModelScopeKeys ?? resultSummary.read_model_scope_keys)
      .filter((scopeKey) => scopeKey !== "all"),
    operationBarrierTargets,
    source: job.source ?? {},
    retryable: job.retryable === true,
    retryMode: job.retry_mode ?? job.retryMode ?? "",
    acknowledgeable: job.acknowledgeable === true,
    attention: job.attention === true,
    supersededByJobId: job.superseded_by_job_id ?? job.supersededByJobId ?? null,
    affectedMonths: toStringArray(job.affected_months ?? job.affectedMonths ?? resultSummary.affectedMonths ?? resultSummary.affected_months),
    error: job.error ?? null,
    createdAt: job.created_at ?? job.createdAt ?? "",
    updatedAt: job.updated_at ?? job.updatedAt ?? "",
    finishedAt: job.finished_at ?? job.finishedAt ?? null,
  };
}

export async function fetchActiveBackgroundJobs(signal?: AbortSignal): Promise<BackgroundJobActivePayload> {
  const payload = await requestJson<ApiBackgroundJobActivePayload>("/api/background-jobs/active", {
    method: "GET",
    signal,
  });
  return {
    jobs: (payload.jobs ?? []).map(mapBackgroundJob).filter((job) => job.jobId),
  };
}

export async function acknowledgeBackgroundJob(jobId: string, signal?: AbortSignal): Promise<BackgroundJob> {
  const payload = await requestJson<{ job?: ApiBackgroundJob }>(`/api/background-jobs/${encodeURIComponent(jobId)}/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal,
  });
  return mapBackgroundJob(payload.job ?? { job_id: jobId, status: "acknowledged" });
}

export async function retryBackgroundJob(job: BackgroundJob, signal?: AbortSignal): Promise<void> {
  if (!job.retryable) {
    throw new Error("当前后台任务没有可用的重新执行入口");
  }
  await requestJson<unknown>(`/api/background-jobs/${encodeURIComponent(job.jobId)}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal,
  });
}

export async function retryBackgroundJobById(jobId: string, signal?: AbortSignal): Promise<void> {
  await requestJson<unknown>(`/api/background-jobs/${encodeURIComponent(jobId)}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    signal,
  });
}
