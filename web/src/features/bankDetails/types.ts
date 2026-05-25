import type { BankTransactionTagDictionary } from "../pendingInvoices/types";

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
  readModelStatus?: "fresh" | "refreshing";
  cacheStatus?: string | null;
};

export type BankDetailAccountsRequest = {
  dateFrom?: string | null;
  dateTo?: string | null;
  signal?: AbortSignal;
};

export type BankTransactionDirection = "income" | "expense";

export type BankTransactionCategoryCode = string;

export type BankTransactionCategoryCounts = Record<string, number> & { uncategorized: number };

export type OaRelationTag = "有oa" | "无oa";

export type InvoiceRelationTag = "有发票" | "无发票";

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
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categoryPath: string[];
  categorySource: string;
  categoryVersion: number | null;
  autoCategoryCode: BankTransactionCategoryCode | null;
  autoCategoryLabel: string | null;
  autoCategoryPath: string[];
  autoCategorySource: string;
  autoCategoryReason: string | null;
  autoCategoryConfidence: string | null;
  effectiveCategoryCode: BankTransactionCategoryCode | null;
  effectiveCategoryLabel: string | null;
  effectiveCategoryPath: string[];
  effectiveCategorySource: string;
  oaRelationTag: OaRelationTag;
  invoiceRelationTag: InvoiceRelationTag;
  relationTags: string[];
  relationCaseId: string | null;
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
  categoryCounts: BankTransactionCategoryCounts;
  tagDictionary?: BankTransactionTagDictionary;
  readModelStatus?: "fresh" | "refreshing";
  cacheStatus?: string | null;
};

export type BankDetailTransactionsRequest = {
  accountKey?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  keyword?: string | null;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
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

export type SaveBankTransactionCategoryUpdate = {
  transactionId: string;
  categoryCode: BankTransactionCategoryCode | null;
  expectedVersion: number | null;
};

export type SaveBankTransactionCategoriesRequest = {
  updates: SaveBankTransactionCategoryUpdate[];
  signal?: AbortSignal;
};

export type SavedBankTransactionCategory = {
  transactionId: string;
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categoryPath: string[];
  version: number | null;
};

export type SaveBankTransactionCategoriesResponse = {
  updatedTransactionIds: string[];
  updatedCategories: SavedBankTransactionCategory[];
  affectedMonths: string[];
  workbenchRebuildQueued: boolean;
};
