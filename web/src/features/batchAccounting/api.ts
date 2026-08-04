import type {
  BatchAccountingAmountCheck,
  BatchAccountingBankRow,
  BatchAccountingMutationResult,
  BatchAccountingOaRow,
  BatchAccountingPageInfo,
  BatchAccountingRelation,
  BatchAccountingResponse,
  BatchAccountingTagRules,
  FetchBatchAccountingRequest,
  SubmitBatchAccountingRequest,
  SaveBatchAccountingTagRulesRequest,
  WithdrawBatchAccountingRequest,
} from "./types";
import { apiRequestJson } from "../apiClient";

type ApiBankRow = {
  id?: string | null;
  trade_time?: string | null;
  tradeTime?: string | null;
  counterparty_name?: string | null;
  counterpartyName?: string | null;
  direction?: string | null;
  direction_label?: string | null;
  directionLabel?: string | null;
  amount?: string | null;
  bank_name?: string | null;
  bankName?: string | null;
  account_last4?: string | null;
  accountLast4?: string | null;
  relation_id?: string | null;
  relationId?: string | null;
  version?: number | null;
  tag_code?: string | null;
  tagCode?: string | null;
  tag_label?: string | null;
  tagLabel?: string | null;
  tag_primary_label?: string | null;
  tagPrimaryLabel?: string | null;
  tag_sub_label?: string | null;
  tagSubLabel?: string | null;
};

type ApiOaRow = {
  id?: string | null;
  applicant?: string | null;
  apply_time?: string | null;
  applyTime?: string | null;
  project_name?: string | null;
  projectName?: string | null;
  amount?: string | null;
  reason?: string | null;
  linked_invoice_row_ids?: string[] | null;
  linkedInvoiceRowIds?: string[] | null;
};

type ApiSummary = {
  unsubmitted_count?: number | null;
  unsubmittedCount?: number | null;
  submitted_count?: number | null;
  submittedCount?: number | null;
};

type ApiAmountCheck = {
  status?: string | null;
  direction?: string | null;
  bank_amount?: string | null;
  bankAmount?: string | null;
  oa_amount?: string | null;
  oaAmount?: string | null;
  amount_delta?: string | null;
  amountDelta?: string | null;
  requires_note?: boolean | null;
  requiresNote?: boolean | null;
};

type ApiRelation = {
  relation_id?: string | null;
  relationId?: string | null;
  note?: string | null;
  amount_check?: ApiAmountCheck | null;
  amountCheck?: ApiAmountCheck | null;
};

type ApiResponse = {
  summary?: ApiSummary | null;
  bank_rows?: ApiBankRow[] | null;
  bankRows?: ApiBankRow[] | null;
  oa_rows?: ApiOaRow[] | null;
  oaRows?: ApiOaRow[] | null;
  relations_by_bank_row_id?: ApiRelationsByBankRowId | null;
  relationsByBankRowId?: ApiRelationsByBankRowId | null;
  pagination?: ApiPagination | null;
  tag_selection_version?: number | null;
  tagSelectionVersion?: number | null;
};

type ApiTagRule = {
  code?: string | null;
  label?: string | null;
  path?: string[] | null;
  output_primary_label?: string | null;
  outputPrimaryLabel?: string | null;
  output_sub_label?: string | null;
  outputSubLabel?: string | null;
};

type ApiTagRules = {
  version?: number | null;
  bank_auto_tag_rules_version?: number | null;
  bankAutoTagRulesVersion?: number | null;
  selected_tag_codes?: string[] | null;
  selectedTagCodes?: string[] | null;
  active_tags?: ApiTagRule[] | null;
  activeTags?: ApiTagRule[] | null;
  can_save?: boolean | null;
  canSave?: boolean | null;
};

type ApiPageInfo = {
  page?: number | null;
  page_size?: number | null;
  pageSize?: number | null;
  total?: number | null;
};

type ApiPagination = {
  bank_rows?: ApiPageInfo | null;
  bankRows?: ApiPageInfo | null;
  oa_rows?: ApiPageInfo | null;
  oaRows?: ApiPageInfo | null;
};

type ApiRelationValue = ApiOaRow[] | {
  relation_id?: string | null;
  relationId?: string | null;
  relation?: ApiRelation | null;
  note?: string | null;
  amount_check?: ApiAmountCheck | null;
  amountCheck?: ApiAmountCheck | null;
  oa_rows?: ApiOaRow[] | null;
  oaRows?: ApiOaRow[] | null;
};

type ApiRelationsByBankRowId = Record<string, ApiRelationValue>;

