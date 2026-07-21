import type { BankTransactionTagDictionary } from "../pendingInvoices/types";
import type { OperationBarrierTarget } from "../operationBarrier/api";

export type BankDetailAccount = {
  accountIdentity?: string | null;
  accountKey: string;
  bankName: string;
  accountLast4: string;
  displayName: string;
  accountNo?: string | null;
  accountName?: string | null;
  currency?: string | null;
  latestBalance: string | null;
  latestBalanceAt: string | null;
  latestBalanceTransactionId?: string | null;
  hasBalance: boolean;
  transactionCount: number;
  transactionTotalCount?: number;
};

export type BankDetailReadModelStatus = "fresh" | "refreshing" | "stale" | "schema_mismatch" | "missing";

export type BankDetailAccountsResponse = {
  accounts: BankDetailAccount[];
  totalBalance: string | null;
  balanceAccountCount: number;
  missingBalanceAccountCount: number;
  totalBalancesByCurrency?: Record<string, string>;
  balanceReadModelStatus?: BankDetailReadModelStatus;
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

export type BankDetailRelationStatus = "linked" | "unlinked" | "";

export type BankInternalTransferCounterpart = {
  transactionId: string;
  tradeTime: string;
  bankName: string;
  accountLast4: string;
  amount: string;
  directionLabel: "收" | "支" | "";
  counterpartyName: string;
};

export type BankDetailCategoryResolutionStatus =
  | "unmatched"
  | "auto_matched"
  | "needs_confirmation"
  | "internal_transfer"
  | "manual_confirmed";

export type BankDetailAutoCandidateCategory = {
  categoryCode: BankTransactionCategoryCode;
  categoryLabel: string | null;
  categoryPrimaryLabel: string | null;
  categorySubLabel: string | null;
  categoryThirdLabel: string | null;
  categoryLabelPath: string[];
  categoryPath: string[];
  turnoverRole: string | null;
  turnoverActionType: string | null;
  turnoverFamily: string | null;
  ruleCode: string | null;
  reason: string | null;
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
  categoryThirdLabel: string | null;
  categoryLabelPath: string[];
  categorySource: string;
  categoryVersion: number | null;
  categoryResolutionStatus: BankDetailCategoryResolutionStatus;
  categoryRuleVersion: string | null;
  manualConfirmedCategoryCode: BankTransactionCategoryCode | null;
  autoCategoryCode: BankTransactionCategoryCode | null;
  autoCategoryLabel: string | null;
  autoCategoryPath: string[];
  autoCategoryPrimaryLabel: string | null;
  autoCategorySubLabel: string | null;
  autoCategoryThirdLabel: string | null;
  autoCategoryLabelPath: string[];
  autoCategorySource: string;
  autoCategoryReason: string | null;
  autoCategoryConfidence: string | null;
  autoCandidateCategoryCodes: BankTransactionCategoryCode[];
  autoCandidateCategories: BankDetailAutoCandidateCategory[];
  internalTransferCounterpart: BankInternalTransferCounterpart | null;
  effectiveCategoryCode: BankTransactionCategoryCode | null;
  effectiveCategoryLabel: string | null;
  effectiveCategoryPath: string[];
  effectiveCategoryPrimaryLabel: string | null;
  effectiveCategorySubLabel: string | null;
  effectiveCategoryThirdLabel: string | null;
  effectiveCategoryLabelPath: string[];
  effectiveCategorySource: string;
  oaRelationTag: OaRelationTag;
  invoiceRelationTag: InvoiceRelationTag;
  relationTags: string[];
  relationCaseId: string | null;
  relationStatus: BankDetailRelationStatus;
};

export type BankDetailStatistics = {
  transactionCount?: number;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
  classifiedTransactionCount?: number;
  unclassifiedTransactionCount?: number;
  linkedTransactionCount?: number;
  unlinkedTransactionCount?: number;
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
  statistics?: BankDetailStatistics;
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
  categoryThirdLabel?: string | null;
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
  categoryThirdLabel?: string | null;
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

export type BankTurnoverActionTypeOption = {
  value: string;
  label: string;
  expectedDirection?: string | null;
  businessType?: string | null;
  side?: string | null;
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
  sortOrder?: number;
  direction: BankAutoTagDirection;
  accountScope: BankAutoTagAccountScope;
  outputPrimaryLabel: string;
  outputSubLabel: string;
  outputThirdLabel?: string;
  turnoverRole?: string;
  turnoverActionType?: string;
  turnoverFamily?: string;
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
  turnoverThirdLabelOptions: BankAutoTagFieldOption[];
  turnoverActionTypeOptions: BankTurnoverActionTypeOption[];
  permissions: {
    canSave: boolean;
  };
  readModelStatus?: "fresh" | "refreshing" | string;
  readModelScopeKeys: string[];
  freshnessTargets: OperationBarrierTarget[];
  operationBarrierTargets: OperationBarrierTarget[];
  refreshReason?: "saved" | "reapplied";
};

export type SaveBankAutoTagRule = {
  code?: string;
  label: string;
  priority?: number;
  sortOrder?: number;
  outputPrimaryLabel: string;
  outputSubLabel: string;
  outputThirdLabel?: string;
  turnoverActionType?: string;
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
  | "all"
  | "year"
  | "month";

export type BankDateFilter =
  | {
    preset: "all";
    dateFrom: null;
    dateTo: null;
  }
  | {
    preset: "year";
    year: string;
    dateFrom: string;
    dateTo: string;
  }
  | {
    preset: "month";
    month: string;
    dateFrom: string;
    dateTo: string;
  };
