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
                self.assertEqual(report["audit_status"]["integrity"], "pass")
                self.assertEqual(report["audit_status"]["freshness"], "fresh")
                self.assertEqual(report["summary"]["blocking_issue_sample_count"], 0)
                self.assertEqual(report["issues"], [])
                self.assertEqual(report["audit_contract"]["write_policy"], "read_only")
                self.assertTrue(report["audit_contract"]["canonical_expected_set"])
                self.assertTrue(report["audit_contract"]["key_display_fields"])
                self.assertEqual(report["audit_contract"]["snapshot_consistency"], "caller_managed")
                self.assertFalse(report["audit_contract"]["database_snapshot"])
                self.assertEqual(connection.executed, [])
                queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
                self.assertIn(contract.source_tables[0], queried_sql)
                self.assertIn(contract.read_model_tables[0], queried_sql)
                self.assertIn("/* check: relation_edge_equality */", queried_sql)

    def test_proof_checks_are_blocking_integrity_gates(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "key_display_fields": [
                        {"subject_id": "bank-1", "scope_key": "2026-05", "source_amount": "10", "projected_amount": "9"}
                    ],
                    "bank_account_balance_equality": [
                        {"subject_id": "acct:1", "scope_key": "all", "expected_count": 2, "projected_count": 1}
                    ],
                    "relation_edge_equality": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-05",
                            "row_id": "bank-1",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "canonical_missing_group_edge",
                        }
                    ],
                }
            ),
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {
                "bank_details_account_balance_mismatch": 1,
                "bank_details_key_display_fields_mismatch": 1,
                "bank_details_relation_edge_mismatch": 1,
            },
        )

    def test_pending_invoice_canonical_member_gap_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_expected_set": [
                        {
                            "subject_id": "bank-missing",
                            "scope_key": "2026-05",
                            "direction": "expense",
                            "mismatch_kind": "canonical_missing_projection",
                        }
                    ]
                }
            ),
            domain_key="pending_invoices",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"pending_invoices_canonical_expected_set_mismatch": 1},
        )

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
                "relation_edge_equality": [
                    {
                        "subject_id": "case-1",
                        "scope_key": "2026-05",
                        "row_id": "bank-1",
                        "row_type": "bank_transaction",
                        "mismatch_kind": "canonical_missing_group_edge",
                    }
                ],
            }
        )

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_details",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")
        issue_codes = set(report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("read_model_scope_not_fresh", issue_codes)
        self.assertIn("read_model_outbox_not_drained", issue_codes)
        self.assertIn("bank_details_scope_row_count_mismatch", issue_codes)
        self.assertIn("bank_details_row_source_versions_mismatch", issue_codes)
        self.assertIn("bank_details_relation_source_versions_mismatch", issue_codes)
        self.assertIn("bank_details_missing_read_model_scope", issue_codes)
        self.assertIn("bank_details_missing_read_model_row", issue_codes)
        self.assertIn("bank_details_orphan_read_model_row", issue_codes)
        self.assertIn("bank_details_duplicate_read_model_identity", issue_codes)
        self.assertIn("bank_details_relation_edge_mismatch", issue_codes)
        self.assertEqual(report["summary"]["blocking_issue_sample_count"], 10)
        self.assertEqual(connection.executed, [])

        summary_params = connection.fetch_one_calls[0][1]
        self.assertEqual(summary_params[-2:], ("default", "default"))
        outbox_params = next(params for sql, params in connection.fetch_all_calls if "outbox_backlog" in sql)
        self.assertEqual(outbox_params, ("default", 51))

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
            report["summary"]["issue_sample_counts_by_code"],
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

    def test_pending_invoice_relation_audit_uses_scope_aware_bidirectional_edge_equality(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        relation_sql = next(sql for sql, _params in connection.fetch_all_calls if "relation_edge_equality" in sql)
        self.assertIn("relation_scope_candidates", relation_sql)
        self.assertIn("expected_edges", relation_sql)
        self.assertIn("projected_group_edges", relation_sql)
        self.assertIn("projected_index_edges", relation_sql)
        self.assertIn("canonical_missing_group_edge", relation_sql)
        self.assertIn("projected_group_edge_not_canonical", relation_sql)
        self.assertIn("group_edge_missing_row_index", relation_sql)
        self.assertIn("row_index_edge_missing_group", relation_sql)

    def test_formatted_display_amounts_are_normalized_before_numeric_proof(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="cost_statistics",
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("replace(member.value->>'amount', ',', '')", queried_sql)
        self.assertIn("replace(row.payload->>'amount', ',', '')", queried_sql)
        self.assertIn("replace(model.payload->'payload'->'summary'->>'total_amount', ',', '')", queried_sql)

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
        self.assertEqual(payload["summary"]["issue_sample_counts_by_code"], {"read_model_scope_not_fresh": 1})


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
