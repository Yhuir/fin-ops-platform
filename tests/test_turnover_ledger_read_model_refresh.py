from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.turnover_ledger_read_model_refresh import TurnoverLedgerReadModelRefreshService


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[tuple[str, object]] = []

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, object]:
        self.rebuilt.append((scope_key, source_version))
        return {"scope_key": scope_key, "row_count": 2}


class FakeQueue:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))


class TurnoverLedgerReadModelRefreshServiceTests(unittest.TestCase):
    def test_worker_handler_rebuilds_scope_and_completes_dirty_scope(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = TurnoverLedgerReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="turnover_ledger.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-03",
            scope_type="turnover_ledger",
            scope_key="2026-03",
            dedupe_key=None,
            payload={"scope_type": "turnover_ledger", "scope_key": "2026-03", "source_version": 7},
            attempts=0,
            status="pending",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "2026-03", "row_count": 2})
        self.assertEqual(builder.rebuilt, [("2026-03", 7)])
        self.assertEqual(
            queue.completed,
            [{"tenant_id": "default", "scope_type": "turnover_ledger", "scope_key": "2026-03", "source_version": 7}],
        )

    def test_worker_handler_rejects_wrong_event_type(self) -> None:
        service = TurnoverLedgerReadModelRefreshService(projection_builder=FakeProjectionBuilder())
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="bank_detail.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-03",
            scope_type="turnover_ledger",
            scope_key="2026-03",
            dedupe_key=None,
            payload={},
            attempts=0,
            status="pending",
        )

        with self.assertRaises(ValueError):
            service.handle_runtime_event(event)


if __name__ == "__main__":
    unittest.main()
