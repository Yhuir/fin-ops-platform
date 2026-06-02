from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_query_gateway import ReadModelQueryGateway


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.refreshes.append(dict(kwargs))


class RedisRecorder:
    def __init__(self, value: dict[str, object] | None = None) -> None:
        self.value = value
        self.gets: list[str] = []
        self.sets: list[tuple[str, dict[str, object], int]] = []

    def get_json(self, key: str) -> dict[str, object] | None:
        self.gets.append(key)
        return self.value

    def set_json(self, key: str, value: dict[str, object], *, ttl_seconds: int) -> bool:
        self.sets.append((key, value, ttl_seconds))
        return True


class ReadModelQueryGatewayTests(unittest.TestCase):
    def test_fresh_cache_hit_does_not_call_sql_or_enqueue_refresh(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder({"payload": {"rows": [{"id": "cached"}]}})
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: (_ for _ in ()).throw(AssertionError("SQL should not be called on cache hit")),
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [{"id": "cached"}])
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(result.payload["read_model_scope_key"], "all")
        self.assertTrue(result.cache_hit)
        self.assertFalse(result.refresh_enqueued)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(redis.gets, ["example:all:v3"])

    def test_stale_sql_view_enqueues_refresh_without_populating_cache(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: {
                "payload": {"rows": [{"id": "stale"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 2},
                "generated_at": "2026-05-21T09:00:00+00:00",
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3",
            cache_ttl_seconds=60,
            stale_reason="api_stale",
            source_mismatch_reason="api_source_versions_stale",
        )

        self.assertEqual(result.payload["rows"], [{"id": "stale"}])
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["source_version_mismatch"])
        self.assertEqual(result.payload["refresh_reason"], "source_version_mismatch")
        self.assertTrue(result.refresh_enqueued)
        self.assertFalse(result.cache_hit)
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "example", "scope_key": "all", "reason": "api_source_versions_stale"}],
        )
        self.assertEqual(redis.sets, [])

    def test_missing_sql_view_returns_refreshing_empty_payload_and_enqueues_miss(self) -> None:
        queue = QueueRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: None,
            empty_payload_factory=lambda: {"rows": [], "summary": {"row_count": 0}},
            missing_reason="api_miss",
        )

        self.assertEqual(result.payload["rows"], [])
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_scope_key"], "all")
        self.assertEqual(result.payload["source_versions"], {"source_version": "3"})
        self.assertEqual(result.payload["refresh_reason"], "api_miss")
        self.assertTrue(result.refresh_enqueued)
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "example", "scope_key": "all", "reason": "api_miss"}],
        )


if __name__ == "__main__":
    unittest.main()
