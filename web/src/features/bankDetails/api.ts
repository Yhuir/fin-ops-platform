import type {
  BankDetailAccount,
  BankDetailAccountsRequest,
  BankDetailAccountsResponse,
  BankDetailAutoCandidateCategory,
  BankDetailCategoryResolutionStatus,
  BankDetailReadModelStatus,
  BankDetailExportRequest,
  BankDetailExportResponse,
  BankDetailTransaction,
  BankDetailTransactionsRequest,
  BankDetailTransactionsResponse,
  BankAutoTagEditableRule,
  BankAutoTagAccountScope,
  BankAutoTagRuleConditions,
  BankAutoTagRulesResponse,
  BankAutoTagSystemRule,
  BankInternalTransferCounterpart,
  SaveBankAutoTagRulesRequest,
  BankDetailRelationStatus,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
  InvoiceRelationTag,
  OaRelationTag,
} from "./types";
import { ApiClientError, apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";
import { mapBankTransactionTagDictionary } from "../pendingInvoices/api";
import type { OperationBarrierTarget } from "../operationBarrier/api";

type ApiBankDetailAccount = {
  account_identity?: string | null;
  account_key: string;
  bank_name: string;
  account_last4: string;
  display_name: string;
  account_no?: string | null;
  account_name?: string | null;
  currency?: string | null;
  latest_balance: string | null;
  latest_balance_at: string | null;
  latest_balance_transaction_id?: string | null;
  has_balance: boolean;
  transaction_count: number;
  transaction_total_count?: number | null;
};

type ApiBankDetailAccountsResponse = {
  accounts: ApiBankDetailAccount[];
  total_balance: string | null;
  balance_account_count: number;
  missing_balance_account_count: number;
  total_balances_by_currency?: Record<string, string>;
  balance_read_model_status?: string | null;
  read_model_status?: string | null;
  cache_status?: string | null;
};

type ApiBankDetailTransaction = {
  id: string;
  trade_time: string;
  counterparty_name: string;
  direction: "income" | "expense";
  direction_label: "收" | "支";
  amount: string;
  balance: string | null;
  summary: string;
  purpose: string;
  purpose_text?: string | null;
  summary_text?: string | null;
  note_text?: string | null;
  bank_name: string;
  account_last4: string;
  category_code?: BankTransactionCategoryCode | null;
  category_label?: string | null;
  category_path?: string[];
  category_primary_label?: string | null;
  category_sub_label?: string | null;
  category_third_label?: string | null;
  category_label_path?: string[];
  turnover_role?: string | null;
  turnover_action_type?: string | null;
  turnover_family?: string | null;
  category_source?: string | null;
  category_version?: number | null;
  category_resolution_status?: string | null;
  category_rule_version?: string | null;
  manual_confirmed_category_code?: BankTransactionCategoryCode | null;
  auto_category_code?: BankTransactionCategoryCode | null;
  auto_category_label?: string | null;
  auto_category_path?: string[];
  auto_category_primary_label?: string | null;
  auto_category_sub_label?: string | null;
  auto_category_third_label?: string | null;
  auto_category_label_path?: string[];
  auto_category_source?: string | null;
  auto_category_reason?: string | null;
  auto_category_confidence?: string | null;
  auto_candidate_category_codes?: unknown[];
  auto_candidate_categories?: ApiBankDetailAutoCandidateCategory[];
  internal_transfer_counterpart?: ApiBankInternalTransferCounterpart | null;
  effective_category_code?: BankTransactionCategoryCode | null;
  effective_category_label?: string | null;
  effective_category_path?: string[];
  effective_category_primary_label?: string | null;
  effective_category_sub_label?: string | null;
  effective_category_third_label?: string | null;
  effective_category_label_path?: string[];
  effective_category_source?: string | null;
  oa_relation_tag?: string | null;
  invoice_relation_tag?: string | null;
  relation_tags?: string[];
  relation_case_id?: string | null;
  relation_status?: string | null;
  relationStatus?: string | null;
};

type ApiBankDetailAutoCandidateCategory = {
  category_code?: string | null;
  category_label?: string | null;
  category_primary_label?: string | null;
  category_sub_label?: string | null;
  category_third_label?: string | null;
  category_label_path?: unknown[];
  category_path?: unknown[];
  turnover_role?: string | null;
  turnover_action_type?: string | null;
  turnover_family?: string | null;
  rule_code?: string | null;
  reason?: string | null;
};

type ApiBankInternalTransferCounterpart = {
  transaction_id?: string | null;
  trade_time?: string | null;
  bank_name?: string | null;
  account_last4?: string | null;
  amount?: string | null;
  direction_label?: string | null;
  counterparty_name?: string | null;
};

type ApiBankDetailTransactionsResponse = {
  account_key?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  rows: ApiBankDetailTransaction[];
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  };
  category_counts?: Record<string, number>;
  tag_dictionary?: Parameters<typeof mapBankTransactionTagDictionary>[0];
  bank_transaction_tags?: Parameters<typeof mapBankTransactionTagDictionary>[0];
  read_model_status?: string | null;
  cache_status?: string | null;
};

