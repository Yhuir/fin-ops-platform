import { readOATokenCookie } from "../session/api";
import { apiUrl } from "../../app/runtime";
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

function withAuthHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(url), {
    ...init,
    headers: withAuthHeaders(init.headers),
    credentials: init.credentials ?? "include",
  });
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  if (trimmedText && (/^<!doctype\s+html/i.test(trimmedText) || /^<html[\s>]/i.test(trimmedText))) {
    throw new Error("后台任务接口返回了 HTML 页面，请确认后端服务和 /api 代理已正常启动。");
  }
  let payload = {} as T;
  if (trimmedText) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch {
      throw new Error("后台任务接口返回的不是合法 JSON。");
    }
  }
  if (!response.ok) {
    const message = payload && typeof payload === "object" && "message" in payload
      ? String((payload as { message?: unknown }).message || "").trim()
      : "";
    throw new Error(message || trimmedText || "后台任务操作失败。");
  }
  return payload;
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

export function mapBackgroundJob(job: ApiBackgroundJob): BackgroundJob {
  const jobId = job.job_id ?? job.jobId ?? "";
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
    resultSummary: job.result_summary ?? job.resultSummary ?? {},
    source: job.source ?? {},
    retryable: job.retryable === true,
    retryMode: job.retry_mode ?? job.retryMode ?? "",
    acknowledgeable: job.acknowledgeable === true,
    attention: job.attention === true,
    supersededByJobId: job.superseded_by_job_id ?? job.supersededByJobId ?? null,
    affectedMonths: toStringArray(job.affected_months ?? job.affectedMonths),
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
