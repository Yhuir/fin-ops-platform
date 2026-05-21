from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
import re
import tempfile
import unittest
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
]
EXPECTED_TABLES = [
    "audit.events",
    "audit.app_health_alerts",
    "job.outbox_events",
    "job.background_jobs",
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
    "read_model.workbench_rows",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.search_index_rows",
    "read_model.pending_invoice_rows",
    "read_model.cost_statistics_read_models",
    "read_model.tax_offset_read_models",
]


def migration_sql() -> str:
    return "\n".join((MIGRATIONS_DIR / name).read_text(encoding="utf-8") for name in EXPECTED_MIGRATIONS)


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    return re.sub(r"--.*?$", "", sql, flags=re.M)


class PostgresMigrationDiscoveryTests(unittest.TestCase):
    def test_expected_migration_files_are_present_and_ordered(self) -> None:
        migrations = migrate.discover_migrations(MIGRATIONS_DIR)
        self.assertEqual([item.path.name for item in migrations], EXPECTED_MIGRATIONS)
        self.assertEqual([item.version for item in migrations], [f"{number:04d}" for number in range(1, 12)])
        for item in migrations:
            self.assertRegex(item.checksum_sha256, r"^[0-9a-f]{64}$")

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
        with patch.dict(os.environ, {"DATABASE_URL": ""}):
            exit_code = migrate.main(["status", "--migrations-dir", str(MIGRATIONS_DIR)], stdout=stdout, stderr=stderr)
        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("PostgreSQL connection is required", stderr.getvalue())

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
    def test_sql_contains_required_schemas_and_tables(self) -> None:
        sql = migration_sql().lower()
        for schema in ("app", "read_model", "job", "audit", "staging"):
            self.assertIn(f"create schema if not exists {schema}", sql)
        for table in EXPECTED_TABLES:
            self.assertIn(f"create table if not exists {table}", sql)

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
            "temporary_object_key",
            "source_storage_uri",
            "verified_at",
            "tombstoned_at",
            "grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker",
            "grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_worker",
        ):
            self.assertIn(required, sql)

    def test_sql_does_not_contain_forbidden_operations_or_secrets(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
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
            self.assertIsNone(re.search(pattern, sql), pattern)

    def test_core_tables_keep_legacy_or_external_identity_and_raw_payload(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        for table in EXPECTED_TABLES:
            pattern = rf"create table if not exists {re.escape(table)}\s*\((.*?)\);"
            match = re.search(pattern, sql, flags=re.S)
            self.assertIsNotNone(match, table)
            body = match.group(1)
            self.assertIn("id uuid primary key default gen_random_uuid()", body, table)
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
        self.assertIn("oa_applications_scope_month_row_idx", sql)


if __name__ == "__main__":
    unittest.main()
