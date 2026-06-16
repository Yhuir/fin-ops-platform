from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.tools import p2p3_gate_result_classifier


class P2P3GateResultClassifierTests(unittest.TestCase):
    def test_classifies_configuration_missing_as_environment_required(self) -> None:
        payload = p2p3_gate_result_classifier.classify_gate_result({
            "status": "configuration_missing",
            "tool": "read_model_slo_smoke",
            "error": "postgres_configuration_missing",
            "blocking_condition": "database_url_required",
            "required_env": ["FIN_OPS_POSTGRES_DATABASE_URL"],
            "next_actions": ["provide db url"],
            "forbidden_without_approval": ["database writes"],
        })

        self.assertEqual(payload["classification"], "environment-required")
        self.assertEqual(payload["source_tool"], "read_model_slo_smoke")
        self.assertEqual(payload["blocking_condition"], "database_url_required")
        self.assertEqual(payload["next_actions"], ["provide db url"])
        self.assertEqual(payload["forbidden_without_approval"], ["database writes"])

    def test_classifies_auth_input_and_dry_run_branches(self) -> None:
        cases = [
            ({"status": "auth_missing"}, "auth-required"),
            ({"status": "input_error", "error": "scenario_empty"}, "input-required"),
            ({"status": "no_candidates"}, "approved-scenario-required"),
            ({"status": "dry_run"}, "approval-required"),
        ]

        for source, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(
                    p2p3_gate_result_classifier.classify_gate_result(source)["classification"],
                    expected,
                )

    def test_classifies_runtime_and_durable_gate_failures(self) -> None:
        runtime = p2p3_gate_result_classifier.classify_gate_result({
            "status": "fail",
            "failed_checks": ["health_ready_payload"],
            "runtime_blockers": {"dirty_scopes": {"pending": 3}},
            "runtime_blocker_count": 1,
        })
        durable = p2p3_gate_result_classifier.classify_gate_result({
            "status": "fail",
            "failed_checks": ["read_model_direct_smoke"],
        })

        self.assertEqual(runtime["classification"], "runtime-repair-or-deploy-required")
        self.assertEqual(runtime["runtime_blockers"], {"dirty_scopes": {"pending": 3}})
        self.assertEqual(durable["classification"], "durable-evidence-required")

    def test_classifies_direct_health_ready_payload_failure_as_runtime_repair(self) -> None:
        payload = p2p3_gate_result_classifier.classify_gate_result({
            "status": "fail",
            "tool": "health_ready_payload_probe",
            "errors": ["slo_miss", "response_too_large"],
            "runtime_blockers": {"dirty_scopes": {"pending": 3}},
            "runtime_blocker_count": 1,
        })

        self.assertEqual(payload["classification"], "runtime-repair-or-deploy-required")
        self.assertEqual(payload["errors"], ["slo_miss", "response_too_large"])
        self.assertEqual(payload["runtime_blockers"], {"dirty_scopes": {"pending": 3}})
        self.assertIn("Rerun health_ready_payload_probe", payload["next_actions"][2])

    def test_passed_result_records_passed_classification(self) -> None:
        payload = p2p3_gate_result_classifier.classify_gate_result({"status": "pass", "tool": "x"})

        self.assertEqual(payload["classification"], "passed")
        self.assertIn("Record the passing evidence", payload["next_actions"][0])

    def test_cli_reads_file_and_rejects_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "result.json"
            result_path.write_text('{"status":"auth_missing"}\n', encoding="utf-8")
            stdout = StringIO()
            exit_code = p2p3_gate_result_classifier.main(["--result", str(result_path)], stdout=stdout)
            payload = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["classification"], "auth-required")

        stdout = StringIO()
        exit_code = p2p3_gate_result_classifier.main([], stdin=StringIO("[]"), stdout=stdout)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "input_error")
        self.assertEqual(payload["error"], "json_payload_not_object")


if __name__ == "__main__":
    unittest.main()
