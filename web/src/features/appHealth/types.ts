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

export type AppHealthJobSummary = {
  jobId: string;
  type: string;
  label: string;
  shortLabel: string;
  status: string;
  message?: string;
  retryable?: boolean;
  acknowledgeable?: boolean;
  affectedMonths?: string[];
};

export type AppHealthResolveDetails = {
  fallbackReason?: string;
  details?: string[];
  primaryRunning?: AppHealthJobSummary | null;
  primaryAttention?: AppHealthJobSummary | null;
  attentionCount?: number;
  matchingRunningMonths?: string[];
  matchingDirtyMonths?: string[];
  matchingError?: string | null;
};

export type ApiAppHealthPayload = {
  status?: string;
  generated_at?: string;
  version?: number;
  app_status?: unknown;
  session?: {
    status?: string;
  };
  oa_sync?: ApiOaSyncStatus;
  workbench_read_model?: {
    status?: string;
    read_model_status?: string;
    consistency_status?: string;
    active_generation_id?: string | null;
    failed_generation_id?: string | null;
    last_error?: string | null;
    consistency_failures?: Array<Record<string, unknown>>;
    dirty_scopes?: string[];
    matching_dirty_scopes?: Array<Record<string, unknown>>;
    matching_running_scopes?: string[];
    last_matching_error?: string | null;
    stale_scopes?: string[];
    rebuilding_scopes?: string[];
  };
  background_jobs?: {
    active?: number;
    queued?: number;
    running?: number;
    attention?: number;
    primary_running?: ApiAppHealthJobSummary | null;
    primaryRunning?: ApiAppHealthJobSummary | null;
    primary_attention?: ApiAppHealthJobSummary | null;
    primaryAttention?: ApiAppHealthJobSummary | null;
  };
  dependencies?: Record<string, { status?: string; message?: string } | unknown>;
  metrics?: Record<string, number | string | boolean | null | undefined>;
  alerts?: unknown[];
};

export type ApiAppHealthJobSummary = {
  job_id?: string;
  jobId?: string;
  type?: string;
  label?: string;
  short_label?: string;
  shortLabel?: string;
  status?: string;
  message?: string;
  retryable?: boolean;
  acknowledgeable?: boolean;
  affected_months?: string[];
  affectedMonths?: string[];
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

export type OperationsDashboardAvailability = "available" | "unknown";

export type OperationsDashboardPercentiles = {
  p50: number | null;
  p95: number | null;
  p99: number | null;
};

export type OperationsDashboardInventorySource = {
  key: string;
  label: string;
  count: number | null;
  latest_synced_at: string | null;
  status: OperationsDashboardAvailability;
};

export type OperationsDashboardInventoryBlock = {
  total_count: number | null;
  latest_synced_at: string | null;
  status: OperationsDashboardAvailability;
  sources: OperationsDashboardInventorySource[];
};

export type OperationsDashboardEndpointPerformance = {
  endpoint: string;
  sample_count: number;
  last_status_code: number | null;
  duration_ms: OperationsDashboardPercentiles;
  database_duration_ms: OperationsDashboardPercentiles;
  connection_acquire_ms: OperationsDashboardPercentiles;
  sql_execute_fetch_ms: OperationsDashboardPercentiles;
  database_query_count: OperationsDashboardPercentiles;
};

export type OperationsDashboardOutboxMetric = {
  pending_count: number | null;
  publishing_count: number | null;
  failed_count: number | null;
  publish_failed_count: number | null;
  oldest_pending_age_seconds: number | null;
  status: OperationsDashboardAvailability;
  warning_code?: string;
};

export type OperationsDashboardQueueMetric = {
  event_type: string;
  queue: string;
  messages: number | null;
  unacked: number | null;
  consumers: number | null;
  dlq_messages: number | null;
  status: OperationsDashboardAvailability;
  warning_code?: string;
};

export type OperationsDashboardReadModelMetric = {
  key: string;
  refresh_duration_ms: OperationsDashboardPercentiles;
  historical_refresh_duration_ms?: OperationsDashboardPercentiles;
  refresh_duration_windows?: {
    recent_15m?: {
      sample_count: number;
      last_completed_at: string | null;
      duration_ms: OperationsDashboardPercentiles;
    };
    recent_1h?: {
      sample_count: number;
      last_completed_at: string | null;
      duration_ms: OperationsDashboardPercentiles;
    };
  };
  refresh_duration_by_kind?: Record<string, unknown>;
  stale_count: number | null;
  unavailable_count: number | null;
  status: OperationsDashboardAvailability;
  warning_code?: string;
};

export type OperationsDashboardWorkerMetric = {
  worker_kind: string;
  heartbeat_lag_seconds: number | null;
  status: OperationsDashboardAvailability;
  warning_code?: string;
};

export type OperationsDashboardPayload = {
  generated_at: string;
  data_inventory: {
    bank: OperationsDashboardInventoryBlock;
    invoice: OperationsDashboardInventoryBlock;
    oa: OperationsDashboardInventoryBlock;
  };
  request_performance: {
    window: {
      type: "process_rolling_window";
      sample_limit_per_endpoint: number;
      reset_on_restart: true;
    };
    endpoints: OperationsDashboardEndpointPerformance[];
  };
  runtime_performance: {
    outbox: OperationsDashboardOutboxMetric;
    queues: OperationsDashboardQueueMetric[];
    read_models: OperationsDashboardReadModelMetric[];
    workers: OperationsDashboardWorkerMetric[];
  };
  freshness: {
    warnings: string[];
  };
};
