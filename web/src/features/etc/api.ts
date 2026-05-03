import { readOATokenCookie } from "../session/api";
import { mapBackgroundJob, type ApiBackgroundJob } from "../backgroundJobs/api";
import type {
  EtcImportConfirmResult,
  EtcImportItem,
  EtcImportPreviewResult,
  EtcImportSummary,
  EtcInvoice,
  EtcInvoiceListPayload,
  EtcInvoiceQuery,
  EtcOaDraftPayload,
} from "./types";

type ApiEtcInvoice = {
  id: string;
  invoice_number: string;
  issue_date: string;
  passage_start_date?: string | null;
  passage_end_date?: string | null;
  plate_number?: string | null;
  seller_name?: string | null;
  buyer_name?: string | null;
  amount_without_tax?: string | number | null;
  tax_amount?: string | number | null;
  total_amount?: string | number | null;
  status: "unsubmitted" | "submitted";
  has_pdf?: boolean | null;
  has_xml?: boolean | null;
};

type ApiEtcInvoicePayload = {
  counts?: {
    unsubmitted?: number;
    submitted?: number;
  };
  items?: ApiEtcInvoice[];
  pagination?: {
    page?: number;
    page_size?: number;
    total?: number;
  };
};

type ApiEtcImportSummary = {
  job?: ApiBackgroundJob;
  sessionId?: string;
  session_id?: string;
  summary?: {
    imported?: number;
    duplicatesSkipped?: number;
    duplicates_skipped?: number;
    attachmentsCompleted?: number;
    attachments_completed?: number;
    failed?: number;
  };
  imported?: number;
  duplicatesSkipped?: number;
  duplicates_skipped?: number;
  attachmentsCompleted?: number;
  attachments_completed?: number;
  failed?: number;
  items?: ApiEtcImportItem[];
};

type ApiEtcImportItem = {
  invoiceNumber?: string;
  invoice_number?: string;
  fileName?: string;
  file_name?: string;
  status?: string;
  reason?: string;
  message?: string;
};

type ApiEtcOaDraftPayload = {
  batchId?: string;
  batch_id?: string;
  oaDraftId?: string;
  oa_draft_id?: string;
  oaDraftUrl?: string;
  oa_draft_url?: string;
};

function withAuthHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers ?? undefined);
  const token = readOATokenCookie();
  if (token && !nextHeaders.has("Authorization")) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: withAuthHeaders(init.headers),
    credentials: init.credentials ?? "include",
  });
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  let payload = {} as T;
  if (trimmedText.length > 0) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch (error) {
      const contentType = response.headers.get("Content-Type") ?? "";
      const looksLikeHtml = trimmedText.startsWith("<") || contentType.toLowerCase().includes("text/html");
      if (looksLikeHtml) {
        throw new Error("ETC 接口返回了 HTML 页面，请检查 fin-ops 后端代理路径或服务器部署配置。");
      }
      throw new Error("ETC 接口返回了无效 JSON。");
    }
  }
  if (!response.ok) {
    const errorPayload = payload as { message?: unknown; error?: unknown };
    const message = typeof errorPayload.message === "string" ? errorPayload.message : "";
    throw new Error(message || trimmedText || "ETC API request failed");
  }
  return payload;
}

function normalizeMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return "0.00";
  }
  return String(value);
}

function mapInvoice(invoice: ApiEtcInvoice): EtcInvoice {
  return {
    id: invoice.id,
    invoiceNumber: invoice.invoice_number,
    issueDate: invoice.issue_date,
    passageStartDate: invoice.passage_start_date ?? null,
    passageEndDate: invoice.passage_end_date ?? null,
    plateNumber: invoice.plate_number ?? "",
    sellerName: invoice.seller_name ?? "",
    buyerName: invoice.buyer_name ?? "",
    amountWithoutTax: normalizeMoney(invoice.amount_without_tax),
    taxAmount: normalizeMoney(invoice.tax_amount),
    totalAmount: normalizeMoney(invoice.total_amount),
    status: invoice.status,
    hasPdf: Boolean(invoice.has_pdf),
    hasXml: Boolean(invoice.has_xml),
  };
}

