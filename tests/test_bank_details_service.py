from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.bank_details_relation_tag_projection_service import (
    BankDetailsRelationTagProjectionService,
)
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_RELATION_MODE
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


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
        counterparty_name: str = "供应商A",
        summary: str | None = None,
        remark: str | None = None,
    ) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no=f"622200001111{account_last4}",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw=counterparty_name,
            amount=Decimal("100.00"),
            signed_amount=Decimal("-100.00"),
            txn_date=trade_time[:10],
            trade_time=trade_time,
            balance=Decimal("900.00"),
            summary=summary,
            remark=remark,
            imported_bank_name=bank_name,
            imported_bank_last4=account_last4,
        )

    def _internal_transfer_transaction(
        self,
        *,
        transaction_id: str,
        direction: TransactionDirection,
        trade_time: str,
        account_no: str,
        account_last4: str,
        bank_name: str,
        counterparty_name: str,
    ) -> BankTransaction:
        signed_amount = Decimal("13000.00") if direction == TransactionDirection.INFLOW else Decimal("-13000.00")
        return BankTransaction(
            id=transaction_id,
            account_no=account_no,
            account_name="云南溯源科技有限公司",
            txn_direction=direction,
            counterparty_name_raw=counterparty_name,
            amount=Decimal("13000.00"),
            signed_amount=signed_amount,
            txn_date=trade_time[:10],
            trade_time=trade_time,
            balance=Decimal("50000.00"),
            summary="内部转账",
            remark="账户间调拨",
            imported_bank_name=bank_name,
            imported_bank_last4=account_last4,
        )

    def _internal_transfer_transactions(self) -> list[BankTransaction]:
        return [
            self._internal_transfer_transaction(
                transaction_id="txn-transfer-out",
                direction=TransactionDirection.OUTFLOW,
                trade_time="2026-04-03 10:00:00",
                account_no="6222000011116386",
                account_last4="6386",
                bank_name="工商银行",
                counterparty_name="云南溯源科技有限公司建设银行账户",
            ),
            self._internal_transfer_transaction(
                transaction_id="txn-transfer-in",
                direction=TransactionDirection.INFLOW,
                trade_time="2026-04-03 12:00:00",
                account_no="6227000011111410",
                account_last4="1410",
                bank_name="建设银行",
                counterparty_name="云南溯源科技有限公司工商银行账户",
            ),
        ]

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

    def test_transactions_default_to_no_relation_tags_without_provider(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id="txn-no-relation",
                        trade_time="2026-04-01 09:00:00",
                    )
                ]
            )
        )

        row = service.list_transactions(account_key="工商银行:6386")["rows"][0]

        self.assertEqual(row["oa_relation_tag"], "无oa")
        self.assertEqual(row["invoice_relation_tag"], "无发票")
        self.assertEqual(row["relation_tags"], ["无oa", "无发票"])
        self.assertNotIn("relation_case_id", row)

    def test_transactions_use_relation_provider_for_oa_and_invoice_tags(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id="txn-linked",
                        trade_time="2026-04-01 09:00:00",
                    )
                ]
            ),
            relation_tag_provider=lambda transaction_id: {
                "case_id": "CASE-LINKED",
                "row_types": ["bank", "oa", "invoice"],
            } if transaction_id == "txn-linked" else None,
        )

        row = service.list_transactions(account_key="工商银行:6386")["rows"][0]

        self.assertEqual(row["oa_relation_tag"], "有oa")
        self.assertEqual(row["invoice_relation_tag"], "有发票")
        self.assertEqual(row["relation_tags"], ["有oa", "有发票"])
        self.assertEqual(row["relation_case_id"], "CASE-LINKED")

    def test_transactions_use_relation_provider_for_invoice_only_boundary(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id="txn-invoice-only",
                        trade_time="2026-04-01 09:00:00",
                    )
                ]
            ),
            relation_tag_provider=lambda _transaction_id: {
                "case_id": "CASE-INVOICE",
                "row_types": ["bank", "invoice"],
            },
        )

        row = service.list_transactions(account_key="工商银行:6386")["rows"][0]

        self.assertEqual(row["oa_relation_tag"], "无oa")
        self.assertEqual(row["invoice_relation_tag"], "有发票")
        self.assertEqual(row["relation_tags"], ["无oa", "有发票"])
        self.assertEqual(row["relation_case_id"], "CASE-INVOICE")

    def test_transactions_use_relation_provider_for_oa_only_boundary(self) -> None:
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(
                        transaction_id="txn-oa-only",
                        trade_time="2026-04-01 09:00:00",
                    )
                ]
            ),
            relation_tag_provider=lambda _transaction_id: {
                "case_id": "CASE-OA",
                "row_types": ["bank", "oa"],
            },
        )

        row = service.list_transactions(account_key="工商银行:6386")["rows"][0]

        self.assertEqual(row["oa_relation_tag"], "有oa")
        self.assertEqual(row["invoice_relation_tag"], "无发票")
        self.assertEqual(row["relation_tags"], ["有oa", "无发票"])
        self.assertEqual(row["relation_case_id"], "CASE-OA")

    def test_relation_tag_projection_keeps_no_oa_relation_over_candidates_and_groups(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        pair_relation_service.create_active_relation(
            case_id="NO-OA-CASE",
            row_ids=["txn-no-oa"],
            row_types=["bank"],
            relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
            created_by="tester",
        )
        candidate_match_service = WorkbenchCandidateMatchService()
        candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-no-oa-candidate", "txn-no-oa"],
                "oa_row_ids": ["oa-no-oa-candidate"],
                "bank_row_ids": ["txn-no-oa"],
                "invoice_row_ids": [],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "candidate should not override explicit no OA",
                "conflict_candidate_keys": [],
                "source_versions": {},
            }
        )
        service = BankDetailsRelationTagProjectionService(
            pair_relation_service=pair_relation_service,
            candidate_match_service=candidate_match_service,
            workbench_read_model_provider=lambda: {
                "scope_key": "all",
                "generated_at": "2026-05-15T00:00:00",
                "source_versions": {},
                "payload": {
                    "open": {
                        "groups": [
                            {
                                "group_id": "candidate:no-oa-group",
                                "oa_rows": [{"id": "oa-no-oa-group", "type": "oa"}],
                                "bank_rows": [{"id": "txn-no-oa", "type": "bank"}],
                                "invoice_rows": [],
                            }
                        ]
                    }
                },
            },
        )

        self.assertEqual(
            service.relation_tag_for_transaction("txn-no-oa"),
            {"case_id": "NO-OA-CASE", "row_types": ["bank"]},
        )

    def test_relation_tag_projection_merges_missing_types_without_replacing_active_case(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        pair_relation_service.create_active_relation(
            case_id="CASE-INVOICE-ACTIVE",
            row_ids=["txn-with-invoice", "inv-active"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
        )
        candidate_match_service = WorkbenchCandidateMatchService()
        candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-candidate", "txn-with-invoice"],
                "oa_row_ids": ["oa-candidate"],
                "bank_row_ids": ["txn-with-invoice"],
                "invoice_row_ids": [],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "candidate supplies OA while active relation supplies invoice",
                "conflict_candidate_keys": [],
                "source_versions": {},
            }
        )
        service = BankDetailsRelationTagProjectionService(
            pair_relation_service=pair_relation_service,
            candidate_match_service=candidate_match_service,
            workbench_read_model_provider=lambda: {
                "scope_key": "all",
                "generated_at": "2026-05-15T00:00:00",
                "source_versions": {},
                "payload": {},
            },
        )

        self.assertEqual(
            service.relation_tag_for_transaction("txn-with-invoice"),
            {"case_id": "CASE-INVOICE-ACTIVE", "row_types": ["bank", "invoice", "oa"]},
        )

    def test_relation_tag_projection_uses_workbench_candidate_priority_without_mixing_cases(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        candidate_match_service = WorkbenchCandidateMatchService()
        low_priority = candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-low", "txn-shared"],
                "oa_row_ids": ["oa-low"],
                "bank_row_ids": ["txn-shared"],
                "invoice_row_ids": [],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "lower priority incomplete candidate",
                "conflict_candidate_keys": [],
                "source_versions": {},
            }
        )
        high_priority = candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank_invoice",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "same_amount",
                "row_ids": ["oa-high", "txn-shared", "inv-high"],
                "oa_row_ids": ["oa-high"],
                "bank_row_ids": ["txn-shared"],
                "invoice_row_ids": ["inv-high"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "higher priority complete candidate",
                "conflict_candidate_keys": [],
                "source_versions": {},
            }
        )
        service = BankDetailsRelationTagProjectionService(
            pair_relation_service=pair_relation_service,
            candidate_match_service=candidate_match_service,
        )

        self.assertNotEqual(low_priority["candidate_key"], high_priority["candidate_key"])
        self.assertEqual(
            service.relation_tag_for_transaction("txn-shared"),
            {"case_id": high_priority["candidate_key"], "row_types": ["bank", "invoice", "oa"]},
        )

    def test_relation_tag_projection_degrades_when_workbench_read_model_provider_fails(self) -> None:
        pair_relation_service = WorkbenchPairRelationService()
        candidate_match_service = WorkbenchCandidateMatchService()
        candidate = candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-fallback", "txn-fallback"],
                "oa_row_ids": ["oa-fallback"],
                "bank_row_ids": ["txn-fallback"],
                "invoice_row_ids": [],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "candidate remains usable without read model",
                "conflict_candidate_keys": [],
                "source_versions": {},
            }
        )

        def raise_read_model_error() -> dict[str, object]:
            raise RuntimeError("workbench read model unavailable")

        service = BankDetailsRelationTagProjectionService(
            pair_relation_service=pair_relation_service,
            candidate_match_service=candidate_match_service,
            workbench_read_model_provider=raise_read_model_error,
        )

        self.assertEqual(
            service.relation_tag_for_transaction("txn-fallback"),
            {"case_id": candidate["candidate_key"], "row_types": ["bank", "oa"]},
        )

    def test_transactions_use_batch_relation_provider_once_and_degrade_on_failure(self) -> None:
        calls: list[list[str]] = []
        service = BankDetailsService(
            _ImportServiceStub(
                [
                    self._transaction(transaction_id="txn-batch-1", trade_time="2026-04-01 09:00:00"),
                    self._transaction(transaction_id="txn-batch-2", trade_time="2026-04-01 10:00:00"),
                ]
            ),
            relation_tag_batch_provider=lambda transaction_ids: calls.append(list(transaction_ids)) or {
                "txn-batch-1": {"case_id": "CASE-BATCH", "row_types": ["bank", "oa"]},
            },
        )

        payload = service.list_transactions(account_key="工商银行:6386")

        self.assertEqual(calls, [["txn-batch-1", "txn-batch-2"]])
        rows = {row["id"]: row for row in payload["rows"]}
        self.assertEqual(rows["txn-batch-1"]["relation_tags"], ["有oa", "无发票"])
        self.assertEqual(rows["txn-batch-1"]["relation_case_id"], "CASE-BATCH")
        self.assertEqual(rows["txn-batch-2"]["relation_tags"], ["无oa", "无发票"])

        failing_service = BankDetailsService(
            _ImportServiceStub([self._transaction(transaction_id="txn-fail", trade_time="2026-04-01 09:00:00")]),
            relation_tag_batch_provider=lambda _transaction_ids: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        failing_row = failing_service.list_transactions(account_key="工商银行:6386")["rows"][0]
        self.assertEqual(failing_row["relation_tags"], ["无oa", "无发票"])

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

    def test_transactions_use_auto_category_as_effective_when_no_manual_category(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-fee",
                trade_time="2026-04-03 09:15:30",
                summary="网银手续费",
            )
        ]
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            category_service=BankTransactionCategoryService.from_snapshot(
                None,
                transaction_exists=lambda transaction_id: transaction_id == "txn-fee",
            ),
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        payload = service.list_transactions(account_key="工商银行:6386")

        row = payload["rows"][0]
        self.assertEqual(row["trade_time"], "2026-04-03 09:15:30")
        self.assertEqual(row["manual_category_code"], None)
        self.assertEqual(row["manual_category_source"], "")
        self.assertEqual(row["auto_category_code"], "fee")
        self.assertEqual(row["auto_category_label"], "手续费")
        self.assertEqual(row["auto_category_source"], "auto")
        self.assertEqual(row["auto_category_confidence"], "high")
        self.assertEqual(row["effective_category_code"], "fee")
        self.assertEqual(row["effective_category_label"], "手续费")
        self.assertEqual(row["effective_category_source"], "auto")
        self.assertEqual(row["category_code"], "fee")
        self.assertEqual(row["category_label"], "手续费")
        self.assertEqual(row["category_path"], ["自动识别", "手续费"])
        self.assertEqual(row["category_source"], "auto")
        self.assertEqual(row["category_version"], 0)

    def test_saved_manual_category_overrides_auto_category(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-fee",
                trade_time="2026-04-03 09:00:00",
                summary="网银手续费",
            )
        ]
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-fee",
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-fee", "category_code": "bonus", "expected_version": 0}],
            actor="YNSYLP005",
        )
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            category_service=category_service,
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        row = service.list_transactions(account_key="工商银行:6386")["rows"][0]

        self.assertEqual(row["manual_category_code"], "bonus")
        self.assertEqual(row["manual_category_source"], "manual")
        self.assertEqual(row["auto_category_code"], "fee")
        self.assertEqual(row["effective_category_code"], "bonus")
        self.assertEqual(row["effective_category_source"], "manual")
        self.assertEqual(row["category_code"], "bonus")
        self.assertEqual(row["category_version"], 1)

    def test_manual_clear_suppresses_auto_category_and_counts_as_uncategorized(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-fee",
                trade_time="2026-04-03 09:00:00",
                summary="网银手续费",
            )
        ]
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-fee",
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-fee", "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            category_service=category_service,
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        payload = service.list_transactions(account_key="工商银行:6386")
        row = payload["rows"][0]

        self.assertEqual(row["manual_category_code"], None)
        self.assertEqual(row["manual_category_source"], "manual")
        self.assertEqual(row["auto_category_code"], "fee")
        self.assertEqual(row["effective_category_code"], None)
        self.assertEqual(row["effective_category_source"], "")
        self.assertEqual(row["category_code"], None)
        self.assertEqual(row["category_label"], None)
        self.assertEqual(row["category_version"], 1)
        self.assertEqual(payload["category_counts"]["fee"], 0)
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)

    def test_category_counts_are_based_on_effective_categories_across_full_filter(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-fee",
                trade_time="2026-04-03 09:00:00",
                summary="网银手续费",
            ),
            self._transaction(
                transaction_id="txn-bonus",
                trade_time="2026-04-02 09:00:00",
                summary="年终奖",
            ),
            self._transaction(
                transaction_id="txn-manual-clear",
                trade_time="2026-04-01 09:00:00",
                summary="网银手续费",
            ),
        ]
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-bonus", "category_code": "salary", "expected_version": 0}],
            actor="YNSYLP005",
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-manual-clear", "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            category_service=category_service,
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        payload = service.list_transactions(account_key="工商银行:6386", page=1, page_size=1)

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-fee"])
        self.assertEqual(payload["category_counts"]["fee"], 1)
        self.assertEqual(payload["category_counts"]["salary"], 1)
        self.assertEqual(payload["category_counts"]["bonus"], 0)
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)

    def test_keyword_search_filters_full_account_date_result_before_pagination_and_counts(self) -> None:
        transactions = [
            self._transaction(
                transaction_id="txn-newest",
                trade_time="2026-04-03 09:00:00",
                counterparty_name="普通供应商A",
                summary="普通付款",
                remark="普通用途",
            ),
            self._transaction(
                transaction_id="txn-middle",
                trade_time="2026-04-02 09:00:00",
                counterparty_name="普通供应商B",
                summary="普通付款",
                remark="普通用途",
            ),
            self._transaction(
                transaction_id="txn-target",
                trade_time="2026-04-01 09:00:00",
                counterparty_name="跨页目标供应商",
                summary="网银手续费",
                remark="跨页目标用途",
            ),
        ]
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        payload = service.list_transactions(
            account_key="工商银行:6386",
            date_from="2026-04-01",
            date_to="2026-04-30",
            keyword="跨页目标",
            page=1,
            page_size=2,
        )

        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-target"])
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["category_counts"]["fee"], 1)
        self.assertEqual(payload["category_counts"]["uncategorized"], 0)

    def test_internal_transfer_auto_category_uses_date_range_context_across_accounts(self) -> None:
        transactions = self._internal_transfer_transactions()
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        all_payload = service.list_transactions(date_from="2026-04-01", date_to="2026-04-30")
        out_account_payload = service.list_transactions(
            account_key="工商银行:6386",
            date_from="2026-04-01",
            date_to="2026-04-30",
        )
        in_account_payload = service.list_transactions(
            account_key="建设银行:1410",
            date_from="2026-04-01",
            date_to="2026-04-30",
        )

        self.assertCountEqual([row["id"] for row in all_payload["rows"]], ["txn-transfer-out", "txn-transfer-in"])
        self.assertEqual({row["auto_category_code"] for row in all_payload["rows"]}, {"internal_transfer"})
        self.assertEqual({row["effective_category_code"] for row in all_payload["rows"]}, {"internal_transfer"})
        self.assertEqual(all_payload["category_counts"]["internal_transfer"], 2)
        self.assertEqual(all_payload["category_counts"]["uncategorized"], 0)

        self.assertEqual([row["id"] for row in out_account_payload["rows"]], ["txn-transfer-out"])
        self.assertEqual(out_account_payload["rows"][0]["auto_category_code"], "internal_transfer")
        self.assertEqual(out_account_payload["rows"][0]["effective_category_code"], "internal_transfer")
        self.assertEqual(out_account_payload["category_counts"]["internal_transfer"], 1)
        self.assertEqual(out_account_payload["category_counts"]["uncategorized"], 0)

        self.assertEqual([row["id"] for row in in_account_payload["rows"]], ["txn-transfer-in"])
        self.assertEqual(in_account_payload["rows"][0]["auto_category_code"], "internal_transfer")
        self.assertEqual(in_account_payload["rows"][0]["effective_category_code"], "internal_transfer")
        self.assertEqual(in_account_payload["category_counts"]["internal_transfer"], 1)
        self.assertEqual(in_account_payload["category_counts"]["uncategorized"], 0)

    def test_manual_clear_suppresses_one_internal_transfer_auto_category_without_hiding_counterpart_auto(self) -> None:
        transactions = self._internal_transfer_transactions()
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {transaction.id for transaction in transactions},
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-transfer-out", "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )
        service = BankDetailsService(
            _ImportServiceStub(transactions),
            category_service=category_service,
            auto_category_service=BankTransactionAutoCategoryService(),
        )

        out_account_payload = service.list_transactions(
            account_key="工商银行:6386",
            date_from="2026-04-01",
            date_to="2026-04-30",
        )
        in_account_payload = service.list_transactions(
            account_key="建设银行:1410",
            date_from="2026-04-01",
            date_to="2026-04-30",
        )
        all_payload = service.list_transactions(date_from="2026-04-01", date_to="2026-04-30")

        cleared_row = out_account_payload["rows"][0]
        self.assertEqual(cleared_row["id"], "txn-transfer-out")
        self.assertEqual(cleared_row["manual_category_source"], "manual")
        self.assertEqual(cleared_row["auto_category_code"], "internal_transfer")
        self.assertEqual(cleared_row["effective_category_code"], None)
        self.assertEqual(out_account_payload["category_counts"]["internal_transfer"], 0)
        self.assertEqual(out_account_payload["category_counts"]["uncategorized"], 1)

        counterpart_row = in_account_payload["rows"][0]
        self.assertEqual(counterpart_row["id"], "txn-transfer-in")
        self.assertEqual(counterpart_row["manual_category_source"], "")
        self.assertEqual(counterpart_row["auto_category_code"], "internal_transfer")
        self.assertEqual(counterpart_row["effective_category_code"], "internal_transfer")
        self.assertEqual(in_account_payload["category_counts"]["internal_transfer"], 1)
        self.assertEqual(in_account_payload["category_counts"]["uncategorized"], 0)

        self.assertEqual(all_payload["category_counts"]["internal_transfer"], 1)
        self.assertEqual(all_payload["category_counts"]["uncategorized"], 1)


if __name__ == "__main__":
    unittest.main()
