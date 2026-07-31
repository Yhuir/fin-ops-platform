from __future__ import annotations


class WorkbenchRefreshStatusPayloadNormalizer:
    """Pure Workbench refresh-status payload normalizer."""

    def normalize(
        self,
        payload: dict[str, object],
        *,
        scope_key: str,
        fallback_status: str = "fresh",
    ) -> dict[str, object]:
        dirty_scopes = payload.get("dirty_scopes") if isinstance(payload.get("dirty_scopes"), list) else []
        running_scopes = payload.get("running_scopes") if isinstance(payload.get("running_scopes"), list) else []
        dirty_statuses = {
            str(scope.get("status") or "").strip().lower()
            for scope in dirty_scopes
            if isinstance(scope, dict)
        }
        has_active_dirty_scope = bool(dirty_statuses.intersection({"pending", "processing", "queued", "running"}))
        raw_status = str(payload.get("read_model_status") or payload.get("status") or fallback_status).strip().lower()
        if has_active_dirty_scope:
            read_model_status = "refreshing"
        elif dirty_statuses.intersection({"failed", "dead_lettered"}):
            read_model_status = "failed"
        elif raw_status in {"failed", "error"}:
            read_model_status = "failed"
        elif raw_status in {"refreshing", "rebuilding", "pending", "processing", "queued", "running"}:
            read_model_status = "refreshing"
        elif raw_status in {"stale", "dirty"}:
            read_model_status = "stale"
        elif raw_status == "unavailable":
            read_model_status = "unavailable"
        else:
            read_model_status = "fresh"

        last_error = payload.get("last_error")
        if not last_error:
            last_error = next(
                (
                    scope.get("last_error")
                    for scope in dirty_scopes
                    if isinstance(scope, dict) and scope.get("last_error")
                ),
                None,
            )
        if read_model_status == "refreshing":
            last_error = None
        read_model_version = (
            payload.get("active_generation_id")
            or payload.get("read_model_version")
            or payload.get("source_version")
            or payload.get("version")
            or next(
                (
                    scope.get("source_version")
                    for scope in dirty_scopes
                    if isinstance(scope, dict) and scope.get("source_version") is not None
                ),
                None,
            )
        )
        generated_at = payload.get("generated_at") or payload.get("read_model_generated_at")
        return {
            **payload,
            "scope_key": str(payload.get("scope_key") or scope_key or "all"),
            "read_model_status": read_model_status,
            "generated_at": generated_at,
            "active_generation_id": payload.get("active_generation_id"),
            "building_generation_id": payload.get("building_generation_id"),
            "failed_generation_id": payload.get("failed_generation_id"),
            "read_model_version": read_model_version,
            "dirty_scopes": dirty_scopes,
            "running_scopes": running_scopes,
            "processed_count": payload.get("processed_count") if payload.get("processed_count") is not None else None,
            "total_count": payload.get("total_count") if payload.get("total_count") is not None else None,
            "worker_lag_seconds": payload.get("worker_lag_seconds") if payload.get("worker_lag_seconds") is not None else None,
            "last_error": last_error,
            "retryable": bool(read_model_status in {"failed", "stale", "unavailable"}),
        }
