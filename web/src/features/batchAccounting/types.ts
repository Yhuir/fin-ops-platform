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

export type BatchAccountingResponse = {
  summary: BatchAccountingSummary;
  bankRows: BatchAccountingBankRow[];
  oaRows: BatchAccountingOaRow[];
  relationsByBankRowId: Record<string, BatchAccountingOaRow[]>;
};

export type FetchBatchAccountingRequest = {
  bankYear: string;
  oaYear: string;
  bucket: BatchAccountingBucket;
  signal?: AbortSignal;
};

export type SubmitBatchAccountingRequest = {
  bankYear: string;
  oaYear: string;
  bankRowId: string;
  oaRowIds: string[];
  expectedVersion?: number | null;
  signal?: AbortSignal;
};

export type WithdrawBatchAccountingRequest = {
  relationId: string;
  expectedVersion?: number | null;
  reason: string;
  signal?: AbortSignal;
};

export type BatchAccountingMutationResult = {
  success: boolean;
  relationId: string;
  affectedRowIds: string[];
  affectedMonths: string[];
  message: string;
};
