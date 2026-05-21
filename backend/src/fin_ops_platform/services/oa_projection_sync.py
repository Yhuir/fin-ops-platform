from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class OAProjectionSyncService:
    def __init__(
        self,
        *,
        source_adapter: Any,
        projection_repository: Any,
        queue_repository: Any,
    ) -> None:
        self._source_adapter = source_adapter
        self._projection_repository = projection_repository
        self._queue_repository = queue_repository

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        scope_key = self._event_scope_key(event)
        records = self._load_records(scope_key)
        upserted_count = self._projection_repository.upsert_application_records(records, scope_key=scope_key)
        result = {
            "sync_type": "oa_projection",
            "scope_key": scope_key,
            "status": "succeeded",
            "scanned_count": len(records),
            "upserted_count": upserted_count,
            "skipped_count": max(0, len(records) - upserted_count),
            "error_count": 0,
        }
        record_sync_run = getattr(self._projection_repository, "record_sync_run", None)
        if callable(record_sync_run):
            record_sync_run(result)
        self._mark_downstream_dirty(scope_key, records)
        return result

    @staticmethod
    def _event_scope_key(event: RuntimeQueueEvent) -> str:
        payload_scope = event.payload.get("scope_key") if isinstance(event.payload, dict) else None
        return str(payload_scope or event.scope_key or event.aggregate_id or "all").strip() or "all"

    def _load_records(self, scope_key: str) -> list[OAApplicationRecord]:
        if scope_key != "all":
            return list(self._source_adapter.list_application_records(scope_key))
        list_all = getattr(self._source_adapter, "list_all_application_records", None)
        if callable(list_all):
            return list(list_all())
        records: list[OAApplicationRecord] = []
        list_months = getattr(self._source_adapter, "list_available_months", None)
        months = list(list_months()) if callable(list_months) else []
        for month in months:
            records.extend(self._source_adapter.list_application_records(month))
        return records

    def _mark_downstream_dirty(self, scope_key: str, records: list[OAApplicationRecord]) -> None:
        months = {
            str(record.month).strip()
            for record in list(records or [])
            if str(getattr(record, "month", "")).strip()
        }
        if scope_key != "all" and scope_key:
            months.add(scope_key)
        target_scopes = sorted({month for month in months if month and month != "all"})
        if target_scopes:
            target_scopes.append("all")
        else:
            target_scopes = ["all"]
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return
        for target_scope in target_scopes:
            enqueue(scope_type="workbench", scope_key=target_scope, reason="oa_projection_sync")
            enqueue(scope_type="search", scope_key=target_scope, reason="oa_projection_sync")
        for pending_scope in ("expense:all", "income:all"):
            enqueue(scope_type="pending_invoice", scope_key=pending_scope, reason="oa_projection_sync")

