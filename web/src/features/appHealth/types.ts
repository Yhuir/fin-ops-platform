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
  workbench_matching?: {
    status?: string;
    dirty_scopes?: string[];
    matching_dirty_scopes?: Array<Record<string, unknown>>;
    matching_running_scopes?: string[];
    last_matching_error?: string | null;
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
export type OperationsDashboardWorkerStatus =
  | OperationsDashboardAvailability
  | "ready"
  | "idle"
  | "working"
  | "running"
  | "processing"
  | "missing"
  | "stale"
  | "mismatch"
  | "unavailable";

export type OperationsDashboardPercentiles = {
  p50: number | null;
  p95: number | null;
  p99: number | null;
};

export type OperationsDashboardInventorySource = {
  key: string;
  label: string;
  count: number | null;
  supplementary_count?: number | null;
  latest_synced_at: string | null;
  status: OperationsDashboardAvailability;
};

export type OperationsDashboardInventoryBlock = {
  total_count: number | null;
  latest_synced_at: string | null;
  status: OperationsDashboardAvailability;
  sources: OperationsDashboardInventorySource[];
};

export type OperationsDashboardImportEvent = {
  key: string;
  batch_id: string;
  batch_type: string;
  source_key: string;
  label: string;
  source_name: string;
  imported_by: string;
  count: number | null;
  supplementary_count: number | null;
  imported_at: string | null;
  status: string;
  session_id?: string | null;
  file_id?: string | null;
  job_id?: string | null;
  job_stage?: string | null;
  error?: string | null;
  selected_bank_name?: string | null;
  selected_bank_last4?: string | null;
  detected_bank_name?: string | null;
  detected_last4?: string | null;
  withdrawal_allowed?: boolean;
  withdrawal?: {
    withdrawn_count?: number;
    withdrawn_by?: string;
    withdrawn_at?: string;
    reason?: string;
  } | null;
};

export type BankImportWithdrawalPayload = {
  status: "withdrawn";
  batch_id: string;
  withdrawn_count: number;
  idempotent_replay: boolean;
};

export type OperationsImportHistoryPayload = {
  rows: OperationsDashboardImportEvent[];
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
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
  status: OperationsDashboardWorkerStatus;
  warning_code?: string;
};

export type OperationsDashboardWorkerMetric = {
  worker_id?: string;
  worker_instance?: string;
  worker_kind: string;
  expected_worker_kind?: string;
  worker_status?: string;
  heartbeat_lag_seconds: number | null;
  heartbeat_stale_after_seconds?: number | null;
  required?: boolean;
  current_effective?: boolean;
  expected_transport?: string;
  expected_event_types?: string[];
  configured_event_types?: string[];
  status: OperationsDashboardWorkerStatus;
  warning_code?: string;
};

export type OperationsDashboardPayload = {
  generated_at: string;
  data_inventory: {
    bank: OperationsDashboardInventoryBlock;
    invoice: OperationsDashboardInventoryBlock;
    oa: OperationsDashboardInventoryBlock;
    import_events: OperationsDashboardImportEvent[];
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
    workers: OperationsDashboardWorkerMetric[];
  };
  freshness: {
    warnings: string[];
  };
};

export type InputInvoiceUsageAuditStatus = "pass" | "issues_found" | string;

export type PageAuditPageKey =
  | "reconciliation-workbench"
  | "cost-statistics"
  | "bank-details"
  | "oa-pending-payments"
  | "bank-flow-rule-batches"
  | "batch-accounting"
  | "turnover-ledger"
  | "etc-tickets"
  | "tax-offset"
  | "pending-invoices"
  | "input-invoice-usage"
  | "output-invoice-collections"
  | "settings"
  | "app-health-operations"
  | "imports.bank-transactions"
  | "imports.invoices"
  | "imports.etc-invoices";

export type PageAuditStatus = {
  integrity?: "pass" | "issues_found";
  freshness?: "fresh" | "not_fresh";
  queue?: "drained" | "backlog";
  external?: "pass" | "fail" | "unknown" | "not_applicable" | string;
};

export type PageAuditSummary = {
  source_fact_count?: number | null;
  active_relation_count?: number | null;
  linked_relation_group_count?: number | null;
  outbox_backlog_count?: number | null;
  active_workbench_pair_relation_count?: number | null;
  linked_workbench_relation_group_count?: number | null;
  blocking_issue_sample_count?: number | null;
  issue_sample_count?: number | null;
  error_sample_count?: number | null;
  warning_sample_count?: number | null;
  issue_sample_counts_by_code?: Record<string, number>;
  issue_sample_limit_per_code?: number | null;
  issue_samples_truncated?: boolean;
  detected_issue_code_count?: number | null;
};

export type InputInvoiceUsageAuditSummary = PageAuditSummary & {
  active_input_invoice_count?: number | null;
};

export type OutputInvoiceCollectionAuditSummary = PageAuditSummary & {
  active_output_invoice_count?: number | null;
};

export type PageAuditIssue = {
  severity?: string;
  code?: string;
  message?: string;
  subject_id?: string | null;
  scope_key?: string | null;
  details?: Record<string, unknown> | null;
};

export type PageAuditContract = {
  source_tables?: string[];
  relation_tables?: string[];
  scope_types?: string[];
  event_types?: string[];
  pass_condition?: string;
  guarantee_boundary?: string;
  canonical_expected_set?: string;
  key_display_fields?: string[];
  relation_edge_equality?: string;
  snapshot_consistency?: "repeatable_read_read_only" | "caller_managed" | string;
  database_snapshot?: boolean;
  external_source_boundary?: string;
  proof_checks?: string[];
  contract_revision?: string;
  proof_availability?: "ready" | "unavailable" | string;
  relation_proof_required?: boolean;
  write_policy?: "read_only" | string;
};

export type PageAuditPayload = {
  mode?: string;
  tenant_id?: string;
  page_key?: PageAuditPageKey;
  domain_key?: string;
  label?: string;
  generated_at?: string;
  overall_status?: InputInvoiceUsageAuditStatus;
  audit_status?: PageAuditStatus;
  summary?: PageAuditSummary;
  issues?: PageAuditIssue[];
  audit_contract?: PageAuditContract;
};

export type InputInvoiceUsageAuditPayload = PageAuditPayload & {
  summary?: InputInvoiceUsageAuditSummary;
};

export type OutputInvoiceCollectionAuditPayload = PageAuditPayload & {
  summary?: OutputInvoiceCollectionAuditSummary;
};

export type AppHealthSystemAuditPayload = PageAuditPayload & {
  summary?: PageAuditSummary & {
    registered_page_count?: number | null;
    audited_business_page_count?: number | null;
    passed_business_page_count?: number | null;
    database_internal_contracts?: "pass" | "issues_found" | string;
    end_to_end_source_truth?: "unproven" | "proven_as_of_external_evidence" | "not_applicable" | string;
  };
  database_system_snapshot?: {
    system_audit_id?: string;
    snapshot_identity?: string;
    snapshot_generated_at?: string;
    snapshot_consistency?: string;
    database_snapshot?: boolean;
    evidence_fingerprint?: string;
    page_results?: PageAuditPayload[];
  };
  runtime_observation?: {
    observed_at?: string;
    database_snapshot?: boolean;
    warnings?: string[];
  };
  external_evidence?: {
    status?: "pass" | "fail" | "unknown" | "not_applicable" | string;
    end_to_end_source_truth?: "unproven" | "proven_as_of_external_evidence" | "not_applicable" | string;
    as_of?: string;
    claim_boundary?: string;
    summary?: {
      required_domain_count?: number;
      passed_domain_count?: number;
      failed_domain_count?: number;
      unknown_domain_count?: number;
    };
    domains?: Array<{
      domain?: "bank" | "oa" | "invoice" | "etc" | string;
      status?: "pass" | "fail" | "unknown" | string;
      reason?: string;
      evidence_id?: string;
      source_snapshot_id?: string;
      observed_at?: string;
      valid_until?: string;
      manifest_fingerprint?: string;
      issue_count?: number;
      boundary?: string;
    }>;
    items?: Array<{
      domain?: "bank" | "oa" | "invoice" | "etc" | string;
      status?: "pass" | "fail" | "unknown" | string;
      reason?: string;
      evidence_id?: string;
      observed_at?: string;
      boundary?: string;
    }>;
    page_coverage?: Array<{
      page_key?: PageAuditPageKey;
      status?: "pass" | "fail" | "unknown" | "not_applicable" | string;
      dependency_keys?: Array<"bank" | "oa" | "invoice" | "etc" | string>;
      boundary?: string;
    }>;
  };
  page_projection?: OperationsDashboardPayload;
};
