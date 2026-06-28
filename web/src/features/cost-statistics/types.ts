export type CostProjectScope = "active" | "all";

export type CostSummary = {
  rowCount: number;
  transactionCount: number;
  totalAmount: string;
};

export type CostTimeRow = {
  transactionId: string;
  tradeTime: string;
  direction: string;
  projectName: string;
  expenseType: string;
  expenseContent: string;
  amount: string;
  counterpartyName: string;
  paymentAccountLabel: string;
  remark: string;
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
};

export type CostStatisticsExplorer = {
  month: string;
  summary: CostSummary;
  timeRows: CostTimeRow[];
  projectRows: CostProjectExplorerRow[];
  expenseTypeRows: CostExpenseTypeExplorerRow[];
};

export type CostMonthSummaryRow = {
  projectName: string;
  expenseType: string;
  expenseContent: string;
  amount: string;
  transactionCount: number;
  sampleTransactionIds: string[];
};

export type CostMonthStatistics = {
  month: string;
  summary: CostSummary;
  rows: CostMonthSummaryRow[];
};

export type CostProjectRow = {
  transactionId: string;
  tradeTime: string;
  direction?: string;
  projectName?: string;
  expenseType: string;
  expenseContent: string;
  amount: string;
  counterpartyName: string;
  paymentAccountLabel: string;
};

export type CostProjectStatistics = {
  month: string;
  projectName: string;
  summary: CostSummary;
  rows: CostProjectRow[];
};

export type CostTransactionDetail = {
  month: string;
  transaction: {
    id: string;
    projectName: string;
    expenseType: string;
    expenseContent: string;
    tradeTime: string;
    direction: string;
    amount: string;
    counterpartyName: string;
    paymentAccountLabel: string;
    oaApplicant: string;
    remark: string;
    summaryFields: Record<string, string>;
    detailFields: Record<string, string>;
  };
};

export type CostStatisticsExportPreview = {
  view: "time" | "project" | "expense_type";
  fileName: string;
  scopeLabel: string;
  summary: {
    rowCount: number;
    transactionCount: number;
    totalAmount: string;
    sheetCount: number;
  };
  sheetNames: string[];
  columns: string[];
  rows: string[][];
};
