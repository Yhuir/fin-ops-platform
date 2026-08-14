from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import sync_slo_baseline


class FakeRuntimeMonitoringRepository:
    def __init__(self, connection):
        self.connection = connection

    def health_summary(self):
        return {
            "queue_backlog": {"done": 10},
            "failed_jobs": 0,
        }

    def app_status_runtime_snapshot(self):
        return {
            "outbox_statuses": {
                "oa.sync": {"status": "ready"},
                "import.process.requested": {"status": "failed", "last_error": "import failed"},
            },
            "worker_statuses": {
                "oa-sync": {"status": "ready"},
                "import": {"status": "unavailable"},
            },
        }

    def dashboard_worker_metrics(self):
        return [{"worker_instance": "oa-sync", "status": "ready"}]

    def dashboard_queue_metrics(self):
        return [{"event_type": "oa.sync", "messages": 0, "dlq_messages": 0}]

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
                    "schema_name": "app",
                    "table_name": "workbench_pair_relations",
                    "total_bytes": 1024,
                    "estimated_rows": 20,
                    "seq_scan": 1,
                    "idx_scan": 2,
                }
            ]
        if "from pg_stat_user_indexes" in normalized:
            return [
                {
                    "schema_name": "app",
                    "table_name": "workbench_pair_relations",
                    "index_name": "workbench_pair_relations_pkey",
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
                    "query": "select relation_id from app.workbench_pair_relations where tenant_id = $1",
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
        self.assertEqual(payload["evidence_bands"]["current_production"]["status"], "measured")
        self.assertFalse(payload["evidence_bands"]["current_production"]["release_blocked"])
        self.assertEqual(payload["evidence_bands"]["target_scale"]["status"], "not_measured")
        self.assertTrue(payload["evidence_bands"]["target_scale"]["requires_isolated_database"])
        self.assertEqual(
            payload["evidence_bands"]["target_scale"]["required_rows"],
            {"bank_transactions": 1_000_000, "invoices": 500_000, "oa": 1_000_000, "relations": 500_000},
        )
        self.assertEqual(payload["slo_targets"]["canonical_api_read_p99_ms"], 1000)
        self.assertNotIn("heavy_workbench_local_convergence_p95_ms", payload["slo_targets"])
        self.assertEqual(payload["runtime_health"]["data"]["failed_jobs"], 0)
        self.assertIn("import.process.requested", payload["runtime_snapshot"]["data"]["outbox_attention"])
        self.assertIn("import", payload["runtime_snapshot"]["data"]["worker_attention"])
        self.assertEqual(payload["postgres_connections"]["data"]["max_connections"], 100)
        self.assertEqual(payload["postgres_table_sizes"]["data"][0]["schema_name"], "app")
        self.assertEqual(payload["postgres_table_sizes"]["data"][0]["table_name"], "workbench_pair_relations")
        self.assertIn("app.workbench_pair_relations", payload["pg_stat_statements"]["data"]["rows"][0]["query"])
        self.assertNotIn("read_model.workbench_groups", json.dumps(payload, sort_keys=True))
        self.assertTrue(payload["pg_stat_statements"]["data"]["installed"])
        self.assertEqual(payload["explain_probes"]["status"], "available")
        self.assertEqual(payload["explain_probes"]["data"][0]["node_type"], "Aggregate")
        self.assertEqual(payload["api_performance"]["status"], "not_collected")

    def test_collect_baseline_fails_closed_when_critical_sections_are_unavailable(self) -> None:
        unavailable = {"status": "unavailable", "error": "database unavailable"}
        with (
            patch.object(sync_slo_baseline, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository),
            patch.object(sync_slo_baseline, "_safe_section", return_value=unavailable),
        ):
            payload = sync_slo_baseline.collect_baseline(FakeConnection(), limit=5)

        current = payload["evidence_bands"]["current_production"]
        self.assertEqual(current["status"], "not_measured")
        self.assertTrue(current["release_blocked"])
        self.assertIn("runtime_health", current["reason"])
        self.assertIn("postgres_index_usage", current["reason"])

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
