import type {
  ConfirmTurnoverRelationRequest,
  FetchTurnoverLedgerRequest,
  SaveTurnoverLedgerExtraRequest,
  SaveTurnoverLedgerExtraResponse,
  TurnoverBankRow,
  TurnoverLedgerChip,
  TurnoverLedgerExportDownload,
  TurnoverLedgerExportPreview,
  TurnoverLedgerExportRow,
  TurnoverLedgerFamilySummary,
  TurnoverLedgerGroup,
  TurnoverLedgerGroupedResponse,
  TurnoverLedgerGroupedRow,
  TurnoverLedgerExtra,
  TurnoverLedgerResponse,
  TurnoverLedgerRow,
  TurnoverLedgerSummary,
  TurnoverRelationDetail,
  TurnoverRelationMutationResponse,
  WithdrawTurnoverRelationRequest,
} from "./types";

type ApiTurnoverLedgerChip = string | {
  label?: string | null;
  tone?: string | null;
};

type ApiTurnoverLedgerSummary = {
  pending_repayment_amount?: string | null;
  repaid_amount?: string | null;
  pending_collection_amount?: string | null;
  collected_amount?: string | null;
  closed_amount?: string | null;
  suggested_count?: number | null;
  conflict_count?: number | null;
  row_count?: number | null;
};

type ApiTurnoverLedgerFamilySummary = {
  family?: string | null;
  label?: string | null;
  pending_amount?: string | null;
  closed_amount?: string | null;
  row_count?: number | null;
};

type ApiTurnoverLedgerRow = {
  relation_id?: string | null;
  status?: string | null;
  status_label?: string | null;
  row_tone?: string | null;
  chips?: ApiTurnoverLedgerChip[];
  family?: string | null;
  family_label?: string | null;
  counterparty_name?: string | null;
  principal_amount?: string | null;
  settled_amount?: string | null;
  balance_amount?: string | null;
  first_transaction_at?: string | null;
  last_settlement_at?: string | null;
  bank_account_labels?: string[];
  summary_text?: string | null;
  annual_interest_rate?: string | null;
  loan_days?: number | null;
  accrued_interest?: string | null;
  sync_to_workbench?: boolean | null;
  bank_row_ids?: string[];
  category_codes?: string[];
  business_type?: string | null;
};

type ApiTurnoverLedgerResponse = {
  summary?: ApiTurnoverLedgerSummary;
  family_summaries?: ApiTurnoverLedgerFamilySummary[] | Record<string, ApiTurnoverLedgerSummary & ApiTurnoverLedgerFamilySummary>;
  rows?: ApiTurnoverLedgerRow[];
  pagination?: {
    page?: number | null;
    page_size?: number | null;
    total?: number | null;
  };
};

type ApiTurnoverLedgerGroupedRow = {
  row_kind?: string | null;
  relation_id?: string | null;
  lot_id?: string | null;
  parent_relation_id?: string | null;
  principal_bank_row_id?: string | null;
  settlement_bank_row_ids?: string[];
  status?: string | null;
  status_label?: string | null;
  row_tone?: string | null;
  borrow_amount?: string | null;
  borrow_date?: string | null;
  borrow_direction?: string | null;
  repayment_amount?: string | null;
  repayment_date?: string | null;
  repayment_direction?: string | null;
  balance_amount?: string | null;
  counterparty_bank_name?: string | null;
  repayment_remark?: string | null;
  interest_rate_type?: string | null;
  interest_rate_value?: string | null;
  interest_paid_amount?: string | null;
  loan_days?: number | null;
  accrued_interest?: string | null;
  interest_paid_date?: string | null;
  interest_payment_method?: string | null;
  note?: string | null;
  bank_row_ids?: string[];
};

