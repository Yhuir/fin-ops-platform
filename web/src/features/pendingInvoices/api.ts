import type {
  AttachExistingInvoiceConfirmRequest,
  AttachExistingInvoicePreview,
  AttachExistingInvoicePreviewRequest,
  AttachExistingInvoiceResult,
  BankTransactionTagDefinition,
  BankTransactionTagDictionary,
  FetchPendingInvoiceCandidatesRequest,
  FetchPendingInvoiceRowsRequest,
  ManualPendingInvoicePreview,
  ManualPendingInvoiceRequest,
  ManualPendingInvoiceResult,
  PendingInvoiceBankTransaction,
  PendingInvoiceCandidate,
  PendingInvoiceCandidatesResponse,
  PendingInvoiceDetailSection,
  PendingInvoiceDirection,
  PendingInvoiceExportDownload,
  PendingInvoiceExportPreview,
  PendingInvoiceFilter,
  PendingInvoiceFilterOptionsResponse,
  PendingInvoiceObjectDetail,
  PendingInvoiceObjectDetailTarget,
  PendingInvoiceOaSummary,
  PendingInvoiceRelationDetail,
  PendingInvoiceRuleGroup,
  PendingInvoiceRulesPayload,
  PendingInvoiceRow,
  PendingInvoiceRowsResponse,
  PendingInvoiceSummary,
} from "./types";
import { apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";

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

type ApiInvoiceSummary = Partial<{
  id: string | null;
  invoice_id: string | null;
  invoice_no: string | null;
  digital_invoice_no: string | null;
  invoice_code: string | null;
  issue_date: string | null;
  total_with_tax: string | null;
  seller_name: string | null;
  seller_tax_no: string | null;
  buyer_name: string | null;
  invoice_type: string | null;
}>;

type ApiOaSummary = Partial<{
  id: string | null;
  applicant: string | null;
  application_type: string | null;
  project_name: string | null;
  status: string | null;
}>;

type ApiPendingInvoiceRow = {
  id?: string | null;
  bank_transaction?: Partial<{
    id: string | null;
    counterparty_name: string | null;
    counterparty_account_no: string | null;
    counterparty_bank_name: string | null;
    trade_time: string | null;
    booked_date: string | null;
    debit_amount: string | null;
    credit_amount: string | null;
    amount: string | null;
    balance: string | null;
    currency: string | null;
    bank_name: string | null;
    account_name: string | null;
    account_last4: string | null;
    summary: string | null;
    remark: string | null;
    statement_serial_no: string | null;
    enterprise_serial_no: string | null;
    voucher_type: string | null;
    voucher_no: string | null;
    effective_tag_code: string | null;
    effective_tag_label: string | null;
  }> | null;
  invoice_acquisition_status?: Partial<{
    code: string | null;
    label: string | null;
    reason: string | null;
    severity: string | null;
    primary_action: string | null;
    matched_rule: Partial<{
      source: string | null;
      group: string | null;
      tag_code: string | null;
      tag_label: string | null;
    }> | null;
  }> | null;
  input_invoices?: Partial<{
    primary: ApiInvoiceSummary | null;
    relation_count: number | null;
    has_multiple: boolean | null;
    summaries: ApiInvoiceSummary[] | null;
    payment_summary: Partial<{
      paid_total: string | null;
      invoice_total: string | null;
      remaining_amount: string | null;
      difference_amount: string | null;
    }> | null;
  }> | null;
  oa?: Partial<{
    primary: ApiOaSummary | null;
    relation_count: number | null;
    has_multiple: boolean | null;
    detail_available: boolean | null;
    summaries: ApiOaSummary[] | null;
  }> | null;
  invoices?: ApiInvoiceSummary[] | null;
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
  read_model_status?: string | null;
  tag_dictionary?: ApiTagDictionary | null;
  bank_transaction_tags?: ApiTagDictionary | null;
};

type ApiPendingInvoiceRulesPayload = {
  version?: number | string | null;
  permissions?: { can_save?: boolean | null } | null;
  bank_transaction_tags?: ApiTagDictionary | null;
  groups?: Partial<Record<"requires_invoice" | "bank_statement_as_invoice" | "no_invoice_required", {
    tag_codes?: unknown[] | null;
    tags?: Array<Partial<{ code: string | null; label: string | null; status: string | null }>> | null;
  }>> | null;
  requires_invoice?: unknown[] | null;
  bank_statement_as_invoice?: unknown[] | null;
  no_invoice_required?: unknown[] | null;
};

type ApiRelationDetail = {
  transaction_summary?: Partial<{
    id: string | null;
    counterparty_name: string | null;
    trade_time: string | null;
    debit_amount: string | null;
    amount: string | null;
  }> | null;
  related_invoices?: ApiInvoiceSummary[] | null;
  payment_rows?: Array<Partial<{
    id: string | null;
    trade_time: string | null;
    counterparty_name: string | null;
    debit_amount: string | null;
    amount: string | null;
    relation_case_id: string | null;
  }>> | null;
  paid_total?: string | null;
  invoice_total?: string | null;
  remaining_amount?: string | null;
  difference_amount?: string | null;
  available_actions?: unknown[] | null;
};

type ApiDetailPayload = {
  title?: string | null;
  subtitle?: string | null;
  detail_available?: boolean | null;
  unavailable_reason?: string | null;
  sections?: Array<{
    title?: string | null;
    fields?: Array<{ label?: string | null; value?: string | number | null }> | null;
  }> | null;
} & Record<string, unknown>;

type ApiCandidatesResponse = {
  rows?: Array<ApiInvoiceSummary & Partial<{
    invoice_id: string | null;
    related_paid_total: string | null;
    remaining_amount: string | null;
    amount_difference_abs: string | null;
    candidate_status: string | null;
    conflict_reason: string | null;
  }>> | null;
  pagination?: {
    page?: number | null;
    page_size?: number | null;
    total?: number | null;
  } | null;
};

type ApiAttachPreview = {
  preview_id?: string | null;
  request_key?: string | null;
  can_confirm?: boolean | null;
  transaction_summary?: ApiRelationDetail["transaction_summary"];
  invoice_summary?: ApiInvoiceSummary | null;
  payment_impact?: Partial<{
    paid_total_before: string | null;
    paid_total_after: string | null;
    invoice_total: string | null;
    remaining_amount_after: string | null;
    difference_amount_after: string | null;
  }> | null;
  affected_months?: unknown[] | null;
  warnings?: unknown[] | null;
  conflicts?: unknown[] | null;
  expires_at?: string | null;
};

type ApiAttachResult = {
  status?: string | null;
  request_id?: string | null;
  request_key?: string | null;
  transaction_id?: string | null;
  invoice_id?: string | null;
  relation_case_id?: string | null;
  relation_mode?: string | null;
  affected_transaction_ids?: unknown[] | null;
  affected_invoice_ids?: unknown[] | null;
  affected_months?: unknown[] | null;
  row?: ApiPendingInvoiceRow | null;
};

type ApiExportPreview = {
  file_name?: string | null;
  row_count?: number | string | null;
  scope_label?: string | null;
  columns?: unknown[] | null;
  sample_rows?: Array<Record<string, unknown>> | null;
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

function numberValue(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : [];
}

function objectStringMap(value: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [snakeToCamel(key), item === null || item === undefined ? "" : String(item)]));
}

