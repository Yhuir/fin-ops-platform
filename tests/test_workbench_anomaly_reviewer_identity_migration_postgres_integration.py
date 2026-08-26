from __future__ import annotations

import unittest
from pathlib import Path

from fin_ops_platform.postgres import migrate

from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)

MIGRATION_SQL = (
    Path(__file__).resolve().parents[1]
    / "backend/src/fin_ops_platform/postgres/migrations/0156_backfill_workbench_anomaly_reviewer_identity.sql"
).read_text(encoding="utf-8")


class WorkbenchAnomalyReviewerIdentityMigrationPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0155")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def _insert_review(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_cases(
                case_id, status, resolution, version, business_line, scenario, scope_month,
                row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
            ) values (
                'ANOMALY-REVIEW-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'resolved',
                'accept_paired',
                3,
                'reconciliation_workbench',
                'workbench_anomaly_review',
                '2026-08-01',
                array[]::text[],
                array[]::text[],
                '8',
                '2026-08-25T17:01:44.700999+08:00',
                '8',
                '2026-08-25T17:01:44.700999+08:00',
                jsonb_build_object(
                    'normalized_payload',
                    jsonb_build_object(
                        'fingerprint', repeat('a', 64),
                        'group_id', 'case:CASE-1',
                        'decision', 'accept_paired',
                        'note', '',
                        'updated_by', '8'
                    )
                )
            );
            """,
        )

    def test_0156_backfills_identity_without_rewriting_review_facts_and_is_idempotent(self) -> None:
        self._insert_review()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into audit.events(
                event_type, object_type, object_id, actor_id, actor_name, actor_account,
                occurred_at
            ) values
                ('operation.completed', 'workbench', 'older', '8', '杨丽萍', 'YNSYLP007',
                 '2026-08-24T10:00:00+08:00'),
                ('operation.completed', 'workbench', 'newer', '8', '杨丽萍', 'YNSYLP007',
                 '2026-08-26T10:00:00+08:00');
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    resolution,
                    version,
                    updated_by,
                    to_char(updated_at at time zone 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS.US'),
                    raw_payload#>>'{normalized_payload,actor_account}',
                    raw_payload#>>'{normalized_payload,actor_name}'
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
                """,
            ),
            "accept_paired|3|8|2026-08-25 17:01:44.700999|YNSYLP007|杨丽萍",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_case_events
                where case_id = 'ANOMALY-REVIEW-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
                  and event_type = 'workbench_anomaly_reviewer_identity_backfilled'
                  and actor_id = 'system:migration:0156';
                """,
            ),
            "1",
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_case_events
                where case_id = 'ANOMALY-REVIEW-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
                """,
            ),
            "1",
        )

    def test_0156_rejects_ambiguous_actor_accounts_without_partial_backfill(self) -> None:
        self._insert_review()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into audit.events(
                event_type, object_type, object_id, actor_id, actor_name, actor_account
            ) values
                ('operation.completed', 'workbench', 'one', '8', '杨丽萍', 'YNSYLP007'),
                ('operation.completed', 'workbench', 'two', '8', '杨丽萍', 'CONFLICT');
            """,
        )

        with self.assertRaisesRegex(migrate.MigrationError, "has 2 authoritative accounts"):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select coalesce(
                    raw_payload#>>'{normalized_payload,actor_account}',
                    '<missing>'
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
                """,
            ),
            "<missing>",
        )


if __name__ == "__main__":
    unittest.main()
