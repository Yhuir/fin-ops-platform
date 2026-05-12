from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha1
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService


class _ImportServiceStub:
    def __init__(self, transactions: list[BankTransaction]) -> None:
        self._transactions = list(transactions)

    def list_transactions(self) -> list[BankTransaction]:
        return list(self._transactions)


class _LedgerExtraServiceStub:
    def __init__(self, extras: dict[str, dict[str, object]]) -> None:
        self._extras = dict(extras)

    def get(self, relation_id: str) -> dict[str, object]:
        return dict(self._extras.get(relation_id, {}))


class TurnoverLedgerServiceTests(unittest.TestCase):
    def _transaction(
        self,
        transaction_id: str,
        *,
        direction: TransactionDirection,
        amount: str,
        counterparty: str,
        trade_time: str,
        summary: str = "",
        remark: str = "",
        bank_name: str = "建行",
        last4: str = "8106",
    ) -> BankTransaction:
        signed_amount = Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount)
        return BankTransaction(
            id=transaction_id,
            account_no=f"622200001111{last4}",
            txn_direction=direction,
            counterparty_name_raw=counterparty,
            amount=Decimal(amount),
            signed_amount=signed_amount,
            txn_date=trade_time[:10],
            trade_time=trade_time,
            pay_receive_time=trade_time,
            summary=summary,
            remark=remark,
            imported_bank_name=bank_name,
            imported_bank_last4=last4,
        )

    def _service(self) -> tuple[TurnoverLedgerService, BankTransactionCategoryService, TurnoverRelationService]:
        transactions = [
            self._transaction(
                "txn-borrow-in",
                direction=TransactionDirection.INFLOW,
                amount="200000.00",
                counterparty="梁希涛",
                trade_time="2026-02-04 13:23:17",
                summary="暂借款",
                remark="借入基本户",
            ),
            self._transaction(
                "txn-borrow-repaid",
                direction=TransactionDirection.OUTFLOW,
                amount="200000.00",
                counterparty="梁希涛",
                trade_time="2026-03-05 09:34:42",
                summary="还暂借款",
                remark="归还",
            ),
            self._transaction(
                "txn-business-open",
                direction=TransactionDirection.OUTFLOW,
                amount="5000.00",
                counterparty="昆明建设集团",
                trade_time="2026-03-06 10:00:00",
                summary="质保金",
                remark="项目A",
                bank_name="交行",
                last4="3847",
            ),
        ]
        import_service = _ImportServiceStub(transactions)
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id
            in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [
                {
                    "transaction_id": "txn-borrow-in",
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-borrow-repaid",
                    "category_code": "borrow_in_company_repaid",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-business-open",
                    "category_code": "business_warranty_pending_collection",
                    "expected_version": 0,
                },
            ],
            actor="YNSYLP005",
        )
        relation_service = TurnoverRelationService.from_snapshot(None)
        ledger_service = TurnoverLedgerService(
            import_service=import_service,
            category_service=category_service,
            relation_service=relation_service,
        )
        return ledger_service, category_service, relation_service

    def _relation_id(self, *row_ids: str) -> str:
        digest = sha1("|".join(sorted(row_ids)).encode("utf-8")).hexdigest()[:16]
        return f"turnover_rel_{digest}"

    def _grouped_service(self) -> TurnoverLedgerService:
        transactions = [
            self._transaction(
                "txn-mixed-borrow-in",
                direction=TransactionDirection.INFLOW,
                amount="9000.00",
                counterparty="云南路桥",
                trade_time="2026-01-01 09:00:00",
                summary="公司暂借款",
                remark="未还本金",
                bank_name="建行",
                last4="1001",
            ),
            self._transaction(
                "txn-mixed-borrow-out",
                direction=TransactionDirection.OUTFLOW,
                amount="8000.00",
                counterparty="云南路桥",
                trade_time="2026-01-16 09:00:00",
                summary="借出周转款",
                remark="待收回",
                bank_name="工行",
                last4="2002",
            ),
            self._transaction(
                "txn-business-no-rate",
                direction=TransactionDirection.OUTFLOW,
                amount="5000.00",
                counterparty="昆明建设集团",
                trade_time="2026-01-20 09:00:00",
                summary="质保金",
                remark="项目A",
                bank_name="交行",
                last4="3847",
            ),
        ]
        import_service = _ImportServiceStub(transactions)
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id
            in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [
                {
                    "transaction_id": "txn-mixed-borrow-in",
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-mixed-borrow-out",
                    "category_code": "borrow_out_company_lent",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-business-no-rate",
                    "category_code": "business_warranty_pending_collection",
                    "expected_version": 0,
                },
            ],
            actor="YNSYLP005",
        )
        relation_service = TurnoverRelationService.from_snapshot(None)
        extra_service = _LedgerExtraServiceStub(
            {
                self._relation_id("txn-mixed-borrow-in"): {
                    "interest_rate_type": "annual",
                    "interest_rate_value": "0.120000",
                    "interest_paid_amount": "10.00",
                    "interest_paid_date": "2026-01-25",
                    "interest_payment_method": "银行转账",
                    "note": "年息测试",
                },
                self._relation_id("txn-mixed-borrow-out"): {
                    "interest_rate_type": "monthly",
                    "interest_rate_value": "0.015000",
                    "interest_paid_amount": "0.00",
                    "interest_paid_date": None,
                    "interest_payment_method": "",
                    "note": "月息测试",
                },
            }
        )
        return TurnoverLedgerService(
            import_service=import_service,
            category_service=category_service,
            relation_service=relation_service,
            extra_service=extra_service,
            today_provider=lambda: date(2026, 1, 31),
        )

    def _single_grouped_service(
        self,
        *,
        transaction_id: str,
        direction: TransactionDirection,
        category_code: str,
        counterparty: str = "云南路桥",
    ) -> TurnoverLedgerService:
        transaction = self._transaction(
            transaction_id,
            direction=direction,
            amount="7000.00",
            counterparty=counterparty,
            trade_time="2026-01-10 09:00:00",
            summary="单笔方向测试",
        )
        import_service = _ImportServiceStub([transaction])
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda candidate_id: candidate_id == transaction.id,
        )
        category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_id,
                    "category_code": category_code,
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )
        return TurnoverLedgerService(
            import_service=import_service,
            category_service=category_service,
            relation_service=TurnoverRelationService.from_snapshot(None),
            today_provider=lambda: date(2026, 1, 31),
        )

    def _lot_grouped_service(self, *, repayment_amount: str, today: date) -> TurnoverLedgerService:
        transactions = [
            self._transaction(
                "txn-jia-principal-200k",
                direction=TransactionDirection.INFLOW,
                amount="200000.00",
                counterparty="贾小花",
                trade_time="2026-02-04 13:20:48",
                summary="个人暂借款",
                remark="待还款",
                bank_name="建行",
                last4="1001",
            ),
            self._transaction(
                "txn-jia-principal-100k",
                direction=TransactionDirection.INFLOW,
                amount="100000.00",
                counterparty="贾小花",
                trade_time="2026-02-04 17:07:45",
                summary="个人暂借款",
                remark="待还款",
                bank_name="建行",
                last4="1001",
            ),
            self._transaction(
                "txn-jia-repayment",
                direction=TransactionDirection.OUTFLOW,
                amount=repayment_amount,
                counterparty="贾小花",
                trade_time="2026-03-04 15:24:58",
                summary="还个人暂借款",
                remark="已还款",
                bank_name="建行",
                last4="1001",
            ),
        ]
        import_service = _ImportServiceStub(transactions)
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id
            in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [
                {
                    "transaction_id": "txn-jia-principal-200k",
                    "category_code": "borrow_in_personal_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-jia-principal-100k",
                    "category_code": "borrow_in_personal_pending_repayment",
                    "expected_version": 0,
                },
                {
                    "transaction_id": "txn-jia-repayment",
                    "category_code": "borrow_in_personal_repaid",
                    "expected_version": 0,
                },
            ],
            actor="YNSYLP005",
        )
        relation_id = self._relation_id(
            "txn-jia-principal-200k",
            "txn-jia-principal-100k",
            "txn-jia-repayment",
        )
        extra_service = _LedgerExtraServiceStub(
            {
                relation_id: {
                    "interest_rate_type": "annual",
                    "interest_rate_value": "0.120000",
                    "interest_paid_amount": "0.00",
                    "interest_paid_date": None,
                    "interest_payment_method": "",
                    "note": "贾小花批次计息",
                }
            }
        )
        return TurnoverLedgerService(
            import_service=import_service,
            category_service=category_service,
            relation_service=TurnoverRelationService.from_snapshot(None),
            extra_service=extra_service,
            today_provider=lambda: today,
        )

    def test_payload_summarizes_only_tagged_turnover_rows(self) -> None:
        ledger_service, _, _ = self._service()

        payload = ledger_service.list_ledger()

        self.assertEqual(payload["summary"]["repaid_amount"], "200000.00")
        self.assertEqual(payload["summary"]["pending_collection_amount"], "5000.00")
        self.assertEqual(payload["summary"]["closed_amount"], "200000.00")
        self.assertEqual(payload["summary"]["suggested_count"], 1)
        self.assertEqual(payload["summary"]["row_count"], 2)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 2})
        company_summary = next(
            summary for summary in payload["family_summaries"] if summary["family"] == "company"
        )
        business_summary = next(
            summary for summary in payload["family_summaries"] if summary["family"] == "business"
        )
        self.assertEqual(company_summary["label"], "公司往来")
        self.assertEqual(company_summary["closed_amount"], "200000.00")
        self.assertEqual(business_summary["pending_amount"], "5000.00")
        closed_row = next(
            row for row in payload["rows"] if row["counterparty_name"] == "梁希涛"
        )
        self.assertEqual(closed_row["family"], "company")
        self.assertEqual(closed_row["status"], "deterministic")
        self.assertEqual(closed_row["row_tone"], "success")
        self.assertEqual(closed_row["bank_account_labels"], ["建行 8106"])
        self.assertIn("暂借款", closed_row["summary_text"])
        self.assertTrue(closed_row["sync_to_workbench"])

    def test_family_and_status_filters_are_applied_before_pagination(self) -> None:
        ledger_service, _, _ = self._service()

        payload = ledger_service.list_ledger(family="business", status="suggested", page=1, page_size=10)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["family"], "business")
        self.assertEqual(payload["rows"][0]["status"], "suggested")
        self.assertEqual(payload["rows"][0]["counterparty_name"], "昆明建设集团")

    def test_grouped_ledger_groups_same_counterparty_family_and_summarizes_pending_amounts(self) -> None:
        ledger_service = self._grouped_service()

        payload = ledger_service.list_grouped_ledger(family="company", page=1, page_size=10)

        self.assertEqual(payload["filters"], {"family": "company", "status": None})
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 10, "total": 1})
        group = payload["groups"][0]
        self.assertEqual(group["counterparty_name"], "云南路桥")
        self.assertEqual(group["family"], "company")
        self.assertEqual(group["family_label"], "公司往来")
        self.assertEqual(group["row_span"], 3)
        self.assertEqual(group["pending_direction"], "mixed")
        self.assertEqual(group["pending_direction_label"], "混合余额")
        self.assertEqual(group["pending_amount"], "17000.00")
        self.assertEqual(len(group["lot_rows"]), 2)
        self.assertEqual(group["rows"][0], group["summary_row"])

    def test_grouped_ledger_calculates_annual_interest_and_borrow_in_directions(self) -> None:
        ledger_service = self._grouped_service()

        payload = ledger_service.list_grouped_ledger(family="company")

        group = payload["groups"][0]
        row = next(
            row for row in group["lot_rows"] if row["bank_row_ids"] == ["txn-mixed-borrow-in"]
        )
        self.assertEqual(row["row_kind"], "allocation_lot")
        self.assertEqual(row["borrow_amount"], "9000.00")
        self.assertEqual(row["borrow_date"], "2026-01-01")
        self.assertEqual(row["borrow_direction"], "income")
        self.assertEqual(row["repayment_amount"], "0.00")
        self.assertIsNone(row["repayment_date"])
        self.assertEqual(row["repayment_direction"], "expense")
        self.assertEqual(row["interest_rate_type"], "annual")
        self.assertEqual(row["interest_rate_value"], "0.120000")
        self.assertEqual(row["interest_paid_amount"], "10.00")
        self.assertEqual(row["interest_paid_date"], "2026-01-25")
        self.assertEqual(row["interest_payment_method"], "银行转账")
        self.assertEqual(row["note"], "年息测试")
        self.assertEqual(row["loan_days"], 30)
        self.assertEqual(row["accrued_interest"], "88.77")

    def test_grouped_ledger_uses_repayment_direction_for_pure_borrow_in_group(self) -> None:
        ledger_service = self._single_grouped_service(
            transaction_id="txn-pure-borrow-in",
            direction=TransactionDirection.INFLOW,
            category_code="borrow_in_company_pending_repayment",
        )

        payload = ledger_service.list_grouped_ledger(family="company")

        group = payload["groups"][0]
        self.assertEqual(group["pending_direction"], "repayment")
        self.assertEqual(group["pending_direction_label"], "待还款")
        self.assertEqual(group["pending_amount"], "7000.00")

    def test_grouped_ledger_calculates_monthly_interest_and_borrow_out_directions(self) -> None:
        ledger_service = self._grouped_service()

        payload = ledger_service.list_grouped_ledger(family="company")

        group = payload["groups"][0]
        row = next(
            row for row in group["lot_rows"] if row["bank_row_ids"] == ["txn-mixed-borrow-out"]
        )
        self.assertEqual(row["row_kind"], "allocation_lot")
        self.assertEqual(row["borrow_amount"], "8000.00")
        self.assertEqual(row["borrow_date"], "2026-01-16")
        self.assertEqual(row["borrow_direction"], "expense")
        self.assertEqual(row["repayment_amount"], "0.00")
        self.assertIsNone(row["repayment_date"])
        self.assertEqual(row["repayment_direction"], "income")
        self.assertEqual(row["interest_rate_type"], "monthly")
        self.assertEqual(row["interest_rate_value"], "0.015000")
        self.assertEqual(row["loan_days"], 15)
        self.assertEqual(row["accrued_interest"], "60.00")

    def test_grouped_ledger_uses_collection_direction_for_pure_borrow_out_group(self) -> None:
        ledger_service = self._single_grouped_service(
            transaction_id="txn-pure-borrow-out",
            direction=TransactionDirection.OUTFLOW,
            category_code="borrow_out_company_lent",
        )

        payload = ledger_service.list_grouped_ledger(family="company")

        group = payload["groups"][0]
        self.assertEqual(group["pending_direction"], "collection")
        self.assertEqual(group["pending_direction_label"], "待收款")
        self.assertEqual(group["pending_amount"], "7000.00")

    def test_grouped_ledger_returns_stable_defaults_when_rate_is_missing(self) -> None:
        ledger_service = self._grouped_service()

        payload = ledger_service.list_grouped_ledger(family="business")

        group = payload["groups"][0]
        self.assertEqual(group["pending_direction"], "collection")
        self.assertEqual(group["pending_direction_label"], "待收款")
        self.assertEqual(group["pending_amount"], "5000.00")
        row = group["lot_rows"][0]
        self.assertEqual(row["interest_rate_type"], "none")
        self.assertEqual(row["interest_rate_value"], "0.000000")
        self.assertEqual(row["interest_paid_amount"], "0.00")
        self.assertEqual(row["loan_days"], 11)
        self.assertEqual(row["accrued_interest"], "0.00")
        self.assertEqual(row["borrow_direction"], "expense")
        self.assertEqual(row["repayment_direction"], "income")

    def test_grouped_ledger_keeps_legacy_list_ledger_compatible(self) -> None:
        ledger_service = self._grouped_service()

        payload = ledger_service.list_ledger(family="company", page=1, page_size=1)

        self.assertIn("rows", payload)
        self.assertNotIn("groups", payload)
        self.assertEqual(payload["pagination"]["page_size"], 1)

    def test_grouped_ledger_returns_summary_and_fifo_lots_for_jia_xiaohua_closed_batch(self) -> None:
        ledger_service = self._lot_grouped_service(
            repayment_amount="300000.00",
            today=date(2026, 4, 5),
        )

        payload = ledger_service.list_grouped_ledger(family="personal")

        group = payload["groups"][0]
        self.assertEqual(group["counterparty_name"], "贾小花")
        self.assertEqual(group["row_span"], 4)
        self.assertEqual(group["rows"][0], group["summary_row"])
        summary = group["summary_row"]
        self.assertEqual(summary["row_kind"], "summary")
        self.assertEqual(summary["display_level"], "group_summary")
        self.assertEqual(summary["borrow_amount"], "300000.00")
        self.assertEqual(summary["repayment_amount"], "300000.00")
        self.assertEqual(summary["balance_amount"], "0.00")
        self.assertIsNone(summary["loan_days"])
        self.assertEqual(summary["accrued_interest"], "2761.65")

        flow_rows = group["flow_rows"]
        self.assertEqual(len(flow_rows), 3)
        self.assertEqual([row["row_kind"] for row in flow_rows], ["flow", "flow", "flow"])
        self.assertEqual(
            [row["source_bank_row_id"] for row in flow_rows],
            ["txn-jia-principal-200k", "txn-jia-principal-100k", "txn-jia-repayment"],
        )
        self.assertEqual(len({row["source_bank_row_id"] for row in flow_rows}), 3)
        self.assertEqual(
            [(row["flow_direction"], row["flow_amount"]) for row in flow_rows],
            [("income", "200000.00"), ("income", "100000.00"), ("expense", "300000.00")],
        )
        repayment_flow_rows = [
            row
            for row in flow_rows
            if row["source_bank_row_id"] == "txn-jia-repayment"
        ]
        self.assertEqual(len(repayment_flow_rows), 1)
        self.assertEqual(repayment_flow_rows[0]["borrow_amount"], "0.00")
        self.assertEqual(repayment_flow_rows[0]["borrow_date"], None)
        self.assertEqual(repayment_flow_rows[0]["repayment_amount"], "300000.00")
        self.assertEqual(repayment_flow_rows[0]["repayment_date"], "2026-03-04")

        allocation_lots = group["allocation_lots"]
        self.assertIs(group["lot_rows"], allocation_lots)
        self.assertEqual(len(allocation_lots), 2)
        self.assertEqual([row["row_kind"] for row in allocation_lots], ["allocation_lot", "allocation_lot"])
        self.assertEqual([row["borrow_amount"] for row in allocation_lots], ["200000.00", "100000.00"])
        self.assertEqual(
            [row["allocated_repayment_amount"] for row in allocation_lots],
            ["200000.00", "100000.00"],
        )
        self.assertEqual([row["repayment_amount"] for row in allocation_lots], ["200000.00", "100000.00"])
        self.assertEqual([row["balance_amount"] for row in allocation_lots], ["0.00", "0.00"])
        self.assertEqual([row["loan_days"] for row in allocation_lots], [28, 28])
        self.assertEqual([row["accrued_interest"] for row in allocation_lots], ["1841.10", "920.55"])
        self.assertEqual(
            [row["settlement_bank_row_ids"] for row in allocation_lots],
            [["txn-jia-repayment"], ["txn-jia-repayment"]],
        )

    def test_grouped_ledger_allocates_partial_repayment_and_interest_by_lot(self) -> None:
        ledger_service = self._lot_grouped_service(
            repayment_amount="250000.00",
            today=date(2026, 4, 5),
        )

        payload = ledger_service.list_grouped_ledger(family="personal")

        group = payload["groups"][0]
        self.assertEqual(group["row_span"], 4)
        summary = group["summary_row"]
        self.assertEqual(summary["borrow_amount"], "300000.00")
        self.assertEqual(summary["repayment_amount"], "250000.00")
        self.assertEqual(summary["balance_amount"], "50000.00")
        self.assertEqual(summary["accrued_interest"], "3813.70")

        first_lot, second_lot = group["lot_rows"]
        self.assertEqual(first_lot["principal_bank_row_id"], "txn-jia-principal-200k")
        self.assertEqual(first_lot["repayment_amount"], "200000.00")
        self.assertEqual(first_lot["balance_amount"], "0.00")
        self.assertEqual(first_lot["repayment_date"], "2026-03-04")
        self.assertEqual(first_lot["loan_days"], 28)
        self.assertEqual(first_lot["accrued_interest"], "1841.10")

        self.assertEqual(second_lot["principal_bank_row_id"], "txn-jia-principal-100k")
        self.assertEqual(second_lot["repayment_amount"], "50000.00")
        self.assertEqual(second_lot["balance_amount"], "50000.00")
        self.assertEqual(second_lot["repayment_date"], "2026-03-04")
        self.assertEqual(second_lot["loan_days"], 60)
        self.assertEqual(second_lot["accrued_interest"], "1972.60")


if __name__ == "__main__":
    unittest.main()