function snakeToCamel(value: string) {
  return value.replace(/_([a-z])/g, (_match, letter: string) => letter.toUpperCase());
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
  const debitAmount = stringValue(value?.debit_amount, stringValue(value?.amount));
  return {
    id: stringValue(value?.id, fallbackId),
    counterpartyName: stringValue(value?.counterparty_name, "—"),
    counterpartyAccountNo: stringValue(value?.counterparty_account_no),
    counterpartyBankName: stringValue(value?.counterparty_bank_name),
    tradeTime: stringValue(value?.trade_time),
    bookedDate: stringValue(value?.booked_date),
    debitAmount,
    creditAmount: stringValue(value?.credit_amount),
    amount: debitAmount,
    balance: stringValue(value?.balance),
    currency: stringValue(value?.currency),
    bankName: stringValue(value?.bank_name),
    accountName: stringValue(value?.account_name),
    accountLast4: stringValue(value?.account_last4),
    summary: stringValue(value?.summary),
    remark: stringValue(value?.remark),
    statementSerialNo: stringValue(value?.statement_serial_no),
    enterpriseSerialNo: stringValue(value?.enterprise_serial_no),
    voucherType: stringValue(value?.voucher_type),
    voucherNo: stringValue(value?.voucher_no),
    effectiveTagCode: value?.effective_tag_code ?? null,
    effectiveTagLabel: value?.effective_tag_label ?? null,
  };
}

