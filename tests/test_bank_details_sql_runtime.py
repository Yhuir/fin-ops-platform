from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)


class FakeCategoryService:
    def __init__(self, categories: dict[str, dict[str, object]] | None = None) -> None:
        self.categories = categories or {}

    def get(self, transaction_id: str) -> dict[str, object]:
        return dict(self.categories.get(transaction_id) or {})

    def bulk_get(self, transaction_ids: list[str]) -> dict[str, dict[str, object]]:
        return {transaction_id: dict(self.categories.get(transaction_id) or {}) for transaction_id in transaction_ids}


class FakeAutoCategoryService:
    def __init__(self, suggestions: dict[str, dict[str, object]] | None = None) -> None:
        self.suggestions = suggestions or {}

    def suggestions_by_transaction_id(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        return {
            str(row.get("id") or row.get("transaction_id") or ""): dict(
                self.suggestions.get(str(row.get("id") or row.get("transaction_id") or "")) or {}
            )
            for row in rows
        }


class BankTransactionEffectiveCategoryProviderTests(unittest.TestCase):
    def test_provider_is_direct_bank_tag_source(self) -> None:
        provider = BankTransactionEffectiveCategoryProvider(
            category_service=FakeCategoryService(
                {
                    "txn-confirmed": {
                        "category_code": "equipment_purchase",
                        "category_label": "设备采购",
                        "category_path": ["货款", "设备采购"],
                        "category_label_path": ["货款", "设备采购"],
                        "category_primary_label": "货款",
                        "category_sub_label": "设备采购",
                        "source": "auto_confirmation",
                        "category_version": 7,
                    }
                }
            ),
            auto_category_service=FakeAutoCategoryService(
                {
                    "txn-auto": {
                        "category_code": "equipment_purchase",
                        "category_label": "设备采购",
                        "category_path": ["货款", "设备采购"],
                        "category_label_path": ["货款", "设备采购"],
                        "category_primary_label": "货款",
                        "category_sub_label": "设备采购",
                    }
                }
            ),
        )

        categories = provider.bulk_get_for_rows(
            [
                {"id": "txn-auto", "txn_direction": "outflow", "amount": "100.00"},
                {"id": "txn-confirmed", "txn_direction": "outflow", "amount": "200.00"},
                {"id": "txn-empty", "txn_direction": "outflow", "amount": "1.00"},
            ]
        )

        self.assertEqual(categories["txn-auto"]["category_code"], "equipment_purchase")
        self.assertEqual(categories["txn-auto"]["source"], "auto")
        self.assertEqual(categories["txn-confirmed"]["category_code"], "equipment_purchase")
        self.assertEqual(categories["txn-confirmed"]["source"], "manual_confirmation")
        self.assertEqual(categories["txn-confirmed"]["category_version"], 7)
        self.assertIsNone(categories["txn-empty"]["category_code"])

    def test_provider_does_not_expose_read_model_freshness_contract(self) -> None:
        provider = BankTransactionEffectiveCategoryProvider(
            category_service=FakeCategoryService(),
            auto_category_service=FakeAutoCategoryService(),
        )

        self.assertFalse(hasattr(provider, "last_source_versions"))
        self.assertFalse(hasattr(provider, "get_by_transaction_ids"))
        self.assertFalse(hasattr(provider, "list_by_month"))


class BankDetailReadModelRemovalTests(unittest.TestCase):
    def test_bank_detail_runtime_files_are_removed(self) -> None:
        removed_paths = [
            "backend/src/fin_ops_platform/services/bank_detail_read_model_refresh.py",
            "backend/src/fin_ops_platform/services/bank_detail_read_model_refresh_producer.py",
            "backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py",
            "backend/src/fin_ops_platform/services/bank_detail_sql_projection.py",
            "backend/src/fin_ops_platform/services/bank_transaction_tag_read_facade.py",
            "backend/src/fin_ops_platform/app/bank_detail_backfill.py",
        ]

        for path in removed_paths:
            with self.subTest(path=path):
                self.assertFalse(Path(path).exists())


if __name__ == "__main__":
    unittest.main()
