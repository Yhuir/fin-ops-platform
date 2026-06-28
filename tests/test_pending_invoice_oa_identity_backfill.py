from __future__ import annotations

import unittest

from fin_ops_platform.services.pending_invoice_oa_identity_backfill import PendingInvoiceOaIdentityBackfillService


class FakeRepository:
    def __init__(self) -> None:
        self.fetch_all_calls: list[str] = []

    def invalid_read_model_rows(self) -> list[dict[str, object]]:
        return [
            {
                "row_id": "txn-1",
                "direction": "expense",
                "scope_key": "expense:all:2026-05",
                "oa_payload": {"primary": {"id": "candidate:bad-oa"}},
            }
        ]

    def invalid_relation_rows(self) -> list[dict[str, object]]:
        return [{"case_id": "case-invalid", "row_ids": ["candidate:bad-oa"], "row_types": ["oa"]}]

    def missing_oa_relation_rows(self) -> list[dict[str, object]]:
        return [{"case_id": "candidate:missing-oa", "row_ids": ["txn-1", "inv-1"], "row_types": ["bank", "invoice"]}]


class PendingInvoiceOaIdentityBackfillTests(unittest.TestCase):
    def test_inspects_invalid_oa_identity_without_enqueuing_pending_scopes(self) -> None:
        repository = FakeRepository()
        queue = object()
        service = PendingInvoiceOaIdentityBackfillService(repository=repository, queue_repository=queue)

        report = service.inspect()

        self.assertEqual(report["invalid_read_model_rows"][0]["oa_id"], "candidate:bad-oa")
        self.assertTrue(report["manual_repair_required"])
        self.assertEqual(report["affected_scope_keys"], ["expense:all:2026-05", "expense:all"])


if __name__ == "__main__":
    unittest.main()
