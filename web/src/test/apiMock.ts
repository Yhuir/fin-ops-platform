import { vi } from "vitest";

import { SELECTABLE_CATEGORY_OPTIONS } from "../features/bankDetails/categoryOptions";

type MockFetchResponse = {
  status?: number;
  body: unknown;
};

type MockFetchResult = MockFetchResponse | Response;

type MockFetchHandler = (request: {
  url: URL;
  init?: RequestInit;
  jsonBody: Record<string, unknown> | null;
  formData: FormData | null;
}) => MockFetchResult | Promise<MockFetchResult>;

type MockApiOptions = {
  workbenchErrorMonths?: string[];
  workbenchEmptyPayload?: boolean;
  taxErrorMonths?: string[];
  costErrorMonths?: string[];
  costExplorerFailuresBeforeSuccess?: number;
  costExplorerDelayMs?: number;
  costDetailFailuresBeforeSuccess?: number;
  costDetailDelayMs?: number;
  costExportErrorViews?: string[];
  costDuplicateTransactionRows?: boolean;
  costTagRulesCanSave?: boolean;
  sessionMode?: "authorized" | "forbidden" | "expired" | "error";
  sessionAccessTier?: "admin" | "full_access" | "read_export_only" | "denied";
  sessionUsername?: string;
  sessionDisplayName?: string;
  actionDelayMs?: number;
  workbenchLoadDelayMs?: number;
  workbenchBackgroundLoadDelayMs?: number;
  workbenchPrimaryDelayMs?: number;
  workbenchIgnoredDelayMs?: number;
  workbenchSettingsDelayMs?: number;
  operationBarrierDelay?: Promise<void>;
  operationBarrierStatus?: Record<string, unknown>;
  importPreviewDelayMs?: number;
  etcImportPreviewDelayMs?: number;
  importConfirmPreviewStale?: boolean;
  importConfirmOperationBarrierTargets?: Array<Record<string, string>>;
  etcImportConfirmPreviewStale?: boolean;
  etcImportConfirmStaleReconciliationTask?: boolean;
  etcImportBlockingIssues?: Array<Record<string, unknown>>;
  etcInvoiceStoreBatches?: Array<Record<string, unknown>>;
  readyEtcReconciliationTasks?: Array<Record<string, unknown>>;
  workbenchColumnLayouts?: {
    oa?: string[];
    bank?: string[];
    invoice?: string[];
  };
  emptyBodyPaths?: string[];
  workbenchOaSyncStatuses?: Array<Record<string, unknown>>;
  dataResetPasswordShouldFail?: boolean;
  dataResetJobPollsBeforeComplete?: number;
  backgroundJobs?: Array<Record<string, unknown>>;
  backgroundJobRetryStatus?: number;
  backgroundJobRetryBody?: Record<string, unknown>;
  backgroundJobAcknowledgeStatus?: number;
  backgroundJobAcknowledgeBody?: Record<string, unknown>;
  appHealth?: Record<string, unknown>;
  appHealthErrorStatus?: number;
  appHealthErrorBody?: Record<string, unknown>;
  appHealthDashboard?: Record<string, unknown>;
  appHealthDashboardSequence?: Array<{ status?: number; body: Record<string, unknown> }>;
  appHealthDashboardErrorStatus?: number;
  appHealthDashboardErrorBody?: Record<string, unknown>;
  appHealthSystemAudit?: Record<string, unknown>;
  appHealthSystemAuditStatus?: number;
  appHealthSystemAuditBody?: Record<string, unknown>;
  workbenchExceptionPreview?: Record<string, unknown>;
  workbenchExceptionApply?: Record<string, unknown>;
  workbenchConfirmPreview?: Record<string, unknown>;
  workbenchWithdrawPreview?: Record<string, unknown>;
  transformWorkbenchPayload?: (body: Record<string, unknown>) => Record<string, unknown>;
  transformWorkbenchConfirmActionResponse?: (body: Record<string, unknown>) => Record<string, unknown>;
  transformWorkbenchWithdrawActionResponse?: (body: Record<string, unknown>) => Record<string, unknown>;
  workbenchExceptionPreviewStatus?: number;
  workbenchExceptionApplyStatus?: number;
  workbenchExceptionPreviewDelayMs?: number;
  workbenchExceptionApplyDelayMs?: number;
  includeOaAttachmentPaymentReceipt?: boolean;
  initialImportPreviewFileNames?: string[];
  initialImportPreviewOverrides?: Array<Record<string, string | null | undefined>>;
  bankDetailPostSaveAccountsTotalBalance?: string;
  bankDetailPostSaveTransactionsEmpty?: boolean;
  bankDetailManualAssignmentActive?: boolean;
};

const templateRegistry = [
  {
    template_code: "invoice_export",
    label: "发票导出",
    file_extensions: [".xlsx"],
    record_type: "invoice",
    allowed_batch_types: ["input_invoice", "output_invoice"],
    required_headers: ["发票代码", "发票号码", "销方识别号", "购买方名称"],
  },
  {
    template_code: "bank_statement",
    label: "银行流水",
    file_extensions: [".xls", ".xlsx"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["交易日期或时间", "借方和贷方金额，或金额和收支方向"],
  },
];

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function buildDefaultWorkbenchExceptionPreview(rowIds: string[]) {
  return {
    rule_version: "exception_rules_v1",
    scenario: {
      business_line: "expense",
      scenario_code: "expense_oa_bank_invoice_equal",
      scenario_label: "OA、支出流水和进项发票金额一致",
    },
    amount_summary: {
      oa_total: "58000.00",
      bank_expense_total: "58000.00",
      bank_income_total: "0.00",
      input_invoice_total: "58000.00",
      output_invoice_total: "0.00",
      relation: "all_equal",
    },
    automatic_actions: [],
    available_actions: [
      {
        action_code: "wait_input_invoice",
        label: "追进项发票",
        result_status: "open",
        required_fields: ["note"],
      },
    ],
    warnings: [],
    workflow_projection: {
      next_status: "open",
    },
    candidate_evidence: [
      {
        id: "mock-candidate",
        label: `已选择 ${rowIds.length} 条记录`,
        detail: "前端 mock preview 由后端驱动动作清单。",
      },
    ],
    can_apply: true,
  };
}

function createEtcInvoiceStore(options: Pick<MockApiOptions, "etcInvoiceStoreBatches"> = {}) {
  let invoices = [
    {
      id: "etc-inv-001",
      invoice_number: "ETC-2026-001",
      issue_date: "2026-02-27",
      passage_start_date: "2026-02-27",
      passage_end_date: "2026-02-27",
      plate_number: "云ADA0381",
      seller_name: "云南高速通行费",
      buyer_name: "云南溯源科技",
      amount_without_tax: "12.34",
      tax_amount: "0.73",
      total_amount: "13.07",
      status: "unsubmitted" as const,
      has_pdf: true,
      has_xml: true,
    },
    {
      id: "etc-inv-002",
      invoice_number: "ETC-2026-002",
      issue_date: "2026-02-27",
      passage_start_date: "2026-02-27",
      passage_end_date: "2026-02-27",
      plate_number: "云ADA0381",
      seller_name: "云南高速通行费",
      buyer_name: "云南溯源科技",
      amount_without_tax: "18.10",
      tax_amount: "1.09",
      total_amount: "19.19",
      status: "unsubmitted" as const,
      has_pdf: true,
      has_xml: true,
    },
    {
      id: "etc-inv-003",
      invoice_number: "ETC-2026-003",
      issue_date: "2026-02-28",
      passage_start_date: "2026-02-28",
      passage_end_date: "2026-02-28",
      plate_number: "云A8H66Q",
      seller_name: "昆明绕城高速",
      buyer_name: "云南溯源科技",
      amount_without_tax: "20.14",
      tax_amount: "1.21",
      total_amount: "21.35",
      status: "unsubmitted" as const,
      has_pdf: false,
      has_xml: true,
    },
    {
      id: "etc-inv-004",
      invoice_number: "ETC-2026-004",
      issue_date: "2026-01-18",
      passage_start_date: "2026-01-18",
      passage_end_date: "2026-01-18",
      plate_number: "云ADA0381",
      seller_name: "云南高速通行费",
      buyer_name: "云南溯源科技",
      amount_without_tax: "30.00",
      tax_amount: "1.80",
      total_amount: "31.80",
      status: "submitted" as const,
      has_pdf: true,
      has_xml: true,
    },
  ];
  let batches = [
    {
      id: "etc-batch-unsubmitted-01",
      etc_batch_id: "ETC-2026-03-A",
      external_batch_id: "ETC-2026-03-A",
      status: "unsubmitted" as const,
      source_type: "normal_oa_draft",
      invoice_ids: ["etc-inv-001", "etc-inv-002"],
      linked_oa_row_id: null,
      linked_oa_case_id: null,
      linked_oa_applicant: null,
      linked_oa_apply_date: null,
      linked_oa_amount: null,
      amount_delta: null,
      note: "",
    },
    {
      id: "etc-batch-unsubmitted-02",
      etcBatchId: "ETC-2026-03-B",
      externalBatchId: "ETC-2026-03-B",
      status: "unsubmitted" as const,
      sourceType: "normal_oa_draft",
      invoiceIds: ["etc-inv-003"],
      linkedOaRowId: null,
      linkedOaCaseId: null,
      linkedOaApplicant: null,
      linkedOaApplyDate: null,
      linkedOaAmount: null,
      amountDelta: null,
      note: "",
    },
    {
      id: "etc-batch-submitted-01",
      etc_batch_id: "ETC-HIST-2026-01",
      external_batch_id: "ETC-HIST-2026-01",
      status: "submitted" as const,
      source_type: "historical_repair",
      invoice_ids: ["etc-inv-004"],
      linked_oa_row_id: "oa-exp-1994",
      linked_oa_case_id: "etc-historical-2026-01",
      linked_oa_applicant: "刘树刚",
      linked_oa_apply_date: "2026-02-02",
      linked_oa_amount: "31.80",
      amount_delta: "0.00",
      note: "历史补关联",
    },
  ];
  if (options.etcInvoiceStoreBatches) {
    batches = options.etcInvoiceStoreBatches.map((batch) => ({ ...batch })) as typeof batches;
  }

  const textField = (source: Record<string, unknown>, ...keys: string[]) => {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
    return "";
  };

  const stringListField = (source: Record<string, unknown>, ...keys: string[]) => {
    for (const key of keys) {
      const value = source[key];
      if (Array.isArray(value)) {
        return value.map((item) => String(item).trim()).filter(Boolean);
      }
    }
    return [];
  };

  const numberField = (source: Record<string, unknown>, fallback: number, ...keys: string[]) => {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === "number" && Number.isFinite(value)) {
        return value;
      }
    }
    return fallback;
  };

  const businessStatusForBatch = (batch: (typeof batches)[number]) => {
    const rawBatch = batch as Record<string, unknown>;
    return textField(rawBatch, "business_status", "businessStatus")
      || (batch.status === "submitted" ? "oa_submitted" : "imported");
  };

  const businessBatchIsSubmitted = (batch: (typeof batches)[number]) =>
    ["oa_submitted", "manually_marked_submitted"].includes(businessStatusForBatch(batch));

  const businessBatchBucket = (batch: (typeof batches)[number]) => {
    const status = businessStatusForBatch(batch);
    if (["oa_submitted", "manually_marked_submitted", "closed"].includes(status)) {
      return "submitted";
    }
    return status === "oa_confirmation_pending" ? "staged" : "unsubmitted";
  };

  const batchBusinessIds = (batch: (typeof batches)[number]) => {
    const rawBatch = batch as Record<string, unknown>;
    return new Set([
      batch.id,
      textField(rawBatch, "business_batch_id", "businessBatchId"),
      textField(rawBatch, "submission_batch_id", "submissionBatchId"),
      textField(rawBatch, "external_etc_batch_id", "externalEtcBatchId"),
      textField(rawBatch, "external_batch_id", "externalBatchId"),
      textField(rawBatch, "etc_batch_id", "etcBatchId"),
      ...stringListField(rawBatch, "import_batch_ids", "importBatchIds"),
    ].filter(Boolean));
  };

  const findBatchByBusinessId = (batchId: string) => {
    const normalizedId = String(batchId ?? "").trim();
    return batches.find((item) => batchBusinessIds(item).has(normalizedId)) ?? null;
  };

  const getBatchInvoiceIds = (batch: (typeof batches)[number]) => (
    "invoice_ids" in batch ? batch.invoice_ids : batch.invoiceIds
  ) ?? [];

  const invoicesForBatch = (batch: (typeof batches)[number]) => {
    const invoiceIds = new Set(getBatchInvoiceIds(batch));
    return invoices.filter((invoice) => invoiceIds.has(invoice.id));
  };

  const monthFromBatchIdentifier = (value: unknown) => {
    const text = String(value ?? "");
    const dashed = text.match(/(20\d{2})[-/年](0?[1-9]|1[0-2])/);
    if (dashed) {
      return `${dashed[1]}-${String(dashed[2]).padStart(2, "0")}`;
    }
    const compact = text.match(/(20\d{2})(0[1-9]|1[0-2])(?:\d{2})?/);
    return compact ? `${compact[1]}-${compact[2]}` : "";
  };

  const batchScopeMonth = (batch: (typeof batches)[number], items = invoicesForBatch(batch)) => {
    const rawBatch = batch as Record<string, unknown>;
    const amountBreakdown = typeof rawBatch.amount_breakdown === "object" && rawBatch.amount_breakdown !== null
      ? rawBatch.amount_breakdown as Record<string, unknown>
      : typeof rawBatch.amountBreakdown === "object" && rawBatch.amountBreakdown !== null
        ? rawBatch.amountBreakdown as Record<string, unknown>
        : {};
    return textField(rawBatch, "scope_month", "scopeMonth")
      || textField(amountBreakdown, "scope_month", "scopeMonth")
      || monthFromBatchIdentifier(textField(rawBatch, "external_etc_batch_id", "externalEtcBatchId"))
      || monthFromBatchIdentifier(textField(rawBatch, "external_batch_id", "externalBatchId"))
      || monthFromBatchIdentifier(textField(rawBatch, "etc_batch_id", "etcBatchId"))
      || String(items[0]?.issue_date ?? "").slice(0, 7);
  };

  const batchCounts = () => ({
    unsubmitted: batches.filter((batch) => batch.status === "unsubmitted").length,
    submitted: batches.filter((batch) => batch.status === "submitted").length,
  });

  const batchDateRange = (items: typeof invoices, startKey: "issue_date" | "passage_start_date", endKey: "issue_date" | "passage_end_date") => {
    const starts = items.map((invoice) => invoice[startKey]).filter(Boolean).sort();
    const ends = items.map((invoice) => invoice[endKey]).filter(Boolean).sort();
    return {
      start: starts[0] ?? null,
      end: ends[ends.length - 1] ?? null,
    };
  };

  const summarizePlates = (items: typeof invoices) => {
    const byPlate = new Map<string, { invoice_count: number; total_amount: string }>();
    items.forEach((invoice) => {
      const current = byPlate.get(invoice.plate_number) ?? { invoice_count: 0, total_amount: "0.00" };
      byPlate.set(invoice.plate_number, {
        invoice_count: current.invoice_count + 1,
        total_amount: (Number(current.total_amount) + Number(invoice.total_amount)).toFixed(2),
      });
    });
    return Array.from(byPlate.entries()).map(([plate_number, summary]) => ({
      plate_number,
      ...summary,
    }));
  };

  const hydrateBatch = (batch: (typeof batches)[number], includeInvoices = false) => {
    const items = invoicesForBatch(batch);
    const issueRange = batchDateRange(items, "issue_date", "issue_date");
    const passageRange = batchDateRange(items, "passage_start_date", "passage_end_date");
    const plateSummary = summarizePlates(items);
    const totalAmount = items.reduce((sum, invoice) => sum + Number(invoice.total_amount), 0).toFixed(2);
    const taxAmount = items.reduce((sum, invoice) => sum + Number(invoice.tax_amount), 0).toFixed(2);
    return {
      ...batch,
      invoice_count: items.length,
      total_amount: totalAmount,
      tax_amount: taxAmount,
      issue_start_date: issueRange.start,
      issue_end_date: issueRange.end,
      passage_start_date: passageRange.start,
      passage_end_date: passageRange.end,
      plate_count: plateSummary.length,
      plate_summary: plateSummary,
      ...(includeInvoices ? { invoice_items: cloneJson(items) } : {}),
    };
  };

  const hydrateBusinessBatch = (batch: (typeof batches)[number], includeInvoices = false) => {
    const hydrated = hydrateBatch(batch, includeInvoices);
    const batchId = "id" in batch ? batch.id : "";
    const rawBatch = batch as Record<string, unknown>;
    const isSubmitted = batch.status === "submitted";
    const scopeMonth = batchScopeMonth(batch);
    const amountBreakdown = typeof rawBatch.amount_breakdown === "object" && rawBatch.amount_breakdown !== null
      ? rawBatch.amount_breakdown as Record<string, unknown>
      : typeof rawBatch.amountBreakdown === "object" && rawBatch.amountBreakdown !== null
        ? rawBatch.amountBreakdown as Record<string, unknown>
        : {};
    const businessBatchId = textField(rawBatch, "business_batch_id", "businessBatchId") || batchId;
    const importBatchIds = stringListField(rawBatch, "import_batch_ids", "importBatchIds");
    const submissionBatchId = textField(rawBatch, "submission_batch_id", "submissionBatchId");
    const externalEtcBatchId = textField(rawBatch, "external_etc_batch_id", "externalEtcBatchId");
    const invoiceSummary = typeof rawBatch.invoice_summary === "object" && rawBatch.invoice_summary !== null
      ? rawBatch.invoice_summary as Record<string, unknown>
      : typeof rawBatch.invoiceSummary === "object" && rawBatch.invoiceSummary !== null
        ? rawBatch.invoiceSummary as Record<string, unknown>
        : null;
    const batchStatus = businessStatusForBatch(batch);
    const canCreateDraft = ["imported", "oa_draft_failed", "not_submitted", "manually_marked_not_submitted"].includes(batchStatus)
      && hydrated.invoice_count > 0;
    return {
      business_batch_id: businessBatchId,
      task_id: textField(rawBatch, "task_id", "taskId") || (batchId === "etc-batch-unsubmitted-01" ? "etc-recon-task-001" : ""),
      title: textField(rawBatch, "title", "name"),
      status: batchStatus,
      version: numberField(rawBatch, 7, "version"),
      owner_user_id: "web_finance_user",
      owner_org_id: "finance",
      import_batch_ids: importBatchIds.length ? importBatchIds : [`${batchId}-import-001`],
      submission_batch_id: submissionBatchId || (isSubmitted ? batchId : ""),
      external_etc_batch_id: externalEtcBatchId || (
        hydrated.external_batch_id
        ?? hydrated.externalBatchId
        ?? hydrated.etc_batch_id
        ?? hydrated.etcBatchId
      ),
      oa_draft_id: "",
      oa_draft_url: "",
      oa_row_id: hydrated.linked_oa_row_id ?? hydrated.linkedOaRowId ?? "",
      oa_process_status: isSubmitted ? "in_progress" : "",
      invoice_summary: {
        count: numberField(invoiceSummary ?? {}, hydrated.invoice_count, "count"),
        amount: textField(invoiceSummary ?? {}, "amount") || hydrated.total_amount,
      },
      create_oa_draft_action: {
        enabled: canCreateDraft,
        code: canCreateDraft ? "ready" : batchStatus === "oa_confirmation_pending" ? "oa_confirmation_pending" : "invalid_batch_status",
        message: canCreateDraft ? "可以提交审批。" : batchStatus === "oa_confirmation_pending" ? "审批草稿已创建，请先确认是否已在 OA 提交。" : "当前批次状态不能创建审批草稿。",
      },
      scope_month: scopeMonth,
      amount_breakdown: {
        ...amountBreakdown,
        scope_month: scopeMonth,
      },
      created_at: "2026-05-19T09:00:00+08:00",
      updated_at: "2026-05-19T09:00:00+08:00",
      ...(includeInvoices ? {
        invoice_ids: getBatchInvoiceIds(batch),
        import_attempts: [
          {
            attempt_id: `${batchId}-attempt-001`,
            import_batch_id: `${batchId}-import-001`,
            status: "imported",
            imported: hydrated.invoice_count,
            duplicates_skipped: 0,
            attachments_completed: 0,
            failed: 0,
            created_at: "2026-05-19T09:00:00+08:00",
          },
        ],
        audit_events: [],
        invoice_items: hydrated.invoice_items,
      } : {}),
    };
  };

  const counts = () => ({
    unsubmitted: invoices.filter((invoice) => invoice.status === "unsubmitted").length,
    submitted: invoices.filter((invoice) => invoice.status === "submitted").length,
  });

  return {
    list({ status, month, plate, keyword }: { status?: string | null; month?: string | null; plate?: string | null; keyword?: string | null }) {
      const normalizedKeyword = String(keyword ?? "").trim();
      const normalizedPlate = String(plate ?? "").trim();
      const rows = invoices.filter((invoice) => {
        if (status && invoice.status !== status) {
          return false;
        }
        if (month && !invoice.issue_date.startsWith(month)) {
          return false;
        }
        if (normalizedPlate && !invoice.plate_number.includes(normalizedPlate)) {
          return false;
        }
        if (normalizedKeyword) {
          const searchable = `${invoice.invoice_number} ${invoice.seller_name} ${invoice.buyer_name} ${invoice.plate_number}`;
          if (!searchable.includes(normalizedKeyword)) {
            return false;
          }
        }
        return true;
      });
      return {
        counts: counts(),
        items: cloneJson(rows),
        pagination: {
          page: 1,
          page_size: 100,
          total: rows.length,
        },
      };
    },
    listBusinessBatches({
      bucket,
      month,
      plate,
      keyword,
      page = 1,
      pageSize = 100,
    }: {
      bucket?: string | null;
      month?: string | null;
      plate?: string | null;
      keyword?: string | null;
      page?: number;
      pageSize?: number;
    }) {
      const normalizedBucket = ["unsubmitted", "staged", "submitted"].includes(String(bucket)) ? bucket : "unsubmitted";
      const normalizedKeyword = String(keyword ?? "").trim().toLowerCase();
      const normalizedPlate = String(plate ?? "").trim().toLowerCase();
      const filteredBatches = batches
        .filter((batch) => {
          const items = invoicesForBatch(batch);
          const scopeMonth = batchScopeMonth(batch, items);
          if (month && scopeMonth) {
            return scopeMonth === month;
          }
          if (month && !items.some((invoice) => [
              invoice.issue_date,
              invoice.passage_start_date,
              invoice.passage_end_date,
            ].some((value) => String(value ?? "").startsWith(month)))) {
            return false;
          }
          if (normalizedPlate && !items.some((invoice) => invoice.plate_number.toLowerCase().includes(normalizedPlate))) {
            return false;
          }
          if (normalizedKeyword) {
            const searchable = [
              "etc_batch_id" in batch ? batch.etc_batch_id : batch.etcBatchId,
              "external_batch_id" in batch ? batch.external_batch_id : batch.externalBatchId,
              ...items.map((invoice) => `${invoice.invoice_number} ${invoice.seller_name} ${invoice.plate_number}`),
            ].join(" ").toLowerCase();
            return searchable.includes(normalizedKeyword);
          }
          return true;
        });
      const rows = filteredBatches
        .filter((batch) => {
          return businessBatchBucket(batch) === normalizedBucket;
        })
        .map((batch) => hydrateBusinessBatch(batch))
        .filter(Boolean);
      return {
        ok: true,
        data: {
          counts: {
            unsubmitted: filteredBatches.filter((batch) => businessBatchBucket(batch) === "unsubmitted").length,
            staged: filteredBatches.filter((batch) => businessBatchBucket(batch) === "staged").length,
            submitted: filteredBatches.filter((batch) => businessBatchBucket(batch) === "submitted").length,
          },
          items: cloneJson(rows.slice((page - 1) * pageSize, page * pageSize)),
          pagination: {
            page,
            page_size: pageSize,
            total: rows.length,
          },
        },
        error: null,
      };
    },
    createBusinessBatch(taskId: string, title = "新建ETC批次") {
      const id = `etc_business_batch_new_${String(batches.length + 1).padStart(4, "0")}`;
      const batch = {
        id,
        business_batch_id: id,
        task_id: taskId,
        title,
        etc_batch_id: "新建ETC批次",
        external_batch_id: "新建ETC批次",
        business_status: "draft",
        version: 1,
        status: "unsubmitted" as const,
        source_type: "etc_business_batch",
        invoice_ids: [],
        import_batch_ids: [],
        invoice_summary: { count: 0, amount: "0.00" },
        linked_oa_row_id: null,
        linked_oa_case_id: null,
        linked_oa_applicant: null,
        linked_oa_apply_date: null,
        linked_oa_amount: null,
        amount_delta: "0.00",
        note: "",
      };
      batches = [batch as (typeof batches)[number], ...batches];
      return {
        ok: true,
        data: {
          businessBatch: cloneJson(hydrateBusinessBatch(batch as (typeof batches)[number], true)),
        },
        error: null,
      };
    },
    updateBusinessBatchTitle(batchId: string, title: string) {
      const normalizedTitle = String(title ?? "").trim();
      if (!normalizedTitle) {
        return {
          status: 422,
          body: { ok: false, data: null, error: { code: "invalid_business_batch_title", message: "批次标题不能为空。" } },
        };
      }
      const existing = findBatchByBusinessId(batchId);
      if (!existing) {
        return {
          status: 404,
          body: { ok: false, data: null, error: { code: "business_batch_not_found", message: "ETC业务批次不存在。" } },
        };
      }
      if (businessBatchIsSubmitted(existing)) {
        return {
          status: 422,
          body: { ok: false, data: null, error: { code: "business_batch_title_locked", message: "已提交批次不能修改标题。" } },
        };
      }
      batches = batches.map((item) =>
        batchBusinessIds(item).has(batchId)
          ? {
              ...item,
              title: normalizedTitle,
              version: numberField(item as Record<string, unknown>, 1, "version") + 1,
            }
          : item,
      );
      const updated = findBatchByBusinessId(batchId);
      return {
        status: 200,
        body: {
          ok: true,
          data: {
            businessBatch: updated ? cloneJson(hydrateBusinessBatch(updated, true)) : null,
          },
          error: null,
        },
      };
    },
    businessBatchDetail(batchId: string) {
      const batch = findBatchByBusinessId(batchId);
      return batch ? cloneJson(hydrateBusinessBatch(batch, true)) : null;
    },
    businessBatchDraft(batchId: string) {
      const batch = findBatchByBusinessId(batchId);
      if (!batch) {
        return null;
      }
      return {
        ...hydrateBusinessBatch(batch, true),
        status: "oa_confirmation_pending",
        version: 8,
        submission_batch_id: "etc_batch_0027",
        oa_draft_id: "oa_draft_001",
        oa_draft_url: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
      };
    },
    deleteBatch(batchId: string, options: { allowSubmitted?: boolean } = {}) {
      const batch = options.allowSubmitted ? findBatchByBusinessId(batchId) : batches.find((item) => item.id === batchId);
      if (!batch || (batch.status !== "unsubmitted" && !options.allowSubmitted)) {
        return false;
      }
      const invoiceIds = new Set(getBatchInvoiceIds(batch));
      batches = batches.filter((item) => item.id !== batchId);
      if (options.allowSubmitted) {
        invoices = invoices.map((invoice) =>
          invoiceIds.has(invoice.id) ? { ...invoice, status: "unsubmitted" as const } : invoice
        );
      }
      return true;
    },
    previewZip(fileNames: string[], blockingIssues: Array<Record<string, unknown>> = []) {
      return {
        sessionId: "etc_import_session_0001",
        imported: 1,
        duplicatesSkipped: 1,
        attachmentsCompleted: 1,
        failed: 1,
        audit: {
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
        },
        items: [
          {
            invoiceNumber: "ETC-2026-005",
            fileName: fileNames[0] ?? "etc-2026-03.zip",
            status: "imported",
            reason: "新发票待导入",
          },
          {
            invoiceNumber: "ETC-2026-001",
            fileName: fileNames[0] ?? "etc-2026-03.zip",
            status: "duplicate_skipped",
            reason: "发票号码已存在",
          },
          {
            invoiceNumber: "ETC-2026-003",
            fileName: fileNames[1] ?? fileNames[0] ?? "etc-2026-04.zip",
            status: "attachment_completed",
            reason: "已补齐 PDF 附件",
          },
          {
            invoiceNumber: "",
            fileName: fileNames[1] ?? fileNames[0] ?? "etc-2026-04.zip",
            status: "failed",
            reason: "zip 内缺少可识别 XML",
          },
        ],
        reconciliationFilter: {
          taskId: "etc_task_ready_001",
          taskVersion: 7,
          confirmedItemSetHash: "sha256:mock",
          allowedInvoiceNumbers: ["ETC-2026-005"],
          items: [],
          blockingIssues,
        },
      };
    },
    confirmImport() {
      return {
        job: {
          job_id: "job_etc_import_0001",
          type: "etc_invoice_import",
          label: "导入 ETC发票",
          short_label: "正在导入 ETC发票 0/4",
          status: "queued",
          phase: "queued",
          current: 0,
          total: 4,
          percent: 0,
          message: "ETC发票导入任务已创建。",
          result_summary: {
            created: 0,
            imported: 0,
            updated: 0,
            attachments_completed: 0,
            duplicates: 0,
            failed: 0,
            total: 4,
          },
          error: null,
          created_at: "2026-05-03T10:00:00+00:00",
          updated_at: "2026-05-03T10:00:00+00:00",
          finished_at: null,
        },
      };
    },
    readyReconciliationTasks(tasks?: Array<Record<string, unknown>>) {
      return {
        tasks: tasks ?? [
          {
            taskId: "etc_task_ready_001",
            status: "ready_for_import",
            version: 7,
            title: "2026-03 ETC 对账",
            periodStart: "2026-03-01",
            periodEnd: "2026-03-31",
            oaTotalAmount: "108.40",
            etcInvoiceCount: 8,
            supplementCount: 1,
            vehiclePlates: ["云ADA0381"],
          },
        ],
      };
    },
  };
}

