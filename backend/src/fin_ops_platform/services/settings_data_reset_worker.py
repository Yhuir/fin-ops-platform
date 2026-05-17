from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
)
from fin_ops_platform.services.worker_task_protocol import (
    PermanentWorkerError,
    WorkerTaskContext,
    WorkerTaskEnvelope,
    sanitize_error_detail,
)


SETTINGS_DATA_RESET_TASK_TYPE = "settings_data_reset"
DATA_RESET_REQUEST_SCHEMA_VERSION = "finops.platform_legacy.data_reset_request.v1"
ALLOW_DATA_RESET_WORKER_ENV = "FIN_OPS_ALLOW_DATA_RESET_WORKER"
SUPPORTED_DATA_RESET_ACTIONS = {
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
}

ResetProgress = Callable[[str, str, int], None]
ResetExecutor = Callable[..., Mapping[str, object]]
Clock = Callable[[], datetime]


class SettingsDataResetWorkerHandler:
    def __init__(
        self,
        *,
        reset_executor: ResetExecutor,
        allow_destructive: bool | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._reset_executor = reset_executor
        self._allow_destructive = allow_destructive
        self._clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, envelope: WorkerTaskEnvelope, context: WorkerTaskContext) -> dict[str, object]:
        if envelope.task_type != SETTINGS_DATA_RESET_TASK_TYPE:
            raise PermanentWorkerError(
                "UNSUPPORTED_WORKER_TASK_TYPE",
                "Settings data reset worker received an unsupported task type.",
                error_detail={"task_type": envelope.task_type},
            )
        command = _parse_data_reset_command(envelope)
        if not _worker_execution_allowed(self._allow_destructive):
            raise PermanentWorkerError(
                "DATA_RESET_WORKER_NOT_ALLOWED",
                "Settings data reset worker requires explicit maintenance execution authorization.",
                error_detail={
                    "required_env": ALLOW_DATA_RESET_WORKER_ENV,
                    "task_id": envelope.task_id,
                    "action": command["action"],
                },
            )

        context.heartbeat()

        def progress(phase: str, _message: str, percent: int) -> None:
            context.heartbeat()

        result = self._reset_executor(command["action"], progress=progress)
        safe_result = sanitize_error_detail(dict(result or {}))
        status = str(safe_result.get("status") or "completed")
        proof = _worker_proof(envelope, context, command, self._clock())
        return {
            **safe_result,
            "status": status,
            "worker_proof": proof,
        }


def _parse_data_reset_command(envelope: WorkerTaskEnvelope) -> dict[str, object]:
    schema_version = _optional_text(envelope.payload.get("schema_version"))
    if schema_version and schema_version != DATA_RESET_REQUEST_SCHEMA_VERSION:
        raise PermanentWorkerError(
            "DATA_RESET_SCHEMA_UNSUPPORTED",
            "Settings data reset worker payload schema is unsupported.",
            error_detail={"schema_version": schema_version},
        )
    action = _command_text(envelope, "action")
    if action not in SUPPORTED_DATA_RESET_ACTIONS:
        raise PermanentWorkerError(
            "DATA_RESET_ACTION_UNSUPPORTED",
            "Settings data reset worker action is unsupported.",
            error_detail={"action": action, "supported_actions": sorted(SUPPORTED_DATA_RESET_ACTIONS)},
        )
    approval_id = _command_text(envelope, "approval_id")
    if not approval_id:
        raise PermanentWorkerError(
            "DATA_RESET_APPROVAL_REQUIRED",
            "Settings data reset worker requires approval_id before destructive execution.",
            error_detail={"task_id": envelope.task_id, "action": action},
        )
    backup_evidence_id = _command_text(envelope, "backup_evidence_id")
    if not backup_evidence_id:
        raise PermanentWorkerError(
            "DATA_RESET_BACKUP_EVIDENCE_REQUIRED",
            "Settings data reset worker requires backup_evidence_id before destructive execution.",
            error_detail={"task_id": envelope.task_id, "action": action, "approval_id": approval_id},
        )
    scope = envelope.payload.get("scope")
    if scope is None:
        scope = envelope.source.get("scope")
    if scope is None:
        scope = envelope.scope
    if not isinstance(scope, dict):
        raise PermanentWorkerError(
            "DATA_RESET_SCOPE_INVALID",
            "Settings data reset worker scope must be an object.",
            error_detail={"task_id": envelope.task_id, "action": action},
        )
    return {
        "action": action,
        "approval_id": approval_id,
        "backup_evidence_id": backup_evidence_id,
        "scope": dict(scope),
    }


def _command_text(envelope: WorkerTaskEnvelope, field_name: str) -> str:
    value = envelope.payload.get(field_name)
    text = _optional_text(value)
    if text:
        return text
    return _optional_text(envelope.source.get(field_name)) or ""


def _optional_text(value: object) -> str:
    return str(value or "").strip()


def _worker_execution_allowed(allow_destructive: bool | None) -> bool:
    if allow_destructive is not None:
        return bool(allow_destructive)
    return os.environ.get(ALLOW_DATA_RESET_WORKER_ENV) == "1"


def _worker_proof(
    envelope: WorkerTaskEnvelope,
    context: WorkerTaskContext,
    command: Mapping[str, object],
    executed_at: datetime,
) -> dict[str, object]:
    source = envelope.source
    return {
        "task_id": envelope.task_id,
        "outbox_event_id": _optional_text(source.get("outbox_event_id")) or _optional_text(source.get("event_id")) or None,
        "data_reset_request_id": _optional_text(source.get("data_reset_request_id"))
        or _optional_text(source.get("aggregate_id"))
        or envelope.task_id,
        "attempt_id": context.attempt_id,
        "attempt_no": context.attempt_no,
        "trace_id": envelope.trace_id,
        "action": command["action"],
        "approval_id": command["approval_id"],
        "backup_evidence_id": command["backup_evidence_id"],
        "scope": command["scope"],
        "executed_at": executed_at.isoformat(),
    }
