export type CostSummary = {
  rowCount: number;
  transactionCount: number;
  totalAmount: string;
  expenseAmount?: string;
  incomeAmount?: string;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
};

export type CostStatisticsPageStatistics = {
  transactionCount?: number;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
  untaggedTransactionCount?: number;
  projectCount?: number;
  expenseTypeCount?: number;
  bankTagCount?: number;
  costTransactionCount?: number;
};

export type CostExplorerEntryRow = {
  entryId: string;
  rowKind: "bank_transaction" | "oa_allocation";
  transactionId?: string;
  allocationId?: string;
  occurredAt: string;
  direction: string;
  projectName: string;
  expenseType: string;
  expenseContent: string;
  amount: string;
  counterpartyName: string;
  oaApplicant: string;
  paymentAccountLabel: string;
  remark: string;
  bankTagCode: string;
  bankTagLabel: string;
  bankTagPrimaryLabel: string;
  bankTagSubLabel: string;
  bankTagLabelPath: string[];
};

export type CostBankExplorerRow = {
  paymentAccountLabel: string;
  totalAmount: string;
  transactionCount: number;
  projectCount: number;
  percentageLabel: string;
};

export type CostProjectExplorerRow = {
  projectName: string;
  totalAmount: string;
  transactionCount: number;
  expenseTypeCount: number;
  percentageLabel?: string;
};

export type CostExpenseTypeExplorerRow = {
  expenseType: string;
  totalAmount: string;
  transactionCount: number;
  projectCount: number;
  percentageLabel: string;
};

export type CostBankTagPrimaryExplorerRow = {
  primaryLabel: string;
  expenseAmount: string;
  incomeAmount: string;
  expenseTransactionCount: number;
  incomeTransactionCount: number;
  subTagCount: number;
};

export type CostBankTagSubExplorerRow = {
  primaryLabel: string;
  subLabel: string;
  expenseAmount: string;
  incomeAmount: string;
  expenseTransactionCount: number;
  incomeTransactionCount: number;
};

export type CostStatisticsView = "time" | "project" | "bank" | "expense_type" | "bank_tag";

export type CostStatisticsExplorerPage = {
  scope: string;
  view: CostStatisticsView;
  summary: CostSummary;
  statistics?: CostStatisticsPageStatistics;
  availableYears: string[];
  facets: {
    projects: CostProjectExplorerRow[];
    expenseTypes: CostExpenseTypeExplorerRow[];
    bankAccounts: CostBankExplorerRow[];
    bankTagPrimary: CostBankTagPrimaryExplorerRow[];
    bankTagSub: CostBankTagSubExplorerRow[];
  };
  rows: CostExplorerEntryRow[];
  allocationQuality?: {
    excludedAllocationCount: number;
    excludedByReason: Array<{ reason: string; count: number }>;
    pendingManualAllocationCount: number;
    staleManualAllocationCount: number;
  };
  rowCount: number;
  nextCursor?: string;
};

export type CostStatisticsManualAllocationUnit = {
  unitId: string;
  oaId: string;
  expenseItemId: string;
  projectId: string;
  projectName: string;
  expenseType: string;
  expenseContent: string;
  oaApplicant: string;
  oaOriginalAmount: string;
};

export type CostStatisticsManualAllocationSource = {
  sourceId: string;
  sourceKind: "outflow" | "paid_wrong_refund";
  amount: string;
  tradeTime: string;
  counterpartyName: string;
  paymentAccountLabel: string;
  remark: string;
};

export type CostStatisticsManualAllocationLine = {
  unitId: string;
  sourceId: string;
  sourceKind: "outflow" | "paid_wrong_refund";
  amount: string;
};

export type CostStatisticsManualAllocationTask = {
  relationCaseId: string;
  relationVersion: number;
  sourceFingerprint: string;
  status: "pending" | "stale" | "allocated";
  oaAllocationTotal: string;
  bankOutflowTotal: string;
  paidWrongRefundTotal: string;
  netCashCost: string;
  difference: string;
  units: CostStatisticsManualAllocationUnit[];
  sources: CostStatisticsManualAllocationSource[];
  allocations: CostStatisticsManualAllocationLine[];
  version: number;
  updatedBy: string;
  updatedAt: string;
  canSave: boolean;
};

export type CostStatisticsManualAllocationPage = {
  items: CostStatisticsManualAllocationTask[];
  rowCount: number;
  counts: { pending: number; allocated: number };
  nextCursor?: string;
};

