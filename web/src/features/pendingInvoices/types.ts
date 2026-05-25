export type PendingInvoiceDirection = "expense" | "income";

export type PendingInvoiceFilter =
  | "all"
  | "requires_invoice"
  | "bank_statement_as_invoice"
  | "no_invoice_required";

export type PendingInvoiceReadModelStatus = "fresh" | "refreshing" | "stale" | (string & {});

export type PendingInvoiceStatusCode =
  | "paid_invoiced"
  | "paid_pending_invoice"
  | "paid_pending_future_invoice"
  | "invoice_not_fully_paid"
  | "no_invoice_required"
  | "bank_statement_as_invoice"
  | "pending"
  | (string & {});

export type PendingInvoiceStatusSeverity = "success" | "info" | "warning" | "error" | "default" | (string & {});

export type PendingInvoicePrimaryAction =
  | "view_relation"
  | "view_payment_detail"
  | "attach_or_create_invoice"
  | "attach_existing_invoice"
  | "manual_invoice"
  | "view_rules"
  | "open_rules"
  | "none"
  | (string & {});

export type PendingInvoiceSortField =
  | "trade_date"
  | "amount"
  | "counterparty_name"
  | "status_code"
  | "seller_name"
  | "invoice_total"
  | "oa_applicant"
  | "project_name";

export type PendingInvoiceSortDirection = "asc" | "desc";

export type PendingInvoiceColumnFilter =
  | { field: "trade_date"; operator: "between"; value: { from?: string; to?: string } }
  | { field: "bank_name" | "account_name" | "counterparty_name" | "seller_name" | "oa_applicant" | "project_name"; operator: "contains"; value: string }
  | { field: "bank_name" | "account_name" | "counterparty_name" | "seller_name" | "oa_applicant" | "project_name" | "status_code" | "rule_group"; operator: "in"; values: string[] }
  | { field: "amount" | "invoice_total"; operator: "between"; value: { min?: string; max?: string } }
  | { field: "amount" | "invoice_total"; operator: "eq"; value: string }
  | { field: "summary_remark"; operator: "contains"; value: string };

export type BankTransactionTagStatus = "active" | "archived" | (string & {});

export type BankTransactionTagSource = "system" | "custom" | (string & {});

export type BankTransactionTagDefinition = {
  code: string;
  label: string;
  path: string[];
  status: BankTransactionTagStatus;
  source: BankTransactionTagSource;
};

export type BankTransactionTagDictionary = {
  version: number;
  tags: BankTransactionTagDefinition[];
};

export type PendingInvoiceTagGroups = {
  requiresInvoice: string[];
  bankStatementAsInvoice: string[];
  noInvoiceRequired: string[];
};

export type PendingInvoiceRuleGroupCode = "requires_invoice" | "bank_statement_as_invoice" | "no_invoice_required";

export type PendingInvoiceRuleTag = {
  code: string;
  label: string;
  status: BankTransactionTagStatus;
};

export type PendingInvoiceRuleGroup = {
  code: PendingInvoiceRuleGroupCode;
  label: string;
  tagCodes: string[];
  tags: PendingInvoiceRuleTag[];
};

export type PendingInvoiceRulesPayload = {
  version: number;
  availableTags: PendingInvoiceRuleTag[];
  groups: {
    requiresInvoice: PendingInvoiceRuleGroup;
    bankStatementAsInvoice: PendingInvoiceRuleGroup;
    noInvoiceRequired: PendingInvoiceRuleGroup;
  };
  permissions: {
    canSave: boolean;
  };
};

export type PendingInvoiceBankTransaction = {
  id: string;
  accountNo: string;
  counterpartyName: string;
  counterpartyAccountNo: string;
  counterpartyBankName: string;
  tradeTime: string;
  bookedDate: string;
  debitAmount: string;
  creditAmount: string;
  amount: string;
  balance: string;
  currency: string;
  bankName: string;
  bankShortName: string;
  accountName: string;
  accountLast4: string;
  summary: string;
  remark: string;
  statementSerialNo: string;
  enterpriseSerialNo: string;
  voucherType: string;
  voucherNo: string;
  effectiveTagCode: string | null;
  effectiveTagLabel: string | null;
};

export type PendingInvoiceMatchedRule = {
  source: string;
  group: PendingInvoiceRuleGroupCode | (string & {});
  tagCode: string;
  tagLabel: string;
} | null;

