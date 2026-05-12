from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService


class _ImportServiceStub:
    def __init__(self, transactions: list[BankTransaction]) -> None:
        self._transactions = transactions

    def list_transactions(self) -> list[BankTransaction]:
        return list(self._transactions)


class BankDetailsServiceTests(unittest.TestCase):
    def _transaction(
        self,
        *,
        transaction_id: str,
        trade_time: str,
        account_last4: str = "6386",
        bank_name: str = "工商银行",
    ) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no=f"622200001111{account_last4}",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="供应商A",
            amount=Decimal("100.00"),
            signed_amount=Decimal("-100.00"),
            txn_date=trade_time[:10],
            trade_time=trade_time,
            balance=Decimal("900.00"),
            imported_bank_name=bank_name,
            imported_bank_last4=account_last4,
        )

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

    def test_accounts_transaction_count_respects_date_range(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id="txn-before",
                        trade_time="2026-03-31 09:00:00",
                        account_last4="6386",
                    ),
                    self._transaction(
                        transaction_id="txn-in-range-1",
                        trade_time="2026-04-01 09:00:00",
                        account_last4="6386",
                    ),
                    self._transaction(
                        transaction_id="txn-in-range-2",
                        trade_time="2026-04-30 09:00:00",
                        account_last4="6386",
                    ),
                    self._transaction(
                        transaction_id="txn-after",
                        trade_time="2026-05-01 09:00:00",
                        account_last4="6386",
                    ),
                    self._transaction(
                        transaction_id="txn-other-account",
                        trade_time="2026-03-30 09:00:00",
                        account_last4="1410",
                    ),
                ]
            )
        )

        payload = service.list_accounts(date_from="2026-04-01", date_to="2026-04-30")

        account_6386 = next(account for account in payload["accounts"] if account["account_last4"] == "6386")
        account_1410 = next(account for account in payload["accounts"] if account["account_last4"] == "1410")
        self.assertEqual(account_6386["transaction_count"], 2)
        self.assertEqual(account_1410["transaction_count"], 0)

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

    def test_transactions_returns_requested_page_total_and_page_size(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id=f"txn-{index}",
                        trade_time=f"2026-04-0{index} 09:00:00",
                    )
                    for index in range(1, 6)
                ]
            )
        )

        payload = service.list_transactions(account_key="工商银行:6386", page=2, page_size=2)

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-3", "txn-2"])
        self.assertEqual(payload["pagination"], {"page": 2, "page_size": 2, "total": 5})

    def test_transactions_page_size_is_capped_at_500(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id=f"txn-{index:03d}",
                        trade_time=f"2026-04-01 09:{index // 60:02d}:{index % 60:02d}",
                    )
                    for index in range(501)
                ]
            )
        )

        payload = service.list_transactions(account_key="工商银行:6386", page=1, page_size=999)

        self.assertEqual(len(payload["rows"]), 500)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 500, "total": 501})

    def test_transactions_include_categories_and_full_query_range_category_counts(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-newest",
                trade_time="2026-04-03 09:00:00",
                account_last4="6386",
            ),
            self._transaction(
                transaction_id="txn-middle",
                trade_time="2026-04-02 09:00:00",
                account_last4="6386",
            ),
            self._transaction(
                transaction_id="txn-oldest",
                trade_time="2026-04-01 09:00:00",
                account_last4="6386",
            ),
        ]
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [
                {"transaction_id": "txn-newest", "category_code": "borrow_in_company_pending_repayment", "expected_version": 0},
                {"transaction_id": "txn-middle", "category_code": "business_warranty_pending_collection", "expected_version": 0},
            ],
            actor="YNSYLP005",
        )
        service = BankDetailsService(_ImportServiceStub(transactions), category_service=category_service)

        payload = service.list_transactions(
            account_key="工商银行:6386",
            date_from="2026-04-01",
            date_to="2026-04-03",
            page=1,
            page_size=1,
        )

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-newest"])
        self.assertEqual(payload["rows"][0]["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(payload["rows"][0]["category_label"], "公司暂借款：待还款")
        self.assertEqual(payload["rows"][0]["category_path"], ["借入", "公司往来款", "待还款"])
        self.assertEqual(payload["rows"][0]["category_version"], 1)
        self.assertEqual(payload["category_counts"]["borrow_in_company_pending_repayment"], 1)
        self.assertEqual(payload["category_counts"]["business_warranty_pending_collection"], 1)
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)


if __name__ == "__main__":
    unittest.main()