type ApiBankAutoTagRuleConditions = {
  match_fields?: unknown[];
  exact?: unknown[];
  contains?: unknown[];
  excludes?: unknown[];
  exact_any?: unknown[];
  contains_any?: unknown[];
  contains_all?: unknown[];
  none_of?: unknown[];
  regex_any?: unknown[];
};

type ApiBankAutoTagAccountScope = {
  type?: string;
  values?: unknown[];
};

type ApiBankAutoTagEditableRule = {
  code?: string;
  label?: string;
  status?: "active" | "archived";
  source?: "system" | "custom";
  priority?: number;
  priority_label?: string;
  sort_order?: number;
  output_primary_label?: string;
  output_sub_label?: string;
  output_third_label?: string;
  turnover_role?: string;
  turnover_action_type?: string;
  turnover_family?: string;
  direction?: string;
  account_scope?: ApiBankAutoTagAccountScope;
  rules?: ApiBankAutoTagRuleConditions;
  rule_summary?: string;
  editable?: boolean;
  archivable?: boolean;
  sortable?: boolean;
};

type ApiBankAutoTagSystemRule = {
  code?: string;
  label?: string;
  priority_label?: string;
  source?: "system" | "custom";
  status?: "active" | "archived";
  editable?: boolean;
  archivable?: boolean;
  sortable?: boolean;
};

type ApiBankAutoTagRulesResponse = {
  version?: number;
  system_rule?: ApiBankAutoTagSystemRule;
  active_rules?: ApiBankAutoTagEditableRule[];
  archived_rules?: ApiBankAutoTagEditableRule[];
  field_options?: { value?: string; label?: string }[];
  turnover_third_label_options?: { value?: string; label?: string }[];
  turnover_action_type_options?: Array<{
    value?: string;
    label?: string;
    expected_direction?: string | null;
    business_type?: string | null;
    side?: string | null;
  }>;
  permissions?: { can_save?: boolean };
  read_model_status?: "fresh" | "refreshing" | string;
  read_model_scope_keys?: unknown;
  readModelScopeKeys?: unknown;
  freshness_targets?: unknown;
  freshnessTargets?: unknown;
  operation_barrier_targets?: unknown;
  operationBarrierTargets?: unknown;
};

const BANK_DETAIL_API_ERROR_MESSAGES: Record<string, string> = {
  invalid_category_code: "该银行明细标签不存在，请刷新后重新选择。",
  archived_category_code: "该银行明细标签已停用，不能再用于新的银行明细。",
  category_version_conflict: "银行明细标签已更新，请刷新后重新保存。",
  permission_denied: "当前账户没有保存自动标签规则权限。",
  bank_transaction_tags_version_conflict: "规则已被其他用户更新，请刷新后重新编辑。",
  invalid_bank_auto_tag_rules_request: "自动标签规则请求不合法，请刷新后重试。",
  invalid_auto_tag_rule: "自动标签规则校验失败，请检查规则内容。",
  bank_auto_tag_rules_reapply_unavailable: "自动标签规则已保存，但银行明细刷新队列暂时不可用，请稍后重试。",
  unknown_bank_transaction_tag: "该银行明细标签不存在，请刷新后重新选择。",
  bank_transaction_tag_in_use_by_pending_invoice_filter: "该银行明细标签仍被下游规则引用，请先解除引用后再停用。",
  bank_detail_export_account_required: "请选择具体银行账户后再导出当前账户。",
  bank_detail_export_account_not_found: "当前银行账户不存在或不在当前筛选范围内。",
  bank_detail_export_row_limit_exceeded: "当前筛选命中流水过多，请缩小日期范围、选择具体银行或增加搜索条件后再导出。",
  invalid_category_confirmation_candidate: "只能选择当前自动规则命中的候选标签。",
  invalid_manual_category_assignment_target: "当前流水已有自动标签或候选确认状态，不能走人工待分类入口。",
  invalid_manual_category_assignment_candidate: "只能选择当前自动标签规则中的可用标签。",
};

function normalizeBankDetailReadModelStatus(value: unknown): BankDetailReadModelStatus {
  if (value === "fresh" || value === "refreshing" || value === "stale" || value === "schema_mismatch" || value === "missing") {
    return value;
  }
  return "refreshing";
}

