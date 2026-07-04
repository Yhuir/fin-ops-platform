from __future__ import annotations

import unittest

from fin_ops_platform.services.cost_statistics_derived_lifecycle_executor import (
    CostStatisticsDerivedLifecycleExecutor,
)


class _RuntimeRecorder:
    def __init__(self) -> None:
        self.invalidate_all_calls: list[dict[str, object]] = []
        self.invalidate_scope_calls: list[dict[str, object]] = []
        self.invalidate_all_result = ["active:all", "all:all"]
        self.invalidate_scopes_result = ["active:2026-05", "all:2026-05"]

    def invalidate_read_models(self, *, schedule_warmup: bool = True, persist_empty: bool = True) -> list[str]:
        self.invalidate_all_calls.append(
            {"schedule_warmup": schedule_warmup, "persist_empty": persist_empty}
        )
        return list(self.invalidate_all_result)

    def invalidate_read_model_scopes(
        self,
        scope_keys: list[str],
        *,
        reason: str = "",
        schedule_warmup: bool = True,
        persist_empty: bool = True,
    ) -> list[str]:
        self.invalidate_scope_calls.append(
            {
                "scope_keys": list(scope_keys),
                "reason": reason,
                "schedule_warmup": schedule_warmup,
                "persist_empty": persist_empty,
            }
        )
        return list(self.invalidate_scopes_result)


class CostStatisticsDerivedLifecycleExecutorTests(unittest.TestCase):
    def test_execute_invalidates_explicit_scopes_and_reports_gateway_refresh_job(self) -> None:
        runtime = _RuntimeRecorder()
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
            can_enqueue_refresh=lambda: True,
        )

        result = executor.execute(
            {
                "scope_keys": [" active:2026-05 ", "", "all:2026-05"],
                "reason": "invoice_import_confirmed",
            },
            schedule_warmup=True,
        )

        self.assertEqual(runtime.invalidate_all_calls, [])
        self.assertEqual(
            runtime.invalidate_scope_calls,
            [
                {
                    "scope_keys": ["active:2026-05", "all:2026-05"],
                    "reason": "invoice_import_confirmed",
                    "schedule_warmup": True,
                    "persist_empty": True,
                }
            ],
        )
        self.assertEqual(enqueued, [])
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 2},
                "invalidated_scopes": ["active:2026-05", "all:2026-05"],
                "enqueued_jobs": ["cost_statistics.read_model.refresh"],
            },
        )

    def test_execute_preserves_no_warmup_refresh_fallback_metadata_and_deleted_scope_shape(self) -> None:
        runtime = _RuntimeRecorder()
        runtime.invalidate_scopes_result = []
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or True,
            can_enqueue_refresh=lambda: False,
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
            },
            schedule_warmup=False,
        )

        self.assertEqual(
            runtime.invalidate_scope_calls,
            [
                {
                    "scope_keys": ["active:2026-06"],
                    "reason": "pending_invoice_rules_changed",
                    "schedule_warmup": False,
                    "persist_empty": False,
                }
            ],
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

    def test_execute_all_scope_uses_all_invalidation_without_warmup_fallback_when_gateway_unavailable(self) -> None:
        runtime = _RuntimeRecorder()
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda _scope_keys, **_kwargs: False,
            can_enqueue_refresh=lambda: False,
        )

        result = executor.execute(
            {"scope_keys": ["all"], "reason": "settings_project_status_changed"},
            schedule_warmup=True,
        )

        self.assertEqual(
            runtime.invalidate_all_calls,
            [{"schedule_warmup": True, "persist_empty": True}],
        )
        self.assertEqual(runtime.invalidate_scope_calls, [])
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 2},
                "invalidated_scopes": ["active:all", "all:all"],
                "enqueued_jobs": [],
            },
        )

    def test_execute_no_scope_refresh_fallback_defaults_to_all(self) -> None:
        runtime = _RuntimeRecorder()
        runtime.invalidate_scopes_result = []
        enqueued: list[dict[str, object]] = []
        executor = CostStatisticsDerivedLifecycleExecutor(
            runtime_service=runtime,
            enqueue_refresh=lambda scope_keys, **kwargs: enqueued.append(
                {"scope_keys": list(scope_keys), **dict(kwargs)}
            ) or False,
            can_enqueue_refresh=lambda: True,
        )

        result = executor.execute({}, schedule_warmup=False)

        self.assertEqual(
            runtime.invalidate_scope_calls,
            [
                {
                    "scope_keys": [],
                    "reason": "derived_lifecycle_cost_statistics",
                    "schedule_warmup": False,
                    "persist_empty": True,
                }
            ],
        )
        self.assertEqual(
            enqueued,
            [{"scope_keys": ["all"], "reason": "derived_lifecycle_cost_statistics", "metadata": None}],
        )
        self.assertEqual(
            result,
            {
                "deleted_counts": {"cost_statistics_read_models": 1},
                "invalidated_scopes": ["all"],
                "enqueued_jobs": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
