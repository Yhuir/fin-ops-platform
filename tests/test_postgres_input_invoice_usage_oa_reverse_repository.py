from __future__ import annotations

from datetime import UTC, datetime
import unittest

from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InputInvoiceUsageOaReverseBatch,
    InputInvoiceUsageOaReverseStatus,
    _batch_to_storage,
)
from fin_ops_platform.services.postgres_repositories.input_invoice_usage_oa_reverse import (
    PostgresInputInvoiceUsageOaReverseBatchRepository,
)


class RecordingConnection:
    def __init__(self) -> None:
        self.fetches: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_rows: list[dict[str, object]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetches.append((" ".join(sql.split()), params))
        return list(self.fetch_all_rows)


class PostgresInputInvoiceUsageOaReverseBatchRepositoryTests(unittest.TestCase):
    def test_list_batches_by_status_reads_raw_payload_in_updated_order(self) -> None:
        batch = InputInvoiceUsageOaReverseBatch(
            batch_id="batch-history",
            status=InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value,
            version=3,
            target_applicant_code="zhou_jieying",
            target_applicant_name="周洁莹",
            invoice_ids=["inv-1"],
            preview_id="preview-1",
            preview_hash="hash-1",
            preview_summary={"totalWithTax": "100.00"},
            invoice_display_rows=[{"invoiceNo": "1001", "sellerName": "供应商", "totalWithTax": "100.00"}],
            updated_at=datetime(2026, 6, 10, tzinfo=UTC),
        )
        connection = RecordingConnection()
        connection.fetch_all_rows = [{"raw_payload": _batch_to_storage(batch)}]
        repository = PostgresInputInvoiceUsageOaReverseBatchRepository(connection)

        batches = repository.list_batches_by_status([InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value], limit=10)

        sql, params = connection.fetches[0]
        self.assertIn("from app.input_invoice_usage_oa_reverse_batches", sql)
        self.assertIn("where status = any(%s)", sql)
        self.assertIn("order by updated_at desc", sql)
        self.assertEqual(params[0], [InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value])
        self.assertEqual(params[1], 10)
        self.assertEqual(batches[0].batch_id, "batch-history")
        self.assertEqual(batches[0].status, InputInvoiceUsageOaReverseStatus.SUBMITTED_CONFIRMED.value)


if __name__ == "__main__":
    unittest.main()
