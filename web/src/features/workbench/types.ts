export type WorkbenchRecordType = "oa" | "bank" | "invoice";

export type WorkbenchSourceKind =
  | "no_oa_bank_batch_summary"
  | "etc_invoice_summary"
  | "etc_invoice"
  | "oa_attachment_invoice"
  | "oa_attachment_payment_receipt"
  | "oa_attachment_unknown"
  | (string & {});

export type {
  WorkbenchExceptionAction,
  WorkbenchExceptionAmountSummary,
  WorkbenchExceptionApplyPayload,
  WorkbenchExceptionApplyResult,
  WorkbenchExceptionBusinessLine,
  WorkbenchExceptionCandidateEvidence,
  WorkbenchExceptionPreview,
  WorkbenchExceptionPreviewPayload,
  WorkbenchExceptionResultStatus,
  WorkbenchExceptionScenario,
  WorkbenchExceptionWarning,
} from "./exceptionTypes";

export type WorkbenchActionVariant = "detail-only" | "bank-review" | "confirm-exception";

export type WorkbenchDetailField = {
  label: string;
  value: string;
};

export type WorkbenchBankTextField = {
  label: string;
  value: string;
};

export type WorkbenchRecord = {
  id: string;
  caseId?: string;
  exceptionCaseId?: string;
  recordType: WorkbenchRecordType;
  sourceKind?: WorkbenchSourceKind;
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
  categoryCode?: string;
  categoryLabel?: string;
  categoryPath?: string[];
  categorySource?: string;
  bankTextFields?: WorkbenchBankTextField[];
  specialMetadata?: Record<string, unknown>;
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

export type WorkbenchRelationMode = "no_oa_bank_batch" | (string & {});

export type WorkbenchDisplayMode = "collapsed_summary" | "normal" | (string & {});

export type WorkbenchCandidateGroup = {
  id: string;
  groupType: WorkbenchGroupType;
  matchConfidence: WorkbenchMatchConfidence;
  reason: string;
  relationMode?: WorkbenchRelationMode;
  displayMode?: WorkbenchDisplayMode;
  defaultCollapsed?: boolean;
  summaryRow?: WorkbenchRecord;
  rows: WorkbenchPaneRows;
  collapsedRows?: Partial<WorkbenchPaneRows>;
  canWithdraw?: boolean;
  specialMetadata?: Record<string, unknown>;
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

export type WorkbenchInvoiceInventory = {
  systemTotal: number;
  manualImportTotal: number;
  workbenchVisibleTotal: number;
  hiddenSubmittedEtcTotal: number;
  extraEtcTotal: number;
  etcSummaryBatchCount: number;
  oaAttachmentTotal: number;
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
  invoiceInventory: WorkbenchInvoiceInventory;
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

export type OaManualSearchItem = {
  date: string;
  amount: string;
  content: string;
  projectName: string;
  reason: string;
  attachmentFileCount: number;
  importableInvoiceCount: number;
};

export type OaManualSearchRow = {
  rowId: string;
  oaNo: string;
  applicant: string;
  applicationDate: string;
  formType: string;
  formTypeLabel: string;
  status: string;
  statusLabel: string;
  projectName: string;
  reason: string;
  amount: string;
  attachmentFileCount: number;
  importableInvoiceCount: number;
  unrecognizedAttachmentCount: number;
  importStatus: string;
  importedAt: string | null;
  canImport: boolean;
  disabledReason: string;
  items: OaManualSearchItem[];
};

export type OaManualSearchResult = {
  rows: OaManualSearchRow[];
  total: number;
  page: number;
  pageSize: number;
};

export type OaManualImportEntry = {
  rowId: string;
  actorId?: string;
  importedAt?: string | null;
  source?: string;
  audit?: Record<string, unknown>;
};

export type OaManualImportResult = {
  imported: string[];
  alreadyImported: string[];
  failed: Array<Record<string, unknown>>;
  rows: OaManualSearchRow[];
};

export type OaManualImportList = {
  rowIds: string[];
  entries: OaManualImportEntry[];
};

export type OaManualAttachmentRefreshResult = {
  rows: Array<{
    rowId: string;
    attachmentFileCount: number;
    importableInvoiceCount: number;
    unrecognizedAttachmentCount: number;
  }>;
  errors: Array<Record<string, unknown>>;
};

export type OaManualSearchFilters = {
  query?: string;
  formTypes?: string[];
  statuses?: string[];
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  pageSize?: number;
};
