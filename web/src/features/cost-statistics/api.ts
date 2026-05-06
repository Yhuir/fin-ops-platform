import type {
  CostExpenseTypeExplorerRow,
  CostProjectScope,
  CostProjectExplorerRow,
  CostStatisticsExportPreview,
  CostStatisticsExplorer,
  CostMonthStatistics,
  CostProjectStatistics,
  CostTimeRow,
  CostTransactionDetail,
} from "./types";

type ApiCostSummary = {
  row_count: number;
  transaction_count: number;
  total_amount: string;
};

type ApiCostMonthSummaryRow = {
  project_name: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  transaction_count: number;
  sample_transaction_ids: string[];
};

type ApiCostMonthStatistics = {
  month: string;
  summary: ApiCostSummary;
  rows: ApiCostMonthSummaryRow[];
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
};

type ApiCostProjectExplorerRow = {
  project_name: string;
  total_amount: string;
  transaction_count: number;
  expense_type_count: number;
};

type ApiCostExpenseTypeExplorerRow = {
  expense_type: string;
  total_amount: string;
  transaction_count: number;
  project_count: number;
};

type ApiCostStatisticsExplorer = {
  month: string;
  summary: ApiCostSummary;
  time_rows: ApiCostTimeRow[];
  project_rows: ApiCostProjectExplorerRow[];
  expense_type_rows: ApiCostExpenseTypeExplorerRow[];
};

type ApiCostProjectRow = {
  transaction_id: string;
  trade_time: string;
  direction: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  counterparty_name: string;
  payment_account_label: string;
};

type ApiCostProjectStatistics = {
  month: string;
  project_name: string;
  summary: ApiCostSummary;
  rows: ApiCostProjectRow[];
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
  };
};

type ApiCostStatisticsExportPreview = {
  view: "time" | "project" | "expense_type";
  file_name: string;
  scope_label: string;
  summary: ApiCostSummary & {
    sheet_count: number;
  };
  sheet_names: string[];
  columns: string[];
  rows: string[][];
};

type ExplorerCacheEntry = {
  payload: CostStatisticsExplorer;
  cachedAt: number;
};

const COST_EXPLORER_CACHE_TTL_MS = 5 * 60 * 1000;
const costExplorerCache = new Map<string, ExplorerCacheEntry>();

function mapSummary(summary: ApiCostSummary) {
  return {
    rowCount: summary.row_count,
    transactionCount: summary.transaction_count,
    totalAmount: summary.total_amount,
  };
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const payload = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(typeof payload === "object" && payload ? JSON.stringify(payload) : "request failed");
  }
  return payload;
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

function buildExplorerCacheKey(month: string, projectScope: CostProjectScope) {
  return `${projectScope}:${month}`;
}

export function getCachedCostStatisticsExplorer(
  month: string,
  projectScope: CostProjectScope = "active",
): CostStatisticsExplorer | null {
  const entry = costExplorerCache.get(buildExplorerCacheKey(month, projectScope));
  if (!entry) {
    return null;
  }
  if (Date.now() - entry.cachedAt > COST_EXPLORER_CACHE_TTL_MS) {
    costExplorerCache.delete(buildExplorerCacheKey(month, projectScope));
    return null;
  }
  return entry.payload;
}

export function clearCostStatisticsExplorerCache() {
  costExplorerCache.clear();
}

export async function fetchCostStatisticsMonth(
  month: string,
  signal?: AbortSignal,
  projectScope: CostProjectScope = "active",
): Promise<CostMonthStatistics> {
  const payload = await requestJson<ApiCostMonthStatistics>(buildScopedUrl("/api/cost-statistics", {
    month,
    project_scope: projectScope,
  }), {
    method: "GET",
    signal,
  });

  return {
    month: payload.month,
    summary: mapSummary(payload.summary),
    rows: payload.rows.map((row) => ({
      projectName: row.project_name,
      expenseType: row.expense_type,
      expenseContent: row.expense_content,
      amount: row.amount,
      transactionCount: row.transaction_count,
      sampleTransactionIds: row.sample_transaction_ids,
    })),
  };
}

