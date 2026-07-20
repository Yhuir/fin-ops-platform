from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_relation_read_model_refresh import (
    WORKBENCH_RELATION_REFRESH_EVENT_TYPE,
    WorkbenchRelationReadModelRefreshService,
)


class RecordingProjectionBuilder:
    def __init__(self) -> None:
        self.full_scopes: list[str] = []
        self.full_force_refresh: list[bool] = []
        self.partial_calls: list[dict[str, object]] = []
        self.relation_delta_calls: list[dict[str, object]] = []

    def rebuild_workbench_relation_read_model_scope(
        self,
        scope_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        self.full_scopes.append(scope_key)
        self.full_force_refresh.append(force_refresh)
        return {"scope_key": scope_key, "row_count": 100}

    def list_workbench_relation_scope_shards(self, scope_key: str) -> list[str]:
        return ["2026-04", "2026-05"] if scope_key == "all" else [scope_key]

    def rebuild_workbench_relation_read_model_rows(self, scope_key: str, *, row_ids: list[str]) -> dict[str, object]:
        self.partial_calls.append({"scope_key": scope_key, "row_ids": list(row_ids)})
        return {"scope_key": scope_key, "row_count": len(row_ids), "partial": True}

    def rebuild_workbench_relation_read_model_relation_delta(
        self,
        scope_key: str,
        *,
        row_ids: list[str],
    ) -> dict[str, object]:
        self.relation_delta_calls.append({"scope_key": scope_key, "row_ids": list(row_ids)})
        return {"scope_key": scope_key, "row_count": len(row_ids), "partial": True, "relation_delta": True}


class RecordingQueueRepository:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []
        self.enqueued: list[dict[str, object]] = []

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


def _event(payload: dict[str, object], *, scope_key: str = "2026-05") -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type=WORKBENCH_RELATION_REFRESH_EVENT_TYPE,
        aggregate_type="read_model",
        aggregate_id=scope_key,
        scope_type="workbench_relation",
        scope_key=scope_key,
        dedupe_key=None,
        payload=payload,
        attempts=0,
        status="processing",
    )


class WorkbenchRelationReadModelRefreshServiceTests(unittest.TestCase):
    def test_handle_runtime_event_uses_partial_row_refresh_when_event_has_row_ids(self) -> None:
        projection_builder = RecordingProjectionBuilder()
        queue_repository = RecordingQueueRepository()
        service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue_repository,
        )

        result = service.handle_runtime_event(
            _event(
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-05",
                    "metadata": {"row_ids": ["txn-1", "oa-1", "txn-1"]},
                }
            )
        )

        self.assertTrue(result["partial"])
        self.assertEqual(projection_builder.full_scopes, [])
        self.assertEqual(
            projection_builder.partial_calls,
            [{"scope_key": "2026-05", "row_ids": ["txn-1", "oa-1"]}],
        )
        self.assertEqual(
            queue_repository.completed,
            [{"tenant_id": "default", "scope_type": "workbench_relation", "scope_key": "2026-05"}],
        )

    def test_handle_runtime_event_uses_full_scope_refresh_without_row_ids(self) -> None:
        projection_builder = RecordingProjectionBuilder()
        service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=RecordingQueueRepository(),
        )

        result = service.handle_runtime_event(
            _event({"scope_type": "workbench_relation", "scope_key": "2026-05"})
        )

        self.assertEqual(result["row_count"], 100)
        self.assertEqual(projection_builder.full_scopes, ["2026-05"])
        self.assertEqual(projection_builder.full_force_refresh, [False])
        self.assertEqual(projection_builder.partial_calls, [])

    def test_handle_runtime_event_uses_explicit_relation_delta_contract(self) -> None:
        projection_builder = RecordingProjectionBuilder()
        queue_repository = RecordingQueueRepository()
        service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue_repository,
        )

        result = service.handle_runtime_event(
            _event(
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-05",
                    "metadata": {
                        "row_ids": ["txn-1"],
                        "relation_deltas": {
                            "case-1": {"status": "active", "row_ids": ["oa-1", "txn-1"]}
                        },
                    },
                }
            )
        )

        self.assertTrue(result["relation_delta"])
        self.assertEqual(
            projection_builder.relation_delta_calls,
            [{"scope_key": "2026-05", "row_ids": ["txn-1", "oa-1"]}],
        )
        self.assertEqual(projection_builder.partial_calls, [])
        self.assertEqual(projection_builder.full_scopes, [])

    def test_force_refresh_bypasses_partial_hint_and_source_version_skip(self) -> None:
        projection_builder = RecordingProjectionBuilder()
        service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=RecordingQueueRepository(),
        )

        service.handle_runtime_event(
            _event(
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-05",
                    "metadata": {
                        "row_ids": ["txn-1"],
                        "relation_deltas": {"case-1": {"row_ids": ["txn-1"]}},
                        "force_refresh": True,
                    },
                }
            )
        )

        self.assertEqual(projection_builder.partial_calls, [])
        self.assertEqual(projection_builder.relation_delta_calls, [])
        self.assertEqual(projection_builder.full_scopes, ["2026-05"])
        self.assertEqual(projection_builder.full_force_refresh, [True])

    def test_all_force_refresh_propagates_to_every_month_shard(self) -> None:
        projection_builder = RecordingProjectionBuilder()
        queue_repository = RecordingQueueRepository()
        service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue_repository,
        )

        result = service.handle_runtime_event(
            _event(
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "all",
                    "metadata": {"force_refresh": True},
                },
                scope_key="all",
            )
        )

        self.assertEqual(result["enqueued_scope_keys"], ["2026-04", "2026-05"])
        self.assertEqual(
            queue_repository.enqueued,
            [
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-04",
                    "reason": "workbench_relation_month_shard",
                    "metadata": {"force_refresh": True},
                },
                {
                    "scope_type": "workbench_relation",
                    "scope_key": "2026-05",
                    "reason": "workbench_relation_month_shard",
                    "metadata": {"force_refresh": True},
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
