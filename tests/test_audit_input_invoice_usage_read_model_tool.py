from __future__ import annotations

import io
import json
import unittest

from fin_ops_platform.tools import audit_input_invoice_usage_read_model


class FakeConnection:
    def __init__(
        self,
        *,
        summary: dict[str, object] | None = None,
        rows_by_check: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.summary = summary or {
            "active_input_invoice_count": 2,
            "active_input_invoice_total_with_tax": "300.00",
            "read_model_invoice_member_count": 2,
            "read_model_row_count": 1,
            "input_invoice_usage_scope_count": 1,
            "workbench_relation_scope_count": 1,
            "active_workbench_pair_relation_count": 1,
            "linked_workbench_relation_group_count": 1,
        }
        self.rows_by_check = rows_by_check or {}
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        self.fetch_one_calls.append((sql, params))
        return dict(self.summary)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return [dict(row) for row in self.rows_by_check.get(_check_name(sql), [])]

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        raise AssertionError("audit must be read-only")


class AuditInputInvoiceUsageReadModelToolTests(unittest.TestCase):
    def test_clean_audit_passes_without_writes(self) -> None:
        connection = FakeConnection()

        report = audit_input_invoice_usage_read_model.audit_input_invoice_usage_read_model(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(report["issues"], [])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.invoices", queried_sql)
        self.assertIn("read_model.input_invoice_usage_rows", queried_sql)
        self.assertIn("read_model.workbench_relation_rows", queried_sql)
        self.assertIn("read_model.workbench_relation_groups", queried_sql)

    def test_reports_full_data_and_relation_invariant_failures(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "missing_read_model_member": [
                    {"invoice_id": "inv-missing", "scope_key": "2026-05", "invoice_no": "1001"}
                ],
                "duplicate_invoice_member": [
                    {
                        "invoice_id": "inv-dup",
                        "scope_key": "2026-05",
                        "row_count": 2,
                        "row_ids": ["row-a", "row-b"],
                    }
                ],
                "amount_mismatch": [
                    {
                        "row_id": "row-amount",
                        "scope_key": "2026-05",
                        "app_total_with_tax": "300.00",
                        "payload_total_with_tax": "200.00",
                    }
                ],
                "active_relation_missing_workbench_row": [
                    {
                        "case_id": "case-1",
                        "scope_key": "2026-05",
                        "invoice_id": "inv-1",
                        "relation_row_id": "inv-1",
                    }
                ],
                "active_relation_missing_workbench_group": [
                    {
                        "case_id": "case-2",
                        "scope_key": "2026-06",
                        "invoice_id": "inv-2",
                        "relation_row_id": "inv-2",
                    }
                ],
                "cross_scope_relation_distribution": [
                    {
                        "case_id": "case-cross",
                        "scope_key": "2026-04",
                        "invoice_id": "inv-cross",
                        "relation_row_id": "inv-cross",
                    }
                ],
                "candidate_relation_in_input_usage": [
                    {
                        "row_id": "row-candidate",
                        "scope_key": "2026-05",
                        "invoice_id": "inv-candidate",
                    }
                ],
                "candidate_workbench_relation": [
                    {
                        "row_id": "inv-candidate",
                        "scope_key": "2026-05",
                        "invoice_id": "inv-candidate",
                    }
                ],
            }
        )

        report = audit_input_invoice_usage_read_model.audit_input_invoice_usage_read_model(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        issue_codes = set(report["summary"]["issue_counts_by_code"])
        self.assertIn("missing_input_invoice_usage_member", issue_codes)
        self.assertIn("duplicate_input_invoice_usage_member", issue_codes)
        self.assertIn("input_invoice_usage_amount_mismatch", issue_codes)
        self.assertIn("active_relation_missing_workbench_relation_row", issue_codes)
        self.assertIn("active_relation_missing_workbench_relation_group", issue_codes)
        self.assertIn("cross_scope_relation_member_not_distributed", issue_codes)
        self.assertIn("candidate_relation_projected_into_input_usage", issue_codes)
        self.assertIn("candidate_workbench_relation_for_input_invoice", issue_codes)
        self.assertEqual(report["summary"]["blocking_issue_count"], 8)
        self.assertEqual(connection.executed, [])

    def test_cli_fail_on_issues_returns_nonzero(self) -> None:
        stdout = io.StringIO()

        exit_code = audit_input_invoice_usage_read_model.main(
            ["--json", "--fail-on-issues"],
            connection=FakeConnection(
                rows_by_check={
                    "dirty_scope": [
                        {
                            "scope_type": "input_invoice_usage",
                            "scope_key": "2026-05",
                            "status": "failed",
                        }
                    ]
                }
            ),
            stdout=stdout,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["overall_status"], "issues_found")
        self.assertEqual(payload["summary"]["issue_counts_by_code"], {"read_model_scope_not_fresh": 1})

    def test_example_limit_is_applied_per_issue_code(self) -> None:
        rows = [
            {"invoice_id": f"inv-{index}", "scope_key": "2026-05"}
            for index in range(3)
        ]

        report = audit_input_invoice_usage_read_model.audit_input_invoice_usage_read_model(
            FakeConnection(rows_by_check={"missing_read_model_member": rows}),
            example_limit=2,
        )

        self.assertEqual(report["summary"]["issue_counts_by_code"], {"missing_input_invoice_usage_member": 3})
        self.assertEqual(len(report["issues"]), 2)


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
