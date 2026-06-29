from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY


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
    "app.bank_transaction_category_confirmations",
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
    "app.tax_offset_plans",
    "app.etc_invoices",
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
    "read_model.workbench_rows",
    "read_model.workbench_groups",
    "read_model.workbench_group_rows",
    "read_model.workbench_generations",
    "read_model.workbench_generation_stats",
    "read_model.workbench_summary",
    "read_model.workbench_snapshots",
    "read_model.workbench_candidate_matches",
    "read_model.workbench_reconciliation_decisions",
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
    "read_model.cost_statistics_read_models",
    "read_model.cost_statistics_rows",
    "read_model.tax_offset_read_models",
    "read_model.tax_offset_items",
    "read_model.no_oa_bank_batch_rows",
    "read_model.turnover_ledger_rows",
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
    "workbench_relation": ("read_model.workbench_reconciliation_decisions",),
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
    "cost_statistics": ("read_model.cost_statistics_read_models", "read_model.cost_statistics_rows"),
    "tax_offset": ("read_model.tax_offset_read_models", "read_model.tax_offset_items"),
    "no_oa_bank_batch": ("read_model.no_oa_bank_batch_rows",),
    "turnover_ledger": ("read_model.turnover_ledger_rows",),
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
        self.assertEqual([item.version for item in migrations], [f"{number:04d}" for number in range(1, 78)])
        for item in migrations:
            self.assertRegex(item.checksum_sha256, r"^[0-9a-f]{64}$")

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
        self.assertIn("workbench_relation_rows_tenant_row_idx", sql)

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

    def test_oa_pending_payment_bank_relation_schema_and_migration_are_declared(self) -> None:
        sql = strip_sql_comments(migration_sql()).lower()

        self.assertIn("create table if not exists app.oa_pending_payment_bank_relations", sql)
        self.assertIn("create table if not exists app.bank_transaction_relation_claims", sql)
        self.assertIn("bank_transaction_relation_claims_active_bank_uidx", sql)
        self.assertIn("on app.bank_transaction_relation_claims (bank_transaction_id)", sql)
        self.assertIn("where status = 'active'", sql)
        self.assertIn("oa_pending_payment_bank_relations_oa_gin", sql)
        self.assertIn("oa_pending_payment_bank_relations_bank_gin", sql)
        self.assertIn("special_metadata->>'origin' = 'oa_pending_payment_in_progress'", sql)
        self.assertIn("migrated_to_pending_relation_id", sql)
        self.assertIn("oa_pending_payment_in_progress_relation_migrated", sql)

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

    def test_app_status_read_model_storage_contracts_are_declared(self) -> None:
        sql = migration_sql().lower()
        expected_tables = set(EXPECTED_TABLES)

        self.assertEqual(set(READ_MODEL_STORAGE_CONTRACTS), set(APP_STATUS_READ_MODEL_REGISTRY))
        for read_model_key, tables in READ_MODEL_STORAGE_CONTRACTS.items():
            with self.subTest(read_model_key=read_model_key):
                self.assertTrue(tables)
                self.assertLessEqual(set(tables), expected_tables)
                for table in tables:
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
        sql = re.sub(r"\binsert\s+into\s+app\.oa_attachment_invoice_cache_sources\b", "insert into allowed_lookup_backfill", sql)
        for table_name in (
            "oa_pending_payment_bank_relations",
            "bank_transaction_relation_claims",
            "oa_pending_payment_bank_relation_events",
            "workbench_pair_relation_history",
        ):
            sql = re.sub(
                rf"\binsert\s+into\s+app\.{table_name}\b",
                f"insert into allowed_0073_{table_name}",
                sql,
            )
        sql = re.sub(
            r"\binsert\s+into\s+read_model\.workbench_generations\s*\(.*?on\s+conflict\s*\(generation_id\)\s+do\s+nothing;",
            "insert into allowed_workbench_generation_backfill",
            sql,
            flags=re.S,
        )
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


if __name__ == "__main__":
    unittest.main()