type ApiTurnoverLedgerGroup = {
  group_id?: string | null;
  counterparty_name?: string | null;
  family?: string | null;
  family_label?: string | null;
  pending_direction?: string | null;
  pending_direction_label?: string | null;
  pending_amount?: string | null;
  pending_repayment_amount?: string | null;
  pending_collection_amount?: string | null;
  closed_amount?: string | null;
  row_span?: number | null;
  group_tone?: string | null;
  summary_row?: ApiTurnoverLedgerGroupedRow | null;
  lot_rows?: ApiTurnoverLedgerGroupedRow[];
  rows?: ApiTurnoverLedgerGroupedRow[];
};

type ApiTurnoverLedgerGroupedResponse = {
  summary?: ApiTurnoverLedgerSummary;
  family_summaries?: ApiTurnoverLedgerResponse["family_summaries"];
  groups?: ApiTurnoverLedgerGroup[];
  pagination?: ApiTurnoverLedgerResponse["pagination"];
};

type ApiTurnoverLedgerExtra = {
  relation_id?: string | null;
  interest_rate_type?: string | null;
  interest_rate_value?: string | null;
  interest_paid_amount?: string | null;
  interest_paid_date?: string | null;
  interest_payment_method?: string | null;
  note?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
};

type ApiSaveTurnoverLedgerExtraResponse = {
  extra?: ApiTurnoverLedgerExtra;
  row?: ApiTurnoverLedgerGroupedRow | null;
};

type ApiTurnoverLedgerExportSummary = {
  row_count?: number | null;
  pending_repayment_amount?: string | null;
  pending_collection_amount?: string | null;
  accrued_interest?: string | null;
};

type ApiTurnoverLedgerExportRow = {
  sequence_no?: number | null;
  row_type?: string | null;
  lot_id?: string | null;
  family_label?: string | null;
  counterparty_name?: string | null;
  pending_repayment_amount?: string | null;
  pending_collection_amount?: string | null;
  balance_amount?: string | null;
  borrow_amount?: string | null;
  borrow_date?: string | null;
  repayment_amount?: string | null;
  repayment_date?: string | null;
  counterparty_bank_name?: string | null;
  repayment_remark?: string | null;
  interest_rate_type?: string | null;
  interest_rate_value?: string | null;
  interest_paid_amount?: string | null;
  loan_days?: number | null;
  accrued_interest?: string | null;
  interest_paid_date?: string | null;
  interest_payment_method?: string | null;
  note?: string | null;
  status_label?: string | null;
  status?: string | null;
};

type ApiTurnoverLedgerExportPreview = {
  file_name?: string | null;
  scope_label?: string | null;
  summary?: ApiTurnoverLedgerExportSummary;
  columns?: string[];
  rows?: ApiTurnoverLedgerExportRow[];
};

type ApiTurnoverBankRow = {
  id?: string | null;
  trade_time?: string | null;
  counterparty_name?: string | null;
  counterparty_name_raw?: string | null;
  direction?: string | null;
  txn_direction?: string | null;
  direction_label?: string | null;
  amount?: string | null;
  debit_amount?: string | null;
  credit_amount?: string | null;
  bank_account_label?: string | null;
  imported_bank_name?: string | null;
  imported_bank_last4?: string | null;
  bank_name?: string | null;
  account_last4?: string | null;
  summary?: string | null;
  remark?: string | null;
  purpose?: string | null;
  category_label?: string | null;
};

type ApiTurnoverRelationDetail = {
  relation?: ApiTurnoverLedgerRow;
  row?: ApiTurnoverLedgerRow;
  bank_rows?: ApiTurnoverBankRow[];
  audit_history?: Array<Record<string, unknown>>;
};

type ApiTurnoverRelationMutationResponse = {
  relation_id?: string | null;
  status?: string | null;
  relation?: ApiTurnoverLedgerRow;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const rawText = await response.text();
  const trimmedText = rawText.trim();
  const contentType = response.headers?.get?.("Content-Type") ?? "";
  if (trimmedText && looksLikeHtml(trimmedText)) {
    throw new Error(
      `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务已启动，并通过支持 /api 代理的前端开发服务访问。`,
    );
  }

  let payload = {} as T;
  if (trimmedText) {
    try {
      payload = JSON.parse(trimmedText) as T;
    } catch {
      throw new Error(
        contentType
          ? `接口 ${url} 返回的不是合法 JSON：${contentType}`
          : `接口 ${url} 返回的不是合法 JSON。`,
      );
    }
  }
  if (!response.ok) {
    throw new Error(extractErrorMessage(payload) || trimmedText || "request failed");
  }
  return payload;
}

