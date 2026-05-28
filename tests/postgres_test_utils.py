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
]
TEST_SCHEMAS = ("audit", "job", "read_model", "app", "staging")
TEST_TABLES = (
    "audit.events",
    "audit.app_health_alerts",
    "job.outbox_events",
    "job.background_jobs",
    "job.import_jobs",
    "job.workbench_matching_dirty_scopes",
    "job.read_model_dirty_scopes",
    "job.runtime_worker_heartbeats",
    "read_model.workbench_rows",
    "read_model.workbench_groups",
    "read_model.workbench_group_rows",
    "read_model.workbench_summary",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.workbench_reconciliation_decisions",
    "read_model.search_index_rows",
    "read_model.pending_invoice_rows",
    "read_model.pending_invoice_scopes",
    "read_model.bank_detail_rows",
    "read_model.bank_detail_scopes",
    "read_model.input_invoice_usage_rows",
    "read_model.input_invoice_usage_scopes",
    "read_model.output_invoice_collection_rows",
    "read_model.output_invoice_collection_scopes",
    "read_model.cost_statistics_read_models",
    "read_model.cost_statistics_rows",
    "read_model.tax_offset_read_models",
    "read_model.tax_offset_items",
    "read_model.no_oa_bank_batch_rows",
    "read_model.turnover_ledger_rows",
    "app.import_batches",
    "app.import_batch_rows",
    "app.file_objects",
    "app.import_files",
    "app.invoices",
    "app.bank_transactions",
    "app.bank_transaction_categories",
    "app.bank_transaction_category_events",
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
    "app.manual_oa_imports",
    "app.tax_certified_import_sessions",
    "app.tax_certified_import_batches",
    "app.tax_certified_import_records",
    "app.etc_invoices",
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
    "app.app_settings",
    "app.pending_invoice_manual_invoice_commands",
)
RESERVED_DATABASE_NAMES = {"fin_ops", "postgres", "template0", "template1"}


def require_postgres_test_database_url() -> str:
    database_url = (os.environ.get("FIN_OPS_TEST_DATABASE_URL") or "").strip()
    if not database_url:
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
