from __future__ import annotations

import io
import json
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories import page_business_audit
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import audit_cost_statistics_page
from fin_ops_platform.tools import audit_page_business_read_model
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


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
        check_name = _check_name(sql)
        if check_name == "oa_pending_payment_query_state" and check_name not in self.rows_by_check:
            return [_fresh_oa_pending_payment_query_state_row()]
        return [dict(row) for row in self.rows_by_check.get(check_name, [])]

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

    def test_bank_flow_rule_batch_audit_proves_page_and_active_relation_member_sets(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_flow_rule_batches",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("row.payload->'bank_transaction_ids'", consumer_sql)
        self.assertIn("row.payload->'row_ids'", consumer_sql)
        self.assertIn("relation.relation_mode = 'bank_flow_rule_batch'", consumer_sql)
        self.assertIn("submitted_batch_missing_active_relation", consumer_sql)
        self.assertIn("non_submitted_batch_has_active_relation", consumer_sql)
        self.assertIn("active_relation_member_set_mismatch", consumer_sql)
        self.assertIn("active_relation_without_canonical_batch", consumer_sql)
        self.assertEqual(params, (51,))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_submitted_bank_flow_batch_without_relation_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "batch-1",
                            "scope_key": "2026-06",
                            "row_id": "batch-1",
                            "row_type": "bank_flow_rule_batch",
                            "mismatch_kind": "submitted_batch_missing_active_relation",
                            "canonical_status": "submitted",
                            "canonical_member_ids": ["bank-1", "bank-2"],
                            "projected_member_ids": ["bank-1", "bank-2"],
                            "relation_member_ids": None,
                        }
                    ]
                }
            ),
            domain_key="bank_flow_rule_batches",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_flow_rule_batches_consumer_relation_edge_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["canonical_status"], "submitted")

    def test_bank_flow_page_member_set_mismatch_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "batch-2",
                            "scope_key": "2026-06",
                            "row_id": "batch-2",
                            "row_type": "bank_flow_rule_batch",
                            "mismatch_kind": "page_consumer_member_set_mismatch",
                            "canonical_member_ids": ["bank-1", "bank-2"],
                            "projected_member_ids": ["bank-1"],
                        }
                    ]
                }
            ),
            domain_key="bank_flow_rule_batches",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["issues"][0]["details"]["mismatch_kind"], "page_consumer_member_set_mismatch")

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
        self.assertIn("source.txn_direction in ('outflow', 'inflow')", queried_sql)
        self.assertIn("projected.transaction_id = projected.projected_row_id", queried_sql)
        self.assertNotIn("pending_invoices_relation_source_versions_mismatch", queried_sql)

    def test_bank_detail_audit_uses_uuid_identity_and_stable_source_versions(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_details",
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("row.transaction_id = source.id::text", queried_sql)
        self.assertIn("row.source_versions, '{}'::jsonb) - 'source_version'", queried_sql)
        self.assertIn("canonical_relation_summary", queried_sql)
        self.assertIn("scope_bank_identities", queried_sql)
        self.assertIn("coalesce(source.legacy_mongo_id, source.id::text)", queried_sql)
        self.assertIn("source.id::text", queried_sql)
        self.assertIn("relation.row_ids && identities.row_ids", queried_sql)

    def test_bank_detail_audit_proves_linked_relation_tag_case_and_status_contract(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_details",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("cardinality(group_row.oa_row_ids) > 0", consumer_sql)
        self.assertIn("cardinality(group_row.input_invoice_ids) > 0", consumer_sql)
        self.assertIn("shared_bank_member_multiple_cases", consumer_sql)
        self.assertIn("linked_case_mismatch", consumer_sql)
        self.assertIn("linked_oa_tag_mismatch", consumer_sql)
        self.assertIn("linked_invoice_tag_mismatch", consumer_sql)
        self.assertIn("consumer_linked_tag_not_shared", consumer_sql)
        self.assertIn("projected.relation_status = 'linked'", consumer_sql)
        self.assertNotIn("'candidate'", consumer_sql)
        self.assertEqual(params, ("default", "default", 51))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_bank_detail_missing_linked_tag_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "bank-1",
                            "scope_key": "2026-06",
                            "row_id": "bank-1",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "linked_oa_tag_mismatch",
                            "expected_case_id": "case-1",
                            "expected_has_oa": True,
                            "projected_oa_relation_tag": "无oa",
                        }
                    ]
                }
            ),
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_details_consumer_relation_edge_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["expected_case_id"], "case-1")

    def test_bank_detail_multiple_active_relation_cases_are_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "bank-overlap",
                            "scope_key": "2026-06",
                            "row_id": "bank-overlap",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "shared_bank_member_multiple_cases",
                            "linked_case_count": 2,
                        }
                    ]
                }
            ),
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["issues"][0]["details"]["linked_case_count"], 2)

    def test_batch_audits_recompute_their_domain_specific_display_contracts(self) -> None:
        batch_accounting_connection = FakeConnection()
        audit_page_business_read_model.audit_page_business_read_model(
            batch_accounting_connection,
            domain_key="batch_accounting",
        )
        batch_accounting_sql = " ".join(sql for sql, _params in batch_accounting_connection.fetch_all_calls)
        self.assertIn("group_row.payload->>'relation_mode'", batch_accounting_sql)
        self.assertNotIn("group_row.relation_kind, '') <> coalesce(relation.relation_mode", batch_accounting_sql)

        rule_batch_connection = FakeConnection()
        audit_page_business_read_model.audit_page_business_read_model(
            rule_batch_connection,
            domain_key="bank_flow_rule_batches",
        )
        rule_batch_sql = " ".join(sql for sql, _params in rule_batch_connection.fetch_all_calls)
        self.assertIn("batch.raw_payload->'normalized_payload'->>'batch_type'", rule_batch_sql)
        self.assertIn("when batch.canonical_batch_type = 'internal_transfer'", rule_batch_sql)
        self.assertIn("then coalesce(max(abs(bank.amount)), 0)", rule_batch_sql)

    def test_batch_accounting_audit_proves_direct_shared_consumer_case_set(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="batch_accounting",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("relation.special_metadata->>'source' = 'batch_accounting'", consumer_sql)
        self.assertIn("canonical.relation_mode <> 'batch_accounting'", consumer_sql)
        self.assertIn("canonical_case_missing_direct_consumer", consumer_sql)
        self.assertIn("direct_consumer_mode_or_metadata_mismatch", consumer_sql)
        self.assertIn("direct_consumer_case_not_canonical", consumer_sql)
        self.assertEqual(params, ("default", 51))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_batch_accounting_wrong_canonical_relation_mode_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "case-batch-1",
                            "scope_key": "2026-06",
                            "row_id": "case-batch-1",
                            "row_type": "batch_accounting_relation",
                            "mismatch_kind": "canonical_batch_accounting_relation_mode_mismatch",
                            "canonical_relation_mode": "manual",
                        }
                    ]
                }
            ),
            domain_key="batch_accounting",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"batch_accounting_consumer_relation_edge_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["canonical_relation_mode"], "manual")

    def test_turnover_audit_uses_effective_bank_detail_leaves_as_independent_expected_set(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="turnover_ledger",
        )

        canonical_sql = next(sql for sql, _params in connection.fetch_all_calls if "canonical_expected_set" in sql)
        self.assertIn("from read_model.bank_detail_rows detail", canonical_sql)
        self.assertIn("join app.bank_transactions source", canonical_sql)
        self.assertIn("app.app_settings", canonical_sql)
        self.assertIn("array_agg(row_id order by row_id) as bank_row_ids", canonical_sql)
        self.assertIn("projected.bank_row_ids <> canonical.bank_row_ids", canonical_sql)
        self.assertIn("canonical_missing_projection", canonical_sql)
        self.assertIn("projection_not_canonical", canonical_sql)

        business_sql = next(sql for sql, _params in connection.fetch_all_calls if "source_business_fields_mismatch" in sql)
        self.assertIn("expected_pending_repayment", business_sql)
        self.assertIn("expected_pending_collection", business_sql)
        self.assertIn("expected_balance", business_sql)
        self.assertIn("ledger.payload->>'pending_repayment_amount'", business_sql)
        self.assertIn("ledger.payload->>'collected_amount'", business_sql)

    def test_turnover_audit_proves_ledger_and_flow_relation_consumer_edges(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="turnover_ledger",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("ledger.relation_id || ':flow:'", consumer_sql)
        self.assertIn("anchor.anchor_payload->'workbench_relations'", consumer_sql)
        self.assertIn("group_row.bank_transaction_ids && anchor.anchor_bank_row_ids", consumer_sql)
        self.assertIn("shared_edge_missing_consumer", consumer_sql)
        self.assertIn("consumer_edge_not_shared", consumer_sql)
        self.assertEqual(params, ("default", 51))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_turnover_flow_missing_relation_member_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "ledger-1:flow:1",
                            "scope_key": "2026-06",
                            "row_id": "bank-2",
                            "row_type": "bank_transaction",
                            "case_id": "case-turnover-1",
                            "mismatch_kind": "shared_edge_missing_consumer",
                        }
                    ]
                }
            ),
            domain_key="turnover_ledger",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"turnover_ledger_consumer_relation_edge_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["case_id"], "case-turnover-1")

    def test_cost_statistics_expected_set_does_not_treat_ready_rows_as_missing(self) -> None:
        connection = FakeConnection()

        audit_cost_statistics_page(
            connection,
        )

        canonical_sql = next(sql for sql, _params in connection.fetch_all_calls if "canonical_expected_set" in sql)
        self.assertIn("where project_scope = 'all'", canonical_sql)
        self.assertNotIn("project_scope = 'all' and cache_status = 'fresh'", canonical_sql)

    def test_cost_statistics_expected_set_uses_builder_payload_eligibility_contract(self) -> None:
        connection = FakeConnection()

        audit_cost_statistics_page(
            connection,
        )

        canonical_sql = next(sql for sql, _params in connection.fetch_all_calls if "canonical_expected_set" in sql)
        self.assertIn("group_row.source_kinds && array['oa', 'bank']::text[]", canonical_sql)
        self.assertIn("zone = 'paired'", canonical_sql)
        self.assertNotIn("candidate", canonical_sql)
        self.assertIn("bool_or(pane = 'oa') as has_oa", canonical_sql)
        self.assertIn("bool_or(pane = 'bank') as has_bank", canonical_sql)
        self.assertIn("member.member_payload->>'project_id'", canonical_sql)
        self.assertIn("member.member_payload->>'applicant'", canonical_sql)
        self.assertIn("member.member_payload->>'debit_amount'", canonical_sql)
        self.assertIn("left join lateral", canonical_sql)
        self.assertIn("source.id = case", canonical_sql)
        self.assertIn("source.legacy_mongo_id = bank_identity.transaction_id", canonical_sql)
        self.assertNotIn("bank_source.id::text =", canonical_sql)
        self.assertIn("expected_fields", canonical_sql)
        self.assertIn("projected_fields", canonical_sql)
        expected_bank_flow_sql = canonical_sql.split("expected_bank_flow as", 1)[1].split("projected_bank_flow as", 1)[0]
        self.assertIn("from app.bank_transactions source", expected_bank_flow_sql)
        self.assertIn("coalesce(source.legacy_mongo_id, source.id::text) as transaction_id", expected_bank_flow_sql)
        self.assertNotIn("read_model.bank_detail_rows", expected_bank_flow_sql)

    def test_cost_statistics_reuses_workbench_integrity_proof_in_same_snapshot(self) -> None:
        report = audit_cost_statistics_page(
            FakeConnection(
                rows_by_check={
                    "workbench_canonical_object_set": [
                        {
                            "subject_id": "bank-missing",
                            "scope_key": "2026-06",
                            "mismatch_kind": "canonical_missing_projection",
                        }
                    ]
                }
            ),
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"cost_statistics_dependency_workbench_workbench_canonical_object_set_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["dependency"], "workbench")

    def test_cost_statistics_binds_month_upstream_versions_and_parent_shards(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "cost_source_version_proofs": [
                    {
                        "issue_code": "cost_statistics_upstream_source_versions_mismatch",
                        "subject_id": "all:2026-06",
                        "scope_key": "all:2026-06",
                        "details": {
                            "embedded_workbench_source_versions": {"generation": "old"},
                            "current_workbench_source_versions": {"generation": "new"},
                        },
                    },
                    {
                        "issue_code": "cost_statistics_parent_source_shards_mismatch",
                        "subject_id": "all:all",
                        "scope_key": "all:all",
                        "details": {
                            "expected_shard_count": 2,
                            "present_shard_count": 1,
                        },
                    },
                ]
            }
        )

        report = audit_cost_statistics_page(
            connection,
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {
                "cost_statistics_parent_source_shards_mismatch": 1,
                "cost_statistics_upstream_source_versions_mismatch": 1,
            },
        )
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("source_versions->'workbench_source_versions'", queried_sql)
        self.assertIn("source_versions->'bank_detail_source_versions'", queried_sql)
        self.assertIn("expected_source_shards", queried_sql)
        self.assertIn("expected_shard_count > 0", queried_sql)

    def test_cost_statistics_recalculates_bank_flow_and_group_summaries(self) -> None:
        connection = FakeConnection()

        audit_cost_statistics_page(
            connection,
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("cost_bank_flow_key_fields", queried_sql)
        self.assertIn("detail.transaction_id in (", queried_sql)
        self.assertIn("source.id::text", queried_sql)
        self.assertIn("coalesce(source.legacy_mongo_id, source.id::text)", queried_sql)
        self.assertIn("bank_tag_label_path", queried_sql)
        self.assertIn("bank_flow_summary", queried_sql)
        self.assertIn("select project_scope || ':all', row_key, amount", queried_sql)
        self.assertIn("read_model.cost_statistics_bank_flow_rows", queried_sql)
        self.assertNotIn("bank_flow_time_rows", queried_sql)
        self.assertIn("expected_sub_label", queried_sql)
        self.assertIn("cost_group_summaries", queried_sql)
        self.assertIn("expected_projects", queried_sql)
        self.assertIn("expected_expenses", queried_sql)
        self.assertIn("cost_bank_accounts", queried_sql)
        self.assertIn("bank_account_mappings", queried_sql)

    def test_cost_statistics_bank_account_mapping_gap_is_blocking(self) -> None:
        report = audit_cost_statistics_page(
            FakeConnection(
                rows_by_check={
                    "cost_business_value_proofs": [
                        {
                            "issue_code": "cost_statistics_bank_accounts_mismatch",
                            "subject_id": "all:2026-06:建设银行:8106",
                            "scope_key": "all:2026-06",
                            "details": {
                                "bank_name": "建设银行",
                                "account_last4": "8106",
                                "expected_source": "settings",
                                "projected_source": None,
                            },
                        }
                    ]
                }
            ),
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"cost_statistics_bank_accounts_mismatch": 1},
        )

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

    def test_oa_pending_payment_audit_proves_registered_consumer_edges(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="oa_pending_payments",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("app.oa_pending_payment_admissions", consumer_sql)
        self.assertIn("row.payload->'oa'->'summaries'", consumer_sql)
        self.assertIn("row.payload->'bankTransaction'->'summaries'", consumer_sql)
        self.assertIn("row.payload->'invoice'->'summaries'", consumer_sql)
        self.assertIn("shared_edge_missing_consumer", consumer_sql)
        self.assertIn("consumer_edge_not_shared", consumer_sql)
        self.assertEqual(params, ("default", "default", "default", 51))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])
        self.assertIn("registered page consumer summaries", report["audit_contract"]["relation_edge_equality"])

    def test_oa_pending_payment_audit_uses_the_same_dynamic_freshness_contract_as_the_page(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="oa_pending_payments",
        )

        fresh_gate_sql, _params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "oa_pending_payment_query_state" in sql
        )
        target_inventory_sql = fresh_gate_sql.split("select\n                target.scope_key", 1)[0]
        self.assertIn("source_watermark.version as source_snapshot_version", fresh_gate_sql)
        self.assertIn("pending_relation_watermark.version as pending_relation_version", fresh_gate_sql)
        self.assertIn("latest_dirty.source_version as dirty_source_version", fresh_gate_sql)
        self.assertIn("relation_scope.source_versions as relation_source_versions", fresh_gate_sql)
        self.assertIn("dead_lettered", fresh_gate_sql)
        self.assertNotIn("select relation_scope.scope_key", target_inventory_sql)
        base_versions = page_business_audit.oa_pending_payment_base_source_versions()
        self.assertIn("oa_pending_payment_postgres_projector_version", base_versions)
        self.assertEqual(report["label"], "OA 待付款核对")

    def test_oa_pending_payment_dynamic_version_gap_is_freshness_not_false_integrity(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "oa_pending_payment_query_state": [
                        {
                            "scope_key": "2026-06",
                            "actual_source_versions": {"version": 1},
                            "expected_source_versions": {"version": 2},
                        }
                    ]
                }
            ),
            domain_key="oa_pending_payments",
        )

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "drained")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"read_model_scope_not_fresh": 1},
        )

    def test_oa_pending_payment_expected_set_uses_native_ids_and_exact_month_membership(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="oa_pending_payments",
        )

        canonical_sql = next(sql for sql, _params in connection.fetch_all_calls if "canonical_expected_set" in sql)
        orphan_sql = next(sql for sql, _params in connection.fetch_all_calls if "orphan_read_model_row" in sql)
        self.assertIn("unnest(row.oa_ids)", canonical_sql)
        self.assertNotIn("jsonb_array_elements", canonical_sql)
        self.assertIn("projected.scope_key = canonical.scope_key", canonical_sql)
        self.assertIn("source.scope_key = projected.scope_key", canonical_sql)
        self.assertIn("unnest(row.oa_ids)", orphan_sql)

    def test_oa_pending_payment_shared_edge_missing_from_consumer_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "case-oa-1",
                            "scope_key": "2026-06",
                            "row_id": "bank-1",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "shared_edge_missing_consumer",
                        }
                    ]
                }
            ),
            domain_key="oa_pending_payments",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"oa_pending_payments_consumer_relation_edge_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["mismatch_kind"], "shared_edge_missing_consumer")

    def test_oa_pending_payment_audit_proves_non_outflow_edges_without_treating_them_as_payment_summaries(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="oa_pending_payments",
        )

        consumer_sql, _params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("nonOutflowRelationEdges", consumer_sql)
        self.assertIn("edge.value->>'bankTransactionId'", consumer_sql)
        self.assertIn("edge.value->>'relationCaseId'", consumer_sql)

    def test_cost_statistics_bank_flow_recalculation_uses_bank_detail_scope_owner(self) -> None:
        connection = FakeConnection()

        audit_cost_statistics_page(
            connection,
        )

        bank_flow_sql = next(
            sql
            for sql, _params in connection.fetch_all_calls
            if "cost_bank_flow_key_fields" in sql
        )
        self.assertIn("detail.scope_key as bank_detail_scope_key", bank_flow_sql)
        self.assertIn("month_key <> coalesce(bank_detail_scope_key", bank_flow_sql)
        self.assertIn("detail.payload as bank_detail_payload", bank_flow_sql)
        self.assertIn("nullif(purpose, '')", bank_flow_sql)
        self.assertIn("nullif(bank_detail_payload->>'remark', '')", bank_flow_sql)

    def test_pending_invoice_audit_proves_registered_consumer_edges(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        consumer_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "consumer_relation_edge_equality" in sql
        )
        self.assertIn("row.payload->'oa'->'summaries'", consumer_sql)
        self.assertIn("row.payload->'bank_transactions'->'summaries'", consumer_sql)
        self.assertIn("row.payload->'input_invoices'->'summaries'", consumer_sql)
        self.assertIn("when row.direction = 'income'", consumer_sql)
        self.assertEqual(params, ("default", 51))
        self.assertIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_pending_invoice_consumer_edge_not_in_shared_relation_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "case-pending-1",
                            "scope_key": "2026-06",
                            "row_id": "invoice-extra",
                            "row_type": "input_invoice",
                            "mismatch_kind": "consumer_edge_not_shared",
                        }
                    ]
                }
            ),
            domain_key="pending_invoices",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"pending_invoices_consumer_relation_edge_mismatch": 1},
        )

    def test_unregistered_consumer_contract_does_not_claim_consumer_equality(self) -> None:
        connection = FakeConnection()

        report = audit_cost_statistics_page(
            connection,
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertNotIn("consumer_relation_edge_equality", queried_sql)
        self.assertNotIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_numeric_proofs_use_typed_bank_rows_and_normalize_json_summaries(self) -> None:
        connection = FakeConnection()

        audit_cost_statistics_page(
            connection,
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertNotIn("replace(member.value->>'amount', ',', '')", queried_sql)
        self.assertIn("sum(abs(row.amount))", queried_sql)
        self.assertIn("replace(row.payload->>'amount', ',', '')", queried_sql)
        self.assertIn("model.payload->'payload'->'summary'->>'total_amount'", queried_sql)

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


class BankDetailAuditPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def test_cross_month_relation_membership_is_part_of_each_bank_scope_expected_summary(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status, raw_payload
            ) values
                ('bank-feb', '6222', 'inflow', '测试往来', 100, 100, '2026-02-01', '2026-02-01', 'active', '{}'::jsonb),
                ('bank-mar', '6222', 'outflow', '测试往来', 100, -100, '2026-03-01', '2026-03-01', 'active', '{}'::jsonb)
            """
        )
        relation = self.connection.fetch_one(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types, updated_at
            ) values (
                'turnover:test-cross-month', 'turnover_manual_closure', 'active', '2026-03-01',
                array['bank-feb', 'bank-mar'], array['bank', 'bank'],
                '2026-07-13 08:00:00+00'::timestamptz
            )
            returning updated_at::text as relation_updated_at
            """
        )
        relation_updated_at = str((relation or {})["relation_updated_at"])
        for scope_key in ("2026-02", "2026-03"):
            source_versions = {
                "workbench_relation_source_versions": {
                    "source": "workbench_pair_relations",
                    "scope_key": scope_key,
                    "relation_count": 1,
                    "relation_updated_at": relation_updated_at,
                }
            }
            self.connection.execute(
                """
                insert into read_model.bank_detail_scopes(
                    scope_key, scope_month, schema_version, status, row_count, source_versions
                ) values (%s, (%s || '-01')::date, 10, 'fresh', 0, %s::jsonb)
                """,
                (scope_key, scope_key, json.dumps(source_versions)),
            )

        sql, params, _issue_code = page_business_audit._embedded_relation_source_summary_query(  # noqa: SLF001
            "bank_details",
            "read_model.bank_detail_scopes",
            "scope",
            "default",
            50,
        )

        self.assertEqual(self.connection.fetch_all(sql, params), [])

        self.connection.execute(
            """
            update read_model.bank_detail_scopes
            set source_versions = jsonb_set(
                source_versions,
                '{workbench_relation_source_versions,relation_count}',
                '0'::jsonb
            )
            where scope_key = '2026-02'
            """
        )
        mismatches = self.connection.fetch_all(sql, params)

        self.assertEqual([row["scope_key"] for row in mismatches], ["2026-02"])
        self.assertEqual(mismatches[0]["current_relation_versions"]["relation_count"], 1)


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


def _fresh_oa_pending_payment_query_state_row() -> dict[str, object]:
    base_versions = page_business_audit.oa_pending_payment_base_source_versions()
    expected_versions = {
        **base_versions,
        "oa_pending_payment_source_snapshot_version": 1,
        "completed_oa_signature": "completed",
        "in_progress_admission_signature": "admission",
        "payment_status_signature": "payment",
        "oa_pending_payment_source_signature": "source",
        "oa_pending_payment_relation_version": 1,
        "oa_pending_payment_event_source_version": 1,
        "workbench_relation_source_versions": {"relation": 1},
    }
    return {
        "scope_key": "2026-06",
        "row_count": 1,
        "generated_at": "2026-07-16T00:00:00Z",
        "cache_status": "fresh",
        "actual_source_versions": expected_versions,
        "source_status": "success",
        "source_snapshot_version": 1,
        "source_payload": {
            "completed_oa_signature": "completed",
            "admission_signature": "admission",
            "payment_status_signature": "payment",
            "source_signature": "source",
        },
        "pending_relation_version": 1,
        "relation_scope_exists": True,
        "relation_cache_status": "fresh",
        "relation_source_versions": {"relation": 1},
        "dirty_status": "done",
        "dirty_source_version": 1,
        "outbox_blocking": False,
    }


if __name__ == "__main__":
    unittest.main()
