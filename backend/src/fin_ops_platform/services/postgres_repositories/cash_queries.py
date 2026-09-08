"""Bounded, single-snapshot SQL reads owned exclusively by the cash module."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

from fin_ops_platform.services.cash_domain import CashError


def _missing() -> None:
    raise CashError("cash_not_found", "Cash object is unavailable.", 404)


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _where(query: dict[str, Any], fields: dict[str, str]) -> tuple[str, list[Any]]:
    clauses, params = [], []
    for key, column in fields.items():
        if key in query:
            value = query[key]
            if isinstance(value, list):
                nonnull = [item for item in value if item is not None]
                alternatives = []
                if nonnull:
                    sql_type = "uuid" if key.endswith("_id") and key not in {"project_id", "source_project_id"} else "text"
                    alternatives.append(f"{column} = any(%s::{sql_type}[])")
                    params.append(nonnull)
                if None in value:
                    alternatives.append(f"{column} is null")
                clauses.append("(" + " or ".join(alternatives) + ")")
            else:
                clauses.append(f"{column} = %s")
                params.append(value)
    return " and ".join(clauses) or "true", params


def _page(tx: Any, sql: str, params: list[Any], query: dict[str, Any], *, order: str, tie: str = "id") -> dict[str, Any]:
    total = tx.fetch_one(f"select count(*) as total from ({sql}) counted", tuple(params))["total"]
    rows = tx.fetch_all(f"select * from ({sql}) paged order by {order} {query['order']} nulls last, {tie} {query['order']} limit %s offset %s", (*params, query["page_size"], (query["page"] - 1) * query["page_size"]))
    return {"rows": rows, "pagination": {"page": query["page"], "page_size": query["page_size"], "total": total}}


_PROJECT = "case when {a}.oa_project_id is null then null else jsonb_build_object('id',{a}.oa_project_id,'name_snapshot',{a}.project_name_snapshot) end"
_TASK = """case when o.id is null then null else jsonb_build_object(
    'occurrence_id',o.id::text,'occurrence_version',o.version,'template_id',o.template_id::text,
    'month',to_char(o.month,'YYYY-MM'),'title',o.template_values_snapshot->>'title',
    'kind',o.template_values_snapshot->>'kind') end"""
_FLOW_COLUMNS = f"""f.id,f.version,f.occurred_on,f.kind,f.amount,
    case when fa.id is null then null else jsonb_build_object('id',fa.id::text,'name',fa.name) end as from_account,
    case when ta.id is null then null else jsonb_build_object('id',ta.id::text,'name',ta.name) end as to_account,
    case when c.id is null then null else jsonb_build_object('id',c.id::text,'name',c.name,'group',c."group") end as category,
    {_PROJECT.format(a='f')} as project,f.person_name,f.content,f.source_kind,{_TASK} as task,
    case when f.kind='receipt' then f.amount end as income_amount,
    case when f.kind='payment' then f.amount end as expense_amount"""
_FLOW_JOINS = """from cash.flows f
    left join cash.accounts fa on fa.id=f.from_account_id
    left join cash.accounts ta on ta.id=f.to_account_id
    left join cash.categories c on c.id=f.category_id
    left join cash.task_occurrences o on o.id=f.task_occurrence_id"""
_FLOW_BUDGET = """select f.id,
    coalesce((select sum(i.original_amount) from cash.items i where i.origin_flow_id=f.id and i.type='loan'),0)
      + coalesce((select sum(s.amount) from cash.settlements s where s.flow_id=f.id and s.kind in ('cash_repayment','company_collection')),0) as obligation_allocated_amount,
    coalesce((select sum(i.original_amount) from cash.items i where i.origin_flow_id=f.id and i.type='expense'),0)
      + coalesce((select sum(s.amount) from cash.settlements s where s.flow_id=f.id and s.kind in ('expense_payment','expense_refund')),0) as expense_allocated_amount
    from cash.flows f"""
_SETTLEMENT_COLUMNS = f"""s.id,s.version,s.kind,s.occurred_on,s.amount,s.remark,s.category_id,
    case when sc.id is null then null else jsonb_build_object('id',sc.id::text,'name',sc.name,'group',sc."group") end as category,
    s.item_id,i.version as item_version,i.content as item_content,
    s.source_item_id,si.version as source_item_version,si.content as source_item_content,
    s.flow_id,f.version as flow_version,f.source_kind as flow_source_kind,{_TASK} as task"""
_SETTLEMENT_JOINS = """from cash.settlements s left join cash.items i on i.id=s.item_id
    left join cash.items si on si.id=s.source_item_id left join cash.flows f on f.id=s.flow_id
    left join cash.task_occurrences o on o.id=f.task_occurrence_id
    left join cash.categories sc on sc.id=case when s.kind in ('cash_repayment','company_collection') then f.category_id
      when s.kind in ('expense_payment','expense_refund') then i.category_id
      when s.source_item_id is not null then si.category_id else s.category_id end"""
_ITEM_AMOUNTS = """select i.*,
    coalesce(a.cash_settled_amount,0) as cash_settled_amount,
    coalesce(a.ticket_offset_amount,0) as ticket_offset_amount,
    coalesce(a.non_ticket_offset_amount,0) as non_ticket_offset_amount,
    i.original_amount-coalesce(a.cash_settled_amount,0)-coalesce(a.ticket_offset_amount,0)-coalesce(a.non_ticket_offset_amount,0) as remaining_obligation_amount,
    coalesce(a.paid_amount,0)+case when i.origin_flow_id is not null and i.type='expense' then i.original_amount else 0 end as paid_amount,
    coalesce(a.refund_amount,0) as refund_amount,i.original_amount-coalesce(a.refund_amount,0) as net_expense_amount,
    coalesce(b.used_amount,0) as used_amount,coalesce(b.offset_amount,0) as offset_amount,
    case when i.type='ticket_source' then i.original_amount-coalesce(b.used_amount,0)
         when i.type='expense' then i.original_amount-coalesce(a.refund_amount,0)-coalesce(b.non_ticket_used,0) end as available_source_amount
    from cash.items i
    left join lateral (select
      sum(s.amount) filter(where s.kind in ('cash_repayment','company_collection')) as cash_settled_amount,
      sum(s.amount) filter(where s.kind='ticket_offset') as ticket_offset_amount,
      sum(s.amount) filter(where s.kind='non_ticket_offset') as non_ticket_offset_amount,
      sum(s.amount) filter(where s.kind='expense_payment') as paid_amount,
      sum(s.amount) filter(where s.kind='expense_refund') as refund_amount
      from cash.settlements s where s.item_id=i.id) a on true
    left join lateral (select sum(s.amount) filter(where s.kind in ('ticket_use','ticket_offset')) as used_amount,
      sum(s.amount) filter(where s.kind='ticket_offset') as offset_amount,
      sum(s.amount) filter(where s.kind='non_ticket_offset') as non_ticket_used
      from cash.settlements s where s.source_item_id=i.id) b on true"""


class CashQueryRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def list_configuration(self, kind: str, query: dict[str, Any]) -> dict[str, Any]:
        table = {"accounts": "accounts", "categories": "categories", "bill-labels": "bill_labels"}[kind]
        with self.snapshot() as tx:
            where, params = _where(query, {"enabled": "enabled", "group": '"group"'})
            if "keyword" in query:
                text = "concat_ws(' ',bank_name,label)" if kind == "bill-labels" else "name"
                where += f" and {text} ilike %s"
                params.append(_like(query["keyword"]))
            return _page(tx, f"select * from cash.{table} where {where}", params, query, order=query["sort"])

    @contextmanager
    def snapshot(self) -> Iterator[Any]:
        with self.connection.transaction() as tx:
            tx.execute("set transaction isolation level repeatable read read only")
            yield tx

    @staticmethod
    def _require(tx: Any, table: str, object_id: str) -> dict[str, Any]:
        if table not in {"flows", "items", "task_occurrences", "task_templates", "accounts"}:
            raise ValueError("Unsupported cash reference.")
        row = tx.fetch_one(f"select * from cash.{table} where id=%s", (object_id,))
        if row is None:
            _missing()
        return row

    def list_flows(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            condition, params = _where(query, {"project_id": "f.oa_project_id", "category_id": "f.category_id", "kind": "f.kind", "person": "f.person_name", "source": "f.source_kind", "task_occurrence_id": "f.task_occurrence_id"})
            for key, column in (("date_from", "f.occurred_on >="), ("date_to", "f.occurred_on <=")):
                if key in query:
                    condition += f" and {column} %s"
                    params.append(query[key])
            if "keyword" in query:
                condition += " and concat_ws(' ',f.content,f.person_name,f.remark,f.project_name_snapshot) ilike %s"
                params.append(_like(query["keyword"]))
            if "task_occurrence_id" in query:
                self._require(tx, "task_occurrences", query["task_occurrence_id"])
            target = None
            if "item_id" in query:
                target = self._require(tx, "items", query["item_id"])
                if query["purpose"] != "settlement":
                    condition += " and (exists(select 1 from cash.settlements s where s.flow_id=f.id and s.item_id=%s) or exists(select 1 from cash.items i where i.origin_flow_id=f.id and i.id=%s))"
                    params.extend([query["item_id"], query["item_id"]])
            balance_cte, running, balance_join = "", "null::numeric", ""
            account_ids = query.get("account_id")
            if isinstance(account_ids, str):
                account_ids = [account_ids]
            if account_ids is not None:
                accounts = tx.fetch_all("select id from cash.accounts where id=any(%s::uuid[])", (account_ids,))
                if len(accounts) != len(account_ids):
                    _missing()
                condition += " and (f.from_account_id=any(%s::uuid[]) or f.to_account_id=any(%s::uuid[]))"
                params.extend([account_ids, account_ids])
            if account_ids is not None and len(account_ids) == 1:
                balance_cte = """, account_ledger as materialized (select f.id,a.opening_amount+
                    sum(case when f.to_account_id=a.id then f.amount else -f.amount end)
                    over(order by f.occurred_on,f.created_at,f.id rows unbounded preceding) as balance
                    from cash.accounts a join cash.flows f on f.from_account_id=a.id or f.to_account_id=a.id
                    where a.id=%s) """
                running = "ledger.balance"
                balance_join = " join account_ledger ledger on ledger.id=f.id"
            base_sql = f"select f.* from cash.flows f where {condition}"
            page_sort = query["sort"] + " " + query["order"] + ", created_at " + query["order"] + ", id " + query["order"]
            page_cte = f"with selected_page as materialized ({base_sql} order by {page_sort} limit %s offset %s)"
            prefix = [*params, query["page_size"], (query["page"] - 1) * query["page_size"]]
            if balance_cte:
                prefix.append(account_ids[0])
            joins = _FLOW_JOINS.replace("from cash.flows f", "from selected_page f")
            sql = f"{page_cte}{balance_cte} select {_FLOW_COLUMNS}, f.created_at as recorded_at,{running} as account_running_balance, b.obligation_allocated_amount,b.expense_allocated_amount {joins} join ({_FLOW_BUDGET}) b on b.id=f.id {balance_join}"
            context = None
            if query["purpose"] == "task_link":
                template = self._require(tx, "task_templates", query["template_id"])
                occurrence = tx.fetch_one("select * from cash.task_occurrences where template_id=%s and month=%s", (query["template_id"], query["month"]))
                kind = occurrence["template_values_snapshot"]["kind"] if occurrence else template["kind"]
                eligible_month = occurrence is not None or template["enabled"] and template["effective_from_month"] <= query["month"] and (template["effective_to_month"] is None or query["month"] <= template["effective_to_month"])
                context = {"template_id": template["id"], "template_version": template["version"], "occurrence_id": occurrence["id"] if occurrence else None, "version": occurrence["version"] if occurrence else None}
                sql = f"select r.*,r.obligation_allocated_amount as allocated_amount,r.amount-r.obligation_allocated_amount as available_amount,case when not %s then 'target_incompatible' when kind<>%s then 'direction_mismatch' when task is not null then 'already_claimed' else null end as unavailable_reason from ({sql}) r"
                prefix = [eligible_month, kind, *prefix]
            elif query["purpose"] == "settlement":
                kind = query["settlement_kind"]
                compatible = {"cash_repayment": {"loan"}, "company_collection": {"company_receivable"}, "expense_payment": {"expense"}, "expense_refund": {"expense"}}
                expected_kind = "payment" if kind == "expense_payment" or kind == "cash_repayment" and target["obligation_direction"] == "payable" else "receipt"
                budget = "expense_allocated_amount" if kind.startswith("expense_") else "obligation_allocated_amount"
                context = {"item_id": target["id"], "item_version": target["version"]}
                target_values = tx.fetch_one(f"select * from ({_ITEM_AMOUNTS}) i where i.id=%s", (query["item_id"],))
                remaining = min(target_values["paid_amount"], target_values["original_amount"]) - target_values["refund_amount"] if kind == "expense_refund" else target_values["original_amount"] - target_values["paid_amount"] if kind == "expense_payment" else target_values["remaining_obligation_amount"]
                sql = f"select r.*,r.{budget} as allocated_amount,r.amount-r.{budget} as available_amount,case when not %s then 'target_incompatible' when r.kind<>%s then 'direction_mismatch' when (r.project->>'id') is distinct from %s or r.occurred_on<%s then 'target_incompatible' when r.amount-r.{budget}<=0 or %s<=0 then 'no_available_amount' else null end as unavailable_reason from ({sql}) r"
                prefix = [target["type"] in compatible[kind], expected_kind, target["oa_project_id"], target["origin_date"], remaining, *prefix]
            if query["purpose"] != "list":
                sql = f"select r.*,unavailable_reason is null as selectable from ({sql}) r"
            rows = tx.fetch_all(f"select * from ({sql}) r order by {query['sort']} {query['order']},recorded_at {query['order']},id {query['order']}", tuple(prefix))
            for row in rows:
                row.pop("recorded_at")
            totals = tx.fetch_one(f"select count(*) as flow_count,coalesce(sum(amount) filter(where kind='receipt'),0) as income_amount,coalesce(sum(amount) filter(where kind='payment'),0) as expense_amount,coalesce(sum(amount) filter(where kind='transfer'),0) as transfer_amount,min(occurred_on) as first_day,max(occurred_on) as last_day from ({base_sql}) filtered", tuple(params))
            result = {"rows": rows, "pagination": {"page": query["page"], "page_size": query["page_size"], "total": totals["flow_count"]}}
            start, end = query.get("date_from", totals.pop("first_day")), query.get("date_to", totals.pop("last_day"))
            totals.pop("first_day", None)
            totals.pop("last_day", None)
            balances = self._balances(tx, start, end, account_ids) if start is not None else []
            result["summary"] = {"period": {"date_from": start, "date_to": end}, "filtered_totals": totals, "account_balances": balances}
            if context is not None:
                result["selection_context"] = context
            return result

    @staticmethod
    def _balances(tx: Any, start: date, end: date, account_ids: list[str] | None) -> list[dict[str, Any]]:
        return tx.fetch_all("""select a.id as account_id,a.name as account_name,a.opening_date,
            case when a.opening_date>%s then 'not_started' when a.opening_date>%s then 'starts_during_period' else 'complete' end as coverage_state,
            case when a.opening_date>%s then null else greatest(a.opening_date,%s) end as coverage_start,
            case when a.opening_date<=%s then a.opening_amount+coalesce(d.before_net,0) end as opening_balance,
            case when a.opening_date<=%s then a.opening_amount+coalesce(d.before_net,0) end as balance_at_coverage_start,
            case when a.opening_date<=%s then coalesce(d.inflow,0) end as period_inflow,
            case when a.opening_date<=%s then coalesce(d.outflow,0) end as period_outflow,
            case when a.opening_date<=%s then a.opening_amount+coalesce(d.before_net,0)+coalesce(d.inflow,0)-coalesce(d.outflow,0) end as ending_balance
            from cash.accounts a left join lateral (select
              sum(case when f.to_account_id=a.id then f.amount else -f.amount end) filter(where f.occurred_on<%s) as before_net,
              sum(f.amount) filter(where f.occurred_on>=%s and f.to_account_id=a.id) as inflow,
              sum(f.amount) filter(where f.occurred_on>=%s and f.from_account_id=a.id) as outflow
              from cash.flows f where (f.from_account_id=a.id or f.to_account_id=a.id)
              and f.occurred_on>=a.opening_date and f.occurred_on<=%s) d on true
            where (%s::uuid[] is null or a.id=any(%s::uuid[])) order by a.name,a.id""", (end, start, end, start, start, end, end, end, end, start, start, start, end, account_ids, account_ids))

    def get_flow(self, flow_id: str) -> dict[str, Any]:
        with self.snapshot() as tx:
            flow = tx.fetch_one(f"select {_FLOW_COLUMNS},null::numeric as account_running_balance,f.remark,f.created_by_account,f.created_by_name,f.created_at,f.updated_at {_FLOW_JOINS} where f.id=%s", (flow_id,))
            if flow is None:
                _missing()
            allocations = tx.fetch_all(f"select {_SETTLEMENT_COLUMNS} {_SETTLEMENT_JOINS} where s.flow_id=%s order by s.occurred_on,s.id limit 20", (flow_id,))
            counts = tx.fetch_one("""select
                (select count(*) from cash.settlements where flow_id=%s) as settlement_count,
                (select count(*) from cash.items where origin_flow_id=%s and origin_mode='created') as source_owned_item_count,
                (select count(*) from cash.items i where i.origin_flow_id=%s or exists(select 1 from cash.settlements s where s.flow_id=%s and s.item_id=i.id)) as item_count,
                exists(select 1 from cash.items i where i.origin_flow_id=%s and i.origin_mode='created'
                    and (exists(select 1 from cash.settlements s where s.item_id=i.id or s.source_item_id=i.id)
                      or exists(select 1 from cash.items child where (child.related_obligation_id=i.id or child.ticket_source_id=i.id)
                        and child.origin_flow_id is distinct from i.origin_flow_id))) as source_correction_required""", (flow_id, flow_id, flow_id, flow_id, flow_id))
            items = tx.fetch_all("""select i.id,i.version,i.content,i.origin_mode from cash.items i where i.origin_flow_id=%s
                or exists(select 1 from cash.settlements s where s.flow_id=%s and s.item_id=i.id) order by i.id limit 20""", (flow_id, flow_id))
            task = flow["task"]
            tasks = [{"id": task["occurrence_id"], "version": task["occurrence_version"], "title": task["title"]}] if task else []
            return {"flow": flow, "allocations": allocations, "allocation_count": counts["settlement_count"], "allocations_has_more": counts["settlement_count"] > 20, "task": task,
                    "delete_impact": {"flow_version": flow["version"], "task_count": len(tasks), **counts, "tasks": tasks, "items": items, "preview_truncated": counts["item_count"] > 20}}

    def list_items(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            for field, table in (("origin_flow_id", "flows"), ("related_obligation_id", "items"), ("ticket_source_id", "items")):
                if field in query:
                    self._require(tx, table, query[field])
            condition, params = _where(query, {"type": "i.type", "ledger_group": "i.ledger_group", "counterparty": "i.counterparty", "project_id": "i.oa_project_id", "bill_label_id": "i.bill_label_id", "bill_month": "i.bill_month", "is_opening": "i.is_opening", "origin_flow_id": "i.origin_flow_id", "related_obligation_id": "i.related_obligation_id", "ticket_source_id": "i.ticket_source_id"})
            if "origin_date_from" in query:
                condition += " and i.origin_date between %s and %s"
                params.extend([query["origin_date_from"], query["origin_date_to"]])
            if "has_bill_label" in query:
                condition += " and (i.bill_label_id is not null)=%s"
                params.append(query["has_bill_label"])
            if "keyword" in query:
                condition += " and concat_ws(' ',i.content,i.counterparty,i.project_name_snapshot,i.ticket_provider) ilike %s"
                params.append(_like(query["keyword"]))
            kind, purpose = query.get("settlement_kind"), query["purpose"]
            selector = "null::text"
            context, extra = {}, []
            if purpose != "list":
                eligible_types = ({"ticket_offset": {"ticket_source"}, "ticket_use": {"ticket_source"}, "non_ticket_offset": {"expense"}} if purpose == "settlement_source" else {"cash_repayment": {"loan"}, "company_collection": {"company_receivable"}, "expense_payment": {"expense"}, "expense_refund": {"expense"}, "ticket_offset": {"loan", "company_receivable"}, "non_ticket_offset": {"loan", "company_receivable"}}).get(kind, set())
                selector = "case when not (i.type=any(%s::text[])) then 'target_incompatible'"
                extra.append(sorted(eligible_types))
                personal_owner = None
                if kind in {"ticket_offset", "non_ticket_offset"}:
                    settings = tx.fetch_one("select personal_counterparty,personal_opening_date from cash.settings where id=1")
                    if settings is None:
                        raise RuntimeError("Cash settings row is missing.")
                    if settings["personal_opening_date"] is not None:
                        personal_owner = settings["personal_counterparty"]
                for key, table in (("flow_id", "flows"), ("source_item_id", "items"), ("item_id", "items")):
                    if key in query:
                        parent = self._require(tx, table, query[key])
                        context[key] = parent["id"]
                        context[key.removesuffix("_id") + "_version"] = parent["version"]
                        if purpose == "settlement_source" and key == "item_id" and kind in {"ticket_offset", "non_ticket_offset"} and parent["ledger_group"] == "personal":
                            selector += " when %s::text is null or %s::text is distinct from %s::text then 'target_incompatible'"
                            extra.extend([personal_owner, personal_owner, parent["counterparty"]])
                            if kind == "ticket_offset":
                                selector += " when i.ticket_provider is distinct from %s then 'target_incompatible'"
                            else:
                                selector += " when not exists(select 1 from cash.items owner where owner.id=i.related_obligation_id and owner.type='loan' and owner.ledger_group='personal' and owner.counterparty=%s) then 'target_incompatible'"
                            extra.append(parent["counterparty"])
                        elif purpose == "settlement_target" and key == "source_item_id" and kind in {"ticket_offset", "non_ticket_offset"}:
                            source_owner = parent["ticket_provider"] if parent["type"] == "ticket_source" and kind == "ticket_offset" else None
                            if parent["type"] == "expense" and kind == "non_ticket_offset" and parent["related_obligation_id"] is not None:
                                owner = self._require(tx, "items", parent["related_obligation_id"])
                                if owner["type"] == "loan" and owner["ledger_group"] == "personal":
                                    source_owner = owner["counterparty"]
                            selector += " when i.ledger_group='personal' and (%s::text is null or i.counterparty is distinct from %s::text or i.counterparty is distinct from %s::text) then 'target_incompatible'"
                            extra.extend([personal_owner, personal_owner, source_owner])
                            selector += " when i.ledger_group is distinct from 'personal' and i.oa_project_id is distinct from %s then 'target_incompatible'"
                            extra.append(parent["oa_project_id"])
                        else:
                            selector += " when i.oa_project_id is distinct from %s then 'target_incompatible'"
                            extra.append(parent["oa_project_id"])
                        if key != "flow_id":
                            selector += " when i.id=%s then 'target_incompatible'"
                            extra.append(parent["id"])
                        elif kind in {"cash_repayment", "company_collection", "expense_payment", "expense_refund"}:
                            selector += " when (case when %s='expense_payment' or (%s='cash_repayment' and i.obligation_direction='payable') then 'payment' else 'receipt' end)<>%s then 'direction_mismatch'"
                            extra.extend([kind, kind, parent["kind"]])
                            selector += " when i.origin_date>%s then 'target_incompatible'"
                            extra.append(parent["occurred_on"])
                available = "i.available_source_amount" if purpose == "settlement_source" else "least(i.paid_amount,i.original_amount)-i.refund_amount" if kind == "expense_refund" else "i.original_amount-i.paid_amount" if kind == "expense_payment" else "i.remaining_obligation_amount"
                selector += f" when {available}<=0 then 'no_available_amount' else null end"
            page_order = f"{query['sort']} {query['order']},id {query['order']}"
            total = tx.fetch_one(f"select count(*) as total from cash.items i where {condition}", tuple(params))["total"]
            amounts = _ITEM_AMOUNTS.replace("from cash.items i", "from selected_page i")
            sql = f"""with selected_page as materialized (
                select i.* from cash.items i where {condition} order by {page_order} limit %s offset %s)
                select i.*, {_PROJECT.format(a='i')} as project,
                case when c.id is null then null else jsonb_build_object('id',c.id::text,'name',c.name,'group',c."group") end as category,
                {selector} as unavailable_reason from ({amounts}) i left join cash.categories c on c.id=i.category_id"""
            sql = f"select r.*,unavailable_reason is null as selectable from ({sql}) r"
            rows = tx.fetch_all(f"{sql} order by {page_order}", (*params, query["page_size"], (query["page"] - 1) * query["page_size"], *extra))
            result = {"rows": rows, "pagination": {"page": query["page"], "page_size": query["page_size"], "total": total}}
            if context:
                result["selection_context"] = context
            return result

    def get_item(self, item_id: str) -> dict[str, Any]:
        with self.snapshot() as tx:
            item = tx.fetch_one("""select i.*,case when c.id is null then null else jsonb_build_object('id',c.id::text,'name',c.name,'group',c."group") end as category
                from cash.items i left join cash.categories c on c.id=i.category_id where i.id=%s""", (item_id,))
            if item is None:
                _missing()
            values = tx.fetch_one(f"select * from ({_ITEM_AMOUNTS}) i where i.id=%s", (item_id,))
            keys = {"loan": ("original_amount", "cash_settled_amount", "ticket_offset_amount", "non_ticket_offset_amount", "remaining_obligation_amount"), "company_receivable": ("original_amount", "cash_settled_amount", "ticket_offset_amount", "non_ticket_offset_amount", "remaining_obligation_amount"), "expense": ("original_amount", "paid_amount", "refund_amount", "net_expense_amount", "available_source_amount"), "ticket_source": ("original_amount", "used_amount", "offset_amount", "available_source_amount")}[item["type"]]
            amounts = {key: values[key] for key in keys}
            if item["type"] == "ticket_source":
                amounts["provided_amount"] = amounts.pop("original_amount")
            if item["type"] == "expense":
                amounts["available_offset_amount"] = amounts.pop("available_source_amount")
            total = tx.fetch_one("select count(*) as total from cash.settlements where item_id=%s or source_item_id=%s", (item_id, item_id))["total"]
            settlements = tx.fetch_all(f"select {_SETTLEMENT_COLUMNS} {_SETTLEMENT_JOINS} where s.item_id=%s or s.source_item_id=%s order by s.occurred_on desc,s.id desc limit 20", (item_id, item_id))
            return {"item": item, "amounts": amounts, "settlements": settlements, "settlement_count": total, "settlements_has_more": total > 20}

    def list_settlements(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            for field, table in (("item_id", "items"), ("source_item_id", "items"), ("flow_id", "flows")):
                if field in query:
                    self._require(tx, table, query[field])
            condition, params = _where(query, {"item_id": "s.item_id", "source_item_id": "s.source_item_id", "flow_id": "s.flow_id", "kind": "s.kind"})
            if "date_from" in query:
                condition += " and s.occurred_on between %s and %s"
                params.extend([query["date_from"], query["date_to"]])
            sql = f"select {_SETTLEMENT_COLUMNS} {_SETTLEMENT_JOINS} where {condition}"
            result = _page(tx, sql, params, query, order=query["sort"])
            result["summary"] = {"amounts_by_kind": tx.fetch_all(f"select kind,count(*) as settlement_count,sum(amount) as amount from ({sql}) r group by kind order by kind", tuple(params))}
            return result

    def project_options(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            flow_scope, item_scope = "f.oa_project_id is not null", "i.oa_project_id is not null"
            flow_params, item_params = [], []
            has_parent = "item_id" in query or "task_occurrence_id" in query
            if "item_id" in query:
                self._require(tx, "items", query["item_id"])
                flow_scope += " and (exists(select 1 from cash.settlements s where s.flow_id=f.id and s.item_id=%s) or exists(select 1 from cash.items i where i.origin_flow_id=f.id and i.id=%s))"
                flow_params.extend([query["item_id"], query["item_id"]])
                item_scope += " and i.id=%s"
                item_params.append(query["item_id"])
            if "task_occurrence_id" in query:
                self._require(tx, "task_occurrences", query["task_occurrence_id"])
                flow_scope += " and f.task_occurrence_id=%s"
                flow_params.append(query["task_occurrence_id"])
                item_scope += " and exists(select 1 from cash.flows f where f.task_occurrence_id=%s and (f.id=i.origin_flow_id or exists(select 1 from cash.settlements s where s.flow_id=f.id and (s.item_id=i.id or s.source_item_id=i.id))))"
                item_params.append(query["task_occurrence_id"])
            if "date_to" in query:
                if has_parent and "date_from" in query:
                    flow_scope += " and f.occurred_on between %s and %s"
                    flow_params.extend([query["date_from"], query["date_to"]])
                    item_scope += " and (i.origin_date between %s and %s or exists(select 1 from cash.settlements s where (s.item_id=i.id or s.source_item_id=i.id) and s.occurred_on between %s and %s))"
                    item_params.extend([query["date_from"], query["date_to"]] * 2)
                else:
                    # Candidate identity is historical through period end, not
                    # restricted to projects first used within the visible year.
                    flow_scope += " and f.occurred_on<=%s"
                    flow_params.append(query["date_to"])
                    item_scope += " and i.origin_date<=%s"
                    item_params.append(query["date_to"])
            # Sort project/name groups, not every historical transaction. Keep
            # the same latest timestamp and deterministic name tie-break.
            sql = f"""select distinct on(id) id,name from (
                select id,name,max(updated_at) as updated_at from (
                select f.oa_project_id as id,f.project_name_snapshot as name,f.updated_at from cash.flows f where {flow_scope}
                union all select i.oa_project_id,i.project_name_snapshot,i.updated_at from cash.items i where {item_scope}
                ) history group by id,name
                ) reduced order by id,updated_at desc,name"""
            params = [*flow_params, *item_params]
            if "keyword" in query:
                sql = f"select * from ({sql}) r where name ilike %s"
                params.append(_like(query["keyword"]))
            return _page(tx, sql, params, query, order="name")

    def query_turnover(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            if query["view"] == "unsettled":
                return self._query_unsettled(tx, query)
            # Obligation events and expense events are separate contributions, never copies of cash.
            scope, scope_params = _where(query, {"ledger_group": "i.ledger_group", "counterparty": "i.counterparty", "project_id": "i.oa_project_id"})
            cte = f"""with obligations as (
                select i.id,i.original_amount,i.is_opening,i.origin_date,i.created_at,i.content,i.origin_flow_id,
                  i.ledger_group,i.counterparty,i.oa_project_id,i.project_name_snapshot,i.obligation_direction,
                  i.original_amount-coalesce(s.settled,0) as remaining_amount,
                  case when i.type='company_receivable' and i.ticket_source_id is not null then
                    case when coalesce(s.collected,0)=0 then 'open'
                      when s.collected=i.original_amount then 'settled' else 'partial' end
                  end as ticket_collection_state
                from cash.items i left join (select item_id,sum(amount) as settled,
                  sum(amount) filter(where kind='company_collection') as collected from cash.settlements
                  where kind in ('cash_repayment','company_collection','ticket_offset','non_ticket_offset')
                  and occurred_on<=%s group by item_id) s on s.item_id=i.id
                where i.type in ('loan','company_receivable') and i.origin_date<=%s and {scope}
            ), events as (
                select 'item:'||i.id as row_id,case when i.is_opening then 'opening' else 'principal' end as row_kind,
                  i.id as item_id,i.origin_date as occurred_on,i.created_at,0 as rank,i.content,
                  i.original_amount, null::numeric as repayment_amount,null::numeric as reimbursement_received_amount,
                  null::numeric as ticket_offset_amount,null::numeric as non_ticket_offset_amount,null::numeric as real_expense_amount,
                  case when i.origin_flow_id is not null and i.obligation_direction='payable' and not i.is_opening then i.original_amount end as cash_received_amount,
                  case when i.origin_flow_id is not null and i.obligation_direction='receivable' and not i.is_opening then i.original_amount end as cash_paid_amount,
                  0::numeric as reduction,i.origin_flow_id as flow_id,null::uuid as settlement_id,null::uuid as expense_item_id,f.category_id
                from obligations i left join cash.flows f on f.id=i.origin_flow_id
                where i.origin_date>=%s
                union all
                select 'settlement:'||s.id,'settlement',s.item_id,s.occurred_on,s.created_at,1,coalesce(s.remark,i.content),null,
                  case when s.kind='cash_repayment' then s.amount end,
                  case when s.kind='company_collection' then s.amount end,
                  case when s.kind='ticket_offset' then s.amount end,
                  case when s.kind='non_ticket_offset' then s.amount end,null,
                  case when s.kind='company_collection' or (s.kind='cash_repayment' and i.obligation_direction='receivable') then s.amount end,
                  case when s.kind='cash_repayment' and i.obligation_direction='payable' then s.amount end,
                  s.amount,s.flow_id,s.id,null,
                  case when s.kind in ('cash_repayment','company_collection') then f.category_id
                    when s.source_item_id is not null then source.category_id else s.category_id end
                from cash.settlements s join obligations i on i.id=s.item_id
                left join cash.flows f on f.id=s.flow_id left join cash.items source on source.id=s.source_item_id
                where s.kind in ('cash_repayment','company_collection','ticket_offset','non_ticket_offset') and s.occurred_on between %s and %s
                union all
                select 'expense:'||e.id,'expense',e.related_obligation_id,e.origin_date,e.created_at,2,e.content,
                  null,null,null,null,null,e.original_amount,null,null,0,e.origin_flow_id,null,e.id,e.category_id
                from cash.items e join obligations i on i.id=e.related_obligation_id
                where e.type='expense' and e.origin_date between %s and %s
                union all
                select 'expense_settlement:'||s.id,'expense',e.related_obligation_id,s.occurred_on,s.created_at,3,
                  coalesce(s.remark,e.content),null,null,null,null,null,
                  case when s.kind='expense_refund' then -s.amount end,null,null,0,s.flow_id,s.id,e.id,e.category_id
                from cash.settlements s join cash.items e on e.id=s.item_id join obligations i on i.id=e.related_obligation_id
                where s.kind in ('expense_payment','expense_refund') and s.occurred_on between %s and %s
            ), complete_events as (
                select e.*,i.ledger_group,i.counterparty,i.oa_project_id,i.project_name_snapshot,i.obligation_direction,i.remaining_amount,
                  i.original_amount as obligation_original_amount,i.ticket_collection_state,
                  case when i.remaining_amount=0 then 'settled' when i.remaining_amount=i.original_amount then 'open' else 'partial' end as state
                from events e join obligations i on i.id=e.item_id
            ) """
            condition, params = _where(query, {"category_id": "e.category_id", "state": "e.state"})
            if "personal_variant" in query:
                condition += {"principal": " and e.row_kind in ('opening','principal')", "settlement": " and e.row_kind='settlement'", "neutral": " and e.row_kind='expense'"}[query["personal_variant"]]
            if "keyword" in query:
                condition += " and concat_ws(' ',e.content,e.counterparty,e.project_name_snapshot) ilike %s"
                params.append(_like(query["keyword"]))
            sql = cte + f"""select e.row_id,e.row_kind,e.ledger_group,
                case when e.ledger_group='personal' then case when e.row_kind in ('opening','principal') then 'principal' when e.row_kind='settlement' then 'settlement' else 'neutral' end end as personal_variant,
                e.occurred_on,e.item_id,e.counterparty,{_PROJECT.format(a='e')} as project,e.content,e.state,e.original_amount,
                e.repayment_amount,e.reimbursement_received_amount,e.ticket_offset_amount,e.non_ticket_offset_amount,e.real_expense_amount,
                e.cash_received_amount,e.cash_paid_amount,e.flow_id,e.settlement_id,e.expense_item_id,e.ticket_collection_state,
                e.obligation_direction,e.remaining_amount,e.obligation_original_amount,e.created_at,e.category_id from complete_events e where {condition}"""
            params = [query["date_to"], query["date_to"], *scope_params, query["date_from"], *([query["date_from"], query["date_to"]] * 3), *params]
            columns = ("repayment_amount", "reimbursement_received_amount", "ticket_offset_amount", "non_ticket_offset_amount", "real_expense_amount", "cash_received_amount", "cash_paid_amount")
            row_money = ("original_amount", *columns, "remaining_after_event")
            row_casts = ",".join(f"'{key}',p.{key}::text" for key in row_money)
            summary_casts = ",".join(f"'{key}',t.{key}::text" for key in ("principal_amount", "opening_adjustment_amount", *columns))
            combined = tx.fetch_one(f"""with matched as materialized ({sql}),
                selected_page as materialized (select * from matched order by {query['sort']} {query['order']} nulls last,row_id {query['order']} limit %s offset %s),
                page_rows as (select m.*,
                  case when c.id is not null then jsonb_build_object('id',c.id,'name',c.name,'group',c."group") end as category,
                  case when m.settlement_id is not null then s.remark else i.remark end as remark,
                  case when m.row_kind='expense' then null
                  when m.row_kind in ('opening','principal') then m.original_amount
                  else m.obligation_original_amount-coalesce((select sum(s.amount) from cash.settlements s
                    where s.item_id=m.item_id and s.kind in ('cash_repayment','company_collection','ticket_offset','non_ticket_offset')
                    and (s.occurred_on,s.created_at,s.id)<=(m.occurred_on,m.created_at,m.settlement_id)),0) end as remaining_after_event
                  from selected_page m
                  left join cash.categories c on c.id=m.category_id
                  left join cash.items i on i.id=coalesce(m.expense_item_id,m.item_id)
                  left join cash.settlements s on s.id=m.settlement_id),
                totals as (select count(*) as event_count,
                  coalesce(sum(original_amount) filter(where row_kind='principal'),0.00) as principal_amount,
                  coalesce(sum(original_amount) filter(where row_kind='opening'),0.00) as opening_adjustment_amount,
                  {','.join('coalesce(sum('+column+'),0.00) as '+column for column in columns)} from matched),
                unique_items as (select distinct item_id,obligation_direction,remaining_amount from matched)
                select t.event_count as total,
                  coalesce((select jsonb_agg((to_jsonb(p)-'obligation_direction'-'remaining_amount'-'obligation_original_amount'-'created_at'-'category_id')||jsonb_build_object({row_casts})
                    order by p.{query['sort']} {query['order']} nulls last,p.row_id {query['order']}) from page_rows p),'[]'::jsonb) as rows,
                  jsonb_build_object('event_count',t.event_count,{summary_casts},'remaining_obligation_amount',
                    (select jsonb_build_object('receivable',coalesce(sum(remaining_amount) filter(where obligation_direction='receivable'),0.00)::text,
                      'payable',coalesce(sum(remaining_amount) filter(where obligation_direction='payable'),0.00)::text) from unique_items)) as summary
                from totals t""", (*params, query["page_size"], (query["page"] - 1) * query["page_size"]))
            return {"view": "events", "rows": combined["rows"], "summary": combined["summary"], "pagination": {"page": query["page"], "page_size": query["page_size"], "total": combined["total"]}}

    @staticmethod
    def _query_unsettled(tx: Any, query: dict[str, Any]) -> dict[str, Any]:
        condition, params = _where(query, {"ledger_group": "i.ledger_group", "counterparty": "i.counterparty", "project_id": "i.oa_project_id"})
        if "keyword" in query:
            condition += " and concat_ws(' ',i.content,i.counterparty,i.project_name_snapshot) ilike %s"
            params.append(_like(query["keyword"]))
        order = f"{query['sort']} {query['order']} nulls last,item_id {query['order']}"
        money = ",".join(f"'{key}',p.{key}::text" for key in ("original_amount", "settled_amount", "remaining_amount"))
        result = tx.fetch_one(f"""with scope as materialized (
            select i.* from cash.items i where i.type in ('loan','company_receivable') and i.origin_date<=%s and {condition}
          ), settled as (select s.item_id,sum(s.amount) as amount from cash.settlements s join scope i on i.id=s.item_id
            where s.kind in ('cash_repayment','company_collection','ticket_offset','non_ticket_offset') and s.occurred_on<=%s group by s.item_id),
          matched as materialized (select i.id as item_id,i.type,i.origin_date,i.ledger_group,i.counterparty,
            {_PROJECT.format(a='i')} as project,i.content,i.obligation_direction,i.original_amount,i.version,
            coalesce(s.amount,0.00) as settled_amount,i.original_amount-coalesce(s.amount,0.00) as remaining_amount
            from scope i left join settled s on s.item_id=i.id where i.original_amount-coalesce(s.amount,0)>0),
          selected_page as (select * from matched order by {order} limit %s offset %s)
          select count(*) as total,
            coalesce((select jsonb_agg(to_jsonb(p)||jsonb_build_object({money}) order by p.{order}) from selected_page p),'[]'::jsonb) as rows,
            jsonb_build_object('item_count',count(*),'remaining_obligation_amount',jsonb_build_object(
              'receivable',coalesce(sum(remaining_amount) filter(where obligation_direction='receivable'),0.00)::text,
              'payable',coalesce(sum(remaining_amount) filter(where obligation_direction='payable'),0.00)::text)) as summary
          from matched""", (query["date_to"], *params, query["date_to"], query["page_size"], (query["page"] - 1) * query["page_size"]))
        return {"view": "unsettled", "rows": result["rows"], "summary": result["summary"], "pagination": {"page": query["page"], "page_size": query["page_size"], "total": result["total"]}}

    def query_tickets(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            condition, params = _where(query, {"ticket_provider": "i.ticket_provider", "project_id": "i.oa_project_id"})
            condition += " and i.type='ticket_source' and i.ticket_provided_on<=%s"
            params.append(query["date_to"])
            if query["view"] == "period":
                condition += " and i.ticket_provided_on>=%s"
                params.append(query["date_from"])
            if "keyword" in query:
                condition += " and concat_ws(' ',i.content,i.ticket_provider,i.project_name_snapshot) ilike %s"
                params.append(_like(query["keyword"]))
            sql = f"""with sources as materialized (select i.* from cash.items i where {condition}),
                usage as (select s.source_item_id,sum(s.amount) as used_amount,
                  sum(s.amount) filter(where s.kind='ticket_offset') as offset_amount
                  from cash.settlements s join sources i on i.id=s.source_item_id
                  where s.kind in ('ticket_use','ticket_offset') and s.occurred_on<=%s group by s.source_item_id),
                receivables as materialized (select c.id,c.ticket_source_id,c.original_amount from cash.items c join sources i on i.id=c.ticket_source_id
                  where c.type='company_receivable' and c.origin_date<=%s),
                receipts as (select s.item_id,sum(s.amount) filter(where s.kind='company_collection') as cash_received_amount,
                  sum(s.amount) filter(where s.kind in ('ticket_offset','non_ticket_offset')) as noncash_settled_amount
                  from cash.settlements s join receivables c on c.id=s.item_id
                  where s.kind in ('company_collection','ticket_offset','non_ticket_offset') and s.occurred_on<=%s group by s.item_id),
                collection as (select c.ticket_source_id,sum(c.original_amount) as receivable_amount,
                  sum(coalesce(r.cash_received_amount,0)) as cash_received_amount,
                  sum(coalesce(r.noncash_settled_amount,0)) as noncash_settled_amount
                  from receivables c left join receipts r on r.item_id=c.id group by c.ticket_source_id)
                select i.id,i.version,i.ticket_provider,i.ticket_provided_on,i.content,{_PROJECT.format(a='i')} as project,
                i.original_amount as provided_amount,coalesce(u.used_amount,0) as used_amount,coalesce(u.offset_amount,0) as offset_amount,
                i.original_amount-coalesce(u.used_amount,0) as available_source_amount,coalesce(r.receivable_amount,0) as receivable_amount,
                coalesce(r.cash_received_amount,0) as cash_received_amount,
                coalesce(r.noncash_settled_amount,0) as noncash_settled_amount,
                coalesce(r.receivable_amount,0)-coalesce(r.cash_received_amount,0)-coalesce(r.noncash_settled_amount,0) as remaining_receivable_amount,
                case when r.ticket_source_id is null then 'unregistered' when coalesce(r.cash_received_amount,0)=0 then 'open'
                  when r.cash_received_amount=r.receivable_amount then 'settled' else 'partial' end as collection_state,
                case when coalesce(u.used_amount,0)=0 then 'unused' when u.used_amount=i.original_amount then 'used' else 'partial' end as state
                from sources i left join usage u on u.source_item_id=i.id left join collection r on r.ticket_source_id=i.id"""
            params += [query["date_to"]] * 3
            if "state" in query:
                state_filter, state_params = _where(query, {"state": "r.state"})
                sql = f"select * from ({sql}) r where {state_filter}"
                params.extend(state_params)
            if query["view"] == "pending_collection":
                sql = f"select * from ({sql}) r where remaining_receivable_amount>0"
            names = ("provided_amount", "used_amount", "offset_amount", "available_source_amount", "receivable_amount", "cash_received_amount", "noncash_settled_amount", "remaining_receivable_amount")
            casts = ",".join(f"'{name}',round(p.{name},2)::text" for name in names)
            totals = ",".join(f"'{name}',coalesce(sum({name}),0.00)::text" for name in names)
            order = f"{query['sort']} {query['order']} nulls last,id {query['order']}"
            result = tx.fetch_one(f"""with matched as materialized ({sql}),
              selected_page as (select * from matched order by {order} limit %s offset %s)
              select count(*) as total,
                coalesce((select jsonb_agg(to_jsonb(p)||jsonb_build_object({casts}) order by p.{order}) from selected_page p),'[]'::jsonb) as rows,
                jsonb_build_object({totals}) as summary from matched""", (*params, query["page_size"], (query["page"] - 1) * query["page_size"]))
            return {"view": query["view"], "rows": result["rows"], "summary": result["summary"], "pagination": {"page": query["page"], "page_size": query["page_size"], "total": result["total"]}}

    def query_personal(self, query: dict[str, Any]) -> dict[str, Any]:
        with self.snapshot() as tx:
            start, end = date(query["year"], 1, 1), date(query["year"], 12, 31)
            settings = tx.fetch_one("select personal_opening_date,personal_counterparty from cash.settings where id=1")
            if settings is None:
                raise RuntimeError("Cash settings row is missing.")
            opening = settings["personal_opening_date"]
            counterparty = settings["personal_counterparty"]
            if counterparty is not None and tx.fetch_one("select exists(select 1 from cash.items where type='loan' and ledger_group='personal' and counterparty is distinct from %s) as conflict", (counterparty,))["conflict"]:
                raise CashError("cash_conflict", "个人账包含其他归属人的历史记录，请先核对归属。", 409)
            if counterparty is None or opening is None:
                summary = {name: None for name in ("opening_obligation_amount", "opening_adjustment_amount", "new_principal_amount", "cash_repayment_amount", "ticket_offset_amount", "non_ticket_offset_amount", "remaining_obligation_amount", "year_principal_amount")}
                summary.update(counterparty=counterparty, coverage={"state": "unconfigured", "opening_date": opening, "coverage_start": None},
                    month_principal_totals=[{"month": f"{query['year']:04d}-{n:02d}", "principal_amount": None, "coverage_state": "unconfigured"} for n in range(1, 13)])
                return {"rows": [], "summary": summary, "pagination": {"page": query["page"], "page_size": query["page_size"], "total": 0}}
            scope, params = _where(query, {"bill_label_id": "i.bill_label_id", "project_id": "i.oa_project_id", "bill_month": "i.bill_month"})
            scope += " and i.type='loan' and i.ledger_group='personal' and i.counterparty=%s"
            params.append(counterparty)
            if "keyword" in query:
                scope += " and concat_ws(' ',i.content,i.counterparty,i.project_name_snapshot,b.bank_name,b.label) ilike %s"
                params.append(_like(query["keyword"]))
            base = f"select i.* from cash.items i left join cash.bill_labels b on b.id=i.bill_label_id where {scope}"
            summary = tx.fetch_one(f"""with owned as materialized ({base}), reductions as (
                select s.item_id,sum(s.amount) filter(where s.occurred_on<%s) as before_settled,
                  sum(s.amount) filter(where s.kind='cash_repayment' and s.occurred_on>=%s) as cash_repaid,
                  sum(s.amount) filter(where s.kind='ticket_offset' and s.occurred_on>=%s) as ticket_repaid,
                  sum(s.amount) filter(where s.kind='non_ticket_offset' and s.occurred_on>=%s) as non_ticket_repaid
                from cash.settlements s join owned i on i.id=s.item_id
                where s.kind in ('cash_repayment','ticket_offset','non_ticket_offset') and s.occurred_on<=%s group by s.item_id
              ), amounts as (select i.*,coalesce(s.before_settled,0) as before_settled,coalesce(s.cash_repaid,0) as cash_repaid,
                  coalesce(s.ticket_repaid,0) as ticket_repaid,coalesce(s.non_ticket_repaid,0) as non_ticket_repaid
                from owned i left join reductions s on s.item_id=i.id where i.origin_date<=%s)
                select coalesce(sum(original_amount-before_settled) filter(where origin_date<%s or (is_opening and origin_date=%s)),0) as opening_obligation_amount,
                  coalesce(sum(original_amount) filter(where is_opening and origin_date>%s and origin_date<=%s),0) as opening_adjustment_amount,
                  coalesce(sum(original_amount) filter(where not is_opening and origin_date between %s and %s),0) as new_principal_amount,
                  coalesce(sum(cash_repaid),0) as cash_repayment_amount,coalesce(sum(ticket_repaid),0) as ticket_offset_amount,
                  coalesce(sum(non_ticket_repaid),0) as non_ticket_offset_amount,
                  coalesce(sum(original_amount-before_settled-cash_repaid-ticket_repaid-non_ticket_repaid),0) as remaining_obligation_amount
                from amounts""", (*params, start, start, start, start, end, end, start, start, start, end, start, end))
            coverage_state = "unconfigured" if opening is None else "not_started" if opening > end else "starts_during_period" if opening > start else "complete"
            summary["coverage"] = {"state": coverage_state, "opening_date": opening, "coverage_start": max(start, opening) if opening is not None and opening <= end else None}
            if coverage_state != "complete":
                summary["opening_obligation_amount"] = None
            if coverage_state in {"unconfigured", "not_started"}:
                for key in tuple(summary):
                    if key != "coverage":
                        summary[key] = None
            summary["counterparty"] = counterparty
            monthly = tx.fetch_all(f"""with owned as ({base}), totals as (
                select date_trunc('month',origin_date)::date as month,sum(original_amount) as amount from owned
                where not is_opening and origin_date between %s and %s group by 1)
                select to_char(m.month,'YYYY-MM') as month,
                  case when (m.month+interval '1 month')::date<=%s then null else coalesce(t.amount,0.00) end as principal_amount,
                  case when (m.month+interval '1 month')::date<=%s then 'not_started' when m.month<%s then 'starts_during_period' else 'complete' end as coverage_state
                from generate_series(%s::date,%s::date,interval '1 month') m(month) left join totals t on t.month=m.month order by m.month""",
                (*params, start, end, opening, opening, opening, start, date(query["year"], 12, 1)))
            summary["month_principal_totals"] = monthly
            summary["year_principal_amount"] = summary["new_principal_amount"]
            if query["view"] == "matrix":
                sql = f"""with owned as materialized ({base}), groups as (
                  select distinct bill_label_id from owned where origin_date<=%s
                ), months as (select generate_series(%s::date,%s::date,interval '1 month')::date as month),
                monthly as (select bill_label_id,date_trunc('month',origin_date)::date as month,sum(original_amount) as amount,count(*) as item_count
                  from owned where not is_opening group by bill_label_id,date_trunc('month',origin_date)::date)
                select coalesce(g.bill_label_id::text,'non_bill') as row_key,b.bank_name,b.label,
                  case when b.id is null then null else jsonb_build_object('id',b.id::text,'bank_name',b.bank_name,'label',b.label) end as bill_label,
                  jsonb_agg(jsonb_build_object('month',to_char(m.month,'YYYY-MM'),
                    'principal_amount',case when %s::date is null or (m.month+interval '1 month')::date<=%s::date then null else coalesce(a.amount,0.00)::text end,
                    'item_count',case when %s::date is null or (m.month+interval '1 month')::date<=%s::date then null else coalesce(a.item_count,0) end,
                    'coverage_state',case when %s::date is null then 'unconfigured' when (m.month+interval '1 month')::date<=%s::date then 'not_started' when m.month<%s::date then 'starts_during_period' else 'complete' end)
                    order by m.month) as months,
                  case when %s::date is null or %s::date>%s then null else coalesce(sum(a.amount),0) end as year_principal_amount
                from groups g cross join months m left join cash.bill_labels b on b.id=g.bill_label_id
                left join monthly a on a.bill_label_id is not distinct from g.bill_label_id and a.month=m.month
                group by g.bill_label_id,b.id,b.bank_name,b.label"""
                values = [*params, end, start, date(query["year"], 12, 1), opening, opening, opening, opening, opening, opening, opening, opening, opening, end]
                result = _page(tx, sql, values, query, order=query["sort"], tie="row_key")
                for row in result["rows"]:
                    row.pop("bank_name")
                    row.pop("label")
            else:
                kind = {"cash_repayments": "cash_repayment", "ticket_offsets": "ticket_offset", "non_ticket_offsets": "non_ticket_offset"}[query["view"]]
                detail_condition, detail_params = _where(query, {"source_project_id": "si.oa_project_id", "category_id": "case when s.source_item_id is null then s.category_id else si.category_id end"})
                sql = f"""select {_SETTLEMENT_COLUMNS},
                    case when b.id is null then null else jsonb_build_object('id',b.id::text,'bank_name',b.bank_name,'label',b.label) end as bill_label,
                    to_char(i.bill_month,'YYYY-MM') as bill_month,i.counterparty,{_PROJECT.format(a='i')} as project,
                    {_PROJECT.format(a='si')} as source_project
                    {_SETTLEMENT_JOINS} left join cash.bill_labels b on b.id=i.bill_label_id
                    where {scope} and s.kind=%s and s.occurred_on between %s and %s and {detail_condition}"""
                detail_values = [*params, kind, start, end, *detail_params]
                result = _page(tx, sql, detail_values, query, order=query["sort"])
                result["filtered_totals"] = tx.fetch_one(f"select count(*) as settlement_count,coalesce(sum(amount),0.00) as amount from ({sql}) r", tuple(detail_values))
            result["summary"] = summary
            return result
