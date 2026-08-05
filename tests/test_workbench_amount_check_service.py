import unittest

from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService


class WorkbenchAmountCheckServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchAmountCheckService()

    def test_flags_only_isolated_oa_total_when_bank_and_invoice_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [self._invoice_row("90")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], ["oa_total"])

    def test_flags_only_isolated_invoice_total_when_oa_and_bank_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [self._invoice_row("90")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], ["invoice_total"])

    def test_flags_both_comparable_totals_when_invoice_missing(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(result["mismatch_fields"], ["oa_total", "bank_total"])

    def test_etc_batch_oa_bank_mismatch_without_invoice_requires_note(self) -> None:
        oa_row = self._oa_row("100")
        oa_row["source"] = "etc_batch"
        oa_row["etc_batch_id"] = "etc_20260503_001"

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("90")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(result["mismatch_fields"], ["oa_total", "bank_total"])

    def test_flags_all_totals_when_three_amounts_all_differ(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [self._invoice_row("80")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(
            result["mismatch_fields"],
            ["oa_total", "bank_total", "invoice_total"],
        )

    def test_matched_when_all_three_totals_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [self._invoice_row("100")],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], [])
        self.assertEqual(result["oa_total"], "100.00")
        self.assertEqual(result["bank_total"], "100.00")
        self.assertEqual(result["invoice_total"], "100.00")

    def test_unknown_invoice_type_is_not_defaulted_to_payment_direction(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [
                    {
                        "type": "invoice",
                        "id": "inv-unknown",
                        "invoice_type": "电子普通发票",
                        "total_with_tax": "100",
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["invoice_total"], "100.00")

    def test_missing_total_remains_null_when_persistable(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [],
            }
        )

        self.assertEqual(result["oa_total"], "100.00")
        self.assertEqual(result["bank_total"], "100.00")
        self.assertIsNone(result["invoice_total"])

    def test_payment_relation_uses_payment_bank_total_when_bank_rows_include_receipts(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("300000")],
                "bank": [
                    self._bank_row("300000"),
                    self._bank_income_row("100000"),
                    self._bank_income_row("200000"),
                ],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["direction"], "payment")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], [])
        self.assertEqual(result["oa_total"], "300000.00")
        self.assertEqual(result["bank_total"], "300000.00")
        self.assertEqual(result["oa_amount"], "300000.00")
        self.assertEqual(result["bank_amount"], "300000.00")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_oa_reconciliation_amount_overrides_header_amount_for_preview_check(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("2308.02", reconciliation_amount="2038.02")],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_explicit_reconciliation_amount_wins_over_legacy_detail_mismatch_fields(self) -> None:
        oa_row = self._oa_row("2308.02", reconciliation_amount="2038.02")
        oa_row["detail_fields"] = {
            "金额来源": "主表总金额",
            "明细金额合计": "1999.99",
            "金额差异": "主表总金额 2308.02；明细合计 1999.99；差异 308.03",
        }

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_legacy_oa_detail_sum_is_used_when_header_amount_has_recorded_mismatch(self) -> None:
        oa_row = self._oa_row("2308.02")
        oa_row["detail_fields"] = {
            "金额来源": "主表总金额",
            "明细金额合计": "2038.02",
            "金额差异": "主表总金额 2308.02；明细合计 2038.02；差异 270.00",
        }

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_oa_invoice_anomaly_uses_exact_cent_totals_across_all_rows(self) -> None:
        anomaly = self.service.oa_invoice_anomaly(
            {
                "oa": [{**self._oa_row("1079.87"), "id": "oa-1"}],
                "invoice": [
                    {**self._invoice_row("290.00"), "id": "invoice-1"},
                    {**self._invoice_row("789.86"), "id": "invoice-2"},
                ],
            },
            relation_id="CASE-1",
        )

        self.assertIsNotNone(anomaly)
        assert anomaly is not None
        self.assertEqual(anomaly["code"], "oa_invoice_anomaly")
        self.assertEqual(len(anomaly["items"]), 1)
        item = anomaly["items"][0]
        self.assertEqual(item["label"], "金额不一致")
        self.assertEqual(item["oa_total"], "1079.87")
        self.assertEqual(item["invoice_total"], "1079.86")
        self.assertEqual(item["amount_delta"], "0.01")
        self.assertEqual(len(anomaly["fingerprint"]), 64)

    def test_oa_invoice_anomaly_is_absent_for_exact_match_or_missing_side(self) -> None:
        self.assertIsNone(
            self.service.oa_invoice_anomaly(
                {
                    "oa": [{**self._oa_row("76.80"), "id": "oa-1"}],
                    "invoice": [
                        {**self._invoice_row("29"), "id": "invoice-1"},
                        {**self._invoice_row("47.8"), "id": "invoice-2"},
                    ],
                },
                relation_id="CASE-1",
            )
        )

    def test_expense_items_compare_all_explicitly_bound_invoices_per_item(self) -> None:
        oa_row = {
            **self._oa_row("695.00"),
            "id": "oa-1",
            "expense_items": [
                {"id": "item-290", "amount": "290.00", "attachment_file_count": "2"},
                {"id": "item-405", "amount": "405.00", "attachment_file_count": "2"},
            ],
        }
        invoices = [
            {**self._invoice_row("145.00"), "id": "invoice-145-a", "source_expense_item_id": "item-290"},
            {**self._invoice_row("145.00"), "id": "invoice-145-b", "source_expense_item_id": "item-290"},
            {**self._invoice_row("350.00"), "id": "invoice-350", "source_expense_item_id": "item-405"},
            {**self._invoice_row("55.00"), "id": "invoice-55", "source_expense_item_id": "item-405"},
        ]

        self.assertIsNone(
            self.service.oa_invoice_anomaly(
                {"oa": [oa_row], "invoice": invoices},
                relation_id="CASE-ITEMS",
            )
        )

    def test_expense_item_mismatch_is_one_comparison_unit_not_one_per_invoice(self) -> None:
        anomaly = self.service.oa_invoice_anomaly(
            {
                "oa": [{
                    **self._oa_row("290.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-290", "amount": "290.00", "attachment_file_count": "2"}],
                }],
                "invoice": [
                    {**self._invoice_row("145.00"), "id": "invoice-1", "source_expense_item_id": "item-290"},
                    {**self._invoice_row("144.99"), "id": "invoice-2", "source_expense_item_id": "item-290"},
                ],
            },
            relation_id="CASE-ITEM-MISMATCH",
        )

        assert anomaly is not None
        self.assertEqual(len(anomaly["items"]), 1)
        self.assertEqual(anomaly["items"][0]["code"], "oa_invoice_amount_mismatch")
        self.assertEqual(anomaly["items"][0]["invoice_row_ids"], ["invoice-1", "invoice-2"])
        self.assertEqual(anomaly["items"][0]["amount_delta"], "0.01")

    def test_uploaded_expense_item_without_parsed_invoice_is_missing_anomaly(self) -> None:
        anomaly = self.service.oa_invoice_anomaly(
            {
                "oa": [{
                    **self._oa_row("38.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-38", "amount": "38.00", "attachment_file_count": "1"}],
                }],
                "invoice": [],
            },
            relation_id="CASE-MISSING",
        )

        assert anomaly is not None
        self.assertEqual(len(anomaly["items"]), 1)
        item = anomaly["items"][0]
        self.assertEqual(item["code"], "oa_invoice_attachment_missing")
        self.assertEqual(item["label"], "OA发票附件缺失")
        self.assertEqual(item["source_expense_item_id"], "item-38")
        self.assertEqual(item["attachment_file_count"], 1)
        self.assertEqual(item["invoice_row_ids"], [])
        self.assertIsNone(
            self.service.oa_invoice_anomaly(
                {"oa": [{**self._oa_row("76.80"), "id": "oa-1"}], "invoice": []},
                relation_id="CASE-1",
            )
        )
        self.assertIsNone(
            self.service.oa_invoice_anomaly(
                {
                    "oa": [{**self._oa_row("76.80"), "id": "oa-1"}],
                    "invoice": [
                        {**self._invoice_row("29.00"), "id": "invoice-1"},
                        {"type": "invoice", "id": "invoice-without-amount"},
                    ],
                },
                relation_id="CASE-1",
            )
        )

    @staticmethod
    def _oa_row(amount: str, *, reconciliation_amount: str | None = None) -> dict[str, str]:
        row = {
            "type": "oa",
            "apply_type": "付款",
            "amount": amount,
        }
        if reconciliation_amount is not None:
            row["reconciliation_amount"] = reconciliation_amount
        return row

    @staticmethod
    def _bank_row(amount: str) -> dict[str, str]:
        return {
            "type": "bank",
            "debit_amount": amount,
        }

    @staticmethod
    def _bank_income_row(amount: str) -> dict[str, str]:
        return {
            "type": "bank",
            "credit_amount": amount,
        }

    @staticmethod
    def _invoice_row(amount: str) -> dict[str, str]:
        return {
            "type": "invoice",
            "invoice_type": "input",
            "total_with_tax": amount,
        }


if __name__ == "__main__":
    unittest.main()
