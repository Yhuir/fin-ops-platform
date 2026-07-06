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
        self.partial_calls: list[dict[str, object]] = []

    def rebuild_workbench_relation_read_model_scope(self, scope_key: str) -> dict[str, object]:
        self.full_scopes.append(scope_key)
        return {"scope_key": scope_key, "row_count": 100}

    def rebuild_workbench_relation_read_model_rows(self, scope_key: str, *, row_ids: list[str]) -> dict[str, object]:
        self.partial_calls.append({"scope_key": scope_key, "row_ids": list(row_ids)})
        return {"scope_key": scope_key, "row_count": len(row_ids), "partial": True}


class RecordingQueueRepository:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))


def _event(payload: dict[str, object]) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type=WORKBENCH_RELATION_REFRESH_EVENT_TYPE,
        aggregate_type="read_model",
        aggregate_id="2026-05",
        scope_type="workbench_relation",
        scope_key="2026-05",
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
        self.assertEqual(projection_builder.partial_calls, [])


if __name__ == "__main__":
    unittest.main()
