from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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
                    "source": "",
                    "scope_month": "2026-06-01",
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
                    "version": 5,
                    "updated_at": "2026-06-13T10:00:00+08:00",
                }
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
        self.assertEqual(scenarios[0]["steps"][0]["path"], "/api/turnover-ledger/relations/turnover_rel_1/withdraw")
        self.assertEqual(scenarios[1]["steps"][0]["path"], "/api/workbench/actions/withdraw-link")
        self.assertEqual(scenarios[1]["steps"][0]["json"]["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(scenarios[2]["steps"][0]["path"], "/api/no-oa-bank-batches/BATCH-1/withdraw")
        self.assertTrue(all(scenario["metadata"]["requires_manual_approval_before_apply"] for scenario in scenarios))

    def test_generated_context_scenarios_are_guarded_by_manual_approval(self) -> None:
        report = discovery.discover_write_operation_scenarios(FakeConnection(), limit=5)
        scenarios = report["scenario_json"]["scenarios"]

        self.assertTrue(
            all(
                scenario["metadata"]["requires_manual_approval_before_apply"]
                for scenario in scenarios
            )
        )
        self.assertTrue(report["safety"]["requires_real_auth_to_apply"])
        self.assertTrue(report["safety"]["requires_manual_approval_before_apply"])

    def test_cli_writes_report_and_scenario_files_without_mutating(self) -> None:
        with TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "report.json"
            scenario_path = Path(temp_dir) / "scenario.json"
            with unittest.mock.patch.object(discovery.PostgresSettings, "from_env", return_value=object()), unittest.mock.patch.object(
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
                    ]
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(report["mode"], "read_only")
        self.assertEqual(len(scenario["scenarios"]), 3)


if __name__ == "__main__":
    unittest.main()