async function requestBlob(url: string, init: RequestInit = {}): Promise<TurnoverLedgerExportDownload> {
  const response = await fetch(url, init);
  const contentType = response.headers?.get?.("Content-Type") ?? "";

  if (contentType.toLowerCase().includes("text/html")) {
    const rawText = await response.text();
    if (looksLikeHtml(rawText)) {
      throw new Error(
        `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务已启动，并通过支持 /api 代理的前端开发服务访问。`,
      );
    }
    throw new Error(rawText || `接口 ${url} 返回的不是 xlsx 文件：${contentType}`);
  }

  if (!response.ok) {
    const rawText = await response.text();
    if (looksLikeHtml(rawText)) {
      throw new Error(
        `接口返回了 HTML 页面：${url}。说明请求没有进入后端 API，请确认后端服务已启动，并通过支持 /api 代理的前端开发服务访问。`,
      );
    }
    let payload: unknown = {};
    if (rawText.trim()) {
      try {
        payload = JSON.parse(rawText);
      } catch {
        payload = {};
      }
    }
    throw new Error(extractErrorMessage(payload) || rawText || "request failed");
  }

  const blob = await response.blob();
  const contentDisposition = response.headers?.get?.("Content-Disposition") ?? null;
  return {
    blob,
    fileName: parseContentDispositionFileName(contentDisposition) ?? "往来款台账.xlsx",
  };
}

function looksLikeHtml(rawText: string) {
  const trimmedText = rawText.trim();
  return /^<!doctype\s+html/i.test(trimmedText) || /^<html[\s>]/i.test(trimmedText);
}

function extractErrorMessage(payload: unknown) {
  if (payload && typeof payload === "object" && "message" in payload) {
    const message = (payload as { message?: unknown }).message;
    return typeof message === "string" ? message : "";
  }
  return "";
}

function text(value: string | null | undefined, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function moneyNumber(value: string | null | undefined) {
  const parsed = Number(String(value ?? "").replace(/,/g, "").trim());
  return Number.isFinite(parsed) ? parsed : 0;
}

function numberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : 0;
}

function nullableNumberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : null;
}

function stringList(value: string[] | undefined) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
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

function normalizeTone(value: string | null | undefined): TurnoverLedgerRow["rowTone"] {
  if (value === "success" || value === "warning" || value === "info" || value === "danger" || value === "error" || value === "muted") {
    return value;
  }
  return "muted";
}

function mapChip(chip: ApiTurnoverLedgerChip): TurnoverLedgerChip {
  if (typeof chip === "string") {
    return { label: chip };
  }
  return {
    label: text(chip.label),
    tone: normalizeTone(chip.tone),
  };
}

function mapSummary(summary: ApiTurnoverLedgerSummary | undefined): TurnoverLedgerSummary {
  return {
    pendingRepaymentAmount: text(summary?.pending_repayment_amount, "0.00"),
    repaidAmount: text(summary?.repaid_amount, "0.00"),
    pendingCollectionAmount: text(summary?.pending_collection_amount, "0.00"),
    collectedAmount: text(summary?.collected_amount, "0.00"),
    closedAmount: text(summary?.closed_amount, "0.00"),
    suggestedCount: numberValue(summary?.suggested_count),
    conflictCount: numberValue(summary?.conflict_count),
    rowCount: numberValue(summary?.row_count),
  };
}

function mapFamilySummary(summary: ApiTurnoverLedgerFamilySummary): TurnoverLedgerFamilySummary {
  return {
    family: text(summary.family),
    label: text(summary.label),
    pendingAmount: text(summary.pending_amount, "0.00"),
    closedAmount: text(summary.closed_amount, "0.00"),
    rowCount: numberValue(summary.row_count),
  };
}

