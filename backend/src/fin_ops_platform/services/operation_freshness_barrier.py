from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY


BLOCKED_READ_MODEL_STATUSES = {"failed", "unavailable"}
BUSY_READ_MODEL_STATUSES = {
    "missing",
    "refreshing",
    "stale",
    "schema_mismatch",
    "source_mismatch",
}
BLOCKED_OUTBOX_STATUSES = {"failed", "dead_lettered", "publish_failed"}
BUSY_OUTBOX_STATUSES = {"pending", "processing", "publishing"}


@dataclass(frozen=True, slots=True)
class OperationFreshnessTarget:
    read_model_key: str
    scope_key: str = "all"
    scope_type: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "OperationFreshnessTarget":
        read_model_key = _clean_text(payload.get("read_model_key") or payload.get("key"))
        scope_key = _clean_text(payload.get("scope_key")) or "all"
        scope_type = _clean_text(payload.get("scope_type")) or None
        if not read_model_key:
            raise ValueError("read_model_key is required")
        definition = _definition_for_target(read_model_key)
        return cls(
            read_model_key=read_model_key,
            scope_key=scope_key,
            scope_type=scope_type or (definition.scope_type if definition is not None else None),
        )


class OperationFreshnessBarrierService:
    """Resolves post-mutation freshness from existing runtime/readiness facts."""

    def __init__(self, *, runtime_snapshot_provider: Callable[[], dict[str, Any]]) -> None:
        self._runtime_snapshot_provider = runtime_snapshot_provider

    def status_payload(self, targets: list[OperationFreshnessTarget]) -> dict[str, Any]:
        snapshot = self._runtime_snapshot()
        read_model_statuses = _dict(snapshot.get("read_model_statuses"))
        outbox_statuses = _dict(snapshot.get("outbox_statuses"))
        worker_statuses = _dict(snapshot.get("worker_statuses"))
        target_payloads = [
            self._target_status_payload(
                target,
                read_model_statuses=read_model_statuses,
                outbox_statuses=outbox_statuses,
                worker_statuses=worker_statuses,
            )
            for target in targets
        ]
        blocked_targets = [target for target in target_payloads if target["status"] == "blocked"]
        refreshing_targets = [target for target in target_payloads if target["status"] == "refreshing"]
        status = "blocked" if blocked_targets else "refreshing" if refreshing_targets else "fresh"
        return {
            "status": status,
            "fresh": status == "fresh",
            "targets": target_payloads,
            "blocked_targets": blocked_targets,
            "refreshing_targets": refreshing_targets,
        }

    def _runtime_snapshot(self) -> dict[str, Any]:
        try:
            snapshot = self._runtime_snapshot_provider()
        except Exception as exc:  # pragma: no cover - defensive degradation path.
            return {
                "read_model_statuses": {
                    "__runtime__": {
                        "status": "unavailable",
                        "last_error": str(exc) or exc.__class__.__name__,
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {},
            }
        return snapshot if isinstance(snapshot, dict) else {}

    def _target_status_payload(
        self,
        target: OperationFreshnessTarget,
        *,
        read_model_statuses: dict[str, Any],
        outbox_statuses: dict[str, Any],
        worker_statuses: dict[str, Any],
    ) -> dict[str, Any]:
        definition = _definition_for_target(target.read_model_key)
        scope_type = target.scope_type or (definition.scope_type if definition is not None else target.read_model_key)
        base = {
            "read_model_key": target.read_model_key,
            "scope_type": scope_type,
            "scope_key": target.scope_key,
        }
        if definition is None:
            return {
                **base,
                "status": "blocked",
                "raw_status": "unknown",
                "reason": "unknown_read_model",
            }
        runtime_status = _dict(read_model_statuses.get("__runtime__"))
        if _clean_text(runtime_status.get("status")) == "unavailable":
            return {
                **base,
                "status": "blocked",
                "raw_status": "unavailable",
                "reason": "runtime_unavailable",
                "last_error": runtime_status.get("last_error"),
            }
        read_model_payload = _dict(read_model_statuses.get(target.read_model_key))
        read_model_scope = _matching_scope(read_model_payload, scope_type=scope_type, scope_key=target.scope_key)
        raw_status = _clean_text((read_model_scope or read_model_payload).get("status")) or "missing"
        target_status = _barrier_status(raw_status)
        reason = _clean_text((read_model_scope or read_model_payload).get("reason"))
        last_error = (read_model_scope or read_model_payload).get("last_error")
        updated_at = (read_model_scope or read_model_payload).get("updated_at")
        generated_at = read_model_payload.get("generated_at")
        if read_model_scope is None and target.scope_key != "all":
            fallback_scope = _matching_scope(read_model_payload, scope_type=scope_type, scope_key="all")
            if fallback_scope is not None and _clean_text(fallback_scope.get("status")) == "fresh":
                raw_status = "fresh"
                target_status = "fresh"
                reason = ""
                last_error = fallback_scope.get("last_error")
                updated_at = fallback_scope.get("updated_at")
            elif raw_status == "fresh":
                raw_status = "missing"
                target_status = "refreshing"
                reason = "target readiness scope missing"
        outbox_payload = _target_outbox_payload(
            _dict(outbox_statuses.get(definition.refresh_event_type)),
            scope_type=scope_type,
            scope_key=target.scope_key,
        )
        outbox_status = _clean_text(outbox_payload.get("status"))
        if outbox_status in BLOCKED_OUTBOX_STATUSES:
            target_status = "blocked"
            raw_status = outbox_status
            reason = "refresh outbox blocked"
            last_error = outbox_payload.get("last_error") or last_error
            updated_at = outbox_payload.get("updated_at") or updated_at
        elif target_status == "fresh" and outbox_status in BUSY_OUTBOX_STATUSES:
            target_status = "refreshing"
            raw_status = outbox_status
            reason = "refresh outbox pending"
            updated_at = outbox_payload.get("updated_at") or updated_at
        worker_payload = _dict(worker_statuses.get(definition.worker_instance))
        result = {
            **base,
            "status": target_status,
            "fresh": target_status == "fresh",
            "blocking": target_status != "fresh",
            "raw_status": raw_status,
        }
        if reason:
            result["reason"] = reason
        if last_error:
            result["last_error"] = last_error
        if updated_at:
            result["updated_at"] = updated_at
        if generated_at:
            result["generated_at"] = generated_at
        if worker_payload:
            result["worker_status"] = worker_payload.get("status")
            if worker_payload.get("heartbeat_lag_seconds") is not None:
                result["worker_heartbeat_lag_seconds"] = worker_payload.get("heartbeat_lag_seconds")
        return result


def targets_from_payload(payload: dict[str, Any]) -> list[OperationFreshnessTarget]:
    raw_targets = payload.get("targets")
    if raw_targets is None and payload.get("read_model_key"):
        raw_targets = [payload]
    if not isinstance(raw_targets, list):
        raise ValueError("targets must be a list")
    targets: list[OperationFreshnessTarget] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ValueError("targets entries must be objects")
        targets.append(OperationFreshnessTarget.from_payload(item))
    return targets


def _barrier_status(status: str) -> str:
    normalized = _clean_text(status)
    if normalized == "fresh":
        return "fresh"
    if normalized in BLOCKED_READ_MODEL_STATUSES:
        return "blocked"
    if normalized in BUSY_READ_MODEL_STATUSES:
        return "refreshing"
    return "refreshing"


def _definition_for_target(read_model_key: str) -> Any:
    normalized = _clean_text(read_model_key)
    return APP_STATUS_READ_MODEL_REGISTRY.get(normalized)


def _matching_scope(payload: dict[str, Any], *, scope_type: str, scope_key: str) -> dict[str, Any] | None:
    for scope in payload.get("scopes") if isinstance(payload.get("scopes"), list) else []:
        scope_payload = _dict(scope)
        if _clean_text(scope_payload.get("scope_type")) != scope_type:
            continue
        if _clean_text(scope_payload.get("scope_key")) == scope_key:
            return scope_payload
    if _clean_text(payload.get("scope_type")) == scope_type and _clean_text(payload.get("scope_key")) == scope_key:
        return payload
    return None


def _target_outbox_payload(payload: dict[str, Any], *, scope_type: str, scope_key: str) -> dict[str, Any]:
    if not payload:
        return {}
    if scope_key == "all":
        return payload
    scoped_payload = _matching_scope(payload, scope_type=scope_type, scope_key=scope_key)
    if scoped_payload is not None:
        return scoped_payload
    if isinstance(payload.get("scopes"), list):
        return {}
    return payload


def _clean_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
