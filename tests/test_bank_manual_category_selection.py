from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_category_selection import validate_manual_assignment_rule
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryValidationError


class ManualCategorySelectionTests(unittest.TestCase):
    def validate(self, selection, rule=None):
        validate_manual_assignment_rule(
            selection=selection,
            rule=rule or {"direction": "expense", "output_primary_label": "费用", "output_sub_label": "手续费"},
            direction="expense", transaction_id="bank-1",
        )

    def test_code_only_and_current_path_are_valid(self):
        self.validate({"category_code": "fee"})
        self.validate({"category_code": "fee", "category_label_path": ["费用", "手续费"]})

    def test_changed_path_and_invented_third_label_are_rejected(self):
        for path in (["费用", "旧名称"], ["费用", "手续费", "公司往来"]):
            with self.subTest(path=path), self.assertRaises(BankTransactionCategoryValidationError):
                self.validate({"category_code": "fee", "category_label_path": path})

    def test_external_turnover_keeps_legitimate_third_level_choices(self):
        self.validate(
            {"category_code": "external", "category_third_label": "公司往来", "category_label_path": ["外部往来款付款", "借出款", "公司往来"]},
            {"direction": "expense", "output_primary_label": "外部往来款付款", "output_sub_label": "借出款"},
        )

    def test_conflicting_primary_and_path_are_rejected(self):
        with self.assertRaises(BankTransactionCategoryValidationError):
            self.validate({"category_primary_label": "货款", "category_label_path": ["费用", "手续费"]})
