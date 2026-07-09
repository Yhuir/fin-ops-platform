import { apiUrl } from "../../app/runtime";
import { ApiClientError, apiRequestJson } from "../apiClient";
import type {
  ApiAppHealthPayload,
  ApiOaSyncStatus,
  AppHealthBackgroundJobsSource,
  AppHealthOaSyncSource,
  AppHealthWorkbenchSource,
  InputInvoiceUsageAuditPayload,
  OperationsDashboardPayload,
  OutputInvoiceCollectionAuditPayload,
} from "./types";

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  try {
    return await apiRequestJson<T>(path, {
      method: "GET",
      signal,
    });
  } catch (error) {
    if (error instanceof ApiClientError) {
      const appHealthError = new Error(error.responseText.trim() || error.message || "App health request failed");
      appHealthError.name = error.status === 401
        ? "AppHealthUnauthorizedError"
        : error.status === 403
          ? "AppHealthForbiddenError"
          : "AppHealthRequestError";
      throw appHealthError;
    }
    throw error;
  }
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

export async function fetchAppHealthDashboard(signal?: AbortSignal): Promise<OperationsDashboardPayload> {
  return requestJson<OperationsDashboardPayload>("/api/operations/app-health-dashboard", signal);
}

export async function fetchInputInvoiceUsageAudit(signal?: AbortSignal): Promise<InputInvoiceUsageAuditPayload> {
  return requestJson<InputInvoiceUsageAuditPayload>("/api/operations/app-health/input-invoice-usage-audit", signal);
}

export async function fetchOutputInvoiceCollectionAudit(signal?: AbortSignal): Promise<OutputInvoiceCollectionAuditPayload> {
  return requestJson<OutputInvoiceCollectionAuditPayload>("/api/operations/app-health/output-invoice-collection-audit", signal);
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
