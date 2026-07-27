import type {
  CostBankExplorerRow,
  CostBankTagPrimaryExplorerRow,
  CostBankTagSubExplorerRow,
  CostExpenseTypeExplorerRow,
  CostProjectScope,
  CostProjectExplorerRow,
  CostStatisticsExportPreview,
  CostStatisticsExplorerPage,
  CostStatisticsExplorerPageRequest,
  CostStatisticsTagRules,
  CostStatisticsTagRuleTag,
  CostStatisticsView,
  CostTimeRow,
  CostTransactionDetail,
  SaveCostStatisticsTagRulesRequest,
} from "./types";
import { apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";

type ApiCostSummary = {
  row_count: number;
  transaction_count: number;
  total_amount: string;
  expense_amount?: string | null;
  income_amount?: string | null;
  expense_transaction_count?: number | null;
  income_transaction_count?: number | null;
};

type ApiCostTimeRow = {
  transaction_id: string;
  trade_time: string;
  direction: string;
  project_name: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  counterparty_name: string;
  payment_account_label: string;
  remark: string;
  bank_tag_code?: string | null;
  bank_tag_label?: string | null;
  bank_tag_primary_label?: string | null;
  bank_tag_sub_label?: string | null;
  bank_tag_label_path?: string[] | null;
};

type ApiCostProjectExplorerRow = {
  project_name: string;
  total_amount: string;
  transaction_count: number;
  expense_type_count: number;
  percentage_label?: string | null;
};

type ApiCostExpenseTypeExplorerRow = {
  expense_type: string;
  total_amount: string;
  transaction_count: number;
  project_count: number;
  percentage_label: string;
};

type ApiCostBankExplorerRow = {
  payment_account_label: string;
  total_amount: string;
  transaction_count: number;
  project_count: number;
  percentage_label: string;
};

type ApiCostBankTagPrimaryExplorerRow = {
  primary_label: string;
  expense_amount: string;
  income_amount: string;
  expense_transaction_count: number;
  income_transaction_count: number;
  sub_tag_count: number;
};

type ApiCostBankTagSubExplorerRow = {
  primary_label: string;
  sub_label: string;
  expense_amount: string;
  income_amount: string;
  expense_transaction_count: number;
  income_transaction_count: number;
};

type ApiCostStatisticsExplorerPage = {
  scope: string;
  view: CostStatisticsExplorerPage["view"];
  summary: ApiCostSummary;
  statistics?: {
    transaction_count?: number | null;
    expense_transaction_count?: number | null;
    income_transaction_count?: number | null;
    cost_group_count?: number | null;
    tagged_transaction_count?: number | null;
    untagged_transaction_count?: number | null;
    project_count?: number | null;
    expense_type_count?: number | null;
    bank_tag_count?: number | null;
    cost_transaction_count?: number | null;
  } | null;
  available_years?: string[] | null;
  facets?: {
    projects?: ApiCostProjectExplorerRow[] | null;
    expense_types?: ApiCostExpenseTypeExplorerRow[] | null;
    bank_accounts?: ApiCostBankExplorerRow[] | null;
    bank_tag_primary?: ApiCostBankTagPrimaryExplorerRow[] | null;
    bank_tag_sub?: ApiCostBankTagSubExplorerRow[] | null;
  } | null;
  rows?: ApiCostTimeRow[] | null;
  row_count: number;
  next_cursor?: string | null;
};

type ApiCostTransactionDetail = {
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
    oa_applicant: string;
    remark: string;
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
    }> | null;
    bank_tag_code?: string | null;
    bank_tag_label?: string | null;
    bank_tag_primary_label?: string | null;
    bank_tag_sub_label?: string | null;
    bank_tag_label_path?: string[] | null;
  };
};

type ApiCostStatisticsExportPreview = {
  view: "time" | "bank_tag" | "project" | "expense_type";
  file_name: string;
  scope_label: string;
  summary: ApiCostSummary & {
    sheet_count: number;
  };
  sheet_names: string[];
  columns: string[];
  rows: string[][];
};

