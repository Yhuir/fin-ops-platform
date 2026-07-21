import type { OperationBarrierTarget } from "../operationBarrier/api";

export type TurnoverLedgerFamily = "all" | "personal" | "company" | "bank" | "business";

export type TurnoverLedgerDirectionFilter = "all" | "borrow_in" | "borrow_out";

export type TurnoverLedgerTagDefinition = {
  code: string;
  label: string;
  path: string[];
  source: string;
  status: string;
  outputPrimaryLabel: string;
  outputSubLabel: string;
  turnoverRole: string;
  turnoverActionType: string;
};

export type TurnoverLedgerTagSelection = {
  version: number;
  selectedTagCodes: string[];
  inactiveSelectedTagCodes: string[];
  activeTags: TurnoverLedgerTagDefinition[];
};

export type SaveTurnoverLedgerTagSelectionRequest = {
  expectedVersion: number;
  selectedTagCodes: string[];
  signal?: AbortSignal;
};

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

export type TurnoverLedgerStatistics = {
  transactionCount?: number;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
  closedGroupCount?: number;
  ledgerGroupCount?: number;
  unclosedGroupCount?: number;
  linkedOaTransactionCount?: number;
  linkedInvoiceTransactionCount?: number;
};

export type TurnoverLedgerFamilySummary = {
  family: Exclude<TurnoverLedgerFamily, "all"> | string;
  label: string;
  pendingRepaymentAmount: string;
  repaidAmount: string;
  pendingCollectionAmount: string;
  collectedAmount: string;
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
  categoryPrimaryLabel: string;
  categorySubLabel: string;
  categoryThirdLabel: string;
  categoryLabelPath: string[];
  categoryVersion: number | null;
  counterpartyBankName: string;
  bankAccountLabels: string[];
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
  workbenchRelationStatus: string;
  workbenchRelationCaseIds: string[];
  workbenchRelationMode: string;
  workbenchRelationSource: string;
  workbenchRelationRowIds: string[];
  linkedOa: boolean;
  linkedInvoice: boolean;
  cashClosureLinked: boolean;
  cashClosureCaseId: string;
  cashClosureSource: string;
  cashClosureRelationId: string;
  counterpartyName?: string;
  familyLabel?: string;
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
  repaidAmount: string;
  pendingCollectionAmount: string;
  collectedAmount: string;
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
  statistics?: TurnoverLedgerStatistics;
  readModelStatus?: string;
  readModelStaleReasons?: string[];
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
  affectedMonths: string[];
  affectedScopeKeys: string[];
  readModelScopeKeys: string[];
  workbenchPairRelationId: string;
  workbenchRelationMode: string;
  freshnessTargets: OperationBarrierTarget[];
  operationBarrierTargets: OperationBarrierTarget[];
};

export type ConfirmTurnoverRelationRequest = {
  bankRowIds: string[];
  note?: string;
  signal?: AbortSignal;
};

export type ConfirmTurnoverClosureRequest = ConfirmTurnoverRelationRequest & {
  expectedVersions?: Record<string, unknown>;
  idempotencyKey?: string;
};

export type WithdrawTurnoverRelationRequest = {
  relationId: string;
  note?: string;
  signal?: AbortSignal;
};

export type WithdrawTurnoverClosureRequest = {
  cashClosureCaseId: string;
  note?: string;
  signal?: AbortSignal;
};
