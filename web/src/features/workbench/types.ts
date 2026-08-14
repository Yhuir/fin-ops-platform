import type {
  BankTransactionTagDictionary,
  PendingInvoiceTagGroups,
} from "../pendingInvoices/types";

export type WorkbenchRecordType = "oa" | "bank" | "invoice";

export type WorkbenchSourceKind =
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

export type WorkbenchExpenseItem = {
  id: string;
  rowIndex: string;
  projectName: string;
  amount: string;
  feeContent?: string;
  feeDescription?: string;
  attachmentFileCount?: number;
  attachmentParseFailedCount?: number;
  oaInvoiceAnomaly?: WorkbenchAnomalyItem;
};

export type WorkbenchAmountCheck = {
  status: "matched" | "mismatch" | "unknown" | (string & {});
  direction: "expense" | "payment" | "receipt" | "unknown" | (string & {});
  bankAmount: string;
  oaAmount: string;
  oaTotal?: string;
  bankTotal?: string;
  invoiceTotal?: string;
  amountDelta: string;
  requiresNote: boolean;
};

export type WorkbenchAnomalyItem = {
  code:
    | "oa_bank_amount_mismatch"
    | "oa_invoice_amount_mismatch"
    | "bank_invoice_amount_mismatch"
    | "oa_invoice_attachment_missing"
    | "oa_invoice_attachment_parse_failed"
    | "oa_invoice_attachment_unassigned"
    | (string & {});
  label: string;
  displayLabel: string;
  fingerprint: string;
  comparisonUnitId: string;
  sourceOaIds: string[];
  sourceExpenseItemIds: string[];
  oaTotal?: string;
  bankTotal?: string;
  invoiceTotal?: string;
  amountDelta?: string;
  mismatchPair?: ["oa" | "bank" | "invoice", "oa" | "bank" | "invoice"];
  invoiceRowIds: string[];
  attachmentFileCount: number;
};

export type WorkbenchAnomaly = {
  code: "workbench_anomaly" | (string & {});
  fingerprint: string;
  reviewDecision: "pending" | "accept_paired" | "keep_unpaired";
  reviewedItemFingerprints: string[];
  reviewNote: string;
  reviewedBy: string;
  reviewedAt?: string;
  items: WorkbenchAnomalyItem[];
};

export type WorkbenchZoneId = "paired" | "unpaired";

export type WorkbenchBankCategoryResolutionStatus =
  | "unmatched"
  | "auto_matched"
  | "needs_confirmation"
  | "internal_transfer"
  | "manual_confirmed"
  | (string & {});