export async function fetchCostStatisticsExplorer(
  month: string,
  signal?: AbortSignal,
  projectScope: CostProjectScope = "active",
): Promise<CostStatisticsExplorer> {
  const payload = await requestJson<ApiCostStatisticsExplorer>(
    buildScopedUrl("/api/cost-statistics/explorer", {
      month,
      project_scope: projectScope,
    }),
    {
      method: "GET",
      signal,
    },
  );

  const mappedPayload = {
    month: payload.month,
    summary: mapSummary(payload.summary),
    timeRows: payload.time_rows.map<CostTimeRow>((row) => ({
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
    })),
    projectRows: payload.project_rows.map<CostProjectExplorerRow>((row) => ({
      projectName: row.project_name,
      totalAmount: row.total_amount,
      transactionCount: row.transaction_count,
      expenseTypeCount: row.expense_type_count,
    })),
    expenseTypeRows: payload.expense_type_rows.map<CostExpenseTypeExplorerRow>((row) => ({
      expenseType: row.expense_type,
      totalAmount: row.total_amount,
      transactionCount: row.transaction_count,
      projectCount: row.project_count,
    })),
  };
  costExplorerCache.set(buildExplorerCacheKey(month, projectScope), {
    payload: mappedPayload,
    cachedAt: Date.now(),
  });
  return mappedPayload;
}

export async function fetchProjectCostStatistics(
  month: string,
  projectName: string,
  signal?: AbortSignal,
  projectScope: CostProjectScope = "active",
): Promise<CostProjectStatistics> {
  const payload = await requestJson<ApiCostProjectStatistics>(
    buildScopedUrl(`/api/cost-statistics/projects/${encodeURIComponent(projectName)}`, {
      month,
      project_scope: projectScope,
    }),
    {
      method: "GET",
      signal,
    },
  );

  return {
    month: payload.month,
    projectName: payload.project_name,
    summary: mapSummary(payload.summary),
    rows: payload.rows.map((row) => ({
      transactionId: row.transaction_id,
      tradeTime: row.trade_time,
      direction: row.direction,
      projectName: projectName,
      expenseType: row.expense_type,
      expenseContent: row.expense_content,
      amount: row.amount,
      counterpartyName: row.counterparty_name,
      paymentAccountLabel: row.payment_account_label,
    })),
  };
}

export async function fetchCostTransactionDetail(
  transactionId: string,
  signal?: AbortSignal,
  projectScope: CostProjectScope = "active",
): Promise<CostTransactionDetail> {
  const payload = await requestJson<ApiCostTransactionDetail>(
    buildScopedUrl(`/api/cost-statistics/transactions/${encodeURIComponent(transactionId)}`, {
      project_scope: projectScope,
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
      view: "time";
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
  if (params.view === "time") {
    const scopeLabel =
      params.startDate && params.endDate
        ? `${params.startDate}至${params.endDate}`
        : params.startMonth && params.endMonth
          ? `${params.startMonth}至${params.endMonth}`
        : params.month === "all"
            ? "全部期间"
            : params.month;
    return `成本统计_${scopeLabel}_按时间统计.xlsx`;
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
  return `成本统计_${params.month}_流水详情_${params.projectName ?? "未命名项目"}_${params.transactionId}.xlsx`;
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

export async function exportCostStatisticsView(params: CostExportParams) {
  const query = buildCostStatisticsQuery(params, { includeProjectExportOptions: true });
  const response = await fetch(`/api/cost-statistics/export?${query.toString()}`, { method: "GET" });
  if (!response.ok) {
    throw new Error("cost_statistics_export_failed");
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
      view: "time";
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
      sheetCount: payload.summary.sheet_count,
    },
    sheetNames: payload.sheet_names,
    columns: payload.columns,
    rows: payload.rows,
  };
}
