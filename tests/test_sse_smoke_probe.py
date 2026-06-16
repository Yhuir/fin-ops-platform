from __future__ import annotations

import json
from unittest.mock import patch
import unittest

from fin_ops_platform.tools import sse_smoke_probe


class SseSmokeProbeTests(unittest.TestCase):
    def test_requires_auth_by_default_without_sampling(self) -> None:
        report = sse_smoke_probe.collect_sse_smoke(
            base_url="https://example.test",
            probes=[sse_smoke_probe.SseProbe("app", "/api/app-health/stream", ("app_health",))],
            headers={},
        )

        self.assertEqual(report["status"], "auth_missing")
        self.assertFalse(report["auth_configured"])

    def test_collects_default_sse_first_events_with_api_prefix(self) -> None:
        observed: list[str] = []

        def request_fn(url: str, headers, timeout_seconds: float, max_bytes: int) -> sse_smoke_probe.SseProbeResponse:
            observed.append(url)
            event_name = "app_health" if "app-health" in url else "workbench.read_model.completed"
            return sse_smoke_probe.SseProbeResponse(
                status_code=200,
                headers={
                    "content-type": "text/event-stream; charset=utf-8",
                    "cache-control": "no-cache, no-transform",
                    "x-accel-buffering": "no",
                },
                body=f"event: {event_name}\ndata: {{}}\n\n".encode("utf-8"),
            )

        report = sse_smoke_probe.collect_sse_smoke(
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["probe_count"], 2)
        self.assertEqual(observed[0], "https://example.test/fin-ops-api/api/app-health/stream")
        self.assertEqual(observed[1], "https://example.test/fin-ops-api/api/workbench/events?month=all")
        self.assertEqual(report["probes"][0]["event_names"], ["app_health"])
        self.assertEqual(report["probes"][1]["event_names"], ["workbench.read_model.completed"])
        self.assertNotIn("token", json.dumps(report))

    def test_rejects_html_shell_even_when_status_matches(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float, max_bytes: int) -> sse_smoke_probe.SseProbeResponse:
            return sse_smoke_probe.SseProbeResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>fin ops</body></html>",
            )

        report = sse_smoke_probe.collect_sse_smoke(
            base_url="https://example.test",
            probes=[sse_smoke_probe.SseProbe("app", "/api/app-health/stream", ("app_health",))],
            headers={"Cookie": "Admin-Token=token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["errors"], ["html_response_for_api_probe"])

    def test_unexpected_status_takes_precedence_over_html_body(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float, max_bytes: int) -> sse_smoke_probe.SseProbeResponse:
            return sse_smoke_probe.SseProbeResponse(
                status_code=401,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>login</body></html>",
            )

        report = sse_smoke_probe.collect_sse_smoke(
            base_url="https://example.test",
            probes=[sse_smoke_probe.SseProbe("app", "/api/app-health/stream", ("app_health",))],
            headers={"Cookie": "Admin-Token=token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["errors"], ["unexpected_status:401"])

    def test_missing_or_unexpected_event_fails(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float, max_bytes: int) -> sse_smoke_probe.SseProbeResponse:
            return sse_smoke_probe.SseProbeResponse(
                status_code=200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                body=b"event: other\ndata: {}\n\n",
            )

        report = sse_smoke_probe.collect_sse_smoke(
            base_url="https://example.test",
            probes=[sse_smoke_probe.SseProbe("app", "/api/app-health/stream", ("app_health",))],
            headers={"Cookie": "Admin-Token=token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["errors"], ["unexpected_sse_event"])

    def test_first_event_latency_over_target_fails(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float, max_bytes: int) -> sse_smoke_probe.SseProbeResponse:
            return sse_smoke_probe.SseProbeResponse(
                status_code=200,
                headers={"content-type": "text/event-stream; charset=utf-8"},
                body=b"event: app_health\ndata: {}\n\n",
            )

        with patch.object(sse_smoke_probe, "monotonic", side_effect=[10.0, 11.5]):
            report = sse_smoke_probe.collect_sse_smoke(
                base_url="https://example.test",
                probes=[sse_smoke_probe.SseProbe("app", "/api/app-health/stream", ("app_health",), target_ms=1000)],
                headers={"Cookie": "Admin-Token=token"},
                request_fn=request_fn,
            )

        self.assertEqual(report["status"], "fail")
        self.assertIn("sse_first_event_slo_miss", report["probes"][0]["errors"])


if __name__ == "__main__":
    unittest.main()
