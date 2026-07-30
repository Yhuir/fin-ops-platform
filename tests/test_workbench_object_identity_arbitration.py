from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_object_identity_arbitration import WorkbenchObjectIdentityArbitrationService


class WorkbenchObjectIdentityArbitrationTests(unittest.TestCase):
    def test_strong_invoice_identity_suppresses_unpaired_alias_when_any_alias_is_paired(self) -> None:
        rows_by_id = {
            "oa-att-inv-1": {
                "id": "oa-att-inv-1",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "paired",
                "case_id": "CASE-1",
                "digital_invoice_no": "265320000000992",
                "invoice_no": "265320000000992",
                "total_with_tax": "300.00",
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "source_kind": "invoice",
                "status": "unpaired",
                "digital_invoice_no": "265320000000992",
                "invoice_no": "265320000000992",
                "total_with_tax": "300.00",
            },
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], ["invoice-1"])
        self.assertNotIn("invoice-1", rows_by_id)
        self.assertEqual(rows_by_id["oa-att-inv-1"]["identity_alias_rows"]["invoice"][0]["id"], "invoice-1")
        self.assertEqual(rows_by_id["oa-att-inv-1"]["object_identity_kind"], "digital_invoice_no")

    def test_weak_invoice_tax_identity_does_not_suppress_unpaired_rows(self) -> None:
        rows_by_id = {
            "invoice-left": {
                "id": "invoice-left",
                "type": "invoice",
                "source_kind": "invoice",
                "status": "paired",
                "seller_tax_no": "SELLER-TAX",
                "buyer_tax_no": "BUYER-TAX",
                "invoice_date": "2026-01-20",
                "total_with_tax": "300.00",
            },
            "invoice-right": {
                "id": "invoice-right",
                "type": "invoice",
                "source_kind": "invoice",
                "status": "unpaired",
                "seller_tax_no": "SELLER-TAX",
                "buyer_tax_no": "BUYER-TAX",
                "invoice_date": "2026-01-20",
                "total_with_tax": "300.00",
            },
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], [])
        self.assertIn("invoice-left", rows_by_id)
        self.assertIn("invoice-right", rows_by_id)
        self.assertEqual(rows_by_id["invoice-left"]["object_identity_kind"], "tax_amount_fingerprint")

    def test_etc_batch_summaries_with_the_same_invoice_count_keep_distinct_batch_identity(self) -> None:
        rows_by_id = {
            row_id: {
                "id": row_id,
                "type": "invoice",
                "source_kind": "etc_invoice_summary",
                "status": "paired",
                "invoice_code": batch_id,
                "invoice_no": "ETC发票 68 张",
                "digital_invoice_no": "ETC发票 68 张",
            }
            for batch_id, row_id in (
                ("etc_20260720_001", "etc-summary-etc_20260720_001"),
                ("etc_batch_0045", "etc-summary-etc_batch_0045"),
            )
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], [])
        self.assertEqual(set(rows_by_id), {"etc-summary-etc_20260720_001", "etc-summary-etc_batch_0045"})
        self.assertEqual(
            rows_by_id["etc-summary-etc_20260720_001"]["object_identity_key"],
            "etc-summary-etc_20260720_001",
        )
        self.assertEqual(
            rows_by_id["etc-summary-etc_20260720_001"]["object_identity_kind"],
            "etc_batch_summary_id",
        )

    def test_stable_bank_identity_is_audited_but_not_collapsed_when_all_rows_are_unpaired(self) -> None:
        rows_by_id = {
            "bank-left": self._bank_row("bank-left"),
            "bank-right": self._bank_row("bank-right"),
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], [])
        self.assertIn("bank-left", rows_by_id)
        self.assertIn("bank-right", rows_by_id)
        self.assertEqual(rows_by_id["bank-left"]["identity_warnings"][0]["code"], "duplicate_stable_identity")

    def test_stable_bank_identity_suppresses_unpaired_alias_when_one_alias_is_paired(self) -> None:
        rows_by_id = {
            "bank-left": {
                **self._bank_row("bank-left"),
                "status": "paired",
                "case_id": "CASE-BANK",
            },
            "bank-right": self._bank_row("bank-right"),
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], ["bank-right"])
        self.assertNotIn("bank-right", rows_by_id)
        self.assertEqual(rows_by_id["bank-left"]["identity_alias_rows"]["bank"][0]["id"], "bank-right")

    def test_nonformal_auto_close_override_does_not_own_strong_invoice_identity(self) -> None:
        rows_by_id = {
            "oa-att-inv-1": {
                "id": "oa-att-inv-1",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "unpaired",
                "auto_close_suppressed": True,
                "digital_invoice_no": "265320000000993",
                "total_with_tax": "300.00",
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "source_kind": "invoice",
                "status": "unpaired",
                "digital_invoice_no": "265320000000993",
                "total_with_tax": "300.00",
            },
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], ["oa-att-inv-1"])
        self.assertEqual(set(rows_by_id), {"invoice-1"})
        self.assertEqual(rows_by_id["invoice-1"]["identity_alias_rows"]["invoice"][0]["id"], "oa-att-inv-1")

    def test_oa_rows_keep_row_id_identity_without_weak_business_field_merge(self) -> None:
        rows_by_id = {
            "oa-left": {
                "id": "oa-left",
                "type": "oa",
                "source_kind": "oa",
                "amount": "300.00",
                "applicant": "张三",
                "project_name": "同一项目",
            },
            "oa-right": {
                "id": "oa-right",
                "type": "oa",
                "source_kind": "oa",
                "amount": "300.00",
                "applicant": "张三",
                "project_name": "同一项目",
            },
        }

        result = WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)

        self.assertEqual(result["suppressed_row_ids"], [])
        self.assertEqual(rows_by_id["oa-left"]["object_identity_key"], "oa-left")
        self.assertEqual(rows_by_id["oa-right"]["object_identity_key"], "oa-right")

    @staticmethod
    def _bank_row(row_id: str) -> dict[str, str]:
        return {
            "id": row_id,
            "type": "bank",
            "source_kind": "bank_transaction",
            "status": "unpaired",
            "account_no": "622200008106",
            "trade_time": "2026-02-12 15:08:35",
            "txn_direction": "outflow",
            "amount": "300.00",
            "counterparty_name": "云南元大工程咨询有限责任公司",
        }


if __name__ == "__main__":
    unittest.main()
