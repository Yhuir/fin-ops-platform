export type CashPageRows<T> = { rows: T[]; pagination: { page: number; page_size: number; total: number } };
export type CashProject = { id: string; name_snapshot: string } | null;
export type CashItemType = "loan" | "company_receivable" | "expense" | "ticket_source";
export type CashSettlementKind = "cash_repayment" | "company_collection" | "expense_payment" | "expense_refund" | "ticket_use" | "ticket_offset" | "non_ticket_offset";
export type CashCategory = { id: string; name: string; group: string };
export type CashPersonalSetting = { opening_date: string | null; counterparty: string | null; version: number };
export type CashPersonalContext = { opening_date: string; counterparty: string };
export type CashItem = {
  id: string; version: number; type: CashItemType; origin_date: string; original_amount: string;
  is_opening: boolean; obligation_direction: "receivable" | "payable" | null;
  ledger_group: "company" | "external_person" | "personal" | null; counterparty: string | null;
  oa_project_id: string | null; project_name_snapshot: string | null; project?: CashProject;
  origin_flow_id: string | null; origin_mode: "created" | "linked" | null;
  bill_label_id: string | null; bill_month: string | null;
  ticket_provider: string | null; ticket_provided_on: string | null; ticket_description: string | null;
  related_obligation_id: string | null; ticket_source_id: string | null; content: string; remark: string | null;
  category_id: string | null; category: CashCategory | null;
  selectable?: boolean; unavailable_reason?: string | null; remaining_obligation_amount?: string;
  available_source_amount?: string;
};
export type CashSettlement = {
  category_id: string | null; category: CashCategory | null;
  id: string; version: number; kind: CashSettlementKind; occurred_on: string; amount: string; remark: string | null;
  item_id: string | null; item_version: number | null; item_content: string | null;
  source_item_id: string | null; source_item_version: number | null; source_item_content: string | null;
  flow_id: string | null; flow_version: number | null; flow_source_kind: "manual" | "monthly_task" | null;
  task: { occurrence_id: string; occurrence_version: number; title: string } | null;
};
export type CashItemDetailData = {
  item: CashItem; amounts: Record<string, string>; settlements: CashSettlement[];
  settlement_count: number; settlements_has_more: boolean;
};
export const itemTypeLabels: Record<CashItemType, string> = {
  loan: "借款 / 代付", company_receivable: "公司应收", expense: "真实费用", ticket_source: "票据提供",
};
export const settlementLabels: Record<CashSettlementKind, string> = {
  cash_repayment: "现金归还", company_collection: "公司实际回款", expense_payment: "费用付款",
  expense_refund: "费用退款", ticket_use: "票据使用", ticket_offset: "票据抵债", non_ticket_offset: "无票 / 其他冲抵",
};
export function cashAmount(value: string | null): string {
  if (value === null) return "—";
  if (!/^-?\d+(?:\.\d{1,2})?$/.test(value)) throw new Error("现金金额格式不正确。");
  const [whole, fraction = ""] = value.split(".");
  return `${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;
}
export function cashMoneyInput(value: string): string {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) throw new Error("金额须为正数，最多两位小数。");
  const [whole, fraction = ""] = value.trim().split(".");
  const amount = `${whole.replace(/^0+(?=\d)/, "")}.${fraction.padEnd(2, "0")}`;
  if (/^0\.00$/.test(amount)) throw new Error("金额必须大于零。");
  return amount;
}
export function cashToday(): string {
  return new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Shanghai" });
}
export function settlementVersions(row: CashSettlement) {
  const items = new Map<string, number>();
  if (row.item_id && row.item_version !== null) items.set(row.item_id, row.item_version);
  if (row.source_item_id && row.source_item_version !== null) items.set(row.source_item_id, row.source_item_version);
  return {
    items: Array.from(items, ([id, version]) => ({ id, version })),
    flows: row.flow_id && row.flow_version !== null ? [{ id: row.flow_id, version: row.flow_version }] : [],
    occurrences: row.task ? [{ id: row.task.occurrence_id, version: row.task.occurrence_version }] : [],
  };
}
