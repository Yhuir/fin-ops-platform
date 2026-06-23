from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_auto_category_suggestion_provider import (
    BankDetailAutoCategorySuggestionProvider,
)


class _ImportService:
    def __init__(self) -> None:
        self.transaction_ids: list[str] = []

    def get_transaction(self, transaction_id: str) -> dict[str, object]:
        self.transaction_ids.append(transaction_id)
        return {
            "counterparty_name_raw": "供应商A",
            "amount": "100.00",
            "txn_direction": "outflow",
            "trade_time": "2026-06-24 10:00:00",
        }


class _BankDetailsService:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def auto_category_input_row(self, row: dict[str, object]) -> dict[str, object]:
        self.rows.append(dict(row))
        return {
            "id": row["id"],
            "counterparty_name": row["counterparty_name_raw"],
            "debit_amount": row["amount"],
        }


class _AutoCategoryService:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def suggest_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        self.rows.extend(rows)
        return {
            "txn-1": {
                "category_resolution_status": "needs_confirmation",
                "auto_candidate_category_codes": ["fee"],
            }
        }


class BankDetailAutoCategorySuggestionProviderTests(unittest.TestCase):
    def test_latest_uses_normalized_transaction_and_service_owned_input_row(self) -> None:
        import_service = _ImportService()
        bank_details_service = _BankDetailsService()
        auto_category_service = _AutoCategoryService()
        provider = BankDetailAutoCategorySuggestionProvider(
            import_service=import_service,
            bank_details_service=bank_details_service,  # type: ignore[arg-type]
            bank_transaction_auto_category_service=auto_category_service,  # type: ignore[arg-type]
        )

        suggestion = provider.latest(" txn-1 ")

        self.assertEqual(import_service.transaction_ids, ["txn-1"])
        self.assertEqual(bank_details_service.rows[0]["id"], "txn-1")
        self.assertEqual(auto_category_service.rows, [{"id": "txn-1", "counterparty_name": "供应商A", "debit_amount": "100.00"}])
        self.assertEqual(suggestion, {"category_resolution_status": "needs_confirmation", "auto_candidate_category_codes": ["fee"]})


if __name__ == "__main__":
    unittest.main()
