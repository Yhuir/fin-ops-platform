from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import runtime_sync_closure_gate as gate


class FakeRuntimeMonitoringRepository:
    def __init__(self, _connection) -> None:
        pass

    def health_summary(self) -> dict[str, object]:
        return {
            "queue_backlog": {},
            "failed_jobs": 0,
            "stale_dirty_scope_count": 0,
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 0,
            "rabbitmq_queue_depth": 0,
            "rabbitmq_unacked_messages": 0,
            "rabbitmq_dlq_count": 0,
            "read_model_refresh_failure_rate": 0.0,
        }


class RuntimeSyncClosureGateTests(unittest.TestCase):
    def test_gate_fails_without_authenticated_http_and_write_scenario(self) -> None:
        with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
            gate.read_model_slo_smoke,
            "run_smoke",
            return_value={"status": "dry_run", "planned_scope_count": 14},
        ), patch.object(
            gate.write_operation_slo_audit,
            "audit_write_operation_slo",
            return_value={
                "status": "pass",
                "event_sample_count": 13,
                "expectation_count": 13,
                "failed_expectation_count": 0,
                "missing_expectation_count": 0,
                "results": [],
            },
        ):
            report = gate.run_closure_gate(
                object(),
                base_url="https://example.test",
                headers={},
            )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("read_model_direct_smoke", report["failed_checks"])
        self.assertIn("authenticated_http_slo", report["failed_checks"])
        self.assertIn("write_operation_e2e", report["failed_checks"])
        self.assertFalse(report["auth_configured"])

    def test_gate_passes_only_when_all_required_sections_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value={"status": "pass", "failed_count": 0, "results": []},
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value={"status": "pass", "auth_configured": True, "summary": {"failed_probe_count": 0}, "probes": []},
            ), patch.object(
                gate.write_operation_slo_audit,
                "audit_write_operation_slo",
                return_value={
                    "status": "pass",
                    "event_sample_count": 13,
                    "expectation_count": 13,
                    "failed_expectation_count": 0,
                    "missing_expectation_count": 0,
                    "results": [],
                },
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "load_scenarios",
                return_value=[object()],
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "run_write_operation_e2e_smoke",
                return_value={"status": "pass", "scenario_count": 1, "failed_scenario_count": 0, "results": []},
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(report["failed_checks"], [])
        self.assertTrue(report["auth_configured"])

    def test_write_scenario_dry_run_does_not_satisfy_closure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value={"status": "pass", "failed_count": 0, "results": []},
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value={"status": "pass", "auth_configured": True, "summary": {"failed_probe_count": 0}, "probes": []},
            ), patch.object(
                gate.write_operation_slo_audit,
                "audit_write_operation_slo",
                return_value={
                    "status": "pass",
                    "event_sample_count": 13,
                    "expectation_count": 13,
                    "failed_expectation_count": 0,
                    "missing_expectation_count": 0,
                    "results": [],
                },
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "load_scenarios",
                return_value=[object()],
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "run_write_operation_e2e_smoke",
                return_value={"status": "dry_run", "scenario_count": 1},
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=False,
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("write_operation_e2e", report["failed_checks"])


if __name__ == "__main__":
    unittest.main()