function mapFamilySummaries(
  familySummaries: ApiTurnoverLedgerResponse["family_summaries"],
): TurnoverLedgerFamilySummary[] {
  if (Array.isArray(familySummaries)) {
    return familySummaries.map(mapFamilySummary);
  }
  if (!familySummaries || typeof familySummaries !== "object") {
    return [];
  }
  return Object.entries(familySummaries).map(([family, summary]) => {
    const pendingAmount = Number((summary.pending_repayment_amount ?? "0").replace(/,/g, ""))
      + Number((summary.pending_collection_amount ?? "0").replace(/,/g, ""));
    return {
      family,
      label: text(summary.label, family),
      pendingAmount: Number.isFinite(pendingAmount) ? pendingAmount.toFixed(2) : "0.00",
      closedAmount: text(summary.closed_amount, "0.00"),
      rowCount: numberValue(summary.row_count),
    };
  });
}

function mapRow(row: ApiTurnoverLedgerRow): TurnoverLedgerRow {
  return {
    relationId: text(row.relation_id),
    status: text(row.status),
    statusLabel: text(row.status_label),
    rowTone: normalizeTone(row.row_tone),
    chips: Array.isArray(row.chips) ? row.chips.map(mapChip).filter((chip) => chip.label) : [],
    family: text(row.family),
    familyLabel: text(row.family_label),
    counterpartyName: text(row.counterparty_name),
    principalAmount: text(row.principal_amount, "0.00"),
    settledAmount: text(row.settled_amount, "0.00"),
    balanceAmount: text(row.balance_amount, "0.00"),
    firstTransactionAt: row.first_transaction_at ?? null,
    lastSettlementAt: row.last_settlement_at ?? null,
    bankAccountLabels: stringList(row.bank_account_labels),
    summaryText: text(row.summary_text),
    annualInterestRate: row.annual_interest_rate ?? null,
    loanDays: row.loan_days ?? null,
    accruedInterest: row.accrued_interest ?? null,
    syncToWorkbench: Boolean(row.sync_to_workbench),
    bankRowIds: stringList(row.bank_row_ids),
    categoryCodes: stringList(row.category_codes),
    businessType: row.business_type ?? null,
  };
}

function mapGroupedRow(row: ApiTurnoverLedgerGroupedRow, fallbackRowKind = ""): TurnoverLedgerGroupedRow {
  return {
    rowKind: text(row.row_kind, fallbackRowKind),
    relationId: text(row.relation_id),
    lotId: text(row.lot_id),
    parentRelationId: text(row.parent_relation_id),
    principalBankRowId: text(row.principal_bank_row_id),
    settlementBankRowIds: stringList(row.settlement_bank_row_ids),
    status: text(row.status),
    statusLabel: text(row.status_label),
    rowTone: normalizeTone(row.row_tone),
    borrowAmount: text(row.borrow_amount, "0.00"),
    borrowDate: row.borrow_date ?? null,
    borrowDirection: text(row.borrow_direction),
    repaymentAmount: text(row.repayment_amount, "0.00"),
    repaymentDate: row.repayment_date ?? null,
    repaymentDirection: text(row.repayment_direction),
    balanceAmount: text(row.balance_amount, "0.00"),
    counterpartyBankName: text(row.counterparty_bank_name),
    repaymentRemark: text(row.repayment_remark),
    interestRateType: text(row.interest_rate_type, "none"),
    interestRateValue: text(row.interest_rate_value, "0.000000"),
    interestPaidAmount: text(row.interest_paid_amount, "0.00"),
    loanDays: nullableNumberValue(row.loan_days),
    accruedInterest: text(row.accrued_interest, "0.00"),
    interestPaidDate: row.interest_paid_date ?? null,
    interestPaymentMethod: text(row.interest_payment_method),
    note: text(row.note),
    bankRowIds: stringList(row.bank_row_ids),
  };
}

