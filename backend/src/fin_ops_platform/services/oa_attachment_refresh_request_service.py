from __future__ import annotations

import re
from hashlib import sha256
from typing import Any
from uuid import UUID

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.oa_adapter import is_in_progress_expense_claim
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    is_completed_workflow_status,
)

REFRESH_ATTACHMENTS_OPERATION = "refresh_attachments"
_MONTH_SCOPE_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")


class OAAttachmentRefreshRequestError(RuntimeError):
    code = "oa_attachment_refresh_request_failed"


class OAAttachmentRefreshRowNotFoundError(OAAttachmentRefreshRequestError):
    code = "oa_row_not_found"


class OAAttachmentRefreshRowNotRefreshableError(OAAttachmentRefreshRequestError):
    code = "oa_row_not_refreshable"


class OAAttachmentRefreshEventNotFoundError(OAAttachmentRefreshRequestError):
    code = "oa_attachment_refresh_event_not_found"


class OAAttachmentRefreshRequestService:
    """Queue exact OA attachment refreshes and expose only their public status contract."""

    def __init__(self, *, queue_repository: Any, workflow_reader: Any) -> None:
        if not callable(getattr(queue_repository, "enqueue", None)):
            raise RuntimeError("OA attachment refresh requires the runtime queue repository.")
        if not callable(getattr(queue_repository, "get_event_status", None)):
            raise RuntimeError("OA attachment refresh requires runtime event status reads.")
        if not callable(getattr(queue_repository, "get_active_event_by_dedupe_key", None)):
            raise RuntimeError("OA attachment refresh requires active runtime event reads.")
        if not callable(getattr(workflow_reader, "list_application_records_by_row_ids", None)):
            raise RuntimeError("OA attachment refresh requires the PostgreSQL workflow reader.")
        self._queue_repository = queue_repository
        self._workflow_reader = workflow_reader

    def request(self, row_ids: list[str], *, actor_id: str) -> dict[str, object]:
        normalized_row_ids = _normalize_row_ids(row_ids)
        identity = sha256("\n".join(sorted(normalized_row_ids)).encode("utf-8")).hexdigest()
        dedupe_key = f"oa.sync:refresh_attachments:{identity}"
        active_event = self._queue_repository.get_active_event_by_dedupe_key(dedupe_key)
        if active_event is not None:
            active_payload = active_event.payload
            if (
                active_event.event_type != "oa.sync"
                or not isinstance(active_payload, dict)
                or active_payload.get("operation") != REFRESH_ATTACHMENTS_OPERATION
            ):
                raise OAAttachmentRefreshRequestError(
                    "OA 附件刷新幂等键已被其他任务占用。"
                )
            active_row_ids = _normalize_row_ids(active_payload.get("row_ids"))
            active_scope_keys = _normalize_scope_keys(
                active_payload.get("affected_scope_keys")
            )
            if set(active_row_ids) != set(normalized_row_ids):
                raise OAAttachmentRefreshRequestError(
                    "OA 附件刷新幂等任务合同不一致。"
                )
            return {
                "event_id": active_event.event_id,
                "status": "pending",
                "row_ids": active_row_ids,
                "affected_scope_keys": active_scope_keys,
            }
        records = list(self._workflow_reader.list_application_records_by_row_ids(normalized_row_ids))
        records_by_id = {record.id: record for record in records}
        if len(records_by_id) != len(records):
            raise OAAttachmentRefreshRequestError("OA row_id 查询返回重复记录，不能刷新附件。")
        unexpected_row_ids = sorted(set(records_by_id) - set(normalized_row_ids))
        if unexpected_row_ids:
            raise OAAttachmentRefreshRequestError(
                f"OA row_id 查询返回未请求记录：{', '.join(unexpected_row_ids)}"
            )
        missing_row_ids = [row_id for row_id in normalized_row_ids if row_id not in records_by_id]
        if missing_row_ids:
            raise OAAttachmentRefreshRowNotFoundError(
                f"OA row_id 不存在：{', '.join(missing_row_ids)}"
            )
        unsupported_row_ids = [
            row_id
            for row_id in normalized_row_ids
            if not is_completed_workflow_status(records_by_id[row_id].workflow_status)
            and not is_in_progress_expense_claim(records_by_id[row_id])
        ]
        if unsupported_row_ids:
            raise OAAttachmentRefreshRowNotRefreshableError(
                "仅支持已完成流程或进行中的日常报销刷新附件："
                + ", ".join(unsupported_row_ids)
            )
        affected_scope_keys = sorted(
            {
                month
                for row_id in normalized_row_ids
                if (month := clean_string(records_by_id[row_id].month))
            }
        )
        if not affected_scope_keys:
            raise OAAttachmentRefreshRequestError("OA 记录缺少有效月份，不能刷新附件。")
        invalid_scope_keys = [
            scope_key
            for scope_key in affected_scope_keys
            if not _MONTH_SCOPE_PATTERN.fullmatch(scope_key)
        ]
        if invalid_scope_keys:
            raise OAAttachmentRefreshRequestError(
                f"OA 记录月份无效：{', '.join(invalid_scope_keys)}"
            )
        scope_key = affected_scope_keys[0] if len(affected_scope_keys) == 1 else "all"
        event = self._queue_repository.enqueue(
            event_type="oa.sync",
            aggregate_type="oa_attachment_refresh",
            aggregate_id=identity,
            scope_type="oa",
            scope_key=scope_key,
            dedupe_key=dedupe_key,
            payload={
                "operation": REFRESH_ATTACHMENTS_OPERATION,
                "row_ids": normalized_row_ids,
                "affected_scope_keys": affected_scope_keys,
                "triggered_by": clean_string(actor_id) or "workbench_settings",
            },
            priority="high",
        )
        if event.status != "pending":
            raise RuntimeError("OA attachment refresh enqueue returned an invalid status.")
        return {
            "event_id": event.event_id,
            "status": "queued",
            "row_ids": normalized_row_ids,
            "affected_scope_keys": affected_scope_keys,
        }

    def status(self, event_id: str) -> dict[str, object]:
        normalized_event_id = clean_string(event_id)
        try:
            UUID(normalized_event_id)
        except (TypeError, ValueError) as exc:
            raise OAAttachmentRefreshEventNotFoundError("OA 附件刷新任务不存在。") from exc
        event = self._queue_repository.get_event_status(normalized_event_id)
        if not isinstance(event, dict) or event.get("event_type") != "oa.sync":
            raise OAAttachmentRefreshEventNotFoundError("OA 附件刷新任务不存在。")
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("operation") != REFRESH_ATTACHMENTS_OPERATION:
            raise OAAttachmentRefreshEventNotFoundError("OA 附件刷新任务不存在。")
        row_ids = _normalize_row_ids(payload.get("row_ids"))
        affected_scope_keys = _normalize_scope_keys(payload.get("affected_scope_keys"))
        status = clean_string(event.get("status"))
        if status not in {"pending", "processing", "done", "failed", "dead_lettered"}:
            raise OAAttachmentRefreshRequestError("OA 附件刷新任务状态无效。")
        response: dict[str, object] = {
            "event_id": normalized_event_id,
            "status": status,
            "row_ids": row_ids,
            "affected_scope_keys": affected_scope_keys,
        }
        if status == "done":
            runtime_result = event.get("runtime_result")
            if not isinstance(runtime_result, dict) or not isinstance(runtime_result.get("rows"), list):
                response["status"] = "failed"
                response["error"] = "OA 附件刷新结果合同不完整，请联系管理员。"
                return response
            try:
                response["result"] = _public_runtime_result(
                    runtime_result,
                    affected_scope_keys=affected_scope_keys,
                    expected_row_ids=row_ids,
                )
            except (TypeError, ValueError):
                response["status"] = "failed"
                response["error"] = "OA 附件刷新结果合同不完整，请联系管理员。"
        elif status in {"failed", "dead_lettered"}:
            response["error"] = "OA 附件刷新失败，请重试或联系管理员。"
        return response


