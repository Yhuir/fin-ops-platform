from __future__ import annotations

import os
import re
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from fin_ops_platform.postgres import migrate

MIGRATIONS_DIR = Path("backend/src/fin_ops_platform/postgres/migrations")
EXPECTED_MIGRATIONS = [
    "0001_extensions_and_schemas.sql",
    "0002_core_imports_invoices_bank.sql",
    "0003_workbench_relations_exceptions.sql",
    "0004_oa_projection_sync.sql",
    "0005_tax_etc_turnover_settings_jobs.sql",
    "0006_read_models.sql",
    "0007_grants.sql",
    "0008_pending_invoice_commands.sql",
    "0009_runtime_infrastructure.sql",
    "0010_runtime_phase2_cutover.sql",
    "0011_runtime_phase2_query_indexes.sql",
    "0012_workbench_rows_scope_unique.sql",
    "0013_oa_attachment_cache_sources.sql",
    "0014_workbench_groups_read_model.sql",
    "0015_workbench_groups_sort_columns.sql",
    "0016_runtime_outbox_envelope_fields.sql",
    "0017_rabbitmq_outbox_publish_state.sql",
    "0018_api_performance_read_model.sql",
    "0019_import_jobs.sql",
    "0020_oa_attachment_cache_source_identity_links.sql",
    "0021_read_model_hot_path_indexes.sql",
    "0022_read_model_native_closeout.sql",
    "0023_workbench_group_rows_filters.sql",
    "0024_pending_invoice_query_fields.sql",
    "0025_pending_invoice_runtime_grants.sql",
    "0026_invoice_usage_collection_read_models.sql",
    "0027_invoice_usage_collection_runtime_grants.sql",
    "0028_workbench_reconciliation_decisions.sql",
    "0029_workbench_reconciliation_runtime_grants.sql",
    "0030_bank_detail_read_model.sql",
    "0031_bank_transaction_auto_category_context_index.sql",
    "0032_bank_detail_runtime_grants.sql",
    "0033_bank_detail_primary_sub_labels.sql",
    "0034_workbench_generation_convergence.sql",
    "0035_workbench_generation_runtime_grants.sql",
    "0036_workbench_generation_consistency.sql",
    "0037_workbench_generation_stats_retention.sql",
    "0038_workbench_generation_stats_runtime_grants.sql",
    "0039_bank_account_balance_read_model.sql",
    "0040_pending_invoice_source_versions.sql",
    "0041_bank_transaction_category_confirmations.sql",
    "0042_bank_detail_candidate_projection.sql",
    "0043_workbench_idempotency_records.sql",
    "0044_bank_detail_external_turnover_third_labels.sql",
    "0045_output_invoice_collection_lifecycle.sql",
    "0046_input_invoice_usage_oa_reverse_batches.sql",
    "0047_oa_pending_payment_read_model.sql",
    "0048_oa_pending_payment_bank_paid_total.sql",
    "0049_oa_pending_payment_detail_lookup_indexes.sql",
    "0050_tax_offset_plans.sql",
    "0051_pending_invoice_cash_income_scope.sql",
    "0052_workbench_relation_distribution.sql",
    "0053_pending_invoice_cash_income_rows.sql",
    "0054_workbench_relation_hot_path_indexes.sql",
    "0055_invoice_lifecycle_distribution.sql",
    "0056_app_status_readiness.sql",
    "0057_app_health_dashboard_metrics_indexes.sql",
    "0058_workbench_object_identity.sql",
    "0059_input_invoice_usage_bank_filters.sql",
    "0060_oa_pending_payment_bank_filters.sql",
    "0061_output_invoice_collection_bank_filters.sql",
    "0062_workbench_relation_etc_external_batch_idx.sql",
    "0063_etc_remove_oa_detection_runtime.sql",
    "0064_etc_scrub_oa_detection_metadata.sql",
    "0065_invoice_canonical_identity_fingerprint_invariant.sql",
    "0066_oa_applicant_credentials.sql",
    "0067_app_status_current_effective_outbox_index.sql",
    "0068_outbox_read_model_refresh_metric_samples.sql",
    "0069_oa_attachment_identity_bridge_repair.sql",
    "0070_workbench_unused_write_indexes.sql",
    "0071_oa_application_workflow_status.sql",
    "0072_oa_pending_payment_workflow_status.sql",
    "0073_oa_pending_payment_bank_relations.sql",
    "0074_etc_batch_invoice_links.sql",
    "0075_etc_batch_invoice_links_runtime_grants.sql",
    "0076_outbox_read_model_refresh_metric_attention.sql",
    "0077_workbench_relation_rows_scope_unique.sql",
    "0078_workbench_relation_rows_scope_unique_repair.sql",
    "0079_workbench_relation_rows_scope_unique_hardening.sql",
    "0080_no_oa_bank_batch_relation_mode_filter.sql",
    "0081_oa_source_aliases.sql",
    "0082_bank_flow_rule_batch_storage.sql",
    "0083_bank_flow_rule_batch_tag_rules.sql",
    "0084_runtime_queue_history_retention.sql",
    "0085_pending_invoice_trade_date_nulls_last_index.sql",
    "0086_runtime_queue_claim_hot_path.sql",
    "0087_oa_pending_payment_claim_hot_path.sql",
    "0088_app_health_dashboard_current_effective_hot_path.sql",
    "0089_read_model_performance_hot_paths.sql",
    "0090_import_etc_list_hot_paths.sql",
    "0091_import_file_ordering_hot_path.sql",
    "0092_cost_statistics_parent_rollup_hot_path.sql",
    "0093_workbench_relation_source_version_hot_paths.sql",
    "0094_input_invoice_usage_oa_reverse_preview_hot_path.sql",
    "0095_oa_pending_payment_admissions.sql",
    "0096_oa_pending_payment_admission_runtime_grants.sql",
    "0097_drop_import_files_batch_fallback.sql",
    "0098_etc_import_session_files.sql",
    "0099_external_control_evidence.sql",
    "0100_phase19_runtime_grants.sql",
    "0101_phase19_audit_contract_boundaries.sql",
    "0102_workbench_idempotency_runtime_evidence_grant.sql",
    "0103_etc_reconciliation_task_timestamps.sql",
    "0104_oa_pending_payment_source_snapshot.sql",
    "0105_cost_statistics_freshness_gate.sql",
    "0106_oa_pending_payment_native_oa_ids.sql",
    "0107_cost_statistics_structured_bank_flow_rows.sql",
    "0108_cost_statistics_bank_flow_runtime_grant.sql",
    "0109_oa_pending_payment_freshness_gate_hot_path.sql",
    "0110_oa_pending_payment_outbox_freshness_hot_path.sql",
    "0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql",
    "0112_batch_accounting_oa_type_hot_path.sql",
    "0113_batch_accounting_relation_count_hot_path.sql",
    "0114_operation_barrier_latest_scope_hot_path.sql",
    "0115_turnover_ledger_relation_delta_hot_path.sql",
    "0116_workbench_etc_relation_enrichment_hot_path.sql",
    "0117_workbench_matching_idempotency_runtime_grant.sql",
    "0118_bank_flow_rule_batch_settings_raw_alignment.sql",
    "0119_turnover_ledger_scope_summaries.sql",
    "0120_bank_transaction_category_legacy_lookup.sql",
    "0121_app_health_scope_evidence_hot_path.sql",
    "0122_cost_statistics_access_convergence_hot_paths.sql",
    "0123_drop_legacy_cost_statistics_bank_flow_rows.sql",
    "0124_bank_detail_canonical_source_proof.sql",
    "0125_workbench_canonical_proof_identity_indexes.sql",
    "0126_cost_statistics_direct_canonical_read.sql",
    "0127_direct_canonical_page_runtime_retirement.sql",
    "0128_tax_offset_plan_runtime_grant.sql",
    "0129_runtime_outbox_canonical_attempts_contract.sql",
    "0130_canonical_finance_domain_contracts.sql",
    "0131_validate_canonical_finance_domain_contracts.sql",
    "0132_settings_access_control_guard.sql",
    "0133_settings_access_control_canonical_order.sql",
    "0134_restore_invoice_import_provenance.sql",
    "0135_batch_accounting_tag_selection.sql",
    "0136_unify_in_progress_oa_workbench_relations.sql",
    "0137_oa_attachment_identity_context_index.sql",
    "0138_operation_audit_and_financial_fact_guard.sql",
    "0139_idempotency_and_worker_attempt_history.sql",
    "0140_bank_transaction_identity_strength.sql",
    "0141_settings_data_reset_recovery_guard.sql",
    "0142_operation_history_logical_operations.sql",
    "0143_import_lifecycle_hot_paths.sql",
    "0144_import_file_session_owner.sql",
    "0145_bank_relation_requirement_recalculation.sql",
    "0146_bank_relation_requirement_rollout_retry.sql",
    "0147_bank_relation_requirement_scope_retry.sql",
    "0148_retire_workbench_matching_progress_jobs.sql",
    "0149_remove_read_model_runtime.sql",
    "0150_workbench_oa_supporting_documents.sql",
    "0151_workbench_matching_worker_idempotency_grant.sql",
    "0152_workbench_supporting_document_gallery_index.sql",
    "0153_oa_source_alias_attachment_identity_repair.sql",
    "0154_migrate_etc_summary_anomaly_review.sql",
    "0155_revalidate_etc_summary_anomaly_review.sql",
    "0156_backfill_workbench_anomaly_reviewer_identity.sql",
    "0157_cost_statistics_manual_allocations.sql",
    "0158_oa_payment_status_auto_reconcile.sql",
    "0159_oa_payment_status_runtime_grant.sql",
    "0160_remove_oa_payment_status_writeback_ownership.sql",
    "0161_converge_formal_bank_relation_requirements.sql",
    "0162_cost_statistics_unit_manual_allocations.sql",
    "0163_workbench_relation_receipts.sql",
    "0164_manual_bank_entry_audit_contract.sql",
    "0165_page_access_accounts.sql",
    "0166_cash_ledger.sql",
]
EXPECTED_TABLES = [
    "audit.events",
    "audit.app_health_alerts",
    "audit.external_control_evidence",
    "audit.external_control_evidence_items",
    "job.outbox_events",
    "job.background_jobs",
    "job.import_jobs",
    "job.runtime_event_attempts",
    "job.settings_data_reset_recovery_receipts",
    "job.workbench_matching_dirty_scopes",
    "job.read_model_dirty_scopes",
    "job.runtime_worker_heartbeats",
    "staging.mongo_exports",
    "staging.mongo_raw_records",
    "staging.id_mappings",
    "app.import_batches",
    "app.import_batch_rows",
    "app.import_files",
    "app.file_objects",
    "app.workbench_oa_supporting_documents",
    "app.invoices",
    "app.bank_transactions",
    "app.financial_fact_corrections",
    "app.bank_transaction_categories",
    "app.bank_transaction_category_events",
    "app.bank_transaction_category_confirmations",
    "app.matching_runs",
    "app.matching_results",
    "app.workbench_pair_relations",
    "app.cost_statistics_manual_allocations",
    "app.workbench_relation_receipts",
    "app.workbench_pair_relation_history",
    "app.workbench_row_overrides",
    "app.workbench_exception_cases",
    "app.workbench_exception_case_events",
    "app.no_oa_bank_batches",
    "app.no_oa_bank_batch_events",
    "app.bank_flow_rule_batches",
    "app.bank_flow_rule_batch_events",
    "app.oa_applications",
    "app.oa_application_items",
    "app.oa_attachments",
    "app.oa_sync_runs",
    "app.oa_sync_watermarks",
    "app.oa_attachment_invoice_cache",
    "app.oa_source_aliases",
    "app.manual_oa_imports",
    "app.tax_certified_import_sessions",
    "app.tax_certified_import_batches",
    "app.tax_certified_import_records",
    "app.tax_offset_plans",
    "app.etc_invoices",
    "app.etc_import_session_files",
    "app.etc_import_sessions",
    "app.etc_import_batches",
    "app.etc_submission_batches",
    "app.etc_business_batches",
    "app.etc_batch_invoice_links",
    "app.etc_reconciliation_tasks",
    "app.etc_reconciliation_files",
    "app.historical_etc_repair_bundles",
    "app.historical_etc_repair_parsed_seeds",
    "app.historical_etc_repair_states",
    "app.turnover_relations",
    "app.turnover_relation_events",
    "app.turnover_ledger_extras",
    "app.app_settings",
    "app.pending_invoice_manual_invoice_commands",
    "app.workbench_idempotency_records",
    "app.output_invoice_collection_status_overrides",
    "app.output_invoice_collection_reminders",
    "app.output_invoice_collection_red_relations",
    "app.output_invoice_receipt_settings",
    "app.output_invoice_receipt_number_counters",
    "app.output_invoice_receipts",
    "app.output_invoice_receipt_events",
    "app.input_invoice_usage_oa_reverse_batches",
    "app.oa_applicant_credentials",
    "app.oa_pending_payment_bank_relations",
    "app.bank_transaction_relation_claims",
    "app.oa_pending_payment_bank_relation_events",
    "app.oa_pending_payment_admissions",
    "app.oa_pending_payment_status_snapshots",
    "read_model.workbench_rows",
    "read_model.workbench_groups",
    "read_model.workbench_group_rows",
    "read_model.workbench_generations",
    "read_model.workbench_generation_stats",
    "read_model.workbench_summary",
    "read_model.workbench_snapshots",
    "read_model.workbench_relation_scopes",
    "read_model.workbench_relation_groups",
    "read_model.workbench_relation_rows",
    "read_model.search_index_rows",
    "read_model.pending_invoice_rows",
    "read_model.pending_invoice_scopes",
    "read_model.invoice_lifecycle_rows",
    "read_model.invoice_lifecycle_scopes",
    "read_model.input_invoice_usage_rows",
    "read_model.input_invoice_usage_scopes",
    "read_model.output_invoice_collection_rows",
    "read_model.output_invoice_collection_scopes",
    "read_model.oa_pending_payment_rows",
    "read_model.oa_pending_payment_scopes",
    "read_model.bank_detail_rows",
    "read_model.bank_detail_scopes",
    "read_model.bank_account_balances",
    "read_model.tax_offset_read_models",
    "read_model.tax_offset_items",
    "read_model.no_oa_bank_batch_rows",
    "read_model.bank_flow_rule_batch_rows",
    "read_model.turnover_ledger_rows",
    "read_model.turnover_ledger_scopes",
]
READ_MODEL_STORAGE_CONTRACTS = {
    "workbench": (
        "read_model.workbench_generations",
        "read_model.workbench_rows",
        "read_model.workbench_groups",
        "read_model.workbench_group_rows",
        "read_model.workbench_summary",
        "read_model.workbench_snapshots",
    ),
    "workbench_relation": (
        "read_model.workbench_relation_scopes",
        "read_model.workbench_relation_groups",
        "read_model.workbench_relation_rows",
    ),
    "bank_detail": ("read_model.bank_detail_rows", "read_model.bank_detail_scopes"),
    "bank_account_balance": ("read_model.bank_account_balances",),
    "pending_invoice": ("read_model.pending_invoice_rows", "read_model.pending_invoice_scopes"),
    "search": ("read_model.search_index_rows",),
    "invoice_lifecycle": ("read_model.invoice_lifecycle_rows", "read_model.invoice_lifecycle_scopes"),
    "input_invoice_usage": ("read_model.input_invoice_usage_rows", "read_model.input_invoice_usage_scopes"),
    "output_invoice_collection": (
        "read_model.output_invoice_collection_rows",
        "read_model.output_invoice_collection_scopes",
    ),
    "oa_pending_payment": ("read_model.oa_pending_payment_rows", "read_model.oa_pending_payment_scopes"),
    "tax_offset": ("read_model.tax_offset_read_models", "read_model.tax_offset_items"),
    "no_oa_bank_batch": ("read_model.no_oa_bank_batch_rows",),
    "bank_flow_rule_batch": ("read_model.bank_flow_rule_batch_rows",),
    "turnover_ledger": ("read_model.turnover_ledger_rows", "read_model.turnover_ledger_scopes"),
}


