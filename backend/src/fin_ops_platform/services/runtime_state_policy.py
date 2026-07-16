from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


MIRROR_WRITE_REQUIRED = "mirror_write_required"
REBUILDABLE = "rebuildable"
RETENTION_ONLY = "retention_only"
CLEANUP_CANDIDATE = "cleanup_candidate"
BLOCKED_UNKNOWN = "blocked_unknown"

BACKGROUND_JOB_ACTIVE_STATUSES = {"queued", "running"}
BACKGROUND_JOB_ATTENTION_STATUSES = {"failed", "partial_success"}
BACKGROUND_JOB_TERMINAL_STATUSES = {
    "succeeded",
    "partial_success",
    "failed",
    "cancelled",
    "acknowledged",
    "superseded",
}
BACKGROUND_JOB_KNOWN_STATUSES = BACKGROUND_JOB_ACTIVE_STATUSES | BACKGROUND_JOB_TERMINAL_STATUSES
BACKGROUND_JOB_REBUILDABLE_TYPES = {
    "workbench_matching",
    "workbench_rebuild",
    "workbench_read_model_rebuild",
    "oa_sync_workbench_rebuild",
    "tax_offset_cache_warmup",
    "historical_etc_reconcile",
}
BACKGROUND_JOB_KNOWN_TYPES = BACKGROUND_JOB_REBUILDABLE_TYPES | {
    "etc_invoice_import",
    "file_import",
    "settings_data_reset",
}
BACKGROUND_JOB_RETRYABLE_TYPES = {
    "file_import",
    "workbench_matching",
    "tax_offset_cache_warmup",
}

APP_HEALTH_ALERT_KNOWN_STATUSES = {"active", "recovered"}
APP_HEALTH_ALERT_KNOWN_SEVERITIES = {"critical", "warning", "info"}
APP_HEALTH_ALERT_REBUILDABLE_KINDS = {
    "oa_sync_dirty_scope",
    "workbench_rebuild_long_running",
    "background_job_long_running",
    "dependency_unavailable",
    "session_blocked",
}


@dataclass(frozen=True)
class RuntimeStatePolicyDecision:
    domain: str
    classification: str
    mirror_write_required: bool
    cutover_blocking: bool
    reason: str
    status: str | None = None
    runtime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_background_job(
    payload: Mapping[str, Any] | object,
    *,
    present_in_primary: bool = True,
    present_in_shadow: bool = True,
) -> RuntimeStatePolicyDecision:
    if not isinstance(payload, Mapping):
        return _blocked("background_jobs", "background job payload is not an object")

    status = _normalized_string(payload.get("status"))
    job_type = _normalized_string(payload.get("type") or payload.get("job_type"))
    if status not in BACKGROUND_JOB_KNOWN_STATUSES:
        return _blocked("background_jobs", f"unknown background job status {status or '<empty>'!r}", status=status)
    if job_type not in BACKGROUND_JOB_KNOWN_TYPES:
        return _blocked(
            "background_jobs",
            f"unknown background job type {job_type or '<empty>'!r}",
            status=status,
            runtime_type=job_type or None,
        )

    if status in BACKGROUND_JOB_ACTIVE_STATUSES:
        return RuntimeStatePolicyDecision(
            domain="background_jobs",
            classification=MIRROR_WRITE_REQUIRED,
            mirror_write_required=True,
            cutover_blocking=False,
            reason="active background job affects visible progress and restart recovery",
            status=status,
            runtime_type=job_type,
        )

    if status in BACKGROUND_JOB_ATTENTION_STATUSES and not _has_ack_or_supersede(payload):
        return RuntimeStatePolicyDecision(
            domain="background_jobs",
            classification=MIRROR_WRITE_REQUIRED,
            mirror_write_required=True,
            cutover_blocking=False,
            reason="unacknowledged attention job affects retry or user follow-up",
            status=status,
            runtime_type=job_type,
        )

    if present_in_shadow and not present_in_primary:
        if not _has_any_timestamp(payload):
            return _blocked(
                "background_jobs",
                "shadow-only terminal job lacks timestamp for cleanup or retention policy",
                status=status,
                runtime_type=job_type,
            )
        return RuntimeStatePolicyDecision(
            domain="background_jobs",
            classification=CLEANUP_CANDIDATE,
            mirror_write_required=False,
            cutover_blocking=False,
            reason="shadow-only terminal job is stale runtime history and can be retained or cleaned under audit",
            status=status,
            runtime_type=job_type,
        )

    if job_type in BACKGROUND_JOB_REBUILDABLE_TYPES and _has_rebuild_context(payload):
        return RuntimeStatePolicyDecision(
            domain="background_jobs",
            classification=REBUILDABLE,
            mirror_write_required=False,
            cutover_blocking=False,
            reason="terminal derived job can be regenerated from current business state and scoped metadata",
            status=status,
            runtime_type=job_type,
        )

    return RuntimeStatePolicyDecision(
        domain="background_jobs",
        classification=RETENTION_ONLY,
        mirror_write_required=False,
        cutover_blocking=False,
        reason="terminal background job is audit or diagnostic history",
        status=status,
        runtime_type=job_type,
    )


