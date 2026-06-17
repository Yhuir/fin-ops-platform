import type { Page, Route } from "@playwright/test";

export type AccessTier = "denied" | "read_export_only" | "full_access" | "admin";

type SessionMode = "admin" | "full_access" | "read_export_only" | "forbidden" | "expired" | "error";

type ApiMockOptions = {
  sessionMode?: SessionMode;
  dashboardError?: boolean;
};

type WorkbenchZone = "paired" | "open";
type BatchAccountingBucket = "unsubmitted" | "submitted";
type ImportScenario = "bank" | "invoice";
type SettingsDataResetAction = "reset_bank_transactions" | "reset_invoices" | "reset_oa_and_rebuild";
type EtcBusinessBatchStatus = "imported" | "oa_confirmation_pending" | "manually_marked_submitted" | "not_submitted";
type NoOaBrowserBatchStatus = "draft" | "submitted" | "withdrawn";
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

function appStatusOverview() {
  return {
    version: 1,
    generated_at: "2026-06-17T01:00:00Z",
    overall: {
      level: "ok",
      color: "green",
      reason: "浏览器 e2e mock runtime ready",
      blocks_mutations: false,
      write_safety: {
        status: "ready",
        reason: "",
        blocks_mutations: false,
        blockers: [],
      },
    },
    domains: [
      {
        key: "workbench",
        label: "关联台",
        route: "/",
        level: "ok",
        status: "ready",
        reason: "mock ready",
        details: [],
        read_models: ["workbench"],
        read_model_scopes: [],
        workers: ["workbench-read-model"],
        job_ids: [],
        updated_at: "2026-06-17T01:00:00Z",
      },
    ],
    background_tasks: [],
    alerts: [],
  };
}

