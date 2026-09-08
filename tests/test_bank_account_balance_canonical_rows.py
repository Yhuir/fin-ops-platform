import unittest

from fin_ops_platform.services.bank_account_balance_canonical_rows import (
    BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL,
)


class BankAccountBalanceCanonicalRowsTests(unittest.TestCase):
    def test_account_identity_label_prefers_actual_account_number_and_consistent_metadata(self) -> None:
        sql = " ".join(BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL.split())

        self.assertIn("normalized_account_no, nullif(normalized_payload->>'imported_bank_last4'", sql)
        self.assertIn("right(normalized_account_no, 4) = right(normalized_payload->>'imported_bank_last4', 4)", sql)
        self.assertIn("order by account_identity, label_consistent desc, trade_time_sort desc", sql)
