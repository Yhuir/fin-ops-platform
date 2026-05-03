export type WorkbenchRecordType = "oa" | "bank" | "invoice";

export type WorkbenchActionVariant = "detail-only" | "bank-review" | "confirm-exception";

export type WorkbenchDetailField = {
  label: string;
  value: string;
};

export type WorkbenchRecord = {
  id: string;
  caseId?: string;
  recordType: WorkbenchRecordType;
  sourceKind?: string;
  label: string;
  status: string;
  statusCode: string;
  statusTone: string;
  exceptionHandled: boolean;
  amount: string;
  counterparty: string;
  tableValues: Record<string, string>;
  detailFields: WorkbenchDetailField[];
  actionVariant: WorkbenchActionVariant;
  availableActions: string[];
  tags?: string[];
};

export type WorkbenchProjectSetting = {
  id: string;
  projectCode: string;
  projectName: string;
  projectStatus: "active" | "completed";
  source?: "oa" | "manual";
  departmentName?: string | null;
  ownerName?: string | null;
};

export type BankAccountMapping = {
  id: string;
  last4: string;
  bankName: string;
  shortName: string;
};

export type WorkbenchColumnLayouts = {
  oa: string[];
  bank: string[];
  invoice: string[];
};

export type WorkbenchOaImportOption = {
  value: string;
  label: string;
};

export type WorkbenchOaImportSettings = {
  formTypes: string[];
  statuses: string[];
  availableFormTypes: WorkbenchOaImportOption[];
  availableStatuses: WorkbenchOaImportOption[];
};

export type WorkbenchSettings = {
  projects: {
    active: WorkbenchProjectSetting[];
    completed: WorkbenchProjectSetting[];
    completedProjectIds: string[];
  };
  bankAccountMappings: BankAccountMapping[];
  accessControl: {
    allowedUsernames: string[];
    readonlyExportUsernames: string[];
    adminUsernames: string[];
    fullAccessUsernames: string[];
  };
  workbenchColumnLayouts: WorkbenchColumnLayouts;
  oaRetention: {
    cutoffDate: string;
  };
  oaImport: WorkbenchOaImportSettings;
  oaInvoiceOffset: {
    applicantNames: string[];
  };
};

export type WorkbenchPaneRows = {
  oa: WorkbenchRecord[];
  bank: WorkbenchRecord[];
  invoice: WorkbenchRecord[];
};

export type WorkbenchMatchConfidence = "high" | "medium" | "low";

export type WorkbenchGroupType = "auto_closed" | "manual_confirmed" | "candidate";

export type WorkbenchCandidateGroup = {
  id: string;
  groupType: WorkbenchGroupType;
  matchConfidence: WorkbenchMatchConfidence;
  reason: string;
  rows: WorkbenchPaneRows;
  canWithdraw?: boolean;
};

export type WorkbenchAmountSummaryTotals = {
  oaTotal: string;
  bankTotal: string;
  invoiceTotal: string;
};

export type WorkbenchAmountSummary = {
  before: WorkbenchAmountSummaryTotals;
  after: WorkbenchAmountSummaryTotals;
  status: "matched" | "mismatch" | "unknown";
  direction: "payment" | "receipt" | "unknown";
  mismatchFields: string[];
};

export type WorkbenchRelationPreviewOperation = "confirm_link" | "withdraw_link";

export type WorkbenchRelationPreview = {
  operation: WorkbenchRelationPreviewOperation;
  canSubmit: boolean;
  requiresNote: boolean;
  message: string;
  before: {
    groups: WorkbenchCandidateGroup[];
  };
  after: {
    groups: WorkbenchCandidateGroup[];
  };
  amountSummary: WorkbenchAmountSummary;
};

export type WorkbenchSummary = {
  oaCount: number;
  bankCount: number;
  invoiceCount: number;
  pairedCount: number;
  openCount: number;
  exceptionCount: number;
  totalCount: number;
};

export type WorkbenchOaStatus = {
  code: "idle" | "loading" | "ready" | "error";
  message: string;
};

export type WorkbenchOaSyncStatus = {
  status: string;
  message: string;
  dirtyScopes: string[];
  changedScopes: string[];
  lastSeenChangeAt: string | null;
  lastSyncedAt: string | null;
  lagSeconds: number | null;
  failedEventCount: number;
  version: number | null;
};

export type WorkbenchData = {
  month: string;
  oaStatus: WorkbenchOaStatus;
  summary: WorkbenchSummary;
  paired: {
    groups: WorkbenchCandidateGroup[];
  };
  open: {
    groups: WorkbenchCandidateGroup[];
  };
};

export type IgnoredWorkbenchData = {
  month: string;
  rows: WorkbenchRecord[];
};

export type WorkbenchAccessRole = "full_access" | "read_export_only";

export type WorkbenchSettingsDataResetAction =
  | "reset_bank_transactions"
  | "reset_invoices"
  | "reset_oa_and_rebuild";

export type WorkbenchSettingsDataResetResult = {
  action: WorkbenchSettingsDataResetAction;
  status: string;
  jobId?: string;
  clearedCollections: string[];
  deletedCounts: Record<string, number>;
  protectedTargets: string[];
  rebuildStatus: string;
  message: string;
};

export type WorkbenchSettingsDataResetJob = {
  jobId: string;
  action: WorkbenchSettingsDataResetAction;
  status: string;
  phase: string;
  message: string;
  current: number;
  total: number;
  percent: number;
  result: WorkbenchSettingsDataResetResult | null;
  error: string | null;
};
