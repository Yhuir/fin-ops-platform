import type { PendingInvoiceDirection } from "./types";

export const ACQUISITION_STATUS_CODES = [
  "paid_pending_invoice", "paid_invoiced", "invoice_not_fully_paid", "bank_statement_as_invoice", "no_invoice_required",
  "income_pending_invoice", "income_invoiced", "income_no_invoice_required", "cash_income",
] as const;
export type AcquisitionStatusCode = typeof ACQUISITION_STATUS_CODES[number];
export type AcquisitionSummary = { bankCount: number; invoiceCount: number; statusCounts: Record<AcquisitionStatusCode, number> };

export function acquisitionOptions(direction: PendingInvoiceDirection) {
  const expense = direction !== "income";
  const income = direction !== "expense";
  return [
    { key: "pending", label: direction === "expense" ? "已支付待取得发票" : direction === "income" ? "已收款待开票" : "待取得／开具发票", codes: [...(expense ? ["paid_pending_invoice"] : []), ...(income ? ["income_pending_invoice"] : [])] },
    { key: "linked", label: direction === "expense" ? "已支付已关联发票" : direction === "income" ? "已收款已关联发票" : "已关联发票", codes: [...(expense ? ["paid_invoiced"] : []), ...(income ? ["income_invoiced"] : [])] },
    ...(expense ? [
      { key: "review", label: "金额待核对", codes: ["invoice_not_fully_paid"] },
      { key: "statement", label: "流水代替发票", codes: ["bank_statement_as_invoice"] },
    ] : []),
    { key: "no_invoice", label: "无需发票", codes: [...(expense ? ["no_invoice_required"] : []), ...(income ? ["income_no_invoice_required"] : [])] },
    ...(income ? [{ key: "cash", label: "现金收入", codes: ["cash_income"] }] : []),
  ].map(option => ({ ...option, codes: option.codes as AcquisitionStatusCode[] }));
}
