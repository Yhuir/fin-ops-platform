export type BankFlowRuleBatchType =
  | "fee"
  | "salary"
  | "holiday_bonus"
  | "bonus"
  | "tax_payment"
  | "treasury_tax_collection"
  | "social_security"
  | "internal_transfer";

export type BankFlowRuleBatchTypeFilter = "all" | BankFlowRuleBatchType;

export type BankFlowRuleBatchStatus =
  | "draft"
  | "submitted"
  | "withdrawn";

export type BankFlowRuleBatchStatusFilter = "all" | BankFlowRuleBatchStatus;
export type BankFlowRuleBatchStatusBucket = "unsubmitted" | "submitted" | "withdrawn" | "all";

export type BankFlowRuleBatchCountMap = Record<string, number>;

export type BankFlowRuleBatchSummaryCategory = {
  code: BankFlowRuleBatchType | string;
  label: string;
  primaryLabel?: string;
  subLabel?: string;
  labelPath?: string[];
  total: number;
  draft: number;
  submitted: number;
  withdrawn: number;
  conflict: number;
  stale: number;
  totalRowCount: number;
  draftRowCount: number;
  submittedRowCount: number;
  withdrawnRowCount: number;
  totalAmount: string;
};

export type BankFlowRuleBatch = {
  batchId: string;
  batchType: BankFlowRuleBatchType | string;
  batchLabel: string;
  scopeMonth?: string;
  accountKey: string;
  bankName: string;
  accountLast4: string;
  status: BankFlowRuleBatchStatus | string;
  statusBucket: BankFlowRuleBatchStatusBucket | string;
  rowCount: number;
  totalAmount: string;
  submittedBy: string;
  submittedAt: string | null;
  withdrawnBy: string;
  withdrawnAt: string | null;
  conflictReason: string;
  blockedReason: string;
  tagCounts: BankFlowRuleBatchCountMap;
  directionCounts: BankFlowRuleBatchCountMap;
  canSubmit: boolean;
  canWithdraw: boolean;
  version: number | null;
  categoryPrimaryLabel?: string;
  categorySubLabel?: string;
  categoryLabelPath?: string[];
};

export type BankFlowRuleBatchSummary = {
  draftCount: number;
  submittedCount: number;
  withdrawnCount: number;
  conflictCount: number;
  staleCount: number;
  totalRowCount: number;
  draftRowCount: number;
  submittedRowCount: number;
  withdrawnRowCount: number;
  totalAmount: string;
  categories: BankFlowRuleBatchSummaryCategory[];
};

export type BankFlowRuleBatchesRequest = {
  month?: string | null;
  type?: BankFlowRuleBatchTypeFilter;
  status?: BankFlowRuleBatchStatusFilter;
  bucket?: BankFlowRuleBatchStatusBucket;
  accountKey?: string | null;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type BankFlowRuleBatchesPageInfo = {
  page: number;
  pageSize: number;
  total: number;
};

export type BankFlowRuleBatchesResponse = {
  summary: BankFlowRuleBatchSummary;
  batches: BankFlowRuleBatch[];
  pagination?: BankFlowRuleBatchesPageInfo;
};

export type BankFlowRuleBatchDirection = "income" | "expense" | string;

export type BankFlowRuleBatchDetailRow = {
  transactionId: string;
  tradeTime: string;
  counterpartyName: string;
  direction: BankFlowRuleBatchDirection;
  directionLabel: string;
  amount: string;
  bankName: string;
  accountLast4: string;
  accountKey: string;
  summary: string;
  purpose: string;
  remark: string;
  categoryCode: string;
  categoryLabel: string;
  categoryPrimaryLabel: string;
  categorySubLabel: string;
  categoryLabelPath: string[];
  categorySource: string;
  relationStatus: string;
  relationCaseIds: string[];
  linkedOaCount: number;
  linkedInvoiceCount: number;
};

export type BankFlowRuleBatchDetail = {
  batch: BankFlowRuleBatch;
  rows: BankFlowRuleBatchDetailRow[];
  tagCounts: BankFlowRuleBatchCountMap;
  directionCounts: BankFlowRuleBatchCountMap;
};

export type SubmitBankFlowRuleBatchRequest = {
  batchId: string;
  expectedVersion: number | null;
  scopeMonth: string;
  note?: string;
  signal?: AbortSignal;
};

export type WithdrawBankFlowRuleBatchRequest = {
  batchId: string;
  expectedVersion: number | null;
  reason: string;
  signal?: AbortSignal;
};

export type ResetSubmittedBankFlowRuleBatchesRequest = {
  reason?: string;
  signal?: AbortSignal;
};

export type SubmitBankFlowRuleBatchesRequest = {
  batches: Array<{
    batchId: string;
    expectedVersion: number | null;
  }>;
  signal?: AbortSignal;
};

export type BankFlowRuleBatchMutationResult = {
  batch: BankFlowRuleBatch | null;
  affectedMonths: string[];
  results: Array<Record<string, unknown>>;
};

export type BankFlowRuleBatchTagDefinition = {
  code: string;
  label: string;
  path: string[];
  source: string;
  status: string;
  direction: string;
  outputPrimaryLabel: string;
  outputSubLabel: string;
};

export type BankFlowRuleBatchTagRule = {
  tagCode: string;
  requiresOa: boolean;
  requiresInvoice: boolean;
};

export type BankFlowRuleBatchTagSelection = {
  version: number;
  bankAutoTagRulesVersion: number;
  activeTags: BankFlowRuleBatchTagDefinition[];
  rules: BankFlowRuleBatchTagRule[];
  requirementsByTagCode: Record<string, { requiresOa: boolean; requiresInvoice: boolean }>;
  eligibilityChanged: boolean;
  eligibilityChangedTagCodes: string[];
  affectedMonths: string[];
  affectedScopeKeys: string[];
};

export type SaveBankFlowRuleBatchTagSelectionRequest = {
  expectedVersion: number;
  rules: BankFlowRuleBatchTagRule[];
  signal?: AbortSignal;
};

export type SubmitBankFlowRuleBatchSelectionRequest = {
  transactionIds: string[];
  scopeMonth: string;
  note?: string;
  signal?: AbortSignal;
};
