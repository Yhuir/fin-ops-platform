"""Cash-only read boundary: strict query input and JSON-safe exact amounts."""

from __future__ import annotations

import json
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


_MULTI_FIELDS = {
    "account_ids": "account_id", "project_ids": "project_id", "category_ids": "category_id",
    "bill_label_ids": "bill_label_id", "kinds": "kind", "sources": "source",
    "states": "state", "groups": "group", "stage_codes": "stage_code",
}
_NULLABLE_MULTI_FIELDS = {"project_ids", "category_ids", "bill_label_ids", "stage_codes"}


def query_sets(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize explicitly allowed JSON arrays into the existing query fields.

    Callers validate their endpoint's field whitelist first. Scalar and plural
    inputs share the repository path; a plural never overrides a scalar.
    """
    result, total = dict(raw), 0
    for plural, singular in _MULTI_FIELDS.items():
        if plural not in raw:
            continue
        if singular in raw:
            invalid(f"{singular} and {plural} cannot be combined.")
        value = raw[plural]
        if not isinstance(value, str):
            invalid(f"{plural} must be a JSON array string.")
        try:
            values = json.loads(value)
        except (ValueError, RecursionError):
            invalid(f"{plural} must be valid JSON.")
        if not isinstance(values, list) or not 1 <= len(values) <= 50:
            invalid(f"{plural} must contain 1 to 50 values.")
        total += len(values)
        if total > 100:
            invalid("Cash query selections cannot exceed 100 values.")
        normalized = []
        for item in values:
            if item is None:
                if plural not in _NULLABLE_MULTI_FIELDS:
                    invalid(f"{plural} does not accept null.")
            elif not isinstance(item, str) or not item.strip() or len(item) > 200:
                invalid(f"{plural} values must be nonempty text of at most 200 characters.")
            else:
                item = item.strip()
                try:
                    item.encode("utf-8")
                except UnicodeEncodeError:
                    invalid(f"{plural} values must be valid UTF-8 text.")
                if "\x00" in item:
                    invalid(f"{plural} values cannot contain null characters.")
                if plural in {"account_ids", "category_ids", "bill_label_ids"}:
                    item = normalize_uuid(item)
            if item in normalized:
                invalid(f"{plural} cannot contain duplicate values.")
            normalized.append(item)
        result.pop(plural)
        result[singular] = normalized
    return result


def query_input(raw: dict[str, Any], allowed: set[str], sorts: set[str], default_sort: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) - allowed - {"page", "page_size", "sort", "order"}:
        invalid("Unknown cash query fields.")
    result = query_sets(raw)
    result["page"] = integer(raw.get("page", 1), "page")
    result["page_size"] = integer(raw.get("page_size", 50), "page_size", maximum=200)
    result["sort"] = raw.get("sort", default_sort)
    result["order"] = raw.get("order", "desc")
    if not isinstance(result["sort"], str) or result["sort"] not in sorts or not isinstance(result["order"], str) or result["order"] not in {"asc", "desc"}:
        invalid("Unsupported sort or order.")
    for name, value in raw.items():
        if name in _MULTI_FIELDS:
            continue
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
        if name in query and any(value not in values for value in (query[name] if isinstance(query[name], list) else [query[name]])):
            invalid(f"Unsupported {name}.")


class CashQueryService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def list_configuration(self, kind: str, raw: dict[str, Any]) -> dict[str, Any]:
        if kind not in {"accounts", "categories", "bill-labels"}:
            invalid("Unknown cash configuration list.")
        allowed = {"enabled", "keyword"} | ({"group", "groups"} if kind == "categories" else set())
        sorts = {"bank_name", "label"} if kind == "bill-labels" else {"name", "created_at"}
        query = query_input(raw, allowed, sorts, "bank_name" if kind == "bill-labels" else "name")
        enum_fields(query, group={"receipt", "payment", "turnover"})
        return serialize(self.repository.list_configuration(kind, query))

    def list_flows(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "item_id", "task_occurrence_id", "account_id", "project_id", "category_id", "kind", "person", "source", "keyword", "purpose", "template_id", "month", "settlement_kind", "account_ids", "project_ids", "category_ids", "kinds", "sources"}, {"occurred_on", "amount"}, "occurred_on")
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
        query = query_input(raw, {"type", "ledger_group", "counterparty", "project_id", "project_ids", "bill_label_id", "bill_month", "origin_date_from", "origin_date_to", "is_opening", "has_bill_label", "keyword", "purpose", "settlement_kind", "flow_id", "source_item_id", "item_id", "origin_flow_id", "related_obligation_id", "ticket_source_id"}, {"origin_date", "original_amount"}, "origin_date")
        enum_fields(query, type={"loan", "company_receivable", "expense", "ticket_source"}, ledger_group={"company", "external_person", "personal"}, purpose={"list", "settlement_target", "settlement_source"}, settlement_kind={"cash_repayment", "company_collection", "expense_payment", "expense_refund", "ticket_use", "ticket_offset", "non_ticket_offset"})
        purpose = query.setdefault("purpose", "list")
        if purpose != "list" and "settlement_kind" not in query:
            invalid("A settlement selector requires settlement_kind.")
        if purpose == "list" and {"settlement_kind", "flow_id", "source_item_id", "item_id"} & query.keys():
            invalid("Settlement context requires a selector purpose.")
        if purpose != "list" and {"origin_flow_id", "related_obligation_id", "ticket_source_id"} & query.keys():
            invalid("Item relationship filters require purpose=list.")
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
        query = query_input(raw, {"date_from", "date_to", "ledger_group", "personal_variant", "counterparty", "project_id", "category_id", "state", "keyword", "project_ids", "category_ids", "states"}, {"occurred_on", "original_amount", "repayment_amount"}, "occurred_on")
        enum_fields(query, ledger_group={"company", "external_person", "personal"}, personal_variant={"principal", "settlement"}, state={"open", "partial", "settled"})
        if "personal_variant" in query and query.get("ledger_group") != "personal":
            invalid("personal_variant requires ledger_group=personal.")
        self._period(query)
        return serialize(self.repository.query_turnover(query))

    def query_tickets(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "ticket_provider", "project_id", "state", "keyword", "project_ids", "states"}, {"ticket_provided_on", "provided_amount", "available_source_amount"}, "ticket_provided_on")
        enum_fields(query, state={"unused", "partial", "used"})
        self._period(query)
        return serialize(self.repository.query_tickets(query))

    def query_personal(self, raw: dict[str, Any]) -> dict[str, Any]:
        view = raw.get("view", "matrix")
        sorts = {"bank_name", "label", "year_principal_amount"} if view == "matrix" else {"occurred_on", "amount"}
        query = query_input(raw, {"year", "view", "bill_label_id", "project_id", "bill_month", "keyword", "project_ids", "bill_label_ids"}, sorts, "bank_name" if view == "matrix" else "occurred_on")
        if "year" not in query:
            invalid("year is required.")
        query["year"] = integer(query["year"], "year", 1, 9998)
        query["view"] = view
        enum_fields(query, view={"matrix", "cash_repayments", "ticket_offsets", "non_ticket_offsets"})
        return serialize(self.repository.query_personal(query))

    def project_options(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"date_from", "date_to", "keyword", "item_id", "task_occurrence_id"}, {"name"}, "name")
        if "date_from" not in query and not ({"item_id", "task_occurrence_id"} & query.keys()):
            invalid("A date range or explicit item/task parent is required.")
        return serialize(self.repository.project_options(query))

    @staticmethod
    def _period(query: dict[str, Any]) -> None:
        if "date_from" not in query:
            invalid("date_from and date_to are required.")
