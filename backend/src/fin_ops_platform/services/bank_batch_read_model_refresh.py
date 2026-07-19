from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchApplicationService,
    BankBatchPairRelationSnapshotPort,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_RELATION_MODE,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE = "no_oa_bank_batch.read_model.refresh"
NO_OA_BANK_BATCH_SCOPE_TYPE = "no_oa_bank_batch"


class BankBatchReadModelPersistencePort:
    """Narrow persistence boundary for no-OA public read model snapshots."""

    def __init__(self, state_store: Any) -> None:
        self._state_store = state_store

    def save_public_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        scope_key: str = "all",
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> None:
        save_scope = getattr(self._state_store, "save_no_oa_bank_batches_scope", None)
        if callable(save_scope):
            save_scope(snapshot, scope_key=scope_key, relation_mode=relation_mode)
            return
        save_snapshot = getattr(self._state_store, "save_no_oa_bank_batches", None)
        if not callable(save_snapshot):
            raise RuntimeError("No-OA read model persistence requires save_no_oa_bank_batches.")
        save_snapshot(snapshot, relation_mode=relation_mode)


class BankBatchReadModelRefreshService:
    def __init__(
        self,
        *,
        import_service: Any,
        effective_category_provider: Any,
        bank_batch_service: Any,
        app_settings_service: Any,
        bank_transaction_category_service: Any,
        pair_relation_service: Any,
        workbench_read_model_service: Any,
        state_store: Any,
        queue_repository: Any | None = None,
        read_model_persistence: Any | None = None,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        relation_facade: Any | None = None,
        application_service_class: type[BankBatchApplicationService] = BankBatchApplicationService,
        refresh_event_type: str = NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE,
        scope_type: str = NO_OA_BANK_BATCH_SCOPE_TYPE,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> None:
        self._refresh_event_type = str(refresh_event_type or NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE).strip()
        self._scope_type = str(scope_type or NO_OA_BANK_BATCH_SCOPE_TYPE).strip()
        self._relation_mode = str(relation_mode or NO_OA_BANK_BATCH_RELATION_MODE).strip()
        self._queue_repository = queue_repository
        self._read_model_persistence = read_model_persistence or BankBatchReadModelPersistencePort(state_store)
        repository_attr = (
            "bank_flow_rule_batch_sql_read_repository"
            if self._relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
            else "no_oa_bank_batch_sql_read_repository"
        )
        bank_batch_read_model_repository = getattr(state_store, repository_attr, None)
        self._application_service = application_service_class(
            import_service=import_service,
            effective_category_provider=effective_category_provider,
            bank_batch_service=bank_batch_service,
            app_settings_service=app_settings_service,
            bank_transaction_category_service=bank_transaction_category_service,
            pair_relation_snapshot_port=BankBatchPairRelationSnapshotPort(pair_relation_service),
            workbench_read_model_service=workbench_read_model_service,
            state_store=state_store,
            bank_batch_read_model_repository=bank_batch_read_model_repository,
            workbench_matching_source_versions_provider=workbench_matching_source_versions_provider,
            queue_repository=queue_repository,
            relation_facade=relation_facade,
        )
        self._bank_batch_service = bank_batch_service

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != self._refresh_event_type:
            raise ValueError(f"Unsupported bank batch read model event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != self._scope_type or not scope_key:
            raise ValueError(f"Bank batch refresh requires scope_type={self._scope_type!r} and scope_key.")

        if not self._event_source_version_is_current(event, scope_key=scope_key):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": event.source_version or event.payload.get("source_version"),
            }

        relation_mode = self._relation_mode_for_event(event)
        precheck_source_versions: dict[str, object] | None = None
        if _is_month_scope(scope_key):
            precheck_source_versions = self._application_service.read_model_scope_source_versions(
                scope_key=scope_key,
                relation_mode=relation_mode,
            )
            unchanged = self._application_service.unchanged_read_model_scope_result(
                scope_key=scope_key,
                source_versions=precheck_source_versions,
                relation_mode=relation_mode,
                allow_refreshing_read_model_status=True,
            )
            if unchanged is not None:
                self._complete_dirty_scope(event, scope_key=scope_key)
                return {
                    **unchanged,
                    "bank_row_count": self._application_service.bank_row_count_from_source_versions(precheck_source_versions),
                }

        bank_rows = self._application_service.bank_transaction_rows(
            month=scope_key,
            include_categories=False,
        )
        categories = self._application_service.effective_categories_for_rows(bank_rows)
        self._application_service.load_relation_source_versions_for_bank_rows(bank_rows)
        source_versions = (
            dict(precheck_source_versions)
            if isinstance(precheck_source_versions, dict) and precheck_source_versions
            else self._application_service.bank_batch_source_versions(
                relation_mode=relation_mode,
            )
        )

        active_relations = self._application_service.active_relations_for_bank_rows(bank_rows)
        bank_rows, _categories = self._application_service.refresh_batches_from_prepared_rows(
            bank_rows=bank_rows,
            categories_by_transaction_id=categories,
            active_relations=active_relations,
            source_versions=source_versions,
            apply_relation_repairs=False,
            scope_key=scope_key,
            relation_mode=relation_mode,
        )
        snapshot = self._bank_batch_service.public_snapshot()
        self._read_model_persistence.save_public_snapshot(
            snapshot,
            scope_key=scope_key,
            relation_mode=relation_mode,
        )
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
                scope_type=self._scope_type,
                scope_key=scope_key,
                source_version=event.source_version or event.payload.get("source_version"),
            )

    def _relation_mode_for_event(self, event: RuntimeQueueEvent) -> str:
        payload = event.payload if isinstance(event.payload, dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        relation_mode = str(metadata.get("relation_mode") or payload.get("relation_mode") or "").strip()
        if relation_mode:
            return relation_mode
        if event.event_type == "bank_flow_rule_batch.read_model.refresh":
            return BANK_FLOW_RULE_BATCH_RELATION_MODE
        action_name = str(metadata.get("action_name") or payload.get("action_name") or "").strip()
        if action_name.startswith("bank_flow_rule_batch"):
            return BANK_FLOW_RULE_BATCH_RELATION_MODE
        return self._relation_mode

    def _event_source_version_is_current(self, event: RuntimeQueueEvent, *, scope_key: str) -> bool:
        is_current = getattr(self._queue_repository, "read_model_refresh_is_current", None)
        if not callable(is_current):
            return True
        return bool(
            is_current(
                tenant_id=event.tenant_id,
                scope_type=self._scope_type,
                scope_key=scope_key,
                source_version=event.source_version or event.payload.get("source_version"),
            )
        )


def _is_month_scope(scope_key: str) -> bool:
    return len(scope_key) == 7 and scope_key[4:5] == "-" and scope_key[:4].isdigit() and scope_key[5:].isdigit()
