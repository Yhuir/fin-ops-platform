from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.output_invoice_collection_audit import (
    OUTPUT_INVOICE_PREDICATE,
    audit_output_invoice_collection_read_model as run_output_invoice_collection_audit,
)


class FakeConnection:
    def __init__(
        self,
        *,
        summary: dict[str, object] | None = None,
        rows_by_check: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.summary = summary or {
            "active_output_invoice_count": 2,
            "active_output_invoice_total_with_tax": "300.00",
            "read_model_invoice_member_count": 2,
            "read_model_row_count": 1,
            "output_invoice_collection_scope_count": 1,
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


class AuditOutputInvoiceCollectionReadModelToolTests(unittest.TestCase):
    def test_clean_audit_passes_without_writes(self) -> None:
        connection = FakeConnection()

        report = run_output_invoice_collection_audit(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(report["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["audit_contract"]["snapshot_consistency"], "caller_managed")
        self.assertFalse(report["audit_contract"]["database_snapshot"])
        self.assertIn("invoice page consumer summaries", report["audit_contract"]["relation_edge_equality"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.invoices", queried_sql)
        self.assertIn("read_model.output_invoice_collection_rows", queried_sql)
        self.assertIn("read_model.workbench_relation_rows", queried_sql)
        self.assertIn("read_model.workbench_relation_groups", queried_sql)
        self.assertIn("output_invoice_ids", queried_sql)
        self.assertIn("/* check: relation_edge_equality */", queried_sql)
        self.assertIn("job.outbox_events", queried_sql)
        self.assertIn("/* check: consumer_relation_edge_equality */", queried_sql)
        source_version_sql = next(
            sql for sql, _params in connection.fetch_all_calls if _check_name(sql) == "source_version_mismatch"
        )
        self.assertIn("embedded_relation_versions - 'workbench_pair_relations_updated_at'", source_version_sql)
        self.assertIn("current_relation_versions - 'workbench_pair_relations_updated_at'", source_version_sql)
        self.assertIn("app.workbench_pair_relations changed_relation", source_version_sql)
        self.assertIn("active_invoice.invoice_id = any(changed_relation.row_ids)", source_version_sql)
        self.assertIn("active_invoice.postgres_invoice_id = any(changed_relation.row_ids)", source_version_sql)
        self.assertIn("changed_relation.row_ids && active_invoice.source_workbench_row_ids", source_version_sql)
        self.assertIn("active_invoice.scope_key = invoice_versions.scope_key", source_version_sql)
        self.assertIn("changed_relation.updated_at >", source_version_sql)

    def test_workbench_relation_outbox_backlog_blocks_queue_proof(self) -> None:
        report = run_output_invoice_collection_audit(
            FakeConnection(
                rows_by_check={
                    "outbox_backlog": [
                        {
                            "event_type": "workbench_relation.read_model.refresh",
                            "scope_key": "2026-05",
                            "status": "pending",
                        }
                    ]
                }
            )
        )

        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"read_model_outbox_not_drained": 1},
        )

    def test_output_consumer_extra_relation_member_is_blocking(self) -> None:
        report = run_output_invoice_collection_audit(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "case-extra",
                            "scope_key": "2026-05",
                            "row_id": "bank-extra",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "consumer_edge_not_shared",
                        }
                    ]
                }
            )
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"output_invoice_collection_consumer_relation_edge_mismatch": 1},
        )

    def test_sql_literal_percent_is_escaped_for_psycopg_placeholders(self) -> None:
        self.assertIn("销项%%", OUTPUT_INVOICE_PREDICATE)
        self.assertNotIn("销项%'", OUTPUT_INVOICE_PREDICATE)

    def test_reports_full_data_and_relation_invariant_failures(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "missing_read_model_member": [
                    {"invoice_id": "out-missing", "scope_key": "2026-05", "invoice_no": "9001"}
                ],
                "source_version_mismatch": [
                    {
                        "scope_key": "2026-05",
                        "embedded_relation_versions": {"source_version": "old"},
                        "current_relation_versions": {"source_version": "new"},
                    }
                ],
            }
        )

        report = run_output_invoice_collection_audit(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        issue_codes = set(report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("missing_output_invoice_collection_member", issue_codes)
        self.assertIn("output_collection_relation_source_versions_mismatch", issue_codes)
        self.assertEqual(report["summary"]["blocking_issue_sample_count"], 2)
        self.assertEqual(connection.executed, [])


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
