export type AppHealthLevel = "ok" | "busy" | "blocked";

export type AppHealthSessionSource = "loading" | "authenticated" | "expired" | "forbidden" | "error";
export type AppHealthBackgroundJobsSource = "idle" | "running" | "attention" | "unreachable";
export type AppHealthImportProgressSource = "idle" | "running" | "error";
export type AppHealthOaSyncSource = "unknown" | "idle" | "refreshing" | "dirty" | "error";
export type AppHealthWorkbenchSource = "unknown" | "loading" | "ready" | "stale" | "error";

export type AppHealthSources = {
  session: AppHealthSessionSource;
  backgroundJobs: AppHealthBackgroundJobsSource;
  importProgress: AppHealthImportProgressSource;
  oaSync: AppHealthOaSyncSource;
  workbench: AppHealthWorkbenchSource;
};

export type AppHealthStatus = {
  level: AppHealthLevel;
  reason: string;
  details: string[];
  blocksMutations: boolean;
  sources: AppHealthSources;
};

export type ApiAppHealthPayload = {
  status?: string;
  generated_at?: string;
  version?: number;
  session?: {
    status?: string;
  };
  oa_sync?: ApiOaSyncStatus;
  workbench_read_model?: {
    status?: string;
    dirty_scopes?: string[];
    stale_scopes?: string[];
    rebuilding_scopes?: string[];
  };
  background_jobs?: {
    active?: number;
    queued?: number;
    running?: number;
    attention?: number;
  };
  dependencies?: Record<string, { status?: string; message?: string } | unknown>;
  metrics?: Record<string, number | string | boolean | null | undefined>;
  alerts?: unknown[];
};

export type ApiOaSyncStatus = {
  status?: string;
  message?: string;
  dirty_scopes?: string[];
  dirtyScopes?: string[];
  changed_scopes?: string[];
  changedScopes?: string[];
  version?: number | null;
  last_synced_at?: string | null;
  lastSyncedAt?: string | null;
};