type ApiMutationResult = {
  success?: boolean | null;
  relation_id?: string | null;
  relationId?: string | null;
  affected_row_ids?: string[] | null;
  affectedRowIds?: string[] | null;
  affected_months?: string[] | null;
  affectedMonths?: string[] | null;
  affected_scope_keys?: string[] | null;
  affectedScopeKeys?: string[] | null;
  message?: string | null;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  return apiRequestJson<T>(url, init);
}

function text(value: string | null | undefined, fallback = "") {
  return typeof value === "string" ? value : fallback;
}

function numberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : 0;
}

function positiveNumberValue(value: number | null | undefined, fallback: number) {
  const number = numberValue(value);
  return number > 0 ? number : fallback;
}

function nullableNumberValue(value: number | null | undefined) {
  return Number.isFinite(value) ? Number(value) : null;
}

function stringList(value: string[] | null | undefined) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : [];
}

function mapBankRow(row: ApiBankRow = {}): BatchAccountingBankRow {
  return {
    id: text(row.id),
    tradeTime: text(row.trade_time ?? row.tradeTime),
    counterpartyName: text(row.counterparty_name ?? row.counterpartyName),
    direction: text(row.direction),
    directionLabel: text(row.direction_label ?? row.directionLabel),
    amount: text(row.amount, "0.00"),
    bankName: text(row.bank_name ?? row.bankName),
    accountLast4: text(row.account_last4 ?? row.accountLast4),
    relationId: text(row.relation_id ?? row.relationId),
    version: nullableNumberValue(row.version),
    tagCode: text(row.tag_code ?? row.tagCode),
    tagLabel: text(row.tag_label ?? row.tagLabel),
    tagPrimaryLabel: text(row.tag_primary_label ?? row.tagPrimaryLabel),
    tagSubLabel: text(row.tag_sub_label ?? row.tagSubLabel),
  };
}

function mapOaRow(row: ApiOaRow = {}): BatchAccountingOaRow {
  return {
    id: text(row.id),
    applicant: text(row.applicant),
    applyTime: text(row.apply_time ?? row.applyTime),
    projectName: text(row.project_name ?? row.projectName),
    amount: text(row.amount, "0.00"),
    reason: text(row.reason),
    linkedInvoiceRowIds: stringList(row.linked_invoice_row_ids ?? row.linkedInvoiceRowIds),
  };
}

function mapAmountCheck(value: ApiAmountCheck | null | undefined): BatchAccountingAmountCheck | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  return {
    status: text(value.status),
    direction: text(value.direction),
    bankAmount: text(value.bank_amount ?? value.bankAmount, "0.00"),
    oaAmount: text(value.oa_amount ?? value.oaAmount, "0.00"),
    amountDelta: text(value.amount_delta ?? value.amountDelta, "0.00"),
    requiresNote: Boolean(value.requires_note ?? value.requiresNote),
  };
}

function mapRelation(value: ApiRelation | null | undefined): BatchAccountingRelation | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  return {
    relationId: text(value.relation_id ?? value.relationId),
    note: text(value.note),
    amountCheck: mapAmountCheck(value.amount_check ?? value.amountCheck),
  };
}

function mapRelations(value: ApiRelationsByBankRowId | null | undefined) {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).map(([bankRowId, relationValue]) => {
      if (Array.isArray(relationValue)) {
        return [
          bankRowId,
          {
            relationId: "",
            oaRows: relationValue.map(mapOaRow),
          },
        ];
      }
      const rows = relationValue.oa_rows ?? relationValue.oaRows ?? [];
      const relation = mapRelation(
        relationValue.relation ?? {
          relation_id: relationValue.relation_id ?? relationValue.relationId,
          note: relationValue.note,
          amount_check: relationValue.amount_check ?? relationValue.amountCheck,
        },
      );
      return [
        bankRowId,
        {
          relationId: text(relationValue.relation_id ?? relationValue.relationId ?? relation?.relationId),
          relation,
          oaRows: Array.isArray(rows) ? rows.map(mapOaRow) : [],
        },
      ];
    }),
  );
}

function mapPageInfo(value: ApiPageInfo | null | undefined): BatchAccountingPageInfo | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  return {
    page: positiveNumberValue(value.page, 1),
    pageSize: positiveNumberValue(value.page_size ?? value.pageSize, 200),
    total: Math.max(0, numberValue(value.total)),
  };
}

function mapMutationResult(payload: ApiMutationResult): BatchAccountingMutationResult {
  return {
    success: Boolean(payload.success),
    relationId: text(payload.relation_id ?? payload.relationId),
    affectedRowIds: stringList(payload.affected_row_ids ?? payload.affectedRowIds),
    affectedMonths: stringList(payload.affected_months ?? payload.affectedMonths),
    affectedScopeKeys: stringList(payload.affected_scope_keys ?? payload.affectedScopeKeys),
    message: text(payload.message),
  };
}

