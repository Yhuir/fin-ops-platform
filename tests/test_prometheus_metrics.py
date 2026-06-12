from __future__ import annotations

import unittest

from fin_ops_platform.services.prometheus_metrics import render_prometheus_metrics


class PrometheusMetricsTests(unittest.TestCase):
    def test_render_prometheus_metrics_exports_runtime_api_and_worker_metrics(self) -> None:
        payload = {
            "status": "ready",
            "runtime_release": {
                "consistent": True,
                "release_metadata": {"release_name": "main-test"},
            },
            "production_runtime_guard": {
                "consistent": True,
                "storage_backend": "postgres",
                "bootstrap_mode": "production",
            },
            "storage": {
                "postgres_schema_version": 68,
                "redis_hit_count": 3,
                "redis_miss_count": 2,
            },
            "runtime_infrastructure": {
                "queue_backlog": {"pending": 4, "failed": 1},
                "dirty_scopes": {"pending": 2},
                "failed_jobs": 1,
                "oldest_pending_event_age_seconds": 12.5,
                "worker_heartbeat_lag_seconds": 8.0,
                "missing_required_worker_count": 0,
                "stale_required_worker_count": 0,
                "mismatched_required_worker_count": 0,
                "read_model_refresh_duration_ms": {"p50": 100.0, "p95": 300.0, "p99": 450.0},
                "read_model_refresh_sample_count": 128,
                "read_model_refresh_failure_rate": 0.01,
                "rabbitmq_publish_status": {"unpublished": 1},
                "rabbitmq_queue_depth": 5,
                "rabbitmq_unacked_messages": 1,
                "rabbitmq_consumer_count": 15,
                "rabbitmq_dlq_count": 0,
                "rabbitmq_publish_confirm_latency_ms": {"p50": 2.0, "p95": 9.0, "p99": 15.0},
                "rabbitmq_publish_confirm_sample_limit": 512,
                "stale_dirty_scope_count": 0,
                "worker_metrics": [
                    {
                        "worker_instance": "workbench",
                        "worker_kind": "workbench-read-model",
                        "status": "available",
                        "heartbeat_lag_seconds": 2.5,
                        "required": True,
                        "current_effective": True,
                    }
                ],
                "workbench_read_model": {
                    "active_scope_count": 9,
                    "active_row_count": 100,
                    "active_group_count": 50,
                    "active_summary_count": 9,
                    "building_scope_count": 0,
                    "failed_scope_count": 0,
                },
            },
            "api_performance": {
                "endpoints": {
                    "GET /api/workbench/summary": {
                        "sample_count": 10,
                        "last_status_code": 200,
                        "duration_ms": {"p50": 50.0, "p95": 90.0, "p99": 100.0},
                        "connection_acquire_ms": {"p50": 1.0, "p95": 2.0, "p99": 3.0},
                        "sql_execute_fetch_ms": {"p50": 10.0, "p95": 20.0, "p99": 30.0},
                        "database_duration_ms": {"p50": 11.0, "p95": 22.0, "p99": 33.0},
                        "database_query_count": {"p50": 2, "p95": 3, "p99": 4},
                    }
                }
            },
        }

        rendered = render_prometheus_metrics(payload)

        self.assertIn("# TYPE finops_ready gauge", rendered)
        self.assertIn('finops_ready{status="ready"} 1', rendered)
        self.assertIn('finops_runtime_release_consistent{release="main-test"} 1', rendered)
        self.assertIn('finops_outbox_events{status="pending"} 4', rendered)
        self.assertIn('finops_read_model_dirty_scopes{status="pending"} 2', rendered)
        self.assertIn('finops_read_model_refresh_duration_ms{quantile="0.95"} 300', rendered)
        self.assertIn("finops_read_model_refresh_sample_count 128", rendered)
        self.assertIn('finops_rabbitmq_publish_confirm_latency_ms{quantile="0.95"} 9', rendered)
        self.assertIn("finops_rabbitmq_publish_confirm_sample_limit 512", rendered)
        self.assertIn(
            'finops_worker_heartbeat_lag_seconds{status="available",worker_instance="workbench",worker_kind="workbench-read-model"} 2.5',
            rendered,
        )
        self.assertIn('finops_api_duration_ms{endpoint="GET /api/workbench/summary",quantile="0.95"} 90', rendered)
        self.assertIn('finops_postgres_schema_version 68', rendered)
        self.assertIn('finops_redis_hit_total 3', rendered)

    def test_render_prometheus_metrics_escapes_label_values(self) -> None:
        rendered = render_prometheus_metrics(
            {
                "status": "not_ready",
                "runtime_release": {
                    "consistent": False,
                    "release_metadata": {"release_name": 'main"bad\\name'},
                },
            }
        )

        self.assertIn('release="main\\"bad\\\\name"', rendered)


if __name__ == "__main__":
    unittest.main()
