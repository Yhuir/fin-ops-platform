import unittest


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class RedisRecorder:
    def __init__(self) -> None:
        self.deletes: list[str] = []

    def delete(self, key: str) -> bool:
        self.deletes.append(key)
        return True


class EmptyCostReadModelService:
    def invalidate_months(self, *_args, **_kwargs) -> list[str]:
        return []

    def snapshot(self) -> dict[str, object]:
        return {"read_models": {}}

    def scope_key(self, month: str, project_scope: str) -> str:
        return f"{project_scope}:{month}"


class CostStatisticsRuntimeServiceTests(unittest.TestCase):
    def test_invalidating_scope_marks_dirty_even_when_no_cached_model_exists(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        queue = QueueRecorder()
        redis = RedisRecorder()
        service = CostStatisticsRuntimeService(
            read_model_service=EmptyCostReadModelService(),
            queue_repository=queue,
            redis_helper=redis,
            persist_read_models=lambda **_kwargs: None,
            source_versions_provider=lambda scope_key: {"scope": scope_key},
        )

        deleted = service.invalidate_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )
        self.assertIn("cost_statistics:explorer:active:2026-05", redis.deletes)
        self.assertIn("cost_statistics:month:active:2026-05", redis.deletes)
        self.assertTrue(any(":schema:2026-05-cost-statistics-explorer-v1:sources:" in key for key in redis.deletes))

    def test_scope_key_normalization_rejects_unknown_project_scopes(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        service = CostStatisticsRuntimeService(read_model_service=EmptyCostReadModelService())

        self.assertEqual(
            service.normalize_scope_keys(["active:2026-05", "all:2026-05", "finished:2026-05", "active:202605"]),
            ["active:2026-05", "all:2026-05"],
        )


if __name__ == "__main__":
    unittest.main()
