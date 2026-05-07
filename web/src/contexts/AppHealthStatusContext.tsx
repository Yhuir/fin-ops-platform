import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useAppChrome } from "./AppChromeContext";
import { useImportProgress } from "./ImportProgressContext";
import { useSession, useSessionPermissions } from "./SessionContext";
import { useBackgroundJobProgress } from "../features/backgroundJobs/BackgroundJobProgressProvider";
import {
  fetchAppHealth,
  fetchOaSyncStatus,
  mapAppHealthBackgroundJobsSource,
  mapAppHealthWorkbenchSource,
  mapOaSyncSource,
  subscribeAppHealth,
} from "../features/appHealth/api";
import {
  createAppHealthBroadcast,
  getAppHealthSnapshotGeneratedAt,
  isAppHealthSnapshotFresh,
  type AppHealthBroadcast,
} from "../features/appHealth/broadcast";
import { resolveAppHealthStatus } from "../features/appHealth/resolveAppHealthStatus";
import type {
  ApiAppHealthJobSummary,
  ApiAppHealthPayload,
  ApiOaSyncStatus,
  AppHealthBackgroundJobsSource,
  AppHealthJobSummary,
  AppHealthImportProgressSource,
  AppHealthOaSyncSource,
  AppHealthResolveDetails,
  AppHealthSessionSource,
  AppHealthSources,
  AppHealthStatus,
  AppHealthWorkbenchSource,
} from "../features/appHealth/types";

const HEALTH_POLL_MS = 5000;
const MAX_HEALTH_FAILURES_BEFORE_BLOCKED = 3;

const defaultSources: AppHealthSources = {
  session: "loading",
  backgroundJobs: "idle",
  importProgress: "idle",
  oaSync: "unknown",
  workbench: "unknown",
};

const defaultStatus = resolveAppHealthStatus(defaultSources);

const AppHealthStatusContext = createContext<AppHealthStatus | null>(null);

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

type LocalHealthJob = {
  jobId?: string;
  job_id?: string;
  type?: string;
  label?: string;
  shortLabel?: string;
  short_label?: string;
  status: string;
  message?: string;
  retryable?: boolean;
  acknowledgeable?: boolean;
  affectedMonths?: string[];
  affected_months?: string[];
};

function hasAttentionJob(jobs: LocalHealthJob[]) {
  return jobs.some((job) => job.status === "failed" || job.status === "partial_success");
}