def _normalize_row_ids(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("row_ids must be an array.")
    if any(not isinstance(value, str) for value in values):
        raise ValueError("row_ids must contain strings only.")
    normalized = list(dict.fromkeys(row_id for value in values if (row_id := value.strip())))
    if not normalized:
        raise ValueError("row_ids must contain at least one non-empty row_id.")
    return normalized


def _normalize_scope_keys(values: object) -> list[str]:
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("affected_scope_keys must be an array of strings.")
    scopes = list(dict.fromkeys(scope for value in values if (scope := value.strip())))
    if not scopes or any(not _MONTH_SCOPE_PATTERN.fullmatch(scope) for scope in scopes):
        raise ValueError("affected_scope_keys must contain valid month scopes.")
    return scopes


def _public_runtime_result(
    result: dict[str, object],
    *,
    affected_scope_keys: list[str],
    expected_row_ids: list[str],
) -> dict[str, object]:
    raw_rows = result.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("runtime result rows must be an array.")
    rows: list[dict[str, object]] = []
    for value in raw_rows:
        if not isinstance(value, dict):
            raise ValueError("runtime result row must be an object.")
        rows.append(
            {
                "row_id": _required_string(value.get("row_id"), "row_id"),
                "attachment_file_count": _required_count(
                    value.get("attachment_file_count"),
                    "attachment_file_count",
                ),
                "importable_invoice_count": _required_count(
                    value.get("importable_invoice_count"),
                    "importable_invoice_count",
                ),
                "unrecognized_attachment_count": _required_count(
                    value.get("unrecognized_attachment_count"),
                    "unrecognized_attachment_count",
                ),
            }
        )
    if set(row["row_id"] for row in rows) != set(expected_row_ids) or len(rows) != len(expected_row_ids):
        raise ValueError("runtime result rows do not match requested row_ids.")
    raw_errors = result.get("errors")
    if not isinstance(raw_errors, list):
        raise ValueError("runtime result errors must be an array.")
    errors: list[dict[str, str]] = []
    for value in raw_errors:
        if not isinstance(value, dict):
            raise ValueError("runtime result error must be an object.")
        errors.append(
            {
                "row_id": _required_string(value.get("row_id"), "error.row_id"),
                "code": _required_string(value.get("code"), "error.code"),
                "message": _required_string(value.get("message"), "error.message"),
            }
        )
    summary = result.get("promotion_summary")
    if not isinstance(summary, dict):
        raise ValueError("runtime result promotion_summary must be an object.")
    public_summary = {
        key: _required_count(value, f"promotion_summary.{key}")
        for key, value in summary.items()
        if key
        in {
            "cache_candidate_count",
            "affected_invoice_count",
            "linked_existing_invoice_count",
            "created_invoice_count",
            "updated_invoice_count",
        }
    }
    result_scope_keys = _normalize_scope_keys(result.get("affected_scope_keys"))
    if set(result_scope_keys) != set(affected_scope_keys):
        raise ValueError("runtime result affected scopes do not match the request.")
    return {
        "rows": rows,
        "errors": errors,
        "promotion_summary": public_summary,
        "affected_scope_keys": result_scope_keys,
    }


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _required_count(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value