type ApiCostStatisticsTagRuleTag = {
  code: string;
  label?: string | null;
  path?: string[] | null;
  source?: string | null;
  status?: string | null;
  direction?: string | null;
  output_primary_label?: string | null;
  output_sub_label?: string | null;
};

type ApiCostStatisticsTagRules = {
  version: number;
  bank_auto_tag_rules_version: number;
  default_selection_applied?: boolean | null;
  selected_tag_codes?: string[] | null;
  effective_selected_tag_codes?: string[] | null;
  inactive_selected_tag_codes?: string[] | null;
  active_tags?: ApiCostStatisticsTagRuleTag[] | null;
  can_save?: boolean | null;
};

function mapSummary(summary: ApiCostSummary) {
  return {
    rowCount: summary.row_count,
    transactionCount: summary.transaction_count,
    totalAmount: summary.total_amount,
    expenseAmount: optionalString(summary.expense_amount),
    incomeAmount: optionalString(summary.income_amount),
    expenseTransactionCount: summary.expense_transaction_count ?? undefined,
    incomeTransactionCount: summary.income_transaction_count ?? undefined,
  };
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function optionalCount(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : undefined;
}

function stringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

function bankTagFields(row: {
  bank_tag_code?: string | null;
  bank_tag_label?: string | null;
  bank_tag_primary_label?: string | null;
  bank_tag_sub_label?: string | null;
  bank_tag_label_path?: string[] | null;
}) {
  const labelPath = stringList(row.bank_tag_label_path) ?? [];
  const primaryLabel = optionalString(row.bank_tag_primary_label) ?? labelPath[0] ?? optionalString(row.bank_tag_label) ?? "未标记";
  const subLabel = optionalString(row.bank_tag_sub_label) ?? labelPath[1] ?? optionalString(row.bank_tag_label) ?? primaryLabel;
  return {
    bankTagCode: optionalString(row.bank_tag_code) ?? "",
    bankTagLabel: optionalString(row.bank_tag_label) ?? subLabel,
    bankTagPrimaryLabel: primaryLabel,
    bankTagSubLabel: subLabel,
    bankTagLabelPath: labelPath.length > 0 ? labelPath : primaryLabel === subLabel ? [primaryLabel] : [primaryLabel, subLabel],
  };
}

function mapCostTimeRow(row: ApiCostTimeRow): CostTimeRow {
  return {
    transactionId: row.transaction_id,
    tradeTime: row.trade_time,
    direction: row.direction,
    projectName: row.project_name,
    expenseType: row.expense_type,
    expenseContent: row.expense_content,
    amount: row.amount,
    counterpartyName: row.counterparty_name,
    paymentAccountLabel: row.payment_account_label,
    remark: row.remark,
    ...bankTagFields(row),
  };
}

function mapTagRuleTag(row: ApiCostStatisticsTagRuleTag): CostStatisticsTagRuleTag {
  return {
    code: row.code,
    label: optionalString(row.label) ?? row.code,
    path: stringList(row.path) ?? [],
    source: optionalString(row.source) ?? "",
    status: optionalString(row.status) ?? "active",
    direction: optionalString(row.direction) ?? "any",
    outputPrimaryLabel: optionalString(row.output_primary_label) ?? optionalString(row.label) ?? row.code,
    outputSubLabel: optionalString(row.output_sub_label) ?? optionalString(row.label) ?? "",
  };
}

function mapTagRules(payload: ApiCostStatisticsTagRules): CostStatisticsTagRules {
  return {
    version: Number(payload.version || 1),
    bankAutoTagRulesVersion: Number(payload.bank_auto_tag_rules_version || 1),
    defaultSelectionApplied: Boolean(payload.default_selection_applied),
    selectedTagCodes: stringList(payload.selected_tag_codes) ?? [],
    effectiveSelectedTagCodes: stringList(payload.effective_selected_tag_codes) ?? stringList(payload.selected_tag_codes) ?? [],
    inactiveSelectedTagCodes: stringList(payload.inactive_selected_tag_codes) ?? [],
    activeTags: (payload.active_tags ?? []).map(mapTagRuleTag).filter((tag) => tag.code.trim()),
    canSave: payload.can_save !== false,
  };
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  return apiRequestJson<T>(url, init);
}

function buildScopedUrl(path: string, params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) {
      query.set(key, value);
    }
  }
  return `${path}?${query.toString()}`;
}

