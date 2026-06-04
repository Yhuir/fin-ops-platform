from __future__ import annotations

import unittest

from fin_ops_platform.services.invoice_lifecycle_read_model_refresh import (
    INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE,
    InvoiceLifecycleReadModelRefreshService,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[str] = []
        self.empty: list[str] = []

    def rebuild_invoice_lifecycle_read_model_scope(self, scope_key: str) -> dict[str, object]:
        self.rebuilt.append(scope_key)
        return {"scope_key": scope_key, "row_count": 3}

    def list_invoice_lifecycle_scope_shards(self, scope_key: str) -> list[str]:
        return ["2026-01", "2026-02"] if scope_key == "all" else []

    def mark_invoice_lifecycle_scope_empty(self, scope_key: str) -> None:
        self.empty.append(scope_key)


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str, source_version=None) -> None:
        self.completed.append((scope_type, scope_key))


class InvoiceLifecycleReadModelRefreshTests(unittest.TestCase):
    def test_rebuilds_month_scope_and_completes_dirty_scope(self) -> None:
        builder = FakeProjectionBuilder()
        queue = QueueRecorder()
        service = InvoiceLifecycleReadModelRefreshService(projection_builder=builder, queue_repository=queue)

        result = service.handle_runtime_event(_event("2026-01"))

        self.assertEqual(result, {"scope_key": "2026-01", "row_count": 3})
        self.assertEqual(builder.rebuilt, ["2026-01"])
        self.assertEqual(queue.completed, [("invoice_lifecycle", "2026-01")])

    def test_expands_all_scope_into_month_shards(self) -> None:
        builder = FakeProjectionBuilder()
        queue = QueueRecorder()
        service = InvoiceLifecycleReadModelRefreshService(projection_builder=builder, queue_repository=queue)

        result = service.handle_runtime_event(_event("all"))

        self.assertEqual(result["enqueued_scope_keys"], ["2026-01", "2026-02"])
        self.assertEqual(queue.refreshes, [
            ("invoice_lifecycle", "2026-01", "invoice_lifecycle_month_shard"),
            ("invoice_lifecycle", "2026-02", "invoice_lifecycle_month_shard"),
        ])
        self.assertEqual(queue.completed, [("invoice_lifecycle", "all")])


def _event(scope_key: str) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id=f"evt-{scope_key}",
        tenant_id="default",
        event_type=INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE,
        aggregate_type="invoice_lifecycle",
        aggregate_id=scope_key,
        scope_type="invoice_lifecycle",
        scope_key=scope_key,
        dedupe_key=None,
        payload={},
        attempts=0,
        status="pending",
    )


if __name__ == "__main__":
    unittest.main()
