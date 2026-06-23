from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_derived_lifecycle_executor import (
    WorkbenchRelationDerivedLifecycleExecutor,
)


class WorkbenchRelationDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_prefers_explicit_scope_keys_and_forwards_metadata(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = WorkbenchRelationDerivedLifecycleExecutor(
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
        )

        result = executor.execute(
            {
                "scope_keys": [" workbench_relation:2026-03 ", "all", ""],
                "reason": "pair_relation_changed",
                "metadata": {
                    "source": "unit-test",
                    "case_id": "CASE-1",
                    "action_name": "confirm_link",
                    "downstream_scope_types": ["pending_invoice"],
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
                    "scope_keys": ["workbench_relation:2026-03", "all"],
                    "reason": "pair_relation_changed",
                    "metadata": {
                        "source": "unit-test",
                        "case_id": "CASE-1",
                        "action_name": "confirm_link",
                        "downstream_scope_types": ["pending_invoice"],
                        "invoice_usage_scope_types": ["input_invoice_usage"],
                        "pending_invoice_scope_keys": ["expense:all:2026-03"],
                    },
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"workbench_relation_read_models": 0},
                "invalidated_scopes": ["workbench_relation:2026-03", "all"],
                "enqueued_jobs": ["workbench_relation.read_model.refresh"],
            },
        )

    def test_execute_falls_back_to_all_and_defaults_reason(self) -> None:
        enqueued: list[dict[str, object]] = []
        executor = WorkbenchRelationDerivedLifecycleExecutor(
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or False,
        )

        result = executor.execute({})

        self.assertEqual(
            enqueued,
            [{"scope_keys": ["all"], "reason": "derived_lifecycle_workbench_relation", "metadata": None}],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"workbench_relation_read_models": 0},
                "invalidated_scopes": ["all"],
                "enqueued_jobs": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