export async function fetchCostStatisticsExplorerPage(
  request: CostStatisticsExplorerPageRequest,
): Promise<CostStatisticsExplorerPage> {
  const payload = await requestJson<ApiCostStatisticsExplorerPage>(
    buildScopedUrl("/api/cost-statistics/explorer", {
      scope: request.scope,
      view: request.view,
      project_scope: request.projectScope ?? "active",
      project_name: request.projectName,
      expense_type: request.expenseType,
      payment_account_label: request.paymentAccountLabel,
      bank_tag_primary_label: request.bankTagPrimaryLabel,
      bank_tag_sub_label: request.bankTagSubLabel,
      cursor: request.cursor,
      page_size: request.pageSize ? String(request.pageSize) : undefined,
      include_statistics: request.includeStatistics === false ? "false" : undefined,
    }),
    {
      method: "GET",
      signal: request.signal,
    },
  );

  const facets = payload.facets ?? {};
  return {
    scope: payload.scope,
    view: payload.view,
    summary: mapSummary(payload.summary),
    statistics: payload.statistics ? {
      transactionCount: optionalCount(payload.statistics.transaction_count),
      expenseTransactionCount: optionalCount(payload.statistics.expense_transaction_count),
      incomeTransactionCount: optionalCount(payload.statistics.income_transaction_count),
      costGroupCount: optionalCount(payload.statistics.cost_group_count),
      taggedTransactionCount: optionalCount(payload.statistics.tagged_transaction_count),
      untaggedTransactionCount: optionalCount(payload.statistics.untagged_transaction_count),
      projectCount: optionalCount(payload.statistics.project_count),
      expenseTypeCount: optionalCount(payload.statistics.expense_type_count),
      bankTagCount: optionalCount(payload.statistics.bank_tag_count),
      costTransactionCount: optionalCount(payload.statistics.cost_transaction_count),
    } : undefined,
    availableYears: stringList(payload.available_years) ?? [],
    facets: {
      projects: (facets.projects ?? []).map<CostProjectExplorerRow>((row) => ({
        projectName: row.project_name,
        totalAmount: row.total_amount,
        transactionCount: row.transaction_count,
        expenseTypeCount: row.expense_type_count,
        percentageLabel: optionalString(row.percentage_label),
      })),
      expenseTypes: (facets.expense_types ?? []).map<CostExpenseTypeExplorerRow>((row) => ({
        expenseType: row.expense_type,
        totalAmount: row.total_amount,
        transactionCount: row.transaction_count,
        projectCount: row.project_count,
        percentageLabel: row.percentage_label,
      })),
      bankAccounts: (facets.bank_accounts ?? []).map<CostBankExplorerRow>((row) => ({
        paymentAccountLabel: row.payment_account_label,
        totalAmount: row.total_amount,
        transactionCount: row.transaction_count,
        projectCount: row.project_count,
        percentageLabel: row.percentage_label,
      })),
      bankTagPrimary: (facets.bank_tag_primary ?? []).map<CostBankTagPrimaryExplorerRow>((row) => ({
        primaryLabel: row.primary_label,
        expenseAmount: row.expense_amount,
        incomeAmount: row.income_amount,
        expenseTransactionCount: row.expense_transaction_count,
        incomeTransactionCount: row.income_transaction_count,
        subTagCount: row.sub_tag_count,
      })),
      bankTagSub: (facets.bank_tag_sub ?? []).map<CostBankTagSubExplorerRow>((row) => ({
        primaryLabel: row.primary_label,
        subLabel: row.sub_label,
        expenseAmount: row.expense_amount,
        incomeAmount: row.income_amount,
        expenseTransactionCount: row.expense_transaction_count,
        incomeTransactionCount: row.income_transaction_count,
      })),
    },
    rows: (payload.rows ?? []).map(mapCostTimeRow),
    rowCount: payload.row_count,
    nextCursor: optionalString(payload.next_cursor),
  };
}

