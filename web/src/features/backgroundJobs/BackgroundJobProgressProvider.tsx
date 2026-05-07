import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { acknowledgeBackgroundJob, fetchActiveBackgroundJobs, retryBackgroundJob } from "./api";
import type { BackgroundJob } from "./types";

const RUNNING_POLL_MS = 1000;
const IDLE_POLL_MS = 12000;
const HIDDEN_POLL_MS = 30000;
const SUCCEEDED_VISIBLE_MS = 8000;
const MAX_FAILURES_BEFORE_WARNING = 3;

type BackgroundJobProgressContextValue = {
  jobs: BackgroundJob[];
  primaryJob: BackgroundJob | null;
  extraCount: number;
  connectionFailed: boolean;
  acknowledgeJob: (jobId: string) => Promise<void>;
  retryJob: (jobId: string) => Promise<void>;
  refresh: () => Promise<void>;
};

const BackgroundJobProgressContext = createContext<BackgroundJobProgressContextValue | null>(null);

function jobPriority(job: BackgroundJob) {
  if (job.status === "failed") {
    return 0;
  }
  if (job.status === "partial_success") {
    return 1;
  }
  if (job.status === "running") {
    return 2;
  }
  if (job.status === "queued") {
    return 3;
  }
  if (job.status === "succeeded") {
    return 4;
  }
  return 5;
}

function jobTime(job: BackgroundJob) {
  const value = Date.parse(job.updatedAt || job.createdAt || "");
  return Number.isFinite(value) ? value : 0;
}

function choosePrimaryJob(jobs: BackgroundJob[]) {
  return [...jobs].sort((left, right) => {
    const priorityDelta = jobPriority(left) - jobPriority(right);
    if (priorityDelta !== 0) {
      return priorityDelta;
    }
    return jobTime(right) - jobTime(left);
  })[0] ?? null;
}

function hasQueuedOrRunningJob(jobs: BackgroundJob[]) {
  return jobs.some((job) => job.status === "queued" || job.status === "running");
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

export function BackgroundJobProgressProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [failureCount, setFailureCount] = useState(0);
  const jobsRef = useRef<BackgroundJob[]>([]);
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const succeededFirstSeenRef = useRef<Map<string, number>>(new Map());

  const applyJobs = useCallback((nextJobs: BackgroundJob[]) => {
    const now = Date.now();
    const nextSucceededSeen = new Map<string, number>();
    const visibleJobs = nextJobs.filter((job) => {
      if (job.status !== "succeeded") {
        return true;
      }
      const firstSeenAt = succeededFirstSeenRef.current.get(job.jobId) ?? now;
      nextSucceededSeen.set(job.jobId, firstSeenAt);
      return now - firstSeenAt <= SUCCEEDED_VISIBLE_MS;
    });
    succeededFirstSeenRef.current = nextSucceededSeen;
    jobsRef.current = visibleJobs;
    setJobs(visibleJobs);
  }, []);

  const refresh = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const payload = await fetchActiveBackgroundJobs(controller.signal);
      applyJobs(payload.jobs);
      setFailureCount(0);
    } catch (error) {
      if (!isAbortError(error)) {
        setFailureCount((current) => current + 1);
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    }
  }, [applyJobs]);

  const acknowledgeJob = useCallback(
    async (jobId: string) => {
      await acknowledgeBackgroundJob(jobId);
      const nextJobs = jobsRef.current.filter((job) => job.jobId !== jobId);
      jobsRef.current = nextJobs;
      setJobs(nextJobs);
      void refresh();
    },
    [refresh],
  );

  const retryJob = useCallback(
    async (jobId: string) => {
      const job = jobsRef.current.find((item) => item.jobId === jobId);
      if (!job) {
        throw new Error("后台任务不存在，无法重新执行。");
      }
      await retryBackgroundJob(job);
      await refresh();
    },
    [refresh],
  );

  useEffect(() => {
    let mounted = true;

    const clearPollTimer = () => {
      if (timerRef.current !== null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };

    const schedule = () => {
      if (!mounted) {
        return;
      }
      clearPollTimer();
      const delay =
        document.visibilityState === "hidden"
          ? HIDDEN_POLL_MS
          : hasQueuedOrRunningJob(jobsRef.current)
            ? RUNNING_POLL_MS
            : IDLE_POLL_MS;
      timerRef.current = window.setTimeout(async () => {
        await refresh();
        schedule();
      }, delay);
    };

    const refreshAndSchedule = async () => {
      await refresh();
      schedule();
    };

    const handleFocus = () => {
      void refreshAndSchedule();
    };
    const handleVisibilityChange = () => {
      void refreshAndSchedule();
    };

    void refreshAndSchedule();
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      mounted = false;
      clearPollTimer();
      abortRef.current?.abort();
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [refresh]);

  const primaryJob = useMemo(() => choosePrimaryJob(jobs), [jobs]);
  const value = useMemo(
    () => ({
      jobs,
      primaryJob,
      extraCount: Math.max(0, jobs.length - 1),
      connectionFailed: !primaryJob && failureCount >= MAX_FAILURES_BEFORE_WARNING,
      acknowledgeJob,
      retryJob,
      refresh,
    }),
    [acknowledgeJob, failureCount, jobs, primaryJob, refresh, retryJob],
  );

  return (
    <BackgroundJobProgressContext.Provider value={value}>
      {children}
    </BackgroundJobProgressContext.Provider>
  );
}

export function useBackgroundJobProgress() {
  const context = useContext(BackgroundJobProgressContext);
  if (!context) {
    throw new Error("useBackgroundJobProgress must be used within BackgroundJobProgressProvider");
  }
  return context;
}
