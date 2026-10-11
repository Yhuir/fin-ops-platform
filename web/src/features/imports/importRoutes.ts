export type ImportWorkflowMode = "bank_transaction" | "invoice" | "etc_invoice";

export function importWorkflowPath(mode: ImportWorkflowMode) {
  switch (mode) {
    case "bank_transaction":
      return "/imports/bank-transactions";
    case "invoice":
      return "/imports/invoices";
    case "etc_invoice":
      return "/imports/etc-invoices";
  }
}

// Navigation context only. These defaults never become source-document facts.
const importEntries = {
  "etc-tickets": { mode: "etc_invoice", label: "返回 ETC 批次", path: "/etc-tickets", invoiceBatchType: "" },
  "bank-details": { mode: "bank_transaction", label: "返回银行明细", path: "/bank-details", invoiceBatchType: "" },
  "input-invoice-usage": { mode: "invoice", label: "返回进项发票", path: "/input-invoice-usage", invoiceBatchType: "input_invoice" },
  "output-invoice-collections": { mode: "invoice", label: "返回销项发票", path: "/output-invoice-collections", invoiceBatchType: "output_invoice" },
} as const;

export type ImportEntrySource = keyof typeof importEntries;

export function importEntryPath(source: ImportEntrySource) {
  return `${importWorkflowPath(importEntries[source].mode)}?from=${source}`;
}

export function importEntryFor(mode: ImportWorkflowMode, source: string | null) {
  if (!source || !Object.prototype.hasOwnProperty.call(importEntries, source)) return null;
  const entry = importEntries[source as ImportEntrySource];
  return entry.mode === mode ? entry : null;
}
