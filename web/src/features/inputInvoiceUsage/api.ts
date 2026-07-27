import { apiFetch, apiRequestJson, looksLikeHtmlResponse } from "../apiClient";
import type {
  CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest,
  CreateInputInvoiceUsageOaReverseBatchRequest,
  InputInvoiceUsageDetailResponse,
  InputInvoiceUsageExportDownload,
  InputInvoiceUsageExportPreview,
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageFilterOptionsResponse,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReversePreviewRequest,
  InputInvoiceUsageOaReversePreviewResponse,
  InputInvoiceUsageOaReverseStagedDraftsResponse,
  InputInvoiceUsageOaReverseSubmittedHistoryResponse,
  InputInvoiceUsagePaymentStatusRulesResponse,
  InputInvoiceUsageQuery,
  InputInvoiceUsageRowsResponse,
  InputInvoiceUsageSortDirection,
  ManualInputInvoiceUsageOaReverseStatusRequest,
  RevokeInputInvoiceUsageOaReverseDraftRequest,
  SaveInputInvoiceUsagePaymentStatusRulesRequest,
  InputInvoiceUsageOaReverseVersionedRequest,
} from "./types";

type FetchRowsRequest = Pick<
  InputInvoiceUsageQuery,
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

function maybeNumber(value: unknown): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function camelOrSnake(source: Record<string, unknown>, camel: string, snake: string) {
  return source[camel] ?? source[snake];
}

function bankDirectionLabel(value: unknown) {
  const text = stringValue(value).trim();
  if (text === "outflow" || text === "支" || text === "支出") {
    return "支出";
  }
  if (text === "inflow" || text === "收" || text === "收入") {
    return "收入";
  }
  return text;
}

function bankAccountLabel(raw: Record<string, unknown>) {
  const explicit = stringValue(camelOrSnake(raw, "bankAccount", "bank_account")).trim();
  if (explicit) {
    return explicit;
  }
  const bankName = stringValue(camelOrSnake(raw, "bankName", "bank_name")).trim();
  const accountLast4 = stringValue(camelOrSnake(raw, "accountLast4", "account_last4")).trim();
  return [bankName, accountLast4].filter(Boolean).join(" ");
}

function unwrapData<T>(payload: T | { data?: T }): T {
  if (payload && typeof payload === "object" && "data" in payload) {
    const data = (payload as { data?: T }).data;
    if (data !== undefined && data !== null) {
      return data;
    }
  }
  return payload as T;
}

function encodeFilters(filters: InputInvoiceUsageFilter[]) {
  return encodeURIComponent(JSON.stringify(filters));
}

