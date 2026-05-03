export type BankDetailAccount = {
  accountKey: string;
  bankName: string;
  accountLast4: string;
  displayName: string;
  latestBalance: string | null;
  latestBalanceAt: string | null;
  hasBalance: boolean;
  transactionCount: number;
};

export type BankDetailAccountsResponse = {
  accounts: BankDetailAccount[];
  totalBalance: string | null;
  balanceAccountCount: number;
  missingBalanceAccountCount: number;
};

export type BankTransactionDirection = "income" | "expense";

export type BankDetailTransaction = {
  id: string;
  tradeTime: string;
  counterpartyName: string;
  direction: BankTransactionDirection;
  directionLabel: "收" | "支";
  amount: string;
  balance: string | null;
  summary: string;
  purpose: string;
  bankName: string;
  accountLast4: string;
};

export type BankDetailTransactionsResponse = {
  accountKey: string | null;
  dateFrom: string | null;
  dateTo: string | null;
  rows: BankDetailTransaction[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type BankDatePreset =
  | "current_month"
  | "previous_month"
  | "last_7_days"
  | "last_30_days"
  | "current_year"
  | "month"
  | "custom";

export type BankDateFilter = {
  preset: BankDatePreset;
  dateFrom: string;
  dateTo: string;
};
