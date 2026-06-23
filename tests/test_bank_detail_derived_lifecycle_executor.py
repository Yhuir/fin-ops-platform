from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_derived_lifecycle_executor import BankDetailDerivedLifecycleExecutor


class BankDetailDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_prefers_explicit_month_scopes_and_forwards_metadata(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = BankDetailDerivedLifecycleExecutor(
            available_month_scope_keys_provider=lambda: ["2026-01", "2026-02"],
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
        )

        result = executor.execute(
            {
                "scope_keys": ["bank_detail:2026-03", "2026-01", "all"],
                "reason": "rules_changed",
                "metadata": {
                    "source": "unit-test",
                    "case_id": "CASE-1",
                    "action_name": "bank_rule_update",
                    "ignored": "not-forwarded",
                },
            }
        )

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["2026-01", "2026-03"],
                    "reason": "rules_changed",
                    "metadata": {"source": "unit-test", "case_id": "CASE-1", "action_name": "bank_rule_update"},
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"bank_detail_read_models": 0},
                "invalidated_scopes": ["2026-01", "2026-03"],
                "enqueued_jobs": ["bank_detail.read_model.refresh"],
            },
        )

    def test_execute_expands_all_scope_through_provider_and_defaults_reason(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = BankDetailDerivedLifecycleExecutor(
            available_month_scope_keys_provider=lambda: ["2026-04", "2026-05"],
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or False,
        )

        result = executor.execute({"scope_keys": ["all"]})

        self.assertEqual(
            enqueued,
            [{"scope_keys": ["2026-04", "2026-05"], "reason": "derived_lifecycle_bank_detail", "metadata": None}],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"bank_detail_read_models": 0},
                "invalidated_scopes": ["2026-04", "2026-05"],
                "enqueued_jobs": [],
            },
        )

    def test_execute_falls_back_to_all_when_no_scope_is_present(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = BankDetailDerivedLifecycleExecutor(
            available_month_scope_keys_provider=lambda: ["2026-04"],
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
        )

        result = executor.execute({})

        self.assertEqual(
            enqueued,
            [{"scope_keys": ["all"], "reason": "derived_lifecycle_bank_detail", "metadata": None}],
        )
        self.assertEqual(result["invalidated_scopes"], ["all"])


if __name__ == "__main__":
    unittest.main()
