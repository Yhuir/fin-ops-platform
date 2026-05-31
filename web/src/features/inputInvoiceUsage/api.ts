import { apiRequestJson } from "../apiClient";
import type {
  CreateInputInvoiceUsageOaReverseBatchRequest,
  InputInvoiceUsageDetailResponse,
  InputInvoiceUsageDetailTarget,
  InputInvoiceUsageFilter,
  InputInvoiceUsageFilterOptionsResponse,
  InputInvoiceUsageOaReverseBatch,
  InputInvoiceUsageOaReversePreviewRequest,
  InputInvoiceUsageOaReversePreviewResponse,
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

function mapInvoice(rawValue: unknown): InputInvoiceUsageRowsResponse["rows"][number]["invoice"] {
  const raw = objectValue(rawValue);
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
  if (!id && !applicant && !applicationType && !projectName) {
    return null;
  }
  return {
    id,
    applicant,
    applicationType,
    projectName,
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
    directionLabel: stringValue(camelOrSnake(raw, "directionLabel", "direction_label") ?? raw.direction),
    bankName: stringValue(camelOrSnake(raw, "bankName", "bank_name")),
    accountLast4: stringValue(camelOrSnake(raw, "accountLast4", "account_last4")),
    summary: stringValue(raw.summary),
    remark: stringValue(raw.remark),
    detailAvailable: booleanValue(camelOrSnake(raw, "detailAvailable", "detail_available")),
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
      return {
        id: stringValue(row.id),
        invoice: {
          ...mapInvoice(row.invoice),
          id: stringValue(camelOrSnake(row, "invoiceId", "invoice_id") ?? objectValue(row.invoice).id),
        },
        paymentStatus: mapPaymentStatus(camelOrSnake(row, "paymentStatus", "payment_status")),
        oa: mapRelation(row.oa, mapOa),
        bank: mapRelation(camelOrSnake(row, "bank", "bankTransactions"), mapBank),
      };
    }),
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
    readModelStatus: stringValue(camelOrSnake(raw, "readModelStatus", "read_model_status")),
    readModelScopeKey: stringValue(camelOrSnake(raw, "readModelScopeKey", "read_model_scope_key")),
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
  const kind = stringValue(raw.kind) === "bank" ? "流水" : "OA";
  const summaries = arrayValue(raw.summaries);
  const sections: InputInvoiceUsageDetailResponse["sections"] = [
    detailSection("关联概况", [
      detailField("发票行 ID", camelOrSnake(raw, "invoiceId", "invoice_id")),
      detailField("关系类型", kind),
      detailField("关系数量", camelOrSnake(raw, "relationCount", "relation_count")),
      detailField("是否多条", camelOrSnake(raw, "hasMultiple", "has_multiple") ? "是" : "否"),
    ]),
  ];
  if (summaries.length > 0) {
    sections.push(detailSection("关联摘要", summaries.map((item, index) => detailField(`${kind} ${index + 1}`, item))));
  }
  const relations = arrayValue(raw.relations);
  if (relations.length > 0) {
    sections.push(detailSection("关联台证据", relations.map((item, index) => detailField(`关系 ${index + 1}`, item))));
  }
  return {
    title: `${kind}关联明细`,
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
    readModelStatus: stringValue(camelOrSnake(raw, "readModelStatus", "read_model_status")),
    readModelScopeKey: stringValue(camelOrSnake(raw, "readModelScopeKey", "read_model_scope_key")),
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
        label: stringValue(rule.label),
        description: stringValue(rule.description),
        priority: numberValue(rule.priority, 0),
        enabled: rule.enabled === undefined ? undefined : booleanValue(rule.enabled),
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
  return {
    invoiceId,
    invoiceNumber: stringValue(camelOrSnake(raw, "invoiceNumber", "invoice_number") ?? camelOrSnake(raw, "invoiceNo", "invoice_no") ?? displayNo),
    displayNo,
    sellerName: stringValue(camelOrSnake(raw, "sellerName", "seller_name")),
    issueDate: stringValue(camelOrSnake(raw, "issueDate", "issue_date") ?? camelOrSnake(raw, "invoiceDate", "invoice_date")),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    paymentStatusLabel: stringValue(camelOrSnake(raw, "paymentStatusLabel", "payment_status_label") ?? camelOrSnake(raw, "statusLabel", "status_label") ?? raw.status),
    targetApplicantName: stringValue(camelOrSnake(raw, "targetApplicantName", "target_applicant_name")),
  };
}

function mapRejectedInvoice(rawValue: unknown) {
  const raw = objectValue(rawValue);
  return {
    invoiceId: stringValue(camelOrSnake(raw, "invoiceId", "invoice_id") ?? raw.id),
    invoiceNumber: stringValue(camelOrSnake(raw, "invoiceNumber", "invoice_number") ?? camelOrSnake(raw, "invoiceNo", "invoice_no")),
    reasonCode: stringValue(camelOrSnake(raw, "reasonCode", "reason_code")),
    reason: stringValue(raw.reason),
  };
}

function mapOaReversePreviewResponse(payload: unknown): InputInvoiceUsageOaReversePreviewResponse {
  const raw = objectValue(unwrapData(payload));
  const topLevelCandidates = arrayValue(camelOrSnake(raw, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice);
  const groups = arrayValue(raw.groups).map((item) => {
    const group = objectValue(item);
    const groupCandidates = arrayValue(camelOrSnake(group, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice);
    const candidateIds = arrayValue(camelOrSnake(group, "candidateInvoiceIds", "candidate_invoice_ids")).map(stringValue);
    return {
      targetApplicantCode: stringValue(camelOrSnake(group, "targetApplicantCode", "target_applicant_code")) || null,
      targetApplicantName: stringValue(camelOrSnake(group, "targetApplicantName", "target_applicant_name")),
      invoiceCount: numberValue(camelOrSnake(group, "invoiceCount", "invoice_count"), groupCandidates.length || candidateIds.length),
      totalWithTax: stringValue(camelOrSnake(group, "totalWithTax", "total_with_tax")),
      candidateInvoiceIds: candidateIds,
      candidateInvoices: groupCandidates,
      rejectedInvoices: arrayValue(camelOrSnake(group, "rejectedInvoices", "rejected_invoices")).map(mapRejectedInvoice),
    };
  });
  return {
    previewId: stringValue(camelOrSnake(raw, "previewId", "preview_id")),
    previewHash: stringValue(camelOrSnake(raw, "previewHash", "preview_hash") ?? camelOrSnake(raw, "expectedPreviewHash", "expected_preview_hash")),
    source: stringValue(raw.source),
    invoiceCount: numberValue(camelOrSnake(raw, "invoiceCount", "invoice_count"), topLevelCandidates.length),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    groups,
    candidateInvoices: topLevelCandidates,
    warnings: arrayValue(raw.warnings).map(stringValue),
    canCreateDraft: booleanValue(camelOrSnake(raw, "canCreateDraft", "can_create_draft")),
    nextAction: stringValue(camelOrSnake(raw, "nextAction", "next_action")),
    unavailableReason: stringValue(camelOrSnake(raw, "unavailableReason", "unavailable_reason")),
    permissions: {
      canCreateBatch: booleanValue(camelOrSnake(objectValue(raw.permissions), "canCreateBatch", "can_create_batch")),
      canCreateDraft: booleanValue(camelOrSnake(objectValue(raw.permissions), "canCreateDraft", "can_create_draft")),
      canRevoke: booleanValue(camelOrSnake(objectValue(raw.permissions), "canRevoke", "can_revoke")),
      canManualStatus: booleanValue(camelOrSnake(objectValue(raw.permissions), "canManualStatus", "can_manual_status")),
    },
  };
}

function mapOaReverseBatch(payload: unknown): InputInvoiceUsageOaReverseBatch {
  const raw = objectValue(unwrapData(payload));
  return {
    batchId: stringValue(camelOrSnake(raw, "batchId", "batch_id") ?? raw.id),
    version: numberValue(raw.version, 0),
    status: stringValue(raw.status),
    selectedInvoiceIds: arrayValue(camelOrSnake(raw, "selectedInvoiceIds", "selected_invoice_ids")).map(stringValue),
    totalWithTax: stringValue(camelOrSnake(raw, "totalWithTax", "total_with_tax")),
    targetApplicantCode: stringValue(camelOrSnake(raw, "targetApplicantCode", "target_applicant_code")) || null,
    targetApplicantName: stringValue(camelOrSnake(raw, "targetApplicantName", "target_applicant_name")) || null,
    invoices: arrayValue(raw.invoices ?? camelOrSnake(raw, "candidateInvoices", "candidate_invoices")).map(mapOaReverseInvoice),
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
    canRevoke: camelOrSnake(raw, "canRevoke", "can_revoke") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canRevoke", "can_revoke")),
    canRefreshStatus: camelOrSnake(raw, "canRefreshStatus", "can_refresh_status") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canRefreshStatus", "can_refresh_status")),
    canManualStatus: camelOrSnake(raw, "canManualStatus", "can_manual_status") === undefined ? undefined : booleanValue(camelOrSnake(raw, "canManualStatus", "can_manual_status")),
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

export async function fetchInputInvoiceUsageFilterOptions(
  request: Pick<FetchRowsRequest, "keyword" | "invoiceDateFrom" | "invoiceDateTo" | "month" | "filters" | "signal">,
): Promise<InputInvoiceUsageFilterOptionsResponse> {
  const params = new URLSearchParams();
  appendRowsQuery(params, { ...request, page: 1, pageSize: 1, sortField: "", sortDirection: "" });
  const payload = await apiRequestJson<unknown>(`/api/input-invoice-usage/filter-options?${params.toString()}`, {
    method: "GET",
    signal: request.signal,
  });
  return mapFilterOptionsResponse(payload);
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