function fieldErrorMessagesFromPayload(payload: unknown) {
  if (!payload || typeof payload !== "object" || !Array.isArray((payload as { field_errors?: unknown }).field_errors)) {
    return [];
  }
  const seen = new Set<string>();
  return ((payload as { field_errors: unknown[] }).field_errors)
    .map((fieldError) => (
      fieldError && typeof fieldError === "object"
        ? String((fieldError as { message?: unknown }).message ?? "").trim()
        : ""
    ))
    .filter((message) => {
      if (!message || seen.has(message)) {
        return false;
      }
      seen.add(message);
      return true;
    });
}

function withFieldErrorMessages(message: string, fieldMessages: string[]) {
  if (!fieldMessages.length) {
    return message;
  }
  return `${message.replace(/[。；;:：]+$/, "")}：${fieldMessages.join("；")}`;
}

function resolveBankDetailApiErrorMessage(payload: unknown, rawText: string) {
  if (payload && typeof payload === "object") {
    const errorCode = String((payload as { error?: unknown }).error ?? "").trim();
    const fieldMessages = fieldErrorMessagesFromPayload(payload);
    if (errorCode && BANK_DETAIL_API_ERROR_MESSAGES[errorCode]) {
      const mapped = BANK_DETAIL_API_ERROR_MESSAGES[errorCode];
      return withFieldErrorMessages(mapped, fieldMessages);
    }
    const message = String((payload as { message?: unknown }).message ?? "").trim();
    if (message) {
      return withFieldErrorMessages(message, fieldMessages);
    }
    if (errorCode) {
      return errorCode;
    }
  }
  return rawText.trim() || "request failed";
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  try {
    return await apiRequestJson<T>(url, init);
  } catch (error) {
    if (error instanceof ApiClientError) {
      const mappedMessage = resolveBankDetailApiErrorMessage(error.payload, error.responseText);
      throw new Error(mappedMessage === error.responseText.trim() ? error.message : mappedMessage);
    }
    throw error;
  }
}

async function requestBlob(url: string, init: RequestInit = {}) {
  const response = await apiFetch(url, init);
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!response.ok) {
    const rawText = await response.text();
    let payload: unknown = null;
    try {
      payload = rawText.trim() ? JSON.parse(rawText) : null;
    } catch {
      payload = null;
    }
    throw new Error(resolveBankDetailApiErrorMessage(payload, rawText));
  }
  if (!contentType.toLowerCase().includes("spreadsheetml.sheet")) {
    const rawText = await response.text();
    if (looksLikeHtmlResponse(rawText, contentType)) {
      throw new Error(`接口返回了 HTML 页面：${url}。说明请求没有进入后端导出 API，请确认后端服务和代理路径已正常配置。`);
    }
    throw new Error(contentType ? `接口 ${url} 返回的不是 Excel 文件：${contentType}` : `接口 ${url} 返回的不是 Excel 文件。`);
  }
  return {
    blob: await response.blob(),
    fileName: filenameFromContentDisposition(response.headers.get("Content-Disposition")) ?? "银行明细导出.xlsx",
  };
}

function filenameFromContentDisposition(value: string | null) {
  if (!value) {
    return null;
  }
  const encodedMatch = /filename\*=UTF-8''([^;]+)/i.exec(value);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return encodedMatch[1];
    }
  }
  const plainMatch = /filename="([^"]+)"/i.exec(value);
  return plainMatch?.[1] ?? null;
}

function mapAccount(account: ApiBankDetailAccount): BankDetailAccount {
  return {
    accountIdentity: account.account_identity ?? null,
    accountKey: account.account_key,
    bankName: account.bank_name,
    accountLast4: account.account_last4,
    displayName: account.display_name,
    accountNo: account.account_no ?? null,
    accountName: account.account_name ?? null,
    currency: account.currency ?? null,
    latestBalance: account.latest_balance,
    latestBalanceAt: account.latest_balance_at,
    latestBalanceTransactionId: account.latest_balance_transaction_id ?? null,
    hasBalance: account.has_balance,
    transactionCount: account.transaction_count,
    transactionTotalCount: Number(account.transaction_total_count) || account.transaction_count,
  };
}

function normalizeOaRelationTag(value: unknown): OaRelationTag {
  return value === "有oa" ? value : "无oa";
}

function normalizeInvoiceRelationTag(value: unknown): InvoiceRelationTag {
  return value === "有发票" ? value : "无发票";
}

function normalizeRelationStatus(value: unknown): BankDetailRelationStatus {
  if (typeof value !== "string") {
    return "";
  }
  const normalized = value.trim();
  if (!normalized) {
    return "";
  }
  return normalized === "linked" ? "linked" : "unlinked";
}

