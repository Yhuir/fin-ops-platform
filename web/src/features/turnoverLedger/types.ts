export type TurnoverLedgerFamily = "all" | "personal" | "company" | "bank" | "business";

export type TurnoverLedgerDirectionFilter = "all" | "borrow_in" | "borrow_out";

export type TurnoverRelationStatus =
  | "suggested"
  | "deterministic"
  | "confirmed"
  | "conflict"
  | "stale"
  | "withdrawn";

export type TurnoverRowTone = "success" | "warning" | "info" | "danger" | "error" | "muted";

export type TurnoverLedgerChip = {
  label: string;
  tone?: TurnoverRowTone | null;
};

export type TurnoverLedgerSummary = {
  pendingRepaymentAmount: string;
  repaidAmount: string;
  pendingCollectionAmount: string;
  collectedAmount: string;
  closedAmount: string;
  suggestedCount: number;
  conflictCount: number;
  rowCount: number;
};

export type TurnoverLedgerFamilySummary = {
  family: Exclude<TurnoverLedgerFamily, "all"> | string;
  label: string;
  pendingAmount: string;
  closedAmount: string;
  rowCount: number;
};

export type TurnoverLedgerRow = {
  relationId: string;
  status: TurnoverRelationStatus | string;
  statusLabel: string;
  rowTone: TurnoverRowTone;
  chips: TurnoverLedgerChip[];
  family: Exclude<TurnoverLedgerFamily, "all"> | string;
  familyLabel: string;
  counterpartyName: string;
  principalAmount: string;
  settledAmount: string;
  balanceAmount: string;
  firstTransactionAt: string | null;
  lastSettlementAt: string | null;
  bankAccountLabels: string[];
  summaryText: string;
  annualInterestRate: string | null;
  loanDays: number | null;
  accruedInterest: string | null;
  syncToWorkbench: boolean;
  bankRowIds: string[];
  categoryCodes: string[];
  businessType: string | null;
};

export type TurnoverLedgerDirection = "income" | "expense" | string;

export type TurnoverLedgerPendingDirection = "repayment" | "collection" | "closed" | "mixed" | string;

export type TurnoverLedgerInterestRateType = "annual" | "monthly" | "none" | string;

export type TurnoverLedgerGroupedRow = {
  rowKind: "summary" | "lot" | "flow" | "allocation_lot" | string;
  relationId: string;
  lotId: string;
  flowId: string;
  parentRelationId: string;
  sourceBankRowId: string;
  principalBankRowId: string;
  settlementBankRowIds: string[];
  status: TurnoverRelationStatus | string;
  statusLabel: string;
  rowTone: TurnoverRowTone;
  transactionAt: string | null;
  flowDirection: TurnoverLedgerDirection;
  flowAmount: string;
  borrowAmount: string;
  borrowDate: string | null;
  borrowDirection: TurnoverLedgerDirection;
  repaymentAmount: string;
  allocatedRepaymentAmount: string;
  repaymentDate: string | null;
  repaymentDirection: TurnoverLedgerDirection;
  balanceAmount: string;
  businessType: string | null;
  categoryCode: string;
  categoryLabel: string;
  categoryVersion: number;
  counterpartyBankName: string;
  summaryText: string;
  allocationStatus: "allocated" | "partial" | "unallocated" | "not_applicable" | string;
  allocatedLotIds: string[];
  repaymentRemark: string;
  interestRateType: TurnoverLedgerInterestRateType;
  interestRateValue: string;
  interestPaidAmount: string;
  loanDays: number | null;
  accruedInterest: string;
  interestPaidDate: string | null;
  interestPaymentMethod: string;
  note: string;
  bankRowIds: string[];
};

export type TurnoverLedgerFlowRow = TurnoverLedgerGroupedRow & {
  rowKind: "flow" | string;
};

export type TurnoverLedgerAllocationLot = TurnoverLedgerGroupedRow & {
  rowKind: "allocation_lot" | "lot" | string;
};

export type TurnoverLedgerGroup = {
  groupId: string;
  counterpartyName: string;
  family: Exclude<TurnoverLedgerFamily, "all"> | string;
  familyLabel: string;
  pendingDirection: TurnoverLedgerPendingDirection;
  pendingDirectionLabel: string;
  pendingAmount: string;
  pendingRepaymentAmount: string;
  pendingCollectionAmount: string;
  closedAmount: string;
  rowSpan: number;
  groupTone: TurnoverRowTone;
  rows: TurnoverLedgerGroupedRow[];
  summaryRow: TurnoverLedgerGroupedRow | null;
  flowRows: TurnoverLedgerFlowRow[];
  allocationLots: TurnoverLedgerAllocationLot[];
  lotRows: TurnoverLedgerGroupedRow[];
};

