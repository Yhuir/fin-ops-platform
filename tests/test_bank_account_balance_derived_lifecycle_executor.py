from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_account_balance_derived_lifecycle_executor import (
    BankAccountBalanceDerivedLifecycleExecutor,
)


class BankAccountBalanceDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_preserves_all_only_refresh_payload_when_enqueued(self) -> None:
        calls: list[str] = []

        def enqueue_refresh(*, reason: str) -> bool:
            calls.append(reason)
            return True

        result = BankAccountBalanceDerivedLifecycleExecutor(enqueue_refresh=enqueue_refresh).execute(
            {"reason": "unit_test"}
        )

        self.assertEqual(calls, ["unit_test"])
        self.assertEqual(result["deleted_counts"], {"bank_account_balance_read_models": 0})
        self.assertEqual(result["invalidated_scopes"], ["all"])
        self.assertEqual(result["enqueued_jobs"], ["bank_account_balance.read_model.refresh"])

    def test_execute_omits_job_when_enqueue_unavailable(self) -> None:
        result = BankAccountBalanceDerivedLifecycleExecutor(enqueue_refresh=lambda **_kwargs: False).execute({})

        self.assertEqual(result["deleted_counts"], {"bank_account_balance_read_models": 0})
        self.assertEqual(result["invalidated_scopes"], ["all"])
        self.assertEqual(result["enqueued_jobs"], [])


if __name__ == "__main__":
    unittest.main()
