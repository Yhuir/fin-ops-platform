from __future__ import annotations

import unittest

from fin_ops_platform.services.operations_audit_service import OperationsAuditService


class FakeOperationsAuditRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def audit_input_invoice_usage(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("input", kwargs))
        return {"kind": "input"}

    def audit_output_invoice_collection(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("output", kwargs))
        return {"kind": "output"}

    def audit_page_business(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("page", kwargs))
        return {"kind": "page"}


class OperationsAuditServiceTests(unittest.TestCase):
    def test_delegates_each_audit_through_explicit_repository_contract(self) -> None:
        repository = FakeOperationsAuditRepository()
        service = OperationsAuditService(repository)

        self.assertEqual(service.audit_input_invoice_usage(tenant_id="tenant-a", sample_limit=10), {"kind": "input"})
        self.assertEqual(service.audit_output_invoice_collection(tenant_id="tenant-a", sample_limit=20), {"kind": "output"})
        self.assertEqual(
            service.audit_page_business(domain_key="bank_details", tenant_id="tenant-a", sample_limit=30),
            {"kind": "page"},
        )
        self.assertEqual(
            repository.calls,
            [
                ("input", {"tenant_id": "tenant-a", "sample_limit": 10}),
                ("output", {"tenant_id": "tenant-a", "sample_limit": 20}),
                ("page", {"domain_key": "bank_details", "tenant_id": "tenant-a", "sample_limit": 30}),
            ],
        )


if __name__ == "__main__":
    unittest.main()
