from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import write_operation_scenario_discovery as discovery


class FakeConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from app.turnover_relations" in normalized:
            return [
                {
                    "relation_id": "turnover_rel_1",
                    "status": "deterministic",
                    "relation_type": "business",
                    "source": "manual",
                    "scope_month": "2026-06-01",
                    "case_id": "turnover:turnover_rel_1",
                    "row_ids": ["txn-1", "oa-1"],
                    "row_count": 2,
                    "relation_mode": "turnover_manual_closure",
                    "version": 3,
                    "updated_at": "2026-06-13T10:00:00+08:00",
                }
            ]
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "CASE-1",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-06-01",
                    "row_ids": ["oa-1", "bank-1"],
                    "version": 4,
                    "updated_at": "2026-06-13T10:00:00+08:00",
                }
            ]
        if "from app.no_oa_bank_batches" in normalized:
            return [
                {
                    "batch_id": "BATCH-1",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "scope_month": "2026-06-01",
                    "row_count": 1,
                    "month_batch_count": 1,
                    "version": 5,
                    "updated_at": "2026-06-13T10:00:00+08:00",
                }
            ]
        raise AssertionError(sql)


class EmptyCandidateConnection:
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return []


class MultiCandidateConnection(FakeConnection):
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from app.turnover_relations" in normalized:
            return []
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": f"CASE-{index}",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "month_scope": "2026-06-01",
                    "row_ids": [f"oa-{index}", f"bank-{index}"],
                    "row_count": 2,
                    "version": index,
                    "updated_at": f"2026-06-13T10:00:0{index}+08:00",
                }
                for index in range(1, 4)
            ]
        if "from app.no_oa_bank_batches" in normalized:
            return [
                {
                    "batch_id": f"BATCH-{index}",
                    "status": "submitted",
                    "status_bucket": "submitted",
                    "scope_month": "2026-06-01",
                    "row_count": 1,
                    "month_batch_count": 2,
                    "version": index,
                    "updated_at": f"2026-06-13T10:00:0{index}+08:00",
                }
                for index in range(1, 3)
            ]
        raise AssertionError(sql)


