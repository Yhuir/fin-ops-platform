import type { BackgroundJob } from "../backgroundJobs/types";

export type EtcInvoiceStatus = "unsubmitted" | "submitted";

export type EtcInvoice = {
  id: string;
  invoiceNumber: string;
  issueDate: string;
  passageStartDate: string | null;
  passageEndDate: string | null;
  plateNumber: string;
  sellerName: string;
  buyerName: string;
  amountWithoutTax: string;
  taxAmount: string;
  totalAmount: string;
  status: EtcInvoiceStatus;
  hasPdf: boolean;
  hasXml: boolean;
};

export type EtcInvoiceCounts = {
  unsubmitted: number;
  submitted: number;
};

export type EtcInvoiceQuery = {
  status?: EtcInvoiceStatus;
  month?: string;
  plate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type EtcInvoiceListPayload = {
  counts: EtcInvoiceCounts;
  items: EtcInvoice[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcImportSummary = {
  imported: number;
  duplicatesSkipped: number;
  attachmentsCompleted: number;
  failed: number;
  items: unknown[];
};

export type EtcImportItemStatus =
  | "created"
  | "duplicate_skipped"
  | "attachment_completed"
  | "failed";

export type EtcImportItem = {
  invoiceNumber: string;
  fileName: string;
  status: EtcImportItemStatus | string;
  reason: string;
};

export type EtcImportPreviewResult = {
  sessionId: string;
  imported: number;
  duplicatesSkipped: number;
  attachmentsCompleted: number;
  failed: number;
  items: EtcImportItem[];
};

export type EtcImportConfirmResult = EtcImportPreviewResult & {
  job?: BackgroundJob;
};

export type EtcOaDraftPayload = {
  batchId: string;
  etcBatchId: string;
  oaDraftId: string;
  oaDraftUrl: string;
};
