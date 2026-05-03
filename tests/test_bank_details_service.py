from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.bank_details_service import BankDetailsService


class _ImportServiceStub:
    def __init__(self, transactions: list[BankTransaction]) -> None:
        self._transactions = transactions

    def list_transactions(self) -> list[BankTransaction]:
        return list(self._transactions)


class BankDetailsServiceTests(unittest.TestCase):
    def test_accounts_group_by_bank_and_last4_with_latest_balances(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    BankTransaction(
                        id="txn-1",
                        account_no="6222000011116386",
                        txn_direction=TransactionDirection.OUTFLOW,
                        counterparty_name_raw="供应商A",
                        amount=Decimal("100.00"),
                        signed_amount=Decimal("-100.00"),
                        txn_date="2026-04-01",
                        trade_time="2026-04-01 09:00:00",
                        balance=Decimal("900.00"),
                        imported_bank_name="工商银行",
                        imported_bank_last4="6386",
                    ),
                    BankTransaction(
                        id="txn-2",
                        account_no="6222000011116386",
                        txn_direction=TransactionDirection.INFLOW,
                        counterparty_name_raw="客户A",
                        amount=Decimal("50.00"),
                        signed_amount=Decimal("50.00"),
                        txn_date="2026-04-03",
                        trade_time="2026-04-03 09:00:00",
                        balance=Decimal("950.00"),
                        imported_bank_name="工商银行",
                        imported_bank_last4="6386",
                    ),
                    BankTransaction(
                        id="txn-3",
                        account_no="6222000011111410",
                        txn_direction=TransactionDirection.OUTFLOW,
                        counterparty_name_raw="供应商B",
                        amount=Decimal("20.00"),
                        signed_amount=Decimal("-20.00"),
                        txn_date="2026-04-02",
                        trade_time="2026-04-02 09:00:00",
                        balance=None,
                        imported_bank_name="工商银行",
                        imported_bank_last4="1410",
                    ),
                ]
            )
        )

        payload = service.list_accounts(date_from="2026-04-03", date_to="2026-04-03")

        self.assertEqual(len(payload["accounts"]), 2)
        account_6386 = next(account for account in payload["accounts"] if account["account_last4"] == "6386")
        account_1410 = next(account for account in payload["accounts"] if account["account_last4"] == "1410")
        self.assertEqual(account_6386["latest_balance"], "950.00")
        self.assertEqual(account_6386["transaction_count"], 1)
        self.assertFalse(account_1410["has_balance"])
        self.assertEqual(account_1410["transaction_count"], 0)
        self.assertEqual(payload["total_balance"], "950.00")
        self.assertEqual(payload["balance_account_count"], 1)
        self.assertEqual(payload["missing_balance_account_count"], 1)

    def test_transactions_filter_by_account_and_date_with_direction_label(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    BankTransaction(
                        id="txn-income",
                        account_no="6222000011116386",
                        txn_direction=TransactionDirection.INFLOW,
                        counterparty_name_raw="客户A",
                        amount=Decimal("50.00"),
                        signed_amount=Decimal("50.00"),
                        txn_date="2026-04-03",
                        trade_time="2026-04-03 09:00:00",
                        balance=Decimal("950.00"),
                        summary="回款",
                        remark="货款",
                        imported_bank_name="工商银行",
                        imported_bank_last4="6386",
                    ),
                    BankTransaction(
                        id="txn-expense",
                        account_no="6222000011116386",
                        txn_direction=TransactionDirection.OUTFLOW,
                        counterparty_name_raw="供应商A",
                        amount=Decimal("100.00"),
                        signed_amount=Decimal("-100.00"),
                        txn_date="2026-03-31",
                        trade_time="2026-03-31 09:00:00",
                        imported_bank_name="工商银行",
                        imported_bank_last4="6386",
                    ),
                ]
            )
        )

        payload = service.list_transactions(
            account_key="工商银行:6386",
            date_from="2026-04-01",
            date_to="2026-04-30",
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], "txn-income")
        self.assertEqual(payload["rows"][0]["direction_label"], "收")
        self.assertEqual(payload["rows"][0]["amount"], "50.00")
        self.assertEqual(payload["rows"][0]["balance"], "950.00")


if __name__ == "__main__":
    unittest.main()
