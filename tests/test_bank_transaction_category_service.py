import unittest

from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryConflictError,
    BankTransactionCategoryValidationError,
    BankTransactionCategoryService,
)


class BankTransactionCategoryServiceTests(unittest.TestCase):
    def test_apply_updates_persists_category_with_version_and_audit_fields(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1"},
        )

        result = service.apply_updates(
            [
                {
                    "transaction_id": "txn-1",
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_transaction_ids"], ["txn-1"])
        self.assertEqual(result["updated_categories"][0]["category_label"], "公司暂借款：待还款")
        self.assertEqual(result["updated_categories"][0]["category_path"], ["借入", "公司往来款", "待还款"])
        self.assertEqual(result["updated_categories"][0]["version"], 1)
        stored = service.get("txn-1")
        self.assertEqual(stored["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(stored["category_label"], "公司暂借款：待还款")
        self.assertEqual(stored["category_path"], ["借入", "公司往来款", "待还款"])
        self.assertEqual(stored["category_version"], 1)
        self.assertEqual(stored["updated_by"], "YNSYLP005")

    def test_apply_updates_rejects_invalid_category_code_atomically(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1", "txn-2"},
        )

        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_updates(
                [
                    {"transaction_id": "txn-1", "category_code": "borrow_out_personal_lent", "expected_version": 0},
                    {"transaction_id": "txn-2", "category_code": "unsupported", "expected_version": 0},
                ],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "invalid_category_code")
        self.assertEqual(service.snapshot()["categories"], {})

    def test_apply_updates_rejects_unknown_transaction(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )

        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_updates(
                [{"transaction_id": "missing-txn", "category_code": "business_warranty_pending_collection", "expected_version": 0}],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "unknown_transaction_id")

    def test_apply_updates_rejects_expected_version_conflict(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "business_bid_bond_pending_collection", "expected_version": 0}],
            actor="YNSYLP005",
        )

        with self.assertRaises(BankTransactionCategoryConflictError) as context:
            service.apply_updates(
                [{"transaction_id": "txn-1", "category_code": "borrow_in_bank_repaid", "expected_version": 0}],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "category_version_conflict")
        self.assertEqual(service.get("txn-1")["category_code"], "business_bid_bond_pending_collection")

    def test_clear_category_keeps_next_version_and_counts_uncategorized(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1", "txn-2"},
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "borrow_out_company_pending_collection", "expected_version": 0}],
            actor="YNSYLP005",
        )

        result = service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": None, "expected_version": 1}],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_code"], None)
        self.assertEqual(result["updated_categories"][0]["category_label"], None)
        self.assertEqual(result["updated_categories"][0]["version"], 2)
        self.assertEqual(service.get("txn-1")["category_version"], 2)
        counts = service.category_counts(["txn-1", "txn-2"])
        self.assertEqual(counts["borrow_out_company_pending_collection"], 0)
        self.assertEqual(counts["uncategorized"], 2)

    def test_snapshot_round_trips_categories(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "borrow_in_personal_repaid", "expected_version": 0}],
            actor="YNSYLP005",
        )

        restored = BankTransactionCategoryService.from_snapshot(
            service.snapshot(),
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )

        self.assertEqual(restored.get("txn-1")["category_label"], "个人暂借款：已还款")
        self.assertEqual(restored.get("txn-1")["category_path"], ["借入", "个人往来款", "已还款"])
        self.assertEqual(restored.get("txn-1")["category_version"], 1)


if __name__ == "__main__":
    unittest.main()
