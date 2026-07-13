from __future__ import annotations

import json
import os
from io import StringIO
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import (
    http_slo_probe,
    read_model_slo_smoke,
    runtime_sync_closure_gate,
    sse_smoke_probe,
    write_operation_e2e_smoke,
    write_operation_slo_audit,
)


class SloToolDefaultTests(unittest.TestCase):
    def test_cli_defaults_match_p2p3_one_second_closure_targets(self) -> None:
        http_args = http_slo_probe.build_parser().parse_args([])
        read_model_args = read_model_slo_smoke.build_parser().parse_args([])
        sse_args = sse_smoke_probe.build_parser().parse_args([])
        write_audit_args = write_operation_slo_audit.build_parser().parse_args([])
        write_e2e_args = write_operation_e2e_smoke.build_parser().parse_args(["--scenario", "/tmp/scenario.json"])
        closure_gate_args = runtime_sync_closure_gate.build_parser().parse_args([])

        self.assertEqual(http_args.target_ms, 1_000.0)
        self.assertEqual(read_model_args.target_ms, 1_000.0)
        self.assertEqual(sse_args.target_ms, 1_000.0)
        self.assertEqual(write_audit_args.target_ms, 1_000.0)
        self.assertIsNone(write_audit_args.p99_target_ms)
        self.assertEqual(write_operation_slo_audit.effective_p99_target_ms_for(write_audit_args.target_ms, None), 3_000.0)
        self.assertEqual(write_e2e_args.write_target_ms, 1_000.0)
        self.assertEqual(write_e2e_args.refresh_target_ms, 30_000.0)
        self.assertEqual(write_e2e_args.http_target_ms, 1_000.0)
        self.assertEqual(closure_gate_args.http_target_ms, 1_000.0)
        self.assertEqual(closure_gate_args.sse_target_ms, 1_000.0)
        self.assertEqual(closure_gate_args.health_ready_target_ms, 1_000.0)
        self.assertEqual(closure_gate_args.health_ready_max_response_bytes, 50_000)
        self.assertEqual(closure_gate_args.health_ready_max_api_performance_endpoints, 20)
        self.assertEqual(closure_gate_args.read_model_target_ms, 1_000.0)
        self.assertEqual(closure_gate_args.write_target_ms, 1_000.0)

    def test_http_sse_and_closure_gate_share_auth_env_defaults(self) -> None:
        env = {
            "FIN_OPS_HTTP_SLO_BASE_URL": "https://example.test",
            "FIN_OPS_HTTP_SLO_API_PREFIX": "/fin-ops-api",
            "FIN_OPS_HTTP_SLO_ADMIN_TOKEN": "admin-token",
            "FIN_OPS_HTTP_SLO_BEARER_TOKEN": "bearer-token",
            "FIN_OPS_HTTP_SLO_COOKIE": "Admin-Token=cookie-token",
        }

        with patch.dict(os.environ, env, clear=False):
            http_args = http_slo_probe.build_parser().parse_args([])
            sse_args = sse_smoke_probe.build_parser().parse_args([])
            closure_gate_args = runtime_sync_closure_gate.build_parser().parse_args([])

        for args in (http_args, sse_args, closure_gate_args):
            with self.subTest(parser=args):
                self.assertEqual(args.base_url, "https://example.test")
                self.assertEqual(args.api_prefix, "/fin-ops-api")
                self.assertEqual(args.admin_token, "admin-token")
                self.assertEqual(args.bearer_token, "bearer-token")
                self.assertEqual(args.cookie, "Admin-Token=cookie-token")

    def test_postgres_gate_tools_return_structured_configuration_missing(self) -> None:
        env = {
            "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
            "FIN_OPS_POSTGRES_DATABASE_URL": "",
            "DATABASE_URL": "",
        }
        tools = (
            ("read_model_slo_smoke", read_model_slo_smoke.main),
            ("write_operation_slo_audit", write_operation_slo_audit.main),
            ("runtime_sync_closure_gate", runtime_sync_closure_gate.main),
        )

        with patch.dict(os.environ, env, clear=False):
            for expected_tool, main in tools:
                with self.subTest(tool=expected_tool):
                    stdout = StringIO()
                    exit_code = main(["--json"], stdout=stdout)
                    payload = json.loads(stdout.getvalue())

                    self.assertEqual(exit_code, 2)
                    self.assertEqual(payload["status"], "configuration_missing")
                    self.assertEqual(payload["tool"], expected_tool)
                    self.assertEqual(payload["error"], "postgres_configuration_missing")
                    self.assertEqual(payload["blocking_condition"], "database_url_required")
                    self.assertIn("FIN_OPS_POSTGRES_DATABASE_URL", payload["required_env"])
                    self.assertIn("DATABASE_URL", payload["required_env"])
                    self.assertTrue(payload["next_actions"])
                    self.assertIn("PostgreSQL read-only dirty scope", " ".join(payload["allowed_remote_evidence"]))
                    self.assertIn("database writes", " ".join(payload["forbidden_without_approval"]))


if __name__ == "__main__":
    unittest.main()
