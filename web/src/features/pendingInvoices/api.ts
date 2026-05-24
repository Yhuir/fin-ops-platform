import type {
  BankTransactionTagDefinition,
  BankTransactionTagDictionary,
  FetchPendingInvoiceRowsRequest,
  ManualPendingInvoicePreview,
  ManualPendingInvoiceRequest,
  ManualPendingInvoiceResult,
  PendingInvoice,
  PendingInvoiceBankTransaction,
  PendingInvoiceDirection,
  PendingInvoiceFilter,
  PendingInvoiceRow,
  PendingInvoiceRowsResponse,
} from "./types";
import { apiRequestJson } from "../apiClient";

type ApiTagDefinition = {
  code?: string | null;
  label?: string | null;
  path?: unknown[] | null;
  status?: string | null;
  source?: string | null;
};

type ApiTagDictionary = {
  version?: number | string | null;
  tags?: ApiTagDefinition[] | null;
  definitions?: ApiTagDefinition[] | null;
};

type ApiPendingInvoiceRow = {
  id?: string | null;
  bank_transaction?: Partial<{
    id: string | null;
    counterparty_name: string | null;
    trade_time: string | null;
    amount: string | null;
    bank_name: string | null;
    account_last4: string | null;
    effective_tag_code: string | null;
    effective_tag_label: string | null;
  }> | null;
  invoices?: Array<Partial<{
    id: string | null;
    invoice_no: string | null;
    digital_invoice_no: string | null;
    issue_date: string | null;
    total_with_tax: string | null;
    seller_name: string | null;
    buyer_name: string | null;
    invoice_type: string | null;
  }>> | null;
  oa_applicant?: string | null;
  can_create_invoice?: boolean | null;
  relation_case_ids?: unknown[] | null;
};

type ApiPendingInvoiceRowsResponse = {
  direction?: string | null;
  filter?: string | null;
  rows?: ApiPendingInvoiceRow[] | null;
  pagination?: {
    page?: number | null;
    page_size?: number | null;
    total?: number | null;
  } | null;
  summary?: {
    total_rows?: number | null;
    missing_invoice_rows?: number | null;
    create_invoice_available_rows?: number | null;
  } | null;
  tag_dictionary?: ApiTagDictionary | null;
  bank_transaction_tags?: ApiTagDictionary | null;
};

type ApiManualPendingInvoicePreview = {
  preview_id?: string | null;
  request_key?: string | null;
  can_confirm?: boolean | null;
  target_invoice_type?: string | null;
  bank_transaction_summary?: {
    id?: string | null;
    direction?: string | null;
    counterparty_name?: string | null;
    trade_time?: string | null;
    amount?: string | null;
  } | null;
  invoice_identity?: {
    source_unique_key?: string | null;
    data_fingerprint?: string | null;
  } | null;
  duplicate_check?: {
    status?: string | null;
    matched_invoice_id?: string | null;
    message?: string | null;
  } | null;
  relation_impact?: {
    relation_mode?: string | null;
    affected_months?: unknown[] | null;
  } | null;
  warnings?: unknown[] | null;
};

type ApiManualPendingInvoiceResult = {
  invoice_id?: string | null;
  relation_case_id?: string | null;
  affected_transaction_ids?: unknown[] | null;
  affected_invoice_ids?: unknown[] | null;
  affected_months?: unknown[] | null;
  row?: ApiPendingInvoiceRow | null;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  return apiRequestJson<T>(url, init);
}

function stringValue(value: unknown, fallback = "") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

export function mapBankTransactionTagDictionary(value: ApiTagDictionary | null | undefined): BankTransactionTagDictionary | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  return {
    version: Number(value.version ?? 0) || 0,
    tags: (value.tags ?? value.definitions ?? []).map((tag): BankTransactionTagDefinition => ({
      code: stringValue(tag.code),
      label: stringValue(tag.label, stringValue(tag.code)),
      path: stringList(tag.path),
      status: stringValue(tag.status, "active") as BankTransactionTagDefinition["status"],
      source: stringValue(tag.source, "system") as BankTransactionTagDefinition["source"],
    })).filter((tag) => tag.code.length > 0),
  };
}

function mapBankTransaction(value: ApiPendingInvoiceRow["bank_transaction"], fallbackId: string): PendingInvoiceBankTransaction {
  return {
    id: stringValue(value?.id, fallbackId),
    counterpartyName: stringValue(value?.counterparty_name, "—"),
    tradeTime: stringValue(value?.trade_time),
    amount: stringValue(value?.amount),
    bankName: stringValue(value?.bank_name),
    accountLast4: stringValue(value?.account_last4),
    effectiveTagCode: value?.effective_tag_code ?? null,
    effectiveTagLabel: value?.effective_tag_label ?? null,
  };
}

function mapInvoice(value: NonNullable<ApiPendingInvoiceRow["invoices"]>[number]): PendingInvoice {
  return {
    id: stringValue(value.id),
    invoiceNo: stringValue(value.invoice_no),
    digitalInvoiceNo: stringValue(value.digital_invoice_no),
    issueDate: stringValue(value.issue_date),
    totalWithTax: stringValue(value.total_with_tax),
    sellerName: stringValue(value.seller_name),
    buyerName: stringValue(value.buyer_name),
    invoiceType: stringValue(value.invoice_type) as PendingInvoice["invoiceType"],
  };
}

