from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from fin_ops_platform.services.operation_history_semantics import semantics_from_audit_row
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
        operation["items"] = self._workbench_items(histories, action_code=operation["action_code"])
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
        semantics = semantics_from_audit_row(row)
        return serialize_value(
            {
                "operation_key": row.get("operation_key"),
                "actor_id": row.get("actor_id"),
                "actor_name": row.get("actor_name"),
                "actor_account": row.get("actor_account"),
                "page_key": row.get("page_key"),
                "action_code": semantics.action_code,
                "action_label": semantics.action_label,
                "action_description": semantics.description,
                "object_type": semantics.object_type,
                "object_label": semantics.object_label,
                "started_at": row.get("started_at") or row.get("occurred_at"),
                "completed_at": row.get("completed_at"),
                "occurred_at": row.get("occurred_at"),
                "outcome": row.get("outcome") or "success",
            }
        )

    @classmethod
    def _workbench_items(
        cls,
        histories: list[dict[str, Any]],
        *,
        action_code: str,
    ) -> list[dict[str, Any]]:
        affected_members: set[tuple[str, str]] = set()
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
            affected_members.update(
                (str(row_type).strip(), str(row_id).strip())
                for row_id, row_type in zip(row_ids, row_types, strict=True)
                if str(row_id).strip() and str(row_type).strip()
            )
        labels = {"oa": "OA", "bank": "银行流水", "invoice": "发票"}
        counts: dict[str, int] = {}
        for row_type, _row_id in affected_members:
            counts[row_type] = counts.get(row_type, 0) + 1
        paired_actions = {
            "workbench.relation.confirm",
            "workbench.advance.confirm",
            "workbench.cash.confirm_pass_through",
            "workbench.cash.confirm_ticket",
        }
        unpaired_actions = {
            "workbench.relation.cancel",
            "workbench.relation.withdraw",
            "workbench.cash.cancel",
        }
        before_status = (
            "未配对" if action_code in paired_actions else "已配对" if action_code in unpaired_actions else ""
        )
        after_status = (
            "已配对" if action_code in paired_actions else "未配对" if action_code in unpaired_actions else ""
        )
        order = {row_type: index for index, row_type in enumerate(labels)}
        return [
            {
                "item_key": f"type-{row_type}",
                "type": labels.get(row_type, "业务记录"),
                "title": f"{count} 条{labels.get(row_type, '业务记录')}",
                "secondary": f"本次操作涉及 {count} 条{labels.get(row_type, '业务记录')}",
                "amount": None,
                "date": None,
                "before_status": before_status,
                "after_status": after_status,
            }
            for row_type, count in sorted(
                counts.items(),
                key=lambda item: (order.get(item[0], len(order)), item[0]),
            )
        ]

    @staticmethod
    def _relation_history_payloads(value: object) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _iso(value: Any) -> str:
        isoformat = getattr(value, "isoformat", None)
        return str(isoformat() if callable(isoformat) else value)
