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
  | "oa_supporting_document"
  | (string & {});

export type WorkbenchActionVariant = "detail-only" | "bank-review";

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
  expenseType?: string;
  feeContent?: string;
  feeDescription?: string;
  attachmentFileCount?: number;
  supportingDocuments?: Array<{
    id: string;
    fileName: string;
    contentType: string;
    sizeBytes: number;
    createdAt: string;
    contentUrl: string;
  }>;
  workbenchAnomalies?: WorkbenchAnomalyItem[];
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

export const WORKBENCH_AMOUNT_ANOMALY_CODES = [
  "oa_bank_equal_invoice_more",
  "oa_bank_equal_invoice_less",
  "oa_invoice_equal_bank_more",
  "oa_invoice_equal_bank_less",
  "bank_invoice_equal_oa_less",
  "bank_invoice_equal_oa_more",
  "all_amounts_different",
] as const;

export type WorkbenchAmountAnomalyCode = typeof WORKBENCH_AMOUNT_ANOMALY_CODES[number];

export const WORKBENCH_AMOUNT_ANOMALY_LABELS: Record<WorkbenchAmountAnomalyCode, string> = {
  oa_bank_equal_invoice_more: "OA 流水一致，票多",
  oa_bank_equal_invoice_less: "OA 流水一致，票少",
  oa_invoice_equal_bank_more: "OA 发票一致，付多",
  oa_invoice_equal_bank_less: "OA 发票一致，付少",
  bank_invoice_equal_oa_less: "发票流水一致，OA 提少了",
  bank_invoice_equal_oa_more: "发票流水一致，OA 提多了",
  all_amounts_different: "三项不一致",
};

export function isWorkbenchAmountAnomalyCode(value: unknown): value is WorkbenchAmountAnomalyCode {
  return typeof value === "string"
    && (WORKBENCH_AMOUNT_ANOMALY_CODES as readonly string[]).includes(value);
}

export type WorkbenchExceptionView = "amount" | "document_only";
export type WorkbenchExceptionBucket = "unpaired" | "paired";

export type WorkbenchExceptionCounts = {
  total: number;
  amountTotal: number;
  documentOnly: number;
  byCode: Record<WorkbenchAmountAnomalyCode, number>;
};

export type WorkbenchAnomalyItem = {
  code:
    | WorkbenchAmountAnomalyCode
    | "oa_invoice_attachment_absent"
    | "oa_invoice_attachment_unparsed"
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
  displayScope: "row" | "expense_item" | "group" | (string & {});
  displayPane: WorkbenchRecordType | "group";
  displayRowId?: string;
  reviewDecision?: "pending" | "accept_paired" | "keep_unpaired";
  reviewNote?: string;
  reviewedByAccount?: string;
  reviewedByName?: string;
  reviewedAt?: string;
};

export type WorkbenchAnomaly = {
  code: "workbench_anomaly" | (string & {});
  fingerprint: string;
  reviewDecision: "pending" | "accept_paired" | "keep_unpaired";
  reviewNote: string;
  reviewedByAccount: string;
  reviewedByName: string;
  reviewedAt?: string;
  confirmation?: {
    note: string;
  };
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
  sourceKinds?: WorkbenchSourceKind[];
  sourceOaId?: string;
  sourceExpenseItemIds?: string[];
  externalUrl?: string;
  expenseItems?: WorkbenchExpenseItem[];
  expenseType?: string;
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
  specialMetadata?: Record<string, unknown>;
  workbenchAnomalies?: WorkbenchAnomalyItem[];
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

export type WorkbenchRecordIdentity = {
  id: string;
  recordType: WorkbenchRecordType;
};

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
  formalMemberIdentities?: WorkbenchRecordIdentity[];
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

export type WorkbenchOaInvoiceSupplementTarget = {
  caseId: string;
  oaRowId: string;
  expenseItemId: string;
};

export type WorkbenchInvoiceExpenseItemCandidate = {
  key: string;
  oaRowId: string;
  oaLabel: string;
  expenseItemId: string;
  rowIndex: string;
  projectName: string;
  amount: string;
  expenseType?: string;
  feeContent?: string;
  feeDescription?: string;
};

export type WorkbenchInvoiceExpenseItemSelection = {
  oaRowId: string;
  expenseItemId: string;
};

export type WorkbenchInvoiceExpenseItemAssignmentTarget = {
  caseId: string;
  invoiceRowId: string;
  invoiceNo: string;
  sellerName: string;
  amount: string;
  anomalyFingerprint: string;
  idempotencyKey: string;
  candidates: WorkbenchInvoiceExpenseItemCandidate[];
};

export type WorkbenchInvoiceExpenseItemAssignmentPayload = {
  caseId: string;
  invoiceRowId: string;
  targets: WorkbenchInvoiceExpenseItemSelection[];
  anomalyFingerprint: string;
  idempotencyKey: string;
};

export type WorkbenchOaSupportingDocument = {
  id: string;
  relationCaseId?: string;
  oaRowId: string;
  expenseItemId: string;
  fileName: string;
  contentType: string;
  sha256: string;
  sizeBytes: number;
  createdBy: string;
  createdAt: string;
  contentUrl: string;
  thumbnailUrl: string;
};

export type WorkbenchOaSupportingDocumentGalleryPage = {
  documents: WorkbenchOaSupportingDocument[];
  pageSize: number;
  hasMore: boolean;
  nextCursor: string | null;
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
  invoiceTotalCount?: number;
  inputInvoiceCount?: number;
  outputInvoiceCount?: number;
  completedOaCount?: number;
  inProgressOaCount?: number;
  expenseTransactionCount?: number;
  incomeTransactionCount?: number;
  manualImportInvoiceCount?: number;
  oaParseCreatedInvoiceCount?: number;
};

export type WorkbenchZoneCounts = {
  groups: number;
  oa: number;
  bank: number;
  invoice: number;
  canonicalInvoice: number;
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
  exceptionBucket?: WorkbenchExceptionBucket;
  exceptionView?: WorkbenchExceptionView;
  exceptionCode?: WorkbenchAmountAnomalyCode;
};

export type WorkbenchFilterOption = {
  value: string;
  label: string;
  missing: boolean;
  group?: string;
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
  rowCounts: Pick<WorkbenchZoneCounts, "oa" | "bank" | "invoice" | "canonicalInvoice" | "rows">;
  hasMore: boolean;
  cursor: string | null;
  nextCursor: string | null;
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
  selectedExceptionCode?: WorkbenchAmountAnomalyCode;
  exceptionCounts?: WorkbenchExceptionCounts;
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
  eventId: string;
  status: "queued" | "pending";
  rowIds: string[];
  affectedScopeKeys: string[];
};

export type OaManualAttachmentRefreshRow = {
  rowId: string;
  attachmentFileCount: number;
  importableInvoiceCount: number;
  unrecognizedAttachmentCount: number;
};

export type OaManualAttachmentRefreshError = {
  rowId: string;
  code: string;
  message: string;
};

export type OaManualAttachmentRefreshStatus = {
  eventId: string;
  status: "pending" | "processing" | "done" | "failed" | "dead_lettered";
  rowIds: string[];
  affectedScopeKeys: string[];
  error: string;
  result: {
    rows: OaManualAttachmentRefreshRow[];
    errors: OaManualAttachmentRefreshError[];
    promotionSummary: Record<string, unknown>;
  } | null;
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
