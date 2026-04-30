import { vi } from "vitest";

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
  dataResetPasswordShouldFail?: boolean;
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
  return {
    session: {
      id: "import_session_0001",
      imported_by: "web_finance_user",
      file_count: fileNames.length,
      status: fileNames.includes("README.md") ? "preview_ready_with_errors" : "preview_ready",
      created_at: "2026-03-26T23:00:00+08:00",
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
      oa_count: 4,
      bank_count: 3,
      invoice_count: 3,
      paired_count: 3,
      open_count: 7,
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
          applicant: "孙悦",
          project_name: "维保补录项目",
          apply_type: "服务费申请",
          amount: "9,800.00",
          counterparty_name: "独立服务商",
          reason: "月度巡检服务待付款",
          oa_bank_relation: { code: "pending_match", label: "待找流水与发票", tone: "warn" },
          detail_fields: {
            审批完成时间: "2026-03-26 09:20",
            附件发票数量: "0",
            附件发票识别情况: "已解析 0 / 6",
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
      ],
      invoice: [
        {
          id: "iv-o-202603-001",
          type: "invoice",
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
      group_type: "auto_closed" | "manual_confirmed" | "candidate";
      match_confidence: "high" | "medium" | "low";
      reason: string;
      oa_rows: Array<Record<string, unknown>>;
      bank_rows: Array<Record<string, unknown>>;
      invoice_rows: Array<Record<string, unknown>>;
    }
  >();

  for (const row of [...rows.oa, ...rows.bank, ...rows.invoice]) {
    const caseId = typeof row.case_id === "string" && row.case_id ? row.case_id : null;
    const groupId = caseId ? `case:${caseId}` : `row:${String(row.id)}`;
    if (!groups.has(groupId)) {
      groups.set(groupId, {
        group_id: groupId,
        group_type: section === "paired" ? "manual_confirmed" : "candidate",
        match_confidence: section === "paired" ? "high" : "medium",
        reason: caseId ? "mock_case_group" : "mock_row_group",
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

  return Array.from(groups.values());
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
    oa_invoice_offset: {
      applicant_names: ["周洁莹"],
    },
  };

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
          message: `已确认 ${rowIds.length} 条记录关联。`,
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

    if ((init?.method ?? "GET").toUpperCase() === "DELETE" && url.pathname.startsWith("/api/workbench/settings/projects/")) {
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
    if (isBinaryLikeResponse(response)) {
      if (options.actionDelayMs && url.pathname.startsWith("/api/workbench/actions/")) {
        await new Promise((resolve) => window.setTimeout(resolve, options.actionDelayMs));
      }
      return response;
    }
    if (options.actionDelayMs && url.pathname.startsWith("/api/workbench/actions/")) {
      await new Promise((resolve) => window.setTimeout(resolve, options.actionDelayMs));
    }
    return jsonResponse(response);
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
