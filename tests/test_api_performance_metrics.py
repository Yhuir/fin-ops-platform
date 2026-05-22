from __future__ import annotations

import unittest

from fin_ops_platform.services.api_performance_metrics import (
    ApiPerformanceRecorder,
    current_request_database_metrics,
    record_database_connection_acquire,
    record_database_query,
    request_database_timing,
)


class ApiPerformanceMetricsTests(unittest.TestCase):
    def test_recorder_reports_request_and_database_p95_by_endpoint(self) -> None:
        recorder = ApiPerformanceRecorder(max_samples_per_endpoint=50)
        for index in range(1, 21):
            recorder.record_request(
                method="GET",
                route_path="/api/workbench/groups",
                status_code=200,
                duration_ms=float(index),
                connection_acquire_duration_ms=float(index / 2),
                sql_execute_fetch_duration_ms=float(index * 1.5),
                database_duration_ms=float(index * 2),
                database_query_count=index % 3,
            )

        summary = recorder.summary()

        endpoint = summary["endpoints"]["GET /api/workbench/groups"]
        self.assertEqual(endpoint["sample_count"], 20)
        self.assertEqual(endpoint["duration_ms"], {"p50": 10.0, "p95": 19.0, "p99": 20.0})
        self.assertEqual(endpoint["connection_acquire_ms"], {"p50": 5.0, "p95": 9.5, "p99": 10.0})
        self.assertEqual(endpoint["sql_execute_fetch_ms"], {"p50": 15.0, "p95": 28.5, "p99": 30.0})
        self.assertEqual(endpoint["database_duration_ms"], {"p50": 20.0, "p95": 38.0, "p99": 40.0})
        self.assertEqual(endpoint["database_query_count"], {"p50": 1.0, "p95": 2.0, "p99": 2.0})
        self.assertEqual(endpoint["last_status_code"], 200)

    def test_database_timing_context_tracks_only_current_request(self) -> None:
        record_database_query(100.0)
        self.assertIsNone(current_request_database_metrics())

        with request_database_timing() as timing:
            record_database_connection_acquire(3.0)
            record_database_query(12.5)
            record_database_query(7.25)
            metrics = current_request_database_metrics()

        self.assertIs(metrics, timing)
        self.assertEqual(timing.query_count, 2)
        self.assertEqual(timing.connection_acquire_duration_ms, 3.0)
        self.assertEqual(timing.sql_execute_fetch_duration_ms, 19.75)
        self.assertEqual(timing.total_duration_ms, 22.75)
        self.assertEqual(timing.max_query_duration_ms, 12.5)
        self.assertIsNone(current_request_database_metrics())


if __name__ == "__main__":
    unittest.main()