export type WorkbenchRecord = {
  id: string;
  caseId?: string;
  exceptionCaseId?: string;
  recordType: WorkbenchRecordType;
  sourceKind?: WorkbenchSourceKind;
  sourceOaId?: string;
  sourceExpenseItemIds?: string[];
  externalUrl?: string;
  expenseItems?: WorkbenchExpenseItem[];
  displayRole?: "expense-claim-summary" | "expense-claim-item";
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
  categoryResolutionStatus?: WorkbenchBankCategoryResolutionStatus;
  bankTextFields?: WorkbenchBankTextField[];
  relationNote?: string;
  relationAmountCheck?: WorkbenchAmountCheck;
  specialMetadata?: Record<string, unknown>;
  oaInvoiceAnomaly?: WorkbenchAnomalyItem;
  displayOnly?: boolean;
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
  attachmentInvoicePromotionMode: "disabled" | "link_existing_only" | "create_missing" | (string & {});
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

export type OaApplicantCredentialStatus = "configured" | "unconfigured" | (string & {});

export type OaApplicantCredentialSummary = {
  targetApplicantCode: string;
  targetApplicantName: string;
  oaUsername: string;
  credentialStatus: OaApplicantCredentialStatus;
  hasCredential: boolean;
  enabled: boolean;
};

export type SaveOaApplicantCredentialRequest = {
  targetApplicantCode: string;
  targetApplicantName: string;
  oaUsername: string;
  password: string;
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

export type WorkbenchRelationGroup = {
  id: string;
  detailKey?: string;
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
  workbenchAnomaly?: WorkbenchAnomaly;
  specialMetadata?: Record<string, unknown>;
  completion?: {
    isComplete: boolean;
    missingRecordTypes: WorkbenchRecordType[];
    blockingReasons: string[];
  };
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
  operationType: "confirm_link" | "withdraw_relation";
  previewId: string;
  submitExpectedVersions: Record<string, unknown>;
  canSubmit: boolean;
  requiresNote: boolean;
  message: string;
  before: {
    groups: WorkbenchRelationGroup[];
  };
  after: {
    groups: WorkbenchRelationGroup[];
  };
  amountSummary: WorkbenchAmountSummary;
};

export type WorkbenchSummary = {
  oaCount: number;
  bankCount: number;
  invoiceCount: number;
  pairedCount: number;
  unpairedCount: number;
  unpairedExceptionCount: number;
  pairedExceptionCount: number;
  totalCount: number;
  zoneCounts: Record<WorkbenchZoneId, WorkbenchZoneCounts>;
};

export type WorkbenchStatistics = {
  oaCount?: number;
  bankTransactionCount?: number;
  inputInvoiceCount?: number;
  outputInvoiceCount?: number;
  pairedGroupCount?: number;
  unpairedObjectCount?: number;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
  pairedOaCount?: number;
  pairedBankTransactionCount?: number;
  pairedInvoiceCount?: number;
  incompleteGroupCount?: number;
  missingOaGroupCount?: number;
  missingBankGroupCount?: number;
  missingInvoiceGroupCount?: number;
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
  status?: string;
  sourceKind?: string;
  sort?: WorkbenchGroupsSort;
  detailLevel?: "summary" | "full";
  filtersByPaneAndColumn?: Partial<Record<WorkbenchRecordType, Record<string, string[]>>>;
  timeFilterByPane?: Partial<Record<WorkbenchRecordType, { mode: "year"; year: string } | { mode: "month"; month: string }>>;
  exceptionBucket?: "unpaired" | "paired";
};

export type WorkbenchFilterOption = {
  value: string;
  label: string;
  missing: boolean;
};

export type WorkbenchFilterOptionsPage = {
  options: WorkbenchFilterOption[];
  pageSize: number;
  hasMore: boolean;
  nextCursor: string | null;
};

export type WorkbenchFilterOptionsRequest = {
  pane: WorkbenchRecordType;
  facet: "column" | "time_year";
  column?: string;
  optionSearch?: string;
  cursor?: string | null;
};

export type WorkbenchFilterOptionsLoader = (
  zone: WorkbenchZoneId,
  request: WorkbenchFilterOptionsRequest,
  signal?: AbortSignal,
) => Promise<WorkbenchFilterOptionsPage>;

export type WorkbenchZonePageInfo = {
  zone: WorkbenchZoneId;
  page: number;
  pageSize: number;
  total: number;
  rowCounts: Pick<WorkbenchZoneCounts, "oa" | "bank" | "invoice" | "rows">;
  hasMore: boolean;
  cursor: string | null;
  nextCursor: string | null;
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
  summary: WorkbenchSummary;
  invoiceInventory: WorkbenchInvoiceInventory;
  paired: {
    groups: WorkbenchRelationGroup[];
  };
  unpaired: {
    groups: WorkbenchRelationGroup[];
  };
};

export type WorkbenchInitialPageResult = {
  data: WorkbenchData;
  pages: Record<WorkbenchZoneId, WorkbenchZonePageInfo>;
  statistics?: WorkbenchStatistics;
};

export type WorkbenchGroupsPageResult = {
  zone: WorkbenchZoneId;
  groups: WorkbenchRelationGroup[];
  page: WorkbenchZonePageInfo;
};

export type IgnoredWorkbenchData = {
  month: string;
  rows: WorkbenchRecord[];
};

export type WorkbenchAccessRole = "full_access" | "read_export_only";

export type WorkbenchAccessAccount = {
  username: string;
  accessTier: WorkbenchAccessRole;
};

export type WorkbenchAccessControl = {
  version: number;
  administrator: {
    username: string;
    accessTier: "admin";
    protected: true;
  };
  accounts: WorkbenchAccessAccount[];
};

export type WorkbenchSettingsDataResetAction =
  | "reset_bank_transactions"
  | "reset_invoices"
  | "reset_oa_and_rebuild";

export type WorkbenchSettingsDataResetPreview = {
  action: WorkbenchSettingsDataResetAction;
  impactCounts: Record<string, number>;
  impactFingerprint: string;
  recoveryReady: boolean;
  recoveryReceiptId: string | null;
  recoveryValidUntil: string | null;
};

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
  affectedScopeKeys: string[];
};

export type OaManualImportList = {
  rowIds: string[];
  entries: OaManualImportEntry[];
};

export type OaManualImportRemovalResult = {
  removed: boolean;
  rowId: string;
  affectedScopeKeys: string[];
};

export type OaManualAttachmentRefreshResult = {
  rows: Array<{
    rowId: string;
    attachmentFileCount: number;
    importableInvoiceCount: number;
    unrecognizedAttachmentCount: number;
  }>;
  errors: Array<Record<string, unknown>>;
  affectedScopeKeys: string[];
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