export type TurnoverLedgerPagination = {
  page: number;
  pageSize: number;
  total: number;
};

export type TurnoverLedgerResponse = {
  summary: TurnoverLedgerSummary;
  familySummaries: TurnoverLedgerFamilySummary[];
  rows: TurnoverLedgerRow[];
  pagination: TurnoverLedgerPagination;
};

export type TurnoverLedgerGroupedResponse = {
  summary: TurnoverLedgerSummary;
  familySummaries: TurnoverLedgerFamilySummary[];
  groups: TurnoverLedgerGroup[];
  pagination: TurnoverLedgerPagination;
};

export type FetchTurnoverLedgerRequest = {
  family?: TurnoverLedgerFamily;
  direction?: TurnoverLedgerDirectionFilter;
  status?: string | null;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type SaveTurnoverBankRowTagsRequest = {
  updates: Array<{
    transactionId: string;
    categoryCode: string;
    expectedVersion: number;
  }>;
  signal?: AbortSignal;
};

export type SaveTurnoverBankRowTagsResponse = {
  updatedCategories: Array<{
    transactionId: string;
    categoryCode: string | null;
    categoryLabel: string | null;
    categoryPath: string[];
    version: number;
  }>;
  affectedMonths: string[];
  turnoverLedgerInvalidated: boolean;
  workbenchInvalidated: boolean;
};

export type TurnoverLedgerExtra = {
  relationId: string;
  interestRateType: TurnoverLedgerInterestRateType;
  interestRateValue: string;
  interestPaidAmount: string;
  interestPaidDate: string | null;
  interestPaymentMethod: string;
  note: string;
  updatedAt: string | null;
  updatedBy: string;
};

export type SaveTurnoverLedgerExtraRequest = Partial<
  Pick<
    TurnoverLedgerExtra,
    | "interestRateType"
    | "interestRateValue"
    | "interestPaidAmount"
    | "interestPaidDate"
    | "interestPaymentMethod"
    | "note"
  >
> & {
  signal?: AbortSignal;
};

export type SaveTurnoverLedgerExtraResponse = {
  extra: TurnoverLedgerExtra;
  row: TurnoverLedgerGroupedRow | null;
};

export type TurnoverLedgerExportRow = {
  sequenceNo: number;
  rowType: "summary" | "lot" | string;
  lotId: string;
  familyLabel: string;
  counterpartyName: string;
  pendingRepaymentAmount: string;
  pendingCollectionAmount: string;
  balanceAmount: string;
  borrowAmount: string;
  borrowDate: string | null;
  repaymentAmount: string;
  repaymentDate: string | null;
  counterpartyBankName: string;
  repaymentRemark: string;
  interestRateType: TurnoverLedgerInterestRateType;
  interestRateValue: string;
  interestPaidAmount: string;
  loanDays: number | null;
  accruedInterest: string;
  interestPaidDate: string | null;
  interestPaymentMethod: string;
  note: string;
  statusLabel: string;
};

export type TurnoverLedgerExportPreview = {
  fileName: string;
  scopeLabel: string;
  summary: {
    rowCount: number;
    pendingRepaymentAmount: string;
    pendingCollectionAmount: string;
    accruedInterest: string;
  };
  columns: string[];
  rows: TurnoverLedgerExportRow[];
};

export type TurnoverLedgerExportDownload = {
  blob: Blob;
  fileName: string;
};

export type TurnoverBankRow = {
  id: string;
  tradeTime: string | null;
  counterpartyName: string;
  directionLabel: string;
  amount: string;
  bankAccountLabel: string;
  summary: string;
  purpose?: string | null;
  categoryLabel?: string | null;
};

export type TurnoverRelationDetail = {
  relation: TurnoverLedgerRow;
  bankRows: TurnoverBankRow[];
  auditHistory: Array<Record<string, unknown>>;
};

export type TurnoverRelationMutationResponse = {
  relationId: string;
  status: string;
};

export type ConfirmTurnoverRelationRequest = {
  bankRowIds: string[];
  note?: string;
  signal?: AbortSignal;
};

export type WithdrawTurnoverRelationRequest = {
  relationId: string;
  note?: string;
  signal?: AbortSignal;
};