export type PendingInvoiceAcquisitionStatus = {
  code: PendingInvoiceStatusCode;
  label: string;
  reason: string;
  severity: PendingInvoiceStatusSeverity;
  primaryAction: PendingInvoicePrimaryAction;
  matchedRule: PendingInvoiceMatchedRule;
};

export type PendingInvoiceSummary = {
  id: string;
  invoiceNo: string;
  digitalInvoiceNo: string;
  invoiceCode: string;
  issueDate: string;
  totalWithTax: string;
  sellerName: string;
  sellerTaxNo: string;
  buyerName: string;
  invoiceType: "input" | "output" | (string & {});
};

export type PendingInvoicePaymentSummary = {
  paidTotal: string;
  invoiceTotal: string;
  remainingAmount: string;
  differenceAmount: string;
};

export type PendingInvoiceInvoiceZone = {
  primary: PendingInvoiceSummary | null;
  relationCount: number;
  hasMultiple: boolean;
  summaries: PendingInvoiceSummary[];
  paymentSummary: PendingInvoicePaymentSummary | null;
};

export type PendingInvoiceOaSummary = {
  id: string;
  applicant: string;
  applicationType: string;
  projectName: string;
  status: string;
};

export type PendingInvoiceOaZone = {
  primary: PendingInvoiceOaSummary | null;
  relationCount: number;
  hasMultiple: boolean;
  detailAvailable: boolean;
  summaries: PendingInvoiceOaSummary[];
};

export type PendingInvoiceSourceSummary = {
  bankTransactionRows: number;
  expenseRows: number;
  incomeRows: number;
  currentDirectionRows: number;
  excludedDirectionRows: number;
};

export type PendingInvoiceRow = {
  id: string;
  bankTransaction: PendingInvoiceBankTransaction;
  invoiceAcquisitionStatus: Readonly<PendingInvoiceAcquisitionStatus>;
  inputInvoices: PendingInvoiceInvoiceZone;
  oa: PendingInvoiceOaZone;
  invoices: PendingInvoiceSummary[];
  oaApplicant: string | null;
  canCreateInvoice: boolean;
  relationCaseIds: string[];
};