function createEtcReconciliationTaskStore() {
  let nextTaskNumber = 2;
  let tasks = [
    {
      taskId: "etc-recon-task-001",
      status: "reviewing",
      version: 3,
      title: "2026-02 ETC 对账",
      periodStart: "2026-02-27",
      periodEnd: "2026-02-28",
      statementPeriodStart: "2026-02-01",
      statementPeriodEnd: "2026-02-29",
      oaTotalAmount: "120.00",
      etcInvoiceAmount: "90.00",
      supplementAmount: "30.00",
      etcInvoiceCount: 2,
      supplementCount: 1,
      canConfirm: false,
      vehiclePlates: ["云ADA0381", "云A8H66Q"],
      creditCardItems: [
        {
          item_id: "card-item-suggested",
          transaction_date: "2026-02-27",
          posting_date: "2026-02-28",
          card_last4: "7788",
          description: "财付通-微信支付-贵州黔通智联",
          amount: "30.00",
          settlement_amount: "30.00",
          is_etc_candidate: true,
          candidate_reason: "ETC关键词",
          recommendation_status: "suggested_match",
          manual_resolution: "unresolved",
        },
        {
          item_id: "card-item-missing",
          transaction_date: "2026-02-28",
          posting_date: "2026-02-29",
          card_last4: "7788",
          description: "高速通行费",
          amount: "60.00",
          settlement_amount: "60.00",
          is_etc_candidate: true,
          recommendation_status: "missing_ticket",
          manual_resolution: "manual_confirmed",
          review_note: "纸质说明已补",
        },
        {
          item_id: "card-item-covered",
          transaction_date: "2026-02-28",
          posting_date: "2026-02-29",
          card_last4: "7788",
          description: "停车费补充凭证",
          amount: "30.00",
          settlement_amount: "30.00",
          is_etc_candidate: false,
          recommendation_status: "not_candidate",
          manual_resolution: "covered_by_supplement",
        },
      ],
      ticketRootItems: [
        {
          item_id: "ticket-item-001",
          vehicle_plate: "云ADA0381",
          transaction_at: "2026-02-27T10:00:00",
          amount: "30.00",
          entry_station: "昆明东",
          exit_station: "玉溪北",
          invoice_count: 1,
          recommendation_status: "suggested_match",
          linked_credit_card_item_ids: ["card-item-suggested"],
        },
        {
          item_id: "ticket-item-extra",
          vehicle_plate: "云A8H66Q",
          transaction_at: "2026-02-28T18:00:00",
          amount: "12.00",
          entry_station: "昆明南",
          exit_station: "呈贡",
          invoice_count: 1,
          recommendation_status: "extra_ticket",
          linked_credit_card_item_ids: [],
        },
      ],
      supplementEvidences: [
        {
          evidence_id: "supplement-001",
          source_name: "parking.pdf",
          evidence_kind: "non_etc_invoice",
          amount: "30.00",
          paid_at: "2026-02-28",
          merchant_name: "停车场",
          tags: ["ETC补充凭证"],
          include_in_etc_zip_check: false,
          include_in_oa_submission: true,
          include_in_workbench: true,
        },
      ],
      reconciledItems: [
        {
          item_id: "RECONCILED-card-item-covered",
          credit_card_item_id: "card-item-covered",
          ticket_root_item_ids: [],
          supplement_evidence_ids: ["supplement-001"],
          resolution: "covered_by_supplement",
          note: "补充非ETC凭证",
          claim_amount: "30.00",
          evidence_amount: "30.00",
          amount_delta: "0.00",
          amount_delta_note: "",
        },
      ],
      parseIssues: [
        {
          issue_id: "parse-issue-001",
          severity: "blocking",
          message: "票根网缺少车牌号，已阻止该页进入核对。",
          source_page: 2,
          field_name: "vehicle_plate",
        },
      ],
    },
    {
      taskId: "etc_task_ready_001",
      status: "ready_for_import",
      version: 7,
      title: "2026-03 ETC 对账",
      periodStart: "2026-03-01",
      periodEnd: "2026-03-31",
      statementPeriodStart: "2026-03-01",
      statementPeriodEnd: "2026-03-31",
      oaTotalAmount: "108.40",
      etcInvoiceAmount: "96.40",
      supplementAmount: "12.00",
      etcInvoiceCount: 8,
      supplementCount: 1,
      canConfirm: false,
      vehiclePlates: ["云ADA0381"],
      creditCardItems: [],
      ticketRootItems: [],
      supplementEvidences: [],
      parseIssues: [],
    },
  ];

  const findTask = (taskId: string) => tasks.find((task) => task.taskId === taskId);
  const bump = (taskId: string, patch: Record<string, unknown> = {}) => {
    const existing = findTask(taskId);
    if (!existing) {
      return null;
    }
    const next = { ...existing, ...patch, version: existing.version + 1 };
    tasks = tasks.map((task) => (task.taskId === taskId ? next : task));
    return cloneJson(next);
  };

  return {
    list() {
      return { tasks: cloneJson(tasks) };
    },
    ready() {
      return {
        tasks: cloneJson(tasks.filter((task) => task.status === "ready_for_import")),
        unavailableTasks: cloneJson(
          tasks
            .filter((task) => task.status !== "ready_for_import")
            .map((task) => ({
              ...task,
              importBlockers: [
                {
                  code: task.status === "imported" ? "already_imported" : "not_confirmed",
                  message: task.status === "imported"
                    ? "该 ETC 对账任务已导入。如需重导，请先移除已导入 ETC 发票。"
                    : "请先在 ETC 对账页确认对账。",
                },
              ],
            })),
        ),
      };
    },
    get(taskId: string) {
      const task = findTask(taskId);
      return task ? cloneJson(task) : null;
    },
    updateTitle(taskId: string, title: string) {
      const normalizedTitle = String(title ?? "").trim();
      if (!normalizedTitle || !findTask(taskId)) {
        return null;
      }
      tasks = tasks.map((task) =>
        task.taskId === taskId
          ? { ...task, title: normalizedTitle, version: task.version + 1 }
          : task,
      );
      return cloneJson(findTask(taskId));
    },
    deleteTask(taskId: string, expectedVersion: number) {
      const task = findTask(taskId);
      if (!task) {
        return { ok: false, status: 404, body: { message: "ETC对账任务不存在。" } };
      }
      if (task.version !== expectedVersion) {
        return { ok: false, status: 409, body: { error: "task_version_conflict", message: "task_version_conflict" } };
      }
      const hasSubmissionLink = Boolean(
        String(task.oaDraftBatchId ?? task.oa_draft_batch_id ?? "").trim()
        || String(task.etcBatchId ?? task.etc_batch_id ?? "").trim()
        || String(task.submittedConfirmedAt ?? task.submitted_confirmed_at ?? "").trim(),
      );
      if (!["draft", "reviewing", "ready_for_import", "imported"].includes(String(task.status)) || hasSubmissionLink) {
        return { ok: false, status: 409, body: { error: "invalid_reconciliation_task_status", message: "invalid_reconciliation_task_status" } };
      }
      tasks = tasks.filter((item) => item.taskId !== taskId);
      return { ok: true, status: 200, body: { deleted: true, taskId, kind: "reconciliation_task" } };
    },
    clearImportedInvoices(taskId: string, expectedVersion: number) {
      const task = findTask(taskId);
      if (!task) {
        return { ok: false, status: 404, body: { message: "ETC对账任务不存在。" } };
      }
      if (task.version !== expectedVersion) {
        return { ok: false, status: 409, body: { error: "task_version_conflict", message: "task_version_conflict" } };
      }
      return {
        ok: true,
        status: 200,
        body: bump(taskId, {
          status: "ready_for_import",
          importBatchId: "",
          import_batch_id: "",
          etcBatchId: "",
          etc_batch_id: "",
        }),
      };
    },
    create(title: string) {
      const task = {
        ...cloneJson(tasks[0]),
        taskId: `etc-recon-task-${String(nextTaskNumber).padStart(3, "0")}`,
        title: title || "新建ETC对账批次",
        status: "draft",
        version: 1,
        canConfirm: false,
        creditCardItems: [],
        ticketRootItems: [],
        supplementEvidences: [],
        reconciledItems: [],
        parseIssues: [],
      };
      nextTaskNumber += 1;
      tasks = [task, ...tasks];
      return cloneJson(task);
    },
    upload(taskId: string) {
      return bump(taskId);
    },
    uploadSupplementForCard(taskId: string, itemId: string) {
      const existing = findTask(taskId);
      if (!existing) {
        return null;
      }
      const evidenceId = `supplement-${String((existing.supplementEvidences ?? []).length + 1).padStart(3, "0")}`;
      return bump(taskId, {
        canConfirm: true,
        supplementAmount: "25.00",
        supplementCount: (existing.supplementEvidences ?? []).length + 1,
        creditCardItems: existing.creditCardItems.map((item) =>
          item.item_id === itemId || item.itemId === itemId
            ? { ...item, manual_resolution: "covered_by_supplement", manualResolution: "covered_by_supplement", review_note: "补充凭证覆盖" }
            : item,
        ),
        supplementEvidences: [
          ...(existing.supplementEvidences ?? []),
          {
            evidence_id: evidenceId,
            source_name: "parking.pdf",
            evidence_kind: "non_etc_invoice",
            amount: "23.00",
            paid_at: "2026-03-03",
            merchant_name: "停车场",
            tags: ["ETC补充凭证"],
            include_in_etc_zip_check: false,
            include_in_oa_submission: true,
            include_in_workbench: true,
          },
        ],
        reconciledItems: [
          ...(existing.reconciledItems ?? []),
          {
            item_id: `RECONCILED-${itemId}`,
            credit_card_item_id: itemId,
            ticket_root_item_ids: [],
            supplement_evidence_ids: [evidenceId],
            resolution: "covered_by_supplement",
            note: "补充凭证覆盖",
            claim_amount: "25.00",
            evidence_amount: "23.00",
            amount_delta: "2.00",
            amount_delta_note: "补充凭证覆盖",
          },
        ],
      });
    },
    patchItem(taskId: string, itemId: string, payload: Record<string, unknown>) {
      const existing = findTask(taskId);
      if (!existing) {
        return null;
      }
      const action = String(payload.action ?? "");
      if (action === "link_ticket") {
        const ticketItemId = String(payload.ticketItemId ?? payload.ticket_item_id ?? "");
        return bump(taskId, {
          creditCardItems: existing.creditCardItems.map((item) =>
            item.item_id === itemId
              ? { ...item, manual_resolution: "included_etc" }
              : item,
          ),
          ticketRootItems: existing.ticketRootItems.map((item) =>
            item.item_id === ticketItemId
              ? {
                  ...item,
                  linked_credit_card_item_ids: Array.from(new Set([...(item.linked_credit_card_item_ids ?? []), itemId])),
                }
              : item,
          ),
        });
      }
      if (action === "link_supplement") {
        return bump(taskId, {
          creditCardItems: existing.creditCardItems.map((item) =>
            item.item_id === itemId
              ? {
                  ...item,
                  manual_resolution: "covered_by_supplement",
                  review_note: String(payload.note ?? item.review_note ?? ""),
                }
              : item,
          ),
        });
      }
      if (action === "exclude_card") {
        return bump(taskId, {
          creditCardItems: existing.creditCardItems.map((item) =>
            item.item_id === itemId
              ? {
                  ...item,
                  manual_resolution: String(payload.manualResolution ?? payload.manual_resolution ?? "excluded_non_etc"),
                  manual_resolution_reason: String(payload.reason ?? payload.note ?? ""),
                }
              : item,
          ),
        });
      }
      if (action === "manual_confirm") {
        return bump(taskId, {
          creditCardItems: existing.creditCardItems.map((item) =>
            item.item_id === itemId
              ? {
                  ...item,
                  manual_resolution: "manual_confirmed",
                  review_note: String(payload.note ?? ""),
                }
              : item,
          ),
        });
      }
      return bump(taskId, {
        creditCardItems: existing.creditCardItems.map((item) =>
          item.item_id === itemId
            ? {
                ...item,
                manual_resolution: String(payload.manualResolution ?? payload.manual_resolution ?? item.manual_resolution),
              }
            : item,
        ),
      });
    },
    confirm(taskId: string) {
      return bump(taskId, { status: "ready_for_import", canConfirm: false });
    },
    reopen(taskId: string) {
      return bump(taskId, { status: "reviewing" });
    },
  };
}

function detectMockBankSelection(fileName: string) {
  if (fileName.includes("historydetail")) {
    return {
      templateCode: "bank_statement",
      bankName: "工商银行",
      last4: "4080",
    };
  }
  if (fileName.includes("交易明细")) {
    return {
      templateCode: "bank_statement",
      bankName: "平安银行",
      last4: "0093",
    };
  }
  if (fileName.includes("民生")) {
    return {
      templateCode: "bank_statement",
      bankName: "民生银行",
      last4: "9486",
    };
  }
  if (fileName.includes("光大")) {
    return {
      templateCode: "bank_statement",
      bankName: "光大银行",
      last4: "8826",
    };
  }
  return {
    templateCode: "bank_statement",
    bankName: "平安银行",
    last4: "0093",
  };
}

function normalizeMockBankNameForConflict(bankName: string | null) {
  return String(bankName ?? "").replace(/\s+/g, "").replace(/银行$/, "");
}

function mockBankNameAliasMatches(selectedAlias: string, detectedAlias: string) {
  return selectedAlias === detectedAlias || selectedAlias.includes(detectedAlias) || detectedAlias.includes(selectedAlias);
}

function buildImportPreviewPayload(
  fileNames: string[],
  overrides: Array<Record<string, string | null | undefined>> = [],
) {
  const knownFileNames = fileNames.filter((fileName) => fileName !== "README.md");
  const sessionAudit = {
    original_count: knownFileNames.reduce((total, fileName) => total + (fileName.includes("发票") ? 14 : 9), 0),
    unique_count: knownFileNames.reduce((total, fileName) => total + (fileName.includes("发票") ? 12 : 8), 0),
    duplicate_count: knownFileNames.length,
    duplicate_in_file_count: knownFileNames.length,
    duplicate_across_files_count: Math.max(0, knownFileNames.length - 1),
    existing_duplicate_count: 2,
    importable_count: knownFileNames.reduce((total, fileName) => total + (fileName.includes("发票") ? 11 : 7), 0),
    update_count: 0,
    merge_count: 0,
    suspected_duplicate_count: knownFileNames.some((fileName) => fileName.includes("发票")) ? 1 : 0,
    error_count: knownFileNames.some((fileName) => fileName.includes("发票")) ? 1 : 0,
    confirmable_count: knownFileNames.reduce((total, fileName) => total + (fileName.includes("发票") ? 11 : 7), 0),
    skipped_count: knownFileNames.length + 2,
  };
  return {
    session: {
      id: "import_session_0001",
      imported_by: "web_finance_user",
      file_count: fileNames.length,
      status: fileNames.includes("README.md") ? "preview_ready_with_errors" : "preview_ready",
      created_at: "2026-03-26T23:00:00+08:00",
      audit: sessionAudit,
    },
    files: fileNames.map((fileName, index) => {
      if (fileName === "README.md") {
        return {
          id: `import_file_${String(index + 1).padStart(4, "0")}`,
          file_name: fileName,
          template_code: null,
          batch_type: null,
          status: "unrecognized_template",
          message: "无法识别文件模板。",
          row_count: 0,
          success_count: 0,
          error_count: 0,
          duplicate_count: 0,
          suspected_duplicate_count: 0,
          updated_count: 0,
          preview_batch_id: null,
          batch_id: null,
          row_results: [],
        };
      }

      const isInvoice = fileName.includes("发票");
      const override = overrides[index] ?? {};
      const detectedBank = detectMockBankSelection(fileName);
      const templateCode = override.template_code ?? (isInvoice ? "invoice_export" : detectedBank.templateCode);
      const batchType = override.batch_type ?? (isInvoice ? "input_invoice" : "bank_transaction");
      const selectedBankName = override.bank_name ?? null;
      const selectedBankShortName = override.bank_short_name ?? null;
      const selectedBankLast4 = override.last4 ?? null;
      const selectedBankMappingId = override.bank_mapping_id ?? null;
      const selectedBankAliases = [selectedBankName, selectedBankShortName]
        .map((item) => normalizeMockBankNameForConflict(item ?? ""))
        .filter(Boolean);
      const detectedBankAlias = normalizeMockBankNameForConflict(detectedBank.bankName);
      const bankNameMatches = selectedBankAliases.some((alias) => mockBankNameAliasMatches(alias, detectedBankAlias));
      const bankSelectionConflict = !isInvoice && (
        (selectedBankAliases.length > 0 && !bankNameMatches)
        || (selectedBankLast4 !== null && selectedBankLast4 !== detectedBank.last4)
      );
      const conflictMessage = bankSelectionConflict
        ? [
          selectedBankAliases.length > 0 && !bankNameMatches
            ? `银行选择为${selectedBankName}，系统识别为${detectedBank.bankName}`
            : null,
          selectedBankLast4 && selectedBankLast4 !== detectedBank.last4
            ? `后四位选择为${selectedBankLast4}，系统识别为${detectedBank.last4}`
            : null,
        ].filter(Boolean).join("；")
        : null;
      if (!isInvoice && fileName.includes("需映射")) {
        return {
          id: `import_file_${String(index + 1).padStart(4, "0")}`,
          file_name: fileName,
          template_code: "bank_statement",
          batch_type: "bank_transaction",
          status: "unrecognized_template",
          message: "缺少收入金额字段，请补充字段映射。",
          row_count: 0,
          success_count: 0,
          error_count: 0,
          duplicate_count: 0,
          suspected_duplicate_count: 0,
          updated_count: 0,
          preview_batch_id: null,
          batch_id: null,
          selected_bank_mapping_id: selectedBankMappingId,
          selected_bank_name: selectedBankName,
          selected_bank_short_name: selectedBankShortName,
          selected_bank_last4: selectedBankLast4,
          detected_bank_name: detectedBank.bankName,
          detected_last4: detectedBank.last4,
          bank_selection_conflict: false,
          conflict_message: null,
          header_signature: "mock-bank-header-signature",
          mapping_candidates: [
            { key: "0", label: "第1列 · 交易日" },
            { key: "1", label: "第2列 · 支出金额" },
            { key: "2", label: "第3列 · 收到数额" },
            { key: "3", label: "第4列 · 对方名称" },
          ],
          mapping_fields: [
            { key: "txn_date", label: "交易日期", selected: "0", required: true },
            { key: "debit_amount", label: "支出金额", selected: "1", required: true },
            { key: "credit_amount", label: "收入金额", selected: null, required: true },
            { key: "counterparty_name", label: "对方名称", selected: "3", required: false },
          ],
          field_mapping: {
            txn_date: "0",
            debit_amount: "1",
            counterparty_name: "3",
          },
          mapping_source: "auto",
          row_results: [],
        };
      }
      return {
        id: `import_file_${String(index + 1).padStart(4, "0")}`,
        file_name: fileName,
        template_code: templateCode,
        batch_type: batchType,
        status: "preview_ready",
        message: "模板识别成功。",
        row_count: isInvoice ? 14 : 9,
        success_count: isInvoice ? 12 : 8,
        error_count: isInvoice ? 1 : 0,
        duplicate_count: 0,
        suspected_duplicate_count: isInvoice ? 1 : 0,
        updated_count: 0,
        audit: {
          original_count: isInvoice ? 14 : 9,
          unique_count: isInvoice ? 12 : 8,
          duplicate_count: 1,
          duplicate_in_file_count: 1,
          duplicate_across_files_count: index > 0 ? 1 : 0,
          existing_duplicate_count: index === 0 ? 2 : 0,
          importable_count: isInvoice ? 11 : 7,
          update_count: 0,
          merge_count: 0,
          suspected_duplicate_count: isInvoice ? 1 : 0,
          error_count: isInvoice ? 1 : 0,
          confirmable_count: isInvoice ? 11 : 7,
          skipped_count: index === 0 ? 3 : 1,
        },
        preview_batch_id: `batch_import_${String(4444 + index)}`,
        batch_id: null,
        stored_file_path: `/tmp/import_session_0001/import_file_${String(index + 1).padStart(4, "0")}_${fileName}`,
        override_template_code: override.template_code ?? null,
        override_batch_type: override.batch_type ?? null,
        selected_bank_mapping_id: selectedBankMappingId,
        selected_bank_name: selectedBankName,
        selected_bank_short_name: selectedBankShortName,
        selected_bank_last4: selectedBankLast4,
        detected_bank_name: isInvoice ? null : detectedBank.bankName,
        detected_last4: isInvoice ? null : detectedBank.last4,
        bank_selection_conflict: bankSelectionConflict,
        conflict_message: conflictMessage,
        row_results: [
          {
            id: `batch_row_${String(index + 1).padStart(5, "0")}`,
            row_no: 1,
            source_record_type: templateCode === "invoice_export" ? "invoice" : "bank_transaction",
            decision: "created",
            decision_reason: "Ready to create new record.",
          },
        ],
      };
    }),
    duplicate_groups: [
      {
        identity_key: "mock:duplicate:001",
        record_type: "invoice",
        duplicate_type: "duplicate_in_file",
        rows: [
          {
            file_id: "import_file_0001",
            file_name: fileNames[0] ?? "一月发票.xlsx",
            row_no: 2,
          },
        ],
      },
    ],
  };
}

function buildWorkbenchPayload(month: string) {
  return toGroupedWorkbenchPayload(buildWorkbenchRowPayload(month));
}

type RawWorkbenchPayload = ReturnType<typeof buildWorkbenchRowPayload>;

function emptyWorkbenchPayload(month: string): RawWorkbenchPayload {
  return {
    month,
    summary: {
      oa_count: 0,
      bank_count: 0,
      invoice_count: 0,
      paired_count: 0,
      unpaired_count: 0,
      exception_count: 0,
    },
    paired: { oa: [], bank: [], invoice: [] },
    unpaired: { oa: [], bank: [], invoice: [] },
  };
}

function mockWorkbenchPayloadForMonth(
  store: ReturnType<typeof createWorkbenchStateStore>,
  month: string,
  options: MockApiOptions,
) {
  return options.workbenchEmptyPayload
    ? emptyWorkbenchPayload(month)
    : cloneJson(store.get(month));
}
type RawWorkbenchSectionKey = "paired" | "unpaired";
type RawWorkbenchPaneKey = "oa" | "bank" | "invoice";
type RawWorkbenchRow = RawWorkbenchPayload["paired"][RawWorkbenchPaneKey][number];

function buildWorkbenchRowPayload(
  month: string,
  options: Pick<MockApiOptions, "includeOaAttachmentPaymentReceipt"> = {},
) {
  if (month === "2026-04") {
    return {
      month,
      summary: {
        oa_count: 2,
        bank_count: 2,
        invoice_count: 2,
        paired_count: 3,
        unpaired_count: 3,
        exception_count: 1,
      },
      paired: {
        oa: [
          {
            id: "oa-p-202604-001",
            type: "oa",
            case_id: "CASE-202604-001",
            applicant: "刘宁",
            project_name: "智能工厂二期",
            apply_type: "差旅报销",
            amount: "860.00",
            counterparty_name: "差旅服务商",
            reason: "现场实施差旅费",
            oa_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
            available_actions: ["detail", "cancel_link"],
          },
        ],
        bank: [
          {
            id: "bk-p-202604-001",
            type: "bank",
            case_id: "CASE-202604-001",
            trade_time: "2026-04-05 10:05",
            debit_amount: "860.00",
            credit_amount: null,
            counterparty_name: "差旅服务商",
            payment_account_label: "建设银行 1138",
            invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
            pay_receive_time: "2026-04-05 10:05",
            remark: "差旅报销已闭环",
            repayment_date: null,
            available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
          },
        ],
        invoice: [
          {
            id: "iv-p-202604-001",
            type: "invoice",
            case_id: "CASE-202604-001",
            seller_tax_no: "91310108MA1N22179P",
            seller_name: "差旅服务商",
            buyer_tax_no: "91310000MA1K8A001X",
            buyer_name: "杭州溯源科技有限公司",
            issue_date: "2026-04-05",
            amount: "860.00",
            tax_rate: "6%",
            tax_amount: "51.60",
            total_with_tax: "911.60",
            invoice_type: "进项普票",
            invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
            available_actions: ["detail", "cancel_link"],
            detail_fields: {
              发票号码: "INV-202604-001",
            },
          },
        ],
      },
      unpaired: {
        oa: [
          {
            id: "oa-o-202604-001",
            type: "oa",
            case_id: "CASE-202604-101",
            applicant: "王青",
            project_name: "维保续费项目",
            apply_type: "市场费用",
            amount: "6,000.00",
            counterparty_name: "杭州张三广告有限公司",
            reason: "4月品牌投放尾款",
            oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
            available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          },
        ],
        bank: [
          {
            id: "bk-o-202604-001",
            type: "bank",
            case_id: "CASE-202604-101",
            trade_time: "2026-04-20 09:15",
            debit_amount: "6,000.00",
            credit_amount: null,
            counterparty_name: "杭州张三广告有限公司",
            payment_account_label: "中国银行 8821",
            invoice_relation: { code: "pending_invoice_match", label: "待关联广告票", tone: "warn" },
            pay_receive_time: "2026-04-20 09:15",
            remark: "应付6000，候选 OA-202604-101",
            repayment_date: null,
            available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
          },
          {
            id: "bk-ex-202604-001",
            type: "bank",
            case_id: null,
            handled_exception: true,
            direction: "支出",
            trade_time: "2026-04-09 15:30",
            debit_amount: "1,250.00",
            credit_amount: null,
            counterparty_name: "异常供应商",
            payment_account_label: "建设银行 8826",
            invoice_relation: { code: "oa_bank_amount_mismatch", label: "金额不一致，继续异常", tone: "danger" },
            pay_receive_time: "2026-04-09 15:30",
            remark: "异常付款，待人工复核",
            repayment_date: null,
            available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
            detail_fields: {
              企业流水号: "SERIAL-EX-001",
            },
          },
        ],
        invoice: [
          {
            id: "iv-o-202604-001",
            type: "invoice",
            case_id: "CASE-202604-101",
            seller_tax_no: "91330102MA8T32A2X7",
            seller_name: "杭州张三广告有限公司",
            buyer_tax_no: "91330106589876543T",
            buyer_name: "杭州溯源科技有限公司",
            issue_date: "2026-04-20",
            amount: "6,000.00",
            tax_rate: "6%",
            tax_amount: "339.62",
            total_with_tax: "6,000.00",
            invoice_type: "进项专票",
            invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
            available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
            detail_fields: {
              发票号码: "INV-202604-101",
            },
          },
        ],
      },
    };
  }

  if (month === "2026-05") {
    return {
      month,
      summary: {
        oa_count: 0,
        bank_count: 0,
        invoice_count: 0,
        paired_count: 0,
        unpaired_count: 0,
        exception_count: 0,
      },
      paired: { oa: [], bank: [], invoice: [] },
      unpaired: { oa: [], bank: [], invoice: [] },
    };
  }

  return {
    month,
    summary: {
      oa_count: 5,
      bank_count: 4,
      invoice_count: 4,
      paired_count: 3,
      unpaired_count: 10,
      exception_count: 1,
    },
    paired: {
      oa: [
        {
          id: "oa-p-202603-001",
          type: "oa",
          case_id: "CASE-202603-001",
          applicant: "赵华",
          project_name: "华东改造项目",
          apply_type: "供应商付款申请",
          amount: "128,000.00",
          counterparty_name: "华东设备供应商",
          reason: "设备首付款支付",
          oa_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
          detail_fields: {
            审批完成时间: "2026-03-25 11:05",
          },
          available_actions: ["detail", "cancel_link"],
        },
      ],
      bank: [
        {
          id: "bk-p-202603-001",
          type: "bank",
          case_id: "CASE-202603-001",
          trade_time: "2026-03-25 14:22",
          debit_amount: "128,000.00",
          credit_amount: null,
          counterparty_name: "华东设备供应商",
          payment_account_label: "招商银行 9123",
          invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
          pay_receive_time: "2026-03-25 14:22",
          remark: "设备采购款，已闭环",
          repayment_date: null,
          available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
        },
      ],
      invoice: [
        {
          id: "iv-p-202603-001",
          type: "invoice",
          case_id: "CASE-202603-001",
          seller_tax_no: "91310000MA1K8A001X",
          seller_name: "杭州溯源科技有限公司",
          buyer_tax_no: "91310110MA1F99088Q",
          buyer_name: "华东设备供应商",
          issue_date: "2026-03-25",
          amount: "128,000.00",
          tax_rate: "13%",
          tax_amount: "16,640.00",
          total_with_tax: "144,640.00",
          invoice_type: "进项专票",
          invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
          available_actions: ["detail", "cancel_link"],
          detail_fields: {
            发票代码: "032002600111",
            发票号码: "00061345",
          },
        },
      ],
    },
    unpaired: {
      oa: [
        {
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
        {
          id: "oa-o-202603-002",
          type: "oa",
          case_id: null,
          applicant: "孙敏",
          project_name: "华东补录项目",
          apply_type: "服务费申请",
          amount: "9,800.00",
          counterparty_name: "华东设备供应商",
          reason: "月度巡检服务待付款",
          oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
          detail_fields: {
            审批完成时间: "2026-03-26 09:20",
            附件发票数量: "0",
            附件发票识别情况: "已解析 0 / 6",
          },
          available_actions: ["detail", "confirm_link", "withdraw_link", "mark_exception", "ignore"],
        },
        {
          id: "oa-o-202603-003",
          type: "oa",
          case_id: "CASE-202603-102",
          applicant: "林晨",
          project_name: "金额差异项目",
          apply_type: "供应商付款申请",
          amount: "10,000.00",
          counterparty_name: "尾差设备商",
          reason: "设备尾款待复核",
          oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
          detail_fields: {
            审批完成时间: "2026-03-29 18:10",
          },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
        },
        {
          id: "oa-exp-2035",
          type: "oa",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          applicant: "胡瑢",
          project_name: "曲靖维护项目；云南溯源科技",
          project_name_display: "多个项目",
          project_names: ["曲靖维护项目", "云南溯源科技"],
          expense_items: [
            {
              id: "oa-exp-2035:item:0",
              row_index: "0",
              project_name: "曲靖维护项目",
              amount: "48.00",
            },
            {
              id: "oa-exp-2035:item:1",
              row_index: "1",
              project_name: "云南溯源科技",
              amount: "200.00",
            },
          ],
          apply_type: "日常报销",
          amount: "248.00",
          counterparty_name: "胡瑢",
          reason: "OA 2035 附件凭证来源归属待核销",
          oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
          detail_fields: {
            审批完成时间: "2026-03-04 10:18",
            明细摘要: "付款项 0 48.00，昆明玉溪来回过路费；付款项 1 200.00，加油费",
          },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
        },
        {
          id: "oa-exp-292",
          type: "oa",
          case_id: "CASE-202603-OA-ATTACHMENT-292",
          applicant: "胡瑢",
          project_name: "红云红河烟草能源管理运维项目",
          apply_type: "日常报销",
          amount: "292.00",
          counterparty_name: "胡瑢",
          reason: "单张 OA 附件票来源归属待核销",
          oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
          detail_fields: {
            审批完成时间: "2026-03-24 11:30",
            明细摘要: "付款项 1 292.00",
          },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
        },
      ],
      bank: [
        {
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
        {
          id: "bk-o-202603-002",
          type: "bank",
          case_id: null,
          trade_time: "2026-03-27 09:40",
          debit_amount: "1,879.45",
          credit_amount: null,
          counterparty_name: "ETC过路费",
          payment_account_label: "工商银行 6621",
          invoice_relation: { code: "manual_review", label: "待人工核查", tone: "danger" },
          pay_receive_time: "2026-03-27 09:40",
          remark: "导入自动打标，待人工核查",
          repayment_date: null,
          available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
        },
        {
          id: "bk-o-202603-003",
          type: "bank",
          case_id: "CASE-202603-102",
          trade_time: "2026-03-29 10:18",
          debit_amount: "10,000.00",
          credit_amount: null,
          counterparty_name: "尾差设备商",
          payment_account_label: "建设银行 1138",
          invoice_relation: { code: "pending_invoice_match", label: "待关联设备票", tone: "warn" },
          pay_receive_time: "2026-03-29 10:18",
          remark: "设备尾款存在发票尾差",
          repayment_date: null,
          available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
        },
      ],
      invoice: [
        {
          id: "iv-o-202603-001",
          type: "invoice",
          source_kind: "oa_attachment_invoice",
          case_id: "CASE-202603-101",
          seller_tax_no: "91330108MA27B4011D",
          seller_name: "智能工厂设备商",
          buyer_tax_no: "91310000MA1K8A001X",
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
            source_expense_row_index: "1",
            source_expense_item_id: "oa-o-202603-001:item:1",
            source_attachment_name: "设备尾款附件发票.pdf",
            source_attachment_key: "oa-o-202603-001/item-1/invoice.pdf",
          },
        },
        {
          id: "iv-o-202603-003",
          type: "invoice",
          case_id: "CASE-202603-102",
          seller_tax_no: "91330108MA27B4011E",
          seller_name: "尾差设备商",
          buyer_tax_no: "91310000MA1K8A001X",
          buyer_name: "杭州溯源科技有限公司",
          issue_date: "2026-03-29",
          amount: "9,999.99",
          tax_rate: "13%",
          tax_amount: "1,150.44",
          total_with_tax: "9,999.99",
          invoice_type: "进项专票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "12561049",
          },
        },
        {
          id: "iv-oa-2035-machine-25",
          type: "invoice",
          source_kind: "oa_attachment_invoice",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          seller_tax_no: "91530100OA2035A",
          seller_name: "昆玉高速公路收费站",
          buyer_tax_no: "915300007194052520",
          buyer_name: "杭州溯源科技有限公司",
          issue_date: "2026-03-04",
          amount: "25.00",
          tax_rate: "0%",
          tax_amount: "0.00",
          total_with_tax: "25.00",
          invoice_type: "进项普票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "OA2035-MACHINE-25",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "0",
            source_expense_item_id: "oa-exp-2035:item:0",
            source_attachment_name: "过路费机打发票合图.jpg",
            source_attachment_key: "oa-exp-2035/item-0/toll-invoices.jpg",
          },
        },
        {
          id: "iv-oa-2035-machine-23",
          type: "invoice",
          source_kind: "oa_attachment_invoice",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          seller_tax_no: "91530100OA2035B",
          seller_name: "玉昆高速公路收费站",
          buyer_tax_no: "915300007194052520",
          buyer_name: "杭州溯源科技有限公司",
          issue_date: "2026-03-04",
          amount: "23.00",
          tax_rate: "0%",
          tax_amount: "0.00",
          total_with_tax: "23.00",
          invoice_type: "进项普票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "OA2035-MACHINE-23",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "0",
            source_expense_item_id: "oa-exp-2035:item:0",
            source_attachment_name: "过路费机打发票合图.jpg",
            source_attachment_key: "oa-exp-2035/item-0/toll-invoices.jpg",
          },
        },
        {
          id: "iv-oa-2035-fuel-200",
          type: "invoice",
          source_kind: "oa_attachment_invoice",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          seller_tax_no: "91530100OA2035C",
          seller_name: "中国石油云南销售公司",
          buyer_tax_no: "915300007194052520",
          buyer_name: "杭州溯源科技有限公司",
          issue_date: "2026-03-04",
          amount: "200.00",
          tax_rate: "0%",
          tax_amount: "0.00",
          total_with_tax: "200.00",
          invoice_type: "进项普票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "OA2035-FUEL-200",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "1",
            source_expense_item_id: "oa-exp-2035:item:1",
            source_attachment_name: "加油电子发票.pdf",
            source_attachment_key: "oa-exp-2035/item-1/fuel-invoice.pdf",
          },
        },
        ...(options.includeOaAttachmentPaymentReceipt
          ? [{
            id: "pay-oa-2035-fuel-200",
            type: "invoice",
            source_kind: "oa_attachment_payment_receipt",
            case_id: "CASE-202603-OA-ATTACHMENT-2035",
            seller_tax_no: "",
            seller_name: "微信支付",
            buyer_tax_no: "",
            buyer_name: "胡瑢",
            issue_date: "2026-03-04",
            amount: "200.00",
            tax_rate: "0%",
            tax_amount: "0.00",
            total_with_tax: "200.00",
            invoice_type: "付款凭证",
            invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
            available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
            detail_fields: {
              发票号码: "PAY-OA2035-WXPAY-200",
              derived_from_oa_id: "oa-exp-2035",
              source_expense_row_index: "1",
              source_expense_item_id: "oa-exp-2035:item:1",
              source_attachment_name: "加油微信支付凭证.png",
              source_attachment_key: "oa-exp-2035/item-1/fuel-payment.png",
            },
          }]
          : []),
        {
          id: "iv-oa-attachment-292-001",
          type: "invoice",
          source_kind: "oa_attachment_invoice",
          case_id: "CASE-202603-OA-ATTACHMENT-292",
          seller_tax_no: "91530100OAATT292A",
          seller_name: "云南能源服务有限公司",
          buyer_tax_no: "915300007194052520",
          buyer_name: "杭州溯源科技有限公司",
          issue_date: "2026-03-24",
          amount: "292.00",
          tax_rate: "0%",
          tax_amount: "0.00",
          total_with_tax: "292.00",
          invoice_type: "进项普票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "OAATT-292-001",
            derived_from_oa_id: "oa-exp-292",
            source_expense_row_index: "1",
            source_expense_item_id: "oa-exp-292:item:1",
            source_attachment_name: "付款项1-能源服务.pdf",
            source_attachment_key: "oa-exp-292/item-1/energy.pdf",
          },
        },
      ],
    },
  };
}

