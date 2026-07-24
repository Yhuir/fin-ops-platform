import unittest


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.refresh_details: list[dict[str, object]] = []

    def enqueue_read_model_refresh(
        self,
        *,
        scope_type: str,
        scope_key: str,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.refreshes.append((scope_type, scope_key, reason))
        self.refresh_details.append(
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "reason": reason,
                "metadata": dict(metadata) if isinstance(metadata, dict) else None,
            }
        )


class CostStatisticsRuntimeServiceTests(unittest.TestCase):
    def test_invalidating_scope_only_marks_durable_scopes_dirty(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        queue = QueueRecorder()
        service = CostStatisticsRuntimeService(queue_repository=queue)

        invalidated = service.invalidate_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(invalidated, ["active:2026-05", "all:2026-05"])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )

    def test_enqueue_read_model_refresh_normalizes_legacy_month_scope(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        queue = QueueRecorder()
        service = CostStatisticsRuntimeService(queue_repository=queue)

        enqueued = service.enqueue_read_model_refresh("2026-05", reason="unit_test")

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )

    def test_global_invalidation_marks_parent_refreshes_as_explicit_force(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        queue = QueueRecorder()
        service = CostStatisticsRuntimeService(queue_repository=queue)

        invalidated = service.invalidate_read_models()

        self.assertEqual(invalidated, ["active:all", "all:all"])
        self.assertEqual(
            queue.refresh_details,
            [
                {
                    "scope_type": "cost_statistics",
                    "scope_key": "active:all",
                    "reason": "cost_statistics_read_model_invalidated",
                    "metadata": {"force_refresh": True},
                },
                {
                    "scope_type": "cost_statistics",
                    "scope_key": "all:all",
                    "reason": "cost_statistics_read_model_invalidated",
                    "metadata": {"force_refresh": True},
                },
            ],
        )

    def test_scope_key_normalization_rejects_unknown_project_scopes(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        service = CostStatisticsRuntimeService()

        self.assertEqual(
            service.normalize_scope_keys(["active:2026-05", "all:2026-05", "finished:2026-05", "active:202605"]),
            ["active:2026-05", "all:2026-05"],
        )

    def test_invalidation_without_durable_queue_does_not_claim_success(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        service = CostStatisticsRuntimeService()

        self.assertEqual(service.invalidate_read_models(), [])
        self.assertEqual(
            service.invalidate_read_model_scopes(["2026-05"], reason="unit_test"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
