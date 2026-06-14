from __future__ import annotations

import io
import json
import unittest

from fin_ops_platform.tools import workbench_relation_history_replay


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-a",
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "row_ids": ["bank-1", "invoice-1"],
                    "row_types": ["bank", "invoice"],
                    "raw_payload": {
                        "normalized_payload": {
                            "case_id": "case-a",
                            "row_ids": ["bank-1", "invoice-1"],
                            "row_types": ["bank", "invoice"],
                        }
                    },
                },
                {
                    "case_id": "case-b",
                    "relation_mode": "no_oa_bank_batch",
                    "status": "active",
                    "row_ids": ["bank-1"],
                    "row_types": ["bank"],
                    "raw_payload": {"normalized_payload": {"case_id": "case-b"}},
                },
                {
                    "case_id": "case-bad",
                    "relation_mode": "page_private_mode",
                    "status": "active",
                    "row_ids": ["oa-1", "invoice-2"],
                    "row_types": ["oa"],
                    "raw_payload": {"normalized_payload": {"case_id": "case-bad"}},
                },
                {
                    "case_id": "legacy-cancelled",
                    "relation_mode": "legacy_page_private_mode",
                    "status": "cancelled",
                    "row_ids": ["bank-legacy"],
                    "row_types": ["bank"],
                    "raw_payload": {"normalized_payload": {"case_id": "legacy-cancelled"}},
                },
                {
                    "case_id": "case-display-only",
                    "relation_mode": "existing_case",
                    "status": "active",
                    "row_ids": ["invoice-display"],
                    "row_types": ["invoice"],
                    "raw_payload": {"normalized_payload": {"case_id": "case-display-only"}},
                },
            ]
        if "from app.workbench_pair_relation_history" in normalized:
            return [
                {
                    "case_id": "case-a",
                    "event_type": "confirm_link",
                    "before_payload": [
                        {
                            "case_id": "case-display-history",
                            "relation_mode": "existing_case",
                            "status": "active",
                            "row_ids": ["bank-1", "invoice-1"],
                            "row_types": ["bank", "invoice"],
                        },
                        {
                            "case_id": "case-unmarked-manual-history",
                            "relation_mode": "manual_confirmed",
                            "status": "active",
                            "row_ids": ["bank-2", "invoice-2"],
                            "row_types": ["bank", "invoice"],
                        }
                    ],
                    "after_payload": [],
                    "raw_payload": {"normalized_payload": {"operation_type": "confirm_link"}},
                },
                {
                    "case_id": "orphan-case",
                    "event_type": "confirm_link",
                    "before_payload": [],
                    "after_payload": [],
                    "raw_payload": {"normalized_payload": {"operation_type": "confirm_link"}},
                },
            ]
        if "from read_model.app_status_readiness" in normalized:
            return [{"read_model_key": "workbench_relation", "status": "fresh", "scope_key": "all"}]
        return []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        return 1


class WorkbenchRelationHistoryReplayToolTests(unittest.TestCase):
    def test_dry_run_reports_relation_issues_without_writing(self) -> None:
        stdout = io.StringIO()
        connection = FakeConnection()

        exit_code = workbench_relation_history_replay.main(
            ["--json"],
            connection=connection,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["overall_status"], "issues_found")
        issue_codes = {issue["code"] for issue in payload["issues"]}
        self.assertIn("active_row_occupied_by_multiple_cases", issue_codes)
        self.assertIn("row_ids_row_types_length_mismatch", issue_codes)
        self.assertIn("unknown_relation_mode", issue_codes)
        self.assertIn("display_only_relation_mode_in_write_model", issue_codes)
        self.assertIn("display_only_relation_in_confirm_history", issue_codes)
        self.assertIn("non_restorable_relation_in_confirm_history", issue_codes)
        self.assertIn("relation_without_history", issue_codes)
        self.assertIn("orphan_history_case", issue_codes)
        self.assertEqual(payload["summary"]["display_only_history_before_relation_count"], 1)
        self.assertEqual(payload["summary"]["non_restorable_history_before_relation_count"], 2)
        unknown_mode_issues = [
            issue
            for issue in payload["issues"]
            if issue["code"] == "unknown_relation_mode"
        ]
        self.assertIn(
            {
                "status": "active",
                "relation_mode": "page_private_mode",
            },
            [issue["details"] for issue in unknown_mode_issues],
        )
        self.assertIn(
            {
                "status": "cancelled",
                "relation_mode": "legacy_page_private_mode",
            },
            [issue["details"] for issue in unknown_mode_issues],
        )
        severity_by_mode = {
            issue["details"]["relation_mode"]: issue["severity"]
            for issue in unknown_mode_issues
        }
        self.assertEqual(severity_by_mode["page_private_mode"], "error")
        self.assertEqual(severity_by_mode["legacy_page_private_mode"], "warning")
        display_only_write_issues = [
            issue
            for issue in payload["issues"]
            if issue["code"] == "display_only_relation_mode_in_write_model"
        ]
        self.assertEqual(display_only_write_issues[0]["severity"], "error")
        self.assertEqual(connection.executed, [])

    def test_fail_on_issues_returns_nonzero_after_printing_report(self) -> None:
        stdout = io.StringIO()

        exit_code = workbench_relation_history_replay.main(
            ["--json", "--fail-on-issues"],
            connection=FakeConnection(),
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertGreater(payload["summary"]["issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
