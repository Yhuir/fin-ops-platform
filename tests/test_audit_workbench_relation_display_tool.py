from __future__ import annotations

import io
import inspect
import json
import unittest

from fin_ops_platform.tools import audit_workbench_relation_display
from fin_ops_platform.services.postgres_repositories import workbench_page_audit
from fin_ops_platform.services.postgres_repositories import workbench_projection_audit


class FakeConnection:
    def __init__(
        self,
        *,
        relations: list[dict[str, object]] | None = None,
        generations: list[dict[str, object]] | None = None,
        group_rows: list[dict[str, object]] | None = None,
        projection_issues: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self._relations = relations if relations is not None else [_relation()]
        self._generations = generations if generations is not None else [
            _generation("2026-01", "2026-06-14 10:00:00+08"),
            _generation("2026-02", "2026-06-14 10:00:00+08"),
            _generation("all", "2026-06-14 10:01:00+08"),
        ]
        self._group_rows = group_rows if group_rows is not None else [
            _group_row("all", "bank-1"),
            _group_row("all", "invoice-1"),
            _group_row("2026-01", "bank-1"),
            _group_row("2026-01", "invoice-1"),
            _group_row("2026-02", "bank-1"),
            _group_row("2026-02", "invoice-1"),
        ]
        self._projection_issues = projection_issues or {}

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        for marker, rows in self._projection_issues.items():
            if f"/* check: {marker} */" in sql:
                return list(rows)
        if "/* check: workbench_" in sql:
            return []
        if "/* check: relation_edge_equality */" in sql:
            return []
        if "from job.read_model_dirty_scopes" in normalized or "from job.outbox_events" in normalized:
            return []
        if "from app.workbench_pair_relations" in normalized:
            return list(self._relations)
        if "from read_model.workbench_generations" in normalized and "join read_model.workbench_group_rows" not in normalized:
            return list(self._generations)
        if "from read_model.workbench_generations" in normalized and "join read_model.workbench_group_rows" in normalized:
            return list(self._group_rows)
        return []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        return 1


class AuditWorkbenchRelationDisplayToolTests(unittest.TestCase):
    def test_clean_relation_display_audit_has_no_blocking_issues(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(FakeConnection())

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["summary"]["active_relation_count"], 1)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["audit_status"], {"integrity": "pass", "freshness": "fresh", "queue": "drained"})
        self.assertIn("active_generation_relation_display", report["audit_contract"]["proof_checks"])
        self.assertIn("canonical_object_expected_set_equality", report["audit_contract"]["proof_checks"])

    def test_relation_display_can_be_clean_while_canonical_object_is_missing(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                projection_issues={
                    "workbench_canonical_object_set": [
                        {
                            "subject_id": "bank-unrelated",
                            "scope_key": "2026-01",
                            "mismatch_kind": "canonical_missing_projection",
                            "canonical_source_kind": "bank",
                            "projected_source_kind": None,
                        }
                    ]
                }
            )
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertIn(
            "workbench_canonical_object_set_mismatch",
            {issue["code"] for issue in report["issues"]},
        )

    def test_etc_summary_can_exist_while_a_canonical_detail_is_missing(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                projection_issues={
                    "workbench_etc_summary_details": [
                        {
                            "subject_id": "etc-summary-batch-1",
                            "scope_key": "all",
                            "mismatch_kind": "detail",
                            "canonical_amount": "100.00",
                            "projected_amount": None,
                        }
                    ]
                }
            )
        )

        self.assertIn(
            "workbench_etc_summary_details_mismatch",
            {issue["code"] for issue in report["issues"]},
        )

    def test_stale_generation_dependency_version_blocks_page_audit(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                projection_issues={
                    "workbench_generation_source_versions": [
                        {
                            "subject_id": "workbench:2026-01:001",
                            "scope_key": "2026-01",
                            "source_versions": {"builder": "old"},
                            "expected_builder": "current",
                        }
                    ]
                }
            )
        )

        self.assertIn(
            "workbench_generation_source_versions_mismatch",
            {issue["code"] for issue in report["issues"]},
        )

    def test_ignored_override_missing_from_projection_blocks_page_audit(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                projection_issues={
                    "workbench_override_exception_fields": [
                        {
                            "subject_id": "bank-ignored",
                            "scope_key": "all",
                            "mismatch_kind": "override",
                            "field_name": "ignored",
                            "canonical_value": True,
                            "projected_value": None,
                        }
                    ]
                }
            )
        )

        self.assertIn(
            "workbench_override_exception_fields_mismatch",
            {issue["code"] for issue in report["issues"]},
        )

    def test_reports_split_all_scope_and_stale_all_generation_without_writing(self) -> None:
        connection = FakeConnection(
            generations=[
                _generation("2026-01", "2026-06-14 10:02:00+08"),
                _generation("all", "2026-06-14 10:01:00+08"),
            ],
            group_rows=[
                _group_row("all", "bank-1", group_id="case:case-a"),
                _group_row("all", "invoice-1", group_id="scope:2026-01:temp:invoice"),
                _group_row("2026-01", "bank-1", group_id="case:case-a"),
                _group_row("2026-01", "invoice-1", group_id="case:case-a"),
            ],
        )

        report = audit_workbench_relation_display.audit_workbench_relation_display(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertGreater(report["summary"]["blocking_issue_count"], 0)
        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("relation_rows_split_across_groups", issue_codes)
        self.assertIn("all_generation_older_than_member_scope_generation", issue_codes)
        self.assertEqual(connection.executed, [])

    def test_reports_missing_member_scope_rows_and_payload_mismatch(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                group_rows=[
                    _group_row("all", "bank-1"),
                    _group_row("all", "invoice-1", payload_case_id="other-case"),
                    _group_row("2026-01", "bank-1"),
                ],
            )
        )

        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("relation_rows_missing_from_member_scope_generation", issue_codes)
        self.assertIn("relation_row_payload_case_mismatch", issue_codes)
        self.assertGreater(report["summary"]["blocking_issue_count"], 0)

    def test_reports_multi_oa_relation_bank_row_missing_source_alignment(self) -> None:
        report = audit_workbench_relation_display.audit_workbench_relation_display(
            FakeConnection(
                relations=[
                    {
                        "case_id": "case-multi-oa",
                        "relation_mode": "manual_confirmed",
                        "status": "active",
                        "row_ids": ["oa-29350", "oa-88050", "bank-29350"],
                        "row_types": ["oa", "oa", "bank"],
                        "month_scope": "2026-05-01",
                        "updated_at": "2026-06-23 09:00:00+08",
                        "raw_payload": {},
                    }
                ],
                generations=[_generation("all", "2026-06-23 09:05:00+08")],
                group_rows=[
                    _group_row("all", "oa-29350", group_id="case:case-multi-oa", payload_case_id="case-multi-oa"),
                    _group_row("all", "oa-88050", group_id="case:case-multi-oa", payload_case_id="case-multi-oa"),
                    _group_row("all", "bank-29350", group_id="case:case-multi-oa", payload_case_id="case-multi-oa"),
                ],
            )
        )

        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("relation_bank_row_missing_source_oa_alignment", issue_codes)
        self.assertGreater(report["summary"]["blocking_issue_count"], 0)

    def test_reports_visible_automatic_decision_rows_without_active_relation(self) -> None:
        connection = FakeConnection(
            relations=[],
            generations=[_generation("all", "2026-07-10 09:00:00+08")],
            group_rows=[
                _group_row(
                    "all",
                    "invoice-decision-1",
                    group_id="case:decision:decision-1",
                    payload_case_id="decision:decision-1",
                    relation_mode="automatic_decision",
                ),
            ],
        )

        report = audit_workbench_relation_display.audit_workbench_relation_display(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["summary"]["visible_automatic_decision_row_count"], 1)
        issue_codes = {issue["code"] for issue in report["issues"]}
        self.assertIn("visible_automatic_decision_group", issue_codes)
        self.assertEqual(connection.executed, [])

    def test_cli_fail_on_issues_returns_nonzero(self) -> None:
        stdout = io.StringIO()

        exit_code = audit_workbench_relation_display.main(
            ["--json", "--fail-on-issues"],
            connection=FakeConnection(
                group_rows=[
                    _group_row("all", "bank-1", group_id="case:case-a"),
                ],
            ),
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertIn("relation_rows_missing_from_all_generation", payload["summary"]["issue_counts_by_code"])

    def test_module_has_cli_entrypoint(self) -> None:
        source = inspect.getsource(audit_workbench_relation_display)
        core_source = inspect.getsource(workbench_page_audit)
        projection_source = inspect.getsource(workbench_projection_audit)

        self.assertIn('if __name__ == "__main__"', source)
        self.assertIn("raise SystemExit(main())", source)
        self.assertNotIn("from app.workbench_pair_relations", source)
        self.assertIn("from app.workbench_pair_relations", core_source)
        self.assertNotIn("ArgumentParser", core_source)
        self.assertIn("from app.oa_applications", projection_source)
        self.assertNotIn("ArgumentParser", projection_source)


def _relation() -> dict[str, object]:
    return {
        "case_id": "case-a",
        "relation_mode": "manual_confirmed",
        "status": "active",
        "row_ids": ["bank-1", "invoice-1"],
        "row_types": ["bank", "invoice"],
        "month_scope": "2026-01-01",
        "updated_at": "2026-06-14 09:00:00+08",
        "raw_payload": {
            "normalized_payload": {
                "case_id": "case-a",
                "relation_mode": "manual_confirmed",
                "row_ids": ["bank-1", "invoice-1"],
                "row_types": ["bank", "invoice"],
            }
        },
    }


def _generation(scope_key: str, activated_at: str) -> dict[str, object]:
    return {
        "scope_key": scope_key,
        "generation_id": f"workbench:{scope_key}:001",
        "activated_at": activated_at,
        "row_count": 2,
        "group_count": 1,
        "build_metadata": {},
    }


def _group_row(
    scope_key: str,
    row_id: str,
    *,
    group_id: str = "case:case-a",
    payload_case_id: str = "case-a",
    relation_mode: str = "manual_confirmed",
) -> dict[str, object]:
    if row_id.startswith("bank"):
        pane = "bank"
    elif row_id.startswith("oa"):
        pane = "oa"
    else:
        pane = "invoice"
    return {
        "scope_key": scope_key,
        "generation_id": f"workbench:{scope_key}:001",
        "generation_activated_at": "2026-06-14 10:00:00+08",
        "group_id": group_id,
        "zone": "open",
        "pane": pane,
        "row_id": row_id,
        "row_role": "normal",
        "source_kind": pane,
        "status": "paired",
        "payload": {
            "id": row_id,
            "case_id": payload_case_id,
            "status": "paired",
            "relation_mode": relation_mode,
        },
    }


if __name__ == "__main__":
    unittest.main()