function mapGroup(group: ApiTurnoverLedgerGroup): TurnoverLedgerGroup {
  const rows = (group.rows ?? []).map((row) => mapGroupedRow(row));
  const summaryRow = group.summary_row
    ? mapGroupedRow(group.summary_row, "summary")
    : rows[0]
      ? { ...rows[0], rowKind: rows[0].rowKind || "summary" }
      : null;
  const lotRows = (group.lot_rows ?? []).map((row) => mapGroupedRow(row, "lot"));
  const pendingDirection = text(group.pending_direction, "closed");
  const pendingAmount = text(group.pending_amount, "0.00");
  return {
    groupId: text(group.group_id),
    counterpartyName: text(group.counterparty_name),
    family: text(group.family),
    familyLabel: text(group.family_label),
    pendingDirection,
    pendingDirectionLabel: text(group.pending_direction_label, "已闭合"),
    pendingAmount,
    pendingRepaymentAmount: text(group.pending_repayment_amount, pendingDirection === "repayment" ? pendingAmount : "0.00"),
    pendingCollectionAmount: text(group.pending_collection_amount, pendingDirection === "collection" ? pendingAmount : "0.00"),
    closedAmount: text(group.closed_amount, pendingDirection === "closed" ? pendingAmount : "0.00"),
    rowSpan: numberValue(group.row_span) || rows.length,
    groupTone: normalizeTone(group.group_tone),
    rows,
    summaryRow,
    lotRows,
  };
}

function mapExtra(extra: ApiTurnoverLedgerExtra, relationId = ""): TurnoverLedgerExtra {
  return {
    relationId: text(extra.relation_id, relationId),
    interestRateType: text(extra.interest_rate_type, "none"),
    interestRateValue: text(extra.interest_rate_value, "0.000000"),
    interestPaidAmount: text(extra.interest_paid_amount, "0.00"),
    interestPaidDate: extra.interest_paid_date ?? null,
    interestPaymentMethod: text(extra.interest_payment_method),
    note: text(extra.note),
    updatedAt: extra.updated_at ?? null,
    updatedBy: text(extra.updated_by),
  };
}

function mapExportRow(row: ApiTurnoverLedgerExportRow): TurnoverLedgerExportRow {
  return {
    sequenceNo: numberValue(row.sequence_no),
    rowType: text(row.row_type),
    lotId: text(row.lot_id),
    familyLabel: text(row.family_label),
    counterpartyName: text(row.counterparty_name),
    pendingRepaymentAmount: text(row.pending_repayment_amount, "0.00"),
    pendingCollectionAmount: text(row.pending_collection_amount, "0.00"),
    balanceAmount: text(row.balance_amount, "0.00"),
    borrowAmount: text(row.borrow_amount, "0.00"),
    borrowDate: row.borrow_date ?? null,
    repaymentAmount: text(row.repayment_amount, "0.00"),
    repaymentDate: row.repayment_date ?? null,
    counterpartyBankName: text(row.counterparty_bank_name),
    repaymentRemark: text(row.repayment_remark),
    interestRateType: text(row.interest_rate_type, "none"),
    interestRateValue: text(row.interest_rate_value, "0.000000"),
    interestPaidAmount: text(row.interest_paid_amount, "0.00"),
    loanDays: nullableNumberValue(row.loan_days),
    accruedInterest: text(row.accrued_interest, "0.00"),
    interestPaidDate: row.interest_paid_date ?? null,
    interestPaymentMethod: text(row.interest_payment_method),
    note: text(row.note),
    statusLabel: text(row.status_label ?? row.status),
  };
}