function formatBankDetailTradeTime(value: string) {
  const normalized = String(value ?? "").trim().replace("T", " ");
  if (normalized.length >= 25 && ["+", "-"].includes(normalized[19]) && /^\d{2}:\d{2}$/.test(normalized.slice(20, 25))) {
    return normalized.slice(0, 19);
  }
  if (normalized.endsWith("Z") && normalized.length >= 20) {
    return normalized.slice(0, 19);
  }
  return normalized;
}

function normalizeDirectionLabel(value: unknown): BankInternalTransferCounterpart["directionLabel"] {
  if (value === "收" || value === "支") {
    return value;
  }
  return "";
}

function mapInternalTransferCounterpart(
  value: ApiBankInternalTransferCounterpart | null | undefined,
): BankInternalTransferCounterpart | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const transactionId = String(value.transaction_id ?? "").trim();
  if (!transactionId) {
    return null;
  }
  return {
    transactionId,
    tradeTime: formatBankDetailTradeTime(String(value.trade_time ?? "")),
    bankName: String(value.bank_name ?? "").trim(),
    accountLast4: String(value.account_last4 ?? "").trim(),
    amount: String(value.amount ?? "").trim(),
    directionLabel: normalizeDirectionLabel(value.direction_label),
    counterpartyName: String(value.counterparty_name ?? "").trim(),
  };
}

function normalizeCategoryResolutionStatus(value: unknown): BankDetailCategoryResolutionStatus {
  if (
    value === "auto_matched"
    || value === "needs_confirmation"
    || value === "internal_transfer"
    || value === "manual_confirmed"
  ) {
    return value;
  }
  return "unmatched";
}

function mapAutoCandidateCategory(value: ApiBankDetailAutoCandidateCategory): BankDetailAutoCandidateCategory | null {
  const categoryCode = String(value.category_code ?? "").trim();
  if (!categoryCode) {
    return null;
  }
  return {
    categoryCode,
    categoryLabel: value.category_label ?? null,
    categoryPrimaryLabel: value.category_primary_label ?? null,
    categorySubLabel: value.category_sub_label ?? null,
    categoryThirdLabel: value.category_third_label ?? null,
    categoryLabelPath: Array.isArray(value.category_label_path) ? value.category_label_path.map(String).filter(Boolean) : [],
    categoryPath: Array.isArray(value.category_path) ? value.category_path.map(String).filter(Boolean) : [],
    turnoverRole: value.turnover_role ?? null,
    turnoverActionType: value.turnover_action_type ?? null,
    turnoverFamily: value.turnover_family ?? null,
    ruleCode: value.rule_code ?? null,
    reason: value.reason ?? null,
  };
}