export async function fetchCostStatisticsTagRules(signal?: AbortSignal): Promise<CostStatisticsTagRules> {
  const payload = await requestJson<ApiCostStatisticsTagRules>("/api/cost-statistics/tag-rules", {
    method: "GET",
    signal,
  });
  return mapTagRules(payload);
}

export async function saveCostStatisticsTagRules(
  request: SaveCostStatisticsTagRulesRequest,
): Promise<CostStatisticsTagRules> {
  const payload = await requestJson<ApiCostStatisticsTagRules>("/api/cost-statistics/tag-rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_version: request.expectedVersion,
      selected_tag_codes: request.selectedTagCodes,
    }),
  });
  return mapTagRules(payload);
}

export async function fetchCostTransactionDetail(
  transactionId: string,
  view: CostStatisticsView,
  scope: string,
  signal?: AbortSignal,
  projectScope: CostProjectScope = "active",
): Promise<CostTransactionDetail> {
  const payload = await requestJson<ApiCostTransactionDetail>(
    buildScopedUrl(`/api/cost-statistics/transactions/${encodeURIComponent(transactionId)}`, {
      project_scope: projectScope,
      view,
      scope,
    }),
    {
      method: "GET",
      signal,
    },
  );

  return {
    month: payload.month,
    transaction: {
      id: payload.transaction.id,
      projectName: payload.transaction.project_name,
      expenseType: payload.transaction.expense_type,
      expenseContent: payload.transaction.expense_content,
      tradeTime: payload.transaction.trade_time,
      direction: payload.transaction.direction,
      amount: payload.transaction.amount,
      counterpartyName: payload.transaction.counterparty_name,
      paymentAccountLabel: payload.transaction.payment_account_label,
      oaApplicant: payload.transaction.oa_applicant,
      remark: payload.transaction.remark,
      summaryFields: payload.transaction.summary_fields,
      detailFields: payload.transaction.detail_fields,
      costAllocations: (payload.transaction.cost_allocations ?? []).map((allocation) => ({
        rowKey: allocation.row_key,
        projectName: allocation.project_name,
        projectId: allocation.project_id,
        expenseType: allocation.expense_type,
        expenseContent: allocation.expense_content,
        oaApplicant: allocation.oa_applicant,
        amount: allocation.amount,
      })),
      ...bankTagFields(payload.transaction),
    },
  };
}

export type ProjectCostExportParams = {
  month: string;
  view: "project";
  projectScope?: CostProjectScope;
  projectNames: string[];
  expenseTypes?: string[];
  aggregateBy: "month" | "year";
  includeOaDetails?: boolean;
  includeInvoiceDetails?: boolean;
  includeExceptionRows?: boolean;
  includeIgnoredRows?: boolean;
  includeExpenseContentSummary?: boolean;
  sortBy?: "time" | "expense_type" | "amount_desc";
};

export type CostExportParams =
  | {
      month: string;
      view: "time" | "bank_tag";
      projectScope?: CostProjectScope;
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "month";
      projectScope?: CostProjectScope;
    }
  | ProjectCostExportParams
  | {
      month: string;
      view: "expense_type";
      projectScope?: CostProjectScope;
      expenseTypes: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "transaction";
      projectScope?: CostProjectScope;
      transactionId: string;
      projectName?: string;
    };

function parseContentDispositionFileName(contentDisposition: string | null) {
  if (!contentDisposition) {
    return null;
  }
  const extendedMatch = contentDisposition.match(/filename\*\s*=\s*(?:UTF-8''|utf-8'')?([^;]+)/);
  if (extendedMatch?.[1]) {
    try {
      return decodeURIComponent(extendedMatch[1].trim().replace(/^"(.*)"$/, "$1"));
    } catch {
      return extendedMatch[1].trim().replace(/^"(.*)"$/, "$1");
    }
  }
  const match = contentDisposition.match(/filename="([^"]+)"/);
  return match?.[1] ?? null;
}

