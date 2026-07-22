from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_query_gateway import ReadModelQueryGateway


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[dict[str, object]] = []
        self.active_refreshes: set[tuple[str, str, str]] = set()
        self.active_checks: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.refreshes.append(dict(kwargs))

    def read_model_refresh_is_active(self, *, tenant_id: str, scope_type: str, scope_key: str) -> bool:
        key = (tenant_id, scope_type, scope_key)
        self.active_checks.append(key)
        return key in self.active_refreshes


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
    def test_load_requires_expected_freshness_contract(self) -> None:
        gateway = ReadModelQueryGateway(queue_repository=QueueRecorder())

        with self.assertRaisesRegex(ValueError, "expected_source_versions or expected_schema_version"):
            gateway.load(
                scope_type="example",
                scope_key="all",
                load_view=lambda: {"payload": {"rows": []}, "refresh_status": "fresh"},
                empty_payload_factory=lambda: {"rows": []},
            )

    def test_fresh_cache_hit_requires_current_view_proof_and_does_not_enqueue_refresh(self) -> None:
        queue = QueueRecorder()
        view_loads: list[str] = []
        redis = RedisRecorder(
            {
                "payload": {
                    "rows": [{"id": "cached"}],
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                },
                "fresh_gate": {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                },
            }
        )
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: (_ for _ in ()).throw(AssertionError("full payload must not load on a cache hit")),
            load_freshness_view=lambda: (
                view_loads.append("loaded")
                or {
                    "payload": {},
                    "refresh_status": "fresh",
                    "source_versions": {"source_version": 3},
                }
            ),
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [{"id": "cached"}])
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(result.payload["read_model_scope_key"], "all")
        self.assertFalse(result.payload["refresh_enqueued"])
        self.assertTrue(result.cache_hit)
        self.assertFalse(result.refresh_enqueued)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(view_loads, ["loaded"])
        self.assertEqual(redis.gets, ["example:all:v3"])

    def test_matching_cache_is_not_consumed_when_current_view_is_dirty(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder(
            {
                "payload": {"rows": [{"id": "cached"}]},
                "fresh_gate": {
                    "scope_key": "2026-05",
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                },
            }
        )
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="bank_detail",
            scope_key="2026-05",
            expected_source_versions={"source_version": 3},
            load_freshness_view=lambda: {
                "payload": {},
                "refresh_status": "processing",
                "source_versions": {"source_version": 3},
            },
            load_view=lambda: {
                "payload": {"rows": [{"id": "sql-stale"}]},
                "refresh_status": "processing",
                "source_versions": {"source_version": 3},
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="bank-detail:2026-05:v3",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [{"id": "sql-stale"}])
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertFalse(result.cache_hit)
        self.assertEqual(redis.gets, [])
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "bank_detail", "scope_key": "2026-05", "reason": "api_stale"}],
        )

    def test_cache_missing_expected_schema_misses_and_uses_sql_view(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder(
            {
                "payload": {
                    "rows": [{"id": "cached"}],
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                },
                "fresh_gate": {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                },
            }
        )
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            expected_schema_version="schema-v2",
            load_view=lambda: {
                "payload": {"rows": [{"id": "sql"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
                "schema_version": "schema-v2",
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3:schema-v2",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [{"id": "sql"}])
        self.assertFalse(result.cache_hit)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(len(redis.sets), 1)

    def test_invalid_fresh_cache_payload_contract_misses_and_uses_sql_view(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder(
            {
                "payload": {
                    "rows": [{"id": "legacy"}],
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                    "schema_version": "schema-v2",
                },
                "fresh_gate": {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "source_versions": {"source_version": "3"},
                    "schema_version": "schema-v2",
                },
            }
        )
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            expected_schema_version="schema-v2",
            load_view=lambda: {
                "payload": {"items": [{"id": "sql"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
                "schema_version": "schema-v2",
            },
            empty_payload_factory=lambda: {"items": []},
            payload_validator=lambda payload: isinstance(payload.get("items"), list),
            cache_key="example:all:v3:schema-v2",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["items"], [{"id": "sql"}])
        self.assertFalse(result.cache_hit)
        self.assertFalse(result.refresh_enqueued)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(len(redis.sets), 1)

    def test_legacy_cache_without_fresh_gate_or_source_versions_misses_and_repopulates(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder({"payload": {"rows": [{"id": "legacy"}], "read_model_status": "fresh"}})
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: {
                "payload": {"rows": [{"id": "sql"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [{"id": "sql"}])
        self.assertFalse(result.cache_hit)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(len(redis.sets), 1)

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

    def test_missing_sql_view_schema_enqueues_refresh_without_populating_cache(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_schema_version="schema-v2",
            expected_source_versions={"source_version": 3},
            load_view=lambda: {
                "payload": {"rows": [{"id": "missing-schema"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3:schema-v2",
            cache_ttl_seconds=60,
            source_mismatch_reason="api_source_versions_stale",
        )

        self.assertEqual(result.payload["rows"], [{"id": "missing-schema"}])
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["schema_version_missing"])
        self.assertEqual(result.payload["refresh_reason"], "source_version_mismatch")
        self.assertTrue(result.refresh_enqueued)
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

    def test_missing_sql_view_does_not_report_new_enqueue_when_scope_is_already_active(self) -> None:
        queue = QueueRecorder()
        queue.active_refreshes.add(("default", "example", "all"))
        gateway = ReadModelQueryGateway(queue_repository=queue)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: None,
            empty_payload_factory=lambda: {"rows": [], "summary": {"row_count": 0}},
            missing_reason="api_miss",
        )

        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertFalse(result.payload["refresh_enqueued"])
        self.assertFalse(result.refresh_enqueued)
        self.assertEqual(queue.active_checks, [("default", "example", "all")])
        self.assertEqual(queue.refreshes, [])

    def test_invalid_sql_payload_contract_enqueues_refresh_without_populating_cache(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: {
                "payload": {"rows": [{"id": "legacy"}]},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
                "schema_version": "schema-v2",
                "generated_at": "2026-05-21T09:00:00+00:00",
            },
            empty_payload_factory=lambda: {"rows": [], "summary": {"row_count": 0}},
            payload_validator=lambda payload: isinstance(payload.get("items"), list),
            payload_invalid_reason="api_payload_shape_invalid",
            expected_schema_version="schema-v2",
            cache_key="example:all:v3:schema-v2",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["rows"], [])
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["api_payload_shape_invalid"])
        self.assertEqual(result.payload["refresh_reason"], "api_payload_shape_invalid")
        self.assertTrue(result.refresh_enqueued)
        self.assertFalse(result.cache_hit)
        self.assertEqual(
            queue.refreshes,
            [{"scope_type": "example", "scope_key": "all", "reason": "api_payload_shape_invalid"}],
        )
        self.assertEqual(redis.sets, [])

    def test_cost_statistics_refresh_uses_registered_scope_policy_before_enqueue(self) -> None:
        queue = QueueRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue)

        result = gateway.load(
            scope_type="cost_statistics",
            scope_key="2026-05",
            expected_source_versions={"source_version": 3},
            load_view=lambda: None,
            empty_payload_factory=lambda: {"rows": []},
            missing_reason="api_miss",
        )

        self.assertTrue(result.refresh_enqueued)
        self.assertEqual(
            queue.refreshes,
            [
                {"scope_type": "cost_statistics", "scope_key": "active:2026-05", "reason": "api_miss"},
                {"scope_type": "cost_statistics", "scope_key": "all:2026-05", "reason": "api_miss"},
            ],
        )

    def test_fresh_sql_view_sets_refresh_enqueued_false_and_populates_cache(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        gateway = ReadModelQueryGateway(queue_repository=queue, redis_helper=redis)

        result = gateway.load(
            scope_type="example",
            scope_key="all",
            expected_source_versions={"source_version": 3},
            load_view=lambda: {
                "payload": {"rows": []},
                "refresh_status": "fresh",
                "source_versions": {"source_version": 3},
                "generated_at": "2026-05-21T09:00:00+00:00",
            },
            empty_payload_factory=lambda: {"rows": []},
            cache_key="example:all:v3",
            cache_ttl_seconds=60,
        )

        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertFalse(result.payload["refresh_enqueued"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(len(redis.sets), 1)
        self.assertEqual(redis.sets[0][1]["fresh_gate"]["scope_key"], "all")
        self.assertEqual(redis.sets[0][1]["fresh_gate"]["source_versions"], {"source_version": "3"})


if __name__ == "__main__":
    unittest.main()