function mapInvoice(value: ApiInvoiceSummary | null | undefined): PendingInvoiceSummary {
  const id = stringValue(value?.id, stringValue(value?.invoice_id));
  return {
    id,
    invoiceNo: stringValue(value?.invoice_no),
    digitalInvoiceNo: stringValue(value?.digital_invoice_no),
    invoiceCode: stringValue(value?.invoice_code),
    issueDate: stringValue(value?.issue_date),
    totalWithTax: stringValue(value?.total_with_tax),
    sellerName: stringValue(value?.seller_name),
    sellerTaxNo: stringValue(value?.seller_tax_no),
    buyerName: stringValue(value?.buyer_name),
    invoiceType: stringValue(value?.invoice_type, "input") as PendingInvoiceSummary["invoiceType"],
  };
}

function hasInvoiceIdentity(invoice: PendingInvoiceSummary) {
  return Boolean(invoice.id || invoice.invoiceNo || invoice.digitalInvoiceNo);
}

function mapOa(value: ApiOaSummary | null | undefined): PendingInvoiceOaSummary {
  return {
    id: stringValue(value?.id),
    applicant: stringValue(value?.applicant),
    applicationType: stringValue(value?.application_type),
    projectName: stringValue(value?.project_name),
    status: stringValue(value?.status),
  };
}

function statusLabel(code: string) {
  const labels: Record<string, string> = {
    paid_invoiced: "已支付已开票",
    paid_pending_invoice: "已支付待开票",
    paid_pending_future_invoice: "已支付待后期集中开票",
    invoice_not_fully_paid: "未支付完已开票",
    no_invoice_required: "无需开票",
    bank_statement_as_invoice: "流水代替发票",
    pending: "待处理",
  };
  return labels[code] ?? code;
}

export function mapPendingInvoiceRow(row: ApiPendingInvoiceRow): PendingInvoiceRow {
  const id = stringValue(row.id, stringValue(row.bank_transaction?.id));
  const legacyInvoices = (row.invoices ?? []).map(mapInvoice).filter(hasInvoiceIdentity);
  const inputSummaries = (row.input_invoices?.summaries ?? []).map(mapInvoice).filter(hasInvoiceIdentity);
  const primaryInvoice = mapInvoice(row.input_invoices?.primary ?? legacyInvoices[0] ?? null);
  const invoices = inputSummaries.length > 0 ? inputSummaries : legacyInvoices;
  const statusCode = stringValue(row.invoice_acquisition_status?.code, legacyInvoices.length > 0 ? "paid_invoiced" : "pending");
  const matchedRule = row.invoice_acquisition_status?.matched_rule;
  const oaPrimary = row.oa?.primary ? mapOa(row.oa.primary) : (
    row.oa_applicant ? { id: "", applicant: row.oa_applicant, applicationType: "", projectName: "", status: "" } : null
  );
  return {
    id,
    bankTransaction: mapBankTransaction(row.bank_transaction, id),
    invoiceAcquisitionStatus: Object.freeze({
      code: statusCode as PendingInvoiceRow["invoiceAcquisitionStatus"]["code"],
      label: stringValue(row.invoice_acquisition_status?.label, statusLabel(statusCode)),
      reason: stringValue(row.invoice_acquisition_status?.reason),
      severity: stringValue(row.invoice_acquisition_status?.severity, "default") as PendingInvoiceRow["invoiceAcquisitionStatus"]["severity"],
      primaryAction: stringValue(row.invoice_acquisition_status?.primary_action, row.can_create_invoice ? "manual_invoice" : "none") as PendingInvoiceRow["invoiceAcquisitionStatus"]["primaryAction"],
      matchedRule: matchedRule ? {
        source: stringValue(matchedRule.source),
        group: stringValue(matchedRule.group) as NonNullable<PendingInvoiceRow["invoiceAcquisitionStatus"]["matchedRule"]>["group"],
        tagCode: stringValue(matchedRule.tag_code),
        tagLabel: stringValue(matchedRule.tag_label),
      } : null,
    }),
    inputInvoices: {
      primary: hasInvoiceIdentity(primaryInvoice) ? primaryInvoice : null,
      relationCount: numberValue(row.input_invoices?.relation_count, invoices.length),
      hasMultiple: row.input_invoices?.has_multiple === true || invoices.length > 1,
      summaries: invoices,
      paymentSummary: row.input_invoices?.payment_summary ? {
        paidTotal: stringValue(row.input_invoices.payment_summary.paid_total),
        invoiceTotal: stringValue(row.input_invoices.payment_summary.invoice_total),
        remainingAmount: stringValue(row.input_invoices.payment_summary.remaining_amount),
        differenceAmount: stringValue(row.input_invoices.payment_summary.difference_amount),
      } : null,
    },
    oa: {
      primary: oaPrimary,
      relationCount: numberValue(row.oa?.relation_count, oaPrimary ? 1 : 0),
      hasMultiple: row.oa?.has_multiple === true,
      detailAvailable: row.oa?.detail_available !== false,
      summaries: (row.oa?.summaries ?? []).map(mapOa).filter((item) => item.id || item.applicant),
    },
    invoices,
    oaApplicant: oaPrimary?.applicant || null,
    canCreateInvoice: row.can_create_invoice === true || ["attach_or_create_invoice", "manual_invoice"].includes(stringValue(row.invoice_acquisition_status?.primary_action)),
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
    readModelStatus: stringValue(payload.read_model_status, "fresh") as PendingInvoiceRowsResponse["readModelStatus"],
    tagDictionary: mapBankTransactionTagDictionary(payload.tag_dictionary ?? payload.bank_transaction_tags),
  };
}

