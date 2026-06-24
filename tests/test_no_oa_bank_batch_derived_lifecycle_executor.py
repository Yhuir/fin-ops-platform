from __future__ import annotations

import unittest

from fin_ops_platform.services.no_oa_bank_batch_derived_lifecycle_executor import (
    NoOaBankBatchDerivedLifecycleExecutor,
)


class NoOaBankBatchDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_prefers_month_scopes_and_forwards_metadata(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = NoOaBankBatchDerivedLifecycleExecutor(
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            )
            or True,
        )

        result = executor.execute(
            {
                "scope_keys": [" no_oa_bank_batch:2026-04 ", "2026-03", "all", ""],
                "reason": "no_oa_bank_batch_changed",
                "metadata": {
                    "source": "unit-test",
                    "case_id": "CASE-1",
                    "action_name": "no_oa_bank_batch_submit",
                    "downstream_scope_types": ["no_oa_bank_batch"],
                    "invoice_usage_scope_types": ["input_invoice_usage"],
                    "pending_invoice_scope_keys": ["expense:all:2026-03"],
                    "ignored": "not-forwarded",
                },
            }
        )

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["2026-03", "2026-04"],
                    "reason": "no_oa_bank_batch_changed",
                    "metadata": {
                        "source": "unit-test",
                        "case_id": "CASE-1",
                        "action_name": "no_oa_bank_batch_submit",
                        "downstream_scope_types": ["no_oa_bank_batch"],
                        "invoice_usage_scope_types": ["input_invoice_usage"],
                        "pending_invoice_scope_keys": ["expense:all:2026-03"],
                    },
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"no_oa_bank_batch_read_models": 0},
                "invalidated_scopes": ["2026-03", "2026-04"],
                "enqueued_jobs": ["no_oa_bank_batch.read_model.refresh"],
            },
        )

    def test_execute_falls_back_to_all_and_defaults_reason(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = NoOaBankBatchDerivedLifecycleExecutor(
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            )
            or False,
        )

        result = executor.execute({"scope_keys": ["not-a-month"]})

        self.assertEqual(
            enqueued,
            [{"scope_keys": ["all"], "reason": "derived_lifecycle_no_oa_bank_batch", "metadata": None}],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"no_oa_bank_batch_read_models": 0},
                "invalidated_scopes": ["all"],
                "enqueued_jobs": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
