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

    @staticmethod
    def _oa_row(amount: str) -> dict[str, str]:
        return {
            "type": "oa",
            "apply_type": "付款",
            "amount": amount,
        }

    @staticmethod
    def _bank_row(amount: str) -> dict[str, str]:
        return {
            "type": "bank",
            "debit_amount": amount,
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