function mapBankRow(row: ApiTurnoverBankRow): TurnoverBankRow {
  const debitAmount = text(row.debit_amount);
  const creditAmount = text(row.credit_amount);
  const debitNumber = moneyNumber(debitAmount);
  const creditNumber = moneyNumber(creditAmount);
  const direction = text(row.direction ?? row.txn_direction).toLowerCase();
  const directionLabel = text(
    row.direction_label,
    debitNumber > 0
      ? "支"
      : creditNumber > 0
        ? "收"
        : direction === "outflow" || direction === "expense"
          ? "支"
          : direction === "inflow" || direction === "income"
            ? "收"
            : "",
  );
  const bankName = text(row.imported_bank_name ?? row.bank_name);
  const last4 = text(row.imported_bank_last4 ?? row.account_last4);
  return {
    id: text(row.id),
    tradeTime: row.trade_time ?? null,
    counterpartyName: text(row.counterparty_name ?? row.counterparty_name_raw),
    directionLabel,
    amount: text(row.amount, debitNumber > 0 ? debitAmount : creditNumber > 0 ? creditAmount : "0.00"),
    bankAccountLabel: text(row.bank_account_label, [bankName, last4].filter(Boolean).join(" ")),
    summary: [row.summary, row.purpose, row.remark].map((value) => text(value)).filter(Boolean).join(" / "),
    purpose: row.purpose ?? null,
    categoryLabel: row.category_label ?? null,
  };
}

function mapMutation(payload: ApiTurnoverRelationMutationResponse): TurnoverRelationMutationResponse {
  const relation = payload.relation;
  return {
    relationId: text(payload.relation_id ?? relation?.relation_id),
    status: text(payload.status ?? relation?.status),
  };
}

export async function fetchTurnoverLedger({
  family = "all",
  status,
  page = 1,
  pageSize = 100,
  signal,
}: FetchTurnoverLedgerRequest = {}): Promise<TurnoverLedgerResponse> {
  const params = new URLSearchParams();
  params.set("family", family);
  if (status) {
    params.set("status", status);
  }
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const payload = await requestJson<ApiTurnoverLedgerResponse>(`/api/turnover-ledger?${params.toString()}`, {
    method: "GET",
    signal,
  });
  return {
    summary: mapSummary(payload.summary),
    familySummaries: mapFamilySummaries(payload.family_summaries),
    rows: (payload.rows ?? []).map(mapRow),
    pagination: {
      page: payload.pagination?.page ?? page,
      pageSize: payload.pagination?.page_size ?? pageSize,
      total: payload.pagination?.total ?? payload.rows?.length ?? 0,
    },
  };
}

export async function fetchTurnoverLedgerGrouped({
  family = "all",
  status,
  page = 1,
  pageSize = 100,
  signal,
}: FetchTurnoverLedgerRequest = {}): Promise<TurnoverLedgerGroupedResponse> {
  const params = new URLSearchParams();
  params.set("view", "grouped");
  params.set("family", family);
  if (status) {
    params.set("status", status);
  }
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  const payload = await requestJson<ApiTurnoverLedgerGroupedResponse>(`/api/turnover-ledger?${params.toString()}`, {
    method: "GET",
    signal,
  });
  return {
    summary: mapSummary(payload.summary),
    familySummaries: mapFamilySummaries(payload.family_summaries),
    groups: (payload.groups ?? []).map(mapGroup),
    pagination: {
      page: payload.pagination?.page ?? page,
      pageSize: payload.pagination?.page_size ?? pageSize,
      total: payload.pagination?.total ?? payload.groups?.length ?? 0,
    },
  };
}

export async function fetchTurnoverRelationDetail(
  relationId: string,
  signal?: AbortSignal,
): Promise<TurnoverRelationDetail> {
  const payload = await requestJson<ApiTurnoverRelationDetail>(
    `/api/turnover-ledger/relations/${encodeURIComponent(relationId)}`,
    { method: "GET", signal },
  );
  return {
    relation: mapRow(payload.row ?? payload.relation ?? { relation_id: relationId }),
    bankRows: (payload.bank_rows ?? []).map(mapBankRow),
    auditHistory: payload.audit_history ?? [],
  };
}

export async function fetchTurnoverRelationExtra(
  relationId: string,
  signal?: AbortSignal,
): Promise<TurnoverLedgerExtra> {
  const payload = await requestJson<ApiTurnoverLedgerExtra | { extra?: ApiTurnoverLedgerExtra }>(
    `/api/turnover-ledger/relations/${encodeURIComponent(relationId)}/extra`,
    { method: "GET", signal },
  );
  const extra = (payload as { extra?: ApiTurnoverLedgerExtra }).extra ?? (payload as ApiTurnoverLedgerExtra);
  return mapExtra(extra, relationId);
}