function appendRowsQuery(params: URLSearchParams, request: FetchRowsRequest) {
  params.set("page", String(request.page));
  params.set("page_size", String(request.pageSize));
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

function buildRowsQuery(request: FetchRowsRequest) {
  const params = new URLSearchParams();
  appendRowsQuery(params, request);
  params.delete("page");
  params.delete("page_size");
  return params.toString();
}

function mapInvoice(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["invoice"] {
  const raw = objectValue(rawValue);
  const rawPermissions = raw.permissions === undefined || raw.permissions === null ? null : objectValue(raw.permissions);
  return {
    id: stringValue(raw.id),
    displayNo: stringValue(camelOrSnake(raw, "displayNo", "display_no") ?? camelOrSnake(raw, "invoiceNo", "invoice_no")),
    invoiceNo: stringValue(camelOrSnake(raw, "invoiceNo", "invoice_no")),
    invoiceCode: stringValue(camelOrSnake(raw, "invoiceCode", "invoice_code")),
    digitalInvoiceNo: stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no")),
    issueDate: stringValue(camelOrSnake(raw, "issueDate", "issue_date") ?? camelOrSnake(raw, "invoiceDate", "invoice_date")),
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

function mapPaymentStatus(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["paymentStatus"] {
  const raw = objectValue(rawValue);
  return {
    code: stringValue(raw.code),
    label: stringValue(raw.label),
    reason: stringValue(raw.reason),
  };
}

function mapOa(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["oa"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(raw.id ?? camelOrSnake(raw, "oaId", "oa_id") ?? camelOrSnake(raw, "primaryOaId", "primary_oa_id"));
  const applicant = stringValue(raw.applicant ?? camelOrSnake(raw, "applicantName", "applicant_name"));
  const applicationType = stringValue(camelOrSnake(raw, "applicationType", "application_type"));
  const projectName = stringValue(camelOrSnake(raw, "projectName", "project_name"));
  const amount = stringValue(raw.amount);
  if (!id && !applicant && !applicationType && !projectName && !amount) {
    return null;
  }
  return {
    id,
    applicant,
    applicationType,
    projectName,
    amount,
    detailAvailable: booleanValue(camelOrSnake(raw, "detailAvailable", "detail_available")),
  };
}

function mapBank(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["bank"]["primary"] {
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
    directionLabel: bankDirectionLabel(camelOrSnake(raw, "directionLabel", "direction_label") ?? raw.direction),
    bankName: stringValue(camelOrSnake(raw, "bankName", "bank_name")),
    accountLast4: stringValue(camelOrSnake(raw, "accountLast4", "account_last4")),
    bankAccount: bankAccountLabel(raw),
    summary: stringValue(raw.summary),
    remark: stringValue(raw.remark),
    detailAvailable: booleanValue(camelOrSnake(raw, "detailAvailable", "detail_available")),
  };
}

function mapInvoiceRelation(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["invoiceRelations"]["primary"] {
  const raw = objectValue(rawValue);
  const id = stringValue(raw.id ?? camelOrSnake(raw, "invoiceId", "invoice_id") ?? camelOrSnake(raw, "primaryInvoiceId", "primary_invoice_id"));
  const invoiceNo = stringValue(camelOrSnake(raw, "invoiceNo", "invoice_no"));
  const invoiceCode = stringValue(camelOrSnake(raw, "invoiceCode", "invoice_code"));
  const digitalInvoiceNo = stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no"));
  const explicitDisplayNo = stringValue(camelOrSnake(raw, "displayNo", "display_no")).trim();
  const displayNo = explicitDisplayNo || digitalInvoiceNo || [invoiceCode, invoiceNo].filter(Boolean).join(" ");
  const sellerName = stringValue(camelOrSnake(raw, "sellerName", "seller_name"));
  const totalWithTax = stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax"));
  if (!id && !displayNo && !sellerName && !totalWithTax) {
    return null;
  }
  return {
    id,
    displayNo,
    invoiceNo,
    invoiceCode,
    digitalInvoiceNo,
    invoiceDate: stringValue(camelOrSnake(raw, "invoiceDate", "invoice_date") ?? camelOrSnake(raw, "issueDate", "issue_date")),
    sellerName,
    sellerTaxNo: stringValue(camelOrSnake(raw, "sellerTaxNo", "seller_tax_no")),
    totalWithTax,
    taxableItemName: stringValue(camelOrSnake(raw, "taxableItemName", "taxable_item_name")),
  };
}

function mapRelation<T>(rawValue: unknown, mapper: (value: unknown) => T | null): {
  primary: T | null;
  relationCount: number;
  hasMultiple: boolean;
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
    detailMode: detailMode === "list" || detailMode === "single" ? detailMode : primary ? "single" : "none",
    summaries,
  };
}

function mapRowsResponse(payload: unknown): InputInvoiceUsageRowsResponse {
  const raw = objectValue(payload);
  const pagination = objectValue(raw.pagination);
  return {
    rows: arrayValue(raw.rows).map((item) => {
      const row = objectValue(item);
      const invoiceRelationsRaw = camelOrSnake(row, "invoiceRelations", "invoice_relations");
      const invoiceRelations = mapRelation(invoiceRelationsRaw, mapInvoiceRelation);
      const invoiceRelationsObject = objectValue(invoiceRelationsRaw);
      return {
        id: stringValue(row.id),
        invoice: {
          ...mapInvoice(row.invoice),
          id: stringValue(camelOrSnake(row, "invoiceId", "invoice_id") ?? objectValue(row.invoice).id),
        },
        paymentStatus: mapPaymentStatus(camelOrSnake(row, "paymentStatus", "payment_status")),
        oa: mapRelation(row.oa, mapOa),
        bank: mapRelation(camelOrSnake(row, "bank", "bankTransactions"), mapBank),
        invoiceRelations: {
          ...invoiceRelations,
          totalWithTax: stringValue(camelOrSnake(invoiceRelationsObject, "totalWithTax", "total_with_tax")),
        },
      };
    }),
    summary: raw.summary && typeof raw.summary === "object" ? (() => {
      const summary = objectValue(raw.summary);
      return {
        invoiceCount: numberValue(camelOrSnake(summary, "invoiceCount", "invoice_count"), 0),
        totalWithTax: stringValue(camelOrSnake(summary, "totalWithTax", "total_with_tax")),
        matchedOaCount: numberValue(camelOrSnake(summary, "matchedOaCount", "matched_oa_count"), 0),
        matchedBankTransactionCount: numberValue(camelOrSnake(summary, "matchedBankTransactionCount", "matched_bank_transaction_count"), 0),
        pendingCount: numberValue(camelOrSnake(summary, "pendingCount", "pending_count"), 0),
      };
    })() : undefined,
    statistics: raw.statistics && typeof raw.statistics === "object" ? (() => {
      const statistics = objectValue(raw.statistics);
      return {
        invoiceCount: optionalCount(camelOrSnake(statistics, "invoiceCount", "invoice_count")),
        linkedOaInvoiceCount: optionalCount(camelOrSnake(statistics, "linkedOaInvoiceCount", "linked_oa_invoice_count")),
        linkedBankInvoiceCount: optionalCount(camelOrSnake(statistics, "linkedBankInvoiceCount", "linked_bank_invoice_count")),
        paidInvoiceCount: optionalCount(camelOrSnake(statistics, "paidInvoiceCount", "paid_invoice_count")),
        unlinkedOaInvoiceCount: optionalCount(camelOrSnake(statistics, "unlinkedOaInvoiceCount", "unlinked_oa_invoice_count")),
        unlinkedBankInvoiceCount: optionalCount(camelOrSnake(statistics, "unlinkedBankInvoiceCount", "unlinked_bank_invoice_count")),
        unpaidInvoiceCount: optionalCount(camelOrSnake(statistics, "unpaidInvoiceCount", "unpaid_invoice_count")),
        formalRelationGroupCount: optionalCount(camelOrSnake(statistics, "formalRelationGroupCount", "formal_relation_group_count")),
        oaReverseBatchCount: optionalCount(camelOrSnake(statistics, "oaReverseBatchCount", "oa_reverse_batch_count")),
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
        mode: stringValue(config.mode) as InputInvoiceUsageRowsResponse["filterConfig"][number]["mode"],
        sortable: booleanValue(config.sortable),
        operators: arrayValue(config.operators).map(stringValue) as InputInvoiceUsageRowsResponse["filterConfig"][number]["operators"],
      };
    }),
    filterOptions: mapFilterOptionsResponse({
      fields: camelOrSnake(raw, "filterOptions", "filter_options"),
    }).fields,
  };
}

function detailField(label: string, value: unknown): InputInvoiceUsageDetailResponse["sections"][number]["fields"][number] {
  return {
    label,
    value: value === undefined ? "" : typeof value === "object" && value !== null ? JSON.stringify(value) : stringValue(value),
  };
}

function detailSection(title: string, fields: InputInvoiceUsageDetailResponse["sections"][number]["fields"]) {
  return { title, fields };
}

function objectEntriesSection(title: string, value: unknown) {
  const raw = objectValue(value);
  const fields = Object.entries(raw).map(([key, item]) => detailField(key, item));
  return fields.length > 0 ? detailSection(title, fields) : null;
}

function mapDetailSections(value: unknown): InputInvoiceUsageDetailResponse["sections"] {
  return arrayValue(value).map((sectionValue) => {
    const section = objectValue(sectionValue);
    return detailSection(
      stringValue(section.title) || "详情",
      arrayValue(section.fields).map((fieldValue) => {
        const field = objectValue(fieldValue);
        return detailField(stringValue(field.label) || "字段", field.value);
      }),
    );
  }).filter((section) => section.fields.length > 0);
}

function mapInvoiceDetailResponse(payload: unknown): InputInvoiceUsageDetailResponse {
  const raw = objectValue(payload);
  const invoiceNo = stringValue(camelOrSnake(raw, "digitalInvoiceNo", "digital_invoice_no") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? raw.id);
  const sections: InputInvoiceUsageDetailResponse["sections"] = [
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
      detailField("来源批次", camelOrSnake(raw, "sourceBatchId", "source_batch_id")),
    ]),
  ];

  const lineItems = arrayValue(camelOrSnake(raw, "lineItems", "line_items"));
  if (lineItems.length > 0) {
    sections.push(detailSection("货物或应税劳务明细", lineItems.map((item, index) => {
      const line = objectValue(item);
      return detailField(`明细 ${index + 1}`, [
        stringValue(camelOrSnake(line, "taxableItemName", "taxable_item_name")),
        `规格型号 ${stringValue(camelOrSnake(line, "specificationModel", "specification_model")) || "-"}`,
        `单位 ${stringValue(line.unit) || "-"}`,
        `数量 ${stringValue(line.quantity) || "-"}`,
        `单价 ${stringValue(camelOrSnake(line, "unitPrice", "unit_price")) || "-"}`,
        `金额 ${stringValue(line.amount) || "-"}`,
        `税率 ${stringValue(camelOrSnake(line, "taxRate", "tax_rate")) || "-"}`,
        `税额 ${stringValue(camelOrSnake(line, "taxAmount", "tax_amount")) || "-"}`,
        `价税合计 ${stringValue(camelOrSnake(line, "totalWithTax", "total_with_tax")) || "-"}`,
        `备注 ${stringValue(line.remark) || "-"}`,
      ].join(" / "));
    })));
  }

  const sourceLinks = objectEntriesSection("来源链接", camelOrSnake(raw, "sourceLinks", "source_links"));
  if (sourceLinks) {
    sections.push(sourceLinks);
  }

  return {
    title: "发票详情",
    subtitle: invoiceNo,
    sections,
  };
}

function mapBankDetailResponse(payload: unknown): InputInvoiceUsageDetailResponse {
  const raw = objectValue(payload);
  const sections: InputInvoiceUsageDetailResponse["sections"] = [
    detailSection("流水主信息", [
      detailField("对方户名", camelOrSnake(raw, "counterpartyName", "counterparty_name")),
      detailField("交易时间", camelOrSnake(raw, "tradeTime", "trade_time")),
      detailField("金额", raw.amount),
      detailField("收支方向", raw.direction),
      detailField("支付银行", camelOrSnake(raw, "bankName", "bank_name")),
      detailField("支付账号", camelOrSnake(raw, "accountNo", "account_no")),
      detailField("支付账号后四位", camelOrSnake(raw, "accountLast4", "account_last4")),
      detailField("币种", raw.currency),
    ]),
    detailSection("对方与摘要", [
      detailField("对方账号", camelOrSnake(raw, "counterpartyAccountNo", "counterparty_account_no")),
      detailField("对方开户机构", camelOrSnake(raw, "counterpartyBankName", "counterparty_bank_name")),
      detailField("记账日期", camelOrSnake(raw, "bookedDate", "booked_date")),
      detailField("摘要", raw.summary),
      detailField("备注", raw.remark),
    ]),
  ];
  const bankTextFields = objectEntriesSection("银行原始字段", camelOrSnake(raw, "bankTextFields", "bank_text_fields"));
  if (bankTextFields) {
    sections.push(bankTextFields);
  }
  return {
    title: "银行流水详情",
    subtitle: stringValue(camelOrSnake(raw, "counterpartyName", "counterparty_name") ?? raw.id),
    sections,
  };
}

function mapOaDetailResponse(payload: unknown): InputInvoiceUsageDetailResponse {
  const raw = objectValue(payload);
  if (camelOrSnake(raw, "detailAvailable", "detail_available") === false) {
    return {
      title: "OA详情",
      subtitle: stringValue(camelOrSnake(raw, "oaId", "oa_id")),
      detailAvailable: false,
      unavailableReason: "后端未提供可稳定展示的 OA 完整详情。",
      sections: [],
    };
  }
  const sections: InputInvoiceUsageDetailResponse["sections"] = [
    detailSection("OA主信息", [
      detailField("申请人", camelOrSnake(raw, "applicantName", "applicant_name")),
      detailField("报销/支付", camelOrSnake(raw, "applicationType", "application_type")),
      detailField("项目名称", camelOrSnake(raw, "projectName", "project_name")),
      detailField("流程号", camelOrSnake(raw, "workflowNo", "workflow_no")),
      detailField("状态", raw.status),
      detailField("金额", raw.amount),
      detailField("月份", raw.month),
      detailField("事由", raw.reason),
      detailField("对方户名", camelOrSnake(raw, "counterpartyName", "counterparty_name")),
      detailField("打开链接", camelOrSnake(raw, "openUrl", "open_url")),
    ]),
  ];
  const detailFields = objectEntriesSection("OA原始字段", camelOrSnake(raw, "detailFields", "detail_fields"));
  if (detailFields) {
    sections.push(detailFields);
  }
  return {
    title: "OA详情",
    subtitle: stringValue(camelOrSnake(raw, "workflowNo", "workflow_no") ?? camelOrSnake(raw, "oaId", "oa_id")),
    detailAvailable: true,
    sections,
  };
}

function mapRelationDetailResponse(payload: unknown): InputInvoiceUsageDetailResponse {
  const raw = objectValue(payload);
  const rawKind = stringValue(raw.kind);
  const kind = rawKind === "bank" ? "银行流水" : rawKind === "invoice" ? "发票" : "OA";
  const detailSections = mapDetailSections(raw.sections);
  const summaries = arrayValue(raw.summaries);
  const sections: InputInvoiceUsageDetailResponse["sections"] = [
    detailSection("关联概况", [
      detailField("发票行 ID", camelOrSnake(raw, "invoiceId", "invoice_id")),
      detailField("关系类型", kind),
      detailField("关系数量", camelOrSnake(raw, "relationCount", "relation_count")),
      detailField("是否多条", camelOrSnake(raw, "hasMultiple", "has_multiple") ? "是" : "否"),
    ]),
  ];
  if (detailSections.length > 0) {
    sections.push(...detailSections);
  } else if (summaries.length > 0) {
    sections.push(detailSection("关联摘要", summaries.map((item, index) => detailField(`${kind} ${index + 1}`, item))));
  }
  const relations = arrayValue(raw.relations);
  if (relations.length > 0) {
    sections.push(detailSection("关联台证据", relations.map((item, index) => detailField(`关系 ${index + 1}`, item))));
  }
  return {
    title: stringValue(raw.title) || `${kind}关联明细`,
    subtitle: stringValue(camelOrSnake(raw, "rowId", "row_id")),
    detailAvailable: camelOrSnake(raw, "detailAvailable", "detail_available") !== false,
    sections,
  };
}

function mapFilterOptionsResponse(payload: unknown): InputInvoiceUsageFilterOptionsResponse {
  const raw = objectValue(payload);
  return {
    fields: arrayValue(raw.fields).map((item) => {
      const field = objectValue(item);
      return {
        field: stringValue(field.field),
        label: stringValue(field.label),
        mode: stringValue(field.mode) as InputInvoiceUsageRowsResponse["filterConfig"][number]["mode"],
        sortable: booleanValue(field.sortable),
        operators: arrayValue(field.operators).map(stringValue) as InputInvoiceUsageRowsResponse["filterConfig"][number]["operators"],
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

function mapPermissions(rawValue: unknown) {
  const raw = objectValue(rawValue);
  return {
    canSave: booleanValue(camelOrSnake(raw, "canSave", "can_save")),
  };
}

function mapPaymentStatusRulesResponse(payload: unknown): InputInvoiceUsagePaymentStatusRulesResponse {
  const raw = objectValue(unwrapData(payload));
  const source = objectValue(raw.source ?? raw.metadata);
  return {
    version: (raw.version as number | string | null | undefined) ?? null,
    readOnly: camelOrSnake(raw, "readOnly", "read_only") === undefined
      ? true
      : booleanValue(camelOrSnake(raw, "readOnly", "read_only")),
    permissions: mapPermissions(raw.permissions),
    rules: arrayValue(raw.rules).map((item) => {
      const rule = objectValue(item);
      return {
        id: stringValue(rule.id),
        code: stringValue(rule.code),
        statusCode: stringValue(camelOrSnake(rule, "statusCode", "status_code")),
        label: stringValue(rule.label),
        description: stringValue(rule.description),
        reason: stringValue(rule.reason),
        priority: numberValue(rule.priority, 0),
        enabled: rule.enabled === undefined ? undefined : booleanValue(rule.enabled),
        conditions: objectValue(rule.conditions),
        applicantConstraints: arrayValue(camelOrSnake(rule, "applicantConstraints", "applicant_constraints")).map(stringValue),
      };
    }),
    pendingDirections: arrayValue(camelOrSnake(raw, "pendingDirections", "pending_directions")).map((item) => {
      const direction = objectValue(item);
      return {
        code: stringValue(direction.code),
        label: stringValue(direction.label),
      };
    }),
    source: Object.keys(source).length > 0 ? {
      version: stringValue(source.version),
      updatedAt: stringValue(camelOrSnake(source, "updatedAt", "updated_at")),
      updatedBy: stringValue(camelOrSnake(source, "updatedBy", "updated_by")),
    } : undefined,
  };
}

function mapOaReverseInvoice(rawValue: unknown) {
  const raw = objectValue(rawValue);
  const invoiceId = stringValue(camelOrSnake(raw, "invoiceId", "invoice_id") ?? raw.id);
  const displayNo = stringValue(camelOrSnake(raw, "displayNo", "display_no") ?? camelOrSnake(raw, "invoiceNumber", "invoice_number") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? invoiceId);
  const paymentStatus = objectValue(camelOrSnake(raw, "paymentStatus", "payment_status"));
  return {
    invoiceId,
    invoiceNumber: stringValue(camelOrSnake(raw, "invoiceNumber", "invoice_number") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? displayNo),
    displayNo,
    sellerName: stringValue(camelOrSnake(raw, "sellerName", "seller_name")),
    issueDate: stringValue(camelOrSnake(raw, "issueDate", "issue_date") ?? camelOrSnake(raw, "invoiceDate", "invoice_date")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    paymentStatusLabel: stringValue(camelOrSnake(raw, "paymentStatusLabel", "payment_status_label") ?? camelOrSnake(raw, "statusLabel", "status_label") ?? paymentStatus.label ?? raw.status),
    targetApplicantName: stringValue(camelOrSnake(raw, "targetApplicantName", "target_applicant_name")),
    oaRelationStatus: stringValue(camelOrSnake(raw, "oaRelationStatus", "oa_relation_status")),
  };
}

function mapRejectedInvoice(rawValue: unknown) {
  const raw = objectValue(rawValue);
  const displayNo = stringValue(
    camelOrSnake(raw, "displayNo", "display_no")
      ?? camelOrSnake(raw, "invoiceNumber", "invoice_number")
      ?? camelOrSnake(raw, "invoiceNo", "invoice_no")
      ?? raw.id,
  );
  const paymentStatus = objectValue(camelOrSnake(raw, "paymentStatus", "payment_status"));
  return {
    invoiceId: stringValue(camelOrSnake(raw, "invoiceId", "invoice_id") ?? raw.id),
    invoiceNumber: stringValue(camelOrSnake(raw, "invoiceNumber", "invoice_number") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? displayNo),
    displayNo,
    sellerName: stringValue(camelOrSnake(raw, "sellerName", "seller_name")),
    issueDate: stringValue(camelOrSnake(raw, "issueDate", "issue_date") ?? camelOrSnake(raw, "invoiceDate", "invoice_date")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    paymentStatusLabel: stringValue(
      camelOrSnake(raw, "paymentStatusLabel", "payment_status_label")
        ?? camelOrSnake(raw, "statusLabel", "status_label")
        ?? paymentStatus.label
        ?? raw.status,
    ),
    oaRelationStatus: stringValue(camelOrSnake(raw, "oaRelationStatus", "oa_relation_status")),
    reasonCode: stringValue(camelOrSnake(raw, "reasonCode", "reason_code")),
    reason: stringValue(raw.reason),
  };
}

function mapOaReversePreviewResponse(payload: unknown): InputInvoiceUsageOaReversePreviewResponse {
  const raw = objectValue(unwrapData(payload));
  const rawPermissions = raw.permissions === undefined || raw.permissions === null ? null : objectValue(raw.permissions);
  const topLevelRows = arrayValue(camelOrSnake(raw, "invoiceRows", "invoice_rows")).map(mapOaReverseInvoice);
  const topLevelCandidates = topLevelRows.length > 0
    ? topLevelRows
    : arrayValue(camelOrSnake(raw, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice);
  const groups = arrayValue(raw.groups).map((item) => {
    const group = objectValue(item);
    const groupRows = arrayValue(camelOrSnake(group, "invoiceRows", "invoice_rows")).map(mapOaReverseInvoice);
    const groupCandidates = groupRows.length > 0
      ? groupRows
      : arrayValue(camelOrSnake(group, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice);
    const candidateIds = arrayValue(camelOrSnake(group, "candidateInvoiceIds", "candidate_invoice_ids")).map(stringValue);
    return {
      targetApplicantCode: stringValue(camelOrSnake(group, "targetApplicantCode", "target_applicant_code")) || null,
      targetApplicantName: stringValue(camelOrSnake(group, "targetApplicantName", "target_applicant_name")),
      invoiceCount: numberValue(camelOrSnake(group, "invoiceCount", "invoice_count"), groupCandidates.length || candidateIds.length),
      totalWithTax: stringValue(camelOrSnake(group, "totalWithTax", "total_with_tax")),
      invoiceRows: groupCandidates,
      candidateInvoiceIds: candidateIds,
      candidateInvoices: groupCandidates,
      rejectedInvoices: arrayValue(camelOrSnake(group, "rejectedInvoices", "rejected_invoices")).map(mapRejectedInvoice),
    };
  });
  return {
    previewId: stringValue(camelOrSnake(raw, "previewId", "preview_id")),
    previewHash: stringValue(camelOrSnake(raw, "previewHash", "preview_hash") ?? camelOrSnake(raw, "expectedPreviewHash", "expected_preview_hash")),
    source: stringValue(raw.source),
    targetApplicantCode: stringValue(camelOrSnake(raw, "targetApplicantCode", "target_applicant_code")),
    targetApplicantName: stringValue(camelOrSnake(raw, "targetApplicantName", "target_applicant_name")),
    targetApplicants: arrayValue(camelOrSnake(raw, "targetApplicants", "target_applicants")).map((item) => {
      const applicant = objectValue(item);
      return {
        code: stringValue(applicant.code),
        name: stringValue(applicant.name),
      };
    }).filter((applicant) => applicant.code && applicant.name),
    invoiceCount: numberValue(camelOrSnake(raw, "invoiceCount", "invoice_count"), topLevelCandidates.length),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    groups,
    invoiceRows: topLevelCandidates,
    candidateInvoices: topLevelCandidates,
    rejectedInvoices: arrayValue(camelOrSnake(raw, "rejectedInvoices", "rejected_invoices")).map(mapRejectedInvoice),
    warnings: arrayValue(raw.warnings).map(stringValue),
    canCreateDraft: booleanValue(camelOrSnake(raw, "canCreateDraft", "can_create_draft")),
    nextAction: stringValue(camelOrSnake(raw, "nextAction", "next_action")),
    unavailableReason: stringValue(camelOrSnake(raw, "unavailableReason", "unavailable_reason")),
    permissions: rawPermissions ? {
      canCreateBatch: camelOrSnake(rawPermissions, "canCreateBatch", "can_create_batch") === undefined
        ? undefined
        : booleanValue(camelOrSnake(rawPermissions, "canCreateBatch", "can_create_batch")),
      canCreateDraft: camelOrSnake(rawPermissions, "canCreateDraft", "can_create_draft") === undefined
        ? undefined
        : booleanValue(camelOrSnake(rawPermissions, "canCreateDraft", "can_create_draft")),
      canRevoke: camelOrSnake(rawPermissions, "canRevoke", "can_revoke") === undefined
        ? undefined
        : booleanValue(camelOrSnake(rawPermissions, "canRevoke", "can_revoke")),
      canManualStatus: camelOrSnake(rawPermissions, "canManualStatus", "can_manual_status") === undefined
        ? undefined
        : booleanValue(camelOrSnake(rawPermissions, "canManualStatus", "can_manual_status")),
    } : undefined,
  };
}

function mapOaReverseBatch(payload: unknown): InputInvoiceUsageOaReverseBatch {
  const raw = objectValue(unwrapData(payload));
  const invoiceIds = arrayValue(camelOrSnake(raw, "invoiceIds", "invoice_ids") ?? camelOrSnake(raw, "selectedInvoiceIds", "selected_invoice_ids")).map(stringValue);
  const invoiceRows = arrayValue(camelOrSnake(raw, "invoiceRows", "invoice_rows") ?? raw.invoices ?? camelOrSnake(raw, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice);
  const previewSummary = objectValue(camelOrSnake(raw, "previewSummary", "preview_summary"));
  return {
    batchId: stringValue(camelOrSnake(raw, "batchId", "batch_id") ?? raw.id),
    version: numberValue(raw.version, 0),
    status: stringValue(raw.status),
    invoiceIds,
    selectedInvoiceIds: invoiceIds,
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax") ?? previewSummary.totalWithTax ?? previewSummary.total_with_tax),
    previewSummary: Object.keys(previewSummary).length > 0 ? {
      invoiceCount: numberValue(camelOrSnake(previewSummary, "invoiceCount", "invoice_count"), invoiceRows.length),
      totalWithTax: stringValue(camelOrSnake(previewSummary, "totalWithTax", "total_with_tax")),
    } : undefined,
    targetApplicantCode: stringValue(camelOrSnake(raw, "targetApplicantCode", "target_applicant_code")) || null,
    targetApplicantName: stringValue(camelOrSnake(raw, "targetApplicantName", "target_applicant_name")) || null,
    invoiceRows,
    invoices: invoiceRows,
    rejectedInvoices: arrayValue(camelOrSnake(raw, "rejectedInvoices", "rejected_invoices")).map(mapRejectedInvoice),
    oaDraftId: stringValue(camelOrSnake(raw, "oaDraftId", "oa_draft_id")) || null,
    oaDraftUrl: stringValue(camelOrSnake(raw, "oaDraftUrl", "oa_draft_url")) || null,
    oaProcessStatus: stringValue(camelOrSnake(raw, "oaProcessStatus", "oa_process_status")) || null,
    oaDetectionStatus: stringValue(camelOrSnake(raw, "oaDetectionStatus", "oa_detection_status")) || null,
    nextRunAt: stringValue(camelOrSnake(raw, "nextRunAt", "next_run_at")) || null,
    attempts: maybeNumber(raw.attempts),
    conflictCandidates: arrayValue(camelOrSnake(raw, "conflictCandidates", "conflict_candidates")).map((item) => {
      const candidate = objectValue(item);
      return {
        id: stringValue(candidate.id),
        label: stringValue(candidate.label),
        reason: stringValue(candidate.reason),
      };
    }),
    idempotentReplay: booleanValue(camelOrSnake(raw, "idempotentReplay", "idempotent_replay")),
    auditEventId: stringValue(camelOrSnake(raw, "auditEventId", "audit_event_id")) || null,
    canCreateDraft: camelOrSnake(raw, "canCreateDraft", "can_create_draft") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canCreateDraft", "can_create_draft")),
    canConfirmSubmission: camelOrSnake(raw, "canConfirmSubmission", "can_confirm_submission") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canConfirmSubmission", "can_confirm_submission")),
    canRevoke: camelOrSnake(raw, "canRevoke", "can_revoke") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canRevoke", "can_revoke")),
    canManualStatus: camelOrSnake(raw, "canManualStatus", "can_manual_status") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canManualStatus", "can_manual_status")),
  };
}

function mapOaReverseSubmittedHistory(payload: unknown): InputInvoiceUsageOaReverseSubmittedHistoryResponse {
  const raw = objectValue(unwrapData(payload));
  return {
    items: arrayValue(raw.items).map((item) => {
      const history = objectValue(item);
      return {
        targetApplicantName: stringValue(camelOrSnake(history, "targetApplicantName", "target_applicant_name")),
        submittedAt: stringValue(camelOrSnake(history, "submittedAt", "submitted_at")),
        totalWithTax: stringValue(camelOrSnake(history, "totalWithTax", "total_with_tax")),
        invoiceCount: numberValue(camelOrSnake(history, "invoiceCount", "invoice_count"), 0),
        invoices: arrayValue(history.invoices).map((invoiceValue) => {
          const invoice = objectValue(invoiceValue);
          return {
            invoiceNo: stringValue(camelOrSnake(invoice, "invoiceNo", "invoice_no")),
            invoiceDate: stringValue(camelOrSnake(invoice, "invoiceDate", "invoice_date")),
            sellerName: stringValue(camelOrSnake(invoice, "sellerName", "seller_name")),
            totalWithTax: stringValue(camelOrSnake(invoice, "totalWithTax", "total_with_tax")),
          };
        }),
      };
    }),
  };
}

function mapOaReverseStagedDrafts(payload: unknown): InputInvoiceUsageOaReverseStagedDraftsResponse {
  const raw = objectValue(unwrapData(payload));
  return {
    items: arrayValue(raw.items).map(mapOaReverseBatch),
  };
}

function objectStringMap(value: unknown): Record<string, string> {
  const raw = objectValue(value);
  return Object.fromEntries(Object.entries(raw).map(([key, item]) => [key, stringValue(item)]));
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

async function requestExportBlob(url: string, init: RequestInit = {}): Promise<InputInvoiceUsageExportDownload> {
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
      const payload = JSON.parse(rawText) as { message?: string };
      message = payload.message || "导出接口返回了非 xlsx 响应。";
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
    fileName: parseContentDispositionFileName(response.headers?.get?.("Content-Disposition") ?? null) ?? "进项发票使用情况.xlsx",
  };
}

export async function fetchInputInvoiceUsageRows(request: FetchRowsRequest): Promise<InputInvoiceUsageRowsResponse> {
  const params = new URLSearchParams();
  appendRowsQuery(params, request);
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/rows?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapRowsResponse(payload);
}

export async function fetchInputInvoiceUsageExportPreview(request: FetchRowsRequest): Promise<InputInvoiceUsageExportPreview> {
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/export-preview?${buildRowsQuery(request)}`, {
    method: "GET",
    signal: request.signal,
  });
  const raw = objectValue(unwrapData(payload));
  return {
    fileName: stringValue(camelOrSnake(raw, "fileName", "file_name") ?? "进项发票使用情况.xlsx"),
    rowCount: numberValue(camelOrSnake(raw, "rowCount", "row_count"), 0),
    scopeLabel: stringValue(camelOrSnake(raw, "scopeLabel", "scope_label")),
    columns: arrayValue(raw.columns).map(stringValue),
    sampleRows: arrayValue(camelOrSnake(raw, "sampleRows", "sample_rows")).map(objectStringMap),
    message: stringValue(raw.message),
  };
}

export async function downloadInputInvoiceUsageExport(request: FetchRowsRequest): Promise<InputInvoiceUsageExportDownload> {
  return requestExportBlob(`/api/input-invoice-usage/export?${buildRowsQuery(request)}`, {
    method: "GET",
    signal: request.signal,
  });
}

export async function fetchInputInvoiceUsageInvoiceDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/invoices/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapInvoiceDetailResponse(payload);
}

export async function fetchInputInvoiceUsageBankTransactionDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/bank-transactions/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapBankDetailResponse(payload);
}

export async function fetchInputInvoiceUsageOaDetail(id: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/oa/${encodeURIComponent(id)}/detail`, {
    method: "GET",
    signal,
  });
  return mapOaDetailResponse(payload);
}

export async function fetchInputInvoiceUsageRowRelationDetail(target: InputInvoiceUsageDetailTarget, signal?: AbortSignal) {
  const params = new URLSearchParams();
  params.set("kind", target.kind === "relationList" ? target.relationKind ?? "oa" : target.kind);
  if (target.scopeKey) {
    params.set("month", target.scopeKey);
  }
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/rows/${encodeURIComponent(target.rowId ?? target.id)}/relation-details?${params.toString()}`,
    { method: "GET", signal },
  );
  return mapRelationDetailResponse(payload);
}

export async function fetchInputInvoiceUsagePaymentStatusRules(signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/payment-status-rules", {
    method: "GET",
    signal,
  });
  return mapPaymentStatusRulesResponse(payload);
}

export async function saveInputInvoiceUsagePaymentStatusRules(
  request: SaveInputInvoiceUsagePaymentStatusRulesRequest,
) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/payment-status-rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expectedVersion: request.expectedVersion,
      idempotencyKey: request.idempotencyKey,
      rules: request.rules,
      pendingDirections: request.pendingDirections,
    }),
  });
  return mapPaymentStatusRulesResponse(payload);
}

export async function previewInputInvoiceUsageOaReverse(
  request: InputInvoiceUsageOaReversePreviewRequest,
  signal?: AbortSignal,
) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/oa-reverse/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source: request.source ?? (request.selectedInvoiceIds.length > 0 ? "explicitSelection" : "currentFilters"),
      filters: request.filters,
      invoiceIds: request.selectedInvoiceIds,
      ...(request.targetApplicantCode ? { targetApplicantCode: request.targetApplicantCode } : {}),
    }),
    signal,
  });
  return mapOaReversePreviewResponse(payload);
}

export async function createInputInvoiceUsageOaReverseBatch(
  request: CreateInputInvoiceUsageOaReverseBatchRequest,
) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/oa-reverse/batches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      previewId: request.previewId,
      ...(request.expectedPreviewHash ? { expectedPreviewHash: request.expectedPreviewHash } : {}),
      idempotencyKey: request.idempotencyKey,
      ...(request.selectedInvoiceIds ? { invoiceIds: request.selectedInvoiceIds } : {}),
      ...(request.targetApplicantCode ? { targetApplicantCode: request.targetApplicantCode } : {}),
    }),
  });
  return mapOaReverseBatch(payload);
}

export async function createInputInvoiceUsageOaReverseDraftFromSelection(
  request: CreateInputInvoiceUsageOaReverseDraftFromSelectionRequest,
) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/oa-reverse/oa-draft", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      previewId: request.previewId,
      ...(request.expectedPreviewHash ? { expectedPreviewHash: request.expectedPreviewHash } : {}),
      idempotencyKey: request.idempotencyKey,
      invoiceIds: request.selectedInvoiceIds,
      ...(request.targetApplicantCode ? { targetApplicantCode: request.targetApplicantCode } : {}),
    }),
  });
  return mapOaReverseBatch(payload);
}

export async function fetchInputInvoiceUsageOaReverseSubmittedHistory(signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/oa-reverse/submitted-history", {
    method: "GET",
    signal,
  });
  return mapOaReverseSubmittedHistory(payload);
}

export async function fetchInputInvoiceUsageOaReverseStagedDrafts(signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>("/api/input-invoice-usage/oa-reverse/staged-drafts", {
    method: "GET",
    signal,
  });
  return mapOaReverseStagedDrafts(payload);
}

export async function fetchInputInvoiceUsageOaReverseBatch(batchId: string, signal?: AbortSignal) {
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/oa-reverse/batches/${encodeURIComponent(batchId)}`,
    { method: "GET", signal },
  );
  return mapOaReverseBatch(payload);
}

export async function createInputInvoiceUsageOaReverseDraft(
  batchId: string,
  request: InputInvoiceUsageOaReverseVersionedRequest,
) {
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/oa-reverse/batches/${encodeURIComponent(batchId)}/oa-draft`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expectedVersion: request.expectedVersion,
        ...(request.idempotencyKey ? { idempotencyKey: request.idempotencyKey } : {}),
      }),
    },
  );
  return mapOaReverseBatch(payload);
}

export async function revokeInputInvoiceUsageOaReverseDraft(
  batchId: string,
  request: RevokeInputInvoiceUsageOaReverseDraftRequest,
) {
  const reason = request.reason.trim();
  if (!reason) {
    throw new Error("撤销原因不能为空。");
  }
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/oa-reverse/batches/${encodeURIComponent(batchId)}/oa-draft/revoke`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expectedVersion: request.expectedVersion,
        reason,
        ...(request.idempotencyKey ? { idempotencyKey: request.idempotencyKey } : {}),
      }),
    },
  );
  return mapOaReverseBatch(payload);
}

export async function refreshInputInvoiceUsageOaReverseStatus(
  batchId: string,
  request: Pick<InputInvoiceUsageOaReverseVersionedRequest, "expectedVersion">,
) {
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/oa-reverse/batches/${encodeURIComponent(batchId)}/oa-status/refresh`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedVersion: request.expectedVersion }),
    },
  );
  return mapOaReverseBatch(payload);
}

export async function manualInputInvoiceUsageOaReverseStatus(
  batchId: string,
  request: ManualInputInvoiceUsageOaReverseStatusRequest,
) {
  const reason = request.reason.trim();
  if (!reason) {
    throw new Error("人工处理原因不能为空。");
  }
  const payload = await apiRequestJson<unknown>(
    `/api/input-invoice-usage/oa-reverse/batches/${encodeURIComponent(batchId)}/manual-oa-status`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision: request.decision,
        expectedVersion: request.expectedVersion,
        reason,
        ...(request.candidateOaRowId ? { candidateOaRowId: request.candidateOaRowId } : {}),
        ...(request.idempotencyKey ? { idempotencyKey: request.idempotencyKey } : {}),
      }),
    },
  );
  return mapOaReverseBatch(payload);
}

export function nextSortDirection(currentField: string, currentDirection: InputInvoiceUsageSortDirection | "", field: string) {
  if (currentField !== field || !currentDirection) {
    return "asc";
  }
  return currentDirection === "asc" ? "desc" : "asc";
}
