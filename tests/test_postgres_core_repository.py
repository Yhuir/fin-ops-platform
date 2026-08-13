import unittest
from decimal import Decimal

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

    def test_save_invoice_drops_weak_fingerprint_and_keeps_canonical_legacy_id_owner(self) -> None:
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
        self.assertIn("on conflict (legacy_mongo_id)", sql)
        self.assertNotIn("on conflict (source_unique_key)", sql)
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

    def test_etc_metadata_update_does_not_replace_formal_source_owner(self) -> None:
        connection = _CaptureConnection()

        PostgresCoreRepository(connection)._update_invoice_etc_metadata(
            connection,
            {
                "id": "invoice-1",
                "etc_invoice_id": "etc-invoice-1",
                "source_batch_id": "etc_import_batch_0018",
                "source_links": [
                    {
                        "source_type": "etc_invoice_import",
                        "source_id": "etc-invoice-1",
                        "batch_id": "etc_import_batch_0018",
                    }
                ],
            },
        )

        sql, params = connection.calls[0]
        self.assertNotIn("legacy_source_batch_id =", sql)
        self.assertNotIn("etc_import_batch_0018", params)

    def test_invoice_read_restores_all_merge_fields_from_normalized_payload(self) -> None:
        invoice = PostgresCoreRepository(_CaptureConnection())._invoice_from_row(
            {
                "legacy_id": "inv_imported_0700",
                "invoice_type": "input",
                "invoice_no": "26539150014000401220",
                "counterparty_name": "中国铁路昆明局集团有限公司",
                "amount": "145.00",
                "signed_amount": "145.00",
                "written_off_amount": "0",
                "status": "pending",
                "raw_payload": {
                    "normalized_payload": {
                        "tax_classification_code": "3010101",
                        "specific_business_type": "铁路客运",
                        "taxable_item_name": "客运服务",
                        "specification_model": "G2842",
                        "unit": "张",
                        "quantity": "1",
                        "unit_price": "145.00",
                        "invoice_source": "OA附件解析",
                        "invoice_kind": "铁路电子客票",
                        "is_positive_invoice": "是",
                        "risk_level": "正常",
                        "issuer": "中国铁路昆明局集团有限公司",
                        "remark": "昆明至大理",
                        "project_id": "project-1",
                        "department_id": "department-1",
                    }
                },
            }
        )

        self.assertEqual(invoice.tax_classification_code, "3010101")
        self.assertEqual(invoice.specific_business_type, "铁路客运")
        self.assertEqual(invoice.taxable_item_name, "客运服务")
        self.assertEqual(invoice.specification_model, "G2842")
        self.assertEqual(invoice.unit, "张")
        self.assertEqual(invoice.quantity, Decimal("1"))
        self.assertEqual(invoice.unit_price, Decimal("145.00"))
        self.assertEqual(invoice.invoice_source, "OA附件解析")
        self.assertEqual(invoice.invoice_kind, "铁路电子客票")
        self.assertEqual(invoice.is_positive_invoice, "是")
        self.assertEqual(invoice.risk_level, "正常")
        self.assertEqual(invoice.issuer, "中国铁路昆明局集团有限公司")
        self.assertEqual(invoice.remark, "昆明至大理")
        self.assertEqual(invoice.project_id, "project-1")
        self.assertEqual(invoice.department_id, "department-1")


if __name__ == "__main__":
    unittest.main()
