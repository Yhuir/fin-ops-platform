from __future__ import annotations

from io import StringIO
import json
import unittest

from fin_ops_platform.tools import production_external_gate_preflight as preflight


class ProductionExternalGatePreflightTests(unittest.TestCase):
    def test_reports_missing_external_inputs_without_leaking_secret_values(self) -> None:
        report = preflight.build_report({"FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://secret-db"})

        self.assertEqual(report["status"], "external_input_required")
        self.assertEqual(report["ready_gate_count"], 0)
        self.assertEqual(report["gate_count"], 5)
        self.assertEqual(
            report["gates"]["production_admin_app_health_browser"]["missing_env"],
            ["FIN_OPS_E2E_ADMIN_TOKEN"],
        )
        self.assertEqual(
            report["gates"]["write_operation_apply"]["missing_env"],
            ["FIN_OPS_WRITE_E2E_SCENARIO", "FIN_OPS_WRITE_E2E_APPROVAL_TICKET"],
        )
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("postgresql://secret-db", encoded)

    def test_reports_ready_only_when_all_external_gate_inputs_are_present(self) -> None:
        env = {
            "FIN_OPS_E2E_ADMIN_TOKEN": "admin-secret",
            "FIN_OPS_E2E_OA_TOKEN": "user-secret",
            "FIN_OPS_HTTP_SLO_BEARER_TOKEN": "bearer-secret",
            "FIN_OPS_HTTP_SLO_ADMIN_TOKEN": "admin-secret",
            "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://secret-db",
            "FIN_OPS_WRITE_E2E_SCENARIO": "/tmp/scenario.json",
            "FIN_OPS_WRITE_E2E_APPROVAL_TICKET": "APPROVED-1",
        }

        report = preflight.build_report(env)

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["ready_gate_count"], report["gate_count"])
        encoded = json.dumps(report, ensure_ascii=False)
        for secret in env.values():
            self.assertNotIn(secret, encoded)

    def test_require_ready_exits_two_when_external_inputs_are_missing(self) -> None:
        stdout = StringIO()
        exit_code = preflight.main(["--require-ready"], stdout=stdout, environ={})

        self.assertEqual(exit_code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "external_input_required")


if __name__ == "__main__":
    unittest.main()
