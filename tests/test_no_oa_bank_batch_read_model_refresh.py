from __future__ import annotations

import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.no_oa_bank_batch_read_model_refresh import (
    NoOaBankBatchReadModelPersistencePort,
    NoOaBankBatchReadModelRefreshService,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class NoOaBankBatchReadModelRefreshTests(unittest.TestCase):
    def test_persistence_port_delegates_to_store_snapshot_save(self) -> None:
        class StateStore:
            def __init__(self) -> None:
                self.saved_snapshots: list[dict[str, object]] = []

            def save_no_oa_bank_batches(self, snapshot: dict[str, object]) -> None:
                self.saved_snapshots.append(dict(snapshot))

        state_store = StateStore()
        port = NoOaBankBatchReadModelPersistencePort(state_store)

        port.save_public_snapshot({"batches": {"batch-1": {"status": "draft"}}})

        self.assertEqual(state_store.saved_snapshots, [{"batches": {"batch-1": {"status": "draft"}}}])

    def test_refresh_persists_through_explicit_persistence_boundary(self) -> None:
        class StateStore:
            def save_no_oa_bank_batches(self, *_args, **_kwargs) -> None:
                raise AssertionError("refresh handler must use read_model_persistence, not broad state_store")

        class Persistence:
            def __init__(self) -> None:
                self.saved_snapshots: list[dict[str, object]] = []

            def save_public_snapshot(self, snapshot: dict[str, object]) -> None:
                self.saved_snapshots.append(dict(snapshot))

        app = build_application()
        persistence = Persistence()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=app._import_service,
            effective_category_provider=app._bank_transaction_effective_category_provider,
            no_oa_bank_batch_service=app._no_oa_bank_batch_service,
            app_settings_service=app._app_settings_service,
            bank_transaction_category_service=app._bank_transaction_category_service,
            pair_relation_service=app._workbench_pair_relation_service,
            workbench_read_model_service=app._workbench_read_model_service,
            state_store=StateStore(),
            read_model_persistence=persistence,
            workbench_matching_source_versions_provider=app._workbench_matching_source_versions,
        )

        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-explicit-persistence",
                tenant_id="default",
                event_type="no_oa_bank_batch.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="all",
                scope_type="no_oa_bank_batch",
                scope_key="all",
                dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:all",
                payload={"scope_type": "no_oa_bank_batch", "scope_key": "all", "source_version": 1},
                attempts=1,
                status="processing",
                source_version=1,
            )
        )

        self.assertEqual(result["scope_key"], "all")
        self.assertEqual(len(persistence.saved_snapshots), 1)

    def test_refresh_does_not_repair_workbench_relations_from_read_model_path(self) -> None:
        class ImportService:
            def list_transactions(self, *, month: str = "all"):
                return [
                    {
                        "id": "fee-1",
                        "txn_date": "2026-03-10",
                        "txn_direction": "outflow",
                        "amount": "3.00",
                        "bank_name": "CCB",
                        "account_no": "6222000000008106",
                        "counterparty_name": "云南三源",
                    }
                ]

        class EffectiveCategoryProvider:
            def bulk_get_for_rows(self, rows):
                return {
                    str(row["id"]): {
                        "transaction_id": row["id"],
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_source": "auto",
                    }
                    for row in rows
                }

        class StateStore:
            def __init__(self) -> None:
                self.saved_no_oa_snapshots: list[dict[str, object]] = []

            def save_no_oa_bank_batches(self, snapshot) -> None:
                self.saved_no_oa_snapshots.append(dict(snapshot))

            def save_workbench_pair_relations(self, *_args, **_kwargs) -> None:
                raise AssertionError("no-OA read model refresh must not repair pair relations")

            def save_no_oa_bank_batch_mutation(self, **_kwargs) -> None:
                raise AssertionError("no-OA read model refresh must not persist relation mutations")

        pair_relation_service = WorkbenchPairRelationService()
        batch_id = NoOaBankBatchService._batch_id("single:fee:2026-03:CCB:8106")
        no_oa_service = NoOaBankBatchService.from_snapshot(
            {
                "batches": {
                    batch_id: {
                        "batch_id": batch_id,
                        "batch_key": "single:fee:2026-03:CCB:8106",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "bank_name": "CCB",
                        "account_last4": "8106",
                        "status": "submitted",
                        "row_ids": ["fee-1"],
                        "row_count": 1,
                        "total_amount": "3.00",
                        "tag_counts": {"fee": 1},
                        "direction_counts": {"income": 0, "expense": 1},
                        "relation_case_id": batch_id,
                        "source_versions": {},
                        "evidence": {"source": "test"},
                        "category_source": "auto",
                        "created_by": "finance-user",
                        "created_at": "2026-03-10T00:00:00+00:00",
                        "submitted_by": "finance-user",
                        "submitted_at": "2026-03-10T00:00:00+00:00",
                        "version": 1,
                        "updated_at": "2026-03-10T00:00:00+00:00",
                    }
                }
            },
            pair_relation_service=pair_relation_service,
        )
        state_store = StateStore()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=ImportService(),
            effective_category_provider=EffectiveCategoryProvider(),
            no_oa_bank_batch_service=no_oa_service,
            app_settings_service=type(
                "Settings",
                (),
                {
                    "get_no_oa_bank_batch_tag_selection_payload": lambda _self: {
                        "version": 1,
                        "selected_tag_codes": ["fee"],
                    }
                },
            )(),
            bank_transaction_category_service=type("CategoryService", (), {"snapshot": lambda _self: {}})(),
            pair_relation_service=pair_relation_service,
            workbench_read_model_service=type("WorkbenchReadModel", (), {"snapshot": lambda _self: {}})(),
            state_store=state_store,
            workbench_matching_source_versions_provider=lambda: {},
            relation_facade=type(
                "RelationFacade",
                (),
                {
                    "list_by_month": lambda _self, *_args, **_kwargs: {
                        "status": "fresh",
                        "rows": [],
                        "groups": [],
                        "source_versions": {},
                    }
                },
            )(),
        )

        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-no-repair",
                tenant_id="default",
                event_type="no_oa_bank_batch.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="all",
                scope_type="no_oa_bank_batch",
                scope_key="all",
                dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:all",
                payload={"scope_type": "no_oa_bank_batch", "scope_key": "all", "source_version": 5},
                attempts=1,
                status="processing",
                source_version=5,
            )
        )

        self.assertEqual(result["scope_key"], "all")
        self.assertEqual(pair_relation_service.list_active_relations(), [])
        self.assertEqual(len(state_store.saved_no_oa_snapshots), 1)

    def test_source_versions_include_bank_detail_source_versions_from_tag_facade(self) -> None:
        class EffectiveCategoryProvider:
            last_source_versions = {"bank_detail": {"scope_key": "2026-04", "source_version": 11}}

            def bulk_get_for_rows(self, _rows):
                return {}

        app = build_application()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=app._import_service,
            effective_category_provider=EffectiveCategoryProvider(),
            no_oa_bank_batch_service=app._no_oa_bank_batch_service,
            app_settings_service=app._app_settings_service,
            bank_transaction_category_service=app._bank_transaction_category_service,
            pair_relation_service=app._workbench_pair_relation_service,
            workbench_read_model_service=app._workbench_read_model_service,
            state_store=app._state_store,
            workbench_matching_source_versions_provider=app._workbench_matching_source_versions,
        )

        source_versions = service._application_service.no_oa_bank_batch_source_versions()

        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {"bank_detail": {"scope_key": "2026-04", "source_version": 11}},
        )

    def test_facade_non_fresh_error_does_not_save_no_oa_snapshot(self) -> None:
        class ImportService:
            def list_transactions(self, *, month: str = "all"):
                return [
                    {
                        "id": "txn-1",
                        "txn_date": "2026-04-23",
                        "txn_direction": "outflow",
                        "amount": "23053.31",
                        "counterparty_name": "云南辰飞机电工程有限公司",
                        "summary": "货款",
                    }
                ]

        class EffectiveCategoryProvider:
            def bulk_get_for_rows(self, _rows):
                raise RuntimeError("bank_detail_read_model_not_fresh")

        class StateStore:
            def save_no_oa_bank_batches(self, *_args, **_kwargs) -> None:
                raise AssertionError("non-fresh bank detail tags must not publish a no-OA snapshot")

        app = build_application()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=ImportService(),
            effective_category_provider=EffectiveCategoryProvider(),
            no_oa_bank_batch_service=app._no_oa_bank_batch_service,
            app_settings_service=app._app_settings_service,
            bank_transaction_category_service=app._bank_transaction_category_service,
            pair_relation_service=app._workbench_pair_relation_service,
            workbench_read_model_service=app._workbench_read_model_service,
            state_store=StateStore(),
            workbench_matching_source_versions_provider=app._workbench_matching_source_versions,
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            service.handle_runtime_event(
                RuntimeQueueEvent(
                    event_id="evt-non-fresh",
                    tenant_id="default",
                    event_type="no_oa_bank_batch.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="all",
                    scope_type="no_oa_bank_batch",
                    scope_key="all",
                    dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:all",
                    payload={"scope_type": "no_oa_bank_batch", "scope_key": "all", "source_version": 4},
                    attempts=1,
                    status="processing",
                    source_version=4,
                )
            )

    def test_refresh_reads_effective_categories_once_for_same_rows(self) -> None:
        class ImportService:
            def list_transactions(self, *, month: str = "all"):
                self.last_month = month
                return [
                    {
                        "id": "txn-once",
                        "txn_date": "2026-04-23",
                        "txn_direction": "outflow",
                        "amount": "12.00",
                        "bank_name": "CCB",
                        "account_no": "6222000000008106",
                        "counterparty_name": "测试供应商",
                    }
                ]

        class EffectiveCategoryProvider:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []

            def bulk_get_for_rows(self, rows):
                self.calls.append([str(row.get("id") or "") for row in rows])
                return {
                    "txn-once": {
                        "transaction_id": "txn-once",
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_source": "auto",
                    }
                }

        class StateStore:
            def save_no_oa_bank_batches(self, _snapshot) -> None:
                return None

        app = build_application()
        provider = EffectiveCategoryProvider()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=ImportService(),
            effective_category_provider=provider,
            no_oa_bank_batch_service=app._no_oa_bank_batch_service,
            app_settings_service=type(
                "Settings",
                (),
                {
                    "get_no_oa_bank_batch_tag_selection_payload": lambda _self: {
                        "version": 1,
                        "selected_tag_codes": ["fee"],
                    }
                },
            )(),
            bank_transaction_category_service=app._bank_transaction_category_service,
            pair_relation_service=app._workbench_pair_relation_service,
            workbench_read_model_service=app._workbench_read_model_service,
            state_store=StateStore(),
            workbench_matching_source_versions_provider=app._workbench_matching_source_versions,
        )

        service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-once",
                tenant_id="default",
                event_type="no_oa_bank_batch.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="all",
                scope_type="no_oa_bank_batch",
                scope_key="all",
                dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:all",
                payload={"scope_type": "no_oa_bank_batch", "scope_key": "all", "source_version": 4},
                attempts=1,
                status="processing",
                source_version=4,
            )
        )

        self.assertEqual(provider.calls, [["txn-once"]])

    def test_month_scope_refresh_reads_only_month_and_preserves_other_month_batches(self) -> None:
        class ImportService:
            def __init__(self) -> None:
                self.months: list[str] = []

            def list_transactions(self, *, month: str = "all"):
                self.months.append(month)
                if month != "2026-04":
                    raise AssertionError(f"monthly no-OA refresh must not read {month!r}")
                return [
                    {
                        "id": "fee-apr",
                        "txn_date": "2026-04-23",
                        "txn_direction": "outflow",
                        "amount": "12.00",
                        "bank_name": "CCB",
                        "account_no": "6222000000008106",
                        "counterparty_name": "四月供应商",
                    }
                ]

        class EffectiveCategoryProvider:
            def bulk_get_for_rows(self, rows):
                return {
                    str(row["id"]): {
                        "transaction_id": row["id"],
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_source": "auto",
                    }
                    for row in rows
                }

        class StateStore:
            def __init__(self) -> None:
                self.saved_no_oa_snapshots: list[dict[str, object]] = []

            def save_no_oa_bank_batches(self, snapshot) -> None:
                self.saved_no_oa_snapshots.append(dict(snapshot))

        old_batch = {
            "batch_id": "submitted-mar",
            "batch_key": "single:fee:2026-03:CCB:8106",
            "batch_type": "fee",
            "batch_label": "手续费",
            "scope_month": "2026-03",
            "account_key": "CCB:8106",
            "bank_name": "CCB",
            "account_last4": "8106",
            "status": "submitted",
            "status_bucket": "submitted",
            "row_ids": ["fee-mar"],
            "row_count": 1,
            "total_amount": "8.00",
            "tag_counts": {"fee": 1},
            "direction_counts": {"income": 0, "expense": 1},
            "relation_case_id": "submitted-mar",
            "source_versions": {},
            "evidence": {"source": "test"},
            "category_source": "auto",
            "created_by": "finance-user",
            "created_at": "2026-03-10T00:00:00+00:00",
            "submitted_by": "finance-user",
            "submitted_at": "2026-03-10T00:00:00+00:00",
            "version": 1,
            "updated_at": "2026-03-10T00:00:00+00:00",
        }
        pair_relation_service = WorkbenchPairRelationService()
        no_oa_service = NoOaBankBatchService.from_snapshot(
            {"batches": {old_batch["batch_id"]: old_batch}},
            pair_relation_service=pair_relation_service,
        )
        state_store = StateStore()
        import_service = ImportService()
        service = NoOaBankBatchReadModelRefreshService(
            import_service=import_service,
            effective_category_provider=EffectiveCategoryProvider(),
            no_oa_bank_batch_service=no_oa_service,
            app_settings_service=type(
                "Settings",
                (),
                {
                    "get_no_oa_bank_batch_tag_selection_payload": lambda _self: {
                        "version": 1,
                        "selected_tag_codes": ["fee"],
                    }
                },
            )(),
            bank_transaction_category_service=type("CategoryService", (), {"snapshot": lambda _self: {}})(),
            pair_relation_service=pair_relation_service,
            workbench_read_model_service=type("WorkbenchReadModel", (), {"snapshot": lambda _self: {}})(),
            state_store=state_store,
            workbench_matching_source_versions_provider=lambda: {},
            relation_facade=type(
                "RelationFacade",
                (),
                {
                    "list_by_month": lambda _self, *_args, **_kwargs: {
                        "status": "fresh",
                        "rows": [],
                        "groups": [],
                        "source_versions": {},
                    }
                },
            )(),
        )

        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-apr",
                tenant_id="default",
                event_type="no_oa_bank_batch.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="2026-04",
                scope_type="no_oa_bank_batch",
                scope_key="2026-04",
                dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:2026-04",
                payload={"scope_type": "no_oa_bank_batch", "scope_key": "2026-04", "source_version": 4},
                attempts=1,
                status="processing",
                source_version=4,
            )
        )

        self.assertEqual(result["scope_key"], "2026-04")
        self.assertEqual(import_service.months, ["2026-04"])
        self.assertEqual(len(state_store.saved_no_oa_snapshots), 1)
        batches = state_store.saved_no_oa_snapshots[0]["batches"]
        self.assertIn("submitted-mar", batches)
        self.assertTrue(
            any(
                isinstance(batch, dict)
                and batch.get("scope_month") == "2026-04"
                and batch.get("status") == "draft"
                for batch in batches.values()
            )
        )

    def test_stale_source_version_does_not_rebuild_or_overwrite_read_model(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.completions: list[dict[str, object]] = []

            def read_model_refresh_is_current(self, **_kwargs) -> bool:
                return False

            def complete_read_model_refresh(self, **kwargs) -> None:
                self.completions.append(dict(kwargs))

        class StateStore:
            def save_no_oa_bank_batches(self, *_args, **_kwargs) -> None:
                raise AssertionError("stale no-OA refresh events must not overwrite the read model")

        app = build_application()
        original_build_batches = app._no_oa_bank_batch_service.build_batches

        def fail_if_rebuilt(*_args, **_kwargs):
            raise AssertionError("stale no-OA refresh events must not rebuild batches")

        queue_repository = QueueRepository()
        app._no_oa_bank_batch_service.build_batches = fail_if_rebuilt
        service = NoOaBankBatchReadModelRefreshService(
            import_service=app._import_service,
            effective_category_provider=app._bank_transaction_effective_category_provider,
            no_oa_bank_batch_service=app._no_oa_bank_batch_service,
            app_settings_service=app._app_settings_service,
            bank_transaction_category_service=app._bank_transaction_category_service,
            pair_relation_service=app._workbench_pair_relation_service,
            workbench_read_model_service=app._workbench_read_model_service,
            state_store=StateStore(),
            queue_repository=queue_repository,
            workbench_matching_source_versions_provider=app._workbench_matching_source_versions,
        )
        try:
            result = service.handle_runtime_event(
                RuntimeQueueEvent(
                    event_id="evt-old",
                    tenant_id="default",
                    event_type="no_oa_bank_batch.read_model.refresh",
                    aggregate_type="read_model",
                    aggregate_id="all",
                    scope_type="no_oa_bank_batch",
                    scope_key="all",
                    dedupe_key="no_oa_bank_batch.read_model.refresh:no_oa_bank_batch:all",
                    payload={"scope_type": "no_oa_bank_batch", "scope_key": "all", "source_version": 3},
                    attempts=1,
                    status="processing",
                    source_version=3,
                )
            )
        finally:
            app._no_oa_bank_batch_service.build_batches = original_build_batches

        self.assertEqual(
            result,
            {
                "scope_key": "all",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 3,
            },
        )
        self.assertEqual(queue_repository.completions, [])


if __name__ == "__main__":
    unittest.main()