export async function saveTurnoverRelationExtra(
  relationId: string,
  { signal, ...extra }: SaveTurnoverLedgerExtraRequest,
): Promise<SaveTurnoverLedgerExtraResponse> {
  const body: Record<string, string | null> = {};
  if (extra.interestRateType !== undefined) {
    body.interest_rate_type = extra.interestRateType;
  }
  if (extra.interestRateValue !== undefined) {
    body.interest_rate_value = extra.interestRateValue;
  }
  if (extra.interestPaidAmount !== undefined) {
    body.interest_paid_amount = extra.interestPaidAmount;
  }
  if (extra.interestPaidDate !== undefined) {
    body.interest_paid_date = extra.interestPaidDate;
  }
  if (extra.interestPaymentMethod !== undefined) {
    body.interest_payment_method = extra.interestPaymentMethod;
  }
  if (extra.note !== undefined) {
    body.note = extra.note;
  }

  const payload = await requestJson<ApiSaveTurnoverLedgerExtraResponse>(
    `/api/turnover-ledger/relations/${encodeURIComponent(relationId)}/extra`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal,
    },
  );
  return {
    extra: mapExtra(payload.extra ?? { relation_id: relationId }, relationId),
    row: payload.row ? mapGroupedRow(payload.row) : null,
  };
}

export async function fetchTurnoverLedgerExportPreview(
  {
    family = "all",
    signal,
  }: Pick<FetchTurnoverLedgerRequest, "family" | "signal"> = {},
): Promise<TurnoverLedgerExportPreview> {
  const params = new URLSearchParams();
  params.set("family", family);
  const payload = await requestJson<ApiTurnoverLedgerExportPreview>(
    `/api/turnover-ledger/export-preview?${params.toString()}`,
    { method: "GET", signal },
  );
  return {
    fileName: text(payload.file_name, "往来款台账.xlsx"),
    scopeLabel: text(payload.scope_label),
    summary: {
      rowCount: numberValue(payload.summary?.row_count),
      pendingRepaymentAmount: text(payload.summary?.pending_repayment_amount, "0.00"),
      pendingCollectionAmount: text(payload.summary?.pending_collection_amount, "0.00"),
      accruedInterest: text(payload.summary?.accrued_interest, "0.00"),
    },
    columns: stringList(payload.columns),
    rows: (payload.rows ?? []).map(mapExportRow),
  };
}

export async function downloadTurnoverLedgerExport(
  {
    family = "all",
    signal,
  }: Pick<FetchTurnoverLedgerRequest, "family" | "signal"> = {},
): Promise<TurnoverLedgerExportDownload> {
  const params = new URLSearchParams();
  params.set("family", family);
  return requestBlob(`/api/turnover-ledger/export?${params.toString()}`, {
    method: "GET",
    signal,
  });
}

export async function confirmTurnoverRelation({
  bankRowIds,
  note,
  signal,
}: ConfirmTurnoverRelationRequest): Promise<TurnoverRelationMutationResponse> {
  const payload = await requestJson<ApiTurnoverRelationMutationResponse>(
    "/api/turnover-ledger/relations/confirm",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        bank_row_ids: bankRowIds,
        ...(note ? { note } : {}),
      }),
      signal,
    },
  );
  return mapMutation(payload);
}

export async function withdrawTurnoverRelation({
  relationId,
  note,
  signal,
}: WithdrawTurnoverRelationRequest): Promise<TurnoverRelationMutationResponse> {
  const payload = await requestJson<ApiTurnoverRelationMutationResponse>(
    `/api/turnover-ledger/relations/${encodeURIComponent(relationId)}/withdraw`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(note ? { note } : {}),
      signal,
    },
  );
  return mapMutation(payload);
}
