import type {
  BankDetailAccount,
  BankDetailAccountsResponse,
  BankDetailTransaction,
  BankDetailTransactionsResponse,
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
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const rawText = await response.text();
  const payload = rawText.trim() ? JSON.parse(rawText) as T : {} as T;
  if (!response.ok) {
    throw new Error(rawText.trim() || "request failed");
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
  };
}

export async function fetchBankDetailAccounts(signal?: AbortSignal): Promise<BankDetailAccountsResponse> {
  const payload = await requestJson<ApiBankDetailAccountsResponse>("/api/bank-details/accounts", {
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
  signal,
}: {
  accountKey?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  signal?: AbortSignal;
}): Promise<BankDetailTransactionsResponse> {
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
  };
}
