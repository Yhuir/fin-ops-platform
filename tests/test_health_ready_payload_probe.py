from __future__ import annotations

import gzip
import json
from time import sleep
import unittest

from fin_ops_platform.tools.health_ready_payload_probe import (
    collect_health_ready_payload,
    resolve_health_ready_url,
)
from fin_ops_platform.tools.http_slo_probe import HttpProbeResponse


class HealthReadyPayloadProbeTests(unittest.TestCase):
    def test_passes_for_bounded_ready_payload(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            request_fn=lambda _url, _headers, _timeout: _json_response(
                {
                    "status": "ready",
                    "api_performance": {
                        "endpoint_count": 25,
                        "omitted_endpoint_count": 5,
                        "endpoints": {f"GET /api/example-{index}": {} for index in range(20)},
                    },
                }
            ),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["url"], "https://example.test/fin-ops-api/health/ready")
        self.assertEqual(report["api_performance_endpoints_returned"], 20)
        self.assertEqual(report["api_performance_endpoint_count"], 25)
        self.assertEqual(report["api_performance_omitted_endpoint_count"], 5)
        self.assertEqual(report["errors"], [])

    def test_decodes_gzip_ready_payload(self) -> None:
        payload = {
            "status": "ready",
            "api_performance": {
                "endpoint_count": 1,
                "omitted_endpoint_count": 0,
                "endpoints": {"GET /api/example": {}},
            },
        }
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json", "content-encoding": "gzip"},
                body=gzip.compress(json.dumps(payload).encode("utf-8")),
            ),
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["health_status"], "ready")
        self.assertEqual(report["errors"], [])

    def test_fails_for_unbounded_api_performance_payload(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: _json_response(
                {
                    "status": "ready",
                    "api_performance": {
                        "window_sample_limit": 512,
                        "total_sample_count": 2700,
                        "endpoints": {f"GET /api/example-{index}": {} for index in range(21)},
                    },
                }
            ),
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("api_performance_endpoints_unbounded", report["errors"])
        self.assertIn("api_performance_bound_metadata_missing", report["errors"])

    def test_consumes_authoritative_readiness_blockers(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: _json_response(
                {
                    "status": "ready",
                    "runtime_release": {
                        "release_metadata": {
                            "release_name": "main-abc-20260616",
                        }
                    },
                    "runtime_infrastructure": {
                        "queue_backlog": {"dead_lettered": 3},
                        "dirty_scopes": {"done": 130021, "pending": 3},
                        "failed_jobs": 3,
                        "worker_metrics": [
                            {"status": "available"},
                            {"status": "stale"},
                        ],
                    },
                    "readiness_blockers": {
                        "required_worker_stale": 1,
                        "critical_outbox_failed": 3,
                    },
                    "api_performance": {
                        "endpoint_count": 1,
                        "omitted_endpoint_count": 0,
                        "endpoints": {"GET /api/example": {}},
                    },
                }
            ),
        )

        self.assertEqual(report["runtime_release_name"], "main-abc-20260616")
        self.assertEqual(
            report["runtime_blockers"],
            {"required_worker_stale": 1, "critical_outbox_failed": 3},
        )
        self.assertEqual(report["runtime_blocker_count"], 2)

    def test_does_not_infer_blockers_from_diagnostic_counts(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: _json_response(
                {
                    "status": "ready",
                    "runtime_infrastructure": {
                        "queue_backlog": {"done": 20},
                        "dirty_scopes": {"done": 100},
                        "worker_metric_count": 2,
                        "worker_status_counts": {"available": 1, "mismatch": 1},
                    },
                    "api_performance": {
                        "endpoint_count": 1,
                        "omitted_endpoint_count": 0,
                        "endpoints": {"GET /api/example": {}},
                    },
                }
            ),
        )

        self.assertEqual(report["runtime_blockers"], {})

    def test_fails_for_503_not_ready_with_authoritative_blockers(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: _json_response(
                {
                    "status": "not_ready",
                    "readiness_blockers": {"required_worker_missing": 6},
                    "api_performance": {
                        "endpoint_count": 1,
                        "omitted_endpoint_count": 0,
                        "endpoints": {"GET /health/ready": {}},
                    },
                },
                status_code=503,
            ),
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["health_status"], "not_ready")
        self.assertEqual(report["runtime_blockers"], {"required_worker_missing": 6})
        self.assertIn("unexpected_status:503", report["errors"])
        self.assertIn("health_status_not_ready", report["errors"])

    def test_fails_for_slow_or_large_payload(self) -> None:
        def slow_large_response(_url: str, _headers: dict[str, str], _timeout: float) -> HttpProbeResponse:
            sleep(0.005)
            return _json_response({
                "status": "ready",
                "api_performance": {
                    "endpoint_count": 1,
                    "omitted_endpoint_count": 0,
                    "endpoints": {"GET /api/example": {}},
                },
                "padding": "x" * 200,
            })

        report = collect_health_ready_payload(
            base_url="https://example.test",
            target_ms=1,
            max_response_bytes=100,
            request_fn=slow_large_response,
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("slo_miss", report["errors"])
        self.assertIn("response_too_large", report["errors"])

    def test_fails_for_html_fallback(self) -> None:
        report = collect_health_ready_payload(
            base_url="https://example.test",
            request_fn=lambda _url, _headers, _timeout: HttpProbeResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html></html>",
            ),
        )

        self.assertEqual(report["status"], "fail")
        self.assertIn("html_response_for_health_ready_probe", report["errors"])

    def test_resolve_health_ready_url_prefixes_non_api_health_paths(self) -> None:
        self.assertEqual(
            resolve_health_ready_url("https://example.test/root", "/health/ready", api_prefix="/fin-ops-api"),
            "https://example.test/root/fin-ops-api/health/ready",
        )
        self.assertEqual(
            resolve_health_ready_url("https://example.test", "/fin-ops-api/health/ready", api_prefix="/fin-ops-api"),
            "https://example.test/fin-ops-api/health/ready",
        )


def _json_response(payload: dict[str, object], *, status_code: int = 200) -> HttpProbeResponse:
    return HttpProbeResponse(
        status_code=status_code,
        headers={"content-type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


if __name__ == "__main__":
    unittest.main()
