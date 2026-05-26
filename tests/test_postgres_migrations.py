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
]
EXPECTED_TABLES = [
    "audit.events",
    "audit.app_health_alerts",
    "job.outbox_events",
    "job.background_jobs",
    "job.import_jobs",
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
    "read_model.workbench_groups",
    "read_model.workbench_group_rows",
    "read_model.workbench_summary",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.workbench_reconciliation_decisions",
    "read_model.search_index_rows",
    "read_model.pending_invoice_rows",
    "read_model.pending_invoice_scopes",
    "read_model.input_invoice_usage_rows",
    "read_model.input_invoice_usage_scopes",
    "read_model.output_invoice_collection_rows",
    "read_model.output_invoice_collection_scopes",
    "read_model.bank_detail_rows",
    "read_model.bank_detail_scopes",
    "read_model.cost_statistics_read_models",
    "read_model.cost_statistics_rows",
    "read_model.tax_offset_read_models",
    "read_model.tax_offset_items",
    "read_model.no_oa_bank_batch_rows",
    "read_model.turnover_ledger_rows",
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
        self.assertEqual([item.version for item in migrations], [f"{number:04d}" for number in range(1, 33)])
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
            "outbox_events_priority_chk",
            "outbox_events_schema_version_chk",
            "outbox_events_max_attempts_chk",
            "read_model_dirty_scopes_priority_chk",
            "outbox_events_claim_priority_idx",
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
            "grant select, insert, update, delete on read_model.workbench_reconciliation_decisions to fin_ops_app_runtime",
            "grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_app_runtime",
            "grant select, insert, update on app.matching_runs to fin_ops_app_runtime",
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
            "workbench_reconciliation_decisions_tenant_key_uidx",
            "workbench_reconciliation_decisions_scope_status_idx",
            "workbench_reconciliation_decisions_row_ids_gin",
            "workbench_matching_dirty_scopes_claim_idx",
            "matching_runs_tenant_request_id_uidx",
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
        ):
            self.assertIn(required, sql)

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

    def test_sql_does_not_contain_forbidden_operations_or_secrets(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()
        sql = re.sub(r"\binsert\s+into\s+app\.oa_attachment_invoice_cache_sources\b", "insert into allowed_lookup_backfill", sql)
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
        self.assertIn("deduped_sources as", sql)

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
