from __future__ import annotations

import unittest

from fin_ops_platform.services.operations_audit_service import OperationsAuditService, PageAuditUnavailableError


class FakeOperationsAuditRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

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


if __name__ == "__main__":
    unittest.main()
