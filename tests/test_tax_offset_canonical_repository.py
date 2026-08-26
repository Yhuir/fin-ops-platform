from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.services.postgres_repositories.tax_offset import (
    PostgresTaxOffsetCanonicalRepository,
)


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.queries: list[str] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def execute(self, sql: str, _params: object = None) -> None:
        self.commands.append(" ".join(sql.split()).lower())

    def fetch_all(self, sql: str, _params: object = None) -> list[dict[str, object]]:
        normalized = " ".join(sql.split()).lower()
        self.queries.append(normalized)
        if "from app.invoices" in normalized:
            return [
                {
                    "row_id": "output-1",
                    "invoice_type": "销项发票",
                    "invoice_no": "OUT-1",
                    "invoice_date": "2026-05-01",
                    "buyer_name": "客户",
                    "tax_amount": "13.00",
                    "total_with_tax": "113.00",
                    "tax_rate": "13%",
                    "raw_payload": {},
                },
                {
                    "row_id": "input-1",
                    "invoice_type": "进项发票",
                    "invoice_no": "IN-1",
                    "invoice_date": "2026-05-02",
                    "seller_name": "供应商一",
                    "tax_amount": "6.00",
                    "total_with_tax": "106.00",
                    "tax_rate": "6%",
                    "raw_payload": {"risk_level": "低"},
                },
                {
                    "row_id": "input-2",
                    "invoice_type": "进项发票",
                    "invoice_no": "IN-2",
                    "invoice_date": "2026-05-03",
                    "seller_name": "供应商二",
                    "tax_amount": "3.00",
                    "total_with_tax": "103.00",
                    "tax_rate": "3%",
                    "raw_payload": {},
                },
            ]
        if "from app.tax_certified_import_records" in normalized:
            return [
                {
                    "certified_unique_key": "certified-1",
                    "invoice_no": "IN-1",
                    "invoice_date": "2026-05-02",
                    "seller_name": "供应商一",
                    "amount": "100.00",
                    "tax_amount": "6.00",
                    "status": "已认证",
                    "raw_payload": {},
                }
            ]
        raise AssertionError(f"unexpected query: {normalized}")

    def fetch_one(self, sql: str, _params: object = None) -> dict[str, object] | None:
        normalized = " ".join(sql.split()).lower()
        self.queries.append(normalized)
        if "from app.tax_offset_plans" in normalized:
            return {
                "selected_output_ids": ["output-1"],
                "selected_input_ids": ["input-2", "missing-input"],
            }
        raise AssertionError(f"unexpected query: {normalized}")


class TaxOffsetCanonicalRepositoryTests(unittest.TestCase):
    def test_loads_rows_summary_statistics_and_saved_plan_in_one_fixed_snapshot(self) -> None:
        connection = FakeConnection()

        payload = PostgresTaxOffsetCanonicalRepository(connection).load_month_payload("2026-05")

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            connection.commands,
            ["set transaction isolation level repeatable read read only"],
        )
        self.assertEqual(len(connection.queries), 3)
        self.assertTrue(all("workbench" not in query and "read_model." not in query for query in connection.queries))
        self.assertEqual([row["id"] for row in payload["output_items"]], ["output-1"])
        self.assertEqual([row["id"] for row in payload["input_plan_items"]], ["input-1", "input-2"])
        self.assertEqual(payload["locked_certified_input_ids"], ["input-1"])
        self.assertEqual(payload["default_selected_output_ids"], ["output-1"])
        self.assertEqual(payload["default_selected_input_ids"], ["input-2"])
        self.assertEqual(payload["summary"]["output_tax"], "13.00")
        self.assertEqual(payload["summary"]["certified_input_tax"], "6.00")
        self.assertEqual(payload["summary"]["planned_input_tax"], "3.00")
        self.assertEqual(payload["statistics"]["input_invoice_count"], 2)
        self.assertEqual(payload["statistics"]["output_invoice_count"], 1)
        self.assertEqual(
            payload["statistics"],
            {"input_invoice_count": 2, "output_invoice_count": 1},
        )
        self.assertRegex(payload["canonical_snapshot_version"], r"^tax-offset-v1:[0-9a-f]{64}$")

    def test_rejects_invalid_month_before_opening_a_snapshot(self) -> None:
        connection = FakeConnection()

        with self.assertRaisesRegex(ValueError, "month must be YYYY-MM"):
            PostgresTaxOffsetCanonicalRepository(connection).load_month_payload("202605")

        self.assertEqual(connection.transaction_count, 0)
        self.assertEqual(connection.queries, [])


if __name__ == "__main__":
    unittest.main()