function appendRowsQuery(params: URLSearchParams, request: FetchPendingInvoiceRowsRequest, includePagination: boolean) {
  params.set("direction", request.direction);
  if (request.direction === "expense" && request.filter) {
    params.set("filter", request.filter);
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
  if (includePagination && request.page) {
    params.set("page", String(request.page));
  }
  if (includePagination && request.pageSize) {
    params.set("page_size", String(request.pageSize));
  }
  if (request.filters?.length) {
    params.set("filters", JSON.stringify(request.filters));
  }
  if (request.sortField) {
    params.set("sort_field", request.sortField);
  }
  if (request.sortDirection) {
    params.set("sort_direction", request.sortDirection);
  }
}

function buildRowsQuery(request: FetchPendingInvoiceRowsRequest, includePagination = true) {
  const params = new URLSearchParams();
  appendRowsQuery(params, request, includePagination);
  return params.toString();
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
  const payload = await requestJson<ApiPendingInvoiceRowsResponse>(`/api/pending-invoices/rows?${buildRowsQuery(request)}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapRowsResponse(payload, request);
}

export async function fetchPendingInvoiceFilterOptions(request: FetchPendingInvoiceRowsRequest): Promise<PendingInvoiceFilterOptionsResponse> {
  const payload = await requestJson<{
    fields?: Array<{ field?: string; label?: string; operators?: unknown[]; options?: Array<{ value?: string; label?: string; count?: number }> }>;
    options?: Record<string, Array<{ value?: string; label?: string; count?: number }>>;
  }>(
    `/api/pending-invoices/filter-options?${buildRowsQuery(request, false)}`,
    { method: "GET", signal: request.signal },
  );
  return {
    fields: (payload.fields ?? []).map((field) => {
      const fieldName = stringValue(field.field);
      const options = field.options ?? payload.options?.[fieldName] ?? [];
      return {
        field: fieldName,
        label: stringValue(field.label, fieldName),
        operators: stringList(field.operators),
        options: options.map((option) => ({
          value: stringValue(option.value),
          label: stringValue(option.label, stringValue(option.value)),
          count: numberValue(option.count),
        })),
      };
    }),
  };
}

const RULE_LABELS = {
  requires_invoice: "需要开票",
  bank_statement_as_invoice: "流水代替发票",
  no_invoice_required: "无需开票",
} as const;

function mapRuleGroup(payload: ApiPendingInvoiceRulesPayload, code: keyof typeof RULE_LABELS): PendingInvoiceRuleGroup {
  const group = payload.groups?.[code];
  const tagCodes = stringList(group?.tag_codes ?? payload[code]);
  const tags = (group?.tags ?? []).map((tag) => ({
    code: stringValue(tag.code),
    label: stringValue(tag.label, stringValue(tag.code)),
    status: stringValue(tag.status, "active") as PendingInvoiceRuleGroup["tags"][number]["status"],
  })).filter((tag) => tag.code);
  return {
    code,
    label: RULE_LABELS[code],
    tagCodes: tagCodes.length > 0 ? tagCodes : tags.map((tag) => tag.code),
    tags,
  };
}

function mapRulesPayload(payload: ApiPendingInvoiceRulesPayload): PendingInvoiceRulesPayload {
  const availableTags = (payload.bank_transaction_tags?.tags ?? payload.bank_transaction_tags?.definitions ?? [])
    .map((tag) => ({
      code: stringValue(tag.code),
      label: stringValue(tag.label, stringValue(tag.code)),
      status: stringValue(tag.status, "active") as PendingInvoiceRuleGroup["tags"][number]["status"],
    }))
    .filter((tag) => tag.code && tag.status !== "archived");
  return {
    version: numberValue(payload.version),
    availableTags,
    groups: {
      requiresInvoice: mapRuleGroup(payload, "requires_invoice"),
      bankStatementAsInvoice: mapRuleGroup(payload, "bank_statement_as_invoice"),
      noInvoiceRequired: mapRuleGroup(payload, "no_invoice_required"),
    },
    permissions: {
      canSave: payload.permissions?.can_save !== false,
    },
  };
}

function rulesRequestBody(payload: PendingInvoiceRulesPayload) {
  return {
    groups: {
      requires_invoice: { tag_codes: payload.groups.requiresInvoice.tagCodes },
      bank_statement_as_invoice: { tag_codes: payload.groups.bankStatementAsInvoice.tagCodes },
      no_invoice_required: { tag_codes: payload.groups.noInvoiceRequired.tagCodes },
    },
  };
}

export async function fetchPendingInvoiceRules(signal?: AbortSignal): Promise<PendingInvoiceRulesPayload> {
  const payload = await requestJson<ApiPendingInvoiceRulesPayload>("/api/pending-invoices/rules", { method: "GET", signal });
  return mapRulesPayload(payload);
}

export async function savePendingInvoiceRules(payload: PendingInvoiceRulesPayload, signal?: AbortSignal): Promise<PendingInvoiceRulesPayload> {
  const response = await requestJson<ApiPendingInvoiceRulesPayload>("/api/pending-invoices/rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rulesRequestBody(payload)),
    signal,
  });
  return mapRulesPayload(response);
}

function mapRelationDetail(payload: ApiRelationDetail): PendingInvoiceRelationDetail {
  return {
    transactionSummary: {
      id: stringValue(payload.transaction_summary?.id),
      counterpartyName: stringValue(payload.transaction_summary?.counterparty_name),
      tradeTime: stringValue(payload.transaction_summary?.trade_time),
      debitAmount: stringValue(payload.transaction_summary?.debit_amount, stringValue(payload.transaction_summary?.amount)),
    },
    relatedInvoices: (payload.related_invoices ?? []).map(mapInvoice).filter(hasInvoiceIdentity),
    paymentRows: (payload.payment_rows ?? []).map((row) => ({
      id: stringValue(row.id),
      tradeTime: stringValue(row.trade_time),
      counterpartyName: stringValue(row.counterparty_name),
      debitAmount: stringValue(row.debit_amount, stringValue(row.amount)),
      relationCaseId: stringValue(row.relation_case_id),
    })),
    paidTotal: stringValue(payload.paid_total),
    invoiceTotal: stringValue(payload.invoice_total),
    remainingAmount: stringValue(payload.remaining_amount),
    differenceAmount: stringValue(payload.difference_amount),
    availableActions: stringList(payload.available_actions),
  };
}

export async function fetchPendingInvoiceRelationDetail(transactionId: string, signal?: AbortSignal): Promise<PendingInvoiceRelationDetail> {
  const payload = await requestJson<ApiRelationDetail>(
    `/api/pending-invoices/rows/${encodeURIComponent(transactionId)}/relation-detail`,
    { method: "GET", signal },
  );
  return mapRelationDetail(payload);
}

function detailPath(target: PendingInvoiceObjectDetailTarget) {
  if (target.kind === "bankTransaction") {
    return `/api/pending-invoices/bank-transactions/${encodeURIComponent(target.id)}/detail`;
  }
  if (target.kind === "invoice") {
    return `/api/pending-invoices/invoices/${encodeURIComponent(target.id)}/detail`;
  }
  return `/api/pending-invoices/oa/${encodeURIComponent(target.id)}/detail`;
}

function mapDetail(payload: ApiDetailPayload, target: PendingInvoiceObjectDetailTarget): PendingInvoiceObjectDetail {
  const sections: PendingInvoiceDetailSection[] = (payload.sections ?? []).map((section) => ({
    title: stringValue(section.title, "详情"),
    fields: (section.fields ?? []).map((field) => ({
      label: stringValue(field.label),
      value: field.value,
    })).filter((field) => field.label),
  }));
  if (sections.length === 0) {
    const fields = Object.entries(payload)
      .filter(([key, value]) => !["title", "subtitle", "detail_available", "unavailable_reason", "sections"].includes(key) && ["string", "number", "boolean"].includes(typeof value))
      .map(([key, value]) => ({ label: key, value: String(value) }));
    if (fields.length > 0) {
      sections.push({ title: "详情字段", fields });
    }
  }
  return {
    title: stringValue(payload.title, target.id),
    subtitle: stringValue(payload.subtitle),
    detailAvailable: payload.detail_available !== false,
    unavailableReason: stringValue(payload.unavailable_reason),
    sections,
  };
}

export async function fetchPendingInvoiceObjectDetail(target: PendingInvoiceObjectDetailTarget, signal?: AbortSignal): Promise<PendingInvoiceObjectDetail> {
  const payload = await requestJson<ApiDetailPayload>(detailPath(target), { method: "GET", signal });
  return mapDetail(payload, target);
}

export async function fetchPendingInvoiceCandidates(request: FetchPendingInvoiceCandidatesRequest): Promise<PendingInvoiceCandidatesResponse> {
  const params = new URLSearchParams();
  params.set("transaction_id", request.transactionId);
  if (request.keyword?.trim()) {
    params.set("keyword", request.keyword.trim());
  }
  if (request.sellerName?.trim()) {
    params.set("seller_name", request.sellerName.trim());
  }
  if (request.issueDateFrom) {
    params.set("issue_date_from", request.issueDateFrom);
  }
  if (request.issueDateTo) {
    params.set("issue_date_to", request.issueDateTo);
  }
  if (request.amountMin) {
    params.set("amount_min", request.amountMin);
  }
  if (request.amountMax) {
    params.set("amount_max", request.amountMax);
  }
  if (request.sortField) {
    params.set("sort_field", request.sortField);
  }
  if (request.sortDirection) {
    params.set("sort_direction", request.sortDirection);
  }
  if (request.page) {
    params.set("page", String(request.page));
  }
  if (request.pageSize) {
    params.set("page_size", String(request.pageSize));
  }
  const payload = await requestJson<ApiCandidatesResponse>(`/api/pending-invoices/invoice-candidates?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
  return {
    rows: (payload.rows ?? []).map((row): PendingInvoiceCandidate => {
      const invoice = mapInvoice(row);
      const invoiceId = stringValue(row.invoice_id, invoice.id);
      return {
        ...invoice,
        id: invoice.id || invoiceId,
        invoiceId,
        relatedPaidTotal: stringValue(row.related_paid_total),
        remainingAmount: stringValue(row.remaining_amount),
        amountDifferenceAbs: stringValue(row.amount_difference_abs),
        candidateStatus: stringValue(row.candidate_status, "available") as PendingInvoiceCandidate["candidateStatus"],
        conflictReason: stringValue(row.conflict_reason),
      };
    }),
    pagination: {
      page: payload.pagination?.page ?? request.page ?? 1,
      pageSize: payload.pagination?.page_size ?? request.pageSize ?? 20,
      total: payload.pagination?.total ?? payload.rows?.length ?? 0,
    },
  };
}

export async function previewAttachExistingInvoice(request: AttachExistingInvoicePreviewRequest): Promise<AttachExistingInvoicePreview> {
  const payload = await requestJson<ApiAttachPreview>(
    `/api/pending-invoices/rows/${encodeURIComponent(request.transactionId)}/attach-existing-invoice/preview`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ invoice_id: request.invoiceId, request_id: request.requestId }),
    },
  );
  return {
    previewId: stringValue(payload.preview_id),
    requestKey: stringValue(payload.request_key),
    canConfirm: payload.can_confirm === true,
    transactionSummary: mapRelationDetail({ transaction_summary: payload.transaction_summary }).transactionSummary,
    invoiceSummary: mapInvoice(payload.invoice_summary),
    paymentImpact: {
      paidTotalBefore: stringValue(payload.payment_impact?.paid_total_before),
      paidTotalAfter: stringValue(payload.payment_impact?.paid_total_after),
      invoiceTotal: stringValue(payload.payment_impact?.invoice_total),
      remainingAmountAfter: stringValue(payload.payment_impact?.remaining_amount_after),
      differenceAmountAfter: stringValue(payload.payment_impact?.difference_amount_after),
    },
    affectedMonths: stringList(payload.affected_months),
    warnings: stringList(payload.warnings),
    conflicts: stringList(payload.conflicts),
    expiresAt: stringValue(payload.expires_at),
  };
}