function buildFallbackExportFileName(params: CostExportParams) {
  if (params.view === "time" || params.view === "bank_tag") {
    const scopeLabel =
      params.startDate && params.endDate
        ? `${params.startDate}至${params.endDate}`
        : params.startMonth && params.endMonth
          ? `${params.startMonth}至${params.endMonth}`
        : params.month === "all"
            ? "全部期间"
            : params.month;
    return `成本统计_${scopeLabel}_${params.view === "bank_tag" ? "按标签统计" : "按时间统计"}.xlsx`;
  }
  if (params.view === "month") {
    return `成本统计_${params.month}_月份汇总.xlsx`;
  }
  if (params.view === "project") {
    const projectLabel =
      params.projectNames.length === 1 ? params.projectNames[0] : `${params.projectNames[0]}等${params.projectNames.length}个项目`;
    return `成本统计_全部期间_按项目统计_按${params.aggregateBy === "month" ? "月" : "年"}_${projectLabel}.xlsx`;
  }
  if (params.view === "expense_type") {
    const scopeLabel =
      params.startDate && params.endDate
        ? `${params.startDate}至${params.endDate}`
        : params.startMonth && params.endMonth
          ? `${params.startMonth}至${params.endMonth}`
        : params.month === "all"
            ? "全部期间"
            : params.month;
    const expenseTypeLabel =
      params.expenseTypes.length === 1 ? params.expenseTypes[0] : `${params.expenseTypes[0]}等${params.expenseTypes.length}类`;
    return `成本统计_${scopeLabel}_按费用类型统计_${expenseTypeLabel}.xlsx`;
  }
  if (params.view === "transaction") {
    return `成本统计_${params.month}_流水详情_${params.projectName ?? "未命名项目"}_${params.transactionId}.xlsx`;
  }
  throw new Error(`unsupported cost statistics export view: ${params.view}`);
}

function buildCostStatisticsQuery(
  params: CostExportParams | PreviewCostExportParams,
  options: {
    includeProjectExportOptions: boolean;
  },
) {
  const query = new URLSearchParams({
    month: params.month,
    view: params.view,
  });
  query.set("project_scope", params.projectScope ?? "active");

  if ("startMonth" in params && params.startMonth) {
    query.set("start_month", params.startMonth);
  }
  if ("endMonth" in params && params.endMonth) {
    query.set("end_month", params.endMonth);
  }
  if ("startDate" in params && params.startDate) {
    query.set("start_date", params.startDate);
  }
  if ("endDate" in params && params.endDate) {
    query.set("end_date", params.endDate);
  }

  if (params.view === "project") {
    for (const projectName of params.projectNames) {
      query.append("project_name", projectName);
    }
    query.set("aggregate_by", params.aggregateBy);
    for (const expenseType of params.expenseTypes ?? []) {
      query.append("expense_type", expenseType);
    }
    if (options.includeProjectExportOptions) {
      const projectParams = params as ProjectCostExportParams;
      query.set("include_oa_details", String(projectParams.includeOaDetails ?? true));
      query.set("include_invoice_details", String(projectParams.includeInvoiceDetails ?? true));
      query.set("include_exception_rows", String(projectParams.includeExceptionRows ?? true));
      query.set("include_ignored_rows", String(projectParams.includeIgnoredRows ?? true));
      query.set("include_expense_content_summary", String(projectParams.includeExpenseContentSummary ?? true));
      query.set("sort_by", projectParams.sortBy ?? "time");
    }
  }

  if (params.view === "expense_type") {
    for (const expenseType of params.expenseTypes) {
      query.append("expense_type", expenseType);
    }
  }

  if (params.view === "transaction") {
    query.set("transaction_id", params.transactionId);
    if (params.projectName) {
      query.set("project_name", params.projectName);
    }
  }

  return query;
}

