import type {
  CostBankExplorerRow,
  CostBankTagPrimaryExplorerRow,
  CostBankTagSubExplorerRow,
  CostTagExplorerRow,
  CostStatisticsManualAllocationSummary,
  CostSourceAllocations,
  CostProjectExplorerRow,
  CostStatisticsExportPreview,
  CostStatisticsExplorerPage,
  CostStatisticsExplorerPageRequest,
  CostStatisticsNoOaRules,
  CostStatisticsManualAllocationPage,
  CostStatisticsManualAllocationPageRequest,
  CostStatisticsManualAllocationTask,
  CostStatisticsTagRuleTag,
  CostStatisticsView,
  CostExplorerEntryRow,
  CostEntryDetail,
  SaveCostStatisticsNoOaRulesRequest,
  SaveCostStatisticsManualAllocationRequest,
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

type ApiCostExplorerEntryRow = {
  entry_id: string;
  row_kind: "bank_transaction" | "oa_allocation";
  transaction_id?: string | null;
  allocation_id?: string | null;
  occurred_at: string | null;
  allocation_state?: "source_resolved";
  direction: string;
  project_name: string;
  expense_type: string;
  expense_content: string;
  amount: string;
  counterparty_name: string;
  oa_applicant: string;
  payment_account_label: string;
  bank_account_label?: string | null;
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
  primary_tag_count: number;
};

type ApiCostTagExplorerRow = {
  key: string; label: string; total_amount: string; row_count: number; project_count: number;
};

type ApiCostBankExplorerRow = {
  bank_account_label: string;
  total_amount: string;
  project_count: number;
};

type ApiCostBankTagPrimaryExplorerRow = {
  primary_label: string;
  expense_amount: string;
  income_amount: string;
  net_outflow_amount: string;
  expense_transaction_count: number;
  income_transaction_count: number;
  transaction_count: number;
  sub_tag_count: number;
};

type ApiCostBankTagSubExplorerRow = {
  primary_label: string;
  sub_label: string;
  expense_amount: string;
  income_amount: string;
  net_outflow_amount: string;
  expense_transaction_count: number;
  income_transaction_count: number;
  transaction_count: number;
};

type ApiCostStatisticsExplorerPage = {
  scope: string;
  view: CostStatisticsExplorerPage["view"];
  summary: ApiCostSummary;
  statistics?: {
    project_count?: number | null;
    primary_tag_count?: number | null;
    bank_account_count?: number | null;
    cost_transaction_count?: number | null;
    transaction_count?: number | null;
    expense_transaction_count?: number | null;
    income_transaction_count?: number | null;
    untagged_transaction_count?: number | null;
    bank_tag_count?: number | null;
  } | null;
  available_years?: string[] | null;
  facets?: {
    projects?: ApiCostProjectExplorerRow[] | null;
    cost_tag_primary?: ApiCostTagExplorerRow[] | null;
    cost_tag_sub?: ApiCostTagExplorerRow[] | null;
    bank_accounts?: ApiCostBankExplorerRow[] | null;
    bank_tag_primary?: ApiCostBankTagPrimaryExplorerRow[] | null;
    bank_tag_sub?: ApiCostBankTagSubExplorerRow[] | null;
  } | null;
  rows?: ApiCostExplorerEntryRow[] | null;
  row_count: number;
  next_cursor?: string | null;
  allocation_quality?: {
    excluded_allocation_count: number;
    excluded_by_reason?: Array<{ reason: string; count: number }> | null;
    pending_manual_allocation_count?: number | null;
    stale_manual_allocation_count?: number | null;
    undated_amount: string;
    undated_row_count: number;
  } | null;
};

type ApiCostStatisticsManualAllocationTask = {
  relation_case_id: string;
  relation_version: number;
  source_fingerprint: string;
  scope_version: number;
  status: "pending" | "allocated";
  pending_reasons: string[];
  amounts_fixed: boolean;
  source_allocations: ApiCostSourceAllocations | null;
  suggested_source_allocations: ApiCostSourceAllocations | null;
  oa_total: string;
  gross_outflow_total: string;
  wrong_payment_refund_total: string;
  net_outflow_total: string;
  units: Array<{
    unit_id: string;
    oa_id: string;
    oa_apply_type: string;
    expense_item_id: string;
    project_id: string;
    project_name: string;
    expense_type: string;
    expense_content: string;
    oa_applicant: string;
    oa_original_amount: string;
  }>;
  bank_events: Array<{
    transaction_id: string;
    event_kind: "outflow" | "wrong_payment_refund";
    in_project_cost_scope: boolean;
    amount: string;
    trade_time: string;
    counterparty_name: string;
    tags: string[];
    bank_account_label: string;
    bank_tag_code: string;
    bank_tag_primary_label: string;
    bank_tag_sub_label: string;
  }>;
  allocations: Array<{
    unit_id: string;
    amount: string;
  }>;
  non_cost_amount: string;
  non_cost_reason: string;
  version: number;
  updated_by: string;
  updated_at: string;
  can_save: boolean;
};

type ApiCostSourceAllocations = {
  cost_lines: Array<{ unit_id: string; bank_transaction_id: string; amount: string }>;
  refund_links: Array<{ refund_transaction_id: string; bank_transaction_id: string; amount: string }>;
  non_cost_lines: Array<{ bank_transaction_id: string; amount: string }>;
};

type ApiCostManualAllocationSummary = Omit<ApiCostStatisticsManualAllocationTask, "units" | "bank_events" | "allocations" | "source_allocations" | "suggested_source_allocations"> & {
  project_names: string[]; unit_count: number; bank_event_count: number;
};

type ApiCostStatisticsManualAllocationPage = {
  items: ApiCostManualAllocationSummary[];
  row_count: number;
  counts: { pending: number; allocated: number };
  next_cursor?: string | null;
};

type ApiCostBankTransactionDetail = {
  month: string;
  kind: "bank_transaction";
  bank_transaction: {
    id: string;
    expense_content: string;
    trade_time: string;
    direction: string;
    amount: string;
    counterparty_name: string;
    payment_account_label: string;
    bank_account_label: string;
    remark: string;
    bank_tag_code?: string | null;
    bank_tag_label?: string | null;
    bank_tag_primary_label?: string | null;
    bank_tag_sub_label?: string | null;
    bank_tag_label_path?: string[] | null;
    project_name?: string | null;
    expense_type?: string | null;
  };
};

type ApiCostAllocationDetail = {
  month: string;
  kind: "oa_allocation";
  allocation: {
    allocation_id: string;
    transaction_id: string | null;
    occurred_at: string | null;
    allocation_state: "source_resolved";
    bank_tag_code: string;
    bank_tag_primary_label: string;
    bank_tag_sub_label: string;
    bank_tag_label_path: string[];
    oa_id: string;
    oa_apply_type: string;
    expense_item_id: string;
    oa_completed_at: string;
    project_name: string;
    project_id: string;
    expense_type: string;
    expense_content: string;
    amount: string;
    counterparty_name: string;
    payment_account_label: string;
    bank_account_label: string;
    oa_applicant: string;
    oa_original_amount: string;
    oa_allocation_weight: string;
    bank_event_amount: string;
  };
  payment_evidence: Array<{
    transaction_id: string;
    trade_time: string;
    amount: string;
    direction: string;
    counterparty_name: string;
    payment_account_label: string;
    remark: string;
    bank_tag_code: string;
    bank_tag_label: string;
  }>;
  reconciliation: {
    relation_case_id: string;
    oa_total: string;
    gross_outflow_total: string;
    wrong_payment_refund_total: string;
    net_outflow_total: string;
    difference: string;
    cash_payment_ratio: string;
    status: "balanced" | "mismatch";
  };
};

type ApiCostStatisticsExportPreview = {
  view: "time" | "bank_tag" | "bank_account" | "project" | "cost_tag";
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

type ApiCostStatisticsRulesBase = {
  version: number;
  bank_auto_tag_rules_version: number;
  selected_tag_codes?: string[] | null;
  inactive_selected_tag_codes?: string[] | null;
  available_tags?: ApiCostStatisticsTagRuleTag[] | null;
  can_save?: boolean | null;
};

type ApiCostStatisticsNoOaRules = ApiCostStatisticsRulesBase & {
  projects?: Array<{
    id: string;
    display_name: string;
    tag_codes?: string[] | null;
  }> | null;
};

function mapSummary(summary: ApiCostSummary) {
  return {
    rowCount: summary.row_count,
    transactionCount: summary.transaction_count,
    totalAmount: summary.total_amount,
    expenseAmount: optionalString(summary.expense_amount),
    incomeAmount: optionalString(summary.income_amount),
    expenseTransactionCount: optionalCount(summary.expense_transaction_count),
    incomeTransactionCount: optionalCount(summary.income_transaction_count),
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
  return {
    bankTagCode: row.bank_tag_code ?? "",
    bankTagLabel: row.bank_tag_label ?? "",
    bankTagPrimaryLabel: row.bank_tag_primary_label ?? "",
    bankTagSubLabel: row.bank_tag_sub_label ?? "",
    bankTagLabelPath: row.bank_tag_label_path ?? [],
  };
}

function mapCostExplorerEntryRow(row: ApiCostExplorerEntryRow): CostExplorerEntryRow {
  return {
    entryId: row.entry_id,
    rowKind: row.row_kind,
    transactionId: row.transaction_id ?? null,
    allocationState: row.row_kind === "bank_transaction" ? "source_resolved" : row.allocation_state!,
    allocationId: optionalString(row.allocation_id),
    occurredAt: row.occurred_at,
    direction: row.direction,
    projectName: row.project_name,
    expenseType: row.expense_type,
    expenseContent: row.expense_content,
    amount: row.amount,
    counterpartyName: row.counterparty_name,
    oaApplicant: row.oa_applicant,
    paymentAccountLabel: row.payment_account_label,
    bankAccountLabel: optionalString(row.bank_account_label) ?? "",
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

function mapNoOaRules(payload: ApiCostStatisticsNoOaRules): CostStatisticsNoOaRules {
  return {
    version: Number(payload.version || 1),
    bankAutoTagRulesVersion: Number(payload.bank_auto_tag_rules_version || 1),
    projects: (payload.projects ?? []).map((project) => ({
      id: project.id,
      displayName: project.display_name,
      tagCodes: stringList(project.tag_codes) ?? [],
    })),
    inactiveSelectedTagCodes: stringList(payload.inactive_selected_tag_codes) ?? [],
    availableTags: (payload.available_tags ?? []).map(mapTagRuleTag).filter((tag) => tag.code.trim()),
    canSave: payload.can_save !== false,
  };
}

function mapManualAllocationTask(
  task: ApiCostStatisticsManualAllocationTask,
): CostStatisticsManualAllocationTask {
  return {
    relationCaseId: task.relation_case_id,
    relationVersion: task.relation_version,
    sourceFingerprint: task.source_fingerprint, scopeVersion: task.scope_version,
    status: task.status,
    pendingReasons: task.pending_reasons,
    amountsFixed: task.amounts_fixed,
    suggestedSourceAllocations: task.suggested_source_allocations === null ? null : mapSourceAllocations(task.suggested_source_allocations),
    sourceAllocations: task.source_allocations === null ? null : mapSourceAllocations(task.source_allocations),
    oaTotal: task.oa_total,
    grossOutflowTotal: task.gross_outflow_total,
    wrongPaymentRefundTotal: task.wrong_payment_refund_total,
    netOutflowTotal: task.net_outflow_total,
    units: task.units.map((unit) => ({
      unitId: unit.unit_id,
      oaId: unit.oa_id,
      oaApplyType: unit.oa_apply_type,
      expenseItemId: unit.expense_item_id,
      projectId: unit.project_id,
      projectName: unit.project_name,
      expenseType: unit.expense_type,
      expenseContent: unit.expense_content,
      oaApplicant: unit.oa_applicant,
      oaOriginalAmount: unit.oa_original_amount,
    })),
    bankEvents: task.bank_events.map((event) => ({
      transactionId: event.transaction_id,
      eventKind: event.event_kind,
      inProjectCostScope: event.in_project_cost_scope,
      amount: event.amount,
      tradeTime: event.trade_time,
      counterpartyName: event.counterparty_name,
      tags: event.tags,
      bankAccountLabel: event.bank_account_label,
      bankTagCode: event.bank_tag_code,
      bankTagPrimaryLabel: event.bank_tag_primary_label,
      bankTagSubLabel: event.bank_tag_sub_label,
    })),
    allocations: task.allocations.map((line) => ({
      unitId: line.unit_id,
      amount: line.amount,
    })),
    nonCostAmount: task.non_cost_amount,
    nonCostReason: task.non_cost_reason,
    version: task.version,
    updatedBy: task.updated_by,
    updatedAt: task.updated_at,
    canSave: task.can_save,
  };
}

function mapSourceAllocations(value: ApiCostSourceAllocations): CostSourceAllocations {
  return {
    costLines: value.cost_lines.map(line => ({ unitId: line.unit_id, bankTransactionId: line.bank_transaction_id, amount: line.amount })),
    refundLinks: value.refund_links.map(line => ({ refundTransactionId: line.refund_transaction_id, bankTransactionId: line.bank_transaction_id, amount: line.amount })),
    nonCostLines: value.non_cost_lines.map(line => ({ bankTransactionId: line.bank_transaction_id, amount: line.amount })),
  };
}

function mapManualSummary(task: ApiCostManualAllocationSummary): CostStatisticsManualAllocationSummary {
  return {
    relationCaseId: task.relation_case_id, relationVersion: task.relation_version,
    sourceFingerprint: task.source_fingerprint, scopeVersion: task.scope_version, status: task.status, pendingReasons: task.pending_reasons,
    amountsFixed: task.amounts_fixed, oaTotal: task.oa_total, grossOutflowTotal: task.gross_outflow_total,
    wrongPaymentRefundTotal: task.wrong_payment_refund_total, netOutflowTotal: task.net_outflow_total,
    nonCostAmount: task.non_cost_amount, nonCostReason: task.non_cost_reason,
    version: task.version, updatedBy: task.updated_by, updatedAt: task.updated_at, canSave: task.can_save,
    projectNames: task.project_names, unitCount: task.unit_count, bankEventCount: task.bank_event_count,
  };
}

function mapCostTagFacet(row: ApiCostTagExplorerRow): CostTagExplorerRow {
  return { key: row.key, label: row.label, totalAmount: row.total_amount, rowCount: row.row_count, projectCount: row.project_count };
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
      project_name: request.view === "project" || request.view === "bank_account" ? request.projectName : undefined,
      bank_tag_primary_key: ["project", "bank_account", "cost_tag"].includes(request.view) ? request.bankTagPrimaryKey : undefined,
      bank_tag_sub_key: ["project", "bank_account", "cost_tag"].includes(request.view) ? request.bankTagSubKey : undefined,
      bank_account_label: request.view === "bank_account" ? request.bankAccountLabel : undefined,
      bank_tag_primary_label: request.view === "bank_tag" ? request.bankTagPrimaryLabel : undefined,
      bank_tag_sub_label: request.view === "bank_tag" ? request.bankTagSubLabel : undefined,
      query: request.query,
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
      projectCount: optionalCount(payload.statistics.project_count),
      primaryTagCount: optionalCount(payload.statistics.primary_tag_count),
      bankAccountCount: optionalCount(payload.statistics.bank_account_count),
      costTransactionCount: optionalCount(payload.statistics.cost_transaction_count),
      transactionCount: optionalCount(payload.statistics.transaction_count),
      expenseTransactionCount: optionalCount(payload.statistics.expense_transaction_count),
      incomeTransactionCount: optionalCount(payload.statistics.income_transaction_count),
      untaggedTransactionCount: optionalCount(payload.statistics.untagged_transaction_count),
      bankTagCount: optionalCount(payload.statistics.bank_tag_count),
    } : undefined,
    availableYears: stringList(payload.available_years) ?? [],
    facets: {
      projects: (facets.projects ?? []).map<CostProjectExplorerRow>((row) => ({
        projectName: row.project_name,
        totalAmount: row.total_amount,
        primaryTagCount: row.primary_tag_count,
      })),
      costTagPrimary: (facets.cost_tag_primary ?? []).map(mapCostTagFacet),
      costTagSub: (facets.cost_tag_sub ?? []).map(mapCostTagFacet),
      bankAccounts: (facets.bank_accounts ?? []).map<CostBankExplorerRow>((row) => ({
        bankAccountLabel: row.bank_account_label,
        totalAmount: row.total_amount,
        projectCount: row.project_count,
      })),
      bankTagPrimary: (facets.bank_tag_primary ?? []).map<CostBankTagPrimaryExplorerRow>((row) => ({
        primaryLabel: row.primary_label,
        expenseAmount: row.expense_amount,
        incomeAmount: row.income_amount,
        netOutflowAmount: row.net_outflow_amount,
        expenseTransactionCount: row.expense_transaction_count,
        incomeTransactionCount: row.income_transaction_count,
        transactionCount: row.transaction_count,
        subTagCount: row.sub_tag_count,
      })),
      bankTagSub: (facets.bank_tag_sub ?? []).map<CostBankTagSubExplorerRow>((row) => ({
        primaryLabel: row.primary_label,
        subLabel: row.sub_label,
        expenseAmount: row.expense_amount,
        incomeAmount: row.income_amount,
        netOutflowAmount: row.net_outflow_amount,
        expenseTransactionCount: row.expense_transaction_count,
        incomeTransactionCount: row.income_transaction_count,
        transactionCount: row.transaction_count,
      })),
    },
    rows: (payload.rows ?? []).map(mapCostExplorerEntryRow),
    allocationQuality: payload.allocation_quality ? {
      excludedAllocationCount: payload.allocation_quality.excluded_allocation_count,
      excludedByReason: (payload.allocation_quality.excluded_by_reason ?? []).map((item) => ({
        reason: item.reason,
        count: item.count,
      })),
      pendingManualAllocationCount: optionalCount(payload.allocation_quality.pending_manual_allocation_count) ?? 0,
      staleManualAllocationCount: optionalCount(payload.allocation_quality.stale_manual_allocation_count) ?? 0,
      undatedAmount: payload.allocation_quality.undated_amount,
      undatedRowCount: payload.allocation_quality.undated_row_count,
    } : undefined,
    rowCount: payload.row_count,
    nextCursor: optionalString(payload.next_cursor),
  };
}

export async function fetchCostStatisticsManualAllocations(
  request: CostStatisticsManualAllocationPageRequest,
): Promise<CostStatisticsManualAllocationPage> {
  const query = new URLSearchParams({
    page_size: String(request.pageSize ?? 50),
    status: request.status,
  });
  if (request.cursor) query.set("cursor", request.cursor);
  if (request.query) query.set("query", request.query);
  const payload = await requestJson<ApiCostStatisticsManualAllocationPage>(
    `/api/cost-statistics/manual-allocations?${query.toString()}`,
    { method: "GET", signal: request.signal },
  );
  return {
    items: payload.items.map(mapManualSummary),
    rowCount: payload.row_count,
    counts: payload.counts,
    nextCursor: optionalString(payload.next_cursor),
  };
}

export async function fetchCostStatisticsManualAllocation(caseId: string, signal?: AbortSignal): Promise<CostStatisticsManualAllocationTask> {
  const task = await apiRequestJson<ApiCostStatisticsManualAllocationTask>(`/api/cost-statistics/manual-allocations/${encodeURIComponent(caseId)}`, { method: "GET", signal }, { timeoutMs: 15000, timeoutMessage: "任务读取超时，请重试" });
  return mapManualAllocationTask(task);
}

export async function saveCostStatisticsManualAllocation(
  request: SaveCostStatisticsManualAllocationRequest,
): Promise<CostStatisticsManualAllocationTask> {
  const payload = await apiRequestJson<ApiCostStatisticsManualAllocationTask>(
    `/api/cost-statistics/manual-allocations/${encodeURIComponent(request.relationCaseId)}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        relation_case_id: request.relationCaseId,
        expected_version: request.expectedVersion,
        source_fingerprint: request.sourceFingerprint,
        scope_version: request.scopeVersion,
        allocations: request.allocations.map((line) => ({
          unit_id: line.unitId,
          amount: line.amount,
        })),
        source_allocations: {
        cost_lines: request.sourceAllocations.costLines.map(line => ({ unit_id: line.unitId, bank_transaction_id: line.bankTransactionId, amount: line.amount })),
        refund_links: request.sourceAllocations.refundLinks.map(line => ({ refund_transaction_id: line.refundTransactionId, bank_transaction_id: line.bankTransactionId, amount: line.amount })),
        non_cost_lines: request.sourceAllocations.nonCostLines.map(line => ({ bank_transaction_id: line.bankTransactionId, amount: line.amount })),
      },
      non_cost_amount: request.nonCostAmount,
        non_cost_reason: request.nonCostReason,
      }),
    },
    { timeoutMs: 15000, timeoutMessage: "保存结果待确认", allowHtmlFallback: false },
  );
  return mapManualAllocationTask(payload);
}

export async function fetchCostStatisticsNoOaRules(signal?: AbortSignal): Promise<CostStatisticsNoOaRules> {
  const payload = await requestJson<ApiCostStatisticsNoOaRules>("/api/cost-statistics/no-oa-rules", {
    method: "GET",
    signal,
  });
  return mapNoOaRules(payload);
}

export async function saveCostStatisticsNoOaRules(
  request: SaveCostStatisticsNoOaRulesRequest,
): Promise<CostStatisticsNoOaRules> {
  const payload = await requestJson<ApiCostStatisticsNoOaRules>("/api/cost-statistics/no-oa-rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_version: request.expectedVersion,
      projects: request.projects.map((project) => ({
        id: project.id,
        display_name: project.displayName,
        tag_codes: project.tagCodes,
      })),
    }),
  });
  return mapNoOaRules(payload);
}

export async function fetchCostEntryDetail(
  row: Pick<CostExplorerEntryRow, "entryId" | "rowKind">,
  view: CostStatisticsView,
  scope: string,
  signal?: AbortSignal,
): Promise<CostEntryDetail> {
  const path = row.rowKind === "bank_transaction"
    ? `/api/cost-statistics/bank-transactions/${encodeURIComponent(row.entryId)}`
    : `/api/cost-statistics/allocations/${encodeURIComponent(row.entryId)}`;
  const payload = await requestJson<ApiCostBankTransactionDetail | ApiCostAllocationDetail>(
    buildScopedUrl(path, {
      view,
      scope,
    }),
    {
      method: "GET",
      signal,
    },
  );

  if (payload.kind === "bank_transaction") {
    return {
      month: payload.month,
      kind: payload.kind,
      bankTransaction: {
        id: payload.bank_transaction.id,
        expenseContent: payload.bank_transaction.expense_content,
        tradeTime: payload.bank_transaction.trade_time,
        direction: payload.bank_transaction.direction,
        amount: payload.bank_transaction.amount,
        counterpartyName: payload.bank_transaction.counterparty_name,
        paymentAccountLabel: payload.bank_transaction.payment_account_label,
        remark: payload.bank_transaction.remark,
        projectName: optionalString(payload.bank_transaction.project_name),
        expenseType: optionalString(payload.bank_transaction.expense_type),
        ...bankTagFields(payload.bank_transaction),
      },
    };
  }
  const allocation = payload.allocation;
  return {
    month: payload.month,
    kind: payload.kind,
    allocation: {
      allocationId: allocation.allocation_id,
      transactionId: allocation.transaction_id,
      occurredAt: allocation.occurred_at,
      allocationState: allocation.allocation_state,
      ...bankTagFields(allocation),
      oaId: allocation.oa_id,
      oaApplyType: allocation.oa_apply_type,
      expenseItemId: allocation.expense_item_id,
      oaCompletedAt: allocation.oa_completed_at,
      projectName: allocation.project_name,
      projectId: allocation.project_id,
      expenseType: allocation.expense_type,
      expenseContent: allocation.expense_content,
      amount: allocation.amount,
      counterpartyName: allocation.counterparty_name,
      paymentAccountLabel: allocation.payment_account_label,
      bankAccountLabel: allocation.bank_account_label,
      oaApplicant: allocation.oa_applicant,
      oaOriginalAmount: allocation.oa_original_amount,
      oaAllocationWeight: allocation.oa_allocation_weight,
      bankEventAmount: allocation.bank_event_amount,
    },
    paymentEvidence: payload.payment_evidence.map((item) => ({
      transactionId: item.transaction_id,
      tradeTime: item.trade_time,
      amount: item.amount,
      direction: item.direction,
      counterpartyName: item.counterparty_name,
      paymentAccountLabel: item.payment_account_label,
      remark: item.remark,
      bankTagCode: item.bank_tag_code,
      bankTagLabel: item.bank_tag_label,
    })),
    reconciliation: {
      relationCaseId: payload.reconciliation.relation_case_id,
      oaTotal: payload.reconciliation.oa_total,
      grossOutflowTotal: payload.reconciliation.gross_outflow_total,
      wrongPaymentRefundTotal: payload.reconciliation.wrong_payment_refund_total,
      netOutflowTotal: payload.reconciliation.net_outflow_total,
      difference: payload.reconciliation.difference,
      cashPaymentRatio: payload.reconciliation.cash_payment_ratio,
      status: payload.reconciliation.status,
    },
  };
}

export type ProjectCostExportParams = {
  month: string;
  view: "project";
  projectNames: string[];
  bankTagPrimaryKeys?: string[];
  aggregateBy: "month" | "year";
};

export type CostExportParams =
  | {
      month: string;
      view: "time" | "bank_tag";
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "bank_account";
      bankAccountLabels: string[];
      projectNames?: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | ProjectCostExportParams
  | {
      month: string;
      view: "cost_tag";
      bankTagPrimaryKeys: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  ;

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

function buildCostStatisticsQuery(
  params: CostExportParams | PreviewCostExportParams,
) {
  const query = new URLSearchParams({
    month: params.month,
    view: params.view,
  });

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
    for (const expenseType of params.bankTagPrimaryKeys ?? []) {
      query.append("bank_tag_primary_key", expenseType);
    }

  }

  if (params.view === "bank_account") {
    for (const bankAccountLabel of params.bankAccountLabels) {
      query.append("bank_account_label", bankAccountLabel);
    }
    for (const projectName of params.projectNames ?? []) {
      query.append("project_name", projectName);
    }
  }

  if (params.view === "cost_tag") {
    for (const expenseType of params.bankTagPrimaryKeys) {
      query.append("bank_tag_primary_key", expenseType);
    }
  }

  return query;
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
  const query = buildCostStatisticsQuery(params);
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
  const blob = await response.blob();
  const contentDisposition =
    typeof response.headers?.get === "function" ? response.headers.get("Content-Disposition") : null;
  const fileName =
    parseContentDispositionFileName(contentDisposition);
  if (!fileName) throw new Error("成本统计导出缺少文件名，请重试或联系管理员。");

  return {
    blob,
    fileName,
  };
}

export type PreviewCostExportParams =
  | {
      month: string;
      view: "time" | "bank_tag";
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "bank_account";
      bankAccountLabels: string[];
      projectNames?: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    }
  | {
      month: string;
      view: "project";
      projectNames: string[];
      aggregateBy: "month" | "year";
      bankTagPrimaryKeys?: string[];
    }
  | {
      month: string;
      view: "cost_tag";
      bankTagPrimaryKeys: string[];
      startMonth?: string;
      endMonth?: string;
      startDate?: string;
      endDate?: string;
    };

export async function fetchCostStatisticsExportPreview(
  params: PreviewCostExportParams,
  signal?: AbortSignal,
): Promise<CostStatisticsExportPreview> {
  const query = buildCostStatisticsQuery(params);
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
      expenseAmount: optionalString(payload.summary.expense_amount),
      incomeAmount: optionalString(payload.summary.income_amount),
      expenseTransactionCount: optionalCount(payload.summary.expense_transaction_count),
      incomeTransactionCount: optionalCount(payload.summary.income_transaction_count),
    },
    sheetNames: payload.sheet_names,
    columns: payload.columns,
    rows: payload.rows,
  };
}
import type { ProjectCostScope } from "./types";

export function fetchProjectCostScope(signal?: AbortSignal): Promise<ProjectCostScope> {
  return requestJson<ProjectCostScope>("/api/cost-statistics/project-cost-scope", { method: "GET", signal });
}

export function saveProjectCostScope(version: number, codes: string[]): Promise<ProjectCostScope> {
  return apiRequestJson<ProjectCostScope>("/api/cost-statistics/project-cost-scope", {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ expected_version: version, selected_tag_codes: codes }),
  }, { timeoutMs: 15000, timeoutMessage: "保存结果待核实", allowHtmlFallback: false });
}
