import type { TaxCertifiedInvoiceRecord, TaxInvoiceRecord, TaxMonthData, TaxSummary } from "./types";

type ApiTaxSummary = {
  output_tax: string;
  certified_input_tax?: string;
  planned_input_tax?: string;
  input_tax: string;
  deductible_tax: string;
  result_label: string;
  result_amount: string;
};

type ApiOutputItem = {
  id: string;
  buyer_name: string;
  issue_date: string;
  invoice_no: string;
  tax_amount: string;
  total_with_tax: string;
  invoice_type: string;
};

type ApiInputItem = {
  id: string;
  seller_name: string;
  issue_date: string;
  invoice_no: string;
  tax_amount: string;
  total_with_tax: string;
  risk_level: string;
  certified_status?: string;
  is_locked_certified?: boolean;
};

type ApiCertifiedItem = {
  id: string;
  seller_name: string;
  issue_date: string;
  invoice_no: string;
  tax_amount: string;
  total_with_tax: string;
  status?: string;
  matched_input_id?: string | null;
  matched_invoice_no?: string | null;
};

type ApiTaxMonthPayload = {
  month: string;
  output_items: ApiOutputItem[];
  input_items?: ApiInputItem[];
  input_plan_items?: ApiInputItem[];
  certified_items?: ApiCertifiedItem[];
  certified_matched_rows?: ApiCertifiedItem[];
  certified_outside_plan_rows?: ApiCertifiedItem[];
  locked_certified_input_ids?: string[];
  default_selected_output_ids: string[];
  default_selected_input_ids: string[];
  summary: ApiTaxSummary;
};

type ApiTaxCalculatePayload = {
  month: string;
  summary: ApiTaxSummary;
};

function parseMoney(value: string) {
  return Number(value.replace(/,/g, ""));
}

function formatMoney(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function mapSummary(summary: ApiTaxSummary): TaxSummary {
  return {
    outputTax: summary.output_tax,
    certifiedInputTax: summary.certified_input_tax ?? "0.00",
    plannedInputTax: summary.planned_input_tax ?? "0.00",
    inputTax: summary.input_tax,
    deductibleTax: summary.deductible_tax,
    resultLabel: summary.result_label,
    resultAmount: summary.result_amount,
  };
}

function deriveAmount(totalWithTax: string, taxAmount: string) {
  return formatMoney(parseMoney(totalWithTax) - parseMoney(taxAmount));
}

function mapOutputItem(item: ApiOutputItem): TaxInvoiceRecord {
  return {
    id: item.id,
    invoiceNo: item.invoice_no,
    invoiceType: item.invoice_type,
    counterparty: item.buyer_name,
    issueDate: item.issue_date,
    taxRate: "--",
    amount: deriveAmount(item.total_with_tax, item.tax_amount),
    taxAmount: item.tax_amount,
  };
}

function mapInputItem(item: ApiInputItem): TaxInvoiceRecord {
  return {
    id: item.id,
    invoiceNo: item.invoice_no,
    invoiceType: `进项票（风险${item.risk_level}）`,
    counterparty: item.seller_name,
    issueDate: item.issue_date,
    taxRate: "--",
    amount: deriveAmount(item.total_with_tax, item.tax_amount),
    taxAmount: item.tax_amount,
    statusLabel: item.certified_status ?? "待认证",
    isLocked: Boolean(item.is_locked_certified),
    isSelectable: !item.is_locked_certified,
  };
}

function mapCertifiedItem(item: ApiCertifiedItem): TaxCertifiedInvoiceRecord {
  return {
    id: item.id,
    invoiceNo: item.invoice_no,
    invoiceType: item.status ?? "已认证",
    counterparty: item.seller_name,
    issueDate: item.issue_date,
    taxRate: "--",
    amount: deriveAmount(item.total_with_tax, item.tax_amount),
    taxAmount: item.tax_amount,
    statusLabel: item.status ?? "已认证",
    isLocked: true,
    isSelectable: false,
    matchedInputId: item.matched_input_id ?? null,
  };
}

async function requestJson<T>(url: string, init: RequestInit = {}) {
  const response = await fetch(url, init);
  const payload = (await response.json()) as T;
  if (!response.ok) {
    throw new Error(typeof payload === "object" && payload ? JSON.stringify(payload) : "request failed");
  }
  return payload;
}

export async function fetchTaxOffsetMonth(month: string, signal?: AbortSignal): Promise<TaxMonthData> {
  const payload = await requestJson<ApiTaxMonthPayload>(`/api/tax-offset?month=${month}`, {
    method: "GET",
    signal,
  });

  const inputPlanItems = payload.input_plan_items ?? payload.input_items ?? [];
  const certifiedMatchedRows = payload.certified_matched_rows ?? [];
  const certifiedOutsidePlanRows = payload.certified_outside_plan_rows ?? [];
  const lockedCertifiedInputIds = payload.locked_certified_input_ids ?? [];

  return {
    outputInvoices: payload.output_items.map(mapOutputItem),
    inputPlanInvoices: inputPlanItems.map(mapInputItem),
    certifiedMatchedInvoices: certifiedMatchedRows.map(mapCertifiedItem),
    certifiedOutsidePlanInvoices: certifiedOutsidePlanRows.map(mapCertifiedItem),
    lockedCertifiedInputIds,
    defaultSelectedOutputIds: payload.default_selected_output_ids,
    defaultSelectedInputIds: payload.default_selected_input_ids,
    summary: mapSummary(payload.summary),
  };
}

export async function calculateTaxOffset(params: {
  month: string;
  selectedOutputIds: string[];
  selectedInputIds: string[];
}) {
  const payload = await requestJson<ApiTaxCalculatePayload>("/api/tax-offset/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      month: params.month,
      selected_output_ids: params.selectedOutputIds,
      selected_input_ids: params.selectedInputIds,
    }),
  });

  return mapSummary(payload.summary);
}
