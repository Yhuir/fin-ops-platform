from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.no_oa_bank_batch_application_service import NoOaBankBatchApplicationService
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE = "no_oa_bank_batch.read_model.refresh"
NO_OA_BANK_BATCH_SCOPE_TYPE = "no_oa_bank_batch"


class NoOaBankBatchReadModelRefreshService:
    def __init__(
        self,
        *,
        import_service: Any,
        effective_category_provider: Any,
        no_oa_bank_batch_service: Any,
        app_settings_service: Any,
        bank_transaction_category_service: Any,
        pair_relation_service: Any,
        workbench_read_model_service: Any,
        state_store: Any,
        queue_repository: Any | None = None,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        relation_facade: Any | None = None,
    ) -> None:
        self._state_store = state_store
        self._queue_repository = queue_repository
        self._application_service = NoOaBankBatchApplicationService(
            import_service=import_service,
            effective_category_provider=effective_category_provider,
            no_oa_bank_batch_service=no_oa_bank_batch_service,
            app_settings_service=app_settings_service,
            bank_transaction_category_service=bank_transaction_category_service,
            pair_relation_service=pair_relation_service,
            workbench_read_model_service=workbench_read_model_service,
            state_store=state_store,
            workbench_matching_source_versions_provider=workbench_matching_source_versions_provider,
            queue_repository=queue_repository,
            relation_facade=relation_facade,
        )
        self._no_oa_bank_batch_service = no_oa_bank_batch_service

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE:
            raise ValueError(f"Unsupported no-OA bank batch read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != NO_OA_BANK_BATCH_SCOPE_TYPE or not scope_key:
            raise ValueError("No-OA bank batch refresh requires scope_type='no_oa_bank_batch' and scope_key.")

        if not self._event_source_version_is_current(event, scope_key=scope_key):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": event.source_version or event.payload.get("source_version"),
            }

        bank_rows, _categories = self._application_service.refresh_batches(
            apply_relation_repairs=False
        )
        snapshot = self._no_oa_bank_batch_service.snapshot()
        self._state_store.save_no_oa_bank_batches(snapshot)
        self._complete_dirty_scope(event, scope_key=scope_key)
        batches = snapshot.get("batches") if isinstance(snapshot, dict) else {}
        return {
            "scope_key": scope_key,
            "bank_row_count": len(bank_rows),
            "batch_count": len(batches) if isinstance(batches, dict) else 0,
        }

    def _complete_dirty_scope(self, event: RuntimeQueueEvent, *, scope_key: str) -> None:
        complete_dirty_scope = getattr(self._queue_repository, "complete_read_model_refresh", None)
        if callable(complete_dirty_scope):
            complete_dirty_scope(
                tenant_id=event.tenant_id,
                scope_type=NO_OA_BANK_BATCH_SCOPE_TYPE,
                scope_key=scope_key,
                source_version=event.source_version or event.payload.get("source_version"),
            )

    def _event_source_version_is_current(self, event: RuntimeQueueEvent, *, scope_key: str) -> bool:
        is_current = getattr(self._queue_repository, "read_model_refresh_is_current", None)
        if not callable(is_current):
            return True
        return bool(
            is_current(
                tenant_id=event.tenant_id,
                scope_type=NO_OA_BANK_BATCH_SCOPE_TYPE,
                scope_key=scope_key,
                source_version=event.source_version or event.payload.get("source_version"),
            )
        )
