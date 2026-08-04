import unittest

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


class _CaptureConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> int:
        self.calls.append((sql, params))
        return 1


class PostgresCoreRepositoryTests(unittest.TestCase):
    def test_submitted_etc_overlap_casts_json_audit_values_to_text(self) -> None:
        connection = _CaptureConnection()

        updated = PostgresCoreRepository(connection).repair_submitted_etc_invoice_overlap(
            invoice_id="invoice-1",
            etc_invoice_id="etc-invoice-1",
            etc_batch_id="batch-1",
            reason="repair",
            operator="ops",
        )

        sql, params = connection.calls[0]
        self.assertEqual(updated, 1)
        self.assertIn("'source_id', %s::text", sql)
        self.assertIn("'batch_id', coalesce(%s::text, '')", sql)
        self.assertIn("'repair_reason', %s::text", sql)
        self.assertIn("'operator', %s::text", sql)
        self.assertEqual(
            params,
            (
                "etc-invoice-1",
                "etc-invoice-1",
                "batch-1",
                "repair",
                "ops",
                "etc-invoice-1",
                "invoice-1",
            ),
        )

    def test_save_invoice_drops_weak_fingerprint_when_source_unique_key_exists(self) -> None:
        connection = _CaptureConnection()
        repository = PostgresCoreRepository(connection)

        repository._save_invoice(
            connection,
            {
                "id": "inv_existing_etc_stale",
                "invoice_type": "input",
                "invoice_no": "26537911470300077680",
                "digital_invoice_no": "26537911470300077680",
                "source_unique_key": "26537911470300077680",
                "data_fingerprint": "invoice:昆明新机场高速公路建设发展有限公司:2026-03-31:9.22",
                "invoice_date": "2026-03-31",
                "counterparty": {"id": "cp_etc", "name": "昆明新机场高速公路建设发展有限公司"},
                "seller_name": "昆明新机场高速公路建设发展有限公司",
                "amount": "9.22",
                "signed_amount": "9.22",
                "total_with_tax": "9.22",
            },
        )

        self.assertEqual(len(connection.calls), 1)
        sql, params = connection.calls[0]
        self.assertIn("on conflict (source_unique_key) where source_unique_key is not null", sql)
        self.assertEqual(params[5], "26537911470300077680")
        self.assertIsNone(params[6])

    def test_save_invoice_without_canonical_identity_keeps_legacy_id_conflict_target(self) -> None:
        connection = _CaptureConnection()

        PostgresCoreRepository(connection)._save_invoice(
            connection,
            {
                "id": "inv_without_canonical_identity",
                "invoice_type": "input",
                "invoice_no": "legacy-invoice-no",
                "invoice_date": "2026-03-31",
                "counterparty": {"id": "cp_legacy", "name": "测试销方"},
                "amount": "9.22",
                "signed_amount": "9.22",
            },
        )

        sql, _params = connection.calls[0]
        self.assertIn("on conflict (legacy_mongo_id)", sql)


if __name__ == "__main__":
    unittest.main()