export type PendingInvoiceRowsResponse = {
  direction: PendingInvoiceDirection;
  filter: PendingInvoiceFilter;
  rows: PendingInvoiceRow[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
  summary: {
    totalRows: number;
    missingInvoiceRows: number;
    createInvoiceAvailableRows: number;
    sourceSummary?: PendingInvoiceSourceSummary;
  };
  readModelStatus: PendingInvoiceReadModelStatus;
  tagDictionary?: BankTransactionTagDictionary;
};

export type FetchPendingInvoiceRowsRequest = {
  direction: PendingInvoiceDirection;
  filter?: PendingInvoiceFilter;
  dateFrom?: string | null;
  dateTo?: string | null;
  keyword?: string | null;
  page?: number;
  pageSize?: number;
  filters?: PendingInvoiceColumnFilter[];
  sortField?: PendingInvoiceSortField;
  sortDirection?: PendingInvoiceSortDirection;
  signal?: AbortSignal;
};

export type PendingInvoiceFilterOption = {
  value: string;
  label: string;
  count: number;
};

export type PendingInvoiceFilterField = {
  field: string;
  label: string;
  operators: string[];
  options: PendingInvoiceFilterOption[];
};

export type PendingInvoiceFilterOptionsResponse = {
  fields: PendingInvoiceFilterField[];
};

export type PendingInvoiceRelationDetail = {
  transactionSummary: {
    id: string;
    counterpartyName: string;
    tradeTime: string;
    debitAmount: string;
  };
  relatedInvoices: PendingInvoiceSummary[];
  paymentRows: Array<{
    id: string;
    tradeTime: string;
    counterpartyName: string;
    debitAmount: string;
    relationCaseId: string;
  }>;
  paidTotal: string;
  invoiceTotal: string;
  remainingAmount: string;
  differenceAmount: string;
  availableActions: string[];
};

export type PendingInvoiceObjectDetailTarget = {
  kind: "bankTransaction" | "invoice" | "oa";
  id: string;
  rowId?: string;
};

export type PendingInvoiceDetailField = {
  label: string;
  value: string | number | null | undefined;
};

export type PendingInvoiceDetailSection = {
  title: string;
  fields: PendingInvoiceDetailField[];
};

export type PendingInvoiceOaPrintField = {
  label: string;
  value: string | number | null | undefined;
};

export type PendingInvoiceOaApproval = {
  title: string;
  lines: string[];
  signature: string;
};

export type PendingInvoiceOaPrintLayout = {
  formTitle: string;
  downloadLabel: string;
  fields: PendingInvoiceOaPrintField[];
  approvals: PendingInvoiceOaApproval[];
};

export type PendingInvoiceObjectDetail = {
  title: string;
  subtitle: string;
  detailAvailable: boolean;
  unavailableReason: string;
  sections: PendingInvoiceDetailSection[];
  oaPrintLayout?: PendingInvoiceOaPrintLayout;
};

export type PendingInvoiceCandidateStatus = "available" | "already_related" | "conflict" | (string & {});

export type PendingInvoiceCandidateSortField = "issue_date" | "total_with_tax" | "seller_name" | "amount_difference_abs";

export type FetchPendingInvoiceCandidatesRequest = {
  transactionId: string;
  keyword?: string | null;
  sellerName?: string | null;
  issueDateFrom?: string | null;
  issueDateTo?: string | null;
  amountMin?: string | null;
  amountMax?: string | null;
  sortField?: PendingInvoiceCandidateSortField;
  sortDirection?: PendingInvoiceSortDirection;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type PendingInvoiceCandidate = PendingInvoiceSummary & {
  invoiceId: string;
  relatedPaidTotal: string;
  remainingAmount: string;
  amountDifferenceAbs: string;
  candidateStatus: PendingInvoiceCandidateStatus;
  conflictReason: string;
};

export type PendingInvoiceCandidatesResponse = {
  rows: PendingInvoiceCandidate[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type AttachExistingInvoicePreviewRequest = {
  transactionId: string;
  invoiceId: string;
  requestId: string;
};

export type AttachExistingInvoicePreview = {
  previewId: string;
  requestKey: string;
  canConfirm: boolean;
  transactionSummary: PendingInvoiceRelationDetail["transactionSummary"];
  invoiceSummary: PendingInvoiceSummary;
  paymentImpact: {
    paidTotalBefore: string;
    paidTotalAfter: string;
    invoiceTotal: string;
    remainingAmountAfter: string;
    differenceAmountAfter: string;
  };
  affectedMonths: string[];
  warnings: string[];
  conflicts: string[];
  expiresAt: string;
};

export type AttachExistingInvoiceConfirmRequest = {
  transactionId: string;
  invoiceId: string;
  previewId: string;
  requestId: string;
};

export type AttachExistingInvoiceResult = {
  status: string;
  requestId: string;
  requestKey: string;
  transactionId: string;
  invoiceId: string;
  relationCaseId: string;
  relationMode: string;
  affectedTransactionIds: string[];
  affectedInvoiceIds: string[];
  affectedMonths: string[];
  row: PendingInvoiceRow | null;
};

export type PendingInvoiceExportPreview = {
  fileName: string;
  rowCount: number;
  scopeLabel: string;
  columns: string[];
  sampleRows: Array<Record<string, string>>;
};

export type PendingInvoiceExportDownload = {
  blob: Blob;
  fileName: string;
};

export type ManualPendingInvoiceRequest = {
  requestId: string;
  previewId?: string;
  bankTransactionId: string;
  invoiceNo?: string;
  digitalInvoiceNo?: string;
  invoiceCode?: string;
  issueDate: string;
  totalWithTax: string;
  taxAmount?: string;
  taxRate?: string;
  sellerName: string;
  sellerTaxNo?: string;
  buyerName: string;
  buyerTaxNo?: string;
  remark?: string;
};

export type ManualPendingInvoicePreview = {
  previewId: string;
  requestKey: string;
  canConfirm: boolean;
  targetInvoiceType: "input" | "output" | (string & {});
  bankTransactionSummary: {
    id: string;
    direction: PendingInvoiceDirection | (string & {});
    counterpartyName: string;
    tradeTime: string;
    amount: string;
  };
  invoiceIdentity: {
    sourceUniqueKey: string;
    dataFingerprint: string;
  };
  duplicateCheck: {
    status: string;
    matchedInvoiceId: string | null;
    message: string;
  };
  relationImpact: {
    relationMode: string;
    affectedMonths: string[];
  };
  affectedMonths: string[];
  warnings: string[];
};

export type ManualPendingInvoiceResult = {
  invoiceId: string;
  relationCaseId: string;
  affectedTransactionIds: string[];
  affectedInvoiceIds: string[];
  affectedMonths: string[];
  row: PendingInvoiceRow | null;
};
