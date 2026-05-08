import type { BackgroundJob } from "../backgroundJobs/types";
import type { ImportPreviewAuditCounts } from "../imports/types";

export type EtcBatchStatus = "unsubmitted" | "submitted";

export type EtcInvoiceStatus = EtcBatchStatus;

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

export type EtcPlateSummary = {
  plateNumber: string;
  invoiceCount: number;
  totalAmount: string;
};

export type EtcBatchSummary = {
  id: string;
  etcBatchId: string;
  externalBatchId: string;
  status: EtcBatchStatus;
  sourceType: string;
  invoiceCount: number;
  totalAmount: string;
  taxAmount: string;
  issueStartDate: string | null;
  issueEndDate: string | null;
  passageStartDate: string | null;
  passageEndDate: string | null;
  plateCount: number;
  plateSummary: EtcPlateSummary[];
  linkedOaRowId: string;
  linkedOaCaseId: string;
  linkedOaApplicant: string;
  linkedOaApplyDate: string;
  linkedOaAmount: string;
  amountDelta: string;
  note: string;
};

export type EtcBatchDetail = EtcBatchSummary & {
  invoiceItems: EtcInvoice[];
};

export type EtcBatchCounts = {
  unsubmitted: number;
  submitted: number;
};

export type EtcBatchQuery = {
  status?: EtcBatchStatus;
  month?: string;
  plate?: string;
  keyword?: string;
  page?: number;
  pageSize?: number;
  signal?: AbortSignal;
};

export type EtcInvoiceQuery = EtcBatchQuery;

export type EtcInvoiceListPayload = {
  counts: EtcInvoiceCounts;
  items: EtcInvoice[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
  };
};

export type EtcBatchListPayload = {
  counts: EtcBatchCounts;
  items: EtcBatchSummary[];
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
  audit?: ImportPreviewAuditCounts;
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
