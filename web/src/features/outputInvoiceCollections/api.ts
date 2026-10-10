import { sourceDetailSections } from "../sourceDetail";
import { readExportCount, validateExportCount, type ExportSummary } from "../exports/types";
import { mapBankSplitParts } from '../bankSplits/api';
import { apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";
import { OUTPUT_COLLECTION_STATUS_CODES } from "./types";
import type {
  OutputInvoiceCollectionDetailResponse,
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionExportDownload,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterOptionsResponse,
  OutputInvoiceCollectionQuery,
  OutputInvoiceCollectionRowsResponse,
  OutputInvoiceCollectionSortDirection,
} from "./types";

type FetchRowsRequest = Pick<
  OutputInvoiceCollectionQuery,
  "page" | "pageSize" | "keyword" | "invoiceDateFrom" | "invoiceDateTo" | "month" | "filters" | "sortField" | "sortDirection"
> & {
  signal?: AbortSignal;
};

function stringValue(value: unknown) {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

function formalRelationStatus(value: unknown): "linked" | "unlinked" {
  return stringValue(value).trim() === "linked" ? "linked" : "unlinked";
}

function booleanValue(value: unknown) {
  return value === true;
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalCount(value: unknown): number | undefined {
  if (value === null || value === undefined || value === "") {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : undefined;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {};
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function camelOrSnake(source: Record<string, unknown>, camel: string, snake: string) {
  return source[camel] ?? source[snake];
}

function encodeFilters(filters: OutputInvoiceCollectionFilter[]) {
  return encodeURIComponent(JSON.stringify(filters));
}

function appendRowsQuery(params: URLSearchParams, request: FetchRowsRequest, includePagination = true) {
  if (includePagination) {
    params.set("page", String(request.page));
    params.set("page_size", String(request.pageSize));
  }
  if (request.keyword.trim()) {
    params.set("keyword", request.keyword.trim());
  }
  if (request.invoiceDateFrom) {
    params.set("invoice_date_from", request.invoiceDateFrom);
  }
  if (request.invoiceDateTo) {
    params.set("invoice_date_to", request.invoiceDateTo);
  }
  if (request.month) {
    params.set("month", request.month);
  }
  if (request.filters.length > 0) {
    params.set("filters", encodeFilters(request.filters));
  }
  if (request.sortField && request.sortDirection) {
    params.set("sort_field", request.sortField);
    params.set("sort_direction", request.sortDirection);
  }
}

function buildRowsQuery(request: FetchRowsRequest, includePagination = true) {
  const params = new URLSearchParams();
  appendRowsQuery(params, request, includePagination);
  return params.toString();
}

function parseContentDispositionFileName(contentDisposition: string | null) {
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

async function requestExportBlob(url: string, init: RequestInit = {}): Promise<OutputInvoiceCollectionExportDownload> {
  const response = await apiFetch(url, init);
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  if (!response.ok) {
    const rawText = await response.text();
    let message = rawText || "导出请求失败";
    try {
      const payload = JSON.parse(rawText) as { error?: { message?: string }; message?: string };
      message = payload.error?.message ?? payload.message ?? message;
    } catch {
      // Keep raw text.
    }
    throw new Error(message);
  }
  if (contentType.toLowerCase().includes("json")) {
    const rawText = await response.text();
    let message = rawText || "导出接口返回了非 xlsx 响应。";
    try {
      const payload = JSON.parse(rawText) as { error?: { message?: string }; message?: string };
      message = payload.error?.message ?? payload.message ?? "导出接口返回了非 xlsx 响应。";
    } catch {
      // Keep raw text.
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
  return {
    blob: await response.blob(),
    fileName: parseContentDispositionFileName(response.headers?.get?.("Content-Disposition") ?? null) ?? "销项发票收款情况.xlsx",
    count: readExportCount(response.headers),
  };
}

function mapInvoice(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["invoice"] {
  const raw = objectValue(rawValue);
  const isPositiveInvoice = stringValue(camelOrSnake(raw, "isPositiveInvoice", "is_positive_invoice")).trim();
  const reversalTargetInvoiceNos = arrayValue(
    camelOrSnake(raw, "reversalTargetInvoiceNos", "reversal_target_invoice_nos"),
  ).map(stringValue).filter(Boolean);
  return {
    id: stringValue(raw.id),
    displayNo: stringValue(camelOrSnake(raw, "displayNo", "display_no") ?? camelOrSnake(raw, "invoiceNo", "invoice_no")),
    invoiceNo: stringValue(camelOrSnake(raw, "invoiceNo", "invoice_no")),
    invoiceCode: stringValue(camelOrSnake(raw, "invoiceCode", "invoice_code")),
    digitalInvoiceNo: stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no")),
    issueDate: stringValue(camelOrSnake(raw, "issueDate", "issue_date") ?? camelOrSnake(raw, "invoiceDate", "invoice_date")),
    buyerName: stringValue(camelOrSnake(raw, "buyerName", "buyer_name")),
    buyerTaxNo: stringValue(camelOrSnake(raw, "buyerTaxNo", "buyer_tax_no")),
    sellerName: stringValue(camelOrSnake(raw, "sellerName", "seller_name")),
    sellerTaxNo: stringValue(camelOrSnake(raw, "sellerTaxNo", "seller_tax_no")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    amountWithoutTax: stringValue(camelOrSnake(raw, "amountWithoutTax", "amount_without_tax") ?? raw.amount),
    taxRate: stringValue(camelOrSnake(raw, "taxRate", "tax_rate")) || "—",
    taxAmount: stringValue(camelOrSnake(raw, "taxAmount", "tax_amount")),
    taxAmountText: stringValue(camelOrSnake(raw, "taxAmountText", "tax_amount_text")),
    specificBusinessType: stringValue(camelOrSnake(raw, "specificBusinessType", "specific_business_type")),
    taxableItemName: stringValue(camelOrSnake(raw, "taxableItemName", "taxable_item_name")),
    reversalTargetInvoiceNos,
    polarity: isPositiveInvoice === "是" ? "blue" : isPositiveInvoice === "否" ? "red" : "unknown",
  };
}

function mapCollectionStatus(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["collectionStatus"] {
  const raw = objectValue(rawValue);
  if (!OUTPUT_COLLECTION_STATUS_CODES.some(code => code === raw.code)
      || typeof raw.label !== "string" || !raw.label.trim()) {
    throw new Error("销项发票状态数据无效，请刷新重试。");
  }
  return {
    code: stringValue(raw.code),
    label: raw.label,
    reason: stringValue(raw.reason),
    collectedAmount: stringValue(camelOrSnake(raw, "collectedAmount", "collected_amount")),
    pendingAmount: stringValue(camelOrSnake(raw, "pendingAmount", "pending_amount")),
  };
}

function mapBank(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["bank"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(raw.id ?? camelOrSnake(raw, "bankTransactionId", "bank_transaction_id") ?? camelOrSnake(raw, "primaryBankTransactionId", "primary_bank_transaction_id"));
  const counterpartyName = stringValue(camelOrSnake(raw, "counterpartyName", "counterparty_name"));
  const tradeTime = stringValue(camelOrSnake(raw, "tradeTime", "trade_time"));
  const amount = stringValue(raw.amount);
  if (!id && !counterpartyName && !tradeTime && !amount) {
    return null;
  }
  return {
    id,
    parentRowId: stringValue(raw.parent_row_id),
    bankSplitParts: mapBankSplitParts(raw.bank_split_parts),
    originalAmount: stringValue(raw.original_amount),
    counterpartyName,
    tradeTime,
    amount,
    direction: stringValue(raw.direction),
    directionLabel: stringValue(camelOrSnake(raw, "directionLabel", "direction_label") ?? raw.direction),
    bankName: stringValue(camelOrSnake(raw, "bankName", "bank_name")),
    bankShortName: stringValue(camelOrSnake(raw, "bankShortName", "bank_short_name")),
    accountLast4: stringValue(camelOrSnake(raw, "accountLast4", "account_last4")),
    summary: stringValue(raw.summary),
    remark: stringValue(raw.remark),
    relationCaseId: stringValue(camelOrSnake(raw, "relationCaseId", "relation_case_id")),
    relationStatus: formalRelationStatus(camelOrSnake(raw, "relationStatus", "relation_status")),
    relationSource: stringValue(camelOrSnake(raw, "relationSource", "relation_source")),
    detailAvailable: id !== "",
  };
}

function mapRelatedInvoice(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["invoiceRelations"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(raw.id ?? camelOrSnake(raw, "invoiceId", "invoice_id") ?? camelOrSnake(raw, "primaryInvoiceId", "primary_invoice_id"));
  const invoiceNo = stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no") ?? camelOrSnake(raw, "invoiceNo", "invoice_no"));
  const totalWithTax = stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax"));
  if (!id && !invoiceNo && !totalWithTax) {
    return null;
  }
  const memberRow = raw.memberRow === undefined ? undefined : objectValue(raw.memberRow);
  return {
    ...mapInvoice(raw), id,
    invoiceDate: stringValue(camelOrSnake(raw, "invoiceDate", "invoice_date")),
    relationId: stringValue(camelOrSnake(raw, "relationId", "relation_id")),
    relationMode: stringValue(camelOrSnake(raw, "relationMode", "relation_mode")),
    relationCaseId: stringValue(camelOrSnake(raw, "relationCaseId", "relation_case_id")),
    relationStatus: formalRelationStatus(camelOrSnake(raw, "relationStatus", "relation_status")),
    relationSource: stringValue(camelOrSnake(raw, "relationSource", "relation_source")),
    memberRow: memberRow ? {
      collectionStatus: mapCollectionStatus(memberRow.collectionStatus),
      bank: mapRelation(memberRow.bankTransactions, mapBank),
    } : undefined,
  };
}

function mapRelation<T>(rawValue: unknown, mapper: (value: unknown) => T | null): {
  originalAmount: string;
  originalTransactionCount: number;
  bankSplitParts: ReturnType<typeof mapBankSplitParts>;
  primary: T | null;
  relationCount: number;
  hasMultiple: boolean;
  receivedTotal?: string;
  totalWithTax?: string;
  detailMode: "none" | "single" | "list";
  summaries: T[];
} {
  const raw = objectValue(rawValue);
  const primary = mapper(raw.primary) ?? mapper(raw);
  const summaries = arrayValue(raw.summaries).map(mapper).filter((item): item is T => Boolean(item));
  const detailMode = stringValue(camelOrSnake(raw, "detailMode", "detail_mode"));
  return {
    primary,
    originalAmount: stringValue(raw.original_amount),
    originalTransactionCount: numberValue(raw.original_transaction_count, 0),
    bankSplitParts: mapBankSplitParts(raw.bank_split_parts),
    relationCount: numberValue(camelOrSnake(raw, "relationCount", "relation_count"), primary ? 1 : 0),
    hasMultiple: booleanValue(camelOrSnake(raw, "hasMultiple", "has_multiple")),
    receivedTotal: stringValue(camelOrSnake(raw, "receivedTotal", "received_total")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    detailMode: detailMode === "list" || detailMode === "single" ? detailMode : primary ? "single" : "none",
    summaries,
  };
}

function mapRowsResponse(payload: unknown): OutputInvoiceCollectionRowsResponse {
  const raw = objectValue(payload);
  const pagination = objectValue(raw.pagination);
  return {
    rows: arrayValue(raw.rows).map((item) => {
      const row = objectValue(item);
      const bank = mapRelation(camelOrSnake(row, "bank", "bankTransactions"), mapBank);
      const invoiceRelations = mapRelation(camelOrSnake(row, "invoiceRelations", "invoice_relations"), mapRelatedInvoice);
      if (invoiceRelations.relationCount > 1 && (invoiceRelations.summaries.length !== invoiceRelations.relationCount
        || new Set(invoiceRelations.summaries.map(member => member.id)).size !== invoiceRelations.relationCount
        || invoiceRelations.summaries.some(member => !member.id || !member.memberRow))) {
        throw new Error('关联发票成员信息不完整，请重新查询。');
      }
      if (bank.originalTransactionCount > 1 && (bank.summaries.some(member => !member.id)
        || new Set(bank.summaries.map(member => member.parentRowId || member.id)).size !== bank.originalTransactionCount)) {
        throw new Error('关联流水成员信息不完整，请重新查询。');
      }
      return {
        id: stringValue(row.id),
        invoiceId: stringValue(camelOrSnake(row, "invoiceId", "invoice_id")),
        invoiceIdentityKey: stringValue(camelOrSnake(row, "invoiceIdentityKey", "invoice_identity_key")),
        invoice: {
          ...mapInvoice(row.invoice),
          id: stringValue(camelOrSnake(row, "invoiceId", "invoice_id") ?? objectValue(row.invoice).id),
        },
        collectionStatus: mapCollectionStatus(camelOrSnake(row, "collectionStatus", "collection_status")),
        bank,
        invoiceRelations,
      };
    }),
    summary: raw.summary && typeof raw.summary === "object" ? (() => {
      const summary = objectValue(raw.summary);
      return {
        invoiceCount: numberValue(camelOrSnake(summary, "invoiceCount", "invoice_count"), 0),
        totalWithTax: stringValue(camelOrSnake(summary, "totalWithTax", "total_with_tax")),
        amountWithoutTax: stringValue(camelOrSnake(summary, "amountWithoutTax", "amount_without_tax")),
        collectedAmount: stringValue(camelOrSnake(summary, "collectedAmount", "collected_amount")),
        pendingAmount: stringValue(camelOrSnake(summary, "pendingAmount", "pending_amount")),
        pendingCollectionCount: numberValue(camelOrSnake(summary, "pendingCollectionCount", "pending_collection_count"), 0),
        partialCollectionCount: numberValue(camelOrSnake(summary, "partialCollectionCount", "partial_collection_count"), 0),
      };
    })() : undefined,
    statistics: raw.statistics && typeof raw.statistics === "object" ? (() => {
      const statistics = objectValue(raw.statistics);
      return {
        invoiceCount: optionalCount(camelOrSnake(statistics, "invoiceCount", "invoice_count")),
        incomeBankTransactionCount: optionalCount(camelOrSnake(statistics, "incomeBankTransactionCount", "income_bank_transaction_count")),
        blueInvoiceCount: optionalCount(camelOrSnake(statistics, "blueInvoiceCount", "blue_invoice_count")),
        redInvoiceCount: optionalCount(camelOrSnake(statistics, "redInvoiceCount", "red_invoice_count")),
      };
    })() : undefined,
    pagination: {
      page: numberValue(pagination.page, 1),
      pageSize: numberValue(camelOrSnake(pagination, "pageSize", "page_size"), 20),
      total: numberValue(pagination.total, 0),
    },
    filterConfig: arrayValue(camelOrSnake(raw, "filterConfig", "filter_config")).map((item) => {
      const config = objectValue(item);
      return {
        field: stringValue(config.field),
        label: stringValue(config.label),
        mode: stringValue(config.mode) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["mode"],
        sortable: booleanValue(config.sortable),
        operators: arrayValue(config.operators).map(stringValue) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["operators"],
      };
    }),
    filterOptions: mapFilterOptionsResponse({
      fields: camelOrSnake(raw, "filterOptions", "filter_options"),
    }).fields,
  };
}

function mapInvoiceDetailResponse(payload: unknown): OutputInvoiceCollectionDetailResponse {
  const raw = objectValue(payload);
  return {title: "发票详情", detailAvailable: raw.detailAvailable !== false,
    sections: raw.detailAvailable === false ? [] : sourceDetailSections(raw.sections)};
}

function mapBankDetailResponse(payload: unknown): OutputInvoiceCollectionDetailResponse {
  const raw = objectValue(payload);
  return {title: "银行流水详情", detailAvailable: raw.detailAvailable !== false,
    sections: raw.detailAvailable === false ? [] : sourceDetailSections(raw.sections)};
}

function mapFilterOptionsResponse(payload: unknown): OutputInvoiceCollectionFilterOptionsResponse {
  const raw = objectValue(payload);
  const rawFields = arrayValue(raw.fields);
  const statusFields = rawFields.map(objectValue).filter(field => field.field === "collection_status");
  const statusOptions = arrayValue(statusFields[0]?.options).map(objectValue);
  if (statusFields.length !== 1 || statusOptions.length !== OUTPUT_COLLECTION_STATUS_CODES.length
      || OUTPUT_COLLECTION_STATUS_CODES.some(code => statusOptions.filter(option => option.value === code).length !== 1)
      || statusOptions.some(option => typeof option.label !== "string" || !option.label.trim()
        || typeof option.count !== "number" || !Number.isSafeInteger(option.count) || option.count < 0)) {
    throw new Error("销项发票分类统计不完整或无效，请刷新重试。");
  }
  return {
    fields: rawFields.map((item) => {
      const field = objectValue(item);
      return {
        field: stringValue(field.field),
        label: stringValue(field.label),
        mode: stringValue(field.mode) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["mode"],
        sortable: booleanValue(field.sortable),
        operators: arrayValue(field.operators).map(stringValue) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["operators"],
        options: (field.field === "collection_status"
          ? OUTPUT_COLLECTION_STATUS_CODES.map(code => statusOptions.find(option => option.value === code)!)
          : arrayValue(field.options)).map((option) => {
          const rawOption = objectValue(option);
          return {
            value: stringValue(rawOption.value),
            label: stringValue(rawOption.label),
            count: field.field === "collection_status" ? rawOption.count as number
              : rawOption.count === undefined ? undefined : numberValue(rawOption.count, 0),
          };
        }),
      };
    }),
  };
}

export async function fetchOutputInvoiceCollectionRows(request: FetchRowsRequest): Promise<OutputInvoiceCollectionRowsResponse> {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/rows?${buildRowsQuery(request)}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapRowsResponse(payload);
}

export async function fetchOutputInvoiceCollectionExportSummary(query: FetchRowsRequest, signal: AbortSignal): Promise<ExportSummary> {
  const raw = await apiRequestJson<{ row_count: number }>(`/api/output-invoice-collections/export-summary?${buildRowsQuery(query, false)}`, { method: "GET", signal });
  return { rowCount: validateExportCount(raw.row_count) };
}

export async function downloadOutputInvoiceCollectionExport(request: FetchRowsRequest): Promise<OutputInvoiceCollectionExportDownload> {
  return requestExportBlob(`/api/output-invoice-collections/export?${buildRowsQuery(request, false)}`, {
    method: "GET",
    signal: request.signal,
  });
}

export async function fetchOutputInvoiceCollectionInvoiceDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/invoices/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapInvoiceDetailResponse(payload);
}

export async function fetchOutputInvoiceCollectionOaDetail(id: string, signal?: AbortSignal): Promise<OutputInvoiceCollectionDetailResponse> {
  const raw = await apiRequestJson<{sections: unknown}>(`/api/output-invoice-collections/oa/${encodeURIComponent(id)}/detail`, { signal });
  return { title: 'OA详情', sections: sourceDetailSections(raw.sections) };
}

export async function fetchOutputInvoiceCollectionBankTransactionDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/bank-transactions/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapBankDetailResponse(payload);
}


export function nextSortDirection(
  currentField: string,
  currentDirection: OutputInvoiceCollectionSortDirection | "",
  field: string,
) {
  if (currentField !== field || !currentDirection) {
    return "asc";
  }
  return currentDirection === "asc" ? "desc" : "asc";
}
