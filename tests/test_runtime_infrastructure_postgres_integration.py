from __future__ import annotations

import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations,
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
    truncate_test_database,
)


class RuntimeInfrastructurePostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)
        truncate_test_database(self.database_url)

    def test_runtime_infrastructure_tables_exist(self) -> None:
        for table in ("job.read_model_dirty_scopes", "job.runtime_worker_heartbeats"):
            exists = fetch_scalar(
                self.database_url,
                f"select to_regclass('{table}') is not null;",
            )
            self.assertEqual(exists, "t", table)

    def test_outbox_events_runtime_columns_exist(self) -> None:
        columns = (
            "tenant_id",
            "scope_type",
            "scope_key",
            "dedupe_key",
            "attempts",
            "processed_at",
        )
        column_list = ", ".join(f"'{column}'" for column in columns)
        count = fetch_scalar(
            self.database_url,
            f"""
            select count(*)
            from information_schema.columns
            where table_schema = 'job'
              and table_name = 'outbox_events'
              and column_name in ({column_list});
            """,
        )
        self.assertEqual(count, str(len(columns)))

    def test_outbox_attempt_columns_stay_synchronized(self) -> None:
        trigger_name = fetch_scalar(
            self.database_url,
            """
            select tgname
            from pg_trigger
            where tgrelid = 'job.outbox_events'::regclass
              and tgname = 'outbox_events_sync_attempts_trg'
              and not tgisinternal;
            """,
        )
        self.assertEqual(trigger_name, "outbox_events_sync_attempts_trg")

        function_name = fetch_scalar(
            self.database_url,
            """
            select pronamespace::regnamespace::text || '.' || proname
            from pg_proc
            where pronamespace = 'job'::regnamespace
              and proname = 'sync_outbox_event_attempts';
            """,
        )
        self.assertEqual(function_name, "job.sync_outbox_event_attempts")

        inserted = fetch_scalar(
            self.database_url,
            """
            insert into job.outbox_events(event_type, status, attempt_count, attempts)
            values ('runtime_infrastructure_test', 'pending', 3, 0)
            returning id::text || E'\t' || attempt_count::text || E'\t' || attempts::text;
            """,
        )
        event_id, attempt_count, attempts = inserted.split("\t")
        self.assertEqual((attempt_count, attempts), ("3", "3"))

        updated = fetch_scalar(
            self.database_url,
            f"""
            update job.outbox_events
            set attempts = 5
            where id = '{event_id}'::uuid
            returning attempt_count::text || E'\t' || attempts::text;
            """,
        )
        self.assertEqual(tuple(updated.split("\t")), ("5", "5"))

    def test_outbox_status_check_constraint_rejects_invalid_status(self) -> None:
        constraint_name = fetch_scalar(
            self.database_url,
            """
            select conname
            from pg_constraint
            where conrelid = 'job.outbox_events'::regclass
              and conname = 'outbox_events_status_chk'
              and contype = 'c';
            """,
        )
        self.assertEqual(constraint_name, "outbox_events_status_chk")

        with self.assertRaises(migrate.MigrationError):
            migrate.run_psql(
                self.database_url,
                sql="""
                insert into job.outbox_events(event_type, status)
                values ('runtime_infrastructure_test', 'not_a_status');
                """,
            )

        event_id = fetch_scalar(
            self.database_url,
            """
            insert into job.outbox_events(event_type, status)
            values ('runtime_infrastructure_test', 'pending')
            returning id;
            """,
        )
        with self.assertRaises(migrate.MigrationError):
            migrate.run_psql(
                self.database_url,
                sql=f"""
                update job.outbox_events
                set status = 'not_a_status'
                where id = '{event_id}'::uuid;
                """,
            )

    def test_outbox_dedupe_partial_unique_index_predicate_exists(self) -> None:
        predicate = fetch_scalar(
            self.database_url,
            """
            select pg_get_expr(indexes.indpred, indexes.indrelid)
            from pg_index indexes
            join pg_class index_class on index_class.oid = indexes.indexrelid
            where index_class.relname = 'outbox_events_dedupe_uidx'
              and indexes.indrelid = 'job.outbox_events'::regclass
              and indexes.indisunique;
            """,
        )
        self.assertIn("dedupe_key IS NOT NULL", predicate)
        self.assertIn("pending", predicate)
        self.assertIn("processing", predicate)

    def test_0009_backfills_attempts_from_preexisting_attempt_count(self) -> None:
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0008")
        event_id = fetch_scalar(
            self.database_url,
            """
            insert into job.outbox_events(event_type, status, attempt_count)
            values ('runtime_infrastructure_backfill_test', 'pending', 3)
            returning id;
            """,
        )

        apply_test_migrations_through(self.database_url, "0009")

        attempts = fetch_scalar(
            self.database_url,
            f"""
            select attempt_count::text || E'\t' || attempts::text
            from job.outbox_events
            where id = '{event_id}'::uuid;
            """,
        )
        self.assertEqual(tuple(attempts.split("\t")), ("3", "3"))

    def test_outbox_dedupe_partial_unique_index_enforces_active_events_only(self) -> None:
        insert_sql = """
            insert into job.outbox_events(event_type, status, tenant_id, dedupe_key)
            values ('runtime_infrastructure_dedupe_test', 'pending', 'tenant-a', 'same-key');
            """
        migrate.run_psql(self.database_url, sql=insert_sql)
        with self.assertRaises(migrate.MigrationError):
            migrate.run_psql(self.database_url, sql=insert_sql)

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into job.outbox_events(event_type, status, tenant_id, dedupe_key)
            values ('runtime_infrastructure_dedupe_test', 'done', 'tenant-a', 'same-key');
            """,
        )


if __name__ == "__main__":
    unittest.main()
