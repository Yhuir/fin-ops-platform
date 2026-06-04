from __future__ import annotations

import unittest

from fin_ops_platform.services.invoice_lifecycle_read_facade import InvoiceLifecycleReadFacade


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class FakeLifecycleRepository:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload
        self.subject_calls: list[dict[str, object]] = []
        self.month_calls: list[dict[str, object]] = []

    def get_invoice_lifecycle_rows_by_subject_ids(
        self,
        subject_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.subject_calls.append({"subject_ids": list(subject_ids), "tenant_id": tenant_id})
        return self.payload

    def list_invoice_lifecycle_rows(
        self,
        *,
        month: str,
        subject_types: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        self.month_calls.append({"month": month, "subject_types": list(subject_types or []), "tenant_id": tenant_id})
        return self.payload


class InvoiceLifecycleReadFacadeTests(unittest.TestCase):
    def test_get_by_subject_ids_returns_fresh_lifecycle_rows(self) -> None:
        repository = FakeLifecycleRepository(
            {
                "read_model_status": "fresh",
                "rows": [
                    {
                        "subject_id": "inv-1",
                        "subject_type": "input_invoice",
                        "payment_status": {"code": "paid", "label": "已付款"},
                        "certification_status": {"code": "certified", "label": "已认证"},
                    }
                ],
                "source_versions": {"invoice_lifecycle_policy_schema_version": 1},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        facade = InvoiceLifecycleReadFacade(read_model_repository=repository)

        payload = facade.get_by_subject_ids(["inv-1"], require_fresh=True, reason="unit_test")

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(payload["rows"][0]["payment_status"]["code"], "paid")
        self.assertEqual(repository.subject_calls[0]["subject_ids"], ["inv-1"])

    def test_non_fresh_result_enqueues_invoice_lifecycle_refresh(self) -> None:
        repository = FakeLifecycleRepository(
            {
                "read_model_status": "missing",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
                "stale_reasons": ["read_model_missing"],
            }
        )
        queue = QueueRecorder()
        facade = InvoiceLifecycleReadFacade(read_model_repository=repository, queue_repository=queue)

        payload = facade.get_by_subject_ids(["inv-1"], require_fresh=True, reason="pending_invoice_projection")

        self.assertEqual(payload["status"], "missing")
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [("invoice_lifecycle", "2026-01", "pending_invoice_projection")])

    def test_list_by_month_passes_subject_type_filter(self) -> None:
        repository = FakeLifecycleRepository(
            {
                "read_model_status": "fresh",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": ["2026-01"],
            }
        )
        facade = InvoiceLifecycleReadFacade(read_model_repository=repository)

        payload = facade.list_by_month("2026-01", subject_types=["input_invoice", "bank_transaction"])

        self.assertEqual(payload["status"], "fresh")
        self.assertEqual(repository.month_calls[0]["subject_types"], ["input_invoice", "bank_transaction"])


if __name__ == "__main__":
    unittest.main()
