"""Original financial amounts are independent of purpose and relation amounts."""
import unittest

from fin_ops_platform.services.bank_transaction_unit import original_bank_display_totals


class BankOriginalDisplayTests(unittest.TestCase):
    def test_parent_identity_deduplicates_amount_and_parts_without_merging_equal_parents(self):
        parts = [
            {"id": "principal", "category_code": "loan", "amount": "1000000.00"},
            {"id": "interest", "category_code": "interest", "amount": "1497.22"},
        ]
        first = {"parent_row_id": "bank-one", "original_amount": "1001497.22", "bank_split_parts": parts}
        second = {"parent_row_id": "bank-two", "original_amount": "1001497.22", "bank_split_parts": []}
        result = original_bank_display_totals([
            {**first, "amount": "1000000.00"}, {**first, "amount": "1497.22"}, second,
        ])
        self.assertEqual(result["original_amount"], "2002994.44")
        self.assertEqual(result["original_transaction_count"], 2)
        self.assertEqual(result["bank_split_parts"], parts)
        self.assertNotIn("amount", result)

    def test_empty_result_has_no_fabricated_zero_bank_transaction(self):
        self.assertEqual(original_bank_display_totals([]), {
            "original_amount": "", "original_transaction_count": 0, "bank_split_parts": [],
        })

    def test_unsplit_amounts_use_decimal_precision(self):
        self.assertEqual(original_bank_display_totals([
            {"parent_row_id": "a", "original_amount": "0.10"},
            {"parent_row_id": "b", "original_amount": "0.20"},
        ])["original_amount"], "0.30")

    def test_missing_original_amount_does_not_fall_back_to_business_amount(self):
        with self.assertRaises(KeyError):
            original_bank_display_totals([{"parent_row_id": "a", "amount": "1497.22"}])