class WriteOperationScenarioDiscoveryTests(unittest.TestCase):
    def test_discovers_turnover_scenario_and_context_candidates(self) -> None:
        report = discovery.discover_write_operation_scenarios(FakeConnection(), limit=5)

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["candidate_counts"]["turnover_manual_closure_or_withdraw"], 1)
        self.assertEqual(report["candidate_counts"]["workbench_pair_withdraw_context"], 1)
        self.assertEqual(report["candidate_counts"]["no_oa_bank_batch_withdraw_context"], 1)
        scenarios = report["scenario_json"]["scenarios"]
        self.assertEqual(len(scenarios), 3)
        operations = [scenario["operation"] for scenario in scenarios]
        self.assertEqual(
            operations,
            [
                "turnover_manual_closure_or_withdraw",
                "workbench_relation_withdraw",
                "no_oa_bank_batch_withdraw",
            ],
        )
        self.assertEqual(scenarios[0]["steps"][0]["path"], "/api/workbench/actions/withdraw-link")
        self.assertEqual(scenarios[0]["steps"][0]["json"]["row_ids"], ["txn-1", "oa-1"])
        self.assertEqual(scenarios[0]["metadata"]["candidate_case_id"], "turnover:turnover_rel_1")
        self.assertEqual(scenarios[1]["steps"][0]["path"], "/api/workbench/actions/withdraw-link")
        self.assertEqual(scenarios[1]["steps"][0]["json"]["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(scenarios[2]["steps"][0]["path"], "/api/no-oa-bank-batches/BATCH-1/withdraw")
        self.assertTrue(all("requires_manual_approval_before_apply" not in scenario["metadata"] for scenario in scenarios))
        self.assertEqual(
            scenarios[0]["metadata"]["approval_ticket"],
            "FINOPS-WRITE-SMOKE-STANDING-20260702",
        )
        self.assertEqual(
            report["standard_inputs"]["scenario_path"],
            "/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json",
        )

    def test_turnover_discovery_matches_withdraw_boundary_source_contract(self) -> None:
        connection = FakeConnection()

        report = discovery.discover_write_operation_scenarios(connection, limit=5)

        turnover_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "from app.turnover_relations" in " ".join(sql.lower().split())
        )
        self.assertIn("raw_payload->'normalized_payload'->>'source'", turnover_sql)
        self.assertIn("= 'manual'", turnover_sql)
        self.assertIn("join app.workbench_pair_relations", turnover_sql)
        self.assertNotIn("<> 'system'", turnover_sql)
        turnover = report["candidates"]["turnover_manual_closure_or_withdraw"][0]
        self.assertEqual(turnover["source"], "manual")
        self.assertEqual(turnover["candidate_path"], "/api/workbench/actions/withdraw-link")

    def test_generated_context_scenarios_are_guarded_by_standing_ticket(self) -> None:
        report = discovery.discover_write_operation_scenarios(FakeConnection(), limit=5)
        scenarios = report["scenario_json"]["scenarios"]

        self.assertTrue(
            all(
                scenario["metadata"]["approval_ticket_policy"]
                == "standing_ticket_allowed_for_controlled_reversible_smoke"
                for scenario in scenarios
            )
        )
        self.assertTrue(report["safety"]["requires_real_auth_to_apply"])
        self.assertTrue(report["safety"]["requires_approval_ticket_before_apply"])
        self.assertNotIn("requires_manual_approval_before_apply", report["safety"])
        self.assertEqual(report["safety"]["approval_ticket"], "FINOPS-WRITE-SMOKE-STANDING-20260702")

    def test_standard_apply_scenarios_are_capped_per_operation(self) -> None:
        report = discovery.discover_write_operation_scenarios(MultiCandidateConnection(), limit=5)

        self.assertEqual(report["candidate_counts"]["workbench_pair_withdraw_context"], 3)
        self.assertEqual(report["candidate_counts"]["no_oa_bank_batch_withdraw_context"], 2)
        scenarios = report["scenario_json"]["scenarios"]
        self.assertEqual(
            [scenario["operation"] for scenario in scenarios],
            ["workbench_relation_withdraw", "no_oa_bank_batch_withdraw"],
        )
        self.assertEqual(scenarios[0]["name"], "workbench-withdraw-CASE-1")
        self.assertEqual(scenarios[1]["name"], "no-oa-withdraw-BATCH-1")

    def test_no_oa_discovery_requires_active_relation_contract(self) -> None:
        connection = FakeConnection()

        discovery.discover_write_operation_scenarios(connection, limit=5)

        no_oa_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "from app.no_oa_bank_batches" in " ".join(sql.lower().split())
        )
        normalized_sql = " ".join(no_oa_sql.lower().split())
        self.assertIn("join app.workbench_pair_relations relation", normalized_sql)
        self.assertIn("batch.raw_payload->'normalized_payload'->>'relation_case_id'", normalized_sql)
        self.assertIn("relation.status = 'active'", normalized_sql)
        self.assertIn("relation.relation_mode = 'no_oa_bank_batch'", normalized_sql)
        self.assertIn("batch.raw_payload->'normalized_payload'->>'relation_mode'", normalized_sql)
        self.assertIn("= 'no_oa_bank_batch'", normalized_sql)

    def test_report_defines_page_write_scenario_policy_and_standing_ticket(self) -> None:
        report = discovery.discover_write_operation_scenarios(FakeConnection(), limit=5)

        policy_by_page = {policy["page_key"]: policy for policy in report["page_write_scenario_policy"]}

        self.assertEqual(
            policy_by_page["turnover-ledger"]["scenario_operations"],
            ["turnover_manual_closure_or_withdraw"],
        )
        self.assertEqual(
            policy_by_page["reconciliation-workbench"]["approval_ticket"],
            "FINOPS-WRITE-SMOKE-STANDING-20260702",
        )
        self.assertEqual(policy_by_page["bank-details"]["apply_policy"], "fanout_evidence")
        self.assertEqual(
            policy_by_page["bank-details"]["scenario_operations"],
            [
                "turnover_manual_closure_or_withdraw",
                "workbench_relation_withdraw",
                "no_oa_bank_batch_withdraw",
            ],
        )
        self.assertEqual(policy_by_page["settings"]["apply_policy"], "no_standing_production_apply")
        self.assertEqual(policy_by_page["settings"]["approval_ticket"], "")
        for page_key, policy in policy_by_page.items():
            if policy["apply_policy"] == "no_standing_production_apply":
                self.assertEqual(policy["scenario_operations"], [], page_key)
                self.assertEqual(
                    policy["approval_ticket_policy"],
                    "standing_ticket_not_allowed_use_staging_or_single_use_approval",
                )
                continue
            self.assertEqual(policy["scenario_env"], "FIN_OPS_WRITE_E2E_SCENARIO", page_key)
            self.assertEqual(policy["approval_ticket_env"], "FIN_OPS_WRITE_E2E_APPROVAL_TICKET", page_key)
            self.assertEqual(policy["approval_ticket"], "FINOPS-WRITE-SMOKE-STANDING-20260702", page_key)

    def test_cli_writes_report_and_scenario_files_without_mutating(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            scenario_path = Path(temp_dir) / "scenario.json"
            stdout = StringIO()
            with patch.object(discovery.PostgresSettings, "from_env", return_value=object()), patch.object(
                discovery,
                "PostgresConnection",
                return_value=FakeConnection(),
            ):
                exit_code = discovery.main(
                    [
                        "--output",
                        str(report_path),
                        "--scenario-output",
                        str(scenario_path),
                    ],
                    stdout=stdout,
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["mode"], "read_only")
        self.assertTrue(report["scenario_output"]["written"])
        self.assertEqual(report["scenario_output"]["scenario_count"], 3)
        self.assertEqual(
            scenario["standard_inputs"]["approval_ticket"],
            "FINOPS-WRITE-SMOKE-STANDING-20260702",
        )
        self.assertIn("page_write_scenario_policy", scenario)
        self.assertEqual(len(scenario["scenarios"]), 3)

    def test_cli_does_not_write_empty_scenario_file_when_no_candidates_are_found(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            scenario_path = Path(temp_dir) / "scenario.json"
            stdout = StringIO()
            with patch.object(discovery.PostgresSettings, "from_env", return_value=object()), patch.object(
                discovery,
                "PostgresConnection",
                return_value=EmptyCandidateConnection(),
            ):
                exit_code = discovery.main(
                    [
                        "--output",
                        str(report_path),
                        "--scenario-output",
                        str(scenario_path),
                    ],
                    stdout=stdout,
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            stdout_report = json.loads(stdout.getvalue())

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["status"], "no_candidates")
        self.assertEqual(stdout_report["status"], "no_candidates")
        self.assertFalse(report["scenario_output"]["written"])
        self.assertEqual(report["scenario_output"]["reason"], "no_candidates")
        self.assertFalse(scenario_path.exists())

    def test_cli_returns_configuration_missing_when_postgres_url_is_absent(self) -> None:
        env = {
            "FIN_OPS_APP_STORAGE_BACKEND": "postgres",
            "FIN_OPS_POSTGRES_DATABASE_URL": "",
            "DATABASE_URL": "",
        }
        stdout = StringIO()

        with patch.dict(os.environ, env, clear=False):
            exit_code = discovery.main(["--json"], stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(payload["status"], "configuration_missing")
        self.assertEqual(payload["tool"], "write_operation_scenario_discovery")
        self.assertEqual(payload["error"], "postgres_configuration_missing")


if __name__ == "__main__":
    unittest.main()
