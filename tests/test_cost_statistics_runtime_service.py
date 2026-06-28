import unittest


class RedisRecorder:
    def __init__(self) -> None:
        self.deletes: list[str] = []

    def delete(self, key: str) -> bool:
        self.deletes.append(key)
        return True


class CostStatisticsRuntimeServiceTests(unittest.TestCase):
    def test_invalidating_scope_marks_dirty_even_when_no_cached_model_exists(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        redis = RedisRecorder()
        service = CostStatisticsRuntimeService(
            redis_helper=redis,
            source_versions_provider=lambda scope_key: {"scope": scope_key},
        )

        deleted = service.invalidate_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertIn("cost_statistics:explorer:active:2026-05", redis.deletes)
        self.assertIn("cost_statistics:month:active:2026-05", redis.deletes)
        self.assertTrue(any(":schema:2026-05-cost-statistics-explorer-v1:sources:" in key for key in redis.deletes))

    def test_enqueue_refresh_for_months_only_clears_cache_for_direct_api_reads(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        redis = RedisRecorder()
        service = CostStatisticsRuntimeService(
            redis_helper=redis,
            source_versions_provider=lambda scope_key: {"scope": scope_key},
        )

        enqueued = service.enqueue_refresh_for_months(["2026-05"], reason="unit_test")

        self.assertFalse(enqueued)
        self.assertTrue(redis.deletes)

    def test_scope_key_normalization_rejects_unknown_project_scopes(self) -> None:
        from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

        service = CostStatisticsRuntimeService()

        self.assertEqual(
            service.normalize_scope_keys(["active:2026-05", "all:2026-05", "finished:2026-05", "active:202605"]),
            ["active:2026-05", "all:2026-05"],
        )


if __name__ == "__main__":
    unittest.main()