function mapTransaction(row: ApiBankDetailTransaction): BankDetailTransaction {
  const rawRelationTags = Array.isArray(row.relation_tags)
    ? row.relation_tags.map(String).map((tag) => tag.trim()).filter(Boolean)
    : [];
  const oaRelationTag = normalizeOaRelationTag(row.oa_relation_tag ?? rawRelationTags[0]);
  const invoiceRelationTag = normalizeInvoiceRelationTag(row.invoice_relation_tag ?? rawRelationTags[1]);
  const relationTags = [oaRelationTag, invoiceRelationTag];
  const relationStatus = normalizeRelationStatus(row.relation_status ?? row.relationStatus);
  return {
    id: row.id,
    tradeTime: formatBankDetailTradeTime(row.trade_time),
    counterpartyName: row.counterparty_name,
    direction: row.direction,
    directionLabel: row.direction_label,
    amount: row.amount,
    balance: row.balance,
    summary: row.summary,
    purpose: row.purpose,
    purposeText: row.purpose_text ?? "",
    summaryText: row.summary_text ?? "",
    noteText: row.note_text ?? "",
    bankName: row.bank_name,
    accountLast4: row.account_last4,
    categoryCode: row.category_code ?? null,
    categoryLabel: row.category_label ?? null,
    categoryPath: Array.isArray(row.category_path) ? row.category_path.map(String).filter(Boolean) : [],
    categoryPrimaryLabel: row.category_primary_label ?? null,
    categorySubLabel: row.category_sub_label ?? null,
    categoryThirdLabel: row.category_third_label ?? null,
    categoryLabelPath: Array.isArray(row.category_label_path) ? row.category_label_path.map(String).filter(Boolean) : [],
    categorySource: row.category_source ?? "",
    categoryVersion: row.category_version ?? null,
    categoryResolutionStatus: normalizeCategoryResolutionStatus(row.category_resolution_status),
    categoryRuleVersion: row.category_rule_version ?? null,
    manualConfirmedCategoryCode: row.manual_confirmed_category_code ?? null,
    autoCategoryCode: row.auto_category_code ?? null,
    autoCategoryLabel: row.auto_category_label ?? null,
    autoCategoryPath: Array.isArray(row.auto_category_path) ? row.auto_category_path.map(String).filter(Boolean) : [],
    autoCategoryPrimaryLabel: row.auto_category_primary_label ?? null,
    autoCategorySubLabel: row.auto_category_sub_label ?? null,
    autoCategoryThirdLabel: row.auto_category_third_label ?? null,
    autoCategoryLabelPath: Array.isArray(row.auto_category_label_path) ? row.auto_category_label_path.map(String).filter(Boolean) : [],
    autoCategorySource: row.auto_category_source ?? "",
    autoCategoryReason: row.auto_category_reason ?? null,
    autoCategoryConfidence: row.auto_category_confidence ?? null,
    autoCandidateCategoryCodes: Array.isArray(row.auto_candidate_category_codes)
      ? row.auto_candidate_category_codes.map(String).filter(Boolean)
      : [],
    autoCandidateCategories: Array.isArray(row.auto_candidate_categories)
      ? row.auto_candidate_categories.map(mapAutoCandidateCategory).filter((item): item is BankDetailAutoCandidateCategory => item !== null)
      : [],
    internalTransferCounterpart: mapInternalTransferCounterpart(row.internal_transfer_counterpart),
    effectiveCategoryCode: row.effective_category_code ?? null,
    effectiveCategoryLabel: row.effective_category_label ?? null,
    effectiveCategoryPath: Array.isArray(row.effective_category_path) ? row.effective_category_path.map(String).filter(Boolean) : [],
    effectiveCategoryPrimaryLabel: row.effective_category_primary_label ?? null,
    effectiveCategorySubLabel: row.effective_category_sub_label ?? null,
    effectiveCategoryThirdLabel: row.effective_category_third_label ?? null,
    effectiveCategoryLabelPath: Array.isArray(row.effective_category_label_path) ? row.effective_category_label_path.map(String).filter(Boolean) : [],
    effectiveCategorySource: row.effective_category_source ?? "",
    oaRelationTag,
    invoiceRelationTag,
    relationTags,
    relationCaseId: relationStatus === "linked" && typeof row.relation_case_id === "string" && row.relation_case_id.trim()
      ? row.relation_case_id.trim()
      : null,
    relationStatus,
  };
}

function mapCategoryCounts(
  counts: ApiBankDetailTransactionsResponse["category_counts"] = {},
): BankTransactionCategoryCounts {
  return {
    uncategorized: 0,
    ...Object.fromEntries(
      Object.entries(counts).map(([key, value]) => [key, Number(value) || 0]),
    ),
  };
}

function stringList(values: unknown[] | undefined) {
  return Array.isArray(values) ? values.map(String).map((value) => value.trim()).filter(Boolean) : [];
}

function unknownStringList(value: unknown) {
  return Array.isArray(value) ? value.map(String).map((item) => item.trim()).filter(Boolean) : [];
}

