from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import unittest

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict, ImportJobRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.settings_data_reset_request import (
    PostgresSettingsDataResetRequestRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
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
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url))
        self.runtime_queue = RuntimeQueueRepository(self.connection)

    def test_runtime_infrastructure_tables_exist(self) -> None:
        for table in (
            "job.read_model_dirty_scopes",
            "job.runtime_event_attempts",
            "job.runtime_worker_heartbeats",
        ):
            exists = fetch_scalar(
                self.database_url,
                f"select to_regclass('{table}') is not null;",
            )
            self.assertEqual(exists, "t", table)

    def test_ready_health_summary_executes_authoritative_blocker_queries(self) -> None:
        class RabbitMqMetricsUnavailable:
            @staticmethod
            def summary() -> dict[str, object]:
                return {"rabbitmq_metric_error": "integration_test_skipped"}

        summary = RuntimeMonitoringRepository(
            self.connection,
            rabbitmq_metrics_provider=RabbitMqMetricsUnavailable(),
        ).ready_health_summary()

        self.assertIn("critical_failed_outbox_count", summary)
        self.assertIn("critical_failed_dirty_scope_count", summary)
        self.assertIn("critical_stale_dirty_scope_count", summary)
        self.assertEqual(set(summary["critical_read_models"]), {"workbench", "workbench_relation"})

    def test_outbox_events_runtime_columns_exist(self) -> None:
        columns = (
            "tenant_id",
            "scope_type",
            "scope_key",
            "dedupe_key",
            "attempts",
            "processed_at",
            "schema_version",
            "source_version",
            "priority",
            "trace_id",
            "max_attempts",
            "dead_lettered_at",
            "publish_status",
            "published_at",
            "publish_attempt_count",
            "publish_last_error",
            "next_publish_at",
            "publish_locked_by",
            "publish_locked_at",
            "rabbitmq_exchange",
            "rabbitmq_routing_key",
            "rabbitmq_message_id",
            "publish_confirmed_at",
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

    def test_read_model_refresh_proofs_round_trip_and_coalesce_active_targets(
        self,
    ) -> None:
        workbench_metadata = {
            "freshness_token": "workbench-target",
            "expected_source_versions": {"builder": "workbench-v6"},
        }
        workbench_event = self.runtime_queue.enqueue_read_model_refresh_if_inactive(
            scope_type="workbench",
            scope_key="2026-05",
            reason="api_groups_stale",
            metadata=workbench_metadata,
        )
        self.assertIsNotNone(workbench_event)
        self.assertEqual(
            workbench_event.payload["metadata"],
            workbench_metadata,
        )
        self.assertIsNone(
            self.runtime_queue.enqueue_read_model_refresh_if_inactive(
                scope_type="workbench",
                scope_key="2026-05",
                reason="api_groups_stale",
                metadata=workbench_metadata,
            )
        )

    def test_outbox_attempt_count_is_an_exact_one_way_mirror_of_attempts(self) -> None:
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
            select procedure.pronamespace::regnamespace::text || '.' || procedure.proname
            from pg_trigger trigger
            join pg_proc procedure on procedure.oid = trigger.tgfoid
            where trigger.tgrelid = 'job.outbox_events'::regclass
              and trigger.tgname = 'outbox_events_sync_attempts_trg'
              and not trigger.tgisinternal;
            """,
        )
        self.assertEqual(function_name, "job.mirror_outbox_event_attempts")

        inserted = fetch_scalar(
            self.database_url,
            """
            insert into job.outbox_events(event_type, status, attempt_count, attempts)
            values ('runtime_infrastructure_test', 'pending', 3, 0)
            returning id::text || E'\t' || attempt_count::text || E'\t' || attempts::text;
            """,
        )
        event_id, attempt_count, attempts = inserted.split("\t")
        self.assertEqual((attempt_count, attempts), ("0", "0"))

        compatibility_only_update = fetch_scalar(
            self.database_url,
            f"""
            update job.outbox_events
            set attempt_count = 9
            where id = '{event_id}'::uuid
            returning attempt_count::text || E'\t' || attempts::text;
            """,
        )
        self.assertEqual(tuple(compatibility_only_update.split("\t")), ("0", "0"))

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

    def test_outbox_progressive_envelope_constraints_are_validated(self) -> None:
        expected_constraints = {
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
        }
        rows = self.connection.fetch_all(
            """
            select conname, convalidated
            from pg_constraint
            where conrelid = 'job.outbox_events'::regclass
              and conname::text = any(%s::text[])
            """,
            (sorted(expected_constraints),),
        )

        self.assertEqual({row["conname"] for row in rows}, expected_constraints)
        self.assertTrue(all(row["convalidated"] is True for row in rows))

    def test_outbox_progressive_envelope_constraints_reject_new_invalid_rows(self) -> None:
        invalid_inserts = {
            "negative_attempts": """
                insert into job.outbox_events(event_type, attempts)
                values ('runtime.integration.invalid-attempts', -1);
            """,
            "negative_publish_attempts": """
                insert into job.outbox_events(event_type, publish_attempt_count)
                values ('runtime.integration.invalid-publish-attempts', -1);
            """,
            "empty_event_type": """
                insert into job.outbox_events(event_type)
                values ('   ');
            """,
            "empty_tenant_id": """
                insert into job.outbox_events(event_type, tenant_id)
                values ('runtime.integration.invalid-tenant', '   ');
            """,
            "non_object_payload": """
                insert into job.outbox_events(event_type, payload)
                values ('runtime.integration.invalid-payload', '[]'::jsonb);
            """,
            "non_object_raw_payload": """
                insert into job.outbox_events(event_type, raw_payload)
                values ('runtime.integration.invalid-raw-payload', '[]'::jsonb);
            """,
            "partial_runtime_lock": """
                insert into job.outbox_events(event_type, locked_by)
                values ('runtime.integration.invalid-runtime-lock', 'worker-a');
            """,
            "processing_without_lock": """
                insert into job.outbox_events(event_type, status)
                values ('runtime.integration.invalid-processing-lock', 'processing');
            """,
            "partial_publish_lock": """
                insert into job.outbox_events(event_type, publish_locked_by)
                values ('runtime.integration.invalid-publish-lock', 'publisher-a');
            """,
            "publishing_without_lock": """
                insert into job.outbox_events(event_type, publish_status)
                values ('runtime.integration.invalid-publishing-lock', 'publishing');
            """,
            "terminal_without_timestamp": """
                insert into job.outbox_events(event_type, status)
                values ('runtime.integration.invalid-terminal-timestamp', 'done');
            """,
            "dead_letter_without_dead_letter_timestamp": """
                insert into job.outbox_events(event_type, status, processed_at)
                values (
                    'runtime.integration.invalid-dead-letter-timestamp',
                    'dead_lettered',
                    clock_timestamp()
                );
            """,
            "published_without_timestamps": """
                insert into job.outbox_events(event_type, publish_status)
                values ('runtime.integration.invalid-publish-timestamps', 'published');
            """,
        }

        for case_name, sql in invalid_inserts.items():
            with self.subTest(case_name=case_name), self.assertRaises(migrate.MigrationError):
                migrate.run_psql(self.database_url, sql=sql)

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
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into job.outbox_events(event_type, status, processed_at, dead_lettered_at)
            values (
                'runtime_infrastructure_test',
                'dead_lettered',
                clock_timestamp(),
                clock_timestamp()
            );
            """,
        )

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
        self.assertNotIn("processing", predicate)

    def test_outbox_envelope_view_exposes_rabbitmq_safe_fields(self) -> None:
        event = self.runtime_queue.enqueue_read_model_refresh(
            scope_type="workbench_relation",
            scope_key="all",
            reason="integration-test",
            priority="high",
            trace_id="trace-integration",
        )
        row = self.connection.fetch_one(
            """
            select
              event_id,
              event_type,
              scope_type,
              scope_key,
              source_version,
              priority,
              trace_id,
              schema_version,
              publish_status,
              publish_attempt_count,
              payload
            from job.runtime_outbox_envelope_v1
            where event_id = %s
            """,
            (event.event_id,),
        )

        self.assertEqual(row["event_id"], event.event_id)
        self.assertEqual(row["event_type"], "workbench_relation.read_model.refresh")
        self.assertEqual(row["scope_type"], "workbench_relation")
        self.assertEqual(row["scope_key"], "all")
        self.assertEqual(row["source_version"], event.source_version)
        self.assertEqual(row["priority"], "high")
        self.assertEqual(row["trace_id"], "trace-integration")
        self.assertEqual(row["schema_version"], 1)
        self.assertEqual(row["publish_status"], "unpublished")
        self.assertEqual(row["publish_attempt_count"], 0)
        self.assertEqual(row["payload"]["source_version"], event.source_version)

    def test_active_refresh_remains_true_after_outbox_completion_until_dirty_scope_completes(self) -> None:
        event = self.runtime_queue.enqueue_read_model_refresh(
            scope_type="workbench",
            scope_key="2026-02",
            reason="api_groups_source_versions_stale",
        )
        self.connection.fetch_one(
            """
            update job.outbox_events
            set status = 'done', processed_at = clock_timestamp()
            where id = %s
            returning id
            """,
            (event.event_id,),
        )

        self.assertTrue(
            self.runtime_queue.read_model_refresh_is_active(
                tenant_id="default",
                scope_type="workbench",
                scope_key="2026-02",
            )
        )
        self.assertTrue(
            self.runtime_queue.complete_read_model_refresh(
                tenant_id="default",
                scope_type="workbench",
                scope_key="2026-02",
                source_version=event.source_version,
            )
        )
        self.assertFalse(
            self.runtime_queue.read_model_refresh_is_active(
                tenant_id="default",
                scope_type="workbench",
                scope_key="2026-02",
            )
        )

    def test_relation_delta_metadata_dedupe_merges_cases_and_overwrites_same_case(self) -> None:
        first = self.runtime_queue.enqueue_read_model_refresh(
            scope_type="turnover_ledger",
            scope_key="2026-05",
            reason="turnover_relation_changed",
            metadata={
                "relation_deltas": {
                    "CASE-A": {"status": "active", "row_ids": ["oa-a", "bank-a"]},
                }
            },
        )
        second = self.runtime_queue.enqueue_read_model_refresh(
            scope_type="turnover_ledger",
            scope_key="2026-05",
            reason="turnover_relation_changed",
            metadata={
                "relation_deltas": {
                    "CASE-B": {"status": "active", "row_ids": ["oa-b", "bank-b"]},
                }
            },
        )
        third = self.runtime_queue.enqueue_read_model_refresh(
            scope_type="turnover_ledger",
            scope_key="2026-05",
            reason="turnover_relation_changed",
            metadata={
                "relation_deltas": {
                    "CASE-A": {"status": "cancelled", "row_ids": ["oa-a", "bank-a"]},
                }
            },
        )

        self.assertEqual(second.event_id, first.event_id)
        self.assertEqual(third.event_id, first.event_id)
        row = self.connection.fetch_one(
            "select source_version, payload from job.outbox_events where id = %s",
            (first.event_id,),
        )
        self.assertEqual(row["source_version"], 2)
        self.assertEqual(
            row["payload"]["metadata"]["relation_deltas"],
            {
                "CASE-A": {"status": "cancelled", "row_ids": ["oa-a", "bank-a"]},
                "CASE-B": {"status": "active", "row_ids": ["oa-b", "bank-b"]},
            },
        )

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
            insert into job.outbox_events(event_type, status, tenant_id, dedupe_key, processed_at)
            values (
                'runtime_infrastructure_dedupe_test',
                'done',
                'tenant-a',
                'same-key',
                clock_timestamp()
            );
            """,
        )

    def test_runtime_queue_enqueue_inserts_pending_event(self) -> None:
        event = self.runtime_queue.enqueue(
            tenant_id="tenant-a",
            event_type="runtime.integration.created",
            aggregate_type="invoice",
            aggregate_id="invoice-1",
            scope_type="month",
            scope_key="2026-05",
            dedupe_key="runtime-integration-created",
            payload={"invoice_id": "invoice-1"},
        )

        row = self.connection.fetch_one(
            """
            select
              tenant_id,
              event_type,
              aggregate_type,
              aggregate_id,
              scope_type,
              scope_key,
              dedupe_key,
              payload,
              status,
              attempts
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["tenant_id"], "tenant-a")
        self.assertEqual(row["event_type"], "runtime.integration.created")
        self.assertEqual(row["aggregate_type"], "invoice")
        self.assertEqual(row["aggregate_id"], "invoice-1")
        self.assertEqual(row["scope_type"], "month")
        self.assertEqual(row["scope_key"], "2026-05")
        self.assertEqual(row["dedupe_key"], "runtime-integration-created")
        self.assertEqual(row["payload"], {"invoice_id": "invoice-1"})
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["attempts"], 0)

    def test_runtime_queue_duplicate_pending_dedupe_key_returns_same_event_but_processing_allows_new_version(self) -> None:
        first = self.runtime_queue.enqueue(
            tenant_id="tenant-a",
            event_type="runtime.integration.dedupe",
            dedupe_key="active-duplicate",
            payload={"first": True},
        )

        duplicate = self.runtime_queue.enqueue(
            tenant_id="tenant-a",
            event_type="runtime.integration.dedupe",
            dedupe_key="active-duplicate",
            payload={"second": True},
        )

        self.assertEqual(duplicate.event_id, first.event_id)
        count = self.connection.fetch_one(
            """
            select count(*) as count
            from job.outbox_events
            where tenant_id = %s
              and dedupe_key = %s
            """,
            ("tenant-a", "active-duplicate"),
        )
        self.assertEqual(count["count"], 1)

        self.assertTrue(self.runtime_queue.claim_next("worker-1", event_types=["runtime.integration.dedupe"]))
        while_processing = self.runtime_queue.enqueue(
            tenant_id="tenant-a",
            event_type="runtime.integration.dedupe",
            dedupe_key="active-duplicate",
            payload={"while_processing": True},
        )
        self.assertNotEqual(while_processing.event_id, first.event_id)
        self.assertTrue(self.runtime_queue.complete(first.event_id, "worker-1"))
        after_done = self.runtime_queue.enqueue(
            tenant_id="tenant-a",
            event_type="runtime.integration.dedupe",
            dedupe_key="active-duplicate",
            payload={"after_done": True},
        )
        self.assertNotEqual(after_done.event_id, first.event_id)

    def test_atomic_batch_read_model_enqueue_only_creates_uncovered_exact_scopes(self) -> None:
        initial = self.runtime_queue.enqueue_read_model_refreshes_if_inactive(
            scope_type="workbench_relation",
            scope_keys=["2026-02", "2026-03"],
            reason="api_source_versions_stale",
        )

        self.assertEqual(
            [event.scope_key for event in initial],
            ["2026-02", "2026-03"],
        )
        self.assertEqual(
            self.runtime_queue.enqueue_read_model_refreshes_if_inactive(
                scope_type="workbench_relation",
                scope_keys=["2026-02", "2026-03"],
                reason="api_source_versions_stale",
            ),
            [],
        )

        mixed = self.runtime_queue.enqueue_read_model_refreshes_if_inactive(
            scope_type="workbench_relation",
            scope_keys=["2026-02", "2026-04"],
            reason="api_source_versions_stale",
        )

        self.assertEqual([event.scope_key for event in mixed], ["2026-04"])
        counts = self.connection.fetch_one(
            """
            select
                count(*) filter (where status in ('pending', 'processing'))::integer
                    as active_event_count,
                (
                    select count(*)::integer
                    from job.read_model_dirty_scopes
                    where scope_type = 'workbench_relation'
                      and status in ('pending', 'processing')
                ) as active_dirty_count
            from job.outbox_events
            where event_type = 'workbench_relation.read_model.refresh'
            """
        )
        self.assertEqual(counts["active_event_count"], 3)
        self.assertEqual(counts["active_dirty_count"], 3)

    def test_completed_freshness_target_coalesces_concurrent_stale_callers(self) -> None:
        first = self.runtime_queue.enqueue_read_model_refresh_if_inactive(
            scope_type="workbench_relation",
            scope_key="2026-04",
            reason="api_groups_stale",
            metadata={"freshness_token": "target-a"},
        )
        assert first is not None
        self.assertTrue(
            self.runtime_queue.complete_read_model_refresh(
                tenant_id="default",
                scope_type="workbench_relation",
                scope_key="2026-04",
                source_version=first.source_version,
            )
        )
        self.connection.fetch_one(
            """
            update job.outbox_events
            set status = 'done', processed_at = clock_timestamp()
            where id = %s
            returning id
            """,
            (first.event_id,),
        )

        def enqueue_same_target(_index: int) -> str | None:
            connection = PostgresConnection(
                PostgresSettings(
                    database_url=self.database_url,
                    pool_enabled=False,
                )
            )
            event = RuntimeQueueRepository(connection).enqueue_read_model_refresh_if_inactive(
                scope_type="workbench_relation",
                scope_key="2026-04",
                reason="api_groups_stale",
                metadata={"freshness_token": "target-a"},
            )
            return event.event_id if event is not None else None

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(enqueue_same_target, range(4)))

        self.assertEqual(results, [None, None, None, None])
        event_count = self.connection.fetch_one(
            """
            select count(*)::integer as count
            from job.outbox_events
            where event_type = 'workbench_relation.read_model.refresh'
              and scope_key = '2026-04'
            """
        )
        self.assertEqual(event_count["count"], 1)

        second = self.runtime_queue.enqueue_read_model_refresh_if_inactive(
            scope_type="workbench_relation",
            scope_key="2026-04",
            reason="api_groups_stale",
            metadata={"freshness_token": "target-b"},
        )
        assert second is not None
        self.assertTrue(
            self.runtime_queue.complete_read_model_refresh(
                tenant_id="default",
                scope_type="workbench_relation",
                scope_key="2026-04",
                source_version=second.source_version,
            )
        )
        self.connection.fetch_one(
            """
            update job.outbox_events
            set status = 'done', processed_at = clock_timestamp()
            where id = %s
            returning id
            """,
            (second.event_id,),
        )

        third = self.runtime_queue.enqueue_read_model_refresh_if_inactive(
            scope_type="workbench_relation",
            scope_key="2026-04",
            reason="api_groups_stale",
            metadata={"freshness_token": "target-a"},
        )
        assert third is not None
        self.connection.fetch_one(
            """
            update job.outbox_events
            set status = 'done', processed_at = clock_timestamp()
            where id = %s
            returning id
            """,
            (third.event_id,),
        )
        self.connection.fetch_one(
            """
            update job.read_model_dirty_scopes
            set status = 'failed', last_error = 'fixture failed dirty scope'
            where scope_type = 'workbench_relation'
              and scope_key = '2026-04'
            returning id
            """,
        )

        recovered = self.runtime_queue.enqueue_read_model_refresh_if_inactive(
            scope_type="workbench_relation",
            scope_key="2026-04",
            reason="api_groups_stale",
            metadata={"freshness_token": "target-a"},
        )
        self.assertIsNotNone(recovered)

    def test_runtime_queue_claim_next_sets_processing_lock_and_attempts(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.claim", payload={"claim": True})

        claimed = self.runtime_queue.claim_next("worker-claim", event_types=["runtime.integration.claim"])

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.event_id, event.event_id)
        self.assertEqual(claimed.status, "processing")
        self.assertEqual(claimed.attempts, 1)
        row = self.connection.fetch_one(
            """
            select status, locked_by, locked_at is not null as has_locked_at, attempts, attempt_count
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(row["status"], "processing")
        self.assertEqual(row["locked_by"], "worker-claim")
        self.assertTrue(row["has_locked_at"])
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["attempt_count"], 1)

    def test_runtime_queue_records_each_execution_attempt_and_result(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.attempt-history")
        claimed = self.runtime_queue.claim_next(
            "worker-attempt-history",
            event_types=["runtime.integration.attempt-history"],
        )
        self.assertIsNotNone(claimed)

        self.assertTrue(
            self.runtime_queue.complete(
                event.event_id,
                "worker-attempt-history",
                {"processed": 1},
            )
        )
        attempt = self.connection.fetch_one(
            """
            select queue_attempt, worker_id, outcome, result_summary, duration_ms
            from job.runtime_event_attempts
            where event_id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(attempt["queue_attempt"], 1)
        self.assertEqual(attempt["worker_id"], "worker-attempt-history")
        self.assertEqual(attempt["outcome"], "succeeded")
        self.assertEqual(attempt["result_summary"], {"processed": 1})
        self.assertGreaterEqual(attempt["duration_ms"], 0)

    def test_runtime_queue_release_and_defer_persist_attempt_decrements(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.attempt-decrement")
        claimed = self.runtime_queue.claim_next(
            "worker-attempt-decrement",
            event_types=["runtime.integration.attempt-decrement"],
        )
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.attempts, 1)

        self.assertTrue(
            self.runtime_queue.release_event(
                event.event_id,
                "worker-attempt-decrement",
                reason="integration-release",
            )
        )
        released = self.connection.fetch_one(
            """
            select status, attempts, attempt_count, locked_by, locked_at
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(released["status"], "pending")
        self.assertEqual((released["attempts"], released["attempt_count"]), (0, 0))
        self.assertIsNone(released["locked_by"])
        self.assertIsNone(released["locked_at"])

        reclaimed = self.runtime_queue.claim_next(
            "worker-attempt-decrement",
            event_types=["runtime.integration.attempt-decrement"],
        )
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed.attempts, 1)
        self.assertTrue(
            self.runtime_queue.defer_event(
                event.event_id,
                "worker-attempt-decrement",
                reason="integration-defer",
                delay_seconds=0.1,
            )
        )
        deferred = self.connection.fetch_one(
            """
            select status, attempts, attempt_count, locked_by, locked_at
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(deferred["status"], "pending")
        self.assertEqual((deferred["attempts"], deferred["attempt_count"]), (0, 0))
        self.assertIsNone(deferred["locked_by"])
        self.assertIsNone(deferred["locked_at"])
        attempts = self.connection.fetch_all(
            """
            select queue_attempt, outcome
            from job.runtime_event_attempts
            where event_id = %s
            order by started_at, id
            """,
            (event.event_id,),
        )
        self.assertEqual(
            [(attempt["queue_attempt"], attempt["outcome"]) for attempt in attempts],
            [(1, "released"), (1, "deferred")],
        )

    def test_settings_reset_job_and_event_are_atomic_and_idempotent(self) -> None:
        jobs = BackgroundJobService()
        queue = RuntimeQueueRepository(self.connection)
        repository = PostgresSettingsDataResetRequestRepository(self.connection, queue)
        job = jobs.build_job(
            job_type="settings_data_reset",
            label="重置银行流水",
            owner_user_id="YNSYLP005",
            visibility="system",
            idempotency_key="reset-request-1",
            source={"action": "reset_bank_transactions"},
        )
        impact_fingerprint = "a" * 64
        receipt = self.connection.fetch_one(
            """
            insert into job.settings_data_reset_recovery_receipts(
                action, impact_fingerprint, restore_point_run_id, dump_sha256,
                dump_size_bytes, created_by, valid_until
            ) values ('reset_bank_transactions', %s, 'integration-reset-1', %s, 1, 'YNSYLP005', now() + interval '1 hour')
            returning receipt_id::text as receipt_id
            """,
            (impact_fingerprint, "b" * 64),
        )

        created_payload, created = repository.create_or_get(
            job_payload=job.to_payload(),
            request_fingerprint="fingerprint-1",
            event_type="settings.data_reset.requested",
            action="reset_bank_transactions",
            reason="集成测试数据清理",
            impact_fingerprint=impact_fingerprint,
            recovery_receipt_id=receipt["receipt_id"],
            request_id="integration-request-1",
        )
        replay_payload, replay_created = repository.create_or_get(
            job_payload=jobs.build_job(
                job_type="settings_data_reset",
                label="重置银行流水",
                owner_user_id="YNSYLP005",
                visibility="system",
                idempotency_key="reset-request-1",
                source={"action": "reset_bank_transactions"},
            ).to_payload(),
            request_fingerprint="fingerprint-1",
            event_type="settings.data_reset.requested",
            action="reset_bank_transactions",
            reason="集成测试数据清理",
            impact_fingerprint=impact_fingerprint,
            recovery_receipt_id=receipt["receipt_id"],
            request_id="integration-request-1",
        )

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(created_payload["job_id"], replay_payload["job_id"])
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.background_jobs where job_type = 'settings_data_reset';",
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.outbox_events where event_type = 'settings.data_reset.requested';",
            ),
            "1",
        )

    def test_settings_reset_request_rolls_back_job_when_enqueue_fails(self) -> None:
        class FailingQueue:
            @staticmethod
            def enqueue_in_transaction(**_kwargs):
                raise RuntimeError("queue unavailable")

        repository = PostgresSettingsDataResetRequestRepository(self.connection, FailingQueue())
        job = BackgroundJobService().build_job(
            job_type="settings_data_reset",
            label="重置银行流水",
            owner_user_id="YNSYLP005",
            visibility="system",
            idempotency_key="reset-request-rollback",
            source={"action": "reset_bank_transactions"},
        )
        impact_fingerprint = "c" * 64
        receipt = self.connection.fetch_one(
            """
            insert into job.settings_data_reset_recovery_receipts(
                action, impact_fingerprint, restore_point_run_id, dump_sha256,
                dump_size_bytes, created_by, valid_until
            ) values ('reset_bank_transactions', %s, 'integration-reset-rollback', %s, 1, 'YNSYLP005', now() + interval '1 hour')
            returning receipt_id::text as receipt_id
            """,
            (impact_fingerprint, "d" * 64),
        )

        with self.assertRaisesRegex(RuntimeError, "queue unavailable"):
            repository.create_or_get(
                job_payload=job.to_payload(),
                request_fingerprint="fingerprint-rollback",
                event_type="settings.data_reset.requested",
                action="reset_bank_transactions",
                reason="集成测试回滚",
                impact_fingerprint=impact_fingerprint,
                recovery_receipt_id=receipt["receipt_id"],
                request_id="integration-request-rollback",
            )

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from job.background_jobs where idempotency_key = 'reset-request-rollback';",
            ),
            "0",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                f"select count(*) from job.settings_data_reset_recovery_receipts where receipt_id = '{receipt['receipt_id']}'::uuid and consumed_by_job_id is null;",
            ),
            "1",
        )

    def test_import_job_request_identity_and_retry_lease_are_durable(self) -> None:
        repository = ImportJobRepository(self.connection)
        job = repository.create_or_get_job(
            import_type="bank_transactions.import",
            import_session_id="integration-session-1",
            source_file_id="integration-file-1",
            idempotency_key="integration-import-1",
            payload={"session_id": "integration-session-1"},
        )
        replay = repository.create_or_get_job(
            import_type="bank_transactions.import",
            import_session_id="integration-session-1",
            source_file_id="integration-file-1",
            idempotency_key="integration-import-1",
            payload={"session_id": "integration-session-1"},
        )
        self.assertEqual(job.import_job_id, replay.import_job_id)
        self.assertEqual(job.request_fingerprint, replay.request_fingerprint)

        with self.assertRaises(ImportJobIdempotencyConflict):
            repository.create_or_get_job(
                import_type="bank_transactions.import",
                import_session_id="integration-session-2",
                source_file_id="integration-file-2",
                idempotency_key="integration-import-1",
                payload={"session_id": "integration-session-2"},
            )

        processing = repository.mark_processing(job.import_job_id, worker_id="integration-import-worker")
        self.assertIsNotNone(processing)
        self.assertIsNone(repository.mark_processing(job.import_job_id, worker_id="competing-worker"))
        self.assertTrue(
            repository.mark_retryable(
                job.import_job_id,
                worker_id="integration-import-worker",
                error="transient integration failure",
            )
        )
        retried = repository.mark_processing(job.import_job_id, worker_id="integration-import-worker")
        self.assertIsNotNone(retried)
        self.assertEqual(retried.attempt_count, 2)
        self.assertTrue(
            repository.mark_failed(
                job.import_job_id,
                worker_id="integration-import-worker",
                error="terminal integration failure",
            )
        )
        manual_retry = repository.create_or_get_job(
            import_type="bank_transactions.import",
            import_session_id="integration-session-1",
            source_file_id="integration-file-1",
            idempotency_key="integration-import-1",
            payload={"session_id": "integration-session-1"},
        )
        self.assertEqual(manual_retry.import_job_id, job.import_job_id)
        self.assertEqual(manual_retry.status, "pending")
        self.assertEqual(manual_retry.attempt_count, 0)
        self.assertIsNone(manual_retry.last_error)

    def test_runtime_queue_claim_next_reclaims_stale_processing_event(self) -> None:
        row = self.connection.fetch_one(
            """
            insert into job.outbox_events (
              event_type,
              status,
              locked_by,
              locked_at,
              attempts,
              attempt_count,
              payload
            )
            values (
              'runtime.integration.reclaim',
              'processing',
              'dead-worker',
              now() - interval '10 minutes',
              2,
              2,
              '{"reclaim": true}'::jsonb
            )
            returning id::text as event_id
            """
        )

        claimed = self.runtime_queue.claim_next(
            "new-worker",
            event_types=["runtime.integration.reclaim"],
            lock_timeout_seconds=300,
        )

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.event_id, row["event_id"])
        self.assertEqual(claimed.status, "processing")
        self.assertEqual(claimed.attempts, 3)
        stored = self.connection.fetch_one(
            """
            select status, locked_by, locked_at > now() - interval '1 minute' as lock_refreshed, attempts, attempt_count
            from job.outbox_events
            where id = %s
            """,
            (row["event_id"],),
        )
        self.assertEqual(stored["status"], "processing")
        self.assertEqual(stored["locked_by"], "new-worker")
        self.assertTrue(stored["lock_refreshed"])
        self.assertEqual(stored["attempts"], 3)
        self.assertEqual(stored["attempt_count"], 3)

    def test_runtime_queue_does_not_reclaim_stale_processing_event_before_available_at(self) -> None:
        row = self.connection.fetch_one(
            """
            insert into job.outbox_events (
              event_type,
              status,
              locked_by,
              locked_at,
              available_at,
              attempts,
              attempt_count,
              payload
            )
            values (
              'runtime.integration.future-reclaim',
              'processing',
              'dead-worker',
              now() - interval '10 minutes',
              now() + interval '10 minutes',
              2,
              2,
              '{"future_reclaim": true}'::jsonb
            )
            returning id::text as event_id
            """
        )

        claimed_before_available = self.runtime_queue.claim_next(
            "new-worker",
            event_types=["runtime.integration.future-reclaim"],
            lock_timeout_seconds=300,
        )

        self.assertIsNone(claimed_before_available)
        self.connection.execute(
            """
            update job.outbox_events
            set available_at = now() - interval '1 minute'
            where id = %s
            """,
            (row["event_id"],),
        )

        claimed_after_available = self.runtime_queue.claim_next(
            "new-worker",
            event_types=["runtime.integration.future-reclaim"],
            lock_timeout_seconds=300,
        )

        self.assertIsNotNone(claimed_after_available)
        self.assertEqual(claimed_after_available.event_id, row["event_id"])
        self.assertEqual(claimed_after_available.attempts, 3)

    def test_runtime_queue_complete_marks_done_and_sets_processed_at(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.complete")
        self.assertIsNotNone(self.runtime_queue.claim_next("worker-complete", event_types=["runtime.integration.complete"]))

        self.assertTrue(self.runtime_queue.complete(event.event_id, "worker-complete", result_payload={"ok": True}))

        row = self.connection.fetch_one(
            """
            select
              status,
              processed_at is not null as has_processed_at,
              locked_by,
              locked_at,
              raw_payload->'runtime_result' as runtime_result
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(row["status"], "done")
        self.assertTrue(row["has_processed_at"])
        self.assertIsNone(row["locked_by"])
        self.assertIsNone(row["locked_at"])
        self.assertEqual(row["runtime_result"], {"ok": True})

    def test_runtime_queue_fail_retry_returns_pending_with_next_available_at(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.retry")
        claimed = self.runtime_queue.claim_next("worker-retry", event_types=["runtime.integration.retry"])
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.attempts, 1)

        self.assertTrue(
            self.runtime_queue.fail(
                event.event_id,
                "worker-retry",
                "temporary failure",
                retry=True,
                retry_delay_seconds=30,
            )
        )

        row = self.connection.fetch_one(
            """
            select
              status,
              last_error,
              locked_by,
              locked_at,
              attempts,
              attempt_count,
              available_at > now() as scheduled_later
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["last_error"], "temporary failure")
        self.assertIsNone(row["locked_by"])
        self.assertIsNone(row["locked_at"])
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["attempt_count"], 1)
        self.assertTrue(row["scheduled_later"])

    def test_runtime_queue_fail_without_retry_marks_failed(self) -> None:
        event = self.runtime_queue.enqueue(event_type="runtime.integration.fail")
        self.assertIsNotNone(self.runtime_queue.claim_next("worker-fail", event_types=["runtime.integration.fail"]))

        self.assertTrue(self.runtime_queue.fail(event.event_id, "worker-fail", "fatal failure", retry=False))

        row = self.connection.fetch_one(
            """
            select
              status,
              last_error,
              processed_at is not null as has_processed_at,
              locked_by,
              locked_at
            from job.outbox_events
            where id = %s
            """,
            (event.event_id,),
        )
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["last_error"], "fatal failure")
        self.assertTrue(row["has_processed_at"])
        self.assertIsNone(row["locked_by"])
        self.assertIsNone(row["locked_at"])


if __name__ == "__main__":
    unittest.main()
