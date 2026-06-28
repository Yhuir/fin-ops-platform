from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_matching_row_provider import WorkbenchMatchingRowProvider


class FakeConnection:
    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        assert "app.app_settings" in sql
        return {"settings_payload": {"bank_account_mappings": [{"last4": "1234", "bank_name": "测试银行"}]}}

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.bank_transactions" in sql:
            return [
                {
                    "row_id": "bank-1",
                    "account_no": "00001234",
                    "account_name": "基本户",
                    "txn_direction": "支出",
                    "counterparty_name_raw": "供应商",
                    "amount": "88.00",
                    "txn_date": "2026-03-02",
                    "trade_time": "2026-03-02T09:00:00",
                    "summary": "付款",
                    "remark": "备注",
                    "project_id": "p1",
                    "raw_payload": {"摘要": "付款"},
                }
            ]
        if "from app.invoices" in sql:
            return [
                {
                    "row_id": "invoice-1",
                    "invoice_type": "专票",
                    "invoice_no": "001",
                    "invoice_code": "A",
                    "digital_invoice_no": "",
                    "invoice_date": "2026-03-03",
                    "counterparty_name": "供应商",
                    "seller_name": "供应商",
                    "seller_tax_no": "tax-s",
                    "buyer_name": "本公司",
                    "buyer_tax_no": "tax-b",
                    "amount": "80.00",
                    "tax_rate": "0.06",
                    "tax_amount": "4.80",
                    "total_with_tax": "84.80",
                    "status": "active",
                    "workbench_visibility": "visible",
                    "tags": [],
                    "source_links": [],
                    "raw_payload": {},
                }
            ]
        return []


class FakeOaQueryService:
    def get_workbench(self, month: str) -> None:
        self.month = month

    def list_record_snapshots(self) -> list[dict[str, object]]:
        return [{"id": "oa-1", "_month": self.month, "type": "oa", "amount": "84.80"}]

    def serialize_row(self, row: dict[str, object]) -> dict[str, object]:
        return dict(row)


class WorkbenchMatchingRowProviderTests(unittest.TestCase):
    def test_rows_for_scope_uses_direct_fact_sources(self) -> None:
        rows = WorkbenchMatchingRowProvider(
            connection=FakeConnection(),
            oa_query_service=FakeOaQueryService(),
        ).rows_for_scope("2026-03")

        self.assertEqual(rows["oa_rows"][0]["id"], "oa-1")
        self.assertIn("测试银行", rows["bank_rows"][0]["payment_account_label"])
        self.assertEqual(rows["invoice_rows"][0]["id"], "invoice-1")


if __name__ == "__main__":
    unittest.main()
