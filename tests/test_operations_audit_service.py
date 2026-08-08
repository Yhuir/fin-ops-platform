from __future__ import annotations

from datetime import UTC, datetime
import unittest

from fin_ops_platform.services.operations_audit_service import OperationsAuditService, PageAuditUnavailableError


class FakeOperationsAuditRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.history_rows: list[dict[str, object]] = []

    def list_operation_events(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(("history", kwargs))
        return list(self.history_rows)

    def get_operation_event(self, event_id: str) -> dict[str, object] | None:
        self.calls.append(("detail", {"event_id": event_id}))
        return next((row for row in self.history_rows if row["id"] == event_id), None)

    def audit_page(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("page", kwargs))
        return {"kind": "page"}

    def audit_system(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("system", kwargs))
        return {"kind": "system"}


class OperationsAuditServiceTests(unittest.TestCase):
    def test_delegates_page_audit_through_explicit_repository_contract(self) -> None:
        repository = FakeOperationsAuditRepository()
        service = OperationsAuditService(repository)

        self.assertEqual(
            service.audit_page(page_key="bank-details", tenant_id="tenant-a", sample_limit=30),
            {"kind": "page"},
        )
        self.assertEqual(
            repository.calls,
            [
                ("page", {"page_key": "bank-details", "tenant_id": "tenant-a", "sample_limit": 30}),
            ],
        )

    def test_system_page_uses_explicit_dashboard_projection_boundary(self) -> None:
        repository = FakeOperationsAuditRepository()
        dashboard_builder = lambda _connection: {"kind": "dashboard"}
        service = OperationsAuditService(repository, dashboard_payload_builder=dashboard_builder)

        self.assertEqual(
            service.audit_page(page_key="app-health-operations", tenant_id="tenant-a"),
            {"kind": "system"},
        )
        self.assertEqual(repository.calls[0][0], "system")
        self.assertEqual(repository.calls[0][1]["tenant_id"], "tenant-a")
        self.assertIs(repository.calls[0][1]["dashboard_payload_builder"], dashboard_builder)

    def test_system_page_without_dashboard_projection_fails_closed(self) -> None:
        repository = FakeOperationsAuditRepository()
        service = OperationsAuditService(repository)

        with self.assertRaisesRegex(PageAuditUnavailableError, "dashboard projection is unavailable"):
            service.audit_page(page_key="app-health-operations", tenant_id="tenant-a")

        self.assertEqual(repository.calls, [])

    def test_lists_operation_history_with_bounded_stable_cursor(self) -> None:
        repository = FakeOperationsAuditRepository()
        occurred_at = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        repository.history_rows = [
            {"id": f"10000000-0000-4000-8000-{index:012d}", "occurred_at": occurred_at}
            for index in range(1, 4)
        ]
        service = OperationsAuditService(repository)

        payload = service.list_operation_history(limit=2, actor_id=" YNSYLP005 ", search=" 关联 ")

        self.assertEqual(len(payload["rows"]), 2)
        self.assertEqual(payload["limit"], 2)
        self.assertEqual(
            payload["next_cursor"],
            "2026-08-09T12:00:00+00:00|10000000-0000-4000-8000-000000000002",
        )
        self.assertEqual(repository.calls[0][1]["limit"], 3)
        self.assertEqual(repository.calls[0][1]["actor_id"], "YNSYLP005")
        self.assertEqual(repository.calls[0][1]["search"], "关联")

    def test_rejects_invalid_history_cursor_date_and_event_id(self) -> None:
        service = OperationsAuditService(FakeOperationsAuditRepository())

        with self.assertRaisesRegex(ValueError, "cursor"):
            service.list_operation_history(cursor="not-a-cursor")
        with self.assertRaisesRegex(ValueError, "date"):
            service.list_operation_history(date_from="not-a-date")
        with self.assertRaises(ValueError):
            service.get_operation_history_event("not-an-id")


if __name__ == "__main__":
    unittest.main()
