from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from fin_ops_platform.services.page_audit_registry import page_audit_registration
from fin_ops_platform.services.postgres_repositories.common import serialize_value


class OperationsAuditRepository(Protocol):
    def list_operation_events(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def get_operation_event(self, event_id: str) -> dict[str, Any] | None: ...

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
    ) -> dict[str, Any]:
        page_size = max(1, min(int(limit), 200))
        cursor_time, cursor_id = self._parse_cursor(cursor)
        rows = self._repository.list_operation_events(
            limit=page_size + 1,
            cursor_occurred_at=cursor_time,
            cursor_id=cursor_id,
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
            next_cursor = f"{self._iso(last.get('occurred_at'))}|{last.get('id')}"
        return {
            "rows": [serialize_value(row) for row in visible],
            "next_cursor": next_cursor,
            "limit": page_size,
        }

    def get_operation_history_event(self, event_id: str) -> dict[str, Any] | None:
        normalized = str(UUID(str(event_id or "").strip()))
        row = self._repository.get_operation_event(normalized)
        return serialize_value(row) if row is not None else None

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
            occurred_at, event_id = normalized.rsplit("|", 1)
            datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
            UUID(event_id)
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid operation history cursor.") from exc
        return occurred_at, event_id

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
    def _iso(value: Any) -> str:
        isoformat = getattr(value, "isoformat", None)
        return str(isoformat() if callable(isoformat) else value)
