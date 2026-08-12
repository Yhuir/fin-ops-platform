from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
from urllib.parse import urlsplit, unquote
import unittest

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.postgres_connection import redact_database_url


MIGRATIONS_DIR = Path("backend/src/fin_ops_platform/postgres/migrations")
EXPECTED_MIGRATION_FILES = [
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
]
TEST_SCHEMAS = ("audit", "job", "read_model", "app", "staging")
TEST_TABLES = (
    "audit.events",
    "app.financial_fact_corrections",
    "audit.app_health_alerts",
    "audit.external_control_evidence_items",
    "audit.external_control_evidence",
    "job.outbox_events",
    "job.background_jobs",
    "job.import_jobs",
    "job.runtime_event_attempts",
    "job.settings_data_reset_recovery_receipts",
    "job.workbench_matching_dirty_scopes",
    "job.read_model_dirty_scopes",
    "job.runtime_worker_heartbeats",
    "read_model.workbench_rows",
    "read_model.workbench_groups",
    "read_model.workbench_group_rows",
    "read_model.workbench_summary",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.workbench_generation_stats",
    "read_model.workbench_generations",
    "read_model.workbench_reconciliation_decisions",
    "read_model.workbench_relation_scopes",
    "read_model.workbench_relation_groups",
    "read_model.workbench_relation_rows",
    "read_model.search_index_rows",
    "read_model.app_status_readiness",
    "read_model.pending_invoice_rows",
    "read_model.pending_invoice_scopes",
    "read_model.invoice_lifecycle_rows",
    "read_model.invoice_lifecycle_scopes",
    "read_model.bank_detail_rows",
    "read_model.bank_detail_scopes",
    "read_model.bank_account_balances",
    "read_model.bank_flow_rule_batch_rows",
    "read_model.input_invoice_usage_rows",
    "read_model.input_invoice_usage_scopes",
    "read_model.output_invoice_collection_rows",
    "read_model.output_invoice_collection_scopes",
    "read_model.oa_pending_payment_rows",
    "read_model.oa_pending_payment_scopes",
    "read_model.tax_offset_read_models",
    "read_model.tax_offset_items",
    "read_model.no_oa_bank_batch_rows",
    "read_model.turnover_ledger_rows",
    "read_model.turnover_ledger_scopes",
    "app.import_batches",
    "app.import_batch_rows",
    "app.file_objects",
    "app.import_files",
    "app.invoices",
    "app.bank_transactions",
    "app.bank_transaction_categories",
    "app.bank_transaction_category_confirmations",
    "app.bank_transaction_category_events",
    "app.bank_transaction_relation_claims",
    "app.bank_flow_rule_batches",
    "app.bank_flow_rule_batch_events",
    "app.matching_runs",
    "app.matching_results",
    "app.workbench_pair_relations",
    "app.workbench_pair_relation_history",
    "app.workbench_row_overrides",
    "app.workbench_exception_cases",
    "app.workbench_exception_case_events",
    "app.no_oa_bank_batches",
    "app.no_oa_bank_batch_events",
    "app.oa_applications",
    "app.oa_application_items",
    "app.oa_attachments",
    "app.oa_sync_runs",
    "app.oa_sync_watermarks",
    "app.oa_attachment_invoice_cache",
    "app.oa_attachment_invoice_cache_sources",
    "app.oa_applicant_credentials",
    "app.oa_pending_payment_admissions",
    "app.oa_pending_payment_bank_relations",
    "app.oa_pending_payment_bank_relation_events",
    "app.oa_pending_payment_status_snapshots",
    "app.oa_source_aliases",
    "app.manual_oa_imports",
    "app.tax_certified_import_sessions",
    "app.tax_certified_import_batches",
    "app.tax_certified_import_records",
    "app.etc_invoices",
    "app.etc_batch_invoice_links",
    "app.etc_import_session_files",
    "app.etc_import_sessions",
    "app.etc_import_batches",
    "app.etc_submission_batches",
    "app.etc_business_batches",
    "app.etc_reconciliation_tasks",
    "app.etc_reconciliation_files",
    "app.historical_etc_repair_bundles",
    "app.historical_etc_repair_parsed_seeds",
    "app.historical_etc_repair_states",
    "app.turnover_relations",
    "app.turnover_relation_events",
    "app.turnover_ledger_extras",
    "app.input_invoice_usage_oa_reverse_batches",
    "app.output_invoice_collection_red_relations",
    "app.output_invoice_collection_reminders",
    "app.output_invoice_collection_status_overrides",
    "app.output_invoice_receipt_events",
    "app.output_invoice_receipt_number_counters",
    "app.output_invoice_receipt_settings",
    "app.output_invoice_receipts",
    "app.tax_offset_plans",
    "app.workbench_idempotency_records",
    "app.app_settings",
    "app.pending_invoice_manual_invoice_commands",
    "staging.id_mappings",
    "staging.mongo_exports",
    "staging.mongo_raw_records",
)
RESERVED_DATABASE_NAMES = {"fin_ops", "postgres", "template0", "template1"}


