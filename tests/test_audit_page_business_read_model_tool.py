from __future__ import annotations

import io
import json
import unittest

from fin_ops_platform.tools import audit_page_business_read_model


class FakeConnection:
    def __init__(
        self,
        *,
        summary: dict[str, object] | None = None,
        rows_by_check: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.summary = summary or {
            "source_fact_count": 2,
            "read_model_row_count": 2,
            "read_model_scope_count": 1,
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
            "dirty_scope_count": 0,
            "outbox_backlog_count": 0,
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
        raise AssertionError("page business audit must be read-only")


class AuditPageBusinessReadModelToolTests(unittest.TestCase):
    def test_clean_audit_passes_for_every_registered_page_without_writes(self) -> None:
        for domain_key, contract in audit_page_business_read_model.PAGE_AUDIT_CONTRACTS.items():
            with self.subTest(domain_key=domain_key):
                connection = FakeConnection()

                report = audit_page_business_read_model.audit_page_business_read_model(
                    connection,
                    domain_key=domain_key,
                )

                self.assertEqual(report["overall_status"], "pass")
                self.assertEqual(report["summary"]["blocking_issue_count"], 0)
                self.assertEqual(report["issues"], [])
                self.assertEqual(report["audit_contract"]["write_policy"], "read_only")
                self.assertEqual(connection.executed, [])
                queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
                self.assertIn(contract.source_tables[0], queried_sql)
                self.assertIn(contract.read_model_tables[0], queried_sql)

    def test_reports_page_data_relation_and_freshness_failures(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "dirty_scope": [
                    {
                        "scope_type": "bank_detail",
                        "scope_key": "2026-05",
                        "status": "failed",
                        "last_error": "refresh failed",
                    }
                ],
                "outbox_backlog": [
                    {
                        "event_type": "bank_detail.read_model.refresh",
                        "scope_key": "2026-05",
                        "status": "pending",
                    }
                ],
                "scope_row_count_mismatch": [
                    {
                        "scope_type": "bank_detail",
                        "scope_key": "2026-05",
                        "scope_row_count": 1,
                        "actual_row_count": 2,
                    }
                ],
                "source_versions_mismatch": [
                    {
                        "subject_id": "bank-1",
                        "scope_key": "2026-05",
                        "row_source_versions": {"a": 1},
                        "scope_source_versions": {"a": 2},
                    }
                ],
                "missing_read_model_scope": [
                    {
                        "scope_key": "2026-06",
                        "source_count": 3,
                    }
                ],
                "missing_read_model_row": [
                    {
                        "subject_id": "bank-missing",
                        "scope_key": "2026-05",
                        "amount": "100.00",
                    }
                ],
                "orphan_read_model_row": [
                    {
                        "subject_id": "bank-orphan",
                        "scope_key": "2026-05",
                    }
                ],
                "duplicate_read_model_identity": [
                    {
                        "subject_id": "bank-dup",
                        "row_count": 2,
                    }
                ],
                "relation_distribution": [
                    {
                        "subject_id": "case-1",
                        "scope_key": "2026-05",
                        "row_id": "bank-1",
                        "row_type": "bank_transaction",
                    }
                ],
                "candidate_relation_projection": [
                    {
                        "subject_id": "case-candidate",
                        "scope_key": "2026-05",
                        "relation_status": "linked",
                        "canonical_status": "candidate",
                    }
                ],
            }
        )

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_details",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        issue_codes = set(report["summary"]["issue_counts_by_code"])
        self.assertIn("read_model_scope_not_fresh", issue_codes)
        self.assertIn("read_model_outbox_not_drained", issue_codes)
        self.assertIn("bank_details_scope_row_count_mismatch", issue_codes)
        self.assertIn("bank_details_row_source_versions_mismatch", issue_codes)
        self.assertIn("bank_details_relation_source_versions_mismatch", issue_codes)
        self.assertIn("bank_details_missing_read_model_scope", issue_codes)
        self.assertIn("bank_details_missing_read_model_row", issue_codes)
        self.assertIn("bank_details_orphan_read_model_row", issue_codes)
        self.assertIn("bank_details_duplicate_read_model_identity", issue_codes)
        self.assertIn("bank_details_active_relation_missing_distribution", issue_codes)
        self.assertIn("bank_details_candidate_relation_projected_as_linked", issue_codes)
        self.assertEqual(report["summary"]["blocking_issue_count"], 11)
        self.assertEqual(connection.executed, [])

    def test_bank_flow_rule_batch_audit_compares_business_fields_not_raw_version_shape(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "source_business_fields_mismatch": [
                    {
                        "subject_id": "batch-1",
                        "scope_key": "2026-05",
                        "source_status": "submitted",
                        "read_model_status": "draft",
                        "source_total_amount": "100.00",
                        "read_model_total_amount": "90.00",
                    }
                ]
            }
        )

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_flow_rule_batches",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_counts_by_code"],
            {"bank_flow_rule_batches_business_fields_mismatch": 1},
        )
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("source_business_fields_mismatch", queried_sql)
        self.assertNotIn("read_model.source_versions as row_source_versions", queried_sql)

    def test_pending_invoice_audit_uses_page_read_model_scope_contract(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        queried_summary_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertIn("from read_model.pending_invoice_rows row", queried_summary_sql)
        self.assertIn("join app.bank_transactions source", queried_summary_sql)
        self.assertIn("count(distinct relation.case_id)", queried_summary_sql)
        self.assertIn("join read_model.pending_invoice_rows pending_row", queried_summary_sql)

        scope_sql = next(sql for sql, _params in connection.fetch_all_calls if "scope_row_count_mismatch" in sql)
        self.assertIn("row.direction = scope.direction", scope_sql)
        self.assertIn("row.status_code in", scope_sql)
        self.assertNotIn("row.scope_key like scope.scope_key", scope_sql)

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertNotIn("source.txn_direction in ('outflow', 'inflow')", queried_sql)
        self.assertNotIn("pending_invoices_relation_source_versions_mismatch", queried_sql)

    def test_pending_invoice_relation_audit_uses_active_exists_and_any_distribution_scope(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        relation_sql = next(sql for sql, _params in connection.fetch_all_calls if "relation_distribution" in sql)
        self.assertIn("where not exists", relation_sql.lower())
        self.assertIn("join read_model.pending_invoice_rows pending_row", relation_sql)
        self.assertIn("relation.row_types[member.ordinality] in ('bank', 'bank_transaction')", relation_sql)
        self.assertIn("from read_model.workbench_relation_rows relation_row", relation_sql)
        self.assertIn("join read_model.workbench_relation_groups relation_group", relation_sql)

        candidate_sql = next(sql for sql, _params in connection.fetch_all_calls if "candidate_relation_projection" in sql)
        self.assertIn("not exists", candidate_sql.lower())
        self.assertIn("active_relation.status = 'active'", candidate_sql)
        self.assertIn("from unnest(group_row.bank_transaction_ids)", " ".join(candidate_sql.split()))
        self.assertIn("join read_model.pending_invoice_rows pending_row", " ".join(candidate_sql.split()))

    def test_cli_fail_on_issues_returns_nonzero(self) -> None:
        stdout = io.StringIO()

        exit_code = audit_page_business_read_model.main(
            ["bank_details", "--json", "--fail-on-issues"],
            connection=FakeConnection(
                rows_by_check={
                    "dirty_scope": [
                        {
                            "scope_type": "bank_detail",
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


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