function readModelTargets(value: unknown): OperationBarrierTarget[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const targets: OperationBarrierTarget[] = [];
  const seen = new Set<string>();
  value.forEach((item) => {
    if (!item || typeof item !== "object") {
      return;
    }
    const raw = item as Record<string, unknown>;
    const readModelKey = String(raw.readModelKey ?? raw.read_model_key ?? "").trim();
    const scopeKey = String(raw.scopeKey ?? raw.scope_key ?? "").trim();
    const scopeType = String(raw.scopeType ?? raw.scope_type ?? "").trim();
    if (!readModelKey || !scopeKey) {
      return;
    }
    const key = `${readModelKey}\u0000${scopeKey}\u0000${scopeType}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    targets.push({
      readModelKey,
      scopeKey,
      ...(scopeType ? { scopeType } : {}),
    });
  });
  return targets;
}

function mapAutoTagRuleConditions(rules: ApiBankAutoTagRuleConditions | undefined): BankAutoTagRuleConditions {
  return {
    matchFields: stringList(rules?.match_fields),
    exactAny: stringList(rules?.exact_any ?? rules?.exact),
    containsAny: stringList(rules?.contains_any ?? rules?.contains),
    containsAll: stringList(rules?.contains_all),
    noneOf: stringList(rules?.none_of ?? rules?.excludes),
    regexAny: stringList(rules?.regex_any),
  };
}

function mapAutoTagDirection(value: unknown) {
  return value === "income" || value === "expense" ? value : "any";
}

function mapAutoTagAccountScope(scope: ApiBankAutoTagAccountScope | undefined): BankAutoTagAccountScope {
  const type = scope?.type === "bank_account" || scope?.type === "account_type" || scope?.type === "bank" ? scope.type : "any";
  return {
    type,
    values: type === "any" ? [] : stringList(scope?.values),
  };
}

function mapAutoTagEditableRule(rule: ApiBankAutoTagEditableRule): BankAutoTagEditableRule {
  return {
    code: typeof rule.code === "string" && rule.code.trim() ? rule.code.trim() : undefined,
    label: String(rule.label ?? "").trim(),
    status: rule.status === "archived" ? "archived" : "active",
    source: rule.source === "system" ? "system" : "custom",
    priority: typeof rule.priority === "number" ? rule.priority : undefined,
    priorityLabel: String(rule.priority_label ?? "").trim() || undefined,
    sortOrder: typeof rule.sort_order === "number" ? rule.sort_order : undefined,
    outputPrimaryLabel: String(rule.output_primary_label ?? rule.label ?? "").trim(),
    outputSubLabel: String(rule.output_sub_label ?? "").trim(),
    outputThirdLabel: "",
    turnoverRole: String(rule.turnover_role ?? "").trim(),
    turnoverActionType: String(rule.turnover_action_type ?? "").trim(),
    turnoverFamily: String(rule.turnover_family ?? "").trim(),
    direction: mapAutoTagDirection(rule.direction),
    accountScope: mapAutoTagAccountScope(rule.account_scope),
    rules: mapAutoTagRuleConditions(rule.rules),
    ruleSummary: String(rule.rule_summary ?? "").trim(),
    editable: rule.editable !== false,
    archivable: rule.archivable !== false,
    sortable: rule.sortable !== false,
  };
}

function mapAutoTagSystemRule(rule: ApiBankAutoTagSystemRule | undefined): BankAutoTagSystemRule {
  return {
    code: String(rule?.code ?? "internal_transfer"),
    label: String(rule?.label ?? "内部往来款"),
    priorityLabel: String(rule?.priority_label ?? "优先级 1"),
    source: rule?.source === "custom" ? "custom" : "system",
    status: rule?.status === "archived" ? "archived" : "active",
    editable: Boolean(rule?.editable),
    archivable: Boolean(rule?.archivable),
    sortable: Boolean(rule?.sortable),
  };
}

function mapAutoTagRulesResponse(payload: ApiBankAutoTagRulesResponse): BankAutoTagRulesResponse {
  const freshnessTargets = readModelTargets(payload.freshness_targets ?? payload.freshnessTargets);
  const operationBarrierTargets = readModelTargets(payload.operation_barrier_targets ?? payload.operationBarrierTargets);
  return {
    version: Number(payload.version) || 1,
    systemRule: mapAutoTagSystemRule(payload.system_rule),
    activeRules: Array.isArray(payload.active_rules) ? payload.active_rules.map(mapAutoTagEditableRule) : [],
    archivedRules: Array.isArray(payload.archived_rules) ? payload.archived_rules.map(mapAutoTagEditableRule) : [],
    fieldOptions: Array.isArray(payload.field_options)
      ? payload.field_options.map((option) => ({
        value: String(option.value ?? "").trim(),
        label: String(option.label ?? "").trim(),
      })).filter((option) => option.value && option.label)
      : [],
    turnoverThirdLabelOptions: Array.isArray(payload.turnover_third_label_options)
      ? payload.turnover_third_label_options.map((option) => ({
        value: String(option.value ?? "").trim(),
        label: String(option.label ?? "").trim(),
      })).filter((option) => option.value && option.label)
      : [],
    turnoverActionTypeOptions: Array.isArray(payload.turnover_action_type_options)
      ? payload.turnover_action_type_options.map((option) => ({
        value: String(option.value ?? "").trim(),
        label: String(option.label ?? "").trim(),
        expectedDirection: option.expected_direction ?? null,
        businessType: option.business_type ?? null,
        side: option.side ?? null,
      })).filter((option) => option.value && option.label)
      : [],
    permissions: { canSave: payload.permissions?.can_save !== false },
    readModelStatus: normalizeBankDetailReadModelStatus(payload.read_model_status),
    readModelScopeKeys: unknownStringList(payload.read_model_scope_keys ?? payload.readModelScopeKeys),
    freshnessTargets,
    operationBarrierTargets: operationBarrierTargets.length > 0 ? operationBarrierTargets : freshnessTargets,
  };
}

function serializeAutoTagRuleConditions(rules: BankAutoTagRuleConditions) {
  return {
    match_fields: rules.matchFields,
    exact_any: rules.exactAny,
    contains_any: rules.containsAny,
    contains_all: rules.containsAll,
    none_of: rules.noneOf,
    regex_any: rules.regexAny,
  };
}

function serializeSaveAutoTagRulesRequest(payload: SaveBankAutoTagRulesRequest) {
  return {
    expected_version: payload.expectedVersion,
    ...(payload.refreshScope ? {
      refresh_scope: {
        date_from: payload.refreshScope.dateFrom ?? null,
        date_to: payload.refreshScope.dateTo ?? null,
      },
    } : {}),
    active_rules: payload.activeRules.map((rule) => ({
      ...(rule.code ? { code: rule.code } : {}),
      label: rule.label,
      ...(typeof rule.priority === "number" ? { priority: rule.priority } : {}),
      ...(typeof rule.sortOrder === "number" ? { sort_order: rule.sortOrder } : {}),
      output_primary_label: rule.outputPrimaryLabel,
      output_sub_label: rule.outputSubLabel,
      ...(rule.turnoverActionType ? { turnover_action_type: rule.turnoverActionType } : {}),
      direction: rule.direction,
      account_scope: rule.accountScope,
      rules: serializeAutoTagRuleConditions(rule.rules),
    })),
    archived_rules: payload.archivedRules.map((rule) => ({
      ...(rule.code ? { code: rule.code } : {}),
      label: rule.label,
      ...(typeof rule.priority === "number" ? { priority: rule.priority } : {}),
      ...(typeof rule.sortOrder === "number" ? { sort_order: rule.sortOrder } : {}),
      output_primary_label: rule.outputPrimaryLabel,
      output_sub_label: rule.outputSubLabel,
      ...(rule.turnoverActionType ? { turnover_action_type: rule.turnoverActionType } : {}),
      direction: rule.direction,
      account_scope: rule.accountScope,
      rules: serializeAutoTagRuleConditions(rule.rules),
    })),
  };
}

export async function fetchBankDetailAccounts({
  dateFrom,
  dateTo,
  signal,
}: BankDetailAccountsRequest = {}): Promise<BankDetailAccountsResponse> {
  const params = new URLSearchParams();
  if (dateFrom) {
    params.set("date_from", dateFrom);
  }
  if (dateTo) {
    params.set("date_to", dateTo);
  }
  const query = params.toString();
  const payload = await requestJson<ApiBankDetailAccountsResponse>(`/api/bank-details/accounts${query ? `?${query}` : ""}`, {
    method: "GET",
    signal,
  });
  return {
    accounts: payload.accounts.map(mapAccount),
    totalBalance: payload.total_balance,
    balanceAccountCount: payload.balance_account_count,
    missingBalanceAccountCount: payload.missing_balance_account_count,
    totalBalancesByCurrency: payload.total_balances_by_currency ?? undefined,
    balanceReadModelStatus: normalizeBankDetailReadModelStatus(payload.balance_read_model_status),
    readModelStatus: normalizeBankDetailReadModelStatus(payload.read_model_status),
    cacheStatus: payload.cache_status ?? null,
  };
}

export async function fetchBankDetailTransactions({
  accountKey,
  dateFrom,
  dateTo,
  keyword,
  categoryCode,
  categoryPrimaryLabel,
  categorySubLabel,
  categoryThirdLabel,
  page,
  pageSize,
  signal,
}: BankDetailTransactionsRequest): Promise<BankDetailTransactionsResponse> {
  const params = new URLSearchParams();
  if (accountKey) {
    params.set("account_key", accountKey);
  }
  if (dateFrom) {
    params.set("date_from", dateFrom);
  }
  if (dateTo) {
    params.set("date_to", dateTo);
  }
  const normalizedKeyword = keyword?.trim();
  if (normalizedKeyword) {
    params.set("keyword", normalizedKeyword);
  }
  if (categoryCode) {
    params.set("category_code", categoryCode);
  }
  if (categoryPrimaryLabel) {
    params.set("category_primary_label", categoryPrimaryLabel);
  }
  if (categorySubLabel) {
    params.set("category_sub_label", categorySubLabel);
  }
  if (categoryThirdLabel) {
    params.set("category_third_label", categoryThirdLabel);
  }
  if (page) {
    params.set("page", String(page));
  }
  if (pageSize) {
    params.set("page_size", String(pageSize));
  }
  const query = params.toString();
  const payload = await requestJson<ApiBankDetailTransactionsResponse>(
    `/api/bank-details/transactions${query ? `?${query}` : ""}`,
    { method: "GET", signal },
  );
  return {
    accountKey: payload.account_key ?? accountKey ?? null,
    dateFrom: payload.date_from ?? dateFrom ?? null,
    dateTo: payload.date_to ?? dateTo ?? null,
    rows: payload.rows.map(mapTransaction),
    pagination: {
      page: payload.pagination?.page ?? 1,
      pageSize: payload.pagination?.page_size ?? 100,
      total: payload.pagination?.total ?? payload.rows.length,
    },
    categoryCounts: mapCategoryCounts(payload.category_counts),
    tagDictionary: mapBankTransactionTagDictionary(payload.tag_dictionary ?? payload.bank_transaction_tags),
    readModelStatus: normalizeBankDetailReadModelStatus(payload.read_model_status),
    cacheStatus: payload.cache_status ?? null,
  };
}

export async function fetchBankAutoTagRules({
  signal,
}: { signal?: AbortSignal } = {}): Promise<BankAutoTagRulesResponse> {
  const payload = await requestJson<ApiBankAutoTagRulesResponse>("/api/bank-details/auto-tag-rules", {
    method: "GET",
    signal,
  });
  return mapAutoTagRulesResponse(payload);
}

export async function saveBankAutoTagRules(
  payload: SaveBankAutoTagRulesRequest,
): Promise<BankAutoTagRulesResponse> {
  const response = await requestJson<ApiBankAutoTagRulesResponse>("/api/bank-details/auto-tag-rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(serializeSaveAutoTagRulesRequest(payload)),
  });
  return { ...mapAutoTagRulesResponse(response), refreshReason: "saved" };
}

export async function reapplyBankAutoTagRules(): Promise<BankAutoTagRulesResponse> {
  const response = await requestJson<ApiBankAutoTagRulesResponse>("/api/bank-details/auto-tag-rules/reapply", {
    method: "POST",
  });
  return { ...mapAutoTagRulesResponse(response), refreshReason: "reapplied" };
}

export async function confirmBankDetailCategory(
  transactionId: string,
  categoryCode: BankTransactionCategoryCode,
  categoryThirdLabel?: string | null,
): Promise<unknown> {
  return requestJson(`/api/bank-details/transactions/${encodeURIComponent(transactionId)}/category-confirmation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      category_code: categoryCode,
      ...(categoryThirdLabel ? { category_third_label: categoryThirdLabel } : {}),
    }),
  });
}

