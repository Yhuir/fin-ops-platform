export type NoOaBankBatchType =
  | "fee"
  | "salary"
  | "holiday_bonus"
  | "bonus"
  | "tax_payment"
  | "treasury_tax_collection"
  | "social_security"
  | "internal_transfer";

export type NoOaBankBatchTypeFilter = "all" | NoOaBankBatchType;

export type NoOaBankBatchStatus =
  | "draft"
  | "submitted"
  | "withdrawn";

export type NoOaBankBatchStatusFilter = "all" | NoOaBankBatchStatus;
export type NoOaBankBatchStatusBucket = "unsubmitted" | "submitted" | "withdrawn" | "all";
export type NoOaBankBatchReadModelStatus = "fresh" | "refreshing" | "stale" | "schema_mismatch" | "missing";

export type NoOaBankBatchCountMap = Record<string, number>;

export type NoOaBankBatchSummaryCategory = {
  code: NoOaBankBatchType | string;
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
  totalAmount: string;
};

export type NoOaBankBatch = {
  batchId: string;
  batchType: NoOaBankBatchType | string;
  batchLabel: string;
  scopeMonth: string;
  accountKey: string;
  bankName: string;
  accountLast4: string;
  status: NoOaBankBatchStatus | string;
  statusBucket: NoOaBankBatchStatusBucket | string;
  rowCount: number;
  totalAmount: string;
  submittedBy: string;
  submittedAt: string | null;
  withdrawnBy: string;
  withdrawnAt: string | null;
  conflictReason: string;
  blockedReason: string;
  tagCounts: NoOaBankBatchCountMap;
  directionCounts: NoOaBankBatchCountMap;
  canSubmit: boolean;
  canWithdraw: boolean;
  version: number | null;
  categoryPrimaryLabel?: string;
  categorySubLabel?: string;
  categoryLabelPath?: string[];
};

export type NoOaBankBatchSummary = {
  draftCount: number;
  submittedCount: number;
  withdrawnCount: number;
  conflictCount: number;
  staleCount: number;
  totalAmount: string;
  categories: NoOaBankBatchSummaryCategory[];
};

export type NoOaBankBatchesRequest = {
  month?: string | null;
  type?: NoOaBankBatchTypeFilter;
  status?: NoOaBankBatchStatusFilter;
  bucket?: NoOaBankBatchStatusBucket;
  accountKey?: string | null;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type NoOaBankBatchesPageInfo = {
  page: number;
  pageSize: number;
  total: number;
};

export type NoOaBankBatchesResponse = {
  summary: NoOaBankBatchSummary;
  batches: NoOaBankBatch[];
  pagination?: NoOaBankBatchesPageInfo;
  readModelStatus: NoOaBankBatchReadModelStatus;
  readModelStaleReasons: string[];
};

export type NoOaBankBatchDirection = "income" | "expense" | string;

export type NoOaBankBatchDetailRow = {
  transactionId: string;
  tradeTime: string;
  counterpartyName: string;
  direction: NoOaBankBatchDirection;
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

export type NoOaBankBatchDetail = {
  batch: NoOaBankBatch;
  rows: NoOaBankBatchDetailRow[];
  tagCounts: NoOaBankBatchCountMap;
  directionCounts: NoOaBankBatchCountMap;
};

export type SubmitNoOaBankBatchRequest = {
  batchId: string;
  expectedVersion: number | null;
  note?: string;
  signal?: AbortSignal;
};

export type WithdrawNoOaBankBatchRequest = {
  batchId: string;
  expectedVersion: number | null;
  reason: string;
  signal?: AbortSignal;
};

export type SubmitNoOaBankBatchesRequest = {
  batches: Array<{
    batchId: string;
    expectedVersion: number | null;
  }>;
  signal?: AbortSignal;
};

export type NoOaBankBatchMutationResult = {
  batch: NoOaBankBatch | null;
  affectedMonths: string[];
  workbenchRebuildQueued: boolean;
  results: Array<Record<string, unknown>>;
};

export type NoOaBankBatchTagDefinition = {
  code: string;
  label: string;
  path: string[];
  source: string;
  status: string;
  outputPrimaryLabel: string;
  outputSubLabel: string;
};

export type NoOaBankBatchTagSelection = {
  version: number;
  bankAutoTagRulesVersion: number;
  selectedTagCodes: string[];
  inactiveSelectedTagCodes: string[];
  activeTags: NoOaBankBatchTagDefinition[];
};

export type SaveNoOaBankBatchTagSelectionRequest = {
  expectedVersion: number;
  selectedTagCodes: string[];
  signal?: AbortSignal;
};

export type SubmitNoOaBankBatchSelectionRequest = {
  transactionIds: string[];
  note?: string;
  signal?: AbortSignal;
};