function appHealthPayload() {
  return {
    status: "ok",
    generated_at: "2026-06-17T01:00:00Z",
    version: 1,
    app_status: appStatusOverview(),
    session: { status: "authenticated" },
    oa_sync: {
      status: "idle",
      dirty_scopes: [],
      changed_scopes: [],
      version: 1,
      last_synced_at: "2026-06-17T01:00:00Z",
    },
    workbench_read_model: {
      status: "ready",
      read_model_status: "fresh",
      dirty_scopes: [],
      matching_dirty_scopes: [],
      matching_running_scopes: [],
      stale_scopes: [],
      rebuilding_scopes: [],
      last_matching_error: null,
    },
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
  return {
    total_count: 1,
    latest_synced_at: "2026-06-17T01:00:00Z",
    status: "available",
    sources: [
      {
        key: `${label}-mock`,
        label,
        count: 1,
        latest_synced_at: "2026-06-17T01:00:00Z",
        status: "available",
      },
    ],
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

function linkedWorkbenchRows() {
  const rows = workbenchRows();
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
      available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
    },
    invoice: {
      ...rows.invoice,
      invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
      available_actions: ["detail", "cancel_link"],
    },
  };
}

function buildWorkbenchGroup(zone: WorkbenchZone, linked: boolean) {
  const rows = linked ? linkedWorkbenchRows() : workbenchRows();
  return {
    group_id: "case:CASE-202603-101",
    group_type: zone === "paired" ? "manual_confirmed" : "candidate",
    match_confidence: zone === "paired" ? "high" : "medium",
    reason: "browser_e2e_relation_fanout",
    oa_rows: [rows.oa],
    bank_rows: [rows.bank],
    invoice_rows: [rows.invoice],
    can_withdraw: zone === "paired",
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

function workbenchGroups(zone: WorkbenchZone, relationConfirmed: boolean) {
  if (zone === "paired") {
    return relationConfirmed ? [buildWorkbenchGroup("paired", true)] : [];
  }
  return relationConfirmed ? [] : [buildWorkbenchGroup("open", false)];
}

function countWorkbenchRows(groups: Array<ReturnType<typeof buildWorkbenchGroup>>) {
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

function workbenchSummary(relationConfirmed: boolean) {
  return {
    oa_count: 1,
    bank_count: 1,
    invoice_count: 1,
    paired_count: relationConfirmed ? 1 : 0,
    open_count: relationConfirmed ? 0 : 1,
    exception_count: 0,
  };
}

function workbenchSummaryPayload(relationConfirmed: boolean) {
  return {
    month: "all",
    summary: workbenchSummary(relationConfirmed),
    oa_status: { code: "ready", message: "OA 已同步" },
    invoice_inventory: {
      system_total: 1,
      manual_import_total: 0,
      workbench_visible_total: 1,
      hidden_submitted_etc_total: 0,
      extra_etc_total: 0,
      etc_summary_batch_count: 0,
      oa_attachment_total: 1,
    },
    read_model_status: "fresh",
    generated_at: "2026-06-17T01:00:00Z",
  };
}

function workbenchGroupsPayload(zone: WorkbenchZone, relationConfirmed: boolean) {
  const groups = workbenchGroups(zone, relationConfirmed);
  return {
    month: "all",
    zone,
    page: 1,
    page_size: 50,
    total: groups.length,
    row_counts: countWorkbenchRows(groups),
    has_more: false,
    groups,
    read_model_status: "fresh",
  };
}

function workbenchSettingsPayload() {
  return {
    projects: {
      active: [],
      completed: [],
      completed_project_ids: [],
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
      allowed_usernames: [],
      readonly_export_usernames: [],
      admin_usernames: ["YNSYLP005"],
      full_access_usernames: [],
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

function legacyWorkbenchPayload(relationConfirmed: boolean) {
  return {
    month: "all",
    summary: workbenchSummary(relationConfirmed),
    oa_status: { code: "ready", message: "OA 已同步" },
    invoice_inventory: {
      system_total: 1,
      manual_import_total: 0,
      workbench_visible_total: 1,
      hidden_submitted_etc_total: 0,
      extra_etc_total: 0,
      etc_summary_batch_count: 0,
      oa_attachment_total: 1,
    },
    paired: { groups: workbenchGroups("paired", relationConfirmed) },
    open: { groups: workbenchGroups("open", relationConfirmed) },
    read_model_status: "fresh",
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

function importAudit(scenario: ImportScenario, imported = false) {
  if (scenario === "invoice") {
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

function importPreviewFile(scenario: ImportScenario, fileName: string, index: number, imported = false) {
  const sessionId = importSessionIds[scenario];

  if (scenario === "invoice") {
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

  const selectedBankLast4 = "8826";
  const detectedLast4 = index === 0 ? "4080" : selectedBankLast4;
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

function importSessionPayload(scenario: ImportScenario, imported = false) {
  const sessionId = importSessionIds[scenario];
  return {
    session: {
      id: sessionId,
      imported_by: "web_finance_user",
      file_count: importFiles[scenario].length,
      status: imported ? "confirmed" : "preview_ready",
      created_at: "2026-06-17T01:00:00Z",
      audit: importAudit(scenario, imported),
    },
    files: importFiles[scenario].map((fileName, index) => importPreviewFile(scenario, fileName, index, imported)),
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
    created_at: "2026-06-17T09:00:00+08:00",
    updated_at: "2026-06-17T09:00:00+08:00",
    ...(includeItems ? { invoice_items: etcBusinessBatchInvoiceItems() } : {}),
  };
}

function etcBusinessBatchListPayload(status: string | null, batchStatus: EtcBusinessBatchStatus) {
  const submitted = batchStatus === "manually_marked_submitted";
  const wantsSubmitted = status === "submitted";
  const visible = wantsSubmitted ? submitted : !submitted;
  return {
    items: visible ? [etcBusinessBatchPayload(batchStatus, false)] : [],
    counts: {
      active: submitted ? 0 : 1,
      submitted: submitted ? 1 : 0,
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
    tax_offset_read_model_schema_version: "mock-tax-offset-v1",
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

function taxSummary(selectedInputIds: string[], certifiedImported: boolean) {
  const outputTax = 41600;
  const certifiedTax = certifiedImported ? 14080 : 0;
  const plannedTax = selectedInputIds.reduce((total, id) => {
    if (id === "ti-202603-001" && !certifiedImported) {
      return total + 12480;
    }
    if (id === "ti-202603-002") {
      return total + 5760;
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

function taxOffsetPayload(selectedInputIds: string[], certifiedImported: boolean) {
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
  ];
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
    default_selected_input_ids: certifiedImported ? ["ti-202603-002"] : selectedInputIds,
    summary: taxSummary(certifiedImported ? ["ti-202603-002"] : selectedInputIds, certifiedImported),
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

function inputInvoiceUsageRowsPayload() {
  return {
    rows: [
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
          code: "pending",
          label: "待处理",
          reason: "尚未创建 OA 反提关系。",
        },
        oa: {
          primary: {
            id: "oa-input-e2e-001",
            applicant: "陈秀云",
            application_type: "费用报销",
            project_name: "浏览器进项项目",
            amount: "88.00",
            detail_available: true,
          },
          relation_count: 1,
          has_multiple: false,
          detail_mode: "single",
          summaries: [],
        },
        bank: {
          primary: {
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
      },
    ],
    pagination: { page: 1, page_size: 20, total: 1 },
    filter_config: [
      { field: "seller_name", label: "销方名称", mode: "enum_multi", sortable: true, operators: ["in", "contains"] },
      { field: "payment_status", label: "支付状态", mode: "enum_multi", sortable: true, operators: ["in"] },
      { field: "oa_applicant", label: "OA申请人", mode: "enum_multi", sortable: true, operators: ["in"] },
    ],
    read_model_status: "fresh",
    read_model_scope_key: "all",
  };
}

function inputInvoiceUsageFilterOptionsPayload() {
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

function inputInvoiceOaReversePreviewPayload(selectedInvoiceIds: string[]) {
  const selected = selectedInvoiceIds.length > 0
    ? selectedInvoiceIds
    : ["input-oa-invoice-e2e-001", "input-oa-invoice-e2e-002"];
  const invoices = [inputInvoiceOaReverseInvoice(1), inputInvoiceOaReverseInvoice(2)]
    .filter((invoice) => selected.includes(invoice.invoice_id));
  const isSubset = invoices.length === 1;
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
    total_with_tax: isSubset ? "49.86" : "99.72",
    invoice_rows: invoices,
    groups: [
      {
        target_applicant_code: "chen_xiuyun",
        target_applicant_name: "陈秀云",
        invoice_count: invoices.length,
        total_with_tax: isSubset ? "49.86" : "99.72",
        candidate_invoice_ids: invoices.map((invoice) => invoice.invoice_id),
        invoice_rows: invoices,
        rejected_invoices: [],
      },
    ],
    can_create_draft: true,
    next_action: "create_oa_draft",
    permissions: { can_create_draft: true, can_manual_status: true },
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

function oaPendingPaymentRowsPayload() {
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
        },
        paymentStatus: {
          code: "partially_paid",
          label: "支付少了",
          reason: "支出流水合计小于 OA 金额",
          severity: "warning",
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
          hasMultiple: false,
          detailMode: "single",
        },
      },
    ],
    pagination: { page: 1, pageSize: 20, total: 1 },
    summary: {
      rowCount: 1,
      oaAmountTotal: "12000.00",
      bankPaidTotal: "8000.00",
      statusCounts: { partially_paid: 1 },
    },
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

function oaPendingPaymentFilterOptionsPayload() {
  return {
    fields: [
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
        options: [{ value: "partially_paid", label: "支付少了", count: 1 }],
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
    ],
    readModelStatus: "fresh",
    read_model_status: "fresh",
    read_model_scope_key: "all",
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

function pendingInvoiceExpenseRulesPayload() {
  return {
    version: 1,
    direction: "expense",
    available_tags: [],
    groups: {
      requires_invoice: { tag_codes: [], tags: [] },
      bank_statement_as_invoice: { tag_codes: [], tags: [] },
      no_invoice_required: { tag_codes: [], tags: [] },
    },
    permissions: { can_save: false },
  };
}

const completedCostProjectNames = new Set([
  "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
]);

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

function isCostProjectVisibleForScope(projectName: string, projectScope: string | null) {
  return projectScope === "all" || !completedCostProjectNames.has(projectName);
}

function sumCostAmounts(rows: Array<{ amount: string }>) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  return total.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function allCostProjectRows() {
  return Object.values(costProjectRows).reduce<Record<string, CostBrowserProjectRow[]>>((result, projectMap) => {
    for (const [projectName, rows] of Object.entries(projectMap)) {
      result[projectName] = [...(result[projectName] ?? []), ...rows];
    }
    return result;
  }, {});
}

function costTimeRows(month: string, projectScope: string | null) {
  const sourceProjectRowMap = month === "all" ? allCostProjectRows() : (costProjectRows[month] ?? {});
  return Object.entries(sourceProjectRowMap)
    .filter(([projectName]) => isCostProjectVisibleForScope(projectName, projectScope))
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

function costStatisticsExplorerPayload(month: string, projectScope: string | null) {
  const timeRows = costTimeRows(month, projectScope);
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
    read_model_status: "fresh",
    read_model_scope_key: `${projectScope ?? "active"}:${month}`,
    read_model_generated_at: "2026-06-17T09:30:00+08:00",
    read_model_stale_reasons: [],
  };
}

function costTransactionPayload(transactionId: string) {
  const row = costTimeRows("all", "all").find((item) => item.transaction_id === transactionId);
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

function costStatisticsExportPreviewPayload(url: URL) {
  const month = url.searchParams.get("month") ?? "all";
  const view = url.searchParams.get("view") ?? "time";
  const projectScope = url.searchParams.get("project_scope") ?? "active";
  const projectNames = new Set(url.searchParams.getAll("project_name").filter(Boolean));
  const expenseTypes = new Set(url.searchParams.getAll("expense_type").filter(Boolean));
  const rows = costTimeRows(month, projectScope)
    .filter((row) => (projectNames.size > 0 ? projectNames.has(row.project_name) : true))
    .filter((row) => (expenseTypes.size > 0 ? expenseTypes.has(row.expense_type) : true));
  const fileName = view === "project"
    ? "成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx"
    : "成本统计_全部期间_按时间统计.xlsx";
  return {
    view,
    file_name: fileName,
    scope_label: month === "all" ? "全部期间" : month,
    summary: {
      row_count: rows.length,
      transaction_count: rows.length,
      total_amount: sumCostAmounts(rows),
      sheet_count: view === "project" ? 8 : 1,
    },
    sheet_names: view === "project" ? ["导出说明", "项目汇总", "流水明细"] : ["按时间统计"],
    columns: ["时间", "项目名称", "费用类型", "金额", "费用内容", "对方户名", "支付账户"],
    rows: rows.map((row) => [
      row.trade_time,
      row.project_name,
      row.expense_type,
      row.amount,
      row.expense_content,
      row.counterparty_name,
      row.payment_account_label,
    ]),
  };
}

function noOaBankBatchVersion(status: NoOaBrowserBatchStatus) {
  if (status === "draft") {
    return 1;
  }
  if (status === "submitted") {
    return 2;
  }
  return 3;
}

function noOaBankBatch(status: NoOaBrowserBatchStatus) {
  return {
    batch_id: "no-oa-batch-e2e-001",
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
    version: noOaBankBatchVersion(status),
  };
}

function noOaBankBatchSummary(status: NoOaBrowserBatchStatus) {
  const draft = status === "draft" ? 1 : 0;
  const submitted = status === "submitted" ? 1 : 0;
  const withdrawn = status === "withdrawn" ? 1 : 0;
  return {
    draft_count: draft,
    submitted_count: submitted,
    withdrawn_count: withdrawn,
    conflict_count: 0,
    stale_count: 0,
    total_amount: "8.80",
    categories: [
      {
        code: "fee",
        label: "手续费",
        primary_label: "费用",
        sub_label: "手续费",
        total: 1,
        draft,
        submitted,
        withdrawn,
        conflict: 0,
        stale: 0,
        total_amount: "8.80",
      },
    ],
  };
}

function noOaBankBatchesPayload(status: NoOaBrowserBatchStatus, bucket: string | null) {
  const batch = noOaBankBatch(status);
  const visible = (
    (bucket === "submitted" && status === "submitted")
    || (bucket === "withdrawn" && status === "withdrawn")
    || ((bucket === null || bucket === "unsubmitted") && status === "draft")
  );
  return {
    summary: noOaBankBatchSummary(status),
    batches: visible ? [batch] : [],
    pagination: {
      page: 1,
      page_size: 200,
      total: visible ? 1 : 0,
    },
    read_model_status: "fresh",
    read_model_stale_reasons: [],
  };
}

function noOaBankBatchDetailPayload(status: NoOaBrowserBatchStatus) {
  return {
    batch: noOaBankBatch(status),
    tag_counts: { fee: 1 },
    direction_counts: { expense: 1 },
    rows: [
      {
        transaction_id: "no-oa-bank-e2e-001",
        trade_time: "2026-05-03 10:20:00",
        counterparty_name: "建设银行",
        direction: "expense",
        direction_label: "支",
        amount: "8.80",
        bank_name: "建设银行",
        account_last4: "8106",
        account_key: "ccb:8106",
        summary: "网银手续费",
        purpose: "结算",
        remark: "浏览器 e2e 月结手续费",
        category_code: "fee",
        category_label: "手续费",
        category_primary_label: "费用",
        category_sub_label: "手续费",
        category_label_path: ["费用", "手续费"],
        category_source: "auto",
        relation_status: status === "draft" ? "" : "linked",
        relation_case_ids: status === "draft" ? [] : ["no-oa-relation-e2e-001"],
        linked_oa_count: 0,
        linked_invoice_count: 0,
      },
    ],
  };
}

function noOaBankBatchMutationPayload(status: NoOaBrowserBatchStatus) {
  return {
    batch: noOaBankBatch(status),
    affected_months: ["2026-05"],
    workbench_rebuild_queued: true,
    results: [],
  };
}

function noOaBankBatchTagSelectionPayload() {
  return {
    version: 3,
    bank_auto_tag_rules_version: 7,
    selected_tag_codes: ["fee"],
    inactive_selected_tag_codes: [],
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
        label: "工资",
        output_primary_label: "人工成本",
        output_sub_label: "工资",
        status: "active",
      },
    ],
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

function outputInvoiceCollectionRowsPayload(statusSaved: boolean, reminderSaved: boolean, receiptCreated: boolean) {
  return {
    rows: [
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
        collection_status: outputInvoiceCollectionStatus(statusSaved, reminderSaved),
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
        red_invoice: {
          relation_count: 0,
          has_multiple: false,
          detail_mode: "none",
          summaries: [],
        },
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
    ],
    summary: {
      invoice_count: 1,
      total_with_tax: "12,345.67",
      collected_amount: "5,000.00",
      pending_amount: "7,345.67",
      pending_collection_count: statusSaved ? 0 : 1,
      partial_collection_count: statusSaved ? 0 : 1,
      receipt_pending_count: receiptCreated ? 0 : 1,
    },
    pagination: { page: 1, page_size: 20, total: 1 },
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

function outputInvoiceCollectionFilterOptionsPayload(statusSaved: boolean, receiptCreated: boolean) {
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

function outputInvoiceReceiptHistoryPayload(receiptCreated: boolean) {
  return {
    invoice_id: "out-e2e-001",
    source_available: true,
    source_name: "formal_receipt_lifecycle",
    receipts: receiptCreated
      ? [
        {
          id: "receipt-output-e2e-001",
          receipt_no: "SK2026050002",
          amount: "5,000.00",
          created_at: "2026-05-03T10:40:00+08:00",
          status: "issued",
        },
      ]
      : [],
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
    candidate_keys: ["CASE-202603-101"],
    can_submit: true,
    requires_note: false,
    message: "确认后将把 1 条 OA、1 条流水和 1 条发票闭环。",
    before: { groups: [buildWorkbenchGroup("open", false)] },
    after: { groups: [buildWorkbenchGroup("paired", true)] },
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
    freshness_targets: [
      {
        read_model_key: "workbench_relation",
        scope_key: "2026-03",
      },
    ],
    operation_projection: {
      after: {
        paired_groups: [buildWorkbenchGroup("paired", true)],
        open_groups: [],
      },
    },
    message: "已确认 3 条记录关联。",
  };
}

function operationBarrierPayload() {
  return {
    status: "fresh",
    fresh: true,
    targets: [
      {
        read_model_key: "workbench_relation",
        scope_type: "",
        scope_key: "2026-03",
        status: "fresh",
        raw_status: "fresh",
        fresh: true,
        blocking: false,
        generated_at: "2026-06-17T01:00:00Z",
      },
    ],
    blocked_targets: [],
    refreshing_targets: [],
  };
}

function turnoverLedgerTagSelectionPayload() {
  return {
    version: 1,
    selected_tag_codes: ["external_turnover_payment", "external_turnover_collection"],
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
  };
}

function turnoverLedgerPayload(relationClosed: boolean) {
  const summaryRow = turnoverSummaryRow(relationClosed);
  const flowRows = [
    turnoverFlowRow(turnoverBankRows.expense, "expense", relationClosed, 1),
    turnoverFlowRow(turnoverBankRows.income, "income", relationClosed, 2),
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
    read_model_status: "fresh",
    read_model_stale_reasons: [],
  };
}

function turnoverClosureMutationPayload() {
  return {
    turnover_relation: {
      relation_id: "turnover_rel_e2e_closure",
      status: "confirmed",
    },
    workbench_pair_relation: {
      case_id: "turnover:turnover_rel_e2e_closure",
      relation_mode: "turnover_manual_closure",
    },
    affected_months: ["2026-05"],
    freshness_targets: [
      { read_model_key: "turnover_ledger", scope_key: "all" },
      { read_model_key: "workbench_relation", scope_key: "2026-05" },
      { read_model_key: "workbench", scope_key: "2026-05" },
      { read_model_key: "workbench", scope_key: "all" },
    ],
  };
}

function bankAccountsPayload() {
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
    read_model_status: "fresh",
    balance_read_model_status: "fresh",
  };
}

function bankTransactionsPayload(relationConfirmed: boolean, bankImportConfirmed = false) {
  const relationTags = relationConfirmed ? ["有oa", "有发票"] : ["候选oa", "候选发票"];
  return {
    account_key: null,
    date_from: "2026-01-01",
    date_to: "2026-12-31",
    rows: [
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
        relation_case_id: "CASE-202603-101",
        relation_status: relationConfirmed ? "linked" : "candidate",
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
    ],
    category_counts: { equipment_payment: 1, uncategorized: 0 },
    pagination: { page: 1, page_size: 100, total: bankImportConfirmed ? 2 : 1 },
    tag_dictionary: {
      version: 1,
      tags: [
        {
          code: "equipment_payment",
          label: "设备款",
          path: ["自动识别", "设备款"],
          status: "active",
          source: "system",
        },
      ],
    },
    read_model_status: "fresh",
  };
}

function bankAutoTagRulesPayload() {
  return {
    version: 1,
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
    active_rules: [],
    archived_rules: [],
    field_options: [
      { value: "counterparty_name", label: "对方户名" },
      { value: "purpose_text", label: "用途/交易用途" },
      { value: "summary_text", label: "摘要" },
      { value: "note_text", label: "备注/附言/客户附言" },
    ],
    turnover_third_label_options: [],
    turnover_action_type_options: [],
    permissions: { can_save: true },
    read_model_status: "fresh",
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
      relation_count: relationConfirmed ? 1 : 0,
      linked_relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      summaries: relationConfirmed && inputInvoice ? [inputInvoice] : [],
      payment_summary: relationConfirmed ? {
        paid_total: "58000.00",
        invoice_total: "65540.00",
        remaining_amount: "0.00",
        difference_amount: "7540.00",
      } : null,
    },
    oa: {
      primary: oaSummary,
      relation_count: relationConfirmed ? 1 : 0,
      has_multiple: false,
      detail_available: relationConfirmed,
      summaries: relationConfirmed && oaSummary ? [oaSummary] : [],
    },
    invoices: relationConfirmed && inputInvoice ? [inputInvoice] : [],
    oa_applicant: relationConfirmed ? "陈涛" : null,
    can_create_invoice: !relationConfirmed,
    available_actions: relationConfirmed ? ["view_relation"] : ["attach_existing_invoice", "view_payment_detail"],
    relation_case_ids: relationConfirmed ? ["CASE-202603-101"] : [],
  };
}

function pendingInvoiceRowsPayload(relationConfirmed: boolean) {
  return {
    direction: "expense",
    filter: "all",
    rows: [pendingInvoiceRow(relationConfirmed)],
    pagination: { page: 1, page_size: 50, total: 1 },
    summary: {
      total_rows: 1,
      missing_invoice_rows: relationConfirmed ? 0 : 1,
      create_invoice_available_rows: relationConfirmed ? 0 : 1,
      source_summary: {
        bank_transaction_rows: 1,
        expense_rows: 1,
        income_rows: 0,
        current_direction_rows: 1,
        excluded_direction_rows: 0,
      },
    },
    read_model_status: "fresh",
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

function batchAccountingPayload(url: URL, relationSubmitted: boolean) {
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
    read_model_status: "fresh",
    read_model_stale_reasons: [],
    read_model_scope_keys: ["2026-04"],
    refresh_enqueued: false,
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
  let relationConfirmed = false;
  let batchAccountingSubmitted = false;
  let turnoverClosureConfirmed = false;
  let latestImportScenario: ImportScenario = "bank";
  const importConfirmed: Record<ImportScenario, boolean> = {
    bank: false,
    invoice: false,
  };
  let taxCertifiedImported = false;
  let taxSelectedInputIds = ["ti-202603-001", "ti-202603-002"];
  let outputInvoiceStatusSaved = false;
  let outputInvoiceReminderSaved = false;
  let outputInvoiceReceiptCreated = false;
  let inputInvoiceOaSubmitted = false;
  let etcBusinessBatchStatus: EtcBusinessBatchStatus = "imported";
  let noOaBankBatchStatus: NoOaBrowserBatchStatus = "draft";
  let settingsDataResetJob: {
    action: SettingsDataResetAction;
    jobId: string;
    pollCount: number;
    status: "running" | "completed";
  } | null = null;
  await page.route(/.*\/(api\/|imports\/files\/|imports\/templates)/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeApiPath(url.pathname);
    calls.push(`${request.method()} ${path}`);

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
      return json(route, appHealthPayload());
    }

    if (path === "/api/oa-sync/status") {
      return json(route, {
        status: "idle",
        dirty_scopes: [],
        changed_scopes: [],
        version: 1,
        last_synced_at: "2026-06-17T01:00:00Z",
      });
    }

    if (path === "/api/operation-barrier/status") {
      return json(route, operationBarrierPayload());
    }

    if (path === "/api/workbench/settings") {
      return json(route, workbenchSettingsPayload());
    }

    if (path === "/api/workbench/settings/oa-applicant-credentials") {
      return json(route, oaApplicantCredentialsPayload());
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
      return json(route, etcImportPayload(true));
    }

    if (path === "/api/etc/reconciliation-tasks") {
      return json(route, { tasks: [] });
    }

    if (path === "/api/etc/business-batches") {
      return json(route, etcBusinessBatchListPayload(url.searchParams.get("status"), etcBusinessBatchStatus));
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001") {
      if (request.method() === "GET") {
        return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
      }
      if (request.method() === "DELETE") {
        return json(route, { ok: true });
      }
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001/oa-draft") {
      etcBusinessBatchStatus = "oa_confirmation_pending";
      return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
    }

    if (path === "/api/etc/business-batches/etc-business-e2e-001/manual-oa-status") {
      const body = JSON.parse(request.postData() || "{}") as { decision?: string };
      etcBusinessBatchStatus = body.decision === "submitted" ? "manually_marked_submitted" : "not_submitted";
      return json(route, { businessBatch: etcBusinessBatchPayload(etcBusinessBatchStatus, true) });
    }

    if (path === "/api/tax-offset") {
      return json(route, taxOffsetPayload(taxSelectedInputIds, taxCertifiedImported));
    }

    if (path === "/api/tax-offset/calculate") {
      const body = JSON.parse(request.postData() || "{}") as { selected_input_ids?: string[] };
      const selectedInputIds = Array.isArray(body.selected_input_ids) ? body.selected_input_ids : taxSelectedInputIds;
      return json(route, {
        month: "2026-03",
        summary: taxSummary(selectedInputIds, taxCertifiedImported),
      });
    }

    if (path === "/api/tax-offset/plans") {
      const body = JSON.parse(request.postData() || "{}") as { selected_input_ids?: string[] };
      taxSelectedInputIds = Array.isArray(body.selected_input_ids) ? body.selected_input_ids : taxSelectedInputIds;
      return json(route, {
        status: "saved",
        plan: {
          id: "tax-offset-plan-e2e-001",
          month: "2026-03",
          selected_output_ids: ["to-202603-001"],
          selected_input_ids: taxSelectedInputIds,
          summary: taxSummary(taxSelectedInputIds, taxCertifiedImported),
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
      return json(route, inputInvoiceUsageRowsPayload());
    }

    if (path === "/api/input-invoice-usage/filter-options") {
      return json(route, inputInvoiceUsageFilterOptionsPayload());
    }

    if (path === "/api/input-invoice-usage/oa-reverse/preview") {
      const body = JSON.parse(request.postData() || "{}") as {
        invoiceIds?: string[];
        invoice_ids?: string[];
      };
      return json(route, inputInvoiceOaReversePreviewPayload(body.invoiceIds ?? body.invoice_ids ?? []));
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
      return json(route, oaPendingPaymentRowsPayload());
    }

    if (path === "/api/oa-pending-payments/filter-options") {
      return json(route, oaPendingPaymentFilterOptionsPayload());
    }

    if (path === "/api/oa-pending-payments/oa/oa-payment-e2e-001/detail") {
      return json(route, oaPendingPaymentDetailPayload("oa"));
    }

    if (path === "/api/oa-pending-payments/bank-transactions/bank-payment-e2e-001/detail") {
      return json(route, oaPendingPaymentDetailPayload("bank"));
    }

    if (path === "/api/oa-pending-payments/invoices/invoice-payment-e2e-001/detail") {
      return json(route, oaPendingPaymentDetailPayload("invoice"));
    }

    if (path === "/api/pending-invoices/rules") {
      return json(route, pendingInvoiceExpenseRulesPayload());
    }

    if (path === "/api/cost-statistics/explorer") {
      return json(route, costStatisticsExplorerPayload(
        url.searchParams.get("month") ?? "all",
        url.searchParams.get("project_scope") ?? "active",
      ));
    }

    if (path === "/api/cost-statistics/export-preview") {
      return json(route, costStatisticsExportPreviewPayload(url));
    }

    if (path === "/api/cost-statistics/export") {
      return json(route, {
        error: "cost_statistics_export_row_limit_exceeded",
        message: "导出结果超过 20000 行，请缩小筛选范围后重试。",
        details: { total: 20001, limit: 20000 },
      }, 400);
    }

    const costTransactionDetailMatch = path.match(/^\/api\/cost-statistics\/transactions\/([^/]+)$/);
    if (costTransactionDetailMatch) {
      return json(route, costTransactionPayload(decodeURIComponent(costTransactionDetailMatch[1] ?? "")));
    }

    if (path === "/api/cost-statistics") {
      return json(route, {
        month: url.searchParams.get("month") ?? "all",
        summary: costStatisticsExplorerPayload(
          url.searchParams.get("month") ?? "all",
          url.searchParams.get("project_scope") ?? "active",
        ).summary,
        rows: [],
      });
    }

    if (path === "/api/no-oa-bank-batches/tag-selection") {
      return json(route, noOaBankBatchTagSelectionPayload());
    }

    if (path === "/api/no-oa-bank-batches") {
      return json(route, noOaBankBatchesPayload(noOaBankBatchStatus, url.searchParams.get("bucket")));
    }

    if (path === "/api/no-oa-bank-batches/no-oa-batch-e2e-001") {
      return json(route, noOaBankBatchDetailPayload(noOaBankBatchStatus));
    }

    if (path === "/api/no-oa-bank-batches/submit-selection") {
      noOaBankBatchStatus = "submitted";
      return json(route, noOaBankBatchMutationPayload(noOaBankBatchStatus));
    }

    if (path === "/api/no-oa-bank-batches/no-oa-batch-e2e-001/withdraw") {
      noOaBankBatchStatus = "withdrawn";
      return json(route, noOaBankBatchMutationPayload(noOaBankBatchStatus));
    }

    if (path === "/api/output-invoice-collections/rows") {
      return json(route, outputInvoiceCollectionRowsPayload(
        outputInvoiceStatusSaved,
        outputInvoiceReminderSaved,
        outputInvoiceReceiptCreated,
      ));
    }

    if (path === "/api/output-invoice-collections/filter-options") {
      return json(route, outputInvoiceCollectionFilterOptionsPayload(outputInvoiceStatusSaved, outputInvoiceReceiptCreated));
    }

    if (path === "/api/output-invoice-collections/status-rules") {
      return json(route, outputInvoiceCollectionStatusRulesPayload());
    }

    if (path === "/api/output-invoice-collections/receipt-preview") {
      return json(route, outputInvoiceReceiptPreviewPayload());
    }

    if (path === "/api/output-invoice-collections/receipts/history") {
      return json(route, outputInvoiceReceiptHistoryPayload(outputInvoiceReceiptCreated));
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-status") {
      outputInvoiceStatusSaved = true;
      return json(route, {
        ok: true,
        row_id: "output-collection-row-e2e-001",
        lifecycle_status: "updated",
      });
    }

    if (path === "/api/output-invoice-collections/rows/output-collection-row-e2e-001/collection-reminder") {
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
      outputInvoiceReceiptCreated = true;
      return json(route, {
        ok: true,
        receipt: {
          id: "receipt-output-e2e-001",
          receipt_no: "SK2026050002",
          status: "issued",
        },
      });
    }

    if (path === "/api/workbench") {
      return json(route, legacyWorkbenchPayload(relationConfirmed));
    }

    if (path === "/imports/files/preview") {
      latestImportScenario = inferImportScenarioFromPostData(
        `${request.postData() ?? ""}\n${request.headers().referer ?? ""}`,
      );
      return json(route, importSessionPayload(latestImportScenario, false));
    }

    if (path === "/imports/files/confirm") {
      importConfirmed[latestImportScenario] = true;
      return json(route, importSessionPayload(latestImportScenario, true));
    }

    if (path === `/imports/files/sessions/${importSessionIds.bank}`) {
      return json(route, importSessionPayload("bank", importConfirmed.bank));
    }

    if (path === `/imports/files/sessions/${importSessionIds.invoice}`) {
      return json(route, importSessionPayload("invoice", importConfirmed.invoice));
    }

    if (path === "/api/turnover-ledger/tag-selection") {
      return json(route, turnoverLedgerTagSelectionPayload());
    }

    if (path === "/api/turnover-ledger") {
      return json(route, turnoverLedgerPayload(turnoverClosureConfirmed));
    }

    if (path === "/api/turnover-ledger/closures/confirm") {
      turnoverClosureConfirmed = true;
      return json(route, turnoverClosureMutationPayload());
    }

    if (path === "/api/turnover-ledger/relations/turnover_rel_e2e_closure/withdraw") {
      turnoverClosureConfirmed = false;
      return json(route, {
        relation_id: "turnover_rel_e2e_closure",
        status: "withdrawn",
        ...turnoverClosureMutationPayload(),
      });
    }

    if (path === "/api/workbench/summary") {
      return json(route, workbenchSummaryPayload(relationConfirmed));
    }

    if (path === "/api/workbench/groups") {
      const zone = url.searchParams.get("zone") === "paired" ? "paired" : "open";
      return json(route, workbenchGroupsPayload(zone, relationConfirmed));
    }

    if (path === "/api/workbench/ignored") {
      return json(route, { month: url.searchParams.get("month") ?? "all", rows: [] });
    }

    if (path === "/api/workbench/settings") {
      return json(route, workbenchSettingsPayload());
    }

    if (path === "/api/workbench/actions/confirm-link/preview") {
      return json(route, confirmPreviewPayload());
    }

    if (path === "/api/workbench/actions/confirm-link") {
      relationConfirmed = true;
      return json(route, confirmResultPayload());
    }

    if (path === "/api/bank-details/accounts") {
      return json(route, bankAccountsPayload());
    }

    if (path === "/api/bank-details/transactions") {
      return json(route, bankTransactionsPayload(relationConfirmed, importConfirmed.bank));
    }

    if (path === "/api/bank-details/auto-tag-rules") {
      return json(route, bankAutoTagRulesPayload());
    }

    if (path === "/api/pending-invoices/rows") {
      return json(route, pendingInvoiceRowsPayload(relationConfirmed));
    }

    if (path === "/api/pending-invoices/filter-options") {
      return json(route, pendingInvoiceFilterOptionsPayload(relationConfirmed));
    }

    if (path === "/api/batch-accounting") {
      return json(route, batchAccountingPayload(url, batchAccountingSubmitted));
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

    return json(route, {});
  });

  return {
    calls,
    count(methodAndPath: string) {
      return calls.filter((entry) => entry === methodAndPath).length;
    },
  };
}