def classify_app_health_alert(
    payload: Mapping[str, Any] | object,
    *,
    present_in_primary: bool = True,
    present_in_shadow: bool = True,
) -> RuntimeStatePolicyDecision:
    if not isinstance(payload, Mapping):
        return _blocked("app_health_alerts", "app health alert payload is not an object")

    status = _normalized_string(payload.get("status"))
    severity = _normalized_string(payload.get("severity"))
    kind = _normalized_string(payload.get("kind"))
    if status not in APP_HEALTH_ALERT_KNOWN_STATUSES:
        return _blocked("app_health_alerts", f"unknown alert status {status or '<empty>'!r}", status=status)
    if severity not in APP_HEALTH_ALERT_KNOWN_SEVERITIES:
        return _blocked(
            "app_health_alerts",
            f"unknown alert severity {severity or '<empty>'!r}",
            status=status,
            runtime_type=kind or None,
        )
    if kind not in APP_HEALTH_ALERT_REBUILDABLE_KINDS:
        return _blocked(
            "app_health_alerts",
            f"unknown alert kind {kind or '<empty>'!r}",
            status=status,
            runtime_type=kind or None,
        )

    if status == "active":
        return RuntimeStatePolicyDecision(
            domain="app_health_alerts",
            classification=MIRROR_WRITE_REQUIRED,
            mirror_write_required=True,
            cutover_blocking=False,
            reason="active health alert is current runtime state and must be mirrored during controlled rehearsal",
            status=status,
            runtime_type=kind,
        )

    if present_in_shadow and not present_in_primary:
        return RuntimeStatePolicyDecision(
            domain="app_health_alerts",
            classification=CLEANUP_CANDIDATE,
            mirror_write_required=False,
            cutover_blocking=False,
            reason="shadow-only recovered health alert can be cleaned after retention review",
            status=status,
            runtime_type=kind,
        )

    return RuntimeStatePolicyDecision(
        domain="app_health_alerts",
        classification=RETENTION_ONLY,
        mirror_write_required=False,
        cutover_blocking=False,
        reason="recovered health alert is short-term diagnostic history",
        status=status,
        runtime_type=kind,
    )


def _blocked(
    domain: str,
    reason: str,
    *,
    status: str | None = None,
    runtime_type: str | None = None,
) -> RuntimeStatePolicyDecision:
    return RuntimeStatePolicyDecision(
        domain=domain,
        classification=BLOCKED_UNKNOWN,
        mirror_write_required=False,
        cutover_blocking=True,
        reason=reason,
        status=status,
        runtime_type=runtime_type,
    )


def _normalized_string(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_ack_or_supersede(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("acknowledged_at") or payload.get("superseded_at") or payload.get("superseded_by_job_id"))


def _has_any_timestamp(payload: Mapping[str, Any]) -> bool:
    return bool(payload.get("finished_at") or payload.get("updated_at") or payload.get("created_at"))


def _has_rebuild_context(payload: Mapping[str, Any]) -> bool:
    source = payload.get("source")
    scopes = payload.get("affected_scopes")
    months = payload.get("affected_months")
    return bool(
        (isinstance(source, Mapping) and source)
        or (isinstance(scopes, list) and scopes)
        or (isinstance(months, list) and months)
    )
