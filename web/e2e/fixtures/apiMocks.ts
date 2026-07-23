import type { Page, Route } from "@playwright/test";

import { createMinimalXlsx } from "./xlsx";

export type AccessTier = "denied" | "read_export_only" | "full_access" | "admin";

type SessionMode = "admin" | "full_access" | "read_export_only" | "forbidden" | "expired" | "error";
type OaSyncMockMode = "idle" | "dirty" | "refreshing" | "error";
type WorkbenchHealthMockStatus = "ready" | "stale" | "rebuilding" | "error";
type WorkbenchRefreshMockStatus = "fresh" | "refreshing" | "stale" | "failed" | "unavailable";
type WorkbenchPageMockStatus = "fresh" | "refreshing" | "stale";
type OperationBarrierMockMode = "fresh" | "refreshing" | "blocked";
type InputInvoiceUsageReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type OaPendingPaymentReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type OutputInvoiceCollectionReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type OutputInvoiceReceiptLifecycleState = "none" | "issued" | "voided" | "reissued";
type PendingInvoiceReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type BankDetailReadModelMockStatus = "fresh" | "refreshing" | "stale" | "schema_mismatch" | "missing";
type CostStatisticsReadModelMockStatus = "fresh" | "refreshing" | "stale" | "failed" | "unavailable";
type TaxOffsetReadModelMockStatus = "fresh" | "refreshing" | "stale" | "failed" | "missing" | "unavailable";
type BankFlowRuleBatchReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type BatchAccountingReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type TurnoverLedgerReadModelMockStatus = "fresh" | "refreshing" | "stale" | "missing";
type BankDetailClassificationMockMode = "auto_matched" | "needs_confirmation" | "unmatched";
type BankDetailCategoryOverride = {
  categoryCode: string;
  primaryLabel: string;
  subLabel: string;
  thirdLabel?: string | null;
  labelPath: string[];
  source: "auto_confirmation" | "manual";
};
type BankAutoTagRulesPayloadOptions = {
  version?: number;
  readModelStatus?: "fresh" | "refreshing";
  salarySubLabel?: string;
};

type ApiMockOptions = {
  appHealthWriteSafetyBlocked?: boolean;
  bankImportConfirmError?: boolean;
  bankImportConfirmPreviewStale?: boolean;
  bankImportDownstreamFanout?: boolean;
  bankImportIncludeCorruptFile?: boolean;
  bankImportNoAccountConflict?: boolean;
  bankImportPreviewDelayMs?: number;
  etcImportConfirmError?: boolean;
  etcImportDownstreamFanout?: boolean;
  etcImportConfirmPreviewStale?: boolean;
  etcImportConfirmStaleReconciliationTask?: boolean;
  etcTicketBusinessBatchesFailOnce?: boolean;
  etcTicketBusinessBatchesFailuresBeforeSuccess?: number;
  etcTicketBusinessBatchDeleteFailOnce?: boolean;
  etcTicketBusinessBatchDeleteFailuresBeforeSuccess?: number;
  etcTicketInitialBusinessBatchStatus?: EtcBusinessBatchStatus;
  etcTicketSourceFileDeleteFailOnce?: boolean;
  etcTicketSourceFileDeleteFailuresBeforeSuccess?: number;
  etcTicketSourceFileUploadFailOnce?: boolean;
  etcTicketSourceFileUploadFailuresBeforeSuccess?: number;
  etcTicketWorkflowTaskMatchesBusinessBatch?: boolean;
  etcTicketOaDraftFailOnce?: boolean;
  etcTicketOaDraftFailuresBeforeSuccess?: number;
  etcTicketManualStatusFailOnce?: boolean;
  etcTicketManualStatusFailuresBeforeSuccess?: number;
  etcTicketReconciliationWorkflow?: boolean;
  invoiceImportConfirmError?: boolean;
  invoiceImportConfirmPreviewStale?: boolean;
  invoiceImportDownstreamFanout?: boolean;
  invoiceImportIncludeCorruptFile?: boolean;
  invoiceImportPreviewDelayMs?: number;
  bankFlowRuleCostFanout?: boolean;
  bankFlowRuleBatchFailOnce?: boolean;
  bankFlowRuleBatchFailuresBeforeSuccess?: number;
  bankFlowRuleBatchReadModelStatus?: BankFlowRuleBatchReadModelMockStatus;
  bankFlowRuleBatchReadModelStatuses?: BankFlowRuleBatchReadModelMockStatus[];
  bankFlowRuleBatchScenario?: BankFlowRuleBatchMockScenario;
  settingsProjectScopeFanout?: boolean;
  turnoverCostFanout?: boolean;
  turnoverLedgerFailOnce?: boolean;
  turnoverLedgerFailuresBeforeSuccess?: number;
  turnoverLedgerReadModelStatus?: TurnoverLedgerReadModelMockStatus;
  turnoverLedgerReadModelStatuses?: TurnoverLedgerReadModelMockStatus[];
  bankDetailsAccountReadModelStatus?: BankDetailReadModelMockStatus;
  bankDetailsAccountReadModelStatuses?: BankDetailReadModelMockStatus[];
  bankDetailsClassificationMode?: BankDetailClassificationMockMode;
  bankDetailsExportReadModelStatus?: BankDetailReadModelMockStatus;
  bankDetailsLargeDataset?: boolean;
  bankDetailsTransactionReadModelStatus?: BankDetailReadModelMockStatus;
  bankDetailsTransactionReadModelStatuses?: BankDetailReadModelMockStatus[];
  bankDetailsTransactionsEmpty?: boolean;
  bankDetailsTransactionsTotal?: number;
  batchAccountingInitialSubmitted?: boolean;
  batchAccountingFailOnce?: boolean;
  batchAccountingFailuresBeforeSuccess?: number;
  batchAccountingReadModelStatus?: BatchAccountingReadModelMockStatus;
  batchAccountingReadModelStatuses?: BatchAccountingReadModelMockStatus[];
  costStatisticsExportDownloadSuccess?: boolean;
  costStatisticsExportReadModelStatus?: CostStatisticsReadModelMockStatus;
  costStatisticsAppStatusReadModelStatus?: CostStatisticsReadModelMockStatus;
  costStatisticsAppStatusScopeKey?: string;
  costStatisticsExplorerFailOnce?: boolean;
  costStatisticsExplorerFailuresBeforeSuccess?: number;
  costStatisticsLargeDataset?: boolean;
  costStatisticsReadModelStatus?: CostStatisticsReadModelMockStatus;
  costStatisticsRelationFanout?: boolean;
  costStatisticsTransactionDetailReadModelStatus?: CostStatisticsReadModelMockStatus;
  inputInvoiceUsageExportReadModelStatus?: InputInvoiceUsageReadModelMockStatus;
  inputInvoiceUsageExportRowLimitError?: boolean;
  inputInvoiceUsageFilterSortRows?: boolean;
  inputInvoiceUsagePaymentRulesSaveFlow?: boolean;
  inputInvoiceUsageReadModelStatus?: InputInvoiceUsageReadModelMockStatus;
  inputInvoiceUsageRowsFailOnce?: boolean;
  inputInvoiceUsageRowsFailuresBeforeSuccess?: number;
  inputInvoiceUsageRelationDetailReadModelStatus?: InputInvoiceUsageReadModelMockStatus;
  inputInvoiceUsageRelationFanout?: boolean;
  oaPendingPaymentBankLinkDelayMs?: number;
  oaPendingPaymentBankLinkError?: boolean;
  oaPendingPaymentBankLinkFlow?: boolean;
  oaPendingPaymentWritebackPaidDelayMs?: number;
  oaPendingPaymentWritebackPaidError?: boolean;
  oaPendingPaymentWritebackPaidFlow?: boolean;
  oaPendingPaymentDetailReadModelRefreshing?: boolean;
  oaPendingPaymentReadModelStatus?: OaPendingPaymentReadModelMockStatus;
  oaPendingPaymentRowsFailOnce?: boolean;
  oaPendingPaymentRowsFailuresBeforeSuccess?: number;
  oaPendingPaymentRelationFanout?: boolean;
  outputInvoiceCollectionExportRowLimitError?: boolean;
  outputInvoiceCollectionInitialReceiptCreated?: boolean;
  outputInvoiceCollectionListInteractions?: boolean;
  outputInvoiceCollectionRowsFailOnce?: boolean;
  outputInvoiceCollectionRowsFailuresBeforeSuccess?: number;
  outputInvoiceCollectionReceiptCreateFailOnce?: boolean;
  outputInvoiceCollectionReceiptCreateFailuresBeforeSuccess?: number;
  outputInvoiceCollectionReceiptReissueFailOnce?: boolean;
  outputInvoiceCollectionReceiptReissueFailuresBeforeSuccess?: number;
  outputInvoiceCollectionReceiptVoidFailOnce?: boolean;
  outputInvoiceCollectionReceiptVoidFailuresBeforeSuccess?: number;
  outputInvoiceCollectionReminderFailOnce?: boolean;
  outputInvoiceCollectionReminderFailuresBeforeSuccess?: number;
  outputInvoiceCollectionStatusFailOnce?: boolean;
  outputInvoiceCollectionStatusFailuresBeforeSuccess?: number;
  outputInvoiceDownstreamFanout?: boolean;
  outputInvoiceCollectionReadModelStatus?: OutputInvoiceCollectionReadModelMockStatus;
  outputInvoiceRedRelationCandidate?: boolean;
  pendingInvoiceAttachExistingBatchRows?: boolean;
  pendingInvoiceAttachExistingConfirmFailOnce?: boolean;
  pendingInvoiceAttachExistingConfirmFailuresBeforeSuccess?: number;
  pendingInvoiceAttachExistingPreviewConflict?: boolean;
  pendingInvoiceIncomeBatchRows?: boolean;
  pendingInvoiceIncomeStatusFailOnce?: boolean;
  pendingInvoiceIncomeStatusFailuresBeforeSuccess?: number;
  pendingInvoiceIncomeStatusError?: boolean;
  pendingInvoiceExportRowLimitError?: boolean;
  pendingInvoiceFilterSortRows?: boolean;
  pendingInvoiceRowsFailOnce?: boolean;
  pendingInvoiceRowsFailuresBeforeSuccess?: number;
  pendingInvoiceRulesSaveFailOnce?: boolean;
  pendingInvoiceRulesSaveFlow?: boolean;
  pendingInvoiceRulesSaveFailuresBeforeSuccess?: number;
  pendingInvoiceReadModelStatus?: PendingInvoiceReadModelMockStatus;
  pendingInvoiceRowsEmpty?: boolean;
  sessionMode?: SessionMode;
  taxOffsetLargeDataset?: boolean;
  taxOffsetReadModelStatus?: TaxOffsetReadModelMockStatus;
  taxOffsetReadModelStatuses?: TaxOffsetReadModelMockStatus[];
  taxOffsetPlanSaveConflict?: boolean;
  dashboardError?: boolean;
  oaSyncMode?: OaSyncMockMode;
  operationBarrierMode?: OperationBarrierMockMode;
  workbenchConfirmSubmitConflict?: boolean;
  workbenchConfirmSubmitDelayMs?: number;
  workbenchConfirmSubmitError?: boolean;
  workbenchConfirmSubmitFailuresBeforeSuccess?: number;
  workbenchFreshRefetchError?: boolean;
  workbenchGroupsFailuresBeforeSuccess?: number;
  workbenchHealthStatus?: WorkbenchHealthMockStatus;
  workbenchCashSpecialActions?: boolean;
  workbenchInitialExceptionApplied?: boolean;
  workbenchInitialRelationConfirmed?: boolean;
  workbenchInitialRowIgnored?: boolean;
  workbenchBankFlowRuleBatchScenario?: boolean;
  workbenchLargeDataset?: boolean;
  workbenchPageEmpty?: boolean;
  workbenchPageStatus?: WorkbenchPageMockStatus;
  workbenchRefreshStatus?: WorkbenchRefreshMockStatus;
  workbenchWithdrawSubmitDelayMs?: number;
};

type WorkbenchZone = "paired" | "unpaired";
type BatchAccountingBucket = "unsubmitted" | "submitted";
type ImportScenario = "bank" | "invoice";
type SettingsDataResetAction = "reset_bank_transactions" | "reset_invoices" | "reset_oa_and_rebuild";
type EtcBusinessBatchStatus = "imported" | "oa_confirmation_pending" | "manually_marked_submitted" | "not_submitted";
type BankFlowRuleBrowserBatchStatus = "draft" | "submitted" | "withdrawn";
type BankFlowRuleBatchMockScenario = "single" | "ordinaryDraftMatrix" | "internalTransferPairs";
type CostBrowserProjectRow = {
  transaction_id: string;
  trade_time: string;
  direction: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  counterparty_name: string;
  payment_account_label: string;
};

const importSessionIds: Record<ImportScenario, string> = {
  bank: "import_session_e2e_bank",
  invoice: "import_session_e2e_invoice",
};

const importFiles: Record<ImportScenario, string[]> = {
  bank: ["historydetail14080.xlsx", "2026-01-01至2026-01-31交易明细.xlsx"],
  invoice: ["一月发票.xlsx", "二月发票.xlsx"],
};

const turnoverBankRows = {
  expense: "turnover-bank-expense-1000",
  income: "turnover-bank-income-1000",
} as const;

const turnoverBankRowVersions = {
  [turnoverBankRows.expense]: 1,
  [turnoverBankRows.income]: 2,
} as const;

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function sessionPayload(accessTier: AccessTier) {
  const allowed = accessTier !== "denied";
  return {
    user: {
      user_id: "e2e-user",
      username: accessTier === "admin" ? "YNSYLP005" : "E2EUSER001",
      nickname: accessTier === "admin" ? "管理员" : "浏览器测试用户",
      display_name: accessTier === "admin" ? "管理员" : "浏览器测试用户",
      dept_id: "finance",
      dept_name: "财务部",
      avatar: null,
    },
    roles: accessTier === "admin" ? ["fin_ops_admin"] : ["fin_ops_user"],
    permissions: ["finops:app:view"],
    allowed,
    access_tier: accessTier,
    can_access_app: allowed,
    can_mutate_data: accessTier === "admin" || accessTier === "full_access",
    can_admin_access: accessTier === "admin",
  };
}

function appStatusWriteSafety(blocksMutations = false, reason = blocksMutations ? "写操作暂不可用" : "写操作可用") {
  return {
    status: blocksMutations ? "blocked" : "ready",
    reason,
    blocks_mutations: blocksMutations,
    blockers: blocksMutations ? ["runtime"] : [],
  };
}

function appStatusWorkbenchDomain(status: WorkbenchHealthMockStatus = "ready") {
  const readModelStatus = status === "ready" ? "ready" : status === "rebuilding" ? "refreshing" : status === "error" ? "failed" : "stale";
  const level = status === "error" ? "blocked" : status === "ready" ? "ok" : "busy";
  const reason = status === "ready"
    ? "关联台已同步"
    : status === "rebuilding"
      ? "关联台刷新中"
      : status === "error"
        ? "关联台刷新失败"
        : "关联台待刷新";
  return {
    key: "workbench",
    label: "关联台",
    route: "/",
    level,
    status: readModelStatus,
    reason,
    details: [],
    read_models: ["workbench"],
    read_model_scopes: [],
    workers: ["workbench-read-model"],
    job_ids: [],
    updated_at: "2026-06-17T01:00:00Z",
  };
}

function appStatusCostStatisticsDomain(
  status: CostStatisticsReadModelMockStatus,
  scopeKey = "active:2026-03",
) {
  const level = status === "fresh"
    ? "ok"
    : status === "failed" || status === "unavailable"
      ? "blocked"
      : "busy";
  return {
    key: "cost-statistics",
    label: "成本统计",
    route: "/cost-statistics",
    level,
    status,
    reason: status === "fresh" ? "成本统计已同步" : "成本统计需要刷新",
    details: [],
    read_models: ["cost_statistics"],
    read_model_scopes: [
      {
        read_model_key: "cost_statistics",
        scope_type: "project_month",
        scope_key: scopeKey,
        status,
        last_error: status === "failed" ? "browser cost statistics refresh failed" : "",
        updated_at: "2026-06-17T01:00:00Z",
      },
    ],
    workers: ["cost-statistics-read-model"],
    job_ids: [],
    updated_at: "2026-06-17T01:00:00Z",
  };
}

function appStatusOverall(options: ApiMockOptions = {}) {
  const writeSafety = appStatusWriteSafety(options.appHealthWriteSafetyBlocked === true);
  if (options.appHealthWriteSafetyBlocked) {
    return {
      level: "blocked",
      color: "red",
      reason: writeSafety.reason,
      blocks_mutations: true,
      write_safety: writeSafety,
    };
  }
  if (options.workbenchHealthStatus === "error") {
    return {
      level: "blocked",
      color: "red",
      reason: "关联台刷新失败",
      blocks_mutations: false,
      write_safety: writeSafety,
    };
  }
  if (options.oaSyncMode === "refreshing") {
    return {
      level: "busy",
      color: "yellow",
      reason: "OA 正在同步",
      blocks_mutations: false,
      write_safety: writeSafety,
    };
  }
  if (options.oaSyncMode === "dirty" || options.workbenchHealthStatus === "stale") {
    return {
      level: "busy",
      color: "yellow",
      reason: "关联台待刷新",
      blocks_mutations: false,
      write_safety: writeSafety,
    };
  }
  if (options.workbenchHealthStatus === "rebuilding") {
    return {
      level: "busy",
      color: "yellow",
      reason: "关联台刷新中",
      blocks_mutations: false,
      write_safety: writeSafety,
    };
  }
  return {
    level: "ok",
    color: "green",
    reason: "浏览器 e2e mock runtime ready",
    blocks_mutations: false,
    write_safety: writeSafety,
  };
}

function appStatusOverview(options: ApiMockOptions = {}) {
  const costStatisticsDomain = options.costStatisticsAppStatusReadModelStatus
    ? [appStatusCostStatisticsDomain(
        options.costStatisticsAppStatusReadModelStatus,
        options.costStatisticsAppStatusScopeKey,
      )]
    : [];
  return {
    version: 1,
    generated_at: "2026-06-17T01:00:00Z",
    overall: appStatusOverall(options),
    domains: [appStatusWorkbenchDomain(options.workbenchHealthStatus), ...costStatisticsDomain],
    background_tasks: [],
    alerts: [],
  };
}

function oaSyncPayload(mode: OaSyncMockMode = "idle") {
  return {
    status: mode === "dirty" ? "idle" : mode,
    message: mode === "refreshing"
      ? "OA 正在同步"
      : mode === "dirty"
        ? "OA 有待处理变更"
        : mode === "error"
          ? "OA 同步失败"
          : "OA 已同步",
    dirty_scopes: mode === "dirty" ? ["2026-03"] : [],
    changed_scopes: [],
    version: 1,
    last_synced_at: "2026-06-17T01:00:00Z",
  };
}

function workbenchReadModelHealthPayload(status: WorkbenchHealthMockStatus = "ready") {
  return {
    status,
    read_model_status: status === "ready" ? "fresh" : status === "rebuilding" ? "refreshing" : status === "error" ? "failed" : "stale",
    dirty_scopes: status === "ready" ? [] : ["2026-03"],
    matching_dirty_scopes: status === "ready" ? [] : ["2026-03"],
    matching_running_scopes: status === "rebuilding" ? ["2026-03"] : [],
    stale_scopes: status === "ready" ? [] : ["2026-03"],
    rebuilding_scopes: status === "rebuilding" ? ["2026-03"] : [],
    last_matching_error: status === "error" ? "browser workbench refresh failed" : null,
  };
}

function workbenchRefreshStatusPayload(status: WorkbenchRefreshMockStatus = "fresh") {
  const scopeStatus = status === "fresh"
    ? "completed"
    : status === "failed" || status === "unavailable"
      ? "failed"
      : "processing";
  return {
    scope_key: "all",
    read_model_status: status,
    read_model_version: "workbench-refresh-e2e-001",
    active_generation_id: "workbench-generation-e2e-001",
    dirty_scopes: status === "fresh"
      ? []
      : [
        {
          scope_key: "2026-03",
          status: scopeStatus,
          last_error: status === "failed" ? "browser refresh failed" : null,
        },
      ],
    last_error: status === "failed" ? "browser refresh failed" : null,
    retryable: status === "failed",
  };
}

function appHealthPayload(options: ApiMockOptions = {}) {
  return {
    status: "ok",
    generated_at: "2026-06-17T01:00:00Z",
    version: 1,
    app_status: appStatusOverview(options),
    session: { status: "authenticated" },
    oa_sync: oaSyncPayload(options.oaSyncMode),
    workbench_read_model: workbenchReadModelHealthPayload(options.workbenchHealthStatus),
    background_jobs: {
      active: 0,
      queued: 0,
      running: 0,
      attention: 0,
      primary_running: null,
      primary_attention: null,
    },
    dependencies: {},
    metrics: {},
    alerts: [],
  };
}

function inventoryBlock(label: string) {
  const sources = label === "OA"
    ? [
      {
        key: "oa_records",
        label: "单据",
        count: 1,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
      {
        key: "oa_records_completed",
        label: "已完成 OA",
        count: 1,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
      {
        key: "oa_records_in_progress",
        label: "进行中 OA",
        count: 0,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
      {
        key: "oa_items",
        label: "明细",
        count: 1,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
    ]
    : [
      {
        key: `${label}-mock`,
        label,
        count: 1,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
    ];
  return {
    total_count: 1,
    latest_synced_at: "2026-06-17T01:00:00Z",
    status: "available",
    sources,
  };
}

function percentile(value: number | null) {
  return {
    p50: value,
    p95: value,
    p99: value,
  };
}

function operationsDashboardPayload() {
  return {
    generated_at: "2026-06-17T01:00:00Z",
    data_inventory: {
      bank: inventoryBlock("银行流水"),
      invoice: inventoryBlock("发票"),
      oa: inventoryBlock("OA"),
    },
    request_performance: {
      window: {
        type: "process_rolling_window",
        sample_limit_per_endpoint: 100,
        reset_on_restart: true,
      },
      endpoints: [
        {
          endpoint: "/api/session/me",
          sample_count: 3,
          last_status_code: 200,
          duration_ms: percentile(45),
          database_duration_ms: percentile(8),
          connection_acquire_ms: percentile(2),
          sql_execute_fetch_ms: percentile(5),
          database_query_count: percentile(1),
        },
      ],
    },
    runtime_performance: {
      outbox: {
        pending_count: 0,
        publishing_count: 0,
        failed_count: 0,
        publish_failed_count: 0,
        oldest_pending_age_seconds: null,
        status: "available",
      },
      queues: [],
      read_models: [
        {
          key: "workbench",
          refresh_duration_ms: percentile(120),
          refresh_duration_windows: {
            recent_15m: {
              sample_count: 1,
              last_completed_at: "2026-06-17T01:00:00Z",
              duration_ms: percentile(120),
            },
          },
          stale_count: 0,
          unavailable_count: 0,
          status: "available",
        },
      ],
      workers: [
        {
          worker_kind: "workbench-read-model",
          heartbeat_lag_seconds: 1,
          status: "available",
        },
      ],
    },
    freshness: {
      warnings: [],
    },
  };
}

function appHealthSystemAuditPayload() {
  return {
    mode: "app-health-system-audit",
    tenant_id: "default",
    page_key: "app-health-operations",
    overall_status: "pass",
    audit_status: {
      integrity: "pass",
      freshness: "fresh",
      queue: "drained",
      external: "unknown",
    },
    summary: {
      registered_page_count: 17,
      audited_business_page_count: 16,
      passed_business_page_count: 16,
      database_internal_contracts: "pass",
      end_to_end_source_truth: "unproven",
      issue_sample_count: 0,
      error_sample_count: 0,
      warning_sample_count: 0,
      blocking_issue_sample_count: 0,
      issue_sample_counts_by_code: {},
      issue_sample_limit_per_code: 50,
      issue_samples_truncated: false,
      detected_issue_code_count: 0,
    },
    issues: [],
    audit_contract: {
      pass_condition: "integrity=pass and freshness=fresh and queue=drained and database_snapshot=true",
      snapshot_consistency: "repeatable_read_read_only",
      database_snapshot: true,
      proof_availability: "ready",
      contract_revision: "page-audit-contract.v22",
      write_policy: "read_only",
    },
    database_system_snapshot: {
      system_audit_id: "system-audit:e2e-fixture",
      snapshot_identity: "100:100:",
      snapshot_generated_at: "2026-07-10T08:00:00Z",
      snapshot_consistency: "repeatable_read_read_only",
      database_snapshot: true,
      evidence_fingerprint: "e2e-fixture",
      page_results: [],
    },
    runtime_observation: {
      observed_at: "2026-07-10T08:00:00Z",
      database_snapshot: false,
      warnings: [],
    },
    external_evidence: {
      status: "unknown",
      end_to_end_source_truth: "unproven",
      summary: { required_domain_count: 4, passed_domain_count: 0, failed_domain_count: 0, unknown_domain_count: 4 },
      claim_boundary: "external manifests are not registered",
      domains: ["bank", "oa", "invoice", "etc"].map((domain) => ({
        domain,
        status: "unknown",
        boundary: "external control evidence not registered",
      })),
    },
    page_projection: operationsDashboardPayload(),
    generated_at: "2026-07-10T08:00:00Z",
  };
}

function oaApplicantCredentialsPayload() {
  return {
    credentials: [
      {
        target_applicant_code: "chen_xiuyun",
        target_applicant_name: "陈秀云",
        oa_username: "chen_xiuyun",
        credential_status: "configured",
        has_credential: true,
        enabled: true,
      },
    ],
  };
}

function settingsDataResetJobPayload(params: {
  action: SettingsDataResetAction;
  jobId: string;
  status: "running" | "completed";
}) {
  const running = params.status === "running";
  return {
    job: {
      job_id: params.jobId,
      action: params.action,
      status: params.status,
      phase: running ? "clear" : "complete",
      message: running ? "正在清理 app 内部状态。" : "已完成数据重置。",
      current: running ? 25 : 100,
      total: 100,
      percent: running ? 25 : 100,
      result: running
        ? null
        : {
          action: params.action,
          status: "completed",
          job_id: params.jobId,
          cleared_collections: ["workbench_read_models"],
          deleted_counts: {
            workbench_read_models: 1,
          },
          protected_targets: ["form_data_db.form_data"],
          rebuild_status: params.action === "reset_oa_and_rebuild" ? "completed" : "not_applicable",
          message: "已完成数据重置。",
        },
      error: null,
    },
  };
}

function normalizeApiPath(pathname: string) {
  return pathname.replace(/^\/fin-ops-api/, "");
}

function workbenchRows() {
  return {
    oa: {
      id: "oa-o-202603-001",
      type: "oa",
      case_id: "CASE-202603-101",
      applicant: "陈涛",
      project_name: "智能工厂项目",
      apply_type: "供应商付款申请",
      amount: "58,000.00",
      counterparty_name: "智能工厂设备商",
      reason: "设备尾款待支付",
      oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
      detail_fields: {
        审批完成时间: "2026-03-28 18:10",
      },
      available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
    },
    bank: {
      id: "bk-o-202603-001",
      type: "bank",
      case_id: "CASE-202603-101",
      trade_time: "2026-03-28 10:18",
      debit_amount: "58,000.00",
      credit_amount: null,
      counterparty_name: "智能工厂设备商",
      payment_account_label: "建设银行 1138",
      invoice_relation: { code: "pending_invoice_match", label: "待关联设备票", tone: "warn" },
      pay_receive_time: "2026-03-28 10:18",
      remark: "设备尾款待进项票",
      repayment_date: null,
      available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
    },
    invoice: {
      id: "iv-o-202603-001",
      type: "invoice",
      source_kind: "oa_attachment_invoice",
      case_id: "CASE-202603-101",
      seller_tax_no: "91330108MA27B4011D",
      seller_name: "智能工厂设备商",
      buyer_tax_no: "91310000MA1F99088Q",
      buyer_name: "杭州溯源科技有限公司",
      issue_date: "2026-03-28",
      amount: "58,000.00",
      tax_rate: "13%",
      tax_amount: "7,540.00",
      total_with_tax: "65,540.00",
      invoice_type: "进项专票",
      invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
      available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
      detail_fields: {
        发票号码: "12561048",
        derived_from_oa_id: "oa-o-202603-001",
        source_expense_item_id: "oa-o-202603-001:item:1",
        source_attachment_name: "设备尾款附件发票.pdf",
      },
    },
  };
}

function linkedWorkbenchRows(includeCashSpecialActions = false) {
  const rows = workbenchRows();
  const linkedBankActions = [
    "detail",
    "view_relation",
    "cancel_link",
    "handle_exception",
    ...(includeCashSpecialActions
      ? ["confirm_cash_pass_through", "confirm_cash_ticket_purchase", "cancel_cash_special"]
      : []),
  ];
  return {
    oa: {
      ...rows.oa,
      oa_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
      available_actions: ["detail", "cancel_link"],
    },
    bank: {
      ...rows.bank,
      invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
      remark: "设备尾款已闭环",
      available_actions: linkedBankActions,
    },
    invoice: {
      ...rows.invoice,
      invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
      available_actions: ["detail", "cancel_link"],
    },
  };
}

function buildPairedWorkbenchGroup(includeCashSpecialActions = false) {
  const rows = linkedWorkbenchRows(includeCashSpecialActions);
  return {
    group_id: "case:CASE-202603-101",
    group_type: "relation",
    match_confidence: "high",
    reason: "browser_e2e_relation_fanout",
    oa_rows: [rows.oa],
    bank_rows: [rows.bank],
    invoice_rows: [rows.invoice],
    can_withdraw: true,
    amount_check: {
      status: "matched",
      direction: "payment",
      bank_amount: "58000.00",
      oa_amount: "58000.00",
      amount_delta: "0.00",
      requires_note: false,
    },
  };
}

function buildUnpairedWorkbenchGroup(
  rowType: "oa" | "bank" | "invoice",
  row: ReturnType<typeof workbenchRows>["oa" | "bank" | "invoice"],
) {
  return {
    group_id: `row:${row.id}`,
    group_type: "unpaired",
    reason: "browser_e2e_canonical_unpaired_fact",
    oa_rows: rowType === "oa" ? [row] : [],
    bank_rows: rowType === "bank" ? [row] : [],
    invoice_rows: rowType === "invoice" ? [row] : [],
    can_withdraw: false,
  };
}

function buildUnpairedWorkbenchGroups(rows = workbenchRows()) {
  return [
    buildUnpairedWorkbenchGroup("oa", rows.oa),
    buildUnpairedWorkbenchGroup("bank", rows.bank),
    buildUnpairedWorkbenchGroup("invoice", rows.invoice),
  ];
}

function bankFlowRuleSourceRow(
  index: number,
  overrides: Record<string, unknown> = {},
) {
  const suffix = String(index).padStart(3, "0");
  return {
    id: `bk-flow-rule-e2e-${suffix}`,
    type: "bank",
    case_id: "bank_flow_rule_batch_e2e_fee",
    relation_mode: "bank_flow_rule_batch",
    trade_time: `2026-05-0${index} 10:20:00`,
    debit_amount: "8.80",
    credit_amount: "",
    counterparty_name: "建设银行",
    payment_account_label: "建设银行 8106",
    remark: `流水规则手续费明细 ${index}`,
    invoice_relation: { code: "bank_flow_rule_batch", label: "流水规则批次", tone: "success" },
    display_tags: ["流水规则", "手续费"],
    available_actions: ["detail", "view_relation"],
    special_metadata: {
      source: "bank_flow_rule_batch",
      source_batch_id: "bank_flow_rule_batch_e2e_fee",
      relation_mode: "bank_flow_rule_batch",
      flow_rule_tag_code: "fee",
      flow_rule_version: 3,
      requires_oa: false,
      requires_invoice: false,
      source_row_count: 4,
      collapsed_bank_rows: true,
    },
    ...overrides,
  };
}

function bankFlowRuleInvoiceRow() {
  return {
    id: "iv-flow-rule-e2e-needs-invoice",
    type: "invoice",
    source_kind: "manual_input_invoice",
    case_id: "bank_flow_rule_batch_e2e_invoice_required",
    seller_tax_no: "91330108MA27B4011D",
    seller_name: "建设银行",
    buyer_tax_no: "91310000MA1F99088Q",
    buyer_name: "杭州溯源科技有限公司",
    issue_date: "2026-05-09",
    amount: "19.90",
    tax_rate: "6%",
    tax_amount: "1.13",
    total_with_tax: "19.90",
    invoice_type: "进项普票",
    invoice_bank_relation: { code: "pending_bank_flow_rule_batch", label: "待确认流水规则批次", tone: "warn" },
    available_actions: ["detail", "confirm_link"],
    detail_fields: {
      发票号码: "BFR-INV-E2E-001",
      来源: "浏览器 e2e 补票候选",
    },
  };
}

function bankFlowRuleInvoiceRequiredGroup(zone: WorkbenchZone, linked: boolean) {
  const bankRow = bankFlowRuleSourceRow(9, {
    id: "bk-flow-rule-e2e-needs-invoice",
    case_id: "bank_flow_rule_batch_e2e_invoice_required",
    remark: linked ? "补齐发票后进入已配对" : "需要发票后才进入已配对",
    debit_amount: "19.90",
    invoice_relation: {
      code: linked ? "fully_linked" : "bank_flow_rule_batch_requires_invoice",
      label: linked ? "完全关联" : "需补发票",
      tone: linked ? "success" : "warn",
    },
    available_actions: linked ? ["detail", "view_relation"] : ["detail", "confirm_link"],
    special_metadata: {
      source: "bank_flow_rule_batch",
      source_batch_id: "bank_flow_rule_batch_e2e_invoice_required",
      relation_mode: "bank_flow_rule_batch",
      flow_rule_tag_code: "fee",
      flow_rule_version: 3,
      requires_oa: false,
      requires_invoice: true,
      source_row_count: 1,
      collapsed_bank_rows: false,
    },
  });
  const invoiceRow = {
    ...bankFlowRuleInvoiceRow(),
    invoice_bank_relation: {
      code: linked ? "fully_linked" : "pending_bank_flow_rule_batch",
      label: linked ? "完全关联" : "待确认流水规则批次",
      tone: linked ? "success" : "warn",
    },
    available_actions: linked ? ["detail", "view_relation"] : ["detail", "confirm_link"],
  };
  return {
    group_id: "bank-flow-rule-batch:bank_flow_rule_batch_e2e_invoice_required",
    group_type: zone === "paired" ? "relation" : "unpaired",
    match_confidence: zone === "paired" ? "high" : "medium",
    reason: linked ? "流水规则已补齐发票" : "流水规则待补发票",
    relation_mode: "bank_flow_rule_batch",
    oa_rows: [],
    bank_rows: [bankRow],
    invoice_rows: [invoiceRow],
    can_withdraw: false,
  };
}

function bankFlowRuleWorkbenchGroups(
  zone: WorkbenchZone,
  invoiceRequiredConfirmed = false,
  includeFullCollapsedRows = false,
) {
  const invoiceRequiredGroup = bankFlowRuleInvoiceRequiredGroup(zone, invoiceRequiredConfirmed);
  if (zone === "paired") {
    const collapsedRows = [1, 2, 3, 4].map((index) => bankFlowRuleSourceRow(index));
    const summaryRow = {
      ...bankFlowRuleSourceRow(0, {
        id: "bank-flow-rule-summary-e2e-fee",
        source_kind: "bank_flow_rule_batch_summary",
        trade_time: "2026-05",
        debit_amount: "35.20",
        counterparty_name: "流水规则手续费批次",
        remark: "4 条手续费流水",
      }),
      special_metadata: {
        source: "bank_flow_rule_batch",
        source_batch_id: "bank_flow_rule_batch_e2e_fee",
        relation_mode: "bank_flow_rule_batch",
        flow_rule_tag_code: "fee",
        flow_rule_version: 3,
        requires_oa: false,
        requires_invoice: false,
        source_row_count: 4,
        collapsed_bank_rows: true,
      },
    };
    return [{
      group_id: "bank-flow-rule-batch:bank_flow_rule_batch_e2e_fee",
      group_type: "relation",
      match_confidence: "high",
      reason: "流水规则手续费批次",
      relation_mode: "bank_flow_rule_batch",
      display_mode: "collapsed_summary",
      default_collapsed: true,
      summary_row: summaryRow,
      collapsed_rows: {
        bank: includeFullCollapsedRows ? collapsedRows : collapsedRows.slice(0, 3),
        oa: [],
        invoice: [],
      },
      collapsed_row_counts: { oa: 0, bank: 4, invoice: 0 },
      row_counts: { oa: 0, bank: 4, invoice: 0 },
      display_row_counts: { oa: 0, bank: 1, invoice: 0 },
      oa_rows: [],
      bank_rows: [summaryRow],
      invoice_rows: [],
      can_withdraw: false,
    }, ...(invoiceRequiredConfirmed ? [invoiceRequiredGroup] : [])];
  }
  return invoiceRequiredConfirmed ? [] : [invoiceRequiredGroup];
}

function bankFlowRuleConfirmPreviewPayload() {
  return {
    operation: "confirm_link",
    operation_type: "confirm_link",
    preview_id: "bank-flow-rule-confirm-preview",
    submit_expected_versions: { bank_flow_rule_batch_e2e_invoice_required: 1 },
    can_submit: true,
    requires_note: false,
    message: "确认后将把 1 条流水和 1 条发票按流水规则闭环。",
    before: { groups: [bankFlowRuleInvoiceRequiredGroup("unpaired", false)] },
    after: { groups: [bankFlowRuleInvoiceRequiredGroup("paired", true)] },
    amount_summary: {
      before: { oa_total: "0.00", bank_total: "19.90", invoice_total: "19.90" },
      after: { oa_total: "0.00", bank_total: "19.90", invoice_total: "19.90" },
      status: "matched",
      direction: "payment",
      mismatch_fields: [],
    },
  };
}

function bankFlowRuleConfirmResultPayload() {
  return {
    success: true,
    action: "confirm_link",
    month: "all",
    affected_row_ids: ["bk-flow-rule-e2e-needs-invoice", "iv-flow-rule-e2e-needs-invoice"],
    case_id: "bank_flow_rule_batch_e2e_invoice_required",
    affected_months: ["2026-05"],
    affected_scope_keys: ["2026-05"],
    freshness_targets: [
      { read_model_key: "workbench_relation", scope_key: "2026-05" },
      { read_model_key: "bank_flow_rule_batch", scope_key: "2026-05" },
    ],
    operation_projection: {
      after: {
        paired_groups: [bankFlowRuleInvoiceRequiredGroup("paired", true)],
        unpaired_groups: [],
      },
    },
    message: "已确认流水规则批次补票关联。",
  };
}

function buildLargeWorkbenchGroup(index: number, zone: WorkbenchZone = "unpaired") {
  const suffix = String(index).padStart(3, "0");
  const caseId = `CASE-LARGE-202603-${suffix}`;
  const amount = `${(42000 + index * 137).toLocaleString("en-US")}.00`;
  const supplier = `长列表供应商${suffix}有限公司`;
  const rows = {
    oa: {
      ...workbenchRows().oa,
      id: `oa-large-202603-${suffix}`,
      case_id: caseId,
      applicant: `大数据申请人${suffix}`,
      project_name: `长列表项目第${index}组`,
      amount,
      counterparty_name: supplier,
      reason: `第${index}组设备服务尾款，备注文本较长用于验证列宽和横向滚动稳定性`,
      detail_fields: {
        审批完成时间: `2026-03-${String((index % 27) + 1).padStart(2, "0")} 18:10`,
        大数据场景: `第${index}组 OA 详情`,
      },
    },
    bank: {
      ...workbenchRows().bank,
      id: `bk-large-202603-${suffix}`,
      case_id: caseId,
      trade_time: `2026-03-${String((index % 27) + 1).padStart(2, "0")} 10:18`,
      debit_amount: amount,
      counterparty_name: supplier,
      payment_account_label: `建设银行 ${String(1100 + index).slice(-4)}`,
      pay_receive_time: `2026-03-${String((index % 27) + 1).padStart(2, "0")} 10:18`,
      remark: `第${index}组长列表流水备注，包含跨栏长文本用于验证滚动后不遮挡操作区`,
      detail_fields: {
        银行流水编号: `BK-LARGE-${suffix}`,
        大数据场景: `第${index}组银行流水详情`,
      },
    },
    invoice: {
      ...workbenchRows().invoice,
      id: `iv-large-202603-${suffix}`,
      case_id: caseId,
      seller_tax_no: `91330108MA27B${suffix}`,
      seller_name: supplier,
      issue_date: `2026-03-${String((index % 27) + 1).padStart(2, "0")}`,
      amount,
      total_with_tax: amount,
      detail_fields: {
        发票号码: `LARGE-${suffix}`,
        大数据场景: `第${index}组发票详情`,
      },
    },
  };
  if (zone === "unpaired") {
    const rowType = (["oa", "bank", "invoice"] as const)[(index - 1) % 3];
    return buildUnpairedWorkbenchGroup(rowType, rows[rowType]);
  }
  return {
    group_id: `case:${caseId}`,
    group_type: "relation",
    match_confidence: "high",
    reason: `browser_e2e_large_dataset_${suffix}`,
    oa_rows: [rows.oa],
    bank_rows: [rows.bank],
    invoice_rows: [rows.invoice],
    can_withdraw: true,
    amount_check: {
      status: "matched",
      direction: "payment",
      bank_amount: amount.replace(/,/g, ""),
      oa_amount: amount.replace(/,/g, ""),
      amount_delta: "0.00",
      requires_note: false,
    },
  };
}

function largeWorkbenchGroups(zone: WorkbenchZone) {
  const total = zone === "paired" ? 5 : 205;
  return Array.from({ length: total }, (_, index) => buildLargeWorkbenchGroup(index + 1, zone));
}

function buildProcessedExceptionGroup() {
  const rows = workbenchRows();
  const handledRows = {
    oa: {
      ...rows.oa,
      handled_exception: true,
      oa_bank_relation: { code: "wait_input_invoice", label: "追进项发票", tone: "danger" },
      relation_note: "浏览器异常备注",
      available_actions: ["detail", "cancel_exception"],
    },
    bank: {
      ...rows.bank,
      handled_exception: true,
      invoice_relation: { code: "wait_input_invoice", label: "追进项发票", tone: "danger" },
      relation_note: "浏览器异常备注",
      available_actions: ["detail", "cancel_exception"],
    },
    invoice: {
      ...rows.invoice,
      handled_exception: true,
      invoice_bank_relation: { code: "wait_input_invoice", label: "追进项发票", tone: "danger" },
      relation_note: "浏览器异常备注",
      available_actions: ["detail", "cancel_exception"],
    },
  };
  return {
    group_id: "case:CASE-202603-101",
    group_type: "processed_exception",
    match_confidence: "medium",
    reason: "browser_e2e_processed_exception",
    oa_rows: [handledRows.oa],
    bank_rows: [handledRows.bank],
    invoice_rows: [handledRows.invoice],
    can_withdraw: false,
    relation_note: "浏览器异常备注",
    processed_exception_summary: {
      scenario: {
        code: "expense_oa_bank_missing_invoice",
        label: "OA和支出流水一致，缺进项发票",
      },
      resolution: {
        action_code: "wait_input_invoice",
        action_label: "追进项发票",
        note: "浏览器异常备注",
      },
      detail_note: "浏览器异常备注",
      display_tags: ["追进项发票"],
    },
    amount_check: {
      status: "mismatch",
      direction: "payment",
      bank_amount: "58000.00",
      oa_amount: "58000.00",
      amount_delta: "0.00",
      requires_note: true,
    },
  };
}

function buildUnpairedGroupsWithoutIgnoredInvoice() {
  return buildUnpairedWorkbenchGroups().filter((group) => group.invoice_rows.length === 0);
}

function ignoredWorkbenchRows(rowIgnored: boolean) {
  if (!rowIgnored) {
    return [];
  }
  const invoice = workbenchRows().invoice;
  return [
    {
      ...invoice,
      ignored: true,
      handled_exception: false,
      invoice_bank_relation: { code: "ignored", label: "浏览器忽略发票", tone: "warn" },
      available_actions: ["detail"],
      relation_note: "由关联台忽略发票：iv-o-202603-001",
    },
  ];
}

function workbenchGroups(
  zone: WorkbenchZone,
  relationConfirmed: boolean,
  exceptionApplied = false,
  rowIgnored = false,
  largeDataset = false,
  includeCashSpecialActions = false,
) {
  if (largeDataset) {
    return largeWorkbenchGroups(zone);
  }
  if (zone === "paired") {
    return relationConfirmed ? [buildPairedWorkbenchGroup(includeCashSpecialActions)] : [];
  }
  if (exceptionApplied) {
    return [buildProcessedExceptionGroup()];
  }
  if (rowIgnored) {
    return buildUnpairedGroupsWithoutIgnoredInvoice();
  }
  return relationConfirmed ? [] : buildUnpairedWorkbenchGroups();
}

function countWorkbenchRows(groups: Array<{ oa_rows: unknown[]; bank_rows: unknown[]; invoice_rows: unknown[] }>) {
  const counts = groups.reduce((total, group) => ({
    oa: total.oa + group.oa_rows.length,
    bank: total.bank + group.bank_rows.length,
    invoice: total.invoice + group.invoice_rows.length,
  }), { oa: 0, bank: 0, invoice: 0 });
  return {
    ...counts,
    rows: counts.oa + counts.bank + counts.invoice,
  };
}

const workbenchSearchableRowFields = [
  "label",
  "status",
  "category_label",
  "counterparty_name",
  "amount",
  "amount_value",
  "applicant",
  "application_time",
  "apply_time",
  "project_name_display",
  "project_name",
  "apply_type",
  "reason",
  "trade_time",
  "direction",
  "debit_amount",
  "credit_amount",
  "payment_account_label",
  "remark",
  "repayment_date",
  "seller_tax_no",
  "seller_name",
  "buyer_tax_no",
  "buyer_name",
  "invoice_code",
  "invoice_no",
  "digital_invoice_no",
  "issue_date",
  "tax_rate",
  "tax_amount",
  "total_with_tax",
  "invoice_type",
] as const;

function workbenchGroupMatchesSearch(group: unknown, query: string) {
  const normalizedQuery = query.trim().toLocaleLowerCase("zh-CN");
  if (!normalizedQuery || !group || typeof group !== "object") {
    return !normalizedQuery;
  }
  const payload = group as Record<string, unknown>;
  const rows: unknown[] = [];
  ["oa_rows", "bank_rows", "invoice_rows"].forEach((key) => {
    const value = payload[key];
    if (Array.isArray(value)) rows.push(...value);
  });
  const collapsedRows = payload.collapsed_rows;
  if (collapsedRows && typeof collapsedRows === "object") {
    Object.values(collapsedRows).forEach((value) => {
      if (Array.isArray(value)) rows.push(...value);
    });
  }
  return rows.some((row) => workbenchSearchableRowText(row).includes(normalizedQuery));
}

function workbenchSearchableRowText(row: unknown) {
  if (!row || typeof row !== "object") {
    return "";
  }
  const payload = row as Record<string, unknown>;
  const values = workbenchSearchableRowFields.map((key) => payload[key]);
  ["oa_bank_relation", "invoice_relation", "invoice_bank_relation", "relation"].forEach((key) => {
    const relation = payload[key];
    if (relation && typeof relation === "object") {
      values.push((relation as Record<string, unknown>).label);
    }
  });
  if (Array.isArray(payload.tags)) {
    values.push(...payload.tags);
  }
  if (Array.isArray(payload.bank_text_fields)) {
    payload.bank_text_fields.forEach((field) => {
      if (field && typeof field === "object") {
        values.push((field as Record<string, unknown>).label, (field as Record<string, unknown>).value);
      }
    });
  }
  values.push(...workbenchRowDisplaySearchAliases(payload));
  return values
    .filter((value): value is string | number => typeof value === "string" || typeof value === "number")
    .join(" ")
    .trim()
    .toLocaleLowerCase("zh-CN");
}

function workbenchRowDisplaySearchAliases(row: Record<string, unknown>) {
  const aliases: string[] = [];
  if (row.type === "bank" && typeof row.payment_account_label === "string") {
    const compactAccount = row.payment_account_label
      .replace(/^中国工商银行|^工商银行/, "工行")
      .replace(/^中国建设银行|^建设银行/, "建行")
      .replace(/^中国农业银行|^农业银行/, "农行")
      .replace(/^中国银行/, "中行")
      .replace(/^招商银行/, "招行")
      .replace(/^交通银行/, "交行")
      .replace(/^中国光大银行|^光大银行/, "光大")
      .replace(/^中国民生银行|^民生银行/, "民生")
      .replace(/^平安银行/, "平安");
    if (compactAccount !== row.payment_account_label) aliases.push(compactAccount);
  }
  if (row.type === "invoice") {
    const invoiceType = String(row.invoice_type ?? "").toLocaleLowerCase("zh-CN");
    if (invoiceType.includes("销") || invoiceType.includes("output") || invoiceType.includes("sale")) aliases.push("销");
    if (invoiceType.includes("进") || invoiceType.includes("input") || invoiceType.includes("purchase")) aliases.push("进");
    const sourceKind = String(row.source_kind ?? "");
    const sourceLabels: Record<string, string> = {
      etc_invoice_summary: "ETC批次",
      etc_invoice: "ETC",
      oa_attachment_invoice: "OA附件",
      oa_attachment_payment_receipt: "付款凭证",
      oa_attachment_unknown: "未识别附件",
    };
    if (invoiceType || sourceKind) aliases.push(sourceLabels[sourceKind] ?? "人工导入");
  }
  return aliases;
}

function workbenchSummary(
  relationConfirmed: boolean,
  exceptionApplied = false,
  rowIgnored = false,
  pageEmpty = false,
  largeDataset = false,
) {
  if (pageEmpty) {
    return {
      oa_count: 0,
      bank_count: 0,
      invoice_count: 0,
      paired_count: 0,
      unpaired_count: 0,
      exception_count: 0,
      ignored_count: rowIgnored ? 1 : 0,
    };
  }
  if (largeDataset) {
    return {
      oa_count: 210,
      bank_count: 210,
      invoice_count: 210,
      paired_count: 5,
      unpaired_count: 205,
      exception_count: 0,
      ignored_count: rowIgnored ? 1 : 0,
    };
  }
  return {
    oa_count: 1,
    bank_count: 1,
    invoice_count: 1,
    paired_count: relationConfirmed ? 1 : 0,
    unpaired_count: relationConfirmed || exceptionApplied ? 0 : 1,
    exception_count: exceptionApplied ? 3 : 0,
    ignored_count: rowIgnored ? 1 : 0,
  };
}

function workbenchGroupsPayload(
  zone: WorkbenchZone,
  relationConfirmed: boolean,
  exceptionApplied = false,
  rowIgnored = false,
  pageStatus: WorkbenchPageMockStatus = "fresh",
  pageEmpty = false,
  largeDataset = false,
  includeCashSpecialActions = false,
  page = 1,
  pageSize = 50,
  search = "",
) {
  const readModelVersion = relationConfirmed || exceptionApplied || rowIgnored
    ? "workbench-generation-e2e-002"
    : "workbench-generation-e2e-001";
  const allGroups = pageEmpty
    ? []
    : workbenchGroups(
      zone,
      relationConfirmed,
      exceptionApplied,
      rowIgnored,
      largeDataset,
      includeCashSpecialActions,
    );
  const normalizedSearch = search.trim().toLowerCase();
  const groups = normalizedSearch
    ? allGroups.filter((group) => workbenchGroupMatchesSearch(group, normalizedSearch))
    : allGroups;
  const boundedPage = Math.max(1, page);
  const boundedPageSize = Math.max(1, pageSize);
  const start = (boundedPage - 1) * boundedPageSize;
  const pageGroups = groups.slice(start, start + boundedPageSize);
  return {
    month: "all",
    zone,
    page: boundedPage,
    page_size: boundedPageSize,
    total: groups.length,
    row_counts: countWorkbenchRows(groups),
    has_more: start + pageGroups.length < groups.length,
    groups: pageGroups,
    read_model_status: pageStatus,
    read_model_version: readModelVersion,
    active_generation_id: readModelVersion,
  };
}

function bankFlowRuleWorkbenchGroupsPayload(
  zone: WorkbenchZone,
  relationConfirmed: boolean,
  page = 1,
  pageSize = 200,
  search = "",
) {
  const allGroups = bankFlowRuleWorkbenchGroups(zone, relationConfirmed);
  const normalizedSearch = search.trim().toLowerCase();
  const groups = normalizedSearch
    ? allGroups.filter((group) => workbenchGroupMatchesSearch(group, normalizedSearch))
    : allGroups;
  const boundedPage = Math.max(1, page);
  const boundedPageSize = Math.max(1, pageSize);
  const start = (boundedPage - 1) * boundedPageSize;
  const pageGroups = groups.slice(start, start + boundedPageSize);
  const readModelVersion = relationConfirmed
    ? "workbench-generation-e2e-002"
    : "workbench-generation-e2e-001";
  return {
    month: "all",
    zone,
    page: boundedPage,
    page_size: boundedPageSize,
    total: groups.length,
    row_counts: countWorkbenchRows(groups),
    has_more: start + pageGroups.length < groups.length,
    groups: pageGroups,
    read_model_status: "fresh",
    read_model_version: readModelVersion,
    active_generation_id: readModelVersion,
  };
}

function findWorkbenchRow(
  rowId: string,
  relationConfirmed: boolean,
  exceptionApplied = false,
  rowIgnored = false,
  largeDataset = false,
  includeCashSpecialActions = false,
) {
  const groups = [
    ...workbenchGroups(
      "paired",
      relationConfirmed,
      exceptionApplied,
      rowIgnored,
      largeDataset,
      includeCashSpecialActions,
    ),
    ...workbenchGroups("unpaired", relationConfirmed, exceptionApplied, rowIgnored, largeDataset),
  ];
  return groups
    .flatMap((group) => [...group.oa_rows, ...group.bank_rows, ...group.invoice_rows])
    .find((row) => row.id === rowId) ?? null;
}

function workbenchSettingsPayload(
  completedProjectIds: string[] = [],
  includeCostProject = false,
  accessControl: {
    allowedUsernames?: string[];
    readonlyExportUsernames?: string[];
    adminUsernames?: string[];
  } = {},
) {
  const settingsProjectCompleted = completedProjectIds.includes(settingsCostProject.id);
  const activeProjects = includeCostProject && !settingsProjectCompleted ? [settingsCostProject] : [];
  const completedProjects = includeCostProject && settingsProjectCompleted
    ? [{ ...settingsCostProject, project_status: "completed" as const }]
    : [];
  return {
    projects: {
      active: activeProjects,
      completed: completedProjects,
      completed_project_ids: completedProjectIds,
    },
    bank_account_mappings: [
      {
        id: "bank_mapping_8826",
        last4: "8826",
        bank_name: "建设银行",
        short_name: "建行",
      },
    ],
    access_control: {
      allowed_usernames: accessControl.allowedUsernames ?? [],
      readonly_export_usernames: accessControl.readonlyExportUsernames ?? [],
      admin_usernames: accessControl.adminUsernames ?? ["YNSYLP005"],
      full_access_usernames: (accessControl.allowedUsernames ?? []).filter(
        (username) => !(accessControl.readonlyExportUsernames ?? []).includes(username),
      ),
    },
    workbench_column_layouts: {
      oa: ["applicant", "projectName", "amount", "counterparty", "reason"],
      bank: ["counterparty", "amount", "loanRepaymentDate", "note"],
      invoice: ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
    },
    oa_retention: { cutoff_date: "2026-01-01" },
    oa_import: {
      form_types: ["payment_request", "expense_claim"],
      statuses: ["completed"],
      available_form_types: [
        { value: "payment_request", label: "支付申请" },
        { value: "expense_claim", label: "日常报销" },
      ],
      available_statuses: [
        { value: "completed", label: "已完成" },
        { value: "in_progress", label: "进行中" },
      ],
    },
    oa_invoice_offset: { applicant_names: [] },
    pending_invoice_tag_groups: {
      groups: {
        requires_invoice: { tag_codes: [] },
        bank_statement_as_invoice: { tag_codes: [] },
        no_invoice_required: { tag_codes: [] },
      },
    },
  };
}

function workbenchInitialPayload(
  relationConfirmed: boolean,
  exceptionApplied = false,
  rowIgnored = false,
  pageStatus: WorkbenchPageMockStatus = "fresh",
  pageEmpty = false,
  largeDataset = false,
  includeCashSpecialActions = false,
  zoneSearch: Partial<Record<WorkbenchZone, string>> = {},
) {
  const readModelVersion = relationConfirmed || exceptionApplied || rowIgnored
    ? "workbench-generation-e2e-002"
    : "workbench-generation-e2e-001";
  return {
    month: "all",
    summary: workbenchSummary(relationConfirmed, exceptionApplied, rowIgnored, pageEmpty, largeDataset),
    oa_status: { code: "ready", message: "OA 已同步" },
    invoice_inventory: {
      system_total: largeDataset ? 210 : 1,
      manual_import_total: 0,
      workbench_visible_total: largeDataset ? 210 : 1,
      hidden_submitted_etc_total: 0,
      extra_etc_total: 0,
      etc_summary_batch_count: 0,
      oa_attachment_total: largeDataset ? 210 : 1,
    },
    paired: workbenchGroupsPayload(
      "paired",
      relationConfirmed,
      exceptionApplied,
      rowIgnored,
      pageStatus,
      pageEmpty,
      largeDataset,
      includeCashSpecialActions,
      1,
      50,
      zoneSearch.paired ?? "",
    ),
    unpaired: workbenchGroupsPayload(
      "unpaired",
      relationConfirmed,
      exceptionApplied,
      rowIgnored,
      pageStatus,
      pageEmpty,
      largeDataset,
      includeCashSpecialActions,
      1,
      50,
      zoneSearch.unpaired ?? "",
    ),
    read_model_status: pageStatus,
    read_model_version: readModelVersion,
    active_generation_id: readModelVersion,
    generated_at: "2026-06-17T01:00:00Z",
  };
}

function inferImportScenarioFromPostData(postData: string | null): ImportScenario {
  if (
    postData?.includes("input_invoice")
    || postData?.includes("output_invoice")
    || postData?.includes("invoice_export")
    || postData?.includes("一月发票.xlsx")
    || postData?.includes("二月发票.xlsx")
  ) {
    return "invoice";
  }
  return "bank";
}

function importAudit(
  scenario: ImportScenario,
  imported = false,
  options: { corruptBankFile?: boolean; corruptInvoiceFile?: boolean } = {},
) {
  if (scenario === "invoice") {
    if (options.corruptInvoiceFile) {
      return {
        original_count: 15,
        unique_count: 13,
        duplicate_count: 1,
        duplicate_in_file_count: 1,
        duplicate_across_files_count: 0,
        existing_duplicate_count: 1,
        importable_count: imported ? 0 : 11,
        update_count: 0,
        merge_count: 0,
        suspected_duplicate_count: 1,
        error_count: 1,
        confirmable_count: imported ? 0 : 11,
        skipped_count: 3,
      };
    }
    return {
      original_count: 28,
      unique_count: 24,
      duplicate_count: 2,
      duplicate_in_file_count: 2,
      duplicate_across_files_count: 0,
      existing_duplicate_count: 2,
      importable_count: imported ? 0 : 22,
      update_count: 0,
      merge_count: 0,
      suspected_duplicate_count: 1,
      error_count: 1,
      confirmable_count: imported ? 0 : 22,
      skipped_count: 4,
    };
  }
  if (options.corruptBankFile) {
    return {
      original_count: 10,
      unique_count: 9,
      duplicate_count: 1,
      duplicate_in_file_count: 1,
      duplicate_across_files_count: 0,
      existing_duplicate_count: 0,
      importable_count: imported ? 0 : 7,
      update_count: 0,
      merge_count: 0,
      suspected_duplicate_count: 0,
      error_count: 1,
      confirmable_count: imported ? 0 : 7,
      skipped_count: 2,
    };
  }
  return {
    original_count: 18,
    unique_count: 16,
    duplicate_count: 2,
    duplicate_in_file_count: 2,
    duplicate_across_files_count: 1,
    existing_duplicate_count: 2,
    importable_count: imported ? 0 : 14,
    update_count: 0,
    merge_count: 0,
    suspected_duplicate_count: 0,
    error_count: 0,
    confirmable_count: imported ? 0 : 14,
    skipped_count: 4,
  };
}

function importPreviewFile(
  scenario: ImportScenario,
  fileName: string,
  index: number,
  imported = false,
  options: { corruptBankFile?: boolean; corruptInvoiceFile?: boolean; noBankAccountConflict?: boolean } = {},
) {
  const sessionId = importSessionIds[scenario];

  if (scenario === "invoice") {
    if (options.corruptInvoiceFile && index === 0) {
      return {
        id: `invoice_import_file_e2e_${index + 1}`,
        file_name: fileName,
        template_code: null,
        batch_type: "output_invoice",
        status: "unrecognized_template",
        message: "文件损坏，无法读取发票明细。",
        row_count: 0,
        success_count: 0,
        error_count: 1,
        duplicate_count: 0,
        suspected_duplicate_count: 0,
        updated_count: 0,
        audit: {
          original_count: 1,
          unique_count: 1,
          duplicate_count: 0,
          duplicate_in_file_count: 0,
          duplicate_across_files_count: 0,
          existing_duplicate_count: 0,
          importable_count: 0,
          update_count: 0,
          merge_count: 0,
          suspected_duplicate_count: 0,
          error_count: 1,
          confirmable_count: 0,
          skipped_count: 1,
        },
        preview_batch_id: `invoice_import_preview_e2e_${index + 1}`,
        batch_id: null,
        stored_file_path: `/tmp/${sessionId}/${fileName}`,
        override_template_code: "invoice_export",
        override_batch_type: "output_invoice",
        selected_bank_mapping_id: null,
        selected_bank_name: null,
        selected_bank_short_name: null,
        selected_bank_last4: null,
        detected_bank_name: null,
        detected_last4: null,
        bank_selection_conflict: false,
        conflict_message: null,
        row_results: [
          {
            id: "invoice_import_corrupt_row_e2e_1",
            row_no: 1,
            source_record_type: "invoice",
            decision: "error",
            decision_reason: "文件损坏，无法读取发票明细。",
            trade_time: null,
            direction: "output_invoice",
            amount: null,
            counterparty_name: fileName,
          },
        ],
      };
    }
    const batchType = index === 0 ? "output_invoice" : "input_invoice";
    return {
      id: `invoice_import_file_e2e_${index + 1}`,
      file_name: fileName,
      template_code: "invoice_export",
      batch_type: batchType,
      status: imported ? "confirmed" : "preview_ready",
      message: imported ? "已确认导入。" : "发票模板识别成功。",
      row_count: 14,
      success_count: 11,
      error_count: index === 0 ? 1 : 0,
      duplicate_count: 1,
      suspected_duplicate_count: index === 1 ? 1 : 0,
      updated_count: 0,
      audit: {
        original_count: 14,
        unique_count: 12,
        duplicate_count: 1,
        duplicate_in_file_count: 1,
        duplicate_across_files_count: 0,
        existing_duplicate_count: 1,
        importable_count: imported ? 0 : 11,
        update_count: 0,
        merge_count: 0,
        suspected_duplicate_count: index === 1 ? 1 : 0,
        error_count: index === 0 ? 1 : 0,
        confirmable_count: imported ? 0 : 11,
        skipped_count: 2,
      },
      preview_batch_id: `invoice_import_preview_e2e_${index + 1}`,
      batch_id: imported ? `invoice_import_batch_e2e_${index + 1}` : null,
      stored_file_path: `/tmp/${sessionId}/${fileName}`,
      override_template_code: "invoice_export",
      override_batch_type: batchType,
      selected_bank_mapping_id: null,
      selected_bank_name: null,
      selected_bank_short_name: null,
      selected_bank_last4: null,
      detected_bank_name: null,
      detected_last4: null,
      bank_selection_conflict: false,
      conflict_message: null,
      row_results: [
        {
          id: `invoice_import_preview_row_${index + 1}`,
          row_no: 1,
          source_record_type: "invoice",
          decision: imported ? "duplicate_skipped" : "created",
          decision_reason: imported ? "已导入或重复跳过。" : "Ready to create new invoice.",
          trade_time: index === 0 ? "2026-05-20" : "2026-05-21",
          direction: batchType,
          amount: index === 0 ? "65540.00" : "18320.00",
          counterparty_name: index === 0 ? "浏览器销项客户" : "浏览器进项供应商",
        },
      ],
    };
  }

  if (options.corruptBankFile && index === 0) {
    return {
      id: `import_file_e2e_${index + 1}`,
      file_name: fileName,
      template_code: null,
      batch_type: "bank_transaction",
      status: "unrecognized_template",
      message: "文件损坏，无法读取银行流水模板。",
      row_count: 0,
      success_count: 0,
      error_count: 1,
      duplicate_count: 0,
      suspected_duplicate_count: 0,
      updated_count: 0,
      audit: {
        original_count: 1,
        unique_count: 1,
        duplicate_count: 0,
        duplicate_in_file_count: 0,
        duplicate_across_files_count: 0,
        existing_duplicate_count: 0,
        importable_count: 0,
        update_count: 0,
        merge_count: 0,
        suspected_duplicate_count: 0,
        error_count: 1,
        confirmable_count: 0,
        skipped_count: 1,
      },
      preview_batch_id: `bank_import_preview_e2e_${index + 1}`,
      batch_id: null,
      stored_file_path: `/tmp/${sessionId}/${fileName}`,
      override_template_code: null,
      override_batch_type: null,
      selected_bank_mapping_id: "bank_mapping_8826",
      selected_bank_name: "建设银行",
      selected_bank_short_name: "建行",
      selected_bank_last4: "8826",
      detected_bank_name: null,
      detected_last4: null,
      bank_selection_conflict: false,
      conflict_message: null,
      row_results: [
        {
          id: "bank_import_corrupt_row_e2e_1",
          row_no: 1,
          source_record_type: "bank_transaction",
          decision: "error",
          decision_reason: "文件损坏，无法读取银行流水模板。",
          account_no: null,
          trade_time: null,
          direction: null,
          amount: null,
          counterparty_name: fileName,
        },
      ],
    };
  }

  const selectedBankLast4 = "8826";
  const detectedLast4 = options.noBankAccountConflict ? selectedBankLast4 : index === 0 ? "4080" : selectedBankLast4;
  const conflict = !imported && detectedLast4 !== selectedBankLast4;
  return {
    id: `import_file_e2e_${index + 1}`,
    file_name: fileName,
    template_code: index === 0 ? "icbc_historydetail" : "pingan_transaction_detail",
    batch_type: "bank_transaction",
    status: imported ? "confirmed" : "preview_ready",
    message: imported ? "已确认导入。" : "模板识别成功。",
    row_count: 9,
    success_count: 8,
    error_count: 0,
    duplicate_count: 1,
    suspected_duplicate_count: 0,
    updated_count: 0,
    audit: {
      original_count: 9,
      unique_count: 8,
      duplicate_count: 1,
      duplicate_in_file_count: 1,
      duplicate_across_files_count: index > 0 ? 1 : 0,
      existing_duplicate_count: index === 0 ? 2 : 0,
      importable_count: imported ? 0 : 7,
      update_count: 0,
      merge_count: 0,
      suspected_duplicate_count: 0,
      error_count: 0,
      confirmable_count: imported ? 0 : 7,
      skipped_count: index === 0 ? 3 : 1,
    },
    preview_batch_id: `bank_import_preview_e2e_${index + 1}`,
    batch_id: imported ? `bank_import_batch_e2e_${index + 1}` : null,
    stored_file_path: `/tmp/${sessionId}/${fileName}`,
    override_template_code: null,
    override_batch_type: null,
    selected_bank_mapping_id: "bank_mapping_8826",
    selected_bank_name: "建设银行",
    selected_bank_short_name: "建行",
    selected_bank_last4: selectedBankLast4,
    detected_bank_name: "建设银行",
    detected_last4: detectedLast4,
    bank_selection_conflict: conflict,
    conflict_message: conflict ? "后四位选择为8826，系统识别为4080" : null,
    row_results: [
      {
        id: `bank_import_preview_row_${index + 1}`,
        row_no: 1,
        source_record_type: "bank_transaction",
        decision: imported ? "duplicate_skipped" : "created",
        decision_reason: imported ? "已导入或重复跳过。" : "Ready to create new bank transaction.",
        account_no: `6222********${detectedLast4}`,
        trade_time: index === 0 ? "2026-05-18 09:30:00" : "2026-05-19 10:40:00",
        direction: index === 0 ? "income" : "expense",
        amount: index === 0 ? "1688.00" : "488.00",
        counterparty_name: index === 0 ? "导入浏览器测试客户" : "导入浏览器测试供应商",
      },
    ],
  };
}

function importDuplicateGroups(scenario: ImportScenario) {
  if (scenario === "invoice") {
    return [
      {
        identity_key: "invoice:e2e:duplicate:001",
        record_type: "invoice",
        duplicate_type: "duplicate_in_file",
        rows: [
          {
            file_id: "invoice_import_file_e2e_1",
            file_name: importFiles.invoice[0],
            row_no: 3,
            decision: "duplicate_skipped",
            decision_reason: "同文件重复。",
            trade_time: "2026-05-20",
            direction: "output_invoice",
            amount: "65540.00",
            counterparty_name: "浏览器销项客户",
          },
        ],
      },
    ];
  }
  return [
    {
      identity_key: "bank:e2e:duplicate:001",
      record_type: "bank_transaction",
      duplicate_type: "duplicate_in_file",
      rows: [
        {
          file_id: "import_file_e2e_1",
          file_name: importFiles.bank[0],
          row_no: 2,
          decision: "duplicate_skipped",
          decision_reason: "同文件重复。",
          account_no: "6222********4080",
          trade_time: "2026-05-18 09:35:00",
          direction: "income",
          amount: "1688.00",
          counterparty_name: "导入浏览器测试客户",
        },
      ],
    },
  ];
}

function importSessionPayload(
  scenario: ImportScenario,
  imported = false,
  options: { corruptBankFile?: boolean; corruptInvoiceFile?: boolean; noBankAccountConflict?: boolean } = {},
) {
  const sessionId = importSessionIds[scenario];
  return {
    session: {
      id: sessionId,
      imported_by: "web_finance_user",
      file_count: importFiles[scenario].length,
      status: imported ? "confirmed" : "preview_ready",
      created_at: "2026-06-17T01:00:00Z",
      audit: importAudit(scenario, imported, options),
    },
    files: importFiles[scenario].map((fileName, index) => importPreviewFile(scenario, fileName, index, imported, options)),
    duplicate_groups: importDuplicateGroups(scenario),
    matching_run: imported
      ? {
        id: `match_run_import_${scenario}_e2e_001`,
        triggered_by: `import_session:${sessionId}`,
        result_count: 2,
        automatic_count: 1,
        suggested_count: 1,
        manual_review_count: 0,
      }
      : undefined,
    operation_barrier_targets: [],
  };
}

function etcReadyTasksPayload() {
  return {
    tasks: [
      {
        task_id: "etc_task_ready_001",
        status: "ready_for_import",
        version: 7,
        title: "2026-03 ETC 对账",
        period_start: "2026-03-01",
        period_end: "2026-03-31",
        oa_total_amount: "188.00",
        etc_invoice_count: 3,
        supplement_count: 1,
        vehicle_plates: ["云ADA0381"],
      },
    ],
    unavailable_tasks: [],
  };
}

function etcImportAudit() {
  return {
    original_count: 4,
    unique_count: 3,
    duplicate_count: 1,
    duplicate_in_file_count: 1,
    duplicate_across_files_count: 0,
    existing_duplicate_count: 1,
    importable_count: 1,
    update_count: 0,
    merge_count: 1,
    suspected_duplicate_count: 0,
    error_count: 1,
    confirmable_count: 2,
    skipped_count: 2,
  };
}

function etcImportPayload(includeJob = false) {
  return {
    ...(includeJob
      ? {
        job: {
          job_id: "job_etc_import_e2e_001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "正在导入 ETC发票 0/4",
          status: "queued",
          phase: "queued",
          current: 0,
          total: 4,
          percent: 0,
          message: "ETC发票导入任务已创建。",
          source: {
            task_id: "etc_task_ready_001",
            route: "/imports/etc-invoices",
            affected_domains: ["imports_etc_invoices", "etc_tickets"],
          },
          affected_months: ["2026-03"],
          created_at: "2026-06-17T01:00:00Z",
          updated_at: "2026-06-17T01:00:00Z",
        },
      }
      : {}),
    session_id: "etc_import_session_e2e_001",
    summary: {
      imported: 1,
      duplicates_skipped: 1,
      attachments_completed: 1,
      failed: 1,
    },
    audit: etcImportAudit(),
    import_audit: etcImportAudit(),
    reconciliation_filter: {
      task_id: "etc_task_ready_001",
      task_version: 7,
      confirmed_item_set_hash: "etc-task-ready-e2e-hash",
      allowed_invoice_numbers: ["ETC-2026-005", "ETC-2026-007"],
      blocking_issues: [],
    },
    items: [
      {
        invoice_number: "ETC-2026-005",
        file_name: "etc-2026-03.zip",
        status: "imported",
        reason: "新发票待导入",
        filter_status: "included",
        requirement_id: "REQ-ETC-001",
      },
      {
        invoice_number: "ETC-2026-006",
        file_name: "etc-2026-03.zip",
        status: "duplicate_skipped",
        reason: "同包重复 XML",
        filter_status: "included",
        requirement_id: "REQ-ETC-001",
      },
      {
        invoice_number: "ETC-2026-007",
        file_name: "etc-2026-04.zip",
        status: "attachment_completed",
        reason: "补充凭证匹配",
        filter_status: "included",
        requirement_id: "REQ-ETC-002",
      },
      {
        invoice_number: "",
        file_name: "broken-etc.xml",
        status: "failed",
        reason: "XML 解析失败",
        filter_status: "not_in_reconciliation_preview",
        requirement_id: null,
      },
    ],
  };
}

function etcReconciliationWorkflowTaskPayload(options: {
  sourceFileDeleted?: boolean;
  taskId?: string;
  ticketRootUploaded?: boolean;
} = {}) {
  const sourceFileDeleted = Boolean(options.sourceFileDeleted);
  const sourceFiles = [
    ...(!sourceFileDeleted
      ? [{
        file_id: "etc-source-e2e-001",
        source_kind: "credit_card_statement",
        original_name: "ccb-statement.pdf",
        content_type: "application/pdf",
        has_blocking_issue: false,
      }]
      : []),
    ...(options.ticketRootUploaded
      ? [{
        file_id: "etc-source-e2e-upload-001",
        source_kind: "ticket_root",
        original_name: "ticket-root-upload.txt",
        content_type: "text/plain",
        has_blocking_issue: false,
      }]
      : []),
  ];
  return {
    task_id: options.taskId ?? "etc-recon-workflow-e2e-001",
    status: "reviewing",
    version: 5 + (sourceFileDeleted ? 1 : 0) + (options.ticketRootUploaded ? 1 : 0),
    title: "2026-03 ETC 对账流程",
    period_start: "2026-03-01",
    period_end: "2026-03-31",
    statement_period_start: "2026-03-01",
    statement_period_end: "2026-03-31",
    oa_total_amount: "120.00",
    etc_invoice_amount: "95.00",
    supplement_amount: "25.00",
    etc_invoice_count: 2,
    supplement_count: 1,
    can_confirm: false,
    vehicle_plates: ["云ADA0381"],
    confirmed_item_set_hash: "",
    import_batch_id: "",
    etc_batch_id: "",
    has_imported_invoices: false,
    imported_invoice_count: 0,
    imported_invoice_amount: "0.00",
    oa_draft_batch_id: "",
    oa_draft_status: "",
    submitted_confirmed_at: "",
    source_files: sourceFiles,
    credit_card_items: [
      {
        item_id: "etc-card-e2e-001",
        transaction_date: "2026-03-27",
        posting_date: "2026-03-28",
        card_last4: "3632",
        description: "高速通行费",
        amount: "95.00",
        settlement_amount: "95.00",
        is_etc_candidate: true,
        candidate_reason: "ETC关键词",
        recommendation_status: "ticket_suggested",
        manual_resolution: "unresolved",
        manual_resolution_reason: "",
        review_note: "",
      },
    ],
    ticket_root_items: [
      {
        item_id: "etc-ticket-root-e2e-001",
        source_file_id: "etc-source-e2e-002",
        vehicle_plate: "云ADA0381",
        transaction_at: "2026-03-27T10:20:00",
        amount: "95.00",
        entry_station: "昆明东",
        exit_station: "大理",
        invoice_count: 1,
        recommendation_status: "suggested",
        linked_credit_card_item_ids: [],
      },
    ],
    supplement_evidences: [
      {
        evidence_id: "etc-supplement-e2e-001",
        source_name: "parking.pdf",
        evidence_kind: "non_etc_invoice",
        amount: "25.00",
        paid_at: "2026-03-27",
        merchant_name: "高速停车费",
        tags: ["parking"],
        include_in_etc_zip_check: true,
        include_in_oa_submission: true,
        include_in_workbench: true,
      },
    ],
    reconciled_items: [],
    parse_issues: [
      {
        issue_id: "etc-parse-warning-e2e-001",
        file_id: "etc-source-e2e-002",
        source_kind: "ticket_root",
        original_name: "ticket-root.txt",
        severity: "warning",
        message: "票根网缺少车牌号，等待人工核对。",
        source_line: 3,
        extraction_method: "txt",
        field_name: "vehicle_plate",
      },
    ],
  };
}

function etcBusinessBatchVersion(status: EtcBusinessBatchStatus) {
  if (status === "imported") {
    return 7;
  }
  if (status === "oa_confirmation_pending") {
    return 8;
  }
  return 9;
}

function etcBusinessBatchInvoiceItems() {
  return [
    {
      id: "etc-inv-e2e-001",
      invoice_number: "ETC-E2E-001",
      issue_date: "2026-03-27",
      passage_start_date: "2026-03-27",
      passage_end_date: "2026-03-27",
      plate_number: "云ADA0381",
      seller_name: "云南高速通行费",
      buyer_name: "云南溯源科技",
      amount_without_tax: "12.34",
      tax_amount: "0.73",
      total_amount: "13.07",
      status: "unsubmitted",
      has_pdf: true,
      has_xml: true,
    },
    {
      id: "etc-inv-e2e-002",
      invoice_number: "ETC-E2E-002",
      issue_date: "2026-03-28",
      passage_start_date: "2026-03-28",
      passage_end_date: "2026-03-28",
      plate_number: "云ADA0381",
      seller_name: "云南高速通行费",
      buyer_name: "云南溯源科技",
      amount_without_tax: "18.10",
      tax_amount: "1.09",
      total_amount: "19.19",
      status: "unsubmitted",
      has_pdf: true,
      has_xml: true,
    },
  ];
}

function etcBusinessBatchPayload(status: EtcBusinessBatchStatus, includeItems = false) {
  const draftCreated = status !== "imported" && status !== "not_submitted";
  const submitted = status === "manually_marked_submitted";
  const createOaDraftAction = status === "imported" || status === "not_submitted"
    ? { enabled: true, code: "ready", message: "可以提交审批。" }
    : status === "oa_confirmation_pending"
      ? { enabled: false, code: "oa_confirmation_pending", message: "审批草稿已创建，请先确认是否已在 OA 提交。" }
      : { enabled: false, code: "invalid_batch_status", message: "当前批次状态不能创建审批草稿。" };
  return {
    business_batch_id: "etc-business-e2e-001",
    task_id: "etc-recon-e2e-001",
    status,
    version: etcBusinessBatchVersion(status),
    owner_user_id: "web_finance_user",
    owner_org_id: "finance",
    import_batch_ids: ["etc-import-e2e-001"],
    submission_batch_id: draftCreated ? "etc-submission-e2e-001" : "",
    external_etc_batch_id: "ETC-E2E-2026-03",
    oa_draft_id: draftCreated ? "oa-draft-etc-e2e-001" : "",
    oa_draft_url: draftCreated ? "https://oa.example.test/draft/etc-e2e" : "",
    oa_row_id: submitted ? "oa-etc-e2e-001" : "",
    oa_process_status: submitted ? "manual_without_oa_row" : "",
    invoice_summary: { count: 2, amount: "32.26" },
    create_oa_draft_action: createOaDraftAction,
    created_at: "2026-06-17T09:00:00+08:00",
    updated_at: "2026-06-17T09:00:00+08:00",
    ...(includeItems ? {
      invoice_ids: ["etc-inv-e2e-001", "etc-inv-e2e-002"],
      import_attempts: [
        {
          attempt_id: "etc-import-attempt-e2e-001",
          import_batch_id: "etc-import-e2e-001",
          status: "imported",
          imported: 2,
          duplicates_skipped: 0,
          attachments_completed: 0,
          failed: 0,
          created_at: "2026-06-17T09:00:00+08:00",
        },
      ],
      audit_events: [],
      invoice_items: etcBusinessBatchInvoiceItems(),
    } : {}),
  };
}

function etcBusinessBatchListPayload(bucket: string | null, batchStatus: EtcBusinessBatchStatus, deleted = false) {
  if (deleted) {
    return {
      items: [],
      counts: {
        unsubmitted: 0,
        staged: 0,
        submitted: 0,
      },
      pagination: {
        page: 1,
        page_size: 100,
        total: 0,
      },
    };
  }
  const batchBucket = batchStatus === "manually_marked_submitted"
    ? "submitted"
    : batchStatus === "oa_confirmation_pending"
      ? "staged"
      : "unsubmitted";
  const requestedBucket = bucket ?? "unsubmitted";
  const visible = requestedBucket === batchBucket;
  return {
    items: visible ? [etcBusinessBatchPayload(batchStatus, false)] : [],
    counts: {
      unsubmitted: batchBucket === "unsubmitted" ? 1 : 0,
      staged: batchBucket === "staged" ? 1 : 0,
      submitted: batchBucket === "submitted" ? 1 : 0,
    },
    pagination: {
      page: 1,
      page_size: 100,
      total: visible ? 1 : 0,
    },
  };
}

function taxSourceVersions(month: string) {
  return {
    tax_offset_read_model_schema_version: "2026-07-tax-offset-audit-proof-v3",
    invoice_fact_source_version: `mock-invoice-facts:${month}`,
    tax_certified_import_source_version: `mock-certified:${month}`,
  };
}

function formatTaxAmount(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function taxSummary(
  selectedInputIds: string[],
  certifiedImported: boolean,
  invoiceImportFanout = false,
  etcImportFanout = false,
) {
  const outputTax = 41600;
  const certifiedTax = certifiedImported ? 14080 : 0;
  const plannedTax = selectedInputIds.reduce((total, id) => {
    if (id === "ti-202603-001" && !certifiedImported) {
      return total + 12480;
    }
    if (id === "ti-202603-002") {
      return total + 5760;
    }
    if (invoiceImportFanout && id === "ti-202603-import-001") {
      return total + 1038.87;
    }
    if (etcImportFanout && id === "ti-202603-etc-import-001") {
      return total + 0.73;
    }
    return total;
  }, 0);
  const inputTax = certifiedTax + plannedTax;
  const deductibleTax = Math.min(outputTax, inputTax);
  const resultAmount = outputTax - deductibleTax;
  return {
    output_tax: formatTaxAmount(outputTax),
    certified_input_tax: formatTaxAmount(certifiedTax),
    planned_input_tax: formatTaxAmount(plannedTax),
    input_tax: formatTaxAmount(inputTax),
    deductible_tax: formatTaxAmount(deductibleTax),
    result_label: resultAmount >= 0 ? "本月应纳税额" : "本月留抵税额",
    result_amount: formatTaxAmount(Math.abs(resultAmount)),
  };
}

function taxOffsetLargeOutputItems() {
  return Array.from({ length: 80 }, (_, index) => {
    const sequence = index + 2;
    const day = String((index % 28) + 1).padStart(2, "0");
    const taxAmount = 800 + index * 17.35;
    const totalWithTax = taxAmount * 8.7;
    return {
      id: `to-202603-large-${String(sequence).padStart(3, "0")}`,
      buyer_name: `华东超长项目甲方-${String(sequence).padStart(3, "0")}-窄屏横向滚动验证`,
      issue_date: `2026-03-${day}`,
      invoice_no: `90342${String(sequence).padStart(5, "0")}`,
      tax_rate: index % 3 === 0 ? "13%" : "6%",
      tax_amount: formatTaxAmount(taxAmount),
      total_with_tax: formatTaxAmount(totalWithTax),
      invoice_type: "销项专票",
    };
  });
}

function taxOffsetLargeInputItems() {
  return Array.from({ length: 90 }, (_, index) => {
    const sequence = index + 3;
    const day = String(28 - (index % 28)).padStart(2, "0");
    const taxAmount = 360 + index * 11.2;
    const totalWithTax = taxAmount * 17.6;
    return {
      id: `ti-202603-large-${String(sequence).padStart(3, "0")}`,
      seller_name: `进项超长供应商-${String(sequence).padStart(3, "0")}-筛选滚动验证`,
      issue_date: `2026-03-${day}`,
      invoice_no: `11299${String(sequence).padStart(5, "0")}`,
      tax_rate: index % 2 === 0 ? "13%" : "6%",
      tax_amount: formatTaxAmount(taxAmount),
      total_with_tax: formatTaxAmount(totalWithTax),
      risk_level: index % 4 === 0 ? "高" : index % 3 === 0 ? "中" : "低",
      certified_status: "待认证",
      is_locked_certified: false,
    };
  });
}

function taxOffsetPayload(
  selectedInputIds: string[],
  certifiedImported: boolean,
  invoiceImportFanout = false,
  etcImportFanout = false,
  readModelStatus: TaxOffsetReadModelMockStatus = "fresh",
  largeDataset = false,
) {
  const month = "2026-03";
  const inputItems = [
    {
      id: "ti-202603-001",
      seller_name: "设备供应商",
      issue_date: "2026-03-22",
      invoice_no: "11203490",
      tax_rate: "13%",
      tax_amount: "12,480.00",
      total_with_tax: "108,480.00",
      risk_level: "低",
      certified_status: certifiedImported ? "已认证" : "待认证",
      is_locked_certified: certifiedImported,
    },
    {
      id: "ti-202603-002",
      seller_name: "材料供应商",
      issue_date: "2026-03-26",
      invoice_no: "11203491",
      tax_rate: "6%",
      tax_amount: "5,760.00",
      total_with_tax: "101,760.00",
      risk_level: "中",
      certified_status: "待认证",
      is_locked_certified: false,
    },
    ...(invoiceImportFanout
      ? [
        {
          id: "ti-202603-import-001",
          seller_name: "发票导入进项供应商",
          issue_date: "2026-05-21",
          invoice_no: "SD-INV-IMPORT-E2E-001",
          tax_rate: "6%",
          tax_amount: "1,038.87",
          total_with_tax: "18,320.00",
          risk_level: "低",
          certified_status: "待认证",
          is_locked_certified: false,
        },
      ]
      : []),
    ...(etcImportFanout
      ? [
        {
          id: "ti-202603-etc-import-001",
          seller_name: "ETC导入通行服务商",
          issue_date: "2026-03-27",
          invoice_no: "ETC-2026-005",
          tax_rate: "6%",
          tax_amount: "0.73",
          total_with_tax: "13.07",
          risk_level: "低",
          certified_status: "待认证",
          is_locked_certified: false,
        },
      ]
      : []),
    ...(largeDataset ? taxOffsetLargeInputItems() : []),
  ];
  const defaultSelectedInputIds = certifiedImported
    ? ["ti-202603-002"]
    : [
      ...selectedInputIds,
      ...(invoiceImportFanout && !selectedInputIds.includes("ti-202603-import-001") ? ["ti-202603-import-001"] : []),
      ...(etcImportFanout && !selectedInputIds.includes("ti-202603-etc-import-001") ? ["ti-202603-etc-import-001"] : []),
    ];
  if (readModelStatus !== "fresh") {
    return {
      month,
      read_model_status: readModelStatus,
      read_model_scope_key: month,
      read_model_generated_at: "2026-06-17T01:00:00Z",
      read_model_stale_reasons: [`tax_offset_${readModelStatus}`],
      source_versions: taxSourceVersions(month),
      output_items: [],
      input_plan_items: [],
      certified_items: [],
      certified_matched_rows: [],
      certified_outside_plan_rows: [],
      locked_certified_input_ids: [],
      default_selected_output_ids: [],
      default_selected_input_ids: [],
      summary: {
        output_tax: "0.00",
        certified_input_tax: "0.00",
        planned_input_tax: "0.00",
        input_tax: "0.00",
        deductible_tax: "0.00",
        result_label: "本月留抵税额",
        result_amount: "0.00",
      },
    };
  }

  return {
    month,
    read_model_status: "fresh",
    read_model_scope_key: month,
    read_model_generated_at: "2026-06-17T01:00:00Z",
    read_model_stale_reasons: [],
    source_versions: taxSourceVersions(month),
    output_items: [
      {
        id: "to-202603-001",
        buyer_name: "华东项目甲方",
        issue_date: "2026-03-25",
        invoice_no: "90342011",
        tax_rate: "13%",
        tax_amount: "41,600.00",
        total_with_tax: "361,600.00",
        invoice_type: "销项专票",
      },
      ...(largeDataset ? taxOffsetLargeOutputItems() : []),
    ],
    input_plan_items: inputItems,
    certified_items: certifiedImported
      ? [
        {
          id: "tc-202603-001",
          seller_name: "设备供应商",
          issue_date: "2026-03-22",
          invoice_no: "11203490",
          tax_rate: "13%",
          tax_amount: "12,480.00",
          total_with_tax: "108,480.00",
          status: "已认证",
          matched_input_id: "ti-202603-001",
        },
        {
          id: "tc-202603-002",
          seller_name: "高速通行服务商",
          issue_date: "2026-03-28",
          invoice_no: "ETC-202603-7788",
          tax_rate: "6%",
          tax_amount: "1,600.00",
          total_with_tax: "28,266.67",
          status: "已认证",
          matched_input_id: null,
        },
      ]
      : [],
    certified_matched_rows: certifiedImported
      ? [
        {
          id: "tc-202603-001",
          seller_name: "设备供应商",
          issue_date: "2026-03-22",
          invoice_no: "11203490",
          tax_rate: "13%",
          tax_amount: "12,480.00",
          total_with_tax: "108,480.00",
          status: "已认证",
          matched_input_id: "ti-202603-001",
        },
      ]
      : [],
    certified_outside_plan_rows: certifiedImported
      ? [
        {
          id: "tc-202603-002",
          seller_name: "高速通行服务商",
          issue_date: "2026-03-28",
          invoice_no: "ETC-202603-7788",
          tax_rate: "6%",
          tax_amount: "1,600.00",
          total_with_tax: "28,266.67",
          status: "已认证",
          matched_input_id: null,
        },
      ]
      : [],
    locked_certified_input_ids: certifiedImported ? ["ti-202603-001"] : [],
    default_selected_output_ids: ["to-202603-001"],
    default_selected_input_ids: defaultSelectedInputIds,
    summary: taxSummary(defaultSelectedInputIds, certifiedImported, invoiceImportFanout, etcImportFanout),
  };
}

function taxCertifiedImportPreviewPayload() {
  return {
    session: {
      id: "tax-certified-session-e2e-001",
      imported_by: "E2EUSER001",
      file_count: 1,
      status: "preview_ready",
    },
    files: [
      {
        id: "tax-certified-file-e2e-001",
        file_name: "2026年3月 进项认证结果.xlsx",
        month: "2026-03",
        recognized_count: 2,
        invalid_count: 0,
        matched_plan_count: 1,
        outside_plan_count: 1,
        rows: [
          {
            id: "tax-certified-row-e2e-001",
            month: "2026-03",
            row_status: "recognized",
            match_status: "matched_plan",
            matched_plan_id: "ti-202603-001",
            dedupe_status: "new",
            error_message: null,
            digital_invoice_no: null,
            invoice_code: "5300261130",
            invoice_no: "11203490",
            issue_date: "2026-03-22",
            seller_tax_no: "91530100E2E0001",
            seller_name: "设备供应商",
            tax_amount: "12,480.00",
            deductible_tax_amount: "12,480.00",
            selection_status: "用途确认",
            invoice_status: "正常",
            selection_time: "2026-04-01 09:10:00",
            source_file_name: "2026年3月 进项认证结果.xlsx",
            source_row_number: 1,
          },
          {
            id: "tax-certified-row-e2e-002",
            month: "2026-03",
            row_status: "recognized",
            match_status: "outside_plan",
            matched_plan_id: null,
            dedupe_status: "new",
            error_message: null,
            digital_invoice_no: "ETC-202603-7788",
            invoice_code: null,
            invoice_no: "ETC-202603-7788",
            issue_date: "2026-03-28",
            seller_tax_no: "91530100E2E0002",
            seller_name: "高速通行服务商",
            tax_amount: "1,600.00",
            deductible_tax_amount: "1,600.00",
            selection_status: "用途确认",
            invoice_status: "正常",
            selection_time: "2026-04-01 09:12:00",
            source_file_name: "2026年3月 进项认证结果.xlsx",
            source_row_number: 2,
          },
        ],
      },
    ],
    summary: {
      recognized_count: 2,
      invalid_count: 0,
      matched_plan_count: 1,
      outside_plan_count: 1,
    },
  };
}

function taxCertifiedImportConfirmPayload() {
  return {
    success: true,
    batch: {
      id: "tax-certified-batch-e2e-001",
      session_id: "tax-certified-session-e2e-001",
      imported_by: "E2EUSER001",
      file_count: 1,
      months: ["2026-03"],
      persisted_record_count: 2,
    },
  };
}

function inputInvoiceUsageWorkbenchRelationRow(relationConfirmed: boolean) {
  return {
    id: "input-usage-row-e2e-relation",
    invoice: {
      id: "input-invoice-row-e2e-relation",
      display_no: "SD-INV-E2E-REL-001",
      invoice_no: "12561048",
      invoice_code: "3300",
      digital_invoice_no: "SD-INV-E2E-REL-001",
      issue_date: "2026-03-28",
      seller_name: "智能工厂设备商",
      seller_tax_no: "91330108MA27B4011D",
      total_with_tax: "65540.00",
      amount_without_tax: "58000.00",
      tax_rate: "13%",
      tax_amount: "7540.00",
      specific_business_type: "设备采购",
      taxable_item_name: "智能工厂设备尾款",
    },
    payment_status: relationConfirmed
      ? {
        code: "paid",
        label: "已支付",
        reason: "关联台已确认 OA、流水和进项发票，支付状态可由 linked 关系证明。",
      }
      : {
        code: "pending",
        label: "待处理",
        reason: "关联台尚未建立 active 正式关系，不能证明已支付。",
      },
    oa: {
      primary: relationConfirmed
        ? {
            id: "oa-o-202603-001",
            applicant: "陈涛",
            application_type: "供应商付款申请",
            project_name: "智能工厂项目",
            amount: "58000.00",
            detail_available: true,
            relation_case_id: "CASE-202603-101",
            relation_status: "linked",
            relation_source: "workbench_relation",
          }
        : null,
      relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      detail_mode: relationConfirmed ? "single" : "none",
      summaries: [],
    },
    bank: {
      primary: relationConfirmed
        ? {
            id: "bk-o-202603-001",
            counterparty_name: "智能工厂设备商",
            trade_time: "2026-03-28 10:18:00",
            amount: "58000.00",
            direction: "outflow",
            direction_label: "支出",
            bank_name: "建设银行",
            account_last4: "1138",
            summary: "设备尾款已闭环",
            remark: "关联台已确认",
            detail_available: true,
            relation_case_id: "CASE-202603-101",
            relation_status: "linked",
            relation_source: "workbench_relation",
          }
        : null,
      relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      detail_mode: relationConfirmed ? "single" : "none",
      summaries: [],
    },
    invoice_relations: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      detail_mode: "none",
      summaries: [],
      total_with_tax: "0.00",
    },
  };
}

function inputInvoiceUsageRowsPayload(
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  readModelStatus: InputInvoiceUsageReadModelMockStatus = "fresh",
  includeRelationDetailList = false,
  paymentRulesSaved = false,
  paymentRulesSaveFlow = false,
  includeInvoiceImportRows = false,
) {
  if (readModelStatus !== "fresh") {
    return {
      rows: [],
      pagination: { page: 1, page_size: 20, total: 0 },
      filter_config: [
        { field: "seller_name", label: "销方名称", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
        { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
        { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
      ],
      read_model_status: "refreshing",
      read_model_scope_key: "all",
      read_model_stale_reasons: [`input_invoice_usage_${readModelStatus}`],
      refresh_enqueued: true,
    };
  }
  const rows = [
    ...(includeWorkbenchRelationEvidence ? [inputInvoiceUsageWorkbenchRelationRow(relationConfirmed)] : []),
    ...(includeInvoiceImportRows
      ? [
        {
          id: "input-usage-row-e2e-import",
          invoice: {
            id: "input-invoice-row-e2e-import",
            display_no: "SD-INV-IMPORT-E2E-001",
            invoice_no: "IMPORT-E2E-001",
            invoice_code: "5300",
            digital_invoice_no: "SD-INV-IMPORT-E2E-001",
            issue_date: "2026-05-21",
            seller_name: "发票导入进项供应商",
            seller_tax_no: "91530100IMPORTIN",
            total_with_tax: "18,320.00",
            amount_without_tax: "17,281.13",
            tax_rate: "6%",
            tax_amount: "1,038.87",
            specific_business_type: "导入发票",
            taxable_item_name: "发票导入 e2e 进项服务",
          },
          payment_status: {
            code: "pending",
            label: "待处理",
            reason: "发票导入后等待 OA 或流水关系刷新。",
          },
          oa: {
            primary: null,
            relation_count: 0,
            has_multiple: false,
            detail_mode: "none",
            summaries: [],
          },
          bank: {
            primary: null,
            relation_count: 0,
            has_multiple: false,
            detail_mode: "none",
            summaries: [],
          },
          invoice_relations: {
            primary: null,
            relation_count: 0,
            has_multiple: false,
            detail_mode: "none",
            summaries: [],
            total_with_tax: "0.00",
          },
        },
      ]
      : []),
    {
      id: "input-usage-row-e2e-001",
      invoice: {
        id: "input-invoice-row-e2e-001",
        display_no: "SD-INV-E2E-0001",
        invoice_no: "E2E-0001",
        invoice_code: "5300",
        digital_invoice_no: "SD-INV-E2E-0001",
        issue_date: "2026-05-02",
        seller_name: "浏览器进项供应商",
        seller_tax_no: "91530100E2EIN001",
        total_with_tax: "88.00",
        amount_without_tax: "83.02",
        tax_rate: "6%",
        tax_amount: "4.98",
        specific_business_type: "技术服务",
        taxable_item_name: "浏览器 e2e 进项服务",
      },
      payment_status: {
        code: paymentRulesSaveFlow ? "waiting_payment" : "pending",
        label: paymentRulesSaveFlow
          ? (paymentRulesSaved ? "待付款（规则保存后刷新）" : "待付款（自动识别有oa无流水）")
          : "待处理",
        reason: paymentRulesSaveFlow
          ? (paymentRulesSaved ? "保存后的支付状态规则重新计算。" : "当前规则识别有 OA 无流水。")
          : "尚未创建 OA 反提关系。",
      },
      oa: {
        primary: {
          id: "oa-input-e2e-001",
          applicant: "陈秀云",
          application_type: "费用报销",
          project_name: "浏览器进项项目",
          amount: includeRelationDetailList ? "188.00" : "88.00",
          detail_available: true,
        },
        relation_count: includeRelationDetailList ? 2 : 1,
        has_multiple: includeRelationDetailList,
        detail_mode: includeRelationDetailList ? "list" : "single",
        summaries: includeRelationDetailList
          ? [
            {
              oa_id: "oa-input-e2e-001",
              applicant_name: "陈秀云",
              amount: "88.00",
              relation_status: "linked",
            },
            {
              oa_id: "oa-input-e2e-002",
              applicant_name: "刘际涛",
              amount: "100.00",
              relation_status: "linked",
            },
          ]
          : [],
      },
      bank: {
        primary: paymentRulesSaveFlow ? null : {
          id: "bank-input-e2e-001",
          counterparty_name: "浏览器进项供应商",
          trade_time: "2026-05-03 10:30:00",
          amount: "88.00",
          direction: "outflow",
          direction_label: "支出",
          bank_name: "建设银行",
          account_last4: "1138",
          summary: "浏览器 e2e 进项付款",
          remark: "进项使用 e2e",
          detail_available: true,
        },
        relation_count: paymentRulesSaveFlow ? 0 : 1,
        has_multiple: false,
        detail_mode: paymentRulesSaveFlow ? "none" : "single",
        summaries: [],
      },
      invoice_relations: {
        primary: null,
        relation_count: 0,
        has_multiple: false,
        detail_mode: "none",
        summaries: [],
        total_with_tax: "0.00",
      },
    },
  ];
  return {
    rows,
    pagination: { page: 1, page_size: 20, total: rows.length },
    filter_config: [
      { field: "seller_name", label: "销方名称", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
    ],
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

type InputInvoiceUsageFilterSortRowInput = {
  id: string;
  displayNo: string;
  issueDate: string;
  sellerName: string;
  sellerTaxNo: string;
  totalWithTax: string;
  paymentCode: string;
  paymentLabel: string;
  oaApplicant: string;
  oaApplicationType: string;
  oaProjectName: string;
  bankCounterpartyName: string;
  bankTradeTime: string;
  bankAmount: string;
  bankAccount: string;
  bankDirection: string;
  bankDirectionLabel: string;
  summary: string;
};

function inputInvoiceUsageFilterSortRow(input: InputInvoiceUsageFilterSortRowInput) {
  return {
    id: input.id,
    invoice: {
      id: `${input.id}-invoice`,
      display_no: input.displayNo,
      invoice_no: input.displayNo.replace("SD-INV-", ""),
      invoice_code: "5300",
      digital_invoice_no: input.displayNo,
      issue_date: input.issueDate,
      seller_name: input.sellerName,
      seller_tax_no: input.sellerTaxNo,
      total_with_tax: input.totalWithTax,
      amount_without_tax: input.totalWithTax,
      tax_rate: "6%",
      tax_amount: "0.00",
      specific_business_type: "技术服务",
      taxable_item_name: `${input.sellerName} e2e 服务`,
    },
    payment_status: {
      code: input.paymentCode,
      label: input.paymentLabel,
      reason: input.paymentLabel,
    },
    oa: {
      primary: {
        id: `${input.id}-oa`,
        applicant: input.oaApplicant,
        application_type: input.oaApplicationType,
        project_name: input.oaProjectName,
        amount: input.totalWithTax,
        detail_available: true,
      },
      relation_count: 1,
      has_multiple: false,
      detail_mode: "single",
      summaries: [],
    },
    bank: {
      primary: {
        id: `${input.id}-bank`,
        counterparty_name: input.bankCounterpartyName,
        trade_time: input.bankTradeTime,
        amount: input.bankAmount,
        direction: input.bankDirection,
        direction_label: input.bankDirectionLabel,
        bank_name: "建设银行",
        account_last4: input.bankAccount.slice(-4),
        bank_account: input.bankAccount,
        summary: input.summary,
        remark: `${input.summary} 备注`,
        detail_available: true,
      },
      relation_count: 1,
      has_multiple: false,
      detail_mode: "single",
      summaries: [],
    },
    invoice_relations: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      detail_mode: "none",
      summaries: [],
      total_with_tax: "0.00",
    },
  };
}

function inputInvoiceUsageFilterSortDataset() {
  const anchorRows = [
    inputInvoiceUsageFilterSortRow({
      id: "input-usage-filter-row-001",
      displayNo: "SD-INV-E2E-0001",
      issueDate: "2026-05-02",
      sellerName: "浏览器进项供应商",
      sellerTaxNo: "91530100E2EIN001",
      totalWithTax: "88.00",
      paymentCode: "pending",
      paymentLabel: "待处理",
      oaApplicant: "陈秀云",
      oaApplicationType: "费用报销",
      oaProjectName: "浏览器进项项目",
      bankCounterpartyName: "浏览器进项供应商",
      bankTradeTime: "2026-05-03 10:30:00",
      bankAmount: "88.00",
      bankAccount: "建设银行 1138",
      bankDirection: "outflow",
      bankDirectionLabel: "支出",
      summary: "浏览器 e2e 进项付款",
    }),
    inputInvoiceUsageFilterSortRow({
      id: "input-usage-filter-row-002",
      displayNo: "SD-INV-E2E-0002",
      issueDate: "2026-05-04",
      sellerName: "已支付筛选供应商",
      sellerTaxNo: "91530100E2EIN002",
      totalWithTax: "166.00",
      paymentCode: "paid",
      paymentLabel: "已支付",
      oaApplicant: "李雷",
      oaApplicationType: "采购付款",
      oaProjectName: "已支付项目",
      bankCounterpartyName: "已支付筛选供应商",
      bankTradeTime: "2026-05-05 10:30:00",
      bankAmount: "166.00",
      bankAccount: "招商银行 6688",
      bankDirection: "outflow",
      bankDirectionLabel: "支出",
      summary: "已支付付款",
    }),
    inputInvoiceUsageFilterSortRow({
      id: "input-usage-filter-row-003",
      displayNo: "SD-INV-E2E-0003",
      issueDate: "2026-04-30",
      sellerName: "排序靠前供应商",
      sellerTaxNo: "91530100E2EIN003",
      totalWithTax: "66.00",
      paymentCode: "pending",
      paymentLabel: "待处理",
      oaApplicant: "王芳",
      oaApplicationType: "费用报销",
      oaProjectName: "排序项目",
      bankCounterpartyName: "排序靠前供应商",
      bankTradeTime: "2026-05-01 10:30:00",
      bankAmount: "66.00",
      bankAccount: "建设银行 1138",
      bankDirection: "outflow",
      bankDirectionLabel: "支出",
      summary: "排序付款",
    }),
  ];
  const fillerRows = Array.from({ length: 19 }, (_, index) => {
    const sequence = index + 10;
    return inputInvoiceUsageFilterSortRow({
      id: `input-usage-filter-row-${sequence}`,
      displayNo: `SD-INV-E2E-${String(sequence).padStart(4, "0")}`,
      issueDate: `2026-05-${String(6 + index).padStart(2, "0")}`,
      sellerName: `分页供应商${String(index + 1).padStart(2, "0")}`,
      sellerTaxNo: `91530100E2EPAGE${String(index + 1).padStart(2, "0")}`,
      totalWithTax: `${100 + index}.00`,
      paymentCode: index % 2 === 0 ? "pending" : "paid",
      paymentLabel: index % 2 === 0 ? "待处理" : "已支付",
      oaApplicant: index % 2 === 0 ? "陈秀云" : "李雷",
      oaApplicationType: index % 2 === 0 ? "费用报销" : "采购付款",
      oaProjectName: `分页项目${String(index + 1).padStart(2, "0")}`,
      bankCounterpartyName: `分页供应商${String(index + 1).padStart(2, "0")}`,
      bankTradeTime: `2026-05-${String(6 + index).padStart(2, "0")} 10:30:00`,
      bankAmount: `${100 + index}.00`,
      bankAccount: index % 2 === 0 ? "建设银行 1138" : "招商银行 6688",
      bankDirection: "outflow",
      bankDirectionLabel: "支出",
      summary: `分页付款${String(index + 1).padStart(2, "0")}`,
    });
  });
  return [
    ...anchorRows,
    ...fillerRows,
    inputInvoiceUsageFilterSortRow({
      id: "input-usage-filter-row-099",
      displayNo: "SD-INV-E2E-0099",
      issueDate: "2026-01-08",
      sellerName: "页外供应商",
      sellerTaxNo: "91530100E2EOUT99",
      totalWithTax: "990.00",
      paymentCode: "pending",
      paymentLabel: "待处理",
      oaApplicant: "赵敏",
      oaApplicationType: "费用报销",
      oaProjectName: "页外项目",
      bankCounterpartyName: "页外供应商",
      bankTradeTime: "2026-01-09 10:30:00",
      bankAmount: "990.00",
      bankAccount: "工商银行 9900",
      bankDirection: "outflow",
      bankDirectionLabel: "支出",
      summary: "页外付款",
    }),
  ];
}

function parseInputInvoiceUsageFilters(url?: URL) {
  const rawFilters = url?.searchParams.get("filters");
  if (!rawFilters) {
    return [];
  }
  try {
    const decoded = decodeURIComponent(rawFilters);
    const parsed = JSON.parse(decoded);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function inputInvoiceUsageNestedString(row: Record<string, unknown>, path: string[]) {
  let current: unknown = row;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return "";
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return String(current ?? "");
}

function inputInvoiceUsageFieldValue(row: Record<string, unknown>, field: string) {
  if (field === "invoice_date") {
    return inputInvoiceUsageNestedString(row, ["invoice", "issue_date"]);
  }
  if (field === "seller_name") {
    return inputInvoiceUsageNestedString(row, ["invoice", "seller_name"]);
  }
  if (field === "payment_status") {
    return inputInvoiceUsageNestedString(row, ["payment_status", "code"]);
  }
  if (field === "oa_applicant") {
    return inputInvoiceUsageNestedString(row, ["oa", "primary", "applicant"]);
  }
  if (field === "oa_application_type") {
    return inputInvoiceUsageNestedString(row, ["oa", "primary", "application_type"]);
  }
  if (field === "oa_project_name") {
    return inputInvoiceUsageNestedString(row, ["oa", "primary", "project_name"]);
  }
  if (field === "bank_counterparty_name") {
    return inputInvoiceUsageNestedString(row, ["bank", "primary", "counterparty_name"]);
  }
  if (field === "bank_account") {
    return inputInvoiceUsageNestedString(row, ["bank", "primary", "bank_account"])
      || [
        inputInvoiceUsageNestedString(row, ["bank", "primary", "bank_name"]),
        inputInvoiceUsageNestedString(row, ["bank", "primary", "account_last4"]),
      ].filter(Boolean).join(" ");
  }
  if (field === "bank_direction") {
    return inputInvoiceUsageNestedString(row, ["bank", "primary", "direction"]);
  }
  return "";
}

function applyInputInvoiceUsageListQuery(rows: Array<Record<string, unknown>>, url?: URL) {
  let nextRows = rows.slice();
  const keyword = url?.searchParams.get("keyword")?.trim();
  if (keyword) {
    nextRows = nextRows.filter((row) => [
      inputInvoiceUsageNestedString(row, ["invoice", "display_no"]),
      inputInvoiceUsageNestedString(row, ["invoice", "seller_name"]),
      inputInvoiceUsageNestedString(row, ["oa", "primary", "applicant"]),
      inputInvoiceUsageNestedString(row, ["bank", "primary", "counterparty_name"]),
      inputInvoiceUsageNestedString(row, ["bank", "primary", "summary"]),
    ].some((value) => value.includes(keyword)));
  }

  for (const filter of parseInputInvoiceUsageFilters(url)) {
    const field = String(filter?.field ?? "");
    const operator = String(filter?.operator ?? "");
    if (operator === "in" && Array.isArray(filter?.values)) {
      const values = new Set(filter.values.map((value: unknown) => String(value)));
      nextRows = nextRows.filter((row) => values.has(inputInvoiceUsageFieldValue(row, field)));
      continue;
    }
    if ((operator === "contains" || operator === "equals") && typeof filter?.value === "string") {
      const value = filter.value;
      nextRows = nextRows.filter((row) => {
        const fieldValue = inputInvoiceUsageFieldValue(row, field);
        return operator === "contains" ? fieldValue.includes(value) : fieldValue === value;
      });
    }
  }

  const sortField = url?.searchParams.get("sort_field") ?? "";
  const sortDirection = url?.searchParams.get("sort_direction") ?? "";
  if (sortField && (sortDirection === "asc" || sortDirection === "desc")) {
    nextRows.sort((left, right) => {
      const result = inputInvoiceUsageFieldValue(left, sortField).localeCompare(
        inputInvoiceUsageFieldValue(right, sortField),
        "zh-Hans-CN",
      );
      return sortDirection === "asc" ? result : -result;
    });
  }
  return nextRows;
}

function inputInvoiceUsageFilterConfig() {
  return [
    { field: "seller_name", label: "销方名称", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
    { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
    { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
    { field: "oa_application_type", label: "类型", mode: "enum_multi", sortable: true, operators: ["in"] },
    { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in"] },
    { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in"] },
    { field: "bank_account", label: "银行账户", mode: "enum_multi", sortable: false, operators: ["in"] },
    { field: "bank_direction", label: "收支", mode: "enum_multi", sortable: false, operators: ["in"] },
  ];
}

function inputInvoiceUsageOptionLabel(field: string, value: string) {
  if (field === "payment_status") {
    return value === "paid" ? "已支付" : value === "pending" ? "待处理" : value;
  }
  if (field === "bank_direction") {
    return value === "outflow" ? "支出" : value === "inflow" ? "收入" : value;
  }
  return value;
}

function inputInvoiceUsageOptionsForRows(rows: Array<Record<string, unknown>>, field: string) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = inputInvoiceUsageFieldValue(row, field);
    if (!value) {
      continue;
    }
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([left], [right]) => {
      if (left === "页外供应商") {
        return -1;
      }
      if (right === "页外供应商") {
        return 1;
      }
      return left.localeCompare(right, "zh-Hans-CN");
    })
    .map(([value, count]) => ({ value, label: inputInvoiceUsageOptionLabel(field, value), count }));
}

function inputInvoiceUsageFilterSortOptionsPayload() {
  const rows = inputInvoiceUsageFilterSortDataset();
  return {
    fields: inputInvoiceUsageFilterConfig().map((config) => ({
      ...config,
      options: inputInvoiceUsageOptionsForRows(rows, config.field),
    })),
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function inputInvoiceUsageFilterSortRowsPayload(url?: URL) {
  const rows = inputInvoiceUsageFilterSortDataset();
  const filteredRows = applyInputInvoiceUsageListQuery(rows, url);
  const page = positiveInteger(url?.searchParams.get("page"), 1);
  const pageSize = positiveInteger(url?.searchParams.get("page_size"), 20);
  const offset = (page - 1) * pageSize;
  return {
    rows: filteredRows.slice(offset, offset + pageSize),
    pagination: { page, page_size: pageSize, total: filteredRows.length },
    filter_config: inputInvoiceUsageFilterConfig(),
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function inputInvoiceUsageFilterOptionsPayload(readModelStatus: InputInvoiceUsageReadModelMockStatus = "fresh") {
  if (readModelStatus !== "fresh") {
    return {
      fields: [],
      read_model_status: "refreshing",
      read_model_scope_key: "all",
      read_model_stale_reasons: [`input_invoice_usage_${readModelStatus}`],
      refresh_enqueued: true,
    };
  }
  return {
    fields: [
      {
        field: "seller_name",
        label: "销方名称",
        mode: "enum_multi",
        sortable: true,
        operators: ["in", "contains"],
        options: [{ value: "浏览器进项供应商", label: "浏览器进项供应商", count: 1 }],
      },
      {
        field: "payment_status",
        label: "支付状态",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "pending", label: "待处理", count: 1 }],
      },
      {
        field: "oa_applicant",
        label: "OA申请人",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "陈秀云", label: "陈秀云", count: 1 }],
      },
    ],
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function inputInvoiceUsageRelationDetailPayload(
  kind: string,
  readModelStatus: InputInvoiceUsageReadModelMockStatus = "fresh",
) {
  const relationLabel = kind === "bank" ? "银行流水" : kind === "invoice" ? "发票" : "OA";
  if (readModelStatus !== "fresh") {
    return {
      row_id: "input-usage-row-e2e-001",
      invoice_id: "input-invoice-row-e2e-001",
      kind,
      title: `${relationLabel}关联明细`,
      relation_count: 0,
      has_multiple: false,
      summaries: [],
      sections: [],
      read_model_status: "refreshing",
      read_model_scope_key: "all",
      read_model_stale_reasons: [`input_invoice_usage_relation_detail_${readModelStatus}`],
      refresh_enqueued: true,
    };
  }
  return {
    row_id: "input-usage-row-e2e-001",
    invoice_id: "input-invoice-row-e2e-001",
    kind,
    title: `${relationLabel}关联明细`,
    relation_count: 2,
    has_multiple: true,
    summaries: ["陈秀云 88.00", "刘际涛 100.00"],
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function inputInvoiceUsageExportPreviewPayload(readModelStatus: InputInvoiceUsageReadModelMockStatus = "fresh") {
  if (readModelStatus !== "fresh") {
    return {
      file_name: "input-invoice-usage.xlsx",
      row_count: 0,
      scope_label: "当前筛选",
      columns: [],
      sample_rows: [],
      read_model_status: "refreshing",
      readModelStatus: "refreshing",
      message: "进项发票使用情况数据正在刷新，请稍后重试导出。",
      refresh_enqueued: true,
    };
  }
  return {
    file_name: "input-invoice-usage.xlsx",
    row_count: 1,
    scope_label: "当前筛选",
    columns: [
      "发票号码",
      "销方名称",
      "价税合计",
      "支付状态",
      "OA申请人",
      "OA金额",
      "支出流水对方户名",
      "关系案例",
      "关系状态",
    ],
    sample_rows: [
      {
        发票号码: "SD-INV-E2E-0001",
        销方名称: "浏览器进项供应商",
        价税合计: "88.00",
        支付状态: "待处理",
        OA申请人: "陈秀云",
        OA金额: "88.00",
        支出流水对方户名: "浏览器进项供应商",
        关系案例: "CASE-INPUT-E2E-001",
        关系状态: "linked",
      },
    ],
    read_model_status: "fresh",
  };
}

function inputInvoiceUsageExportBody(url: URL) {
  return [
    "发票号码,销方名称,价税合计,支付状态,OA申请人,OA金额,支出流水对方户名,关系案例,关系状态",
    [
      "SD-INV-E2E-0001",
      "浏览器进项供应商",
      "88.00",
      "待处理",
      "陈秀云",
      "88.00",
      "浏览器进项供应商",
      "CASE-INPUT-E2E-001",
      "linked",
    ].join(","),
    `keyword=${url.searchParams.get("keyword") ?? ""}`,
    `sort_field=${url.searchParams.get("sort_field") ?? ""}`,
    `sort_direction=${url.searchParams.get("sort_direction") ?? ""}`,
    `filters=${url.searchParams.get("filters") ?? ""}`,
    `page=${url.searchParams.get("page") ?? ""}`,
    `page_size=${url.searchParams.get("page_size") ?? ""}`,
  ].join("\n");
}

function inputInvoiceOaReverseInvoice(index: 1 | 2) {
  return {
    invoice_id: `input-oa-invoice-e2e-00${index}`,
    invoice_no: `SD-INV-E2E-00${index}`,
    display_no: `SD-INV-E2E-00${index}`,
    seller_name: index === 1 ? "浏览器进项供应商一" : "浏览器进项供应商二",
    issue_date: index === 1 ? "2026-05-20" : "2026-05-21",
    total_with_tax: "49.86",
    payment_status_label: "待处理",
    target_applicant_name: index === 1 ? "陈秀云" : "周洁莹",
  };
}

function inputInvoiceOaReverseWorkbenchInvoice() {
  return {
    invoice_id: "input-invoice-row-e2e-relation",
    invoice_no: "SD-INV-E2E-REL-001",
    display_no: "SD-INV-E2E-REL-001",
    seller_name: "智能工厂设备商",
    issue_date: "2026-03-28",
    total_with_tax: "65540.00",
    payment_status_label: "待处理",
    target_applicant_name: "陈涛",
  };
}

function inputInvoiceOaReverseRejectedRelationInvoice() {
  return {
    ...inputInvoiceOaReverseWorkbenchInvoice(),
    payment_status_label: "已支付",
    oa_relation_status: "linked",
    reason_code: "already_has_active_oa",
    reason: "关联台已确认 OA 关系。",
  };
}

function inputInvoiceUsagePaymentStatusRulesPayload(
  canSave: boolean,
  options: { version?: number; waitingPaymentLabel?: string } = {},
) {
  const version = options.version ?? 1;
  const waitingPaymentLabel = options.waitingPaymentLabel ?? "待付款（自动识别有oa无流水）";
  return {
    version,
    read_only: !canSave,
    rules: [
      {
        id: "waiting_payment",
        code: "waiting_payment",
        label: waitingPaymentLabel,
        description: "有发票、有 OA、无流水",
        priority: 6,
      },
      {
        id: "paid_full_match",
        code: "paid_full_match",
        label: "已付款（自动识别有oa有流水）",
        description: "有发票、有 OA、有流水，并且关联台完全匹配",
        priority: 2,
      },
    ],
    pending_directions: [
      { code: "pending", label: "待处理" },
      { code: "wei_dailian_batch_reverse", label: "韦代连批量反提oa" },
      { code: "chen_xiuyun_batch_reverse", label: "陈秀云批量反提oa" },
    ],
    permissions: { can_save: canSave },
  };
}

function inputInvoiceOaReversePreviewPayload(
  selectedInvoiceIds: string[],
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  canCreateDraft = true,
) {
  const selectableInvoices = [
    inputInvoiceOaReverseInvoice(1),
    inputInvoiceOaReverseInvoice(2),
    ...includeWorkbenchRelationEvidence && !relationConfirmed ? [inputInvoiceOaReverseWorkbenchInvoice()] : [],
  ];
  const selected = selectedInvoiceIds.length > 0
    ? selectedInvoiceIds
    : selectableInvoices.map((invoice) => invoice.invoice_id);
  const invoices = selectableInvoices
    .filter((invoice) => selected.includes(invoice.invoice_id));
  const isSubset = invoices.length === 1;
  const totalWithTax = invoices
    .reduce((total, invoice) => total + Number.parseFloat(invoice.total_with_tax), 0)
    .toFixed(2);
  const rejectedRelationInvoices = includeWorkbenchRelationEvidence && relationConfirmed
    ? [inputInvoiceOaReverseRejectedRelationInvoice()]
    : [];
  return {
    preview_id: isSubset ? "input-oa-reverse-preview-e2e-subset" : "input-oa-reverse-preview-e2e-all",
    preview_hash: isSubset ? "input-oa-reverse-hash-e2e-subset" : "input-oa-reverse-hash-e2e-all",
    source: selectedInvoiceIds.length > 0 ? "explicitSelection" : "currentFilters",
    target_applicant_code: "chen_xiuyun",
    target_applicant_name: "陈秀云",
    target_applicants: [
      { code: "chen_xiuyun", name: "陈秀云" },
      { code: "zhou_jieying", name: "周洁莹" },
    ],
    invoice_count: invoices.length,
    total_with_tax: totalWithTax,
    invoice_rows: invoices,
    groups: [
      {
        target_applicant_code: "chen_xiuyun",
        target_applicant_name: "陈秀云",
        invoice_count: invoices.length,
        total_with_tax: totalWithTax,
        candidate_invoice_ids: invoices.map((invoice) => invoice.invoice_id),
        invoice_rows: invoices,
        rejected_invoices: rejectedRelationInvoices,
      },
    ],
    rejected_invoices: rejectedRelationInvoices,
    can_create_draft: canCreateDraft,
    next_action: canCreateDraft ? "create_oa_draft" : "read_only",
    permissions: { can_create_draft: canCreateDraft, can_manual_status: canCreateDraft },
  };
}

function inputInvoiceOaReverseDraftPayload(status: "oa_draft_created" | "submitted_confirmed") {
  return {
    batch_id: "input-oa-reverse-batch-e2e-001",
    version: status === "submitted_confirmed" ? 5 : 4,
    status,
    invoice_ids: ["input-oa-invoice-e2e-001"],
    selected_invoice_ids: ["input-oa-invoice-e2e-001"],
    total_with_tax: "49.86",
    preview_summary: { invoice_count: 1, total_with_tax: "49.86" },
    target_applicant_code: "chen_xiuyun",
    target_applicant_name: "陈秀云",
    invoice_rows: [inputInvoiceOaReverseInvoice(1)],
    invoices: [inputInvoiceOaReverseInvoice(1)],
    rejected_invoices: [],
    oa_draft_id: "oa-draft-input-e2e-001",
    oa_draft_url: "https://oa.example.test/draft/input-e2e",
    oa_detection_status: status === "submitted_confirmed" ? "submitted_confirmed" : "draft_created",
    can_confirm_submission: status === "oa_draft_created",
    can_manual_status: true,
  };
}

function inputInvoiceOaReverseSubmittedHistoryPayload(submitted: boolean) {
  return {
    items: submitted
      ? [
        {
          target_applicant_name: "陈秀云",
          submitted_at: "2026-06-17T09:30:00+08:00",
          total_with_tax: "49.86",
          invoice_count: 1,
          invoices: [
            {
              invoice_no: "SD-INV-E2E-001",
              invoice_date: "2026-05-20",
              seller_name: "浏览器进项供应商一",
              total_with_tax: "49.86",
            },
          ],
        },
      ]
      : [],
  };
}

function oaPendingPaymentRowsPayload(includeInvoiceImportEvidence = false) {
  return {
    rows: [
      {
        id: "oa-payment-row-e2e-001",
        oa: {
          id: "oa-payment-e2e-001",
          applicantName: "浏览器付款申请人",
          applicationType: "支付申请",
          projectName: "浏览器待付款项目",
          applicationTime: "2026-05-20",
          amount: "12000.00",
          detailAvailable: true,
          relationCount: 1,
          relationStatus: "linked",
          relationSource: "workbench_relation",
        },
        paymentStatus: {
            code: "paid",
            label: "已支付",
            reason: "已存在已配对支出流水关系，金额差额不影响付款状态",
            severity: "success",
        },
        bankTransaction: {
          primaryBankTransactionId: "bank-payment-e2e-001",
          accountDetailNo: "bank-detail-payment-e2e-001",
          enterpriseSerialNo: "E2E-PAY-SERIAL-001",
          voucherKind: "电子转账凭证",
          voucherNo: "E2E-PAY-001",
          bankName: "建设银行",
          accountNo: "6222000000001234",
          accountLast4: "1234",
          bankAccount: "建设银行 1234",
          direction: "outflow",
          directionLabel: "支出",
          accountName: "云南溯源科技有限公司",
          tradeTime: "2026-05-21 09:30:00",
          debitAmount: "8000.00",
          creditAmount: "0.00",
          balance: "100000.00",
          currency: "人民币元",
          counterpartyName: "浏览器待付款供应商",
          counterpartyAccountNo: "2502124119024521999",
          counterpartyBankName: "建设银行昆明支行",
          bookedDate: "20260521",
          summary: "浏览器待付款",
          remark: "部分支付",
          amount: "8000.00",
          paidTotal: "8000.00",
          relationCount: 1,
          relationStatus: "linked",
          relationSource: "workbench_relation",
          hasMultiple: false,
          detailMode: "single",
        },
        invoice: {
          primaryInvoiceId: "invoice-payment-e2e-001",
          digitalInvoiceNo: "INV-PAY-E2E-001",
          sellerName: "浏览器待付款供应商",
          invoiceDate: "2026-05-22",
          totalWithTax: "12000.00",
          relationCount: 1,
          relationStatus: "linked",
          relationSource: "workbench_relation",
          hasMultiple: false,
          detailMode: "single",
        },
      },
      ...(includeInvoiceImportEvidence ? [
        {
          id: "oa-payment-row-invoice-import-e2e-001",
          oa: {
            id: "oa-payment-invoice-import-e2e-001",
            applicantName: "发票导入待付款申请人",
            applicationType: "支付申请",
            projectName: "发票导入待付款项目",
            applicationTime: "2026-05-21",
            amount: "18320.00",
            detailAvailable: true,
            relationCount: 1,
            relationStatus: "linked",
            relationSource: "invoice_import",
          },
          paymentStatus: {
            code: "paid",
            label: "已支付",
            reason: "发票导入后 OA 待付款 read model 已刷新。",
            severity: "success",
          },
          bankTransaction: {
            primaryBankTransactionId: "bank-payment-invoice-import-e2e-001",
            accountDetailNo: "bank-detail-invoice-import-e2e-001",
            enterpriseSerialNo: "E2E-IMPORT-PAY-SERIAL-001",
            voucherKind: "电子转账凭证",
            voucherNo: "E2E-IMPORT-PAY-001",
            bankName: "建设银行",
            accountNo: "6222000000001138",
            accountLast4: "1138",
            bankAccount: "建设银行 1138",
            direction: "outflow",
            directionLabel: "支出",
            accountName: "云南溯源科技有限公司",
            tradeTime: "2026-05-21 10:20:00",
            debitAmount: "18320.00",
            creditAmount: "0.00",
            balance: "81680.00",
            currency: "人民币元",
            counterpartyName: "发票导入进项供应商",
            counterpartyAccountNo: "2502124119024521888",
            counterpartyBankName: "建设银行昆明支行",
            bookedDate: "20260521",
            summary: "发票导入后待付款已闭环",
            remark: "发票导入下游刷新",
            amount: "18320.00",
            paidTotal: "18320.00",
            relationCount: 1,
            relationStatus: "linked",
            relationSource: "invoice_import",
            hasMultiple: false,
            detailMode: "single",
          },
          invoice: {
            primaryInvoiceId: "input-invoice-row-e2e-import",
            digitalInvoiceNo: "SD-INV-IMPORT-E2E-001",
            sellerName: "发票导入进项供应商",
            invoiceDate: "2026-05-21",
            totalWithTax: "18320.00",
            relationCount: 1,
            relationStatus: "linked",
            relationSource: "invoice_import",
            hasMultiple: false,
            detailMode: "single",
          },
        },
      ] : []),
    ],
    pagination: { page: 1, pageSize: 20, total: includeInvoiceImportEvidence ? 2 : 1 },
    summary: {
      rowCount: includeInvoiceImportEvidence ? 2 : 1,
      oaAmountTotal: includeInvoiceImportEvidence ? "30320.00" : "12000.00",
      bankPaidTotal: includeInvoiceImportEvidence ? "26320.00" : "8000.00",
      statusCounts: { paid: includeInvoiceImportEvidence ? 2 : 1 },
    },
    filterOptions: oaPendingPaymentFilterOptions(),
    filterConfig: [
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_trade_time", label: "交易时间", mode: "date", sortable: true, operators: ["between", "equals"] },
      { field: "bank_account", label: "银行账户", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "bank_direction", label: "收支", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "seller_name", label: "发票方", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
    ],
    readModelStatus: "fresh",
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function oaPendingPaymentWritebackPaidRowsPayload(confirmed: boolean) {
  return {
    rows: [
      {
        id: "oa-writeback-paid-row-e2e-001",
        oa: {
          id: "oa-writeback-paid-e2e-001",
          primaryOaId: "oa-writeback-paid-e2e-001",
          applicantName: "进行中付款申请人",
          applicationType: "付款申请",
          projectName: "进行中写回项目",
          applicationTime: "2026-06-18",
          amount: "9800.00",
          detailAvailable: true,
          workflowStatus: "in_progress",
          relationCount: 1,
          relationStatus: "linked",
          relationSource: "workbench_relation",
        },
        paymentStatus: {
          code: "paid",
          label: "已支付",
          reason: "支出流水合计等于 OA 金额，等待用户确认写回 OA。",
          severity: "success",
        },
        oaPaymentWriteback: confirmed
          ? { code: "written", label: "已写回", flowIds: ["flow-writeback-paid-e2e-001"], syncStatus: "ready" }
          : { code: "not_written", label: "未写回", flowIds: ["flow-writeback-paid-e2e-001"], syncStatus: "ready" },
        bankTransaction: {
          primaryBankTransactionId: "bank-writeback-paid-e2e-001",
          accountDetailNo: "bank-detail-writeback-paid-e2e-001",
          enterpriseSerialNo: "E2E-WRITEBACK-PAID-SERIAL-001",
          voucherKind: "电子转账凭证",
          voucherNo: "E2E-WRITEBACK-PAID-001",
          bankName: "招商银行",
          accountNo: "6222000000006789",
          accountLast4: "6789",
          bankAccount: "招商银行 6789",
          direction: "outflow",
          directionLabel: "支出",
          accountName: "云南溯源科技有限公司",
          tradeTime: "2026-06-18 10:30:00",
          debitAmount: "9800.00",
          creditAmount: "0.00",
          balance: "102400.00",
          currency: "人民币元",
          counterpartyName: "进行中写回供应商",
          counterpartyAccountNo: "2502124119024526789",
          counterpartyBankName: "招商银行昆明支行",
          bookedDate: "20260618",
          summary: confirmed ? "进行中 OA 已写回" : "进行中 OA 待写回",
          remark: confirmed ? "写回后刷新" : "确认已支付前",
          amount: "9800.00",
          paidTotal: "9800.00",
          relationCount: 1,
          relationStatus: "linked",
          relationSource: "workbench_relation",
          hasMultiple: false,
          detailMode: "single",
        },
        invoice: {
          primaryInvoiceId: null,
          digitalInvoiceNo: "",
          sellerName: "",
          invoiceDate: "",
          totalWithTax: "",
          relationCount: 0,
          hasMultiple: false,
          detailMode: "none",
        },
      },
    ],
    pagination: { page: 1, pageSize: 20, total: 1 },
    summary: {
      rowCount: 1,
      oaAmountTotal: "9800.00",
      bankPaidTotal: "9800.00",
      statusCounts: { paid: 1 },
      viewCounts: { completed: 1, in_progress: 1 },
    },
    filterOptions: oaPendingPaymentFilterOptions(),
    filterConfig: [
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_trade_time", label: "交易时间", mode: "date", sortable: true, operators: ["between", "equals"] },
      { field: "bank_account", label: "银行账户", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "bank_direction", label: "收支", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "seller_name", label: "发票方", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
    ],
    readModelStatus: "fresh",
    read_model_status: "fresh",
    read_model_scope_key: "oa_pending_payment:in_progress",
    sourceVersions: { oa_pending_payment: confirmed ? 2 : 1, workbench: 1 },
    source_versions: { oa_pending_payment: confirmed ? 2 : 1, workbench: 1 },
    viewMode: "in_progress",
    view_mode: "in_progress",
  };
}

function oaPendingPaymentBankLinkRowsPayload(linked: boolean) {
  return {
    rows: [
      {
        id: "oa-bank-link-row-e2e-001",
        oa: {
          id: "oa-bank-link-e2e-001",
          primaryOaId: "oa-bank-link-e2e-001",
          applicantName: "进行中关联申请人",
          applicationType: "付款申请",
          projectName: "进行中关联项目",
          applicationTime: "2026-06-18",
          amount: "7600.00",
          detailAvailable: true,
          workflowStatus: "in_progress",
          relationCount: linked ? 1 : 0,
          relationStatus: linked ? "linked" : undefined,
          relationSource: linked ? "workbench_relation" : undefined,
        },
        paymentStatus: linked
          ? {
            code: "paid",
            label: "已支付",
            reason: "支出流水已通过进行中 OA 关联抽屉建立 Workbench relation，并已自动写回 OA。",
            severity: "success",
          }
          : {
            code: "unpaid",
            label: "未支付",
            reason: "未关联支出流水",
            severity: "warning",
          },
        oaPaymentWriteback: linked
          ? { code: "written", label: "已写回", flowIds: ["flow-bank-link-e2e-001"], syncStatus: "ready" }
          : { code: "not_written", label: "未写回", flowIds: ["flow-bank-link-e2e-001"], syncStatus: "ready" },
        bankTransaction: linked
          ? {
            primaryBankTransactionId: "bank-link-e2e-001",
            accountDetailNo: "bank-detail-link-e2e-001",
            enterpriseSerialNo: "E2E-BANK-LINK-SERIAL-001",
            voucherKind: "电子转账凭证",
            voucherNo: "E2E-BANK-LINK-001",
            bankName: "招商银行",
            accountNo: "6222000000004567",
            accountLast4: "4567",
            bankAccount: "招商银行 4567",
            direction: "outflow",
            directionLabel: "支出",
            accountName: "云南溯源科技有限公司",
            tradeTime: "2026-06-18 11:20:00",
            debitAmount: "7600.00",
            creditAmount: "0.00",
            balance: "88800.00",
            currency: "人民币元",
            counterpartyName: "进行中关联供应商",
            counterpartyAccountNo: "2502124119024524567",
            counterpartyBankName: "招商银行昆明支行",
            bookedDate: "20260618",
            summary: "进行中 OA 抽屉关联",
            remark: "只建立 Workbench relation",
            amount: "7600.00",
            paidTotal: "7600.00",
            relationCount: 1,
            relationStatus: "linked_in_progress",
            relationSource: "workbench_relation",
            hasMultiple: false,
            detailMode: "single",
          }
          : {
            primaryBankTransactionId: null,
            accountDetailNo: "",
            enterpriseSerialNo: "",
            voucherKind: "",
            voucherNo: "",
            bankName: "",
            accountNo: "",
            accountLast4: "",
            bankAccount: "",
            direction: "",
            directionLabel: "",
            accountName: "",
            tradeTime: "",
            debitAmount: "",
            creditAmount: "",
            balance: "",
            currency: "",
            counterpartyName: "",
            counterpartyAccountNo: "",
            counterpartyBankName: "",
            bookedDate: "",
            summary: "",
            remark: "",
            amount: "",
            paidTotal: "0.00",
            relationCount: 0,
            hasMultiple: false,
            detailMode: "none",
          },
        invoice: {
          primaryInvoiceId: null,
          digitalInvoiceNo: "",
          sellerName: "",
          invoiceDate: "",
          totalWithTax: "",
          relationCount: 0,
          hasMultiple: false,
          detailMode: "none",
        },
      },
    ],
    pagination: { page: 1, pageSize: 20, total: 1 },
    summary: {
      rowCount: 1,
      oaAmountTotal: "7600.00",
      bankPaidTotal: linked ? "7600.00" : "0.00",
      statusCounts: linked ? { paid: 1 } : { unpaid: 1 },
      viewCounts: { completed: 1, in_progress: 1 },
    },
    filterOptions: oaPendingPaymentFilterOptions(),
    filterConfig: [
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_trade_time", label: "交易时间", mode: "date", sortable: true, operators: ["between", "equals"] },
      { field: "bank_account", label: "银行账户", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "bank_direction", label: "收支", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "seller_name", label: "发票方", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
    ],
    readModelStatus: "fresh",
    read_model_status: "fresh",
    read_model_scope_key: "oa_pending_payment:in_progress",
    sourceVersions: { oa_pending_payment: linked ? 2 : 1, workbench: linked ? 2 : 1 },
    source_versions: { oa_pending_payment: linked ? 2 : 1, workbench: linked ? 2 : 1 },
    viewMode: "in_progress",
    view_mode: "in_progress",
  };
}

function oaPendingPaymentBankCandidatesPayload(relationStatus = "all") {
  const rows = [
    {
      id: "bank-link-e2e-001",
      counterpartyName: "进行中关联供应商",
      tradeTime: "2026-06-18 11:20:00",
      amount: "7600.00",
      bankName: "招商银行",
      accountNo: "6222000000004567",
      accountLast4: "4567",
      bankAccount: "招商银行 4567",
      direction: "outflow",
      directionLabel: "支出",
      summary: "进行中 OA 抽屉关联",
      remark: "未配对支出流水",
      relationStatus: "unmatched",
      relationStatusLabel: "未配对",
    },
    {
      id: "bank-link-matched-e2e-001",
      counterpartyName: "已配对供应商",
      tradeTime: "2026-06-18 12:00:00",
      amount: "1200.00",
      bankName: "建设银行",
      accountNo: "6222000000009912",
      accountLast4: "9912",
      bankAccount: "建设银行 9912",
      direction: "outflow",
      directionLabel: "支出",
      summary: "其他业务已配对",
      remark: "不可选择",
      relationStatus: "matched",
      relationStatusLabel: "已配对",
    },
    {
      id: "bank-link-progress-e2e-001",
      counterpartyName: "已关联进行中供应商",
      tradeTime: "2026-06-18 13:00:00",
      amount: "300.00",
      bankName: "光大银行",
      accountNo: "6222000000008826",
      accountLast4: "8826",
      bankAccount: "光大银行 8826",
      direction: "outflow",
      directionLabel: "支出",
      summary: "已关联进行中OA流水",
      remark: "不可选择",
      relationStatus: "linked_in_progress",
      relationStatusLabel: "已关联进行中OA",
      linkedOaRowIds: ["oa-other-in-progress-e2e"],
    },
  ];
  const filteredRows = relationStatus === "all" ? rows : rows.filter((row) => row.relationStatus === relationStatus);
  return {
    rows: filteredRows,
    pagination: { page: 1, pageSize: 100, total: filteredRows.length },
    filters: { relationStatus, keyword: "" },
  };
}

function oaPendingPaymentRelationFanoutRowsPayload(relationConfirmed: boolean) {
  const relationFields = {
    relationStatus: relationConfirmed ? "linked" : "unlinked",
    relationSource: relationConfirmed ? "workbench_relation" : "",
  };
  return {
    rows: [
      {
        id: "oa-payment-row-workbench-001",
        oa: {
          id: "oa-o-202603-001",
          applicantName: "陈涛",
          applicationType: "供应商付款申请",
          projectName: "智能工厂项目",
          applicationTime: "2026-03-28",
          amount: "58000.00",
          detailAvailable: true,
          relationCount: relationConfirmed ? 1 : 0,
          ...relationFields,
        },
        paymentStatus: relationConfirmed
          ? {
            code: "paid",
            label: "已支付",
            reason: "关联台已确认 OA、银行流水和进项发票。",
            severity: "success",
          }
          : {
            code: "unpaid",
            label: "未支付",
            reason: "关联台尚未建立 active 正式关系，不能计入已支付。",
            severity: "warning",
          },
        bankTransaction: {
          primaryBankTransactionId: relationConfirmed ? "bk-o-202603-001" : "",
          accountDetailNo: relationConfirmed ? "bk-o-202603-001" : "",
          enterpriseSerialNo: relationConfirmed ? "E2E-BANK-202603-001" : "",
          voucherKind: "电子转账凭证",
          voucherNo: "E2E-BANK-202603-001",
          bankName: "建设银行",
          accountNo: "bank-account-1138",
          accountLast4: "1138",
          bankAccount: "建设银行 1138",
          direction: "outflow",
          directionLabel: "支出",
          accountName: "杭州溯源科技有限公司",
          tradeTime: "2026-03-28 10:18:00",
          debitAmount: "58000.00",
          creditAmount: "0.00",
          balance: "130500.50",
          currency: "人民币元",
          counterpartyName: relationConfirmed ? "智能工厂设备商" : "",
          counterpartyAccountNo: "",
          counterpartyBankName: "建设银行",
          bookedDate: "20260328",
          summary: relationConfirmed ? "设备尾款已闭环" : "",
          remark: relationConfirmed ? "关联台已确认" : "",
          amount: "58000.00",
          paidTotal: relationConfirmed ? "58000.00" : "0.00",
          relationCount: relationConfirmed ? 1 : 0,
          ...relationFields,
          hasMultiple: false,
          detailMode: "single",
        },
        invoice: {
          primaryInvoiceId: relationConfirmed ? "iv-o-202603-001" : "",
          digitalInvoiceNo: relationConfirmed ? "12561048" : "",
          sellerName: relationConfirmed ? "智能工厂设备商" : "",
          invoiceDate: relationConfirmed ? "2026-03-28" : "",
          totalWithTax: relationConfirmed ? "65540.00" : "0.00",
          relationCount: relationConfirmed ? 1 : 0,
          ...relationFields,
          hasMultiple: false,
          detailMode: "single",
        },
      },
    ],
    pagination: { page: 1, pageSize: 20, total: 1 },
    summary: {
      rowCount: 1,
      oaAmountTotal: "58000.00",
      bankPaidTotal: relationConfirmed ? "58000.00" : "0.00",
      statusCounts: relationConfirmed ? { paid: 1 } : { unpaid: 1 },
    },
    filterOptions: oaPendingPaymentFilterOptions(),
    filterConfig: [
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_project_name", label: "项目名称", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_counterparty_name", label: "对方户名", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "bank_trade_time", label: "交易时间", mode: "date", sortable: true, operators: ["between", "equals"] },
      { field: "bank_account", label: "银行账户", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "bank_direction", label: "收支", mode: "enum_multi", sortable: false, operators: ["in"] },
      { field: "seller_name", label: "发票方", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"] },
    ],
    readModelStatus: "fresh",
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function oaPendingPaymentNonFreshRowsPayload(readModelStatus: OaPendingPaymentReadModelMockStatus) {
  const payload = oaPendingPaymentRowsPayload(false);
  return {
    ...payload,
    rows: [],
    pagination: { page: 1, pageSize: 20, total: 0 },
    summary: { rowCount: 0, viewCounts: { completed: 0, in_progress: 0 } },
    readModelStatus,
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : ["oa_pending_payment_source_version_missing"],
    read_model_scope_key: "oa_pending_payment:all",
    sourceVersions: { oa_pending_payment: 1, workbench: 1 },
    source_versions: { oa_pending_payment: 1, workbench: 1 },
  };
}

function oaPendingPaymentFilterOptions() {
  const fields = [
      {
        field: "oa_applicant",
        label: "OA申请人",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "浏览器付款申请人", label: "浏览器付款申请人", count: 1 }],
      },
      {
        field: "oa_project_name",
        label: "项目名称",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "浏览器待付款项目", label: "浏览器待付款项目", count: 1 }],
      },
      {
        field: "payment_status",
        label: "支付状态",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "paid", label: "已支付", count: 1 }],
      },
      {
        field: "bank_counterparty_name",
        label: "对方户名",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "浏览器待付款供应商", label: "浏览器待付款供应商", count: 1 }],
      },
      { field: "bank_trade_time", label: "交易时间", mode: "date", sortable: true, operators: ["between", "equals"], options: [] },
      {
        field: "bank_account",
        label: "银行账户",
        mode: "enum_multi",
        sortable: false,
        operators: ["in"],
        options: [{ value: "建设银行 1234", label: "建设银行 1234", count: 1 }],
      },
      {
        field: "bank_direction",
        label: "收支",
        mode: "enum_multi",
        sortable: false,
        operators: ["in"],
        options: [{ value: "outflow", label: "支出", count: 1 }],
      },
      {
        field: "seller_name",
        label: "发票方",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [{ value: "浏览器待付款供应商", label: "浏览器待付款供应商", count: 1 }],
      },
      { field: "invoice_date", label: "开票日期", mode: "date", sortable: true, operators: ["between", "equals"], options: [] },
  ];
  return Object.fromEntries(fields.map((field) => [field.field, field.options]));
}

function oaPendingPaymentUnavailableDetailPayload() {
  return {
    title: "OA详情",
    subtitle: "oa-payment-e2e-001",
    detailAvailable: false,
    unavailableReason: "详情数据正在刷新，请稍后重试。",
    sections: [],
    read_model_status: "refreshing",
  };
}

function oaPendingPaymentDetailPayload(kind: "oa" | "bank" | "invoice") {
  if (kind === "oa") {
    return {
      title: "OA详情",
      subtitle: "oa-payment-e2e-001",
      detailAvailable: true,
      sections: [
        {
          title: "OA信息",
          fields: [
            { label: "申请人", value: "浏览器付款申请人" },
            { label: "项目名称", value: "浏览器待付款项目" },
            { label: "金额", value: "12000.00" },
          ],
        },
      ],
    };
  }
  if (kind === "bank") {
    return {
      title: "支出流水详情",
      subtitle: "bank-payment-e2e-001",
      detailAvailable: true,
      sections: [
        {
          title: "流水信息",
          fields: [
            { label: "支出银行", value: "建设银行" },
            { label: "对方户名", value: "浏览器待付款供应商" },
            { label: "流水金额", value: "8000.00" },
          ],
        },
      ],
    };
  }
  return {
    title: "发票详情",
    subtitle: "invoice-payment-e2e-001",
    detailAvailable: true,
    sections: [
      {
        title: "发票情况",
        fields: [
          { label: "发票号码", value: "INV-PAY-E2E-001" },
          { label: "进项发票方名称", value: "浏览器待付款供应商" },
          { label: "价税合计", value: "12000.00" },
        ],
      },
    ],
  };
}

function pendingInvoiceExpenseRulesPayload({
  canSave = false,
  readModelStatus = "fresh",
  version = 1,
}: {
  canSave?: boolean;
  readModelStatus?: "fresh" | "refreshing";
  version?: number;
} = {}) {
  return {
    version,
    direction: "expense",
    read_model_status: readModelStatus,
    available_tags: [
      {
        code: "equipment_payment",
        label: "设备款",
        path: ["成本", "设备款"],
        output_primary_label: "成本",
        output_sub_label: "设备款",
        status: "active",
        source: "system",
      },
      {
        code: "salary",
        label: "工资",
        path: ["费用", "工资"],
        output_primary_label: "费用",
        output_sub_label: "工资",
        status: "active",
        source: "system",
      },
    ],
    groups: {
      requires_invoice: { tag_codes: ["equipment_payment", "salary"], tags: [] },
      bank_statement_as_invoice: { tag_codes: [], tags: [] },
      no_invoice_required: { tag_codes: [], tags: [] },
    },
    permissions: { can_save: canSave },
  };
}

const completedCostProjectNames = new Set([
  "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
]);
const settingsCostProject = {
  id: "settings-cost-project-e2e",
  project_code: "SETTINGS-COST-E2E",
  project_name: "昆明卷烟厂动力设备控制系统升级改造项目",
  project_status: "active" as const,
  source: "manual" as const,
};

const costProjectRows: Record<string, Record<string, CostBrowserProjectRow[]>> = {
  "2026-03": {
    云南溯源科技: [
      {
        transaction_id: "cost-txn-e2e-001",
        trade_time: "2026-03-10 21:27:55",
        direction: "支出",
        expense_type: "设备货款及材料费",
        expense_content: "PLC 模块采购",
        amount: "10,000.00",
        counterparty_name: "浏览器设备供应商",
        payment_account_label: "工商银行 账户 0001",
      },
      {
        transaction_id: "cost-txn-e2e-002",
        trade_time: "2026-03-12 08:40:12",
        direction: "支出",
        expense_type: "设备货款及材料费",
        expense_content: "PLC 模块采购配件",
        amount: "2,500.00",
        counterparty_name: "浏览器设备供应商",
        payment_account_label: "工商银行 账户 0001",
      },
      {
        transaction_id: "cost-txn-e2e-003",
        trade_time: "2026-03-18 17:02:09",
        direction: "支出",
        expense_type: "交通费",
        expense_content: "项目现场往返交通",
        amount: "860.00",
        counterparty_name: "浏览器航空",
        payment_account_label: "招商银行 账户 2201",
      },
    ],
    "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目": [
      {
        transaction_id: "cost-txn-e2e-004",
        trade_time: "2026-03-20 15:11:02",
        direction: "支出",
        expense_type: "人工费/劳务费/服务费",
        expense_content: "现场调试服务",
        amount: "5,200.00",
        counterparty_name: "浏览器运维服务商",
        payment_account_label: "建设银行 账户 1388",
      },
    ],
  },
  "2026-04": {
    "昆明卷烟厂动力设备控制系统升级改造项目": [
      {
        transaction_id: "cost-txn-e2e-101",
        trade_time: "2026-04-02 09:15:08",
        direction: "支出",
        expense_type: "经营/办公费用",
        expense_content: "项目办公室租赁",
        amount: "4,800.00",
        counterparty_name: "浏览器办公室出租方",
        payment_account_label: "平安银行 账户 8821",
      },
    ],
  },
};

const largeCostStatisticsProjectName = "大型成本浏览器稳定性项目-超长项目名称用于验证窄屏滚动与换行不遮挡";
const largeCostStatisticsProjectRows: CostBrowserProjectRow[] = Array.from({ length: 120 }, (_, index) => {
  const rowNumber = index + 1;
  const day = String((index % 28) + 1).padStart(2, "0");
  const hour = String(index % 24).padStart(2, "0");
  const minute = String((index * 7) % 60).padStart(2, "0");
  return {
    transaction_id: `large-cost-txn-e2e-${String(rowNumber).padStart(3, "0")}`,
    trade_time: `2026-03-${day} ${hour}:${minute}:00`,
    direction: "支出",
    expense_type: `大型宽表费用类型-${(index % 4) + 1}`,
    expense_content: `大型成本流水费用内容 ${rowNumber}，用于验证长文本、窄屏、滚动、项目下钻和金额列稳定展示`,
    amount: (1000 + rowNumber * 17.35).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
    counterparty_name: `大型成本浏览器供应商${String(rowNumber).padStart(3, "0")}有限公司-超长对方户名`,
    payment_account_label: `招商银行 成本大数据测试账户 ${String(880000 + rowNumber)}`,
  };
});

const workbenchRelationCostProjectName = "智能工厂项目";
const workbenchRelationCostRow: CostBrowserProjectRow = {
  transaction_id: "bk-o-202603-001",
  trade_time: "2026-03-28 10:18",
  direction: "支出",
  expense_type: "设备货款及材料费",
  expense_content: "智能工厂设备尾款",
  amount: "58,000.00",
  counterparty_name: "智能工厂设备商",
  payment_account_label: "建设银行 1138",
};
const invoiceImportCostProjectName = "发票导入成本项目";
const invoiceImportCostRow: CostBrowserProjectRow = {
  transaction_id: "invoice-import-cost-e2e-001",
  trade_time: "2026-05-21 10:20",
  direction: "支出",
  expense_type: "设备货款及材料费",
  expense_content: "发票导入进项成本",
  amount: "18,320.00",
  counterparty_name: "发票导入进项供应商",
  payment_account_label: "建设银行 1138",
};
const etcImportCostProjectName = "ETC导入通行成本项目";
const etcImportCostRow: CostBrowserProjectRow = {
  transaction_id: "etc-import-cost-e2e-001",
  trade_time: "2026-03-27 09:10",
  direction: "支出",
  expense_type: "通行费",
  expense_content: "ETC高速通行费",
  amount: "32.26",
  counterparty_name: "ETC导入通行服务商",
  payment_account_label: "建设银行 1138",
};
const bankImportCostProjectName = "银行导入成本项目";
const bankImportCostRow: CostBrowserProjectRow = {
  transaction_id: "bank-import-cost-e2e-001",
  trade_time: "2026-03-25 14:22",
  direction: "支出",
  expense_type: "经营/办公费用",
  expense_content: "银行流水导入成本",
  amount: "1,688.00",
  counterparty_name: "导入浏览器测试客户",
  payment_account_label: "建设银行 8826",
};
const bankFlowRuleCostProjectName = "流水规则手续费成本项目";
const bankFlowRuleCostRow: CostBrowserProjectRow = {
  transaction_id: "bank-flow-rule-e2e-001",
  trade_time: "2026-05-03 10:20:00",
  direction: "支出",
  expense_type: "手续费",
  expense_content: "网银手续费",
  amount: "8.80",
  counterparty_name: "建设银行",
  payment_account_label: "建设银行 8106",
};
const turnoverCostProjectName = "外部往来闭环成本项目";
const turnoverCostRow: CostBrowserProjectRow = {
  transaction_id: turnoverBankRows.expense,
  trade_time: "2026-05-03 10:00:00",
  direction: "支出",
  expense_type: "外部往来款付款",
  expense_content: "浏览器 e2e 归还借款",
  amount: "1,000.00",
  counterparty_name: "建设银行",
  payment_account_label: "建行 8106",
};

function isCostProjectVisibleForScope(
  projectName: string,
  projectScope: string | null,
  completedProjectNames = completedCostProjectNames,
) {
  return projectScope === "all" || !completedProjectNames.has(projectName);
}

function sumCostAmounts(rows: Array<{ amount: string }>) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  return total.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function costProjectRowsForMonth(
  month: string,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
  includeLargeCostDataset = false,
) {
  const projectRowsForMonth = costProjectRows[month] ?? {};
  let result = projectRowsForMonth;
  if (month === "2026-03" && includeLargeCostDataset) {
    result = {
      ...result,
      [largeCostStatisticsProjectName]: [
        ...(result[largeCostStatisticsProjectName] ?? []),
        ...largeCostStatisticsProjectRows,
      ],
    };
  }
  if (month === "2026-03" && relationConfirmed && includeWorkbenchRelationEvidence) {
    result = {
      ...result,
      [workbenchRelationCostProjectName]: [
        ...(result[workbenchRelationCostProjectName] ?? []),
        workbenchRelationCostRow,
      ],
    };
  }
  if (month === "2026-05" && includeInvoiceImportEvidence) {
    result = {
      ...result,
      [invoiceImportCostProjectName]: [
        ...(result[invoiceImportCostProjectName] ?? []),
        invoiceImportCostRow,
      ],
    };
  }
  if (month === "2026-03" && includeEtcImportEvidence) {
    result = {
      ...result,
      [etcImportCostProjectName]: [
        ...(result[etcImportCostProjectName] ?? []),
        etcImportCostRow,
      ],
    };
  }
  if (month === "2026-03" && includeBankImportEvidence) {
    result = {
      ...result,
      [bankImportCostProjectName]: [
        ...(result[bankImportCostProjectName] ?? []),
        bankImportCostRow,
      ],
    };
  }
  if (month === "2026-05" && includeBankFlowRuleCostEvidence) {
    result = {
      ...result,
      [bankFlowRuleCostProjectName]: [
        ...(result[bankFlowRuleCostProjectName] ?? []),
        bankFlowRuleCostRow,
      ],
    };
  }
  if (month === "2026-05" && includeTurnoverCostEvidence) {
    result = {
      ...result,
      [turnoverCostProjectName]: [
        ...(result[turnoverCostProjectName] ?? []),
        turnoverCostRow,
      ],
    };
  }
  return result;
}

function allCostProjectRows(
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
  includeLargeCostDataset = false,
) {
  const months = new Set(Object.keys(costProjectRows));
  if (includeLargeCostDataset) {
    months.add("2026-03");
  }
  if (includeInvoiceImportEvidence) {
    months.add("2026-05");
  }
  if (includeEtcImportEvidence) {
    months.add("2026-03");
  }
  if (includeBankImportEvidence) {
    months.add("2026-03");
  }
  if (includeBankFlowRuleCostEvidence) {
    months.add("2026-05");
  }
  if (includeTurnoverCostEvidence) {
    months.add("2026-05");
  }
  const projectMaps = Array.from(months)
    .map((month) => costProjectRowsForMonth(
      month,
      relationConfirmed,
      includeWorkbenchRelationEvidence,
      includeInvoiceImportEvidence,
      includeEtcImportEvidence,
      includeBankImportEvidence,
      includeBankFlowRuleCostEvidence,
      includeTurnoverCostEvidence,
      includeLargeCostDataset,
    ));
  return projectMaps.reduce<Record<string, CostBrowserProjectRow[]>>((result, projectMap) => {
    for (const [projectName, rows] of Object.entries(projectMap)) {
      result[projectName] = [...(result[projectName] ?? []), ...rows];
    }
    return result;
  }, {});
}

function costTimeRows(
  month: string,
  projectScope: string | null,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
  completedProjectNames = completedCostProjectNames,
  includeLargeCostDataset = false,
) {
  const sourceProjectRowMap = month === "all"
    ? allCostProjectRows(relationConfirmed, includeWorkbenchRelationEvidence, includeInvoiceImportEvidence, includeEtcImportEvidence, includeBankImportEvidence, includeBankFlowRuleCostEvidence, includeTurnoverCostEvidence, includeLargeCostDataset)
    : costProjectRowsForMonth(month, relationConfirmed, includeWorkbenchRelationEvidence, includeInvoiceImportEvidence, includeEtcImportEvidence, includeBankImportEvidence, includeBankFlowRuleCostEvidence, includeTurnoverCostEvidence, includeLargeCostDataset);
  return Object.entries(sourceProjectRowMap)
    .filter(([projectName]) => isCostProjectVisibleForScope(projectName, projectScope, completedProjectNames))
    .flatMap(([projectName, rows]) =>
      rows.map((row) => ({
        transaction_id: row.transaction_id,
        trade_time: row.trade_time,
        direction: row.direction,
        project_name: projectName,
        expense_type: row.expense_type,
        expense_content: row.expense_content,
        amount: row.amount,
        counterparty_name: row.counterparty_name,
        payment_account_label: row.payment_account_label,
        remark: "浏览器成本统计明细",
      })),
    )
    .sort((left, right) => right.trade_time.localeCompare(left.trade_time));
}

function costBankFlowRows(
  month: string,
  projectScope: string | null,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
  completedProjectNames = completedCostProjectNames,
  includeLargeCostDataset = false,
) {
  const expenseRows = costTimeRows(
    month,
    projectScope,
    relationConfirmed,
    includeWorkbenchRelationEvidence,
    includeInvoiceImportEvidence,
    includeEtcImportEvidence,
    includeBankImportEvidence,
    includeBankFlowRuleCostEvidence,
    includeTurnoverCostEvidence,
    completedProjectNames,
    includeLargeCostDataset,
  ).map((row) => ({
    ...row,
    bank_tag_code: "expense_material",
    bank_tag_label: "支出 / 材料采购",
    bank_tag_primary_label: "支出",
    bank_tag_sub_label: "材料采购",
    bank_tag_label_path: ["支出", "材料采购"],
  }));
  const incomeRows = [
    {
      transaction_id: "cost-income-e2e-001",
      trade_time: "2026-03-18 10:08:00",
      direction: "收入",
      project_name: "未配对OA",
      expense_type: "银行流水",
      expense_content: "浏览器客户回款",
      amount: "8,888.00",
      counterparty_name: "浏览器回款客户",
      payment_account_label: "工商银行 账户 0001",
      remark: "浏览器收入流水",
      bank_tag_code: "income_collection",
      bank_tag_label: "收入 / 客户回款",
      bank_tag_primary_label: "收入",
      bank_tag_sub_label: "客户回款",
      bank_tag_label_path: ["收入", "客户回款"],
    },
    {
      transaction_id: "cost-income-e2e-101",
      trade_time: "2026-04-18 10:08:00",
      direction: "收入",
      project_name: "未配对OA",
      expense_type: "银行流水",
      expense_content: "浏览器四月客户回款",
      amount: "6,666.00",
      counterparty_name: "浏览器回款客户",
      payment_account_label: "工商银行 账户 0001",
      remark: "浏览器收入流水",
      bank_tag_code: "income_collection",
      bank_tag_label: "收入 / 客户回款",
      bank_tag_primary_label: "收入",
      bank_tag_sub_label: "客户回款",
      bank_tag_label_path: ["收入", "客户回款"],
    },
  ].filter((row) => month === "all" || row.trade_time.startsWith(month));
  return [...expenseRows, ...incomeRows]
    .sort((left, right) => right.trade_time.localeCompare(left.trade_time));
}

function costStatisticsExplorerPayload(
  month: string,
  projectScope: string | null,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
  readModelStatus: CostStatisticsReadModelMockStatus = "fresh",
  completedProjectNames = completedCostProjectNames,
  includeLargeCostDataset = false,
) {
  const timeRows = costTimeRows(
    month,
    projectScope,
    relationConfirmed,
    includeWorkbenchRelationEvidence,
    includeInvoiceImportEvidence,
    includeEtcImportEvidence,
    includeBankImportEvidence,
    includeBankFlowRuleCostEvidence,
    includeTurnoverCostEvidence,
    completedProjectNames,
    includeLargeCostDataset,
  );
  const bankFlowTimeRows = costBankFlowRows(
    month,
    projectScope,
    relationConfirmed,
    includeWorkbenchRelationEvidence,
    includeInvoiceImportEvidence,
    includeEtcImportEvidence,
    includeBankImportEvidence,
    includeBankFlowRuleCostEvidence,
    includeTurnoverCostEvidence,
    completedProjectNames,
    includeLargeCostDataset,
  );
  const expenseBankRows = bankFlowTimeRows.filter((row) => row.direction === "支出");
  const incomeBankRows = bankFlowTimeRows.filter((row) => row.direction === "收入");
  const projectGroups = new Map<string, { amount: number; transactionCount: number; expenseTypes: Set<string> }>();
  const expenseTypeGroups = new Map<string, { amount: number; transactionCount: number; projects: Set<string> }>();

  for (const row of timeRows) {
    const project = projectGroups.get(row.project_name) ?? { amount: 0, transactionCount: 0, expenseTypes: new Set<string>() };
    project.amount += Number(row.amount.replace(/,/g, ""));
    project.transactionCount += 1;
    project.expenseTypes.add(row.expense_type);
    projectGroups.set(row.project_name, project);

    const expenseType = expenseTypeGroups.get(row.expense_type) ?? { amount: 0, transactionCount: 0, projects: new Set<string>() };
    expenseType.amount += Number(row.amount.replace(/,/g, ""));
    expenseType.transactionCount += 1;
    expenseType.projects.add(row.project_name);
    expenseTypeGroups.set(row.expense_type, expenseType);
  }

  return {
    month,
    summary: {
      row_count: timeRows.length,
      transaction_count: timeRows.length,
      total_amount: sumCostAmounts(timeRows),
    },
    time_rows: timeRows,
    bank_flow_summary: {
      row_count: bankFlowTimeRows.length,
      transaction_count: bankFlowTimeRows.length,
      total_amount: sumCostAmounts(bankFlowTimeRows),
      expense_amount: sumCostAmounts(expenseBankRows),
      income_amount: sumCostAmounts(incomeBankRows),
      expense_transaction_count: expenseBankRows.length,
      income_transaction_count: incomeBankRows.length,
    },
    bank_flow_time_rows: bankFlowTimeRows,
    bank_accounts: [
      {
        bank_name: "工商银行",
        account_last4: "0001",
        payment_account_label: "工商银行 账户 0001",
        source: "settings",
      },
      {
        bank_name: "平安银行",
        account_last4: "8821",
        payment_account_label: "平安银行 账户 8821",
        source: "settings",
      },
      {
        bank_name: "民生银行",
        account_last4: "9486",
        payment_account_label: "民生银行 账户 9486",
        source: "settings",
      },
    ],
    project_rows: Array.from(projectGroups.entries()).map(([projectName, bucket]) => ({
      project_name: projectName,
      total_amount: bucket.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      transaction_count: bucket.transactionCount,
      expense_type_count: bucket.expenseTypes.size,
    })),
    expense_type_rows: Array.from(expenseTypeGroups.entries()).map(([expenseType, bucket]) => ({
      expense_type: expenseType,
      total_amount: bucket.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      transaction_count: bucket.transactionCount,
      project_count: bucket.projects.size,
    })),
    read_model_status: readModelStatus,
    read_model_scope_key: `${projectScope ?? "active"}:${month}`,
    read_model_generated_at: "2026-06-17T09:30:00+08:00",
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : [`cost_statistics_${readModelStatus}`],
  };
}

function costStatisticsExplorerPagePayload(
  url: URL,
  payload: ReturnType<typeof costStatisticsExplorerPayload>,
  readModelStatus: CostStatisticsReadModelMockStatus,
) {
  const scope = url.searchParams.get("scope") ?? "all";
  const view = url.searchParams.get("view") ?? "time";
  const pageSize = Math.max(1, Math.min(100, Number(url.searchParams.get("page_size") ?? 50) || 50));
  const cursorOffset = Number((url.searchParams.get("cursor") ?? "").replace(/^mock:/, "")) || 0;
  const projectName = url.searchParams.get("project_name") ?? "";
  const expenseType = url.searchParams.get("expense_type") ?? "";
  const paymentAccountLabel = url.searchParams.get("payment_account_label") ?? "";
  const primaryLabel = url.searchParams.get("bank_tag_primary_label") ?? "";
  const subLabel = url.searchParams.get("bank_tag_sub_label") ?? "";
  const inScope = <Row extends { trade_time: string }>(rows: Row[]) => rows.filter((row) => (
    scope === "all"
    || (scope.startsWith("year:") ? row.trade_time.startsWith(`${scope.slice(5)}-`) : row.trade_time.startsWith(scope))
  ));
  const costRows = inScope(payload.time_rows);
  const bankFlowRows = inScope(payload.bank_flow_time_rows);
  const amount = (value: string) => Number(value.replace(/,/g, "")) || 0;
  const formatAmount = (value: number) => value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const percentage = (value: number, total: number) => `${((value / (total || 1)) * 100).toFixed(1)}%`;

  const projectGroups = new Map<string, { rows: typeof costRows; total: number; expenseTypes: Set<string> }>();
  const expenseGroups = new Map<string, { rows: typeof costRows; total: number; projects: Set<string> }>();
  const bankGroups = new Map<string, { rows: typeof costRows; total: number; projects: Set<string> }>();
  for (const row of costRows) {
    const project = projectGroups.get(row.project_name) ?? { rows: [], total: 0, expenseTypes: new Set<string>() };
    project.rows.push(row);
    project.total += amount(row.amount);
    project.expenseTypes.add(row.expense_type);
    projectGroups.set(row.project_name, project);
    const expense = expenseGroups.get(row.expense_type) ?? { rows: [], total: 0, projects: new Set<string>() };
    expense.rows.push(row);
    expense.total += amount(row.amount);
    expense.projects.add(row.project_name);
    expenseGroups.set(row.expense_type, expense);
    const account = bankGroups.get(row.payment_account_label) ?? { rows: [], total: 0, projects: new Set<string>() };
    account.rows.push(row);
    account.total += amount(row.amount);
    account.projects.add(row.project_name);
    bankGroups.set(row.payment_account_label, account);
  }
  for (const account of payload.bank_accounts) {
    if (!bankGroups.has(account.payment_account_label)) {
      bankGroups.set(account.payment_account_label, { rows: [], total: 0, projects: new Set<string>() });
    }
  }
  const total = costRows.reduce((sum, row) => sum + amount(row.amount), 0);
  const projects = Array.from(projectGroups.entries()).map(([name, group]) => ({
    project_name: name,
    total_amount: formatAmount(group.total),
    transaction_count: group.rows.length,
    expense_type_count: group.expenseTypes.size,
    percentage_label: percentage(group.total, total),
  })).sort((left, right) => amount(right.total_amount) - amount(left.total_amount));
  const expenseTypes = Array.from(expenseGroups.entries()).map(([name, group]) => ({
    expense_type: name,
    total_amount: formatAmount(group.total),
    transaction_count: group.rows.length,
    project_count: group.projects.size,
    percentage_label: percentage(group.total, total),
  })).sort((left, right) => amount(right.total_amount) - amount(left.total_amount));
  const bankAccounts = Array.from(bankGroups.entries()).map(([label, group]) => ({
    payment_account_label: label,
    total_amount: formatAmount(group.total),
    transaction_count: group.rows.length,
    project_count: group.projects.size,
    percentage_label: percentage(group.total, total),
  })).sort((left, right) => amount(right.total_amount) - amount(left.total_amount));

  const selectedProjectRows = projectGroups.get(projectName)?.rows ?? [];
  const selectedProjectTotal = selectedProjectRows.reduce((sum, row) => sum + amount(row.amount), 0);
  const projectExpenseTypes = Array.from(new Set(selectedProjectRows.map((row) => row.expense_type))).map((name) => {
    const rows = selectedProjectRows.filter((row) => row.expense_type === name);
    const rowTotal = rows.reduce((sum, row) => sum + amount(row.amount), 0);
    return {
      expense_type: name,
      total_amount: formatAmount(rowTotal),
      transaction_count: rows.length,
      project_count: 1,
      percentage_label: percentage(rowTotal, selectedProjectTotal),
    };
  }).sort((left, right) => amount(right.total_amount) - amount(left.total_amount));
  const selectedBankRows = bankGroups.get(paymentAccountLabel)?.rows ?? [];
  const selectedBankTotal = selectedBankRows.reduce((sum, row) => sum + amount(row.amount), 0);
  const bankProjects = Array.from(new Set(selectedBankRows.map((row) => row.project_name))).map((name) => {
    const rows = selectedBankRows.filter((row) => row.project_name === name);
    const rowTotal = rows.reduce((sum, row) => sum + amount(row.amount), 0);
    return {
      project_name: name,
      total_amount: formatAmount(rowTotal),
      transaction_count: rows.length,
      expense_type_count: new Set(rows.map((row) => row.expense_type)).size,
      percentage_label: percentage(rowTotal, selectedBankTotal),
    };
  }).sort((left, right) => amount(right.total_amount) - amount(left.total_amount));

  const directionFacet = (rows: typeof bankFlowRows) => ({
    expense_amount: sumCostAmounts(rows.filter((row) => row.direction === "支出")),
    income_amount: sumCostAmounts(rows.filter((row) => row.direction === "收入")),
    expense_transaction_count: rows.filter((row) => row.direction === "支出").length,
    income_transaction_count: rows.filter((row) => row.direction === "收入").length,
  });
  const tagGroups = new Map<string, typeof bankFlowRows>();
  for (const row of bankFlowRows) {
    const label = row.bank_tag_primary_label || row.bank_tag_label || "未标记";
    tagGroups.set(label, [...(tagGroups.get(label) ?? []), row]);
  }
  const bankTagPrimary = Array.from(tagGroups.entries()).map(([label, rows]) => ({
    primary_label: label,
    ...directionFacet(rows),
    sub_tag_count: new Set(rows.map((row) => row.bank_tag_sub_label || row.bank_tag_label || label)).size,
  }));
  const primaryRows = tagGroups.get(primaryLabel) ?? [];
  const bankTagSub = Array.from(new Set(primaryRows.map((row) => row.bank_tag_sub_label || row.bank_tag_label || primaryLabel)))
    .map((label) => ({
      primary_label: primaryLabel,
      sub_label: label,
      ...directionFacet(primaryRows.filter((row) => (row.bank_tag_sub_label || row.bank_tag_label || primaryLabel) === label)),
    }));

  let matchedRows = view === "time" ? bankFlowRows : [];
  if (view === "project" && projectName && expenseType) {
    matchedRows = costRows.filter((row) => row.project_name === projectName && row.expense_type === expenseType);
  } else if (view === "bank" && paymentAccountLabel && projectName) {
    matchedRows = costRows.filter((row) => row.payment_account_label === paymentAccountLabel && row.project_name === projectName);
  } else if (view === "expense_type" && expenseType) {
    matchedRows = costRows.filter((row) => row.expense_type === expenseType);
  } else if (view === "bank_tag" && primaryLabel && subLabel) {
    matchedRows = bankFlowRows.filter((row) => (
      (row.bank_tag_primary_label || row.bank_tag_label || "未标记") === primaryLabel
      && (row.bank_tag_sub_label || row.bank_tag_label || primaryLabel) === subLabel
    ));
  }
  const summaryRows = view === "time" || view === "bank_tag" ? bankFlowRows : costRows;
  const expenseRows = summaryRows.filter((row) => row.direction === "支出");
  const incomeRows = summaryRows.filter((row) => row.direction === "收入");
  const rows = readModelStatus === "fresh" ? matchedRows.slice(cursorOffset, cursorOffset + pageSize) : [];
  const nextOffset = cursorOffset + rows.length;
  return {
    scope,
    view,
    summary: {
      row_count: summaryRows.length,
      transaction_count: summaryRows.length,
      total_amount: sumCostAmounts(summaryRows),
      expense_amount: sumCostAmounts(expenseRows),
      income_amount: sumCostAmounts(incomeRows),
      expense_transaction_count: expenseRows.length,
      income_transaction_count: incomeRows.length,
    },
    available_years: Array.from(new Set([...payload.time_rows, ...payload.bank_flow_time_rows]
      .map((row) => row.trade_time.slice(0, 4)))).sort().reverse(),
    facets: readModelStatus === "fresh" ? {
      projects: view === "project" ? projects : view === "bank" && paymentAccountLabel ? bankProjects : [],
      expense_types: view === "expense_type" ? expenseTypes : view === "project" && projectName ? projectExpenseTypes : [],
      bank_accounts: view === "bank" ? bankAccounts : [],
      bank_tag_primary: view === "bank_tag" ? bankTagPrimary : [],
      bank_tag_sub: view === "bank_tag" ? bankTagSub : [],
    } : { projects: [], expense_types: [], bank_accounts: [], bank_tag_primary: [], bank_tag_sub: [] },
    rows,
    row_count: readModelStatus === "fresh" ? matchedRows.length : 0,
    next_cursor: readModelStatus === "fresh" && nextOffset < matchedRows.length ? `mock:${nextOffset}` : null,
    read_model_status: readModelStatus,
    read_model_scope_key: `${url.searchParams.get("project_scope") ?? "active"}:${scope.startsWith("year:") ? "all" : scope}`,
    read_model_generated_at: payload.read_model_generated_at,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : [`cost_statistics_${readModelStatus}`],
  };
}

function costTransactionPayload(
  transactionId: string,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
) {
  const row = costBankFlowRows("all", "all", relationConfirmed, includeWorkbenchRelationEvidence, includeInvoiceImportEvidence, includeEtcImportEvidence, includeBankImportEvidence, includeBankFlowRuleCostEvidence, includeTurnoverCostEvidence)
    .find((item) => item.transaction_id === transactionId);
  return {
    month: transactionId.includes("101") ? "2026-04" : "2026-03",
    transaction: {
      id: transactionId,
      project_name: row?.project_name ?? "云南溯源科技",
      expense_type: row?.expense_type ?? "设备货款及材料费",
      expense_content: row?.expense_content ?? "PLC 模块采购",
      trade_time: row?.trade_time ?? "2026-03-10 21:27:55",
      direction: row?.direction ?? "支出",
      amount: row?.amount ?? "10,000.00",
      counterparty_name: row?.counterparty_name ?? "浏览器设备供应商",
      payment_account_label: row?.payment_account_label ?? "工商银行 账户 0001",
      oa_applicant: "浏览器成本申请人",
      remark: "浏览器成本统计明细",
      summary_fields: {
        资金方向: row?.direction ?? "支出",
        交易时间: row?.trade_time ?? "2026-03-10 21:27:55",
        对方户名: row?.counterparty_name ?? "浏览器设备供应商",
      },
      detail_fields: {
        账号: "62220001",
        账户名称: "云南溯源科技有限公司",
        摘要: row?.expense_content ?? "PLC 模块采购",
        备注: "浏览器成本统计明细",
        费用类型: row?.expense_type ?? "设备货款及材料费",
        费用内容: row?.expense_content ?? "PLC 模块采购",
      },
    },
  };
}

function costStatisticsExportPreviewPayload(
  url: URL,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
) {
  const month = url.searchParams.get("month") ?? "all";
  const view = url.searchParams.get("view") ?? "time";
  const projectScope = url.searchParams.get("project_scope") ?? "active";
  const projectNames = new Set(url.searchParams.getAll("project_name").filter(Boolean));
  const expenseTypes = new Set(url.searchParams.getAll("expense_type").filter(Boolean));
  const isBankFlowView = view === "time" || view === "bank_tag";
  const rows = (isBankFlowView
    ? costBankFlowRows(month, projectScope, relationConfirmed, includeWorkbenchRelationEvidence, includeInvoiceImportEvidence, includeEtcImportEvidence, includeBankImportEvidence, includeBankFlowRuleCostEvidence, includeTurnoverCostEvidence)
    : costTimeRows(month, projectScope, relationConfirmed, includeWorkbenchRelationEvidence, includeInvoiceImportEvidence, includeEtcImportEvidence, includeBankImportEvidence, includeBankFlowRuleCostEvidence, includeTurnoverCostEvidence))
    .filter((row) => (projectNames.size > 0 ? projectNames.has(row.project_name) : true))
    .filter((row) => (expenseTypes.size > 0 ? expenseTypes.has(row.expense_type) : true));
  const fileName = view === "project"
    ? "成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx"
    : view === "bank_tag"
      ? "成本统计_全部期间_按标签统计.xlsx"
    : "成本统计_全部期间_按时间统计.xlsx";
  const expenseRows = rows.filter((row) => row.direction === "支出");
  const incomeRows = rows.filter((row) => row.direction === "收入");
  const bankTagColumns = ["时间", "主标签", "子标签", "资金方向", "金额", "费用内容", "对方户名", "支付账户"];
  const timeColumns = ["时间", "项目名称", "费用类型", "金额", "费用内容", "资金方向", "对方户名", "支付账户"];
  return {
    view,
    file_name: fileName,
    scope_label: month === "all" ? "全部期间" : month,
    summary: {
      row_count: rows.length,
      transaction_count: rows.length,
      total_amount: sumCostAmounts(rows),
      expense_amount: sumCostAmounts(expenseRows),
      income_amount: sumCostAmounts(incomeRows),
      expense_transaction_count: expenseRows.length,
      income_transaction_count: incomeRows.length,
      sheet_count: view === "project" ? 8 : 1,
    },
    sheet_names: view === "project" ? ["导出说明", "项目汇总", "流水明细"] : [view === "bank_tag" ? "按标签统计" : "按时间统计"],
    columns: view === "bank_tag" ? bankTagColumns : timeColumns,
    rows: rows.map((row) => view === "bank_tag"
      ? [
          row.trade_time,
          "bank_tag_primary_label" in row ? row.bank_tag_primary_label : "未分类",
          "bank_tag_sub_label" in row ? row.bank_tag_sub_label : "未分类",
          row.direction,
          row.amount,
          row.expense_content,
          row.counterparty_name,
          row.payment_account_label,
        ]
      : [row.trade_time, row.project_name, row.expense_type, row.amount, row.expense_content, row.direction, row.counterparty_name, row.payment_account_label]),
  };
}

function costStatisticsExportBody(
  url: URL,
  relationConfirmed = false,
  includeWorkbenchRelationEvidence = false,
  includeInvoiceImportEvidence = false,
  includeEtcImportEvidence = false,
  includeBankImportEvidence = false,
  includeBankFlowRuleCostEvidence = false,
  includeTurnoverCostEvidence = false,
) {
  const month = url.searchParams.get("month") ?? "all";
  const projectScope = url.searchParams.get("project_scope") ?? "active";
  const projectNames = new Set(url.searchParams.getAll("project_name").filter(Boolean));
  const expenseTypes = new Set(url.searchParams.getAll("expense_type").filter(Boolean));
  const view = url.searchParams.get("view") ?? "time";
  const exportRows = (view === "time" || view === "bank_tag" ? costBankFlowRows : costTimeRows)(
    month,
    projectScope,
    relationConfirmed,
    includeWorkbenchRelationEvidence,
    includeInvoiceImportEvidence,
    includeEtcImportEvidence,
    includeBankImportEvidence,
    includeBankFlowRuleCostEvidence,
    includeTurnoverCostEvidence,
  )
    .filter((row) => (projectNames.size > 0 ? projectNames.has(row.project_name) : true))
    .filter((row) => (expenseTypes.size > 0 ? expenseTypes.has(row.expense_type) : true));
  const preview = costStatisticsExportPreviewPayload(
    url,
    relationConfirmed,
    includeWorkbenchRelationEvidence,
    includeInvoiceImportEvidence,
    includeEtcImportEvidence,
    includeBankImportEvidence,
    includeBankFlowRuleCostEvidence,
    includeTurnoverCostEvidence,
  );
  return [
    preview.file_name,
    ["流水ID", ...preview.columns].join(","),
    ...exportRows.map((row) => [
      row.transaction_id,
      ...(view === "bank_tag"
        ? [
            row.trade_time,
            "bank_tag_primary_label" in row ? row.bank_tag_primary_label : "未分类",
            "bank_tag_sub_label" in row ? row.bank_tag_sub_label : "未分类",
            row.direction,
            row.amount,
            row.expense_content,
            row.counterparty_name,
            row.payment_account_label,
          ]
        : [row.trade_time, row.project_name, row.expense_type, row.amount, row.expense_content, row.direction, row.counterparty_name, row.payment_account_label]),
    ].join(",")),
    [
      "导出筛选",
      `view=${url.searchParams.get("view") ?? ""}`,
      `month=${url.searchParams.get("month") ?? ""}`,
      `project_scope=${url.searchParams.get("project_scope") ?? ""}`,
      `project_name=${url.searchParams.getAll("project_name").join("|")}`,
      `expense_type=${url.searchParams.getAll("expense_type").join("|")}`,
      `page=${url.searchParams.get("page") ?? ""}`,
      `page_size=${url.searchParams.get("page_size") ?? ""}`,
    ].join(","),
  ].join("\n");
}

function bankFlowRuleBatchVersion(status: BankFlowRuleBrowserBatchStatus) {
  if (status === "draft") {
    return 1;
  }
  if (status === "submitted") {
    return 2;
  }
  return 3;
}

function bankFlowRuleBatch(status: BankFlowRuleBrowserBatchStatus, overrides: Record<string, unknown> = {}) {
  return {
    batch_id: "bank-flow-rule-batch-e2e-001",
    batch_type: "fee",
    batch_label: "手续费",
    category_primary_label: "费用",
    category_sub_label: "手续费",
    category_label_path: ["费用", "手续费"],
    scope_month: "2026-05",
    account_key: "ccb:8106",
    bank_name: "建设银行",
    account_last4: "8106",
    status,
    status_bucket: status === "draft" ? "unsubmitted" : status,
    row_count: 1,
    total_amount: "8.80",
    tag_counts: { fee: 1 },
    direction_counts: { expense: 1 },
    can_submit: status === "draft",
    can_withdraw: status === "submitted",
    submitted_by: status === "submitted" || status === "withdrawn" ? "browser-e2e" : "",
    submitted_at: status === "submitted" || status === "withdrawn" ? "2026-06-17T09:30:00+08:00" : null,
    withdrawn_by: status === "withdrawn" ? "browser-e2e" : "",
    withdrawn_at: status === "withdrawn" ? "2026-06-17T09:40:00+08:00" : null,
    conflict_reason: "",
    blocked_reason: "",
    version: bankFlowRuleBatchVersion(status),
    ...overrides,
  };
}

const bankFlowRuleOrdinaryDraftMatrixDefinitions = [
  { batchType: "fee", batchLabel: "手续费", primaryLabel: "费用", subLabel: "手续费", bankName: "建设银行", accountLast4: "8106", amount: "1.00" },
  { batchType: "salary", batchLabel: "工资", primaryLabel: "薪资社保福利", subLabel: "工资", bankName: "工商银行", accountLast4: "6386", amount: "2.00" },
  { batchType: "holiday_bonus", batchLabel: "过节费", primaryLabel: "薪资社保福利", subLabel: "过节费", bankName: "中国银行", accountLast4: "7001", amount: "3.00" },
  { batchType: "bonus", batchLabel: "奖金", primaryLabel: "薪资社保福利", subLabel: "奖金", bankName: "招商银行", accountLast4: "9988", amount: "4.00" },
  { batchType: "tax_payment", batchLabel: "税款", primaryLabel: "税款", subLabel: "税款", bankName: "农业银行", accountLast4: "2211", amount: "5.00" },
  { batchType: "treasury_tax_collection", batchLabel: "国库税款", primaryLabel: "税款", subLabel: "国库税款", bankName: "交通银行", accountLast4: "3344", amount: "6.00" },
  { batchType: "social_security", batchLabel: "社保", primaryLabel: "薪资社保福利", subLabel: "社保", bankName: "民生银行", accountLast4: "5566", amount: "7.00" },
];

function bankFlowRuleOrdinaryDraftMatrixBatches() {
  return bankFlowRuleOrdinaryDraftMatrixDefinitions.map((definition) => bankFlowRuleBatch("draft", {
    batch_id: `bank-flow-rule-batch-e2e-${definition.batchType}`,
    batch_type: definition.batchType,
    batch_label: definition.batchLabel,
    category_primary_label: definition.primaryLabel,
    category_sub_label: definition.subLabel,
    category_label_path: [definition.primaryLabel, definition.subLabel],
    account_key: `${definition.bankName}:${definition.accountLast4}`,
    bank_name: definition.bankName,
    account_last4: definition.accountLast4,
    total_amount: definition.amount,
    tag_counts: { [definition.batchType]: 1 },
    direction_counts: { expense: 1 },
  }));
}

function bankFlowRuleInternalTransferPairBatches(status: BankFlowRuleBrowserBatchStatus) {
  return [
    bankFlowRuleBatch(status, {
      batch_id: "bank-flow-internal-ceb-8826",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      category_primary_label: "内部往来款",
      category_sub_label: "",
      category_label_path: ["内部往来款"],
      scope_month: "2026-01",
      account_key: "ceb:8826",
      bank_name: "光大银行",
      account_last4: "8826",
      row_count: 2,
      total_amount: "50000.00",
      tag_counts: { internal_transfer: 2 },
      direction_counts: { income: 1, expense: 1 },
    }),
    bankFlowRuleBatch(status, {
      batch_id: "bank-flow-internal-ccb-8106",
      batch_type: "internal_transfer",
      batch_label: "内部往来款",
      category_primary_label: "内部往来款",
      category_sub_label: "",
      category_label_path: ["内部往来款"],
      scope_month: "2026-01",
      account_key: "ccb:8106",
      bank_name: "建设银行",
      account_last4: "8106",
      row_count: 2,
      total_amount: "7000.00",
      tag_counts: { internal_transfer: 2 },
      direction_counts: { income: 1, expense: 1 },
    }),
  ];
}

function bankFlowRuleBatchesForScenario(status: BankFlowRuleBrowserBatchStatus, scenario: BankFlowRuleBatchMockScenario = "single") {
  if (scenario === "ordinaryDraftMatrix" && status === "draft") {
    return bankFlowRuleOrdinaryDraftMatrixBatches();
  }
  if (scenario === "internalTransferPairs") {
    return bankFlowRuleInternalTransferPairBatches(status);
  }
  return [bankFlowRuleBatch(status)];
}

function bankFlowRuleMoneyTotal(batches: Array<Record<string, unknown>>) {
  const total = batches.reduce((sum, batch) => {
    const amount = Number(batch.total_amount ?? 0);
    return Number.isFinite(amount) ? sum + amount : sum;
  }, 0);
  return total.toFixed(2);
}

function bankFlowRuleBatchSummary(status: BankFlowRuleBrowserBatchStatus, batches = bankFlowRuleBatchesForScenario(status)) {
  const draft = batches.filter((batch) => batch.status_bucket === "unsubmitted" && batch.status === "draft").length;
  const submitted = batches.filter((batch) => batch.status_bucket === "submitted").length;
  const withdrawn = batches.filter((batch) => batch.status_bucket === "withdrawn").length;
  const stale = batches.filter((batch) => batch.status === "stale").length;
  const categoriesByCode = new Map<string, {
    code: string;
    label: string;
    primary_label: string;
    sub_label: string;
    total: number;
    draft: number;
    submitted: number;
    withdrawn: number;
    conflict: number;
    stale: number;
    total_row_count: number;
    draft_row_count: number;
    submitted_row_count: number;
    withdrawn_row_count: number;
    total_amount: string;
  }>();
  for (const batch of batches) {
    const code = String(batch.batch_type ?? "");
    const current = categoriesByCode.get(code) ?? {
      code,
      label: String(batch.batch_label ?? ""),
      primary_label: String(batch.category_primary_label ?? ""),
      sub_label: String(batch.category_sub_label ?? ""),
      total: 0,
      draft: 0,
      submitted: 0,
      withdrawn: 0,
      conflict: 0,
      stale: 0,
      total_row_count: 0,
      draft_row_count: 0,
      submitted_row_count: 0,
      withdrawn_row_count: 0,
      total_amount: "0.00",
    };
    const batchRowCount = Number(batch.row_count ?? 0);
    current.total += 1;
    current.total_row_count += batchRowCount;
    if (batch.status_bucket === "unsubmitted" && batch.status === "draft") {
      current.draft += 1;
      current.draft_row_count += batchRowCount;
    }
    if (batch.status_bucket === "submitted") {
      current.submitted += 1;
      current.submitted_row_count += batchRowCount;
    }
    if (batch.status_bucket === "withdrawn") {
      current.withdrawn += 1;
      current.withdrawn_row_count += batchRowCount;
    }
    if (batch.status === "conflict") {
      current.conflict += 1;
    }
    if (batch.status === "stale") {
      current.stale += 1;
    }
    current.total_amount = bankFlowRuleMoneyTotal([{
      total_amount: current.total_amount,
    }, batch]);
    categoriesByCode.set(code, current);
  }
  return {
    draft_count: draft,
    submitted_count: submitted,
    withdrawn_count: withdrawn,
    conflict_count: 0,
    stale_count: stale,
    total_row_count: batches.reduce((sum, batch) => sum + Number(batch.row_count ?? 0), 0),
    draft_row_count: batches
      .filter((batch) => batch.status_bucket === "unsubmitted" && batch.status === "draft")
      .reduce((sum, batch) => sum + Number(batch.row_count ?? 0), 0),
    submitted_row_count: batches
      .filter((batch) => batch.status_bucket === "submitted")
      .reduce((sum, batch) => sum + Number(batch.row_count ?? 0), 0),
    withdrawn_row_count: batches
      .filter((batch) => batch.status_bucket === "withdrawn")
      .reduce((sum, batch) => sum + Number(batch.row_count ?? 0), 0),
    total_amount: bankFlowRuleMoneyTotal(batches),
    categories: Array.from(categoriesByCode.values()),
  };
}

function bankFlowRuleBatchesPayload(
  status: BankFlowRuleBrowserBatchStatus,
  bucket: string | null,
  readModelStatus: BankFlowRuleBatchReadModelMockStatus = "fresh",
  scenario: BankFlowRuleBatchMockScenario = "single",
) {
  const batches = bankFlowRuleBatchesForScenario(status, scenario);
  const visibleBatches = batches.filter((batch) => {
    if (bucket === "submitted") {
      return batch.status_bucket === "submitted";
    }
    if (bucket === "withdrawn") {
      return batch.status_bucket === "withdrawn";
    }
    return bucket === null || bucket === "unsubmitted"
      ? batch.status_bucket === "unsubmitted"
      : true;
  });
  return {
    summary: bankFlowRuleBatchSummary(status, batches),
    batches: visibleBatches,
    pagination: {
      page: 1,
      page_size: 200,
      total: visibleBatches.length,
    },
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : [`bank_flow_rule_batch_${readModelStatus}`],
  };
}

function bankFlowRuleBatchDetailPayload(
  status: BankFlowRuleBrowserBatchStatus,
  batchId = "bank-flow-rule-batch-e2e-001",
  scenario: BankFlowRuleBatchMockScenario = "single",
) {
  const batch = bankFlowRuleBatchesForScenario(status, scenario)
    .find((candidate) => candidate.batch_id === batchId)
    ?? bankFlowRuleBatch(status);
  if (scenario === "internalTransferPairs") {
    return bankFlowRuleInternalTransferDetailPayload(batch, status);
  }
  const transactionId = String(batch.batch_id ?? "bank-flow-rule-batch-e2e-001")
    .replace("bank-flow-rule-batch", "bank-flow-rule");
  const isDefaultFee = batch.batch_id === "bank-flow-rule-batch-e2e-001";
  return {
    batch,
    tag_counts: { fee: 1 },
    direction_counts: { expense: 1 },
    rows: [
      {
        transaction_id: transactionId,
        trade_time: "2026-05-03 10:20:00",
        counterparty_name: String(batch.bank_name ?? "未知对手方"),
        direction: "expense",
        direction_label: "支",
        amount: String(batch.total_amount ?? "0.00"),
        bank_name: String(batch.bank_name ?? ""),
        account_last4: String(batch.account_last4 ?? ""),
        account_key: String(batch.account_key ?? ""),
        summary: isDefaultFee ? "网银手续费" : `${String(batch.batch_label ?? "")}测试流水`,
        purpose: "结算",
        remark: isDefaultFee ? "浏览器 e2e 月结手续费" : `浏览器 e2e ${String(batch.batch_label ?? "")}`,
        category_code: String(batch.batch_type ?? ""),
        category_label: String(batch.batch_label ?? ""),
        category_primary_label: String(batch.category_primary_label ?? ""),
        category_sub_label: String(batch.category_sub_label ?? ""),
        category_label_path: [String(batch.category_primary_label ?? ""), String(batch.category_sub_label ?? "")].filter(Boolean),
        category_source: "auto",
        relation_status: status === "draft" ? "" : "linked",
        relation_case_ids: status === "draft" ? [] : ["bank-flow-rule-relation-e2e-001"],
        linked_oa_count: 0,
        linked_invoice_count: 0,
      },
    ],
  };
}

function bankFlowRuleInternalTransferDetailPayload(batch: Record<string, unknown>, status: BankFlowRuleBrowserBatchStatus) {
  const batchId = String(batch.batch_id ?? "bank-flow-internal");
  const amount = String(batch.total_amount ?? "0.00");
  const isCeb = batchId.includes("ceb");
  const firstBankName = isCeb ? "光大银行" : "建设银行";
  const firstAccountLast4 = isCeb ? "8826" : "8106";
  const secondBankName = isCeb ? "建设银行" : "平安银行";
  const secondAccountLast4 = isCeb ? "8106" : "0093";
  return {
    batch,
    tag_counts: { internal_transfer: 2 },
    direction_counts: { expense: 1, income: 1 },
    rows: [
      {
        transaction_id: `${batchId}-out`,
        trade_time: isCeb ? "2026-01-13 16:59:32" : "2026-01-28 16:31:52",
        counterparty_name: "云南溯源科技有限公司",
        direction: "expense",
        direction_label: "支",
        amount,
        bank_name: firstBankName,
        account_last4: firstAccountLast4,
        account_key: `${firstBankName}:${firstAccountLast4}`,
        summary: isCeb ? "本公司账户" : "电子转账",
        purpose: "",
        remark: "",
        category_code: "internal_transfer",
        category_label: "内部往来款",
        category_primary_label: "内部往来款",
        category_sub_label: "",
        category_label_path: ["内部往来款"],
        category_source: "auto",
        relation_status: status === "draft" ? "" : "linked",
        relation_case_ids: status === "draft" ? [] : [`${batchId}-case`],
        linked_oa_count: 0,
        linked_invoice_count: 0,
      },
      {
        transaction_id: `${batchId}-in`,
        trade_time: isCeb ? "2026-01-13 16:59:37" : "2026-01-28 16:32:03",
        counterparty_name: "云南溯源科技有限公司",
        direction: "income",
        direction_label: "收",
        amount,
        bank_name: secondBankName,
        account_last4: secondAccountLast4,
        account_key: `${secondBankName}:${secondAccountLast4}`,
        summary: isCeb ? "电子汇入" : "跨行转账",
        purpose: "",
        remark: "",
        category_code: "internal_transfer",
        category_label: "内部往来款",
        category_primary_label: "内部往来款",
        category_sub_label: "",
        category_label_path: ["内部往来款"],
        category_source: "auto",
        relation_status: status === "draft" ? "" : "linked",
        relation_case_ids: status === "draft" ? [] : [`${batchId}-case`],
        linked_oa_count: 0,
        linked_invoice_count: 0,
      },
    ],
  };
}

function bankFlowRuleBatchMutationPayload(
  status: BankFlowRuleBrowserBatchStatus,
  scopeKey = "2026-05",
) {
  return {
    batch: bankFlowRuleBatch(status),
    affected_months: [scopeKey],
    affected_scope_keys: [scopeKey],
    read_model_scope_keys: [scopeKey],
    freshness_targets: [],
    operation_barrier_targets: [],
    results: [],
  };
}

function bankFlowRuleBatchResetSubmittedPayload() {
  return {
    ...bankFlowRuleBatchMutationPayload("withdrawn"),
    batch: null,
    results: [{ batch_id: "bank-flow-rule-batch-e2e-001", status: "withdrawn" }],
  };
}

const defaultBankFlowRuleBatchTagRules = [
  { tag_code: "fee", requires_oa: false, requires_invoice: false },
  { tag_code: "salary", requires_oa: false, requires_invoice: false },
];

function bankFlowRuleBatchTagSelectionPayload(
  rules: Array<{ tag_code?: string; requires_oa?: boolean; requires_invoice?: boolean }> = defaultBankFlowRuleBatchTagRules,
  salarySubLabel = "工资",
) {
  return {
    version: 3,
    bank_auto_tag_rules_version: 7,
    active_tags: [
      {
        code: "fee",
        label: "手续费",
        output_primary_label: "费用",
        output_sub_label: "手续费",
        status: "active",
      },
      {
        code: "salary",
        label: salarySubLabel,
        output_primary_label: "人工成本",
        output_sub_label: salarySubLabel,
        status: "active",
      },
    ],
    rules,
  };
}

function bankFlowRuleBatchTagSelectionPayloadForScenario(
  rules: Array<{ tag_code?: string; requires_oa?: boolean; requires_invoice?: boolean }>,
  salarySubLabel: string,
  scenario: BankFlowRuleBatchMockScenario = "single",
) {
  const payload = bankFlowRuleBatchTagSelectionPayload(rules, salarySubLabel);
  if (scenario === "ordinaryDraftMatrix") {
    const matrixRules = bankFlowRuleOrdinaryDraftMatrixDefinitions.map((definition) => (
      payload.rules.find((rule) => rule.tag_code === definition.batchType)
      ?? { tag_code: definition.batchType, requires_oa: false, requires_invoice: false }
    ));
    return {
      ...payload,
      active_tags: bankFlowRuleOrdinaryDraftMatrixDefinitions.map((definition) => ({
        code: definition.batchType,
        label: definition.batchLabel,
        output_primary_label: definition.batchType === "salary" ? "人工成本" : definition.primaryLabel,
        output_sub_label: definition.batchLabel,
        status: "active",
      })),
      rules: matrixRules,
    };
  }
  if (scenario !== "internalTransferPairs") {
    return payload;
  }
  const nextRules = payload.rules.some((rule) => rule.tag_code === "internal_transfer")
    ? payload.rules
    : [
      ...payload.rules,
      { tag_code: "internal_transfer", requires_oa: false, requires_invoice: false },
    ];
  return {
    ...payload,
    active_tags: [
      ...payload.active_tags,
      {
        code: "internal_transfer",
        label: "内部往来款",
        output_primary_label: "内部往来款",
        output_sub_label: "",
        status: "active",
      },
    ],
    rules: nextRules,
  };
}

function outputInvoiceCollectionStatus(saved: boolean, reminderSaved: boolean) {
  if (saved) {
    return {
      code: "pending_red_invoice",
      label: "待冲红",
      reason: "浏览器 e2e 已保存手动收款状态。",
      collected_amount: "5,000.00",
      pending_amount: "7,345.67",
      severity: "warning",
      manual_override: {
        id: "output-status-override-e2e-001",
        status_code: "pending_red_invoice",
        expected_collection_date: "2026-06-20",
        note: "浏览器 e2e 状态备注",
        version: 1,
      },
      expected_collection_date: "2026-06-20",
      reminder: reminderSaved
        ? {
          id: "output-reminder-e2e-001",
          remind_at: "2026-06-18T09:30:00+08:00",
          channel: "oa",
          note: "浏览器 e2e 提醒备注",
          status: "active",
        }
        : null,
    };
  }
  return {
    code: "partial_collected",
    label: "待收款，已收部分款",
    reason: "存在收入流水，但收入流水合计小于发票价税合计。",
    collected_amount: "5,000.00",
    pending_amount: "7,345.67",
    severity: "warning",
    manual_override: null,
    expected_collection_date: null,
    reminder: null,
  };
}

function outputInvoiceRedInvoiceRelation(confirmed: boolean) {
  if (!confirmed) {
    return {
      relation_count: 0,
      has_multiple: false,
      detail_mode: "none",
      summaries: [],
    };
  }

  const manualRelation = {
    id: "out-e2e-002",
    related_invoice_id: "out-e2e-002",
    relation_id: "output-red-relation-e2e-001",
    invoice_no: "XSFP-E2E-0002",
    invoice_date: "2026-05-06",
    buyer_name: "浏览器销项客户",
    total_with_tax: "-12,345.67",
    relation_type: "red_invoice",
    reason: "浏览器 e2e 红字发票关系",
    evidence: "浏览器 e2e 红蓝票关系确认",
    confidence: "manual_confirmed",
    source: "manual",
  };

  return {
    primary: manualRelation,
    relation_count: 1,
    has_multiple: false,
    detail_mode: "single",
    summaries: [manualRelation],
  };
}

function outputInvoiceCollectionRowsPayload(
  statusSaved: boolean,
  reminderSaved: boolean,
  receiptCreated: boolean,
  redRelationConfirmed = false,
  includeRedRelationCandidate = false,
  readModelStatus: OutputInvoiceCollectionReadModelMockStatus = "fresh",
  url?: URL,
  includeInvoiceImportRows = false,
) {
  if (readModelStatus !== "fresh") {
    return {
      rows: [],
      summary: {
        invoice_count: 0,
        total_with_tax: "0.00",
        collected_amount: "0.00",
        pending_amount: "0.00",
        pending_collection_count: 0,
        partial_collection_count: 0,
        receipt_pending_count: 0,
      },
      pagination: { page: 1, page_size: 20, total: 0 },
      filter_config: [
        { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
        { field: "collection_status", label: "收款状态", mode: "enum_multi", sortable: true, operators: ["in"] },
        { field: "receipt_status", label: "收据情况", mode: "enum_multi", sortable: true, operators: ["in"] },
      ],
      read_model_status: "refreshing",
      read_model_scope_key: "2026-05",
      read_model_stale_reasons: [`output_invoice_collection_${readModelStatus}`],
      refresh_enqueued: true,
      generated_at: null,
      source_version: "output-invoice-collections:e2e-nonfresh",
    };
  }

  const rows: Array<Record<string, unknown>> = [
    {
      id: "output-collection-row-e2e-001",
      invoice_id: "out-e2e-001",
      invoice_identity_key: "id:out-e2e-001",
      invoice: {
        id: "out-e2e-001",
        display_no: "XSFP-E2E-0001",
        invoice_no: "E2E-0001",
        invoice_code: "5300",
        digital_invoice_no: "XSFP-E2E-0001",
        issue_date: "2026-05-02",
        buyer_name: "浏览器销项客户",
        buyer_tax_no: "91530100E2E001",
        seller_name: "云南溯源科技有限公司",
        seller_tax_no: "91530000E2ESELLER",
        total_with_tax: "12,345.67",
        amount_without_tax: "11,646.86",
        tax_rate: "6%",
        tax_amount: "698.81",
        specific_business_type: "信息技术服务",
        taxable_item_name: "浏览器 e2e 销项收款服务",
      },
      collection_status: outputInvoiceCollectionStatus(statusSaved || redRelationConfirmed, reminderSaved),
      bank: {
        primary: {
          bank_transaction_id: "bank-output-e2e-001",
          counterparty_name: "浏览器销项客户",
          trade_time: "2026-05-03 10:30:00",
          amount: "5,000.00",
          direction: "inflow",
          direction_label: "收入",
          bank_name: "建设银行",
          account_last4: "8106",
          summary: "浏览器 e2e 客户回款",
          remark: "销项收款 e2e",
          relation_status: "linked",
        },
        relation_count: 1,
        has_multiple: false,
        received_total: "5,000.00",
        detail_mode: "single",
        summaries: [],
      },
      redInvoiceRelation: outputInvoiceRedInvoiceRelation(redRelationConfirmed),
      receipt: receiptCreated
        ? {
          status: "issued",
          label: "已出收据",
          reason: "正式收据已创建。",
          preview_available: true,
          source_available: true,
          latest_receipt: {
            id: "receipt-output-e2e-001",
            receipt_no: "SK2026050002",
            amount: "5,000.00",
            status: "issued",
            created_at: "2026-05-03T10:40:00+08:00",
          },
        }
        : {
          status: "pending",
          label: "待出收据",
          reason: "可基于收入流水生成正式收据。",
          preview_available: true,
          source_available: true,
          latest_receipt: null,
        },
    },
  ];

  if (includeRedRelationCandidate) {
    rows.push({
      id: "output-collection-row-e2e-002",
      invoice_id: "out-e2e-002",
      invoice_identity_key: "id:out-e2e-002",
      invoice: {
        id: "out-e2e-002",
        display_no: "XSFP-E2E-0002",
        invoice_no: "E2E-0002",
        invoice_code: "5300",
        digital_invoice_no: "XSFP-E2E-0002",
        issue_date: "2026-05-06",
        buyer_name: "浏览器销项客户",
        buyer_tax_no: "91530100E2E001",
        seller_name: "云南溯源科技有限公司",
        seller_tax_no: "91530000E2ESELLER",
        total_with_tax: "-12,345.67",
        amount_without_tax: "-11,646.86",
        tax_rate: "6%",
        tax_amount: "-698.81",
        specific_business_type: "红字发票",
        taxable_item_name: "浏览器 e2e 红字发票",
      },
      collection_status: {
        code: "red_invoice_candidate",
        label: "红字发票待关联",
        reason: "等待与原蓝字发票建立人工关系。",
        collected_amount: "0.00",
        pending_amount: "0.00",
        severity: "info",
        manual_override: null,
        expected_collection_date: null,
        reminder: null,
      },
      bank: {
        relation_count: 0,
        has_multiple: false,
        received_total: "0.00",
        detail_mode: "none",
        summaries: [],
      },
      redInvoiceRelation: {
        relation_count: 0,
        has_multiple: false,
        detail_mode: "none",
        summaries: [],
      },
      receipt: {
        status: "not_applicable",
        label: "无需收据",
        reason: "红字发票不生成收据。",
        preview_available: false,
        source_available: true,
        latest_receipt: null,
      },
    });
  }
  if (includeInvoiceImportRows) {
    rows.push({
      id: "output-collection-row-e2e-import",
      invoice_id: "out-import-e2e-001",
      invoice_identity_key: "id:out-import-e2e-001",
      invoice: {
        id: "out-import-e2e-001",
        display_no: "XSFP-IMPORT-E2E-001",
        invoice_no: "IMPORT-E2E-001",
        invoice_code: "5300",
        digital_invoice_no: "XSFP-IMPORT-E2E-001",
        issue_date: "2026-05-20",
        buyer_name: "发票导入销项客户",
        buyer_tax_no: "91530100IMPORTOUT",
        seller_name: "云南溯源科技有限公司",
        seller_tax_no: "91530000E2ESELLER",
        total_with_tax: "65,540.00",
        amount_without_tax: "58,000.00",
        tax_rate: "13%",
        tax_amount: "7,540.00",
        specific_business_type: "导入发票",
        taxable_item_name: "发票导入 e2e 销项服务",
      },
      collection_status: {
        code: "pending_collection",
        label: "待收款",
        reason: "发票导入后等待收入流水关系刷新。",
        collected_amount: "0.00",
        pending_amount: "65,540.00",
        severity: "warning",
        manual_override: null,
        expected_collection_date: null,
        reminder: null,
      },
      bank: {
        relation_count: 0,
        has_multiple: false,
        received_total: "0.00",
        detail_mode: "none",
        summaries: [],
      },
      redInvoiceRelation: outputInvoiceRedInvoiceRelation(false),
      receipt: {
        status: "pending",
        label: "待出收据",
        reason: "等待收款关系后生成正式收据。",
        preview_available: false,
        source_available: true,
        latest_receipt: null,
      },
    });
  }

  const page = positiveInteger(url?.searchParams.get("page"), 1);
  const pageSize = positiveInteger(url?.searchParams.get("page_size"), 20);
  const filteredRows = applyOutputInvoiceCollectionListQuery(rows, url);
  const pageRows = filteredRows.slice((page - 1) * pageSize, page * pageSize);

  return {
    rows: pageRows,
    summary: {
      invoice_count: filteredRows.length,
      total_with_tax: "12,345.67",
      collected_amount: "5,000.00",
      pending_amount: "7,345.67",
      pending_collection_count: statusSaved ? 0 : 1,
      partial_collection_count: statusSaved ? 0 : 1,
      receipt_pending_count: receiptCreated ? 0 : 1,
    },
    pagination: { page, page_size: pageSize, total: filteredRows.length },
    filter_config: [
      { field: "invoice_no", label: "发票号码", mode: "text", sortable: true, operators: ["contains", "equals"] },
      { field: "collection_status", label: "收款状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "receipt_status", label: "收据情况", mode: "enum_multi", sortable: true, operators: ["in"] },
    ],
    read_model_status: "fresh",
    read_model_scope_key: "2026-05",
    generated_at: "2026-06-17T01:00:00Z",
    source_version: "output-invoice-collections:e2e-v1",
  };
}

function positiveInteger(value: string | null | undefined, fallback: number) {
  const parsed = Number.parseInt(value ?? "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseOutputInvoiceCollectionFilters(url?: URL) {
  const rawFilters = url?.searchParams.get("filters");
  if (!rawFilters) {
    return [];
  }
  try {
    const decoded = decodeURIComponent(rawFilters);
    const parsed = JSON.parse(decoded);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function outputInvoiceCollectionNestedString(row: Record<string, unknown>, path: string[]) {
  let current: unknown = row;
  for (const segment of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) {
      return "";
    }
    current = (current as Record<string, unknown>)[segment];
  }
  return String(current ?? "");
}

function outputInvoiceCollectionFieldValue(row: Record<string, unknown>, field: string) {
  if (field === "invoice_no") {
    return outputInvoiceCollectionNestedString(row, ["invoice", "display_no"])
      || outputInvoiceCollectionNestedString(row, ["invoice", "invoice_no"]);
  }
  if (field === "collection_status") {
    return outputInvoiceCollectionNestedString(row, ["collection_status", "code"]);
  }
  if (field === "receipt_status") {
    return outputInvoiceCollectionNestedString(row, ["receipt", "status"]);
  }
  if (field === "buyer_name") {
    return outputInvoiceCollectionNestedString(row, ["invoice", "buyer_name"]);
  }
  return "";
}

function applyOutputInvoiceCollectionListQuery(rows: Array<Record<string, unknown>>, url?: URL) {
  let nextRows = rows.slice();
  const keyword = url?.searchParams.get("keyword")?.trim();
  if (keyword) {
    nextRows = nextRows.filter((row) => [
      outputInvoiceCollectionNestedString(row, ["invoice", "display_no"]),
      outputInvoiceCollectionNestedString(row, ["invoice", "invoice_no"]),
      outputInvoiceCollectionNestedString(row, ["invoice", "buyer_name"]),
      outputInvoiceCollectionNestedString(row, ["bank", "primary", "counterparty_name"]),
      outputInvoiceCollectionNestedString(row, ["bank", "primary", "summary"]),
    ].some((value) => String(value ?? "").includes(keyword)));
  }

  for (const filter of parseOutputInvoiceCollectionFilters(url)) {
    const field = String(filter?.field ?? "");
    const operator = String(filter?.operator ?? "");
    if (operator === "in" && Array.isArray(filter?.values)) {
      const values = new Set(filter.values.map((value: unknown) => String(value)));
      nextRows = nextRows.filter((row) => values.has(outputInvoiceCollectionFieldValue(row, field)));
      continue;
    }
    if ((operator === "contains" || operator === "equals") && typeof filter?.value === "string") {
      const value = filter.value;
      nextRows = nextRows.filter((row) => {
        const fieldValue = outputInvoiceCollectionFieldValue(row, field);
        return operator === "contains" ? fieldValue.includes(value) : fieldValue === value;
      });
    }
  }

  const sortField = url?.searchParams.get("sort_field") ?? "";
  const sortDirection = url?.searchParams.get("sort_direction") ?? "";
  if (sortField && (sortDirection === "asc" || sortDirection === "desc")) {
    nextRows.sort((left, right) => {
      const result = outputInvoiceCollectionFieldValue(left, sortField).localeCompare(
        outputInvoiceCollectionFieldValue(right, sortField),
        "zh-Hans-CN",
      );
      return sortDirection === "asc" ? result : -result;
    });
  }
  return nextRows;
}

function outputInvoiceCollectionFilterOptionsPayload(
  statusSaved: boolean,
  receiptCreated: boolean,
  readModelStatus: OutputInvoiceCollectionReadModelMockStatus = "fresh",
) {
  if (readModelStatus !== "fresh") {
    return {
      fields: [],
      read_model_status: "refreshing",
      read_model_scope_key: "2026-05",
      read_model_stale_reasons: [`output_invoice_collection_${readModelStatus}`],
      refresh_enqueued: true,
    };
  }

  return {
    fields: [
      {
        field: "invoice_no",
        label: "发票号码",
        mode: "text",
        sortable: true,
        operators: ["contains", "equals"],
        options: [],
      },
      {
        field: "collection_status",
        label: "收款状态",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [
          {
            value: statusSaved ? "pending_red_invoice" : "partial_collected",
            label: statusSaved ? "待冲红" : "待收款，已收部分款",
            count: 1,
          },
        ],
      },
      {
        field: "receipt_status",
        label: "收据情况",
        mode: "enum_multi",
        sortable: true,
        operators: ["in"],
        options: [
          {
            value: receiptCreated ? "issued" : "pending",
            label: receiptCreated ? "已出收据" : "待出收据",
            count: 1,
          },
        ],
      },
    ],
    read_model_status: "fresh",
    read_model_scope_key: "2026-05",
  };
}

function outputInvoiceCollectionExportPreviewPayload(redRelationConfirmed = false) {
  return {
    file_name: "output-invoice-collections.xlsx",
    row_count: 1,
    scope_label: "当前筛选",
    columns: [
      "序号",
      "发票号码",
      "购方",
      "收款状态",
      "收款方",
      "收款金额",
      "红蓝票关系",
      "红蓝票来源",
      "红蓝票依据",
      "收据状态",
    ],
    sample_rows: [
      {
        序号: "1",
        发票号码: "XSFP-E2E-0001",
        购方: "浏览器销项客户",
        收款状态: "待收款，已收部分款",
        收款方: "浏览器销项客户",
        收款金额: "5,000.00",
        红蓝票关系: redRelationConfirmed ? "XSFP-E2E-0002" : "",
        红蓝票来源: redRelationConfirmed ? "manual" : "",
        红蓝票依据: redRelationConfirmed ? "浏览器 e2e 红蓝票关系确认" : "",
        收据状态: "待出收据",
      },
    ],
    read_model_status: "fresh",
  };
}

function outputInvoiceCollectionExportBody(redRelationConfirmed: boolean, url: URL) {
  return createMinimalXlsx([
    ["序号", "发票号码", "购方", "收款状态", "收款方", "收款金额", "红蓝票关系", "红蓝票来源", "红蓝票依据", "收据状态"],
    [
      "1",
      "XSFP-E2E-0001",
      "浏览器销项客户",
      "待收款，已收部分款",
      "浏览器销项客户",
      "5,000.00",
      redRelationConfirmed ? "XSFP-E2E-0002" : "",
      redRelationConfirmed ? "manual" : "",
      redRelationConfirmed ? "浏览器 e2e 红蓝票关系确认" : "",
      "待出收据",
    ],
    ["keyword", url.searchParams.get("keyword") ?? ""],
    ["page", url.searchParams.get("page") ?? ""],
  ], "销项收款");
}

function outputInvoiceCollectionStatusRulesPayload() {
  return {
    version: "sheet6-browser-e2e-v1",
    readOnly: true,
    rules: [
      {
        id: "partial_collected",
        label: "待收款，已收部分款",
        description: "收入流水金额小于销项发票金额。",
        recognitionMode: "自动识别",
        requiredFacts: ["销项发票", "收入流水"],
        workbenchRequirement: "关联台或银行流水证明已收部分款。",
        priority: 4,
      },
      {
        id: "pending_red_invoice",
        label: "待冲红",
        description: "人工确认未来需要冲红。",
        recognitionMode: "手动标记",
        requiredFacts: ["销项发票"],
        workbenchRequirement: "人工确认。",
        priority: 6,
      },
    ],
    manualStatusOptions: [
      { code: "pending_collection", label: "待收款", severity: "warning" },
      { code: "pending_red_invoice", label: "待冲红", severity: "warning" },
    ],
    permissions: { can_save: true, can_admin: true },
  };
}

function outputInvoiceReceiptPreviewPayload() {
  return {
    canPreview: true,
    selectedBankTransactionId: "bank-output-e2e-001",
    candidates: [],
    receipt: {
      templateVersion: "sheet7-browser-e2e-v1",
      companyName: "云南溯源科技有限公司",
      title: "收 据",
      date: "2026-05-03",
      dateParts: { year: "2026", month: "05", day: "03" },
      payerName: "浏览器销项客户",
      summary: "浏览器 e2e 销项收款服务",
      amount: "5,000.00",
      amountUppercase: "人民币伍仟元整",
      remark: "销项发票 XSFP-E2E-0001",
      bankName: "建设银行",
      bankTransactionId: "bank-output-e2e-001",
      canCreateFormalReceipt: true,
    },
  };
}

function outputInvoiceReceiptHistoryPayload(receiptState: OutputInvoiceReceiptLifecycleState) {
  const receipts = [];
  if (receiptState === "issued" || receiptState === "voided" || receiptState === "reissued") {
    receipts.push({
      id: "receipt-output-e2e-001",
      receipt_no: "SK2026050002",
      amount: "5,000.00",
      created_at: "2026-05-03T10:40:00+08:00",
      status: receiptState === "issued" ? "issued" : "voided",
      voided_at: receiptState === "issued" ? "" : "2026-05-03T11:10:00+08:00",
      void_reason: receiptState === "issued" ? "" : "浏览器 e2e 作废收据",
    });
  }
  if (receiptState === "reissued") {
    receipts.push({
      id: "receipt-output-e2e-002",
      receipt_no: "SK2026050003",
      amount: "5,000.00",
      created_at: "2026-05-03T11:20:00+08:00",
      status: "issued",
      reissued_from_receipt_id: "receipt-output-e2e-001",
    });
  }
  return {
    invoice_id: "out-e2e-001",
    source_available: true,
    source_name: "formal_receipt_lifecycle",
    receipts,
  };
}

function amountSummary() {
  return {
    before: {
      oa_total: "58000.00",
      bank_total: "58000.00",
      invoice_total: "58000.00",
    },
    after: {
      oa_total: "58000.00",
      bank_total: "58000.00",
      invoice_total: "58000.00",
    },
    status: "matched",
    direction: "payment",
    mismatch_fields: [],
  };
}

function confirmPreviewPayload() {
  return {
    operation: "confirm_link",
    operation_type: "confirm_link",
    preview_id: "browser-e2e-confirm-preview",
    submit_expected_versions: { "CASE-202603-101": 1 },
    can_submit: true,
    requires_note: false,
    message: "确认后将把 1 条 OA、1 条流水和 1 条发票闭环。",
    before: { groups: buildUnpairedWorkbenchGroups() },
    after: { groups: [buildPairedWorkbenchGroup()] },
    amount_summary: amountSummary(),
  };
}

function confirmResultPayload() {
  return {
    success: true,
    action: "confirm_link",
    month: "all",
    affected_row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
    case_id: "CASE-202603-101",
    affected_months: ["2026-03"],
    affected_scope_keys: ["2026-03"],
    freshness_targets: [],
    operation_projection: {
      after: {
        paired_groups: [buildPairedWorkbenchGroup()],
        unpaired_groups: [],
      },
    },
    message: "已确认 3 条记录关联。",
  };
}

function withdrawPreviewPayload() {
  return {
    operation: "withdraw_link",
    operation_type: "withdraw_relation",
    preview_id: "withdraw_relation:CASE-202603-101",
    submit_expected_versions: { "CASE-202603-101": 1 },
    can_submit: true,
    requires_note: false,
    message: "所选记录已确认关联，可在此撤回这组配对关系。",
    active_relation: {
      case_id: "CASE-202603-101",
      version: 1,
      row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
    },
    before: { groups: [buildPairedWorkbenchGroup()] },
    after: { groups: buildUnpairedWorkbenchGroups() },
    amount_summary: amountSummary(),
  };
}

function withdrawResultPayload() {
  return {
    success: true,
    action: "withdraw_link",
    month: "all",
    affected_row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
    case_id: "CASE-202603-101",
    affected_months: ["2026-03"],
    affected_scope_keys: ["2026-03"],
    freshness_targets: [],
    operation_projection: {
      after: {
        paired_groups: [],
        unpaired_groups: buildUnpairedWorkbenchGroups(),
      },
    },
    message: "已撤回 3 条记录关联。",
  };
}

function workbenchExceptionPreviewPayload() {
  return {
    rule_version: "exception_rules_browser_e2e_v1",
    scenario: {
      business_line: "expense",
      scenario_code: "expense_oa_bank_missing_invoice",
      scenario_label: "OA和支出流水一致，缺进项发票",
      confidence: "high",
      amount_relation: "oa_equals_bank_missing_invoice",
    },
    amount_summary: {
      oa_total: "58000.00",
      bank_expense_total: "58000.00",
      bank_income_total: "0.00",
      input_invoice_total: "0.00",
      output_invoice_total: "0.00",
      expense_relation: "oa_equals_bank_missing_invoice",
    },
    automatic_actions: [],
    available_actions: [
      {
        action_code: "wait_input_invoice",
        label: "追进项发票",
        result_status: "open",
        required_fields: ["note"],
        description: "金额已核对，等待后续进项发票补齐。",
      },
    ],
    warnings: [
      {
        code: "missing_input_invoice",
        severity: "warning",
        message: "当前候选缺进项发票，提交后进入已处理异常。",
      },
    ],
    workflow_projection: {
      next_status: "processed_exception",
    },
    candidate_evidence: [
      {
        id: "CASE-202603-101",
        label: "命中候选分组 CASE-202603-101",
        detail: "OA 与银行流水金额一致，发票仍需追踪。",
      },
    ],
    can_apply: true,
  };
}

function workbenchExceptionApplyResultPayload() {
  return {
    success: true,
    case: {
      id: "WEX-BROWSER-001",
      status: "open",
      scenario_code: "expense_oa_bank_missing_invoice",
      action_code: "wait_input_invoice",
    },
    pair_relation: null,
    updated_rows: [],
    affected_row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
    affected_scope_keys: ["2026-03"],
    freshness_targets: [],
    workbench_refresh_required: true,
    message: "已提交统一异常处理。",
  };
}

function workbenchExceptionActionResultPayload(action: "cancel_exception" | "ignore_row" | "unignore_row") {
  const affectedRowIds = action === "ignore_row" || action === "unignore_row"
    ? ["iv-o-202603-001"]
    : ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"];
  const messages = {
    cancel_exception: "已取消异常处理。",
    ignore_row: "已忽略 1 条记录。",
    unignore_row: "已撤回忽略。",
  };
  return {
    success: true,
    action,
    month: "all",
    affected_row_ids: affectedRowIds,
    exception_case_id: "WEX-BROWSER-001",
    affected_months: ["2026-03"],
    affected_scope_keys: ["2026-03"],
    freshness_targets: [],
    message: messages[action],
  };
}

type WorkbenchCashSpecialAction =
  | "confirm_cash_pass_through"
  | "confirm_cash_ticket_purchase"
  | "cancel_cash_special";

function workbenchCashSpecialResultPayload(action: WorkbenchCashSpecialAction) {
  const messages = {
    confirm_cash_pass_through: "已确认现金往来过账。",
    confirm_cash_ticket_purchase: "已确认买票成本。",
    cancel_cash_special: "已取消现金往来特殊处理。",
  };
  return {
    success: true,
    action,
    month: "all",
    affected_row_ids: ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
    case_id: "CASE-202603-101",
    affected_months: ["2026-03"],
    affected_scope_keys: ["2026-03"],
    freshness_targets: [],
    operation_projection: {
      after: {
        paired_groups: [buildPairedWorkbenchGroup(true)],
        unpaired_groups: [],
      },
    },
    message: messages[action],
  };
}

function operationBarrierPayload(mode: OperationBarrierMockMode = "fresh") {
  const fresh = mode === "fresh";
  const blocked = mode === "blocked";
  const target = {
    read_model_key: "workbench_relation",
    scope_type: "",
    scope_key: "2026-03",
    status: fresh ? "fresh" : blocked ? "blocked" : "refreshing",
    raw_status: fresh ? "fresh" : blocked ? "failed" : "processing",
    fresh,
    blocking: blocked,
    reason: blocked ? "browser relation refresh blocked" : mode === "refreshing" ? "browser relation refresh pending" : "",
    last_error: blocked ? "browser relation refresh blocked" : null,
    generated_at: "2026-06-17T01:00:00Z",
  };
  return {
    status: fresh ? "fresh" : blocked ? "blocked" : "refreshing",
    fresh,
    targets: [target],
    blocked_targets: blocked ? [target] : [],
    refreshing_targets: mode === "refreshing" ? [target] : [],
  };
}

function turnoverLedgerTagSelectionPayload(
  selectedTagCodes = ["external_turnover_payment", "external_turnover_collection"],
  version = 1,
) {
  return {
    version,
    selected_tag_codes: selectedTagCodes,
    inactive_selected_tag_codes: [],
    active_tags: [
      {
        code: "external_turnover_payment",
        label: "外部往来款付款",
        path: ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
        source: "browser_e2e",
        status: "active",
        output_primary_label: "外部往来款付款",
        output_sub_label: "归还借款",
        turnover_role: "external_turnover",
        turnover_action_type: "repaid",
      },
      {
        code: "external_turnover_collection",
        label: "外部往来款收款",
        path: ["银行明细自动标签规则", "外部往来款收款", "收回借款"],
        source: "browser_e2e",
        status: "active",
        output_primary_label: "外部往来款收款",
        output_sub_label: "收回借款",
        turnover_role: "external_turnover",
        turnover_action_type: "collected",
      },
    ],
  };
}

function turnoverSummaryRow(relationClosed: boolean) {
  return {
    row_kind: "summary",
    relation_id: relationClosed ? "turnover_rel_e2e_closure" : "turnover_rel_e2e_summary",
    status: relationClosed ? "closed" : "open",
    status_label: relationClosed ? "已闭环" : "待闭环",
    row_tone: relationClosed ? "success" : "warning",
    flow_amount: "0.00",
    borrow_amount: "1000.00",
    borrow_date: "2026-05-02",
    borrow_direction: "income",
    repayment_amount: "1000.00",
    repayment_date: "2026-05-03",
    repayment_direction: "expense",
    balance_amount: relationClosed ? "0.00" : "1000.00",
    category_code: "external_turnover_collection",
    category_label: "外部往来款收款 / 收回借款",
    category_primary_label: "外部往来款收款",
    category_sub_label: "收回借款",
    category_third_label: "",
    category_label_path: ["外部往来款收款", "收回借款"],
    category_version: 1,
    counterparty_bank_name: "建设银行",
    bank_account_labels: ["建行 8106"],
    summary_text: relationClosed ? "浏览器 e2e 闭环完成" : "浏览器 e2e 往来款待闭环",
    allocation_status: "unallocated",
    allocated_lot_ids: [],
    repayment_remark: "浏览器 e2e 往来款",
    interest_rate_type: "none",
    interest_rate_value: "0.000000",
    interest_paid_amount: "0.00",
    loan_days: null,
    accrued_interest: "0.00",
    interest_paid_date: null,
    interest_payment_method: "",
    note: "",
    bank_row_ids: [turnoverBankRows.expense, turnoverBankRows.income],
    workbench_relation_status: relationClosed ? "linked" : "",
    workbench_relation_case_ids: relationClosed ? ["turnover:turnover_rel_e2e_closure"] : [],
    workbench_relation_mode: relationClosed ? "turnover_manual_closure" : "",
    workbench_relation_source: relationClosed ? "manual" : "",
    workbench_relation_row_ids: relationClosed ? [turnoverBankRows.expense, turnoverBankRows.income] : [],
    cash_closure_linked: relationClosed,
    cash_closure_case_id: relationClosed ? "turnover:turnover_rel_e2e_closure" : "",
    cash_closure_source: relationClosed ? "turnover_ledger" : "",
    cash_closure_relation_id: "",
  };
}

function turnoverFlowRow(
  rowId: string,
  direction: "income" | "expense",
  relationClosed: boolean,
  categoryVersion: number,
) {
  const isIncome = direction === "income";
  return {
    row_kind: "flow",
    relation_id: relationClosed ? "turnover_rel_e2e_closure" : `turnover_rel_e2e_${direction}`,
    flow_id: rowId,
    source_bank_row_id: rowId,
    status: relationClosed ? "closed" : "open",
    status_label: relationClosed ? "已闭环" : "待闭环",
    row_tone: relationClosed ? "success" : "warning",
    transaction_at: isIncome ? "2026-05-02 10:00:00" : "2026-05-03 10:00:00",
    flow_direction: direction,
    flow_amount: "1000.00",
    borrow_amount: isIncome ? "1000.00" : "0.00",
    borrow_date: isIncome ? "2026-05-02" : null,
    borrow_direction: isIncome ? "income" : "",
    repayment_amount: isIncome ? "0.00" : "1000.00",
    allocated_repayment_amount: "0.00",
    repayment_date: isIncome ? null : "2026-05-03",
    repayment_direction: isIncome ? "" : "expense",
    balance_amount: relationClosed ? "0.00" : "1000.00",
    category_code: isIncome ? "external_turnover_collection" : "external_turnover_payment",
    category_label: isIncome ? "外部往来款收款 / 收回借款" : "外部往来款付款 / 归还借款",
    category_primary_label: isIncome ? "外部往来款收款" : "外部往来款付款",
    category_sub_label: isIncome ? "收回借款" : "归还借款",
    category_third_label: "",
    category_label_path: isIncome ? ["外部往来款收款", "收回借款"] : ["外部往来款付款", "归还借款"],
    category_version: categoryVersion,
    counterparty_bank_name: "建设银行",
    bank_account_labels: ["建行 8106"],
    summary_text: isIncome ? "浏览器 e2e 收回借款" : "浏览器 e2e 归还借款",
    allocation_status: "unallocated",
    allocated_lot_ids: [],
    repayment_remark: isIncome ? "收到还款" : "支付还款",
    interest_rate_type: "none",
    interest_rate_value: "0.000000",
    interest_paid_amount: "0.00",
    loan_days: null,
    accrued_interest: "0.00",
    interest_paid_date: null,
    interest_payment_method: "",
    note: "",
    bank_row_ids: [rowId],
    workbench_relation_status: relationClosed ? "linked" : "",
    workbench_relation_case_ids: relationClosed ? ["turnover:turnover_rel_e2e_closure"] : [],
    workbench_relation_mode: relationClosed ? "turnover_manual_closure" : "",
    workbench_relation_source: relationClosed ? "manual" : "",
    workbench_relation_row_ids: relationClosed ? [turnoverBankRows.expense, turnoverBankRows.income] : [],
    cash_closure_linked: relationClosed,
    cash_closure_case_id: relationClosed ? "turnover:turnover_rel_e2e_closure" : "",
    cash_closure_source: relationClosed ? "turnover_ledger" : "",
    cash_closure_relation_id: "",
  };
}

function turnoverLedgerPayload(
  relationClosed: boolean,
  readModelStatus: TurnoverLedgerReadModelMockStatus = "fresh",
) {
  const summaryRow = turnoverSummaryRow(relationClosed);
  const flowRows = [
    turnoverFlowRow(turnoverBankRows.expense, "expense", relationClosed, turnoverBankRowVersions[turnoverBankRows.expense]),
    turnoverFlowRow(turnoverBankRows.income, "income", relationClosed, turnoverBankRowVersions[turnoverBankRows.income]),
  ];
  return {
    summary: {
      pending_repayment_amount: "0.00",
      repaid_amount: "1000.00",
      pending_collection_amount: relationClosed ? "0.00" : "1000.00",
      collected_amount: relationClosed ? "1000.00" : "0.00",
      closed_amount: relationClosed ? "1000.00" : "0.00",
      suggested_count: relationClosed ? 0 : 1,
      conflict_count: 0,
      row_count: 1,
    },
    family_summaries: [
      {
        family: "company",
        label: "公司往来",
        pending_repayment_amount: "0.00",
        repaid_amount: "1000.00",
        pending_collection_amount: relationClosed ? "0.00" : "1000.00",
        collected_amount: relationClosed ? "1000.00" : "0.00",
        pending_amount: relationClosed ? "0.00" : "1000.00",
        closed_amount: relationClosed ? "1000.00" : "0.00",
        row_count: 1,
      },
    ],
    groups: [
      {
        group_id: "counterparty:company:e2e",
        counterparty_name: "云南建设有限公司",
        family: "company",
        family_label: "公司往来",
        pending_direction: relationClosed ? "closed" : "mixed",
        pending_direction_label: relationClosed ? "已闭合" : "收支待闭环",
        pending_amount: relationClosed ? "0.00" : "1000.00",
        pending_repayment_amount: "0.00",
        repaid_amount: "1000.00",
        pending_collection_amount: relationClosed ? "0.00" : "1000.00",
        collected_amount: relationClosed ? "1000.00" : "0.00",
        closed_amount: relationClosed ? "1000.00" : "0.00",
        row_span: 3,
        group_tone: relationClosed ? "success" : "warning",
        rows: [summaryRow, ...flowRows],
        summary_row: summaryRow,
        flow_rows: flowRows,
        allocation_lots: [],
        lot_rows: [],
      },
    ],
    pagination: { page: 1, page_size: 50, total: 1 },
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : [`turnover_ledger_${readModelStatus}`],
  };
}

function parseJsonBody(postData: string | null): Record<string, unknown> {
  if (!postData) {
    return {};
  }
  try {
    const parsed = JSON.parse(postData);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sequencedReadModelStatus(
  sequence: BankDetailReadModelMockStatus[] | undefined,
  requestIndex: number,
  fallback: BankDetailReadModelMockStatus | undefined,
) {
  if (!sequence?.length) {
    return fallback ?? "fresh";
  }
  return sequence[Math.min(requestIndex, sequence.length - 1)] ?? fallback ?? "fresh";
}

function turnoverClosureExpectedVersions() {
  return Object.fromEntries(
    Object.entries(turnoverBankRowVersions).map(([rowId, version]) => [
      `turnover_bank_row:${rowId}`,
      version,
    ]),
  );
}

function turnoverClosureRequestConflict(body: Record<string, unknown>) {
  const bankRowIds = Array.isArray(body.bank_row_ids) ? body.bank_row_ids.map(String) : [];
  const expectedRowIds = [turnoverBankRows.expense, turnoverBankRows.income];
  if (JSON.stringify(bankRowIds) !== JSON.stringify(expectedRowIds)) {
    return {
      error: "invalid_bank_row_ids",
      message: "bank_row_ids must match the current turnover closure selection.",
    };
  }
  const expectedVersions = body.expected_versions && typeof body.expected_versions === "object" && !Array.isArray(body.expected_versions)
    ? body.expected_versions as Record<string, unknown>
    : {};
  if (JSON.stringify(expectedVersions) !== JSON.stringify(turnoverClosureExpectedVersions())) {
    return {
      error: "turnover_relation_conflict",
      message: "银行流水状态已变化，请刷新后重试。",
    };
  }
  return null;
}

function turnoverClosureMutationPayload() {
  return {
    status: "confirmed",
    workbench_pair_relation: {
      case_id: "turnover:turnover_rel_e2e_closure",
      relation_mode: "turnover_manual_closure",
    },
    affected_months: ["2026-05"],
    freshness_targets: [],
  };
}

function bankAccountsPayload(readModelStatus: BankDetailReadModelMockStatus = "fresh") {
  return {
    accounts: [
      {
        account_key: "bank-account-1138",
        bank_name: "建设银行",
        account_last4: "1138",
        display_name: "建设银行 1138",
        latest_balance: "130500.50",
        latest_balance_at: "2026-03-28 10:18:00",
        has_balance: true,
        transaction_count: 1,
      },
    ],
    total_balance: "130500.50",
    balance_account_count: 1,
    missing_balance_account_count: 0,
    read_model_status: readModelStatus,
    balance_read_model_status: readModelStatus,
  };
}

function bankTransactionsPayload(
  relationConfirmed: boolean,
  bankImportConfirmed = false,
  options: {
    classificationMode?: BankDetailClassificationMockMode;
    categoryOverride?: BankDetailCategoryOverride | null;
    largeDataset?: boolean;
    page?: number;
    pageSize?: number;
    readModelStatus?: BankDetailReadModelMockStatus;
    rowsEmpty?: boolean;
    total?: number;
  } = {},
) {
  const relationTags = relationConfirmed ? ["有oa", "有发票"] : ["无oa", "无发票"];
  const rows = options.rowsEmpty
    ? []
    : [
      {
        id: "bk-o-202603-001",
        trade_time: "2026-03-28 10:18:00",
        counterparty_name: "智能工厂设备商",
        direction: "expense",
        direction_label: "支",
        amount: "58,000.00",
        balance: "130500.50",
        summary: relationConfirmed ? "设备尾款已闭环" : "设备尾款待进项票",
        purpose: "设备尾款",
        purpose_text: "设备尾款",
        summary_text: relationConfirmed ? "设备尾款已闭环" : "设备尾款待进项票",
        note_text: "",
        bank_name: "建设银行",
        account_last4: "1138",
        category_code: null,
        category_label: null,
        category_path: [],
        category_source: "",
        category_version: 1,
        category_resolution_status: "auto_matched",
        auto_category_code: "equipment_payment",
        auto_category_label: "设备款",
        auto_category_path: ["自动识别", "设备款"],
        auto_category_primary_label: "成本",
        auto_category_sub_label: "设备款",
        auto_category_third_label: null,
        auto_category_label_path: ["成本", "设备款"],
        auto_category_source: "browser_e2e",
        auto_category_reason: "浏览器 e2e mock",
        auto_category_confidence: "high",
        effective_category_code: "equipment_payment",
        effective_category_label: "设备款",
        effective_category_path: ["自动识别", "设备款"],
        effective_category_primary_label: "成本",
        effective_category_sub_label: "设备款",
        effective_category_third_label: null,
        effective_category_label_path: ["成本", "设备款"],
        effective_category_source: "auto",
        oa_relation_tag: relationTags[0],
        invoice_relation_tag: relationTags[1],
        relation_tags: relationTags,
        relation_case_id: relationConfirmed ? "CASE-202603-101" : "",
        relation_status: relationConfirmed ? "linked" : "unlinked",
      },
      ...(bankImportConfirmed ? [
        {
          id: "bk-import-202605-001",
          trade_time: "2026-05-18 09:30:00",
          counterparty_name: "导入浏览器测试客户",
          direction: "income",
          direction_label: "收",
          amount: "1,688.00",
          balance: "132188.50",
          summary: "银行流水导入 browser e2e",
          purpose: "导入回归",
          purpose_text: "导入回归",
          summary_text: "银行流水导入 browser e2e",
          note_text: "",
          bank_name: "建设银行",
          account_last4: "8826",
          category_code: null,
          category_label: null,
          category_path: [],
          category_source: "",
          category_version: 1,
          category_resolution_status: "uncategorized",
          auto_category_code: null,
          auto_category_label: null,
          auto_category_path: [],
          auto_category_primary_label: null,
          auto_category_sub_label: null,
          auto_category_third_label: null,
          auto_category_label_path: [],
          auto_category_source: "",
          auto_category_reason: "",
          auto_category_confidence: "",
          effective_category_code: null,
          effective_category_label: null,
          effective_category_path: [],
          effective_category_primary_label: null,
          effective_category_sub_label: null,
          effective_category_third_label: null,
          effective_category_label_path: [],
          effective_category_source: "",
          oa_relation_tag: "",
          invoice_relation_tag: "",
          relation_tags: [],
          relation_case_id: "",
          relation_status: "",
        },
      ] : []),
      ...(options.largeDataset ? Array.from({ length: 119 }, (_, index) => {
        const sequence = index + 2;
        const padded = String(sequence).padStart(3, "0");
        return {
          id: `bk-large-202603-${padded}`,
          trade_time: `2026-03-${String((sequence % 28) + 1).padStart(2, "0")} 15:42:00`,
          counterparty_name: `长字段浏览器供应商${padded}有限公司-跨区域设备服务与维护合同`,
          direction: "expense",
          direction_label: "支",
          amount: `${(5000 + sequence * 37).toLocaleString("en-US")}.00`,
          balance: `${(130500 - sequence * 19).toLocaleString("en-US")}.50`,
          summary: `浏览器长列表验收摘要 ${padded} - 包含项目、合同、批次和跨页备注`,
          purpose: `设备维护与备品备件采购 ${padded}`,
          purpose_text: `设备维护与备品备件采购 ${padded} / 超长用途字段用于检查列宽与换行`,
          summary_text: `浏览器长列表验收摘要 ${padded} - 包含项目、合同、批次和跨页备注`,
          note_text: `客户附言 ${padded}：跨区域售后服务、安装调试、验收留存和发票待匹配说明`,
          bank_name: "建设银行",
          account_last4: "1138",
          category_code: null,
          category_label: null,
          category_path: [],
          category_source: "",
          category_version: 1,
          category_resolution_status: "auto_matched",
          auto_category_code: "equipment_payment",
          auto_category_label: "设备款",
          auto_category_path: ["自动识别", "设备款"],
          auto_category_primary_label: "成本",
          auto_category_sub_label: "设备款",
          auto_category_third_label: null,
          auto_category_label_path: ["成本", "设备款"],
          auto_category_source: "browser_e2e_large",
          auto_category_reason: "浏览器 e2e 大表格 mock",
          auto_category_confidence: "high",
          effective_category_code: "equipment_payment",
          effective_category_label: "设备款",
          effective_category_path: ["自动识别", "设备款"],
          effective_category_primary_label: "成本",
          effective_category_sub_label: "设备款",
          effective_category_third_label: null,
          effective_category_label_path: ["成本", "设备款"],
          effective_category_source: "auto",
          oa_relation_tag: relationTags[0],
          invoice_relation_tag: relationTags[1],
          relation_tags: relationTags,
          relation_case_id: relationConfirmed ? `CASE-LARGE-202603-${padded}` : "",
          relation_status: relationConfirmed ? "linked" : "unlinked",
        };
      }) : []),
    ];
  const firstRow = rows[0];
  if (firstRow && options.categoryOverride) {
    const override = options.categoryOverride;
    Object.assign(firstRow, {
      category_code: override.categoryCode,
      category_label: override.subLabel,
      category_path: override.labelPath,
      category_primary_label: override.primaryLabel,
      category_sub_label: override.subLabel,
      category_third_label: override.thirdLabel ?? null,
      category_label_path: override.labelPath,
      category_source: override.source,
      category_version: 2,
      category_resolution_status: "manual_confirmed",
      manual_confirmed_category_code: override.categoryCode,
      auto_category_code: null,
      auto_category_label: null,
      auto_category_path: [],
      auto_category_primary_label: null,
      auto_category_sub_label: null,
      auto_category_third_label: null,
      auto_category_label_path: [],
      auto_category_source: "",
      auto_category_reason: "",
      auto_category_confidence: "",
      auto_candidate_category_codes: [],
      auto_candidate_categories: [],
      effective_category_code: override.categoryCode,
      effective_category_label: override.subLabel,
      effective_category_path: override.labelPath,
      effective_category_primary_label: override.primaryLabel,
      effective_category_sub_label: override.subLabel,
      effective_category_third_label: override.thirdLabel ?? null,
      effective_category_label_path: override.labelPath,
      effective_category_source: override.source === "manual" ? "manual" : "auto_confirmation",
    });
  } else if (firstRow && options.classificationMode === "needs_confirmation") {
    Object.assign(firstRow, {
      category_resolution_status: "needs_confirmation",
      auto_category_code: null,
      auto_category_label: null,
      auto_category_path: [],
      auto_category_primary_label: null,
      auto_category_sub_label: null,
      auto_category_third_label: null,
      auto_category_label_path: [],
      effective_category_code: null,
      effective_category_label: null,
      effective_category_path: [],
      effective_category_primary_label: null,
      effective_category_sub_label: null,
      effective_category_third_label: null,
      effective_category_label_path: [],
      effective_category_source: "",
      auto_candidate_category_codes: ["equipment_payment"],
      auto_candidate_categories: [
        {
          category_code: "equipment_payment",
          category_label: "设备款",
          category_primary_label: "成本",
          category_sub_label: "设备款",
          category_third_label: null,
          category_label_path: ["成本", "设备款"],
          category_path: ["自动识别", "设备款"],
          rule_code: "equipment_payment_rule",
          reason: "浏览器 e2e mock 候选",
        },
      ],
    });
  }
  else if (firstRow && options.classificationMode === "unmatched") {
    Object.assign(firstRow, {
      category_resolution_status: "unmatched",
      auto_category_code: null,
      auto_category_label: null,
      auto_category_path: [],
      auto_category_primary_label: null,
      auto_category_sub_label: null,
      auto_category_third_label: null,
      auto_category_label_path: [],
      effective_category_code: null,
      effective_category_label: null,
      effective_category_path: [],
      effective_category_primary_label: null,
      effective_category_sub_label: null,
      effective_category_third_label: null,
      effective_category_label_path: [],
      effective_category_source: "",
    });
  }
  const equipmentPaymentCount = rows.filter((row) => row.effective_category_code === "equipment_payment").length;
  return {
    account_key: null,
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    rows,
    category_counts: {
      equipment_payment: equipmentPaymentCount,
      salary: options.categoryOverride?.categoryCode === "salary" ? 1 : 0,
      external_payment: options.categoryOverride?.categoryCode === "external_payment" ? 1 : 0,
      uncategorized: options.classificationMode === "unmatched" && !options.rowsEmpty && !options.categoryOverride ? 1 : 0,
    },
    pagination: {
      page: options.page ?? 1,
      page_size: options.pageSize ?? 100,
      total: options.total ?? rows.length,
    },
    tag_dictionary: {
      version: 1,
      tags: [
        {
          code: "equipment_payment",
          label: "设备款",
          path: ["自动识别", "设备款"],
          output_primary_label: "成本",
          output_sub_label: "设备款",
          status: "active",
          source: "system",
        },
        {
          code: "salary",
          label: "工资",
          path: ["费用", "工资"],
          output_primary_label: "费用",
          output_sub_label: "工资",
          status: "active",
          source: "system",
        },
        {
          code: "external_payment",
          label: "借出款",
          path: ["外部往来款付款", "借出款"],
          output_primary_label: "外部往来款付款",
          output_sub_label: "借出款",
          status: "active",
          source: "system",
        },
      ],
    },
    read_model_status: options.readModelStatus ?? "fresh",
  };
}

function bankAutoTagRulesPayload(canSave = true, options: BankAutoTagRulesPayloadOptions = {}) {
  const salarySubLabel = options.salarySubLabel ?? "工资";
  return {
    version: options.version ?? 1,
    system_rule: {
      code: "internal_transfer",
      label: "内部往来款",
      priority_label: "优先级 1",
      source: "system",
      status: "active",
      editable: false,
      archivable: false,
      sortable: false,
    },
    active_rules: [
      {
        code: "equipment_payment",
        label: "设备款",
        output_primary_label: "成本",
        output_sub_label: "设备款",
        status: "active",
        source: "custom",
        priority: 2,
        priority_label: "优先级 2",
        sort_order: 1,
        direction: "expense",
        account_scope: { type: "any", values: [] },
        rules: {
          match_fields: ["purpose_text", "summary_text", "note_text", "detail_text"],
          exact_any: [],
          contains_any: ["设备"],
          contains_all: [],
          none_of: [],
          regex_any: [],
        },
        rule_summary: "用途/摘要/备注包含设备",
        editable: true,
        archivable: true,
        sortable: true,
      },
      {
        code: "salary",
        label: salarySubLabel,
        output_primary_label: "费用",
        output_sub_label: salarySubLabel,
        status: "active",
        source: "custom",
        priority: 3,
        priority_label: "优先级 3",
        sort_order: 2,
        direction: "expense",
        account_scope: { type: "any", values: [] },
        rules: {
          match_fields: ["purpose_text", "summary_text", "note_text", "detail_text"],
          exact_any: [],
          contains_any: ["工资"],
          contains_all: [],
          none_of: [],
          regex_any: [],
        },
        rule_summary: "用途/摘要/备注包含工资",
        editable: true,
        archivable: true,
        sortable: true,
      },
      {
        code: "external_payment",
        label: "借出款",
        output_primary_label: "外部往来款付款",
        output_sub_label: "借出款",
        turnover_role: "external_turnover",
        turnover_action_type: "pending_collection",
        status: "active",
        source: "custom",
        priority: 4,
        priority_label: "优先级 4",
        sort_order: 3,
        direction: "expense",
        account_scope: { type: "any", values: [] },
        rules: {
          match_fields: ["counterparty_name", "purpose_text", "summary_text", "note_text"],
          exact_any: [],
          contains_any: ["往来"],
          contains_all: [],
          none_of: [],
          regex_any: [],
        },
        rule_summary: "对方户名/用途/摘要/备注包含往来",
        editable: true,
        archivable: true,
        sortable: true,
      },
    ],
    archived_rules: [],
    field_options: [
      { value: "counterparty_name", label: "对方户名" },
      { value: "purpose_text", label: "用途/交易用途" },
      { value: "summary_text", label: "摘要" },
      { value: "note_text", label: "备注/附言/客户附言" },
    ],
    turnover_third_label_options: [],
    turnover_action_type_options: [],
    permissions: { can_save: canSave },
    read_model_status: options.readModelStatus ?? "fresh",
  };
}

function pendingInvoiceRow(relationConfirmed: boolean) {
  const status = relationConfirmed
    ? {
      code: "paid_invoiced",
      label: "已支付已开票",
      reason: "关联台已确认 OA、流水和进项发票。",
      severity: "success",
      primary_action: "view_relation",
    }
    : {
      code: "paid_pending_invoice",
      label: "已支付待开票",
      reason: "设备款已支付，等待进项发票关联。",
      severity: "warning",
      primary_action: "attach_existing_invoice",
    };
  const inputInvoice = relationConfirmed ? {
    id: "iv-o-202603-001",
    invoice_no: "12561048",
    digital_invoice_no: "",
    invoice_code: "",
    issue_date: "2026-03-28",
    total_with_tax: "65540.00",
    seller_name: "智能工厂设备商",
    seller_tax_no: "91330108MA27B4011D",
    buyer_name: "杭州溯源科技有限公司",
    invoice_type: "input",
    relation_case_id: "CASE-202603-101",
    relation_status: "linked",
    relation_source: "workbench_relation",
  } : null;
  const oaSummary = relationConfirmed ? {
    id: "oa-o-202603-001",
    applicant: "陈涛",
    application_type: "供应商付款申请",
    project_name: "智能工厂项目",
    status: "completed",
    form_no: "CASE-202603-101",
    detail_available: true,
    relation_case_id: "CASE-202603-101",
    relation_status: "linked",
    relation_source: "workbench_relation",
  } : null;
  return {
    id: "bk-o-202603-001",
    bank_transaction: {
      id: "bk-o-202603-001",
      account_no: "bank-account-1138",
      counterparty_name: "智能工厂设备商",
      counterparty_account_no: "",
      counterparty_bank_name: "建设银行",
      trade_time: "2026-03-28 10:18:00",
      booked_date: "2026-03-28",
      debit_amount: "58000.00",
      credit_amount: "0.00",
      amount: "58000.00",
      balance: "130500.50",
      currency: "CNY",
      bank_name: "建设银行",
      bank_short_name: "建行",
      account_name: "杭州溯源科技有限公司",
      account_last4: "1138",
      summary: relationConfirmed ? "设备尾款已闭环" : "设备尾款待进项票",
      remark: relationConfirmed ? "关联台已确认" : "设备尾款待进项票",
      statement_serial_no: "E2E-BANK-202603-001",
      enterprise_serial_no: "E2E-ENT-202603-001",
      voucher_type: "",
      voucher_no: "",
      effective_tag_code: "equipment_payment",
      effective_tag_label: "设备款",
      effective_tag_primary_label: "成本",
      effective_tag_sub_label: "设备款",
      effective_tag_label_path: ["成本", "设备款"],
    },
    invoice_acquisition_status: status,
    input_invoices: {
      primary: inputInvoice,
      relation_count: inputInvoice ? 1 : 0,
      linked_relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      summaries: inputInvoice ? [inputInvoice] : [],
      payment_summary: relationConfirmed ? {
        paid_total: "58000.00",
        invoice_total: "65540.00",
        remaining_amount: "0.00",
        difference_amount: "7540.00",
      } : null,
    },
    oa: {
      primary: oaSummary,
      relation_count: oaSummary ? 1 : 0,
      has_multiple: false,
      detail_available: Boolean(oaSummary),
      summaries: oaSummary ? [oaSummary] : [],
    },
    invoices: inputInvoice ? [inputInvoice] : [],
    oa_applicant: oaSummary ? "陈涛" : null,
    can_create_invoice: !relationConfirmed,
    available_actions: relationConfirmed ? ["view_relation"] : ["attach_existing_invoice", "view_payment_detail"],
    relation_case_ids: inputInvoice || oaSummary ? ["CASE-202603-101"] : [],
  };
}

function pendingInvoiceSecondAttachRow(relationConfirmed: boolean) {
  const status = relationConfirmed
    ? {
      code: "paid_invoiced",
      label: "已支付已开票",
      reason: "选择已有发票已确认。",
      severity: "success",
      primary_action: "view_relation",
    }
    : {
      code: "paid_pending_invoice",
      label: "已支付待开票",
      reason: "设备补付款已支付，等待进项发票关联。",
      severity: "warning",
      primary_action: "attach_existing_invoice",
    };
  const inputInvoice = relationConfirmed ? {
    id: "iv-o-202603-002",
    invoice_no: "12561049",
    digital_invoice_no: "",
    invoice_code: "",
    issue_date: "2026-03-29",
    total_with_tax: "7540.00",
    seller_name: "智能工厂设备商二号",
    seller_tax_no: "91330108MA27B4022D",
    buyer_name: "杭州溯源科技有限公司",
    invoice_type: "input",
    relation_case_id: "CASE-202603-102",
    relation_status: "linked",
    relation_source: "workbench_relation",
  } : null;
  return {
    id: "bk-o-202603-002",
    bank_transaction: {
      id: "bk-o-202603-002",
      account_no: "bank-account-1138",
      counterparty_name: "智能工厂设备商二号",
      counterparty_account_no: "",
      counterparty_bank_name: "建设银行",
      trade_time: "2026-03-29 15:42:00",
      booked_date: "2026-03-29",
      debit_amount: "7540.00",
      credit_amount: "0.00",
      amount: "7540.00",
      balance: "122960.50",
      currency: "CNY",
      bank_name: "建设银行",
      bank_short_name: "建行",
      account_name: "杭州溯源科技有限公司",
      account_last4: "1138",
      summary: relationConfirmed ? "设备补付款已闭环" : "设备补付款待进项票",
      remark: relationConfirmed ? "选择已有发票已确认" : "设备补付款待进项票",
      statement_serial_no: "E2E-BANK-202603-002",
      enterprise_serial_no: "E2E-ENT-202603-002",
      voucher_type: "",
      voucher_no: "",
      effective_tag_code: "equipment_payment",
      effective_tag_label: "设备款",
      effective_tag_primary_label: "成本",
      effective_tag_sub_label: "设备款",
      effective_tag_label_path: ["成本", "设备款"],
    },
    invoice_acquisition_status: status,
    input_invoices: {
      primary: inputInvoice,
      relation_count: inputInvoice ? 1 : 0,
      linked_relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      summaries: inputInvoice ? [inputInvoice] : [],
      payment_summary: relationConfirmed ? {
        paid_total: "7540.00",
        invoice_total: "7540.00",
        remaining_amount: "0.00",
        difference_amount: "0.00",
      } : null,
    },
    oa: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      detail_available: false,
      summaries: [],
    },
    invoices: inputInvoice ? [inputInvoice] : [],
    oa_applicant: null,
    can_create_invoice: !relationConfirmed,
    available_actions: relationConfirmed ? ["view_relation"] : ["attach_existing_invoice", "view_payment_detail"],
    relation_case_ids: inputInvoice ? ["CASE-202603-102"] : [],
  };
}

function pendingInvoiceImportFanoutRow() {
  const inputInvoice = {
    id: "input-invoice-row-e2e-import",
    invoice_no: "SD-INV-IMPORT-E2E-001",
    digital_invoice_no: "SD-INV-IMPORT-E2E-001",
    invoice_code: "",
    issue_date: "2026-05-21",
    total_with_tax: "18320.00",
    seller_name: "发票导入进项供应商",
    seller_tax_no: "91530100MAIMPORT01X",
    buyer_name: "云南溯源科技有限公司",
    invoice_type: "input",
    relation_case_id: "IMPORT-INVOICE-E2E",
    relation_status: "linked",
    relation_source: "invoice_import",
  };
  return {
    id: "pending-invoice-import-row-e2e-001",
    bank_transaction: {
      id: "bank-payment-invoice-import-e2e-001",
      account_no: "bank-account-1138",
      counterparty_name: "发票导入进项供应商",
      counterparty_account_no: "",
      counterparty_bank_name: "建设银行",
      trade_time: "2026-05-21 10:20:00",
      booked_date: "2026-05-21",
      debit_amount: "18320.00",
      credit_amount: "0.00",
      amount: "18320.00",
      balance: "81680.00",
      currency: "CNY",
      bank_name: "建设银行",
      bank_short_name: "建行",
      account_name: "云南溯源科技有限公司",
      account_last4: "1138",
      summary: "发票导入后待找发票已闭环",
      remark: "发票导入下游刷新",
      statement_serial_no: "E2E-BANK-IMPORT-001",
      enterprise_serial_no: "E2E-ENT-IMPORT-001",
      voucher_type: "",
      voucher_no: "",
      effective_tag_code: "equipment_payment",
      effective_tag_label: "设备款",
      effective_tag_primary_label: "成本",
      effective_tag_sub_label: "设备款",
      effective_tag_label_path: ["成本", "设备款"],
    },
    invoice_acquisition_status: {
      code: "paid_invoiced",
      label: "已支付已开票",
      reason: "发票导入后待找发票 read model 已刷新。",
      severity: "success",
      primary_action: "view_relation",
    },
    input_invoices: {
      primary: inputInvoice,
      relation_count: 1,
      linked_relation_count: 1,
      has_multiple: false,
      summaries: [inputInvoice],
      payment_summary: {
        paid_total: "18320.00",
        invoice_total: "18320.00",
        remaining_amount: "0.00",
        difference_amount: "0.00",
      },
    },
    oa: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      detail_available: false,
      summaries: [],
    },
    invoices: [inputInvoice],
    oa_applicant: null,
    can_create_invoice: false,
    available_actions: ["view_relation"],
    relation_case_ids: ["IMPORT-INVOICE-E2E"],
  };
}

function pendingInvoiceRowsPayload(
  relationConfirmed: boolean,
  readModelStatus: PendingInvoiceReadModelMockStatus = "fresh",
  rowsEmpty = false,
  includeAttachExistingBatchRows = false,
  includeIncomeSummaryRows = false,
  includeInvoiceImportEvidence = false,
) {
  const rows = rowsEmpty
    ? []
    : [
      pendingInvoiceRow(relationConfirmed),
      ...(includeAttachExistingBatchRows ? [pendingInvoiceSecondAttachRow(relationConfirmed)] : []),
      ...(includeInvoiceImportEvidence ? [pendingInvoiceImportFanoutRow()] : []),
    ];
  const totalRows = rows.length;
  const missingInvoiceRows = rows.filter((row) => row.invoice_acquisition_status.code !== "paid_invoiced").length;
  return {
    direction: "expense",
    filter: "all",
    rows,
    pagination: { page: 1, page_size: 50, total: totalRows },
    summary: {
      total_rows: totalRows,
      missing_invoice_rows: missingInvoiceRows,
      create_invoice_available_rows: rows.filter((row) => row.can_create_invoice).length,
        source_summary: {
          bank_transaction_rows: totalRows,
          expense_rows: totalRows,
          income_rows: includeIncomeSummaryRows ? 2 : 0,
          current_direction_rows: totalRows,
          excluded_direction_rows: includeIncomeSummaryRows ? 2 : 0,
        },
      },
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : ["workbench_relation_not_fresh"],
    tag_dictionary: {
      version: 1,
      tags: [
        {
          code: "equipment_payment",
          label: "设备款",
          path: ["成本", "设备款"],
          output_primary_label: "成本",
          output_sub_label: "设备款",
          status: "active",
          source: "system",
        },
      ],
    },
  };
}

function pendingInvoiceFiltersFromUrl(url: URL): Array<Record<string, unknown>> {
  const rawFilters = url.searchParams.get("filters");
  if (!rawFilters) {
    return [];
  }
  try {
    const parsed = JSON.parse(rawFilters);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is Record<string, unknown> => (
        typeof item === "object" && item !== null && !Array.isArray(item)
      ))
      : [];
  } catch {
    return [];
  }
}

function pendingInvoiceFilterValues(filters: Array<Record<string, unknown>>, field: string) {
  return new Set(filters
    .filter((filter) => filter.field === field && filter.operator === "in" && Array.isArray(filter.values))
    .flatMap((filter) => (filter.values as unknown[]).map(String)));
}

function pendingInvoiceFilterSortRowsPayload(
  url: URL,
  relationConfirmed: boolean,
  readModelStatus: PendingInvoiceReadModelMockStatus = "fresh",
) {
  const filters = pendingInvoiceFiltersFromUrl(url);
  const selectedStatuses = pendingInvoiceFilterValues(filters, "status_code");
  const selectedCounterparties = pendingInvoiceFilterValues(filters, "counterparty_name");
  const selectedTags = pendingInvoiceFilterValues(filters, "transaction_tag");
  const selectedBankAccounts = pendingInvoiceFilterValues(filters, "bank_account");
  const selectedDirections = pendingInvoiceFilterValues(filters, "direction");
  const keyword = (url.searchParams.get("keyword") ?? "").trim();
  const sortField = url.searchParams.get("sort_field") ?? "trade_date";
  const sortDirection = url.searchParams.get("sort_direction") ?? "desc";
  let rows = [
    pendingInvoiceRow(relationConfirmed),
    pendingInvoiceSecondAttachRow(relationConfirmed),
  ].filter((row) => {
    const statusCode = String(row.invoice_acquisition_status.code ?? "");
    const counterpartyName = String(row.bank_transaction.counterparty_name ?? "");
    const tagCode = String(row.bank_transaction.effective_tag_code ?? "");
    const bankAccount = `${row.bank_transaction.bank_short_name} ${row.bank_transaction.account_last4}`.trim();
    const direction = Number(String(row.bank_transaction.credit_amount ?? "0").replace(/,/g, "")) > 0 ? "income" : "expense";
    const text = JSON.stringify(row);
    return (selectedStatuses.size === 0 || selectedStatuses.has(statusCode))
      && (selectedCounterparties.size === 0 || selectedCounterparties.has(counterpartyName))
      && (selectedTags.size === 0 || selectedTags.has(tagCode))
      && (selectedBankAccounts.size === 0 || selectedBankAccounts.has(bankAccount))
      && (selectedDirections.size === 0 || selectedDirections.has(direction))
      && (!keyword || text.includes(keyword));
  });
  if (sortField === "amount") {
    rows = rows.sort((left, right) => (
      Number(String(left.bank_transaction.amount ?? "0").replace(/,/g, ""))
      - Number(String(right.bank_transaction.amount ?? "0").replace(/,/g, ""))
    ));
  } else if (sortField === "counterparty_name") {
    rows = rows.sort((left, right) => String(left.bank_transaction.counterparty_name).localeCompare(String(right.bank_transaction.counterparty_name), "zh-Hans-CN"));
  } else {
    rows = rows.sort((left, right) => String(left.bank_transaction.trade_time).localeCompare(String(right.bank_transaction.trade_time)));
  }
  if (sortDirection === "desc") {
    rows = rows.reverse();
  }
  const payload = pendingInvoiceRowsPayload(
    relationConfirmed,
    readModelStatus,
    false,
    true,
  );
  payload.rows = rows;
  payload.pagination.total = rows.length;
  payload.summary.total_rows = rows.length;
  payload.summary.missing_invoice_rows = relationConfirmed ? 0 : rows.length;
  payload.summary.create_invoice_available_rows = relationConfirmed ? 0 : rows.length;
  payload.summary.source_summary.bank_transaction_rows = rows.length;
  payload.summary.source_summary.expense_rows = rows.length;
  payload.summary.source_summary.current_direction_rows = rows.length;
  return payload;
}

function pendingInvoiceIncomeRow(id: string, counterpartyName: string, amount: string, statusCode: "income_pending_invoice" | "income_no_invoice_required" | "cash_income") {
  const statusByCode = {
    income_pending_invoice: {
      code: "income_pending_invoice",
      label: "未开票",
      reason: "收入流水未关联销项发票。",
      severity: "warning",
      primary_action: "mark_income_status",
      matched_rule: {
        source: "pending_output_invoice_tag_groups",
        group: "requires_invoice",
        tag_code: "service_income",
        tag_label: "服务收入",
      },
    },
    income_no_invoice_required: {
      code: "income_no_invoice_required",
      label: "无需开票",
      reason: "已人工标记无需开票。",
      severity: "neutral",
      primary_action: "view_detail",
      matched_rule: null,
    },
    cash_income: {
      code: "cash_income",
      label: "现金收入",
      reason: "已人工标记现金收入。",
      severity: "success",
      primary_action: "view_detail",
      matched_rule: null,
    },
  } as const;
  return {
    id,
    bank_transaction: {
      id,
      account_no: "bank-account-1138",
      counterparty_name: counterpartyName,
      counterparty_account_no: "",
      counterparty_bank_name: "招商银行",
      trade_time: id === "income-batch-b" ? "2026-03-30 11:25:00" : "2026-03-30 10:10:00",
      booked_date: "2026-03-30",
      debit_amount: "0.00",
      credit_amount: amount,
      amount,
      balance: "188500.50",
      currency: "CNY",
      bank_name: "招商银行",
      bank_short_name: "招行",
      account_name: "杭州溯源科技有限公司",
      account_last4: "1138",
      summary: "服务收入待确认开票状态",
      remark: "收入批量状态 Browser E2E",
      statement_serial_no: `${id}-statement`,
      enterprise_serial_no: `${id}-enterprise`,
      voucher_type: "",
      voucher_no: "",
      effective_tag_code: "service_income",
      effective_tag_label: "服务收入",
      effective_tag_primary_label: "收入",
      effective_tag_sub_label: "服务收入",
      effective_tag_label_path: ["收入", "服务收入"],
    },
    invoice_acquisition_status: statusByCode[statusCode],
    input_invoices: {
      primary: null,
      relation_count: 0,
      linked_relation_count: 0,
      has_multiple: false,
      summaries: [],
      payment_summary: null,
    },
    oa: {
      primary: null,
      relation_count: 0,
      has_multiple: false,
      detail_available: false,
      summaries: [],
    },
    invoices: [],
    oa_applicant: null,
    can_create_invoice: false,
    available_actions: statusCode === "income_pending_invoice" ? ["mark_income_status"] : ["view_payment_detail"],
    relation_case_ids: [],
  };
}

function pendingInvoiceIncomeRowsPayload(statusCode: "income_pending_invoice" | "income_no_invoice_required" | "cash_income", readModelStatus: PendingInvoiceReadModelMockStatus = "fresh") {
  const rows = [
    pendingInvoiceIncomeRow("income-batch-a", "收入批量客户A", "300.00", statusCode),
    pendingInvoiceIncomeRow("income-batch-b", "收入批量客户B", "200.00", statusCode),
  ];
  return {
    direction: "income",
    filter: "all",
    rows,
    pagination: { page: 1, page_size: 50, total: rows.length },
    summary: {
      total_rows: rows.length,
      missing_invoice_rows: statusCode === "income_pending_invoice" ? rows.length : 0,
      create_invoice_available_rows: 0,
      source_summary: {
        bank_transaction_rows: rows.length + 1,
        expense_rows: 1,
        income_rows: rows.length,
        current_direction_rows: rows.length,
        excluded_direction_rows: 1,
      },
    },
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : ["income_status_not_fresh"],
    tag_dictionary: {
      version: 1,
      tags: [
        {
          code: "service_income",
          label: "服务收入",
          path: ["收入", "服务收入"],
          output_primary_label: "收入",
          output_sub_label: "服务收入",
          status: "active",
          source: "system",
        },
      ],
    },
  };
}

function pendingInvoiceAttachExistingCandidatesPayload(body: Record<string, unknown>) {
  const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids.map(String) : [];
  const isBatch = transactionIds.includes("bk-o-202603-002");
  const rows = [
    {
      invoice_id: "iv-o-202603-001",
      digital_invoice_no: "DIG-EQP-001",
      invoice_no: "12561048",
      issue_date: "2026-03-28",
      seller_name: "智能工厂设备商",
      seller_tax_no: "91330108MA27B4011D",
      total_with_tax: "58000.00",
      related_paid_total: "0.00",
      remaining_amount: "58000.00",
      amount_difference_abs: isBatch ? "7540.00" : "0.00",
      candidate_status: "available",
      bank_relation_status: "unlinked",
      linked_bank_transaction_count: 0,
    },
    ...(isBatch ? [{
      invoice_id: "iv-o-202603-002",
      digital_invoice_no: "DIG-EQP-002",
      invoice_no: "12561049",
      issue_date: "2026-03-29",
      seller_name: "智能工厂设备商二号",
      seller_tax_no: "91330108MA27B4022D",
      total_with_tax: "7540.00",
      related_paid_total: "0.00",
      remaining_amount: "7540.00",
      amount_difference_abs: "58000.00",
      candidate_status: "available",
      bank_relation_status: "linked",
      linked_bank_transaction_count: 1,
    }] : []),
  ];
  return {
    transaction_ids: transactionIds,
    selection_summary: {
      transaction_count: transactionIds.length,
      bank_total: isBatch ? "65540.00" : "58000.00",
    },
    rows,
    pagination: { page: 1, page_size: 20, total: rows.length },
  };
}

function pendingInvoiceAttachExistingPreviewPayload(body: Record<string, unknown>, forceConflict = false) {
  const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids.map(String) : [];
  const invoiceIds = Array.isArray(body.invoice_ids) ? body.invoice_ids.map(String) : [];
  const isBatch = transactionIds.includes("bk-o-202603-002") || invoiceIds.includes("iv-o-202603-002");
  return {
    preview_id: forceConflict ? "attach-preview-conflict" : isBatch ? "attach-preview-batch" : "attach-preview-001",
    request_key: forceConflict
      ? "pending_invoice_attach_existing:conflict"
      : isBatch
        ? "pending_invoice_attach_existing:batch"
        : "pending_invoice_attach_existing:bk-o-202603-001:iv-o-202603-001",
    can_confirm: !forceConflict,
    transaction_summaries: transactionIds.map((id) => ({
      id,
      counterparty_name: id === "bk-o-202603-002" ? "智能工厂设备商二号" : "智能工厂设备商",
      trade_time: id === "bk-o-202603-002" ? "2026-03-29" : "2026-03-28",
      debit_amount: id === "bk-o-202603-002" ? "7540.00" : "58000.00",
    })),
    invoice_summaries: invoiceIds.map((id) => ({
      id,
      digital_invoice_no: id === "iv-o-202603-002" ? "DIG-EQP-002" : "DIG-EQP-001",
      invoice_no: id === "iv-o-202603-002" ? "12561049" : "12561048",
      issue_date: id === "iv-o-202603-002" ? "2026-03-29" : "2026-03-28",
      seller_name: id === "iv-o-202603-002" ? "智能工厂设备商二号" : "智能工厂设备商",
      seller_tax_no: id === "iv-o-202603-002" ? "91330108MA27B4022D" : "91330108MA27B4011D",
      total_with_tax: id === "iv-o-202603-002" ? "7540.00" : "58000.00",
    })),
    selection_summary: {
      transaction_count: transactionIds.length,
      invoice_count: invoiceIds.length,
      bank_total: isBatch ? "65540.00" : "58000.00",
      invoice_total: isBatch ? "65540.00" : "58000.00",
      difference_amount: "0.00",
    },
    payment_impact: {
      paid_total_before: "0.00",
      paid_total_after: isBatch ? "65540.00" : "58000.00",
      invoice_total: isBatch ? "65540.00" : "58000.00",
      remaining_amount_after: "0.00",
      difference_amount_after: "0.00",
    },
    affected_months: ["2026-03"],
    warnings: [],
    conflicts: forceConflict ? [{
      relation_case_id: "CASE-CONFLICT-202603",
      relation_mode: "manual_confirmed",
      row_ids: ["bk-o-202603-001", "iv-o-202603-001"],
    }] : [],
    expires_at: "2026-06-18T10:10:00+08:00",
  };
}

function pendingInvoiceFilterOptionsPayload(relationConfirmed: boolean) {
  return {
    fields: [
      {
        field: "status_code",
        label: "发票获取状态",
        operators: ["in"],
        options: [
          {
            value: relationConfirmed ? "paid_invoiced" : "paid_pending_invoice",
            label: relationConfirmed ? "已支付已开票" : "已支付待开票",
            count: 1,
          },
        ],
      },
      {
        field: "counterparty_name",
        label: "对方户名",
        operators: ["in"],
        options: [{ value: "智能工厂设备商", label: "智能工厂设备商", count: 1 }],
      },
    ],
  };
}

function pendingInvoiceFilterSortOptionsPayload() {
  return {
    fields: [
      {
        field: "status_code",
        label: "发票获取状态",
        operators: ["in"],
        options: [{ value: "paid_pending_invoice", label: "已支付待开票", count: 2 }],
      },
      {
        field: "counterparty_name",
        label: "对方户名",
        operators: ["in"],
        options: [
          { value: "智能工厂设备商", label: "智能工厂设备商", count: 1 },
          { value: "智能工厂设备商二号", label: "智能工厂设备商二号", count: 1 },
        ],
      },
      {
        field: "transaction_tag",
        label: "流水标签",
        operators: ["in"],
        options: [{ value: "equipment_payment", label: "设备款", count: 2 }],
      },
      {
        field: "bank_account",
        label: "银行账户",
        operators: ["in"],
        options: [{ value: "建行 1138", label: "建行 1138", count: 2 }],
      },
      {
        field: "direction",
        label: "收支",
        operators: ["in"],
        options: [{ value: "expense", label: "支出", count: 2 }],
      },
    ],
  };
}

function pendingInvoiceExportPreviewPayload(relationConfirmed: boolean) {
  const row = pendingInvoiceRow(relationConfirmed);
  const invoice = row.input_invoices.primary;
  const oa = row.oa.primary;
  return {
    file_name: "pending-invoices.xlsx",
    row_count: 1,
    scope_label: "当前筛选和排序",
    columns: ["流水ID", "对方户名", "发票获取状态", "OA申请人", "进项发票号码", "关系案例", "关系状态"],
    sample_rows: [{
      流水ID: row.id,
      对方户名: row.bank_transaction.counterparty_name,
      发票获取状态: row.invoice_acquisition_status.label,
      OA申请人: oa?.applicant ?? "",
      进项发票号码: invoice?.invoice_no ?? "",
      关系案例: invoice?.relation_case_id ?? oa?.relation_case_id ?? "",
      关系状态: invoice?.relation_status ?? oa?.relation_status ?? "",
    }],
  };
}

function pendingInvoiceExportBody(relationConfirmed: boolean, url: URL) {
  const row = pendingInvoiceRow(relationConfirmed);
  const invoice = row.input_invoices.primary;
  const oa = row.oa.primary;
  return createMinimalXlsx([
    ["流水ID", "对方户名", "发票获取状态", "OA申请人", "进项发票号码", "关系案例", "关系状态", "摘要"],
    [
      row.id,
      row.bank_transaction.counterparty_name,
      row.invoice_acquisition_status.label,
      oa?.applicant ?? "",
      invoice?.invoice_no ?? "",
      invoice?.relation_case_id ?? oa?.relation_case_id ?? "",
      invoice?.relation_status ?? oa?.relation_status ?? "",
      row.bank_transaction.summary,
    ],
    [
      "导出筛选",
      url.searchParams.get("direction") ?? "",
      url.searchParams.get("filter") ?? "",
      url.searchParams.get("keyword") ?? "",
      url.searchParams.get("sort_field") ?? "",
      url.searchParams.get("sort_direction") ?? "",
      url.searchParams.get("filters") ?? "",
    ],
  ], "待找发票");
}

function bankDetailsExportBody(relationConfirmed: boolean, url: URL) {
  const relationTags = relationConfirmed ? ["有oa", "有发票"] : ["无oa", "无发票"];
  return createMinimalXlsx([
    ["交易ID", "对方户名", "银行账户", "标签", "关系案例", "OA关系", "发票关系", "关系状态", "摘要"],
    [
      "bk-o-202603-001",
      "智能工厂设备商",
      "建设银行 1138",
      "设备款",
      relationConfirmed ? "CASE-202603-101" : "",
      relationTags[0],
      relationTags[1],
      relationConfirmed ? "linked" : "unlinked",
      relationConfirmed ? "设备尾款已闭环" : "设备尾款待进项票",
    ],
    [
      "导出筛选",
      url.searchParams.get("date_from") ?? "",
      url.searchParams.get("date_to") ?? "",
      url.searchParams.get("account_key") ?? "",
      url.searchParams.get("keyword") ?? "",
      url.searchParams.get("category_code") ?? "",
    ],
  ], "银行明细");
}

function batchAccountingOaRows() {
  return [
    {
      id: "ba-oa-202604-001",
      applicant: "刘晨",
      apply_time: "2026-04-02",
      project_name: "品牌广告投放",
      amount: "700.00",
      reason: "4月日常报销，包含广告素材制作。",
      linked_invoice_row_ids: ["ba-inv-202604-001"],
    },
    {
      id: "ba-oa-202604-002",
      applicant: "王青",
      apply_time: "2026-04-03",
      project_name: "客户拜访差旅报销",
      amount: "500.00",
      reason: "上海客户拜访交通与餐费。",
      linked_invoice_row_ids: [],
    },
  ];
}

function batchAccountingBankRow(relationSubmitted: boolean) {
  return {
    id: "ba-bank-202604-001",
    trade_time: "2026-04-03 09:20:00",
    counterparty_name: "批量账务集中处理",
    direction: "expense",
    direction_label: "支出",
    amount: "1200.00",
    bank_name: "建行",
    account_last4: "8106",
    relation_id: relationSubmitted ? "BA-REL-202604-001" : "",
    version: relationSubmitted ? 2 : 1,
  };
}

function batchAccountingPagination(url: URL, bucket: BatchAccountingBucket, bankTotal: number, oaTotal: number) {
  const bankPage = Number(url.searchParams.get("bank_page") ?? "1") || 1;
  const bankPageSize = Number(url.searchParams.get("bank_page_size") ?? "200") || 200;
  const pagination: Record<string, unknown> = {
    bank_rows: { page: bankPage, page_size: bankPageSize, total: bankTotal },
  };
  if (bucket === "unsubmitted") {
    const oaPage = Number(url.searchParams.get("oa_page") ?? "1") || 1;
    const oaPageSize = Number(url.searchParams.get("oa_page_size") ?? "200") || 200;
    pagination.oa_rows = { page: oaPage, page_size: oaPageSize, total: oaTotal };
  }
  return pagination;
}

function batchAccountingPayload(
  url: URL,
  relationSubmitted: boolean,
  readModelStatus: BatchAccountingReadModelMockStatus = "fresh",
) {
  const bucket: BatchAccountingBucket = url.searchParams.get("bucket") === "submitted" ? "submitted" : "unsubmitted";
  const oaRows = batchAccountingOaRows();
  const bankRow = batchAccountingBankRow(relationSubmitted);
  const showSubmittedRelation = bucket === "submitted" && relationSubmitted;
  const showUnsubmittedRows = bucket === "unsubmitted" && !relationSubmitted;
  const bankRows = showSubmittedRelation || showUnsubmittedRows ? [bankRow] : [];
  const visibleOaRows = showUnsubmittedRows ? oaRows : [];
  return {
    summary: {
      unsubmitted_count: relationSubmitted ? 0 : 1,
      submitted_count: relationSubmitted ? 1 : 0,
    },
    bank_rows: bankRows,
    oa_rows: visibleOaRows,
    relations_by_bank_row_id: showSubmittedRelation ? {
      [bankRow.id]: {
        relation_id: "BA-REL-202604-001",
        relation: {
          relation_id: "BA-REL-202604-001",
          note: "",
          amount_check: {
            status: "matched",
            direction: "expense",
            bank_amount: "1200.00",
            oa_amount: "1200.00",
            amount_delta: "0.00",
            requires_note: false,
          },
        },
        oa_rows: oaRows,
      },
    } : {},
    pagination: batchAccountingPagination(url, bucket, bankRows.length, visibleOaRows.length),
    read_model_status: readModelStatus,
    read_model_stale_reasons: readModelStatus === "fresh" ? [] : [`batch_accounting_${readModelStatus}`],
    read_model_scope_keys: ["2026-04"],
    refresh_enqueued: readModelStatus !== "fresh",
  };
}

function batchAccountingSubmitPayload() {
  return {
    success: true,
    relation_id: "BA-REL-202604-001",
    affected_row_ids: ["ba-bank-202604-001", "ba-oa-202604-001", "ba-oa-202604-002"],
    affected_months: ["2026-04"],
    message: "已关联批量账务流水与 2 项 OA。",
  };
}

function batchAccountingWithdrawPayload() {
  return {
    success: true,
    relation_id: "BA-REL-202604-001",
    affected_row_ids: ["ba-bank-202604-001", "ba-oa-202604-001", "ba-oa-202604-002"],
    affected_months: ["2026-04"],
    message: "已撤回批量账务关联。",
  };
}

export async function installDeterministicApiMocks(page: Page, options: ApiMockOptions = {}) {
  await page.addInitScript(() => {
    Object.defineProperty(window, "EventSource", {
      configurable: true,
      value: undefined,
    });
  });

  const calls: string[] = [];
  const requestBodies = new Map<string, Record<string, unknown>[]>();
  let relationConfirmed = options.workbenchInitialRelationConfirmed === true;
  let workbenchExceptionApplied = options.workbenchInitialExceptionApplied === true;
  let workbenchRowIgnored = options.workbenchInitialRowIgnored === true;
  let workbenchConfirmSubmitAttempts = 0;
  let workbenchGroupsFailuresRemaining = options.workbenchGroupsFailuresBeforeSuccess ?? 0;
  const workbenchPageStatus = options.workbenchPageStatus ?? "fresh";
  let bankDetailsCategoryOverride: BankDetailCategoryOverride | null = null;
  let bankAutoTagRulesVersion = 1;
  let bankAutoTagRulesSalarySubLabel = "工资";
  let bankDetailsAccountsRequestCount = 0;
  let bankDetailsTransactionsRequestCount = 0;
  let bankDetailsTransactionsFailuresRemaining = 0;
  let pendingInvoiceIncomeStatus: "income_pending_invoice" | "income_no_invoice_required" | "cash_income" = "income_pending_invoice";
  let pendingInvoiceRowsFailuresRemaining =
    options.pendingInvoiceRowsFailuresBeforeSuccess ?? (options.pendingInvoiceRowsFailOnce ? 1 : 0);
  let pendingInvoiceAttachExistingConfirmFailuresRemaining =
    options.pendingInvoiceAttachExistingConfirmFailuresBeforeSuccess
    ?? (options.pendingInvoiceAttachExistingConfirmFailOnce ? 1 : 0);
  let pendingInvoiceIncomeStatusFailuresRemaining =
    options.pendingInvoiceIncomeStatusFailuresBeforeSuccess
    ?? (options.pendingInvoiceIncomeStatusFailOnce ? 1 : 0);
  let inputInvoiceUsageRowsFailuresRemaining =
    options.inputInvoiceUsageRowsFailuresBeforeSuccess ?? (options.inputInvoiceUsageRowsFailOnce ? 1 : 0);
  let costStatisticsExplorerFailuresRemaining =
    options.costStatisticsExplorerFailuresBeforeSuccess ?? (options.costStatisticsExplorerFailOnce ? 1 : 0);
  let pendingInvoiceRulesVersion = 1;
  let pendingInvoiceRulesSaved = false;
  let pendingInvoiceRulesSaveFailuresRemaining =
    options.pendingInvoiceRulesSaveFailuresBeforeSuccess
    ?? (options.pendingInvoiceRulesSaveFailOnce ? 1 : 0);
  let batchAccountingSubmitted = Boolean(options.batchAccountingInitialSubmitted);
  let batchAccountingRequestCount = 0;
  let batchAccountingFailuresRemaining =
    options.batchAccountingFailuresBeforeSuccess ?? (options.batchAccountingFailOnce ? 1 : 0);
  let turnoverClosureConfirmed = false;
  let latestImportScenario: ImportScenario = "bank";
  const importConfirmed: Record<ImportScenario, boolean> = {
    bank: false,
    invoice: false,
  };
  let etcImportConfirmed = false;
  let etcTicketBusinessBatchesFailuresRemaining =
    options.etcTicketBusinessBatchesFailuresBeforeSuccess ?? (options.etcTicketBusinessBatchesFailOnce ? 1 : 0);
  let etcTicketBusinessBatchDeleteFailuresRemaining =
    options.etcTicketBusinessBatchDeleteFailuresBeforeSuccess ?? (options.etcTicketBusinessBatchDeleteFailOnce ? 1 : 0);
  let etcTicketSourceFileDeleteFailuresRemaining =
    options.etcTicketSourceFileDeleteFailuresBeforeSuccess ?? (options.etcTicketSourceFileDeleteFailOnce ? 1 : 0);
  let etcTicketSourceFileUploadFailuresRemaining =
    options.etcTicketSourceFileUploadFailuresBeforeSuccess ?? (options.etcTicketSourceFileUploadFailOnce ? 1 : 0);
  let etcTicketOaDraftFailuresRemaining =
    options.etcTicketOaDraftFailuresBeforeSuccess ?? (options.etcTicketOaDraftFailOnce ? 1 : 0);
  let etcTicketManualStatusFailuresRemaining =
    options.etcTicketManualStatusFailuresBeforeSuccess ?? (options.etcTicketManualStatusFailOnce ? 1 : 0);
  let taxCertifiedImported = false;
  let taxSelectedInputIds = ["ti-202603-001", "ti-202603-002"];
  let taxOffsetRequestCount = 0;
  let taxOffsetPlanSaveConflictRemaining = Boolean(options.taxOffsetPlanSaveConflict);
  let outputInvoiceStatusSaved = false;
  let outputInvoiceReminderSaved = false;
  let outputInvoiceReceiptState: OutputInvoiceReceiptLifecycleState = options.outputInvoiceCollectionInitialReceiptCreated
    ? "issued"
    : "none";
  let outputInvoiceCollectionRowsFailuresRemaining =
    options.outputInvoiceCollectionRowsFailuresBeforeSuccess ?? (options.outputInvoiceCollectionRowsFailOnce ? 1 : 0);
  let outputInvoiceCollectionReceiptCreateFailuresRemaining =
    options.outputInvoiceCollectionReceiptCreateFailuresBeforeSuccess
    ?? (options.outputInvoiceCollectionReceiptCreateFailOnce ? 1 : 0);
  let outputInvoiceCollectionReceiptVoidFailuresRemaining =
    options.outputInvoiceCollectionReceiptVoidFailuresBeforeSuccess
    ?? (options.outputInvoiceCollectionReceiptVoidFailOnce ? 1 : 0);
  let outputInvoiceCollectionReceiptReissueFailuresRemaining =
    options.outputInvoiceCollectionReceiptReissueFailuresBeforeSuccess
    ?? (options.outputInvoiceCollectionReceiptReissueFailOnce ? 1 : 0);
  let outputInvoiceCollectionReminderFailuresRemaining =
    options.outputInvoiceCollectionReminderFailuresBeforeSuccess
    ?? (options.outputInvoiceCollectionReminderFailOnce ? 1 : 0);
  let outputInvoiceCollectionStatusFailuresRemaining =
    options.outputInvoiceCollectionStatusFailuresBeforeSuccess
    ?? (options.outputInvoiceCollectionStatusFailOnce ? 1 : 0);
  let outputInvoiceRedRelationConfirmed = false;
  let inputInvoiceOaSubmitted = false;
  let inputInvoicePaymentRulesVersion = 1;
  let inputInvoicePaymentRulesSaved = false;
  let oaPendingPaymentRowsFailuresRemaining =
    options.oaPendingPaymentRowsFailuresBeforeSuccess ?? (options.oaPendingPaymentRowsFailOnce ? 1 : 0);
  let oaPendingPaymentBankLinked = false;
  let oaPendingPaymentWritebackPaidConfirmed = false;
  let etcBusinessBatchStatus: EtcBusinessBatchStatus = options.etcTicketInitialBusinessBatchStatus ?? "imported";
  let etcBusinessBatchDeleted = false;
  let etcWorkflowSourceFileDeleted = false;
  let etcWorkflowTicketRootUploaded = false;
  const etcWorkflowTaskId = options.etcTicketWorkflowTaskMatchesBusinessBatch
    ? "etc-recon-e2e-001"
    : "etc-recon-workflow-e2e-001";
  let bankFlowRuleBatchStatus: BankFlowRuleBrowserBatchStatus = "draft";
  let bankFlowRuleBatchFailuresRemaining =
    options.bankFlowRuleBatchFailuresBeforeSuccess ?? (options.bankFlowRuleBatchFailOnce ? 1 : 0);
  let bankFlowRuleBatchesRequestCount = 0;
  const bankFlowRuleMutationScope = options.bankFlowRuleBatchScenario === "internalTransferPairs" ? "2026-01" : "2026-05";
  let bankFlowRuleTagRules = [...defaultBankFlowRuleBatchTagRules];
  let turnoverLedgerFailuresRemaining =
    options.turnoverLedgerFailuresBeforeSuccess ?? (options.turnoverLedgerFailOnce ? 1 : 0);
  let turnoverLedgerRequestCount = 0;
  let turnoverSelectedTagCodes = ["external_turnover_payment", "external_turnover_collection"];
  let turnoverTagSelectionVersion = 1;
  let settingsCompletedProjectIds: string[] = [];
  let settingsAccessControl = {
    allowedUsernames: [] as string[],
    readonlyExportUsernames: [] as string[],
    adminUsernames: ["YNSYLP005"],
  };
  let settingsDataResetJob: {
    action: SettingsDataResetAction;
    jobId: string;
    pollCount: number;
    status: "running" | "completed";
  } | null = null;
  let settingsDataResetCompletedAction: SettingsDataResetAction | null = null;
  await page.route(/.*\/(api\/|imports\/files\/|imports\/templates)/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeApiPath(url.pathname);
    const methodAndPath = `${request.method()} ${path}`;
    calls.push(methodAndPath);
    if (request.method() !== "GET") {
      const existingBodies = requestBodies.get(methodAndPath) ?? [];
      existingBodies.push(parseJsonBody(request.postData()));
      requestBodies.set(methodAndPath, existingBodies);
    }

    if (path === "/api/session/me") {
      if (options.sessionMode === "expired") {
        return json(route, { error: "session_expired", message: "OA 会话已失效" }, 401);
      }
      if (options.sessionMode === "error") {
        return json(route, { error: "session_error", message: "会话校验失败，请稍后重试。" }, 503);
      }
      const accessTier = options.sessionMode === "admin"
        ? "admin"
        : options.sessionMode === "read_export_only"
          ? "read_export_only"
          : options.sessionMode === "forbidden"
            ? "denied"
            : "full_access";
      return json(route, sessionPayload(accessTier));
    }

    if (path === "/api/background-jobs/active") {
      return json(route, { jobs: [] });
    }

    if (path === "/api/app-health") {
      return json(route, appHealthPayload(options));
    }

    if (path === "/api/oa-sync/status") {
      return json(route, oaSyncPayload(options.oaSyncMode));
    }

    if (path === "/api/workbench/refresh-status") {
      return json(route, workbenchRefreshStatusPayload(options.workbenchRefreshStatus));
    }

    if (path === "/api/operation-barrier/status") {
      return json(route, operationBarrierPayload(options.operationBarrierMode));
    }

    if (path === "/api/workbench/settings") {
      if (request.method() === "POST") {
        const body = parseJsonBody(request.postData()) as {
          completed_project_ids?: unknown;
          allowed_usernames?: unknown;
          readonly_export_usernames?: unknown;
          admin_usernames?: unknown;
        };
        settingsCompletedProjectIds = Array.isArray(body.completed_project_ids)
          ? body.completed_project_ids.map((item) => String(item))
          : [];
        settingsAccessControl = {
          allowedUsernames: Array.isArray(body.allowed_usernames)
            ? body.allowed_usernames.map((item) => String(item))
            : [],
          readonlyExportUsernames: Array.isArray(body.readonly_export_usernames)
            ? body.readonly_export_usernames.map((item) => String(item))
            : [],
          adminUsernames: Array.isArray(body.admin_usernames)
            ? body.admin_usernames.map((item) => String(item))
            : ["YNSYLP005"],
        };
      }
      return json(route, workbenchSettingsPayload(
        settingsCompletedProjectIds,
        Boolean(options.settingsProjectScopeFanout),
        settingsAccessControl,
      ));
    }

    if (path === "/api/workbench/settings/oa-applicant-credentials") {
      return json(route, oaApplicantCredentialsPayload());
    }

    const oaApplicantCredentialMatch = path.match(/^\/api\/workbench\/settings\/oa-applicant-credentials\/([^/]+)$/);
    if (oaApplicantCredentialMatch && request.method() === "PUT") {
      const targetApplicantCode = decodeURIComponent(oaApplicantCredentialMatch[1] ?? "");
      const body = parseJsonBody(request.postData()) as {
        targetApplicantName?: string;
        oaUsername?: string;
      };
      return json(route, {
        credential: {
          target_applicant_code: targetApplicantCode,
          target_applicant_name: body.targetApplicantName ?? targetApplicantCode,
          oa_username: body.oaUsername ?? targetApplicantCode,
          credential_status: "configured",
          has_credential: true,
          enabled: true,
        },
      });
    }
    if (oaApplicantCredentialMatch && request.method() === "DELETE") {
      const targetApplicantCode = decodeURIComponent(oaApplicantCredentialMatch[1] ?? "");
      return json(route, {
        credential: {
          target_applicant_code: targetApplicantCode,
          target_applicant_name: targetApplicantCode,
          oa_username: targetApplicantCode,
          credential_status: "missing",
          has_credential: false,
          enabled: true,
        },
      });
    }

    if (path === "/api/workbench/settings/data-reset/jobs/active") {
      const activeJob = settingsDataResetJob?.status === "running"
        ? settingsDataResetJobPayload(settingsDataResetJob).job
        : null;
      return json(route, { job: activeJob });
    }

    if (path === "/api/workbench/settings/data-reset/jobs") {
      const body = JSON.parse(request.postData() || "{}") as {
        action?: SettingsDataResetAction;
        oa_password?: string;
      };
      const action = body.action ?? "reset_bank_transactions";
      if (!body.oa_password) {
        return json(route, {
          error: "oa_password_required",
          message: "当前 OA 用户密码复核失败，未执行数据重置。",
        }, 403);
      }
      settingsDataResetJob = {
        action,
        jobId: "settings-reset-job-e2e-001",
        pollCount: 0,
        status: "running",
      };
      return json(route, settingsDataResetJobPayload(settingsDataResetJob), 202);
    }

    const settingsDataResetJobMatch = path.match(/^\/api\/workbench\/settings\/data-reset\/jobs\/([^/]+)$/);
    if (settingsDataResetJobMatch) {
      if (!settingsDataResetJob) {
        return json(route, {
          error: "settings_data_reset_job_not_found",
          message: "数据重置任务不存在。",
        }, 404);
      }
      settingsDataResetJob.pollCount += 1;
      if (settingsDataResetJob.pollCount >= 2) {
        settingsDataResetJob.status = "completed";
        settingsDataResetCompletedAction = settingsDataResetJob.action;
      }
      return json(route, settingsDataResetJobPayload(settingsDataResetJob));
    }

    if (path === "/api/etc/reconciliation-tasks/ready-for-import") {
      return json(route, etcReadyTasksPayload());
    }

    if (path === "/api/etc/import/preview") {
      return json(route, etcImportPayload(false));
    }

    if (path === "/api/etc/import/confirm") {
      if (options.etcImportConfirmStaleReconciliationTask) {
        return json(route, {
          error: "stale_reconciliation_task_preview",
          message: "ETC 对账任务已更新，请重新预览。",
        }, 409);
      }
      if (options.etcImportConfirmPreviewStale) {
        return json(route, {
          error: "preview_stale",
          message: "ETC 导入预览已过期，请重新预览。",
        }, 409);
      }
      if (options.etcImportConfirmError) {
        return json(route, {
          error: "etc_import_confirm_failed",
          message: "ETC导入任务创建失败，请稍后重试。",
        }, 500);
      }
      etcImportConfirmed = true;
      return json(route, etcImportPayload(true));
    }

    if (path === "/api/etc/reconciliation-tasks") {
      return json(route, {
        tasks: options.etcTicketReconciliationWorkflow
          ? [etcReconciliationWorkflowTaskPayload({
            sourceFileDeleted: etcWorkflowSourceFileDeleted,
            taskId: etcWorkflowTaskId,
            ticketRootUploaded: etcWorkflowTicketRootUploaded,
          })]
          : [],
      });
    }

    if (path === `/api/etc/reconciliation-tasks/${etcWorkflowTaskId}` && request.method() === "GET") {
      return json(route, etcReconciliationWorkflowTaskPayload({
        sourceFileDeleted: etcWorkflowSourceFileDeleted,
        taskId: etcWorkflowTaskId,
        ticketRootUploaded: etcWorkflowTicketRootUploaded,
      }));
    }

    if (path === `/api/etc/reconciliation-tasks/${etcWorkflowTaskId}/source-files/etc-source-e2e-001` && request.method() === "DELETE") {
      if (etcTicketSourceFileDeleteFailuresRemaining > 0) {
        etcTicketSourceFileDeleteFailuresRemaining -= 1;
        return json(route, {
          error: "etc_source_file_delete_temporarily_unavailable",
          message: "ETC源文件删除暂时失败，请重试。",
        }, 503);
      }
      etcWorkflowSourceFileDeleted = true;
      return json(route, etcReconciliationWorkflowTaskPayload({
        sourceFileDeleted: etcWorkflowSourceFileDeleted,
        taskId: etcWorkflowTaskId,
        ticketRootUploaded: etcWorkflowTicketRootUploaded,
      }));
    }

    if (path === `/api/etc/reconciliation-tasks/${etcWorkflowTaskId}/ticket-root-files` && request.method() === "POST") {
      if (etcTicketSourceFileUploadFailuresRemaining > 0) {
        etcTicketSourceFileUploadFailuresRemaining -= 1;
        return json(route, {
          error: "etc_source_file_upload_temporarily_unavailable",
          message: "ETC票根网文件上传暂时失败，请重试。",
        }, 503);
      }
      etcWorkflowTicketRootUploaded = true;
      return json(route, etcReconciliationWorkflowTaskPayload({
        sourceFileDeleted: etcWorkflowSourceFileDeleted,
        taskId: etcWorkflowTaskId,
        ticketRootUploaded: etcWorkflowTicketRootUploaded,
      }));
    }

    if (path === "/api/etc/business-batches") {
      if (etcTicketBusinessBatchesFailuresRemaining > 0) {
        etcTicketBusinessBatchesFailuresRemaining -= 1;
        return json(route, {
          error: "etc_business_batches_temporarily_unavailable",
          message: "ETC业务批次加载暂时失败，请刷新后重试。",
        }, 503);
      }
      if (options.etcImportDownstreamFanout && !etcImportConfirmed) {
        return json(route, {
          items: [],
          counts: { unsubmitted: 0, staged: 0, submitted: 0 },
          pagination: { page: 1, page_size: 100, total: 0 },
        });
      }
      return json(route, etcBusinessBatchListPayload(url.searchParams.get("bucket"), etcBusinessBatchStatus, etcBusinessBatchDeleted));
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001") {
      if (request.method() === "GET") {
        if (etcBusinessBatchDeleted) {
          return json(route, {
            error: "etc_business_batch_not_found",
            message: "ETC业务批次不存在。",
          }, 404);
        }
        return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
      }
      if (request.method() === "DELETE") {
        if (etcTicketBusinessBatchDeleteFailuresRemaining > 0) {
          etcTicketBusinessBatchDeleteFailuresRemaining -= 1;
          return json(route, {
            error: "etc_business_batch_delete_temporarily_unavailable",
            message: "ETC业务批次删除暂时失败，请重试。",
          }, 503);
        }
        etcBusinessBatchDeleted = true;
        return json(route, { ok: true });
      }
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001/oa-draft") {
      if (etcTicketOaDraftFailuresRemaining > 0) {
        etcTicketOaDraftFailuresRemaining -= 1;
        return json(route, {
          error: "etc_oa_draft_temporarily_unavailable",
          message: "审批草稿创建暂时失败，请重试。",
        }, 503);
      }
      etcBusinessBatchStatus = "oa_confirmation_pending";
      return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001/manual-oa-status") {
      if (etcTicketManualStatusFailuresRemaining > 0) {
        etcTicketManualStatusFailuresRemaining -= 1;
        return json(route, {
          error: "etc_manual_oa_status_temporarily_unavailable",
          message: "人工确认暂时失败，请重试。",
        }, 503);
      }
      const body = JSON.parse(request.postData() || "{}") as { decision?: string };
      etcBusinessBatchStatus = body.decision === "submitted" ? "manually_marked_submitted" : "not_submitted";
      return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
    }

    const outputInvoiceDownstreamConfirmed = outputInvoiceRedRelationConfirmed && Boolean(options.outputInvoiceDownstreamFanout);
    const invoiceImportDownstreamConfirmed = importConfirmed.invoice && Boolean(options.invoiceImportDownstreamFanout);
    const etcImportDownstreamConfirmed = etcImportConfirmed && Boolean(options.etcImportDownstreamFanout);
    const bankImportDownstreamConfirmed = importConfirmed.bank && Boolean(options.bankImportDownstreamFanout);
    const bankFlowRuleCostConfirmed = bankFlowRuleBatchStatus === "submitted" && Boolean(options.bankFlowRuleCostFanout);
    const turnoverCostConfirmed = turnoverClosureConfirmed && Boolean(options.turnoverCostFanout);
    const costCompletedProjectNames = new Set(completedCostProjectNames);
    if (settingsCompletedProjectIds.includes(settingsCostProject.id)) {
      costCompletedProjectNames.add(settingsCostProject.project_name);
    }

    if (path === "/api/tax-offset") {
      taxOffsetRequestCount += 1;
      const taxOffsetReadModelStatus = options.taxOffsetReadModelStatuses?.[
        Math.min(taxOffsetRequestCount - 1, options.taxOffsetReadModelStatuses.length - 1)
      ] ?? options.taxOffsetReadModelStatus ?? "fresh";
      return json(route, taxOffsetPayload(
        taxSelectedInputIds,
        taxCertifiedImported,
        invoiceImportDownstreamConfirmed,
        etcImportDownstreamConfirmed,
        taxOffsetReadModelStatus,
        Boolean(options.taxOffsetLargeDataset),
      ), taxOffsetReadModelStatus === "fresh" ? 200 : 202);
    }

    if (path === "/api/tax-offset/calculate") {
      const body = JSON.parse(request.postData() || "{}") as { selected_input_ids?: string[] };
      const selectedInputIds = Array.isArray(body.selected_input_ids) ? body.selected_input_ids : taxSelectedInputIds;
      return json(route, {
        month: "2026-03",
        summary: taxSummary(
          selectedInputIds,
          taxCertifiedImported,
          invoiceImportDownstreamConfirmed,
          etcImportDownstreamConfirmed,
        ),
      });
    }

    if (path === "/api/tax-offset/plans") {
      if (taxOffsetPlanSaveConflictRemaining) {
        taxOffsetPlanSaveConflictRemaining = false;
        return json(route, {
          error: "tax_offset_read_model_version_conflict",
          message: "税金抵扣数据已变化，请刷新后重新保存。",
          read_model_status: "stale",
          read_model_scope_key: "2026-03",
        }, 409);
      }
      const body = JSON.parse(request.postData() || "{}") as { selected_input_ids?: string[] };
      taxSelectedInputIds = Array.isArray(body.selected_input_ids) ? body.selected_input_ids : taxSelectedInputIds;
      return json(route, {
        status: "saved",
        plan: {
          id: "tax-offset-plan-e2e-001",
          month: "2026-03",
          selected_output_ids: ["to-202603-001"],
          selected_input_ids: taxSelectedInputIds,
          summary: taxSummary(
            taxSelectedInputIds,
            taxCertifiedImported,
            invoiceImportDownstreamConfirmed,
            etcImportDownstreamConfirmed,
          ),
          read_model_scope_key: "2026-03",
          source_versions: taxSourceVersions("2026-03"),
          updated_at: "2026-06-17T01:00:00Z",
        },
      });
    }

    if (path === "/api/tax-offset/certified-import/preview") {
      return json(route, taxCertifiedImportPreviewPayload());
    }

    if (path === "/api/tax-offset/certified-import/confirm") {
      taxCertifiedImported = true;
      taxSelectedInputIds = ["ti-202603-002"];
      return json(route, taxCertifiedImportConfirmPayload());
    }

    if (path === "/api/input-invoice-usage/rows") {
      if (inputInvoiceUsageRowsFailuresRemaining > 0) {
        inputInvoiceUsageRowsFailuresRemaining -= 1;
        return json(route, {
          error: "input_invoice_usage_rows_temporarily_unavailable",
          message: "进项发票使用情况加载暂时失败，请刷新后重试。",
        }, 503);
      }
      if (options.inputInvoiceUsageFilterSortRows) {
        return json(route, inputInvoiceUsageFilterSortRowsPayload(url));
      }
      const readModelStatus = options.inputInvoiceUsageReadModelStatus ?? "fresh";
      return json(route, inputInvoiceUsageRowsPayload(
        relationConfirmed,
        Boolean(options.inputInvoiceUsageRelationFanout),
        readModelStatus,
        Boolean(options.inputInvoiceUsageRelationDetailReadModelStatus),
        inputInvoicePaymentRulesSaved,
        Boolean(options.inputInvoiceUsagePaymentRulesSaveFlow),
        invoiceImportDownstreamConfirmed,
      ), readModelStatus === "fresh" ? 200 : 202);
    }

    if (path === "/api/input-invoice-usage/filter-options") {
      if (options.inputInvoiceUsageFilterSortRows) {
        return json(route, inputInvoiceUsageFilterSortOptionsPayload());
      }
      const readModelStatus = options.inputInvoiceUsageReadModelStatus ?? "fresh";
      return json(
        route,
        inputInvoiceUsageFilterOptionsPayload(readModelStatus),
        readModelStatus === "fresh" ? 200 : 202,
      );
    }

    if (path.startsWith("/api/input-invoice-usage/rows/") && path.endsWith("/relation-details")) {
      const readModelStatus = options.inputInvoiceUsageRelationDetailReadModelStatus ?? "fresh";
      return json(
        route,
        inputInvoiceUsageRelationDetailPayload(url.searchParams.get("kind") ?? "oa", readModelStatus),
        readModelStatus === "fresh" ? 200 : 202,
      );
    }

    if (path === "/api/input-invoice-usage/export-preview") {
      if (options.inputInvoiceUsageExportRowLimitError) {
        return json(route, {
          error: {
            code: "input_invoice_usage_export_row_limit_exceeded",
            message: "进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。",
            details: { total: 20001, limit: 20000 },
          },
        }, 400);
      }
      const readModelStatus = options.inputInvoiceUsageExportReadModelStatus
        ?? options.inputInvoiceUsageReadModelStatus
        ?? "fresh";
      return json(
        route,
        inputInvoiceUsageExportPreviewPayload(readModelStatus),
        readModelStatus === "fresh" ? 200 : 202,
      );
    }

    if (path === "/api/input-invoice-usage/export") {
      const readModelStatus = options.inputInvoiceUsageExportReadModelStatus
        ?? options.inputInvoiceUsageReadModelStatus
        ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(route, {
          read_model_status: "refreshing",
          readModelStatus: "refreshing",
          message: "进项发票使用情况数据正在刷新，请稍后重试导出。",
        }, 202);
      }
      if (options.inputInvoiceUsageExportRowLimitError) {
        return json(route, {
          error: {
            code: "input_invoice_usage_export_row_limit_exceeded",
            message: "进项发票使用情况导出超过 20000 行，请缩小筛选范围后重试。",
            details: { total: 20001, limit: 20000 },
          },
        }, 400);
      }
      return route.fulfill({
        status: 200,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''input-invoice-usage.xlsx",
        },
        body: inputInvoiceUsageExportBody(url),
      });
    }

    if (path === "/api/input-invoice-usage/payment-status-rules") {
      const canSaveInputInvoicePaymentRules = options.sessionMode !== "read_export_only"
        && options.sessionMode !== "forbidden"
        && options.sessionMode !== "expired"
        && options.sessionMode !== "error";
      if (request.method() === "GET") {
        return json(route, inputInvoiceUsagePaymentStatusRulesPayload(canSaveInputInvoicePaymentRules, {
          version: inputInvoicePaymentRulesVersion,
          waitingPaymentLabel: inputInvoicePaymentRulesSaved ? "待付款（规则保存后刷新）" : undefined,
        }));
      }
      if (request.method() === "PUT") {
        const body = parseJsonBody(request.postData()) as {
          expectedVersion?: unknown;
          expected_version?: unknown;
          idempotencyKey?: unknown;
          idempotency_key?: unknown;
          rules?: Array<{ id?: string; label?: string }>;
        };
        if (options.inputInvoiceUsagePaymentRulesSaveFlow) {
          const expectedVersion = Number(body.expectedVersion ?? body.expected_version);
          const idempotencyKey = String(body.idempotencyKey ?? body.idempotency_key ?? "").trim();
          if (!idempotencyKey) {
            return json(route, {
              error: {
                code: "input_invoice_usage_payment_rules_idempotency_key_required",
                message: "保存支付状态规则需要 idempotencyKey。",
              },
            }, 400);
          }
          if (expectedVersion !== inputInvoicePaymentRulesVersion) {
            return json(route, {
              error: {
                code: "input_invoice_usage_payment_rules_version_conflict",
                message: "支付状态规则版本冲突。",
                details: { expectedVersion, actualVersion: inputInvoicePaymentRulesVersion },
              },
            }, 409);
          }
          inputInvoicePaymentRulesSaved = true;
          inputInvoicePaymentRulesVersion += 1;
        }
        return json(route, inputInvoiceUsagePaymentStatusRulesPayload(canSaveInputInvoicePaymentRules, {
          version: inputInvoicePaymentRulesVersion,
          waitingPaymentLabel: inputInvoicePaymentRulesSaved ? "待付款（规则保存后刷新）" : undefined,
        }));
      }
    }

    if (path === "/api/input-invoice-usage/oa-reverse/preview") {
      const body = JSON.parse(request.postData() || "{}") as {
        invoiceIds?: string[];
        invoice_ids?: string[];
      };
      const canCreateDraft = options.sessionMode !== "read_export_only"
        && options.sessionMode !== "forbidden"
        && options.sessionMode !== "expired"
        && options.sessionMode !== "error";
      return json(route, inputInvoiceOaReversePreviewPayload(
        body.invoiceIds ?? body.invoice_ids ?? [],
        relationConfirmed,
        Boolean(options.inputInvoiceUsageRelationFanout),
        canCreateDraft,
      ));
    }

    if (path === "/api/input-invoice-usage/oa-reverse/oa-draft") {
      return json(route, inputInvoiceOaReverseDraftPayload("oa_draft_created"));
    }

    if (path === "/api/input-invoice-usage/oa-reverse/submitted-history") {
      return json(route, inputInvoiceOaReverseSubmittedHistoryPayload(inputInvoiceOaSubmitted));
    }

    if (path === "/api/input-invoice-usage/oa-reverse/batches/input-oa-reverse-batch-e2e-001/manual-oa-status") {
      const body = JSON.parse(request.postData() || "{}") as { decision?: string };
      inputInvoiceOaSubmitted = body.decision === "submitted";
      return json(route, inputInvoiceOaReverseDraftPayload(inputInvoiceOaSubmitted ? "submitted_confirmed" : "oa_draft_created"));
    }

    if (path === "/api/oa-pending-payments/rows") {
      if (oaPendingPaymentRowsFailuresRemaining > 0) {
        oaPendingPaymentRowsFailuresRemaining -= 1;
        return json(route, {
          error: "oa_pending_payment_rows_temporarily_unavailable",
          message: "OA 待付款核对加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatus = options.oaPendingPaymentReadModelStatus ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(
          route,
          oaPendingPaymentNonFreshRowsPayload(readModelStatus),
          readModelStatus === "refreshing" ? 202 : 200,
        );
      }
      if (options.oaPendingPaymentBankLinkFlow && url.searchParams.get("view_mode") === "in_progress") {
        return json(route, oaPendingPaymentBankLinkRowsPayload(oaPendingPaymentBankLinked));
      }
      if (options.oaPendingPaymentWritebackPaidFlow && url.searchParams.get("view_mode") === "in_progress") {
        return json(route, oaPendingPaymentWritebackPaidRowsPayload(oaPendingPaymentWritebackPaidConfirmed));
      }
      if (options.oaPendingPaymentRelationFanout) {
        return json(route, oaPendingPaymentRelationFanoutRowsPayload(relationConfirmed));
      }
      return json(route, oaPendingPaymentRowsPayload(invoiceImportDownstreamConfirmed));
    }

    if (path === "/api/oa-pending-payments/bank-transaction-candidates") {
      return json(route, oaPendingPaymentBankCandidatesPayload(url.searchParams.get("relation_status") ?? "all"));
    }

    if (path === "/api/oa-pending-payments/link-bank-transactions") {
      await delay(Math.max(0, options.oaPendingPaymentBankLinkDelayMs ?? 0));
      if (options.oaPendingPaymentBankLinkError) {
        return json(route, {
          error: "oa_pending_payment_link_bank_transactions_rejected",
          message: "支出流水关联校验失败，未创建关联关系。",
          affected_oa_row_ids: [],
          affected_bank_transaction_ids: [],
          readModelRefresh: { scopeKeys: [], enqueued: false, targetSeconds: 0 },
        }, 409);
      }
      oaPendingPaymentBankLinked = true;
      return json(route, {
        success: true,
        action: "oa_pending_payment_link_bank_transactions",
        oaRowIds: ["oa-bank-link-e2e-001"],
        bankTransactionIds: ["bank-link-e2e-001"],
        relation: {
          status: "confirmed",
          origin: "oa_pending_payment_in_progress",
        },
        autoWriteback: { code: "written", label: "已写回", matched: true, writebackCount: 1 },
        oaPaymentWritebacks: [
          { code: "written", label: "已写回", flowIds: ["flow-bank-link-e2e-001"], syncStatus: "ready" },
        ],
        readModelRefresh: { scopeKeys: ["2026-05"], enqueued: true, targetSeconds: 1 },
      });
    }

    if (path === "/api/oa-pending-payments/writeback-paid") {
      await delay(Math.max(0, options.oaPendingPaymentWritebackPaidDelayMs ?? 0));
      if (options.oaPendingPaymentWritebackPaidError) {
        return json(route, {
          error: "oa_pending_payment_writeback_paid_rejected",
          message: "OA 写回校验失败，未写入支付状态。",
          affected_oa_row_ids: [],
          affected_bank_transaction_ids: [],
          read_model_refresh: { scopeKeys: [], enqueued: false, targetSeconds: 0 },
        }, 409);
      }
      if (options.oaPendingPaymentWritebackPaidFlow) {
        oaPendingPaymentWritebackPaidConfirmed = true;
        return json(route, {
          success: true,
          action: "oa_pending_payment_writeback_paid",
          oaRowIds: ["oa-writeback-paid-e2e-001"],
          writebackCount: 1,
          oaPaymentWritebacks: [
            {
              code: "written",
              label: "已写回",
              flowIds: ["flow-writeback-paid-e2e-001"],
              syncStatus: "ready",
            },
          ],
          readModelRefresh: { scopeKeys: ["2026-05"], enqueued: true, targetSeconds: 1 },
        });
      }
      return json(route, {
        success: true,
        action: "oa_pending_payment_writeback_paid",
        oaRowIds: [],
        writebackCount: 0,
        oaPaymentWritebacks: [],
        readModelRefresh: { scopeKeys: [], enqueued: false, targetSeconds: 0 },
      });
    }

    if (path === "/api/oa-pending-payments/oa/oa-payment-e2e-001/detail") {
      if (options.oaPendingPaymentDetailReadModelRefreshing) {
        return json(route, oaPendingPaymentUnavailableDetailPayload(), 202);
      }
      return json(route, oaPendingPaymentDetailPayload("oa"));
    }

    if (path === "/api/oa-pending-payments/bank-transactions/bank-payment-e2e-001/detail") {
      return json(route, oaPendingPaymentDetailPayload("bank"));
    }

    if (path === "/api/oa-pending-payments/invoices/invoice-payment-e2e-001/detail") {
      return json(route, oaPendingPaymentDetailPayload("invoice"));
    }

    if (path === "/api/pending-invoices/rules") {
      if (request.method() === "PUT") {
        if (pendingInvoiceRulesSaveFailuresRemaining > 0) {
          pendingInvoiceRulesSaveFailuresRemaining -= 1;
          return json(route, {
            error: "pending_invoice_rules_save_temporarily_unavailable",
            message: "待找发票规则保存暂时失败，请重试。",
          }, 503);
        }
        pendingInvoiceRulesVersion += 1;
        pendingInvoiceRulesSaved = true;
        return json(route, pendingInvoiceExpenseRulesPayload({
          canSave: Boolean(options.pendingInvoiceRulesSaveFlow),
          readModelStatus: "refreshing",
          version: pendingInvoiceRulesVersion,
        }));
      }
      return json(route, pendingInvoiceExpenseRulesPayload({
        canSave: Boolean(options.pendingInvoiceRulesSaveFlow),
        readModelStatus: pendingInvoiceRulesSaved ? "refreshing" : "fresh",
        version: pendingInvoiceRulesVersion,
      }));
    }

    if (path === "/api/cost-statistics/tag-rules") {
      return json(route, {
        version: 1,
        bank_auto_tag_rules_version: 8,
        default_selection_applied: true,
        selected_tag_codes: ["fee", "__uncategorized__"],
        effective_selected_tag_codes: ["fee", "__uncategorized__"],
        inactive_selected_tag_codes: [],
        active_tags: [
          {
            code: "fee",
            label: "材料费",
            path: ["费用", "材料费"],
            source: "custom",
            status: "active",
            direction: "expense",
            output_primary_label: "费用",
            output_sub_label: "材料费",
          },
          {
            code: "__uncategorized__",
            label: "未分类",
            path: ["未分类", "未分类"],
            source: "system",
            status: "active",
            direction: "expense",
            output_primary_label: "未分类",
            output_sub_label: "未分类",
          },
        ],
        can_save: true,
        operation_barrier_targets: [],
      });
    }

    if (path === "/api/cost-statistics/explorer") {
      const explorerScope = url.searchParams.get("scope") ?? "all";
      const explorerProjectScope = url.searchParams.get("project_scope") ?? "active";
      if (costStatisticsExplorerFailuresRemaining > 0 && explorerScope !== "all") {
        costStatisticsExplorerFailuresRemaining -= 1;
        return json(route, {
          error: "cost_statistics_explorer_temporarily_unavailable",
          message: "成本统计数据加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatus = options.costStatisticsReadModelStatus ?? "fresh";
      const payload = costStatisticsExplorerPayload(
        "all",
        explorerProjectScope,
        relationConfirmed || outputInvoiceDownstreamConfirmed,
        Boolean(options.costStatisticsRelationFanout) || outputInvoiceDownstreamConfirmed,
        invoiceImportDownstreamConfirmed,
        etcImportDownstreamConfirmed,
        bankImportDownstreamConfirmed,
        bankFlowRuleCostConfirmed,
        turnoverCostConfirmed,
        readModelStatus,
        costCompletedProjectNames,
        Boolean(options.costStatisticsLargeDataset),
      );
      return json(
        route,
        costStatisticsExplorerPagePayload(url, payload, readModelStatus),
        readModelStatus === "refreshing" ? 202 : 200,
      );
    }

    if (path === "/api/cost-statistics/export-preview") {
      const exportReadModelStatus = options.costStatisticsExportReadModelStatus ?? "fresh";
      if (exportReadModelStatus !== "fresh") {
        return json(route, {
          error: "cost_statistics_read_model_not_fresh",
          message: "成本统计数据正在刷新，请稍后重试导出。",
          read_model_status: exportReadModelStatus,
          refresh_enqueued: true,
        }, exportReadModelStatus === "refreshing" ? 202 : 409);
      }
      return json(route, costStatisticsExportPreviewPayload(
        url,
        relationConfirmed || outputInvoiceDownstreamConfirmed,
        Boolean(options.costStatisticsRelationFanout) || outputInvoiceDownstreamConfirmed,
        invoiceImportDownstreamConfirmed,
        etcImportDownstreamConfirmed,
        bankImportDownstreamConfirmed,
        bankFlowRuleCostConfirmed,
        turnoverCostConfirmed,
      ));
    }

    if (path === "/api/cost-statistics/export") {
      const exportReadModelStatus = options.costStatisticsExportReadModelStatus ?? "fresh";
      if (exportReadModelStatus !== "fresh") {
        return json(route, {
          error: "cost_statistics_read_model_not_fresh",
          message: "成本统计数据正在刷新，请稍后重试导出。",
          read_model_status: exportReadModelStatus,
          refresh_enqueued: true,
        }, exportReadModelStatus === "refreshing" ? 202 : 409);
      }
      if (options.costStatisticsExportDownloadSuccess) {
        return route.fulfill({
          status: 200,
          contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          headers: {
            "Content-Disposition": "attachment; filename*=UTF-8''%E6%88%90%E6%9C%AC%E7%BB%9F%E8%AE%A1_%E5%85%A8%E9%83%A8%E6%9C%9F%E9%97%B4_%E6%8C%89%E6%97%B6%E9%97%B4%E7%BB%9F%E8%AE%A1.xlsx",
          },
          body: costStatisticsExportBody(
            url,
            relationConfirmed || outputInvoiceDownstreamConfirmed,
            Boolean(options.costStatisticsRelationFanout) || outputInvoiceDownstreamConfirmed,
            invoiceImportDownstreamConfirmed,
            etcImportDownstreamConfirmed,
            bankImportDownstreamConfirmed,
            bankFlowRuleCostConfirmed,
            turnoverCostConfirmed,
          ),
        });
      }
      return json(route, {
        error: "cost_statistics_export_row_limit_exceeded",
        message: "导出结果超过 20000 行，请缩小筛选范围后重试。",
        details: { total: 20001, limit: 20000 },
      }, 400);
    }

    const costTransactionDetailMatch = path.match(/^\/api\/cost-statistics\/transactions\/([^/]+)$/);
    if (costTransactionDetailMatch) {
      const detailReadModelStatus = options.costStatisticsTransactionDetailReadModelStatus ?? "fresh";
      if (detailReadModelStatus !== "fresh") {
        return json(route, {
          error: "cost_statistics_transaction_detail_not_fresh",
          message: "成本统计流水详情正在刷新，请稍后重试。",
          read_model_status: detailReadModelStatus,
          refresh_enqueued: true,
        }, detailReadModelStatus === "refreshing" ? 202 : 409);
      }
      return json(route, costTransactionPayload(
        decodeURIComponent(costTransactionDetailMatch[1] ?? ""),
        relationConfirmed || outputInvoiceDownstreamConfirmed,
        Boolean(options.costStatisticsRelationFanout) || outputInvoiceDownstreamConfirmed,
        invoiceImportDownstreamConfirmed,
        etcImportDownstreamConfirmed,
        bankImportDownstreamConfirmed,
        bankFlowRuleCostConfirmed,
        turnoverCostConfirmed,
      ));
    }

    if (path === "/api/bank-flow-rule-batches/tag-rules" && request.method() === "PUT") {
      const body = parseJsonBody(request.postData()) as {
        rules?: Array<{ tag_code?: string; requires_oa?: boolean; requires_invoice?: boolean }>;
      };
      if (Array.isArray(body.rules)) {
        bankFlowRuleTagRules = body.rules;
      }
      return json(route, {
        ...bankFlowRuleBatchTagSelectionPayloadForScenario(
          bankFlowRuleTagRules,
          bankAutoTagRulesSalarySubLabel,
          options.bankFlowRuleBatchScenario ?? "single",
        ),
        version: 4,
        eligibility_changed: true,
        eligibility_changed_tag_codes: ["salary"],
        affected_months: ["2026-05"],
        affected_scope_keys: ["2026-05"],
        read_model_scope_keys: ["2026-05"],
        freshness_targets: [],
        operation_barrier_targets: [],
        refresh_enqueued: false,
      });
    }

    if (path === "/api/bank-flow-rule-batches/tag-rules") {
      return json(route, bankFlowRuleBatchTagSelectionPayloadForScenario(
        bankFlowRuleTagRules,
        bankAutoTagRulesSalarySubLabel,
        options.bankFlowRuleBatchScenario ?? "single",
      ));
    }

    if (path === "/api/bank-flow-rule-batches") {
      if (bankFlowRuleBatchFailuresRemaining > 0) {
        bankFlowRuleBatchFailuresRemaining -= 1;
        return json(route, {
          error: "bank_flow_rule_batch_temporarily_unavailable",
          message: "流水规则批次加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatuses = options.bankFlowRuleBatchReadModelStatuses;
      const readModelStatus = readModelStatuses?.[
        Math.min(bankFlowRuleBatchesRequestCount, readModelStatuses.length - 1)
      ] ?? options.bankFlowRuleBatchReadModelStatus ?? "fresh";
      bankFlowRuleBatchesRequestCount += 1;
      return json(route, bankFlowRuleBatchesPayload(
        bankFlowRuleBatchStatus,
        url.searchParams.get("bucket"),
        readModelStatus,
        options.bankFlowRuleBatchScenario ?? "single",
      ));
    }

    if (path === "/api/bank-flow-rule-batches/reset-submitted") {
      const payload = bankFlowRuleBatchResetSubmittedPayload();
      bankFlowRuleBatchStatus = "draft";
      return json(route, payload);
    }

    const bankFlowRuleBatchDetailMatch = path.match(/^\/api\/bank-flow-rule-batches\/([^/]+)$/);
    if (bankFlowRuleBatchDetailMatch && request.method() === "GET") {
      return json(route, bankFlowRuleBatchDetailPayload(
        bankFlowRuleBatchStatus,
        decodeURIComponent(bankFlowRuleBatchDetailMatch[1] ?? ""),
        options.bankFlowRuleBatchScenario ?? "single",
      ));
    }

    if (path === "/api/bank-flow-rule-batches/submit-selection") {
      bankFlowRuleBatchStatus = "submitted";
      return json(route, bankFlowRuleBatchMutationPayload(
        bankFlowRuleBatchStatus,
        bankFlowRuleMutationScope,
      ));
    }

    const bankFlowRuleBatchSubmitMatch = path.match(/^\/api\/bank-flow-rule-batches\/([^/]+)\/submit$/);
    if (bankFlowRuleBatchSubmitMatch && request.method() === "POST") {
      bankFlowRuleBatchStatus = "submitted";
      return json(route, bankFlowRuleBatchMutationPayload(
        bankFlowRuleBatchStatus,
        bankFlowRuleMutationScope,
      ));
    }

    if (path === "/api/bank-flow-rule-batches/bank-flow-rule-batch-e2e-001/withdraw") {
      bankFlowRuleBatchStatus = "withdrawn";
      return json(route, bankFlowRuleBatchMutationPayload(
        bankFlowRuleBatchStatus,
        bankFlowRuleMutationScope,
      ));
    }

    if (path === "/api/output-invoice-collections/export-preview") {
      if (options.outputInvoiceCollectionExportRowLimitError) {
        return json(route, {
          error: {
            code: "output_invoice_collection_export_row_limit_exceeded",
            message: "销项发票收款情况导出超过 20000 行，请缩小筛选范围后重试。",
            details: { total: 20001, limit: 20000 },
          },
        }, 400);
      }
      const readModelStatus = options.outputInvoiceCollectionReadModelStatus ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(route, {
          read_model_status: "refreshing",
          readModelStatus: "refreshing",
          message: "销项发票收款情况数据正在刷新，请稍后重试导出。",
        }, 202);
      }
      return json(route, outputInvoiceCollectionExportPreviewPayload(outputInvoiceRedRelationConfirmed));
    }

    if (path === "/api/output-invoice-collections/export") {
      if (options.outputInvoiceCollectionExportRowLimitError) {
        return json(route, {
          error: {
            code: "output_invoice_collection_export_row_limit_exceeded",
            message: "销项发票收款情况导出超过 20000 行，请缩小筛选范围后重试。",
            details: { total: 20001, limit: 20000 },
          },
        }, 400);
      }
      const readModelStatus = options.outputInvoiceCollectionReadModelStatus ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(route, {
          error: {
            code: "output_invoice_collection_read_model_refreshing",
            message: "销项发票收款情况数据正在刷新，请稍后重试导出。",
          },
        }, 409);
      }
      return route.fulfill({
        status: 200,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''output-invoice-collections.xlsx",
        },
        body: outputInvoiceCollectionExportBody(outputInvoiceRedRelationConfirmed, url),
      });
    }

    if (path === "/api/output-invoice-collections/rows") {
      if (outputInvoiceCollectionRowsFailuresRemaining > 0) {
        outputInvoiceCollectionRowsFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_collection_rows_temporarily_unavailable",
          message: "销项发票收款情况加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatus = options.outputInvoiceCollectionReadModelStatus ?? "fresh";
      return json(route, outputInvoiceCollectionRowsPayload(
        outputInvoiceStatusSaved,
        outputInvoiceReminderSaved,
        outputInvoiceReceiptState !== "none",
        outputInvoiceRedRelationConfirmed,
        Boolean(options.outputInvoiceRedRelationCandidate || options.outputInvoiceCollectionListInteractions),
        readModelStatus,
        options.outputInvoiceCollectionListInteractions ? url : undefined,
        invoiceImportDownstreamConfirmed,
      ), readModelStatus === "fresh" ? 200 : 202);
    }

    if (path === "/api/output-invoice-collections/filter-options") {
      const readModelStatus = options.outputInvoiceCollectionReadModelStatus ?? "fresh";
      return json(
        route,
        outputInvoiceCollectionFilterOptionsPayload(outputInvoiceStatusSaved, outputInvoiceReceiptState !== "none", readModelStatus),
        readModelStatus === "fresh" ? 200 : 202,
      );
    }

    if (path === "/api/output-invoice-collections/status-rules") {
      return json(route, outputInvoiceCollectionStatusRulesPayload());
    }

    if (path === "/api/output-invoice-collections/receipt-settings") {
      if (request.method() === "GET") {
        return json(route, {
          settings: {
            tenant_id: "default",
            prefix: "SK",
            reset_period: "monthly",
            version: 1,
            updated_by: "系统",
            updated_at: "2026-04-30T10:00:00+08:00",
          },
        });
      }
      if (request.method() === "PUT") {
        const body = parseJsonBody(request.postData());
        const prefix = typeof body.prefix === "string" ? body.prefix : "SK";
        const resetPeriod = typeof body.resetPeriod === "string" ? body.resetPeriod : "monthly";
        return json(route, {
          settings: {
            tenant_id: "default",
            prefix,
            reset_period: resetPeriod,
            version: 2,
            updated_by: "管理员",
            updated_at: "2026-04-30T10:05:00+08:00",
          },
        });
      }
    }

    if (path === "/api/output-invoice-collections/receipt-preview") {
      return json(route, outputInvoiceReceiptPreviewPayload());
    }

    if (path === "/api/output-invoice-collections/receipts/history") {
      return json(route, outputInvoiceReceiptHistoryPayload(outputInvoiceReceiptState));
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status") {
      if (outputInvoiceCollectionStatusFailuresRemaining > 0) {
        outputInvoiceCollectionStatusFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_collection_status_temporarily_unavailable",
          message: "收款状态保存暂时失败，请重试。",
        }, 503);
      }
      outputInvoiceStatusSaved = true;
      return json(route, {
        ok: true,
        row_id: "output-collection-row-e2e-001",
        lifecycle_status: "updated",
      });
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder") {
      if (outputInvoiceCollectionReminderFailuresRemaining > 0) {
        outputInvoiceCollectionReminderFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_collection_reminder_temporarily_unavailable",
          message: "收款提醒保存暂时失败，请重试。",
        }, 503);
      }
      outputInvoiceReminderSaved = true;
      return json(route, {
        ok: true,
        row_id: "output-collection-row-e2e-001",
        reminder_id: "output-reminder-e2e-001",
      });
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/receipts") {
      const idempotencyKey = request.headers()["idempotency-key"];
      if (!idempotencyKey) {
        return json(route, {
          error: "idempotency_key_required",
          message: "创建正式收据需要 Idempotency-Key。",
        }, 400);
      }
      if (outputInvoiceCollectionReceiptCreateFailuresRemaining > 0) {
        outputInvoiceCollectionReceiptCreateFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_receipt_create_temporarily_unavailable",
          message: "正式收据创建暂时失败，请重试。",
        }, 503);
      }
      outputInvoiceReceiptState = "issued";
      return json(route, {
        ok: true,
        receipt: {
          id: "receipt-output-e2e-001",
          receipt_no: "SK2026050002",
          status: "issued",
        },
      });
    }

    if (path === "/api/output-invoice-collections/receipts/receipt-output-e2e-001/void") {
      if (outputInvoiceCollectionReceiptVoidFailuresRemaining > 0) {
        outputInvoiceCollectionReceiptVoidFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_receipt_void_temporarily_unavailable",
          message: "正式收据作废暂时失败，请重试。",
        }, 503);
      }
      outputInvoiceReceiptState = "voided";
      return json(route, {
        ok: true,
        receipt: {
          id: "receipt-output-e2e-001",
          receipt_no: "SK2026050002",
          status: "voided",
        },
      });
    }

    if (path === "/api/output-invoice-collections/receipts/receipt-output-e2e-001/reissue") {
      if (outputInvoiceCollectionReceiptReissueFailuresRemaining > 0) {
        outputInvoiceCollectionReceiptReissueFailuresRemaining -= 1;
        return json(route, {
          error: "output_invoice_receipt_reissue_temporarily_unavailable",
          message: "正式收据重开暂时失败，请重试。",
        }, 503);
      }
      outputInvoiceReceiptState = "reissued";
      return json(route, {
        ok: true,
        receipt: {
          id: "receipt-output-e2e-002",
          receipt_no: "SK2026050003",
          status: "issued",
          reissued_from_receipt_id: "receipt-output-e2e-001",
        },
      });
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/red-invoice-relations") {
      outputInvoiceRedRelationConfirmed = true;
      return json(route, {
        ok: true,
        relation: {
          id: "output-red-relation-e2e-001",
          row_id: "output-collection-row-e2e-001",
          related_invoice_id: "out-e2e-002",
          relation_type: "red_invoice",
          source: "manual",
        },
      });
    }

    if (path === "/api/output-invoice-collections/red-invoice-relations/output-red-relation-e2e-001") {
      outputInvoiceRedRelationConfirmed = false;
      return json(route, {
        ok: true,
        relation_id: "output-red-relation-e2e-001",
      });
    }

    if (path === "/api/workbench") {
      if (options.workbenchFreshRefetchError && (relationConfirmed || workbenchExceptionApplied)) {
        return json(route, {
          error: "browser_workbench_refetch_failed",
          message: "browser workbench refetch failed",
        }, 500);
      }
      const initialZoneSearch = (zone: WorkbenchZone) => {
        const rawQuery = url.searchParams.get(`${zone}_query`);
        if (!rawQuery) {
          return "";
        }
        try {
          const query = JSON.parse(rawQuery) as { search?: unknown };
          return typeof query.search === "string" ? query.search : "";
        } catch {
          return "";
        }
      };
      if (options.workbenchBankFlowRuleBatchScenario) {
        const readModelVersion = relationConfirmed
          ? "workbench-generation-e2e-002"
          : "workbench-generation-e2e-001";
        return json(route, {
          month: "all",
          summary: {
            oa_count: 0,
            bank_count: 5,
            invoice_count: relationConfirmed ? 1 : 0,
            paired_count: relationConfirmed ? 2 : 1,
            unpaired_count: relationConfirmed ? 0 : 1,
            exception_count: 0,
            ignored_count: 0,
          },
          oa_status: { code: "ready", message: "OA 已同步" },
          invoice_inventory: {
            system_total: 0,
            manual_import_total: 0,
            workbench_visible_total: 0,
            hidden_submitted_etc_total: 0,
            extra_etc_total: 0,
            etc_summary_batch_count: 0,
            oa_attachment_total: 0,
          },
          paired: bankFlowRuleWorkbenchGroupsPayload(
            "paired",
            relationConfirmed,
            1,
            200,
            initialZoneSearch("paired"),
          ),
          unpaired: bankFlowRuleWorkbenchGroupsPayload(
            "unpaired",
            relationConfirmed,
            1,
            200,
            initialZoneSearch("unpaired"),
          ),
          read_model_status: "fresh",
          read_model_version: readModelVersion,
          active_generation_id: readModelVersion,
          generated_at: "2026-06-17T01:00:00Z",
        });
      }
      return json(route, workbenchInitialPayload(
        relationConfirmed,
        workbenchExceptionApplied,
        workbenchRowIgnored,
        workbenchPageStatus,
        options.workbenchPageEmpty === true,
        options.workbenchLargeDataset === true,
        options.workbenchCashSpecialActions === true,
        {
          paired: initialZoneSearch("paired"),
          unpaired: initialZoneSearch("unpaired"),
        },
      ));
    }

    if (path === "/imports/files/preview") {
      latestImportScenario = inferImportScenarioFromPostData(
        `${request.postData() ?? ""}\n${request.headers().referer ?? ""}`,
      );
      if (latestImportScenario === "invoice" && options.invoiceImportPreviewDelayMs && options.invoiceImportPreviewDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, options.invoiceImportPreviewDelayMs));
      }
      if (latestImportScenario === "bank" && options.bankImportPreviewDelayMs && options.bankImportPreviewDelayMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, options.bankImportPreviewDelayMs));
      }
      return json(route, importSessionPayload(latestImportScenario, false, {
        corruptBankFile: latestImportScenario === "bank" && options.bankImportIncludeCorruptFile === true,
        corruptInvoiceFile: latestImportScenario === "invoice" && options.invoiceImportIncludeCorruptFile === true,
        noBankAccountConflict: options.bankImportNoAccountConflict,
      }));
    }

    if (path === "/imports/files/confirm") {
      if (latestImportScenario === "invoice" && options.invoiceImportConfirmPreviewStale) {
        return json(route, {
          error: "preview_stale",
          message: "发票预览已过期，请重新预览。",
        }, 409);
      }
      if (latestImportScenario === "invoice" && options.invoiceImportConfirmError) {
        return json(route, {
          error: "invoice_import_confirm_failed",
          message: "发票导入任务创建失败，请稍后重试。",
        }, 500);
      }
      if (latestImportScenario === "bank" && options.bankImportConfirmPreviewStale) {
        return json(route, {
          error: "preview_stale",
          message: "银行流水预览已过期，请重新预览。",
        }, 409);
      }
      if (latestImportScenario === "bank" && options.bankImportConfirmError) {
        return json(route, {
          error: "bank_import_confirm_failed",
          message: "导入任务创建失败，请稍后重试。",
        }, 500);
      }
      importConfirmed[latestImportScenario] = true;
      return json(route, importSessionPayload(latestImportScenario, true, {
        corruptBankFile: latestImportScenario === "bank" && options.bankImportIncludeCorruptFile === true,
        corruptInvoiceFile: latestImportScenario === "invoice" && options.invoiceImportIncludeCorruptFile === true,
        noBankAccountConflict: options.bankImportNoAccountConflict,
      }));
    }

    if (path === `/imports/files/sessions/${importSessionIds.bank}`) {
      return json(route, importSessionPayload("bank", importConfirmed.bank, {
        corruptBankFile: options.bankImportIncludeCorruptFile,
        noBankAccountConflict: options.bankImportNoAccountConflict,
      }));
    }

    if (path === `/imports/files/sessions/${importSessionIds.invoice}`) {
      return json(route, importSessionPayload("invoice", importConfirmed.invoice, {
        corruptInvoiceFile: options.invoiceImportIncludeCorruptFile,
      }));
    }

    if (path === "/api/turnover-ledger/tag-selection" && request.method() === "PUT") {
      const body = parseJsonBody(request.postData());
      const selectedTagCodes = Array.isArray(body.selected_tag_codes)
        ? body.selected_tag_codes.map(String)
        : [];
      turnoverSelectedTagCodes = selectedTagCodes;
      turnoverTagSelectionVersion += 1;
      return json(route, turnoverLedgerTagSelectionPayload(turnoverSelectedTagCodes, turnoverTagSelectionVersion));
    }

    if (path === "/api/turnover-ledger/tag-selection") {
      return json(route, turnoverLedgerTagSelectionPayload(turnoverSelectedTagCodes, turnoverTagSelectionVersion));
    }

    if (path === "/api/turnover-ledger/relations/turnover_rel_e2e_expense") {
      return json(route, {
        relation: turnoverFlowRow(
          turnoverBankRows.expense,
          "expense",
          turnoverClosureConfirmed,
          turnoverBankRowVersions[turnoverBankRows.expense],
        ),
        bank_rows: [
          {
            id: turnoverBankRows.expense,
            trade_time: "2026-05-03 10:00:00",
            counterparty_name: "云南建设有限公司",
            direction_label: "支",
            amount: "1000.00",
            bank_account_label: "建行 8106",
            summary: "浏览器 e2e 归还借款",
          },
        ],
        audit_history: [],
      });
    }

    if (path === "/api/turnover-ledger/relations/turnover_rel_e2e_expense/extra") {
      if (request.method() === "PUT") {
        return json(route, {
          relation_id: "turnover_rel_e2e_expense",
          extra: parseJsonBody(request.postData()),
        });
      }
      return json(route, {
        relation_id: "turnover_rel_e2e_expense",
        interest_rate_type: "annual",
        interest_rate_value: "0.060000",
        interest_paid_amount: "10.00",
        interest_paid_date: "2026-05-05",
        interest_payment_method: "转账",
        note: "浏览器 e2e 补充信息",
      });
    }

    if (path === "/api/turnover-ledger") {
      if (turnoverLedgerFailuresRemaining > 0) {
        turnoverLedgerFailuresRemaining -= 1;
        return json(route, {
          error: "turnover_ledger_temporarily_unavailable",
          message: "往来款台账加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatuses = options.turnoverLedgerReadModelStatuses;
      const readModelStatus = readModelStatuses?.[
        Math.min(turnoverLedgerRequestCount, readModelStatuses.length - 1)
      ] ?? options.turnoverLedgerReadModelStatus ?? "fresh";
      turnoverLedgerRequestCount += 1;
      return json(route, turnoverLedgerPayload(turnoverClosureConfirmed, readModelStatus));
    }

    if (path === "/api/turnover-ledger/closures/confirm") {
      const conflict = turnoverClosureRequestConflict(parseJsonBody(request.postData()));
      if (conflict) {
        return json(route, conflict, 409);
      }
      turnoverClosureConfirmed = true;
      return json(route, turnoverClosureMutationPayload());
    }

    if (path === "/api/turnover-ledger/closures/withdraw") {
      const body = parseJsonBody(request.postData());
      if (body.cash_closure_case_id !== "turnover:turnover_rel_e2e_closure") {
        return json(route, {
          error: "invalid_cash_closure_case_id",
          message: "cash_closure_case_id must match the active canonical closure.",
        }, 400);
      }
      turnoverClosureConfirmed = false;
      return json(route, {
        ...turnoverClosureMutationPayload(),
        status: "withdrawn",
      });
    }

    if (path === "/api/workbench/groups") {
      if (workbenchGroupsFailuresRemaining > 0) {
        workbenchGroupsFailuresRemaining -= 1;
        return json(route, {
          error: "workbench_groups_temporarily_unavailable",
          message: "关联台下一页暂时加载失败，请重试。",
        }, 503);
      }
      if (options.workbenchFreshRefetchError && (relationConfirmed || workbenchExceptionApplied)) {
        return json(route, {
          error: "browser_workbench_refetch_failed",
          message: "browser workbench refetch failed",
        }, 500);
      }
      const zone = url.searchParams.get("zone") === "paired" ? "paired" : "unpaired";
      const requestedPage = Number.parseInt(url.searchParams.get("page") ?? "1", 10);
      const requestedPageSize = Number.parseInt(url.searchParams.get("page_size") ?? "50", 10);
      if (options.workbenchBankFlowRuleBatchScenario) {
        return json(route, bankFlowRuleWorkbenchGroupsPayload(
          zone,
          relationConfirmed,
          Number.isFinite(requestedPage) ? requestedPage : 1,
          Number.isFinite(requestedPageSize) ? requestedPageSize : 50,
          url.searchParams.get("search") ?? "",
        ));
      }
      return json(route, workbenchGroupsPayload(
        zone,
        relationConfirmed,
        workbenchExceptionApplied,
        workbenchRowIgnored,
        workbenchPageStatus,
        options.workbenchPageEmpty === true,
        options.workbenchLargeDataset === true,
        options.workbenchCashSpecialActions === true,
        Number.isFinite(requestedPage) ? requestedPage : 1,
        Number.isFinite(requestedPageSize) ? requestedPageSize : 50,
        url.searchParams.get("search") ?? "",
      ));
    }

    if (path === "/api/workbench/groups/detail" && options.workbenchBankFlowRuleBatchScenario) {
      const zone = url.searchParams.get("zone") === "unpaired" ? "unpaired" : "paired";
      const groupId = url.searchParams.get("group_id") ?? "";
      const group = bankFlowRuleWorkbenchGroups(zone, relationConfirmed, true)
        .find((candidate) => candidate.group_id === groupId);
      if (!group) {
        return json(route, { error: "workbench_group_not_found" }, 404);
      }
      return json(route, {
        group,
        read_model_status: "fresh",
        read_model_version: relationConfirmed
          ? "workbench-generation-e2e-002"
          : "workbench-generation-e2e-001",
      });
    }

    const workbenchRowDetailMatch = path.match(/^\/api\/workbench\/rows\/([^/]+)$/);
    if (workbenchRowDetailMatch) {
      const rowId = decodeURIComponent(workbenchRowDetailMatch[1] ?? "");
      const row = findWorkbenchRow(
        rowId,
        relationConfirmed,
        workbenchExceptionApplied,
        workbenchRowIgnored,
        options.workbenchLargeDataset === true,
        options.workbenchCashSpecialActions === true,
      );
      if (!row) {
        return json(route, {
          error: "workbench_row_not_found",
          message: "关联台记录不存在。",
        }, 404);
      }
      return json(route, { row });
    }

    if (path === "/api/workbench/ignored") {
      return json(route, {
        month: url.searchParams.get("month") ?? "all",
        rows: ignoredWorkbenchRows(workbenchRowIgnored),
      });
    }

    if (path === "/api/workbench/settings") {
      return json(route, workbenchSettingsPayload());
    }

    if (path === "/api/workbench/actions/confirm-link/preview") {
      if (options.workbenchBankFlowRuleBatchScenario) {
        return json(route, bankFlowRuleConfirmPreviewPayload());
      }
      return json(route, confirmPreviewPayload());
    }

    if (path === "/api/workbench/actions/confirm-link") {
      workbenchConfirmSubmitAttempts += 1;
      const submitDelayMs = Math.max(0, options.workbenchConfirmSubmitDelayMs ?? 0);
      if (submitDelayMs > 0) {
        await delay(submitDelayMs);
      }
      if (options.workbenchConfirmSubmitConflict) {
        return json(route, {
          error: "workbench_relation_preview_stale",
          message: "关联预览已失效，请重新预览。",
        }, 409);
      }
      const failuresBeforeSuccess = Math.max(0, options.workbenchConfirmSubmitFailuresBeforeSuccess ?? 0);
      if (workbenchConfirmSubmitAttempts <= failuresBeforeSuccess) {
        return json(route, {
          error: "browser_confirm_temporarily_unavailable",
          message: "网络暂时失败，请重试。",
        }, 503);
      }
      if (options.workbenchConfirmSubmitError) {
        return json(route, {
          error: "browser_confirm_failed",
          message: "browser confirm failed",
        }, 500);
      }
      relationConfirmed = true;
      if (options.workbenchBankFlowRuleBatchScenario) {
        return json(route, bankFlowRuleConfirmResultPayload());
      }
      return json(route, confirmResultPayload());
    }

    if (path === "/api/workbench/actions/withdraw-link/preview") {
      if (!relationConfirmed) {
        return json(route, {
          error: "workbench_relation_not_found",
          message: "Selected rows do not belong to an active relation.",
        }, 400);
      }
      return json(route, withdrawPreviewPayload());
    }

    if (path === "/api/workbench/actions/withdraw-link") {
      await delay(Math.max(0, options.workbenchWithdrawSubmitDelayMs ?? 200));
      relationConfirmed = false;
      return json(route, withdrawResultPayload());
    }

    if (path === "/api/workbench/exception/preview") {
      return json(route, workbenchExceptionPreviewPayload());
    }

    if (path === "/api/workbench/exception/apply") {
      await delay(200);
      relationConfirmed = false;
      workbenchRowIgnored = false;
      workbenchExceptionApplied = true;
      return json(route, workbenchExceptionApplyResultPayload());
    }

    if (path === "/api/workbench/actions/cancel-exception") {
      await delay(200);
      workbenchExceptionApplied = false;
      relationConfirmed = false;
      return json(route, workbenchExceptionActionResultPayload("cancel_exception"));
    }

    if (path === "/api/workbench/actions/ignore-row") {
      await delay(200);
      workbenchRowIgnored = true;
      workbenchExceptionApplied = false;
      relationConfirmed = false;
      return json(route, workbenchExceptionActionResultPayload("ignore_row"));
    }

    if (path === "/api/workbench/actions/unignore-row") {
      await delay(200);
      workbenchRowIgnored = false;
      return json(route, workbenchExceptionActionResultPayload("unignore_row"));
    }

    if (path === "/api/workbench/actions/confirm-cash-pass-through") {
      await delay(200);
      relationConfirmed = true;
      workbenchExceptionApplied = false;
      workbenchRowIgnored = false;
      return json(route, workbenchCashSpecialResultPayload("confirm_cash_pass_through"));
    }

    if (path === "/api/workbench/actions/confirm-cash-ticket-purchase") {
      await delay(200);
      relationConfirmed = true;
      workbenchExceptionApplied = false;
      workbenchRowIgnored = false;
      return json(route, workbenchCashSpecialResultPayload("confirm_cash_ticket_purchase"));
    }

    if (path === "/api/workbench/actions/cancel-cash-special") {
      await delay(200);
      relationConfirmed = true;
      workbenchExceptionApplied = false;
      workbenchRowIgnored = false;
      return json(route, workbenchCashSpecialResultPayload("cancel_cash_special"));
    }

    if (path === "/api/bank-details/accounts") {
      const readModelStatus = sequencedReadModelStatus(
        options.bankDetailsAccountReadModelStatuses,
        bankDetailsAccountsRequestCount,
        options.bankDetailsAccountReadModelStatus,
      );
      bankDetailsAccountsRequestCount += 1;
      return json(route, bankAccountsPayload(readModelStatus));
    }

    if (path === "/api/bank-details/transactions/export") {
      const exportReadModelStatus = options.bankDetailsExportReadModelStatus
        ?? options.bankDetailsTransactionReadModelStatus
        ?? "fresh";
      if (exportReadModelStatus !== "fresh") {
        return json(route, {
          error: "bank_detail_read_model_not_fresh",
          message: "银行明细正在刷新，请稍后重试导出。",
          read_model_status: exportReadModelStatus,
        }, 409);
      }
      const filename = `银行明细_${url.searchParams.get("mode") === "account" ? "当前账户" : "全部银行"}_${url.searchParams.get("date_from") ?? "全部"}_${url.searchParams.get("date_to") ?? "全部"}.xlsx`;
      return route.fulfill({
        status: 200,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": `attachment; filename*=UTF-8''${encodeURIComponent(filename)}`,
        },
        body: bankDetailsExportBody(relationConfirmed, url),
      });
    }

    if (path === "/api/bank-details/transactions") {
      if (bankDetailsTransactionsFailuresRemaining > 0) {
        bankDetailsTransactionsFailuresRemaining -= 1;
        return json(route, {
          error: "bank_detail_transactions_unavailable",
          message: "银行流水暂时无法加载，请稍后重试。",
        }, 503);
      }
      const readModelStatus = sequencedReadModelStatus(
        options.bankDetailsTransactionReadModelStatuses,
        bankDetailsTransactionsRequestCount,
        options.bankDetailsTransactionReadModelStatus,
      );
      bankDetailsTransactionsRequestCount += 1;
      const page = Number.parseInt(url.searchParams.get("page") ?? "1", 10);
      const pageSize = Number.parseInt(url.searchParams.get("page_size") ?? "100", 10);
      return json(route, bankTransactionsPayload(
        relationConfirmed,
        importConfirmed.bank,
        {
          classificationMode: options.bankDetailsClassificationMode,
          categoryOverride: bankDetailsCategoryOverride,
          largeDataset: options.bankDetailsLargeDataset,
          page: Number.isFinite(page) ? page : 1,
          pageSize: Number.isFinite(pageSize) ? pageSize : 100,
          readModelStatus,
          rowsEmpty: options.bankDetailsTransactionsEmpty
            || settingsDataResetCompletedAction === "reset_bank_transactions",
          total: options.bankDetailsTransactionsTotal,
        },
      ));
    }

    const bankCategoryConfirmationMatch = path.match(/^\/api\/bank-details\/transactions\/([^/]+)\/category-confirmation$/);
    if (bankCategoryConfirmationMatch) {
      const body = parseJsonBody(request.postData());
      if (request.method() === "DELETE") {
        bankDetailsCategoryOverride = null;
        return json(route, {
          ok: true,
          transaction_id: decodeURIComponent(bankCategoryConfirmationMatch[1] ?? ""),
          action: "bank_detail_category_confirmation_revoked",
          affected_months: ["2026-03"],
        });
      }
      bankDetailsCategoryOverride = {
        categoryCode: String(body.category_code ?? "equipment_payment"),
        primaryLabel: String(body.category_primary_label ?? "成本"),
        subLabel: String(body.category_sub_label ?? "设备款"),
        thirdLabel: body.category_third_label ? String(body.category_third_label) : null,
        labelPath: body.category_label_path && Array.isArray(body.category_label_path)
          ? body.category_label_path.map(String)
          : ["成本", "设备款"],
        source: "auto_confirmation",
      };
      return json(route, {
        ok: true,
        transaction_id: decodeURIComponent(bankCategoryConfirmationMatch[1] ?? ""),
        selected_category_code: bankDetailsCategoryOverride.categoryCode,
        affected_months: ["2026-03"],
        freshness_targets: [{ read_model_key: "bank_detail", scope_key: "2026-03" }],
      });
    }

    const bankCategoryAssignmentMatch = path.match(/^\/api\/bank-details\/transactions\/([^/]+)\/category-assignment$/);
    if (bankCategoryAssignmentMatch) {
      const body = parseJsonBody(request.postData());
      if (request.method() === "DELETE") {
        bankDetailsCategoryOverride = null;
        return json(route, {
          ok: true,
          transaction_id: decodeURIComponent(bankCategoryAssignmentMatch[1] ?? ""),
          action: "bank_detail_category_manual_assignment_cleared",
          affected_months: ["2026-03"],
        });
      }
      const primaryLabel = String(body.category_primary_label ?? "费用");
      const subLabel = String(body.category_sub_label ?? "工资");
      const thirdLabel = body.category_third_label ? String(body.category_third_label) : null;
      bankDetailsCategoryOverride = {
        categoryCode: String(body.category_code ?? "salary"),
        primaryLabel,
        subLabel,
        thirdLabel,
        labelPath: body.category_label_path && Array.isArray(body.category_label_path)
          ? body.category_label_path.map(String)
          : [primaryLabel, subLabel].filter(Boolean),
        source: "manual",
      };
      return json(route, {
        ok: true,
        transaction_id: decodeURIComponent(bankCategoryAssignmentMatch[1] ?? ""),
        selected_category_code: bankDetailsCategoryOverride.categoryCode,
        previous_resolution_status: "unmatched",
        assignment_source: "manual",
        affected_months: ["2026-03"],
        freshness_targets: [{ read_model_key: "bank_detail", scope_key: "2026-03" }],
      });
    }

    const canSaveBankAutoTagRules = options.sessionMode !== "read_export_only"
      && options.sessionMode !== "forbidden";
    if (path === "/api/bank-details/auto-tag-rules/reapply") {
      const targets = [{ read_model_key: "bank_detail", scope_key: "2026-03" }];
      return json(route, {
        ...bankAutoTagRulesPayload(canSaveBankAutoTagRules, {
          version: bankAutoTagRulesVersion,
          readModelStatus: "refreshing",
          salarySubLabel: bankAutoTagRulesSalarySubLabel,
        }),
        affected_scope_keys: ["2026-03"],
        read_model_scope_keys: ["2026-03"],
        freshness_targets: targets,
        operation_barrier_targets: targets,
        refresh_enqueued: true,
      }, 202);
    }

    if (path === "/api/bank-details/auto-tag-rules") {
      if (request.method() === "PUT") {
        const body = parseJsonBody(request.postData());
        const activeRules = Array.isArray(body.active_rules)
          ? body.active_rules.filter((rule): rule is Record<string, unknown> => (
            typeof rule === "object" && rule !== null && !Array.isArray(rule)
          ))
          : [];
        const salaryRule = activeRules.find((rule) => rule.code === "salary");
        const salarySubLabel = salaryRule?.output_sub_label;
        if (typeof salarySubLabel === "string" && salarySubLabel.trim()) {
          bankAutoTagRulesSalarySubLabel = salarySubLabel.trim();
        }
        bankAutoTagRulesVersion += 1;
      }
      return json(route, bankAutoTagRulesPayload(canSaveBankAutoTagRules, {
        version: bankAutoTagRulesVersion,
        salarySubLabel: bankAutoTagRulesSalarySubLabel,
      }));
    }

    if (path === "/api/pending-invoices/rows") {
      if (pendingInvoiceRowsFailuresRemaining > 0) {
        pendingInvoiceRowsFailuresRemaining -= 1;
        return json(route, {
          error: "pending_invoice_rows_temporarily_unavailable",
          message: "待找发票加载暂时失败，请刷新后重试。",
        }, 503);
      }
      if (options.pendingInvoiceIncomeBatchRows && url.searchParams.get("direction") === "income") {
        return json(route, pendingInvoiceIncomeRowsPayload(
          pendingInvoiceIncomeStatus,
          options.pendingInvoiceReadModelStatus ?? "fresh",
        ));
      }
      if (options.pendingInvoiceFilterSortRows) {
        return json(route, pendingInvoiceFilterSortRowsPayload(
          url,
          relationConfirmed,
          options.pendingInvoiceReadModelStatus ?? "fresh",
        ));
      }
      return json(route, pendingInvoiceRowsPayload(
        relationConfirmed,
        options.pendingInvoiceReadModelStatus ?? "fresh",
        Boolean(options.pendingInvoiceRowsEmpty),
        Boolean(options.pendingInvoiceAttachExistingBatchRows),
        Boolean(options.pendingInvoiceIncomeBatchRows),
        invoiceImportDownstreamConfirmed,
      ));
    }

    if (path === "/api/pending-invoices/filter-options") {
      if (options.pendingInvoiceFilterSortRows) {
        return json(route, pendingInvoiceFilterSortOptionsPayload());
      }
      return json(route, pendingInvoiceFilterOptionsPayload(relationConfirmed));
    }

    if (path === "/api/pending-invoices/invoice-candidates/batch") {
      return json(route, pendingInvoiceAttachExistingCandidatesPayload(parseJsonBody(request.postData())));
    }

    if (path === "/api/pending-invoices/attach-existing-invoices/preview") {
      return json(route, pendingInvoiceAttachExistingPreviewPayload(
        parseJsonBody(request.postData()),
        Boolean(options.pendingInvoiceAttachExistingPreviewConflict),
      ));
    }

    if (path === "/api/pending-invoices/attach-existing-invoices") {
      const body = parseJsonBody(request.postData());
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids.map(String) : [];
      const invoiceIds = Array.isArray(body.invoice_ids) ? body.invoice_ids.map(String) : [];
      if (pendingInvoiceAttachExistingConfirmFailuresRemaining > 0) {
        pendingInvoiceAttachExistingConfirmFailuresRemaining -= 1;
        return json(route, {
          error: "pending_invoice_attach_existing_temporarily_unavailable",
          message: "选择已有发票关系确认暂时失败，请重试。",
        }, 503);
      }
      relationConfirmed = true;
      return json(route, {
        status: "completed",
        request_id: typeof body.request_id === "string" ? body.request_id : "attach-existing-e2e",
        request_key: transactionIds.includes("bk-o-202603-002")
          ? "pending_invoice_attach_existing:batch"
          : "pending_invoice_attach_existing:bk-o-202603-001:iv-o-202603-001",
        transaction_ids: transactionIds,
        invoice_ids: invoiceIds,
        relation_case_id: transactionIds.includes("bk-o-202603-002") ? "CASE-202603-ATTACH-BATCH" : "CASE-202603-101",
        relation_mode: "pending_invoice_attach_existing_invoice",
        affected_transaction_ids: transactionIds,
        affected_invoice_ids: invoiceIds,
        affected_months: ["2026-03"],
      });
    }

    if (path === "/api/pending-invoices/income-statuses") {
      const body = parseJsonBody(request.postData());
      const statusCode = typeof body.status_code === "string" ? body.status_code : "";
      const transactionIds = Array.isArray(body.transaction_ids) ? body.transaction_ids.map(String) : [];
      if (pendingInvoiceIncomeStatusFailuresRemaining > 0) {
        pendingInvoiceIncomeStatusFailuresRemaining -= 1;
        return json(route, {
          error: "pending_invoice_income_status_temporarily_unavailable",
          message: "收入状态保存暂时失败，请重试。",
          affected_transaction_ids: [],
          affected_months: [],
        }, 503);
      }
      if (options.pendingInvoiceIncomeStatusError) {
        return json(route, {
          error: "pending_invoice_income_status_rejected",
          message: "收入状态批量校验失败，未写入任何流水。",
          affected_transaction_ids: [],
          affected_months: [],
        }, 409);
      }
      if (statusCode === "income_no_invoice_required" || statusCode === "cash_income") {
        pendingInvoiceIncomeStatus = statusCode;
      }
      return json(route, {
        status: "completed",
        request_id: typeof body.request_id === "string" ? body.request_id : "income-status-browser-e2e",
        request_key: `pending_invoice_income_status:${statusCode || "unknown"}`,
        transaction_ids: transactionIds,
        status_code: statusCode || "cash_income",
        affected_transaction_ids: transactionIds,
        affected_invoice_ids: [],
        affected_months: ["2026-03"],
        rows: [],
      });
    }

    if (path === "/api/pending-invoices/export-preview") {
      const readModelStatus = options.pendingInvoiceReadModelStatus ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(route, {
          error: "pending_invoice_read_model_not_fresh",
          message: "待找发票正在刷新，请稍后重试导出。",
          read_model_status: readModelStatus,
        }, 409);
      }
      return json(route, pendingInvoiceExportPreviewPayload(relationConfirmed));
    }

    if (path === "/api/pending-invoices/export") {
      const readModelStatus = options.pendingInvoiceReadModelStatus ?? "fresh";
      if (readModelStatus !== "fresh") {
        return json(route, {
          error: "pending_invoice_read_model_not_fresh",
          message: "待找发票正在刷新，请稍后重试导出。",
          read_model_status: readModelStatus,
        }, 409);
      }
      if (options.pendingInvoiceExportRowLimitError) {
        return json(route, {
          error: "pending_invoice_export_row_limit_exceeded",
          message: "待找发票导出超过 20000 行，请缩小筛选范围后重试。",
          details: { total: 20001, limit: 20000 },
        }, 400);
      }
      return route.fulfill({
        status: 200,
        contentType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers: {
          "Content-Disposition": "attachment; filename*=UTF-8''pending-invoices.xlsx",
        },
        body: pendingInvoiceExportBody(relationConfirmed, url),
      });
    }

    if (path === "/api/batch-accounting") {
      if (batchAccountingFailuresRemaining > 0) {
        batchAccountingFailuresRemaining -= 1;
        return json(route, {
          error: "batch_accounting_temporarily_unavailable",
          message: "批量账务数据加载暂时失败，请刷新后重试。",
        }, 503);
      }
      const readModelStatuses = options.batchAccountingReadModelStatuses;
      const readModelStatus = readModelStatuses?.[
        Math.min(batchAccountingRequestCount, readModelStatuses.length - 1)
      ] ?? options.batchAccountingReadModelStatus ?? "fresh";
      batchAccountingRequestCount += 1;
      return json(route, batchAccountingPayload(url, batchAccountingSubmitted, readModelStatus));
    }

    if (path === "/api/batch-accounting/submit") {
      batchAccountingSubmitted = true;
      return json(route, batchAccountingSubmitPayload());
    }

    if (path === "/api/batch-accounting/BA-REL-202604-001/withdraw") {
      batchAccountingSubmitted = false;
      return json(route, batchAccountingWithdrawPayload());
    }

    if (path === "/api/operations/app-health-dashboard") {
      if (options.dashboardError) {
        return json(route, { error: "dashboard_unavailable", message: "dashboard unavailable" }, 503);
      }
      return json(route, operationsDashboardPayload());
    }

    if (
      path === "/api/operations/app-health/page-audit"
      && url.searchParams.get("page") === "app-health-operations"
    ) {
      return json(route, appHealthSystemAuditPayload());
    }

    return json(route, {});
  });

  return {
    calls,
    count(methodAndPath: string) {
      return calls.filter((entry) => entry === methodAndPath).length;
    },
    bodies(methodAndPath: string) {
      return requestBodies.get(methodAndPath) ?? [];
    },
    lastBody(methodAndPath: string) {
      const bodies = requestBodies.get(methodAndPath) ?? [];
      return bodies[bodies.length - 1] ?? {};
    },
    failNextBankDetailsTransactions(count = 1) {
      bankDetailsTransactionsFailuresRemaining += Math.max(1, count);
    },
  };
}
