from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_available_month_scope_provider import BankDetailAvailableMonthScopeProvider


class _ImportService:
    def __init__(self, rows: list[dict[str, object]], *, accepts_month: bool = True) -> None:
        self._rows = rows
        self._accepts_month = accepts_month
        self.calls: list[dict[str, object]] = []

    def list_transactions(self, **kwargs: object) -> list[dict[str, object]]:
        if kwargs and not self._accepts_month:
            raise TypeError("month not supported")
        self.calls.append(dict(kwargs))
        return list(self._rows)


class _ReadModelRepository:
    def __init__(self, scope_keys: list[str]) -> None:
        self._scope_keys = list(scope_keys)
        self.calls: list[dict[str, object]] = []

    def bank_detail_scope_keys_for_range(self, **kwargs: object) -> list[str]:
        self.calls.append(dict(kwargs))
        return list(self._scope_keys)


class BankDetailAvailableMonthScopeProviderTests(unittest.TestCase):
    def test_scope_keys_prefers_read_model_repository_without_import_scan(self) -> None:
        import_service = _ImportService([{"txn_date": "2026-01-01"}])
        repository = _ReadModelRepository(["2026-03", "all", "bad-scope", "2026-02", "2026-03"])
        provider = BankDetailAvailableMonthScopeProvider(
            import_service=import_service,
            read_model_repository=repository,
        )

        self.assertEqual(provider.scope_keys(), ["2026-02", "2026-03"])
        self.assertEqual(repository.calls, [{"date_from": None, "date_to": None}])
        self.assertEqual(import_service.calls, [])

    def test_scope_keys_without_import_fallback_returns_all_when_repository_missing(self) -> None:
        import_service = _ImportService([{"txn_date": "2026-01-01"}])
        provider = BankDetailAvailableMonthScopeProvider(
            import_service=import_service,
            fallback_to_import_service=False,
        )

        self.assertEqual(provider.scope_keys(), ["all"])
        self.assertEqual(import_service.calls, [])

    def test_scope_keys_collects_sorted_months_from_known_transaction_date_fields(self) -> None:
        import_service = _ImportService(
            [
                {"txn_date": "2026-03-12"},
                {"trade_time": "2026-01-02 08:00:00"},
                {"pay_receive_time": "invalid"},
                {"business_date": "2026-02-28"},
                {"transaction_at": "2026-01-31T00:00:00"},
            ]
        )
        provider = BankDetailAvailableMonthScopeProvider(import_service=import_service)

        self.assertEqual(provider.scope_keys(), ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(import_service.calls, [{"month": "all"}])

    def test_scope_keys_falls_back_to_unfiltered_loader_and_all_scope(self) -> None:
        import_service = _ImportService([], accepts_month=False)
        provider = BankDetailAvailableMonthScopeProvider(import_service=import_service)

        self.assertEqual(provider.scope_keys(), ["all"])
        self.assertEqual(import_service.calls, [{}])


if __name__ == "__main__":
    unittest.main()
