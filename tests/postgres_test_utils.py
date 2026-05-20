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
]
TEST_SCHEMAS = ("audit", "job", "read_model", "app", "staging")
TEST_TABLES = (
    "audit.events",
    "audit.app_health_alerts",
    "job.outbox_events",
    "job.background_jobs",
    "job.workbench_matching_dirty_scopes",
    "read_model.workbench_rows",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.search_index_rows",
    "read_model.cost_statistics_read_models",
    "read_model.tax_offset_read_models",
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