function toGroupedWorkbenchPayload(payload: {
  month: string;
  summary: {
    oa_count: number;
    bank_count: number;
    invoice_count: number;
    paired_count: number;
    unpaired_count: number;
    exception_count: number;
  };
  paired: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>;
  unpaired: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>;
}) {
  const pairedGroups = buildGroups(payload.paired, "paired");
  const unpairedGroups = buildGroups(payload.unpaired, "unpaired");
  const pairedRowCounts = countMockWorkbenchRows(pairedGroups);
  const unpairedRowCounts = countMockWorkbenchRows(unpairedGroups);

  return {
    month: payload.month,
    scope_key: payload.month,
    summary: {
      oa_count: payload.summary.oa_count,
      bank_count: payload.summary.bank_count,
      invoice_count: payload.summary.invoice_count,
      paired_count: pairedGroups.length,
      unpaired_count: unpairedGroups.length,
      exception_count: [...pairedGroups, ...unpairedGroups].filter(
        (group) => (group as { oa_invoice_anomaly?: { state?: string } }).oa_invoice_anomaly?.state === "active",
      ).length,
      ignored_exception_count: [...pairedGroups, ...unpairedGroups].filter(
        (group) => (group as { oa_invoice_anomaly?: { state?: string } }).oa_invoice_anomaly?.state === "ignored",
      ).length,
    },
    invoice_inventory: {
      system_total: 9,
      manual_import_total: 7,
      workbench_visible_total: 4,
      hidden_submitted_etc_total: 2,
      extra_etc_total: 1,
      etc_summary_batch_count: 3,
      oa_attachment_total: 5,
    },
    statistics: {
      oa_count: payload.summary.oa_count,
      bank_transaction_count: payload.summary.bank_count,
      input_invoice_count: payload.summary.invoice_count,
      output_invoice_count: 0,
      paired_group_count: pairedGroups.length,
      unpaired_object_count: unpairedGroups.length,
      expense_transaction_count: 0,
      income_transaction_count: 0,
      paired_oa_count: pairedRowCounts.oa,
      paired_bank_transaction_count: pairedRowCounts.bank,
      paired_invoice_count: pairedRowCounts.invoice,
      incomplete_group_count: 0,
      missing_oa_group_count: 0,
      missing_bank_group_count: 0,
      missing_invoice_group_count: 0,
    },
    paired: { groups: pairedGroups },
    unpaired: { groups: unpairedGroups },
  };
}

function buildGroups(
  rows: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>,
  section: "paired" | "unpaired",
) {
  const groups = new Map<
    string,
    {
      group_id: string;
      detail_key: string;
      group_type: "relation" | "unpaired";
      match_confidence: "high" | "medium" | "low";
      reason: string;
      oa_rows: Array<Record<string, unknown>>;
      bank_rows: Array<Record<string, unknown>>;
      invoice_rows: Array<Record<string, unknown>>;
      can_withdraw?: boolean;
    }
  >();

  for (const row of [...rows.oa, ...rows.bank, ...rows.invoice]) {
    const caseId = typeof row.case_id === "string" && row.case_id ? row.case_id : null;
    const groupId = section === "paired" && caseId ? `case:${caseId}` : `row:${String(row.id)}`;
    if (!groups.has(groupId)) {
      groups.set(groupId, {
        group_id: groupId,
        detail_key: section === "paired" && caseId ? caseId : String(row.id),
        group_type: section === "paired" ? "relation" : "unpaired",
        match_confidence: section === "paired" ? "high" : "low",
        reason: section === "paired" ? "active_formal_relation" : "unpaired_fact",
        oa_rows: [],
        bank_rows: [],
        invoice_rows: [],
      });
    }
    const group = groups.get(groupId)!;
    if (row.type === "oa") {
      group.oa_rows.push(row);
    } else if (row.type === "bank") {
      group.bank_rows.push(row);
    } else {
      group.invoice_rows.push(row);
    }
  }

  return Array.from(groups.values()).map((group) => ({
    ...group,
    can_withdraw: section === "paired" ? true : undefined,
  }));
}

type MockWorkbenchGroup = ReturnType<typeof buildGroups>[number];
type MockWorkbenchJsonParam = Record<string, unknown>;

const MOCK_WORKBENCH_PANES: RawWorkbenchPaneKey[] = ["oa", "bank", "invoice"];

function parseWorkbenchGroupJsonParam(value: string | null): MockWorkbenchJsonParam {
  if (!value) {
    return {};
  }
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as MockWorkbenchJsonParam
      : {};
  } catch {
    return {};
  }
}

function parseMockWorkbenchCursor(value: string | null, prefix: string) {
  if (!value?.startsWith(prefix)) {
    return 0;
  }
  const offset = Number(value.slice(prefix.length));
  return Number.isSafeInteger(offset) && offset >= 0 ? offset : 0;
}

function nextMockWorkbenchCursor(prefix: string, offset: number, pageSize: number, total: number) {
  const nextOffset = offset + pageSize;
  return nextOffset < total ? `${prefix}${nextOffset}` : null;
}

function countMockWorkbenchRows(groups: MockWorkbenchGroup[]) {
  const counts = { oa: 0, bank: 0, invoice: 0, rows: 0 };
  groups.forEach((group) => {
    counts.oa += group.oa_rows.length;
    counts.bank += group.bank_rows.length;
    counts.invoice += group.invoice_rows.length;
  });
  counts.rows = counts.oa + counts.bank + counts.invoice;
  return counts;
}

function mockWorkbenchGroupMatchesQuery(
  group: MockWorkbenchGroup,
  search: string,
  columnFilters: MockWorkbenchJsonParam,
  timeFilters: MockWorkbenchJsonParam,
) {
  const normalizedSearch = normalizeMockWorkbenchText(search);
  if (
    normalizedSearch
    && !normalizeMockWorkbenchText(mockWorkbenchSearchText(group)).includes(normalizedSearch)
  ) {
    return false;
  }

  return mockWorkbenchGroupMatchesStructuredFilters(group, columnFilters, timeFilters);
}

function mockWorkbenchGroupMatchesStructuredFilters(
  group: MockWorkbenchGroup,
  columnFilters: MockWorkbenchJsonParam,
  timeFilters: MockWorkbenchJsonParam,
) {
  const activePanes = MOCK_WORKBENCH_PANES.filter((pane) => {
    const paneColumns = columnFilters[pane];
    const paneTime = timeFilters[pane];
    return (
      (paneColumns && typeof paneColumns === "object" && !Array.isArray(paneColumns) && Object.keys(paneColumns).length > 0)
      || (paneTime && typeof paneTime === "object" && !Array.isArray(paneTime))
    );
  });

  if (activePanes.length === 0) {
    return true;
  }

  return activePanes.every((pane) =>
    groupRowsForMockPane(group, pane).some((row) =>
      mockWorkbenchRowMatchesPaneFilters(row, pane, columnFilters[pane], timeFilters[pane]),
    ),
  );
}

function mockWorkbenchRowMatchesPaneFilters(
  row: Record<string, unknown>,
  pane: RawWorkbenchPaneKey,
  rawColumnFilters: unknown,
  rawTimeFilter: unknown,
) {
  if (rawColumnFilters && typeof rawColumnFilters === "object" && !Array.isArray(rawColumnFilters)) {
    for (const [columnKey, rawValues] of Object.entries(rawColumnFilters)) {
      const selectedValues = normalizeMockWorkbenchSelectedValues(rawValues);
      if (selectedValues.length === 0) {
        continue;
      }
      const rowValues = mockWorkbenchColumnValues(row, pane, columnKey);
      const matchesSelectedValues = pane === "bank" && columnKey === "amount"
        ? selectedValues.every((value) => rowValues.includes(value))
        : selectedValues.some((value) => rowValues.includes(value));
      if (!matchesSelectedValues) {
        return false;
      }
    }
  }

  if (rawTimeFilter && typeof rawTimeFilter === "object" && !Array.isArray(rawTimeFilter)) {
    const timeFilter = rawTimeFilter as Record<string, unknown>;
    const timeValue = String(mockWorkbenchTimeValue(row, pane) ?? "").trim();
    if (!mockWorkbenchTimeMatches(timeValue, timeFilter)) {
      return false;
    }
  }

  return true;
}

function normalizeMockWorkbenchSelectedValues(value: unknown) {
  const values = Array.isArray(value) ? value : [value];
  return values
    .map((item) => String(item ?? "").trim())
    .filter((item) => item && item !== "--" && item !== "—");
}

function mockWorkbenchColumnValues(row: Record<string, unknown>, pane: RawWorkbenchPaneKey, columnKey: string) {
  if (pane === "bank" && columnKey === "amount") {
    return [mockWorkbenchBankDirection(row), stringValue(row.payment_account_label)].filter(Boolean);
  }

  const valueByColumn: Record<string, string> = pane === "oa"
    ? {
      applicant: stringValue(row.applicant),
      projectName: stringValue(row.project_name_display) || stringValue(row.project_name),
      applicationType: stringValue(row.apply_type),
      counterparty: stringValue(row.counterparty_name),
      reconciliationStatus: mockWorkbenchRelationLabel(row, "oa"),
    }
    : pane === "bank"
      ? {
        counterparty: stringValue(row.counterparty_name),
        direction: mockWorkbenchBankDirection(row),
        paymentAccount: stringValue(row.payment_account_label),
        invoiceRelationStatus: mockWorkbenchRelationLabel(row, "bank"),
        loanRepaymentDate: stringValue(row.repayment_date),
      }
      : {
        sellerName: stringValue(row.seller_name),
        buyerName: stringValue(row.buyer_name),
        invoiceType: stringValue(row.invoice_type),
      };

  const value = valueByColumn[columnKey];
  return value ? [value] : [];
}

function mockWorkbenchRelationLabel(row: Record<string, unknown>, pane: RawWorkbenchPaneKey) {
  const relation = pane === "oa"
    ? row.oa_bank_relation
    : pane === "bank"
      ? row.invoice_relation
      : row.invoice_bank_relation;
  return relation && typeof relation === "object" ? stringValue((relation as Record<string, unknown>).label) : "待处理";
}

function mockWorkbenchBankDirection(row: Record<string, unknown>) {
  const explicit = stringValue(row.direction);
  if (explicit === "支出" || explicit === "收入") {
    return explicit;
  }
  if (stringValue(row.debit_amount)) {
    return "支出";
  }
  if (stringValue(row.credit_amount)) {
    return "收入";
  }
  return "未识别";
}

function mockWorkbenchTimeMatches(timeValue: string, timeFilter: Record<string, unknown>) {
  if (!timeValue) {
    return false;
  }
  const mode = String(timeFilter.mode ?? "").trim();
  if (mode === "year") {
    const year = String(timeFilter.year ?? "").trim();
    return /^\d{4}$/.test(year) && timeValue.startsWith(year);
  }
  if (mode === "month") {
    const month = String(timeFilter.month ?? "").trim();
    return /^\d{4}-\d{2}$/.test(month) && timeValue.startsWith(month);
  }
  return true;
}

function mockWorkbenchTimeValue(row: Record<string, unknown>, pane: RawWorkbenchPaneKey) {
  if (pane === "oa") {
    const detailFields = objectValue(row.detail_fields);
    const summaryFields = objectValue(row.summary_fields);
    return (
      detailFields["审批完成时间"]
      ?? detailFields["申请日期"]
      ?? detailFields["创建时间"]
      ?? summaryFields["审批完成时间"]
      ?? summaryFields["申请日期"]
      ?? summaryFields["创建时间"]
    );
  }
  if (pane === "bank") {
    return row.trade_time;
  }
  return row.issue_date;
}

function sortMockWorkbenchGroups(groups: MockWorkbenchGroup[], sort: string) {
  const [pane, direction] = sort.split(":") as [RawWorkbenchPaneKey | undefined, string | undefined];
  if (!pane || !MOCK_WORKBENCH_PANES.includes(pane) || (direction !== "asc" && direction !== "desc")) {
    return groups;
  }

  return [...groups].sort((left, right) => {
    const leftKey = mockWorkbenchGroupSortKey(left, pane, direction);
    const rightKey = mockWorkbenchGroupSortKey(right, pane, direction);
    if (!leftKey && !rightKey) {
      return 0;
    }
    if (!leftKey) {
      return 1;
    }
    if (!rightKey) {
      return -1;
    }
    const comparison = leftKey.localeCompare(rightKey, "zh-CN");
    return direction === "asc" ? comparison : -comparison;
  });
}

function mockWorkbenchGroupSortKey(group: MockWorkbenchGroup, pane: RawWorkbenchPaneKey, direction: "asc" | "desc") {
  const values = groupRowsForMockPane(group, pane)
    .map((row) => String(mockWorkbenchTimeValue(row, pane) ?? "").trim())
    .filter(Boolean)
    .sort((left, right) => left.localeCompare(right, "zh-CN"));
  if (values.length === 0) {
    return null;
  }
  return direction === "asc" ? values[0] : values[values.length - 1];
}

function groupRowsForMockPane(group: MockWorkbenchGroup, pane: RawWorkbenchPaneKey) {
  if (pane === "oa") {
    return group.oa_rows;
  }
  if (pane === "bank") {
    return group.bank_rows;
  }
  return group.invoice_rows;
}

function mockWorkbenchSearchText(group: MockWorkbenchGroup) {
  return MOCK_WORKBENCH_PANES.flatMap((pane) => groupRowsForMockPane(group, pane).map(mockWorkbenchRowSearchText)).join(" ");
}

function mockWorkbenchRowSearchText(row: Record<string, unknown>) {
  return flattenMockWorkbenchText(row).join(" ");
}

function flattenMockWorkbenchText(value: unknown): string[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap(flattenMockWorkbenchText);
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !["id", "row_id", "group_id", "detail_fields"].includes(key))
      .flatMap(([, item]) => flattenMockWorkbenchText(item));
  }
  return [String(value)];
}

function normalizeMockWorkbenchText(value: unknown) {
  return String(value ?? "").trim().toLocaleLowerCase("zh-CN");
}

function stringValue(value: unknown) {
  return String(value ?? "").trim();
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

const WORKBENCH_STATE_MONTHS = ["2026-03", "2026-04"] as const;

function createWorkbenchStateStore(options: Pick<MockApiOptions, "includeOaAttachmentPaymentReceipt"> = {}) {
  const store = new Map<string, RawWorkbenchPayload>();
  const ensureMonth = (month: string) => {
    if (!store.has(month)) {
      store.set(month, cloneJson(buildWorkbenchRowPayload(month, options)));
    }
    return store.get(month)!;
  };
  const buildAllPayload = (): RawWorkbenchPayload => {
    const merged: RawWorkbenchPayload = {
      month: "all",
      summary: {
        oa_count: 0,
        bank_count: 0,
        invoice_count: 0,
        paired_count: 0,
        unpaired_count: 0,
        exception_count: 0,
      },
      paired: { oa: [], bank: [], invoice: [] },
      unpaired: { oa: [], bank: [], invoice: [] },
    };

    for (const month of WORKBENCH_STATE_MONTHS) {
      const payload = ensureMonth(month);
      merged.summary.oa_count += payload.summary.oa_count;
      merged.summary.bank_count += payload.summary.bank_count;
      merged.summary.invoice_count += payload.summary.invoice_count;
      merged.summary.paired_count += payload.summary.paired_count;
      merged.summary.unpaired_count += payload.summary.unpaired_count;
      merged.summary.exception_count += payload.summary.exception_count;
      merged.paired.oa.push(...cloneJson(payload.paired.oa));
      merged.paired.bank.push(...cloneJson(payload.paired.bank));
      merged.paired.invoice.push(...cloneJson(payload.paired.invoice));
      merged.unpaired.oa.push(...cloneJson(payload.unpaired.oa));
      merged.unpaired.bank.push(...cloneJson(payload.unpaired.bank));
      merged.unpaired.invoice.push(...cloneJson(payload.unpaired.invoice));
    }

    return merged;
  };
  return {
    get(month: string) {
      if (month === "all") {
        return buildAllPayload();
      }
      return ensureMonth(month);
    },
    resolveMonthForRow(rowId: string) {
      for (const month of WORKBENCH_STATE_MONTHS) {
        const payload = ensureMonth(month);
        for (const section of ["paired", "unpaired"] as const) {
          for (const pane of ["oa", "bank", "invoice"] as const) {
            if (payload[section][pane].some((row) => String(row.id) === rowId)) {
              return month;
            }
          }
        }
      }
      return undefined;
    },
  };
}

function createIgnoredRowStore() {
  const store = new Map<string, RawWorkbenchRow[]>([
    [
      "2026-04",
      [
        {
          id: "iv-ignored-202604-001",
          type: "invoice",
          case_id: null,
          seller_tax_no: "91310000999999999X",
          seller_name: "忽略发票公司",
          buyer_tax_no: "915300007194052520",
          buyer_name: "云南溯源科技有限公司",
          issue_date: "2026-04-03",
          amount: "1,250.00",
          tax_rate: "6%",
          tax_amount: "70.75",
          total_with_tax: "1,320.75",
          invoice_type: "进项专票",
          invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            发票号码: "INV-IGN-001",
          },
          ignored: true,
        } as unknown as RawWorkbenchRow,
      ],
    ],
  ]);
  return {
    get(month: string) {
      if (month === "all") {
        return WORKBENCH_STATE_MONTHS.flatMap((candidateMonth) => cloneJson(store.get(candidateMonth) ?? []));
      }
      if (!store.has(month)) {
        store.set(month, []);
      }
      return store.get(month)!;
    },
    resolveMonthForRow(rowId: string) {
      for (const month of WORKBENCH_STATE_MONTHS) {
        const rows = store.get(month) ?? [];
        if (rows.some((row) => String(row.id) === rowId)) {
          return month;
        }
      }
      return undefined;
    },
  };
}

function findWorkbenchGroupRows(payload: RawWorkbenchPayload, section: RawWorkbenchSectionKey, rowId: string) {
  const panes: RawWorkbenchPaneKey[] = ["oa", "bank", "invoice"];
  let matchedRow: RawWorkbenchRow | null = null;

  for (const pane of panes) {
    const row = payload[section][pane].find((candidate) => String(candidate.id) === rowId) ?? null;
    if (row) {
      matchedRow = row;
      break;
    }
  }

  if (!matchedRow) {
    return null;
  }

  const caseId = typeof matchedRow.case_id === "string" && matchedRow.case_id ? matchedRow.case_id : null;
  const matchesRow = (candidate: RawWorkbenchRow) =>
    String(candidate.id) === rowId || (caseId !== null && candidate.case_id === caseId);

  return {
    caseId,
    rows: {
      oa: payload[section].oa.filter(matchesRow),
      bank: payload[section].bank.filter(matchesRow),
      invoice: payload[section].invoice.filter(matchesRow),
    },
  };
}

function reopenWorkbenchRow(row: RawWorkbenchRow): RawWorkbenchRow {
  if (row.type === "oa") {
    return {
      ...row,
      oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
      available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
    };
  }

  if (row.type === "bank") {
    return {
      ...row,
      invoice_relation: { code: "pending_invoice_match", label: "待人工确认", tone: "warn" },
      available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
    };
  }

  return {
    ...row,
    invoice_bank_relation: { code: "pending_collection", label: "待匹配付款", tone: "warn" },
    available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
  };
}

function moveInvoiceToIgnored(payload: RawWorkbenchPayload, ignoredRows: RawWorkbenchRow[], rowId: string) {
  const invoiceIndex = payload.unpaired.invoice.findIndex((candidate) => String(candidate.id) === rowId);
  if (invoiceIndex < 0) {
    return false;
  }
  const [row] = payload.unpaired.invoice.splice(invoiceIndex, 1);
  ignoredRows.push({
    ...row,
    available_actions: ["detail"],
  });
  return true;
}

function restoreIgnoredInvoice(payload: RawWorkbenchPayload, ignoredRows: RawWorkbenchRow[], rowId: string) {
  const invoiceIndex = ignoredRows.findIndex((candidate) => String(candidate.id) === rowId);
  if (invoiceIndex < 0) {
    return false;
  }
  const [row] = ignoredRows.splice(invoiceIndex, 1);
  payload.unpaired.invoice.push(reopenWorkbenchRow(row));
  return true;
}

function moveWorkbenchGroup(payload: RawWorkbenchPayload, source: RawWorkbenchSectionKey, target: RawWorkbenchSectionKey, rowId: string) {
  const matchedGroup = findWorkbenchGroupRows(payload, source, rowId);
  if (!matchedGroup) {
    return false;
  }

  const panes: RawWorkbenchPaneKey[] = ["oa", "bank", "invoice"];
  const shouldMove = (candidate: RawWorkbenchRow) =>
    matchedGroup.caseId !== null ? candidate.case_id === matchedGroup.caseId : panes.some((pane) =>
      matchedGroup.rows[pane].some((row) => String(row.id) === String(candidate.id)),
    );

  for (const pane of panes) {
    payload[source][pane] = payload[source][pane].filter((candidate) => !shouldMove(candidate));
    payload[target][pane] = [
      ...payload[target][pane],
      ...matchedGroup.rows[pane].map((row) => (target === "unpaired" ? reopenWorkbenchRow(row) : row)),
    ];
  }

  return true;
}

function withdrawWorkbenchGroup(payload: RawWorkbenchPayload, rowId: string) {
  const matchedGroup = findWorkbenchGroupRows(payload, "paired", rowId);
  if (!matchedGroup) {
    return false;
  }

  const panes: RawWorkbenchPaneKey[] = ["oa", "bank", "invoice"];
  const movedRowIds = new Set(
    panes.flatMap((pane) => matchedGroup.rows[pane].map((row) => String(row.id))),
  );
  const shouldMove = (candidate: RawWorkbenchRow) =>
    movedRowIds.has(String(candidate.id))
    || (matchedGroup.caseId !== null && candidate.case_id === matchedGroup.caseId);

  for (const pane of panes) {
    payload.paired[pane] = payload.paired[pane].filter((candidate) => !shouldMove(candidate));
  }

  payload.unpaired.oa = [
    ...payload.unpaired.oa,
    ...matchedGroup.rows.oa.map((row) => ({ ...reopenWorkbenchRow(row), case_id: "CASE-RESTORED" })),
  ];
  payload.unpaired.invoice = [
    ...payload.unpaired.invoice,
    ...matchedGroup.rows.invoice.map((row) => ({ ...reopenWorkbenchRow(row), case_id: "CASE-RESTORED" })),
  ];
  payload.unpaired.bank = [
    ...payload.unpaired.bank,
    ...matchedGroup.rows.bank.map((row) => ({ ...reopenWorkbenchRow(row), case_id: "" })),
  ];

  return true;
}

function findWorkbenchRowsByIds(
  workbenchStateStore: ReturnType<typeof createWorkbenchStateStore>,
  month: string,
  rowIds: string[],
) {
  const payload = workbenchStateStore.get(month);
  const rowsById = new Map<string, RawWorkbenchRow>();
  for (const section of ["paired", "unpaired"] as const) {
    for (const pane of ["oa", "bank", "invoice"] as const) {
      for (const row of payload[section][pane]) {
        rowsById.set(String(row.id), row);
      }
    }
  }
  return rowIds.map((rowId) => rowsById.get(rowId)).filter((row): row is RawWorkbenchRow => Boolean(row));
}

function buildRelationPreviewGroups(
  rows: RawWorkbenchRow[],
  caseId: string,
  section: "paired" | "unpaired",
  mode: "together" | "separate" | "restored-with-ungrouped" = "together",
) {
  if (mode === "separate") {
    const groupedRows = new Map<string, RawWorkbenchRow[]>();
    for (const row of rows) {
      const existingCaseId = typeof row.case_id === "string" ? row.case_id.trim() : "";
      const groupKey = existingCaseId ? `case:${existingCaseId}` : `selected:${String(row.id)}`;
      const groupRows = groupedRows.get(groupKey) ?? [];
      groupRows.push(row);
      groupedRows.set(groupKey, groupRows);
    }
    return Array.from(groupedRows.values()).flatMap((groupRows) => {
      const firstRow = groupRows[0];
      const existingCaseId = typeof firstRow?.case_id === "string" ? firstRow.case_id.trim() : "";
      return buildRelationPreviewGroups(groupRows, existingCaseId, section, "together");
    });
  }

  const panes: Record<RawWorkbenchPaneKey, RawWorkbenchRow[]> = { oa: [], bank: [], invoice: [] };
  const restoredRows = mode === "restored-with-ungrouped" ? rows.slice(0, 2) : rows;
  const ungroupedRows = mode === "restored-with-ungrouped" ? rows.slice(2) : [];
  for (const row of restoredRows) {
    const pane = row.type === "oa" || row.type === "bank" || row.type === "invoice" ? row.type : null;
    if (!pane) {
      continue;
    }
    panes[pane].push({
      ...row,
      case_id: caseId,
    });
  }
  return [
    ...buildGroups(panes, section),
    ...ungroupedRows.flatMap((row) => buildRelationPreviewGroups([{ ...row, case_id: "" }], "", "unpaired", "together")),
  ];
}

function buildWithdrawAfterPreviewGroups(rows: RawWorkbenchRow[]) {
  const hasOaRow = rows.some((row) => row.type === "oa");
  if (!hasOaRow) {
    return rows.flatMap((row) => buildRelationPreviewGroups([{ ...row, case_id: "" }], "", "unpaired", "together"));
  }
  const restoredRows = rows.filter((row) => row.type !== "bank");
  const restoredRowIds = new Set(restoredRows.map((row) => String(row.id)));
  const ungroupedRows = rows.filter((row) => !restoredRowIds.has(String(row.id)));
  return [
    ...(restoredRows.length >= 2 ? buildRelationPreviewGroups(restoredRows, "CASE-RESTORED", "unpaired", "together") : []),
    ...ungroupedRows.flatMap((row) => buildRelationPreviewGroups([{ ...row, case_id: "" }], "", "unpaired", "together")),
  ];
}

function buildMockRelationPreview({
  operation,
  month,
  rowIds,
  caseId,
  workbenchStateStore,
}: {
  operation: "confirm_link" | "withdraw_link";
  month: string;
  rowIds: string[];
  caseId: string;
  workbenchStateStore: ReturnType<typeof createWorkbenchStateStore>;
}) {
  const rows = findWorkbenchRowsByIds(workbenchStateStore, month, rowIds);
  const isMismatch = rowIds.includes("iv-o-202603-003") || caseId === "CASE-202603-102";
  const withdrawRestoredRows = rows.filter((row) => row.type !== "bank");
  const canRestoreWithdrawRows = rows.some((row) => row.type === "oa") && withdrawRestoredRows.length >= 2;
  const amountSummary = {
    before: {
      oa_total: isMismatch ? "10000.00" : "58000.00",
      bank_total: isMismatch ? "10000.00" : "58000.00",
      invoice_total: isMismatch ? "9999.99" : "58000.00",
    },
    after: {
      oa_total: isMismatch ? "10000.00" : "58000.00",
      bank_total: isMismatch ? "10000.00" : "58000.00",
      invoice_total: isMismatch ? "9999.99" : "58000.00",
    },
    status: isMismatch ? "mismatch" : "matched",
    direction: "payment",
    mismatch_fields: isMismatch ? ["invoice_total"] : [],
  };
  const asSelectionGroups = (groups: ReturnType<typeof buildRelationPreviewGroups>) => groups.map((group) => ({
    ...group,
    group_type: "selection",
    match_confidence: "none",
    zone: "unpaired",
    status: "unpaired",
  }));
  const asRelationGroups = (
    groups: ReturnType<typeof buildRelationPreviewGroups>,
    zone: "paired" | "unpaired",
  ) => groups.map((group) => ({
    ...group,
    group_type: "relation",
    zone,
    status: zone,
  }));
  return {
    operation,
    can_submit: true,
    requires_note: isMismatch && operation === "confirm_link",
    message: isMismatch && operation === "confirm_link" ? "金额不一致，请填写备注。" : "",
    before: {
      groups: operation === "withdraw_link"
        ? asRelationGroups(buildRelationPreviewGroups(rows, caseId, "paired", "together"), "paired")
        : asSelectionGroups(buildRelationPreviewGroups(rows, caseId, "unpaired", "separate")),
    },
    after: {
      groups:
        operation === "withdraw_link"
          ? asSelectionGroups(buildWithdrawAfterPreviewGroups(rows))
          : asRelationGroups(buildRelationPreviewGroups(rows, caseId, "paired", "together"), "paired"),
    },
    amount_summary: amountSummary,
    restored_relations:
      operation === "withdraw_link" && canRestoreWithdrawRows
        ? [{ case_id: "CASE-RESTORED", row_ids: withdrawRestoredRows.map((row) => String(row.id)) }]
        : [],
  };
}

function buildWorkbenchDetail(rowId: string) {
  const details: Record<string, { row: Record<string, unknown> }> = {
    "bk-p-202603-001": {
      row: {
        id: "bk-p-202603-001",
        type: "bank",
        case_id: "CASE-202603-001",
        trade_time: "2026-03-25 14:22",
        debit_amount: "128,000.00",
        credit_amount: null,
        counterparty_name: "华东设备供应商",
        payment_account_label: "招商银行 9123",
        invoice_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
        pay_receive_time: "2026-03-25 14:22",
        remark: "设备采购款，已闭环",
        repayment_date: null,
        available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
        summary_fields: {
          资金方向: "支出",
          交易时间: "2026-03-25 14:22",
          借方发生额: "128,000.00",
          贷方发生额: "—",
          对方户名: "华东设备供应商",
          支付账户: "招商银行 9123",
          和发票关联情况: "完全关联",
          "支付/收款时间": "2026-03-25 14:22",
          备注: "设备采购款，已闭环",
          还借款日期: "—",
        },
        detail_fields: {
          资金方向: "支出",
          账号: "6225 **** **** 9123",
          账户名称: "杭州溯源科技有限公司招商银行基本户",
          余额: "2,488,310.55",
          币种: "CNY",
          对方账号: "6214 **** **** 4432",
          对方开户机构: "中国银行上海张江支行",
          记账日期: "2026-03-25",
          摘要: "设备供应商付款",
          备注: "OA 已闭环，进项票已核销",
          "账户明细编号-交易流水号": "DET-20260325-101",
          企业流水号: "CORP-20260325-7781",
          凭证种类: "网银付款",
          凭证号: "VCH-031525-01",
        },
      },
    },
    "iv-p-202603-001": {
      row: {
        id: "iv-p-202603-001",
        type: "invoice",
        case_id: "CASE-202603-001",
        seller_tax_no: "91310000MA1K8A001X",
        seller_name: "杭州溯源科技有限公司",
        buyer_tax_no: "91310110MA1F99088Q",
        buyer_name: "华东设备供应商",
        issue_date: "2026-03-25",
        amount: "128,000.00",
        tax_rate: "13%",
        tax_amount: "16,640.00",
        total_with_tax: "144,640.00",
        invoice_type: "进项专票",
        invoice_bank_relation: { code: "fully_linked", label: "完全关联", tone: "success" },
        available_actions: ["detail", "cancel_link"],
        summary_fields: {
          销方识别号: "91310000MA1K8A001X",
          销方名称: "杭州溯源科技有限公司",
          购方识别号: "91310110MA1F99088Q",
          购买方名称: "华东设备供应商",
          开票日期: "2026-03-25",
          金额: "128,000.00",
          税率: "13%",
          税额: "16,640.00",
          价税合计: "144,640.00",
          发票类型: "进项专票",
        },
        detail_fields: {
          序号: "1",
          发票代码: "032002600111",
          发票号码: "00061345",
          备注: "已与银行付款和 OA 闭环",
        },
      },
    },
    "iv-o-202603-001": {
      row: {
        id: "iv-o-202603-001",
        type: "invoice",
        source_kind: "oa_attachment_invoice",
        case_id: "CASE-202603-101",
        seller_tax_no: "91330108MA27B4011D",
        seller_name: "智能工厂设备商",
        buyer_tax_no: "91310000MA1K8A001X",
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
          source_expense_row_index: "1",
          source_expense_item_id: "oa-o-202603-001:item:1",
          source_attachment_name: "设备尾款附件发票.pdf",
          source_attachment_key: "oa-o-202603-001/item-1/invoice.pdf",
        },
      },
    },
  };

  return details[rowId] ?? {
    row: {
      id: rowId,
      type: "oa",
      case_id: "CASE-FALLBACK",
      applicant: "未知",
      project_name: "未知项目",
      apply_type: "未知类型",
      amount: "0.00",
      counterparty_name: "未知对方",
      reason: "未知",
      oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
      available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
      summary_fields: {
        申请人: "未知",
        项目名称: "未知项目",
      },
      detail_fields: {
        OA单号: rowId,
      },
    },
  };
}