def require_postgres_test_database_url() -> str:
    database_url = (os.environ.get("FIN_OPS_TEST_DATABASE_URL") or "").strip()
    if not database_url:
        if os.environ.get("FIN_OPS_REQUIRE_SETTINGS_ACL_POSTGRES") == "1":
            raise RuntimeError("FIN_OPS_TEST_DATABASE_URL is required for the settings ACL PostgreSQL gate.")
        raise unittest.SkipTest("FIN_OPS_TEST_DATABASE_URL is not set; skipping PostgreSQL integration tests.")
    assert_safe_test_database_url(database_url)
    return database_url


def assert_safe_test_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name:
        raise AssertionError("FIN_OPS_TEST_DATABASE_URL must include a database name.")
    if database_name in RESERVED_DATABASE_NAMES:
        raise AssertionError(f"Refusing to run PostgreSQL integration tests against reserved database {database_name}.")
    if "test" not in database_name and os.environ.get("FIN_OPS_ALLOW_POSTGRES_TEST_DB") != "1":
        raise AssertionError(
            "Refusing to run PostgreSQL integration tests against a database that is not visibly disposable: "
            f"{redact_database_url(database_url)}"
        )
    return database_name


def discover_stage06_migrations() -> list[migrate.Migration]:
    migrations = migrate.discover_migrations(MIGRATIONS_DIR)
    actual_files = [item.path.name for item in migrations]
    if actual_files != EXPECTED_MIGRATION_FILES:
        raise AssertionError(f"Unexpected stage 06 migration set: {actual_files}")
    return migrations


def apply_test_migrations(database_url: str) -> str:
    assert_safe_test_database_url(database_url)
    output = StringIO()
    migrations = discover_stage06_migrations()
    with _test_db_env():
        migrate.apply_migrations(database_url, migrations, output)
    return output.getvalue()


def apply_test_migrations_through(database_url: str, target_version: str) -> str:
    assert_safe_test_database_url(database_url)
    migrations = discover_stage06_migrations()
    selected_migrations = [item for item in migrations if item.version <= target_version]
    if not selected_migrations or selected_migrations[-1].version != target_version:
        raise AssertionError(f"Unknown migration target version: {target_version}")
    output = StringIO()
    with _test_db_env():
        migrate.apply_migrations(database_url, selected_migrations, output)
    return output.getvalue()


def reset_test_database(database_url: str) -> None:
    database_name = assert_safe_test_database_url(database_url)
    if "test" not in database_name:
        raise AssertionError(
            "Refusing destructive PostgreSQL integration reset against a database that is not visibly disposable: "
            f"{redact_database_url(database_url)}"
        )
    migrate.run_psql(
        database_url,
        sql="""
drop schema if exists audit cascade;
drop schema if exists job cascade;
drop schema if exists read_model cascade;
drop schema if exists app cascade;
drop schema if exists staging cascade;
drop table if exists public.schema_migrations;
""",
    )


def truncate_test_database(database_url: str) -> None:
    assert_safe_test_database_url(database_url)
    table_list = ", ".join(TEST_TABLES)
    migrate.run_psql(
        database_url,
        sql=f"truncate table {table_list} restart identity cascade;",
    )


def fetch_scalar(database_url: str, sql: str) -> str:
    return migrate.run_psql(database_url, sql=sql).strip()


class _test_db_env:
    def __enter__(self) -> None:
        self._previous = os.environ.get("FIN_OPS_ALLOW_POSTGRES_TEST_DB")
        os.environ["FIN_OPS_ALLOW_POSTGRES_TEST_DB"] = "1"

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._previous is None:
            os.environ.pop("FIN_OPS_ALLOW_POSTGRES_TEST_DB", None)
        else:
            os.environ["FIN_OPS_ALLOW_POSTGRES_TEST_DB"] = self._previous
