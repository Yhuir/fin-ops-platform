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
