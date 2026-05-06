import { apiUrl } from "../../app/runtime";
import { readOATokenCookie } from "../session/api";
import type {
  ApiAppHealthPayload,
  ApiOaSyncStatus,
  AppHealthBackgroundJobsSource,
  AppHealthOaSyncSource,
  AppHealthWorkbenchSource,
} from "./types";

function withAuthHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method: "GET",
    credentials: "include",
    headers: withAuthHeaders(),
    signal,
  });
  const rawText = await response.text();
  const payload = rawText.trim().length > 0 ? JSON.parse(rawText) as T : {} as T;
  if (!response.ok) {
    const error = new Error(rawText.trim() || "App health request failed");
    error.name = response.status === 401
      ? "AppHealthUnauthorizedError"
      : response.status === 403
        ? "AppHealthForbiddenError"
        : "AppHealthRequestError";
    throw error;
  }
  return payload;
}

export function mapOaSyncSource(payload: ApiOaSyncStatus | null | undefined): AppHealthOaSyncSource {
  if (!payload) {
    return "unknown";
  }
  const status = String(payload.status ?? "").trim();
  if (status === "error") {
    return "error";
  }
  if (status === "refreshing") {
    return "refreshing";
  }
  const dirtyScopes = payload.dirty_scopes ?? payload.dirtyScopes ?? [];
  if (dirtyScopes.length > 0) {
    return "dirty";
  }
  return "idle";
}

export function mapAppHealthBackgroundJobsSource(payload: ApiAppHealthPayload | null | undefined): AppHealthBackgroundJobsSource {
  const jobs = payload?.background_jobs;
  if (!jobs) {
    return "idle";
  }
  if ((jobs.running ?? 0) > 0 || (jobs.queued ?? 0) > 0) {
    return "running";
  }
  if ((jobs.attention ?? 0) > 0) {
    return "attention";
  }
  return "idle";
}

export function mapAppHealthWorkbenchSource(payload: ApiAppHealthPayload | null | undefined): AppHealthWorkbenchSource {
  const status = String(payload?.workbench_read_model?.status ?? "").trim();
  if (status === "error") {
    return "error";
  }
  if (status === "rebuilding") {
    return "stale";
  }
  if (status === "stale") {
    return "stale";
  }
  if (status === "ready") {
    return "ready";
  }
  return "unknown";
}

export async function fetchOaSyncStatus(signal?: AbortSignal): Promise<ApiOaSyncStatus> {
  return requestJson<ApiOaSyncStatus>("/api/oa-sync/status", signal);
}

export async function fetchAppHealth(signal?: AbortSignal): Promise<ApiAppHealthPayload> {
  return requestJson<ApiAppHealthPayload>("/api/app-health", signal);
}

export type AppHealthSubscription = {
  close: () => void;
};

export function subscribeAppHealth(
  onSnapshot: (payload: ApiAppHealthPayload) => void,
  onError: (error: unknown) => void,
): AppHealthSubscription | null {
  if (typeof globalThis.EventSource !== "function") {
    return null;
  }

  const eventSource = new EventSource(apiUrl("/api/app-health/stream"), {
    withCredentials: true,
  });
  let closed = false;

  const close = () => {
    if (closed) {
      return;
    }
    closed = true;
    eventSource.close();
  };

  eventSource.addEventListener("app_health", (event) => {
    try {
      onSnapshot(JSON.parse(event.data) as ApiAppHealthPayload);
    } catch (error) {
      close();
      onError(error);
    }
  });

  eventSource.onerror = (event) => {
    close();
    onError(event);
  };

  return { close };
}
