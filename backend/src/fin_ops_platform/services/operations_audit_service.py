from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Protocol
from uuid import UUID

from fin_ops_platform.services.operation_history_evidence import normalize_operation_evidence, recorded_api_call
from fin_ops_platform.services.operation_history_semantics import (
    OPERATION_CATEGORIES,
    operation_category,
    semantics_from_audit_row,
)
from fin_ops_platform.services.page_audit_registry import page_audit_registration
from fin_ops_platform.services.postgres_repositories.common import serialize_value


class OperationsAuditRepository(Protocol):
    def list_logical_operations(self, **kwargs: Any) -> list[dict[str, Any]]: ...

    def get_operation_history_snapshot(self, operation_key: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]: ...

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
        category: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
        known_actor: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        page_size = int(limit)
        if not 1 <= page_size <= 200:
            raise ValueError("Operation history limit must be between 1 and 200.")
        if category and category not in OPERATION_CATEGORIES:
            raise ValueError("Invalid operation history category.")
        if outcome and outcome not in {"success", "failed", "pending", "incomplete", "unknown"}:
            raise ValueError("Invalid operation history outcome.")
        if date_from and date_to and self._date(date_from) > self._date(date_to):
            raise ValueError("Operation history date range is reversed.")
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
            category=self._text(category),
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
        logical, events = self._repository.get_operation_history_snapshot(normalized)
        if logical is None:
            return None
        operation = self._operation_summary(self._with_known_actor(logical, known_actor))
        payload = logical.get("evidence_payload") if isinstance(logical.get("evidence_payload"), dict) else logical.get("payload")
        metadata = payload.get("metadata") if isinstance(payload, dict) and isinstance(payload.get("metadata"), dict) else {}
        stored_evidence = metadata.get("evidence")
        request_id = self._text(logical.get("request_id"))
        histories = (self._repository.list_workbench_relation_history_for_request(request_id)
                     if not isinstance(stored_evidence, dict) and request_id and logical.get("page_key") == "reconciliation-workbench"
                     else [])
        detail = (normalize_operation_evidence(stored_evidence) if isinstance(stored_evidence, dict)
                  else self._workbench_relation_detail(histories, action_code=operation["action_code"]))
        calls_by_request: dict[str, dict[str, Any]] = {}
        api_priorities: dict[str, tuple[bool, bool]] = {}
        activities = []
        for event in events:
            call = recorded_api_call(event)
            if call:
                key = f"{call.get('request_id') or event.get('id') or 'request'}:{call.get('path') or ''}"
                previous = calls_by_request.get(key, {})
                event_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                event_metadata = event_payload.get("metadata") if isinstance(event_payload.get("metadata"), dict) else {}
                priority = (event.get("event_type") == "operation.completed", isinstance(event_metadata.get("api_call"), dict))
                merged = dict(previous or call)
                for field, value in call.items():
                    if value is not None and (field != "parameters" or value) and (priority >= api_priorities.get(key, (False, False)) or previous.get(field) is None):
                        merged[field] = value
                calls_by_request[key] = merged
                api_priorities[key] = max(priority, api_priorities.get(key, (False, False)))
            if event.get("event_type") in {"operation.requested", "operation.completed"}:
                continue
            semantics = semantics_from_audit_row(event)
            event_payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_metadata = event_payload.get("metadata") if isinstance(event_payload.get("metadata"), dict) else {}
            fields = [{"label": label, "value": str(event_metadata[key])}
                      for key, label in (("stage", "阶段"), ("status", "任务状态"), ("outcome", "实际结果"), ("row_count", "记录数"), ("filename", "文件"))
                      if event_metadata.get(key) is not None]
            activity_outcome = {"started": "pending", "partial": "incomplete"}.get(event.get("outcome"), event.get("outcome"))
            activities.append({"title": semantics.action_label, "occurred_at": self._iso(event.get("occurred_at")),
                               "outcome": activity_outcome if activity_outcome in {"success", "failed", "pending", "incomplete"} else "unknown", "fields": fields})
        if operation["outcome"] == "pending" and any(call.get("status_code") == 202 for call in calls_by_request.values()):
            accepted = next((event for event in reversed(events) if (recorded_api_call(event) or {}).get("status_code") == 202), None)
            activities.append({"title": "请求已接收", "occurred_at": self._iso(accepted.get("occurred_at")) if accepted else None,
                               "outcome": "pending", "fields": [{"label": "后续处理", "value": "请求已接收；后续结果未记录"}]})
        detail["api_calls"] = list(calls_by_request.values())
        detail["activities"] = activities
        detail["source"] = ("HTTP 请求" if detail["api_calls"] else "系统任务" if str(logical.get("action") or "").startswith(("import_job.", "system.", "job."))
                            else "数据库操作" if str(logical.get("actor_id") or "").endswith(("-repair", "-persistence")) else "审计事件")
        detail["legacy_evidence_missing"] = not any(detail.get(key) for key in ("target", "artifacts", "records", "changes", "failure"))
        operation["detail"] = serialize_value(detail)
        operation["reason"] = self._text(logical.get("reason"))
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
            if datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).tzinfo is None:
                raise ValueError("Cursor timezone is required.")
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
            if len(normalized) != 10 or date.fromisoformat(normalized).isoformat() != normalized:
                raise ValueError("Date must use YYYY-MM-DD.")
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
        category = row.get("category") or operation_category(semantics.action_code)
        evidence_payload = row.get("evidence_payload") if isinstance(row.get("evidence_payload"), dict) else row.get("payload")
        metadata = evidence_payload.get("metadata", {}) if isinstance(evidence_payload, dict) else {}
        evidence = metadata.get("evidence", {}) if isinstance(metadata, dict) else {}
        target = evidence.get("target", {}) if isinstance(evidence, dict) else {}
        return serialize_value(
            {
                "operation_key": row.get("operation_key"),
                "actor_id": row.get("actor_id"),
                "actor_name": row.get("actor_name"),
                "actor_account": row.get("actor_account"),
                "page_key": row.get("page_key"),
                "action_code": row.get("action_code") or semantics.action_code,
                "action_label": row.get("action_label") or semantics.action_label,
                "action_description": row.get("action_description") if "action_description" in row else semantics.description,
                "object_type": semantics.object_type,
                "object_label": row.get("object_label") or semantics.object_label,
                "object_title": row.get("object_title") or (target.get("title") if isinstance(target, dict) else None),
                "category": category,
                "category_label": OPERATION_CATEGORIES[category],
                "started_at": row.get("started_at") or row.get("occurred_at"),
                "completed_at": row.get("completed_at"),
                "occurred_at": row.get("occurred_at"),
                "outcome": row.get("outcome") or "unknown",
            }
        )

    @classmethod
    def _workbench_relation_detail(
        cls,
        histories: list[dict[str, Any]],
        *,
        action_code: str,
    ) -> dict[str, Any]:
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
        records = [
            {
                "record_key": f"type-{row_type}",
                "kind": row_type,
                "title": f"{count} 条{labels.get(row_type, '业务记录')}",
                "fields": [{"label": "涉及数量", "value": str(count)}],
            }
            for row_type, count in sorted(counts.items(), key=lambda item: (order.get(item[0], len(order)), item[0]))
        ]
        return normalize_operation_evidence(
            {
                "records": records,
                "changes": (
                    [{"label": "关联状态", "before": before_status, "after": after_status}]
                    if before_status or after_status
                    else []
                ),
            }
        )

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
