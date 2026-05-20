export type PendingInvoiceDirection = "expense" | "income";

export type PendingInvoiceFilter =
  | "all"
  | "requires_invoice"
  | "bank_statement_as_invoice"
  | "no_invoice_required";

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

export type PendingInvoiceBankTransaction = {
  id: string;
  counterpartyName: string;
  tradeTime: string;
  amount: string;
  bankName: string;
  accountLast4: string;
  effectiveTagCode: string | null;
  effectiveTagLabel: string | null;
};

export type PendingInvoice = {
  id: string;
  invoiceNo: string;
  digitalInvoiceNo: string;
  issueDate: string;
  totalWithTax: string;
  sellerName: string;
  buyerName: string;
  invoiceType: "input" | "output" | (string & {});
};

export type PendingInvoiceRow = {
  id: string;
  bankTransaction: PendingInvoiceBankTransaction;
  invoices: PendingInvoice[];
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
  };
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
  signal?: AbortSignal;
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