export function mapPendingInvoiceRow(row: ApiPendingInvoiceRow): PendingInvoiceRow {
  const id = stringValue(row.id, stringValue(row.bank_transaction?.id));
  return {
    id,
    bankTransaction: mapBankTransaction(row.bank_transaction, id),
    invoices: (row.invoices ?? []).map(mapInvoice).filter((invoice) => invoice.id || invoice.invoiceNo || invoice.digitalInvoiceNo),
    oaApplicant: row.oa_applicant && row.oa_applicant.trim() ? row.oa_applicant : null,
    canCreateInvoice: row.can_create_invoice === true,
    relationCaseIds: stringList(row.relation_case_ids),
  };
}

function mapRowsResponse(payload: ApiPendingInvoiceRowsResponse, request: FetchPendingInvoiceRowsRequest): PendingInvoiceRowsResponse {
  return {
    direction: (payload.direction ?? request.direction) as PendingInvoiceDirection,
    filter: (payload.filter ?? request.filter ?? "all") as PendingInvoiceFilter,
    rows: (payload.rows ?? []).map(mapPendingInvoiceRow),
    pagination: {
      page: payload.pagination?.page ?? 1,
      pageSize: payload.pagination?.page_size ?? request.pageSize ?? 50,
      total: payload.pagination?.total ?? payload.rows?.length ?? 0,
    },
    summary: {
      totalRows: payload.summary?.total_rows ?? payload.rows?.length ?? 0,
      missingInvoiceRows: payload.summary?.missing_invoice_rows ?? 0,
      createInvoiceAvailableRows: payload.summary?.create_invoice_available_rows ?? 0,
    },
    tagDictionary: mapBankTransactionTagDictionary(payload.tag_dictionary ?? payload.bank_transaction_tags),
  };
}

function requestBody(payload: ManualPendingInvoiceRequest) {
  return {
    preview_id: payload.previewId,
    request_id: payload.requestId,
    bank_transaction_id: payload.bankTransactionId,
    invoice_no: payload.invoiceNo,
    digital_invoice_no: payload.digitalInvoiceNo,
    invoice_code: payload.invoiceCode,
    issue_date: payload.issueDate,
    total_with_tax: payload.totalWithTax,
    tax_amount: payload.taxAmount,
    tax_rate: payload.taxRate,
    seller_name: payload.sellerName,
    seller_tax_no: payload.sellerTaxNo,
    buyer_name: payload.buyerName,
    buyer_tax_no: payload.buyerTaxNo,
    remark: payload.remark,
  };
}

export async function fetchPendingInvoiceRows(request: FetchPendingInvoiceRowsRequest): Promise<PendingInvoiceRowsResponse> {
  const params = new URLSearchParams();
  params.set("direction", request.direction);
  if (request.direction === "expense" && request.filter && request.filter !== "all") {
    params.set("filter", request.filter);
  } else if (request.direction === "expense" && request.filter === "all") {
    params.set("filter", "all");
  }
  if (request.dateFrom) {
    params.set("date_from", request.dateFrom);
  }
  if (request.dateTo) {
    params.set("date_to", request.dateTo);
  }
  if (request.keyword?.trim()) {
    params.set("keyword", request.keyword.trim());
  }
  if (request.page) {
    params.set("page", String(request.page));
  }
  if (request.pageSize) {
    params.set("page_size", String(request.pageSize));
  }
  const payload = await requestJson<ApiPendingInvoiceRowsResponse>(`/api/pending-invoices/rows?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapRowsResponse(payload, request);
}

export async function previewManualPendingInvoice(request: ManualPendingInvoiceRequest): Promise<ManualPendingInvoicePreview> {
  const payload = await requestJson<ApiManualPendingInvoicePreview>("/api/pending-invoices/manual-invoices/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody(request)),
  });
  const affectedMonths = stringList(payload.relation_impact?.affected_months);
  return {
    previewId: stringValue(payload.preview_id),
    requestKey: stringValue(payload.request_key),
    canConfirm: payload.can_confirm === true,
    targetInvoiceType: stringValue(payload.target_invoice_type) as ManualPendingInvoicePreview["targetInvoiceType"],
    bankTransactionSummary: {
      id: stringValue(payload.bank_transaction_summary?.id),
      direction: stringValue(payload.bank_transaction_summary?.direction) as ManualPendingInvoicePreview["bankTransactionSummary"]["direction"],
      counterpartyName: stringValue(payload.bank_transaction_summary?.counterparty_name),
      tradeTime: stringValue(payload.bank_transaction_summary?.trade_time),
      amount: stringValue(payload.bank_transaction_summary?.amount),
    },
    invoiceIdentity: {
      sourceUniqueKey: stringValue(payload.invoice_identity?.source_unique_key),
      dataFingerprint: stringValue(payload.invoice_identity?.data_fingerprint),
    },
    duplicateCheck: {
      status: stringValue(payload.duplicate_check?.status),
      matchedInvoiceId: payload.duplicate_check?.matched_invoice_id ?? null,
      message: stringValue(payload.duplicate_check?.message),
    },
    relationImpact: {
      relationMode: stringValue(payload.relation_impact?.relation_mode),
      affectedMonths,
    },
    affectedMonths,
    warnings: stringList(payload.warnings),
  };
}

export async function confirmManualPendingInvoice(request: ManualPendingInvoiceRequest): Promise<ManualPendingInvoiceResult> {
  const payload = await requestJson<ApiManualPendingInvoiceResult>("/api/pending-invoices/manual-invoices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody(request)),
  });
  return {
    invoiceId: stringValue(payload.invoice_id),
    relationCaseId: stringValue(payload.relation_case_id),
    affectedTransactionIds: stringList(payload.affected_transaction_ids),
    affectedInvoiceIds: stringList(payload.affected_invoice_ids),
    affectedMonths: stringList(payload.affected_months),
    row: payload.row ? mapPendingInvoiceRow(payload.row) : null,
  };
}
