from __future__ import annotations

import unittest

from fin_ops_platform.services.tax_offset_derived_lifecycle_executor import TaxOffsetDerivedLifecycleExecutor


class _RuntimeRecorder:
    def __init__(self) -> None:
        self.invalidate_all_calls = 0
        self.invalidate_scope_calls: list[dict[str, object]] = []

    def invalidate_read_models(self) -> list[str]:
        self.invalidate_all_calls += 1
        return ["2026-04", "2026-05"]

    def invalidate_read_model_scopes(self, scope_keys: list[str], *, reason: str = "") -> list[str]:
        self.invalidate_scope_calls.append({"scope_keys": list(scope_keys), "reason": reason})
        if not scope_keys:
            return []
        return ["2026-05"]


class TaxOffsetDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_read_model_invalidates_explicit_scopes_with_reason(self) -> None:
        runtime = _RuntimeRecorder()
        cleared: list[list[str] | None] = []
        executor = TaxOffsetDerivedLifecycleExecutor(
            runtime_service=runtime,
            clear_month_cache=lambda months: cleared.append(months),
        )

        result = executor.execute_read_model(
            {
                "scope_keys": [" tax_offset:2026-05 ", ""],
                "reason": "invoice_import_confirmed",
            }
        )

        self.assertEqual(runtime.invalidate_all_calls, 0)
        self.assertEqual(
            runtime.invalidate_scope_calls,
            [{"scope_keys": ["tax_offset:2026-05"], "reason": "invoice_import_confirmed"}],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"tax_offset_cache_scopes": 1},
                "invalidated_scopes": ["2026-05"],
                "enqueued_jobs": ["tax_offset_cache_warmup"],
            },
        )
        self.assertEqual(cleared, [])

    def test_execute_read_model_invalidates_all_and_defaults_reason(self) -> None:
        runtime = _RuntimeRecorder()
        executor = TaxOffsetDerivedLifecycleExecutor(
            runtime_service=runtime,
            clear_month_cache=lambda _months: None,
        )

        result = executor.execute_read_model({})

        self.assertEqual(runtime.invalidate_all_calls, 0)
        self.assertEqual(
            runtime.invalidate_scope_calls,
            [{"scope_keys": [], "reason": "derived_lifecycle_tax_offset"}],
        )
        self.assertEqual(result["invalidated_scopes"], [])

        result = executor.execute_read_model({"scope_keys": ["all"]})

        self.assertEqual(runtime.invalidate_all_calls, 1)
        self.assertEqual(result["invalidated_scopes"], ["2026-04", "2026-05"])

    def test_execute_month_cache_clears_months_or_all(self) -> None:
        runtime = _RuntimeRecorder()
        cleared: list[list[str] | None] = []
        executor = TaxOffsetDerivedLifecycleExecutor(
            runtime_service=runtime,
            clear_month_cache=lambda months: cleared.append(months),
        )

        result = executor.execute_month_cache(
            {"scope_keys": ["invoice_lifecycle:2026-04", " tax_offset:2026-05 ", ""]}
        )

        self.assertEqual(cleared, [["2026-04", "2026-05"]])
        self.assertEqual(
            result,
            {
                "deleted_counts": {"tax_offset_month_cache": 2},
                "invalidated_scopes": ["2026-04", "2026-05"],
            },
        )

        result = executor.execute_month_cache({"scope_keys": ["all"]})

        self.assertEqual(cleared[-1], None)
        self.assertEqual(
            result,
            {
                "deleted_counts": {"tax_offset_month_cache": 1},
                "invalidated_scopes": ["all"],
            },
        )


if __name__ == "__main__":
    unittest.main()
