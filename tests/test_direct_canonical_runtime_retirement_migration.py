from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)

from postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


MIGRATION_PATH = Path(
    "backend/src/fin_ops_platform/postgres/migrations/"
    "0127_direct_canonical_page_runtime_retirement.sql"
)

RETIRED_EVENT_TYPES = (
    "bank_detail.read_model.refresh",
    "bank_account_balance.read_model.refresh",
    "pending_invoice.read_model.refresh",
    "invoice_lifecycle.read_model.refresh",
    "input_invoice_usage.read_model.refresh",
    "output_invoice_collection.read_model.refresh",
    "oa_pending_payment.read_model.refresh",
    "tax_offset.read_model.refresh",
    "bank_flow_rule_batch.read_model.refresh",
)

RETIRED_SCOPE_TYPES = tuple(
    event_type.removesuffix(".read_model.refresh")
    for event_type in RETIRED_EVENT_TYPES
)


class DirectCanonicalRuntimeRetirementMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(
                database_url=self.database_url,
                pool_enabled=False,
            )
        )

    def test_retirement_is_idempotent_noop_preserving_rollback_evidence(self) -> None:
        with self.connection.transaction() as transaction:
            for event_type in RETIRED_EVENT_TYPES:
                transaction.execute(
                    """
                    insert into job.outbox_events(
                        event_type, aggregate_type, aggregate_id,
                        scope_type, scope_key, dedupe_key, status,
                        last_error, locked_by, locked_at
                    )
                    values (
                        %s, 'read_model', %s,
                        %s, 'all', %s, 'pending',
                        %s, %s, null
                    )
                    """,
                    (
                        event_type,
                        event_type,
                        event_type.removesuffix(".read_model.refresh"),
                        f"retirement:{event_type}",
                        f"evidence:{event_type}",
                        f"worker:{event_type}",
                    ),
                )
            for scope_type in RETIRED_SCOPE_TYPES:
                transaction.execute(
                    """
                    insert into job.read_model_dirty_scopes(
                        scope_type, scope_key, status, last_error,
                        locked_by, locked_at
                    )
                    values (
                        %s, 'all', 'pending', %s, %s, null
                    )
                    """,
                    (
                        scope_type,
                        f"evidence:{scope_type}",
                        f"worker:{scope_type}",
                    ),
                )
                transaction.execute(
                    """
                    insert into read_model.app_status_readiness(
                        read_model_key, scope_type, scope_key, status,
                        schema_version, source_versions, row_count,
                        generated_at, last_error, raw_payload
                    )
                    values (
                        %s, %s, 'all', 'fresh',
                        'rollback-v1', '{"canonical": 7}'::jsonb, 7,
                        now(), %s, '{"rollback": true}'::jsonb
                    )
                    """,
                    (
                        scope_type,
                        scope_type,
                        f"evidence:{scope_type}",
                    ),
                )
            for status in ("processing", "failed", "dead_lettered"):
                transaction.execute(
                    """
                    insert into job.outbox_events(
                        event_type, aggregate_type, aggregate_id,
                        scope_type, scope_key, dedupe_key, status,
                        last_error, locked_by, locked_at
                    )
                    values (
                        'workbench.read_model.refresh', 'read_model', %s,
                        'workbench', %s, %s, %s,
                        %s, %s, case when %s = 'processing' then now() end
                    )
                    """,
                    (
                        status,
                        status,
                        f"retirement:workbench:{status}",
                        status,
                        f"evidence:{status}",
                        f"worker:{status}",
                        status,
                    ),
                )
            for status in ("processing", "failed"):
                transaction.execute(
                    """
                    insert into job.read_model_dirty_scopes(
                        scope_type, scope_key, status, last_error,
                        locked_by, locked_at
                    )
                    values (
                        'workbench', %s, %s, %s, %s,
                        case when %s = 'processing' then now() end
                    )
                    """,
                    (
                        status,
                        status,
                        f"evidence:{status}",
                        f"worker:{status}",
                        status,
                    ),
                )

        outbox_before = self.connection.fetch_all(
            """
            select
                event_type, aggregate_id, scope_type, scope_key,
                dedupe_key, status, last_error, locked_by, locked_at
            from job.outbox_events
            where dedupe_key like 'retirement:%%'
            order by dedupe_key
            """
        )
        dirty_before = self.connection.fetch_all(
            """
            select
                scope_type, scope_key, status, last_error,
                locked_by, locked_at
            from job.read_model_dirty_scopes
            order by scope_type, scope_key
            """
        )
        readiness_before = self.connection.fetch_all(
            """
            select
                read_model_key, scope_type, scope_key, status,
                schema_version, source_versions, row_count,
                generated_at, last_error, raw_payload
            from read_model.app_status_readiness
            order by read_model_key, scope_type, scope_key
            """
        )

        with self.connection.transaction() as transaction:
            transaction.execute(MIGRATION_PATH.read_text(encoding="utf-8"))
            transaction.execute(MIGRATION_PATH.read_text(encoding="utf-8"))

        outbox_after = self.connection.fetch_all(
            """
            select
                event_type, aggregate_id, scope_type, scope_key,
                dedupe_key, status, last_error, locked_by, locked_at
            from job.outbox_events
            where dedupe_key like 'retirement:%%'
            order by dedupe_key
            """
        )
        dirty_after = self.connection.fetch_all(
            """
            select
                scope_type, scope_key, status, last_error,
                locked_by, locked_at
            from job.read_model_dirty_scopes
            order by scope_type, scope_key
            """
        )
        readiness_after = self.connection.fetch_all(
            """
            select
                read_model_key, scope_type, scope_key, status,
                schema_version, source_versions, row_count,
                generated_at, last_error, raw_payload
            from read_model.app_status_readiness
            order by read_model_key, scope_type, scope_key
            """
        )

        self.assertEqual(outbox_after, outbox_before)
        self.assertEqual(dirty_after, dirty_before)
        self.assertEqual(readiness_after, readiness_before)

        tables = {
            str(row["table_name"])
            for row in self.connection.fetch_all(
                """
                select table_name
                from information_schema.tables
                where table_schema = 'read_model'
                  and table_name in (
                      'workbench_rows',
                      'workbench_group_rows',
                      'bank_detail_rows',
                      'pending_invoice_rows',
                      'input_invoice_usage_rows',
                      'output_invoice_collection_rows',
                      'oa_pending_payment_rows'
                  )
                """
            )
        }
        self.assertEqual(
            tables,
            {
                "workbench_rows",
                "workbench_group_rows",
                "bank_detail_rows",
                "pending_invoice_rows",
                "input_invoice_usage_rows",
                "output_invoice_collection_rows",
                "oa_pending_payment_rows",
            },
        )


if __name__ == "__main__":
    unittest.main()
