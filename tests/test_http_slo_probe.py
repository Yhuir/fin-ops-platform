from __future__ import annotations

import json
import unittest

from fin_ops_platform.tools import http_slo_probe


class HttpSloProbeTests(unittest.TestCase):
    def test_requires_auth_by_default_without_sampling(self) -> None:
        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={},
        )

        self.assertEqual(report["status"], "auth_missing")
        self.assertFalse(report["auth_configured"])

    def test_collects_samples_with_api_prefix_without_leaking_auth(self) -> None:
        observed: list[tuple[str, dict[str, str]]] = []

        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            observed.append((url, dict(headers)))
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps({"read_model_status": "fresh", "cache_status": "fresh"}).encode("utf-8"),
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            probes=[http_slo_probe.HttpProbe("workbench", "/api/workbench/summary?month=all")],
            headers={"Authorization": "Bearer secret-token"},
            iterations=2,
            warmup=1,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["summary"]["sample_count"], 2)
        self.assertEqual(observed[0][0], "https://example.test/fin-ops-api/api/workbench/summary?month=all")
        self.assertTrue(report["auth_configured"])
        self.assertNotIn("secret-token", json.dumps(report))
        self.assertEqual(report["probes"][0]["read_model_statuses"], {"fresh": 2})
        self.assertEqual(report["probes"][0]["cache_statuses"], {"fresh": 2})

    def test_unexpected_status_fails_probe(self) -> None:
        def request_fn(url: str, headers, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=401,
                headers={"content-type": "application/json"},
                body=b'{"error":"invalid_oa_session"}',
            )

        report = http_slo_probe.collect_http_slo(
            base_url="https://example.test",
            probes=[http_slo_probe.HttpProbe("session", "/api/session/me")],
            headers={"Cookie": "Admin-Token=token"},
            iterations=1,
            warmup=0,
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["probes"][0]["status_counts"], {"401": 1})
        self.assertEqual(report["probes"][0]["errors"], ["unexpected_status:401"])

    def test_cli_auth_missing_exit_code(self) -> None:
        from io import StringIO

        stdout = StringIO()
        exit_code = http_slo_probe.main(
            ["--base-url", "https://example.test", "--iterations", "1"],
            stdout=stdout,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "auth_missing")


if __name__ == "__main__":
    unittest.main()
