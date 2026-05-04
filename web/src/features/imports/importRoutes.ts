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
