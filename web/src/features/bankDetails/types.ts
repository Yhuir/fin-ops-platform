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

export type BankDetailReadModelStatus = "fresh" | "refreshing" | "stale" | "schema_mismatch" | "missing";

export type BankDetailAccountsResponse = {
  accounts: BankDetailAccount[];
  totalBalance: string | null;
  balanceAccountCount: number;
  missingBalanceAccountCount: number;
  readModelStatus?: BankDetailReadModelStatus;
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

export type BankInternalTransferCounterpart = {
  transactionId: string;
  tradeTime: string;
  bankName: string;
  accountLast4: string;
  amount: string;
  directionLabel: "收" | "支" | "";
  counterpartyName: string;
};

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
  purposeText: string;
  summaryText: string;
  noteText: string;
  bankName: string;
  accountLast4: string;
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categoryPath: string[];
  categoryPrimaryLabel: string | null;
  categorySubLabel: string | null;
  categoryLabelPath: string[];
  categorySource: string;
  categoryVersion: number | null;
  autoCategoryCode: BankTransactionCategoryCode | null;
  autoCategoryLabel: string | null;
  autoCategoryPath: string[];
  autoCategoryPrimaryLabel: string | null;
  autoCategorySubLabel: string | null;
  autoCategoryLabelPath: string[];
  autoCategorySource: string;
  autoCategoryReason: string | null;
  autoCategoryConfidence: string | null;
  internalTransferCounterpart: BankInternalTransferCounterpart | null;
  effectiveCategoryCode: BankTransactionCategoryCode | null;
  effectiveCategoryLabel: string | null;
  effectiveCategoryPath: string[];
  effectiveCategoryPrimaryLabel: string | null;
  effectiveCategorySubLabel: string | null;
  effectiveCategoryLabelPath: string[];
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
  readModelStatus?: BankDetailReadModelStatus;
  cacheStatus?: string | null;
};

export type BankDetailTransactionsRequest = {
  accountKey?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  keyword?: string | null;
  categoryCode?: string | null;
  categoryPrimaryLabel?: string | null;
  categorySubLabel?: string | null;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type BankDetailExportMode = "all" | "account";

export type BankDetailExportRequest = {
  mode: BankDetailExportMode;
  accountKey?: string | null;
  dateFrom?: string | null;
  dateTo?: string | null;
  keyword?: string | null;
  categoryCode?: string | null;
  categoryPrimaryLabel?: string | null;
  categorySubLabel?: string | null;
  signal?: AbortSignal;
};

export type BankDetailExportResponse = {
  blob: Blob;
  fileName: string;
};

export type BankAutoTagFieldOption = {
  value: string;
  label: string;
};

export type BankAutoTagRuleConditions = {
  matchFields: string[];
  exactAny: string[];
  containsAny: string[];
  containsAll: string[];
  noneOf: string[];
  regexAny: string[];
};

export type BankAutoTagDirection = "income" | "expense" | "any";

export type BankAutoTagAccountScope = {
  type: "any" | "bank_account" | "account_type" | "bank";
  values: string[];
};

export type BankAutoTagSystemRule = {
  code: string;
  label: string;
  priorityLabel: string;
  source: "system" | "custom";
  status: "active" | "archived";
  editable: boolean;
  archivable: boolean;
  sortable: boolean;
};

export type BankAutoTagEditableRule = {
  code?: string;
  label: string;
  status: "active" | "archived";
  source: "system" | "custom";
  priority?: number;
  priorityLabel?: string;
  direction: BankAutoTagDirection;
  accountScope: BankAutoTagAccountScope;
  outputPrimaryLabel: string;
  outputSubLabel: string;
  rules: BankAutoTagRuleConditions;
  ruleSummary: string;
  editable: boolean;
  archivable: boolean;
  sortable: boolean;
};

export type BankAutoTagRulesResponse = {
  version: number;
  systemRule: BankAutoTagSystemRule;
  activeRules: BankAutoTagEditableRule[];
  archivedRules: BankAutoTagEditableRule[];
  fieldOptions: BankAutoTagFieldOption[];
  permissions: {
    canSave: boolean;
  };
  readModelStatus?: "fresh" | "refreshing" | string;
};

export type SaveBankAutoTagRule = {
  code?: string;
  label: string;
  outputPrimaryLabel: string;
  outputSubLabel: string;
  direction: BankAutoTagDirection;
  accountScope: BankAutoTagAccountScope;
  rules: BankAutoTagRuleConditions;
};

export type BankAutoTagRefreshScope = {
  dateFrom?: string | null;
  dateTo?: string | null;
};

export type SaveBankAutoTagRulesRequest = {
  expectedVersion: number;
  activeRules: SaveBankAutoTagRule[];
  archivedRules: SaveBankAutoTagRule[];
  refreshScope?: BankAutoTagRefreshScope;
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