export async function fetchBatchAccounting({
  bankYear,
  bucket,
  bankPage,
  bankPageSize,
  oaPage,
  oaPageSize,
  oaSearch,
  signal,
}: FetchBatchAccountingRequest): Promise<BatchAccountingResponse> {
  const params = new URLSearchParams();
  params.set("bank_year", bankYear);
  params.set("bucket", bucket);
  if (bankPage !== undefined) {
    params.set("bank_page", String(bankPage));
  }
  if (bankPageSize !== undefined) {
    params.set("bank_page_size", String(bankPageSize));
  }
  if (oaPage !== undefined) {
    params.set("oa_page", String(oaPage));
  }
  if (oaPageSize !== undefined) {
    params.set("oa_page_size", String(oaPageSize));
  }
  if (oaSearch) {
    params.set("oa_search", oaSearch);
  }
  const payload = await requestJson<ApiResponse>(`/api/batch-accounting?${params.toString()}`, { method: "GET", signal });
  const pagination = payload.pagination;
  return {
    summary: {
      unsubmittedCount: numberValue(payload.summary?.unsubmitted_count ?? payload.summary?.unsubmittedCount),
      submittedCount: numberValue(payload.summary?.submitted_count ?? payload.summary?.submittedCount),
    },
    bankRows: Array.isArray(payload.bank_rows ?? payload.bankRows) ? (payload.bank_rows ?? payload.bankRows ?? []).map(mapBankRow) : [],
    oaRows: Array.isArray(payload.oa_rows ?? payload.oaRows) ? (payload.oa_rows ?? payload.oaRows ?? []).map(mapOaRow) : [],
    relationsByBankRowId: mapRelations(payload.relations_by_bank_row_id ?? payload.relationsByBankRowId),
    pagination: {
      bankRows: mapPageInfo(pagination?.bank_rows ?? pagination?.bankRows),
      oaRows: mapPageInfo(pagination?.oa_rows ?? pagination?.oaRows),
    },
    tagSelectionVersion: positiveNumberValue(
      payload.tag_selection_version ?? payload.tagSelectionVersion,
      1,
    ),
  };
}

function mapTagRules(payload: ApiTagRules): BatchAccountingTagRules {
  const tags = payload.active_tags ?? payload.activeTags ?? [];
  return {
    version: positiveNumberValue(payload.version, 1),
    bankAutoTagRulesVersion: positiveNumberValue(
      payload.bank_auto_tag_rules_version ?? payload.bankAutoTagRulesVersion,
      1,
    ),
    selectedTagCodes: stringList(payload.selected_tag_codes ?? payload.selectedTagCodes),
    activeTags: Array.isArray(tags) ? tags.map((tag) => ({
      code: text(tag.code),
      label: text(tag.label ?? tag.code),
      path: stringList(tag.path),
      outputPrimaryLabel: text(tag.output_primary_label ?? tag.outputPrimaryLabel ?? tag.label ?? tag.code),
      outputSubLabel: text(tag.output_sub_label ?? tag.outputSubLabel),
    })).filter((tag) => Boolean(tag.code)) : [],
    canSave: Boolean(payload.can_save ?? payload.canSave),
  };
}

export async function fetchBatchAccountingTagRules(signal?: AbortSignal) {
  return mapTagRules(await requestJson<ApiTagRules>("/api/batch-accounting/tag-rules", {
    method: "GET",
    signal,
  }));
}

export async function saveBatchAccountingTagRules({
  expectedVersion,
  selectedTagCodes,
  signal,
}: SaveBatchAccountingTagRulesRequest) {
  return mapTagRules(await requestJson<ApiTagRules>("/api/batch-accounting/tag-rules", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      expected_version: expectedVersion,
      selected_tag_codes: selectedTagCodes,
    }),
    signal,
  }));
}

export async function submitBatchAccounting({
  bankYear,
  bankRowId,
  oaRowIds,
  expectedVersion,
  expectedTagSelectionVersion,
  note,
  signal,
}: SubmitBatchAccountingRequest): Promise<BatchAccountingMutationResult> {
  const payload = await requestJson<ApiMutationResult>("/api/batch-accounting/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bank_year: bankYear,
      bank_row_id: bankRowId,
      oa_row_ids: oaRowIds,
      expected_version: expectedVersion,
      expected_tag_selection_version: expectedTagSelectionVersion,
      note: String(note ?? "").trim(),
    }),
    signal,
  });
  return mapMutationResult(payload);
}

export async function withdrawBatchAccounting({
  relationId,
  expectedVersion,
  reason,
  signal,
}: WithdrawBatchAccountingRequest): Promise<BatchAccountingMutationResult> {
  const payload = await requestJson<ApiMutationResult>(
    `/api/batch-accounting/${encodeURIComponent(relationId)}/withdraw`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
      signal,
    },
  );
  return mapMutationResult(payload);
}