async function readExportBlob(response: Response) {
  if (typeof response.blob === "function") {
    return response.blob();
  }
  if (typeof response.text === "function") {
    const text = await response.text();
    return new Blob([text], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
  }
  if (typeof response.json === "function") {
    const payload = await response.json();
    return new Blob([JSON.stringify(payload)], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
  }
  throw new Error("cost_statistics_export_blob_unavailable");
}

function textField(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function exportErrorMessageFromPayload(payload: unknown) {
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const message = textField((payload as { message?: unknown }).message);
  if (message) {
    return message;
  }
  const errorValue = (payload as { error?: unknown }).error;
  if (errorValue && typeof errorValue === "object") {
    const nestedMessage = textField((errorValue as { message?: unknown }).message);
    if (nestedMessage) {
      return nestedMessage;
    }
  }
  return textField(errorValue);
}

function exportErrorMessageFromText(rawText: string, fallback: string) {
  const trimmedText = rawText.trim();
  if (!trimmedText) {
    return fallback;
  }
  try {
    const payload = JSON.parse(trimmedText);
    return exportErrorMessageFromPayload(payload) || fallback;
  } catch {
    return trimmedText;
  }
}

export async function exportCostStatisticsView(params: CostExportParams, signal?: AbortSignal) {
  const query = buildCostStatisticsQuery(params, { includeProjectExportOptions: true });
  const response = await apiFetch(`/api/cost-statistics/export?${query.toString()}`, { method: "GET", signal });
  const contentType = typeof response.headers?.get === "function" ? response.headers.get("Content-Type") ?? "" : "";

  if (!response.ok) {
    const rawText = await response.text();
    if (looksLikeHtmlResponse(rawText, contentType)) {
      throw new Error("成本统计导出接口返回了 HTML 页面，请确认后端服务和 /api 代理已正常启动。");
    }
    throw new Error(exportErrorMessageFromText(rawText, "cost_statistics_export_failed"));
  }

  if (contentType.toLowerCase().includes("text/html")) {
    const rawText = await response.text();
    if (looksLikeHtmlResponse(rawText, contentType)) {
      throw new Error("成本统计导出接口返回了 HTML 页面，请确认后端服务和 /api 代理已正常启动。");
    }
    throw new Error(rawText || `成本统计导出接口返回的不是 xlsx 文件：${contentType}`);
  }
  const blob = await readExportBlob(response);
  const contentDisposition =
    typeof response.headers?.get === "function" ? response.headers.get("Content-Disposition") : null;
  const fileName =
    parseContentDispositionFileName(contentDisposition) ?? buildFallbackExportFileName(params);

  return {
    blob,
    fileName,
  };
}

export type PreviewCostExportParams =
  | {
      month: string;
      view: "time" | "bank_tag";
      projectScope?: CostProjectScope;
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "project";
      projectScope?: CostProjectScope;
      projectNames: string[];
      aggregateBy: "month" | "year";
      expenseTypes?: string[];
    }
  | {
      month: string;
      view: "expense_type";
      projectScope?: CostProjectScope;
      expenseTypes: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    };

export async function fetchCostStatisticsExportPreview(
  params: PreviewCostExportParams,
  signal?: AbortSignal,
): Promise<CostStatisticsExportPreview> {
  const query = buildCostStatisticsQuery(params, { includeProjectExportOptions: false });
  const payload = await requestJson<ApiCostStatisticsExportPreview>(
    `/api/cost-statistics/export-preview?${query.toString()}`,
    {
      method: "GET",
      signal,
    },
  );

  return {
    view: payload.view,
    fileName: payload.file_name,
    scopeLabel: payload.scope_label,
    summary: {
      rowCount: payload.summary.row_count,
      transactionCount: payload.summary.transaction_count,
      totalAmount: payload.summary.total_amount,
      expenseAmount: optionalString(payload.summary.expense_amount),
      incomeAmount: optionalString(payload.summary.income_amount),
      expenseTransactionCount: payload.summary.expense_transaction_count ?? undefined,
      incomeTransactionCount: payload.summary.income_transaction_count ?? undefined,
      sheetCount: payload.summary.sheet_count,
    },
    sheetNames: payload.sheet_names,
    columns: payload.columns,
    rows: payload.rows,
  };
}
