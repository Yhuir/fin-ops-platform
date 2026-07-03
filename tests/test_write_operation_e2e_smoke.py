from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import http_slo_probe, write_operation_e2e_smoke


class FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.started_at = datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc)
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return {"started_at": self.started_at}

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [dict(row) for row in self.rows]


class LimitAwareConnection(FakeConnection):
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        limit = int(params[-1]) if params else len(self.rows)
        return [dict(row) for row in self.rows[:limit]]


def _event(
    *,
    scope_type: str,
    reason: str,
    action_name: str,
    seconds: float = 1.0,
) -> dict[str, object]:
    created_at = datetime(2026, 6, 13, 10, 0, 1, tzinfo=timezone.utc)
    return {
        "event_id": f"{scope_type}-{reason}",
        "tenant_id": "default",
        "event_type": f"{scope_type}.read_model.refresh",
        "scope_type": scope_type,
        "scope_key": "all",
        "reason": reason,
        "action_name": action_name,
        "event_status": "done",
        "source_version": 1,
        "created_at": created_at,
        "processed_at": created_at + timedelta(seconds=seconds),
        "updated_at": created_at + timedelta(seconds=seconds),
        "event_last_error": None,
        "raw_payload": {},
        "dirty_status": "done",
        "dirty_last_error": None,
    }


def _turnover_withdraw_rows() -> list[dict[str, object]]:
    return [
        _event(scope_type="turnover_ledger", reason="turnover_relation_changed", action_name="withdraw_relation"),
        _event(scope_type="workbench", reason="turnover_relation_changed", action_name="withdraw_relation"),
        _event(scope_type="workbench_relation", reason="turnover_relation_changed", action_name="withdraw_relation"),
        _event(scope_type="cost_statistics", reason="turnover_relation_changed", action_name="withdraw_relation"),
        _event(scope_type="search", reason="turnover_relation_changed", action_name="withdraw_relation"),
    ]


