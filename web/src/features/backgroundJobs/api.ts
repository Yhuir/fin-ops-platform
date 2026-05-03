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
  const payload = rawText.trim().length > 0 ? JSON.parse(rawText) as T : {} as T;
  if (!response.ok) {
    throw new Error(rawText.trim() || "Background jobs request failed");
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
  ) {
    return status;
  }
  return "queued";
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
    signal,
  });
  return mapBackgroundJob(payload.job ?? { job_id: jobId, status: "acknowledged" });
}
