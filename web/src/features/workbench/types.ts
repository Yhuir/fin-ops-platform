import type {
  BankTransactionTagDictionary,
  PendingInvoiceTagGroups,
} from "../pendingInvoices/types";

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

export type WorkbenchAmountCheck = {
  status: "matched" | "mismatch" | "unknown" | (string & {});
  direction: "expense" | "payment" | "receipt" | "unknown" | (string & {});
  bankAmount: string;
  oaAmount: string;
  amountDelta: string;
  requiresNote: boolean;
};

export type WorkbenchZoneId = "paired" | "open";

export type WorkbenchReconciliationWarning = {
  code: string;
  message: string;
  severity?: "info" | "warning" | "error" | (string & {});
};

export type WorkbenchReconciliationDecision = {
  decisionId: string;
  decisionKey: string;
  displayState: WorkbenchZoneId;
  decisionStatus: string;
  matchDomain: string;
  matchShape: string;
  ruleCode: string;
  ruleVersion: string;
  rowIds: string[];
  oaRowIds: string[];
  bankRowIds: string[];
  invoiceRowIds: string[];
  amount?: string;
  direction?: string;
  paymentAmountClosed?: boolean | null;
  invoiceAmountClosed?: boolean | null;
  warnings: WorkbenchReconciliationWarning[];
  evidence?: Record<string, unknown>;
  blockers?: unknown[];
  explanation?: string;
  sourceVersions?: Record<string, unknown>;
};

export type WorkbenchRecord = {
  id: string;
  caseId?: string;
  exceptionCaseId?: string;
  recordType: WorkbenchRecordType;
  sourceKind?: WorkbenchSourceKind;
  sourceOaId?: string;
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
  categoryPrimaryLabel?: string;
  categorySubLabel?: string;
  categoryLabelPath?: string[];
  categorySource?: string;
  bankTextFields?: WorkbenchBankTextField[];
  relationNote?: string;
  relationAmountCheck?: WorkbenchAmountCheck;
  specialMetadata?: Record<string, unknown>;
  reconciliationDecision?: WorkbenchReconciliationDecision;
  reconciliationWarnings?: WorkbenchReconciliationWarning[];
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
  bankTransactionTags: BankTransactionTagDictionary;
  pendingInvoiceTagGroups: PendingInvoiceTagGroups;
};

export type WorkbenchPaneRows = {
  oa: WorkbenchRecord[];
  bank: WorkbenchRecord[];
  invoice: WorkbenchRecord[];
};

export type WorkbenchPaneRowCounts = Partial<Record<WorkbenchRecordType, number>>;

export type WorkbenchMatchConfidence = "high" | "medium" | "low";

export type WorkbenchGroupType = WorkbenchZoneId;

export type WorkbenchRelationMode = "no_oa_bank_batch" | (string & {});

export type WorkbenchDisplayMode = "collapsed_summary" | "normal" | (string & {});

export type WorkbenchProcessedExceptionSummary = {
  scenario?: Record<string, unknown>;
  resolution?: Record<string, unknown>;
  detailNote?: string;
  displayTags?: string[];
};

export type WorkbenchCandidateGroup = {
  id: string;
  groupType: WorkbenchGroupType;
  rawGroupType?: string;
  matchConfidence: WorkbenchMatchConfidence;
  reason: string;
  relationMode?: WorkbenchRelationMode;
  displayMode?: WorkbenchDisplayMode;
  defaultCollapsed?: boolean;
  summaryRow?: WorkbenchRecord;
  rows: WorkbenchPaneRows;
  rowCounts?: WorkbenchPaneRowCounts;
  displayRowCounts?: WorkbenchPaneRowCounts;
  collapsedRows?: Partial<WorkbenchPaneRows>;
  collapsedRowCounts?: WorkbenchPaneRowCounts;
  canWithdraw?: boolean;
  relationNote?: string;
  amountCheck?: WorkbenchAmountCheck;
  specialMetadata?: Record<string, unknown>;
  processedExceptionSummary?: WorkbenchProcessedExceptionSummary;
  reconciliationDecision?: WorkbenchReconciliationDecision;
  warnings?: WorkbenchReconciliationWarning[];
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
  zoneCounts: Record<WorkbenchZoneId, WorkbenchZoneCounts>;
};

export type WorkbenchReadModelStatus = "fresh" | "refreshing" | "stale" | "failed" | "unavailable" | (string & {});

export type WorkbenchRefreshScopeStatus = {
  scopeKey: string;
  status: string;
  updatedAt: string | null;
  lastError: string | null;
  sourceVersion: number | null;
};

export type WorkbenchRefreshStatus = {
  scopeKey: string;
  readModelStatus: WorkbenchReadModelStatus;
  consistencyStatus: string | null;
  generatedAt: string | null;
  activeGenerationId: string | null;
  readModelVersion: string | number | null;
  dirtyScopes: WorkbenchRefreshScopeStatus[];
  runningScopes: string[];
  processedCount: number | null;
  totalCount: number | null;
  workerLagSeconds: number | null;
  lastError: string | null;
  retryable: boolean;
};

export type WorkbenchRefreshStatusEvent = {
  event: string;
  status: WorkbenchRefreshStatus;
};

export type WorkbenchZoneCounts = {
  groups: number;
  oa: number;
  bank: number;
  invoice: number;
  rows: number;
};

export type WorkbenchGroupsSort = `${WorkbenchRecordType}:asc` | `${WorkbenchRecordType}:desc`;

export type WorkbenchGroupsPageQuery = {
  search?: string;
  searchMode?: "linked_context";
  searchByPane?: Partial<Record<WorkbenchRecordType, string>>;
  status?: string;
  sourceKind?: string;
  sort?: WorkbenchGroupsSort;
  detailLevel?: "summary" | "full";
  filtersByPaneAndColumn?: Partial<Record<WorkbenchRecordType, Record<string, string[]>>>;
  timeFilterByPane?: Partial<Record<WorkbenchRecordType, { mode: "year"; year: string } | { mode: "month"; month: string }>>;
};

export type WorkbenchZonePageInfo = {
  zone: WorkbenchZoneId;
  page: number;
  pageSize: number;
  total: number;
  rowCounts: Pick<WorkbenchZoneCounts, "oa" | "bank" | "invoice" | "rows">;
  hasMore: boolean;
  readModelStatus: WorkbenchReadModelStatus;
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

export type WorkbenchInitialPageResult = {
  data: WorkbenchData;
  pages: Record<WorkbenchZoneId, WorkbenchZonePageInfo>;
};

export type WorkbenchGroupsPageResult = {
  zone: WorkbenchZoneId;
  groups: WorkbenchCandidateGroup[];
  page: WorkbenchZonePageInfo;
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