export type CostStatisticsManualAllocationPageRequest = {
  status: "pending" | "allocated";
  query?: string;
  cursor?: string;
  pageSize?: number;
  signal?: AbortSignal;
};

export type SaveCostStatisticsManualAllocationRequest = {
  relationCaseId: string;
  expectedVersion: number;
  sourceFingerprint: string;
  allocations: CostStatisticsManualAllocationLine[];
};

export type CostStatisticsExplorerPageRequest = {
  scope: string;
  view: CostStatisticsView;
  projectName?: string;
  expenseType?: string;
  paymentAccountLabel?: string;
  bankTagPrimaryLabel?: string;
  bankTagSubLabel?: string;
  query?: string;
  cursor?: string;
  pageSize?: number;
  includeStatistics?: boolean;
  signal?: AbortSignal;
};

export type CostBankTransactionDetail = {
  month: string;
  kind: "bank_transaction";
  bankTransaction: {
    id: string;
    expenseContent: string;
    tradeTime: string;
    direction: string;
    amount: string;
    counterpartyName: string;
    paymentAccountLabel: string;
    remark: string;
    bankTagCode?: string;
    bankTagLabel?: string;
    bankTagPrimaryLabel?: string;
    bankTagSubLabel?: string;
    bankTagLabelPath?: string[];
    projectName?: string;
    expenseType?: string;
  };
};

export type CostAllocationDetail = {
  month: string;
  kind: "oa_allocation";
  allocation: {
    allocationId: string;
    oaId: string;
    oaApplyType: string;
    expenseItemId: string;
    oaCompletedAt: string;
    projectName: string;
    projectId: string;
    expenseType: string;
    expenseContent: string;
    amount: string;
    counterpartyName: string;
    paymentAccountLabel: string;
    oaApplicant: string;
    oaOriginalAmount: string;
    oaAllocationWeight: string;
    bankEventAmount: string;
  };
  paymentEvidence: Array<{
    transactionId: string;
    tradeTime: string;
    amount: string;
    direction: string;
    counterpartyName: string;
    paymentAccountLabel: string;
    remark: string;
    bankTagCode: string;
    bankTagLabel: string;
  }>;
  reconciliation: {
    relationCaseId: string;
    oaAllocationTotal: string;
    bankOutflowTotal: string;
    paidWrongRefundTotal: string;
    netCashCost: string;
    difference: string;
    cashPaymentRatio: string;
    status: "balanced" | "mismatch";
  };
};

export type CostEntryDetail = CostBankTransactionDetail | CostAllocationDetail;

export type CostStatisticsExportPreview = {
  view: "time" | "bank_tag" | "project" | "expense_type";
  fileName: string;
  scopeLabel: string;
  summary: {
    rowCount: number;
    transactionCount: number;
    totalAmount: string;
    expenseAmount?: string;
    incomeAmount?: string;
    expenseTransactionCount?: number;
    incomeTransactionCount?: number;
    sheetCount: number;
  };
  sheetNames: string[];
  columns: string[];
  rows: string[][];
};

export type CostStatisticsTagRuleTag = {
  code: string;
  label: string;
  path: string[];
  source: string;
  status: string;
  direction: string;
  outputPrimaryLabel: string;
  outputSubLabel: string;
};

export type CostStatisticsTimeTagRules = {
  version: number;
  bankAutoTagRulesVersion: number;
  mode: "all" | "custom";
  selectedTagCodes: string[];
  inactiveSelectedTagCodes: string[];
  availableTags: CostStatisticsTagRuleTag[];
  canSave: boolean;
};

export type SaveCostStatisticsTimeTagRulesRequest = {
  expectedVersion: number;
  mode: "all" | "custom";
  selectedTagCodes: string[];
};

export type CostStatisticsNoOaProject = {
  id: string;
  displayName: string;
  tagCodes: string[];
};

export type CostStatisticsNoOaRules = {
  version: number;
  bankAutoTagRulesVersion: number;
  projects: CostStatisticsNoOaProject[];
  availableTags: CostStatisticsTagRuleTag[];
  inactiveSelectedTagCodes: string[];
  canSave: boolean;
};

export type SaveCostStatisticsNoOaRulesRequest = {
  expectedVersion: number;
  projects: CostStatisticsNoOaProject[];
};