function buildTaxOffsetPayload(month: string) {
  if (month === "2026-04") {
    return {
      month,
      output_items: [
        {
          id: "to-202604-001",
          buyer_name: "智能工厂客户",
          issue_date: "2026-04-08",
          invoice_no: "90352011",
          tax_amount: "18,200.00",
          total_with_tax: "158,200.00",
          invoice_type: "销项专票",
        },
        {
          id: "to-202604-002",
          buyer_name: "项目维保客户",
          issue_date: "2026-04-18",
          invoice_no: "90352012",
          tax_amount: "4,800.00",
          total_with_tax: "84,800.00",
          invoice_type: "销项普票",
        },
      ],
      input_items: [
        {
          id: "ti-202604-001",
          seller_name: "系统设备商",
          issue_date: "2026-04-09",
          invoice_no: "21203490",
          tax_amount: "10,920.00",
          total_with_tax: "94,920.00",
          risk_level: "低",
          certified_status: "已认证",
          is_locked_certified: true,
        },
        {
          id: "ti-202604-002",
          seller_name: "实施外包服务商",
          issue_date: "2026-04-16",
          invoice_no: "21203491",
          tax_amount: "9,600.00",
          total_with_tax: "169,600.00",
          risk_level: "中",
          certified_status: "待认证",
          is_locked_certified: false,
        },
        {
          id: "ti-202604-003",
          seller_name: "办公耗材商",
          issue_date: "2026-04-20",
          invoice_no: "21203492",
          tax_amount: "2,340.00",
          total_with_tax: "20,340.00",
          risk_level: "低",
          certified_status: "待认证",
          is_locked_certified: false,
        },
      ],
      input_plan_items: [
        {
          id: "ti-202604-001",
          seller_name: "系统设备商",
          issue_date: "2026-04-09",
          invoice_no: "21203490",
          tax_amount: "10,920.00",
          total_with_tax: "94,920.00",
          risk_level: "低",
          certified_status: "已认证",
          is_locked_certified: true,
        },
        {
          id: "ti-202604-002",
          seller_name: "实施外包服务商",
          issue_date: "2026-04-16",
          invoice_no: "21203491",
          tax_amount: "9,600.00",
          total_with_tax: "169,600.00",
          risk_level: "中",
          certified_status: "待认证",
          is_locked_certified: false,
        },
        {
          id: "ti-202604-003",
          seller_name: "办公耗材商",
          issue_date: "2026-04-20",
          invoice_no: "21203492",
          tax_amount: "2,340.00",
          total_with_tax: "20,340.00",
          risk_level: "低",
          certified_status: "待认证",
          is_locked_certified: false,
        },
      ],
      certified_items: [
        {
          id: "tc-202604-001",
          seller_name: "系统设备商",
          issue_date: "2026-04-09",
          invoice_no: "21203490",
          tax_amount: "10,920.00",
          total_with_tax: "94,920.00",
          status: "已认证",
        },
        {
          id: "tc-202604-099",
          seller_name: "外部物业服务商",
          issue_date: "2026-04-25",
          invoice_no: "21203999",
          tax_amount: "1,280.00",
          total_with_tax: "21,280.00",
          status: "已认证",
        },
      ],
      certified_matched_rows: [
        {
          id: "tc-202604-001",
          seller_name: "系统设备商",
          issue_date: "2026-04-09",
          invoice_no: "21203490",
          tax_amount: "10,920.00",
          total_with_tax: "94,920.00",
          status: "已认证",
          matched_input_id: "ti-202604-001",
        },
      ],
      certified_outside_plan_rows: [
        {
          id: "tc-202604-099",
          seller_name: "外部物业服务商",
          issue_date: "2026-04-25",
          invoice_no: "21203999",
          tax_amount: "1,280.00",
          total_with_tax: "21,280.00",
          status: "已认证",
          matched_input_id: null,
        },
      ],
      locked_certified_input_ids: ["ti-202604-001"],
      default_selected_output_ids: ["to-202604-001", "to-202604-002"],
      default_selected_input_ids: ["ti-202604-002", "ti-202604-003"],
      summary: {
        output_tax: "23,000.00",
        certified_input_tax: "12,200.00",
        planned_input_tax: "11,940.00",
        input_tax: "24,140.00",
        deductible_tax: "23,000.00",
        result_label: "本月留抵税额",
        result_amount: "1,140.00",
      },
    };
  }

  if (month === "2026-05") {
    return {
      month,
      output_items: [],
      input_items: [],
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
    input_items: [
      {
        id: "ti-202603-001",
        seller_name: "设备供应商",
        issue_date: "2026-03-22",
        invoice_no: "11203490",
        tax_rate: "13%",
        tax_amount: "12,480.00",
        total_with_tax: "108,480.00",
        risk_level: "低",
        certified_status: "待认证",
        is_locked_certified: false,
      },
      {
        id: "ti-202603-002",
        seller_name: "集成服务商",
        issue_date: "2026-03-24",
        invoice_no: "11203491",
        tax_rate: "6%",
        tax_amount: "5,760.00",
        total_with_tax: "101,760.00",
        risk_level: "中",
        certified_status: "待认证",
        is_locked_certified: false,
      },
    ],
    input_plan_items: [
      {
        id: "ti-202603-001",
        seller_name: "设备供应商",
        issue_date: "2026-03-22",
        invoice_no: "11203490",
        tax_rate: "13%",
        tax_amount: "12,480.00",
        total_with_tax: "108,480.00",
        risk_level: "低",
        certified_status: "待认证",
        is_locked_certified: false,
      },
      {
        id: "ti-202603-002",
        seller_name: "集成服务商",
        issue_date: "2026-03-24",
        invoice_no: "11203491",
        tax_rate: "6%",
        tax_amount: "5,760.00",
        total_with_tax: "101,760.00",
        risk_level: "中",
        certified_status: "待认证",
        is_locked_certified: false,
      },
    ],
    certified_items: [],
    certified_matched_rows: [],
    certified_outside_plan_rows: [],
    locked_certified_input_ids: [],
    default_selected_output_ids: ["to-202603-001"],
    default_selected_input_ids: ["ti-202603-001", "ti-202603-002"],
    summary: {
      output_tax: "41,600.00",
      certified_input_tax: "0.00",
      planned_input_tax: "18,240.00",
      input_tax: "18,240.00",
      deductible_tax: "18,240.00",
      result_label: "本月应纳税额",
      result_amount: "23,360.00",
    },
  };
}

function sumTaxAmount(rows: Array<{ tax_amount: string }>) {
  return rows.reduce((sum, row) => sum + Number(row.tax_amount.replace(/,/g, "")), 0);
}

function formatTaxMoney(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function calculateTaxPayload(
  month: string,
  selectedOutputIds: string[],
  selectedInputIds: string[],
  monthPayloadOverride?: ReturnType<typeof buildTaxOffsetPayload>,
) {
  const monthPayload = monthPayloadOverride ?? buildTaxOffsetPayload(month);
  const lockedIds = new Set(monthPayload.locked_certified_input_ids ?? []);
  const selectedPlanRows = (monthPayload.input_plan_items ?? []).filter(
    (item) => selectedInputIds.includes(item.id) && !lockedIds.has(item.id),
  );
  const outputTax = sumTaxAmount(monthPayload.output_items ?? []);
  const certifiedInputTax = sumTaxAmount(monthPayload.certified_items ?? []);
  const plannedInputTax = sumTaxAmount(selectedPlanRows);
  const inputTax = certifiedInputTax + plannedInputTax;
  const deductibleTax = Math.min(outputTax, inputTax);
  const resultLabel = outputTax > deductibleTax ? "本月应纳税额" : "本月留抵税额";
  const resultAmount = outputTax > deductibleTax ? outputTax - deductibleTax : inputTax - deductibleTax;

  return {
    month,
    selected_output_ids: selectedOutputIds,
    selected_input_ids: selectedInputIds,
    summary: {
      output_tax: formatTaxMoney(outputTax),
      certified_input_tax: formatTaxMoney(certifiedInputTax),
      planned_input_tax: formatTaxMoney(plannedInputTax),
      input_tax: formatTaxMoney(inputTax),
      deductible_tax: formatTaxMoney(deductibleTax),
      result_label: resultLabel,
      result_amount: formatTaxMoney(resultAmount),
    },
  };
}

function createTaxOffsetStateStore() {
  const store = new Map<string, ReturnType<typeof buildTaxOffsetPayload>>([
    ["2026-03", buildTaxOffsetPayload("2026-03")],
    ["2026-04", buildTaxOffsetPayload("2026-04")],
    ["2026-05", buildTaxOffsetPayload("2026-05")],
  ]);

  return {
    get(month: string) {
      return cloneJson(store.get(month) ?? buildTaxOffsetPayload(month));
    },
    set(month: string, payload: ReturnType<typeof buildTaxOffsetPayload>) {
      store.set(month, cloneJson(payload));
    },
  };
}

function buildMockCertifiedPreviewRows(month: string) {
  if (month === "2026-03") {
    return [
      {
        id: "tc-preview-202603-001",
        month: "2026-03",
        source_file_name: "2026年3月 进项认证结果  用途确认信息.xlsx",
        source_row_number: 8,
        digital_invoice_no: null,
        invoice_code: "031001900111",
        invoice_no: "11203490",
        issue_date: "2026-03-22",
        seller_tax_no: "91310108MA1N22179P",
        seller_name: "设备供应商",
        amount: "96,000.00",
        tax_amount: "12,480.00",
        deductible_tax_amount: "12,480.00",
        selection_status: "已勾选",
        invoice_status: "正常",
        selection_time: "2026-03-31 10:00:00",
      },
      {
        id: "tc-preview-202603-099",
        month: "2026-03",
        source_file_name: "2026年3月 进项认证结果  用途确认信息.xlsx",
        source_row_number: 15,
        digital_invoice_no: null,
        invoice_code: "031001900199",
        invoice_no: "11203999",
        issue_date: "2026-03-28",
        seller_tax_no: "91530000123456789P",
        seller_name: "物业服务商",
        amount: "12,000.00",
        tax_amount: "1,600.00",
        deductible_tax_amount: "1,600.00",
        selection_status: "已勾选",
        invoice_status: "正常",
        selection_time: "2026-03-31 10:05:00",
      },
    ];
  }

  const count = month === "2026-01" ? 60 : month === "2026-02" ? 39 : 0;
  return Array.from({ length: count }, (_, index) => ({
    id: `tc-preview-${month.replace("-", "")}-${String(index + 1).padStart(3, "0")}`,
    month,
    source_file_name: `${month} 已认证导入.xlsx`,
    source_row_number: index + 8,
    digital_invoice_no: null,
    invoice_code: null,
    invoice_no: `${month.replace("-", "")}${String(index + 1).padStart(6, "0")}`,
    issue_date: `${month}-15`,
    seller_tax_no: `91530000${String(index + 1).padStart(10, "0")}`,
    seller_name: `测试销方 ${index + 1}`,
    amount: "100.00",
    tax_amount: "13.00",
    deductible_tax_amount: "13.00",
    selection_status: "已勾选",
    invoice_status: "正常",
    selection_time: `${month}-28 09:00:00`,
  }));
}

function resolveMockCertifiedPreview(fileName: string) {
  const month = fileName.includes("2026年1月")
    ? "2026-01"
    : fileName.includes("2026年2月")
      ? "2026-02"
      : "2026-03";
  const rows = buildMockCertifiedPreviewRows(month).map((row, index) => {
    const matchedPlan = month === "2026-03" && index === 0;
    return {
      ...row,
      row_status: "recognized",
      match_status: matchedPlan ? "matched_plan" : "outside_plan",
      matched_plan_id: matchedPlan ? "ti-202603-001" : null,
      dedupe_status: "new",
      error_message: null,
    };
  });
  const matchedPlanCount = month === "2026-03" ? 1 : 0;
  const outsidePlanCount = rows.length - matchedPlanCount;
  return {
    month,
    rows,
    recognizedCount: rows.length,
    invalidCount: 0,
    matchedPlanCount,
    outsidePlanCount,
  };
}

function matchCertifiedPreviewRowToPlan(
  row: {
    invoice_no?: string | null;
    seller_tax_no?: string | null;
    seller_name?: string | null;
    issue_date?: string | null;
    tax_amount?: string | null;
  },
  planRows: Array<Record<string, string | boolean | null>>,
) {
  if (row.invoice_no) {
    const invoiceMatch = planRows.find((planRow) => planRow.invoice_no === row.invoice_no);
    if (invoiceMatch) {
      return invoiceMatch;
    }
  }
  return planRows.find((planRow) => {
    const sellerMatches =
      (row.seller_tax_no && planRow.seller_tax_no === row.seller_tax_no) || planRow.seller_name === row.seller_name;
    return sellerMatches && planRow.issue_date === row.issue_date && planRow.tax_amount === row.tax_amount;
  });
}

function applyCertifiedImportToTaxOffsetPayload(
  monthPayload: ReturnType<typeof buildTaxOffsetPayload>,
  certifiedRows: Array<{
    id: string;
    invoice_no?: string | null;
    seller_name?: string | null;
    seller_tax_no?: string | null;
    issue_date?: string | null;
    tax_amount?: string | null;
    amount?: string | null;
    deductible_tax_amount?: string | null;
  }>,
) {
  const nextPayload = cloneJson(monthPayload);
  const inputPlanRows = nextPayload.input_plan_items ?? [];
  const matchedRows: typeof nextPayload.certified_matched_rows = [];
  const outsidePlanRows: typeof nextPayload.certified_outside_plan_rows = [];
  const lockedIds = new Set<string>();
  const certifiedItems = certifiedRows.map((row) => ({
    id: row.id,
    seller_name: row.seller_name ?? "--",
    issue_date: row.issue_date ?? "--",
    invoice_no: row.invoice_no ?? "--",
    tax_amount: row.tax_amount ?? "0.00",
    total_with_tax: formatTaxMoney(
      Number(String(row.amount ?? "0").replace(/,/g, "")) + Number(String(row.tax_amount ?? "0").replace(/,/g, "")),
    ),
    status: "已认证",
  }));

  certifiedRows.forEach((row, index) => {
    const certifiedItem = certifiedItems[index];
    const matchedInput = matchCertifiedPreviewRowToPlan(row, inputPlanRows as Array<Record<string, string | boolean | null>>);
    if (matchedInput) {
      matchedRows.push({
        ...certifiedItem,
        matched_input_id: String(matchedInput.id ?? ""),
      });
      lockedIds.add(String(matchedInput.id ?? ""));
      matchedInput.certified_status = "已认证";
      matchedInput.is_locked_certified = true;
    } else {
      outsidePlanRows.push({
        ...certifiedItem,
        matched_input_id: null,
      });
    }
  });

  nextPayload.certified_items = certifiedItems;
  nextPayload.certified_matched_rows = matchedRows;
  nextPayload.certified_outside_plan_rows = outsidePlanRows;
  nextPayload.locked_certified_input_ids = Array.from(lockedIds);
  nextPayload.default_selected_input_ids = (nextPayload.default_selected_input_ids ?? []).filter((id) => !lockedIds.has(id));
  nextPayload.summary = calculateTaxPayload(
    nextPayload.month,
    nextPayload.default_selected_output_ids ?? [],
    nextPayload.default_selected_input_ids ?? [],
    nextPayload,
  ).summary;
  return nextPayload;
}

type CostProjectRow = {
  transaction_id: string;
  trade_time: string;
  project_name?: string;
  direction: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  counterparty_name: string;
  payment_account_label: string;
  bank_tag_code?: string;
  bank_tag_label?: string;
  bank_tag_primary_label?: string;
  bank_tag_sub_label?: string;
  bank_tag_label_path?: string[];
};

type CostTransactionDetail = {
  month: string;
  transaction: {
    id: string;
    project_name: string;
    expense_type: string;
    expense_content: string;
    trade_time: string;
    direction: string;
    amount: string;
    counterparty_name: string;
    payment_account_label: string;
    remark: string;
    oa_applicant?: string;
    summary_fields: Record<string, string>;
    detail_fields: Record<string, string>;
    cost_allocations?: Array<{
      row_key: string;
      project_name: string;
      project_id: string;
      expense_type: string;
      expense_content: string;
      oa_applicant: string;
      amount: string;
    }>;
  };
};

const completedCostProjectNames = new Set([
  "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
]);

function isCostProjectVisibleForScope(projectName: string, projectScope: string | null | undefined) {
  return projectScope === "all" || !completedCostProjectNames.has(projectName);
}

const costStatisticsProjectRows: Record<string, Record<string, CostProjectRow[]>> = {
  "2026-03": {
    云南溯源科技: [
      {
        transaction_id: "cost-txn-001",
        trade_time: "2026-03-10T21:27:55+08:00",
        direction: "支出",
        expense_type: "设备货款及材料费",
        expense_content: "PLC 模块采购",
        amount: "10,000.00",
        counterparty_name: "昆明设备供应商",
        payment_account_label: "工商银行 账户 0001",
      },
      {
        transaction_id: "cost-txn-002",
        trade_time: "2026-03-12 08:40:12",
        direction: "支出",
        expense_type: "设备货款及材料费",
        expense_content: "PLC 模块采购",
        amount: "2,500.00",
        counterparty_name: "昆明设备供应商",
        payment_account_label: "工商银行 账户 0001",
      },
      {
        transaction_id: "cost-txn-003",
        trade_time: "2026-03-18 17:02:09",
        direction: "支出",
        expense_type: "交通费",
        expense_content: "项目现场往返交通",
        amount: "860.00",
        counterparty_name: "云南航空",
        payment_account_label: "招商银行 账户 2201",
      },
    ],
    "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目": [
      {
        transaction_id: "cost-txn-004",
        trade_time: "2026-03-20 15:11:02",
        direction: "支出",
        expense_type: "人工费/劳务费/服务费",
        expense_content: "现场调试服务",
        amount: "5,200.00",
        counterparty_name: "昆明运维服务商",
        payment_account_label: "建设银行 账户 1388",
      },
    ],
  },
  "2026-04": {
    "昆明卷烟厂动力设备控制系统升级改造项目": [
      {
        transaction_id: "cost-txn-101",
        trade_time: "2026-04-02 09:15:08",
        direction: "支出",
        expense_type: "经营/办公费用",
        expense_content: "项目办公室租赁",
        amount: "4,800.00",
        counterparty_name: "云南冶金集团股份有限公司",
        payment_account_label: "平安银行 账户 8821",
      },
      {
        transaction_id: "cost-txn-102",
        trade_time: "2026-04-16 09:15:08",
        direction: "支出",
        expense_type: "经营/办公费用",
        expense_content: "项目办公室租赁",
        amount: "4,800.00",
        counterparty_name: "云南冶金集团股份有限公司",
        payment_account_label: "平安银行 账户 8821",
      },
    ],
  },
};

const costStatisticsTransactionDetails: Record<string, CostTransactionDetail> = {
  "cost-txn-001": {
    month: "2026-03",
    transaction: {
      id: "cost-txn-001",
      project_name: "云南溯源科技",
      expense_type: "设备货款及材料费",
      expense_content: "PLC 模块采购",
      trade_time: "2026-03-10 21:27:55",
      direction: "支出",
      amount: "10,000.00",
      counterparty_name: "昆明设备供应商",
      payment_account_label: "工商银行 账户 0001",
      remark: "设备采购款",
      oa_applicant: "张三、李四",
      cost_allocations: [
        {
          row_key: "cost-txn-001:oa:oa-a",
          project_name: "云南溯源科技",
          project_id: "P-A",
          expense_type: "设备货款及材料费",
          expense_content: "PLC 模块采购",
          oa_applicant: "张三",
          amount: "6,000.00",
        },
        {
          row_key: "cost-txn-001:oa:oa-b",
          project_name: "昆明升级项目",
          project_id: "P-B",
          expense_type: "安装服务费",
          expense_content: "PLC 安装",
          oa_applicant: "李四",
          amount: "4,000.00",
        },
      ],
      summary_fields: {
        资金方向: "支出",
        交易时间: "2026-03-10 21:27:55",
        对方户名: "昆明设备供应商",
      },
      detail_fields: {
        资金方向: "支出",
        账号: "62220001",
        账户名称: "云南溯源科技有限公司",
        摘要: "PLC 模块采购",
        备注: "设备采购款",
        费用类型: "设备货款及材料费",
        费用内容: "PLC 模块采购",
      },
    },
  },
  "cost-txn-002": {
    month: "2026-03",
    transaction: {
      id: "cost-txn-002",
      project_name: "云南溯源科技",
      expense_type: "设备货款及材料费",
      expense_content: "PLC 模块采购",
      trade_time: "2026-03-12 08:40:12",
      amount: "2,500.00",
      counterparty_name: "昆明设备供应商",
      payment_account_label: "工商银行 账户 0001",
      remark: "设备配件款",
      summary_fields: {
        交易时间: "2026-03-12 08:40:12",
        对方户名: "昆明设备供应商",
      },
      detail_fields: {
        账号: "62220001",
        账户名称: "云南溯源科技有限公司",
        摘要: "PLC 模块采购",
        备注: "设备配件款",
        费用类型: "设备货款及材料费",
        费用内容: "PLC 模块采购",
      },
    },
  },
  "cost-txn-003": {
    month: "2026-03",
    transaction: {
      id: "cost-txn-003",
      project_name: "云南溯源科技",
      expense_type: "交通费",
      expense_content: "项目现场往返交通",
      trade_time: "2026-03-18 17:02:09",
      amount: "860.00",
      counterparty_name: "云南航空",
      payment_account_label: "招商银行 账户 2201",
      remark: "项目交通费",
      summary_fields: {
        交易时间: "2026-03-18 17:02:09",
        对方户名: "云南航空",
      },
      detail_fields: {
        账号: "62220002",
        账户名称: "云南溯源科技有限公司",
        摘要: "项目现场往返交通",
        备注: "项目交通费",
        费用类型: "交通费",
        费用内容: "项目现场往返交通",
      },
    },
  },
  "cost-txn-004": {
    month: "2026-03",
    transaction: {
      id: "cost-txn-004",
      project_name: "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
      expense_type: "人工费/劳务费/服务费",
      expense_content: "现场调试服务",
      trade_time: "2026-03-20 15:11:02",
      amount: "5,200.00",
      counterparty_name: "昆明运维服务商",
      payment_account_label: "建设银行 账户 1388",
      remark: "项目调试服务费",
      summary_fields: {
        交易时间: "2026-03-20 15:11:02",
        对方户名: "昆明运维服务商",
      },
      detail_fields: {
        账号: "62220003",
        账户名称: "云南溯源科技有限公司",
        摘要: "现场调试服务",
        备注: "项目调试服务费",
        费用类型: "人工费/劳务费/服务费",
        费用内容: "现场调试服务",
      },
    },
  },
  "cost-txn-101": {
    month: "2026-04",
    transaction: {
      id: "cost-txn-101",
      project_name: "昆明卷烟厂动力设备控制系统升级改造项目",
      expense_type: "经营/办公费用",
      expense_content: "项目办公室租赁",
      trade_time: "2026-04-02 09:15:08",
      amount: "4,800.00",
      counterparty_name: "云南冶金集团股份有限公司",
      payment_account_label: "平安银行 账户 8821",
      remark: "办公室租赁费",
      summary_fields: {
        交易时间: "2026-04-02 09:15:08",
        对方户名: "云南冶金集团股份有限公司",
      },
      detail_fields: {
        账号: "62220004",
        账户名称: "云南溯源科技有限公司",
        摘要: "项目办公室租赁",
        备注: "办公室租赁费",
        费用类型: "经营/办公费用",
        费用内容: "项目办公室租赁",
      },
    },
  },
  "cost-txn-102": {
    month: "2026-04",
    transaction: {
      id: "cost-txn-102",
      project_name: "昆明卷烟厂动力设备控制系统升级改造项目",
      expense_type: "经营/办公费用",
      expense_content: "项目办公室租赁",
      trade_time: "2026-04-16 09:15:08",
      amount: "4,800.00",
      counterparty_name: "云南冶金集团股份有限公司",
      payment_account_label: "平安银行 账户 8821",
      remark: "办公室租赁费",
      summary_fields: {
        交易时间: "2026-04-16 09:15:08",
        对方户名: "云南冶金集团股份有限公司",
      },
      detail_fields: {
        账号: "62220004",
        账户名称: "云南溯源科技有限公司",
        摘要: "项目办公室租赁",
        备注: "办公室租赁费",
        费用类型: "经营/办公费用",
        费用内容: "项目办公室租赁",
      },
    },
  },
};

function mockBankTagForCostRow(row: CostProjectRow) {
  if (row.expense_type === "交通费") {
    return {
      bank_tag_code: "travel_transport",
      bank_tag_label: "交通费",
      bank_tag_primary_label: "差旅交通",
      bank_tag_sub_label: "交通费",
      bank_tag_label_path: ["差旅交通", "交通费"],
    };
  }
  if (row.expense_type === "经营/办公费用") {
    return {
      bank_tag_code: "office_rent",
      bank_tag_label: "办公租赁",
      bank_tag_primary_label: "运营支出",
      bank_tag_sub_label: "办公租赁",
      bank_tag_label_path: ["运营支出", "办公租赁"],
    };
  }
  if (row.expense_type === "人工费/劳务费/服务费") {
    return {
      bank_tag_code: "field_service",
      bank_tag_label: "现场服务",
      bank_tag_primary_label: "服务支出",
      bank_tag_sub_label: "现场服务",
      bank_tag_label_path: ["服务支出", "现场服务"],
    };
  }
  return {
    bank_tag_code: "project_material",
    bank_tag_label: "设备材料",
    bank_tag_primary_label: "项目开销",
    bank_tag_sub_label: "设备材料",
    bank_tag_label_path: ["项目开销", "设备材料"],
  };
}

function sumCostAmounts(rows: Array<{ amount: string }>) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  return total.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function buildAllCostProjectRows() {
  return Object.values(costStatisticsProjectRows).reduce<Record<string, CostProjectRow[]>>((result, projectMap) => {
    for (const [projectName, rows] of Object.entries(projectMap)) {
      result[projectName] = [...(result[projectName] ?? []), ...rows];
    }
    return result;
  }, {});
}

function buildCostStatisticsExplorerPayload(
  month: string,
  projectScope = "active",
  options: { duplicateTransactionRows?: boolean } = {},
) {
  const baseProjectRowMap = month === "all" ? buildAllCostProjectRows() : (costStatisticsProjectRows[month] ?? {});
  const sourceProjectRowMap = Object.fromEntries(
    Object.entries(baseProjectRowMap).map(([projectName, rows]) => [projectName, [...rows]]),
  );
  if (options.duplicateTransactionRows && (month === "all" || month === "2026-03")) {
    const projectRows = sourceProjectRowMap["云南溯源科技"] ?? [];
    const duplicateSourceRow = projectRows.find((row) => row.transaction_id === "cost-txn-001");
    if (duplicateSourceRow) {
      sourceProjectRowMap["云南溯源科技"] = [
        ...projectRows,
        {
          ...duplicateSourceRow,
          amount: "1,250.00",
          expense_content: "PLC 模块采购追加成本",
        },
      ];
    }
  }
  const projectRowMap = Object.fromEntries(
    Object.entries(sourceProjectRowMap).filter(([projectName]) =>
      isCostProjectVisibleForScope(projectName, projectScope),
    ),
  );
  const timeRows = Object.entries(projectRowMap)
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
        remark: costStatisticsTransactionDetails[row.transaction_id]?.transaction.remark ?? "",
        ...mockBankTagForCostRow(row),
      })),
    )
    .sort((left, right) => right.trade_time.localeCompare(left.trade_time));
  const incomeRows = month === "all" || month === "2026-03"
    ? [{
        transaction_id: "cost-income-001",
        trade_time: "2026-03-22 10:30:00",
        direction: "收入",
        project_name: "未配对OA",
        expense_type: "项目回款",
        expense_content: "客户回款",
        amount: "2,000.00",
        counterparty_name: "项目客户",
        payment_account_label: "工商银行 账户 0001",
        remark: "项目回款",
        bank_tag_code: "income_collection",
        bank_tag_label: "项目回款",
        bank_tag_primary_label: "经营收入",
        bank_tag_sub_label: "项目回款",
        bank_tag_label_path: ["经营收入", "项目回款"],
      }]
    : month === "2026-04"
      ? [{
          transaction_id: "cost-income-101",
          trade_time: "2026-04-18 10:30:00",
          direction: "收入",
          project_name: "未配对OA",
          expense_type: "其他收入",
          expense_content: "退款到账",
          amount: "1,500.00",
          counterparty_name: "供应商退款",
          payment_account_label: "平安银行 账户 8821",
          remark: "退款",
          bank_tag_code: "income_refund",
          bank_tag_label: "退款",
          bank_tag_primary_label: "经营收入",
          bank_tag_sub_label: "退款",
          bank_tag_label_path: ["经营收入", "退款"],
        }]
      : [];
  const bankFlowTimeRows = [...timeRows, ...incomeRows]
    .map((row) => ({
      ...row,
      project_name: "",
      expense_type: "",
      expense_content: row.remark || row.expense_content || "—",
    }))
    .sort((left, right) => right.trade_time.localeCompare(left.trade_time));

  const projectRows = Object.entries(projectRowMap)
    .map(([projectName, rows]) => ({
      project_name: projectName,
      total_amount: sumCostAmounts(rows),
      transaction_count: rows.length,
      expense_type_count: new Set(rows.map((row) => row.expense_type)).size,
    }))
    .sort((left, right) => Number(right.total_amount.replace(/,/g, "")) - Number(left.total_amount.replace(/,/g, "")));

  const expenseTypeGroups = new Map<string, { totalAmount: number; transactionCount: number; projects: Set<string> }>();
  for (const row of timeRows) {
    const bucket = expenseTypeGroups.get(row.expense_type) ?? {
      totalAmount: 0,
      transactionCount: 0,
      projects: new Set<string>(),
    };
    bucket.totalAmount += Number(row.amount.replace(/,/g, ""));
    bucket.transactionCount += 1;
    bucket.projects.add(row.project_name);
    expenseTypeGroups.set(row.expense_type, bucket);
  }
  const expenseTypeRows = Array.from(expenseTypeGroups.entries())
    .map(([expenseType, bucket]) => ({
      expense_type: expenseType,
      total_amount: bucket.totalAmount.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
      transaction_count: bucket.transactionCount,
      project_count: bucket.projects.size,
    }))
    .sort((left, right) => Number(right.total_amount.replace(/,/g, "")) - Number(left.total_amount.replace(/,/g, "")));

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
      expense_amount: sumCostAmounts(bankFlowTimeRows.filter((row) => row.direction === "支出")),
      income_amount: sumCostAmounts(bankFlowTimeRows.filter((row) => row.direction === "收入")),
      expense_transaction_count: bankFlowTimeRows.filter((row) => row.direction === "支出").length,
      income_transaction_count: bankFlowTimeRows.filter((row) => row.direction === "收入").length,
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
    project_rows: projectRows,
    expense_type_rows: expenseTypeRows,
  };
}

function buildCostStatisticsExplorerPagePayload(
  url: URL,
  payload: ReturnType<typeof buildCostStatisticsExplorerPayload>,
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
  const query = (url.searchParams.get("query") ?? "").trim().toLocaleLowerCase("zh-CN");
  const inScope = <Row extends { trade_time: string }>(rows: Row[]) => rows.filter((row) => (
    scope === "all"
    || (scope.startsWith("year:") ? row.trade_time.startsWith(`${scope.slice(5)}-`) : row.trade_time.startsWith(scope))
  ));
  const matchesQuery = (row: Record<string, unknown>) => !query || [
    row.trade_time,
    row.counterparty_name,
    row.payment_account_label,
    row.direction,
    row.amount,
    row.expense_content,
    row.remark,
    row.project_name,
    row.expense_type,
    row.oa_applicant,
    row.bank_tag_primary_label,
    row.bank_tag_sub_label,
    row.bank_tag_label,
  ].map((value) => String(value ?? "")).join("\n").toLocaleLowerCase("zh-CN").includes(query);
  const costRows = inScope(payload.time_rows).filter(matchesQuery);
  const bankFlowRows = inScope(payload.bank_flow_time_rows).filter(matchesQuery);
  const amountNumber = (value: string) => Number(value.replace(/,/g, "")) || 0;
  const percentage = (amount: number, total: number) => `${((amount / (total || 1)) * 100).toFixed(1)}%`;

  const projectGroups = new Map<string, { amount: number; rows: typeof costRows; expenseTypes: Set<string> }>();
  const expenseGroups = new Map<string, { amount: number; rows: typeof costRows; projects: Set<string> }>();
  const bankGroups = new Map<string, { amount: number; rows: typeof costRows; projects: Set<string> }>();
  for (const row of costRows) {
    const project = projectGroups.get(row.project_name) ?? { amount: 0, rows: [], expenseTypes: new Set<string>() };
    project.amount += amountNumber(row.amount);
    project.rows.push(row);
    project.expenseTypes.add(row.expense_type);
    projectGroups.set(row.project_name, project);
    const expense = expenseGroups.get(row.expense_type) ?? { amount: 0, rows: [], projects: new Set<string>() };
    expense.amount += amountNumber(row.amount);
    expense.rows.push(row);
    expense.projects.add(row.project_name);
    expenseGroups.set(row.expense_type, expense);
    const accountLabel = row.payment_account_label || "未识别账户";
    const bank = bankGroups.get(accountLabel) ?? { amount: 0, rows: [], projects: new Set<string>() };
    bank.amount += amountNumber(row.amount);
    bank.rows.push(row);
    bank.projects.add(row.project_name);
    bankGroups.set(accountLabel, bank);
  }
  for (const account of payload.bank_accounts) {
    if (!bankGroups.has(account.payment_account_label)) {
      bankGroups.set(account.payment_account_label, { amount: 0, rows: [], projects: new Set<string>() });
    }
  }
  const costTotal = costRows.reduce((sum, row) => sum + amountNumber(row.amount), 0);
  const projectFacets = Array.from(projectGroups.entries()).map(([name, group]) => ({
    project_name: name,
    total_amount: group.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    transaction_count: group.rows.length,
    expense_type_count: group.expenseTypes.size,
    percentage_label: percentage(group.amount, costTotal),
  })).sort((left, right) => amountNumber(right.total_amount) - amountNumber(left.total_amount));
  const expenseFacets = Array.from(expenseGroups.entries()).map(([name, group]) => ({
    expense_type: name,
    total_amount: group.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    transaction_count: group.rows.length,
    project_count: group.projects.size,
    percentage_label: percentage(group.amount, costTotal),
  })).sort((left, right) => amountNumber(right.total_amount) - amountNumber(left.total_amount));
  const bankFacets = Array.from(bankGroups.entries()).map(([label, group]) => ({
    payment_account_label: label,
    total_amount: group.amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    transaction_count: group.rows.length,
    project_count: group.projects.size,
    percentage_label: percentage(group.amount, costTotal),
  })).sort((left, right) => amountNumber(right.total_amount) - amountNumber(left.total_amount));
  const tagGroups = new Map<string, { rows: typeof bankFlowRows; subLabels: Set<string> }>();
  for (const row of bankFlowRows) {
    const label = row.bank_tag_primary_label || row.bank_tag_label || "未标记";
    const group = tagGroups.get(label) ?? { rows: [], subLabels: new Set<string>() };
    group.rows.push(row);
    group.subLabels.add(row.bank_tag_sub_label || row.bank_tag_label || label);
    tagGroups.set(label, group);
  }
  const directionFacet = (rows: typeof bankFlowRows) => ({
    expense_amount: sumCostAmounts(rows.filter((row) => row.direction === "支出")),
    income_amount: sumCostAmounts(rows.filter((row) => row.direction === "收入")),
    expense_transaction_count: rows.filter((row) => row.direction === "支出").length,
    income_transaction_count: rows.filter((row) => row.direction === "收入").length,
  });
  const bankTagPrimary = Array.from(tagGroups.entries())
    .map(([label, group]) => ({
      primary_label: label,
      ...directionFacet(group.rows),
      sub_tag_count: group.subLabels.size,
    }))
    .sort((left, right) => {
      const rank = (row: typeof left) => {
        const expense = amountNumber(row.expense_amount);
        const income = amountNumber(row.income_amount);
        return expense > 0 && income === 0 ? 0 : expense > 0 && income > 0 ? 1 : income > 0 ? 2 : 3;
      };
      return rank(left) - rank(right)
        || amountNumber(right.expense_amount) + amountNumber(right.income_amount)
          - amountNumber(left.expense_amount) - amountNumber(left.income_amount)
        || left.primary_label.localeCompare(right.primary_label, "zh-CN");
    });
  const bankTagSub = primaryLabel
    ? Array.from(new Set((tagGroups.get(primaryLabel)?.rows ?? []).map((row) => row.bank_tag_sub_label || row.bank_tag_label || primaryLabel)))
        .map((label) => {
          const rows = (tagGroups.get(primaryLabel)?.rows ?? []).filter(
            (row) => (row.bank_tag_sub_label || row.bank_tag_label || primaryLabel) === label,
          );
          return { primary_label: primaryLabel, sub_label: label, ...directionFacet(rows) };
        })
    : [];
  const selectedProjectRows = projectGroups.get(projectName)?.rows ?? [];
  const selectedProjectTotal = selectedProjectRows.reduce((sum, row) => sum + amountNumber(row.amount), 0);
  const projectExpenseFacets = expenseFacets
    .filter((item) => selectedProjectRows.some((row) => row.expense_type === item.expense_type))
    .map((item) => ({
      ...item,
      percentage_label: percentage(amountNumber(item.total_amount), selectedProjectTotal),
    }));
  const selectedBankRows = bankGroups.get(paymentAccountLabel)?.rows ?? [];
  const selectedBankTotal = selectedBankRows.reduce((sum, row) => sum + amountNumber(row.amount), 0);
  const bankProjectFacets = Array.from(new Set(selectedBankRows.map((row) => row.project_name))).map((name) => {
    const rows = selectedBankRows.filter((row) => row.project_name === name);
    const amount = rows.reduce((sum, row) => sum + amountNumber(row.amount), 0);
    return {
      project_name: name,
      total_amount: amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      transaction_count: rows.length,
      expense_type_count: new Set(rows.map((row) => row.expense_type)).size,
      percentage_label: percentage(amount, selectedBankTotal),
    };
  }).sort((left, right) => amountNumber(right.total_amount) - amountNumber(left.total_amount));

  let matchedRows = view === "time" ? bankFlowRows : [];
  if (view === "project" && projectName && expenseType) {
    matchedRows = costRows.filter((row) => row.project_name === projectName && row.expense_type === expenseType);
  } else if (view === "bank" && paymentAccountLabel && projectName) {
    matchedRows = costRows.filter(
      (row) => row.payment_account_label === paymentAccountLabel && row.project_name === projectName,
    );
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
  const rows = matchedRows.slice(cursorOffset, cursorOffset + pageSize);
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
    available_years: Array.from(new Set([...payload.time_rows, ...payload.bank_flow_time_rows].map((row) => row.trade_time.slice(0, 4)))).sort().reverse(),
    facets: {
      projects: view === "project" ? projectFacets : view === "bank" && paymentAccountLabel
        ? bankProjectFacets
        : [],
      expense_types: view === "expense_type" ? expenseFacets : view === "project" && projectName
        ? projectExpenseFacets
        : [],
      bank_accounts: view === "bank" ? bankFacets : [],
      bank_tag_primary: view === "bank_tag" ? bankTagPrimary : [],
      bank_tag_sub: view === "bank_tag" ? bankTagSub : [],
    },
    rows,
    row_count: matchedRows.length,
    next_cursor: nextOffset < matchedRows.length ? `mock:${nextOffset}` : null,
  };
}