def migration_sql() -> str:
    return "\n".join((MIGRATIONS_DIR / name).read_text(encoding="utf-8") for name in EXPECTED_MIGRATIONS)


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--.*?$", "", sql, flags=re.M)


class PostgresMigrationDiscoveryTests(unittest.TestCase):
    def test_expected_migration_files_are_present_and_ordered(self) -> None:
        migrations = migrate.discover_migrations(MIGRATIONS_DIR)
        self.assertEqual([item.path.name for item in migrations], EXPECTED_MIGRATIONS)
        self.assertEqual(
            [item.version for item in migrations],
            [f"{number:04d}" for number in range(1, 167)],
        )
        for item in migrations:
            self.assertRegex(item.checksum_sha256, r"^[0-9a-f]{64}$")

    def test_bank_flow_rule_tag_settings_migration_removes_legacy_selected_shape(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0111_bank_flow_rule_batch_tag_rules_canonical_shape.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("bank_flow_rule_batch_tag_rules", sql)
        self.assertIn("requirements_by_tag_code", sql)
        self.assertIn("selected_tag_codes", sql)
        self.assertIn("jsonb_array_elements_text", sql)
        self.assertNotIn("no_oa_bank_batch_tag_selection", sql)

    def test_workbench_supporting_documents_have_exact_item_lookup_and_file_ownership(self) -> None:
        sql = (MIGRATIONS_DIR / "0150_workbench_oa_supporting_documents.sql").read_text(encoding="utf-8").lower()
        gallery_sql = (
            MIGRATIONS_DIR / "0152_workbench_supporting_document_gallery_index.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists app.workbench_oa_supporting_documents", sql)
        self.assertIn("file_object_id uuid not null references app.file_objects(id)", sql)
        self.assertIn("oa_row_id, expense_item_id, content_sha256", sql)
        self.assertIn("where status = 'active'", sql)
        self.assertIn("(created_at desc, id desc)", gallery_sql)
        self.assertIn("where status = 'active'", gallery_sql)

    def test_oa_source_alias_attachment_repair_is_exact_and_fail_closed(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0153_oa_source_alias_attachment_identity_repair.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("oa-exp-2327", sql)
        self.assertIn("oa-exp-6a86a63777bca2d0c5f62d07", sql)
        self.assertIn("inv_imported_0898", sql)
        self.assertIn("inv_imported_0899", sql)
        self.assertIn("v_expected_legacy_item_ids", sql)
        self.assertIn("v_expected_current_item_ids", sql)
        self.assertIn("invoice.workbench_visibility = 'visible'", sql)
        self.assertIn("current_item_invoice_evidence as materialized", sql)
        self.assertIn("current_owned_evidence as materialized", sql)
        self.assertIn("attachment.normalized_payload->>'source_expense_item_id'", sql)
        self.assertIn("current.invoice_identity = invoice.invoice_identity", sql)
        self.assertNotIn(
            "bridge.source_expense_row_index = invoice.source_expense_row_index",
            sql,
        )
        self.assertIn("matched_invoice_attachment_count <> 2", sql)
        self.assertIn("cardinality(invoice_attachment_key_hashes) <> 2", sql)
        self.assertIn("cardinality(invoice_identity_hashes) <> 2", sql)
        self.assertIn("verified_attachment_identity_migration", sql)
        self.assertIn("system:migration:0153", sql)
        self.assertNotIn("update app.oa_applications", sql)
        self.assertNotIn("update app.invoices", sql)
        self.assertNotIn("delete from", sql)

    def test_etc_summary_anomaly_review_migration_is_exact_append_only_and_fail_closed(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0154_migrate_etc_summary_anomaly_review.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76", sql)
        self.assertIn("cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b", sql)
        self.assertIn("case-batch-txn_imported_1453", sql)
        self.assertIn("etc-summary-etc-oa-20260413-241125", sql)
        self.assertIn("v_expected_members", sql)
        self.assertIn("relation_row.amount_check->>'invoice_total' is distinct from '2411.25'", sql)
        self.assertIn("old_evidence is distinct from v_expected_old_evidence", sql)
        self.assertIn("old_decision.updated_at is distinct from v_reviewed_at", sql)
        self.assertIn("workbench_anomaly_review_migrated", sql)
        self.assertIn("system:migration:0154", sql)
        self.assertIn("insert into app.workbench_exception_cases", sql)
        self.assertNotIn("update app.workbench_exception_cases", sql)
        self.assertNotIn("delete from", sql)

    def test_etc_summary_anomaly_review_revalidation_is_retired_without_data_mutation(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0155_revalidate_etc_summary_anomaly_review.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("targeted 0155 decision rewrite was retired", sql)
        self.assertIn("preserve the 0154 exception rows", sql)
        self.assertNotIn("insert into", sql)
        self.assertNotIn("update app.", sql)
        self.assertNotIn("delete from", sql)

    def test_anomaly_reviewer_identity_backfill_is_fail_closed_and_idempotent(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0156_backfill_workbench_anomaly_reviewer_identity.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("count(distinct lower(btrim(event.actor_account)))", sql)
        self.assertIn("account_count <> 1", sql)
        self.assertIn("'{actor_account}'", sql)
        self.assertIn("'{actor_name}'", sql)
        self.assertIn("workbench_anomaly_reviewer_identity_backfilled", sql)
        self.assertIn("system:migration:0156", sql)
        self.assertIn("nullif(", sql)
        self.assertIn("for update", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("update audit.events", sql)

    def test_cost_statistics_manual_allocations_are_versioned_and_not_deletable_by_runtime_roles(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0157_cost_statistics_manual_allocations.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("relation_case_id text not null unique", normalized_sql)
        self.assertIn("source_fingerprint ~ '^[0-9a-f]{64}$'", normalized_sql)
        self.assertIn("allocations jsonb not null", normalized_sql)
        self.assertIn(
            "grant select, insert, update on app.cost_statistics_manual_allocations to fin_ops_api",
            normalized_sql,
        )
        self.assertIn(
            "grant select, insert, update on app.cost_statistics_manual_allocations to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertNotIn("grant delete", normalized_sql)
        self.assertNotIn("delete from", normalized_sql)

    def test_cost_statistics_manual_allocations_migrate_from_source_matrix_fail_closed(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0162_cost_statistics_unit_manual_allocations.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("jsonb_array_elements(decision.allocations)", normalized_sql)
        self.assertIn("jsonb_object_keys(line.value)", normalized_sql)
        self.assertIn("line.value->>'source_kind' not in ('outflow', 'paid_wrong_refund')", normalized_sql)
        self.assertIn("when 'paid_wrong_refund' then -(line.value->>'amount')::numeric", normalized_sql)
        self.assertIn("group by line.value->>'unit_id'", normalized_sql)
        self.assertIn("reduced.minimum_unit_amount < 0", normalized_sql)
        self.assertIn("reduced.allocated_total <> decision.net_cash_cost", normalized_sql)
        self.assertIn("raise exception", normalized_sql)
        self.assertIn("'unit_id', grouped.unit_id", normalized_sql)
        self.assertIn("'amount', to_char(grouped.unit_amount", normalized_sql)
        self.assertIn("rename column allocations to unit_allocations", normalized_sql)
        self.assertIn("add column non_cost_amount numeric(18, 2) not null default 0.00", normalized_sql)
        self.assertIn("add column non_cost_reason text not null default ''", normalized_sql)
        self.assertIn("non_cost_amount <= net_outflow_total", normalized_sql)
        self.assertNotIn("delete from", normalized_sql)
        self.assertNotIn("drop table", normalized_sql)

    def test_workbench_relation_receipts_are_append_only_and_owned_by_file_objects(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0163_workbench_relation_receipts.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists app.workbench_relation_receipts", normalized_sql)
        self.assertIn(
            "relation_id uuid not null references app.workbench_pair_relations(id)",
            normalized_sql,
        )
        self.assertIn(
            "file_object_id uuid not null references app.file_objects(id)",
            normalized_sql,
        )
        self.assertIn("source_fingerprint ~ '^[0-9a-f]{64}$'", normalized_sql)
        self.assertIn("unique (case_id, source_fingerprint)", normalized_sql)
        self.assertIn("receipt_count > 0", normalized_sql)
        self.assertIn("total_amount >= 0", normalized_sql)
        self.assertIn("raw_payload jsonb not null default '{}'::jsonb", normalized_sql)
        self.assertIn(
            "grant select, insert on app.workbench_relation_receipts to fin_ops_api",
            normalized_sql,
        )
        self.assertIn(
            "grant select, insert on app.workbench_relation_receipts to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertIn(
            "grant select on app.workbench_relation_receipts to fin_ops_readonly",
            normalized_sql,
        )
        self.assertIn(
            "grant select, insert, update, delete on app.workbench_relation_receipts to fin_ops_migrator",
            normalized_sql,
        )
        self.assertNotIn(
            "grant delete on app.workbench_relation_receipts to fin_ops_api",
            normalized_sql,
        )
        self.assertNotIn(
            "grant delete on app.workbench_relation_receipts to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertNotIn(" app_runtime", normalized_sql)

    def test_manual_bank_entry_audit_contract_is_precise_and_non_destructive(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0164_manual_bank_entry_audit_contract.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("update app.import_files", normalized_sql)
        self.assertIn("set audit_contract_revision = 'manual-bank-entry-audit.v1'", normalized_sql)
        self.assertIn("template_kind = 'manual_bank_transaction_entry'", normalized_sql)
        self.assertIn("audit_contract_revision = 'import-page-audit.v1'", normalized_sql)
        self.assertIn("file_object_id is null", normalized_sql)
        self.assertIn("coalesce(btrim(stored_file_path), '') = ''", normalized_sql)
        self.assertIn(
            "raw_payload #>> '{normalized_payload,template_code}'",
            normalized_sql,
        )
        self.assertNotIn("delete from", normalized_sql)
        self.assertNotIn("drop table", normalized_sql)

    def test_oa_payment_status_auto_reconcile_backfill_is_bounded_and_event_only(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0158_oa_payment_status_auto_reconcile.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists app.oa_payment_status_writeback_states", normalized_sql)
        self.assertIn("where relation.status = 'active'", normalized_sql)
        self.assertIn("bank.txn_direction = 'outflow'", normalized_sql)
        self.assertIn("insert into job.outbox_events", normalized_sql)
        self.assertIn("'oa.payment_status.reconcile'", normalized_sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", normalized_sql)
        self.assertIn("do nothing", normalized_sql)
        self.assertNotIn("delete from", normalized_sql)
        self.assertNotIn("update app.oa_", normalized_sql)

    def test_oa_payment_status_runtime_role_can_persist_writeback_ownership(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0159_oa_payment_status_runtime_grant.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn(
            "grant select, insert, update on app.oa_payment_status_writeback_states "
            "to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertNotIn("grant delete", normalized_sql)
        self.assertNotIn("delete from", normalized_sql)

    def test_oa_payment_status_rule_migration_removes_ownership_and_reconciles_all_canonical_oa(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0160_remove_oa_payment_status_writeback_ownership.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("drop table if exists app.oa_payment_status_writeback_states", normalized_sql)
        self.assertIn("from app.oa_applications", normalized_sql)
        self.assertIn("from app.oa_pending_payment_admissions", normalized_sql)
        self.assertIn("select 'default'::text as tenant_id, row_id as oa_id", normalized_sql)
        self.assertIn("select tenant_id, oa_id", normalized_sql)
        self.assertIn("union", normalized_sql)
        self.assertIn("insert into job.outbox_events", normalized_sql)
        self.assertIn("'oa.payment_status.reconcile'", normalized_sql)
        self.assertIn("'migration_0160_rule_reconcile'", normalized_sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", normalized_sql)
        self.assertNotIn("delete from app.oa_", normalized_sql)
        self.assertNotIn("update app.oa_", normalized_sql)

    def test_batch_accounting_oa_type_hot_path_index_matches_query_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0112_batch_accounting_oa_type_hot_path.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("workbench_rows_batch_accounting_oa_type_trgm_idx", sql)
        self.assertIn("coalesce(payload->>'apply_type', '')", sql)
        self.assertIn("coalesce(payload->>'expense_type', '')", sql)
        self.assertIn("gin_trgm_ops", sql)
        self.assertIn("where source_kind = 'oa'", sql)
        self.assertIn("scope_key <> 'all'", sql)

    def test_operation_audit_and_financial_fact_guard_is_append_only_and_reasoned(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0138_operation_audit_and_financial_fact_guard.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists app.financial_fact_corrections", sql)
        self.assertIn("audit_events_append_only", sql)
        self.assertIn("bank_transactions_financial_fact_guard", sql)
        self.assertIn("invoices_financial_fact_guard", sql)
        self.assertIn("workbench_pair_relation_history_append_only", sql)
        self.assertIn("current_setting('fin_ops.correction_reason', true)", sql)
        self.assertIn("before_value", sql)
        self.assertIn("after_value", sql)
        self.assertIn("audit.coverage_started", sql)
        self.assertIn("revoke update, delete on audit.events from fin_ops_api", sql)

    def test_operation_history_logical_operation_indexes_and_actor_snapshot(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0142_operation_history_logical_operations.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists actor_account text", sql)
        self.assertIn("audit_events_request_time_idx", sql)
        self.assertIn("add column if not exists request_id text", sql)
        self.assertIn("workbench_pair_relation_history_request_time_idx", sql)

    def test_import_lifecycle_hot_path_indexes_match_query_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0143_import_lifecycle_hot_paths.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("import_files_lifecycle_batch_idx", sql)
        self.assertIn("raw_payload->'normalized_payload'->>'batch_id'", sql)
        self.assertIn("raw_payload->'normalized_payload'->>'preview_batch_id'", sql)
        self.assertIn("uploaded_at desc", sql)
        self.assertIn("import_jobs_session_latest_idx", sql)
        self.assertIn("(import_session_id, created_at desc, id desc)", sql)

    def test_import_file_session_owner_backfill_uses_linked_batch_owner(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0144_import_file_session_owner.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("update app.import_files", sql)
        self.assertIn("uploaded_by = import_batch.imported_by", sql)
        self.assertIn("jsonb_build_object('imported_by', import_batch.imported_by)", sql)
        self.assertIn("raw_payload->'normalized_payload'->>'preview_batch_id'", sql)
        self.assertIn("from app.import_batches import_batch", sql)

    def test_batch_accounting_relation_count_hot_path_index_matches_query_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0113_batch_accounting_relation_count_hot_path.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("workbench_relation_groups_batch_accounting_year_scope_group_idx", sql)
        self.assertIn("payload->'special_metadata'->>'bank_year'", sql)
        self.assertIn("payload->'special_metadata'->>'year'", sql)
        self.assertIn("scope_key", sql)
        self.assertIn("group_id", sql)
        self.assertIn("where relation_status = 'linked'", sql)
        self.assertIn("payload->'special_metadata'->>'source' = 'batch_accounting'", sql)

    def test_operation_barrier_latest_scope_index_matches_query_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0114_operation_barrier_latest_scope_hot_path.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("outbox_events_operation_barrier_latest_scope_idx", sql)
        self.assertIn("tenant_id", sql)
        self.assertIn("event_type", sql)
        self.assertIn("coalesce(scope_type, raw_payload->>'scope_type'", sql)
        self.assertIn("coalesce(scope_key, raw_payload->>'scope_key'", sql)
        self.assertIn("created_at desc", sql)
        self.assertIn("id desc", sql)
        self.assertIn("include (status, publish_status, updated_at, last_error, publish_last_error)", sql)

    def test_turnover_ledger_relation_delta_index_matches_query_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0115_turnover_ledger_relation_delta_hot_path.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("turnover_ledger_rows_bank_row_ids_gin", sql)
        self.assertIn("read_model.turnover_ledger_rows", sql)
        self.assertIn("using gin (bank_row_ids)", sql)

    def test_turnover_ledger_scope_summary_has_zero_row_and_runtime_contracts(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0119_turnover_ledger_scope_summaries.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists read_model.turnover_ledger_scopes", normalized_sql)
        self.assertIn("scope_key text not null unique", normalized_sql)
        self.assertIn("row_count integer not null default 0", normalized_sql)
        self.assertIn("source_versions jsonb not null", normalized_sql)
        self.assertIn("statistics jsonb not null", normalized_sql)
        self.assertIn("generation bigint not null default 0", normalized_sql)
        self.assertIn("published_source_version bigint", normalized_sql)
        self.assertIn("check (generation >= 0)", normalized_sql)
        self.assertIn("raw_payload = raw_payload - 'page_statistics'", normalized_sql)
        for role in ("fin_ops_worker", "fin_ops_migrator", "fin_ops_app_runtime", "fin_ops_app"):
            self.assertIn(
                f"grant select, insert, update, delete on read_model.turnover_ledger_scopes to {role}",
                normalized_sql,
            )

    def test_workbench_etc_relation_enrichment_indexes_match_exact_contract(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0116_workbench_etc_relation_enrichment_hot_path.sql"
        ).read_text(encoding="utf-8").lower()

        self.assertIn("oa_applications_etc_batch_marker_idx", sql)
        self.assertIn("normalized_payload->>'etc_batch_id'", sql)
        self.assertIn("etc_business_batches_external_scope_idx", sql)
        self.assertIn("external_etc_batch_id", sql)
        self.assertIn("workbench_pair_relations_active_etc_link_idx", sql)
        self.assertIn("special_metadata->'etc_batch_link'", sql)

    def test_workbench_matching_runtime_can_commit_idempotency_records(self) -> None:
        sql = (MIGRATIONS_DIR / "0117_workbench_matching_idempotency_runtime_grant.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("fin_ops_app_runtime", sql)
        self.assertIn(
            "grant select, insert, update on app.workbench_idempotency_records to fin_ops_app_runtime",
            " ".join(sql.split()),
        )
        self.assertNotIn("delete", sql.lower())

    def test_workbench_matching_worker_can_commit_idempotency_records(self) -> None:
        sql = " ".join(
            (
                MIGRATIONS_DIR / "0151_workbench_matching_worker_idempotency_grant.sql"
            )
            .read_text(encoding="utf-8")
            .lower()
            .split()
        )

        self.assertIn(
            "grant select, insert, update on app.workbench_idempotency_records to fin_ops_worker",
            sql,
        )
        self.assertNotIn("delete", sql)

    def test_tax_offset_runtime_can_read_and_save_plans(self) -> None:
        sql = " ".join(
            (
                MIGRATIONS_DIR / "0128_tax_offset_plan_runtime_grant.sql"
            ).read_text(encoding="utf-8").lower().split()
        )

        self.assertIn(
            "grant select, insert, update on app.tax_offset_plans to fin_ops_app_runtime",
            sql,
        )
        self.assertNotIn("delete", sql)

    def test_pending_invoice_filter_constraints_allow_cash_income(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("pending_invoice_scopes_filter_group_check", sql)
        self.assertIn("pending_invoice_rows_filter_group_check", sql)
        self.assertIn("'cash_income'", sql)

    def test_workbench_relation_hot_path_indexes_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("workbench_relation_rows_scope_status_type_idx", sql)
        self.assertIn("workbench_relation_groups_tenant_group_idx", sql)

    def test_workbench_relation_rows_are_scope_unique(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("drop constraint if exists workbench_relation_rows_tenant_id_row_id_key", sql)
        self.assertIn("workbench_relation_rows_tenant_scope_row_key", sql)
        self.assertIn("unique (tenant_id, scope_key, row_id)", sql)
        self.assertIn("workbench_relation_rows_tenant_scope_row_idx", sql)
        self.assertIn("workbench_relation_rows_tenant_row_idx", sql)
        self.assertIn("partition by tenant_id, scope_key, row_id", sql)
        self.assertIn("scope unique index missing after 0079 hardening", sql)

    def test_workbench_unused_write_indexes_are_dropped(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("drop index if exists read_model.workbench_rows_payload_gin", sql)
        self.assertIn("drop index if exists read_model.workbench_groups_searchable_text_trgm", sql)
        self.assertIn("drop index if exists read_model.workbench_group_rows_column_values_gin", sql)

    def test_app_health_dashboard_metrics_indexes_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("outbox_events_read_model_refresh_metrics_idx", sql)
        self.assertIn("on job.outbox_events (event_type, updated_at desc)", sql)
        self.assertIn("where status = 'done'", sql)
        self.assertIn("event_type like '%.read_model.refresh'", sql)
        self.assertIn("raw_payload->'runtime_result' ? 'duration_ms'", sql)
        self.assertIn("outbox_events_read_model_refresh_metric_samples_idx", sql)
        self.assertIn(
            "(coalesce(aggregate_id, raw_payload->>'scope_key', raw_payload->'runtime_result'->>'scope_key', ''))",
            sql,
        )
        self.assertIn("(((raw_payload->'runtime_result'->>'duration_ms')::numeric))", sql)
        self.assertIn("outbox_events_read_model_refresh_metric_attention_idx", sql)
        self.assertIn("on job.outbox_events (event_type, updated_at desc)", sql)
        self.assertIn("status in ('failed', 'dead_lettered')", sql)
        self.assertIn("status = 'done' and raw_payload->'runtime_result' ? 'duration_ms'", " ".join(sql.split()))
        self.assertIn("outbox_events_read_model_scope_evidence_idx", sql)
        self.assertIn(
            "on job.outbox_events (event_type, updated_at desc) where event_type like '%.read_model.refresh'",
            " ".join(sql.split()),
        )
        self.assertIn("workbench_rows_oa_attachment_inventory_idx", sql)
        self.assertIn("on read_model.workbench_rows (row_id, generated_at desc)", sql)
        self.assertIn("where source_kind = 'oa_attachment_invoice'", sql)

    def test_app_status_current_effective_outbox_index_is_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("outbox_events_app_status_current_effective_idx", sql)
        self.assertIn(
            "on job.outbox_events ( status, tenant_id, event_type, scope_type, scope_key, updated_at desc )",
            normalized_sql,
        )
        self.assertIn("'dead_lettered'", sql)
        self.assertIn("'done'", sql)

    def test_app_health_dashboard_current_effective_hot_path_indexes_are_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0088_app_health_dashboard_current_effective_hot_path.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("outbox_events_app_status_current_effective_scope_idx", normalized_sql)
        self.assertIn("coalesce(scope_type, raw_payload->>'scope_type', payload->>'scope_type', aggregate_type, '')", normalized_sql)
        self.assertIn("coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '')", normalized_sql)
        self.assertIn("updated_at desc, created_at, id", normalized_sql)
        self.assertIn("where status in", normalized_sql)
        self.assertIn("app_status_readiness_fresh_scope_updated_idx", normalized_sql)
        self.assertIn("where status = 'fresh'", normalized_sql)

    def test_read_model_performance_hot_path_indexes_are_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0089_read_model_performance_hot_paths.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("bank_transactions_account_balance_projection_idx", normalized_sql)
        self.assertIn("on app.bank_transactions", normalized_sql)
        self.assertIn("trade_time desc", normalized_sql)
        self.assertIn("include ( balance, currency, account_name, source_batch_id, legacy_source_batch_id, raw_payload )", normalized_sql)
        self.assertIn("bank_flow_rule_batch_rows_scope_source_versions_idx", normalized_sql)
        self.assertIn("on read_model.bank_flow_rule_batch_rows", normalized_sql)
        self.assertIn("include (source_versions)", normalized_sql)
        self.assertIn("where status <> 'superseded'", normalized_sql)

    def test_import_and_etc_list_hot_path_indexes_are_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0090_import_etc_list_hot_paths.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("import_files_uploaded_id_idx", normalized_sql)
        self.assertIn("on app.import_files (uploaded_at desc, id desc)", normalized_sql)
        self.assertIn("import_files_session_uploaded_id_idx", normalized_sql)
        self.assertIn("import_files_status_uploaded_id_idx", normalized_sql)
        self.assertIn("etc_invoices_issue_status_id_idx", normalized_sql)
        self.assertIn("include (status, batch_id, business_batch_id, file_path, raw_payload)", normalized_sql)
        self.assertIn("etc_invoices_status_issue_id_idx", normalized_sql)

    def test_import_file_ordering_hot_path_indexes_are_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0091_import_file_ordering_hot_path.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("import_files_uploaded_legacy_id_idx", normalized_sql)
        self.assertIn("coalesce(legacy_mongo_id, id::text)", normalized_sql)
        self.assertIn("on app.import_files (uploaded_at desc, (coalesce(legacy_mongo_id, id::text)) desc)", normalized_sql)
        self.assertIn("import_files_session_uploaded_legacy_id_idx", normalized_sql)
        self.assertIn("import_files_status_uploaded_legacy_id_idx", normalized_sql)

    def test_cost_statistics_parent_rollup_hot_path_index_is_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0092_cost_statistics_parent_rollup_hot_path.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("cost_statistics_rows_parent_rollup_idx", normalized_sql)
        self.assertIn("on read_model.cost_statistics_rows", normalized_sql)
        self.assertIn("project_scope", normalized_sql)
        self.assertIn("scope_month", normalized_sql)
        self.assertIn("trade_date desc nulls last", normalized_sql)
        self.assertIn("where scope_month is not null", normalized_sql)

    def test_workbench_relation_source_version_hot_path_indexes_are_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0093_workbench_relation_source_version_hot_paths.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        for required in (
            "workbench_pair_relations_scope_updated_idx",
            "workbench_pair_relations_updated_idx",
            "workbench_reconciliation_decisions_scope_updated_idx",
            "bank_transaction_relation_claims_active_scope_updated_idx",
            "bank_transactions_month_updated_idx",
            "invoices_month_updated_idx",
            "oa_applications_application_updated_idx",
        ):
            self.assertIn(required, normalized_sql)
        self.assertIn("where status = 'active'", normalized_sql)
        self.assertIn("where status <> 'deleted'", normalized_sql)
        self.assertIn("where application_date is not null", normalized_sql)

    def test_input_invoice_usage_oa_reverse_preview_hot_path_index_is_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0094_input_invoice_usage_oa_reverse_preview_hot_path.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("input_invoice_usage_rows_invoice_id_generated_idx", normalized_sql)
        self.assertIn("on read_model.input_invoice_usage_rows (invoice_id, generated_at desc)", normalized_sql)

    def test_oa_pending_payment_bank_relation_schema_and_migration_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists app.oa_pending_payment_bank_relations", sql)
        self.assertIn("create table if not exists app.bank_transaction_relation_claims", sql)
        self.assertIn("bank_transaction_relation_claims_active_bank_uidx", sql)
        self.assertIn("on app.bank_transaction_relation_claims (bank_transaction_id)", sql)
        self.assertIn("where status = 'active'", sql)
        self.assertIn("bank_transaction_relation_claims_active_oa_scope_bank_idx", sql)
        self.assertIn(
            "on app.bank_transaction_relation_claims ( scope_month, bank_transaction_id )",
            normalized_sql,
        )
        self.assertIn("owner_type = 'oa_pending_payment_relation'", sql)
        self.assertIn("oa_pending_payment_bank_relations_oa_gin", sql)
        self.assertIn("oa_pending_payment_bank_relations_bank_gin", sql)
        self.assertIn("special_metadata->>'origin' = 'oa_pending_payment_in_progress'", sql)
        self.assertIn("migrated_to_pending_relation_id", sql)
        self.assertIn("oa_pending_payment_in_progress_relation_migrated", sql)

    def test_oa_pending_payment_admission_runtime_role_can_replace_scopes(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists app.oa_pending_payment_admissions", normalized_sql)
        self.assertIn(
            "grant select, insert, update, delete on app.oa_pending_payment_admissions to fin_ops_app_runtime",
            normalized_sql,
        )

    def test_bank_flow_rule_batch_independent_storage_schema_and_backfill_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("create table if not exists app.bank_flow_rule_batches", sql)
        self.assertIn("create table if not exists app.bank_flow_rule_batch_events", sql)
        self.assertIn("create table if not exists read_model.bank_flow_rule_batch_rows", sql)
        self.assertIn("bank_flow_rule_batch_rows_filters_idx", sql)
        self.assertIn("bank_flow_rule_batch_rows_generated_idx", sql)
        self.assertIn("bank_flow_rule_batch_rows_source_versions_gin", sql)
        self.assertIn("from app.no_oa_bank_batches", sql)
        self.assertIn("from app.no_oa_bank_batch_events", sql)
        self.assertIn("from read_model.no_oa_bank_batch_rows", sql)
        self.assertIn("= 'bank_flow_rule_batch'", sql)
        self.assertIn("grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_app_runtime", sql)
        self.assertIn("grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_worker", sql)

    def test_bank_flow_rule_batch_tag_rules_settings_are_split_from_no_oa_settings(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("0083_bank_flow_rule_batch_tag_rules", sql)
        self.assertIn("update app.app_settings", sql)
        self.assertIn("'{bank_flow_rule_batch_tag_rules}'", sql)
        self.assertIn("settings_payload->'no_oa_bank_batch_tag_selection'", sql)
        self.assertIn("not (settings_payload ? 'bank_flow_rule_batch_tag_rules')", sql)

    def test_bank_flow_rule_batch_settings_raw_payload_is_aligned_without_changing_canonical_value(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0118_bank_flow_rule_batch_settings_raw_alignment.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(strip_sql_comments(sql).split())

        self.assertIn("update app.app_settings", normalized_sql)
        self.assertIn("'{normalized_payload}'", normalized_sql)
        self.assertIn("'{bank_flow_rule_batch_tag_rules}'", normalized_sql)
        self.assertIn(
            "raw_payload->'normalized_payload'->'bank_flow_rule_batch_tag_rules' is distinct from "
            "settings_payload->'bank_flow_rule_batch_tag_rules'",
            normalized_sql,
        )
        self.assertIn('"canonical_value_changed":false', normalized_sql)
        self.assertNotIn("settings_payload =", normalized_sql)

    def test_settings_access_control_guard_repairs_and_blocks_legacy_admin_writes(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0132_settings_access_control_guard.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(strip_sql_comments(sql).split())

        self.assertIn("update app.app_settings", normalized_sql)
        self.assertIn("insert into audit.events", normalized_sql)
        self.assertIn("settings.access_control.migrated", normalized_sql)
        self.assertIn("sha256", normalized_sql)
        self.assertIn("'{normalized_payload}'", normalized_sql)
        self.assertIn("access_control_version", normalized_sql)
        self.assertIn("admin_usernames", normalized_sql)
        self.assertIn("readonly_export_usernames", normalized_sql)
        self.assertIn("full_access_usernames", normalized_sql)
        self.assertIn("ynsylp005", normalized_sql)
        self.assertIn("add constraint app_settings_access_control_guard", normalized_sql)
        self.assertIn("not valid", normalized_sql)
        self.assertIn("validate constraint app_settings_access_control_guard", normalized_sql)
        self.assertNotIn("create table", normalized_sql)
        self.assertNotIn("job.outbox_events", normalized_sql)

    def test_settings_access_control_canonical_order_repairs_0132_append_bug(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0133_settings_access_control_canonical_order.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(strip_sql_comments(sql).split())

        self.assertIn("settings.access_control.canonical_order_repaired", normalized_sql)
        self.assertIn("migration:0133", normalized_sql)
        self.assertIn("'{normalized_payload}'", normalized_sql)
        self.assertIn(
            "'[\"ynsylp005\"]'::jsonb || (settings_payload->'full_access_usernames') "
            "|| (settings_payload->'readonly_export_usernames')",
            normalized_sql,
        )
        self.assertIn(
            "settings_payload->'allowed_usernames' = ( '[\"ynsylp005\"]'::jsonb "
            "|| (settings_payload->'full_access_usernames') "
            "|| (settings_payload->'readonly_export_usernames') )",
            normalized_sql,
        )
        self.assertIn(
            "validate constraint app_settings_access_control_canonical_order_guard",
            normalized_sql,
        )
        self.assertNotIn("create table", normalized_sql)
        self.assertNotIn("job.outbox_events", normalized_sql)

    def test_page_access_migration_drops_legacy_guards_before_rewriting_settings(self) -> None:
        sql = (
            MIGRATIONS_DIR / "0165_page_access_accounts.sql"
        ).read_text(encoding="utf-8").lower()
        normalized_sql = " ".join(strip_sql_comments(sql).split())

        update_position = normalized_sql.index("update app.app_settings as settings")
        self.assertLess(
            normalized_sql.index("drop constraint if exists app_settings_access_control_guard"),
            update_position,
        )
        self.assertLess(
            normalized_sql.index(
                "drop constraint if exists app_settings_access_control_canonical_order_guard"
            ),
            update_position,
        )
        self.assertGreater(
            normalized_sql.index("add constraint app_settings_page_access_accounts_guard"),
            update_position,
        )
        self.assertIn(
            "validate constraint app_settings_page_access_accounts_guard",
            normalized_sql,
        )

    def test_runtime_queue_history_retention_indexes_and_migrator_delete_grants_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("outbox_events_done_retention_idx", sql)
        self.assertIn("read_model_dirty_scopes_done_retention_idx", sql)
        self.assertIn("where status = 'done'", sql)
        self.assertIn("grant delete on job.outbox_events to fin_ops_migrator", normalized_sql)
        self.assertIn("grant delete on job.read_model_dirty_scopes to fin_ops_migrator", normalized_sql)
        self.assertNotIn("grant select, insert, update, delete on job.outbox_events to fin_ops_worker", normalized_sql)
        self.assertNotIn("grant select, insert, update, delete on job.outbox_events to fin_ops_api", normalized_sql)

    def test_pending_invoice_first_screen_sort_index_matches_query_order(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("pending_invoice_rows_direction_trade_date_nulls_last_idx", sql)
        self.assertIn(
            "on read_model.pending_invoice_rows ( direction, trade_date desc nulls last, row_id )",
            normalized_sql,
        )

    def test_discovery_rejects_invalid_filename(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            (path / "1_bad.sql").write_text("select 1;", encoding="utf-8")
            with self.assertRaises(migrate.MigrationError):
                migrate.discover_migrations(path)

    def test_plan_command_is_offline_when_database_url_is_absent(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            exit_code = migrate.main(["plan", "--migrations-dir", str(MIGRATIONS_DIR)], stdout=stdout, stderr=stderr)
        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn("0001 pending extensions_and_schemas", stdout.getvalue())
        self.assertIn("0007 pending grants", stdout.getvalue())
        self.assertIn("0008 pending pending_invoice_commands", stdout.getvalue())
        self.assertIn("0009 pending runtime_infrastructure", stdout.getvalue())
        self.assertIn("0010 pending runtime_phase2_cutover", stdout.getvalue())
        self.assertIn("0011 pending runtime_phase2_query_indexes", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_status_requires_database_url(self) -> None:
        stdout = StringIO()
        stderr = StringIO()
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "", "FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL": "", "FIN_OPS_POSTGRES_DATABASE_URL": ""},
        ):
            exit_code = migrate.main(["status", "--migrations-dir", str(MIGRATIONS_DIR)], stdout=stdout, stderr=stderr)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("PostgreSQL connection is required", stderr.getvalue())

    def test_database_url_can_use_migrator_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL": "postgresql://migrator:pw@127.0.0.1:5432/fin_ops",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://runtime:pw@127.0.0.1:5432/fin_ops",
            },
        ):
            self.assertEqual(
                migrate.database_url_from_env_or_arg(None),
                "postgresql://migrator:pw@127.0.0.1:5432/fin_ops",
            )

    def test_database_url_can_use_fin_ops_postgres_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "",
                "FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL": "",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://user:pw@127.0.0.1:5432/fin_ops",
            },
        ):
            self.assertEqual(
                migrate.database_url_from_env_or_arg(None),
                "postgresql://user:pw@127.0.0.1:5432/fin_ops",
            )

    def test_format_plan_reports_accepted_checksum_drift(self) -> None:
        migration = migrate.Migration(
            version="0004",
            name="oa_projection_sync",
            path=MIGRATIONS_DIR / "0004_oa_projection_sync.sql",
            checksum_sha256="4388a900905768f32354236d9fdc3f013395b1f3b23df62f7d7e23ec8493480d",
        )
        applied = {
            "0004": migrate.AppliedMigration(
                version="0004",
                name="oa_projection_sync",
                checksum_sha256="3f358b0a830f6de933c4b15f27987c83d1e2be076833585c574685b5121d65f3",
            )
        }

        self.assertEqual(
            migrate.format_plan([migration], applied),
            [
                "0004 accepted-checksum-drift oa_projection_sync "
                "4388a900905768f32354236d9fdc3f013395b1f3b23df62f7d7e23ec8493480d"
            ],
        )

    def test_apply_skips_exact_accepted_checksum_drift(self) -> None:
        migration = migrate.Migration(
            version="0004",
            name="oa_projection_sync",
            path=MIGRATIONS_DIR / "0004_oa_projection_sync.sql",
            checksum_sha256="4388a900905768f32354236d9fdc3f013395b1f3b23df62f7d7e23ec8493480d",
        )
        applied = {
            "0004": migrate.AppliedMigration(
                version="0004",
                name="oa_projection_sync",
                checksum_sha256="3f358b0a830f6de933c4b15f27987c83d1e2be076833585c574685b5121d65f3",
            )
        }
        stdout = StringIO()
        with patch("fin_ops_platform.postgres.migrate.assert_safe_target"), patch(
            "fin_ops_platform.postgres.migrate.ensure_metadata_table"
        ), patch("fin_ops_platform.postgres.migrate.fetch_applied_migrations", return_value=applied):
            migrate.apply_migrations("postgresql://user:pw@127.0.0.1:5432/fin_ops", [migration], stdout)

        self.assertIn("0004 skipped-accepted-checksum-drift oa_projection_sync", stdout.getvalue())

    def test_apply_checksum_mismatch_reports_applied_and_current_checksums(self) -> None:
        migration = migrate.Migration(
            version="0099",
            name="example",
            path=MIGRATIONS_DIR / "0077_workbench_relation_rows_scope_unique.sql",
            checksum_sha256="b" * 64,
        )
        applied = {
            "0099": migrate.AppliedMigration(
                version="0099",
                name="example",
                checksum_sha256="a" * 64,
            )
        }
        stdout = StringIO()

        with patch("fin_ops_platform.postgres.migrate.assert_safe_target"), patch(
            "fin_ops_platform.postgres.migrate.ensure_metadata_table"
        ), patch("fin_ops_platform.postgres.migrate.fetch_applied_migrations", return_value=applied):
            with self.assertRaises(migrate.MigrationError) as error:
                migrate.apply_migrations("postgresql://user:pw@127.0.0.1:5432/fin_ops", [migration], stdout)

        self.assertIn("Applied migration checksum mismatch: 0099 example", str(error.exception))
        self.assertIn("applied=" + "a" * 64, str(error.exception))
        self.assertIn("current=" + "b" * 64, str(error.exception))

    def test_ensure_metadata_table_does_not_require_create_when_table_exists(self) -> None:
        with patch("fin_ops_platform.postgres.migrate.run_psql", return_value="exists") as run_psql:
            migrate.ensure_metadata_table("postgresql://user:pw@127.0.0.1:5432/fin_ops")

        self.assertEqual(run_psql.call_count, 1)

    def test_redacts_database_url_password(self) -> None:
        password_value = "pw"
        database_url = "postgresql://user:" + password_value + "@127.0.0.1:5432/fin_ops?sslmode=disable"
        redacted = migrate.redact_database_url(database_url)
        self.assertEqual(redacted, "postgresql://" + "user:***@" + "127.0.0.1:5432/fin_ops")
        self.assertNotIn(password_value, redacted)

    def test_run_psql_does_not_put_database_url_in_argv(self) -> None:
        completed = Mock(returncode=0, stdout="ok\n", stderr="")
        with patch("fin_ops_platform.postgres.migrate.shutil.which", return_value="/usr/bin/psql"), patch(
            "fin_ops_platform.postgres.migrate.subprocess.run",
            return_value=completed,
        ) as run_mock:
            database_url = "postgresql://user:" + "pw" + "@127.0.0.1:5432/fin_ops"
            output = migrate.run_psql(database_url, sql="select 1;")
        self.assertEqual(output, "ok")
        command = run_mock.call_args.args[0]
        self.assertNotIn(database_url, command)
        env = run_mock.call_args.kwargs["env"]
        self.assertEqual(env["PGDATABASE"], "fin_ops")
        self.assertEqual(env["PGUSER"], "user")


class PostgresMigrationSqlTests(unittest.TestCase):
    def test_bank_transaction_weak_fingerprint_is_not_a_unique_identity(self) -> None:
        sql = (MIGRATIONS_DIR / "0140_bank_transaction_identity_strength.sql").read_text().lower()
        self.assertIn("drop index if exists app.bank_transactions_data_fingerprint_uidx", sql)
        self.assertIn("create index if not exists bank_transactions_data_fingerprint_idx", sql)
        self.assertNotIn("create unique index", sql)

    def test_sql_contains_required_schemas_and_tables(self) -> None:
        sql = migration_sql().lower()
        for schema in ("app", "read_model", "job", "audit", "staging"):
            self.assertIn(f"create schema if not exists {schema}", sql)
        for table in EXPECTED_TABLES:
            self.assertIn(f"create table if not exists {table}", sql)

    def test_read_model_runtime_is_removed_by_latest_forward_migration(self) -> None:
        sql = (MIGRATIONS_DIR / "0149_remove_read_model_runtime.sql").read_text().lower()
        self.assertIn("drop schema if exists read_model cascade", sql)
        self.assertIn("drop table if exists job.read_model_dirty_scopes cascade", sql)
        self.assertIn("drop column if exists read_model_scope_key", sql)
        self.assertIn("where event_type like '%.read_model.refresh'", sql)

    def test_sql_has_required_extensions_and_indexes(self) -> None:
        sql = migration_sql().lower()
        for extension in ("pgcrypto", "pg_trgm", "btree_gin"):
            self.assertIn(f"create extension if not exists {extension}", sql)
        for required in (
            "gin_trgm_ops",
            "using gin (row_ids)",
            "invoices_source_unique_key_uidx",
            "bank_transactions_data_fingerprint_uidx",
            "oa_applications",
            "schema_migrations",
            "outbox_events_dedupe_uidx",
            "read_model_dirty_scopes_active_uidx",
            "runtime_worker_heartbeats_worker_uidx",
            "job.sync_outbox_event_attempts()",
            "outbox_events_sync_attempts_trg",
            "outbox_events_status_chk",
            "outbox_events_priority_chk",
            "outbox_events_schema_version_chk",
            "outbox_events_max_attempts_chk",
            "read_model_dirty_scopes_priority_chk",
            "outbox_events_claim_priority_idx",
            "outbox_events_claim_event_type_priority_idx",
            "outbox_events_trace_idx",
            "runtime_outbox_envelope_v1",
            "publish_status text not null default 'unpublished'",
            "publish_attempt_count integer not null default 0",
            "next_publish_at timestamptz not null default now()",
            "outbox_events_publish_status_chk",
            "outbox_events_publish_claim_idx",
            "outbox_events_publish_lock_idx",
            "outbox_events_rabbitmq_message_idx",
            "drop view if exists job.runtime_outbox_envelope_v1",
            "schema_version integer not null default 1",
            "source_version bigint",
            "priority text not null default 'normal'",
            "trace_id text",
            "dead_lettered_at timestamptz",
            "where dedupe_key is not null and status = 'pending'",
            "file_objects_migration_status_chk",
            "file_objects_storage_backend_chk",
            "file_objects_migration_status_idx",
            "file_objects_verified_storage_idx",
            "file_objects_legacy_gridfs_idx",
            "invoices_legacy_source_batch_idx",
            "invoices_created_id_idx",
            "bank_transactions_legacy_source_batch_idx",
            "bank_transactions_created_id_idx",
            "import_files_status_uploaded_idx",
            "workbench_pair_relations_scope_updated_idx",
            "workbench_reconciliation_decisions_scope_updated_idx",
            "bank_transaction_relation_claims_active_scope_updated_idx",
            "bank_transactions_month_updated_idx",
            "invoices_month_updated_idx",
            "oa_applications_application_updated_idx",
            "read_model_dirty_scopes_workbench_latest_version_idx",
            "read_model_dirty_scopes_bank_detail_latest_version_idx",
            "workbench_exception_cases_scope_updated_idx",
            "workbench_row_overrides_scope_updated_idx",
            "temporary_object_key",
            "source_storage_uri",
            "verified_at",
            "tombstoned_at",
            "grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker",
            "grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_worker",
            "grant select, insert, update, delete on read_model.workbench_groups to fin_ops_worker",
            "grant select, insert, update, delete on read_model.workbench_groups to fin_ops_migrator",
            "grant select, insert, update, delete on read_model.workbench_group_rows to fin_ops_worker",
            "grant select, insert, update, delete on read_model.workbench_group_rows to fin_ops_migrator",
            "grant select, insert, update, delete on read_model.input_invoice_usage_rows to fin_ops_app_runtime",
            "grant select, insert, update, delete on read_model.output_invoice_collection_rows to fin_ops_app_runtime",
            "grant select, insert, update, delete on read_model.oa_pending_payment_rows to fin_ops_app_runtime",
            "grant select, insert, update, delete on read_model.workbench_reconciliation_decisions to fin_ops_app_runtime",
            "grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_app_runtime",
            "grant select, insert, update on app.matching_runs to fin_ops_app_runtime",
            "grant select, insert, update, delete on app.etc_batch_invoice_links to fin_ops_app_runtime",
            "create extension if not exists pg_stat_statements",
            "create table if not exists read_model.workbench_summary",
            "workbench_summary_scope_key_uidx",
            "workbench_summary_scope_month_idx",
            "workbench_summary_source_version_idx",
            "on read_model.workbench_summary (((source_versions->>'source_version')::bigint))",
            "grant select on read_model.workbench_summary to fin_ops_api",
            "grant select, insert, update, delete on read_model.workbench_summary to fin_ops_worker",
            "grant select on read_model.workbench_summary to fin_ops_readonly",
            "grant select, insert, update, delete on read_model.workbench_summary to fin_ops_migrator",
            "create table if not exists read_model.workbench_generations",
            "workbench_generations_status_check",
            "workbench_generations_consistency_status_check",
            "create or replace view read_model.workbench_generation_consistency",
            "create table if not exists read_model.workbench_generation_stats",
            "workbench_generation_stats_scope_zone_status_uidx",
            "workbench_generations_build_batch_idx",
            "workbench_generations_consistency_status_idx",
            "add column if not exists generation_id text",
            "workbench_generations_active_scope_uidx",
            "workbench_snapshots_generation_scope_uidx",
            "workbench_summary_generation_scope_uidx",
            "workbench_rows_generation_scope_row_uidx",
            "workbench_groups_generation_scope_zone_group_uidx",
            "workbench_group_rows_generation_scope_zone_group_pane_role_row_uidx",
            "grant select on read_model.workbench_generations to fin_ops_api",
            "workbench_reconciliation_decisions_tenant_key_uidx",
            "workbench_reconciliation_decisions_scope_status_idx",
            "workbench_reconciliation_decisions_row_ids_gin",
            "workbench_matching_dirty_scopes_claim_idx",
            "matching_runs_tenant_request_id_uidx",
            "workbench_pair_relations_active_etc_external_batch_idx",
            "bank_detail_rows_transaction_uidx",
            "bank_detail_rows_month_time_idx",
            "bank_detail_rows_month_account_time_idx",
            "bank_detail_rows_category_idx",
            "bank_detail_rows_search_trgm",
            "bank_detail_scopes_tenant_scope_uidx",
            "bank_detail_scopes_status_idx",
            "grant select on read_model.bank_detail_rows to fin_ops_api",
            "grant select on read_model.bank_detail_scopes to fin_ops_api",
            "grant select, insert, update, delete on read_model.bank_detail_rows to fin_ops_worker",
            "grant select, insert, update, delete on read_model.bank_detail_scopes to fin_ops_worker",
            "grant select, insert, update, delete on read_model.bank_detail_rows to fin_ops_app_runtime",
            "grant select, insert, update, delete on read_model.bank_detail_scopes to fin_ops_app_runtime",
            "oa_applicant_credentials_target_uidx",
            "encrypted_password bytea",
            "grant select, insert, update, delete on app.oa_applicant_credentials to fin_ops_app_runtime",
        ):
            self.assertIn(required, sql)
        normalized_sql = " ".join(sql.split())
        self.assertIn("on job.outbox_events ( event_type, status,", normalized_sql)
        self.assertIn("case priority when 'urgent' then 3", normalized_sql)
        self.assertIn("where status in ('pending', 'processing')", normalized_sql)

    def test_runtime_queue_claim_hot_path_index_is_declared(self) -> None:
        sql = (MIGRATIONS_DIR / "0086_runtime_queue_claim_hot_path.sql").read_text().lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create index if not exists outbox_events_claim_event_type_priority_idx", normalized_sql)
        self.assertIn("on job.outbox_events ( event_type, status,", normalized_sql)
        self.assertIn("case priority when 'urgent' then 3", normalized_sql)
        self.assertIn("when 'high' then 2", normalized_sql)
        self.assertIn("when 'normal' then 1", normalized_sql)
        self.assertIn("available_at, created_at, id", normalized_sql)
        self.assertIn("where status in ('pending', 'processing')", normalized_sql)

    def test_oa_applicant_credentials_schema_uses_encrypted_password_only(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        body = re.search(
            r"create table if not exists app\.oa_applicant_credentials\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(body)
        table_body = body.group(1)
        for required in (
            "target_applicant_code text not null",
            "target_applicant_name text not null",
            "oa_username text not null",
            "encrypted_password bytea",
            "credential_status text not null default 'unconfigured'",
            "enabled boolean not null default true",
            "updated_by text not null default ''",
            "raw_payload jsonb not null default '{}'::jsonb",
        ):
            self.assertIn(required, table_body)
        self.assertNotRegex(table_body, r"\bpassword\s+text\b")
        self.assertIn("credential_status in ('configured', 'unconfigured')", sql)
        self.assertIn("credential_status <> 'configured' or encrypted_password is not null", sql)

    def test_bank_detail_read_model_schema_is_native_sql_projection(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        rows_body = re.search(
            r"create table if not exists read_model\.bank_detail_rows\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        scopes_body = re.search(
            r"create table if not exists read_model\.bank_detail_scopes\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(rows_body)
        self.assertIsNotNone(scopes_body)
        for required in (
            "transaction_id text not null",
            "scope_key text not null",
            "scope_month date not null",
            "account_key text not null",
            "trade_time_sort timestamptz not null",
            "effective_category_code text",
            "oa_relation_tag text",
            "invoice_relation_tag text",
            "relation_tags text[] not null default '{}'::text[]",
            "search_text text not null default ''",
            "schema_version integer not null",
            "source_versions jsonb not null default '{}'::jsonb",
            "payload jsonb not null default '{}'::jsonb",
            "raw_payload jsonb not null default '{}'::jsonb",
        ):
            self.assertIn(required, rows_body.group(1))
        for required in (
            "tenant_id text not null default 'default'",
            "scope_type text not null default 'bank_detail'",
            "scope_key text not null",
            "schema_version integer not null",
            "status text not null default 'fresh'",
            "row_count integer not null default 0",
            "source_version bigint",
            "generated_at timestamptz",
            "last_error text",
        ):
            self.assertIn(required, scopes_body.group(1))
        self.assertIn("status in ('fresh', 'pending', 'processing', 'stale', 'failed')", sql)

    def test_workbench_reconciliation_decision_and_dirty_queue_schema(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        decision_body = re.search(
            r"create table if not exists read_model\.workbench_reconciliation_decisions\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(decision_body)
        body = decision_body.group(1)
        for required in (
            "tenant_id text not null default 'default'",
            "scope_month date not null",
            "decision_key text not null",
            "display_state text not null",
            "decision_status text not null",
            "match_domain text not null",
            "match_shape text not null",
            "rule_code text not null",
            "rule_version text not null",
            "row_ids text[] not null default '{}'::text[]",
            "oa_row_ids text[] not null default '{}'::text[]",
            "bank_row_ids text[] not null default '{}'::text[]",
            "invoice_row_ids text[] not null default '{}'::text[]",
            "source_versions jsonb not null default '{}'::jsonb",
            "raw_payload jsonb not null default '{}'::jsonb",
            "consumed_by_relation_id text",
            "suppressed_by_exception_case_id text",
        ):
            self.assertIn(required, body)
        self.assertIn("decision_status in ('proposed', 'paired', 'open', 'suppressed', 'consumed', 'expired')", sql)
        self.assertIn("match_domain in ('free', 'special')", sql)
        self.assertIn("display_state in ('paired', 'open')", sql)

    def test_bank_transaction_category_confirmation_schema(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        body = re.search(
            r"create table if not exists app\.bank_transaction_category_confirmations\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(body)
        table_body = body.group(1)
        for required in (
            "tenant_id text not null default 'default'",
            "category_code text not null",
            "candidate_category_codes jsonb not null default '[]'::jsonb",
            "rule_version text not null default ''",
            "status text not null default 'active'",
            "version integer not null default 1",
            "confirmed_by text not null default ''",
            "confirmed_at timestamptz not null default now()",
            "revoked_by text null",
            "revoked_at timestamptz null",
            "raw_payload jsonb not null default '{}'::jsonb",
        ):
            self.assertIn(required, table_body)
        self.assertIn("status in ('active', 'revoked')", sql)
        self.assertIn(
            "on app.bank_transaction_category_confirmations(tenant_id, legacy_transaction_id)",
            sql,
        )

        dirty_body = re.search(
            r"create table if not exists job\.workbench_matching_dirty_scopes\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(dirty_body)
        full_sql = sql
        for required in (
            "add column if not exists tenant_id text not null default 'default'",
            "add column if not exists lease_owner text",
            "add column if not exists lease_expires_at timestamptz",
            "add column if not exists source_versions jsonb not null default '{}'::jsonb",
            "add column if not exists request_id text",
            "add column if not exists tenant_id text not null default 'default'",
            "add column if not exists started_at timestamptz",
            "add column if not exists completed_at timestamptz",
            "add column if not exists failed_at timestamptz",
            "add column if not exists duration_ms integer",
            "add column if not exists error_summary text",
        ):
            self.assertIn(required, full_sql)

    def test_workbench_idempotency_records_schema_contract(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        body = re.search(
            r"create table if not exists app\.workbench_idempotency_records\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(body)
        table_body = body.group(1)
        for required in (
            "id uuid primary key default gen_random_uuid()",
            "tenant_id text not null default 'default'",
            "actor_id text not null",
            "action_name text not null",
            "idempotency_key text not null",
            "request_fingerprint text not null",
            "status text not null default 'reserved'",
            "request_payload jsonb not null default '{}'::jsonb",
            "response_payload jsonb not null default '{}'::jsonb",
            "source_versions jsonb not null default '{}'::jsonb",
            "outbox_event_ids jsonb not null default '[]'::jsonb",
            "trace_id text",
            "reserved_at timestamptz not null default now()",
            "completed_at timestamptz",
            "expires_at timestamptz",
            "last_error text",
            "created_at timestamptz not null default now()",
            "updated_at timestamptz not null default now()",
            "constraint workbench_idempotency_status_chk",
            "status in ('reserved', 'committed', 'failed')",
            "constraint workbench_idempotency_fingerprint_chk",
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
        ):
            self.assertIn(required, table_body)

        for required in (
            "create unique index if not exists workbench_idempotency_identity_uidx",
            "on app.workbench_idempotency_records (tenant_id, actor_id, idempotency_key)",
            "create index if not exists workbench_idempotency_action_status_idx",
            "on app.workbench_idempotency_records (tenant_id, action_name, status, created_at desc)",
            "create index if not exists workbench_idempotency_expires_idx",
            "on app.workbench_idempotency_records (expires_at)",
            "where expires_at is not null",
            "create index if not exists workbench_idempotency_committed_idx",
            "on app.workbench_idempotency_records (tenant_id, actor_id, completed_at desc)",
            "where status = 'committed'",
            "grant select, insert, update on app.workbench_idempotency_records to fin_ops_api",
            "grant select on app.workbench_idempotency_records to fin_ops_worker",
            "grant select on app.workbench_idempotency_records to fin_ops_readonly",
            "grant select, insert, update on app.workbench_idempotency_records to fin_ops_migrator",
        ):
            self.assertIn(required, sql)

        self.assertNotIn(
            "on app.workbench_idempotency_records (tenant_id, action_name, idempotency_key)",
            sql,
        )

    def test_output_invoice_receipt_numbering_schema_contract(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        counters = re.search(
            r"create table if not exists app\.output_invoice_receipt_number_counters\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        receipts = re.search(
            r"create table if not exists app\.output_invoice_receipts\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(counters)
        self.assertIsNotNone(receipts)

        counters_body = counters.group(1)
        for required in (
            "tenant_id text not null default 'default'",
            "prefix text not null",
            "period_key text not null",
            "next_sequence integer not null default 1",
        ):
            self.assertIn(required, counters_body)

        receipts_body = receipts.group(1)
        for required in (
            "tenant_id text not null default 'default'",
            "receipt_no text not null",
            "idempotency_key text not null",
            "constraint output_invoice_receipts_status_chk",
            "status in ('issued', 'voided', 'reissued')",
        ):
            self.assertIn(required, receipts_body)

        for required in (
            "create unique index if not exists output_invoice_receipt_number_counters_scope_uidx",
            "on app.output_invoice_receipt_number_counters(tenant_id, prefix, period_key)",
            "create unique index if not exists output_invoice_receipts_receipt_no_uidx",
            "on app.output_invoice_receipts(tenant_id, receipt_no)",
            "create unique index if not exists output_invoice_receipts_idempotency_uidx",
            "on app.output_invoice_receipts(tenant_id, idempotency_key)",
        ):
            self.assertIn(required, sql)

    def test_sql_does_not_contain_forbidden_operations_or_secrets(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        relation_unification_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0136_unify_in_progress_oa_workbench_relations.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(relation_unification_sql, sql)
        sql = sql.replace(
            relation_unification_sql,
            "approved_oa_pending_relation_unification;",
        )
        sql = re.sub(r"\binsert\s+into\s+app\.oa_attachment_invoice_cache_sources\b", "insert into allowed_lookup_backfill", sql)
        for table_name in (
            "oa_pending_payment_bank_relations",
            "bank_transaction_relation_claims",
            "oa_pending_payment_bank_relation_events",
            "workbench_pair_relation_history",
            "bank_flow_rule_batches",
            "bank_flow_rule_batch_events",
        ):
            sql = re.sub(
                rf"\binsert\s+into\s+app\.{table_name}\b",
                f"insert into allowed_0073_{table_name}",
                sql,
            )
        sql = re.sub(
            r"\binsert\s+into\s+read_model\.bank_flow_rule_batch_rows\b",
            "insert into allowed_0082_bank_flow_rule_batch_rows",
            sql,
        )
        sql = re.sub(
            r"\binsert\s+into\s+read_model\.workbench_generations\s*\(.*?on\s+conflict\s*\(generation_id\)\s+do\s+nothing;",
            "insert into allowed_workbench_generation_backfill",
            sql,
            flags=re.S,
        )
        sql = re.sub(
            r"\binsert\s+into\s+app\.etc_reconciliation_tasks\s*\(.*?on\s+conflict\s*\(task_id\)\s+do\s+nothing;",
            "insert into allowed_phase19_etc_reconciliation_task_repair",
            sql,
            flags=re.S,
        )
        sql = re.sub(
            r"\bdelete\s+from\s+read_model\.workbench_relation_rows\s+target\s+using\s*\(\s*select\s+id,\s+row_number\(\)\s+over\s*\(\s*partition\s+by\s+tenant_id,\s+scope_key,\s+row_id\s+order\s+by\s+generated_at\s+desc,\s+updated_at\s+desc,\s+created_at\s+desc,\s+id\s+desc\s*\)\s+as\s+row_rank\s+from\s+read_model\.workbench_relation_rows\s*\)\s+ranked\s+where\s+target\.id\s+=\s+ranked\.id\s+and\s+ranked\.row_rank\s+>\s+1;",
            "allowed_workbench_relation_rows_dedupe",
            sql,
            flags=re.S,
        )
        approved_retirement_patterns = (
            r"update\s+job\.outbox_events\s+set\s+status\s*=\s*'done'.*?"
            r"where\s+event_type\s*=\s*'cost_statistics\.read_model\.refresh'.*?;",
            r"update\s+job\.read_model_dirty_scopes\s+set\s+status\s*=\s*'done'.*?"
            r"where\s+scope_type\s*=\s*'cost_statistics'.*?;",
            r"delete\s+from\s+read_model\.app_status_readiness\s+"
            r"where\s+read_model_key\s*=\s*'cost_statistics'.*?;",
        )
        checked_sql = sql
        for pattern in approved_retirement_patterns:
            self.assertIsNotNone(
                re.search(pattern, checked_sql, flags=re.S),
                pattern,
            )
            checked_sql = re.sub(
                pattern,
                "approved_cost_statistics_runtime_retirement;",
                checked_sql,
                flags=re.S,
            )
        direct_canonical_retirement_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0127_direct_canonical_page_runtime_retirement.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(direct_canonical_retirement_sql, checked_sql)
        checked_sql = checked_sql.replace(
            direct_canonical_retirement_sql,
            "approved_direct_canonical_page_runtime_retirement;",
        )
        settings_acl_guard_sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0132_settings_access_control_guard.sql").read_text(encoding="utf-8")
        ).lower()
        self.assertIn(settings_acl_guard_sql, checked_sql)
        checked_sql = checked_sql.replace(
            settings_acl_guard_sql,
            "approved_settings_access_control_guard;",
        )
        settings_acl_canonical_order_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0133_settings_access_control_canonical_order.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(settings_acl_canonical_order_sql, checked_sql)
        checked_sql = checked_sql.replace(
            settings_acl_canonical_order_sql,
            "approved_settings_access_control_canonical_order;",
        )
        invoice_provenance_repair_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0134_restore_invoice_import_provenance.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(invoice_provenance_repair_sql, checked_sql)
        checked_sql = checked_sql.replace(
            invoice_provenance_repair_sql,
            "approved_invoice_import_provenance_repair;",
        )
        operation_audit_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0138_operation_audit_and_financial_fact_guard.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(operation_audit_sql, checked_sql)
        checked_sql = checked_sql.replace(
            operation_audit_sql,
            "approved_operation_audit_and_financial_fact_guard;",
        )
        idempotency_reliability_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0139_idempotency_and_worker_attempt_history.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(idempotency_reliability_sql, checked_sql)
        checked_sql = checked_sql.replace(
            idempotency_reliability_sql,
            "approved_idempotency_and_worker_attempt_history;",
        )
        bank_requirement_recalculation_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0145_bank_relation_requirement_recalculation.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(bank_requirement_recalculation_sql, checked_sql)
        checked_sql = checked_sql.replace(
            bank_requirement_recalculation_sql,
            "approved_bank_relation_requirement_recalculation;",
        )
        bank_requirement_rollout_retry_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0146_bank_relation_requirement_rollout_retry.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(bank_requirement_rollout_retry_sql, checked_sql)
        checked_sql = checked_sql.replace(
            bank_requirement_rollout_retry_sql,
            "approved_bank_relation_requirement_rollout_retry;",
        )
        bank_requirement_scope_retry_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0147_bank_relation_requirement_scope_retry.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(bank_requirement_scope_retry_sql, checked_sql)
        checked_sql = checked_sql.replace(
            bank_requirement_scope_retry_sql,
            "approved_bank_relation_requirement_scope_retry;",
        )
        retired_matching_progress_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0148_retire_workbench_matching_progress_jobs.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(retired_matching_progress_sql, checked_sql)
        checked_sql = checked_sql.replace(
            retired_matching_progress_sql,
            "approved_retired_matching_progress_jobs;",
        )
        read_model_removal_sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0149_remove_read_model_runtime.sql").read_text(encoding="utf-8")
        ).lower()
        self.assertIn(read_model_removal_sql, checked_sql)
        checked_sql = checked_sql.replace(
            read_model_removal_sql,
            "approved_read_model_runtime_removal;",
        )
        oa_source_alias_attachment_repair_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0153_oa_source_alias_attachment_identity_repair.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(oa_source_alias_attachment_repair_sql, checked_sql)
        checked_sql = checked_sql.replace(
            oa_source_alias_attachment_repair_sql,
            "approved_oa_source_alias_attachment_identity_repair;",
        )
        etc_summary_anomaly_review_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0154_migrate_etc_summary_anomaly_review.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(etc_summary_anomaly_review_sql, checked_sql)
        checked_sql = checked_sql.replace(
            etc_summary_anomaly_review_sql,
            "approved_etc_summary_anomaly_review_migration;",
        )
        etc_summary_anomaly_revalidation_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0155_revalidate_etc_summary_anomaly_review.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(etc_summary_anomaly_revalidation_sql, checked_sql)
        checked_sql = checked_sql.replace(
            etc_summary_anomaly_revalidation_sql,
            "approved_etc_summary_anomaly_review_revalidation;",
        )
        anomaly_reviewer_identity_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0156_backfill_workbench_anomaly_reviewer_identity.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(anomaly_reviewer_identity_sql, checked_sql)
        checked_sql = checked_sql.replace(
            anomaly_reviewer_identity_sql,
            "approved_anomaly_reviewer_identity_backfill;",
        )
        oa_payment_status_reconcile_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0158_oa_payment_status_auto_reconcile.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(oa_payment_status_reconcile_sql, checked_sql)
        checked_sql = checked_sql.replace(
            oa_payment_status_reconcile_sql,
            "approved_oa_payment_status_reconcile_backfill;",
        )
        oa_payment_status_rule_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0160_remove_oa_payment_status_writeback_ownership.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(oa_payment_status_rule_sql, checked_sql)
        checked_sql = checked_sql.replace(
            oa_payment_status_rule_sql,
            "approved_oa_payment_status_rule_migration;",
        )
        formal_bank_relation_convergence_sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0161_converge_formal_bank_relation_requirements.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        self.assertIn(formal_bank_relation_convergence_sql, checked_sql)
        checked_sql = checked_sql.replace(
            formal_bank_relation_convergence_sql,
            "approved_formal_bank_relation_requirement_convergence;",
        )
        approved_legacy_drops = (
            "drop table if exists read_model.cost_statistics_bank_flow_rows;",
            "drop table if exists read_model.cost_statistics_rows;",
            "drop table if exists read_model.cost_statistics_read_models;",
        )
        for approved_drop in approved_legacy_drops:
            self.assertIn(approved_drop, checked_sql)
            checked_sql = checked_sql.replace(approved_drop, "")
        forbidden_patterns = [
            r"\bdrop\s+(database|schema|table)\b",
            r"\btruncate\b",
            r"\bdelete\s+from\b",
            r"\balter\s+system\b",
            r"\bcopy\s+.*\bprogram\b",
            r"\\copy\b",
            r"\\!",
            r"\bcreate\s+(database|user|role)\b",
            r"\binsert\s+into\s+(app|read_model|job|audit|staging)\.",
            r"\b(double\s+precision|real|float[48]?|money)\b",
            r"\bcreate\s+index\s+concurrently\b",
            r"\bencrypted\s+password\b",
            r"\bpassword\s*=",
            r"mongodb://[^`\s]+@",
            r"postgres(ql)?://[^`\s]+@",
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, checked_sql), pattern)

    def test_bank_relation_requirement_recalculation_is_bounded_and_idempotent(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0145_bank_relation_requirement_recalculation.sql"
            ).read_text(encoding="utf-8")
        ).lower()

        self.assertIn("using gin ((special_metadata -> 'paired_requirement_tag_codes'))", sql)
        self.assertIn("where status = 'active'", sql)
        self.assertIn("insert into job.background_jobs", sql)
        self.assertIn("insert into job.outbox_events", sql)
        self.assertIn(
            "settings.bank_relation_requirements.recalculate.requested",
            sql,
        )
        self.assertIn("on conflict (job_id) do nothing", sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("update app.workbench_pair_relations", sql)

    def test_bank_relation_requirement_rollout_retry_only_replaces_failed_job(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0146_bank_relation_requirement_rollout_retry.sql"
            ).read_text(encoding="utf-8")
        ).lower()

        self.assertIn("old_job.status = 'failed'", sql)
        self.assertIn("rollout-v2-", sql)
        self.assertIn("supersedes_job_id", sql)
        self.assertIn("insert into job.background_jobs", sql)
        self.assertIn("insert into job.outbox_events", sql)
        self.assertIn("on conflict (job_id) do nothing", sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("update app.workbench_pair_relations", sql)

    def test_bank_relation_requirement_scope_retry_only_replaces_failed_v2_job(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0147_bank_relation_requirement_scope_retry.sql"
            ).read_text(encoding="utf-8")
        ).lower()

        self.assertIn("old_job.status = 'failed'", sql)
        self.assertIn("rollout-v3-", sql)
        self.assertIn("rollout-v2-", sql)
        self.assertIn("supersedes_job_id", sql)
        self.assertIn("insert into job.background_jobs", sql)
        self.assertIn("insert into job.outbox_events", sql)
        self.assertIn("on conflict (job_id) do nothing", sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("update app.workbench_pair_relations", sql)

    def test_formal_bank_relation_requirement_convergence_is_worker_owned_and_idempotent(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0161_converge_formal_bank_relation_requirements.sql"
            ).read_text(encoding="utf-8")
        ).lower()

        self.assertIn("bank_relation_requirement_recalculation", sql)
        self.assertIn("formal_relation_mode_convergence", sql)
        self.assertIn("settings.bank_relation_requirements.recalculate.requested", sql)
        self.assertIn("active_job.status in ('queued', 'running')", sql)
        self.assertIn("on conflict (job_id) do nothing", sql)
        self.assertIn("on conflict (tenant_id, dedupe_key)", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("update app.workbench_pair_relations", sql)

    def test_retired_workbench_matching_progress_jobs_only_reach_terminal_status(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0148_retire_workbench_matching_progress_jobs.sql"
            ).read_text(encoding="utf-8")
        ).lower()

        self.assertIn("job_type = 'workbench_matching'", sql)
        self.assertIn("status in ('queued', 'running')", sql)
        self.assertIn("status = 'superseded'", sql)
        self.assertIn("for update", sql)
        self.assertNotIn("delete from", sql)
        self.assertNotIn("drop table", sql)

    def test_oa_attachment_invoice_cache_sources_is_indexed_lookup_table(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        body = re.search(
            r"create table if not exists app\.oa_attachment_invoice_cache_sources\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(body)
        table_body = body.group(1)
        self.assertIn("cache_source_attachment_key text not null references app.oa_attachment_invoice_cache(source_attachment_key) on delete cascade", table_body)
        self.assertIn("source_attachment_key text not null", table_body)
        self.assertIn("primary key (cache_source_attachment_key, source_attachment_key, source_kind)", table_body)
        self.assertIn("oa_attachment_invoice_cache_sources_source_idx", sql)
        self.assertIn("oa_attachment_invoice_cache_sources_cache_idx", sql)
        self.assertIn("oa_attachment_invoice_cache_sources_identity_context_idx", sql)
        self.assertIn("oa_attachments_source_identity_idx", sql)
        self.assertIn("deduped_sources as", sql)
        self.assertIn("attachment_identity_invoice", sql)
        self.assertIn("attachment_identity_evidence", sql)
        self.assertIn("attachment_identity_artifact", sql)

    def test_core_tables_keep_legacy_or_external_identity_and_raw_payload(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        for table in EXPECTED_TABLES:
            pattern = rf"create table if not exists {re.escape(table)}\s*\((.*?)\);"
            match = re.search(pattern, sql, flags=re.S)
            self.assertIsNotNone(match, table)
            body = match.group(1)
            if table in {
                "audit.external_control_evidence",
                "audit.external_control_evidence_items",
                "app.financial_fact_corrections",
                "job.runtime_event_attempts",
            }:
                continue
            self.assertIn("id uuid primary key default gen_random_uuid()", body, table)
            if table == "app.workbench_idempotency_records":
                continue
            self.assertIn("raw_payload jsonb not null default '{}'::jsonb", body, table)
        for table in (
            "app.invoices",
            "app.bank_transactions",
            "app.workbench_pair_relations",
            "app.no_oa_bank_batches",
            "app.tax_certified_import_records",
        ):
            body = re.search(rf"create table if not exists {re.escape(table)}\s*\((.*?)\);", sql, flags=re.S).group(1)
            self.assertRegex(body, r"legacy_(mongo|source)_id|legacy_.*_id", table)
        oa_body = re.search(r"create table if not exists app\.oa_applications\s*\((.*?)\);", sql, flags=re.S).group(1)
        for column in ("oa_source_id", "form_id", "row_id"):
            self.assertIn(column, oa_body)
        self.assertIn("alter table app.oa_applications", sql)
        self.assertIn("add column if not exists scope_month date", sql)
        self.assertIn("add column if not exists workflow_status text", sql)
        self.assertIn("oa_applications_scope_month_row_idx", sql)
        self.assertIn("oa_applications_workflow_status_scope_idx", sql)
        self.assertIn("oa_pending_payment_rows_oa_id_idx", sql)
        self.assertIn("add column if not exists oa_workflow_status text", sql)
        self.assertIn("oa_pending_payment_rows_workflow_scope_idx", sql)
        self.assertIn("oa_pending_payment_rows_bank_transaction_id_idx", sql)
        self.assertIn("oa_pending_payment_rows_invoice_id_idx", sql)

    def test_external_control_evidence_is_immutable_itemized_and_explicitly_granted(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        header = re.search(
            r"create table if not exists audit\.external_control_evidence\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        items = re.search(
            r"create table if not exists audit\.external_control_evidence_items\s*\((.*?)\);",
            sql,
            flags=re.S,
        )
        self.assertIsNotNone(header)
        self.assertIsNotNone(items)
        self.assertIn("coverage_mode text not null check (coverage_mode = 'complete_snapshot')", header.group(1))
        self.assertIn("scope_key text not null check (scope_key = 'all')", header.group(1))
        self.assertIn("unique (tenant_id, domain, manifest_fingerprint)", header.group(1))
        self.assertIn("primary key (evidence_id, item_kind, item_key)", items.group(1))
        self.assertNotIn("delete on audit.external_control_evidence", sql)
        self.assertIn(
            "grant select on audit.external_control_evidence, audit.external_control_evidence_items to fin_ops_api",
            sql,
        )
        self.assertNotIn("insert, update on audit.external_control_evidence to fin_ops_api", sql)
        self.assertIn("grant select, insert, update on audit.external_control_evidence to fin_ops_migrator", sql)

    def test_phase19_new_tables_have_complete_runtime_role_grants(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0100_phase19_runtime_grants.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        for role in ("fin_ops_app_runtime", "fin_ops_api", "fin_ops_migrator"):
            self.assertIn(
                f"grant select, insert, update, delete on app.etc_import_session_files to {role}",
                normalized_sql,
            )
        for role in ("fin_ops_worker", "fin_ops_readonly"):
            self.assertIn(
                f"grant select on app.etc_import_session_files to {role}",
                normalized_sql,
            )
        self.assertIn(
            "grant select on audit.external_control_evidence, audit.external_control_evidence_items "
            "to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertNotRegex(
            normalized_sql,
            r"grant [^;]*(?:insert|update|delete)[^;]* on audit\.external_control_evidence",
        )

    def test_phase19_audit_contract_migration_versions_future_imports_without_backfill(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0101_phase19_audit_contract_boundaries.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("alter table app.import_files add column if not exists audit_contract_revision text", normalized_sql)
        self.assertIn(
            "alter table app.import_files alter column audit_contract_revision set default 'import-page-audit.v1'",
            normalized_sql,
        )
        self.assertIn("alter table app.etc_import_sessions add column if not exists audit_contract_revision text", normalized_sql)
        self.assertIn(
            "alter table app.etc_import_sessions alter column audit_contract_revision set default 'etc-import-page-audit.v1'",
            normalized_sql,
        )
        self.assertNotRegex(normalized_sql, r"update app\.(?:import_files|etc_import_sessions)\s+set audit_contract_revision")

    def test_phase19_audit_contract_migration_repairs_only_deterministic_internal_facts(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0101_phase19_audit_contract_boundaries.sql").read_text(encoding="utf-8")
        ).lower()

        self.assertIn("special_metadata->>'source' = 'batch_accounting'", sql)
        self.assertIn("relation_mode = 'batch_accounting'", sql)
        self.assertIn("insert into app.etc_reconciliation_tasks", sql)
        self.assertIn("where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')", sql)
        self.assertIn("set business_batch_id = null", sql)
        self.assertIn("from app.etc_reconciliation_files file", sql)
        self.assertNotIn("insert into app.file_objects", sql)
        self.assertNotIn("sha256 =", sql)

    def test_workbench_idempotency_runtime_evidence_grant_is_read_only(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0102_workbench_idempotency_runtime_evidence_grant.sql").read_text(
                encoding="utf-8"
            )
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn(
            "grant select on app.workbench_idempotency_records to fin_ops_app_runtime",
            normalized_sql,
        )
        self.assertNotRegex(
            normalized_sql,
            r"grant [^;]*(?:insert|update|delete)[^;]*workbench_idempotency_records",
        )

    def test_etc_reconciliation_task_timestamp_repair_uses_typed_canonical_columns(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0103_etc_reconciliation_task_timestamps.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("update app.etc_reconciliation_tasks task", normalized_sql)
        self.assertIn("jsonb_build_object('created_at', payload.created_at)", normalized_sql)
        self.assertIn("jsonb_build_object('updated_at', payload.updated_at)", normalized_sql)
        self.assertIn(
            "nullif(payload.normalized_payload->>'created_at', '') is null",
            normalized_sql,
        )
        self.assertIn(
            "nullif(payload.normalized_payload->>'updated_at', '') is null",
            normalized_sql,
        )
        self.assertNotIn("updated_at = now()", normalized_sql)
        self.assertNotRegex(normalized_sql, r"\bset\s+(?:status|version|scope_month)\s*=")

    def test_cost_statistics_freshness_gate_tracks_published_queue_version(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0105_cost_statistics_freshness_gate.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn(
            "alter table read_model.cost_statistics_read_models add column if not exists "
            "published_source_version bigint",
            normalized_sql,
        )
        self.assertIn(
            "check (published_source_version is null or published_source_version >= 0)",
            normalized_sql,
        )
        self.assertNotIn("update read_model.cost_statistics_read_models", normalized_sql)
        self.assertNotIn("dirty.status = 'done'", normalized_sql)
        self.assertIn("read_model_dirty_scopes_cost_latest_version_idx", normalized_sql)
        self.assertIn("source_version desc, updated_at desc, id desc", normalized_sql)
        self.assertIn("where scope_type = 'cost_statistics'", normalized_sql)

    def test_legacy_cost_statistics_bank_flow_rows_are_dropped(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0123_drop_legacy_cost_statistics_bank_flow_rows.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertEqual(
            normalized_sql,
            "drop table if exists read_model.cost_statistics_bank_flow_rows;",
        )

    def test_cost_statistics_direct_read_migration_retires_derived_runtime(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0126_cost_statistics_direct_canonical_read.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn(
            "where event_type = 'cost_statistics.read_model.refresh'",
            normalized_sql,
        )
        self.assertIn(
            "where scope_type = 'cost_statistics'",
            normalized_sql,
        )
        self.assertIn(
            "delete from read_model.app_status_readiness",
            normalized_sql,
        )
        self.assertIn(
            "drop table if exists read_model.cost_statistics_rows;",
            normalized_sql,
        )
        self.assertIn(
            "drop table if exists read_model.cost_statistics_read_models;",
            normalized_sql,
        )

    def test_direct_canonical_page_runtime_retirement_preserves_rollback_tables(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0127_direct_canonical_page_runtime_retirement.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertEqual(
            normalized_sql,
            "select 'direct_canonical_page_runtime_retirement_noop'::text;",
        )
        for mutation in ("update ", "delete ", "insert ", "alter ", "drop ", "truncate "):
            self.assertNotIn(mutation, normalized_sql)

    def test_bank_detail_canonical_source_proof_backfill_preserves_mismatched_scopes(
        self,
    ) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0124_bank_detail_canonical_source_proof.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("with canonical_source as", normalized_sql)
        self.assertIn(
            "update read_model.bank_detail_scopes scope set source_versions = "
            "scope.source_versions || jsonb_build_object(",
            normalized_sql,
        )
        self.assertIn(
            "'bank_transactions_context_row_count', canonical.context_row_count",
            normalized_sql,
        )
        self.assertIn(
            "'bank_transactions_updated_at', canonical.bank_transactions_updated_at",
            normalized_sql,
        )
        self.assertIn("scope.row_count = canonical.row_count", normalized_sql)
        self.assertNotIn("insert into job.", normalized_sql)
        self.assertNotIn("update job.", normalized_sql)

    def test_oa_pending_payment_freshness_gate_has_scope_private_latest_version_index(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0109_oa_pending_payment_freshness_gate_hot_path.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("read_model_dirty_scopes_oa_latest_version_idx", normalized_sql)
        self.assertIn(
            "tenant_id, scope_type, scope_key, source_version desc, updated_at desc, id desc",
            normalized_sql,
        )
        self.assertIn("where scope_type = 'oa_pending_payment'", normalized_sql)
        self.assertNotIn("where scope_type in", normalized_sql)

    def test_oa_pending_payment_freshness_gate_has_scope_private_active_outbox_index(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0110_oa_pending_payment_outbox_freshness_hot_path.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("outbox_events_oa_pending_payment_freshness_idx", normalized_sql)
        self.assertIn("on job.outbox_events (tenant_id, scope_key)", normalized_sql)
        self.assertIn("where event_type = 'oa_pending_payment.read_model.refresh'", normalized_sql)
        self.assertIn("status in ('pending', 'processing', 'failed', 'dead_lettered')", normalized_sql)
        self.assertIn("scope_key is not null", normalized_sql)
        self.assertNotIn("event_type like", normalized_sql)

    def test_oa_pending_payment_source_snapshot_is_tenant_scoped_and_runtime_writable(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0104_oa_pending_payment_source_snapshot.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create table if not exists app.oa_pending_payment_status_snapshots", normalized_sql)
        self.assertIn("unique (tenant_id, flow_id)", normalized_sql)
        self.assertIn("on app.oa_pending_payment_status_snapshots (tenant_id, scope_month, flow_id)", normalized_sql)
        self.assertIn(
            "grant select, insert, update, delete on app.oa_pending_payment_status_snapshots to fin_ops_worker",
            normalized_sql,
        )
        self.assertIn(
            "grant select on app.oa_pending_payment_status_snapshots to fin_ops_api",
            normalized_sql,
        )

    def test_oa_pending_payment_native_oa_ids_is_additive_and_non_nullable(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0106_oa_pending_payment_native_oa_ids.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("alter table read_model.oa_pending_payment_rows", normalized_sql)
        self.assertIn(
            "add column if not exists oa_ids text[] not null default array[]::text[]",
            normalized_sql,
        )
        self.assertNotIn("update read_model.oa_pending_payment_rows", normalized_sql)

    def test_canonical_finance_domain_contracts_are_additive_and_non_rewriting(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0130_canonical_finance_domain_contracts.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("set local lock_timeout = '5s'", normalized_sql)
        self.assertIn("set local statement_timeout = '60s'", normalized_sql)
        for table in (
            "app.invoices",
            "app.bank_transactions",
            "app.workbench_pair_relations",
            "job.background_jobs",
        ):
            self.assertIn(f"alter table {table}", normalized_sql)
        for constraint in (
            "invoices_canonical_date_month_chk",
            "invoices_source_links_array_chk",
            "invoices_raw_payload_object_chk",
            "bank_transactions_direction_chk",
            "bank_transactions_canonical_date_month_chk",
            "bank_transactions_text_fields_array_chk",
            "bank_transactions_raw_payload_object_chk",
            "workbench_pair_relations_version_chk",
            "workbench_pair_relations_month_scope_chk",
            "workbench_pair_relations_row_cardinality_chk",
            "workbench_pair_relations_row_values_chk",
            "workbench_pair_relations_json_objects_chk",
            "background_jobs_affected_months_chk",
            "background_jobs_json_objects_chk",
        ):
            self.assertIn(f"constraint {constraint}", normalized_sql)
        self.assertEqual(normalized_sql.count("not valid"), 14)
        self.assertNotIn("validate constraint", normalized_sql)
        for mutation in ("update ", "delete ", "insert ", "truncate "):
            self.assertNotIn(mutation, normalized_sql)

    def test_outbox_attempts_contract_has_one_canonical_counter_and_progressive_checks(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0129_runtime_outbox_canonical_attempts_contract.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("create function job.mirror_outbox_event_attempts()", normalized_sql)
        self.assertNotIn("create or replace function job.sync_outbox_event_attempts()", normalized_sql)
        self.assertIn("new.attempt_count := new.attempts", normalized_sql)
        self.assertNotIn("new.attempts :=", normalized_sql)
        self.assertIn("update job.outbox_events set attempt_count = attempts", normalized_sql)
        for constraint in (
            "outbox_events_attempts_nonnegative_chk",
            "outbox_events_attempt_count_mirror_chk",
            "outbox_events_publish_attempt_count_nonnegative_chk",
            "outbox_events_event_type_nonempty_chk",
            "outbox_events_tenant_id_nonempty_chk",
            "outbox_events_payload_object_chk",
            "outbox_events_raw_payload_object_chk",
            "outbox_events_runtime_lock_pair_chk",
            "outbox_events_processing_lock_required_chk",
            "outbox_events_publish_lock_pair_chk",
            "outbox_events_publishing_lock_required_chk",
            "outbox_events_terminal_processed_at_chk",
            "outbox_events_dead_letter_timestamp_chk",
            "outbox_events_published_timestamps_chk",
        ):
            self.assertIn(f"constraint {constraint}", normalized_sql)
        self.assertEqual(normalized_sql.count("not valid"), 14)
        self.assertNotIn("validate constraint", normalized_sql)

    def test_canonical_finance_domain_contract_validation_is_scoped_and_complete(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR
                / "0131_validate_canonical_finance_domain_contracts.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("set local lock_timeout = '5s'", normalized_sql)
        self.assertIn("set local statement_timeout = '2min'", normalized_sql)
        self.assertIn(
            "array_remove(affected_months, 'all') as affected_months",
            normalized_sql,
        )
        self.assertIn("where 'all' = any(affected_months)", normalized_sql)
        self.assertIn(
            "jsonb_build_object( 'affected_months', to_jsonb(normalized_jobs.affected_months) )",
            normalized_sql,
        )
        for constraint in (
            "outbox_events_attempts_nonnegative_chk",
            "outbox_events_attempt_count_mirror_chk",
            "outbox_events_publish_attempt_count_nonnegative_chk",
            "outbox_events_event_type_nonempty_chk",
            "outbox_events_tenant_id_nonempty_chk",
            "outbox_events_payload_object_chk",
            "outbox_events_raw_payload_object_chk",
            "outbox_events_runtime_lock_pair_chk",
            "outbox_events_processing_lock_required_chk",
            "outbox_events_publish_lock_pair_chk",
            "outbox_events_publishing_lock_required_chk",
            "outbox_events_terminal_processed_at_chk",
            "outbox_events_dead_letter_timestamp_chk",
            "outbox_events_published_timestamps_chk",
            "invoices_canonical_date_month_chk",
            "invoices_source_links_array_chk",
            "invoices_raw_payload_object_chk",
            "bank_transactions_direction_chk",
            "bank_transactions_canonical_date_month_chk",
            "bank_transactions_text_fields_array_chk",
            "bank_transactions_raw_payload_object_chk",
            "workbench_pair_relations_version_chk",
            "workbench_pair_relations_month_scope_chk",
            "workbench_pair_relations_row_cardinality_chk",
            "workbench_pair_relations_row_values_chk",
            "workbench_pair_relations_json_objects_chk",
            "background_jobs_affected_months_chk",
            "background_jobs_json_objects_chk",
        ):
            self.assertIn(f"validate constraint {constraint}", normalized_sql)
        self.assertEqual(normalized_sql.count("validate constraint"), 28)
        for forbidden in (
            "delete from",
            "truncate ",
            "drop table",
            "alter table read_model.",
        ):
            self.assertNotIn(forbidden, normalized_sql)

    def test_batch_accounting_tag_selection_initializes_once_from_active_tags(self) -> None:
        sql = strip_sql_comments(
            (MIGRATIONS_DIR / "0135_batch_accounting_tag_selection.sql").read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("'{batch_accounting_tag_selection}'", normalized_sql)
        self.assertIn("'selected_tag_codes'", normalized_sql)
        self.assertIn("coalesce(definition->>'status', 'active') = 'active'", normalized_sql)
        self.assertIn("not (settings_payload ? 'batch_accounting_tag_selection')", normalized_sql)
        self.assertIn("raw_payload = jsonb_set", normalized_sql)
        self.assertIn("'{normalized_payload}'", normalized_sql)
        self.assertIn("target.next_payload", normalized_sql)
        self.assertNotIn("delete ", normalized_sql)
        self.assertNotIn("drop ", normalized_sql)

    def test_in_progress_oa_relations_migrate_to_formal_owner_and_retire_legacy_writes(self) -> None:
        sql = strip_sql_comments(
            (
                MIGRATIONS_DIR / "0136_unify_in_progress_oa_workbench_relations.sql"
            ).read_text(encoding="utf-8")
        ).lower()
        normalized_sql = " ".join(sql.split())

        self.assertIn("spanning multiple active workbench cases", normalized_sql)
        self.assertIn("overlapping active oa pending relations", normalized_sql)
        self.assertIn("insert into app.workbench_pair_relations", normalized_sql)
        self.assertIn("on conflict (case_id) do update", normalized_sql)
        self.assertIn("migrate_oa_pending_relation_to_formal", normalized_sql)
        self.assertIn("status = 'promoted'", normalized_sql)
        self.assertIn("formal workbench relation is now the sole active owner", normalized_sql)
        self.assertIn("revoke insert, update, delete on app.oa_pending_payment_bank_relations", normalized_sql)
        self.assertIn("grant select on app.oa_pending_payment_bank_relations", normalized_sql)
        self.assertNotIn("update app.oa_pending_payment_admissions", normalized_sql)
        self.assertNotIn("job.outbox_events", normalized_sql)
        self.assertNotIn("read_model.", normalized_sql)



if __name__ == "__main__":
    unittest.main()
