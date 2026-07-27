from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchApplicationService,
    BankBatchPairRelationSnapshotPort,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent

class BankBatchMaterializationService:
    def __init__(
        self,
        *,
        import_service: Any,
        effective_category_provider: Any,
        bank_batch_service: Any,
        app_settings_service: Any,
        bank_transaction_category_service: Any,
        pair_relation_service: Any,
        state_store: Any,
        materialization_persistence: Any,
        workbench_matching_source_versions_provider: Callable[[], dict[str, object]] | None = None,
        relation_facade: Any | None = None,
        relation_source_repository: Any | None = None,
        application_service_class: type[BankBatchApplicationService] = BankBatchApplicationService,
        refresh_event_type: str,
        scope_type: str,
        relation_mode: str,
    ) -> None:
        self._refresh_event_type = str(refresh_event_type).strip()
        self._scope_type = str(scope_type).strip()
        self._relation_mode = str(relation_mode).strip()
        self._materialization_persistence = materialization_persistence
        repository_attr = (
            "bank_flow_rule_batch_canonical_query_repository"
            if self._relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
            else "no_oa_bank_batch_sql_read_repository"
        )
        bank_batch_query_repository = getattr(state_store, repository_attr, None)
        self._application_service = application_service_class(
            import_service=import_service,
            effective_category_provider=effective_category_provider,
            bank_batch_service=bank_batch_service,
            app_settings_service=app_settings_service,
            bank_transaction_category_service=bank_transaction_category_service,
            pair_relation_snapshot_port=BankBatchPairRelationSnapshotPort(pair_relation_service),
            state_store=state_store,
            bank_batch_query_repository=bank_batch_query_repository,
            workbench_matching_source_versions_provider=workbench_matching_source_versions_provider,
            relation_facade=relation_facade,
            relation_source_repository=relation_source_repository,
        )
        self._bank_batch_service = bank_batch_service

    def handle_runtime_event(self, event: RuntimeQueueEvent) -> dict[str, Any]:
        if event.event_type != self._refresh_event_type:
            raise ValueError(f"Unsupported bank batch materialization event type: {event.event_type}")
        scope_type = str(event.scope_type or event.payload.get("scope_type") or "").strip()
        scope_key = str(event.scope_key or event.payload.get("scope_key") or event.aggregate_id or "").strip()
        if scope_type != self._scope_type or not scope_key:
            raise ValueError(
                f"Bank batch materialization requires scope_type={self._scope_type!r} and scope_key."
            )
        source_proof = self._source_proof_before_build(scope_key=scope_key)

        relation_mode = self._relation_mode_for_event(event)
        relation_bundle: dict[str, object] | None = None
        bank_rows: list[dict[str, object]] | None = None
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            bank_rows = self._application_service.bank_transaction_rows(
                month=scope_key,
                include_categories=False,
            )
            relation_bundle = self._application_service.active_relation_source_bundle_for_bank_rows(
                bank_rows,
                scope_key=scope_key,
            )
        precheck_source_versions: dict[str, object] | None = None
        if _is_month_scope(scope_key) or relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
            relation_source_versions = (
                relation_bundle.get("source_versions")
                if isinstance(relation_bundle, dict)
                else None
            )
            precheck_source_versions = self._application_service.canonical_draft_source_versions(
                scope_key=scope_key,
                relation_mode=relation_mode,
                relation_source_versions=(
                    dict(relation_source_versions)
                    if isinstance(relation_source_versions, dict)
                    else None
                ),
                source_scope_keys=(
                    self._source_scope_keys(scope_key, bank_rows)
                    if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
                    else None
                ),
            )
        if bank_rows is None:
            bank_rows = self._application_service.bank_transaction_rows(
                month=scope_key,
                include_categories=False,
            )
        categories = self._application_service.effective_categories_for_rows(bank_rows)
        if relation_mode != BANK_FLOW_RULE_BATCH_RELATION_MODE:
            self._application_service.load_relation_source_versions_for_bank_rows(
                bank_rows,
                relation_mode=relation_mode,
            )
        source_versions = (
            dict(precheck_source_versions)
            if isinstance(precheck_source_versions, dict) and precheck_source_versions
            else self._application_service.bank_batch_source_versions(
                relation_mode=relation_mode,
            )
        )
        if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE and isinstance(relation_bundle, dict):
            relation_source_versions = relation_bundle.get("source_versions")
            if (
                isinstance(relation_source_versions, dict)
                and "workbench_relation_source_versions" not in source_versions
            ):
                source_versions["workbench_relation_source_versions"] = dict(relation_source_versions)

        active_relations = (
            [dict(row) for row in list(relation_bundle.get("rows") or []) if isinstance(row, dict)]
            if isinstance(relation_bundle, dict)
            else self._application_service.active_relations_for_bank_rows(bank_rows)
        )
        bank_rows, _categories = self._application_service.refresh_batches_from_prepared_rows(
            bank_rows=bank_rows,
            categories_by_transaction_id=categories,
            active_relations=active_relations,
            source_versions=source_versions,
            apply_relation_repairs=False,
            scope_key=scope_key,
            relation_mode=relation_mode,
        )
        if not self._publish_source_versions_are_current(
            scope_key=scope_key,
            relation_mode=relation_mode,
            expected_source_versions=source_versions,
        ):
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "canonical_source_changed",
            }
        snapshot = self._bank_batch_service.public_snapshot()
        persisted = self._materialization_persistence.save_public_snapshot(
            snapshot,
            scope_key=scope_key,
            relation_mode=relation_mode,
            expected_source_proof=source_proof,
        )
        if persisted is False:
            return {
                "scope_key": scope_key,
                "skipped": True,
                "skip_reason": "canonical_source_changed",
            }
        batches = snapshot.get("batches") if isinstance(snapshot, dict) else {}
        return {
            "scope_key": scope_key,
            "bank_row_count": len(bank_rows),
            "batch_count": len(batches) if isinstance(batches, dict) else 0,
        }

    def _publish_source_versions_are_current(
        self,
        *,
        scope_key: str,
        relation_mode: str,
        expected_source_versions: dict[str, object],
    ) -> bool:
        return True

    def _source_proof_before_build(
        self,
        *,
        scope_key: str,
    ) -> dict[str, object]:
        return {}

    @staticmethod
    def _source_scope_keys(
        scope_key: str,
        bank_rows: list[dict[str, object]],
    ) -> list[str]:
        return [scope_key] if _is_month_scope(scope_key) else []

    def _relation_mode_for_event(self, event: RuntimeQueueEvent) -> str:
        payload = event.payload if isinstance(event.payload, dict) else {}
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        relation_mode = str(metadata.get("relation_mode") or payload.get("relation_mode") or "").strip()
        if relation_mode:
            return relation_mode
        action_name = str(metadata.get("action_name") or payload.get("action_name") or "").strip()
        if action_name.startswith("bank_flow_rule_batch"):
            return BANK_FLOW_RULE_BATCH_RELATION_MODE
        return self._relation_mode



def _is_month_scope(scope_key: str) -> bool:
    return len(scope_key) == 7 and scope_key[4:5] == "-" and scope_key[:4].isdigit() and scope_key[5:].isdigit()