export async function confirmAttachExistingInvoice(request: AttachExistingInvoiceConfirmRequest): Promise<AttachExistingInvoiceResult> {
  const payload = await requestJson<ApiAttachResult>(
    `/api/pending-invoices/rows/${encodeURIComponent(request.transactionId)}/attach-existing-invoice`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preview_id: request.previewId, invoice_id: request.invoiceId, request_id: request.requestId }),
    },
  );
  return {
    status: stringValue(payload.status),
    requestId: stringValue(payload.request_id),
    requestKey: stringValue(payload.request_key),
    transactionId: stringValue(payload.transaction_id),
    invoiceId: stringValue(payload.invoice_id),
    relationCaseId: stringValue(payload.relation_case_id),
    relationMode: stringValue(payload.relation_mode),
    affectedTransactionIds: stringList(payload.affected_transaction_ids),
    affectedInvoiceIds: stringList(payload.affected_invoice_ids),
    affectedMonths: stringList(payload.affected_months),
    row: payload.row ? mapPendingInvoiceRow(payload.row) : null,
  };
}

export async function fetchPendingInvoiceExportPreview(request: FetchPendingInvoiceRowsRequest): Promise<PendingInvoiceExportPreview> {
  const payload = await requestJson<ApiExportPreview>(`/api/pending-invoices/export-preview?${buildRowsQuery(request, false)}`, {
    method: "GET",
    signal: request.signal,
  });
  return {
    fileName: stringValue(payload.file_name, "待找发票.xlsx"),
    rowCount: numberValue(payload.row_count),
    scopeLabel: stringValue(payload.scope_label),
    columns: stringList(payload.columns),
    sampleRows: (payload.sample_rows ?? []).map(objectStringMap),
  };
}

