from __future__ import annotations

from datetime import UTC, datetime
import unittest

from fin_ops_platform.tools import retired_projection_event_audit as audit


class FakeConnection:
    def __init__(self, rows=None) -> None:
        self.rows = list(rows or [])
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...]):
        self.calls.append((sql, params))
        return list(self.rows)


class RetiredProjectionEventAuditTests(unittest.TestCase):
    def test_clean_window_passes(self) -> None:
        connection = FakeConnection()

        report = audit.audit_retired_projection_events(connection)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["retired_projection_event_count"], 0)
        self.assertIsNone(report["error"])

    def test_any_retired_event_fails(self) -> None:
        connection = FakeConnection(
            [
                {
                    "event_id": "event-1",
                    "event_type": "legacy.read_model.refresh",
                    "event_status": "done",
                }
            ]
        )

        report = audit.audit_retired_projection_events(connection)

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["retired_projection_event_count"], 1)
        self.assertEqual(report["error"], "forbidden_retired_projection_event_detected")

    def test_exact_receipt_ids_are_the_causal_filter(self) -> None:
        connection = FakeConnection()

        audit.recent_retired_projection_events_since(
            connection,
            tenant_id="default",
            started_at=datetime(2026, 8, 15, tzinfo=UTC),
            limit=20,
            event_ids=["event-1", "event-2"],
        )

        sql, params = connection.calls[0]
        self.assertIn("e.id::text = any(%s)", sql)
        self.assertNotIn("e.created_at >= %s", sql)
        self.assertEqual(params[0:2], ("default", audit.RETIRED_EVENT_PATTERN))
        self.assertEqual(params[2], ["event-1", "event-2"])

    def test_committed_workbench_receipt_is_validated(self) -> None:
        connection = FakeConnection(
            [
                {
                    "status": "committed",
                    "outbox_event_ids": ["event-1"],
                    "response_payload": {"ok": True},
                }
            ]
        )

        evidence = audit.workbench_idempotency_evidence(
            connection,
            tenant_id="default",
            idempotency_key="request-1",
        )

        self.assertEqual(evidence["outbox_event_ids"], ["event-1"])
        self.assertEqual(evidence["response_payload"], {"ok": True})


if __name__ == "__main__":
    unittest.main()
