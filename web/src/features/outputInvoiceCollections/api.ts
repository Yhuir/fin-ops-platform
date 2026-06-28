import { apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";
import type {
  OutputInvoiceCollectionDetailResponse,
  OutputInvoiceCollectionDetailTarget,
  OutputInvoiceCollectionExportDownload,
  OutputInvoiceCollectionExportPreview,
  OutputInvoiceCollectionFilter,
  OutputInvoiceCollectionFilterOptionsResponse,
  OutputInvoiceCollectionMutationResponse,
  OutputInvoiceCollectionQuery,
  OutputInvoiceCollectionRedRelationRequest,
  OutputInvoiceCollectionRowsResponse,
  OutputInvoiceCollectionSortDirection,
  OutputInvoiceCollectionReminderUpdateRequest,
  OutputInvoiceCollectionStatusUpdateRequest,
  OutputInvoiceCollectionStatusRulesResponse,
  OutputInvoiceReceiptCreateRequest,
  OutputInvoiceReceiptHistoryResponse,
  OutputInvoiceReceiptPreviewRequest,
  OutputInvoiceReceiptPreviewResponse,
  OutputInvoiceReceiptSettingsResponse,
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

function booleanValue(value: unknown) {
  return value === true;
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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

function objectStringMap(value: unknown): Record<string, string> {
  const raw = objectValue(value);
  return Object.fromEntries(Object.entries(raw).map(([key, item]) => [key, stringValue(item)]));
}

function stringList(value: unknown): string[] {
  return arrayValue(value).map((item) => stringValue(item).trim()).filter(Boolean);
}

function mapMutationResponse(payload: unknown): OutputInvoiceCollectionMutationResponse {
  return {
    raw: payload,
  };
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
  if (!response.ok || response.status === 202) {
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
      message = payload.error?.message ?? payload.message ?? "导出数据暂不可用，请稍后再试。";
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
  };
}

function mapInvoice(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["invoice"] {
  const raw = objectValue(rawValue);
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
    taxRate: stringValue(camelOrSnake(raw, "taxRate", "tax_rate")),
    taxAmount: stringValue(camelOrSnake(raw, "taxAmount", "tax_amount")),
    specificBusinessType: stringValue(camelOrSnake(raw, "specificBusinessType", "specific_business_type")),
    taxableItemName: stringValue(camelOrSnake(raw, "taxableItemName", "taxable_item_name")),
  };
}

function mapCollectionStatus(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["collectionStatus"] {
  const raw = objectValue(rawValue);
  const manualOverride = objectValue(camelOrSnake(raw, "manualOverride", "manual_override"));
  const reminder = objectValue(raw.reminder);
  return {
    code: stringValue(raw.code),
    label: stringValue(raw.label),
    reason: stringValue(raw.reason),
    collectedAmount: stringValue(camelOrSnake(raw, "collectedAmount", "collected_amount")),
    pendingAmount: stringValue(camelOrSnake(raw, "pendingAmount", "pending_amount")),
    severity: stringValue(raw.severity),
    matchedRuleId: stringValue(camelOrSnake(raw, "matchedRuleId", "matched_rule_id")),
    manualOverride: Object.keys(manualOverride).length > 0 ? {
      id: stringValue(manualOverride.id),
      statusCode: stringValue(camelOrSnake(manualOverride, "statusCode", "status_code")),
      expectedCollectionDate: stringValue(camelOrSnake(manualOverride, "expectedCollectionDate", "expected_collection_date")),
      note: stringValue(manualOverride.note),
      version: numberValue(manualOverride.version, 0),
    } : null,
    expectedCollectionDate: stringValue(camelOrSnake(raw, "expectedCollectionDate", "expected_collection_date")),
    reminder: Object.keys(reminder).length > 0 ? {
      id: stringValue(reminder.id),
      remindAt: stringValue(camelOrSnake(reminder, "remindAt", "remind_at")),
      channel: stringValue(reminder.channel),
      note: stringValue(reminder.note),
      status: stringValue(reminder.status),
    } : null,
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
    counterpartyName,
    tradeTime,
    amount,
    direction: stringValue(raw.direction),
    directionLabel: stringValue(camelOrSnake(raw, "directionLabel", "direction_label") ?? raw.direction),
    bankName: stringValue(camelOrSnake(raw, "bankName", "bank_name")),
    accountLast4: stringValue(camelOrSnake(raw, "accountLast4", "account_last4")),
    summary: stringValue(raw.summary),
    remark: stringValue(raw.remark),
    relationCaseId: stringValue(camelOrSnake(raw, "relationCaseId", "relation_case_id")),
    relationStatus: stringValue(camelOrSnake(raw, "relationStatus", "relation_status")),
    relationSource: stringValue(camelOrSnake(raw, "relationSource", "relation_source")),
    detailAvailable: id !== "",
  };
}

function mapOa(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["oa"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(raw.id ?? camelOrSnake(raw, "oaId", "oa_id") ?? camelOrSnake(raw, "primaryOaId", "primary_oa_id"));
  const applicantName = stringValue(camelOrSnake(raw, "applicantName", "applicant_name"));
  const applicationType = stringValue(camelOrSnake(raw, "applicationType", "application_type"));
  const projectName = stringValue(camelOrSnake(raw, "projectName", "project_name"));
  const amount = stringValue(raw.amount);
  if (!id && !applicantName && !applicationType && !projectName && !amount) {
    return null;
  }
  return {
    id,
    applicantName,
    applicationType,
    projectName,
    amount,
    status: stringValue(raw.status),
    relationCaseId: stringValue(camelOrSnake(raw, "relationCaseId", "relation_case_id")),
    relationStatus: stringValue(camelOrSnake(raw, "relationStatus", "relation_status")),
    relationSource: stringValue(camelOrSnake(raw, "relationSource", "relation_source")),
    detailAvailable: booleanValue(camelOrSnake(raw, "detailAvailable", "detail_available")) || id !== "",
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
  return {
    id,
    invoiceNo,
    invoiceCode: stringValue(camelOrSnake(raw, "invoiceCode", "invoice_code")),
    digitalInvoiceNo: stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no")),
    invoiceDate: stringValue(camelOrSnake(raw, "invoiceDate", "invoice_date")),
    buyerName: stringValue(camelOrSnake(raw, "buyerName", "buyer_name")),
    buyerTaxNo: stringValue(camelOrSnake(raw, "buyerTaxNo", "buyer_tax_no")),
    totalWithTax,
    taxableItemName: stringValue(camelOrSnake(raw, "taxableItemName", "taxable_item_name")),
    relationCaseId: stringValue(camelOrSnake(raw, "relationCaseId", "relation_case_id")),
    relationStatus: stringValue(camelOrSnake(raw, "relationStatus", "relation_status")),
    relationSource: stringValue(camelOrSnake(raw, "relationSource", "relation_source")),
  };
}

function mapRedInvoice(rawValue: unknown): OutputInvoiceCollectionRowsResponse["rows"][number]["redInvoice"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(camelOrSnake(raw, "relatedInvoiceId", "related_invoice_id") ?? raw.id);
  const invoiceNo = stringValue(camelOrSnake(raw, "invoiceNo", "invoice_no"));
  if (!id && !invoiceNo) {
    return null;
  }
  return {
    id,
    relationId: stringValue(camelOrSnake(raw, "relationId", "relation_id")),
    invoiceNo,
    invoiceDate: stringValue(camelOrSnake(raw, "invoiceDate", "invoice_date")),
    buyerName: stringValue(camelOrSnake(raw, "buyerName", "buyer_name")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    relationType: stringValue(camelOrSnake(raw, "relationType", "relation_type")),
    reason: stringValue(raw.reason),
    evidence: stringValue(raw.evidence),
    confidence: stringValue(raw.confidence),
    source: stringValue(raw.source),
  };
}

function mapRelation<T>(rawValue: unknown, mapper: (value: unknown) => T | null): {
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
      const receipt = objectValue(row.receipt);
      const latestReceipt = objectValue(camelOrSnake(receipt, "latestReceipt", "latest_receipt"));
      return {
        id: stringValue(row.id),
        invoiceId: stringValue(camelOrSnake(row, "invoiceId", "invoice_id")),
        invoiceIdentityKey: stringValue(camelOrSnake(row, "invoiceIdentityKey", "invoice_identity_key")),
        invoice: {
          ...mapInvoice(row.invoice),
          id: stringValue(camelOrSnake(row, "invoiceId", "invoice_id") ?? objectValue(row.invoice).id),
        },
        collectionStatus: mapCollectionStatus(camelOrSnake(row, "collectionStatus", "collection_status")),
        oa: mapRelation(row.oa, mapOa),
        bank: mapRelation(camelOrSnake(row, "bank", "bankTransactions"), mapBank),
        invoiceRelations: mapRelation(camelOrSnake(row, "invoiceRelations", "invoice_relations"), mapRelatedInvoice),
        redInvoice: mapRelation(camelOrSnake(row, "redInvoice", "redInvoiceRelation"), mapRedInvoice),
        receipt: {
          status: stringValue(receipt.status),
          label: stringValue(receipt.label),
          reason: stringValue(receipt.reason),
          previewAvailable: booleanValue(camelOrSnake(receipt, "previewAvailable", "preview_available")),
          sourceAvailable: booleanValue(camelOrSnake(receipt, "sourceAvailable", "source_available")),
          latestReceipt: Object.keys(latestReceipt).length > 0 ? {
            id: stringValue(latestReceipt.id),
            receiptNo: stringValue(camelOrSnake(latestReceipt, "receiptNo", "receipt_no")),
            amount: stringValue(latestReceipt.amount),
            status: stringValue(latestReceipt.status),
            createdAt: stringValue(camelOrSnake(latestReceipt, "createdAt", "created_at")),
          } : null,
        },
      };
    }),
    summary: (() => {
      const summary = objectValue(raw.summary);
      return {
        invoiceCount: numberValue(camelOrSnake(summary, "invoiceCount", "invoice_count"), 0),
        totalWithTax: stringValue(camelOrSnake(summary, "totalWithTax", "total_with_tax")),
        collectedAmount: stringValue(camelOrSnake(summary, "collectedAmount", "collected_amount")),
        pendingAmount: stringValue(camelOrSnake(summary, "pendingAmount", "pending_amount")),
        pendingCollectionCount: numberValue(camelOrSnake(summary, "pendingCollectionCount", "pending_collection_count"), 0),
        partialCollectionCount: numberValue(camelOrSnake(summary, "partialCollectionCount", "partial_collection_count"), 0),
        receiptPendingCount: numberValue(camelOrSnake(summary, "receiptPendingCount", "receipt_pending_count"), 0),
      };
    })(),
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
    generatedAt: stringValue(camelOrSnake(raw, "generatedAt", "generated_at")),
    sourceVersion: stringValue(camelOrSnake(raw, "sourceVersion", "source_version")),
  };
}

function detailField(label: string, value: unknown): OutputInvoiceCollectionDetailResponse["sections"][number]["fields"][number] {
  return {
    label,
    value: value === undefined ? "" : typeof value === "object" && value !== null ? JSON.stringify(value) : stringValue(value),
  };
}

function detailSection(title: string, fields: OutputInvoiceCollectionDetailResponse["sections"][number]["fields"]) {
  return { title, fields };
}

function objectEntriesSection(title: string, value: unknown) {
  const raw = objectValue(value);
  const fields = Object.entries(raw).map(([key, item]) => detailField(key, item));
  return fields.length > 0 ? detailSection(title, fields) : null;
}

function mapInvoiceDetailResponse(payload: unknown): OutputInvoiceCollectionDetailResponse {
  const raw = objectValue(payload);
  const invoiceNo = stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? raw.id);
  const sections: OutputInvoiceCollectionDetailResponse["sections"] = [
    detailSection("发票主信息", [
      detailField("发票号码", camelOrSnake(raw, "invoiceNo", "invoice_no")),
      detailField("发票代码", camelOrSnake(raw, "invoiceCode", "invoice_code")),
      detailField("数电发票号码", camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no")),
      detailField("开票日期", camelOrSnake(raw, "invoiceDate", "invoice_date")),
      detailField("销方名称", camelOrSnake(raw, "sellerName", "seller_name")),
      detailField("销方识别号", camelOrSnake(raw, "sellerTaxNo", "seller_tax_no")),
      detailField("购买方名称", camelOrSnake(raw, "buyerName", "buyer_name")),
      detailField("购买方识别号", camelOrSnake(raw, "buyerTaxNo", "buyer_tax_no")),
    ]),
    detailSection("金额与税额", [
      detailField("不含税金额", raw.amount),
      detailField("税率", camelOrSnake(raw, "taxRate", "tax_rate")),
      detailField("税额", camelOrSnake(raw, "taxAmount", "tax_amount")),
      detailField("价税合计", camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    ]),
    detailSection("业务与票据", [
      detailField("税收分类编码", camelOrSnake(raw, "taxClassificationCode", "tax_classification_code")),
      detailField("特定业务类型", camelOrSnake(raw, "specificBusinessType", "specific_business_type")),
      detailField("货物或应税劳务名称", camelOrSnake(raw, "taxableItemName", "taxable_item_name")),
      detailField("发票来源", camelOrSnake(raw, "invoiceSource", "invoice_source")),
      detailField("发票票种", camelOrSnake(raw, "invoiceKind", "invoice_kind")),
      detailField("发票状态", camelOrSnake(raw, "invoiceStatus", "invoice_status")),
      detailField("是否正数发票", camelOrSnake(raw, "isPositiveInvoice", "is_positive_invoice")),
      detailField("发票风险等级", camelOrSnake(raw, "riskLevel", "risk_level")),
      detailField("开票人", raw.issuer),
      detailField("备注", raw.remark),
    ]),
  ];
  const sourceLinks = objectEntriesSection("来源链接", camelOrSnake(raw, "sourceLinks", "source_links"));
  if (sourceLinks) {
    sections.push(sourceLinks);
  }
  return { title: "发票详情", subtitle: invoiceNo, sections };
}

function mapBankDetailResponse(payload: unknown): OutputInvoiceCollectionDetailResponse {
  const raw = objectValue(payload);
  return {
    title: "银行流水详情",
    subtitle: stringValue(camelOrSnake(raw, "counterpartyName", "counterparty_name") ?? raw.id),
    sections: [
      detailSection("流水主信息", [
        detailField("对方户名", camelOrSnake(raw, "counterpartyName", "counterparty_name")),
        detailField("交易时间", camelOrSnake(raw, "tradeTime", "trade_time")),
        detailField("金额", raw.amount),
        detailField("收支方向", raw.direction),
        detailField("银行", camelOrSnake(raw, "bankName", "bank_name")),
        detailField("账号后四位", camelOrSnake(raw, "accountLast4", "account_last4")),
      ]),
      detailSection("摘要与备注", [
        detailField("摘要", raw.summary),
        detailField("备注", raw.remark),
      ]),
    ],
  };
}

function mapRelationDetailResponse(payload: unknown): OutputInvoiceCollectionDetailResponse {
  const raw = objectValue(payload);
  const kind = stringValue(raw.kind);
  const label = kind === "oa" ? "OA" : kind === "invoice" ? "发票" : kind === "red_invoice" ? "红蓝票" : kind === "receipt" ? "收据" : "流水";
  const summaries = arrayValue(raw.summaries);
  const relations = arrayValue(raw.relations);
  return {
    title: `${label}关联明细`,
    subtitle: stringValue(camelOrSnake(raw, "rowId", "row_id")),
    detailAvailable: camelOrSnake(raw, "detailAvailable", "detail_available") !== false,
    sections: [
      detailSection("关联概况", [
        detailField("发票行 ID", camelOrSnake(raw, "invoiceId", "invoice_id")),
        detailField("关系类型", label),
        detailField("关系数量", camelOrSnake(raw, "relationCount", "relation_count")),
        detailField("是否多条", camelOrSnake(raw, "hasMultiple", "has_multiple") ? "是" : "否"),
        detailField("事实源可用", camelOrSnake(raw, "sourceAvailable", "source_available") ? "是" : "否"),
      ]),
      ...(summaries.length > 0 ? [detailSection("关联摘要", summaries.map((item, index) => detailField(`${label} ${index + 1}`, item)))] : []),
      ...(relations.length > 0 ? [detailSection("关联台证据", relations.map((item, index) => detailField(`关系 ${index + 1}`, item)))] : []),
    ],
  };
}

function mapFilterOptionsResponse(payload: unknown): OutputInvoiceCollectionFilterOptionsResponse {
  const raw = objectValue(payload);
  return {
    fields: arrayValue(raw.fields).map((item) => {
      const field = objectValue(item);
      return {
        field: stringValue(field.field),
        label: stringValue(field.label),
        mode: stringValue(field.mode) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["mode"],
        sortable: booleanValue(field.sortable),
        operators: arrayValue(field.operators).map(stringValue) as OutputInvoiceCollectionRowsResponse["filterConfig"][number]["operators"],
        options: arrayValue(field.options).map((option) => {
          const rawOption = objectValue(option);
          return {
            value: stringValue(rawOption.value),
            label: stringValue(rawOption.label),
            count: rawOption.count === undefined ? undefined : numberValue(rawOption.count, 0),
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

export async function fetchOutputInvoiceCollectionFilterOptions(
  request: Pick<FetchRowsRequest, "keyword" | "invoiceDateFrom" | "invoiceDateTo" | "month" | "filters" | "signal">,
): Promise<OutputInvoiceCollectionFilterOptionsResponse> {
  const params = new URLSearchParams();
  appendRowsQuery(params, { ...request, page: 1, pageSize: 1, sortField: "", sortDirection: "" });
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/filter-options?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapFilterOptionsResponse(payload);
}

export async function fetchOutputInvoiceCollectionExportPreview(
  request: FetchRowsRequest,
): Promise<OutputInvoiceCollectionExportPreview> {
  const payload = await apiRequestJson<unknown>(
    `/api/output-invoice-collections/export-preview?${buildRowsQuery(request, false)}`,
    { method: "GET", signal: request.signal },
  );
  const raw = objectValue(payload);
  return {
    fileName: stringValue(camelOrSnake(raw, "fileName", "file_name") ?? "销项发票收款情况.xlsx"),
    rowCount: numberValue(camelOrSnake(raw, "rowCount", "row_count"), 0),
    scopeLabel: stringValue(camelOrSnake(raw, "scopeLabel", "scope_label")),
    columns: arrayValue(raw.columns).map(stringValue),
    sampleRows: arrayValue(camelOrSnake(raw, "sampleRows", "sample_rows")).map(objectStringMap),
    message: stringValue(raw.message),
  };
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

export async function fetchOutputInvoiceCollectionBankTransactionDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/bank-transactions/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapBankDetailResponse(payload);
}

export async function fetchOutputInvoiceCollectionRowRelationDetail(
  target: OutputInvoiceCollectionDetailTarget,
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  params.set("kind", target.kind === "relationList" ? target.relationKind ?? "bank" : target.kind);
  const payload = await apiRequestJson<unknown>(
    `/api/output-invoice-collections/rows/${encodeURIComponent(target.rowId ?? target.id)}/relation-details?${params.toString()}`,
    { method: "GET", signal },
  );
  return mapRelationDetailResponse(payload);
}

export async function fetchOutputInvoiceCollectionStatusRules(signal?: AbortSignal) {
  return apiRequestJson<OutputInvoiceCollectionStatusRulesResponse>("/api/output-invoice-collections/status-rules", {
    method: "GET",
    signal,
  });
}

export async function fetchOutputInvoiceReceiptHistory(invoiceId: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(
    `/api/output-invoice-collections/receipts/history?invoice_id=${encodeURIComponent(invoiceId)}`,
    { method: "GET", signal },
  );
  const raw = objectValue(payload);
  return {
    invoiceId: stringValue(camelOrSnake(raw, "invoiceId", "invoice_id")),
    sourceAvailable: booleanValue(camelOrSnake(raw, "sourceAvailable", "source_available")),
    sourceName: stringValue(camelOrSnake(raw, "sourceName", "source_name")),
    receipts: arrayValue(raw.receipts).map((item) => {
      const receipt = objectValue(item);
      return {
        id: stringValue(receipt.id ?? camelOrSnake(receipt, "receiptId", "receipt_id")),
        receiptNo: stringValue(camelOrSnake(receipt, "receiptNo", "receipt_no")),
        amount: stringValue(receipt.amount),
        createdAt: stringValue(camelOrSnake(receipt, "createdAt", "created_at") ?? camelOrSnake(receipt, "issuedAt", "issued_at")),
        voidedAt: stringValue(camelOrSnake(receipt, "voidedAt", "voided_at")),
        voidReason: stringValue(camelOrSnake(receipt, "voidReason", "void_reason")),
        reissuedFromReceiptId: stringValue(camelOrSnake(receipt, "reissuedFromReceiptId", "reissued_from_receipt_id")),
        status: stringValue(receipt.status),
      };
    }),
    message: stringValue(raw.message),
  };
}

export async function previewOutputInvoiceReceipt(
  request: OutputInvoiceReceiptPreviewRequest,
  signal?: AbortSignal,
) {
  return apiRequestJson<OutputInvoiceReceiptPreviewResponse>("/api/output-invoice-collections/receipt-preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });
}

export async function updateOutputInvoiceCollectionStatus(rowId: string, request: OutputInvoiceCollectionStatusUpdateRequest) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/rows/${encodeURIComponent(rowId)}/collection-status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return mapMutationResponse(payload);
}

export async function updateOutputInvoiceCollectionReminder(rowId: string, request: OutputInvoiceCollectionReminderUpdateRequest) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/rows/${encodeURIComponent(rowId)}/collection-reminder`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return mapMutationResponse(payload);
}

export async function cancelOutputInvoiceCollectionReminder(rowId: string, reminderId: string) {
  const payload = await apiRequestJson<unknown>(
    `/api/output-invoice-collections/rows/${encodeURIComponent(rowId)}/collection-reminder/${encodeURIComponent(reminderId)}`,
    { method: "DELETE" },
  );
  return mapMutationResponse(payload);
}

export async function confirmOutputInvoiceRedRelation(rowId: string, request: OutputInvoiceCollectionRedRelationRequest) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/rows/${encodeURIComponent(rowId)}/red-invoice-relations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  return mapMutationResponse(payload);
}

export async function revokeOutputInvoiceRedRelation(relationId: string) {
  const payload = await apiRequestJson<unknown>(
    `/api/output-invoice-collections/red-invoice-relations/${encodeURIComponent(relationId)}`,
    { method: "DELETE" },
  );
  return mapMutationResponse(payload);
}

export async function createOutputInvoiceReceipt(rowId: string, request: OutputInvoiceReceiptCreateRequest) {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/rows/${encodeURIComponent(rowId)}/receipts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": request.idempotencyKey },
    body: JSON.stringify(request),
  });
  return mapMutationResponse(payload);
}

export async function voidOutputInvoiceReceipt(receiptId: string, reason = "") {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/receipts/${encodeURIComponent(receiptId)}/void`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return mapMutationResponse(payload);
}

export async function reissueOutputInvoiceReceipt(receiptId: string, reason = "") {
  const payload = await apiRequestJson<unknown>(`/api/output-invoice-collections/receipts/${encodeURIComponent(receiptId)}/reissue`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  return mapMutationResponse(payload);
}

export async function fetchOutputInvoiceReceiptSettings(signal?: AbortSignal): Promise<OutputInvoiceReceiptSettingsResponse> {
  return apiRequestJson<OutputInvoiceReceiptSettingsResponse>("/api/output-invoice-collections/receipt-settings", {
    method: "GET",
    signal,
  });
}

export async function updateOutputInvoiceReceiptSettings(request: { prefix: string; resetPeriod: string }) {
  return apiRequestJson<OutputInvoiceReceiptSettingsResponse>("/api/output-invoice-collections/receipt-settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
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
