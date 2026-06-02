from __future__ import annotations

import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.no_oa_bank_batch_read_model_refresh import NoOaBankBatchReadModelRefreshService
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class NoOaBankBatchReadModelRefreshTests(unittest.TestCase):
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
