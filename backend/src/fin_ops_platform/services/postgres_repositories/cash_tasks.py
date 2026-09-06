"""Monthly cash-task SQL. GET never materializes or generates cash."""

from __future__ import annotations

from datetime import date
from typing import Any

from fin_ops_platform.services.postgres_repositories.cash import CashRepository
from fin_ops_platform.services.postgres_repositories.cash_queries import _like, _page, _where

_SNAPSHOT = """jsonb_build_object('template_version',t.version,'title',t.title,'kind',t.kind,
    'remind_days',t.remind_days,'instructions',t.instructions,
    'default_account_id',t.default_account_id::text,'default_category_id',t.default_category_id::text)"""
_DUE = "(m.month + (least(t.execution_day,extract(day from (m.month+interval '1 month'-interval '1 day')))::int-1))::date"


class CashTaskRepository:
    def __init__(self, connection: Any) -> None:
        self.core = CashRepository(connection)

    def transaction(self, readonly: bool = False):
        return self.core.transaction(readonly=readonly)

    @staticmethod
    def validate_defaults(tx: Any, values: dict[str, Any]) -> None:
        from fin_ops_platform.services.cash_domain import CashError

        category_id, account_id = values["default_category_id"], values["default_account_id"]
        if category_id is not None:
            row = tx.get("categories", category_id, lock="share")
            if row is None:
                raise CashError("cash_not_found", "Task category is unavailable.", 404)
            if not row["enabled"] or row["group"] not in {values["kind"], "turnover"}:
                raise CashError("cash_invalid_input", "Task category is incompatible.")
        if account_id is not None:
            row = tx.get("accounts", account_id, lock="share")
            if row is None:
                raise CashError("cash_not_found", "Task account is unavailable.", 404)
            if not row["enabled"]:
                raise CashError("cash_invalid_input", "Task account is disabled.")

    def list_templates(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.transaction(readonly=True) as tx:
            where, params = _where(query, {"enabled": "t.enabled", "kind": "t.kind"})
            if "keyword" in query:
                where += " and concat_ws(' ',t.title,t.instructions) ilike %s"
                params.append(_like(query["keyword"]))
            sql = f"select t.* from cash.task_templates t where {where}"
            result = _page(tx.raw, sql, params, query, order=query["sort"])
            for row in result["rows"]:
                row["effective_from_month"] = row["effective_from_month"].strftime("%Y-%m")
                if row["effective_to_month"] is not None:
                    row["effective_to_month"] = row["effective_to_month"].strftime("%Y-%m")
            return result

    @staticmethod
    def materialize_old_months(tx: Any, template_id: str, current_month: date) -> int:
        return tx.raw.execute(f"""insert into cash.task_occurrences
            (id,template_id,month,due_on,planned_amount,processing_state,template_values_snapshot,note)
            select gen_random_uuid(),t.id,m.month,{_DUE},t.default_amount,'pending',{_SNAPSHOT},null
            from cash.task_templates t cross join lateral (select generate_series(t.effective_from_month,
              least(coalesce(t.effective_to_month,%s),%s),interval '1 month')::date as month) m
            where t.id=%s and t.enabled
            on conflict(template_id,month) do nothing""", (current_month, current_month, template_id))

    @staticmethod
    def get_occurrence(tx: Any, template_id: str, month: date, *, lock: bool = False) -> dict[str, Any] | None:
        return tx.raw.fetch_one("select * from cash.task_occurrences where template_id=%s and month=%s" + (" for update" if lock else ""), (template_id, month))

    @staticmethod
    def actual(tx: Any, occurrence_id: str) -> dict[str, Any]:
        return tx.raw.fetch_one("select coalesce(sum(amount),0) as amount,count(*) as flow_count from cash.flows where task_occurrence_id=%s", (occurrence_id,))

    @staticmethod
    def has_history(tx: Any, template_id: str) -> bool:
        return tx.raw.fetch_one("select exists(select 1 from cash.task_occurrences where template_id=%s) as present", (template_id,))["present"]

    @staticmethod
    def _occurrences_sql(lower: date | None, upper: date) -> tuple[str, list[Any]]:
        sql = f"""with candidates as (
            select o.id as occurrence_id,o.version,o.template_id,o.month,o.due_on,o.planned_amount,
              o.processing_state,o.template_values_snapshot,o.note from cash.task_occurrences o
            union all
            select null::uuid,null::integer,t.id,m.month,{_DUE},t.default_amount,'pending',{_SNAPSHOT},null::text
            from cash.task_templates t cross join lateral (select generate_series(
              greatest(t.effective_from_month,coalesce(%s::date,t.effective_from_month)),
              least(coalesce(t.effective_to_month,%s::date),%s::date),interval '1 month')::date as month) m
            where t.enabled and not exists(select 1 from cash.task_occurrences o where o.template_id=t.id and o.month=m.month)
        ), actuals as (
            select c.*,c.template_values_snapshot->>'kind' as kind,c.template_values_snapshot->>'title' as title,
              (c.template_values_snapshot->>'template_version')::integer as template_version,
              c.due_on-(c.template_values_snapshot->>'remind_days')::integer as remind_on,
              case when c.template_values_snapshot->>'kind'='check' then null else coalesce(a.actual_amount,0) end as actual_amount,
              coalesce(a.flow_count,0) as flow_count
            from candidates c left join lateral (select sum(f.amount) as actual_amount,count(*) as flow_count
              from cash.flows f where f.task_occurrence_id=c.occurrence_id) a on true
        ), states as (
            select a.*,case when kind='check' then case when processing_state='checked' then 'completed' else 'pending' end
              when actual_amount=0 then 'pending' when actual_amount<planned_amount then 'partial' else 'completed' end as state
            from actuals a
        ) select template_id::text||':'||to_char(month,'YYYY-MM') as row_key,occurrence_id,version,template_id,template_version,
            to_char(month,'YYYY-MM') as month,title,kind,due_on,remind_on,planned_amount,actual_amount,state,
            processing_state='unpaid' as marked_unpaid,kind<>'check' and planned_amount is null as need_planned_amount,
            kind<>'check' and planned_amount is not null and actual_amount>planned_amount as is_over_plan,
            case when kind='check' then null else greatest(actual_amount-coalesce(planned_amount,actual_amount),0) end as over_plan_amount,
            state<>'completed' and due_on<%s::date as is_overdue,due_on=%s::date as is_due,note,flow_count
            from states"""
        return sql, [lower, upper, upper]

    def list_occurrences(self, query: dict[str, Any], today: date) -> dict[str, Any]:
        from datetime import timedelta

        with self.transaction(readonly=True) as tx:
            if "template_id" in query:
                if tx.get("task_templates", query["template_id"]) is None:
                    from fin_ops_platform.services.cash_domain import CashError

                    raise CashError("cash_not_found", "Task template is unavailable.", 404)
            if "month" in query:
                lower = upper = query["month"]
                window, window_params = "month=%s", [query["month"].strftime("%Y-%m")]
            elif "overdue_as_of" in query:
                lower, upper = None, query["overdue_as_of"].replace(day=1)
                window, window_params = "due_on<%s and state<>'completed'", [query["overdue_as_of"]]
            else:
                lower = (query["reminder_from"] - timedelta(days=31)).replace(day=1)
                upper = (query["reminder_to"] + timedelta(days=62)).replace(day=1)
                window, window_params = "remind_on between %s and %s and state<>'completed'", [query["reminder_from"], query["reminder_to"]]
            sql, params = self._occurrences_sql(lower, upper)
            params.extend([today, today])
            where, extra = _where(query, {"template_id": "template_id", "kind": "kind", "state": "state"})
            where += " and " + window
            extra.extend(window_params)
            if "keyword" in query:
                where += " and concat_ws(' ',title,note) ilike %s"
                extra.append(_like(query["keyword"]))
            sql = f"select * from ({sql}) r where {where}"
            params.extend(extra)
            result = _page(tx.raw, sql, params, query, order=query["sort"], tie="row_key")
            summary = tx.raw.fetch_one(f"select count(*) as task_count,count(*) filter(where state='pending') as pending_count,count(*) filter(where state='partial') as partial_count,count(*) filter(where state='completed') as completed_count,coalesce(sum(actual_amount) filter(where kind='receipt'),0) as receipt_actual_amount,coalesce(sum(actual_amount) filter(where kind='payment'),0) as payment_actual_amount from ({sql}) r", tuple(params))
            summary["counts_by_state"] = {key: summary.pop(key + "_count") for key in ("pending", "partial", "completed")}
            result["summary"] = summary
            return result
