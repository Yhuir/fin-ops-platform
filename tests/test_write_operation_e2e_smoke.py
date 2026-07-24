from __future__ import annotations

from datetime import datetime, timedelta, timezone
import gzip
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
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
        _event(scope_type="cost_statistics", reason="cost_statistics_relation_delta", action_name="withdraw_relation"),
        _event(scope_type="search", reason="turnover_relation_changed", action_name="withdraw_relation"),
    ]


def _system_audit_payload(audit_id: str = "system-audit:test-1") -> dict[str, object]:
    page_results = [
        {
            "page_key": f"page-{index}",
            "overall_status": "pass",
            "audit_status": {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        }
        for index in range(16)
    ]
    return {
        "overall_status": "pass",
        "audit_status": {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        "summary": {
            "registered_page_count": 17,
            "audited_business_page_count": 16,
            "passed_business_page_count": 16,
            "database_internal_contracts": "pass",
        },
        "database_system_snapshot": {
            "system_audit_id": audit_id,
            "snapshot_identity": f"snapshot:{audit_id}",
            "snapshot_consistency": "repeatable_read_read_only",
            "database_snapshot": True,
            "page_results": page_results,
        },
        "audit_contract": {"contract_revision": "page-audit-contract.v26"},
        "external_evidence": {"status": "unknown"},
    }


def _strict_checkpoint(
    name: str,
    *,
    key: str,
    relation_state_after: str,
) -> write_operation_e2e_smoke.WriteCheckpoint:
    return write_operation_e2e_smoke.WriteCheckpoint(
        name=name,
        operations=("workbench_relation_withdraw",),
        steps=(
            write_operation_e2e_smoke.WriteStep(
                name=name,
                method="POST",
                path=f"/api/workbench/actions/{name}",
                json_body={"idempotency_key": key, "row_ids": ["test-row-1"]},
                expected_statuses=(200,),
            ),
        ),
        consumers=(
            write_operation_e2e_smoke.ConsumerProbe(
                probe=http_slo_probe.HttpProbe("consumer", "/api/consumer", target_ms=1000),
                assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/linked", "equals", True),),
            ),
        ),
        system_audit_path="/api/operations/app-health/page-audit?page=app-health-operations",
        relation_state_after=relation_state_after,
    )


_BANK_INVOICE_CONSUMER_PAGES = (
    "reconciliation-workbench",
    "bank-details",
    "pending-invoices",
    "input-invoice-usage",
    "output-invoice-collections",
    "oa-pending-payments",
    "cost-statistics",
    "tax-offset",
)

_CONSUMER_PATHS = {
    "reconciliation-workbench": "/api/workbench/groups?month=2026-07&zone=paired&page=1&page_size=20",
    "bank-details": "/api/bank-details/transactions?year=2026&page=1&page_size=20",
    "pending-invoices": "/api/pending-invoices/rows?page=1&page_size=20",
    "input-invoice-usage": "/api/input-invoice-usage/rows?page=1&page_size=20",
    "output-invoice-collections": "/api/output-invoice-collections/rows?page=1&page_size=20",
    "oa-pending-payments": "/api/oa-pending-payments/rows?page=1&page_size=20",
    "cost-statistics": "/api/cost-statistics/explorer?scope=2026-07&view=time",
    "tax-offset": "/api/tax-offset?month=2026-07",
    "turnover-ledger": "/api/turnover-ledger?view=grouped&page=1&page_size=20",
}


def _raw_relation_checkpoint(
    *,
    name: str,
    operation: str,
    idempotency_key: str,
    relation_state_after: str,
) -> dict[str, object]:
    is_withdraw = name == "withdraw-link"
    read_model_version_name = f"{name}_read_model_version"
    expected_read_model_version = f"${{{read_model_version_name}}}"
    preview_captures = (
        {
            f"{name}_preview_id": "/preview_id",
            f"{name}_versions": "/submit_expected_versions",
        }
        if is_withdraw
        else {}
    )
    mutation_json: dict[str, object] = {
        "month": "2026-07",
        "row_ids": ["bank-test-1", "invoice-test-1"],
        "expected_read_model_version": expected_read_model_version,
        "idempotency_key": idempotency_key,
    }
    if is_withdraw:
        mutation_json.update(
            {
                "preview_id": f"${{{name}_preview_id}}",
                "expected_versions": f"${{{name}_versions}}",
                "operation_type": "withdraw_relation",
            }
        )
    return {
        "name": name,
        "operation": operation,
        "steps": [
            {
                "name": f"{name}-read-version",
                "method": "GET",
                "path": "/api/workbench?month=2026-07",
                "mutation": False,
                "captures": {read_model_version_name: "/read_model_version"},
            },
            {
                "name": f"{name}-preview",
                "method": "POST",
                "path": f"/api/workbench/actions/{name}/preview",
                "mutation": False,
                "json": {
                    "month": "2026-07",
                    "row_ids": ["bank-test-1", "invoice-test-1"],
                    "expected_read_model_version": expected_read_model_version,
                },
                "captures": preview_captures,
            },
            {
                "name": name,
                "method": "POST",
                "path": f"/api/workbench/actions/{name}",
                "json": mutation_json,
            },
        ],
        "consumers": [
            {
                "name": page_key,
                "page_key": page_key,
                "path": _CONSUMER_PATHS[page_key],
                "assertions": [
                    {
                        "pointer": (
                            "/input_plan_items"
                            if page_key == "tax-offset"
                            else "/rows/0/transaction_id"
                            if page_key == "cost-statistics"
                            else "/groups/0/bank_rows/0/id"
                            if page_key == "reconciliation-workbench"
                            else "/rows/0/id"
                        ),
                        "equals": [] if page_key == "tax-offset" else "bank-test-1",
                    }
                ],
            }
            for page_key in _BANK_INVOICE_CONSUMER_PAGES
        ],
        "system_audit": True,
        "relation_state_after": relation_state_after,
    }


def _raw_bank_invoice_scenario(name: str, key_prefix: str) -> dict[str, object]:
    confirm = _raw_relation_checkpoint(
        name="confirm-link",
        operation="workbench_relation_confirm_bank_invoice_cross_page",
        idempotency_key=f"{key_prefix}-confirm",
        relation_state_after="active",
    )
    withdraw = _raw_relation_checkpoint(
        name="withdraw-link",
        operation="workbench_relation_withdraw_bank_invoice_cross_page",
        idempotency_key=f"{key_prefix}-withdraw",
        relation_state_after="inactive",
    )
    recovery = _raw_relation_checkpoint(
        name="withdraw-link",
        operation="workbench_relation_withdraw_bank_invoice_cross_page",
        idempotency_key=f"{key_prefix}-recovery",
        relation_state_after="inactive",
    )
    return {
        "name": name,
        "shape": "bank_invoice",
        "fixture_ownership": "test_owned",
        "checkpoints": [confirm, withdraw],
        "recovery_checkpoint": recovery,
    }


def _raw_bank_turnover_scenario(name: str, key_prefix: str) -> dict[str, object]:
    fixture_row_ids = ["turnover-bank-test-1", "turnover-bank-test-2"]
    consumers = [
        {
            "name": page_key,
            "page_key": page_key,
            "path": _CONSUMER_PATHS[page_key],
            "assertions": [
                {
                    "pointer": (
                        "/rows"
                        if page_key == "input-invoice-usage"
                        else "/rows/0/transaction_id"
                        if page_key == "cost-statistics"
                        else "/groups/0/bank_rows/0/id"
                        if page_key == "reconciliation-workbench"
                        else "/rows/0/id"
                    ),
                    "equals": [] if page_key == "input-invoice-usage" else fixture_row_ids[0],
                }
            ],
        }
        for page_key in (
            "reconciliation-workbench",
            "cost-statistics",
            "turnover-ledger",
            "input-invoice-usage",
        )
    ]
    confirm = {
        "name": "turnover-confirm",
        "operation": "turnover_relation_confirm_cross_page",
        "fixture_row_ids": fixture_row_ids,
        "steps": [
            {
                "name": "turnover-confirm",
                "method": "POST",
                "path": "/api/turnover-ledger/closures/confirm",
                "json": {
                    "bank_row_ids": fixture_row_ids,
                    "expected_versions": {f"turnover_bank_row:{row_id}": 1 for row_id in fixture_row_ids},
                    "idempotency_key": f"{key_prefix}-confirm",
                },
                "captures": {"cash_closure_case_id": "/workbench_pair_relation/case_id"},
            }
        ],
        "consumers": consumers,
        "system_audit": True,
        "relation_state_after": "active",
    }

    def withdraw(checkpoint_name: str, idempotency_key: str) -> dict[str, object]:
        return {
            "name": checkpoint_name,
            "operation": "turnover_relation_withdraw_cross_page",
            "fixture_row_ids": fixture_row_ids,
            "steps": [
                {
                    "name": checkpoint_name,
                    "method": "POST",
                    "path": "/api/turnover-ledger/closures/withdraw",
                    "json": {
                        "cash_closure_case_id": "${cash_closure_case_id}",
                        "idempotency_key": idempotency_key,
                    },
                }
            ],
            "consumers": consumers,
            "system_audit": True,
            "relation_state_after": "inactive",
        }

    return {
        "name": name,
        "shape": "bank_turnover",
        "fixture_ownership": "test_owned",
        "checkpoints": [confirm, withdraw("turnover-withdraw", f"{key_prefix}-withdraw")],
        "recovery_checkpoint": withdraw("turnover-recovery", f"{key_prefix}-recovery"),
    }


class WriteOperationE2ESmokeTests(unittest.TestCase):
    def test_http_request_decodes_gzip_json_before_preflight_parsing(self) -> None:
        payload = json.dumps(_system_audit_payload("system-audit:gzip")).encode("utf-8")

        class Response:
            headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def getcode(self) -> int:
                return 200

            def read(self) -> bytes:
                return gzip.compress(payload)

        with patch("urllib.request.urlopen", return_value=Response()):
            response = write_operation_e2e_smoke._http_request(
                "https://example.test/fin-ops-api/api/operations/app-health/page-audit",
                "GET",
                {"Accept-Encoding": "gzip"},
                None,
                1,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body.decode("utf-8"))["overall_status"], "pass")

    def test_empty_scenarios_return_input_error_instead_of_pass(self) -> None:
        calls: list[str] = []

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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

    def test_apply_executes_step_and_verifies_zero_write_time_page_fan_out(self) -> None:
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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            observed.append((url, method, body))
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"ok":true}',
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
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
        self.assertEqual(
            observed[0][0], "https://example.test/fin-ops-api/api/turnover-ledger/relations/REL-1/withdraw"
        )
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
        connection = LimitAwareConnection([])

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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
        self.assertEqual(
            connection.fetch_all_calls[-1][1][-1], write_operation_e2e_smoke.MIN_WRITE_SLO_EVENT_SAMPLE_LIMIT
        )

    def test_exact_checkpoint_event_set_rejects_unknown_or_unmatched_event_ids(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="workbench_relation_changed", action_name="confirm_link"),
            _event(
                scope_type="workbench_relation",
                reason="workbench_pair_relation_changed",
                action_name="confirm_link",
            ),
        ]
        event_ids = [str(row["event_id"]) for row in rows]

        with patch(
            "fin_ops_platform.tools.write_operation_e2e_smoke.monotonic",
            side_effect=[100.0, 102.0],
        ):
            report = write_operation_e2e_smoke._wait_for_write_slo(
                FakeConnection(rows),
                operations=("workbench_relation_confirm",),
                tenant_id="default",
                started_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc),
                target_ms=1000,
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                limit=10,
                event_ids=[*event_ids, "unknown-extra-event"],
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["error"], "exact_checkpoint_event_set_mismatch")
        self.assertEqual(report["missing_or_unmatched_event_ids"], ["unknown-extra-event"])

    def test_exact_receipt_rejects_forbidden_write_time_page_refreshes(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="older_refresh", action_name="older_action"),
            _event(scope_type="workbench_relation", reason="older_relation_refresh", action_name="older_action"),
            _event(scope_type="cost_statistics", reason="older_cost_refresh", action_name="older_action"),
        ]

        report = write_operation_e2e_smoke._wait_for_write_slo(
            FakeConnection(rows),
            operations=("workbench_relation_confirm",),
            tenant_id="default",
            started_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc),
            target_ms=1000,
            timeout_seconds=1,
            poll_interval_seconds=0.05,
            limit=10,
            event_ids=[str(row["event_id"]) for row in rows],
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["error"], "forbidden_write_time_read_model_fan_out_detected")
        self.assertEqual(report["unexpected_event_contracts"], [])
        self.assertTrue(any(result["status"] == "fail" for result in report["results"]))

    def test_exact_receipt_rejects_refresh_scope_outside_operation_contract(self) -> None:
        rows = [
            _event(scope_type="workbench", reason="older_refresh", action_name="older_action"),
            _event(scope_type="workbench_relation", reason="older_relation_refresh", action_name="older_action"),
            _event(scope_type="tax_offset", reason="unexpected", action_name="unexpected"),
        ]

        with patch(
            "fin_ops_platform.tools.write_operation_e2e_smoke.monotonic",
            side_effect=[100.0, 102.0],
        ):
            report = write_operation_e2e_smoke._wait_for_write_slo(
                FakeConnection(rows),
                operations=("workbench_relation_confirm",),
                tenant_id="default",
                started_at=datetime(2026, 6, 13, 10, 0, 0, tzinfo=timezone.utc),
                target_ms=1000,
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                limit=10,
                event_ids=[str(row["event_id"]) for row in rows],
            )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["error"], "unexpected_checkpoint_event_contract")
        self.assertEqual(report["unexpected_event_contracts"][0]["scope_type"], "tax_offset")

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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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
        self.assertEqual(report["results"][0]["steps"][0]["response_error_code"], "conflict")
        self.assertIsNone(report["results"][0]["steps"][0]["request_id"])

    def test_write_step_reports_safe_request_id_for_bounded_log_lookup(self) -> None:
        step = write_operation_e2e_smoke.WriteStep(
            name="confirm",
            method="POST",
            path="/api/workbench/actions/confirm-link",
            json_body={"idempotency_key": "safe-diagnostic"},
            expected_statuses=(200,),
        )

        executed = write_operation_e2e_smoke._execute_step(
            step,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=500,
                headers={"content-type": "application/json"},
                body=b'{"error":"internal_server_error","requestId":"abcdef123456"}',
            ),
        )

        self.assertEqual(executed.result.request_id, "abcdef123456")
        self.assertEqual(executed.result.response_error_code, "internal_server_error")

    def test_write_step_reports_success_request_id_from_response_header(self) -> None:
        step = write_operation_e2e_smoke.WriteStep(
            name="confirm",
            method="POST",
            path="/api/workbench/actions/confirm-link",
            json_body={"idempotency_key": "safe-success-diagnostic"},
            expected_statuses=(200,),
        )

        executed = write_operation_e2e_smoke._execute_step(
            step,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={
                    "content-type": "application/json",
                    "x-request-id": "123456abcdef",
                },
                body=b'{"success":true}',
            ),
        )

        self.assertEqual(executed.result.request_id, "123456abcdef")
        self.assertIsNone(executed.result.response_error_code)

    def test_write_step_captures_transaction_outbox_receipt(self) -> None:
        step = write_operation_e2e_smoke.WriteStep(
            name="confirm",
            method="POST",
            path="/api/workbench/actions/confirm-link",
            json_body={"idempotency_key": "receipt"},
            expected_statuses=(200,),
        )

        executed = write_operation_e2e_smoke._execute_step(
            step,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"success":true,"outbox_event_ids":["event-1","event-2","event-1"]}',
            ),
        )

        self.assertEqual(
            executed.captures[write_operation_e2e_smoke._RESPONSE_OUTBOX_EVENT_IDS],
            ["event-1", "event-2"],
        )

    def test_write_step_preserves_explicit_zero_fanout_receipt(self) -> None:
        step = write_operation_e2e_smoke.WriteStep(
            name="confirm",
            method="POST",
            path="/api/turnover-ledger/closures/confirm",
            json_body={"idempotency_key": "zero-fanout-receipt"},
            expected_statuses=(200,),
        )

        executed = write_operation_e2e_smoke._execute_step(
            step,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"success":true,"outbox_event_ids":[]}',
            ),
        )

        self.assertIn(write_operation_e2e_smoke._RESPONSE_OUTBOX_EVENT_IDS, executed.captures)
        self.assertEqual(executed.captures[write_operation_e2e_smoke._RESPONSE_OUTBOX_EVENT_IDS], [])

    def test_slow_write_step_fails_before_claiming_write_slo(self) -> None:
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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"ok":true}',
            )

        monotonic_values = iter([100.0, 101.25])
        with patch(
            "fin_ops_platform.tools.write_operation_e2e_smoke.monotonic", side_effect=lambda: next(monotonic_values)
        ):
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
                write_target_ms=1000,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(result["steps"][0]["status"], "fail")
        self.assertEqual(result["steps"][0]["elapsed_ms"], 1250.0)
        self.assertEqual(result["steps"][0]["error"], "write_step_slo_miss:1250.0>1000")
        self.assertEqual(result["write_slo"]["status"], "skipped")

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

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
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

    def test_legacy_scenario_is_normalized_to_one_checkpoint(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps(
                    [
                        {
                            "name": "legacy",
                            "operation": "workbench_relation_withdraw",
                            "steps": [{"path": "/api/workbench/actions/withdraw-link"}],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            scenario = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)[0]

        self.assertEqual(len(scenario.checkpoints), 1)
        self.assertEqual(scenario.checkpoints[0].name, "legacy")

    def test_checkpoint_contract_requires_test_owned_fixture_idempotency_consumers_audit_and_recovery(self) -> None:
        base = {
            "name": "closure",
            "shape": "bank_invoice",
            "fixture_ownership": "test_owned",
            "checkpoints": [
                {
                    "name": "confirm",
                    "operation": "workbench_relation_withdraw",
                    "steps": [{"path": "/api/workbench/actions/confirm-link", "json": {}}],
                    "consumers": [],
                    "system_audit": True,
                    "relation_state_after": "active",
                }
            ],
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([base]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "idempotency_key"):
                write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

    def test_reversible_scenario_rejects_noncanonical_mutation_audit_override_and_unbound_assertion(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        wrong_endpoint = _raw_bank_invoice_scenario("wrong-endpoint", "strict-1")
        wrong_endpoint["checkpoints"][0]["steps"][2]["path"] = "/api/legacy/confirm"  # type: ignore[index]
        cases.append(("endpoint", wrong_endpoint, "canonical Workbench"))

        audit_override = _raw_bank_invoice_scenario("audit-override", "strict-2")
        audit_override["checkpoints"][0]["system_audit"] = {"path": "/api/test"}  # type: ignore[index]
        cases.append(("audit", audit_override, "enable system_audit"))

        unbound = _raw_bank_invoice_scenario("unbound", "strict-3")
        unbound["checkpoints"][0]["consumers"][0]["assertions"] = [  # type: ignore[index]
            {"pointer": "/groups/0/status", "equals": "fresh"}
        ]
        cases.append(("identity", unbound, "test-owned row"))

        metadata_only = _raw_bank_invoice_scenario("metadata-only", "strict-metadata")
        metadata_only["checkpoints"][0]["consumers"][0]["assertions"] = [  # type: ignore[index]
            {"pointer": "/read_model_status", "equals": "fresh"}
        ]
        cases.append(("business-root", metadata_only, "business roots"))

        wrong_consumer_path = _raw_bank_invoice_scenario("wrong-consumer", "strict-4")
        wrong_consumer_path["checkpoints"][0]["consumers"][0]["path"] = "/api/health"  # type: ignore[index]
        cases.append(("consumer-path", wrong_consumer_path, "consumer paths"))

        swapped_withdraw_lock = _raw_bank_invoice_scenario("swapped-lock", "strict-5")
        withdraw_body = swapped_withdraw_lock["checkpoints"][1]["steps"][2]["json"]  # type: ignore[index]
        withdraw_body["preview_id"], withdraw_body["expected_versions"] = (  # type: ignore[index]
            withdraw_body["expected_versions"],
            withdraw_body["preview_id"],
        )
        cases.append(("withdraw-lock", swapped_withdraw_lock, "must consume preview_id"))

        for label, scenario, expected_error in cases:
            with self.subTest(label=label), TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "scenario.json"
                path.write_text(json.dumps([scenario]), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, expected_error):
                    write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

    def test_reversible_scenario_matches_registered_shape_consumers_and_bounded_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([_raw_bank_invoice_scenario("bank-invoice", "shape-1")]), encoding="utf-8")

            scenarios = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

        self.assertEqual(scenarios[0].shape, "bank_invoice")
        self.assertEqual(len(scenarios[0].checkpoints), 2)
        for checkpoint in (*scenarios[0].checkpoints, scenarios[0].recovery_checkpoint):
            assert checkpoint is not None
            self.assertEqual(len(checkpoint.steps), 3)
            read_version, preview, mutation = checkpoint.steps
            self.assertEqual(read_version.method, "GET")
            self.assertEqual(read_version.path, "/api/workbench?month=2026-07")
            self.assertEqual(read_version.captures[0][1], "/read_model_version")
            expected_version = f"${{{read_version.captures[0][0]}}}"
            self.assertEqual(preview.json_body["expected_read_model_version"], expected_version)
            self.assertEqual(mutation.json_body["expected_read_model_version"], expected_version)
        self.assertEqual(
            {consumer.page_key for consumer in scenarios[0].checkpoints[0].consumers},
            set(_BANK_INVOICE_CONSUMER_PAGES),
        )

    def test_bank_turnover_scenario_uses_real_turnover_closure_contract(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([_raw_bank_turnover_scenario("turnover", "shape-2")]), encoding="utf-8")

            scenario = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)[0]

        self.assertEqual(scenario.shape, "bank_turnover")
        self.assertEqual(scenario.checkpoints[0].steps[0].path, "/api/turnover-ledger/closures/confirm")
        self.assertEqual(
            scenario.checkpoints[1].steps[0].path,
            "/api/turnover-ledger/closures/withdraw",
        )
        self.assertEqual(
            scenario.checkpoints[1].steps[0].json_body["cash_closure_case_id"],
            "${cash_closure_case_id}",
        )
        self.assertEqual(scenario.checkpoints[0].fixture_row_ids, scenario.checkpoints[1].fixture_row_ids)

    def test_reversible_scenario_allows_two_exact_scopes_for_one_affected_page(self) -> None:
        scenario = _raw_bank_turnover_scenario("turnover-scopes", "shape-scopes")
        shared_consumers = scenario["checkpoints"][0]["consumers"]  # type: ignore[index]
        cost_consumer = next(
            consumer for consumer in shared_consumers if consumer["page_key"] == "cost-statistics"
        )
        shared_consumers.append(
            {
                **cost_consumer,
                "name": "cost-statistics-all-scope",
                "path": f"{cost_consumer['path']}&project_scope=all",
            }
        )

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([scenario]), encoding="utf-8")
            loaded = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)[0]

        for checkpoint in (*loaded.checkpoints, loaded.recovery_checkpoint):
            assert checkpoint is not None
            self.assertEqual(
                len([consumer for consumer in checkpoint.consumers if consumer.page_key == "cost-statistics"]),
                2,
            )

    def test_reversible_scenario_rejects_three_scopes_for_one_affected_page(self) -> None:
        scenario = _raw_bank_turnover_scenario("turnover-scopes", "shape-scopes")
        shared_consumers = scenario["checkpoints"][0]["consumers"]  # type: ignore[index]
        cost_consumer = next(
            consumer for consumer in shared_consumers if consumer["page_key"] == "cost-statistics"
        )
        for suffix in ("all", "second-all"):
            shared_consumers.append(
                {
                    **cost_consumer,
                    "name": f"cost-statistics-{suffix}",
                    "path": f"{cost_consumer['path']}&project_scope=all&probe={suffix}",
                }
            )

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([scenario]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at most two exact scope probes"):
                write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

    def test_reversible_scenarios_reject_missing_consumer_or_cross_scenario_idempotency_reuse(self) -> None:
        missing_consumer = _raw_bank_invoice_scenario("missing-consumer", "shape-1")
        missing_consumer["checkpoints"][0]["consumers"].pop()  # type: ignore[index]
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([missing_consumer]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "consumers must exactly match"):
                write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            first = _raw_bank_invoice_scenario("first", "shared")
            second = _raw_bank_invoice_scenario("second", "shared")
            path.write_text(json.dumps([first, second]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unique across the file"):
                write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)

    def test_json_pointer_assertions_are_typed_and_fail_closed(self) -> None:
        payload = {"rows": [{"id": "row-1", "labels": ["linked"], "meta": {"state": "active"}}]}
        equals = write_operation_e2e_smoke._evaluate_json_assertion(
            write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/id", "equals", "row-1"),
            payload=payload,
            variables={},
        )
        contains = write_operation_e2e_smoke._evaluate_json_assertion(
            write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/meta", "contains", {"state": "active"}),
            payload=payload,
            variables={},
        )
        excludes = write_operation_e2e_smoke._evaluate_json_assertion(
            write_operation_e2e_smoke.JsonPointerAssertion("/rows", "excludes", "row-2"),
            payload=payload,
            variables={},
        )
        includes_excluded_identity = write_operation_e2e_smoke._evaluate_json_assertion(
            write_operation_e2e_smoke.JsonPointerAssertion("/rows", "excludes", "row-1"),
            payload=payload,
            variables={},
        )
        missing = write_operation_e2e_smoke._evaluate_json_assertion(
            write_operation_e2e_smoke.JsonPointerAssertion("/rows/1/id", "equals", "row-1"),
            payload=payload,
            variables={},
        )

        self.assertEqual(equals["status"], "pass")
        self.assertEqual(contains["status"], "pass")
        self.assertEqual(excludes["status"], "pass")
        self.assertEqual(includes_excluded_identity["status"], "fail")
        self.assertEqual(missing["status"], "fail")

    def test_reversible_consumer_excludes_assertion_binds_test_owned_identity(self) -> None:
        scenario = _raw_bank_turnover_scenario("turnover-excludes", "turnover-excludes")
        for checkpoint in (scenario["checkpoints"][1], scenario["recovery_checkpoint"]):
            workbench = next(
                consumer
                for consumer in checkpoint["consumers"]
                if consumer["page_key"] == "reconciliation-workbench"
            )
            workbench["assertions"] = [{"pointer": "/groups", "excludes": "turnover-bank-test-1"}]

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(json.dumps([scenario]), encoding="utf-8")
            loaded = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)[0]

        for checkpoint in (loaded.checkpoints[1], loaded.recovery_checkpoint):
            assert checkpoint is not None
            assertion = next(
                consumer.assertions[0]
                for consumer in checkpoint.consumers
                if consumer.page_key == "reconciliation-workbench"
            )
            self.assertEqual(assertion.operator, "excludes")
            self.assertEqual(assertion.expected, "turnover-bank-test-1")

    def test_canonical_preview_payloads_fail_closed_before_mutation(self) -> None:
        confirm = write_operation_e2e_smoke.WriteStep(
            name="confirm-preview",
            method="POST",
            path=write_operation_e2e_smoke.CONFIRM_PREVIEW_PATH,
            json_body={"month": "2026-07", "row_ids": ["bank-1", "invoice-1"]},
            expected_statuses=(200,),
            mutation=False,
        )
        withdraw = write_operation_e2e_smoke.WriteStep(
            name="withdraw-preview",
            method="POST",
            path=write_operation_e2e_smoke.WITHDRAW_PREVIEW_PATH,
            json_body={"month": "2026-07", "row_ids": ["bank-1", "invoice-1"]},
            expected_statuses=(200,),
            mutation=False,
            captures=(
                ("preview_id", "/preview_id"),
                ("expected_versions", "/submit_expected_versions"),
            ),
        )

        confirm_result = write_operation_e2e_smoke._execute_step(
            confirm,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"operation":"confirm_link","can_submit":false}',
            ),
        )
        withdraw_result = write_operation_e2e_smoke._execute_step(
            withdraw,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            target_ms=1000,
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"operation":"withdraw_link","can_submit":true,"preview_id":"p1"}',
            ),
        )

        self.assertEqual(confirm_result.result.status, "fail")
        self.assertIn("canonical_relation_preview_not_submittable", confirm_result.result.error or "")
        self.assertEqual(withdraw_result.result.status, "fail")
        self.assertIn("canonical_withdraw_preview_contract_invalid", withdraw_result.result.error or "")

    def test_consumer_and_system_audit_gates_reject_nonfresh_or_incomplete_payloads(self) -> None:
        checkpoint = _strict_checkpoint("confirm", key="confirm-key", relation_state_after="active")

        def nonfresh_request(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"read_model_status":"refreshing","refresh_enqueued":true,"rows":[{"linked":true}]}',
            )

        consumer = write_operation_e2e_smoke._collect_checkpoint_consumers(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=nonfresh_request,
            variables={},
            strict=True,
        )
        audit = write_operation_e2e_smoke._collect_system_audit(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=lambda *args: http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"overall_status":"pass"}',
            ),
        )

        self.assertEqual(consumer["status"], "fail")
        self.assertEqual(consumer["results"][0]["error"], "consumer_read_model_not_fresh")
        self.assertEqual(audit["status"], "fail")
        self.assertEqual(audit["error"], "system_audit_snapshot_missing")

    def test_checkpoint_consumers_probe_open_pages_in_parallel_and_keep_scenario_order(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="parallel-pages",
            operations=("workbench_relation_confirm_cross_page",),
            steps=(),
            consumers=tuple(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe(
                        name,
                        f"/api/{name}",
                        target_ms=1000,
                    ),
                    assertions=(
                        write_operation_e2e_smoke.JsonPointerAssertion(
                            "/rows/0/visible",
                            "equals",
                            True,
                        ),
                    ),
                    page_key=name,
                    role="affected",
                )
                for name in ("page-a", "page-b")
            ),
        )
        both_requests_started = Barrier(2)

        def request_fn(*_args) -> http_slo_probe.HttpProbeResponse:
            both_requests_started.wait(timeout=2)
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b'{"read_model_status":"fresh","refresh_enqueued":false,"rows":[{"visible":true}]}',
            )

        result = write_operation_e2e_smoke._collect_checkpoint_consumers(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=request_fn,
            variables={},
            strict=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            [item["name"] for item in result["results"]],
            ["page-a", "page-b"],
        )

    def test_consumer_slo_failure_keeps_resolved_path_for_terminal_result_identity(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="slow-page",
            operations=("workbench_relation_confirm_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe(
                        "slow-page",
                        "/api/pages/${month}",
                        target_ms=1,
                    ),
                    assertions=(
                        write_operation_e2e_smoke.JsonPointerAssertion(
                            "/rows/0/visible",
                            "equals",
                            True,
                        ),
                    ),
                    page_key="slow-page",
                    role="affected",
                ),
            ),
        )

        with patch(
            "fin_ops_platform.tools.write_operation_e2e_smoke.monotonic",
            side_effect=[10.0, 10.002],
        ):
            result = write_operation_e2e_smoke._collect_checkpoint_consumers(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                request_fn=lambda *_args: http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=b'{"read_model_status":"fresh","refresh_enqueued":false,"rows":[{"visible":true}]}',
                ),
                variables={"month": "2026-07"},
                strict=True,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["results"][0]["path"], "/api/pages/2026-07")
        self.assertEqual(result["results"][0]["error"], "consumer_slo_miss:2.0>1")

    def test_consumer_wait_retries_refreshing_and_affected_business_visibility(self) -> None:
        checkpoint = _strict_checkpoint("confirm", key="confirm-key", relation_state_after="active")
        attempts = 0

        def refreshing_then_fresh(*_args) -> http_slo_probe.HttpProbeResponse:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                status = 202
                payload = {"read_model_status": "refreshing", "refresh_enqueued": True}
            else:
                status = 200
                payload = {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "rows": [{"linked": True}],
                }
            return http_slo_probe.HttpProbeResponse(
                status_code=status,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode(),
            )

        with patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None):
            converged = write_operation_e2e_smoke._wait_for_checkpoint_consumers(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=refreshing_then_fresh,
                variables={},
                strict=True,
            )

        self.assertEqual(converged["status"], "pass")
        self.assertEqual(attempts, 2)

        attempts = 0

        def stale_business_value_then_visible(*_args) -> http_slo_probe.HttpProbeResponse:
            nonlocal attempts
            attempts += 1
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "read_model_status": "fresh",
                        "refresh_enqueued": False,
                        "rows": [{"linked": attempts > 1}],
                    }
                ).encode(),
            )

        with patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None):
            converged = write_operation_e2e_smoke._wait_for_checkpoint_consumers(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=stale_business_value_then_visible,
                variables={},
                strict=True,
                operation_commit_ack_monotonic=write_operation_e2e_smoke.monotonic(),
            )

        self.assertEqual(converged["status"], "pass")
        self.assertEqual(attempts, 2)
        self.assertGreaterEqual(converged["results"][0]["operation_commit_to_visible_ms"], 0)
        self.assertEqual(
            converged["results"][0]["operation_commit_clock"],
            "successful_mutation_response_received",
        )

    def test_consumer_wait_retries_only_unresolved_consumers(self) -> None:
        stable_consumer = write_operation_e2e_smoke.ConsumerProbe(
            probe=http_slo_probe.HttpProbe("stable", "/api/stable", target_ms=1000),
            assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/ready", "equals", True),),
            page_key="stable-page",
            role="affected",
        )
        delayed_consumer = write_operation_e2e_smoke.ConsumerProbe(
            probe=http_slo_probe.HttpProbe("delayed", "/api/delayed", target_ms=1000),
            assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/ready", "equals", True),),
            page_key="delayed-page",
            role="affected",
        )
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="confirm",
            operations=("workbench_relation_confirm_cross_page",),
            steps=(),
            consumers=(stable_consumer, delayed_consumer),
        )
        calls = {"/api/stable": 0, "/api/delayed": 0}

        def request_fn(url: str, *_args) -> http_slo_probe.HttpProbeResponse:
            path = "/api/stable" if url.endswith("/api/stable") else "/api/delayed"
            calls[path] += 1
            refreshing = path == "/api/delayed" and calls[path] == 1
            return http_slo_probe.HttpProbeResponse(
                status_code=202 if refreshing else 200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "read_model_status": "refreshing" if refreshing else "fresh",
                        "refresh_enqueued": refreshing,
                        "ready": not refreshing,
                    }
                ).encode(),
            )

        with patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None):
            result = write_operation_e2e_smoke._wait_for_checkpoint_consumers(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=request_fn,
                variables={},
                strict=True,
            )

        self.assertEqual(result["status"], "pass")
        self.assertEqual([item["page_key"] for item in result["results"]], ["stable-page", "delayed-page"])
        self.assertEqual(calls, {"/api/stable": 1, "/api/delayed": 2})

    def test_system_audit_waits_for_transient_queue_backlog_and_requires_new_snapshot(self) -> None:
        checkpoint = _strict_checkpoint("confirm", key="confirm-key", relation_state_after="active")
        attempts = 0

        def request_fn(*_args) -> http_slo_probe.HttpProbeResponse:
            nonlocal attempts
            attempts += 1
            payload = _system_audit_payload(f"system-audit:attempt:{attempts}")
            if attempts == 1:
                payload["overall_status"] = "issues_found"
                payload["audit_status"] = {
                    "integrity": "pass",
                    "freshness": "not_fresh",
                    "queue": "backlog",
                }
                payload["summary"]["passed_business_page_count"] = 15
                payload["summary"]["database_internal_contracts"] = "issues_found"
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode(),
            )

        with patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None):
            result = write_operation_e2e_smoke._wait_for_system_audit(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=request_fn,
                excluded_audit_ids={"system-audit:attempt:1"},
            )

        self.assertEqual(attempts, 2)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["system_audit_id"], "system-audit:attempt:2")

    def test_nonconsumer_isolation_compares_post_write_payload_to_fresh_baseline(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="isolation",
            operations=("workbench_relation_confirm_bank_invoice_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe("tax", "/api/tax-offset", target_ms=1000),
                    assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/stable_total", "equals", 100),),
                    page_key="tax-offset",
                    role="isolation",
                ),
            ),
        )
        current_total = 100

        def request_fn(*_args) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {"read_model_status": "fresh", "refresh_enqueued": False, "stable_total": current_total}
                ).encode(),
            )

        baseline = write_operation_e2e_smoke._capture_isolation_baseline(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=request_fn,
            variables={},
        )
        current_total = 101
        result = write_operation_e2e_smoke._collect_checkpoint_consumers(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=request_fn,
            variables={},
            strict=True,
            isolation_baseline=baseline["values"],
        )

        self.assertEqual(baseline["status"], "pass")
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["results"][0]["assertions"][0]["error"], "non_consumer_changed")

    def test_isolation_baseline_waits_for_transient_refresh_before_recovery(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="recovery",
            operations=("turnover_relation_withdraw_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe("isolation", "/api/isolation", target_ms=1000),
                    assertions=(
                        write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/id", "equals", "stable"),
                    ),
                    page_key="input-invoice-usage",
                    role="isolation",
                ),
            ),
        )
        attempts = 0

        def refreshing_then_fresh(*_args) -> http_slo_probe.HttpProbeResponse:
            nonlocal attempts
            attempts += 1
            status = 202 if attempts == 1 else 200
            payload = (
                {"read_model_status": "refreshing", "refresh_enqueued": True}
                if status == 202
                else {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "rows": [{"id": "stable"}],
                }
            )
            return http_slo_probe.HttpProbeResponse(
                status_code=status,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode(),
            )

        with patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None):
            baseline = write_operation_e2e_smoke._capture_isolation_baseline(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=refreshing_then_fresh,
                variables={},
            )

        self.assertEqual(baseline["status"], "pass")
        self.assertEqual(attempts, 2)
        self.assertEqual(
            baseline["values"]["input-invoice-usage\x1f/rows/0/id"],
            "stable",
        )

    def test_isolation_baseline_does_not_block_recovery_on_slow_fresh_read(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="recovery",
            operations=("turnover_relation_withdraw_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe("isolation", "/api/isolation", target_ms=0),
                    assertions=(
                        write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/id", "equals", "stable"),
                    ),
                    page_key="input-invoice-usage",
                    role="isolation",
                ),
            ),
        )

        def slow_but_fresh(*_args) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "read_model_status": "fresh",
                        "refresh_enqueued": False,
                        "rows": [{"id": "stable"}],
                    }
                ).encode(),
            )

        baseline = write_operation_e2e_smoke._capture_isolation_baseline(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=slow_but_fresh,
            variables={},
        )

        self.assertEqual(baseline["status"], "pass")
        self.assertEqual(
            baseline["values"]["input-invoice-usage\x1f/rows/0/id"],
            "stable",
        )

    def test_terminal_consumer_failure_does_not_stop_other_consumer_convergence(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="confirm",
            operations=("workbench_relation_confirm_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe("turnover", "/api/turnover-ledger"),
                    assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/ready", "equals", True),),
                    page_key="bank-turnover",
                ),
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe("cost", "/api/cost-statistics/explorer"),
                    assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/ready", "equals", True),),
                    page_key="cost-statistics",
                ),
            ),
        )
        terminal = {
            "page_key": "bank-turnover",
            "name": "turnover",
            "path": "/api/turnover-ledger",
            "role": "affected",
            "status": "fail",
            "error": "consumer_slo_miss:1044>1000",
        }
        refreshing = {
            "page_key": "cost-statistics",
            "name": "cost",
            "path": "/api/cost-statistics/explorer",
            "role": "affected",
            "status": "fail",
            "error": "consumer_read_model_not_fresh",
        }
        converged = {
            "page_key": "cost-statistics",
            "name": "cost",
            "path": "/api/cost-statistics/explorer",
            "role": "affected",
            "status": "pass",
            "operation_commit_to_visible_ms": 900.0,
        }

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._collect_checkpoint_consumers",
                side_effect=[
                    {"status": "fail", "consumer_count": 2, "results": [terminal, refreshing]},
                    {"status": "pass", "consumer_count": 1, "results": [converged]},
                ],
            ) as collect,
            patch("fin_ops_platform.tools.write_operation_e2e_smoke.sleep", return_value=None),
        ):
            result = write_operation_e2e_smoke._wait_for_checkpoint_consumers(
                checkpoint,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                headers={"Authorization": "Bearer token"},
                timeout_seconds=1,
                poll_interval_seconds=0.05,
                request_fn=lambda *_args: http_slo_probe.HttpProbeResponse(200, {}, b"{}"),
                variables={},
                strict=True,
            )

        self.assertEqual(collect.call_count, 2)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["results"][0]["error"], "consumer_slo_miss:1044>1000")
        self.assertEqual(result["results"][1]["status"], "pass")

    def test_cost_consumer_does_not_require_unrelated_source_version_change(self) -> None:
        checkpoint = write_operation_e2e_smoke.WriteCheckpoint(
            name="cost-all-causal",
            operations=("workbench_relation_confirm_cross_page",),
            steps=(),
            consumers=(
                write_operation_e2e_smoke.ConsumerProbe(
                    probe=http_slo_probe.HttpProbe(
                        "cost-all",
                        "/api/cost-statistics/explorer?scope=all&view=time&project_scope=active",
                        target_ms=1000,
                    ),
                    assertions=(
                        write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/linked", "equals", True),
                    ),
                    page_key="cost-statistics",
                    role="affected",
                ),
            ),
        )

        def request_fn(*_args) -> http_slo_probe.HttpProbeResponse:
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "read_model_status": "fresh",
                        "read_model_scope_key": "active:all",
                        "refresh_enqueued": False,
                        "source_versions": {"bank_detail": 1},
                        "rows": [{"linked": True}],
                    }
                ).encode(),
            )

        result = write_operation_e2e_smoke._collect_checkpoint_consumers(
            checkpoint,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            headers={"Authorization": "Bearer token"},
            timeout_seconds=1,
            request_fn=request_fn,
            variables={},
            strict=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["results"][0]["assertions"], [
            {"pointer": "/rows/0/linked", "operator": "equals", "status": "pass"}
        ])

    def test_admin_system_audit_preflight_blocks_first_mutation(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(_strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        calls: list[tuple[str, str]] = []

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            calls.append((method, url))
            return http_slo_probe.HttpProbeResponse(
                status_code=403,
                headers={"content-type": "application/json"},
                body=b'{"error":"forbidden"}',
            )

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
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
        self.assertEqual(
            calls, [("GET", f"https://example.test/fin-ops-api{write_operation_e2e_smoke.SYSTEM_AUDIT_PATH}")]
        )
        self.assertEqual(report["results"][0]["checkpoints"], [])

    def test_ordered_checkpoints_have_independent_timestamps_exact_events_consumers_and_audits(self) -> None:
        checkpoints = (
            _strict_checkpoint("confirm-link", key="confirm-key", relation_state_after="active"),
            _strict_checkpoint("withdraw-link", key="withdraw-key", relation_state_after="inactive"),
        )
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=checkpoints,
            recovery_checkpoint=_strict_checkpoint("recover", key="recovery-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        audit_count = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count
            if "page-audit" in url:
                audit_count += 1
                response = _system_audit_payload(f"system-audit:{audit_count}")
            elif url.endswith("/api/consumer"):
                response = {"read_model_status": "fresh", "refresh_enqueued": False, "rows": [{"linked": True}]}
            else:
                response = {"ok": True}
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(response).encode(),
            )

        timestamps = iter(
            [
                datetime(2026, 7, 12, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 12, 1, 1, tzinfo=timezone.utc),
            ]
        )
        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._database_timestamp",
                side_effect=lambda connection: next(timestamps),
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                side_effect=[["event-confirm"], ["event-withdraw"]],
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                return_value={"status": "pass", "results": []},
            ) as wait_slo,
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "pass")
        self.assertNotEqual(result["checkpoints"][0]["started_at"], result["checkpoints"][1]["started_at"])
        self.assertEqual(wait_slo.call_args_list[0].kwargs["event_ids"], ["event-confirm"])
        self.assertEqual(wait_slo.call_args_list[1].kwargs["event_ids"], ["event-withdraw"])
        self.assertNotEqual(
            result["checkpoints"][0]["system_audit"]["system_audit_id"],
            result["checkpoints"][1]["system_audit"]["system_audit_id"],
        )

    def test_zero_fanout_receipt_skips_durable_lookup_and_does_not_leak_to_next_checkpoint(self) -> None:
        checkpoints = (
            _strict_checkpoint("confirm-link", key="confirm-key", relation_state_after="active"),
            _strict_checkpoint("withdraw-link", key="withdraw-key", relation_state_after="inactive"),
        )
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=checkpoints,
            recovery_checkpoint=_strict_checkpoint("recover", key="recovery-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        audit_count = 0
        mutation_count = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count, mutation_count
            if "page-audit" in url:
                audit_count += 1
                response = _system_audit_payload(f"system-audit:zero-fanout:{audit_count}")
            elif url.endswith("/api/consumer"):
                response = {"read_model_status": "fresh", "refresh_enqueued": False, "rows": [{"linked": True}]}
            else:
                mutation_count += 1
                response = {"ok": True, **({"outbox_event_ids": []} if mutation_count == 1 else {})}
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(response).encode(),
            )

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                return_value=["event-withdraw"],
            ) as durable_receipt,
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                return_value={"status": "pass", "results": []},
            ) as wait_slo,
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
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
        durable_receipt.assert_called_once_with(
            unittest.mock.ANY,
            tenant_id="default",
            idempotency_key="withdraw-key",
        )
        self.assertIsNone(wait_slo.call_args_list[0].kwargs["event_ids"])
        self.assertEqual(wait_slo.call_args_list[1].kwargs["event_ids"], ["event-withdraw"])

    def test_committed_confirm_gate_failure_runs_declared_recovery_and_keeps_original_failure(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(_strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        audit_count = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count
            if "page-audit" in url:
                audit_count += 1
                response = _system_audit_payload(f"system-audit:recovery:{audit_count}")
            elif url.endswith("/api/consumer"):
                response = {"read_model_status": "fresh", "refresh_enqueued": False, "rows": [{"linked": True}]}
            else:
                response = {"ok": True}
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(response).encode(),
            )

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                side_effect=[["event-confirm"], ["event-recover"]],
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                side_effect=[{"status": "fail", "error": "timeout"}, {"status": "pass", "results": []}],
            ),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(result["checkpoints"][0]["write_slo"]["status"], "fail")
        self.assertEqual(result["recovery"]["status"], "pass")
        self.assertFalse(result["recovery_required"])

    def test_committed_write_slo_miss_runs_recovery_before_read_side_convergence(self) -> None:
        isolation_consumer = write_operation_e2e_smoke.ConsumerProbe(
            probe=http_slo_probe.HttpProbe("isolation", "/api/isolation", target_ms=1000),
            assertions=(write_operation_e2e_smoke.JsonPointerAssertion("/rows/0/id", "equals", "stable"),),
            page_key="output-invoice-collections",
            role="isolation",
        )

        def checkpoint(name: str, *, key: str, relation_state_after: str) -> write_operation_e2e_smoke.WriteCheckpoint:
            return write_operation_e2e_smoke.WriteCheckpoint(
                name=name,
                operations=("workbench_relation_withdraw",),
                steps=(
                    write_operation_e2e_smoke.WriteStep(
                        name=name,
                        method="POST",
                        path=f"/api/{name}",
                        json_body={"idempotency_key": key, "row_ids": ["test-row-1"]},
                        expected_statuses=(200,),
                    ),
                ),
                consumers=(isolation_consumer,),
                system_audit_path=write_operation_e2e_smoke.SYSTEM_AUDIT_PATH,
                relation_state_after=relation_state_after,
            )

        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        mutation_started = False
        refresh_ready = False
        audit_count = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count
            if "page-audit" in url:
                audit_count += 1
                payload = _system_audit_payload(f"system-audit:slo-recovery:{audit_count}")
                status = 200
            elif url.endswith("/api/isolation") and mutation_started and not refresh_ready:
                payload = {"read_model_status": "refreshing", "refresh_enqueued": True}
                status = 202
            else:
                payload = {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "rows": [{"id": "stable"}],
                }
                status = 200
            return http_slo_probe.HttpProbeResponse(
                status_code=status,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode(),
            )

        execute_count = 0

        def execute_step(*_args, **_kwargs):
            nonlocal execute_count, mutation_started
            execute_count += 1
            mutation_started = True
            result = write_operation_e2e_smoke.WriteStepResult(
                name="confirm" if execute_count == 1 else "recover",
                method="POST",
                path="/api/confirm" if execute_count == 1 else "/api/recover",
                status="fail" if execute_count == 1 else "pass",
                elapsed_ms=5270.0 if execute_count == 1 else 500.0,
                status_code=200,
                response_bytes=2,
                content_type="application/json",
                error="write_step_slo_miss:5270.0>5000.0" if execute_count == 1 else None,
            )
            return write_operation_e2e_smoke._ExecutedStep(
                result=result,
                captures={
                    write_operation_e2e_smoke._RESPONSE_OUTBOX_EVENT_IDS: [
                        "event-confirm" if execute_count == 1 else "event-recover"
                    ]
                },
                committed=True,
                ambiguous=False,
            )

        wait_event_ids: list[list[str]] = []

        def wait_for_write_slo(*_args, **kwargs):
            nonlocal refresh_ready
            wait_event_ids.append(list(kwargs["event_ids"]))
            refresh_ready = True
            return {"status": "pass", "results": []}

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._execute_step",
                side_effect=execute_step,
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                side_effect=wait_for_write_slo,
            ),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(result["checkpoints"][0]["steps"][0]["error"], "write_step_slo_miss:5270.0>5000.0")
        self.assertNotIn("recovery_precondition", result["checkpoints"][0])
        self.assertEqual(wait_event_ids, [["event-recover"]])
        self.assertEqual(result["recovery"]["status"], "pass")
        self.assertFalse(result["recovery_required"])

    def test_committed_withdraw_gate_failure_does_not_issue_a_second_withdraw(self) -> None:
        checkpoints = (
            _strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),
            _strict_checkpoint("withdraw", key="withdraw-key", relation_state_after="inactive"),
        )
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=checkpoints,
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        audit_count = 0
        mutation_calls = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count, mutation_calls
            if "page-audit" in url:
                audit_count += 1
                response = _system_audit_payload(f"system-audit:withdraw:{audit_count}")
            elif url.endswith("/api/consumer"):
                response = {"read_model_status": "fresh", "refresh_enqueued": False, "rows": [{"linked": True}]}
            else:
                mutation_calls += 1
                response = {"ok": True}
            return http_slo_probe.HttpProbeResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(response).encode(),
            )

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                side_effect=[["event-confirm"], ["event-withdraw"]],
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                side_effect=[{"status": "pass", "results": []}, {"status": "fail", "error": "timeout"}],
            ),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(mutation_calls, 2)
        self.assertNotIn("recovery", result)
        self.assertFalse(result["recovery_required"])

    def test_ambiguous_mutation_is_not_blindly_retried_or_cleaned_up(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(_strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        calls = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal calls
            calls += 1
            if "page-audit" in url:
                return http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(_system_audit_payload("system-audit:preflight")).encode(),
                )
            raise TimeoutError("network result unknown")

        report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
            FakeConnection([]),
            scenarios=[scenario],
            apply=True,
            base_url="https://example.test",
            api_prefix="/fin-ops-api",
            tenant_id="default",
            headers={"Authorization": "Bearer token"},
            approval_reference="TEST-APPROVAL",
            request_fn=request_fn,
        )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(calls, 2)
        self.assertNotIn("recovery", result)
        self.assertTrue(result["recovery_required"])

    def test_http_500_after_durable_commit_runs_recovery(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(_strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        mutation_calls = 0
        audit_count = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal mutation_calls, audit_count
            if "page-audit" in url:
                audit_count += 1
                payload = _system_audit_payload(f"system-audit:500-commit:{audit_count}")
                return http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(payload).encode(),
                )
            if url.endswith("/api/consumer"):
                return http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=b'{"read_model_status":"fresh","refresh_enqueued":false,"rows":[{"linked":true}]}',
                )
            mutation_calls += 1
            return http_slo_probe.HttpProbeResponse(
                status_code=500 if mutation_calls == 1 else 200,
                headers={"content-type": "application/json"},
                body=b'{"error":"gateway_response_mapping_failed"}' if mutation_calls == 1 else b'{"ok":true}',
            )

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.workbench_idempotency_evidence",
                return_value={"status": "committed", "outbox_event_ids": ["event-confirm"], "response_payload": {}},
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                return_value=["event-recover"],
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                return_value={"status": "pass", "results": []},
            ),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertTrue(result["checkpoints"][0]["mutation_committed"])
        self.assertFalse(result["checkpoints"][0]["mutation_ambiguous"])
        self.assertEqual(result["recovery"]["status"], "pass")
        self.assertFalse(result["recovery_required"])
        self.assertEqual(mutation_calls, 2)

    def test_http_500_without_durable_record_requires_manual_recovery(self) -> None:
        scenario = write_operation_e2e_smoke.WriteScenario(
            name="closure",
            operations=(),
            steps=(),
            post_api_probes=(),
            checkpoints=(_strict_checkpoint("confirm", key="confirm-key", relation_state_after="active"),),
            recovery_checkpoint=_strict_checkpoint("recover", key="recover-key", relation_state_after="inactive"),
            fixture_ownership="test_owned",
        )
        mutation_calls = 0

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal mutation_calls
            if "page-audit" in url:
                return http_slo_probe.HttpProbeResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=json.dumps(_system_audit_payload("system-audit:500-missing")).encode(),
                )
            mutation_calls += 1
            return http_slo_probe.HttpProbeResponse(
                status_code=500,
                headers={"content-type": "application/json"},
                body=b'{"error":"unknown"}',
            )

        with patch(
            "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.workbench_idempotency_evidence",
            side_effect=ValueError("expected exactly one Workbench idempotency record"),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertFalse(result["checkpoints"][0]["mutation_committed"])
        self.assertTrue(result["checkpoints"][0]["mutation_ambiguous"])
        self.assertTrue(result["recovery_required"])
        self.assertNotIn("recovery", result)
        self.assertEqual(mutation_calls, 1)

    def test_turnover_http_500_after_commit_recovers_relation_id_from_durable_response(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenario.json"
            path.write_text(
                json.dumps([_raw_bank_turnover_scenario("turnover-500", "turnover-500")]),
                encoding="utf-8",
            )
            scenario = write_operation_e2e_smoke.load_scenarios(path, http_target_ms=1000)[0]

        audit_count = 0
        mutation_paths: list[str] = []

        def request_fn(
            url: str, method: str, headers, body, timeout_seconds: float
        ) -> http_slo_probe.HttpProbeResponse:
            nonlocal audit_count
            route = url.split("/fin-ops-api", 1)[-1]
            if "page-audit" in route:
                audit_count += 1
                payload = _system_audit_payload(f"system-audit:turnover-500:{audit_count}")
                status = 200
            elif method == "POST":
                mutation_paths.append(route)
                payload = {"error": "post_commit_mapping_failed"} if len(mutation_paths) == 1 else {"ok": True}
                status = 500 if len(mutation_paths) == 1 else 200
            elif route.startswith("/api/cost-statistics/explorer"):
                payload = {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "rows": [{"transaction_id": "turnover-bank-test-1"}],
                }
                status = 200
            elif route.startswith("/api/input-invoice-usage/rows"):
                payload = {"read_model_status": "fresh", "refresh_enqueued": False, "rows": []}
                status = 200
            elif route.startswith("/api/workbench/groups"):
                payload = {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "groups": [{"bank_rows": [{"id": "turnover-bank-test-1"}]}],
                }
                status = 200
            else:
                payload = {
                    "read_model_status": "fresh",
                    "refresh_enqueued": False,
                    "rows": [{"id": "turnover-bank-test-1"}],
                }
                status = 200
            return http_slo_probe.HttpProbeResponse(
                status_code=status,
                headers={"content-type": "application/json"},
                body=json.dumps(payload).encode(),
            )

        with (
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.workbench_idempotency_evidence",
                return_value={
                    "status": "committed",
                    "outbox_event_ids": ["event-confirm"],
                    "response_payload": {
                        "workbench_pair_relation": {"case_id": "turnover:closure-500"}
                    },
                },
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke.write_operation_slo_audit.committed_workbench_outbox_event_ids",
                return_value=["event-recovery"],
            ),
            patch(
                "fin_ops_platform.tools.write_operation_e2e_smoke._wait_for_write_slo",
                return_value={"status": "pass", "results": []},
            ),
        ):
            report = write_operation_e2e_smoke.run_write_operation_e2e_smoke(
                FakeConnection([]),
                scenarios=[scenario],
                apply=True,
                base_url="https://example.test",
                api_prefix="/fin-ops-api",
                tenant_id="default",
                headers={"Authorization": "Bearer token"},
                approval_reference="TEST-APPROVAL",
                request_fn=request_fn,
            )

        result = report["results"][0]
        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            mutation_paths,
            [
                "/api/turnover-ledger/closures/confirm",
                "/api/turnover-ledger/closures/withdraw",
            ],
        )
        self.assertEqual(result["recovery"]["status"], "pass")
        self.assertFalse(result["recovery_required"])


if __name__ == "__main__":
    unittest.main()
