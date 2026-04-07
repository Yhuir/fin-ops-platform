export type TaxInvoiceRecord = {
  id: string;
  invoiceNo: string;
  invoiceType: string;
  counterparty: string;
  issueDate: string;
  taxRate: string;
  amount: string;
  taxAmount: string;
  statusLabel?: string;
  isLocked?: boolean;
  isSelectable?: boolean;
};

export type TaxCertifiedInvoiceRecord = TaxInvoiceRecord & {
  matchedInputId: string | null;
};

export type TaxSummary = {
  outputTax: string;
  certifiedInputTax: string;
  plannedInputTax: string;
  inputTax: string;
  deductibleTax: string;
  resultLabel: string;
  resultAmount: string;
};

export type TaxMonthData = {
  outputInvoices: TaxInvoiceRecord[];
  inputPlanInvoices: TaxInvoiceRecord[];
  certifiedMatchedInvoices: TaxCertifiedInvoiceRecord[];
  certifiedOutsidePlanInvoices: TaxCertifiedInvoiceRecord[];
  lockedCertifiedInputIds: string[];
  defaultSelectedOutputIds: string[];
  defaultSelectedInputIds: string[];
  summary: TaxSummary;
};

export type TaxCertifiedImportPreviewRow = {
  id: string;
  month: string;
  digitalInvoiceNo: string | null;
  invoiceCode: string | null;
  invoiceNo: string | null;
  issueDate: string | null;
  sellerTaxNo: string | null;
  sellerName: string | null;
  taxAmount: string | null;
  deductibleTaxAmount: string | null;
  selectionStatus: string | null;
  invoiceStatus: string | null;
  selectionTime: string | null;
  sourceFileName: string;
  sourceRowNumber: number;
};

export type TaxCertifiedImportPreviewFile = {
  id: string;
  fileName: string;
  month: string;
  recognizedCount: number;
  invalidCount: number;
  matchedPlanCount: number;
  outsidePlanCount: number;
  rows: TaxCertifiedImportPreviewRow[];
};

export type TaxCertifiedImportPreviewResult = {
  sessionId: string;
  importedBy: string;
  fileCount: number;
  status: string;
  files: TaxCertifiedImportPreviewFile[];
  summary: {
    recognizedCount: number;
    invalidCount: number;
    matchedPlanCount: number;
    outsidePlanCount: number;
  };
};

export type TaxCertifiedImportConfirmResult = {
  batchId: string;
  sessionId: string;
  importedBy: string;
  fileCount: number;
  months: string[];
  persistedRecordCount: number;
};
