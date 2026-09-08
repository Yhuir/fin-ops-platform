export type CashTaskKind = "receipt" | "payment" | "check";

export type CashTaskTemplate = {
  id: string;
  version: number;
  title: string;
  kind: CashTaskKind;
  execution_day: number;
  remind_days: number;
  effective_from_month: string;
  effective_to_month: string | null;
  enabled: boolean;
  default_account_id: string | null;
  default_category_id: string | null;
  default_amount: string | null;
  instructions: string | null;
};

export type CashTaskOccurrence = {
  row_key: string;
  occurrence_id: string | null;
  version: number | null;
  template_id: string;
  template_version: number;
  month: string;
  title: string;
  kind: CashTaskKind;
  due_on: string;
  remind_on: string;
  planned_amount: string | null;
  actual_amount: string | null;
  state: "pending" | "partial" | "completed";
  marked_unpaid: boolean;
  need_planned_amount: boolean;
  is_over_plan: boolean;
  over_plan_amount: string | null;
  is_overdue: boolean;
  is_due: boolean;
  note: string | null;
  flow_count: number;
  instructions: string | null;
  default_account_id: string | null;
  default_category_id: string | null;
};

export type CashTasksPage<T> = { rows: T[]; pagination: { total: number; page: number; page_size: number } };
export type CashOccurrencesPage = CashTasksPage<CashTaskOccurrence> & {
  summary: {
    task_count: number;
    counts_by_state: Record<CashTaskOccurrence["state"], number>;
    receipt_actual_amount: string;
    payment_actual_amount: string;
  };
};

export function cashTaskIdentity(row: CashTaskOccurrence) {
  return {
    template_id: row.template_id,
    month: row.month,
    expected_version: row.version,
    ...(row.version === null ? { expected_template_version: row.template_version } : {}),
  };
}

export const cashTaskKindLabels: Record<CashTaskKind, string> = {
  receipt: "收入", payment: "支出", check: "核对与跟进",
};

export const cashTaskStateLabels: Record<CashTaskOccurrence["state"], string> = {
  pending: "未处理", partial: "部分办理", completed: "已完成",
};