class WriteOperationE2ESmokeTests(unittest.TestCase):
    def test_empty_scenarios_return_input_error_instead_of_pass(self) -> None:
        calls: list[str] = []

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            calls.append(url)
            return http_slo_probe.HttpProbeResponse(status_code=200, headers={}, body=b"{}")

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
            scenarios=[],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "input_error")
        self.assertEqual(report["error"], "scenario_empty")
        self.assertEqual(report["scenario_count"], 0)
        self.assertEqual(calls, [])

    def test_load_scenarios_and_dry_run_redacts_write_body(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    {
                        "scenarios": [
                            {
                                "name": "turnover-withdraw",
                                "operation": "turnover_manual_closure_or_withdraw",
                                "steps": [
                                    {
                                        "name": "withdraw",
                                        "method": "POST",
                                        "path": "/api/turnover-ledger/relations/REL-1/withdraw",
                                        "json": {"note": "secret business note"},
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            scenarios = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=scenarios,
                apply=False,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={},
            )

        self.assertEqual(report["status"], "dry_run")
        step_plan = report["planned_scenarios"][0]["steps"][0]
        self.assertEqual(step_plan["path"], "/api/turnover-ledger/relations/REL-1/withdraw")
        self.assertTrue(step_plan["has_json_body"])
        self.assertNotIn("secret business note", json.dumps(report))

    def test_cli_dry_run_does_not_require_postgres_configuration(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "turnover-withdraw",
                            "operation": "turnover_manual_closure_or_withdraw",
                            "steps": [
                                {
                                    "name": "withdraw",
                                    "method": "POST",
                                    "path": "/api/turnover-ledger/relations/REL-1/withdraw",
                                    "json": {"note": "dry-run"},
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            exit_code = write_operation_e2e_smoke.main(
                ["--scenario", str(path), "--base-url", "https://example.test"],
                stdout=stdout,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "dry_run")

    def test_cli_returns_input_error_when_scenario_file_is_missing(self) -> None:
        stdout = StringIO()

        exit_code = write_operation_e2e_smoke.main(
            ["--scenario", "/tmp/finops-missing-scenario.json", "--json"],
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "input_error")
        self.assertEqual(payload["tool"], "write_operation_e2e_smoke")
        self.assertEqual(payload["error"], "scenario_file_missing")

    def test_cli_returns_input_error_when_scenario_contract_is_invalid(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text("[]", encoding="utf-8")
            stdout = StringIO()

            exit_code = write_operation_e2e_smoke.main(
                ["--scenario", str(path), "--json"],
                stdout=stdout,
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "input_error")
        self.assertEqual(payload["error"], "scenario_contract_invalid")

    def test_cli_apply_returns_configuration_missing_when_postgres_url_is_absent(self) -> None:
        env = {
            "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
            "FIN_OPS_POSTGRES_DATABASE_URL": "",
            "DATABASE_URL": "",
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "turnover-withdraw",
                            "operation": "turnover_manual_closure_or_withdraw",
                            "steps": [
                                {
                                    "name": "withdraw",
                                    "method": "POST",
                                    "path": "/api/turnover-ledger/relations/REL-1/withdraw",
                                    "json": {"note": "apply"},
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with patch.dict(os.environ, env, clear=False):
                exit_code = write_operation_e2e_smoke.main(
                    ["--scenario", str(path), "--apply", "--approval-ticket", "TEST-APPROVAL", "--json"],
                    stdout=stdout,
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "configuration_missing")
        self.assertEqual(payload["tool"], "write_operation_e2e_smoke")
        self.assertEqual(payload["error"], "postgres_configuration_missing")

    def test_cli_apply_requires_approval_before_postgres_configuration(self) -> None:
        env = {
            "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
            "FIN_OPS_POSTGRES_DATABASE_URL": "",
            "DATABASE_URL": "",
            "FIN_OPS_WRITE_E2E_APPROVAL_TICKET": "",
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "turnover-withdraw",
                            "operation": "turnover_manual_closure_or_withdraw",
                            "steps": [
                                {
                                    "name": "withdraw",
                                    "method": "POST",
                                    "path": "/api/turnover-ledger/relations/REL-1/withdraw",
                                    "json": {"note": "apply"},
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            stdout = StringIO()

            with patch.dict(os.environ, env, clear=False):
                exit_code = write_operation_e2e_smoke.main(
                    ["--scenario", str(path), "--apply", "--json"],
                    stdout=stdout,
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "approval_missing")
        self.assertEqual(payload["error"], "write_operation_e2e_requires_approval_ticket")
        self.assertEqual(payload["required_args"], ["--scenario", "--apply", "--approval-ticket"])

    def test_apply_requires_approval_before_mutating_requests(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="turnover-withdraw",
            operations=("turnover_manual_closure_or_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/turnover-ledger/relations/REL-1/withdraw",
                    json_body={"note": "smoke"},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )
        calls: list[str] = []

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            calls.append(url)
            return http_slo_probe.HttpProbeResponse(status_code=200, headers={}, body=b"{}")

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "approval_missing")
        self.assertEqual(report["error"], "write_operation_e2e_requires_approval_ticket")
        self.assertEqual(calls, [])

    def test_apply_requires_auth_before_mutating_requests(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="turnover-withdraw",
            operations=("turnover_manual_closure_or_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/turnover-ledger/relations/REL-1/withdraw",
                    json_body={"note": "smoke"},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )
        calls: list[str] = []

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            calls.append(url)
            return http_slo_probe.HttpProbeResponse(status_code=200, headers={}, body=b"{}")

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "auth_missing")
        self.assertEqual(calls, [])

    def test_apply_executes_step_and_waits_for_required_write_refreshes(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="turnover-withdraw",
            operations=("turnover_manual_closure_or_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/turnover-ledger/relations/REL-1/withdraw",
                    json_body={"note": "smoke"},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )
        observed: list[tuple[str, str, bytes | None]] = []

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            observed.append((url, method, body))
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"ok":true}',
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection(_turnover_withdraw_rows()),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(observed[0][1], "POST")
        self.assertEqual(observed[0][0], "https://example.test/fin-ops-api/api/turnover-ledger/relations/REL-1/withdraw")
        self.assertEqual(report["results"][0]["write_slo"]["status"], "pass")
        self.assertEqual(len(report["results"][0]["write_slo"]["results"]), 5)

    def test_write_slo_event_sample_uses_effective_floor_when_scenario_limit_is_one(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="workbench-withdraw",
            operations=("workbench_relation_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/workbench/actions/withdraw-link",
                    json_body={"month": "2026-06", "row_ids": ["bank-1", "invoice-1"]},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )
        connection = LimitAwareConnection(
            [
                _event(scope_type="workbench", reason="workbench_relation_changed", action_name="withdraw_link"),
                _event(
                    scope_type="workbench_relation",
                    reason="workbench_pair_relation_changed",
                    action_name="withdraw_link",
                ),
            ]
        )

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"ok":true}',
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            connection,
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
            limit=1,
        )

        write_slo = report["results"][0]["write_slo"]
        self.assertEqual(report["status"], "pass")
        self.assertEqual(write_slo["requested_event_sample_limit"], 1)
        self.assertEqual(
            write_slo["effective_event_sample_limit"],
            write_operation_e2e_smoke.MIN_WRITE_SLO_EVENT_SAMPLE_LIMIT,
        )
        self.assertEqual(connection.fetch_all_calls[-1][1][-1], write_operation_e2e_smoke.MIN_WRITE_SLO_EVENT_SAMPLE_LIMIT)

    def test_write_step_failure_skips_write_slo_claim(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="turnover-withdraw",
            operations=("turnover_manual_closure_or_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/turnover-ledger/relations/REL-1/withdraw",
                    json_body={"note": "smoke"},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=409,
                headers={"content-type": "application/json"},
                body=b'{"error":"conflict"}',
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection(_turnover_withdraw_rows()),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["results"][0]["write_slo"]["status"], "skipped")

    def test_write_step_rejects_html_shell_even_when_status_matches(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="turnover-withdraw",
            operations=("turnover_manual_closure_or_withdraw",),
            steps=(
                write_operation_e2e_smoke.WriteStep(
                    name="withdraw",
                    method="POST",
                    path="/api/turnover-ledger/relations/REL-1/withdraw",
                    json_body={"note": "smoke"},
                    expected_statuses=(200,),
                ),
            ),
            post_api_probes=(),
        )

        def request_fn(url: str, method: str, headers, body, timeout_seconds: float) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                body=b"<!doctype html><html><body>fin ops</body></html>",
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection(_turnover_withdraw_rows()),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/wrong-prefix",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
        )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(result["steps"][0]["error"], "html_response_for_api_probe")
        self.assertEqual(result["write_slo"]["status"], "skipped")

    def test_unknown_operation_in_scenario_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "bad",
                            "operation": "does_not_exist",
                            "steps": [{"path": "/api/test"}],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "Unknown write-operation SLO profiles"):
                write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)


if __name__ == "__main__":
    unittest.main()
