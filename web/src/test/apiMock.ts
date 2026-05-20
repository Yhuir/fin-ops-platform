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
  taxErrorMonths?: string[];
  costErrorMonths?: string[];
  costExportErrorViews?: string[];
  sessionMode?: "authorized" | "forbidden" | "expired" | "error";
  sessionAccessTier?: "admin" | "full_access" | "read_export_only" | "denied";
  sessionUsername?: string;
  sessionDisplayName?: string;
  actionDelayMs?: number;
  workbenchLoadDelayMs?: number;
  workbenchPrimaryDelayMs?: number;
  workbenchIgnoredDelayMs?: number;
  workbenchSettingsDelayMs?: number;
  importPreviewDelayMs?: number;
  etcImportPreviewDelayMs?: number;
  importConfirmPreviewStale?: boolean;
  etcImportConfirmPreviewStale?: boolean;
  etcImportConfirmStaleReconciliationTask?: boolean;
  etcImportBlockingIssues?: Array<Record<string, unknown>>;
  readyEtcReconciliationTasks?: Array<Record<string, unknown>>;
  workbenchColumnLayouts?: {
    oa?: string[];
    bank?: string[];
    invoice?: string[];
  };
  searchDelayMs?: number;
  searchErrorQueries?: string[];
  emptyBodyPaths?: string[];
  workbenchOaStatus?: {
    code: "idle" | "loading" | "ready" | "error";
    message: string;
  };
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
  workbenchExceptionPreview?: Record<string, unknown>;
  workbenchExceptionApply?: Record<string, unknown>;
  workbenchExceptionPreviewStatus?: number;
  workbenchExceptionApplyStatus?: number;
  workbenchExceptionPreviewDelayMs?: number;
  workbenchExceptionApplyDelayMs?: number;
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
    template_code: "icbc_historydetail",
    label: "工商银行流水",
    file_extensions: [".xlsx"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["[HISTORYDETAIL]", "交易时间", "对方单位"],
  },
  {
    template_code: "ceb_transaction_detail",
    label: "光大银行流水",
    file_extensions: [".xls"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["交易日期", "交易时间", "借方发生额"],
  },
  {
    template_code: "ccb_transaction_detail",
    label: "建设银行流水",
    file_extensions: [".xls"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["账号", "账户名称", "借方发生额（支取）"],
  },
  {
    template_code: "cmbc_transaction_detail",
    label: "民生银行流水",
    file_extensions: [".xlsx"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["交易时间", "交易流水号", "借方发生额"],
  },
  {
    template_code: "pingan_transaction_detail",
    label: "平安银行流水",
    file_extensions: [".xlsx"],
    record_type: "bank_transaction",
    allowed_batch_types: ["bank_transaction"],
    required_headers: ["交易时间", "收入", "支出"],
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

function createEtcInvoiceStore() {
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

  const getBatchInvoiceIds = (batch: (typeof batches)[number]) => (
    "invoice_ids" in batch ? batch.invoice_ids : batch.invoiceIds
  ) ?? [];

  const invoicesForBatch = (batch: (typeof batches)[number]) => {
    const invoiceIds = new Set(getBatchInvoiceIds(batch));
    return invoices.filter((invoice) => invoiceIds.has(invoice.id));
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
    const isSubmitted = batch.status === "submitted";
    return {
      business_batch_id: batchId,
      task_id: batchId === "etc-batch-unsubmitted-01" ? "etc-recon-task-001" : "",
      status: isSubmitted ? "oa_submitted" : "imported",
      version: 7,
      owner_user_id: "web_finance_user",
      owner_org_id: "finance",
      import_batch_ids: [`${batchId}-import-001`],
      submission_batch_id: isSubmitted ? batchId : "",
      external_etc_batch_id: hydrated.external_batch_id ?? hydrated.externalBatchId ?? hydrated.etc_batch_id ?? hydrated.etcBatchId,
      oa_draft_id: "",
      oa_draft_url: "",
      oa_row_id: hydrated.linked_oa_row_id ?? hydrated.linkedOaRowId ?? "",
      oa_process_status: isSubmitted ? "in_progress" : "",
      invoice_summary: {
        count: hydrated.invoice_count,
        amount: hydrated.total_amount,
      },
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
      created_at: "2026-05-19T09:00:00+08:00",
      updated_at: "2026-05-19T09:00:00+08:00",
      ...(includeInvoices ? { invoice_items: hydrated.invoice_items } : {}),
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
    listBatches({ status, month, plate, keyword }: { status?: string | null; month?: string | null; plate?: string | null; keyword?: string | null }) {
      const normalizedKeyword = String(keyword ?? "").trim();
      const normalizedPlate = String(plate ?? "").trim();
      const rows = batches
        .filter((batch) => {
          if (status && batch.status !== status) {
            return false;
          }
          const items = invoicesForBatch(batch);
          if (month && !items.some((invoice) => invoice.issue_date.startsWith(month))) {
            return false;
          }
          if (normalizedPlate && !items.some((invoice) => invoice.plate_number.includes(normalizedPlate))) {
            return false;
          }
          if (normalizedKeyword) {
            const searchable = [
              "etc_batch_id" in batch ? batch.etc_batch_id : batch.etcBatchId,
              "external_batch_id" in batch ? batch.external_batch_id : batch.externalBatchId,
              "linked_oa_row_id" in batch ? batch.linked_oa_row_id : batch.linkedOaRowId,
              "linked_oa_applicant" in batch ? batch.linked_oa_applicant : batch.linkedOaApplicant,
              ...items.map((invoice) => `${invoice.invoice_number} ${invoice.seller_name} ${invoice.plate_number}`),
            ].join(" ");
            if (!searchable.includes(normalizedKeyword)) {
              return false;
            }
          }
          return true;
        })
        .map((batch) => hydrateBatch(batch));
      return {
        counts: batchCounts(),
        items: cloneJson(rows),
        pagination: {
          page: 1,
          page_size: 100,
          total: rows.length,
        },
      };
    },
    listBusinessBatches({ status, month, plate, keyword }: { status?: string | null; month?: string | null; plate?: string | null; keyword?: string | null }) {
      const normalizedStatus = status === "active" ? "unsubmitted" : status === "submitted" ? "submitted" : null;
      const normalizedKeyword = String(keyword ?? "").trim();
      const normalizedPlate = String(plate ?? "").trim();
      const rows = batches
        .filter((batch) => {
          if (normalizedStatus && batch.status !== normalizedStatus) {
            return false;
          }
          const items = invoicesForBatch(batch);
          if (month && !items.some((invoice) => invoice.issue_date.startsWith(month))) {
            return false;
          }
          if (normalizedPlate && !items.some((invoice) => invoice.plate_number.includes(normalizedPlate))) {
            return false;
          }
          if (normalizedKeyword) {
            const searchable = [
              "etc_batch_id" in batch ? batch.etc_batch_id : batch.etcBatchId,
              "external_batch_id" in batch ? batch.external_batch_id : batch.externalBatchId,
              ...items.map((invoice) => `${invoice.invoice_number} ${invoice.seller_name} ${invoice.plate_number}`),
            ].join(" ");
            return searchable.includes(normalizedKeyword);
          }
          return true;
        })
        .map((batch) => hydrateBusinessBatch(batch))
        .filter(Boolean);
      return {
        ok: true,
        data: {
          counts: {
            active: batches.filter((batch) => batch.status !== "submitted").length,
            submitted: batches.filter((batch) => batch.status === "submitted").length,
          },
          items: cloneJson(rows),
          pagination: {
            page: 1,
            page_size: 100,
            total: rows.length,
          },
        },
        error: null,
      };
    },
    batchDetail(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      return batch ? cloneJson(hydrateBatch(batch, true)) : null;
    },
    businessBatchDetail(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      return batch ? cloneJson(hydrateBusinessBatch(batch, true)) : null;
    },
    businessBatchDraft(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      if (!batch) {
        return null;
      }
      return {
        ...hydrateBusinessBatch(batch, true),
        status: "oa_submission_detecting",
        version: 8,
        submission_batch_id: "etc_batch_0027",
        oa_draft_id: "oa_draft_001",
        oa_draft_url: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
      };
    },
    deleteBatch(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      if (!batch || batch.status !== "unsubmitted") {
        return false;
      }
      batches = batches.filter((item) => item.id !== batchId);
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
    markSubmitted(invoiceIds: string[]) {
      invoices = invoices.map((invoice) =>
        invoiceIds.includes(invoice.id)
          ? { ...invoice, status: "submitted" as const }
          : invoice,
      );
    },
    markUnsubmitted(invoiceIds: string[]) {
      invoices = invoices.map((invoice) =>
        invoiceIds.includes(invoice.id)
          ? { ...invoice, status: "unsubmitted" as const }
          : invoice,
      );
    },
    markBatchSubmitted(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      if (!batch) {
        return;
      }
      const invoiceIds = getBatchInvoiceIds(batch);
      invoices = invoices.map((invoice) =>
        invoiceIds.includes(invoice.id)
          ? { ...invoice, status: "submitted" as const }
          : invoice,
      );
      batches = batches.map((item) =>
        item.id === batchId
          ? { ...item, status: "submitted" as const }
          : item,
      );
    },
    markBatchUnsubmitted(batchId: string) {
      const batch = batches.find((item) => item.id === batchId);
      if (!batch) {
        return;
      }
      const invoiceIds = getBatchInvoiceIds(batch);
      invoices = invoices.map((invoice) =>
        invoiceIds.includes(invoice.id)
          ? { ...invoice, status: "unsubmitted" as const }
          : invoice,
      );
      batches = batches.map((item) =>
        item.id === batchId
          ? { ...item, status: "unsubmitted" as const }
          : item,
      );
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
      templateCode: "icbc_historydetail",
      bankName: "工商银行",
      last4: "4080",
    };
  }
  if (fileName.includes("交易明细")) {
    return {
      templateCode: "pingan_transaction_detail",
      bankName: "平安银行",
      last4: "0093",
    };
  }
  if (fileName.includes("民生")) {
    return {
      templateCode: "cmbc_transaction_detail",
      bankName: "民生银行",
      last4: "9486",
    };
  }
  if (fileName.includes("光大")) {
    return {
      templateCode: "ceb_transaction_detail",
      bankName: "光大银行",
      last4: "8826",
    };
  }
  return {
    templateCode: "pingan_transaction_detail",
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

function buildWorkbenchPayload(month: string, oaStatus?: MockApiOptions["workbenchOaStatus"]) {
  return toGroupedWorkbenchPayload(buildWorkbenchRowPayload(month), oaStatus);
}

type RawWorkbenchPayload = ReturnType<typeof buildWorkbenchRowPayload>;
type RawWorkbenchSectionKey = "paired" | "open";
type RawWorkbenchPaneKey = "oa" | "bank" | "invoice";
type RawWorkbenchRow = RawWorkbenchPayload["paired"][RawWorkbenchPaneKey][number];

function buildWorkbenchRowPayload(month: string) {
  if (month === "2026-04") {
    return {
      month,
      summary: {
        oa_count: 2,
        bank_count: 2,
        invoice_count: 2,
        paired_count: 3,
        open_count: 3,
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
      open: {
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
        open_count: 0,
        exception_count: 0,
      },
      paired: { oa: [], bank: [], invoice: [] },
      open: { oa: [], bank: [], invoice: [] },
    };
  }

  return {
    month,
    summary: {
      oa_count: 5,
      bank_count: 4,
      invoice_count: 4,
      paired_count: 3,
      open_count: 10,
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
    open: {
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
          project_name: "2024-2026年度红塔集团工作证管理系统维护项目",
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
        {
          id: "pay-oa-2035-etc-25",
          type: "invoice",
          source_kind: "oa_attachment_payment_receipt",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          seller_tax_no: "",
          seller_name: "微信支付",
          buyer_tax_no: "",
          buyer_name: "胡瑢",
          issue_date: "2026-03-04",
          amount: "25.00",
          tax_rate: "",
          tax_amount: "",
          total_with_tax: "25.00",
          invoice_type: "付款凭证",
          invoice_bank_relation: { code: "evidence_only", label: "附件凭证", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            交易单号: "WX2035ETC25",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "0",
            source_expense_item_id: "oa-exp-2035:item:0",
            source_attachment_name: "微信支付过路费25.png",
            source_attachment_key: "oa-exp-2035/item-0/wechat-toll-25.png",
          },
        },
        {
          id: "pay-oa-2035-etc-23",
          type: "invoice",
          source_kind: "oa_attachment_payment_receipt",
          case_id: "CASE-202603-OA-ATTACHMENT-2035",
          seller_tax_no: "",
          seller_name: "微信支付",
          buyer_tax_no: "",
          buyer_name: "胡瑢",
          issue_date: "2026-03-04",
          amount: "23.00",
          tax_rate: "",
          tax_amount: "",
          total_with_tax: "23.00",
          invoice_type: "付款凭证",
          invoice_bank_relation: { code: "evidence_only", label: "附件凭证", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            交易单号: "WX2035ETC23",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "0",
            source_expense_item_id: "oa-exp-2035:item:0",
            source_attachment_name: "微信支付过路费23.png",
            source_attachment_key: "oa-exp-2035/item-0/wechat-toll-23.png",
          },
        },
        {
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
          tax_rate: "",
          tax_amount: "",
          total_with_tax: "200.00",
          invoice_type: "付款凭证",
          invoice_bank_relation: { code: "evidence_only", label: "附件凭证", tone: "warn" },
          available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
          detail_fields: {
            交易单号: "WX2035FUEL200",
            derived_from_oa_id: "oa-exp-2035",
            source_expense_row_index: "1",
            source_expense_item_id: "oa-exp-2035:item:1",
            source_attachment_name: "微信支付加油200.png",
            source_attachment_key: "oa-exp-2035/item-1/wechat-fuel-200.png",
          },
        },
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
    open_count: number;
    exception_count: number;
  };
  paired: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>;
  open: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>;
}, oaStatus?: MockApiOptions["workbenchOaStatus"]) {
  const pairedGroups = buildGroups(payload.paired, "paired");
  const openGroups = buildGroups(payload.open, "open");

  return {
    month: payload.month,
    oa_status: oaStatus ?? { code: "ready", message: "OA 已同步" },
    summary: {
      oa_count: payload.summary.oa_count,
      bank_count: payload.summary.bank_count,
      invoice_count: payload.summary.invoice_count,
      paired_count: pairedGroups.length,
      open_count: openGroups.length,
      exception_count: openGroups.filter((group) => groupHasDanger(group)).length,
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
    paired: { groups: pairedGroups },
    open: { groups: openGroups },
  };
}

function buildGroups(
  rows: Record<"oa" | "bank" | "invoice", Array<Record<string, unknown>>>,
  section: "paired" | "open",
) {
  const groups = new Map<
    string,
    {
      group_id: string;
      group_type: "auto_closed" | "manual_confirmed" | "candidate" | "source_linked";
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
    const groupId = caseId ? `case:${caseId}` : `row:${String(row.id)}`;
    if (!groups.has(groupId)) {
      const isOaAttachmentSourceGroup = caseId?.includes("OA-ATTACHMENT") ?? false;
      groups.set(groupId, {
        group_id: groupId,
        group_type: isOaAttachmentSourceGroup ? "source_linked" : section === "paired" ? "manual_confirmed" : "candidate",
        match_confidence: section === "paired" || isOaAttachmentSourceGroup ? "high" : "medium",
        reason: isOaAttachmentSourceGroup ? "oa_attachment_source_relation" : caseId ? "mock_case_group" : "mock_row_group",
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

  return Array.from(groups.values()).map((group) => {
    const groupRows = [...group.oa_rows, ...group.bank_rows, ...group.invoice_rows];
    const hasWithdrawHistory = groupRows.some((row) =>
      Array.isArray(row.available_actions) && row.available_actions.includes("withdraw_link"),
    );
    return {
      ...group,
      can_withdraw: section === "paired" || hasWithdrawHistory ? true : undefined,
    };
  });
}

function groupHasDanger(group: {
  oa_rows: Array<Record<string, unknown>>;
  bank_rows: Array<Record<string, unknown>>;
  invoice_rows: Array<Record<string, unknown>>;
}) {
  return [...group.oa_rows, ...group.bank_rows, ...group.invoice_rows].some((row) => {
    const relation =
      (row.oa_bank_relation as { tone?: string } | undefined) ??
      (row.invoice_relation as { tone?: string } | undefined) ??
      (row.invoice_bank_relation as { tone?: string } | undefined);
    return relation?.tone === "danger";
  });
}

const WORKBENCH_STATE_MONTHS = ["2026-03", "2026-04"] as const;

function createWorkbenchStateStore() {
  const store = new Map<string, RawWorkbenchPayload>();
  const ensureMonth = (month: string) => {
    if (!store.has(month)) {
      store.set(month, cloneJson(buildWorkbenchRowPayload(month)));
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
        open_count: 0,
        exception_count: 0,
      },
      paired: { oa: [], bank: [], invoice: [] },
      open: { oa: [], bank: [], invoice: [] },
    };

    for (const month of WORKBENCH_STATE_MONTHS) {
      const payload = ensureMonth(month);
      merged.summary.oa_count += payload.summary.oa_count;
      merged.summary.bank_count += payload.summary.bank_count;
      merged.summary.invoice_count += payload.summary.invoice_count;
      merged.summary.paired_count += payload.summary.paired_count;
      merged.summary.open_count += payload.summary.open_count;
      merged.summary.exception_count += payload.summary.exception_count;
      merged.paired.oa.push(...cloneJson(payload.paired.oa));
      merged.paired.bank.push(...cloneJson(payload.paired.bank));
      merged.paired.invoice.push(...cloneJson(payload.paired.invoice));
      merged.open.oa.push(...cloneJson(payload.open.oa));
      merged.open.bank.push(...cloneJson(payload.open.bank));
      merged.open.invoice.push(...cloneJson(payload.open.invoice));
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
        for (const section of ["paired", "open"] as const) {
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

type MockSearchResult = {
  row_id: string;
  record_type: "oa" | "bank" | "invoice";
  month: string;
  zone_hint: "paired" | "open" | "ignored" | "processed_exception";
  matched_field: string;
  title: string;
  primary_meta: string;
  secondary_meta: string;
  status_label: string;
  jump_target: {
    month: string;
    row_id: string;
    zone_hint: "paired" | "open" | "ignored" | "processed_exception";
    record_type: "oa" | "bank" | "invoice";
  };
};

function buildSearchPayload({
  query,
  scope,
  month,
  projectName,
  status,
  limit,
  workbenchStateStore,
  ignoredRowStore,
}: {
  query: string;
  scope: string;
  month: string;
  projectName?: string;
  status?: string;
  limit: number;
  workbenchStateStore: ReturnType<typeof createWorkbenchStateStore>;
  ignoredRowStore: ReturnType<typeof createIgnoredRowStore>;
}) {
  const normalizedQuery = query.trim().toLowerCase();
  const months = month === "all" ? [...WORKBENCH_STATE_MONTHS] : [month];
  const groupedResults = {
    oa: [] as MockSearchResult[],
    bank: [] as MockSearchResult[],
    invoice: [] as MockSearchResult[],
  };

  if (!normalizedQuery) {
    return {
      query,
      summary: { total: 0, oa: 0, bank: 0, invoice: 0 },
      oa_results: [],
      bank_results: [],
      invoice_results: [],
    };
  }

  const matchesField = (value: string | null | undefined) =>
    value && value.toLowerCase().includes(normalizedQuery);

  for (const resolvedMonth of months) {
    const payload = workbenchStateStore.get(resolvedMonth);
    for (const zoneKey of ["paired", "open"] as const) {
      for (const pane of ["oa", "bank", "invoice"] as const) {
        for (const row of payload[zoneKey][pane]) {
          const result = buildSearchResult(row, resolvedMonth, zoneKey, matchesField);
          if (!result) {
            continue;
          }
          if (projectName && !result.title.includes(projectName) && !result.primary_meta.includes(projectName) && !result.secondary_meta.includes(projectName)) {
            continue;
          }
          if (status && status !== "all" && result.zone_hint !== status) {
            continue;
          }
          if (scope !== "all" && result.record_type !== scope) {
            continue;
          }
          groupedResults[result.record_type].push(result);
        }
      }
    }

    for (const row of ignoredRowStore.get(resolvedMonth)) {
      const result = buildSearchResult(row, resolvedMonth, "ignored", matchesField);
      if (!result) {
        continue;
      }
      if (projectName && !result.title.includes(projectName) && !result.primary_meta.includes(projectName) && !result.secondary_meta.includes(projectName)) {
        continue;
      }
      if (status && status !== "all" && result.zone_hint !== status) {
        continue;
      }
      if (scope !== "all" && result.record_type !== scope) {
        continue;
      }
      groupedResults[result.record_type].push(result);
    }
  }

  return {
    query,
    summary: {
      total: groupedResults.oa.length + groupedResults.bank.length + groupedResults.invoice.length,
      oa: groupedResults.oa.length,
      bank: groupedResults.bank.length,
      invoice: groupedResults.invoice.length,
    },
    oa_results: groupedResults.oa.slice(0, limit),
    bank_results: groupedResults.bank.slice(0, limit),
    invoice_results: groupedResults.invoice.slice(0, limit),
  };
}

function buildSearchResult(
  row: RawWorkbenchRow,
  month: string,
  zoneHint: "paired" | "open" | "ignored",
  matchesField: (value: string | null | undefined) => boolean,
): MockSearchResult | null {
  if (row.type === "oa") {
    const detailFields = (row.detail_fields ?? {}) as Record<string, string>;
    const matchField = resolveMatchedField(
      [
        ["项目名称", row.project_name],
        ["申请人", row.applicant],
        ["对方户名", row.counterparty_name],
        ["金额", row.amount],
        ["费用类型", detailFields["费用类型"]],
        ["费用内容", detailFields["费用内容"] ?? row.reason],
        ["OA单号", detailFields["OA单号"]],
      ],
      matchesField,
    );
    if (!matchField) {
      return null;
    }
    return {
      row_id: String(row.id),
      record_type: "oa",
      month,
      zone_hint: zoneHint,
      matched_field: matchField,
      title: String(row.project_name ?? "未命名项目"),
      primary_meta: `${row.applicant ?? "--"} / ${row.counterparty_name ?? "--"} / ${row.amount ?? "--"}`,
      secondary_meta: `${detailFields["费用类型"] ?? "--"} / ${detailFields["费用内容"] ?? row.reason ?? "--"}`,
      status_label: String(row.oa_bank_relation?.label ?? "待处理"),
      jump_target: {
        month,
        row_id: String(row.id),
        zone_hint: zoneHint,
        record_type: "oa",
      },
    };
  }

  if (row.type === "bank") {
    const detailFields = (row.detail_fields ?? {}) as Record<string, string>;
    const effectiveZoneHint = row.handled_exception ? "processed_exception" : zoneHint;
    const matchField = resolveMatchedField(
      [
        ["对方户名", row.counterparty_name],
        ["交易时间", row.trade_time],
        ["金额", row.debit_amount ?? row.credit_amount],
        ["支付账户", row.payment_account_label],
        ["备注", row.remark],
        ["企业流水号", detailFields["企业流水号"]],
        ["账户明细编号-交易流水号", detailFields["账户明细编号-交易流水号"]],
      ],
      matchesField,
    );
    if (!matchField) {
      return null;
    }
    return {
      row_id: String(row.id),
      record_type: "bank",
      month,
      zone_hint: effectiveZoneHint,
      matched_field: matchField,
      title: String(row.counterparty_name ?? "未命名流水"),
      primary_meta: `${row.trade_time ?? "--"} / ${row.debit_amount ?? row.credit_amount ?? "--"} / ${row.direction ?? (row.debit_amount ? "支出" : "收入")}`,
      secondary_meta: `${row.payment_account_label ?? "--"} / ${detailFields["企业流水号"] ?? detailFields["账户明细编号-交易流水号"] ?? row.remark ?? "--"}`,
      status_label: String(row.invoice_relation?.label ?? "待处理"),
      jump_target: {
        month,
        row_id: String(row.id),
        zone_hint: effectiveZoneHint,
        record_type: "bank",
      },
    };
  }

  const detailFields = (row.detail_fields ?? {}) as Record<string, string>;
  const matchField = resolveMatchedField(
    [
      ["发票号码", detailFields["发票号码"]],
      ["数电发票号码", detailFields["数电发票号码"]],
      ["发票代码", detailFields["发票代码"]],
      ["销方名称", row.seller_name],
      ["购方名称", row.buyer_name],
      ["销方识别号", row.seller_tax_no],
      ["购方识别号", row.buyer_tax_no],
      ["金额", row.amount],
    ],
    matchesField,
  );
  if (!matchField) {
    return null;
  }
  return {
    row_id: String(row.id),
    record_type: "invoice",
    month,
    zone_hint: zoneHint,
    matched_field: matchField,
    title: String(detailFields["发票号码"] ?? detailFields["数电发票号码"] ?? row.seller_name ?? "未命名发票"),
    primary_meta: `${row.seller_name ?? "--"} / ${row.amount ?? "--"}`,
    secondary_meta: `${row.issue_date ?? "--"} / ${row.invoice_type ?? "--"}`,
    status_label: zoneHint === "ignored" ? "已忽略" : String(row.invoice_bank_relation?.label ?? "待处理"),
    jump_target: {
      month,
      row_id: String(row.id),
      zone_hint: zoneHint,
      record_type: "invoice",
    },
  };
}

function resolveMatchedField(
  entries: Array<[string, string | null | undefined]>,
  matchesField: (value: string | null | undefined) => boolean,
) {
  const matched = entries.find(([, value]) => matchesField(value));
  return matched?.[0] ?? null;
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
  const invoiceIndex = payload.open.invoice.findIndex((candidate) => String(candidate.id) === rowId);
  if (invoiceIndex < 0) {
    return false;
  }
  const [row] = payload.open.invoice.splice(invoiceIndex, 1);
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
  payload.open.invoice.push(reopenWorkbenchRow(row));
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
      ...matchedGroup.rows[pane].map((row) => (target === "open" ? reopenWorkbenchRow(row) : row)),
    ];
  }

  return true;
}

function findWorkbenchRowsByIds(
  workbenchStateStore: ReturnType<typeof createWorkbenchStateStore>,
  month: string,
  rowIds: string[],
) {
  const payload = workbenchStateStore.get(month);
  const rowsById = new Map<string, RawWorkbenchRow>();
  for (const section of ["paired", "open"] as const) {
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
  section: "paired" | "open",
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
    ...ungroupedRows.flatMap((row) => buildRelationPreviewGroups([{ ...row, case_id: "" }], "", "open", "together")),
  ];
}

function buildWithdrawAfterPreviewGroups(rows: RawWorkbenchRow[]) {
  const restoredRows = rows.filter((row) => row.type !== "bank");
  const restoredRowIds = new Set(restoredRows.map((row) => String(row.id)));
  const ungroupedRows = rows.filter((row) => !restoredRowIds.has(String(row.id)));
  return [
    ...(restoredRows.length >= 2 ? buildRelationPreviewGroups(restoredRows, "CASE-RESTORED", "open", "together") : []),
    ...ungroupedRows.flatMap((row) => buildRelationPreviewGroups([{ ...row, case_id: "" }], "", "open", "together")),
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
  return {
    operation,
    can_submit: true,
    requires_note: isMismatch && operation === "confirm_link",
    message: isMismatch && operation === "confirm_link" ? "金额不一致，请填写备注。" : "",
    before: {
      groups: buildRelationPreviewGroups(
        rows,
        caseId,
        operation === "withdraw_link" ? "paired" : "open",
        operation === "withdraw_link" ? "together" : "separate",
      ),
    },
    after: {
      groups:
        operation === "withdraw_link"
          ? buildWithdrawAfterPreviewGroups(rows)
          : buildRelationPreviewGroups(rows, caseId, "paired", "together"),
    },
    amount_summary: amountSummary,
    restored_relations:
      operation === "withdraw_link"
        ? [{ case_id: "CASE-RESTORED", row_ids: rows.filter((row) => row.type !== "bank").map((row) => String(row.id)) }]
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
  const rows = buildMockCertifiedPreviewRows(month);
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

type CostSummaryRow = {
  project_name: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  transaction_count: number;
  sample_transaction_ids: string[];
};

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
    summary_fields: Record<string, string>;
    detail_fields: Record<string, string>;
  };
};

const costStatisticsMonthRows: Record<string, CostSummaryRow[]> = {
  "2026-03": [
    {
      project_name: "云南溯源科技",
      expense_type: "设备货款及材料费",
      expense_content: "PLC 模块采购",
      amount: "12,500.00",
      transaction_count: 2,
      sample_transaction_ids: ["cost-txn-001", "cost-txn-002"],
    },
    {
      project_name: "云南溯源科技",
      expense_type: "交通费",
      expense_content: "项目现场往返交通",
      amount: "860.00",
      transaction_count: 1,
      sample_transaction_ids: ["cost-txn-003"],
    },
    {
      project_name: "昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
      expense_type: "人工费/劳务费/服务费",
      expense_content: "现场调试服务",
      amount: "5,200.00",
      transaction_count: 1,
      sample_transaction_ids: ["cost-txn-004"],
    },
  ],
  "2026-04": [
    {
      project_name: "昆明卷烟厂动力设备控制系统升级改造项目",
      expense_type: "经营/办公费用",
      expense_content: "项目办公室租赁",
      amount: "9,600.00",
      transaction_count: 2,
      sample_transaction_ids: ["cost-txn-101", "cost-txn-102"],
    },
  ],
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
        trade_time: "2026-03-10 21:27:55",
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

function sumCostAmounts(rows: Array<{ amount: string }>) {
  const total = rows.reduce((sum, row) => sum + Number(row.amount.replace(/,/g, "")), 0);
  return total.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function buildCostStatisticsMonthPayload(month: string, projectScope = "active") {
  const rows = (costStatisticsMonthRows[month] ?? []).filter((row) =>
    isCostProjectVisibleForScope(row.project_name, projectScope),
  );
  return {
    month,
    summary: {
      row_count: rows.length,
      transaction_count: rows.reduce((sum, row) => sum + row.transaction_count, 0),
      total_amount: sumCostAmounts(rows),
    },
    rows,
  };
}

function buildAllCostProjectRows() {
  return Object.values(costStatisticsProjectRows).reduce<Record<string, CostProjectRow[]>>((result, projectMap) => {
    for (const [projectName, rows] of Object.entries(projectMap)) {
      result[projectName] = [...(result[projectName] ?? []), ...rows];
    }
    return result;
  }, {});
}

function buildCostStatisticsExplorerPayload(month: string, projectScope = "active") {
  const sourceProjectRowMap = month === "all" ? buildAllCostProjectRows() : (costStatisticsProjectRows[month] ?? {});
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
      })),
    )
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
    project_rows: projectRows,
    expense_type_rows: expenseTypeRows,
  };
}

function buildCostStatisticsProjectPayload(month: string, projectName: string, projectScope = "active") {
  const rows = isCostProjectVisibleForScope(projectName, projectScope)
    ? month === "all"
      ? buildAllCostProjectRows()[projectName] ?? []
      : (costStatisticsProjectRows[month]?.[projectName] ?? [])
    : [];
  return {
    month,
    project_name: projectName,
    summary: {
      row_count: rows.length,
      transaction_count: rows.length,
      total_amount: sumCostAmounts(rows),
    },
    rows,
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
    view: "time",
    file_name: buildCostStatisticsExportFileName(month, "time", undefined, null, null, null, startMonth, endMonth, undefined, startDate, endDate),
    scope_label: scopeLabel,
    summary: {
      row_count: rows.length,
      transaction_count: rows.length,
      total_amount: sumCostAmounts(rows),
      sheet_count: 1,
    },
    sheet_names: ["按时间统计"],
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
  let latestImportSession = buildImportPreviewPayload([]);
  const etcInvoiceStore = createEtcInvoiceStore();
  const etcReconciliationTaskStore = createEtcReconciliationTaskStore();
  const turnoverExtraStore = new Map<string, Record<string, unknown>>();
  let latestEtcImportPreview = etcInvoiceStore.previewZip([]);
  let latestEtcDraftInvoiceIds: string[] = [];
  let latestEtcDraftBatchId = "";
  const workbenchStateStore = createWorkbenchStateStore();
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
    access_control: {
      allowed_usernames: [],
      readonly_export_usernames: [],
      admin_usernames: ["YNSYLP005"],
      full_access_usernames: [],
    },
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

  const dataResetJobs = new Map<string, Record<string, unknown>>();
  let backgroundJobs = cloneJson(options.backgroundJobs ?? []);
  let workbenchOaSyncStatusIndex = 0;

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
      return {
        body: {
          user: {
            user_id: "101",
            username: options.sessionUsername ?? "liuji",
            nickname: options.sessionDisplayName ?? "刘际涛",
            display_name: options.sessionDisplayName ?? "刘际涛",
            dept_id: "88",
            dept_name: "财务部",
            avatar: null,
          },
          roles: ["finance"],
          permissions: options.sessionMode === "forbidden" ? [] : ["finops:app:view"],
          allowed: options.sessionMode !== "forbidden",
          access_tier:
            options.sessionMode === "forbidden"
              ? "denied"
              : options.sessionAccessTier ?? "full_access",
          can_access_app: options.sessionMode !== "forbidden",
          can_mutate_data:
            options.sessionMode === "forbidden"
              ? false
              : (options.sessionAccessTier ?? "full_access") !== "read_export_only",
          can_admin_access:
            options.sessionMode !== "forbidden" && (options.sessionAccessTier ?? "full_access") === "admin",
        },
      };
    },
    "/imports/templates": () => ({
      body: {
        templates: templateRegistry,
      },
    }),
    "/api/workbench": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.workbenchErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "workbench failed" } };
      }
      return { body: toGroupedWorkbenchPayload(cloneJson(workbenchStateStore.get(month)), options.workbenchOaStatus) };
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
          workbench_read_model: {
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
          access_control: {
            allowed_usernames: Array.isArray(jsonBody.allowed_usernames)
              ? (jsonBody.allowed_usernames as string[]).map((item) => String(item).trim()).filter(Boolean)
              : workbenchSettingsState.access_control.allowed_usernames,
            readonly_export_usernames: Array.isArray(jsonBody.readonly_export_usernames)
              ? (jsonBody.readonly_export_usernames as string[]).map((item) => String(item).trim()).filter(Boolean)
              : workbenchSettingsState.access_control.readonly_export_usernames,
            admin_usernames: Array.isArray(jsonBody.admin_usernames)
              ? (jsonBody.admin_usernames as string[]).map((item) => String(item).trim()).filter(Boolean)
              : workbenchSettingsState.access_control.admin_usernames,
            full_access_usernames: [],
          },
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
        const allowedSet = new Set(workbenchSettingsState.access_control.allowed_usernames);
        const readonlySet = new Set(
          workbenchSettingsState.access_control.readonly_export_usernames.filter((item) => allowedSet.has(item)),
        );
        const adminSet = new Set(workbenchSettingsState.access_control.admin_usernames);
        workbenchSettingsState.access_control.full_access_usernames = workbenchSettingsState.access_control.allowed_usernames.filter(
          (item) => !readonlySet.has(item) && !adminSet.has(item),
        );
      }
      return { body: cloneJson(workbenchSettingsState) };
    },
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
    "/api/workbench/settings/data-reset": ({ jsonBody }) => {
      if (options.dataResetPasswordShouldFail || !jsonBody?.oa_password) {
        return {
          status: 403,
          body: {
            error: "oa_password_verification_failed",
            message: "当前 OA 用户密码复核失败，未执行数据重置。",
          },
        };
      }
      return {
        body: {
          action: String(jsonBody.action ?? ""),
          status: "completed",
          cleared_collections: ["workbench_read_models"],
          deleted_counts: {
            workbench_read_models: 1,
          },
          protected_targets: ["form_data_db.form_data"],
          rebuild_status: jsonBody.action === "reset_oa_and_rebuild" ? "completed" : "not_applicable",
          message: "已完成数据重置。",
        },
      };
    },
    "/api/search": ({ url }) => {
      const query = url.searchParams.get("q") ?? "";
      if (options.searchErrorQueries?.includes(query)) {
        return { status: 500, body: { message: "search failed" } };
      }
      const scope = url.searchParams.get("scope") ?? "all";
      const month = url.searchParams.get("month") ?? "all";
      const projectName = url.searchParams.get("project_name") ?? undefined;
      const status = url.searchParams.get("status") ?? "all";
      const limit = Number.parseInt(url.searchParams.get("limit") ?? "30", 10);
      return {
        body: buildSearchPayload({
          query,
          scope,
          month,
          projectName,
          status,
          limit: Number.isFinite(limit) ? limit : 30,
          workbenchStateStore,
          ignoredRowStore,
        }),
      };
    },
    "/api/tax-offset": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      if (options.taxErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "tax failed" } };
      }
      return { body: taxOffsetStateStore.get(month) };
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
    "/api/cost-statistics": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      const projectScope = url.searchParams.get("project_scope") ?? "active";
      if (options.costErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "cost statistics failed" } };
      }
      return { body: buildCostStatisticsMonthPayload(month, projectScope) };
    },
    "/api/cost-statistics/explorer": ({ url }) => {
      const month = url.searchParams.get("month") ?? "";
      const projectScope = url.searchParams.get("project_scope") ?? "active";
      if (options.costErrorMonths?.includes(month)) {
        return { status: 500, body: { message: "cost statistics failed" } };
      }
      return { body: buildCostStatisticsExplorerPayload(month, projectScope) };
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
    "/api/etc/invoices": ({ url }) => ({
      body: etcInvoiceStore.list({
        status: url.searchParams.get("status"),
        month: url.searchParams.get("month"),
        plate: url.searchParams.get("plate"),
        keyword: url.searchParams.get("keyword"),
      }),
    }),
    "/api/etc/batches": ({ url }) => ({
      body: etcInvoiceStore.listBatches({
        status: url.searchParams.get("status"),
        month: url.searchParams.get("month"),
        plate: url.searchParams.get("plate"),
        keyword: url.searchParams.get("keyword"),
      }),
    }),
    "/api/etc/business-batches": ({ url }) => ({
      body: etcInvoiceStore.listBusinessBatches({
        status: url.searchParams.get("status"),
        month: url.searchParams.get("month"),
        plate: url.searchParams.get("plate"),
        keyword: url.searchParams.get("keyword"),
      }),
    }),
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
    "/api/etc/batches/draft": ({ jsonBody }) => {
      latestEtcDraftInvoiceIds = Array.isArray(jsonBody?.invoiceIds)
        ? (jsonBody.invoiceIds as string[])
        : [];
      return {
        body: {
          batchId: "etc_batch_001",
          etcBatchId: "etc_20260503_001",
          oaDraftId: "oa_draft_001",
          oaDraftUrl: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
        },
      };
    },
    "/api/etc/invoices/revoke-submitted": ({ jsonBody }) => {
      const invoiceIds = Array.isArray(jsonBody?.invoiceIds) ? (jsonBody.invoiceIds as string[]) : [];
      etcInvoiceStore.markUnsubmitted(invoiceIds);
      return {
        body: {
          ok: true,
        },
      };
    },
    "/api/bank-details/accounts": ({ url }) => {
      const dateFrom = url.searchParams.get("date_from");
      const dateTo = url.searchParams.get("date_to");
      const isCurrentYear = dateFrom === "2026-01-01" && dateTo === "2026-12-31";
      return {
        body: {
          total_balance: "130500.50",
          balance_account_count: 1,
          missing_balance_account_count: 1,
          accounts: [
            {
              account_key: "icbc:6386",
              bank_name: "工商银行",
              account_last4: "6386",
              display_name: "工商银行 6386",
              latest_balance: "130500.50",
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
    "/api/bank-details/transactions": ({ url }) => {
      const accountKey = url.searchParams.get("account_key");
      const dateFrom = url.searchParams.get("date_from");
      const dateTo = url.searchParams.get("date_to");
      const keyword = (url.searchParams.get("keyword") ?? "").trim();
      const page = Number(url.searchParams.get("page") ?? "1");
      const pageSize = Number(url.searchParams.get("page_size") ?? "100");
      const isCurrentYear = dateFrom === "2026-01-01" && dateTo === "2026-12-31";
      const visibleRow = {
        id: `bank-detail-${String(page).padStart(3, "0")}`,
        trade_time: "2026-05-01 10:30:00",
        counterparty_name: "云南溯源科技有限公司",
        direction: "income",
        direction_label: "收",
        amount: "20000.00",
        balance: "130500.50",
        summary: "项目回款",
        purpose: "货款",
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
        auto_category_source: "bank_transaction_auto_category_service",
        auto_category_reason: "摘要命中工资规则",
        auto_category_confidence: "high",
        effective_category_code: "salary",
        effective_category_label: "工资",
        effective_category_path: ["自动识别", "工资"],
        effective_category_source: "auto",
        oa_relation_tag: "有oa",
        invoice_relation_tag: "无发票",
        relation_tags: ["有oa", "无发票"],
        relation_case_id: "CASE-202605-001",
      };
      const hiddenTargetRow = {
        ...visibleRow,
        id: "bank-detail-search-target",
        trade_time: "2026-03-01 10:30:00",
        counterparty_name: "跨页目标供应商",
        summary: "网银手续费",
        purpose: "跨页目标用途",
        auto_category_code: "fee",
        auto_category_label: "手续费",
        auto_category_path: ["自动识别", "手续费"],
        auto_category_reason: "摘要命中手续费规则",
        effective_category_code: "fee",
        effective_category_label: "手续费",
        effective_category_path: ["自动识别", "手续费"],
      };
      const searchDataset = [
        visibleRow,
        {
          ...visibleRow,
          id: "bank-detail-search-filler",
          trade_time: "2026-04-01 10:30:00",
          counterparty_name: "普通供应商",
          summary: "普通付款",
          purpose: "普通用途",
          auto_category_code: null,
          auto_category_label: null,
          auto_category_path: [],
          effective_category_code: null,
          effective_category_label: null,
          effective_category_path: [],
          effective_category_source: "",
        },
        hiddenTargetRow,
      ];
      const matchedRows = keyword
        ? searchDataset.filter((row) => Object.values(row).some((value) => (
          Array.isArray(value)
            ? value.join(" ").includes(keyword)
            : String(value ?? "").includes(keyword)
        )))
        : null;
      const rows = !accountKey || accountKey === "icbc:6386"
        ? (matchedRows ?? [visibleRow])
        : [];
      return {
        body: {
          account_key: accountKey,
          date_from: dateFrom,
          date_to: dateTo,
          rows,
          category_counts: keyword
            ? {
              borrow_in_company_pending_repayment: 0,
              business_warranty_pending_collection: 0,
              borrow_out_personal_pending_collection: 0,
              salary: rows.filter((row) => row.effective_category_code === "salary").length,
              fee: rows.filter((row) => row.effective_category_code === "fee").length,
              holiday_bonus: 0,
              bonus: 0,
              uncategorized: rows.filter((row) => !row.effective_category_code).length,
            }
            : {
              borrow_in_company_pending_repayment: 2,
              business_warranty_pending_collection: 1,
              borrow_out_personal_pending_collection: 0,
              salary: !accountKey || accountKey === "icbc:6386" ? 1 : 0,
              fee: 0,
              holiday_bonus: 0,
              bonus: 0,
              uncategorized: (!accountKey || accountKey === "icbc:6386") && isCurrentYear ? 295 : rows.length,
            },
          pagination: {
            page,
            page_size: pageSize,
            total: keyword ? rows.length : (!accountKey || accountKey === "icbc:6386") && isCurrentYear ? 299 : rows.length,
          },
          bank_transaction_tags: {
            version: 1,
            definitions: SELECTABLE_CATEGORY_OPTIONS.map((option) => ({
              code: option.code,
              label: option.label,
              path: option.menuLabel.split(" / "),
              source: "system",
              status: "active",
            })),
          },
        },
      };
    },
    "/api/bank-details/transactions/categories": ({ jsonBody }) => ({
      body: {
        updated_transaction_ids: Array.isArray(jsonBody?.updates)
          ? jsonBody.updates.map((update) => (update as Record<string, unknown>).transaction_id)
          : [],
        updated_categories: Array.isArray(jsonBody?.updates)
          ? jsonBody.updates.map((update) => {
            const categoryCode = (update as Record<string, unknown>).category_code;
            return {
              transaction_id: (update as Record<string, unknown>).transaction_id,
              category_code: categoryCode,
              category_label: categoryCode === "borrow_in_company_pending_repayment" ? "公司暂借款：待还款" : null,
              category_path: categoryCode === "borrow_in_company_pending_repayment" ? ["借入", "公司往来款", "待还款"] : [],
              version: 2,
            };
          })
          : [],
        affected_months: ["2026-05"],
        workbench_rebuild_queued: true,
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
        body: buildMockRelationPreview({
          operation: "confirm_link",
          month,
          rowIds,
          caseId,
          workbenchStateStore,
        }),
      };
    },
    "/api/workbench/actions/confirm-link": ({ jsonBody }) => {
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
          moveWorkbenchGroup(payload, "open", "paired", rowId);
        }
      }
      return {
        body: {
          success: true,
          action: "confirm_link",
          month,
          affected_row_ids: rowIds,
          case_id: typeof jsonBody?.case_id === "string" ? jsonBody.case_id : undefined,
          affected_months: Array.from(touchedMonths),
          message: `已确认 ${rowIds.length} 条记录关联。`,
        },
      };
    },
    "/api/workbench/actions/withdraw-link/preview": ({ jsonBody }) => {
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const month = String(jsonBody?.month ?? "");
      return {
        body: buildMockRelationPreview({
          operation: "withdraw_link",
          month,
          rowIds,
          caseId: "preview:withdraw",
          workbenchStateStore,
        }),
      };
    },
    "/api/workbench/actions/withdraw-link": ({ jsonBody }) => {
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
          moveWorkbenchGroup(payload, "paired", "open", rowId);
        }
      }
      return {
        body: {
          success: true,
          action: "withdraw_link",
          month,
          affected_row_ids: rowIds,
          restored_relations: [],
          changed_scopes: Array.from(touchedMonths),
          message: "已撤回 1 组关联。",
        },
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
          payload.open[pane] = payload.open[pane].map((row) => {
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
              workbench_refresh_required: true,
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
      moveWorkbenchGroup(workbenchStateStore.get(resolvedMonth), "paired", "open", rowId);
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
    "/api/workbench/actions/oa-bank-exception": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const exceptionCode = String(jsonBody?.exception_code ?? "");
      const exceptionLabel = String(jsonBody?.exception_label ?? "");
      const comment = typeof jsonBody?.comment === "string" ? jsonBody.comment : exceptionLabel;
      const touchedMonths = new Set(
        rowIds.map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month)).filter(Boolean) as string[],
      );

      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const pane of ["oa", "bank", "invoice"] as const) {
          payload.open[pane] = payload.open[pane].map((row) => {
            if (!rowIds.includes(String(row.id))) {
              return row;
            }
            if (row.type === "oa") {
              return {
                ...row,
                handled_exception: true,
                oa_bank_relation: { code: exceptionCode, label: exceptionLabel, tone: "danger" },
                available_actions: ["detail", "confirm_link", "mark_exception", "ignore"],
              };
            }
            if (row.type === "bank") {
              return {
                ...row,
                handled_exception: true,
                invoice_relation: { code: exceptionCode, label: exceptionLabel, tone: "danger" },
                available_actions: ["detail", "view_relation", "cancel_link", "handle_exception"],
                remark: comment,
              };
            }
            return row;
          });
        }
      }

      return {
        body: {
          success: true,
          action: "oa_bank_exception",
          month,
          affected_row_ids: rowIds,
          updated_rows: rowIds.map((id) => ({ id })),
          message: `已对 ${rowIds.length} 条记录执行 OA/流水异常处理。`,
        },
      };
    },
    "/api/workbench/actions/cancel-exception": ({ jsonBody }) => {
      const month = String(jsonBody?.month ?? "");
      const rowIds = Array.isArray(jsonBody?.row_ids) ? (jsonBody.row_ids as string[]) : [];
      const touchedMonths = new Set(
        rowIds.map((rowId) => (month === "all" ? workbenchStateStore.resolveMonthForRow(rowId) : month)).filter(Boolean) as string[],
      );

      for (const resolvedMonth of touchedMonths) {
        const payload = workbenchStateStore.get(resolvedMonth);
        for (const pane of ["oa", "bank", "invoice"] as const) {
          payload.open[pane] = payload.open[pane].map((row) => {
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
          return {
            ...file,
            template_code: override.template_code ?? file.template_code ?? "invoice_export",
            batch_type: override.batch_type ?? file.batch_type ?? "input_invoice",
            status: "preview_ready",
            message: "模板识别成功。",
            override_template_code: override.template_code ?? null,
            override_batch_type: override.batch_type ?? null,
          };
        }),
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
    if (url.pathname.startsWith("/api/cost-statistics/projects/")) {
      const projectName = decodeURIComponent(url.pathname.split("/").pop() ?? "");
      const month = url.searchParams.get("month") ?? "";
      const projectScope = url.searchParams.get("project_scope") ?? "active";
      return jsonResponse({ body: buildCostStatisticsProjectPayload(month, projectName, projectScope) });
    }
    if (url.pathname.startsWith("/api/cost-statistics/transactions/")) {
      const transactionId = url.pathname.split("/").pop() ?? "";
      return jsonResponse(buildCostStatisticsTransactionPayload(transactionId));
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
      if (!segment && method === "DELETE") {
        const deleted = etcInvoiceStore.deleteBatch(businessBatchId);
        if (deleted || businessBatchId.startsWith("etc_business_batch_")) {
          return jsonResponse({ body: { ok: true, data: { deleted: true, businessBatchId, kind: "business_batch" }, error: null } });
        }
        return jsonResponse({ status: 409, body: { ok: false, data: null, error: { code: "invalid_status_transition", message: "ETC业务批次不能删除。" } } });
      }
      if (method === "POST" && segment === "oa-draft" && !trailing) {
        const batch = etcInvoiceStore.businessBatchDraft(businessBatchId);
        return batch
          ? jsonResponse({ body: { ok: true, data: { businessBatch: batch }, error: null } })
          : jsonResponse({ status: 404, body: { ok: false, data: null, error: { message: "ETC业务批次不存在。" } } });
      }
      if (method === "POST" && segment === "oa-status" && trailing === "refresh") {
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
    const etcBatchDeleteMatch = url.pathname.match(/^\/api\/etc\/batches\/([^/]+)$/);
    if (etcBatchDeleteMatch && method === "DELETE") {
      const deleted = etcInvoiceStore.deleteBatch(decodeURIComponent(etcBatchDeleteMatch[1] ?? ""));
      return deleted
        ? jsonResponse({ body: { deleted: true } })
        : jsonResponse({ status: 409, body: { error: "etc_batch_delete_conflict", message: "ETC批次不能删除。" } });
    }
    const etcBatchDetailMatch = url.pathname.match(/^\/api\/etc\/batches\/([^/]+)$/);
    if (etcBatchDetailMatch && method === "GET") {
      const batch = etcInvoiceStore.batchDetail(decodeURIComponent(etcBatchDetailMatch[1] ?? ""));
      return batch
        ? jsonResponse({ body: batch })
        : jsonResponse({ status: 404, body: { message: "ETC批次不存在。" } });
    }
    const etcBatchDraftMatch = url.pathname.match(/^\/api\/etc\/batches\/([^/]+)\/draft$/);
    if (etcBatchDraftMatch) {
      latestEtcDraftBatchId = decodeURIComponent(etcBatchDraftMatch[1] ?? "");
      const batch = etcInvoiceStore.batchDetail(latestEtcDraftBatchId);
      return jsonResponse({
        body: {
          batch_id: latestEtcDraftBatchId,
          etc_batch_id: batch?.external_batch_id ?? batch?.externalBatchId ?? "ETC-2026-03-A",
          oa_draft_id: "oa_draft_001",
          oa_draft_url: "https://oa.example.test/oa/#/normal/forms/form/2?formId=2&id=oa_draft_001",
        },
      });
    }
    const etcBatchConfirmMatch = url.pathname.match(/^\/api\/etc\/batches\/([^/]+)\/confirm-submitted$/);
    if (etcBatchConfirmMatch) {
      etcInvoiceStore.markBatchSubmitted(decodeURIComponent(etcBatchConfirmMatch[1] ?? ""));
      return jsonResponse({ body: { ok: true } });
    }
    const etcBatchMarkNotSubmittedMatch = url.pathname.match(/^\/api\/etc\/batches\/([^/]+)\/mark-not-submitted$/);
    if (etcBatchMarkNotSubmittedMatch) {
      const batchId = decodeURIComponent(etcBatchMarkNotSubmittedMatch[1] ?? "");
      if (batchId !== latestEtcDraftBatchId) {
        etcInvoiceStore.markBatchUnsubmitted(batchId);
      }
      return jsonResponse({ body: { ok: true } });
    }
    if (url.pathname === "/api/etc/batches/etc_batch_001/confirm-submitted") {
      etcInvoiceStore.markSubmitted(latestEtcDraftInvoiceIds);
      return jsonResponse({ body: { ok: true } });
    }
    if (url.pathname === "/api/etc/batches/etc_batch_001/mark-not-submitted") {
      return jsonResponse({ body: { ok: true } });
    }
    if (url.pathname.startsWith("/imports/batches/") && url.pathname.endsWith("/revert")) {
      const batchId = url.pathname.split("/")[3] ?? "";
      latestImportSession = {
        ...latestImportSession,
        session: {
          ...latestImportSession.session,
          status: "reverted",
        },
        files: latestImportSession.files.map((file) =>
          file.batch_id === batchId
            ? {
                ...file,
                status: "reverted",
              }
            : file,
        ),
      };
      return jsonResponse({
        body: {
          batch: {
            id: batchId,
            status: "reverted",
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
          cleared_collections: ["workbench_read_models"],
          deleted_counts: {
            workbench_read_models: 1,
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
            label: "生成关联台候选",
          },
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
    const workbenchSpecificDelay =
      (url.pathname === "/api/workbench" ? options.workbenchPrimaryDelayMs : undefined)
      ?? (url.pathname === "/api/workbench/ignored" ? options.workbenchIgnoredDelayMs : undefined)
      ?? (url.pathname === "/api/workbench/settings" ? options.workbenchSettingsDelayMs : undefined);

    if (workbenchSpecificDelay) {
      await new Promise((resolve) => window.setTimeout(resolve, workbenchSpecificDelay));
    } else if (
      options.workbenchLoadDelayMs
      && (
        url.pathname === "/api/workbench"
        || url.pathname === "/api/workbench/ignored"
        || url.pathname === "/api/workbench/settings"
      )
    ) {
      await new Promise((resolve) => window.setTimeout(resolve, options.workbenchLoadDelayMs));
    }
    if (options.searchDelayMs && url.pathname === "/api/search") {
      await new Promise((resolve) => window.setTimeout(resolve, options.searchDelayMs));
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
