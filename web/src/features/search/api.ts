import type {
  WorkbenchSearchRecordType,
  WorkbenchSearchResponse,
  WorkbenchSearchResult,
  WorkbenchSearchScope,
  WorkbenchSearchStatus,
  WorkbenchSearchZoneHint,
} from "./types";

type ApiSearchRecordType = WorkbenchSearchRecordType;

type ApiSearchZoneHint = WorkbenchSearchZoneHint;

type ApiSearchResult = {
  row_id: string;
  record_type: ApiSearchRecordType;
  month: string;
  zone_hint: ApiSearchZoneHint;
  matched_field: string;
  title: string;
  primary_meta: string | string[];
  secondary_meta: string | string[];
  status_label: string;
  jump_target: {
    month: string;
    row_id: string;
    zone_hint: ApiSearchZoneHint;
    record_type: ApiSearchRecordType;
  };
};

function normalizeMetaValue(value: string | string[] | null | undefined): string {
  if (Array.isArray(value)) {
    const parts = value
      .map((item) => String(item ?? "").trim())
      .filter((item) => item.length > 0);
    return parts.length > 0 ? parts.join(" / ") : "—";
  }
  const text = String(value ?? "").trim();
  return text.length > 0 ? text : "—";
}

type ApiSearchResponse = {
  query: string;
  summary: {
    total: number;
    oa: number;
    bank: number;
    invoice: number;
  };
  oa_results: ApiSearchResult[];
  bank_results: ApiSearchResult[];
  invoice_results: ApiSearchResult[];
};

type SearchWorkbenchParams = {
  q: string;
  scope: WorkbenchSearchScope;
  month: string;
  projectName?: string;
  status?: WorkbenchSearchStatus;
  limit?: number;
  signal?: AbortSignal;
};

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    ...init,
  });

  const rawText = await response.text();
  let payload: T | null = null;

  if (rawText.trim().length > 0) {
    try {
      payload = JSON.parse(rawText) as T;
    } catch {
      throw new Error("invalid_json_response");
    }
  }

  if (!response.ok) {
    throw new Error(rawText || "request failed");
  }

  return payload as T;
}

function mapSearchResult(result: ApiSearchResult): WorkbenchSearchResult {
  return {
    rowId: result.row_id,
    recordType: result.record_type,
    month: result.month,
    zoneHint: result.zone_hint,
    matchedField: result.matched_field,
    title: result.title,
    primaryMeta: normalizeMetaValue(result.primary_meta as string | string[] | null | undefined),
    secondaryMeta: normalizeMetaValue(result.secondary_meta as string | string[] | null | undefined),
    statusLabel: result.status_label,
    jumpTarget: {
      month: result.jump_target.month,
      rowId: result.jump_target.row_id,
      zoneHint: result.jump_target.zone_hint,
      recordType: result.jump_target.record_type,
    },
  };
}

export function createEmptySearchResponse(query = ""): WorkbenchSearchResponse {
  return {
    query,
    summary: {
      total: 0,
      oa: 0,
      bank: 0,
      invoice: 0,
    },
    oaResults: [],
    bankResults: [],
    invoiceResults: [],
  };
}

export async function fetchWorkbenchSearch({
  q,
  scope,
  month,
  projectName,
  status = "all",
  limit = 30,
  signal,
}: SearchWorkbenchParams): Promise<WorkbenchSearchResponse> {
  const params = new URLSearchParams({
    q,
    scope,
    month,
    limit: String(limit),
  });

  if (projectName) {
    params.set("project_name", projectName);
  }
  if (status !== "all") {
    params.set("status", status);
  }

  const payload = await requestJson<ApiSearchResponse>(`/api/search?${params.toString()}`, {
    method: "GET",
    signal,
  });

  return {
    query: payload.query,
    summary: payload.summary,
    oaResults: payload.oa_results.map(mapSearchResult),
    bankResults: payload.bank_results.map(mapSearchResult),
    invoiceResults: payload.invoice_results.map(mapSearchResult),
  };
}