function hasRunningJob(jobs: LocalHealthJob[]) {
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

function sessionSourceFromLocal(sessionStatus: ReturnType<typeof useSession>["status"]): AppHealthSessionSource {
  if (sessionStatus === "authenticated") {
    return "authenticated";
  }
  if (sessionStatus === "expired") {
    return "expired";
  }
  if (sessionStatus === "forbidden") {
    return "forbidden";
  }
  if (sessionStatus === "error") {
    return "error";
  }
  return "loading";
}

function sessionSourceFromApi(payload: ApiAppHealthPayload | null): AppHealthSessionSource | null {
  const status = String(payload?.session?.status ?? "").trim();
  if (status === "authenticated" || status === "expired" || status === "forbidden" || status === "error") {
    return status;
  }
  return null;
}

function backgroundSourceFromLocal(
  jobs: LocalHealthJob[],
  connectionFailed: boolean,
  apiPayload: ApiAppHealthPayload | null,
): AppHealthBackgroundJobsSource {
  if (connectionFailed) {
    return "unreachable";
  }
  if (hasRunningJob(jobs)) {
    return "running";
  }
  if (hasAttentionJob(jobs)) {
    return "attention";
  }
  return mapAppHealthBackgroundJobsSource(apiPayload);
}

function importProgressSource(tone: string | null | undefined): AppHealthImportProgressSource {
  if (tone === "error") {
    return "error";
  }
  if (tone === "loading" || tone === "info") {
    return "running";
  }
  return "idle";
}

function workbenchSourceFromShell(level: "ok" | "pending" | "error" | undefined): AppHealthWorkbenchSource {
  if (level === "error") {
    return "error";
  }
  if (level === "pending") {
    return "loading";
  }
  if (level === "ok") {
    return "ready";
  }
  return "unknown";
}

function dirtyScopeCount(payload: ApiAppHealthPayload | null) {
  const scopes = [
    ...(payload?.workbench_read_model?.dirty_scopes ?? []),
    ...(payload?.workbench_read_model?.stale_scopes ?? []),
    ...(payload?.workbench_read_model?.rebuilding_scopes ?? []),
  ];
  return scopes.length;
}

function cleanStringArray(values: unknown): string[] {
  return Array.isArray(values)
    ? values.map((value) => String(value ?? "").trim()).filter(Boolean)
    : [];
}

function isMonthScope(value: string) {
  return /^\d{4}-\d{2}$/.test(value);
}

function mapApiJobSummary(job: ApiAppHealthJobSummary | null | undefined): AppHealthJobSummary | null {
  if (!job) {
    return null;
  }
  return {
    jobId: job.job_id ?? job.jobId ?? "",
    type: job.type ?? "",
    label: job.label ?? "",
    shortLabel: job.short_label ?? job.shortLabel ?? "",
    status: job.status ?? "",
    message: job.message,
    retryable: job.retryable,
    acknowledgeable: job.acknowledgeable,
    affectedMonths: job.affected_months ?? job.affectedMonths ?? [],
  };
}

function mapLocalJobSummary(job: LocalHealthJob | undefined): AppHealthJobSummary | null {
  if (!job) {
    return null;
  }
  return {
    jobId: job.jobId ?? job.job_id ?? "",
    type: job.type ?? "",
    label: job.label ?? "",
    shortLabel: job.shortLabel ?? job.short_label ?? "",
    status: job.status,
    message: job.message,
    retryable: job.retryable,
    acknowledgeable: job.acknowledgeable,
    affectedMonths: job.affectedMonths ?? job.affected_months ?? [],
  };
}

function jobTime(job: LocalHealthJob) {
  const updatedAt = "updatedAt" in job ? String((job as { updatedAt?: unknown }).updatedAt ?? "") : "";
  const updated_at = "updated_at" in job ? String((job as { updated_at?: unknown }).updated_at ?? "") : "";
  const createdAt = "createdAt" in job ? String((job as { createdAt?: unknown }).createdAt ?? "") : "";
  const value = Date.parse(updatedAt || updated_at || createdAt || "");
  return Number.isFinite(value) ? value : 0;
}

function chooseLocalRunningJob(jobs: LocalHealthJob[]) {
  return [...jobs]
    .filter((job) => job.status === "queued" || job.status === "running")
    .sort((left, right) => jobTime(right) - jobTime(left))[0];
}

function chooseLocalAttentionJob(jobs: LocalHealthJob[]) {
  return [...jobs]
    .filter((job) => job.status === "failed" || job.status === "partial_success")
    .sort((left, right) => {
      const statusDelta = (left.status === "failed" ? 0 : 1) - (right.status === "failed" ? 0 : 1);
      if (statusDelta !== 0) {
        return statusDelta;
      }
      return jobTime(right) - jobTime(left);
    })[0];
}

function oaSyncSourceFromPayload(
  apiPayload: ApiAppHealthPayload | null,
  fallbackOaSync: ApiOaSyncStatus | null,
): AppHealthOaSyncSource {
  if (dirtyScopeCount(apiPayload) > 0) {
    return "dirty";
  }
  const apiSource = mapOaSyncSource(apiPayload?.oa_sync);
  if (apiSource !== "unknown") {
    return apiSource;
  }
  return mapOaSyncSource(fallbackOaSync);
}

function detailFromPayload(
  apiPayload: ApiAppHealthPayload | null,
  fallbackOaSync: ApiOaSyncStatus | null,
  shellReason: string | undefined,
  jobs: LocalHealthJob[],
): AppHealthResolveDetails {
  const dependencyMessage = Object.values(apiPayload?.dependencies ?? {}).find((dependency) => {
    if (!dependency || typeof dependency !== "object") {
      return false;
    }
    return typeof (dependency as { message?: unknown }).message === "string";
  }) as { message?: string } | undefined;
  const fallbackReason = (
    dependencyMessage?.message
    ?? apiPayload?.oa_sync?.message
    ?? fallbackOaSync?.message
    ?? shellReason
    ?? ""
  );
  const backgroundJobs = apiPayload?.background_jobs;
  const workbench = apiPayload?.workbench_read_model;
  const matchingDirtyEntries = Array.isArray(workbench?.matching_dirty_scopes)
    ? workbench?.matching_dirty_scopes ?? []
    : [];
  const matchingDirtyMonths = matchingDirtyEntries
    .map((entry) => String(entry?.scope_month ?? "").trim())
    .filter(Boolean);
  return {
    fallbackReason,
    details: [
      dependencyMessage?.message,
      workbench?.last_matching_error ?? undefined,
      shellReason,
    ].filter(Boolean) as string[],
    primaryRunning: mapApiJobSummary(backgroundJobs?.primary_running ?? backgroundJobs?.primaryRunning) ?? mapLocalJobSummary(chooseLocalRunningJob(jobs)),
    primaryAttention: mapApiJobSummary(backgroundJobs?.primary_attention ?? backgroundJobs?.primaryAttention) ?? mapLocalJobSummary(chooseLocalAttentionJob(jobs)),
    attentionCount: backgroundJobs?.attention ?? jobs.filter((job) => job.status === "failed" || job.status === "partial_success").length,
    matchingRunningMonths: cleanStringArray(workbench?.matching_running_scopes),
    matchingDirtyMonths: matchingDirtyMonths.length > 0
      ? matchingDirtyMonths
      : cleanStringArray(workbench?.dirty_scopes ?? []).filter(isMonthScope),
    matchingError: workbench?.last_matching_error ?? null,
  };
}

export function AppHealthStatusProvider({ children }: { children: ReactNode }) {
  const session = useSession();
  const { canMutateData } = useSessionPermissions();
  const { jobs, connectionFailed } = useBackgroundJobProgress();
  const { progress } = useImportProgress();
  const { workbenchStatus } = useAppChrome();
  const [apiPayload, setApiPayload] = useState<ApiAppHealthPayload | null>(null);
  const [fallbackOaSync, setFallbackOaSync] = useState<ApiOaSyncStatus | null>(null);
  const [remoteSessionSource, setRemoteSessionSource] = useState<AppHealthSessionSource | null>(null);
  const [failureCount, setFailureCount] = useState(0);
  const [sseUnavailable, setSseUnavailable] = useState(false);
  const broadcastRef = useRef<AppHealthBroadcast | null>(null);
  const latestSnapshotGeneratedAtRef = useRef<string | null>(null);

  const applyAppHealthSnapshot = useCallback((
    payload: ApiAppHealthPayload,
    options: { broadcast?: boolean; generatedAt?: string } = {},
  ) => {
    const generatedAt = options.generatedAt ?? getAppHealthSnapshotGeneratedAt(payload);
    if (!isAppHealthSnapshotFresh(generatedAt, latestSnapshotGeneratedAtRef.current)) {
      return false;
    }
    latestSnapshotGeneratedAtRef.current = generatedAt;
    setApiPayload(payload);
    setRemoteSessionSource(sessionSourceFromApi(payload));
    setFailureCount(0);
    if (options.broadcast !== false) {
      broadcastRef.current?.publish(payload, generatedAt);
    }
    return true;
  }, []);

  useEffect(() => {
    if (session.status !== "authenticated") {
      return undefined;
    }

    const broadcast = createAppHealthBroadcast((message) => {
      applyAppHealthSnapshot(message.payload, {
        broadcast: false,
        generatedAt: message.generatedAt,
      });
    });
    broadcastRef.current = broadcast;

    return () => {
      if (broadcastRef.current === broadcast) {
        broadcastRef.current = null;
      }
      broadcast?.close();
    };
  }, [applyAppHealthSnapshot, session.status]);

  useEffect(() => {
    if (session.status !== "authenticated") {
      setApiPayload(null);
      setFallbackOaSync(null);
      setRemoteSessionSource(null);
      setFailureCount(0);
      setSseUnavailable(false);
      latestSnapshotGeneratedAtRef.current = null;
      return undefined;
    }

    let mounted = true;
    let timerId: number | null = null;
    let controller: AbortController | null = null;
    let sseSubscription: { close: () => void } | null = null;

    const clearTimer = () => {
      if (timerId !== null) {
        window.clearTimeout(timerId);
        timerId = null;
      }
    };

    const poll = async () => {
      controller?.abort();
      controller = new AbortController();
      try {
        const payload = await fetchAppHealth(controller.signal);
        if (!mounted) {
          return;
        }
        applyAppHealthSnapshot(payload);
      } catch (error) {
        if (!mounted || isAbortError(error)) {
          return;
        }
        const name = error instanceof Error ? error.name : "";
        if (name === "AppHealthUnauthorizedError") {
          setRemoteSessionSource("expired");
        } else if (name === "AppHealthForbiddenError") {
          setRemoteSessionSource("forbidden");
        } else {
          try {
            const fallback = await fetchOaSyncStatus(controller.signal);
            if (!mounted) {
              return;
            }
            setFallbackOaSync(fallback);
            setFailureCount(0);
          } catch (fallbackError) {
            if (!mounted || isAbortError(fallbackError)) {
              return;
            }
            setFailureCount((current) => current + 1);
          }
        }
      } finally {
        if (mounted) {
          clearTimer();
          timerId = window.setTimeout(() => void poll(), HEALTH_POLL_MS);
        }
      }
    };

    if (!sseUnavailable) {
      sseSubscription = subscribeAppHealth(
        (payload) => {
          if (mounted) {
            applyAppHealthSnapshot(payload);
          }
        },
        () => {
          if (!mounted) {
            return;
          }
          sseSubscription?.close();
          sseSubscription = null;
          setSseUnavailable(true);
        },
      );
    }

    if (!sseSubscription) {
      void poll();
    }

    const handleFocus = () => {
      if (!sseSubscription) {
        void poll();
      }
    };
    window.addEventListener("focus", handleFocus);

    return () => {
      mounted = false;
      clearTimer();
      controller?.abort();
      sseSubscription?.close();
      window.removeEventListener("focus", handleFocus);
    };
  }, [applyAppHealthSnapshot, session.status, sseUnavailable]);

  const value = useMemo<AppHealthStatus>(() => {
    const localSessionSource = sessionSourceFromLocal(session.status);
    const sessionSource =
      remoteSessionSource && localSessionSource === "authenticated"
        ? remoteSessionSource
        : localSessionSource;
    const backgroundJobs =
      failureCount >= MAX_HEALTH_FAILURES_BEFORE_BLOCKED
        ? "unreachable"
        : backgroundSourceFromLocal(jobs, connectionFailed, apiPayload);
    const importProgress = importProgressSource(progress?.tone);
    const apiWorkbenchSource = mapAppHealthWorkbenchSource(apiPayload);
    const shellWorkbenchSource = workbenchSourceFromShell(workbenchStatus?.level);
    const workbench =
      apiWorkbenchSource !== "unknown"
        ? apiWorkbenchSource
        : shellWorkbenchSource;
    const sources: AppHealthSources = {
      session: sessionSource,
      backgroundJobs,
      importProgress,
      oaSync: oaSyncSourceFromPayload(apiPayload, fallbackOaSync),
      workbench,
    };
    const detailReason = detailFromPayload(apiPayload, fallbackOaSync, workbenchStatus?.reason, jobs);
    const resolved = resolveAppHealthStatus(sources, detailReason);
    return canMutateData ? resolved : { ...resolved, blocksMutations: true };
  }, [
    apiPayload,
    canMutateData,
    connectionFailed,
    failureCount,
    fallbackOaSync,
    jobs,
    progress?.tone,
    remoteSessionSource,
    session.status,
    workbenchStatus?.level,
    workbenchStatus?.reason,
  ]);

  return <AppHealthStatusContext.Provider value={value}>{children}</AppHealthStatusContext.Provider>;
}

export function useAppHealthStatus() {
  const context = useContext(AppHealthStatusContext);
  if (!context) {
    return defaultStatus;
  }
  return context;
}

export function useCanMutateWithHealth() {
  const { canMutateData } = useSessionPermissions();
  const healthStatus = useAppHealthStatus();
  return canMutateData && !healthStatus.blocksMutations;
}
