from __future__ import annotations

import unittest

from fin_ops_platform.services.pending_invoice_oa_identity_backfill import PendingInvoiceOaIdentityBackfillService


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[str] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append(normalized)
        if "from read_model.pending_invoice_rows" in normalized:
            return [
                {
                    "row_id": "txn-1",
                    "direction": "expense",
                    "scope_key": "expense:all:2026-05",
                    "oa_payload": {"primary": {"id": "candidate:bad-oa"}},
                }
            ]
        if "where status = 'active'" in normalized and "row_id !~ '^oa-'" in normalized:
            return [{"case_id": "case-invalid", "row_ids": ["candidate:bad-oa"], "row_types": ["oa"]}]
        if "case_id like 'candidate:%'" in normalized:
            return [{"case_id": "candidate:missing-oa", "row_ids": ["txn-1", "inv-1"], "row_types": ["bank", "invoice"]}]
        return []


class QueueRecorder:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class PendingInvoiceOaIdentityBackfillTests(unittest.TestCase):
    def test_inspects_invalid_oa_identity_and_enqueues_existing_pending_scopes(self) -> None:
        connection = FakeConnection()
        queue = QueueRecorder()
        service = PendingInvoiceOaIdentityBackfillService(connection=connection, queue_repository=queue)

        report = service.inspect()
        enqueued = service.enqueue_affected_scopes(reason="test_backfill")

        self.assertEqual(report["invalid_read_model_rows"][0]["oa_id"], "candidate:bad-oa")
        self.assertTrue(report["manual_repair_required"])
        self.assertIn("expense:all:2026-05", enqueued)
        self.assertIn(("pending_invoice", "expense:all:2026-05", "test_backfill"), queue.enqueued)
        self.assertIn(("pending_invoice", "income:cash_income", "test_backfill"), queue.enqueued)


if __name__ == "__main__":
    unittest.main()
