"""Cash-only read boundary: strict query input and JSON-safe exact amounts."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from fin_ops_platform.services.cash_domain import invalid, normalize_date, normalize_uuid, serialize


def month(value: Any, name: str = "month") -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}", value):
        invalid(f"{name} must be YYYY-MM.")
    return normalize_date(value + "-01")


def integer(value: Any, name: str, minimum: int = 1, maximum: int = 2147483647) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        invalid(f"{name} must be an integer.")
    result = int(value)
    if not minimum <= result <= maximum:
        invalid(f"{name} is out of range.")
    return result


def query_input(raw: dict[str, Any], allowed: set[str], sorts: set[str], default_sort: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - allowed - {"page", "page_size", "sort", "order"}:
        invalid("Unknown cash query fields.")
    result = dict(raw)
    result["page"] = integer(raw.get("page", 1), "page")
    result["page_size"] = integer(raw.get("page_size", 50), "page_size", maximum=200)
    result["sort"] = raw.get("sort", default_sort)
    result["order"] = raw.get("order", "desc")
    if result["sort"] not in sorts or result["order"] not in {"asc", "desc"}:
        invalid("Unsupported sort or order.")
    for name, value in raw.items():
        if name.endswith("_id") and name not in {"project_id"}:
            result[name] = normalize_uuid(value)
        elif name in {"date_from", "date_to", "origin_date_from", "origin_date_to", "reminder_from", "reminder_to", "overdue_as_of"}:
            result[name] = normalize_date(value)
        elif name in {"month", "bill_month"}:
            result[name] = month(value, name)
        elif name in {"enabled", "is_opening", "has_bill_label"}:
            if value not in (True, False, "true", "false") or isinstance(value, int) and not isinstance(value, bool):
                invalid(f"{name} must be true or false.")
            result[name] = value is True or value == "true"
        elif name not in {"page", "page_size", "sort", "order", "year"}:
            if not isinstance(value, str) or not value.strip() or len(value) > 200:
                invalid(f"{name} must be nonempty text of at most 200 characters.")
            result[name] = value.strip()
    for start, end in (("date_from", "date_to"), ("origin_date_from", "origin_date_to")):
        if (start in result) != (end in result):
            invalid(f"{start} and {end} are required together.")
        if start in result and not 0 <= (result[end] - result[start]).days <= 365:
            invalid("Cash query range must be ordered and at most 366 days.")
    return result


def enum_fields(query: dict[str, Any], **fields: set[str]) -> None:
    for name, values in fields.items():
        if name in query and query[name] not in values:
            invalid(f"Unsupported {name}.")


class CashQueryService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def list_configuration(self, kind: str, raw: dict[str, Any]) -> dict[str, Any]:
        if kind not in {"accounts", "categories", "bill-labels"}:
            invalid("Unknown cash configuration list.")
        allowed = {"enabled", "keyword"} | ({"group"} if kind == "categories" else set())
        sorts = {"bank_name", "label"} if kind == "bill-labels" else {"name", "created_at"}
        query = query_input(raw, allowed, sorts, "bank_name" if kind == "bill-labels" else "name")
        enum_fields(query, group={"receipt", "payment", "turnover"})
        return serialize(self.repository.list_configuration(kind, query))

    def list_flows(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "item_id", "task_occurrence_id", "account_id", "project_id", "category_id", "kind", "person", "source", "keyword", "purpose", "template_id", "month", "settlement_kind"}, {"occurred_on", "amount"}, "occurred_on")
        enum_fields(query, kind={"receipt", "payment", "transfer"}, source={"manual", "monthly_task"}, purpose={"list", "task_link", "settlement"}, settlement_kind={"cash_repayment", "company_collection", "expense_payment", "expense_refund"})
        purpose = query.setdefault("purpose", "list")
        if "date_from" not in query and not ({"item_id", "task_occurrence_id"} & query.keys()):
            invalid("A date range or explicit item/task parent is required.")
        if purpose == "task_link" and not {"template_id", "month"} <= query.keys():
            invalid("Task selection requires template_id and month.")
        if purpose == "settlement" and not {"item_id", "settlement_kind"} <= query.keys():
            invalid("Settlement selection requires item_id and settlement_kind.")
        if purpose != "task_link" and {"template_id", "month"} & query.keys() or purpose != "settlement" and "settlement_kind" in query:
            invalid("Selection contexts cannot be mixed.")
        return serialize(self.repository.list_flows(query))

    def get_flow(self, flow_id: str) -> dict[str, Any]:
        return serialize(self.repository.get_flow(normalize_uuid(flow_id)))

    def list_items(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"type", "ledger_group", "counterparty", "project_id", "bill_label_id", "bill_month", "origin_date_from", "origin_date_to", "is_opening", "has_bill_label", "keyword", "purpose", "settlement_kind", "flow_id", "source_item_id", "item_id"}, {"origin_date", "original_amount"}, "origin_date")
        enum_fields(query, type={"loan", "company_receivable", "expense", "ticket_source"}, ledger_group={"company", "external_person", "personal"}, purpose={"list", "settlement_target", "settlement_source"}, settlement_kind={"cash_repayment", "company_collection", "expense_payment", "expense_refund", "ticket_use", "ticket_offset", "non_ticket_offset"})
        purpose = query.setdefault("purpose", "list")
        if purpose != "list" and "settlement_kind" not in query:
            invalid("A settlement selector requires settlement_kind.")
        if purpose == "list" and {"settlement_kind", "flow_id", "source_item_id", "item_id"} & query.keys():
            invalid("Settlement context requires a selector purpose.")
        if "bill_label_id" in query and query.get("has_bill_label") is False:
            invalid("bill_label_id conflicts with has_bill_label=false.")
        result = self.repository.list_items(query)
        amount_fields = {"cash_settled_amount", "ticket_offset_amount", "non_ticket_offset_amount", "remaining_obligation_amount", "paid_amount", "refund_amount", "net_expense_amount", "used_amount", "offset_amount", "available_source_amount"}
        for row in result["rows"]:
            appropriate = {"cash_settled_amount", "ticket_offset_amount", "non_ticket_offset_amount", "remaining_obligation_amount"} if row["type"] in {"loan", "company_receivable"} else {"paid_amount", "refund_amount", "net_expense_amount", "available_source_amount"} if row["type"] == "expense" else {"used_amount", "offset_amount", "available_source_amount"}
            for key in amount_fields - appropriate:
                row.pop(key)
            if row["bill_month"] is not None:
                row["bill_month"] = row["bill_month"].strftime("%Y-%m")
        return serialize(result)

    def get_item(self, item_id: str) -> dict[str, Any]:
        result = self.repository.get_item(normalize_uuid(item_id))
        if result["item"]["bill_month"] is not None:
            result["item"]["bill_month"] = result["item"]["bill_month"].strftime("%Y-%m")
        return serialize(result)

    def list_settlements(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"item_id", "source_item_id", "flow_id", "kind", "date_from", "date_to"}, {"occurred_on", "amount"}, "occurred_on")
        enum_fields(query, kind={"cash_repayment", "company_collection", "expense_payment", "expense_refund", "ticket_use", "ticket_offset", "non_ticket_offset"})
        if not {"item_id", "source_item_id", "flow_id"} & query.keys():
            invalid("A settlement parent is required.")
        return serialize(self.repository.list_settlements(query))

    def query_turnover(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "ledger_group", "counterparty", "project_id", "category_id", "state", "keyword"}, {"occurred_on", "original_amount", "repayment_amount"}, "occurred_on")
        enum_fields(query, ledger_group={"company", "external_person", "personal"}, state={"open", "partial", "settled"})
        self._period(query)
        return serialize(self.repository.query_turnover(query))

    def query_tickets(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "ticket_provider", "project_id", "state", "keyword"}, {"ticket_provided_on", "provided_amount", "available_source_amount"}, "ticket_provided_on")
        enum_fields(query, state={"unused", "partial", "used"})
        self._period(query)
        return serialize(self.repository.query_tickets(query))

    def query_personal(self, raw: dict[str, Any]) -> dict[str, Any]:
        view = raw.get("view", "matrix")
        sorts = {"bank_name", "label", "year_principal_amount"} if view == "matrix" else {"occurred_on", "amount"}
        query = query_input(raw, {"year", "view", "bill_label_id", "project_id", "bill_month", "keyword"}, sorts, "bank_name" if view == "matrix" else "occurred_on")
        if "year" not in query:
            invalid("year is required.")
        query["year"] = integer(query["year"], "year", 1, 9998)
        query["view"] = view
        enum_fields(query, view={"matrix", "cash_repayments", "ticket_offsets", "non_ticket_offsets"})
        return serialize(self.repository.query_personal(query))

    def project_options(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "keyword"}, {"name"}, "name")
        self._period(query)
        return serialize(self.repository.project_options(query))

    @staticmethod
    def _period(query: dict[str, Any]) -> None:
        if "date_from" not in query:
            invalid("date_from and date_to are required.")
