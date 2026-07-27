from __future__ import annotations

import unittest
from unittest.mock import patch

from fin_ops_platform.tools import sync_slo_baseline


class FakeRuntimeMonitoringRepository:
    def __init__(self, connection):
        self.connection = connection

    def health_summary(self):
        return {
            "queue_backlog": {"done": 10},
            "dirty_scopes": {"done": 9},
            "failed_jobs": 0,
        }

    def app_status_runtime_snapshot(self):
        return {
            "read_model_statuses": {
                "workbench_relation": {"status": "fresh"},
                "search": {"status": "failed", "last_error": "projection failed"},
            },
            "outbox_statuses": {"workbench_relation.read_model.refresh": {"status": "ready"}},
            "worker_statuses": {"workbench-relation": {"status": "ready"}},
        }

    def dashboard_read_model_metrics(self):
        return [
            {
                "key": "workbench_relation",
                "refresh_duration_ms": {"p95": 1200.0},
                "historical_refresh_duration_ms": {"p95": 24000.0},
            }
        ]

    def dashboard_worker_metrics(self):
        return [{"worker_instance": "workbench-relation", "status": "ready"}]

    def dashboard_queue_metrics(self):
        return [{"event_type": "workbench_relation.read_model.refresh", "messages": 0, "dlq_messages": 0}]

    def dashboard_outbox_metric(self):
        return {"pending_count": 0, "failed_count": 0, "status": "available"}


class FakeConnection:
    def __init__(
        self,
        *,
        pg_stat_metric_version: str = "total_exec_time",
        pg_stat_query_error: Exception | None = None,
    ) -> None:
        self.pg_stat_metric_version = pg_stat_metric_version
        self.pg_stat_query_error = pg_stat_query_error
        self.fetch_one_calls: list[str] = []
        self.fetch_all_calls: list[str] = []

    def fetch_one(self, sql: str, params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append(normalized)
        if "from pg_stat_activity" in normalized and "current_setting" in normalized:
            return {
                "total_connections": 7,
                "active_connections": 2,
                "waiting_connections": 0,
                "max_connections": 100,
            }
        if "from pg_extension" in normalized:
            return {"installed": True}
        if normalized.startswith("explain"):
            return {
                "QUERY PLAN": [
                    {
                        "Plan": {
                            "Node Type": "Aggregate",
                            "Startup Cost": 1.0,
                            "Total Cost": 2.0,
                            "Plan Rows": 1,
                            "Plan Width": 8,
                        },
                        "Planning Time": 0.1,
                    }
                ]
            }
        raise AssertionError(sql)

    def fetch_all(self, sql: str, params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append(normalized)
        if "from pg_stat_activity" in normalized and "group by coalesce(state" in normalized:
            return [{"state": "active", "count": 2}, {"state": "idle", "count": 5}]
        if "from pg_stat_activity" in normalized and "application_name" in normalized:
            return [{"application_name": "finops", "count": 7}]
        if "pg_total_relation_size" in normalized:
            return [
                {
                    "schema_name": "read_model",
                    "table_name": "workbench_groups",
                    "total_bytes": 1024,
                    "estimated_rows": 20,
                    "seq_scan": 1,
                    "idx_scan": 2,
                }
            ]
        if "from pg_stat_user_indexes" in normalized:
            return [
                {
                    "schema_name": "read_model",
                    "table_name": "workbench_groups",
                    "index_name": "workbench_groups_idx",
                    "index_bytes": 512,
                    "idx_scan": 0,
                }
            ]
        if "from information_schema.columns" in normalized and "pg_stat_statements" in normalized:
            if self.pg_stat_metric_version == "total_time":
                return [{"column_name": "query"}, {"column_name": "total_time"}, {"column_name": "mean_time"}]
            if self.pg_stat_metric_version == "unsupported":
                return [{"column_name": "query"}, {"column_name": "calls"}]
            return [{"column_name": "query"}, {"column_name": "total_exec_time"}, {"column_name": "mean_exec_time"}]
        if (
            "from pg_stat_statements" in normalized
            and "total_exec_time" in normalized
            and "total_time as total_exec_time" not in normalized
        ):
            if self.pg_stat_query_error is not None:
                raise self.pg_stat_query_error
            return [
                {
                    "query": "select * from read_model.workbench_groups where scope_key = $1",
                    "calls": 3,
                    "total_exec_time": 30.0,
                    "mean_exec_time": 10.0,
                    "rows": 9,
                }
            ]
        if "from pg_stat_statements" in normalized and "total_time as total_exec_time" in normalized:
            if self.pg_stat_query_error is not None:
                raise self.pg_stat_query_error
            return [
                {
                    "query": "select count(*) from job.outbox_events",
                    "calls": 2,
                    "total_exec_time": 12.0,
                    "mean_exec_time": 6.0,
                    "rows": 2,
                }
            ]
        raise AssertionError(sql)


class SyncSloBaselineTests(unittest.TestCase):
    def test_collect_baseline_combines_runtime_database_and_explain_sections(self) -> None:
        with patch.object(sync_slo_baseline, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository):
            payload = sync_slo_baseline.collect_baseline(FakeConnection(), limit=5)

        self.assertEqual(payload["mode"], "read_only")
        self.assertEqual(payload["runtime_health"]["data"]["failed_jobs"], 0)
        self.assertIn("search", payload["runtime_snapshot"]["data"]["read_model_attention"])
        self.assertNotIn("cost_statistics", payload["runtime_snapshot"]["data"]["read_model_attention"])
        self.assertEqual(payload["postgres_connections"]["data"]["max_connections"], 100)
        self.assertEqual(payload["postgres_table_sizes"]["data"][0]["table_name"], "workbench_groups")
        self.assertTrue(payload["pg_stat_statements"]["data"]["installed"])
        self.assertEqual(payload["explain_probes"]["status"], "available")
        self.assertEqual(payload["explain_probes"]["data"][0]["node_type"], "Aggregate")
        self.assertEqual(payload["api_performance"]["status"], "not_collected")

    def test_pg_stat_statements_falls_back_to_legacy_time_columns(self) -> None:
        result = sync_slo_baseline._pg_stat_statements(
            FakeConnection(pg_stat_metric_version="total_time"),
            limit=5,
        )

        self.assertEqual(result["metric_version"], "pg_stat_statements_total_time")
        self.assertEqual(result["rows"][0]["query"], "select count(*) from job.outbox_events")

    def test_pg_stat_statements_reports_real_unloaded_extension_error(self) -> None:
        result = sync_slo_baseline._safe_section(
            lambda: sync_slo_baseline._pg_stat_statements(
                FakeConnection(
                    pg_stat_query_error=RuntimeError("pg_stat_statements must be loaded via shared_preload_libraries")
                ),
                limit=5,
            )
        )

        self.assertEqual(result["status"], "unavailable")
        self.assertIn("shared_preload_libraries", result["error"])


if __name__ == "__main__":
    unittest.main()