function mapEtcImportItem(item: ApiEtcImportItem): EtcImportItem {
  return {
    invoiceNumber: item.invoiceNumber ?? item.invoice_number ?? "",
    fileName: item.fileName ?? item.file_name ?? "",
    status: item.status ?? "",
    reason: item.reason ?? item.message ?? "",
  };
}

function mapEtcImportResult(payload: ApiEtcImportSummary): EtcImportPreviewResult {
  const summary = payload.summary ?? {};
  return {
    sessionId: payload.sessionId ?? payload.session_id ?? "",
    imported: payload.imported ?? summary.imported ?? 0,
    duplicatesSkipped: payload.duplicatesSkipped ?? payload.duplicates_skipped ?? summary.duplicatesSkipped ?? summary.duplicates_skipped ?? 0,
    attachmentsCompleted:
      payload.attachmentsCompleted
      ?? payload.attachments_completed
      ?? summary.attachmentsCompleted
      ?? summary.attachments_completed
      ?? 0,
    failed: payload.failed ?? summary.failed ?? 0,
    items: (payload.items ?? []).map(mapEtcImportItem),
  };
}

function mapEtcImportConfirmResult(payload: ApiEtcImportSummary): EtcImportConfirmResult {
  return {
    ...mapEtcImportResult(payload),
    ...(payload.job ? { job: mapBackgroundJob(payload.job) } : {}),
  };
}

export async function fetchEtcInvoices(query: EtcInvoiceQuery = {}): Promise<EtcInvoiceListPayload> {
  const params = new URLSearchParams();
  if (query.status) {
    params.set("status", query.status);
  }
  if (query.month) {
    params.set("month", query.month);
  }
  if (query.plate) {
    params.set("plate", query.plate);
  }
  if (query.keyword) {
    params.set("keyword", query.keyword);
  }
  params.set("page", String(query.page ?? 1));
  params.set("page_size", String(query.pageSize ?? 100));

  const payload = await requestJson<ApiEtcInvoicePayload>(`/api/etc/invoices?${params.toString()}`, {
    method: "GET",
    signal: query.signal,
  });
  const items = (payload.items ?? []).map(mapInvoice);
  return {
    counts: {
      unsubmitted: payload.counts?.unsubmitted ?? 0,
      submitted: payload.counts?.submitted ?? 0,
    },
    items,
    pagination: {
      page: payload.pagination?.page ?? query.page ?? 1,
      pageSize: payload.pagination?.page_size ?? query.pageSize ?? 100,
      total: payload.pagination?.total ?? items.length,
    },
  };
}

export async function importEtcZipFiles(files: File[]): Promise<EtcImportSummary> {
  return previewEtcZipFiles(files);
}

export async function previewEtcZipFiles(files: File[]): Promise<EtcImportPreviewResult> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const payload = await requestJson<ApiEtcImportSummary>("/api/etc/import/preview", {
    method: "POST",
    body: formData,
  });
  return mapEtcImportResult(payload);
}

export async function confirmEtcImportSession(sessionId: string): Promise<EtcImportConfirmResult> {
  const payload = await requestJson<ApiEtcImportSummary>("/api/etc/import/confirm", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sessionId }),
  });
  return mapEtcImportConfirmResult(payload);
}

export async function createEtcOaDraft(invoiceIds: string[]): Promise<EtcOaDraftPayload> {
  const payload = await requestJson<ApiEtcOaDraftPayload>("/api/etc/batches/draft", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ invoiceIds }),
  });
  return {
    batchId: payload.batchId ?? payload.batch_id ?? "",
    oaDraftId: payload.oaDraftId ?? payload.oa_draft_id ?? "",
    oaDraftUrl: payload.oaDraftUrl ?? payload.oa_draft_url ?? "",
  };
}

export async function confirmEtcBatchSubmitted(batchId: string): Promise<void> {
  await requestJson(`/api/etc/batches/${encodeURIComponent(batchId)}/confirm-submitted`, {
    method: "POST",
  });
}

export async function markEtcBatchNotSubmitted(batchId: string): Promise<void> {
  await requestJson(`/api/etc/batches/${encodeURIComponent(batchId)}/mark-not-submitted`, {
    method: "POST",
  });
}

export async function revokeEtcSubmittedInvoices(invoiceIds: string[]): Promise<void> {
  await requestJson("/api/etc/invoices/revoke-submitted", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ invoiceIds }),
  });
}
