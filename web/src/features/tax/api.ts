import type {
  TaxCertifiedImportConfirmResult,
  TaxCertifiedImportPreviewFile,
  TaxCertifiedImportPreviewResult,
  TaxCertifiedImportPreviewRow,
  TaxCertifiedInvoiceRecord,
  TaxInvoiceRecord,
  TaxMonthData,
  TaxSummary,
} from "./types";

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
  tax_rate?: string;
  tax_amount: string;
  total_with_tax: string;
  invoice_type: string;
};

type ApiInputItem = {
  id: string;
  seller_name: string;
  issue_date: string;
  invoice_no: string;
  tax_rate?: string;
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
  tax_rate?: string;
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

type ApiTaxCertifiedImportPreviewRow = {
  id: string;
  month: string;
  digital_invoice_no?: string | null;
  invoice_code?: string | null;
  invoice_no?: string | null;
  issue_date?: string | null;
  seller_tax_no?: string | null;
  seller_name?: string | null;
  tax_amount?: string | null;
  deductible_tax_amount?: string | null;
  selection_status?: string | null;
  invoice_status?: string | null;
  selection_time?: string | null;
  source_file_name: string;
  source_row_number: number;
};

type ApiTaxCertifiedImportPreviewFile = {
  id: string;
  file_name: string;
  month: string;
  recognized_count: number;
  invalid_count: number;
  matched_plan_count?: number;
  outside_plan_count?: number;
  rows: ApiTaxCertifiedImportPreviewRow[];
};

type ApiTaxCertifiedImportPreviewPayload = {
  session: {
    id: string;
    imported_by: string;
    file_count: number;
    status: string;
  };
  files: ApiTaxCertifiedImportPreviewFile[];
  summary?: {
    recognized_count: number;
    invalid_count: number;
    matched_plan_count: number;
    outside_plan_count: number;
  };
};

type ApiTaxCertifiedImportConfirmPayload = {
  success: boolean;
  batch: {
    id: string;
    session_id: string;
    imported_by: string;
    file_count: number;
    months: string[];
    persisted_record_count: number;
  };
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
    taxRate: item.tax_rate ?? "--",
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
    taxRate: item.tax_rate ?? "--",
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
    taxRate: item.tax_rate ?? "--",
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

function mapPreviewRow(row: ApiTaxCertifiedImportPreviewRow): TaxCertifiedImportPreviewRow {
  return {
    id: row.id,
    month: row.month,
    digitalInvoiceNo: row.digital_invoice_no ?? null,
    invoiceCode: row.invoice_code ?? null,
    invoiceNo: row.invoice_no ?? null,
    issueDate: row.issue_date ?? null,
    sellerTaxNo: row.seller_tax_no ?? null,
    sellerName: row.seller_name ?? null,
    taxAmount: row.tax_amount ?? null,
    deductibleTaxAmount: row.deductible_tax_amount ?? null,
    selectionStatus: row.selection_status ?? null,
    invoiceStatus: row.invoice_status ?? null,
    selectionTime: row.selection_time ?? null,
    sourceFileName: row.source_file_name,
    sourceRowNumber: row.source_row_number,
  };
}

function mapPreviewFile(file: ApiTaxCertifiedImportPreviewFile): TaxCertifiedImportPreviewFile {
  return {
    id: file.id,
    fileName: file.file_name,
    month: file.month,
    recognizedCount: file.recognized_count,
    invalidCount: file.invalid_count,
    matchedPlanCount: file.matched_plan_count ?? 0,
    outsidePlanCount: file.outside_plan_count ?? 0,
    rows: file.rows.map(mapPreviewRow),
  };
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

export async function previewTaxCertifiedImport(params: {
  importedBy: string;
  files: File[];
}): Promise<TaxCertifiedImportPreviewResult> {
  const formData = new FormData();
  formData.append("imported_by", params.importedBy);
  for (const file of params.files) {
    formData.append("files", file);
  }
  const payload = await requestJson<ApiTaxCertifiedImportPreviewPayload>("/api/tax-offset/certified-import/preview", {
    method: "POST",
    body: formData,
  });

  return {
    sessionId: payload.session.id,
    importedBy: payload.session.imported_by,
    fileCount: payload.session.file_count,
    status: payload.session.status,
    files: payload.files.map(mapPreviewFile),
    summary: {
      recognizedCount: payload.summary?.recognized_count ?? payload.files.reduce((sum, file) => sum + file.recognized_count, 0),
      invalidCount: payload.summary?.invalid_count ?? payload.files.reduce((sum, file) => sum + file.invalid_count, 0),
      matchedPlanCount: payload.summary?.matched_plan_count ?? payload.files.reduce((sum, file) => sum + (file.matched_plan_count ?? 0), 0),
      outsidePlanCount: payload.summary?.outside_plan_count ?? payload.files.reduce((sum, file) => sum + (file.outside_plan_count ?? 0), 0),
    },
  };
}

export async function confirmTaxCertifiedImport(sessionId: string): Promise<TaxCertifiedImportConfirmResult> {
  const payload = await requestJson<ApiTaxCertifiedImportConfirmPayload>("/api/tax-offset/certified-import/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
    }),
  });

  return {
    batchId: payload.batch.id,
    sessionId: payload.batch.session_id,
    importedBy: payload.batch.imported_by,
    fileCount: payload.batch.file_count,
    months: payload.batch.months,
    persistedRecordCount: payload.batch.persisted_record_count,
  };
}
