from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)


MIGRATION_SQL = (
    Path(__file__).resolve().parents[1]
    / "backend/src/fin_ops_platform/postgres/migrations/0154_migrate_etc_summary_anomaly_review.sql"
).read_text(encoding="utf-8")


class ETCSummaryAnomalyReviewMigrationPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0153")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def test_0154_migrates_only_the_exact_reviewed_relation_and_is_idempotent(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types,
                amount_check, created_by, created_at, updated_at
            ) values (
                'CASE-BATCH-txn_imported_1453',
                'batch_accounting',
                'active',
                '2026-04-01',
                array[
                    'oa-exp-2080',
                    'txn_imported_1453',
                    'etc-summary-ETC-OA-20260413-241125'
                ]::text[],
                array['oa', 'bank', 'invoice']::text[],
                '{
                    "status":"matched",
                    "oa_total":"2411.25",
                    "bank_total":"2411.25",
                    "invoice_total":"2411.25",
                    "amount_delta":"0.00"
                }'::jsonb,
                '8',
                '2026-04-13T10:52:01+08:00',
                '2026-08-25T16:00:00+08:00'
            );

            insert into app.workbench_exception_cases(
                case_id, status, resolution, version, business_line, scenario, scope_month,
                row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
            ) values (
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd',
                'resolved',
                'accept_paired',
                1,
                'reconciliation_workbench',
                'workbench_anomaly_review',
                '2026-04-01',
                array[]::text[],
                array[]::text[],
                '8',
                '2026-08-25T17:01:44.700999+08:00',
                '8',
                '2026-08-25T17:01:44.700999+08:00',
                jsonb_build_object(
                    'normalized_payload',
                    jsonb_build_object(
                        'case_id', 'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd',
                        'status', 'resolved',
                        'version', 1,
                        'business_line', 'reconciliation_workbench',
                        'scenario_code', 'workbench_anomaly_review',
                        'fingerprint',
                            'e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76',
                        'group_id', 'case:CASE-BATCH-txn_imported_1453',
                        'scope_month', '2026-04',
                        'decision', 'accept_paired',
                        'note', '',
                        'detected_classification_codes', jsonb_build_array(
                            'oa_invoice_attachment_absent',
                            'oa_invoice_attachment_unassigned'
                        ),
                        'evidence_item_fingerprints', jsonb_build_array(
                            '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f',
                            '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
                            'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
                        ),
                        'row_ids', '[]'::jsonb,
                        'candidate_ids', '[]'::jsonb,
                        'updated_by', '8'
                    )
                )
            );
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    status,
                    resolution,
                    updated_by,
                    raw_payload#>>'{normalized_payload,fingerprint}',
                    raw_payload#>>'{normalized_payload,migrated_from_fingerprint}',
                    raw_payload#>>'{normalized_payload,removed_evidence_fingerprint}'
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "resolved|accept_paired|8|"
            "cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b|"
            "e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76|"
            "3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_cases
                where case_id in (
                    'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd',
                    'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba'
                );
                """,
            ),
            "2",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    latest.case_id,
                    latest.raw_payload#>>'{normalized_payload,fingerprint}',
                    latest.resolution,
                    latest.version
                )
                from app.workbench_exception_cases latest
                where latest.raw_payload#>>'{normalized_payload,group_id}' =
                      'case:CASE-BATCH-txn_imported_1453'
                order by latest.updated_at desc, latest.version desc, latest.case_id desc
                limit 1;
                """,
            ),
            "ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba|"
            "cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b|"
            "accept_paired|2",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_case_events
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba'
                  and event_type = 'workbench_anomaly_review_migrated'
                  and actor_id = 'system:migration:0154';
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
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "1",
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_pair_relations
            set updated_at = '2026-08-25T17:01:44.701000+08:00'
            where case_id = 'CASE-BATCH-txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation changed after review",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_pair_relations
            set updated_at = '2026-08-25T16:00:00+08:00'
            where case_id = 'CASE-BATCH-txn_imported_1453';
            """,
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_pair_relations
            set amount_check = jsonb_set(amount_check, '{invoice_total}', '"2411.24"'::jsonb)
            where case_id = 'CASE-BATCH-txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation changed after review",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)


if __name__ == "__main__":
    unittest.main()
