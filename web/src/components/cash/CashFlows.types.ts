import type { CashSettlement } from "./CashItems.types";

export type CashFlowKind = "receipt" | "payment" | "transfer";
export type CashFlow = {
  id: string; version: number; occurred_on: string; kind: CashFlowKind; amount: string;
  from_account: { id: string; name: string } | null; to_account: { id: string; name: string } | null;
  category: { id: string; name: string; group: string } | null;
  project: { id: string; name_snapshot: string } | null; person_name: string | null; content: string;
  source_kind: "manual" | "monthly_task";
  task: { occurrence_id: string; occurrence_version: number; template_id: string; month: string; title: string; kind: string } | null;
  income_amount: string | null; expense_amount: string | null; account_running_balance: string | null;
  remark?: string | null; created_by_account?: string; created_by_name?: string | null;
  created_at?: string; updated_at?: string;
};
export type CashFlowDetail = {
  flow: CashFlow; allocations: CashSettlement[]; allocation_count: number; allocations_has_more: boolean;
  task: CashFlow["task"];
  delete_impact: {
    flow_version: number; task_count: number; item_count: number; settlement_count: number;
    source_owned_item_count: number; source_correction_required: boolean;
    tasks: { id: string; version: number; title: string }[];
    items: { id: string; version: number; content: string }[]; preview_truncated: boolean;
  };
};
export const cashFlowLabels: Record<CashFlowKind, string> = { receipt: "收入", payment: "支出", transfer: "内部转账" };

export type CashFlowSummary = {
  period: { date_from: string | null; date_to: string | null };
  filtered_totals: { flow_count: number; income_amount: string; expense_amount: string; transfer_amount: string };
  account_balances: {
    account_id: string; account_name: string; opening_date: string;
    coverage_state: "complete" | "not_started" | "starts_during_period"; coverage_start: string | null;
    opening_balance: string | null; balance_at_coverage_start: string | null;
    period_inflow: string | null; period_outflow: string | null; ending_balance: string | null;
  }[];
};
