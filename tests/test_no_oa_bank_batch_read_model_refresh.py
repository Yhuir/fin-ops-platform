from __future__ import annotations

import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.no_oa_bank_batch_read_model_refresh import NoOaBankBatchReadModelRefreshService
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class NoOaBankBatchReadModelRefreshTests(unittest.TestCase):
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
