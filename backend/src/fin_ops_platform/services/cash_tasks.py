"""Cash monthly tasks: planned intent and actual cash stay separate."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.cash_domain import (
    CashError,
    check_version,
    conflict,
    enum,
    fields,
    invalid,
    normalize_bool,
    normalize_date,
    normalize_money,
    normalize_text,
    normalize_uuid,
    normalize_version,
    serialize,
    shanghai_today,
)
from fin_ops_platform.services.cash_queries import enum_fields, integer, month, query_input

_TEMPLATE_FIELDS = {"title", "kind", "execution_day", "remind_days", "effective_from_month", "effective_to_month", "enabled", "default_account_id", "default_category_id", "default_amount", "instructions"}
_IDENTITY_FIELDS = {"template_id", "month", "expected_version", "expected_template_version"}


def next_month(value: date) -> date:
    if value.year == 9999 and value.month == 12:
        invalid("Task month is outside the supported calendar.")
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def task_snapshot(template: dict[str, Any]) -> dict[str, Any]:
    return {"template_version": template["version"], **{key: template[key] for key in ("title", "kind", "remind_days", "instructions", "default_account_id", "default_category_id")}}


def occurrence_values(template: dict[str, Any], target_month: date) -> dict[str, Any]:
    return {"id": str(uuid4()), "template_id": template["id"], "month": target_month,
            "due_on": target_month.replace(day=min(template["execution_day"], calendar.monthrange(target_month.year, target_month.month)[1])),
            "planned_amount": template["default_amount"], "processing_state": "pending",
            "template_values_snapshot": task_snapshot(template), "note": None}


def occurrence_row(occurrence: dict[str, Any], actual: dict[str, Any], today: date) -> dict[str, Any]:
    snapshot = occurrence["template_values_snapshot"]
    kind, planned, amount = snapshot["kind"], occurrence["planned_amount"], actual["amount"]
    if kind == "check":
        state = "completed" if occurrence["processing_state"] == "checked" else "pending"
        amount = None
    elif amount == 0:
        state = "pending"
    elif planned is None:
        raise RuntimeError("A cash task with actual cash must retain its planned amount.")
    else:
        state = "partial" if amount < planned else "completed"
    target_month = occurrence["month"].strftime("%Y-%m")
    return {"row_key": str(occurrence["template_id"]) + ":" + target_month,
            "occurrence_id": occurrence["id"], "version": occurrence["version"],
            "template_id": occurrence["template_id"], "template_version": snapshot["template_version"],
            "month": target_month, "title": snapshot["title"], "kind": kind, "due_on": occurrence["due_on"],
            "remind_on": occurrence["due_on"] - timedelta(days=snapshot["remind_days"]),
            "planned_amount": planned, "actual_amount": amount, "state": state,
            "marked_unpaid": occurrence["processing_state"] == "unpaid", "need_planned_amount": kind != "check" and planned is None,
            "is_over_plan": kind != "check" and planned is not None and amount > planned,
            "over_plan_amount": None if kind == "check" else max(amount - planned, Decimal("0.00")) if planned is not None else Decimal("0.00"),
            "is_overdue": state != "completed" and occurrence["due_on"] < today, "is_due": occurrence["due_on"] == today,
            "note": occurrence["note"], "flow_count": actual["flow_count"]}


class CashTaskService:
    def __init__(self, repository: Any, cash_service: Any, *, today=shanghai_today) -> None:
        self.repository, self.cash, self.today = repository, cash_service, today

    def _template_values(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {"title", "kind", "execution_day", "remind_days", "effective_from_month"}
        values = fields(payload, _TEMPLATE_FIELDS | {"id"}, required)
        if type(values["execution_day"]) is not int or type(values["remind_days"]) is not int:
            invalid("Task day fields must be JSON integers.")
        result = {"title": normalize_text(values["title"]), "kind": enum(values["kind"], {"receipt", "payment", "check"}),
                  "execution_day": integer(values["execution_day"], "execution_day", 1, 31),
                  "remind_days": integer(values["remind_days"], "remind_days", 0, 31),
                  "effective_from_month": month(values["effective_from_month"], "effective_from_month"),
                  "effective_to_month": month(values["effective_to_month"], "effective_to_month") if values.get("effective_to_month") is not None else None,
                  "enabled": normalize_bool(values.get("enabled", True)),
                  "default_account_id": normalize_uuid(values.get("default_account_id"), nullable=True),
                  "default_category_id": normalize_uuid(values.get("default_category_id"), nullable=True),
                  "default_amount": normalize_money(values["default_amount"]) if values.get("default_amount") is not None else None,
                  "instructions": normalize_text(values.get("instructions"), maximum=2000, nullable=True)}
        if "id" in values:
            result["id"] = normalize_uuid(values["id"])
        if result["effective_to_month"] is not None and result["effective_to_month"] < result["effective_from_month"]:
            invalid("Task effective dates must be ordered.")
        if result["kind"] == "check" and any(result[key] is not None for key in ("default_account_id", "default_category_id", "default_amount")):
            invalid("Check tasks cannot have money, account or category defaults.")
        return result

    def list_templates(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"enabled", "kind", "keyword"}, {"title", "execution_day", "created_at"}, "title")
        enum_fields(query, kind={"receipt", "payment", "check"})
        return serialize(self.repository.list_templates(query))

    def create_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields(payload, _TEMPLATE_FIELDS | {"id"}, {"id"})
        values = self._template_values(payload)
        if values["effective_from_month"] < self.today().replace(day=1):
            invalid("A new task must start this month or later.")
        with self.repository.transaction() as tx:
            self.repository.validate_defaults(tx, values)
            row = tx.insert("task_templates", values)
            created = row is not None
            if row is None:
                row = tx.get("task_templates", values["id"])
                if row["version"] != 1 or any(row[key] != value for key, value in values.items()):
                    conflict("Task creation ID already has different content.", "cash_submission_conflict")
            return {"template": self._template_output(row), "version": row["version"], "created": created}

    def update_template(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = normalize_uuid(template_id)
        fields(payload, _TEMPLATE_FIELDS | {"expected_version"}, {"expected_version"})
        expected = normalize_version(payload["expected_version"])
        if len(payload) == 1:
            invalid("No task fields were supplied.")
        with self.repository.transaction(readonly=True) as read:
            previous = read.get("task_templates", template_id)
        combined = self._template_output(previous)
        combined = {key: combined[key] for key in _TEMPLATE_FIELDS}
        combined.update({key: value for key, value in payload.items() if key in _TEMPLATE_FIELDS})
        values = self._template_values(combined)
        current_month = self.today().replace(day=1)
        with self.repository.transaction() as tx:
            self.repository.validate_defaults(tx, values)
            old = tx.get("task_templates", template_id, lock="update")
            check_version(old, expected)
            changed = any(old[key] != value for key, value in values.items())
            if not changed:
                return {"template": self._template_output(old), "version": old["version"], "changed": False}
            if values["kind"] != old["kind"] and (self.repository.has_history(tx, template_id) or old["enabled"] and old["effective_from_month"] <= current_month):
                invalid("A task with historical months cannot change kind.")
            restarting = not old["enabled"] and values["enabled"]
            if restarting and "effective_from_month" not in payload:
                invalid("Re-enabling requires an explicit current or future start month.")
            if "effective_from_month" in payload and values["effective_from_month"] < current_month:
                invalid("A task cannot restart in a past month.")
            if old["enabled"]:
                self.repository.materialize_old_months(tx, template_id, current_month)
                if values["enabled"]:
                    values["effective_from_month"] = max(values["effective_from_month"], next_month(current_month))
            if values["effective_to_month"] is not None and values["effective_to_month"] < values["effective_from_month"]:
                invalid("Expired task extension needs an explicit future interval.")
            row = tx.update("task_templates", template_id, values)
            return {"template": self._template_output(row), "version": row["version"], "changed": True}

    def list_occurrences(self, raw: dict[str, Any]) -> dict[str, Any]:
        query = query_input(raw, {"month", "reminder_from", "reminder_to", "overdue_as_of", "template_id", "kind", "state", "keyword"}, {"due_on", "remind_on", "title", "month", "actual_amount"}, "due_on")
        enum_fields(query, kind={"receipt", "payment", "check"}, state={"pending", "partial", "completed"})
        modes = int("month" in query) + int("overdue_as_of" in query) + int("reminder_from" in query or "reminder_to" in query)
        if modes != 1:
            invalid("Select one task month, reminder window or overdue date.")
        if "reminder_from" in query or "reminder_to" in query:
            if not {"reminder_from", "reminder_to"} <= query.keys() or not 0 <= (query["reminder_to"] - query["reminder_from"]).days <= 61:
                invalid("Reminder window must be ordered and at most 62 days.")
            if query["reminder_from"] < date(1, 2, 1) or query["reminder_to"] > date(9999, 10, 1):
                invalid("Reminder window is too close to the calendar boundary.")
        if "overdue_as_of" in query and query["overdue_as_of"] > self.today():
            invalid("Overdue date cannot be in the future.")
        return serialize(self.repository.list_occurrences(query, self.today()))

    @staticmethod
    def _identity(payload: dict[str, Any]) -> tuple[str, date, int | None]:
        fields(payload, set(payload), {"template_id", "month", "expected_version"})
        template_id, target_month = normalize_uuid(payload["template_id"]), month(payload["month"])
        expected = normalize_version(payload["expected_version"], nullable=True)
        if expected is None:
            normalize_version(payload.get("expected_template_version"))
        elif "expected_template_version" in payload:
            normalize_version(payload["expected_template_version"])
        return template_id, target_month, expected

    def _ensure_occurrence(self, tx: Any, payload: dict[str, Any]) -> dict[str, Any]:
        template_id, target_month, expected = self._identity(payload)
        template = tx.get("task_templates", template_id, lock="update")
        occurrence = self.repository.get_occurrence(tx, template_id, target_month, lock=True)
        if occurrence is not None:
            if expected is None:
                conflict("The month was materialized; refresh its version.", "cash_version_conflict")
            check_version(occurrence, expected)
            return occurrence
        if expected is not None:
            conflict("The expected month no longer exists.", "cash_version_conflict")
        check_version(template, payload["expected_template_version"])
        if not template["enabled"] or target_month < template["effective_from_month"] or template["effective_to_month"] is not None and target_month > template["effective_to_month"]:
            invalid("This month is outside the task's active interval.")
        return tx.insert("task_occurrences", occurrence_values(template, target_month))

    def _result(self, tx: Any, occurrence: dict[str, Any], flow: dict[str, Any] | None = None) -> dict[str, Any]:
        row = occurrence_row(occurrence, self.repository.actual(tx, occurrence["id"]), self.today())
        result = {"occurrence": row, "version": occurrence["version"]}
        if flow is not None:
            result["flow"] = flow
        return serialize(result)

    def adjust(self, payload: dict[str, Any]) -> dict[str, Any]:
        fields(payload, _IDENTITY_FIELDS | {"due_on", "planned_amount", "note"}, {"template_id", "month", "expected_version"})
        self._identity(payload)
        if not {"due_on", "planned_amount", "note"} & payload.keys():
            invalid("An adjustment requires a date, target or note.")
        changes = {}
        if "due_on" in payload:
            due = normalize_date(payload["due_on"])
            target = month(payload["month"])
            month_end = target.replace(day=calendar.monthrange(target.year, target.month)[1])
            if (due - target).days < -31 or (due - month_end).days > 31:
                invalid("Adjusted date must remain within 31 days of its month.")
            changes["due_on"] = due
        if "planned_amount" in payload:
            changes["planned_amount"] = normalize_money(payload["planned_amount"]) if payload["planned_amount"] is not None else None
        if "note" in payload:
            changes["note"] = normalize_text(payload["note"], maximum=2000, nullable=True)
        with self.repository.transaction() as tx:
            occurrence = self._ensure_occurrence(tx, payload)
            if "planned_amount" in changes:
                kind = occurrence["template_values_snapshot"]["kind"]
                if kind == "check" and changes["planned_amount"] is not None:
                    invalid("Check task has no planned amount.")
                if kind != "check" and changes["planned_amount"] is None and self.repository.actual(tx, occurrence["id"])["amount"] > 0:
                    invalid("A task with cash cannot clear its target.")
            changes = {key: value for key, value in changes.items() if occurrence[key] != value}
            if changes:
                occurrence = tx.update("task_occurrences", occurrence["id"], changes)
            return self._result(tx, occurrence)

    def _intent(self, payload: dict[str, Any], *, check: bool) -> dict[str, Any]:
        fields(payload, _IDENTITY_FIELDS | {"note"}, {"template_id", "month", "expected_version"})
        self._identity(payload)
        with self.repository.transaction() as tx:
            occurrence = self._ensure_occurrence(tx, payload)
            if (occurrence["template_values_snapshot"]["kind"] == "check") != check:
                invalid("This action does not match the task kind.")
            if not check and self.repository.actual(tx, occurrence["id"])["amount"] > 0:
                conflict("A partially or fully paid task cannot be marked unpaid.")
            changes = {"processing_state": "checked" if check else "unpaid"}
            if "note" in payload:
                changes["note"] = normalize_text(payload["note"], maximum=2000, nullable=True)
            if any(occurrence[key] != value for key, value in changes.items()):
                occurrence = tx.update("task_occurrences", occurrence["id"], changes)
            return self._result(tx, occurrence)

    def mark_unpaid(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._intent(payload, check=False)

    def complete_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._intent(payload, check=True)

    def reopen_check(self, occurrence_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        fields(payload, {"expected_version"}, {"expected_version"})
        occurrence_id = normalize_uuid(occurrence_id)
        with self.repository.transaction() as tx:
            occurrence = tx.get("task_occurrences", occurrence_id, lock="update")
            check_version(occurrence, payload["expected_version"])
            if occurrence["template_values_snapshot"]["kind"] != "check":
                invalid("Only a check task can be reopened.")
            if occurrence["processing_state"] != "pending":
                occurrence = tx.update("task_occurrences", occurrence_id, {"processing_state": "pending"})
            return self._result(tx, occurrence)

    def confirm(self, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        fields(payload, _IDENTITY_FIELDS | {"mode", "planned_amount", "new_flow", "existing_flow"}, {"template_id", "month", "expected_version", "mode"})
        template_id, target_month, expected = self._identity(payload)
        mode = enum(payload["mode"], {"new_flow", "existing_flow"})
        if mode not in payload or ({"new_flow", "existing_flow"} - {mode}) & payload.keys():
            invalid("Exactly one explicit cash confirmation mode is required.")
        planned = normalize_money(payload["planned_amount"]) if "planned_amount" in payload else None
        normalized, existing_expected = None, None
        if mode == "new_flow":
            normalized = self.cash.normalize_flow(payload["new_flow"], actor, source_kind="monthly_task")
            flow_id = normalized["flow"]["id"]
        else:
            reference = fields(payload["existing_flow"], {"flow_id", "expected_flow_version"}, {"flow_id", "expected_flow_version"})
            flow_id = normalize_uuid(reference["flow_id"])
            existing_expected = normalize_version(reference["expected_flow_version"])
        with self.repository.transaction(readonly=True) as read:
            existing = read.get("flows", flow_id, required=False)
            current_occurrence = self.repository.get_occurrence(read, template_id, target_month)
            if existing is not None and existing["task_occurrence_id"] is not None:
                if current_occurrence is None or str(current_occurrence["id"]) != str(existing["task_occurrence_id"]):
                    conflict("Cash already belongs to another task.")
                if normalized is not None:
                    normalized["flow"]["task_occurrence_id"] = str(current_occurrence["id"])
                    replay = self.cash.replay_flow(normalized, read)
                    if replay is not None:
                        return self._result(read, current_occurrence, replay["flow"])
                elif existing["version"] == existing_expected + 1 and current_occurrence["version"] == (expected + 1 if expected is not None else 1):
                    return self._result(read, current_occurrence, existing)
                conflict("This cash association changed after confirmation.", "cash_version_conflict")
            if mode == "existing_flow" and existing is None:
                raise CashError("cash_not_found", "Selected cash flow is unavailable.", 404)
        prepared = self.cash.prepare_flow(normalized) if normalized is not None else None
        with self.repository.transaction() as tx:
            if prepared is not None:
                self.cash.lock_flow_config(tx, [prepared["flow"]], prepared["related_items"], prepared["context"]["selection_settings_version"])
            else:
                # Existing facts may refer to a now-disabled account; linking is not new cash.
                tx.lock_rows("accounts", [existing["from_account_id"], existing["to_account_id"]], "share")
            # Another identical first submission may have committed while this request
            # waited on this template; prove the existing cash before rejecting null CAS.
            tx.get("task_templates", template_id, lock="update")
            concurrent = tx.get("flows", flow_id, required=False)
            current_occurrence = self.repository.get_occurrence(tx, template_id, target_month)
            if concurrent is not None and concurrent["task_occurrence_id"] is not None:
                if current_occurrence is None or str(current_occurrence["id"]) != str(concurrent["task_occurrence_id"]):
                    conflict("Cash already belongs to another task.")
                if normalized is not None:
                    normalized["flow"]["task_occurrence_id"] = str(current_occurrence["id"])
                    replay = self.cash.replay_flow(normalized, tx)
                    if replay is not None:
                        return self._result(tx, current_occurrence, replay["flow"])
                elif concurrent["version"] == existing_expected + 1 and current_occurrence["version"] == (expected + 1 if expected is not None else 1):
                    return self._result(tx, current_occurrence, concurrent)
                conflict("This cash association changed after confirmation.", "cash_version_conflict")
            occurrence = self._ensure_occurrence(tx, payload)
            kind = occurrence["template_values_snapshot"]["kind"]
            if kind == "check":
                invalid("Check tasks do not generate or claim cash.")
            if occurrence["planned_amount"] is None:
                if planned is None:
                    invalid("Set a positive monthly target before confirming cash.")
                occurrence = tx.update("task_occurrences", occurrence["id"], {"planned_amount": planned})
            elif planned is not None and planned != occurrence["planned_amount"]:
                invalid("An existing monthly target must be changed with adjust.")
            if prepared is not None:
                if prepared["flow"]["kind"] != kind:
                    invalid("Cash direction does not match the task.")
                prepared["flow"]["task_occurrence_id"] = str(occurrence["id"])
                result = self.cash.create_flow_in_transaction(tx, prepared)
                flow = result["flow"]
            else:
                flow = tx.get("flows", flow_id, lock="update")
                check_version(flow, existing_expected)
                if flow["kind"] != kind or flow["task_occurrence_id"] is not None:
                    conflict("Selected cash direction or task ownership is incompatible.")
                if flow["from_account_id"] != existing["from_account_id"] or flow["to_account_id"] != existing["to_account_id"]:
                    conflict("Cash accounts changed; refresh before linking.", "cash_version_conflict")
                flow = tx.update("flows", flow_id, {"task_occurrence_id": str(occurrence["id"])})
            occurrence = tx.update("task_occurrences", occurrence["id"], {"processing_state": "pending"})
            return self._result(tx, occurrence, flow)

    @staticmethod
    def _template_output(row: dict[str, Any]) -> dict[str, Any]:
        result = serialize(row)
        for key in ("effective_from_month", "effective_to_month"):
            if result[key] is not None:
                result[key] = result[key][:7]
        return result
