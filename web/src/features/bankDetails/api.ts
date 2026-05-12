import type {
  BankDetailAccount,
  BankDetailAccountsRequest,
  BankDetailAccountsResponse,
  BankDetailTransaction,
  BankDetailTransactionsRequest,
  BankDetailTransactionsResponse,
  BankTransactionCategoryCode,
  BankTransactionCategoryCounts,
  SaveBankTransactionCategoriesRequest,
  SaveBankTransactionCategoriesResponse,
} from "./types";

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
  bank_name: string;
  account_last4: string;
  category_code?: BankTransactionCategoryCode | null;
  category_label?: string | null;
  category_path?: string[];
  category_version?: number | null;
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
};

type ApiSavedBankTransactionCategory = {
  transaction_id: string;
  category_code: BankTransactionCategoryCode | null;
  category_label: string | null;
  category_path?: string[];
  version: number | null;
};

type ApiSaveBankTransactionCategoriesResponse = {
  updated_transaction_ids?: string[];
  updated_categories?: ApiSavedBankTransactionCategory[];
  affected_months?: string[];
  workbench_rebuild_queued?: boolean;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  const looksLikeHtml = /^<!doctype\s+html/i.test(trimmedText) || /^<html[\s>]/i.test(trimmedText);
  if (trimmedText && looksLikeHtml) {
    throw new Error(
      `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务已启动，并通过支持 /api 代理的前端开发服务访问。`,
    );
  }
  let payload = {} as T;
  if (trimmedText) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch {
      throw new Error(
        contentType
          ? `接口 ${url} 返回的不是合法 JSON：${contentType}`
          : `接口 ${url} 返回的不是合法 JSON。`,
      );
    }
  }
  if (!response.ok) {
    throw new Error(trimmedText || "request failed");
  }
  return payload;
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

function mapTransaction(row: ApiBankDetailTransaction): BankDetailTransaction {
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
    bankName: row.bank_name,
    accountLast4: row.account_last4,
    categoryCode: row.category_code ?? null,
    categoryLabel: row.category_label ?? null,
    categoryPath: Array.isArray(row.category_path) ? row.category_path.map(String).filter(Boolean) : [],
    categoryVersion: row.category_version ?? null,
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
  };
}

export async function fetchBankDetailTransactions({
  accountKey,
  dateFrom,
  dateTo,
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
  };
}

export async function saveBankTransactionCategories({
  updates,
  signal,
}: SaveBankTransactionCategoriesRequest): Promise<SaveBankTransactionCategoriesResponse> {
  const payload = await requestJson<ApiSaveBankTransactionCategoriesResponse>(
    "/api/bank-details/transactions/categories",
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        updates: updates.map((update) => ({
          transaction_id: update.transactionId,
          category_code: update.categoryCode,
          expected_version: update.expectedVersion,
        })),
      }),
      signal,
    },
  );
  return {
    updatedTransactionIds: payload.updated_transaction_ids ?? [],
    updatedCategories: (payload.updated_categories ?? []).map((category) => ({
      transactionId: category.transaction_id,
      categoryCode: category.category_code,
      categoryLabel: category.category_label,
      categoryPath: Array.isArray(category.category_path) ? category.category_path.map(String).filter(Boolean) : [],
      version: category.version,
    })),
    affectedMonths: payload.affected_months ?? [],
    workbenchRebuildQueued: payload.workbench_rebuild_queued ?? false,
  };
}