function parseContentDispositionFileName(contentDisposition: string | null): string | null {
  if (!contentDisposition) {
    return null;
  }
  const encodedMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (encodedMatch?.[1]) {
    try {
      return decodeURIComponent(encodedMatch[1]);
    } catch {
      return encodedMatch[1];
    }
  }
  const quotedMatch = contentDisposition.match(/filename="([^"]+)"/i);
  if (quotedMatch?.[1]) {
    return quotedMatch[1];
  }
  const plainMatch = contentDisposition.match(/filename=([^;]+)/i);
  return plainMatch?.[1]?.trim() ?? null;
}

async function requestBlob(url: string, init: RequestInit = {}): Promise<PendingInvoiceExportDownload> {
  const response = await apiFetch(url, init);
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  if (!response.ok) {
    const rawText = await response.text();
    let message = rawText || "request failed";
    try {
      const payload = JSON.parse(rawText) as { error?: { message?: string }; message?: string };
      message = payload.error?.message ?? payload.message ?? message;
    } catch {
      // Keep the raw text.
    }
    throw new Error(message);
  }
  if (contentType.toLowerCase().includes("text/html")) {
    const rawText = await response.text();
    if (looksLikeHtmlResponse(rawText, contentType)) {
      throw new Error(`接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务和代理路径已正常配置。`);
    }
    throw new Error(rawText || `接口 ${url} 返回的不是 xlsx 文件：${contentType}`);
  }
  const blob = await response.blob();
  return {
    blob,
    fileName: parseContentDispositionFileName(response.headers?.get?.("Content-Disposition") ?? null) ?? "待找发票.xlsx",
  };
}

export async function downloadPendingInvoiceExport(request: FetchPendingInvoiceRowsRequest): Promise<PendingInvoiceExportDownload> {
  return requestBlob(`/api/pending-invoices/export?${buildRowsQuery(request, false)}`, {
    method: "GET",
    signal: request.signal,
  });
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
