from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from fin_ops_platform.services.page_audit_registry import page_audit_registration
from fin_ops_platform.services.postgres_repositories.common import serialize_value


class OperationsAuditRepository(Protocol):
    def list_logical_operations(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def list_operation_actors(self) -> list[dict[str, Any]]: ...

    def list_operation_events_for_key(self, operation_key: str) -> list[dict[str, Any]]: ...

    def list_workbench_relation_history_for_request(self, request_id: str) -> list[dict[str, Any]]: ...

    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]: ...

    def audit_system(
        self,
        *,
        tenant_id: str,
        sample_limit: int,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]: ...


class PageAuditUnavailableError(ValueError):
    pass


class OperationsAuditService:
    def __init__(
        self,
        repository: OperationsAuditRepository,
        *,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self._repository = repository
        self._dashboard_payload_builder = dashboard_payload_builder

    def list_operation_history(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        page_key: str | None = None,
        object_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
        known_actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        page_size = max(1, min(int(limit), 200))
        cursor_time, cursor_key = self._parse_cursor(cursor)
        rows = self._repository.list_logical_operations(
            limit=page_size + 1,
            cursor_occurred_at=cursor_time,
            cursor_key=cursor_key,
            actor_id=self._text(actor_id),
            action=self._text(action),
            page_key=self._text(page_key),
            object_type=self._text(object_type),
            outcome=self._text(outcome),
            date_from=self._date(date_from),
            date_to=self._date(date_to),
            search=self._text(search),
        )
        visible = rows[:page_size]
        next_cursor = None
        if len(rows) > page_size and visible:
            last = visible[-1]
            next_cursor = f"{self._iso(last.get('occurred_at'))}|{last.get('operation_key')}"
        return {
            "rows": [self._operation_summary(self._with_known_actor(row, known_actor)) for row in visible],
            "next_cursor": next_cursor,
            "limit": page_size,
        }

    def list_operation_history_actors(self, *, known_actor: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "rows": [
                {
                    "actor_id": str(enriched.get("actor_id") or ""),
                    "actor_name": self._text(enriched.get("actor_name")),
                    "actor_account": self._text(enriched.get("actor_account")),
                }
                for row in self._repository.list_operation_actors()
                for enriched in [self._with_known_actor(row, known_actor)]
            ]
        }

    def get_operation_history(
        self,
        operation_key: str,
        *,
        known_actor: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized = self._operation_key(operation_key)
        events = self._repository.list_operation_events_for_key(normalized)
        if not events:
            return None
        latest = self._with_known_actor(events[-1], known_actor)
        completed = next(
            (event for event in reversed(events) if event.get("event_type") == "operation.completed"),
            None,
        )
        request_id = self._text(latest.get("request_id"))
        histories = (
            self._repository.list_workbench_relation_history_for_request(request_id)
            if request_id and latest.get("page_key") == "reconciliation-workbench"
            else []
        )
        operation = self._operation_summary(
            {
                **latest,
                "operation_key": normalized,
                "started_at": events[0].get("occurred_at"),
                "completed_at": completed.get("occurred_at") if completed else None,
                "outcome": completed.get("outcome") if completed else latest.get("outcome"),
            }
        )
        operation["items"] = self._workbench_items(histories)
        operation["reason"] = self._text(latest.get("reason"))
        return operation

    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int = 50,
    ) -> dict[str, Any]:
        registration = page_audit_registration(page_key)
        if registration.availability != "ready":
            raise PageAuditUnavailableError(
                f"Page audit proof is unavailable for {registration.page_key}: {registration.unavailable_reason}"
            )
        if registration.executor == "system":
            if self._dashboard_payload_builder is None:
                raise PageAuditUnavailableError("App Health system audit dashboard projection is unavailable.")
            return self._repository.audit_system(
                tenant_id=tenant_id,
                sample_limit=sample_limit,
                dashboard_payload_builder=self._dashboard_payload_builder,
            )
        return self._repository.audit_page(
            page_key=registration.page_key,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    @staticmethod
    def _parse_cursor(cursor: str | None) -> tuple[str | None, str | None]:
        normalized = str(cursor or "").strip()
        if not normalized:
            return None, None
        try:
            occurred_at, operation_key = normalized.rsplit("|", 1)
            datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            OperationsAuditService._operation_key(operation_key)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid operation history cursor.") from exc
        return occurred_at, operation_key

    @staticmethod
    def _date(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("Invalid operation history date filter.") from exc
        return normalized

    @staticmethod
    def _text(value: str | None) -> str | None:
        return str(value or "").strip() or None

    @staticmethod
    def _with_known_actor(row: dict[str, Any], known_actor: dict[str, Any] | None) -> dict[str, Any]:
        if not known_actor or str(row.get("actor_id") or "") != str(known_actor.get("actor_id") or ""):
            return row
        return {
            **row,
            "actor_name": row.get("actor_name") or known_actor.get("actor_name"),
            "actor_account": row.get("actor_account") or known_actor.get("actor_account"),
        }

    @staticmethod
    def _operation_key(value: str | None) -> str:
        normalized = str(value or "").strip()
        prefix, separator, identifier = normalized.partition(":")
        if separator != ":" or prefix not in {"request", "event"} or not identifier:
            raise ValueError("Invalid operation history key.")
        if prefix == "event":
            UUID(identifier)
        return normalized

    @classmethod
    def _operation_summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        action = str(row.get("action") or "")
        action_labels = {
            "POST /api/workbench/actions/confirm-link": "确认关联",
            "POST /api/workbench/actions/cancel-link": "取消关联",
            "POST /api/workbench/actions/withdraw-link": "撤回关联",
        }
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        summary = str(payload.get("summary") or "").strip()
        if summary.startswith(("GET /api/", "POST /api/", "PUT /api/", "PATCH /api/", "DELETE /api/")):
            summary = ""
        return serialize_value(
            {
                "operation_key": row.get("operation_key"),
                "event_id": row.get("latest_event_id") or row.get("id"),
                "request_id": row.get("request_id"),
                "trace_id": row.get("trace_id"),
                "object_id": row.get("object_id"),
                "actor_id": row.get("actor_id"),
                "actor_name": row.get("actor_name"),
                "actor_account": row.get("actor_account"),
                "page_key": row.get("page_key"),
                "action_label": action_labels.get(action) or summary or "业务操作",
                "object_type": row.get("object_type"),
                "started_at": row.get("started_at") or row.get("occurred_at"),
                "completed_at": row.get("completed_at"),
                "occurred_at": row.get("occurred_at"),
                "outcome": row.get("outcome") or "success",
            }
        )

    @classmethod
    def _workbench_items(cls, histories: list[dict[str, Any]]) -> list[dict[str, Any]]:
        receipts: list[dict[str, Any]] = []
        for history in histories:
            raw = history.get("raw_payload") if isinstance(history.get("raw_payload"), dict) else {}
            normalized = raw.get("normalized_payload") if isinstance(raw.get("normalized_payload"), dict) else {}
            row_ids = list(normalized.get("affected_row_ids") or history.get("row_ids") or [])
            row_types = list(normalized.get("affected_row_types") or history.get("row_types") or [])
            if len(row_ids) != len(row_types):
                relation_payloads = [
                    relation
                    for key in ("after_relations", "before_relations", "after_payload", "before_payload")
                    for relation in cls._relation_history_payloads(normalized.get(key) or history.get(key))
                ]
                typed_members = [
                    (str(row_id), str(row_type))
                    for relation in relation_payloads
                    for row_id, row_type in zip(
                        list(relation.get("row_ids") or []),
                        list(relation.get("row_types") or []),
                        strict=False,
                    )
                    if str(row_id).strip() and str(row_type).strip()
                ]
                affected_ids = {str(row_id) for row_id in row_ids}
                typed_members = [member for member in typed_members if not affected_ids or member[0] in affected_ids]
                typed_members = list(dict.fromkeys(typed_members))
                if typed_members:
                    row_ids = [row_id for row_id, _row_type in typed_members]
                    row_types = [row_type for _row_id, row_type in typed_members]
            if len(row_ids) != len(row_types):
                continue
            receipts.extend(
                {
                    "item_key": f"item-{len(receipts) + 1}",
                    "type": str(row_type),
                    "title": str(row_id),
                    "secondary": "",
                    "amount": None,
                    "date": None,
                }
                for row_id, row_type in zip(row_ids, row_types, strict=True)
            )
        return receipts

    @staticmethod
    def _relation_history_payloads(value: object) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _display_row(row: dict[str, Any]) -> dict[str, Any]:
        row_type = str(row.get("type") or row.get("source_kind") or "")
        if row_type == "oa":
            return {
                "type": "OA",
                "title": str(row.get("applicant") or row.get("applicant_name") or "OA申请"),
                "secondary": str(row.get("project_name") or row.get("reason") or row.get("apply_type") or ""),
                "amount": row.get("amount"),
                "date": row.get("application_date") or row.get("apply_date"),
            }
        if row_type == "bank":
            return {
                "type": "银行流水",
                "title": str(row.get("counterparty_name") or "未知对手方"),
                "secondary": str(row.get("category_label") or row.get("summary") or row.get("payment_account_label") or ""),
                "amount": row.get("amount"),
                "date": row.get("trade_time") or row.get("txn_date"),
            }
        return {
            "type": "进项发票",
            "title": str(row.get("seller_name") or "发票"),
            "secondary": str(row.get("invoice_no") or row.get("digital_invoice_no") or ""),
            "amount": row.get("total_with_tax") or row.get("amount"),
            "date": row.get("issue_date") or row.get("invoice_date"),
        }

    @staticmethod
    def _iso(value: Any) -> str:
        isoformat = getattr(value, "isoformat", None)
        return str(isoformat() if callable(isoformat) else value)
