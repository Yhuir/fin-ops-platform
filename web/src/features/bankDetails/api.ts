import type {
  BankDetailAccount,
  BankDetailAccountsRequest,
  BankDetailAccountsResponse,
  BankDetailTransaction,
  BankDetailTransactionsRequest,
  BankDetailTransactionsResponse,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
  InvoiceRelationTag,
  OaRelationTag,
} from "./types";
import { ApiClientError, apiRequestJson } from "../apiClient";
import { mapBankTransactionTagDictionary } from "../pendingInvoices/api";

type ApiBankDetailAccount = {
  account_key: string;
  bank_name: string;
  account_last4: string;
  display_name: string;
  latest_balance: string | null;
  latest_balance_at: string | null;
  has_balance: boolean;
  transaction_count: number;
};

type ApiBankDetailAccountsResponse = {
  accounts: ApiBankDetailAccount[];
  total_balance: string | null;
  balance_account_count: number;
  missing_balance_account_count: number;
  read_model_status?: "fresh" | "refreshing";
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
  category_source?: string | null;
  category_version?: number | null;
  auto_category_code?: BankTransactionCategoryCode | null;
  auto_category_label?: string | null;
  auto_category_path?: string[];
  auto_category_source?: string | null;
  auto_category_reason?: string | null;
  auto_category_confidence?: string | null;
  effective_category_code?: BankTransactionCategoryCode | null;
  effective_category_label?: string | null;
  effective_category_path?: string[];
  effective_category_source?: string | null;
  oa_relation_tag?: string | null;
  invoice_relation_tag?: string | null;
  relation_tags?: string[];
  relation_case_id?: string | null;
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
  read_model_status?: "fresh" | "refreshing";
  cache_status?: string | null;
};

const BANK_DETAIL_API_ERROR_MESSAGES: Record<string, string> = {
  invalid_category_code: "该银行明细标签不存在，请刷新后重新选择。",
  archived_category_code: "该银行明细标签已停用，不能再用于新的银行明细。",
  category_version_conflict: "银行明细标签已更新，请刷新后重新保存。",
};

function resolveBankDetailApiErrorMessage(payload: unknown, rawText: string) {
  if (payload && typeof payload === "object") {
    const errorCode = String((payload as { error?: unknown }).error ?? "").trim();
    if (errorCode && BANK_DETAIL_API_ERROR_MESSAGES[errorCode]) {
      return BANK_DETAIL_API_ERROR_MESSAGES[errorCode];
    }
    const message = String((payload as { message?: unknown }).message ?? "").trim();
    if (message) {
      return message;
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

function mapAccount(account: ApiBankDetailAccount): BankDetailAccount {
  return {
    accountKey: account.account_key,
    bankName: account.bank_name,
    accountLast4: account.account_last4,
    displayName: account.display_name,
    latestBalance: account.latest_balance,
    latestBalanceAt: account.latest_balance_at,
    hasBalance: account.has_balance,
    transactionCount: account.transaction_count,
  };
}

function normalizeOaRelationTag(value: unknown): OaRelationTag {
  return value === "有oa" ? "有oa" : "无oa";
}

function normalizeInvoiceRelationTag(value: unknown): InvoiceRelationTag {
  return value === "有发票" ? "有发票" : "无发票";
}

function mapTransaction(row: ApiBankDetailTransaction): BankDetailTransaction {
  const relationTags = Array.isArray(row.relation_tags)
    ? row.relation_tags.map(String).map((tag) => tag.trim()).filter(Boolean)
    : [];
  const oaRelationTag = normalizeOaRelationTag(row.oa_relation_tag ?? relationTags[0]);
  const invoiceRelationTag = normalizeInvoiceRelationTag(row.invoice_relation_tag ?? relationTags[1]);
  return {
    id: row.id,
    tradeTime: row.trade_time,
    counterpartyName: row.counterparty_name,
    direction: row.direction,
    directionLabel: row.direction_label,
    amount: row.amount,
    balance: row.balance,
    summary: row.summary,
    purpose: row.purpose,
    purposeText: row.purpose_text ?? row.purpose ?? "",
    summaryText: row.summary_text ?? row.summary ?? "",
    noteText: row.note_text ?? "",
    bankName: row.bank_name,
    accountLast4: row.account_last4,
    categoryCode: row.category_code ?? null,
    categoryLabel: row.category_label ?? null,
    categoryPath: Array.isArray(row.category_path) ? row.category_path.map(String).filter(Boolean) : [],
    categorySource: row.category_source ?? "",
    categoryVersion: row.category_version ?? null,
    autoCategoryCode: row.auto_category_code ?? null,
    autoCategoryLabel: row.auto_category_label ?? null,
    autoCategoryPath: Array.isArray(row.auto_category_path) ? row.auto_category_path.map(String).filter(Boolean) : [],
    autoCategorySource: row.auto_category_source ?? "",
    autoCategoryReason: row.auto_category_reason ?? null,
    autoCategoryConfidence: row.auto_category_confidence ?? null,
    effectiveCategoryCode: row.effective_category_code ?? null,
    effectiveCategoryLabel: row.effective_category_label ?? null,
    effectiveCategoryPath: Array.isArray(row.effective_category_path) ? row.effective_category_path.map(String).filter(Boolean) : [],
    effectiveCategorySource: row.effective_category_source ?? "",
    oaRelationTag,
    invoiceRelationTag,
    relationTags: [oaRelationTag, invoiceRelationTag],
    relationCaseId: typeof row.relation_case_id === "string" && row.relation_case_id.trim()
      ? row.relation_case_id.trim()
      : null,
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
    readModelStatus: payload.read_model_status,
    cacheStatus: payload.cache_status ?? null,
  };
}

export async function fetchBankDetailTransactions({
  accountKey,
  dateFrom,
  dateTo,
  keyword,
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
    readModelStatus: payload.read_model_status,
    cacheStatus: payload.cache_status ?? null,
  };
}
