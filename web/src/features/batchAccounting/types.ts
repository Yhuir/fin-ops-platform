export type BatchAccountingBucket = "unsubmitted" | "submitted";

export type BatchAccountingSummary = {
  unsubmittedCount: number;
  submittedCount: number;
};

export type BatchAccountingBankRow = {
  id: string;
  tradeTime: string;
  counterpartyName: string;
  direction: string;
  directionLabel: string;
  amount: string;
  bankName: string;
  accountLast4: string;
  relationId: string;
  version: number | null;
};

export type BatchAccountingOaRow = {
  id: string;
  applicant: string;
  applyTime: string;
  projectName: string;
  amount: string;
  reason: string;
  linkedInvoiceRowIds: string[];
};

export type BatchAccountingAmountCheck = {
  status: "matched" | "mismatch" | string;
  direction: string;
  bankAmount: string;
  oaAmount: string;
  amountDelta: string;
  requiresNote: boolean;
};

export type BatchAccountingRelation = {
  relationId: string;
  note: string;
  amountCheck?: BatchAccountingAmountCheck;
};

export type BatchAccountingRelationBucket = {
  relationId: string;
  relation?: BatchAccountingRelation;
  oaRows: BatchAccountingOaRow[];
};

export type BatchAccountingPageInfo = {
  page: number;
  pageSize: number;
  total: number;
};

export type BatchAccountingPagination = {
  bankRows?: BatchAccountingPageInfo;
  oaRows?: BatchAccountingPageInfo;
};

export type BatchAccountingResponse = {
  summary: BatchAccountingSummary;
  bankRows: BatchAccountingBankRow[];
  oaRows: BatchAccountingOaRow[];
  relationsByBankRowId: Record<string, BatchAccountingRelationBucket>;
  pagination: BatchAccountingPagination;
  readModelStatus: string;
  readModelStaleReasons: string[];
  readModelScopeKeys: string[];
  refreshEnqueued: boolean;
};

export type FetchBatchAccountingRequest = {
  bankYear: string;
  bucket: BatchAccountingBucket;
  bankPage?: number;
  bankPageSize?: number;
  oaPage?: number;
  oaPageSize?: number;
  signal?: AbortSignal;
};

export type SubmitBatchAccountingRequest = {
  bankYear: string;
  bankRowId: string;
  oaRowIds: string[];
  expectedVersion?: number | null;
  note?: string;
  signal?: AbortSignal;
};

export type WithdrawBatchAccountingRequest = {
  relationId: string;
  expectedVersion?: number | null;
  reason: string;
  signal?: AbortSignal;
};

export type ReadModelOperationBarrierTarget = {
  readModelKey: string;
  scopeKey: string;
  scopeType?: string;
};

export type BatchAccountingMutationResult = {
  success: boolean;
  relationId: string;
  affectedRowIds: string[];
  affectedMonths: string[];
  affectedScopeKeys: string[];
  readModelScopeKeys: string[];
  freshnessTargets: ReadModelOperationBarrierTarget[];
  operationBarrierTargets: ReadModelOperationBarrierTarget[];
  message: string;
};