function buildCostStatisticsTransactionPayload(transactionId: string) {
  const detail = costStatisticsTransactionDetails[transactionId];
  if (!detail) {
    return {
      status: 404,
      body: {
        message: "transaction not found",
      },
    } satisfies MockFetchResponse;
  }
  return {
    body: detail,
  } satisfies MockFetchResponse;
}

function jsonResponse({ body, status = 200 }: MockFetchResponse): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => cloneJson(body),
    text: async () => JSON.stringify(body),
  } as Response;
}

function binaryResponse({
  body,
  status = 200,
  headers = {},
}: {
  body: BlobPart;
  status?: number;
  headers?: Record<string, string>;
}): Response {
  const normalizedHeaders = new Map(
    Object.entries(headers).flatMap(([key, value]) => [
      [key, value],
      [key.toLowerCase(), value],
    ]),
  );
  const blobValue = new Blob([body], {
    type:
      headers["Content-Type"] ?? "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

  return {
    ok: status >= 200 && status < 300,
    status,
    headers: {
      get(name: string) {
        return normalizedHeaders.get(name) ?? normalizedHeaders.get(name.toLowerCase()) ?? null;
      },
    } as Headers,
    blob: async () => blobValue,
    text: async () => "",
    json: async () => ({}),
  } as Response;
}

function resolveCostStatisticMonths(
  month: string,
  startMonth?: string | null,
  endMonth?: string | null,
  startDate?: string | null,
  endDate?: string | null,
) {
  const allMonths = Object.keys(costStatisticsProjectRows).sort();
  let resolved = month === "all" ? allMonths : [month];
  const derivedStartMonth = startMonth ?? (startDate ? startDate.slice(0, 7) : null);
  const derivedEndMonth = endMonth ?? (endDate ? endDate.slice(0, 7) : null);
  const normalizedStartMonth =
    derivedStartMonth && derivedEndMonth && derivedStartMonth > derivedEndMonth ? derivedEndMonth : derivedStartMonth;
  const normalizedEndMonth =
    derivedStartMonth && derivedEndMonth && derivedStartMonth > derivedEndMonth ? derivedStartMonth : derivedEndMonth;
  if (normalizedStartMonth) {
    resolved = resolved.filter((item) => item >= normalizedStartMonth);
  }
  if (normalizedEndMonth) {
    resolved = resolved.filter((item) => item <= normalizedEndMonth);
  }
  return resolved;
}

function buildFilteredCostTimeRows({
  month,
  startMonth,
  endMonth,
  startDate,
  endDate,
  projectNames,
  expenseTypes,
  projectScope,
}: {
  month: string;
  startMonth?: string | null;
  endMonth?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  projectNames?: string[];
  expenseTypes?: string[];
  projectScope?: string | null;
}) {
  const projectNameSet = new Set((projectNames ?? []).filter(Boolean));
  const expenseTypeSet = new Set((expenseTypes ?? []).filter(Boolean));
  const normalizedStartDate = startDate && endDate && startDate > endDate ? endDate : startDate;
  const normalizedEndDate = startDate && endDate && startDate > endDate ? startDate : endDate;
  return resolveCostStatisticMonths(month, startMonth, endMonth, startDate, endDate)
    .flatMap((resolvedMonth) =>
      Object.entries(costStatisticsProjectRows[resolvedMonth] ?? {}).flatMap(([resolvedProjectName, rows]) =>
        rows.map((row) => ({
          transaction_id: row.transaction_id,
          trade_time: row.trade_time,
          direction: row.direction,
          project_name: resolvedProjectName,
          expense_type: row.expense_type,
          expense_content: row.expense_content,
          amount: row.amount,
          counterparty_name: row.counterparty_name,
          payment_account_label: row.payment_account_label,
        })),
      ),
    )
    .filter((row) => isCostProjectVisibleForScope(row.project_name, projectScope ?? "active"))
    .filter((row) => (projectNameSet.size > 0 ? projectNameSet.has(row.project_name) : true))
    .filter((row) => (expenseTypeSet.size > 0 ? expenseTypeSet.has(row.expense_type) : true))
    .filter((row) => {
      const tradeDate = row.trade_time.slice(0, 10);
      if (normalizedStartDate && tradeDate < normalizedStartDate) {
        return false;
      }
      if (normalizedEndDate && tradeDate > normalizedEndDate) {
        return false;
      }
      return true;
    })
    .sort((left, right) => right.trade_time.localeCompare(left.trade_time));
}

function buildExpenseTypeExportLabel(expenseTypes?: string[], expenseType?: string | null) {
  const normalized = expenseTypes?.filter(Boolean) ?? [];
  if (normalized.length === 0) {
    return expenseType ?? "未命名费用类型";
  }
  if (normalized.length === 1) {
    return normalized[0];
  }
  return `${normalized[0]}等${normalized.length}类`;
}

function buildCostStatisticsExportFileName(
  month: string,
  view: string,
  projectNames?: string[],
  aggregateBy?: string | null,
  expenseType?: string | null,
  transactionId?: string | null,
  startMonth?: string | null,
  endMonth?: string | null,
  expenseTypes?: string[],
  startDate?: string | null,
  endDate?: string | null,
) {
  const monthLabel =
    startDate && endDate
      ? `${startDate}至${endDate}`
      : startMonth && endMonth
        ? `${startMonth}至${endMonth}`
        : month === "all"
          ? "全部期间"
          : month;
  if (view === "time") {
    return `成本统计_${monthLabel}_按时间统计.xlsx`;
  }
  if (view === "bank_tag") {
    return `成本统计_${monthLabel}_按标签统计.xlsx`;
  }
  if (view === "month") {
    return `成本统计_${monthLabel}_月份汇总.xlsx`;
  }
  if (view === "project") {
    const projectLabel =
      projectNames && projectNames.length > 0
        ? projectNames.length === 1
          ? projectNames[0]
          : `${projectNames[0]}等${projectNames.length}个项目`
        : "未命名项目";
    return `成本统计_${monthLabel}_按项目统计_按${aggregateBy === "year" ? "年" : "月"}_${projectLabel}.xlsx`;
  }
  if (view === "expense_type") {
    return `成本统计_${monthLabel}_按费用类型统计_${buildExpenseTypeExportLabel(expenseTypes, expenseType)}.xlsx`;
  }
  return `成本统计_${monthLabel}_流水详情_${projectNames?.[0] ?? "未命名项目"}_${transactionId ?? "unknown"}.xlsx`;
}

function buildCostStatisticsExportPreviewPayload({
  month,
  view,
  projectNames,
  aggregateBy,
  expenseTypes,
  projectScope,
  startMonth,
  endMonth,
  startDate,
  endDate,
}: {
  month: string;
  view: string;
  projectNames?: string[];
  aggregateBy?: string | null;
  expenseTypes?: string[];
  projectScope?: string | null;
  startMonth?: string | null;
  endMonth?: string | null;
  startDate?: string | null;
  endDate?: string | null;
}) {
  const rows = buildFilteredCostTimeRows({
    month,
    startMonth,
    endMonth,
    startDate,
    endDate,
    projectNames,
    expenseTypes,
    projectScope,
  });
  const bankFlowRows = (view === "time" || view === "bank_tag")
    ? resolveCostStatisticMonths(month, startMonth, endMonth, startDate, endDate)
        .flatMap((resolvedMonth) => (
          buildCostStatisticsExplorerPayload(resolvedMonth, projectScope ?? "active").bank_flow_time_rows
        ))
        .filter((row) => {
          const tradeDate = row.trade_time.slice(0, 10);
          const normalizedStartDate = startDate && endDate && startDate > endDate ? endDate : startDate;
          const normalizedEndDate = startDate && endDate && startDate > endDate ? startDate : endDate;
          return (!normalizedStartDate || tradeDate >= normalizedStartDate)
            && (!normalizedEndDate || tradeDate <= normalizedEndDate);
        })
    : rows;
  const scopeLabel =
    startDate && endDate
      ? `${startDate}至${endDate}`
      : startMonth && endMonth
        ? `${startMonth}至${endMonth}`
        : month === "all"
          ? "全部期间"
          : month;
  if (view === "project") {
    return {
      view,
      file_name: buildCostStatisticsExportFileName(
        month,
        view,
        projectNames,
        aggregateBy,
        null,
        null,
        startMonth,
        endMonth,
        undefined,
        startDate,
        endDate,
      ),
      scope_label: scopeLabel,
      summary: {
        row_count: rows.length,
        transaction_count: rows.length,
        total_amount: sumCostAmounts(rows),
        sheet_count: 8,
      },
      sheet_names: [
        "导出说明",
        "项目汇总",
        "按费用类型汇总",
        "按费用内容汇总",
        "流水明细",
        "OA关联明细",
        "发票关联明细",
        "异常与未闭环",
      ],
      columns: ["时间", "费用类型", "金额", "费用内容", "对方户名", "支付账户"],
      rows: rows.map((row) => [
        row.trade_time,
        row.expense_type,
        row.amount,
        row.expense_content,
        row.counterparty_name,
        row.payment_account_label,
      ]),
    };
  }
  if (view === "expense_type") {
    return {
      view,
      file_name: buildCostStatisticsExportFileName(
        month,
        view,
        undefined,
        null,
        expenseTypes?.[0] ?? null,
        null,
        startMonth,
        endMonth,
        expenseTypes,
        startDate,
        endDate,
      ),
      scope_label: scopeLabel,
      summary: {
        row_count: rows.length,
        transaction_count: rows.length,
        total_amount: sumCostAmounts(rows),
        sheet_count: 1,
      },
      sheet_names: ["按费用类型统计"],
      columns: ["时间", "项目名称", "金额", "费用内容", "对方户名", "支付账户"],
      rows: rows.map((row) => [
        row.trade_time,
        row.project_name,
        row.amount,
        row.expense_content,
        row.counterparty_name,
        row.payment_account_label,
      ]),
    };
  }
  return {
    view,
    file_name: buildCostStatisticsExportFileName(month, view, undefined, null, null, null, startMonth, endMonth, undefined, startDate, endDate),
    scope_label: scopeLabel,
    summary: {
      row_count: bankFlowRows.length,
      transaction_count: bankFlowRows.length,
      total_amount: sumCostAmounts(bankFlowRows),
      expense_amount: sumCostAmounts(bankFlowRows.filter((row) => row.direction === "支出")),
      income_amount: sumCostAmounts(bankFlowRows.filter((row) => row.direction === "收入")),
      expense_transaction_count: bankFlowRows.filter((row) => row.direction === "支出").length,
      income_transaction_count: bankFlowRows.filter((row) => row.direction === "收入").length,
      sheet_count: 1,
    },
    sheet_names: [view === "bank_tag" ? "按标签统计" : "按时间统计"],
    columns: ["时间", "项目名称", "费用类型", "金额", "费用内容", "对方户名", "支付账户"],
    rows: bankFlowRows.map((row) => [
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

function isBinaryLikeResponse(value: MockFetchResult): value is Response {
  return (
    typeof value === "object" &&
    value !== null &&
    "blob" in value &&
    typeof value.blob === "function" &&
    "headers" in value
  );
}

export function installMockApiFetch(options: MockApiOptions = {}) {
  let costExplorerFailuresRemaining = Math.max(0, options.costExplorerFailuresBeforeSuccess ?? 0);
  let costDetailFailuresRemaining = Math.max(0, options.costDetailFailuresBeforeSuccess ?? 0);
  let latestImportSession = buildImportPreviewPayload(
    options.initialImportPreviewFileNames ?? [],
    options.initialImportPreviewOverrides ?? [],
  );
  const etcInvoiceStore = createEtcInvoiceStore(options);
  const etcReconciliationTaskStore = createEtcReconciliationTaskStore();
  const turnoverExtraStore = new Map<string, Record<string, unknown>>();
  let latestEtcImportPreview = etcInvoiceStore.previewZip([]);
  let bankDetailAutoTagRulesSaved = false;
  let bankDetailManualAssignmentActive = Boolean(options.bankDetailManualAssignmentActive);
  let workbenchWriteActionCount = 0;
  const workbenchStateStore = createWorkbenchStateStore(options);
  const ignoredRowStore = createIgnoredRowStore();
  const taxOffsetStateStore = createTaxOffsetStateStore();
  let latestTaxCertifiedPreview: {
    session: {
      id: string;
      imported_by: string;
      file_count: number;
      status: string;
    };
    files: Array<{
      id: string;
      file_name: string;
      month: string;
      recognized_count: number;
      invalid_count: number;
      matched_plan_count: number;
      outside_plan_count: number;
      rows: ReturnType<typeof buildMockCertifiedPreviewRows>;
    }>;
    summary: {
      recognized_count: number;
      invalid_count: number;
      matched_plan_count: number;
      outside_plan_count: number;
    };
  } | null = null;
  let workbenchSettingsState = {
    projects: {
      active: [
        {
          id: "proj-001",
          project_code: "YN-001",
          project_name: "云南溯源科技",
          project_status: "active" as const,
          source: "oa" as const,
          department_name: "财务部",
          owner_name: "赵华",
        },
        {
          id: "proj-002",
          project_code: "KM-002",
          project_name: "昆明卷烟厂动力设备控制系统升级改造项目",
          project_status: "active" as const,
          source: "oa" as const,
          department_name: "项目部",
          owner_name: "王青",
        },
      ],
      completed: [
        {
          id: "proj-003",
          project_code: "ZT-003",
          project_name: "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
          project_status: "completed" as const,
          source: "oa" as const,
          department_name: "项目部",
          owner_name: "刘宁",
        },
      ],
      completed_project_ids: ["proj-003"],
    },
    bank_account_mappings: [
      {
        id: "bank_mapping_8826",
        last4: "8826",
        bank_name: "建设银行",
        short_name: "建行",
      },
    ],
    workbench_column_layouts: {
      oa: options.workbenchColumnLayouts?.oa ?? ["applicant", "projectName", "amount", "counterparty", "reason"],
      bank: options.workbenchColumnLayouts?.bank ?? ["counterparty", "amount", "loanRepaymentDate", "note"],
      invoice: options.workbenchColumnLayouts?.invoice ?? ["sellerName", "buyerName", "issueDate", "amount", "grossAmount"],
    },
    oa_retention: {
      cutoff_date: "2026-01-01",
    },
    oa_import: {
      form_types: ["payment_request", "expense_claim"],
      statuses: ["completed"],
      attachment_invoice_promotion_mode: "link_existing_only",
      available_form_types: [
        { value: "payment_request", label: "支付申请" },
        { value: "expense_claim", label: "日常报销" },
      ],
      available_statuses: [
        { value: "completed", label: "已完成" },
        { value: "in_progress", label: "进行中" },
      ],
    },
    oa_invoice_offset: {
      applicant_names: ["周洁莹"],
    },
  };
  let workbenchAccessControlState = {
    version: 1,
    administrator: {
      username: "YNSYLP005",
      access_tier: "admin" as const,
      protected: true as const,
    },
    accounts: [] as Array<{
      username: string;
      access_tier: "full_access" | "read_export_only";
    }>,
  };
  let oaApplicantCredentialsState = [
    {
      targetApplicantCode: "chen_xiuyun",
      targetApplicantName: "陈秀云",
      oaUsername: "chen_xiuyun",
      credentialStatus: "configured",
      hasCredential: true,
      enabled: true,
    },
  ];

  const dataResetJobs = new Map<string, Record<string, unknown>>();
  let backgroundJobs = cloneJson(options.backgroundJobs ?? []);
  let workbenchOaSyncStatusIndex = 0;
  let appHealthDashboardIndex = 0;

  const handlers: Record<string, MockFetchHandler> = {
    "/api/session/me": () => {
      if (options.sessionMode === "expired") {
        return {
          status: 401,
          body: {
            error: "invalid_oa_session",
            message: "请返回 OA 系统重新登录后再进入财务运营平台。",
          },
        };
      }
      if (options.sessionMode === "error") {
        return {
          status: 500,
          body: {
            error: "oa_identity_lookup_failed",
            message: "会话校验失败，请稍后重试。",
          },
        };
      }
      const accessTier = options.sessionMode === "forbidden"
        ? "denied"
        : options.sessionAccessTier ?? "full_access";
      const allowed = accessTier !== "denied";
      return {
        body: {
          user: {
            user_id: "101",
            username: options.sessionUsername ?? (allowed ? "liuji" : "YNSYLP006"),
            nickname: options.sessionDisplayName ?? (allowed ? "刘际涛" : "权限攻击样例"),
            display_name: options.sessionDisplayName ?? (allowed ? "刘际涛" : "权限攻击样例"),
            dept_id: "88",
            dept_name: "财务部",
            avatar: null,
          },
          roles: allowed ? ["finance"] : ["finance", "business", "finops_full_access"],
          permissions: ["finops:app:view"],
          allowed,
          access_tier: accessTier,
          can_access_app: allowed,
          can_mutate_data: accessTier === "admin" || accessTier === "full_access",
          can_admin_access: accessTier === "admin",
        },
      };
    },
    "/imports/templates": () => ({
      body: {
        templates: templateRegistry,
      },
    }),
    "/api/operation-barrier/status": async () => {
      if (options.operationBarrierDelay) {
        await options.operationBarrierDelay;
      }
      return {
        body: options.operationBarrierStatus ?? {
          status: "fresh",
          fresh: true,
          targets: [],
          blocked_targets: [],
          refreshing_targets: [],
        },
      };
    },
    "/api/workbench": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.workbenchErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "workbench failed" } };
      }
      const mappedPayload = toGroupedWorkbenchPayload(
        mockWorkbenchPayloadForMonth(workbenchStateStore, month, options),
      );
      const payload = options.transformWorkbenchPayload
        ? options.transformWorkbenchPayload(cloneJson(mappedPayload)) as typeof mappedPayload
        : mappedPayload;
      const pageForZone = (zone: "paired" | "unpaired") => {
        const query = parseWorkbenchGroupJsonParam(url.searchParams.get(`${zone}_query`));
        const groups = sortMockWorkbenchGroups(
          payload[zone].groups.filter((group) => mockWorkbenchGroupMatchesQuery(
            group,
            String(query.search ?? "").trim(),
            parseWorkbenchGroupJsonParam(JSON.stringify(query.column_filters ?? {})),
            parseWorkbenchGroupJsonParam(JSON.stringify(query.time_filters ?? {})),
          )),
          String(query.sort ?? "").trim(),
        );
        return {
          month: payload.month,
          zone,
          page: 1,
          page_size: 200,
          total: groups.length,
          row_counts: countMockWorkbenchRows(groups),
          has_more: groups.length > 200,
          next_cursor: groups.length > 200 ? "mock-workbench-group:200" : null,
          groups: groups.slice(0, 200),
        };
      };
      return {
        body: {
          ...payload,
          paired: pageForZone("paired"),
          unpaired: pageForZone("unpaired"),
        },
      };
    },
    "/api/workbench/groups": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.workbenchErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "workbench groups failed" } };
      }
      const zone = url.searchParams.get("zone") === "paired" ? "paired" : "unpaired";
      const pageSize = Math.max(1, Number(url.searchParams.get("page_size") ?? "50") || 50);
      const cursorPrefix = "mock-workbench-group:";
      const offset = parseMockWorkbenchCursor(url.searchParams.get("cursor"), cursorPrefix);
      const mappedPayload = toGroupedWorkbenchPayload(mockWorkbenchPayloadForMonth(workbenchStateStore, month, options));
      const payload = options.transformWorkbenchPayload
        ? options.transformWorkbenchPayload(cloneJson(mappedPayload)) as typeof mappedPayload
        : mappedPayload;
      const search = String(url.searchParams.get("search") ?? "").trim();
      const sort = String(url.searchParams.get("sort") ?? "").trim();
      const columnFilters = parseWorkbenchGroupJsonParam(url.searchParams.get("column_filters"));
      const timeFilters = parseWorkbenchGroupJsonParam(url.searchParams.get("time_filters"));
      const exceptionBucket = url.searchParams.get("exception_bucket");
      const groups = sortMockWorkbenchGroups(
        payload[zone].groups.filter((group) => (
          mockWorkbenchGroupMatchesQuery(group, search, columnFilters, timeFilters)
          && (
            exceptionBucket === "active"
              ? (group as { oa_invoice_anomaly?: { state?: string } }).oa_invoice_anomaly?.state === "active"
              : exceptionBucket === "processed"
                ? (group as { oa_invoice_anomaly?: { state?: string } }).oa_invoice_anomaly?.state === "ignored"
                : true
          )
        )),
        sort,
      );
      const rowCounts = countMockWorkbenchRows(groups);
      return {
        body: {
          groups: groups.slice(offset, offset + pageSize),
          total: groups.length,
          row_counts: rowCounts,
          page_size: pageSize,
          has_more: offset + pageSize < groups.length,
          next_cursor: nextMockWorkbenchCursor(cursorPrefix, offset, pageSize, groups.length),
        },
      };
    },
    "/api/workbench/groups/detail": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.workbenchErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "workbench group detail failed" } };
      }
      const zone = url.searchParams.get("zone") === "paired" ? "paired" : "unpaired";
      const groupId = url.searchParams.get("group_id") ?? "";
      const mappedPayload = toGroupedWorkbenchPayload(mockWorkbenchPayloadForMonth(workbenchStateStore, month, options));
      const payload = options.transformWorkbenchPayload
        ? options.transformWorkbenchPayload(cloneJson(mappedPayload)) as typeof mappedPayload
        : mappedPayload;
      const group = payload[zone].groups.find((candidate) => candidate.group_id === groupId);
      if (!group) {
        return { status: 404, body: { message: "workbench group detail not found" } };
      }
      const collapsedRowCounts = group.collapsed_row_counts ?? {
        oa: group.oa_rows.length,
        bank: group.bank_rows.length,
        invoice: group.invoice_rows.length,
      };
      const expandPaneRows = <T extends { id: string }>(rows: T[], expectedCount: number) => {
        if (rows.length === 0 || rows.length >= expectedCount) {
          return rows;
        }
        return Array.from({ length: expectedCount }, (_, index) => (
          index < rows.length
            ? rows[index]
            : { ...rows[index % rows.length], id: `${rows[index % rows.length].id}-detail-${index + 1}` }
        ));
      };
      const paneRows = {
        oa: expandPaneRows(
          group.collapsed_rows?.oa ?? group.oa_rows,
          collapsedRowCounts.oa,
        ),
        bank: expandPaneRows(
          group.collapsed_rows?.bank ?? group.bank_rows,
          collapsedRowCounts.bank,
        ),
        invoice: expandPaneRows(
          group.collapsed_rows?.invoice ?? group.invoice_rows,
          collapsedRowCounts.invoice,
        ),
      };
      return {
        body: {
          group: {
            ...group,
            oa_rows: paneRows.oa,
            bank_rows: paneRows.bank,
            invoice_rows: paneRows.invoice,
            row_counts: collapsedRowCounts,
            collapsed_rows: paneRows,
            collapsed_row_counts: collapsedRowCounts,
          },
        },
      };
    },
    "/api/workbench/filter-options": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      const zone = url.searchParams.get("zone") === "paired" ? "paired" : "unpaired";
      const pane = MOCK_WORKBENCH_PANES.includes(url.searchParams.get("pane") as RawWorkbenchPaneKey)
        ? url.searchParams.get("pane") as RawWorkbenchPaneKey
        : "oa";
      const facet = url.searchParams.get("facet") === "time_year" ? "time_year" : "column";
      const column = String(url.searchParams.get("column") ?? "").trim();
      const pageSize = Math.max(1, Number(url.searchParams.get("page_size") ?? "100") || 100);
      const cursorPrefix = "mock-workbench-option:";
      const offset = parseMockWorkbenchCursor(url.searchParams.get("cursor"), cursorPrefix);
      const payload = toGroupedWorkbenchPayload(mockWorkbenchPayloadForMonth(workbenchStateStore, month, options));
      const columnFilters = parseWorkbenchGroupJsonParam(url.searchParams.get("column_filters"));
      const timeFilters = parseWorkbenchGroupJsonParam(url.searchParams.get("time_filters"));
      if (facet === "column") {
        const paneFilters = objectValue(columnFilters[pane]);
        delete paneFilters[column];
        if (Object.keys(paneFilters).length > 0) columnFilters[pane] = paneFilters;
        else delete columnFilters[pane];
      } else {
        delete timeFilters[pane];
      }
      const groups = payload[zone].groups.filter((group) => mockWorkbenchGroupMatchesQuery(
        group,
        String(url.searchParams.get("search") ?? "").trim(),
        columnFilters,
        timeFilters,
      ));
      const values = new Map<string, { value: string; label: string; missing: boolean }>();
      groups.forEach((group) => {
        groupRowsForMockPane(group, pane)
          .filter((row) => mockWorkbenchRowMatchesPaneFilters(row, pane, columnFilters[pane], timeFilters[pane]))
          .forEach((row) => {
            const rawValues = facet === "time_year"
              ? [String(mockWorkbenchTimeValue(row, pane) ?? "").slice(0, 4)].filter((value) => /^\d{4}$/.test(value))
              : mockWorkbenchColumnValues(row, pane, column);
            const normalizedValues = rawValues.length > 0 ? rawValues : ["__workbench_missing__"];
            normalizedValues.forEach((value) => values.set(value, {
              value,
              label: value === "__workbench_missing__" ? "未填写" : value,
              missing: value === "__workbench_missing__",
            }));
          });
      });
      const optionSearch = normalizeMockWorkbenchText(url.searchParams.get("option_search") ?? "");
      const optionsList = Array.from(values.values())
        .filter((option) => !optionSearch || normalizeMockWorkbenchText(option.label).includes(optionSearch))
        .sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
      return {
        body: {
          options: optionsList.slice(offset, offset + pageSize),
          page_size: pageSize,
          has_more: offset + pageSize < optionsList.length,
          next_cursor: nextMockWorkbenchCursor(cursorPrefix, offset, pageSize, optionsList.length),
        },
      };
    },
    "/api/oa-sync/status": () => {
      const statuses = options.workbenchOaSyncStatuses;
      if (statuses && statuses.length > 0) {
        const status = statuses[Math.min(workbenchOaSyncStatusIndex, statuses.length - 1)];
        workbenchOaSyncStatusIndex += 1;
        return { body: cloneJson(status) };
      }
      return {
        body: {
          status: "synced",
          message: "OA 已同步",
          dirty_scopes: [],
          last_seen_change_at: null,
          last_synced_at: "2026-04-01T12:00:00+08:00",
          lag_seconds: 0,
          failed_event_count: 0,
          version: 0,
        },
      };
    },
    "/api/app-health": () => {
      if (options.appHealthErrorStatus) {
        return {
          status: options.appHealthErrorStatus,
          body: options.appHealthErrorBody ?? { message: "app health failed" },
        };
      }
      const queued = backgroundJobs.filter((job) => String(job.status) === "queued").length;
      const running = backgroundJobs.filter((job) => String(job.status) === "running").length;
      const attention = backgroundJobs.filter((job) => String(job.status) === "failed" || String(job.status) === "partial_success").length;
      return {
        body: options.appHealth ?? {
          status: "ok",
          generated_at: "2026-05-06T00:00:00+08:00",
          session: { status: "authenticated" },
          oa_sync: {
            status: "synced",
            message: "OA 已同步",
            dirty_scopes: [],
          },
          workbench_matching: {
            status: "ready",
            dirty_scopes: [],
            stale_scopes: [],
            rebuilding_scopes: [],
          },
          background_jobs: {
            active: backgroundJobs.length,
            queued,
            running,
            attention,
          },
          dependencies: {},
        },
      };
    },
    "/api/operations/app-health-dashboard": () => {
      if (options.appHealthDashboardSequence && options.appHealthDashboardSequence.length > 0) {
        const item = options.appHealthDashboardSequence[
          Math.min(appHealthDashboardIndex, options.appHealthDashboardSequence.length - 1)
        ];
        appHealthDashboardIndex += 1;
        return {
          status: item.status,
          body: item.body,
        };
      }
      if (options.appHealthDashboardErrorStatus) {
        return {
          status: options.appHealthDashboardErrorStatus,
          body: options.appHealthDashboardErrorBody ?? { message: "app health dashboard failed" },
        };
      }
      return {
        body: options.appHealthDashboard ?? {
          generated_at: "2026-05-23T10:00:00+08:00",
          data_inventory: {
            bank: {
              total_count: 128,
              latest_synced_at: "2026-05-23T09:50:00+08:00",
              status: "available",
              sources: [
                {
                  key: "bank_transactions",
                  label: "银行流水",
                  count: 128,
                  latest_synced_at: "2026-05-23T09:50:00+08:00",
                  status: "available",
                },
              ],
            },
            invoice: {
              total_count: 256,
              latest_synced_at: "2026-05-23T09:48:00+08:00",
              status: "available",
              sources: [
                { key: "manual", label: "手工导入", count: 251, latest_synced_at: "2026-05-23T09:44:00+08:00", status: "available" },
                { key: "input_invoice", label: "进项发票", count: 236, latest_synced_at: "2026-05-23T09:46:00+08:00", status: "available" },
                { key: "output_invoice", label: "销项发票", count: 20, latest_synced_at: "2026-05-23T09:42:00+08:00", status: "available" },
                { key: "oa_attachment", label: "OA 解析", count: 40, supplementary_count: 5, latest_synced_at: "2026-05-23T09:48:00+08:00", status: "available" },
              ],
            },
            oa: {
              total_count: 72,
              latest_synced_at: "2026-05-23T09:45:00+08:00",
              status: "available",
              sources: [
                { key: "oa_records", label: "单据", count: 72, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                { key: "oa_records_completed", label: "已完成 OA", count: 61, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                { key: "oa_records_in_progress", label: "进行中 OA", count: 11, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
                { key: "oa_items", label: "明细", count: 316, latest_synced_at: "2026-05-23T09:45:00+08:00", status: "available" },
              ],
            },
            import_events: [
              {
                key: "bank-5",
                source_key: "bank_transactions",
                label: "流水导入",
                source_name: "bank-5.xlsx",
                imported_by: "admin.ops",
                count: 42,
                supplementary_count: null,
                imported_at: "2026-05-23T09:58:00+08:00",
                status: "succeeded",
              },
              {
                key: "invoice-4",
                source_key: "manual",
                label: "手工导入",
                source_name: "invoice-4.xlsx",
                imported_by: "admin.ops",
                count: 18,
                supplementary_count: null,
                imported_at: "2026-05-23T09:54:00+08:00",
                status: "succeeded",
              },
              {
                key: "bank-4",
                source_key: "bank_transactions",
                label: "流水导入",
                source_name: "bank-4.xlsx",
                imported_by: "admin.ops",
                count: 16,
                supplementary_count: null,
                imported_at: "2026-05-23T09:40:00+08:00",
                status: "succeeded",
              },
              {
                key: "invoice-3",
                source_key: "manual",
                label: "手工导入",
                source_name: "invoice-3.xlsx",
                imported_by: "admin.ops",
                count: 12,
                supplementary_count: null,
                imported_at: "2026-05-23T09:30:00+08:00",
                status: "succeeded",
              },
              {
                key: "bank-3",
                source_key: "bank_transactions",
                label: "流水导入",
                source_name: "bank-3.xlsx",
                imported_by: "admin.ops",
                count: 10,
                supplementary_count: null,
                imported_at: "2026-05-23T09:25:00+08:00",
                status: "succeeded",
              },
              {
                key: "bank-6",
                source_key: "bank_transactions",
                label: "流水导入",
                source_name: "bank-6.xlsx",
                imported_by: "admin.ops",
                count: 8,
                supplementary_count: null,
                imported_at: "2026-05-23T09:20:00+08:00",
                status: "succeeded",
              },
            ],
          },
          request_performance: {
            window: { type: "process_rolling_window", sample_limit_per_endpoint: 512, reset_on_restart: true },
            endpoints: [
              {
                endpoint: "GET /api/workbench",
                sample_count: 12,
                last_status_code: 200,
                duration_ms: { p50: 120, p95: 640, p99: 880 },
                database_duration_ms: { p50: 40, p95: 260, p99: 330 },
                connection_acquire_ms: { p50: 2, p95: 8, p99: 10 },
                sql_execute_fetch_ms: { p50: 36, p95: 240, p99: 300 },
                database_query_count: { p50: 4, p95: 8, p99: 10 },
              },
            ],
          },
          runtime_performance: {
            outbox: {
              pending_count: 3,
              publishing_count: 1,
              failed_count: 0,
              publish_failed_count: 0,
              oldest_pending_age_seconds: 42,
              status: "available",
            },
            queues: [
              {
                event_type: "workbench_relation.read_model.refresh",
                queue: "finops.workbench_relation.read_model.refresh",
                messages: 2,
                unacked: 1,
                consumers: 1,
                dlq_messages: 0,
                status: "available",
              },
            ],
            read_models: [
              {
                key: "workbench_relation",
                refresh_duration_ms: { p50: 110, p95: 450, p99: 700 },
                stale_count: 1,
                unavailable_count: 0,
                status: "available",
              },
            ],
            workers: [
              { worker_kind: "runtime-worker", heartbeat_lag_seconds: 8, status: "available" },
            ],
          },
          freshness: { warnings: [] },
        },
      };
    },
    "/api/operations/history": () => ({
      body: {
        rows: [
          {
            operation_key: "request:request-1",
            actor_id: "005",
            actor_name: "权限管理员",
            actor_account: "YNSYLP005",
            page_key: "reconciliation-workbench",
            action_label: "确认关联",
            object_type: "reconciliation_case",
            started_at: "2026-08-09T12:00:00+08:00",
            completed_at: "2026-08-09T12:00:01+08:00",
            occurred_at: "2026-08-09T12:00:00+08:00",
            outcome: "success",
          },
        ],
        next_cursor: null,
        limit: 50,
      },
    }),
    "/api/operations/import-history": () => ({
      body: {
        rows: [{
          key: "bank-6",
          source_key: "bank_transactions",
          label: "流水导入",
          source_name: "bank-6.xlsx",
          imported_by: "admin.ops",
          count: 8,
          supplementary_count: null,
          imported_at: "2026-05-23T09:20:00+08:00",
          status: "succeeded",
        }],
        pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 },
      },
    }),
    "/api/operations/history/actors": () => ({
      body: { rows: [{ actor_id: "005", actor_name: "权限管理员", actor_account: "YNSYLP005" }] },
    }),
    "/api/operations/app-health/page-audit": ({ url }) => {
      const pageKey = url.searchParams.get("page") ?? "";
      if (pageKey === "app-health-operations" && options.appHealthSystemAuditStatus) {
        return {
          status: options.appHealthSystemAuditStatus,
          body: options.appHealthSystemAuditBody ?? { message: "system audit failed" },
        };
      }
      if (pageKey === "app-health-operations") {
        return {
          body: options.appHealthSystemAudit ?? {
            mode: "app-health-system-audit",
            tenant_id: "default",
            page_key: pageKey,
            generated_at: "2026-05-23T10:01:00+08:00",
            overall_status: "pass",
            audit_status: { integrity: "pass", freshness: "fresh", queue: "drained", external: "unknown" },
            audit_contract: {
              database_snapshot: true,
              snapshot_consistency: "repeatable_read_read_only",
              proof_availability: "ready",
              contract_revision: "page-audit-contract.v22",
            },
            summary: {
              registered_page_count: 18,
              audited_business_page_count: 16,
              passed_business_page_count: 16,
              database_internal_contracts: "pass",
              end_to_end_source_truth: "unproven",
              blocking_issue_sample_count: 0,
              issue_sample_count: 0,
              error_sample_count: 0,
              warning_sample_count: 0,
              issue_sample_counts_by_code: {},
            },
            issues: [],
            database_system_snapshot: {
              system_audit_id: "system-audit:test-fixture",
              snapshot_identity: "100:100:",
              snapshot_generated_at: "2026-05-23T10:01:00+08:00",
              snapshot_consistency: "repeatable_read_read_only",
              database_snapshot: true,
              evidence_fingerprint: "test-fixture",
              page_results: [],
            },
            runtime_observation: {
              observed_at: "2026-05-23T10:01:00+08:00",
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
          },
        };
      }
      return { body: {
        mode: "page-business-read-model-audit",
        page_key: pageKey,
        overall_status: "pass",
        audit_status: { integrity: "pass", freshness: "fresh", queue: "drained" },
        audit_contract: {
          database_snapshot: true,
          snapshot_consistency: "repeatable_read_read_only",
          proof_availability: "ready",
          contract_revision: "page-audit-contract.v9",
          ...(["cost-statistics", "reconciliation-workbench"].includes(pageKey)
            ? { registered_read_model_keys: [] }
            : {}),
        },
        summary: {
          blocking_issue_sample_count: 0,
          issue_sample_count: 0,
        },
        issues: [],
      } };
    },
    "/api/background-jobs/active": () => ({
      body: {
        jobs: cloneJson(backgroundJobs),
      },
    }),
    "/api/workbench/ignored": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      return {
        body: {
          month,
          rows: cloneJson(ignoredRowStore.get(month)),
        },
      };
    },
    "/api/workbench/settings": ({ init, jsonBody }) => {
      if ((init?.method ?? "GET").toUpperCase() === "POST" && jsonBody) {
        const forbiddenAclKeys = [
          "access_control",
          "allowed_usernames",
          "readonly_export_usernames",
          "admin_usernames",
          "full_access_usernames",
          "access_control_version",
        ];
        if (forbiddenAclKeys.some((key) => Object.prototype.hasOwnProperty.call(jsonBody, key))) {
          return {
            ok: false,
            status: 400,
            body: {
              error: "access_control_write_forbidden",
              message: "Access control can only be changed through the administrator access-control API.",
            },
          };
        }
        const completedProjectIds = Array.isArray(jsonBody.completed_project_ids)
          ? (jsonBody.completed_project_ids as string[])
          : workbenchSettingsState.projects.completed_project_ids;
        const bankAccountMappings = Array.isArray(jsonBody.bank_account_mappings)
          ? (jsonBody.bank_account_mappings as Array<{ id?: string; last4?: string; bank_name?: string; bankName?: string; short_name?: string; shortName?: string }>)
          : workbenchSettingsState.bank_account_mappings;
        workbenchSettingsState = {
          projects: {
            ...workbenchSettingsState.projects,
            completed_project_ids: completedProjectIds,
          },
          bank_account_mappings: bankAccountMappings.map((item) => ({
            id: item.id ?? `bank_mapping_${item.last4 ?? "0000"}`,
            last4: item.last4 ?? "0000",
            bank_name: item.bank_name ?? item.bankName ?? "未识别银行",
            short_name: item.short_name ?? item.shortName ?? "",
          })),
          workbench_column_layouts:
            jsonBody.workbench_column_layouts && typeof jsonBody.workbench_column_layouts === "object"
              ? {
                oa: Array.isArray((jsonBody.workbench_column_layouts as Record<string, unknown>).oa)
                  ? ((jsonBody.workbench_column_layouts as Record<string, unknown>).oa as string[]).map((item) => String(item))
                  : workbenchSettingsState.workbench_column_layouts.oa,
                bank: Array.isArray((jsonBody.workbench_column_layouts as Record<string, unknown>).bank)
                  ? ((jsonBody.workbench_column_layouts as Record<string, unknown>).bank as string[]).map((item) => String(item))
                  : workbenchSettingsState.workbench_column_layouts.bank,
                invoice: Array.isArray((jsonBody.workbench_column_layouts as Record<string, unknown>).invoice)
                  ? ((jsonBody.workbench_column_layouts as Record<string, unknown>).invoice as string[]).map((item) => String(item))
                  : workbenchSettingsState.workbench_column_layouts.invoice,
              }
              : workbenchSettingsState.workbench_column_layouts,
          oa_retention:
            jsonBody.oa_retention && typeof jsonBody.oa_retention === "object"
              ? {
                cutoff_date: String((jsonBody.oa_retention as Record<string, unknown>).cutoff_date || "2026-01-01"),
              }
              : workbenchSettingsState.oa_retention,
          oa_import:
            jsonBody.oa_import && typeof jsonBody.oa_import === "object"
              ? {
                ...workbenchSettingsState.oa_import,
                form_types: Array.isArray((jsonBody.oa_import as Record<string, unknown>).form_types)
                  ? ((jsonBody.oa_import as Record<string, unknown>).form_types as unknown[])
                    .map((item) => String(item).trim())
                    .filter(Boolean)
                  : workbenchSettingsState.oa_import.form_types,
                statuses: Array.isArray((jsonBody.oa_import as Record<string, unknown>).statuses)
                  ? ((jsonBody.oa_import as Record<string, unknown>).statuses as unknown[])
                    .map((item) => String(item).trim())
                    .filter(Boolean)
                  : workbenchSettingsState.oa_import.statuses,
                attachment_invoice_promotion_mode:
                  typeof (jsonBody.oa_import as Record<string, unknown>).attachment_invoice_promotion_mode === "string"
                    ? String((jsonBody.oa_import as Record<string, unknown>).attachment_invoice_promotion_mode).trim()
                    : workbenchSettingsState.oa_import.attachment_invoice_promotion_mode,
              }
              : workbenchSettingsState.oa_import,
          oa_invoice_offset:
            jsonBody.oa_invoice_offset && typeof jsonBody.oa_invoice_offset === "object"
              ? {
                applicant_names: Array.isArray((jsonBody.oa_invoice_offset as Record<string, unknown>).applicant_names)
                  ? ((jsonBody.oa_invoice_offset as Record<string, unknown>).applicant_names as unknown[])
                    .map((item) => String(item).trim())
                    .filter(Boolean)
                  : workbenchSettingsState.oa_invoice_offset.applicant_names,
              }
              : workbenchSettingsState.oa_invoice_offset,
        };
      }
      return { body: cloneJson(workbenchSettingsState) };
    },
    "/api/workbench/settings/access-control": ({ init, jsonBody }) => {
      if (options.sessionAccessTier !== "admin") {
        return {
          ok: false,
          status: 403,
          body: { error: "forbidden", message: "当前账号无权执行此操作。" },
        };
      }
      if ((init?.method ?? "GET").toUpperCase() === "PUT") {
        const expectedVersion = jsonBody?.expected_version;
        const accounts = jsonBody?.accounts;
        if (expectedVersion !== workbenchAccessControlState.version) {
          return {
            ok: false,
            status: 409,
            body: {
              error: "access_control_version_conflict",
              message: "Access control version conflict.",
              current_version: workbenchAccessControlState.version,
            },
          };
        }
        if (!Array.isArray(accounts)) {
          return {
            ok: false,
            status: 400,
            body: { error: "invalid_access_control_request", message: "accounts must be an array." },
          };
        }
        const normalizedAccounts = accounts.map((account) => ({
          username: String((account as Record<string, unknown>).username ?? "").trim(),
          access_tier: String((account as Record<string, unknown>).access_tier ?? ""),
        }));
        const invalid = normalizedAccounts.some((account) =>
          !account.username
          || account.username === "YNSYLP005"
          || !["full_access", "read_export_only"].includes(account.access_tier),
        ) || new Set(normalizedAccounts.map((account) => account.username)).size !== normalizedAccounts.length;
        if (invalid) {
          return {
            ok: false,
            status: 400,
            body: { error: "invalid_access_control_request", message: "Invalid access-control accounts." },
          };
        }
        const nextAccounts = normalizedAccounts as typeof workbenchAccessControlState.accounts;
        const changed = JSON.stringify(nextAccounts) !== JSON.stringify(workbenchAccessControlState.accounts);
        if (changed) {
          workbenchAccessControlState = {
            ...workbenchAccessControlState,
            version: workbenchAccessControlState.version + 1,
            accounts: nextAccounts,
          };
        }
      }
      return { body: cloneJson(workbenchAccessControlState) };
    },
    "/api/workbench/settings/oa-applicant-credentials": () => ({
      body: {
        credentials: cloneJson(oaApplicantCredentialsState),
      },
    }),
    "/api/workbench/settings/projects/sync": () => {
      if (!workbenchSettingsState.projects.active.some((project) => project.id === "proj-oa-sync-001")) {
        workbenchSettingsState = {
          ...workbenchSettingsState,
          projects: {
            ...workbenchSettingsState.projects,
            active: [
              ...workbenchSettingsState.projects.active,
              {
                id: "proj-oa-sync-001",
                project_code: "OA-SYNC-001",
                project_name: "OA 同步新增项目",
                project_status: "active" as const,
                source: "oa" as const,
                department_name: "项目部",
                owner_name: "OA项目经理",
              },
            ],
          },
        };
      }
      return {
        body: {
          sync: {
            id: "mock-project-sync",
            status: "completed",
          },
          settings: cloneJson(workbenchSettingsState),
        },
      };
    },
    "/api/workbench/settings/projects": ({ jsonBody }) => {
      const projectCode = String(jsonBody?.project_code ?? "").trim();
      const projectName = String(jsonBody?.project_name ?? "").trim();
      const projectId = projectCode === "LOCAL-001" ? "proj_manual_local_001" : `proj_manual_${projectCode || "new"}`;
      workbenchSettingsState = {
        ...workbenchSettingsState,
        projects: {
          ...workbenchSettingsState.projects,
          active: [
            ...workbenchSettingsState.projects.active.filter((project) => project.id !== projectId),
            {
              id: projectId,
              project_code: projectCode,
              project_name: projectName,
              project_status: "active" as const,
              source: "manual" as const,
              department_name: null,
              owner_name: null,
            },
          ],
        },
      };
      return {
        body: {
          settings: cloneJson(workbenchSettingsState),
        },
      };
    },
    "/api/tax-offset": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.taxErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "tax failed" } };
      }
      const payload = taxOffsetStateStore.get(month) as Record<string, unknown>;
      payload.canonical_snapshot_version = payload.canonical_snapshot_version ?? `mock-tax-offset:${month}`;
      return { body: payload };
    },
    "/api/tax-offset/certified-import/preview": ({ formData }) => {
      const files = formData ? formData.getAll("files").filter((item): item is File => item instanceof File) : [];
      const importedBy = formData?.get("imported_by");
      latestTaxCertifiedPreview = {
        session: {
          id: "tax-certified-session-0001",
          imported_by: typeof importedBy === "string" && importedBy.trim().length > 0 ? importedBy : "system",
          file_count: files.length,
          status: "preview_ready",
        },
        files: files.map((file, index) => {
          const preview = resolveMockCertifiedPreview(file.name);
          return {
            id: `tax-certified-file-${String(index + 1).padStart(4, "0")}`,
            file_name: file.name,
            month: preview.month,
            recognized_count: preview.recognizedCount,
            invalid_count: preview.invalidCount,
            matched_plan_count: preview.matchedPlanCount,
            outside_plan_count: preview.outsidePlanCount,
            rows: preview.rows,
          };
        }),
        summary: {
          recognized_count: files.reduce((sum, file) => sum + resolveMockCertifiedPreview(file.name).recognizedCount, 0),
          invalid_count: files.reduce((sum, file) => sum + resolveMockCertifiedPreview(file.name).invalidCount, 0),
          matched_plan_count: files.reduce((sum, file) => sum + resolveMockCertifiedPreview(file.name).matchedPlanCount, 0),
          outside_plan_count: files.reduce((sum, file) => sum + resolveMockCertifiedPreview(file.name).outsidePlanCount, 0),
        },
      };
      return { body: cloneJson(latestTaxCertifiedPreview) };
    },
    "/api/tax-offset/certified-import/confirm": ({ jsonBody }) => {
      const sessionId = String(jsonBody?.session_id ?? "");
      if (!latestTaxCertifiedPreview || latestTaxCertifiedPreview.session.id !== sessionId) {
        return {
          status: 404,
          body: {
            error: "tax_certified_import_session_not_found",
            message: "session not found",
          },
        };
      }
      const touchedMonths = new Set<string>();
      for (const file of latestTaxCertifiedPreview.files) {
        const currentPayload = taxOffsetStateStore.get(file.month);
        taxOffsetStateStore.set(
          file.month,
          applyCertifiedImportToTaxOffsetPayload(currentPayload, file.rows),
        );
        touchedMonths.add(file.month);
      }
      return {
        body: {
          success: true,
          batch: {
            id: "tax-certified-batch-0001",
            session_id: latestTaxCertifiedPreview.session.id,
            imported_by: latestTaxCertifiedPreview.session.imported_by,
            file_count: latestTaxCertifiedPreview.session.file_count,
            months: Array.from(touchedMonths),
            persisted_record_count: latestTaxCertifiedPreview.summary.recognized_count,
          },
        },
      };
    },
    "/api/cost-statistics/tag-rules": ({ init, jsonBody }) => {
      const selectedCodes = Array.isArray(jsonBody?.selected_tag_codes)
        ? jsonBody.selected_tag_codes.map((code) => String(code))
        : ["fee", "__uncategorized__"];
      return {
        body: {
          version: init?.method === "PUT" ? 2 : 1,
          bank_auto_tag_rules_version: 8,
          default_selection_applied: init?.method !== "PUT",
          selected_tag_codes: selectedCodes,
          effective_selected_tag_codes: selectedCodes,
          inactive_selected_tag_codes: [],
          active_tags: [
            {
              code: "fee",
              label: "材料费",
              path: ["费用", "材料费"],
              source: "custom",
              status: "active",
              direction: "any",
              output_primary_label: "费用",
              output_sub_label: "材料费",
            },
            {
              code: "income_collection",
              label: "项目回款",
              path: ["经营收入", "项目回款"],
              source: "custom",
              status: "active",
              direction: "income",
              output_primary_label: "经营收入",
              output_sub_label: "项目回款",
            },
            {
              code: "__uncategorized__",
              label: "未分类",
              path: ["未分类", "未分类"],
              source: "system",
              status: "active",
              direction: "any",
              output_primary_label: "未分类",
              output_sub_label: "未分类",
            },
          ],
          can_save: options.costTagRulesCanSave ?? true,
        },
      };
    },
    "/api/cost-statistics/explorer": ({ url }) => {
      const scope = url.searchParams.get("scope") ?? "all";
      const month = scope.startsWith("year:") ? "all" : scope;
      const projectScope = url.searchParams.get("project_scope") ?? "active";
      if (costExplorerFailuresRemaining > 0 && month !== "all") {
        costExplorerFailuresRemaining -= 1;
        return {
          status: 503,
          body: {
            error: "cost_statistics_explorer_temporarily_unavailable",
            message: "成本统计数据加载暂时失败，请刷新后重试。",
          },
        };
      }
      if (options.costErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "cost statistics failed" } };
      }
      return {
        body: buildCostStatisticsExplorerPagePayload(
          url,
          buildCostStatisticsExplorerPayload(month, projectScope, {
            duplicateTransactionRows: options.costDuplicateTransactionRows,
          }),
        ),
      };
    },
    "/api/cost-statistics/export-preview": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      const view = url.searchParams.get("view") ?? "time";
      const projectScope = url.searchParams.get("project_scope") ?? "active";
      const projectNames = url.searchParams.getAll("project_name");
      const aggregateBy = url.searchParams.get("aggregate_by");
      const expenseTypes = url.searchParams.getAll("expense_type");
      const startMonth = url.searchParams.get("start_month");
      const endMonth = url.searchParams.get("end_month");
      const startDate = url.searchParams.get("start_date");
      const endDate = url.searchParams.get("end_date");
      return {
        body: buildCostStatisticsExportPreviewPayload({
          month,
          view,
          projectNames,
          aggregateBy,
          expenseTypes,
          projectScope,
          startMonth,
          endMonth,
          startDate,
          endDate,
        }),
      };
    },
    "/api/cost-statistics/export": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      const view = url.searchParams.get("view") ?? "month";
      const projectNames = url.searchParams.getAll("project_name");
      const aggregateBy = url.searchParams.get("aggregate_by");
      const expenseType = url.searchParams.get("expense_type");
      const expenseTypes = url.searchParams.getAll("expense_type");
      const transactionId = url.searchParams.get("transaction_id");
      const startMonth = url.searchParams.get("start_month");
      const endMonth = url.searchParams.get("end_month");
      const startDate = url.searchParams.get("start_date");
      const endDate = url.searchParams.get("end_date");
      if (options.costExportErrorViews?.includes(view)) {
        return {
          status: 500,
          body: { message: "cost statistics export failed" },
        };
      }
      const fileName = buildCostStatisticsExportFileName(
        month,
        view,
        projectNames,
        aggregateBy,
        expenseType,
        transactionId,
        startMonth,
        endMonth,
        expenseTypes,
        startDate,
        endDate,
      );
      return binaryResponse({
        body: `mock export for ${fileName}`,
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": `attachment; filename="${fileName}"`,
        },
      });
    },
    "/api/tax-offset/calculate": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const selectedOutputIds = Array.isArray(jsonBody?.selected_output_ids)
        ? (jsonBody.selected_output_ids as string[])
        : [];
      const selectedInputIds = Array.isArray(jsonBody?.selected_input_ids)
        ? (jsonBody.selected_input_ids as string[])
        : [];
      return { body: calculateTaxPayload(month, selectedOutputIds, selectedInputIds, taxOffsetStateStore.get(month)) };
    },
    "/api/tax-offset/plans": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const selectedOutputIds = Array.isArray(jsonBody?.selected_output_ids)
        ? (jsonBody.selected_output_ids as string[])
        : [];
      const selectedInputIds = Array.isArray(jsonBody?.selected_input_ids)
        ? (jsonBody.selected_input_ids as string[])
        : [];
      return {
        body: {
          status: "saved",
          affected_scope_keys: [month],
          plan: {
            id: "tax-offset-plan-0001",
            month,
            selected_output_ids: selectedOutputIds,
            selected_input_ids: selectedInputIds,
            summary: calculateTaxPayload(month, selectedOutputIds, selectedInputIds, taxOffsetStateStore.get(month)).summary,
            canonical_snapshot_version: String(jsonBody?.expected_canonical_snapshot_version ?? ""),
            updated_at: "2026-06-01T10:00:00+08:00",
          },
        },
      };
    },
    "/api/etc/invoices": ({ url }) => ({
      body: etcInvoiceStore.list({
        status: url.searchParams.get("status"),
        month: url.searchParams.get("month"),
        plate: url.searchParams.get("plate"),
        keyword: url.searchParams.get("keyword"),
      }),
    }),
    "/api/etc/business-batches": ({ url, init, jsonBody }) => {
      if (init?.method === "POST") {
        const title = String(jsonBody?.title ?? "新建ETC批次").trim() || "新建ETC批次";
        const task = etcReconciliationTaskStore.create(title);
        return { status: 201, body: etcInvoiceStore.createBusinessBatch(String(task.taskId ?? ""), title) };
      }
      return {
        body: etcInvoiceStore.listBusinessBatches({
          bucket: url.searchParams.get("bucket"),
          month: url.searchParams.get("month"),
          plate: url.searchParams.get("plate"),
          keyword: url.searchParams.get("keyword"),
          page: Math.max(1, Number(url.searchParams.get("page") ?? 1) || 1),
          pageSize: Math.max(1, Number(url.searchParams.get("page_size") ?? 100) || 100),
        }),
      };
    },
    "/api/etc/reconciliation-tasks/ready-for-import": () => ({
      body: etcReconciliationTaskStore.ready(),
    }),
    "/api/etc/reconciliation-tasks": ({ jsonBody, init }) => {
      if (init?.method === "POST") {
        return { status: 201, body: etcReconciliationTaskStore.create(String(jsonBody?.title ?? "")) };
      }
      return { body: etcReconciliationTaskStore.list() };
    },
    "/api/etc/import/preview": ({ formData }) => {
      const fileNames = (formData?.getAll("files") as File[] | undefined)?.map((file) => file.name) ?? [];
      const taskId = String(formData?.get("task_id") ?? formData?.get("taskId") ?? "");
      if (!taskId) {
        return {
          status: 400,
          body: {
            error: "task_id_required",
            message: "task_id is required.",
          },
        };
      }
      latestEtcImportPreview = etcInvoiceStore.previewZip(fileNames, options.etcImportBlockingIssues ?? []);
      return { body: cloneJson(latestEtcImportPreview) };
    },
    "/api/etc/import/confirm": ({ jsonBody }) => {
      const sessionId = String(jsonBody?.sessionId ?? jsonBody?.session_id ?? "");
      const taskId = String(jsonBody?.taskId ?? jsonBody?.task_id ?? "");
      if (!taskId) {
        return {
          status: 400,
          body: {
            error: "task_id_required",
            message: "task_id is required.",
          },
        };
      }
      if (options.etcImportConfirmPreviewStale) {
        return {
          status: 409,
          body: {
            error: "preview_stale",
          },
        };
      }
      if (options.etcImportConfirmStaleReconciliationTask) {
        return {
          status: 409,
          body: {
            error: "stale_reconciliation_task_preview",
          },
        };
      }
      if (sessionId !== latestEtcImportPreview.sessionId) {
        return {
          status: 404,
          body: {
            error: "etc_import_session_not_found",
            message: "ETC 导入预览会话不存在。",
          },
        };
      }
      return {
        status: 202,
        body: etcInvoiceStore.confirmImport(),
      };
    },
    "/api/bank-details/accounts": ({ url }) => {
      const dateFrom = url.searchParams.get("date_from");
      const dateTo = url.searchParams.get("date_to");
      const isCurrentYear = dateFrom === "2026-01-01" && dateTo === "2026-12-31";
      const totalBalance = bankDetailAutoTagRulesSaved && options.bankDetailPostSaveAccountsTotalBalance
        ? options.bankDetailPostSaveAccountsTotalBalance
        : "130500.50";
      return {
        body: {
          total_balance: totalBalance,
          balance_account_count: 1,
          missing_balance_account_count: 1,
          accounts: [
            {
              account_key: "icbc:6386",
              bank_name: "工商银行",
              account_last4: "6386",
              display_name: "工商银行 6386",
              latest_balance: totalBalance,
              latest_balance_at: "2026-05-01 16:30:00",
              has_balance: true,
              transaction_count: isCurrentYear ? 299 : 1,
            },
            {
              account_key: "bocom:3847",
              bank_name: "交通银行",
              account_last4: "3847",
              display_name: "交通银行 3847",
              latest_balance: null,
              latest_balance_at: null,
              has_balance: false,
              transaction_count: 0,
            },
          ],
        },
      };
    },
    "/api/bank-details/transactions/export": ({ url }) => new Response("mock-bank-detail-export", {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "Content-Disposition": `attachment; filename="bank-details.xlsx"; filename*=UTF-8''${encodeURIComponent(
          url.searchParams.get("mode") === "account" ? "银行明细_工商银行6386.xlsx" : "银行明细_当前筛选_全部银行.xlsx",
        )}`,
      },
    }),
    "/api/bank-details/auto-tag-rules/reapply": () => {
      bankDetailAutoTagRulesSaved = true;
      return {
        status: 200,
        body: {
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
          active_rules: [
            {
              code: "fee",
              label: "手续费",
              output_primary_label: "费用",
              output_sub_label: "手续费",
              status: "active",
              source: "system",
              priority: 2,
              priority_label: "优先级 2",
              sort_order: 1,
              rules: { match_fields: ["counterparty_name", "summary_text", "note_text"], exact: [], contains: ["手续费"], excludes: [] },
              rule_summary: "对方户名/摘要/备注包含：手续费",
              editable: true,
              archivable: true,
              sortable: true,
            },
            {
              code: "salary",
              label: "工资",
              output_primary_label: "费用",
              output_sub_label: "工资",
              status: "active",
              source: "system",
              priority: 2,
              priority_label: "优先级 2",
              sort_order: 2,
              rules: { match_fields: ["summary_text", "purpose_text", "note_text", "detail_text"], exact: [], contains: ["工资", "绩效奖", "年终奖"], excludes: [] },
              rule_summary: "摘要/用途/备注/其他明细包含：工资",
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
            { value: "detail_text", label: "其他明细" },
            { value: "all_text", label: "全部文本" },
          ],
          turnover_third_label_options: [
            { value: "个人往来", label: "个人往来" },
            { value: "公司往来", label: "公司往来" },
            { value: "银行往来", label: "银行往来" },
            { value: "业务往来", label: "业务往来" },
          ],
          turnover_action_type_options: [
            { value: "pending_collection", label: "待收款" },
            { value: "collected", label: "已收款" },
            { value: "pending_repayment", label: "待还款" },
            { value: "repaid", label: "已还款" },
          ],
          permissions: { can_save: true },
        },
      };
    },
    "/api/bank-details/auto-tag-rules": ({ init, jsonBody }) => {
      const baseRules = {
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
        active_rules: [
          {
            code: "fee",
            label: "手续费",
            output_primary_label: "费用",
            output_sub_label: "手续费",
            status: "active",
            source: "system",
            priority: 10,
            priority_label: "优先级 10",
            sort_order: 1,
            rules: { match_fields: ["counterparty_name", "summary_text", "note_text"], exact: [], contains: ["手续费"], excludes: [] },
            rule_summary: "对方户名/摘要/备注包含：手续费",
            editable: true,
            archivable: true,
            sortable: true,
          },
          {
            code: "salary",
            label: "工资",
            output_primary_label: "费用",
            output_sub_label: "工资",
            status: "active",
            source: "system",
            priority: 20,
            priority_label: "优先级 20",
            sort_order: 2,
            rules: { match_fields: ["summary_text", "purpose_text", "note_text", "detail_text"], exact: [], contains: ["工资", "绩效奖", "年终奖"], excludes: [] },
            rule_summary: "摘要/用途/备注/其他明细包含：工资",
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
            direction: "expense",
            status: "active",
            source: "custom",
            priority: 30,
            priority_label: "优先级 30",
            sort_order: 3,
            rules: { match_fields: ["purpose_text", "summary_text"], exact: [], contains: ["借款"], excludes: [] },
            rule_summary: "用途/摘要包含：借款",
            editable: true,
            archivable: true,
            sortable: true,
          },
          {
            code: "external_repaid",
            label: "归还借款",
            output_primary_label: "外部往来款付款",
            output_sub_label: "归还借款",
            turnover_role: "external_turnover",
            turnover_action_type: "repaid",
            direction: "expense",
            status: "active",
            source: "custom",
            priority: 30,
            priority_label: "优先级 30",
            sort_order: 4,
            rules: { match_fields: ["purpose_text", "summary_text"], exact: [], contains: ["还暂借款"], excludes: [] },
            rule_summary: "用途/摘要包含：还暂借款",
            editable: true,
            archivable: true,
            sortable: true,
          },
        ],
        archived_rules: [
          {
            code: "old_bonus",
            label: "旧奖金",
            output_primary_label: "费用",
            output_sub_label: "旧奖金",
            status: "archived",
            source: "custom",
            rules: { match_fields: ["all_text"], exact: [], contains: ["旧奖金"], excludes: [] },
            rule_summary: "全部文本包含：旧奖金",
            editable: true,
            archivable: false,
            sortable: false,
          },
        ],
        field_options: [
          { value: "counterparty_name", label: "对方户名" },
          { value: "purpose_text", label: "用途/交易用途" },
          { value: "summary_text", label: "摘要" },
          { value: "note_text", label: "备注/附言/客户附言" },
          { value: "detail_text", label: "其他明细" },
          { value: "all_text", label: "全部文本" },
        ],
        turnover_third_label_options: [
          { value: "个人往来", label: "个人往来" },
          { value: "公司往来", label: "公司往来" },
          { value: "银行往来", label: "银行往来" },
          { value: "业务往来", label: "业务往来" },
        ],
        turnover_action_type_options: [
          { value: "pending_collection", label: "待收款" },
          { value: "collected", label: "已收款" },
          { value: "pending_repayment", label: "待还款" },
          { value: "repaid", label: "已还款" },
        ],
        permissions: { can_save: true },
      };
      if (String(init?.method || "GET").toUpperCase() !== "PUT") {
        return { body: baseRules };
      }
      bankDetailAutoTagRulesSaved = true;
      const activeRules = Array.isArray(jsonBody?.active_rules) ? jsonBody.active_rules as Array<Record<string, unknown>> : [];
      const archivedRules = Array.isArray(jsonBody?.archived_rules) ? jsonBody.archived_rules as Array<Record<string, unknown>> : [];
      return {
        body: {
          ...baseRules,
          version: 2,
          active_rules: activeRules.map((rule, index) => ({
            code: String(rule.code || `custom_saved_${index}`),
            label: String(rule.label || ""),
            output_primary_label: String(rule.output_primary_label || ""),
            output_sub_label: String(rule.output_sub_label || ""),
            turnover_role: rule.turnover_action_type ? "external_turnover" : "",
            turnover_action_type: String(rule.turnover_action_type || ""),
            status: "active",
            source: rule.code ? "system" : "custom",
            priority: Number(rule.priority) || 2,
            priority_label: `优先级 ${Number(rule.priority) || 2}`,
            sort_order: Number(rule.sort_order) || index + 1,
            rules: rule.rules,
            rule_summary: "已保存",
            editable: true,
            archivable: true,
            sortable: true,
          })),
          archived_rules: archivedRules.map((rule) => ({
            code: String(rule.code || ""),
            label: String(rule.label || ""),
            output_primary_label: String(rule.output_primary_label || ""),
            output_sub_label: String(rule.output_sub_label || ""),
            turnover_role: rule.turnover_action_type ? "external_turnover" : "",
            turnover_action_type: String(rule.turnover_action_type || ""),
            status: "archived",
            source: "custom",
            rules: rule.rules,
            rule_summary: "已停用",
            editable: true,
            archivable: false,
            sortable: false,
          })),
        },
      };
    },
    "/api/bank-details/transactions": ({ url }) => {
      const accountKey = url.searchParams.get("account_key");
      const dateFrom = url.searchParams.get("date_from");
      const dateTo = url.searchParams.get("date_to");
      const keyword = (url.searchParams.get("keyword") ?? "").trim();
      const categoryCode = url.searchParams.get("category_code");
      const categoryPrimaryLabel = url.searchParams.get("category_primary_label");
      const categorySubLabel = url.searchParams.get("category_sub_label");
      const categoryThirdLabel = url.searchParams.get("category_third_label");
      const page = Number(url.searchParams.get("page") ?? "1");
      const pageSize = Number(url.searchParams.get("page_size") ?? "100");
      const isCurrentYear = dateFrom === "2026-01-01" && dateTo === "2026-12-31";
      const visibleRow = {
        id: `bank-detail-${String(page).padStart(3, "0")}`,
        trade_time: "2026-05-01 10:30:00+08:00",
        counterparty_name: "云南溯源科技有限公司",
        direction: "income",
        direction_label: "收",
        amount: "20000.00",
        balance: "130500.50",
        summary: "项目回款",
        purpose: "货款",
        purpose_text: "货款",
        summary_text: "项目回款",
        note_text: "",
        bank_name: "工商银行",
        account_last4: "6386",
        category_code: null,
        category_label: null,
        category_path: [],
        category_source: "",
        category_version: 1,
        auto_category_code: "salary",
        auto_category_label: "工资",
        auto_category_path: ["自动识别", "工资"],
        auto_category_primary_label: "费用",
        auto_category_sub_label: "工资",
        auto_category_third_label: null,
        auto_category_label_path: ["费用", "工资"],
        auto_category_source: "bank_transaction_auto_category_service",
        auto_category_reason: "摘要命中工资规则",
        auto_category_confidence: "high",
        effective_category_code: "salary",
        effective_category_label: "工资",
        effective_category_path: ["自动识别", "工资"],
        effective_category_primary_label: "费用",
        effective_category_sub_label: "工资",
        effective_category_third_label: null,
        effective_category_label_path: ["费用", "工资"],
        effective_category_source: "auto",
        oa_relation_tag: "候选oa",
        invoice_relation_tag: "候选发票",
        relation_tags: ["候选oa", "候选发票"],
        relation_case_id: "candidate:CASE-202605-001",
        relation_status: "candidate",
      };
      const hiddenTargetRow = {
        ...visibleRow,
        id: "bank-detail-search-target",
        trade_time: "2026-03-01 10:30:00",
        counterparty_name: "跨页目标供应商",
        summary: "网银手续费",
        purpose: "跨页目标用途",
        purpose_text: "跨页目标用途",
        summary_text: "网银手续费",
        note_text: "",
        auto_category_code: "fee",
        auto_category_label: "手续费",
        auto_category_path: ["自动识别", "手续费"],
        auto_category_primary_label: "费用",
        auto_category_sub_label: "手续费",
        auto_category_third_label: null,
        auto_category_label_path: ["费用", "手续费"],
        auto_category_reason: "摘要命中手续费规则",
        effective_category_code: "fee",
        effective_category_label: "手续费",
        effective_category_path: ["自动识别", "手续费"],
        effective_category_primary_label: "费用",
        effective_category_sub_label: "手续费",
        effective_category_third_label: null,
        effective_category_label_path: ["费用", "手续费"],
      };
      const internalTransferRow = {
        ...visibleRow,
        id: "bank-detail-internal-transfer",
        trade_time: "2026-04-03 10:00:00",
        counterparty_name: "云南溯源科技有限公司建设银行账户",
        direction: "expense",
        direction_label: "支",
        amount: "13000.00",
        balance: "900.00",
        summary: "内部转账",
        purpose: "内部往来",
        purpose_text: "内部往来",
        summary_text: "内部转账",
        note_text: "",
        bank_name: "工商银行",
        account_last4: "6386",
        auto_category_code: "internal_transfer",
        auto_category_label: "内部往来款",
        auto_category_path: ["自动识别", "内部往来款"],
        auto_category_primary_label: null,
        auto_category_sub_label: null,
        auto_category_third_label: null,
        auto_category_label_path: ["内部往来款"],
        auto_category_reason: "内部往来配对",
        effective_category_code: "internal_transfer",
        effective_category_label: "内部往来款",
        effective_category_path: ["自动识别", "内部往来款"],
        effective_category_primary_label: null,
        effective_category_sub_label: null,
        effective_category_third_label: null,
        effective_category_label_path: ["内部往来款"],
        oa_relation_tag: "候选oa",
        invoice_relation_tag: "候选发票",
        relation_tags: ["候选oa", "候选发票"],
        relation_case_id: "candidate:bank-detail-internal-transfer",
        relation_status: "candidate",
        internal_transfer_counterpart: {
          transaction_id: "bank-detail-internal-transfer-counterpart",
          trade_time: "2026-04-03 12:00:00",
          bank_name: "建设银行",
          account_last4: "1410",
          amount: "13000.00",
          direction_label: "收",
          counterparty_name: "云南溯源科技有限公司工商银行账户",
        },
      };
      const needsConfirmationRow = {
        ...visibleRow,
        id: "bank-detail-needs-confirmation",
        trade_time: "2026-04-02 10:30:00",
        counterparty_name: "候选供应商",
        summary: "网银手续费工资",
        purpose: "手续费工资",
        purpose_text: "手续费工资",
        summary_text: "网银手续费工资",
        note_text: "",
        category_resolution_status: "needs_confirmation",
        category_rule_version: "bank-auto-tag-rules:2",
        manual_confirmed_category_code: null,
        auto_category_code: null,
        auto_category_label: null,
        auto_category_path: [],
        auto_category_primary_label: null,
        auto_category_sub_label: null,
        auto_category_third_label: null,
        auto_category_label_path: [],
        auto_category_source: "",
        auto_category_reason: null,
        auto_category_confidence: null,
        auto_candidate_category_codes: ["fee", "salary", "business_warranty_pending_collection"],
        auto_candidate_categories: [
          {
            category_code: "fee",
            category_label: "手续费",
            category_primary_label: "费用",
            category_sub_label: "手续费",
            category_third_label: null,
            category_label_path: ["费用", "手续费"],
            category_path: ["自动识别", "手续费"],
            rule_code: "fee",
            reason: "摘要命中手续费",
          },
          {
            category_code: "salary",
            category_label: "工资",
            category_primary_label: "费用",
            category_sub_label: "工资",
            category_third_label: null,
            category_label_path: ["费用", "工资"],
            category_path: ["自动识别", "工资"],
            rule_code: "salary",
            reason: "摘要命中工资",
          },
          {
            category_code: "business_warranty_pending_collection",
            category_label: "待收款",
            category_primary_label: "质保金",
            category_sub_label: "待收款",
            category_third_label: null,
            category_label_path: ["质保金", "待收款"],
            category_path: ["业务往来", "质保金", "待收款"],
            rule_code: "business_warranty_pending_collection",
            reason: "旧候选不在当前自动规则中",
          },
        ],
        effective_category_code: null,
        effective_category_label: null,
        effective_category_path: [],
        effective_category_primary_label: null,
        effective_category_sub_label: null,
        effective_category_third_label: null,
        effective_category_label_path: [],
        effective_category_source: "",
      };
      const searchDataset = [
        visibleRow,
        internalTransferRow,
        needsConfirmationRow,
        {
          ...visibleRow,
          id: "bank-detail-search-filler",
          trade_time: "2026-04-01 10:30:00",
          counterparty_name: "普通供应商",
          summary: "普通付款",
          purpose: "普通用途",
          purpose_text: "普通用途",
          summary_text: "普通付款",
          note_text: "",
          category_code: bankDetailManualAssignmentActive ? "salary" : null,
          category_label: bankDetailManualAssignmentActive ? "工资" : null,
          category_path: bankDetailManualAssignmentActive ? ["自动识别", "工资"] : [],
          category_primary_label: bankDetailManualAssignmentActive ? "费用" : null,
          category_sub_label: bankDetailManualAssignmentActive ? "工资" : null,
          category_label_path: bankDetailManualAssignmentActive ? ["费用", "工资"] : [],
          category_source: bankDetailManualAssignmentActive ? "manual" : "",
          category_resolution_status: bankDetailManualAssignmentActive ? "manual_confirmed" : "unmatched",
          manual_confirmed_category_code: bankDetailManualAssignmentActive ? "salary" : null,
          auto_category_code: null,
          auto_category_label: null,
          auto_category_path: [],
          auto_category_primary_label: null,
          auto_category_sub_label: null,
          auto_category_third_label: null,
          auto_category_label_path: [],
          effective_category_code: bankDetailManualAssignmentActive ? "salary" : null,
          effective_category_label: bankDetailManualAssignmentActive ? "工资" : null,
          effective_category_path: bankDetailManualAssignmentActive ? ["自动识别", "工资"] : [],
          effective_category_primary_label: bankDetailManualAssignmentActive ? "费用" : null,
          effective_category_sub_label: bankDetailManualAssignmentActive ? "工资" : null,
          effective_category_third_label: null,
          effective_category_label_path: bankDetailManualAssignmentActive ? ["费用", "工资"] : [],
          effective_category_source: bankDetailManualAssignmentActive ? "manual" : "",
        },
        {
          ...visibleRow,
          id: "bank-detail-external-turnover-needs-confirmation",
          trade_time: "2026-04-01 11:30:00",
          counterparty_name: "外部候选供应商",
          direction: "expense",
          direction_label: "支",
          summary: "借款支出",
          purpose: "借款",
          purpose_text: "借款",
          summary_text: "借款支出",
          note_text: "",
          category_resolution_status: "needs_confirmation",
          category_rule_version: "bank-auto-tag-rules:2",
          manual_confirmed_category_code: null,
          auto_category_code: null,
          auto_category_label: null,
          auto_category_path: [],
          auto_category_primary_label: null,
          auto_category_sub_label: null,
          auto_category_third_label: null,
          auto_category_label_path: [],
          auto_candidate_category_codes: [
            "external_payment",
            "external_payment",
            "external_payment",
            "external_payment",
            "external_repaid",
            "external_repaid",
            "external_repaid",
            "external_repaid",
          ],
          auto_candidate_categories: [
            { code: "external_payment", label: "借出款", actionType: "pending_collection" },
            { code: "external_repaid", label: "归还借款", actionType: "repaid" },
          ].flatMap((subCategory) => ["个人往来", "公司往来", "银行往来", "业务往来"].map((thirdLabel) => ({
            category_code: subCategory.code,
            category_label: subCategory.label,
            category_primary_label: "外部往来款付款",
            category_sub_label: subCategory.label,
            category_third_label: thirdLabel,
            category_label_path: ["外部往来款付款", subCategory.label, thirdLabel],
            category_path: ["自动识别", subCategory.label],
            turnover_role: "external_turnover",
            turnover_action_type: subCategory.actionType,
            turnover_family: thirdLabel === "个人往来" ? "personal" : thirdLabel === "公司往来" ? "company" : thirdLabel === "银行往来" ? "bank" : "business",
            rule_code: subCategory.code,
            reason: "命中外部往来款自动规则，需要确认往来对象类型。",
          }))),
          effective_category_code: null,
          effective_category_label: null,
          effective_category_path: [],
          effective_category_primary_label: null,
          effective_category_sub_label: null,
          effective_category_third_label: null,
          effective_category_label_path: [],
          effective_category_source: "",
        },
        hiddenTargetRow,
      ];
      const defaultFilterDataset = searchDataset.filter((row) => row.id !== "bank-detail-search-target");
      const matchedRows = keyword
        ? searchDataset.filter((row) => Object.values(row).some((value) => (
          Array.isArray(value)
            ? value.join(" ").includes(keyword)
            : String(value ?? "").includes(keyword)
        )))
        : null;
      const hasCategoryFilter = Boolean(categoryCode || categoryPrimaryLabel || categorySubLabel || categoryThirdLabel);
      const categoryMatches = (row: typeof searchDataset[number]) => {
        if (categoryCode === "uncategorized" && row.effective_category_code) {
          return false;
        }
        if (categoryCode && categoryCode !== "uncategorized" && row.effective_category_code !== categoryCode) {
          return false;
        }
        if (categoryPrimaryLabel && row.effective_category_primary_label !== categoryPrimaryLabel) {
          return false;
        }
        if (categorySubLabel && row.effective_category_sub_label !== categorySubLabel) {
          return false;
        }
        if (categoryThirdLabel && row.effective_category_third_label !== categoryThirdLabel) {
          return false;
        }
        return true;
      };
      const rows = !accountKey || accountKey === "icbc:6386"
        ? (matchedRows ?? (hasCategoryFilter ? defaultFilterDataset : [visibleRow])).filter(categoryMatches)
        : [];
      const responseRows = bankDetailAutoTagRulesSaved && options.bankDetailPostSaveTransactionsEmpty ? [] : rows;
      const baseCategoryCounts = {
        borrow_in_company_pending_repayment: 2,
        business_warranty_pending_collection: 1,
        borrow_out_personal_pending_collection: 0,
        salary: responseRows.length && (!accountKey || accountKey === "icbc:6386") ? 1 : 0,
        fee: 0,
        internal_transfer: responseRows.length && (!accountKey || accountKey === "icbc:6386") ? 2 : 0,
        holiday_bonus: 0,
        bonus: 0,
        uncategorized: responseRows.length && (!accountKey || accountKey === "icbc:6386") && isCurrentYear ? 295 : responseRows.length,
      };
      const visibleCategoryCounts = {
        borrow_in_company_pending_repayment: 0,
        business_warranty_pending_collection: 0,
        borrow_out_personal_pending_collection: 0,
        salary: responseRows.filter((row) => row.effective_category_code === "salary").length,
        fee: responseRows.filter((row) => row.effective_category_code === "fee").length,
        internal_transfer: responseRows.filter((row) => row.effective_category_code === "internal_transfer").length,
        holiday_bonus: 0,
        bonus: 0,
        uncategorized: categoryCode === "uncategorized" && (!accountKey || accountKey === "icbc:6386") && isCurrentYear
          ? 295
          : responseRows.filter((row) => !row.effective_category_code).length,
      };
      return {
        body: {
          account_key: accountKey,
          date_from: dateFrom,
          date_to: dateTo,
          rows: responseRows,
          category_counts: keyword || hasCategoryFilter ? visibleCategoryCounts : baseCategoryCounts,
          pagination: {
            page,
            page_size: pageSize,
            total: categoryCode === "uncategorized" && (!accountKey || accountKey === "icbc:6386") && isCurrentYear
              ? 295
              : keyword || hasCategoryFilter
              ? responseRows.length
              : responseRows.length && (!accountKey || accountKey === "icbc:6386") && isCurrentYear ? 299 : responseRows.length,
          },
          bank_transaction_tags: {
            version: 1,
            definitions: SELECTABLE_CATEGORY_OPTIONS.map((option) => ({
              code: option.code,
              label: option.label,
              path: option.menuLabel.split(" / "),
              output_primary_label: option.code === "fee" || option.code === "salary" ? "费用" : option.label,
              output_sub_label: option.code === "fee" ? "手续费" : option.code === "salary" ? "工资" : "",
              source: "system",
              status: "active",
            })),
          },
        },
      };
    },
    "/api/turnover-ledger/tag-selection": () => ({
      body: {
        version: 1,
        selected_tag_codes: ["external_rule_borrow_out", "external_rule_repaid"],
        inactive_selected_tag_codes: [],
        active_tags: [
          {
            code: "external_rule_borrow_out",
            label: "借出款",
            path: ["银行明细自动标签规则", "外部往来款付款", "借出款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "借出款",
            turnover_role: "external_turnover",
            turnover_action_type: "pending_collection",
          },
          {
            code: "external_rule_repaid",
            label: "归还借款",
            path: ["银行明细自动标签规则", "外部往来款付款", "归还借款"],
            source: "custom",
            status: "active",
            output_primary_label: "外部往来款付款",
            output_sub_label: "归还借款",
            turnover_role: "external_turnover",
            turnover_action_type: "repaid",
          },
        ],
      },
    }),
    "/api/turnover-ledger": ({ url }) => {
      const view = url.searchParams.get("view") ?? "";
      const family = url.searchParams.get("family") ?? "all";
      const page = Number(url.searchParams.get("page") ?? "1");
      const pageSize = Number(url.searchParams.get("page_size") ?? "100");
      const allRows = [
        {
          relation_id: "rel-suggested-personal",
          status: "suggested",
          status_label: "待人工确认",
          row_tone: "warning",
          chips: [
            { label: "待确认", tone: "warning" },
            { label: "部分闭合", tone: "info" },
            { label: "未同步关联台", tone: "muted" },
          ],
          family: "personal",
          family_label: "个人往来",
          counterparty_name: "张三",
          principal_amount: "1000.00",
          settled_amount: "200.00",
          balance_amount: "800.00",
          first_transaction_at: "2026-05-01 10:00:00",
          last_settlement_at: "2026-05-03 10:00:00",
          bank_account_labels: ["建行 8106"],
          summary_text: "暂借款 / 还款",
          annual_interest_rate: "3.50%",
          loan_days: 2,
          accrued_interest: "0.19",
          sync_to_workbench: false,
          bank_row_ids: ["bank-personal-001", "bank-personal-002"],
          category_codes: ["borrow_in_personal_pending_repayment", "borrow_in_personal_repaid"],
          business_type: "borrow_in",
        },
        {
          relation_id: "rel-deterministic-bank",
          status: "deterministic",
          status_label: "已闭合",
          row_tone: "success",
          chips: [
            { label: "系统确认", tone: "success" },
            { label: "已同步关联台", tone: "success" },
          ],
          family: "bank",
          family_label: "银行往来",
          counterparty_name: "昆明银行",
          principal_amount: "5000.00",
          settled_amount: "5000.00",
          balance_amount: "0.00",
          first_transaction_at: "2026-04-01 10:00:00",
          last_settlement_at: "2026-04-20 10:00:00",
          bank_account_labels: ["工行 6386"],
          summary_text: "银行往来闭合",
          annual_interest_rate: null,
          loan_days: 19,
          accrued_interest: null,
          sync_to_workbench: true,
          bank_row_ids: ["bank-bank-001", "bank-bank-002"],
          category_codes: ["borrow_in_bank_pending_repayment", "borrow_in_bank_repaid"],
          business_type: "borrow_in",
        },
        {
          relation_id: "rel-company-001",
          status: "confirmed",
          status_label: "人工确认",
          row_tone: "success",
          chips: [
            { label: "人工确认", tone: "success" },
            { label: "已同步关联台", tone: "success" },
          ],
          family: "company",
          family_label: "公司往来",
          counterparty_name: "云南建设有限公司",
          principal_amount: "3000.00",
          settled_amount: "1000.00",
          balance_amount: "2000.00",
          first_transaction_at: "2026-05-02 09:00:00",
          last_settlement_at: "2026-05-04 09:00:00",
          bank_account_labels: ["建行 8106"],
          summary_text: "公司暂借款",
          annual_interest_rate: null,
          loan_days: 2,
          accrued_interest: null,
          sync_to_workbench: true,
          bank_row_ids: ["bank-company-001", "bank-company-002"],
          category_codes: ["borrow_in_company_pending_repayment"],
          business_type: "borrow_in",
        },
      ];
      const rows = family === "all" ? allRows : allRows.filter((row) => row.family === family);
      if (view === "grouped") {
        const allGroups = [
          {
            group_id: "counterparty:personal:张三",
            counterparty_name: "张三",
            family: "personal",
            family_label: "个人往来",
            pending_direction: "repayment",
            pending_direction_label: "待还款",
            pending_amount: "800.00",
            row_span: 1,
            group_tone: "warning",
            rows: [
              {
                relation_id: "rel-suggested-personal",
                status: "suggested",
                status_label: "待人工确认",
                row_tone: "warning",
                borrow_amount: "1000.00",
                borrow_date: "2026-05-01",
                borrow_direction: "income",
                repayment_amount: "200.00",
                repayment_date: "2026-05-03",
                repayment_direction: "expense",
                counterparty_bank_name: "建行 8106",
                repayment_remark: "归还暂借款",
                interest_rate_type: "annual",
                interest_rate_value: "0.035000",
                interest_paid_amount: "0.00",
                loan_days: 2,
                accrued_interest: "0.19",
                interest_paid_date: null,
                interest_payment_method: "",
                note: "",
                bank_row_ids: ["bank-personal-001", "bank-personal-002"],
              },
            ],
          },
          {
            group_id: "counterparty:bank:昆明银行",
            counterparty_name: "昆明银行",
            family: "bank",
            family_label: "银行往来",
            pending_direction: "closed",
            pending_direction_label: "已闭合",
            pending_amount: "0.00",
            row_span: 1,
            group_tone: "success",
            rows: [
              {
                relation_id: "rel-deterministic-bank",
                status: "deterministic",
                status_label: "已闭合",
                row_tone: "success",
                borrow_amount: "5000.00",
                borrow_date: "2026-04-01",
                borrow_direction: "income",
                repayment_amount: "5000.00",
                repayment_date: "2026-04-20",
                repayment_direction: "expense",
                counterparty_bank_name: "工行 6386",
                repayment_remark: "银行往来闭合",
                interest_rate_type: "none",
                interest_rate_value: "0.000000",
                interest_paid_amount: "0.00",
                loan_days: 19,
                accrued_interest: "0.00",
                interest_paid_date: null,
                interest_payment_method: "",
                note: "",
                bank_row_ids: ["bank-bank-001", "bank-bank-002"],
              },
            ],
          },
          {
            group_id: "counterparty:company:云南建设有限公司",
            counterparty_name: "云南建设有限公司",
            family: "company",
            family_label: "公司往来",
            pending_direction: "repayment",
            pending_direction_label: "待还款",
            pending_amount: "2000.00",
            row_span: 1,
            group_tone: "success",
            rows: [
              {
                relation_id: "rel-company-001",
                status: "confirmed",
                status_label: "人工确认",
                row_tone: "success",
                borrow_amount: "3000.00",
                borrow_date: "2026-05-02",
                borrow_direction: "income",
                repayment_amount: "1000.00",
                repayment_date: "2026-05-04",
                repayment_direction: "expense",
                counterparty_bank_name: "建行 8106",
                repayment_remark: "公司暂借款",
                interest_rate_type: "none",
                interest_rate_value: "0.000000",
                interest_paid_amount: "0.00",
                loan_days: 2,
                accrued_interest: "0.00",
                interest_paid_date: null,
                interest_payment_method: "",
                note: "",
                bank_row_ids: ["bank-company-001", "bank-company-002"],
              },
            ],
          },
        ];
        const groups = family === "all" ? allGroups : allGroups.filter((group) => group.family === family);
        const groupsWithLotRows = groups.map((group) => {
          const summaryRow = group.rows[0]
            ? {
              ...group.rows[0],
              row_kind: "summary",
              balance_amount: group.pending_amount,
            }
            : null;
          const lotRows = group.rows.map((row, index) => ({
            ...row,
            row_kind: "lot",
            lot_id: `${row.relation_id}-lot-${index + 1}`,
            parent_relation_id: row.relation_id,
            principal_bank_row_id: row.bank_row_ids[0] ?? "",
            settlement_bank_row_ids: row.bank_row_ids.slice(1),
            balance_amount: index === 0 ? group.pending_amount : "0.00",
          }));
          const flowRows = group.rows.flatMap((row, index) => {
            const baseFlow = {
              relation_id: row.relation_id,
              business_type: "borrow_in",
              counterparty_bank_name: row.counterparty_bank_name,
              summary_text: row.repayment_remark,
              allocation_status: "allocated",
              allocated_lot_ids: [`${row.relation_id}-lot-${index + 1}`],
            };
            return [
              {
                ...baseFlow,
                row_kind: "flow",
                flow_id: `bank:${row.bank_row_ids[0] ?? row.relation_id}`,
                source_bank_row_id: row.bank_row_ids[0] ?? "",
                transaction_at: row.borrow_date,
                flow_direction: row.borrow_direction,
                flow_amount: row.borrow_amount,
                borrow_amount: row.borrow_amount,
                borrow_date: row.borrow_date,
                borrow_direction: row.borrow_direction,
                repayment_amount: "0.00",
                repayment_date: null,
                repayment_direction: row.repayment_direction,
                category_label: `${group.family_label}：${group.pending_direction_label}`,
                bank_row_ids: row.bank_row_ids[0] ? [row.bank_row_ids[0]] : [],
              },
              {
                ...baseFlow,
                row_kind: "flow",
                flow_id: `bank:${row.bank_row_ids[1] ?? `${row.relation_id}:settlement`}`,
                source_bank_row_id: row.bank_row_ids[1] ?? "",
                transaction_at: row.repayment_date,
                flow_direction: row.repayment_direction,
                flow_amount: row.repayment_amount,
                borrow_amount: "0.00",
                borrow_date: null,
                borrow_direction: row.borrow_direction,
                repayment_amount: row.repayment_amount,
                repayment_date: row.repayment_date,
                repayment_direction: row.repayment_direction,
                category_label: `${group.family_label}：${row.repayment_date ? "已还款" : "待还款"}`,
                bank_row_ids: row.bank_row_ids[1] ? [row.bank_row_ids[1]] : [],
              },
            ].filter((flowRow) => flowRow.source_bank_row_id);
          });
          const allocationLots = lotRows.map((row) => ({
            ...row,
            row_kind: "allocation_lot",
            allocated_repayment_amount: row.repayment_amount,
          }));
          return {
            ...group,
            row_span: summaryRow ? 1 + flowRows.length : flowRows.length,
            summary_row: summaryRow,
            flow_rows: flowRows,
            allocation_lots: allocationLots,
            lot_rows: lotRows,
            rows: summaryRow ? [summaryRow] : [],
          };
        });
        return {
          body: {
            summary: {
              pending_repayment_amount: "2800.00",
              repaid_amount: "6200.00",
              pending_collection_amount: "0.00",
              collected_amount: "0.00",
              closed_amount: "5000.00",
              suggested_count: groupsWithLotRows.flatMap((group) => group.rows).filter((row) => row.status === "suggested").length,
              conflict_count: 0,
              row_count: groupsWithLotRows.reduce((sum, group) => sum + group.row_span, 0),
            },
            family_summaries: [
              { family: "personal", label: "个人往来", pending_amount: "800.00", closed_amount: "0.00", row_count: 1 },
              { family: "company", label: "公司往来", pending_amount: "2000.00", closed_amount: "1000.00", row_count: 1 },
              { family: "bank", label: "银行往来", pending_amount: "0.00", closed_amount: "5000.00", row_count: 1 },
              { family: "business", label: "业务往来", pending_amount: "0.00", closed_amount: "0.00", row_count: 0 },
            ],
            groups: groupsWithLotRows,
            pagination: {
              page,
              page_size: pageSize,
              total: groupsWithLotRows.length,
            },
          },
        };
      }
      return {
        body: {
          summary: {
            pending_repayment_amount: "2800.00",
            repaid_amount: "6200.00",
            pending_collection_amount: "0.00",
            collected_amount: "0.00",
            closed_amount: "5000.00",
            suggested_count: rows.filter((row) => row.status === "suggested").length,
            conflict_count: 0,
            row_count: rows.length,
          },
          family_summaries: [
            { family: "personal", label: "个人往来", pending_amount: "800.00", closed_amount: "0.00", row_count: 1 },
            { family: "company", label: "公司往来", pending_amount: "2000.00", closed_amount: "1000.00", row_count: 1 },
            { family: "bank", label: "银行往来", pending_amount: "0.00", closed_amount: "5000.00", row_count: 1 },
            { family: "business", label: "业务往来", pending_amount: "0.00", closed_amount: "0.00", row_count: 0 },
          ],
          rows,
          pagination: {
            page,
            page_size: pageSize,
            total: rows.length,
          },
        },
      };
    },
    "/api/turnover-ledger/export-preview": ({ url }) => {
      const family = url.searchParams.get("family") ?? "all";
      const scopeLabel = family === "all"
        ? "全部"
        : family === "personal"
          ? "个人往来"
          : family === "company"
            ? "公司往来"
            : family === "bank"
              ? "银行往来"
              : "业务往来";
      return {
        body: {
          file_name: `往来款台账-${scopeLabel}-2026-05-12.xlsx`,
          scope_label: scopeLabel,
          summary: {
            row_count: 1,
            pending_repayment_amount: family === "business" ? "0.00" : "2800.00",
            pending_collection_amount: family === "business" ? "8000.00" : "0.00",
            accrued_interest: "0.19",
          },
          columns: [
            "序号",
            "行类型",
            "批次 ID",
            "往来大类",
            "对方户名",
            "待还款金额",
            "待收款金额",
            "余额",
            "借款金额",
            "借款日",
            "还款金额",
            "还款日",
            "对方开户机构",
            "还款备注",
            "利率类型",
            "利率值",
            "已还利息额",
            "借款天数",
            "应还利息",
            "还利息日期",
            "还利息方式",
            "备注",
            "关系状态",
          ],
          rows: [
            {
              sequence_no: 1,
              row_type: "summary",
              lot_id: "",
              family_label: scopeLabel === "全部" ? "个人往来" : scopeLabel,
              counterparty_name: family === "business" ? "昆明客户" : "张三",
              pending_repayment_amount: family === "business" ? "0.00" : "800.00",
              pending_collection_amount: family === "business" ? "8000.00" : "0.00",
              balance_amount: family === "business" ? "8000.00" : "800.00",
              borrow_amount: family === "business" ? "8000.00" : "1000.00",
              borrow_date: "2026-05-01",
              repayment_amount: family === "business" ? "0.00" : "200.00",
              repayment_date: family === "business" ? null : "2026-05-03",
              counterparty_bank_name: family === "business" ? "招商银行" : "建行 8106",
              repayment_remark: family === "business" ? "" : "归还暂借款",
              interest_rate_type: family === "business" ? "none" : "annual",
              interest_rate_value: family === "business" ? "0.000000" : "0.035000",
              interest_paid_amount: "0.00",
              loan_days: family === "business" ? null : 2,
              accrued_interest: family === "business" ? "0.00" : "0.19",
              interest_paid_date: null,
              interest_payment_method: "",
              note: "",
              status_label: "待人工确认",
            },
          ],
        },
      };
    },
    "/api/turnover-ledger/export": ({ url }) => {
      const family = url.searchParams.get("family") ?? "all";
      const scopeLabel = family === "all" ? "全部" : family;
      return binaryResponse({
        body: `mock turnover ledger export ${scopeLabel}`,
        status: 200,
        headers: {
          "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "Content-Disposition": `attachment; filename="turnover-ledger-${scopeLabel}.xlsx"`,
        },
      });
    },
    "/api/turnover-ledger/relations/confirm": () => ({
      body: {
        relation_id: "rel-confirmed-personal",
        status: "confirmed",
      },
    }),
    "/api/workbench/actions/confirm-link/preview": ({ jsonBody }) => {
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      const caseId = typeof jsonBody?.case_id === "string" ? jsonBody.case_id : "preview:confirm";
      return {
        body: options.workbenchConfirmPreview
          ? cloneJson(options.workbenchConfirmPreview)
          : buildMockRelationPreview({
              operation: "confirm_link",
              month,
              rowIds,
              caseId,
              workbenchStateStore,
            }),
      };
    },
    "/api/workbench/actions/confirm-link": ({ jsonBody }) => {
      workbenchWriteActionCount += 1;
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      const touchedMonths = new Set(
        rowIds
          .map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month))
          .filter(Boolean) as string[],
      );
      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const rowId of rowIds) {
          moveWorkbenchGroup(payload, "unpaired", "paired", rowId);
        }
      }
      const body = {
        success: true,
        action: "confirm_link",
        month,
        affected_row_ids: rowIds,
        case_id: typeof jsonBody?.case_id === "string" ? jsonBody.case_id : undefined,
        affected_months: Array.from(touchedMonths),
        affected_scope_keys: Array.from(touchedMonths),
        message: `已确认 ${rowIds.length} 条记录关联。`,
      };
      return {
        body: options.transformWorkbenchConfirmActionResponse
          ? options.transformWorkbenchConfirmActionResponse(cloneJson(body))
          : body,
      };
    },
    "/api/workbench/actions/withdraw-link/preview": ({ jsonBody }) => {
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      return {
        body: options.workbenchWithdrawPreview
          ? cloneJson(options.workbenchWithdrawPreview)
          : buildMockRelationPreview({
              operation: "withdraw_link",
              month,
              rowIds,
              caseId: "preview:withdraw",
              workbenchStateStore,
            }),
      };
    },
    "/api/workbench/actions/withdraw-link": ({ jsonBody }) => {
      workbenchWriteActionCount += 1;
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      const touchedMonths = new Set(
        rowIds
          .map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month))
          .filter(Boolean) as string[],
      );
      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const rowId of rowIds) {
          withdrawWorkbenchGroup(payload, rowId);
        }
      }
      const body = {
        success: true,
        action: "withdraw_link",
        month,
        affected_row_ids: rowIds,
        restored_relations: [],
        changed_scopes: Array.from(touchedMonths),
        affected_scope_keys: Array.from(touchedMonths),
        message: "已撤回 1 组关联。",
      };
      return {
        body: options.transformWorkbenchWithdrawActionResponse
          ? options.transformWorkbenchWithdrawActionResponse(cloneJson(body))
          : body,
      };
    },
    "/api/workbench/exception/preview": ({ jsonBody }) => {
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      return {
        status: options.workbenchExceptionPreviewStatus ?? 200,
        body: options.workbenchExceptionPreview
          ? cloneJson(options.workbenchExceptionPreview)
          : buildDefaultWorkbenchExceptionPreview(rowIds),
      };
    },
    "/api/workbench/exception/apply": ({ jsonBody }) => {
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      const actionCode = String(jsonBody?.action_code ?? "workbench_exception");
      const actionLabel = actionCode === "wait_input_invoice" ? "追进项发票" : actionCode;
      const touchedMonths = new Set(
        rowIds.map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month)).filter(Boolean) as string[],
      );

      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const pane of ["oa", "bank", "invoice"] as const) {
          payload.unpaired[pane] = payload.unpaired[pane].map((row) => {
            if (!rowIds.includes(String(row.id))) {
              return row;
            }
            if (row.type === "oa") {
              return {
                ...row,
                handled_exception: true,
                oa_bank_relation: { code: actionCode, label: actionLabel, tone: "danger" },
                available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
              };
            }
            if (row.type === "bank") {
              return {
                ...row,
                handled_exception: true,
                invoice_relation: { code: actionCode, label: actionLabel, tone: "danger" },
                available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
              };
            }
            return {
              ...row,
              handled_exception: true,
              invoice_bank_relation: { code: actionCode, label: actionLabel, tone: "danger" },
              available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
            };
          });
        }
      }

      return {
        status: options.workbenchExceptionApplyStatus ?? 200,
        body: options.workbenchExceptionApply
          ? cloneJson(options.workbenchExceptionApply)
          : {
              success: true,
              case: { id: "EXC-MOCK-1" },
              pair_relation: null,
              updated_rows: rowIds.map((id) => ({ id })),
              affected_row_ids: rowIds,
              message: "已提交统一异常处理。",
            },
      };
    },
    "/api/workbench/actions/mark-exception": ({ jsonBody }) => ({
      body: {
        success: true,
        action: "mark_exception",
        month: String(jsonBody?.month ?? ""),
        affected_row_ids: [jsonBody?.row_id],
        updated_rows: [{ id: jsonBody?.row_id }],
        message: "已标记异常。",
      },
    }),
    "/api/workbench/actions/cancel-link": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowId = String(jsonBody?.row_id ?? "");
      const resolvedMonth = month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) ?? month : month;
      moveWorkbenchGroup(workbenchStateStore.get(resolvedMonth), "paired", "unpaired", rowId);
      return {
        body: {
          success: true,
          action: "cancel_link",
          month,
          affected_row_ids: [rowId],
          message: "已取消关联并回退为待处理。",
        },
      };
    },
    "/api/workbench/actions/update-bank-exception": ({ jsonBody }) => ({
      body: {
        success: true,
        action: "update_bank_exception",
        month: String(jsonBody?.month ?? ""),
        affected_row_ids: [jsonBody?.row_id],
        updated_rows: [{ id: jsonBody?.row_id }],
        message: "已更新银行异常分类。",
      },
    }),
    "/api/workbench/actions/cancel-exception": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const touchedMonths = new Set(
        rowIds.map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month)).filter(Boolean) as string[],
      );

      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const pane of ["oa", "bank", "invoice"] as const) {
          payload.unpaired[pane] = payload.unpaired[pane].map((row) => {
            if (!rowIds.includes(String(row.id))) {
              return row;
            }
            if (row.type === "oa") {
              return {
                ...row,
                handled_exception: false,
                oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
                available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
              };
            }
            if (row.type === "bank") {
              return {
                ...row,
                handled_exception: false,
                invoice_relation: { code: "pending_invoice_match", label: "待关联设备票", tone: "warn" },
                available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
              };
            }
            return {
              ...row,
              handled_exception: false,
              invoice_bank_relation: { code: "pending_collection", label: "待匹配流水", tone: "warn" },
              available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
            };
          });
        }
      }

      return {
        body: {
          success: true,
          action: "cancel_exception",
          month,
          affected_row_ids: rowIds,
          updated_rows: rowIds.map((id) => ({ id })),
          message: `已取消 ${rowIds.length} 条记录的异常处理。`,
        },
      };
    },
    "/api/workbench/actions/ignore-row": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowId = String(jsonBody?.row_id ?? "");
      const resolvedMonth = month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) ?? month : month;
      moveInvoiceToIgnored(workbenchStateStore.get(resolvedMonth), ignoredRowStore.get(resolvedMonth), rowId);
      return {
        body: {
          success: true,
          action: "ignore_row",
          month,
          affected_row_ids: [rowId],
          updated_rows: [{ id: rowId }],
          message: "已忽略 1 条记录。",
        },
      };
    },
    "/api/workbench/actions/unignore-row": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowId = String(jsonBody?.row_id ?? "");
      const resolvedMonth = month === "all" ? ignoredRowStore.resolveMonthForRow(rowId) ?? month : month;
      restoreIgnoredInvoice(workbenchStateStore.get(resolvedMonth), ignoredRowStore.get(resolvedMonth), rowId);
      return {
        body: {
          success: true,
          action: "unignore_row",
          month,
          affected_row_ids: [rowId],
          updated_rows: [{ id: rowId }],
          message: "已撤回忽略 1 条记录。",
        },
      };
    },
    "/imports/files/preview": ({ formData }) => {
      const fileNames = (formData?.getAll("files") as File[] | undefined)?.map((file) => file.name) ?? [];
      const rawOverrides = formData?.get("file_overrides");
      const overrides =
        typeof rawOverrides === "string"
          ? (JSON.parse(rawOverrides) as Array<Record<string, string>>)
          : [];
      latestImportSession = buildImportPreviewPayload(fileNames, overrides);
      return { body: latestImportSession };
    },
    "/imports/files/confirm": ({ jsonBody }) => {
      if (options.importConfirmPreviewStale) {
        return {
          status: 409,
          body: {
            error: "preview_stale",
          },
        };
      }
      const selectedIds = Array.isArray(jsonBody?.selected_file_ids)
        ? (jsonBody?.selected_file_ids as string[])
        : [];
      latestImportSession = {
        ...latestImportSession,
        session: {
          ...latestImportSession.session,
          status: "confirmed",
        },
        files: latestImportSession.files.map((file) => {
          if (selectedIds.includes(file.id)) {
            return {
              ...file,
              status: "confirmed",
              batch_id: file.preview_batch_id,
            };
          }
          if (file.status === "preview_ready") {
            return {
              ...file,
              status: "skipped",
              batch_id: null,
            };
          }
          return file;
        }),
      };
      return {
        body: {
          ...latestImportSession,
          operation_barrier_targets: options.importConfirmOperationBarrierTargets ?? [],
          matching_run: {
            id: "match_run_0001",
            triggered_by: "import_session:import_session_0001",
            result_count: 2,
            automatic_count: 1,
            suggested_count: 1,
            manual_review_count: 0,
          },
        },
      };
    },
    "/imports/files/retry": ({ jsonBody }) => {
      const selectedIds = Array.isArray(jsonBody?.selected_file_ids)
        ? (jsonBody.selected_file_ids as string[])
        : [];
      const overrides =
        jsonBody?.overrides && typeof jsonBody.overrides === "object"
          ? (jsonBody.overrides as Record<string, Record<string, string>>)
          : {};
      latestImportSession = {
        ...latestImportSession,
        session: {
          ...latestImportSession.session,
          status: "preview_ready",
        },
        files: latestImportSession.files.map((file) => {
          if (!selectedIds.includes(file.id)) {
            return file;
          }
          const override = overrides[file.id] ?? {};
          const fieldMapping = override.field_mapping && typeof override.field_mapping === "object"
            ? override.field_mapping as Record<string, string>
            : null;
          const isBankFile = override.batch_type === "bank_transaction" || file.batch_type === "bank_transaction";
          return {
            ...file,
            template_code: override.template_code ?? file.template_code ?? (isBankFile ? "bank_statement" : "invoice_export"),
            batch_type: override.batch_type ?? file.batch_type ?? (isBankFile ? "bank_transaction" : "input_invoice"),
            status: "preview_ready",
            message: "模板识别成功。",
            override_template_code: override.template_code ?? null,
            override_batch_type: override.batch_type ?? null,
            field_mapping: fieldMapping ?? file.field_mapping ?? {},
            mapping_source: fieldMapping ? "manual" : file.mapping_source ?? null,
          };
        }),
      };
      return { body: latestImportSession };
    },
    "/imports/files/discard": () => {
      latestImportSession = {
        ...latestImportSession,
        session: { ...latestImportSession.session, status: "reverted" },
        files: latestImportSession.files.map((file) => ({ ...file, status: "reverted" })),
      };
      return { body: latestImportSession };
    },
  };

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const url = new URL(rawUrl, "http://localhost");
    const jsonBody =
      typeof init?.body === "string" && init.body.length > 0
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;
    const formData = init?.body instanceof FormData ? init.body : null;
    const method = (init?.method ?? "GET").toUpperCase();

    const oaApplicantCredentialMatch = url.pathname.match(/^\/api\/workbench\/settings\/oa-applicant-credentials\/([^/]+)$/);
    if (oaApplicantCredentialMatch) {
      const targetApplicantCode = decodeURIComponent(oaApplicantCredentialMatch[1] ?? "");
      if (method === "PUT") {
        const credential = {
          targetApplicantCode,
          targetApplicantName: String(jsonBody?.targetApplicantName ?? "").trim(),
          oaUsername: String(jsonBody?.oaUsername ?? "").trim(),
          credentialStatus: "configured",
          hasCredential: Boolean(jsonBody?.password),
          enabled: true,
        };
        oaApplicantCredentialsState = [
          ...oaApplicantCredentialsState.filter((item) => item.targetApplicantCode !== targetApplicantCode),
          credential,
        ];
        return jsonResponse({
          body: {
            credential: cloneJson(credential),
          },
        });
      }
      if (method === "DELETE") {
        const existing = oaApplicantCredentialsState.find((item) => item.targetApplicantCode === targetApplicantCode);
        const credential = {
          targetApplicantCode,
          targetApplicantName: existing?.targetApplicantName ?? "",
          oaUsername: existing?.oaUsername ?? "",
          credentialStatus: "unconfigured",
          hasCredential: false,
          enabled: true,
        };
        oaApplicantCredentialsState = [
          ...oaApplicantCredentialsState.filter((item) => item.targetApplicantCode !== targetApplicantCode),
          credential,
        ];
        return jsonResponse({
          body: {
            credential: cloneJson(credential),
          },
        });
      }
    }

    if (method === "DELETE" && url.pathname.startsWith("/api/workbench/settings/projects/")) {
      const projectId = decodeURIComponent(url.pathname.split("/").pop() ?? "");
      workbenchSettingsState = {
        ...workbenchSettingsState,
        projects: {
          active: workbenchSettingsState.projects.active.filter((project) => project.id !== projectId),
          completed: workbenchSettingsState.projects.completed.filter((project) => project.id !== projectId),
          completed_project_ids: workbenchSettingsState.projects.completed_project_ids.filter((id) => id !== projectId),
        },
      };
      return jsonResponse({
        body: {
          settings: cloneJson(workbenchSettingsState),
        },
      });
    }
    const turnoverExtraMatch = url.pathname.match(/^\/api\/turnover-ledger\/relations\/([^/]+)\/extra$/);
    if (turnoverExtraMatch) {
      const relationId = decodeURIComponent(turnoverExtraMatch[1] ?? "");
      const currentExtra = turnoverExtraStore.get(relationId) ?? {
        relation_id: relationId,
        interest_rate_type: "none",
        interest_rate_value: "0.000000",
        interest_paid_amount: "0.00",
        interest_paid_date: null,
        interest_payment_method: "",
        note: "",
        updated_at: null,
        updated_by: "",
      };
      if ((init?.method ?? "GET").toUpperCase() === "PUT") {
        const nextExtra = {
          ...currentExtra,
          relation_id: relationId,
          interest_rate_type: jsonBody?.interest_rate_type ?? currentExtra.interest_rate_type,
          interest_rate_value: jsonBody?.interest_rate_value ?? currentExtra.interest_rate_value,
          interest_paid_amount: jsonBody?.interest_paid_amount ?? currentExtra.interest_paid_amount,
          interest_paid_date: jsonBody?.interest_paid_date ?? currentExtra.interest_paid_date,
          interest_payment_method: jsonBody?.interest_payment_method ?? currentExtra.interest_payment_method,
          note: jsonBody?.note ?? currentExtra.note,
          updated_at: "2026-05-12T10:00:00+08:00",
          updated_by: "mock-user",
        };
        turnoverExtraStore.set(relationId, nextExtra);
        return jsonResponse({
          body: {
            extra: nextExtra,
            row: {
              relation_id: relationId,
              status: "suggested",
              status_label: "待人工确认",
              row_tone: "warning",
              borrow_amount: "1000.00",
              borrow_date: "2026-05-01",
              borrow_direction: "income",
              repayment_amount: "200.00",
              repayment_date: "2026-05-03",
              repayment_direction: "expense",
              counterparty_bank_name: "建行 8106",
              repayment_remark: "归还暂借款",
              interest_rate_type: nextExtra.interest_rate_type,
              interest_rate_value: nextExtra.interest_rate_value,
              interest_paid_amount: nextExtra.interest_paid_amount,
              loan_days: 2,
              accrued_interest: nextExtra.interest_rate_type === "none" ? "0.00" : "0.19",
              interest_paid_date: nextExtra.interest_paid_date,
              interest_payment_method: nextExtra.interest_payment_method,
              note: nextExtra.note,
              bank_row_ids: ["bank-personal-001", "bank-personal-002"],
            },
          },
        });
      }
      return jsonResponse({ body: currentExtra });
    }

    const turnoverDetailMatch = url.pathname.match(/^\/api\/turnover-ledger\/relations\/([^/]+)$/);
    if (turnoverDetailMatch && turnoverDetailMatch[1] !== "confirm") {
      const relationId = decodeURIComponent(turnoverDetailMatch[1] ?? "");
      return jsonResponse({
        body: {
          relation: {
            relation_id: relationId,
            status: "suggested",
            status_label: "待人工确认",
            row_tone: "warning",
            chips: [
              { label: "待确认", tone: "warning" },
              { label: "未同步关联台", tone: "muted" },
            ],
            family: "personal",
            family_label: "个人往来",
            counterparty_name: "张三",
            principal_amount: "1000.00",
            settled_amount: "200.00",
            balance_amount: "800.00",
            first_transaction_at: "2026-05-01 10:00:00",
            last_settlement_at: "2026-05-03 10:00:00",
            bank_account_labels: ["建行 8106"],
            summary_text: "暂借款",
            annual_interest_rate: "3.50%",
            loan_days: 2,
            accrued_interest: "0.19",
            sync_to_workbench: false,
            bank_row_ids: ["bank-personal-001", "bank-personal-002"],
            category_codes: ["borrow_in_personal_pending_repayment", "borrow_in_personal_repaid"],
            business_type: "borrow_in",
          },
          bank_rows: [
            {
              id: "bank-personal-001",
              trade_time: "2026-05-01 10:00:00",
              counterparty_name: "张三",
              direction_label: "收",
              amount: "1000.00",
              bank_account_label: "建行 8106",
              summary: "暂借款",
              purpose: "借款",
              category_label: "个人暂借款：待还款",
            },
            {
              id: "bank-personal-002",
              trade_time: "2026-05-03 10:00:00",
              counterparty_name: "张三",
              direction_label: "支",
              amount: "200.00",
              bank_account_label: "建行 8106",
              summary: "归还暂借款",
              purpose: "还款",
              category_label: "个人暂借款：已还款",
            },
          ],
          audit_history: [{ action: "generated", note: "system" }],
        },
      });
    }

    const turnoverWithdrawMatch = url.pathname.match(/^\/api\/turnover-ledger\/relations\/([^/]+)\/withdraw$/);
    if (turnoverWithdrawMatch) {
      return jsonResponse({
        body: {
          relation_id: decodeURIComponent(turnoverWithdrawMatch[1] ?? ""),
          status: "withdrawn",
        },
      });
    }

    if (url.pathname.startsWith("/api/workbench/rows/")) {
      return jsonResponse({ body: buildWorkbenchDetail(url.pathname.split("/").pop() ?? "") });
    }
    if (url.pathname.startsWith("/api/operations/history/") && url.pathname !== "/api/operations/history/actors") {
      return jsonResponse({
        body: {
          operation: {
            operation_key: decodeURIComponent(url.pathname.split("/").pop() ?? ""),
            event_id: "event-1",
            request_id: "request-1",
            trace_id: "trace-1",
            object_id: "internal-relation-1",
            actor_id: "005",
            actor_name: "权限管理员",
            actor_account: "YNSYLP005",
            page_key: "reconciliation-workbench",
            action_label: "确认关联",
            object_type: "reconciliation_case",
            started_at: "2026-08-09T12:00:00+08:00",
            completed_at: "2026-08-09T12:00:01+08:00",
            occurred_at: "2026-08-09T12:00:00+08:00",
            outcome: "success",
            reason: "确认关联",
            items: [{
              item_key: "item-1",
              type: "银行流水",
              title: "云南昂超商贸有限公司",
              secondary: "设备采购",
              amount: "2200.00",
              date: "2026-06-08T10:14:33+08:00",
              before_status: "未配对",
              after_status: "已配对",
            }],
          },
        },
      });
    }
    if (url.pathname.startsWith("/api/cost-statistics/transactions/")) {
      if (costDetailFailuresRemaining > 0) {
        costDetailFailuresRemaining -= 1;
        return jsonResponse({
          status: 503,
          body: { error: "cost_statistics_detail_unavailable" },
        });
      }
      if (options.costDetailDelayMs) {
        await new Promise((resolve) => window.setTimeout(resolve, options.costDetailDelayMs));
      }
      const transactionId = url.pathname.split("/").pop() ?? "";
      return jsonResponse(buildCostStatisticsTransactionPayload(transactionId));
    }
    if (url.pathname === "/imports/files/sessions") {
      const isActive = ["preview_ready", "preview_ready_with_errors"].includes(latestImportSession.session.status);
      return jsonResponse({
        body: {
          sessions: isActive && latestImportSession.files.length > 0
            ? [{
                session_id: latestImportSession.session.id,
                imported_by: latestImportSession.session.imported_by,
                file_count: latestImportSession.session.file_count,
                batch_type: latestImportSession.files[0]?.batch_type,
                created_at: latestImportSession.session.created_at,
                updated_at: latestImportSession.session.created_at,
                status: "awaiting_confirmation",
              }]
            : [],
        },
      });
    }
    if (url.pathname.startsWith("/imports/files/sessions/")) {
      return jsonResponse({ body: latestImportSession });
    }
    const etcBusinessBatchRoute = url.pathname.match(/^\/api\/etc\/business-batches\/([^/]+)(?:\/([^/]+)(?:\/([^/]+))?)?$/);
    if (etcBusinessBatchRoute) {
      const businessBatchId = decodeURIComponent(etcBusinessBatchRoute[1] ?? "");
      const segment = etcBusinessBatchRoute[2] ? decodeURIComponent(etcBusinessBatchRoute[2]) : "";
      const trailing = etcBusinessBatchRoute[3] ? decodeURIComponent(etcBusinessBatchRoute[3]) : "";
      if (!segment && method === "GET") {
        const batch = etcInvoiceStore.businessBatchDetail(businessBatchId);
        return batch
          ? jsonResponse({ body: { ok: true, data: { businessBatch: batch }, error: null } })
          : jsonResponse({ status: 404, body: { ok: false, data: null, error: { code: "business_batch_not_found", message: "ETC业务批次不存在。" } } });
      }
      if (!segment && method === "PATCH") {
        const result = etcInvoiceStore.updateBusinessBatchTitle(businessBatchId, String(jsonBody?.title ?? ""));
        const updatedBatch = (result.body as { data?: { businessBatch?: Record<string, unknown> | null } }).data?.businessBatch;
        const taskId = String(updatedBatch?.task_id ?? updatedBatch?.taskId ?? "");
        if (result.status === 200 && taskId) {
          etcReconciliationTaskStore.updateTitle(taskId, String(jsonBody?.title ?? ""));
        }
        return jsonResponse({ status: result.status, body: result.body });
      }
      if (!segment && method === "DELETE") {
        const beforeDelete = etcInvoiceStore.businessBatchDetail(businessBatchId);
        const deleted = etcInvoiceStore.deleteBatch(businessBatchId, { allowSubmitted: true });
        if (deleted || businessBatchId.startsWith("etc_business_batch_")) {
          const kind = beforeDelete?.status === "oa_submitted" ? "submitted_business_batch_reset" : "business_batch";
          return jsonResponse({ body: { ok: true, data: { deleted: true, businessBatchId, kind }, error: null } });
        }
        return jsonResponse({ status: 409, body: { ok: false, data: null, error: { code: "invalid_status_transition", message: "ETC业务批次不能删除。" } } });
      }
      if (method === "POST" && segment === "oa-draft" && !trailing) {
        const batch = etcInvoiceStore.businessBatchDraft(businessBatchId);
        return batch
          ? jsonResponse({ body: { ok: true, data: { businessBatch: batch }, error: null } })
          : jsonResponse({ status: 404, body: { ok: false, data: null, error: { message: "ETC业务批次不存在。" } } });
      }
      if (method === "POST" && segment === "oa-draft" && trailing === "revoke") {
        const batch = etcInvoiceStore.businessBatchDetail(businessBatchId);
        return batch
          ? jsonResponse({ body: { ok: true, data: { businessBatch: { ...batch, status: "not_submitted", version: 9 } }, error: null } })
          : jsonResponse({ status: 404, body: { ok: false, data: null, error: { message: "ETC业务批次不存在。" } } });
      }
      if (method === "POST" && segment === "manual-oa-status") {
        const batch = etcInvoiceStore.businessBatchDetail(businessBatchId);
        const decision = String(jsonBody?.decision ?? "");
        return batch
          ? jsonResponse({ body: { ok: true, data: { businessBatch: { ...batch, status: decision === "submitted" ? "manually_marked_submitted" : "manually_marked_not_submitted", version: 9 } }, error: null } })
          : jsonResponse({ status: 404, body: { ok: false, data: null, error: { message: "ETC业务批次不存在。" } } });
      }
    }
    if (url.pathname === "/api/etc/reconciliation-tasks/ready-for-import") {
      return jsonResponse({ body: etcReconciliationTaskStore.ready() });
    }
    const etcReconciliationTaskRoute = url.pathname.match(/^\/api\/etc\/reconciliation-tasks\/([^/]+)(?:\/([^/]+)(?:\/([^/]+))?)?$/);
    if (etcReconciliationTaskRoute) {
      const taskId = decodeURIComponent(etcReconciliationTaskRoute[1] ?? "");
      const segment = etcReconciliationTaskRoute[2] ? decodeURIComponent(etcReconciliationTaskRoute[2]) : "";
      const trailing = etcReconciliationTaskRoute[3] ? decodeURIComponent(etcReconciliationTaskRoute[3]) : "";
      if (!segment && method === "GET") {
        const task = etcReconciliationTaskStore.get(taskId);
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
      if (!segment && method === "DELETE") {
        const result = etcReconciliationTaskStore.deleteTask(taskId, Number(jsonBody?.expectedVersion ?? jsonBody?.expected_version ?? 0));
        return jsonResponse({ status: result.status, body: result.body });
      }
      if (method === "DELETE" && segment === "imported-invoices") {
        const currentTask = etcReconciliationTaskStore.get(taskId);
        const importedBatchId = String(
          (currentTask as Record<string, unknown> | null)?.etcBatchId
          ?? (currentTask as Record<string, unknown> | null)?.etc_batch_id
          ?? "",
        );
        const result = etcReconciliationTaskStore.clearImportedInvoices(
          taskId,
          Number(jsonBody?.expectedVersion ?? jsonBody?.expected_version ?? 0),
        );
        if (result.ok && importedBatchId) {
          etcInvoiceStore.deleteBatch(importedBatchId);
        }
        return jsonResponse({ status: result.status, body: result.body });
      }
      if (method === "POST" && segment === "supplement-evidences" && trailing) {
        const task = etcReconciliationTaskStore.uploadSupplementForCard(taskId, trailing);
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
      if (method === "POST" && ["credit-card-statement", "ticket-root-files", "ticket-root-texts", "supplement-evidences"].includes(segment)) {
        const task = etcReconciliationTaskStore.upload(taskId);
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
      if (method === "PATCH" && segment === "items" && trailing) {
        const task = etcReconciliationTaskStore.patchItem(taskId, trailing, jsonBody ?? {});
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
      if (method === "POST" && segment === "confirm") {
        const task = etcReconciliationTaskStore.confirm(taskId);
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
      if (method === "POST" && segment === "reopen") {
        const task = etcReconciliationTaskStore.reopen(taskId);
        return task
          ? jsonResponse({ body: task })
          : jsonResponse({ status: 404, body: { message: "ETC对账任务不存在。" } });
      }
    }
    if (url.pathname === "/api/workbench/settings/data-reset/preview") {
      const action = url.searchParams.get("action") ?? "reset_bank_transactions";
      return jsonResponse({
        body: {
          preview: {
            action,
            impact_counts: { bank_transactions: 2 },
            impact_fingerprint: "a".repeat(64),
            recovery_ready: true,
            recovery_receipt_id: "00000000-0000-0000-0000-000000000001",
            recovery_valid_until: "2026-08-09T12:00:00+08:00",
          },
        },
      });
    }
    if ((init?.method ?? "GET").toUpperCase() === "POST" && url.pathname === "/api/workbench/settings/data-reset/jobs") {
      if (options.dataResetPasswordShouldFail || !jsonBody?.oa_password) {
        return jsonResponse({
          status: 403,
          body: {
            error: "oa_password_verification_failed",
            message: "当前 OA 用户密码复核失败，未执行数据重置。",
          },
        });
      }
      const action = String(jsonBody.action ?? "");
      const jobId = `mock-reset-job-${dataResetJobs.size + 1}`;
      const job = {
        job_id: jobId,
        action,
        status: "running",
        phase: "clear",
        message: "正在清理 app 内部状态。",
        current: 25,
        total: 100,
        percent: 25,
        result: null,
        error: null,
      };
      dataResetJobs.set(jobId, job);
      return jsonResponse({ status: 202, body: { job } });
    }
    if (url.pathname === "/api/workbench/settings/data-reset/jobs/active") {
      const activeJob = Array.from(dataResetJobs.values()).find((job) => {
        const status = String(job.status ?? "");
        return status === "queued" || status === "running";
      }) ?? null;
      return jsonResponse({ body: { job: activeJob } });
    }
    if (url.pathname.startsWith("/api/workbench/settings/data-reset/jobs/")) {
      const jobId = decodeURIComponent(url.pathname.split("/").pop() ?? "");
      const existing = dataResetJobs.get(jobId);
      const action = String(existing?.action ?? "reset_bank_transactions");
      const currentPollCount = Number(existing?.poll_count ?? 0) + 1;
      const pollsBeforeComplete = options.dataResetJobPollsBeforeComplete ?? 0;
      if (existing && currentPollCount <= pollsBeforeComplete) {
        const runningJob = {
          ...existing,
          poll_count: currentPollCount,
          status: "running",
        };
        dataResetJobs.set(jobId, runningJob);
        return jsonResponse({ body: { job: runningJob } });
      }
      const job = {
        job_id: jobId,
        action,
        status: "completed",
        phase: "complete",
        message: "已完成数据重置。",
        current: 100,
        total: 100,
        percent: 100,
        result: {
          action,
          status: "completed",
          cleared_collections: ["workbench_row_overrides", "workbench_pair_relations"],
          deleted_counts: {
            workbench_row_overrides: 0,
            workbench_pair_relations: 0,
          },
          protected_targets: ["form_data_db.form_data"],
          rebuild_status: action === "reset_oa_and_rebuild" ? "completed" : "not_applicable",
          message: "已完成数据重置。",
        },
        error: null,
      };
      dataResetJobs.set(jobId, job);
      return jsonResponse({ body: { job } });
    }
    if (
      (init?.method ?? "GET").toUpperCase() === "POST"
      && url.pathname.startsWith("/api/background-jobs/")
      && url.pathname.endsWith("/acknowledge")
    ) {
      if (options.backgroundJobAcknowledgeStatus) {
        return jsonResponse({
          status: options.backgroundJobAcknowledgeStatus,
          body: options.backgroundJobAcknowledgeBody ?? { message: "acknowledge failed" },
        });
      }
      const jobId = decodeURIComponent(url.pathname.split("/")[3] ?? "");
      backgroundJobs = backgroundJobs.filter((job) => String(job.job_id ?? job.jobId ?? "") !== jobId);
      return jsonResponse({
        body: {
          job: {
            job_id: jobId,
            status: "acknowledged",
          },
        },
      });
    }
    if (
      (init?.method ?? "GET").toUpperCase() === "POST"
      && url.pathname.startsWith("/api/background-jobs/")
      && url.pathname.endsWith("/retry")
    ) {
      if (options.backgroundJobRetryStatus) {
        return jsonResponse({
          status: options.backgroundJobRetryStatus,
          body: options.backgroundJobRetryBody ?? { message: "retry failed" },
        });
      }
      const jobId = decodeURIComponent(url.pathname.split("/")[3] ?? "");
      backgroundJobs = backgroundJobs.filter((job) => String(job.job_id ?? job.jobId ?? "") !== jobId);
      return jsonResponse({
        body: {
          job: {
            job_id: `retry_${jobId}`,
            type: "workbench_matching",
            status: "queued",
            label: "生成正式配对关系",
          },
        },
      });
    }
    if (
      url.pathname.startsWith("/api/bank-details/transactions/")
      && (
        url.pathname.endsWith("/category-confirmation")
        || url.pathname.endsWith("/category-assignment")
      )
    ) {
      if (
        url.pathname === "/api/bank-details/transactions/bank-detail-search-filler/category-assignment"
        && String(init?.method || "GET").toUpperCase() === "DELETE"
      ) {
        bankDetailManualAssignmentActive = false;
      }
      return jsonResponse({
        body: {
          changed: true,
          affected_months: ["2026-04"],
        },
      });
    }

    const handler = handlers[url.pathname];
    if (!handler) {
      throw new Error(`Unhandled fetch mock for ${url.pathname}`);
    }

    if (options.emptyBodyPaths?.includes(url.pathname)) {
      return {
        ok: false,
        status: 500,
        json: async () => JSON.parse(""),
        text: async () => "",
      } as Response;
    }

    const response = await handler({ url, init, jsonBody, formData });
    if (options.costExplorerDelayMs && url.pathname === "/api/cost-statistics/explorer") {
      await new Promise((resolve) => window.setTimeout(resolve, options.costExplorerDelayMs));
    }
    const isWorkbenchReadPath =
      url.pathname === "/api/workbench"
      || url.pathname === "/api/workbench/groups"
      || url.pathname === "/api/workbench/filter-options"
      || url.pathname === "/api/workbench/ignored"
      || url.pathname === "/api/workbench/settings";
    const workbenchSpecificDelay =
      (url.pathname === "/api/workbench" ? options.workbenchPrimaryDelayMs : undefined)
      ?? (url.pathname === "/api/workbench/ignored" ? options.workbenchIgnoredDelayMs : undefined)
      ?? (url.pathname === "/api/workbench/settings" ? options.workbenchSettingsDelayMs : undefined);
    const workbenchDelay =
      options.workbenchBackgroundLoadDelayMs && workbenchWriteActionCount > 0 && isWorkbenchReadPath
        ? options.workbenchBackgroundLoadDelayMs
        : workbenchSpecificDelay;

    if (workbenchDelay) {
      await new Promise((resolve) => window.setTimeout(resolve, workbenchDelay));
    } else if (
      options.workbenchLoadDelayMs
      && isWorkbenchReadPath
    ) {
      await new Promise((resolve) => window.setTimeout(resolve, options.workbenchLoadDelayMs));
    }
    const importPreviewDelay =
      (url.pathname === "/imports/files/preview" ? options.importPreviewDelayMs : undefined)
      ?? (url.pathname === "/api/etc/import/preview" ? options.etcImportPreviewDelayMs : undefined);
    if (importPreviewDelay) {
      await new Promise((resolve) => window.setTimeout(resolve, importPreviewDelay));
    }
    const workbenchExceptionDelay =
      (url.pathname === "/api/workbench/exception/preview" ? options.workbenchExceptionPreviewDelayMs : undefined)
      ?? (url.pathname === "/api/workbench/exception/apply" ? options.workbenchExceptionApplyDelayMs : undefined);
    if (workbenchExceptionDelay) {
      await new Promise((resolve) => window.setTimeout(resolve, workbenchExceptionDelay));
    }
    if (isBinaryLikeResponse(response)) {
      if (options.actionDelayMs && url.pathname.startsWith("/api/workbench/actions/")) {
        await new Promise((resolve) => window.setTimeout(resolve, options.actionDelayMs));
      }
      return response;
    }
    if (
      options.actionDelayMs
      && (url.pathname.startsWith("/api/workbench/actions/") || url.pathname.startsWith("/api/workbench/exception/"))
    ) {
      await new Promise((resolve) => window.setTimeout(resolve, options.actionDelayMs));
    }
    return jsonResponse(response);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
