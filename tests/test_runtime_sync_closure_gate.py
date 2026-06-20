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
            "dirty_scopes": {},
            "failed_jobs": 0,
            "stale_dirty_scope_count": 0,
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 0,
            "worker_metrics": [{"worker_kind": "workbench", "status": "ok", "required": True}],
            "rabbitmq_queue_depth": 0,
            "rabbitmq_unacked_messages": 0,
            "rabbitmq_dlq_count": 0,
            "read_model_refresh_failure_rate": 0.0,
        }


class EmptyRuntimeMonitoringRepository:
    def __init__(self, _connection) -> None:
        pass

    def health_summary(self) -> dict[str, object]:
        return {}


def read_model_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "planned_scope_count": 1,
        "result_count": 1,
        "failed_count": 0,
        "results": [
            {
                "status": "pass",
                "read_model_key": "workbench",
                "scope_type": "workbench",
                "scope_key": "all",
                "enqueue_to_fresh_ms": 500.0,
            }
        ],
    }


def http_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "auth_configured": True,
        "summary": {"probe_count": 1, "sample_count": 3, "failed_probe_count": 0},
        "probes": [
            {
                "name": "workbench_groups_all_paired",
                "status": "pass",
                "sample_count": 3,
                "success_count": 3,
            }
        ],
    }


def sse_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "auth_configured": True,
        "summary": {"probe_count": 1, "failed_probe_count": 0, "max_first_event_ms": 500.0},
        "probes": [
            {
                "name": "workbench_events_all",
                "status": "pass",
                "first_event_ms": 500.0,
                "event_names": ["workbench.read_model.completed"],
            }
        ],
    }


def health_ready_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "url": "https://example.test/fin-ops-api/health/ready",
        "elapsed_ms": 120.0,
        "response_bytes": 8_000,
        "health_status": "ready",
        "api_performance_endpoints_returned": 20,
        "api_performance_endpoint_count": 25,
        "api_performance_omitted_endpoint_count": 5,
        "errors": [],
    }


def write_e2e_pass_report() -> dict[str, object]:
    return {
        "status": "pass",
        "scenario_count": 1,
        "failed_scenario_count": 0,
        "results": [
            {
                "name": "ok",
                "status": "pass",
                "operations": ["turnover_manual_closure_or_withdraw"],
                "steps": [{"name": "step_1", "status": "pass"}],
                "write_slo": {"status": "pass"},
                "post_api": {"status": "skipped"},
            }
        ],
    }


class RuntimeSyncClosureGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self._health_ready_patch = patch.object(
            gate.health_ready_payload_probe,
            "collect_health_ready_payload",
            return_value=health_ready_pass_report(),
        )
        self._health_ready_patch.start()
        self.addCleanup(self._health_ready_patch.stop)

    def test_runtime_health_empty_summary_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", EmptyRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("runtime_health", report["failed_checks"])
        runtime_check = next(check for check in report["checks"] if check["name"] == "runtime_health")
        self.assertEqual(runtime_check["payload"]["error"], "runtime_health_missing_facts")
        self.assertIn("queue_backlog", runtime_check["payload"]["missing_fields"])

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
        self.assertIn("sse_first_event_smoke", report["failed_checks"])
        self.assertIn("write_operation_e2e", report["failed_checks"])
        self.assertFalse(report["auth_configured"])
        write_check = next(check for check in report["checks"] if check["name"] == "write_operation_e2e")
        self.assertEqual(write_check["payload"]["status"], "input_required")
        self.assertEqual(write_check["payload"]["missing_args"], ["--write-scenario"])
        self.assertEqual(
            write_check["payload"]["required_args"],
            ["--write-scenario", "--apply-write-scenarios", "--write-approval-ticket"],
        )

    def test_gate_passes_only_when_all_required_sections_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(report["failed_checks"], [])
        self.assertTrue(report["auth_configured"])
        self.assertEqual(report["targets"]["sse_first_event_ms"], 1_000.0)
        self.assertEqual(report["targets"]["health_ready_payload_ms"], 1_000.0)
        self.assertEqual(report["targets"]["health_ready_max_response_bytes"], 50_000)
        self.assertEqual(report["targets"]["health_ready_max_api_performance_endpoints"], 20)

    def test_gate_passes_admin_headers_to_http_slo_probe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ) as collect_http, patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value=write_e2e_pass_report(),
            ):
                gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer user-token"},
                    admin_headers={"Authorization": "Bearer admin-token", "Cookie": "Admin-Token=admin-token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        _, kwargs = collect_http.call_args
        self.assertEqual(kwargs["headers"], {"Authorization": "Bearer user-token"})
        self.assertEqual(
            kwargs["admin_headers"],
            {"Authorization": "Bearer admin-token", "Cookie": "Admin-Token=admin-token"},
        )

    def test_health_ready_payload_failure_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
            ), patch.object(
                gate.health_ready_payload_probe,
                "collect_health_ready_payload",
                return_value={
                    "status": "fail",
                    "url": "https://example.test/fin-ops-api/health/ready",
                    "elapsed_ms": 1900.0,
                    "response_bytes": 128_000,
                    "health_status": "ready",
                    "api_performance_endpoints_returned": 105,
                    "errors": [
                        "slo_miss",
                        "response_too_large",
                        "api_performance_endpoints_unbounded",
                        "api_performance_bound_metadata_missing",
                    ],
                },
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    api_prefix="/fin-ops-api",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("health_ready_payload", report["failed_checks"])
        health_check = next(check for check in report["checks"] if check["name"] == "health_ready_payload")
        self.assertEqual(health_check["payload"]["elapsed_ms"], 1900.0)
        self.assertEqual(health_check["payload"]["response_bytes"], 128_000)
        self.assertIn("api_performance_endpoints_unbounded", health_check["payload"]["errors"])

    def test_http_zero_samples_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value={"status": "pass", "auth_configured": True, "summary": {"probe_count": 0, "sample_count": 0, "failed_probe_count": 0}, "probes": []},
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("authenticated_http_slo", report["failed_checks"])
        http_check = next(check for check in report["checks"] if check["name"] == "authenticated_http_slo")
        self.assertEqual(http_check["payload"]["error"], "http_slo_empty_samples")

    def test_sse_zero_probes_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value={"status": "pass", "auth_configured": True, "summary": {"probe_count": 0, "failed_probe_count": 0}, "probes": []},
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("sse_first_event_smoke", report["failed_checks"])
        sse_check = next(check for check in report["checks"] if check["name"] == "sse_first_event_smoke")
        self.assertEqual(sse_check["payload"]["error"], "sse_smoke_empty_samples")

    def test_read_model_smoke_zero_samples_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value={"status": "pass", "planned_scope_count": 0, "result_count": 0, "failed_count": 0, "results": []},
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("read_model_direct_smoke", report["failed_checks"])
        read_model_check = next(check for check in report["checks"] if check["name"] == "read_model_direct_smoke")
        self.assertEqual(read_model_check["payload"]["error"], "read_model_smoke_empty_samples")

    def test_write_audit_zero_samples_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
            ), patch.object(
                gate.write_operation_slo_audit,
                "audit_write_operation_slo",
                return_value={
                    "status": "pass",
                    "event_sample_count": 0,
                    "expectation_count": 0,
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("write_operation_audit", report["failed_checks"])
        write_audit_check = next(check for check in report["checks"] if check["name"] == "write_operation_audit")
        self.assertEqual(write_audit_check["payload"]["error"], "write_operation_audit_empty_samples")

    def test_write_e2e_zero_results_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                return_value={"status": "pass", "scenario_count": 0, "failed_scenario_count": 0, "results": []},
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("write_operation_e2e", report["failed_checks"])
        write_e2e_check = next(check for check in report["checks"] if check["name"] == "write_operation_e2e")
        self.assertEqual(write_e2e_check["payload"]["error"], "write_operation_e2e_empty_samples")

    def test_write_audit_is_limited_to_approved_scenario_operations_when_scenario_is_supplied(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"confirm","operation":"workbench_relation_confirm","steps":[{"path":"/api/x"}]}]}')
            audit_calls: list[dict[str, object]] = []

            def audit_stub(_connection, **kwargs):
                audit_calls.append(dict(kwargs))
                return {
                    "status": "pass",
                    "event_sample_count": 12,
                    "expectation_count": 12,
                    "failed_expectation_count": 0,
                    "missing_expectation_count": 0,
                    "operations": ["workbench_relation_confirm"],
                    "results": [],
                }

            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
            ), patch.object(
                gate.write_operation_slo_audit,
                "audit_write_operation_slo",
                side_effect=audit_stub,
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "run_write_operation_e2e_smoke",
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.PASS)
        self.assertEqual(audit_calls[0]["operations"], ("workbench_relation_confirm",))

    def test_write_scenario_dry_run_does_not_satisfy_closure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
        write_check = next(check for check in report["checks"] if check["name"] == "write_operation_e2e")
        self.assertEqual(write_check["payload"]["status"], "dry_run")
        self.assertEqual(write_check["payload"]["missing_args"], ["--apply-write-scenarios"])
        self.assertEqual(
            write_check["payload"]["required_args"],
            ["--write-scenario", "--apply-write-scenarios", "--write-approval-ticket"],
        )

    def test_write_scenario_apply_requires_approval_ticket_before_write_e2e_runs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
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
                side_effect=AssertionError("write E2E should not run without approval"),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("write_operation_e2e", report["failed_checks"])
        write_check = next(check for check in report["checks"] if check["name"] == "write_operation_e2e")
        self.assertEqual(write_check["payload"]["status"], "approval_missing")
        self.assertEqual(write_check["payload"]["missing_args"], ["--write-approval-ticket"])
        self.assertEqual(
            write_check["payload"]["required_args"],
            ["--write-scenario", "--apply-write-scenarios", "--write-approval-ticket"],
        )

    def test_invalid_write_scenario_is_reported_as_input_error_without_running_write_checks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[]}', encoding="utf-8")
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value=sse_pass_report(),
            ), patch.object(
                gate.write_operation_slo_audit,
                "audit_write_operation_slo",
                side_effect=AssertionError("write audit should not run for invalid scenarios"),
            ), patch.object(
                gate.write_operation_e2e_smoke,
                "run_write_operation_e2e_smoke",
                side_effect=AssertionError("write E2E should not run for invalid scenarios"),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("write_operation_audit", report["failed_checks"])
        self.assertIn("write_operation_e2e", report["failed_checks"])
        for check_name in ("write_operation_audit", "write_operation_e2e"):
            check = next(item for item in report["checks"] if item["name"] == check_name)
            self.assertEqual(check["payload"]["status"], "input_error")
            self.assertEqual(check["payload"]["error"], "scenario_input_error")
            self.assertEqual(
                check["payload"]["required_args"],
                ["--write-scenario", "--apply-write-scenarios", "--write-approval-ticket"],
            )

    def test_sse_smoke_failure_prevents_closure_pass(self) -> None:
        with TemporaryDirectory() as temp_dir:
            scenario_path = Path(temp_dir) / "scenario.json"
            scenario_path.write_text('{"scenarios":[{"name":"ok","operation":"turnover_manual_closure_or_withdraw","steps":[{"path":"/api/x"}]}]}')
            with patch.object(gate, "RuntimeMonitoringRepository", FakeRuntimeMonitoringRepository), patch.object(
                gate.read_model_slo_smoke,
                "run_smoke",
                return_value=read_model_pass_report(),
            ), patch.object(
                gate.http_slo_probe,
                "collect_http_slo",
                return_value=http_pass_report(),
            ), patch.object(
                gate.sse_smoke_probe,
                "collect_sse_smoke",
                return_value={
                    "status": "fail",
                    "auth_configured": True,
                    "summary": {"failed_probe_count": 1},
                    "probes": [
                        {
                            "name": "workbench_events_all",
                            "status": "fail",
                            "first_event_ms": 1500.0,
                            "errors": ["sse_first_event_slo_miss"],
                        }
                    ],
                },
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
                return_value=write_e2e_pass_report(),
            ):
                report = gate.run_closure_gate(
                    object(),
                    base_url="https://example.test",
                    headers={"Authorization": "Bearer token"},
                    apply_read_model_smoke=True,
                    write_scenario=scenario_path,
                    apply_write_scenarios=True,
                    write_approval_ticket="TEST-APPROVAL",
                )

        self.assertEqual(report["status"], gate.FAIL)
        self.assertIn("sse_first_event_smoke", report["failed_checks"])
        sse_check = next(item for item in report["checks"] if item["name"] == "sse_first_event_smoke")
        self.assertEqual(sse_check["payload"]["failed_probes"][0]["errors"], ["sse_first_event_slo_miss"])


if __name__ == "__main__":
    unittest.main()
