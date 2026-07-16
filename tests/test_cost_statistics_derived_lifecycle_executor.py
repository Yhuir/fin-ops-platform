from __future__ import annotations

import unittest

from fin_ops_platform.services.cost_statistics_derived_lifecycle_executor import (
    CostStatisticsDerivedLifecycleExecutor,
)


class _RuntimeRecorder:
    @staticmethod
    def refresh_scope_keys_from_scope_keys(scope_keys: list[str]) -> list[str]:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        return CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys(scope_keys)


class CostStatisticsDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_enqueues_explicit_scopes_and_reports_gateway_refresh_job(self) -> None:
        runtime = _RuntimeRecorder()
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
        )

        result = executor.execute(
            {
                "scope_keys": [" active:2026-05 ", "", "all:2026-05"],
                "reason": "invoice_import_confirmed",
            }
        )

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["active:2026-05", "all:2026-05"],
                    "reason": "invoice_import_confirmed",
                    "metadata": None,
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 2},
                "invalidated_scopes": ["active:2026-05", "all:2026-05"],
                "enqueued_jobs": ["cost_statistics.read_model.refresh"],
            },
        )

    def test_execute_preserves_refresh_metadata_and_invalidated_scope_shape(self) -> None:
        runtime = _RuntimeRecorder()
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
        )

        result = executor.execute(
            {
                "scope_keys": [" active:2026-06 "],
                "reason": "pending_invoice_rules_changed",
                "metadata": {
                    "source": "unit-test",
                    "case_id": "CASE-1",
                    "action_name": "pending_invoice_rules",
                    "downstream_scope_types": ["cost_statistics"],
                    "invoice_usage_scope_types": ["input_invoice_usage"],
                    "pending_invoice_scope_keys": ["expense:all:2026-06"],
                    "ignored": "not-forwarded",
                },
            }
        )

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["active:2026-06"],
                    "reason": "pending_invoice_rules_changed",
                    "metadata": {
                        "source": "unit-test",
                        "case_id": "CASE-1",
                        "action_name": "pending_invoice_rules",
                        "downstream_scope_types": ["cost_statistics"],
                        "invoice_usage_scope_types": ["input_invoice_usage"],
                        "pending_invoice_scope_keys": ["expense:all:2026-06"],
                    },
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 1},
                "invalidated_scopes": ["active:2026-06"],
                "enqueued_jobs": ["cost_statistics.read_model.refresh"],
            },
        )

    def test_execute_all_scope_reports_no_refresh_when_gateway_unavailable(self) -> None:
        runtime = _RuntimeRecorder()
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or False,
        )

        result = executor.execute(
            {"scope_keys": ["all"], "reason": "settings_project_status_changed"}
        )

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["all"],
                    "reason": "settings_project_status_changed",
                    "metadata": None,
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 0},
                "invalidated_scopes": [],
                "enqueued_jobs": [],
            },
        )

    def test_execute_no_scope_defaults_to_all(self) -> None:
        runtime = _RuntimeRecorder()
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or False,
        )

        result = executor.execute({})

        self.assertEqual(
            enqueued,
            [
                {
                    "scope_keys": ["all"],
                    "reason": "derived_lifecycle_cost_statistics",
                    "metadata": None,
                }
            ],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 0},
                "invalidated_scopes": [],
                "enqueued_jobs": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
