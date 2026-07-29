from __future__ import annotations

import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
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
                self.assertEqual(report["audit_contract"]["read_model_tables"], [])
                self.assertEqual(report["mode"], "page-business-canonical-read-audit")
                if domain_key in {
                    "turnover_ledger",
                    "bank_details",
                    "pending_invoices",
                    "oa_pending_payments",
                    "input_invoice_usage",
                    "output_invoice_collection",
                }:
                    self.assertIn("/* check: direct_canonical_summary */", queried_sql)
                else:
                    self.assertIn("/* check: key_display_fields */", queried_sql)
                self.assertNotIn("read_model.", queried_sql)

    def test_proof_checks_are_blocking_integrity_gates(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_member_shape": [
                        {
                            "subject_id": "case-shape",
                            "scope_key": "2026-05",
                            "row_id_count": 2,
                            "row_type_count": 1,
                        }
                    ],
                    "canonical_relation_bank_member_exists": [
                        {
                            "subject_id": "case-missing",
                            "scope_key": "2026-05",
                            "row_id": "bank-missing",
                            "row_type": "bank_transaction",
                        }
                    ],
                    "canonical_relation_bank_member_unique": [
                        {
                            "subject_id": "bank-overlap",
                            "scope_key": "2026-05",
                            "active_case_ids": ["case-1", "case-2"],
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
                "bank_details_canonical_relation_bank_member_duplicated": 1,
                "bank_details_canonical_relation_bank_member_missing": 1,
                "bank_details_canonical_relation_member_shape_invalid": 1,
            },
        )

    def test_pending_invoice_canonical_member_gap_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_exists": [
                        {
                            "subject_id": "bank-missing",
                            "scope_key": "2026-05",
                            "row_type": "bank_transaction",
                        }
                    ]
                }
            ),
            domain_key="pending_invoices",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"pending_invoices_canonical_relation_bank_member_missing": 1},
        )

    def test_bank_flow_rule_batch_audit_compares_business_fields_not_raw_version_shape(self) -> None:
        connection = FakeConnection(
            rows_by_check={
                "key_display_fields": [
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
            {"bank_flow_rule_batches_key_display_fields_mismatch": 1},
        )
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("key_display_fields", queried_sql)
        self.assertNotIn("read_model.source_versions as row_source_versions", queried_sql)

    def test_missing_live_bank_flow_candidate_is_a_blocking_expected_set_gap(self) -> None:
        connection = FakeConnection()
        source = _bank_flow_188500_candidate_source()
        empty_service = SimpleNamespace(snapshot=lambda: {"batches": {}})
        with (
            patch.object(
                page_business_audit.BankFlowRuleBatchCanonicalQueryRepository,
                "candidate_scope_months",
                return_value=["2026-05"],
            ),
            patch.object(
                page_business_audit.BankFlowRuleBatchCanonicalQueryRepository,
                "read_candidate_guard_source",
                return_value=source,
            ),
            patch.object(
                page_business_audit,
                "build_live_bank_flow_rule_batch_service",
                return_value=empty_service,
            ),
        ):
            report = audit_page_business_read_model.audit_page_business_read_model(
                connection,
                domain_key="bank_flow_rule_batches",
            )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_flow_rule_batches_canonical_expected_set_mismatch": 1},
        )
        self.assertEqual(
            {
                issue["details"]["mismatch_kind"]
                for issue in report["issues"]
                if issue["code"] == "bank_flow_rule_batches_canonical_expected_set_mismatch"
            },
            {"live_candidate_source_row_uncovered"},
        )

    def test_188500_live_bank_flow_candidate_passes_shared_builder_audit(self) -> None:
        connection = FakeConnection()
        with (
            patch.object(
                page_business_audit.BankFlowRuleBatchCanonicalQueryRepository,
                "candidate_scope_months",
                return_value=["2026-05"],
            ),
            patch.object(
                page_business_audit.BankFlowRuleBatchCanonicalQueryRepository,
                "read_candidate_guard_source",
                return_value=_bank_flow_188500_candidate_source(),
            ),
        ):
            report = audit_page_business_read_model.audit_page_business_read_model(
                connection,
                domain_key="bank_flow_rule_batches",
            )

        self.assertEqual(report["overall_status"], "pass")

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
        self.assertIn("unnest(batch.bank_transaction_ids)", consumer_sql)
        self.assertNotIn("read_model.bank_flow_rule_batch_rows", consumer_sql)
        self.assertIn("where relation_mode = 'bank_flow_rule_batch'", consumer_sql)
        self.assertIn("from active_bank_relations", consumer_sql)
        self.assertIn("left join active_batch_relations relation", consumer_sql)
        self.assertIn("where batch.status in ('submitted', 'withdrawn', 'stale')", consumer_sql)
        self.assertIn("submitted_batch_missing_active_relation", consumer_sql)
        self.assertIn("non_submitted_batch_has_active_relation", consumer_sql)
        self.assertIn("active_relation_member_set_mismatch", consumer_sql)
        self.assertNotIn("batch_members_occupied_by_other_active_relation", consumer_sql)
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

    def test_unsubmitted_bank_flow_batch_occupied_by_other_relation_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "consumer_relation_edge_equality": [
                        {
                            "subject_id": "draft-batch",
                            "scope_key": "2026-07",
                            "row_id": "draft-batch",
                            "row_type": "bank_flow_rule_batch",
                            "mismatch_kind": "batch_members_occupied_by_other_active_relation",
                            "canonical_status": "draft",
                            "canonical_member_ids": ["bank-1", "bank-2"],
                            "projected_member_ids": ["bank-1", "bank-2"],
                            "relation_member_ids": None,
                            "conflicting_case_ids": ["submitted-batch"],
                        }
                    ]
                }
            ),
            domain_key="bank_flow_rule_batches",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["issues"][0]["details"]["mismatch_kind"],
            "batch_members_occupied_by_other_active_relation",
        )
        self.assertEqual(report["issues"][0]["details"]["conflicting_case_ids"], ["submitted-batch"])

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

    def test_pending_invoice_audit_uses_direct_canonical_contract(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        queried_sql = " ".join(
            sql
            for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls
        )
        self.assertIn("/* check: direct_canonical_summary */", queried_sql)
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertIn("/* check: canonical_relation_member_shape */", queried_sql)
        self.assertIn("/* check: canonical_relation_bank_member_exists */", queried_sql)
        self.assertNotIn("read_model.pending_invoice", queried_sql)
        self.assertNotIn("pending_invoice.read_model.refresh", queried_sql)

    def test_bank_detail_audit_reads_direct_canonical_facts_only(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="bank_details",
        )

        queried_sql = " ".join(
            sql
            for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls
        )
        self.assertEqual(report["mode"], "page-business-canonical-read-audit")
        self.assertIn("/* check: direct_canonical_summary */", queried_sql)
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertIn("/* check: canonical_relation_member_shape */", queried_sql)
        self.assertIn("/* check: canonical_relation_bank_member_exists */", queried_sql)
        self.assertIn("/* check: canonical_relation_bank_member_unique */", queried_sql)
        self.assertIn("source.id::text", queried_sql)
        self.assertIn("source.legacy_mongo_id = member.row_id", queried_sql)
        self.assertNotIn("read_model.bank_detail", queried_sql)
        self.assertNotIn("job.read_model_dirty_scopes", queried_sql)
        self.assertNotIn("consumer_relation_edge_equality", queried_sql)
        self.assertEqual(
            report["audit_contract"]["proof_checks"],
            [
                "single_repeatable_read_snapshot",
                "canonical_relation_member_existence",
                "canonical_relation_identity_uniqueness",
            ],
        )

    def test_bank_detail_missing_canonical_member_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_exists": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-06",
                            "row_id": "bank-missing",
                            "row_type": "bank_transaction",
                        }
                    ]
                }
            ),
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_details_canonical_relation_bank_member_missing": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["row_id"], "bank-missing")

    def test_bank_detail_multiple_active_relation_cases_are_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_unique": [
                        {
                            "subject_id": "bank-overlap",
                            "scope_key": "2026-06",
                            "active_case_ids": ["case-1", "case-2"],
                        }
                    ]
                }
            ),
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_details_canonical_relation_bank_member_duplicated": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["active_case_ids"], ["case-1", "case-2"])

    def test_batch_audits_recompute_their_domain_specific_display_contracts(self) -> None:
        batch_accounting_connection = FakeConnection()
        audit_page_business_read_model.audit_page_business_read_model(
            batch_accounting_connection,
            domain_key="batch_accounting",
        )
        batch_accounting_sql = " ".join(sql for sql, _params in batch_accounting_connection.fetch_all_calls)
        self.assertIn("relation.relation_mode = 'batch_accounting'", batch_accounting_sql)
        self.assertIn("cardinality(relation.row_ids) <> cardinality(relation.row_types)", batch_accounting_sql)
        self.assertIn("count(distinct member.row_id)", batch_accounting_sql)
        self.assertIn("app.bank_transactions", batch_accounting_sql)
        self.assertNotIn("read_model.", batch_accounting_sql)

        rule_batch_connection = FakeConnection()
        audit_page_business_read_model.audit_page_business_read_model(
            rule_batch_connection,
            domain_key="bank_flow_rule_batches",
        )
        rule_batch_sql = " ".join(sql for sql, _params in rule_batch_connection.fetch_all_calls)
        self.assertIn("batch.raw_payload->'normalized_payload'->>'batch_type'", rule_batch_sql)
        self.assertIn("when batch.canonical_batch_type = 'internal_transfer'", rule_batch_sql)
        self.assertIn("then coalesce(max(abs(bank.amount)), 0)", rule_batch_sql)

    def test_batch_accounting_audit_reads_only_canonical_relations_and_members(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="batch_accounting",
        )

        audit_sql, params = next(
            (sql, params)
            for sql, params in connection.fetch_all_calls
            if "/* check: key_display_fields */" in sql
        )
        self.assertIn("relation.relation_mode = 'batch_accounting'", audit_sql)
        self.assertIn("app.bank_transactions", audit_sql)
        self.assertIn("app.oa_applications", audit_sql)
        self.assertIn("app.invoices", audit_sql)
        self.assertNotIn("special_metadata->'oa_row_ids'", audit_sql)
        self.assertNotIn("special_metadata->'invoice_row_ids'", audit_sql)
        self.assertNotIn("special_metadata->>'bank_row_id'", audit_sql)
        self.assertNotIn("read_model.", audit_sql)
        self.assertEqual(params, (51,))
        self.assertNotIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_batch_accounting_relation_owner_mismatch_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_expected_set": [
                        {
                            "subject_id": "case-batch-1",
                            "scope_key": "2026-06",
                            "relation_mode": "manual",
                            "metadata_source": "batch_accounting",
                        }
                    ]
                }
            ),
            domain_key="batch_accounting",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"batch_accounting_relation_owner_mismatch": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["relation_mode"], "manual")

    def test_turnover_audit_reads_only_canonical_facts(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="turnover_ledger",
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertEqual(report["mode"], "page-business-canonical-read-audit")
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertIn("app.turnover_relations", queried_sql)
        self.assertNotIn("read_model.turnover_ledger", queried_sql)
        self.assertNotIn("job.read_model_dirty_scopes", queried_sql)
        self.assertNotIn("job.outbox_events", queried_sql)
        self.assertEqual(
            report["audit_contract"]["proof_checks"],
            [
                "single_repeatable_read_snapshot",
                "canonical_relation_member_existence",
                "canonical_relation_identity_uniqueness",
                "manual_turnover_relation_member_existence",
            ],
        )

    def test_turnover_flow_missing_relation_member_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_exists": [
                        {
                            "subject_id": "bank-2",
                            "scope_key": "2026-06",
                            "row_id": "bank-2",
                        }
                    ]
                }
            ),
            domain_key="turnover_ledger",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"turnover_ledger_canonical_relation_bank_member_missing": 1},
        )
        self.assertEqual(report["issues"][0]["subject_id"], "bank-2")

    def test_cost_statistics_audit_reads_direct_canonical_facts_only(self) -> None:
        connection = FakeConnection()

        report = audit_cost_statistics_page(
            connection,
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("app.oa_applications", queried_sql)
        self.assertNotIn("read_model.", queried_sql)
        self.assertEqual(
            report["audit_contract"]["proof_checks"],
            [
                "single_repeatable_read_snapshot",
                "canonical_relation_shape",
                "canonical_relation_member_existence",
            ],
        )

    def test_pending_invoice_relation_audit_checks_canonical_member_integrity(self) -> None:
        connection = FakeConnection()

        audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("canonical_relation_member_shape", queried_sql)
        self.assertIn("canonical_relation_bank_member_exists", queried_sql)
        self.assertIn("canonical_relation_bank_member_unique", queried_sql)
        self.assertNotIn("relation_edge_equality", queried_sql)

    def test_oa_pending_payment_audit_reads_direct_canonical_facts_only(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="oa_pending_payments",
        )

        queried_sql = " ".join(
            sql
            for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls
        )
        self.assertEqual(report["mode"], "page-business-canonical-read-audit")
        self.assertEqual(report["label"], "OA 待付款核对")
        self.assertIn("/* check: direct_canonical_summary */", queried_sql)
        self.assertIn("app.oa_applications", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertIn("/* check: canonical_relation_oa_member_exists */", queried_sql)
        self.assertIn("/* check: canonical_relation_bank_member_exists */", queried_sql)
        self.assertIn("/* check: canonical_relation_invoice_member_exists */", queried_sql)
        self.assertIn("/* check: oa_pending_payment_relation_visibility */", queried_sql)
        self.assertNotIn("read_model.oa_pending", queried_sql)
        self.assertNotIn("job.read_model_dirty_scopes", queried_sql)
        self.assertNotIn("job.outbox_events", queried_sql)
        self.assertNotIn("consumer_relation_edge_equality", queried_sql)
        self.assertEqual(report["audit_contract"]["scope_types"], [])
        self.assertEqual(report["audit_contract"]["event_types"], [])
        self.assertEqual(
            report["audit_contract"]["proof_checks"],
            [
                "single_repeatable_read_snapshot",
                "canonical_relation_member_existence",
                "canonical_relation_identity_uniqueness",
                "oa_pending_payment_relation_visibility",
            ],
        )

    def test_oa_pending_payment_hidden_active_outflow_relation_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "oa_pending_payment_relation_visibility": [
                        {
                            "subject_id": "case-turnover-hidden",
                            "scope_key": "2026-05",
                            "existing_outflow_count": None,
                            "payment_status": None,
                        }
                    ]
                }
            ),
            domain_key="oa_pending_payments",
        )

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"oa_pending_payments_active_outflow_relation_not_visible": 1},
        )

    def test_oa_pending_payment_missing_canonical_oa_member_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_oa_member_exists": [
                        {
                            "subject_id": "case-oa-1",
                            "scope_key": "2026-06",
                            "row_id": "oa-missing",
                        }
                    ]
                }
            ),
            domain_key="oa_pending_payments",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"oa_pending_payments_canonical_relation_oa_member_missing": 1},
        )
        self.assertEqual(report["issues"][0]["details"]["row_id"], "oa-missing")

    def test_pending_invoice_audit_has_no_projected_consumer_edge_contract(self) -> None:
        connection = FakeConnection()

        report = audit_page_business_read_model.audit_page_business_read_model(
            connection,
            domain_key="pending_invoices",
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertNotIn("consumer_relation_edge_equality", queried_sql)
        self.assertEqual(report["audit_contract"]["relation_tables"], ["app.workbench_pair_relations"])
        self.assertEqual(report["audit_contract"]["scope_types"], [])
        self.assertEqual(report["audit_contract"]["event_types"], [])

    def test_pending_invoice_duplicate_active_relation_membership_is_blocking(self) -> None:
        report = audit_page_business_read_model.audit_page_business_read_model(
            FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_unique": [
                        {
                            "subject_id": "bank-overlap",
                            "scope_key": "2026-06",
                            "active_case_ids": ["case-1", "case-2"],
                        }
                    ]
                }
            ),
            domain_key="pending_invoices",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"pending_invoices_canonical_relation_bank_member_duplicated": 1},
        )

    def test_unregistered_consumer_contract_does_not_claim_consumer_equality(self) -> None:
        connection = FakeConnection()

        report = audit_cost_statistics_page(
            connection,
        )

        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertNotIn("consumer_relation_edge_equality", queried_sql)
        self.assertNotIn("consumer_relation_edge_equality", report["audit_contract"]["proof_checks"])

    def test_cli_fail_on_issues_returns_nonzero(self) -> None:
        stdout = io.StringIO()

        exit_code = audit_page_business_read_model.main(
            ["bank_details", "--json", "--fail-on-issues"],
            connection=FakeConnection(
                rows_by_check={
                    "canonical_relation_bank_member_exists": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-05",
                            "row_id": "bank-missing",
                            "row_type": "bank_transaction",
                        }
                    ]
                }
            ),
            stdout=stdout,
        )

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["overall_status"], "issues_found")
        self.assertEqual(
            payload["summary"]["issue_sample_counts_by_code"],
            {"bank_details_canonical_relation_bank_member_missing": 1},
        )


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

    def test_missing_canonical_bank_relation_member_is_blocking(self) -> None:
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types, updated_at
            ) values (
                'case:missing-bank', 'manual', 'active', '2026-03-01',
                array['bank-missing'], array['bank'],
                '2026-07-13 08:00:00+00'::timestamptz
            )
            """
        )
        report = audit_page_business_read_model.audit_page_business_read_model(
            self.connection,
            domain_key="bank_details",
        )

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["summary"]["issue_sample_counts_by_code"],
            {"bank_details_canonical_relation_bank_member_missing": 1},
        )


def _bank_flow_188500_candidate_source() -> dict[str, object]:
    return {
        "candidate_rows": [
            {
                "id": "bank-out-188500",
                "trade_time": "2026-05-14T09:00:00",
                "account_key": "CCB:8106",
                "counterparty_name": "云南溯源科技有限公司",
                "direction": "expense",
                "amount": "188500.00",
            },
            {
                "id": "bank-in-188500",
                "trade_time": "2026-05-14T09:30:00",
                "account_key": "ICBC:6386",
                "counterparty_name": "云南溯源科技有限公司",
                "direction": "income",
                "amount": "188500.00",
            },
        ],
        "active_relations": [],
        "formal_items": [],
        "tag_policy": {
            "active_tags": [
                {"code": "internal_transfer", "label": "内部往来款"}
            ],
            "requirements_by_tag_code": {
                "internal_transfer": {
                    "requires_oa": False,
                    "requires_invoice": False,
                }
            },
        },
    }


def _check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()
if __name__ == "__main__":
    unittest.main()