export async function revokeBankDetailCategoryConfirmation(transactionId: string): Promise<unknown> {
  return requestJson(`/api/bank-details/transactions/${encodeURIComponent(transactionId)}/category-confirmation`, {
    method: "DELETE",
  });
}

export async function assignBankDetailCategory(
  transactionId: string,
  categoryCode: BankTransactionCategoryCode,
  options: {
    categoryPrimaryLabel?: string | null;
    categorySubLabel?: string | null;
    categoryThirdLabel?: string | null;
    categoryLabelPath?: string[];
    turnoverActionType?: string | null;
    turnoverFamily?: string | null;
  } = {},
): Promise<unknown> {
  return requestJson(`/api/bank-details/transactions/${encodeURIComponent(transactionId)}/category-assignment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      category_code: categoryCode,
      ...(options.categoryPrimaryLabel ? { category_primary_label: options.categoryPrimaryLabel } : {}),
      ...(options.categorySubLabel ? { category_sub_label: options.categorySubLabel } : {}),
      ...(options.categoryThirdLabel ? { category_third_label: options.categoryThirdLabel } : {}),
      ...(options.categoryLabelPath?.length ? { category_label_path: options.categoryLabelPath } : {}),
      ...(options.turnoverActionType ? { turnover_action_type: options.turnoverActionType } : {}),
      ...(options.turnoverFamily ? { turnover_family: options.turnoverFamily } : {}),
    }),
  });
}

export async function clearBankDetailCategoryAssignment(transactionId: string): Promise<unknown> {
  return requestJson(`/api/bank-details/transactions/${encodeURIComponent(transactionId)}/category-assignment`, {
    method: "DELETE",
  });
}

export async function downloadBankDetailTransactionsExport({
  mode,
  accountKey,
  dateFrom,
  dateTo,
  keyword,
  categoryCode,
  categoryPrimaryLabel,
  categorySubLabel,
  categoryThirdLabel,
  signal,
}: BankDetailExportRequest): Promise<BankDetailExportResponse> {
  const params = new URLSearchParams();
  params.set("mode", mode);
  if (mode === "account" && accountKey) {
    params.set("account_key", accountKey);
  }
  if (dateFrom) {
    params.set("date_from", dateFrom);
  }
  if (dateTo) {
    params.set("date_to", dateTo);
  }
  const normalizedKeyword = keyword?.trim();
  if (normalizedKeyword) {
    params.set("keyword", normalizedKeyword);
  }
  if (categoryCode) {
    params.set("category_code", categoryCode);
  }
  if (categoryPrimaryLabel) {
    params.set("category_primary_label", categoryPrimaryLabel);
  }
  if (categorySubLabel) {
    params.set("category_sub_label", categorySubLabel);
  }
  if (categoryThirdLabel) {
    params.set("category_third_label", categoryThirdLabel);
  }
  return requestBlob(`/api/bank-details/transactions/export?${params.toString()}`, {
    method: "GET",
    signal,
  });
}
