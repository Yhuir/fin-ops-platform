from __future__ import annotations

import unittest

from fin_ops_platform.services.invoice_lifecycle_derived_lifecycle_executor import (
    InvoiceLifecycleDerivedLifecycleExecutor,
)


class InvoiceLifecycleDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_prefers_explicit_scope_keys_and_forwards_metadata(self) -> None:
        executor = InvoiceLifecycleDerivedLifecycleExecutor()

        result = executor.execute(
            {
                "scope_keys": [" invoice_lifecycle:2026-03 ", "all", ""],
                "reason": "invoice_import_confirmed",
                "metadata": {
                    "source": "unit-test",
                    "case_id": "CASE-1",
                    "action_name": "invoice_import",
                    "downstream_scope_types": ["pending_invoice"],
                    "invoice_usage_scope_types": ["input_invoice_usage", "output_invoice_collection"],
                    "pending_invoice_scope_keys": ["expense:all:2026-03"],
                    "ignored": "not-forwarded",
                },
            }
        )

        self.assertEqual(
            result,
            {
                "deleted_counts": {"invoice_lifecycle_read_models": 0},
                "invalidated_scopes": ["invoice_lifecycle:2026-03", "all"],
                "enqueued_jobs": [],
            },
        )

    def test_execute_falls_back_to_all_and_defaults_reason(self) -> None:
        executor = InvoiceLifecycleDerivedLifecycleExecutor()

        result = executor.execute({})

        self.assertEqual(
            result,
            {
                "deleted_counts": {"invoice_lifecycle_read_models": 0},
                "invalidated_scopes": ["all"],
                "enqueued_jobs": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
