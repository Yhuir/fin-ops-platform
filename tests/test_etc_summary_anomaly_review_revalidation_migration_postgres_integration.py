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
    / "backend/src/fin_ops_platform/postgres/migrations/0155_revalidate_etc_summary_anomaly_review.sql"
).read_text(encoding="utf-8")


class ETCSummaryAnomalyReviewRevalidationMigrationPostgresIntegrationTests(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0154")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def _insert_exact_target(
        self,
        *,
        relation_updated_at: str = "2026-08-25T18:00:00+08:00",
    ) -> None:
        migrate.run_psql(
            self.database_url,
            sql=f"""
            insert into app.etc_business_batches(
                legacy_mongo_id, business_batch_id, task_id, status, scope_month,
                invoice_count, total_amount, raw_payload
            ) values (
                'etc_business_batch_hist_20260413_241125',
                'etc_business_batch_hist_20260413_241125',
                'etc_task_hist_20260413_241125',
                'manually_marked_submitted',
                '2026-04-01',
                44,
                2411.25,
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'external_etc_batch_id', 'ETC-OA-20260413-241125',
                    'invoice_ids', (
                        select jsonb_agg(format('etc-target-%s', item.index) order by item.index)
                        from generate_series(1, 44) item(index)
                    )
                ))
            );

            insert into app.etc_invoices(
                legacy_mongo_id, etc_invoice_id, invoice_no, invoice_date, scope_month,
                amount, total_with_tax, status, business_batch_id
            )
            select
                format('etc-target-%s', expected.index),
                format('etc-target-%s', expected.index),
                expected.invoice_identity,
                '2026-02-01'::date + (expected.index - 1),
                '2026-04-01',
                expected.invoice_amount,
                expected.invoice_amount,
                'submitted',
                'etc_business_batch_hist_20260413_241125'
            from (
                select
                    row_number() over (order by contract.invoice_identity)::integer as index,
                    contract.invoice_identity,
                    contract.invoice_amount
                from (values
                    ('26537910570300012469', 53.89::numeric),
                    ('26537910570300034573', 161.82::numeric),
                    ('26537910570300037123', 0.57::numeric),
                    ('26537910610300025134', 3.38::numeric),
                    ('26537910610300026148', 3.41::numeric),
                    ('26537911580200081351', 0.23::numeric),
                    ('26537911600300010886', 29.50::numeric),
                    ('26537911600300012594', 29.35::numeric),
                    ('26537911600400013372', 54.00::numeric),
                    ('26537911620400032751', 6.48::numeric),
                    ('26537911810400028656', 12.29::numeric),
                    ('26537911970200072984', 13.07::numeric),
                    ('26537911970300069262', 21.52::numeric),
                    ('26537911970300071543', 19.00::numeric),
                    ('26537911970400019801', 90.04::numeric),
                    ('26537912020300019049', 19.68::numeric),
                    ('26537912090300001908', 9.34::numeric),
                    ('26537912210300147482', 41.75::numeric),
                    ('26537912210300147687', 147.25::numeric),
                    ('26537912210300149332', 147.25::numeric),
                    ('26537912210300172102', 41.90::numeric),
                    ('26537912210300223450', 64.60::numeric),
                    ('26537912210300230280', 58.64::numeric),
                    ('26537912210300233454', 88.86::numeric),
                    ('26537912210300301090', 147.25::numeric),
                    ('26537912210300337538', 19.01::numeric),
                    ('26537912210300508970', 5.84::numeric),
                    ('26537912210300551760', 146.41::numeric),
                    ('26537912210300650404', 197.60::numeric),
                    ('26537912210300687036', 49.82::numeric),
                    ('26537912210300704407', 3.80::numeric),
                    ('26537912210300707239', 2.90::numeric),
                    ('26537912210300707639', 75.05::numeric),
                    ('26537912210300734001', 126.35::numeric),
                    ('26537912210300735000', 150.10::numeric),
                    ('26537912210400157083', 78.76::numeric),
                    ('26537912330300001801', 22.79::numeric),
                    ('26537912430200039797', 21.35::numeric),
                    ('26537912570200055449', 19.19::numeric),
                    ('26537912570300014720', 5.21::numeric),
                    ('26537912570300045985', 5.21::numeric),
                    ('26537912600300007399', 88.02::numeric),
                    ('26537912600300019970', 88.02::numeric),
                    ('26537912760300008128', 40.75::numeric)
                ) contract(invoice_identity, invoice_amount)
            ) expected;

            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-2080', 'expense_claim', '日常报销', 'oa-exp-2080',
                'active', 'completed', '刘树刚', '2026-04-10', '2026-04-01',
                2411.25, 'CNY',
                jsonb_build_object(
                    'id', 'oa-exp-2080',
                    'amount', '2411.25',
                    'workflow_status', 'completed',
                    'expense_items', jsonb_build_array(
                        jsonb_build_object(
                            'id', 'oa-exp-2080:item:0:63f422ef26de',
                            'row_index', '0',
                            'amount', '2169.68',
                            'attachment_file_count', '0'
                        ),
                        jsonb_build_object(
                            'id', 'oa-exp-2080:item:1:3b08cbfe865a',
                            'row_index', '1',
                            'amount', '241.57',
                            'attachment_file_count', '0'
                        )
                    )
                ),
                '{{}}'::jsonb
            );

            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date,
                txn_month, trade_time, summary, raw_payload, status
            ) values (
                'txn_imported_1453', '8106', '建设银行 8106', 'outflow',
                '批量账务集中处理', 2411.25, -2411.25, '2026-04-13',
                '2026-04-01', '2026-04-13T10:52:01+08:00', '报销',
                '{{}}'::jsonb, 'active'
            );

            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types,
                amount_check, special_metadata, created_by, created_at, updated_at
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
                '{{
                    "status":"matched",
                    "oa_total":"2411.25",
                    "bank_total":"2411.25",
                    "invoice_total":"2411.25",
                    "amount_delta":"0.00",
                    "external_etc_batch_id":"ETC-OA-20260413-241125",
                    "etc_batch_id":"etc_business_batch_hist_20260413_241125"
                }}'::jsonb,
                '{{}}'::jsonb,
                '8',
                '2026-04-13T10:52:01+08:00',
                '{relation_updated_at}'::timestamptz
            );
            """,
        )

    def _insert_old_decision(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_cases(
                case_id, status, resolution, version, business_line, scenario, scope_month,
                row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
            ) values (
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd',
                'resolved', 'accept_paired', 1, 'reconciliation_workbench',
                'workbench_anomaly_review', '2026-04-01', array[]::text[], array[]::text[],
                '8', '2026-08-25T17:01:44.700999+08:00',
                '8', '2026-08-25T17:01:44.700999+08:00',
                jsonb_build_object('normalized_payload', jsonb_build_object(
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
                ))
            );
            """,
        )

    def _insert_migrated_new_decision(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_cases(
                case_id, status, resolution, version, business_line, scenario, scope_month,
                row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
            ) values (
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba',
                'resolved', 'accept_paired', 2, 'reconciliation_workbench',
                'workbench_anomaly_review', '2026-04-01', array[]::text[], array[]::text[],
                '8', '2026-08-25T17:01:44.700999+08:00',
                '8', '2026-08-25T17:01:44.700999+08:00',
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'case_id', 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba',
                    'status', 'resolved',
                    'version', 2,
                    'business_line', 'reconciliation_workbench',
                    'scenario_code', 'workbench_anomaly_review',
                    'fingerprint',
                        'cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b',
                    'group_id', 'case:CASE-BATCH-txn_imported_1453',
                    'scope_month', '2026-04',
                    'decision', 'accept_paired',
                    'note', '',
                    'detected_classification_codes',
                        jsonb_build_array('oa_invoice_attachment_absent'),
                    'evidence_item_fingerprints', jsonb_build_array(
                        '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
                        'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
                    ),
                    'row_ids', '[]'::jsonb,
                    'candidate_ids', '[]'::jsonb,
                    'updated_by', '8',
                    'migration_contract', 'etc-summary-unassigned-removal-v1',
                    'migrated_by', 'system:migration:0154',
                    'migrated_from_fingerprint',
                        'e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76',
                    'removed_evidence_fingerprint',
                        '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f'
                ))
            );
            """,
        )

    def _insert_0154_migration_event(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_case_events(
                exception_case_id, case_id, event_type, actor_id,
                occurred_at, payload, raw_payload
            )
            select
                exception.id,
                exception.case_id,
                'workbench_anomaly_review_migrated',
                'system:migration:0154',
                '2026-08-25T17:01:45+08:00',
                exception.raw_payload->'normalized_payload',
                exception.raw_payload
            from app.workbench_exception_cases exception
            where exception.case_id =
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            """,
        )

    def test_0155_creates_exact_system_correction_without_claiming_generic_audit_review(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into audit.events(
                event_type, actor_id, action, page_key, operation_location,
                outcome, request_id, occurred_at, payload, raw_payload
            ) values (
                'operation.completed', '8', 'workbench.exception.review',
                'reconciliation-workbench', 'http_request', 'success',
                '95949e4f703c4aeabc4461d0db32e034',
                '2026-08-25T17:01:44.705497+08:00',
                jsonb_build_object('legacy_evidence_missing', true),
                '{}'::jsonb
            );
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|', version, updated_by, resolution,
                    raw_payload#>>'{normalized_payload,correction_contract}',
                    raw_payload#>>'{normalized_payload,detected_classification_codes,0}',
                    (not (raw_payload->'normalized_payload' ? 'prior_decision'))::text,
                    (updated_at = (
                        select updated_at from app.workbench_pair_relations
                        where case_id = 'CASE-BATCH-txn_imported_1453'
                    ) + interval '1 microsecond')::text
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "3|system:migration:0155|accept_paired|"
            "etc-summary-anomaly-targeted-revalidation-v1|"
            "oa_invoice_attachment_absent|true|true",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    jsonb_array_length(
                        raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                    ),
                    raw_payload#>>'{normalized_payload,evidence_item_fingerprints,0}',
                    raw_payload#>>'{normalized_payload,evidence_item_fingerprints,1}',
                    jsonb_array_length(raw_payload#>'{normalized_payload,evidence_contract}')
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "2|630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d|"
            "f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af|2",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_case_events
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba'
                  and event_type = 'workbench_anomaly_review_system_corrected'
                  and actor_id = 'system:migration:0155';
                """,
            ),
            "1",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from audit.events
                where event_type = 'workbench.anomaly_review.system_corrected'
                  and object_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba'
                  and actor_id = 'system:migration:0155';
                """,
            ),
            "1",
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    (select count(*) from app.workbench_exception_case_events
                     where actor_id = 'system:migration:0155'),
                    (select count(*) from audit.events
                     where actor_id = 'system:migration:0155')
                );
                """,
            ),
            "1|1",
        )

    def test_0155_revalidates_only_a_stale_exact_0154_decision(self) -> None:
        self._insert_exact_target()
        self._insert_old_decision()
        self._insert_migrated_new_decision()
        self._insert_0154_migration_event()

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|', version, updated_by,
                    raw_payload#>>'{normalized_payload,prior_decision,case_id}',
                    raw_payload#>>'{normalized_payload,prior_decision,version}',
                    raw_payload#>>'{normalized_payload,prior_decision,updated_by}',
                    (updated_at = (
                        select updated_at from app.workbench_pair_relations
                        where case_id = 'CASE-BATCH-txn_imported_1453'
                    ) + interval '1 microsecond')::text
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "3|system:migration:0155|"
            "ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba|2|8|true",
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

    def test_0155_revalidates_an_exact_old_only_decision_and_wins_latest_ordering(
        self,
    ) -> None:
        self._insert_exact_target(relation_updated_at="2026-08-25T16:00:00+08:00")
        self._insert_old_decision()

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                with ranked as (
                    select
                        case_id,
                        resolution,
                        updated_at,
                        row_number() over (
                            partition by raw_payload#>>'{normalized_payload,group_id}'
                            order by updated_at desc, version desc, case_id desc
                        ) as decision_rank
                    from app.workbench_exception_cases
                    where scenario = 'workbench_anomaly_review'
                      and raw_payload#>>'{normalized_payload,group_id}' =
                          'case:CASE-BATCH-txn_imported_1453'
                )
                select concat_ws(
                    '|',
                    case_id,
                    resolution,
                    (updated_at = (
                        select updated_at
                        from app.workbench_exception_cases
                        where case_id =
                            'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd'
                    ) + interval '1 microsecond')::text
                )
                from ranked
                where decision_rank = 1;
                """,
            ),
            "ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba|accept_paired|true",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    version,
                    updated_by,
                    raw_payload#>>'{normalized_payload,prior_decision,case_id}',
                    raw_payload#>>'{normalized_payload,prior_decision,version}'
                )
                from app.workbench_exception_cases
                where case_id =
                    'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "3|system:migration:0155|"
            "ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd|1",
        )

    def test_0155_keeps_an_exact_fresh_0154_decision_unchanged(self) -> None:
        self._insert_exact_target(relation_updated_at="2026-08-25T16:00:00+08:00")
        self._insert_old_decision()
        self._insert_migrated_new_decision()
        self._insert_0154_migration_event()

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|', version, updated_by,
                    (updated_at = timestamptz '2026-08-25T17:01:44.700999+08:00')::text
                )
                from app.workbench_exception_cases
                where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "2|8|true",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.workbench_exception_case_events
                where actor_id = 'system:migration:0155';
                """,
            ),
            "0",
        )

    def test_0155_rejects_v2_without_one_exact_0154_lineage_event(self) -> None:
        self._insert_exact_target(relation_updated_at="2026-08-25T16:00:00+08:00")
        self._insert_old_decision()
        self._insert_migrated_new_decision()

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "exact v2 migration lineage event is missing or conflicting",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self._insert_0154_migration_event()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_case_events
            set case_id = 'ANOMALY-REVIEW-DRIFTED-0154-LINEAGE'
            where actor_id = 'system:migration:0154';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "exact v2 migration lineage event is missing or conflicting",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_case_events
            set case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba'
            where actor_id = 'system:migration:0154';
            """,
        )
        self._insert_0154_migration_event()
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "exact v2 migration lineage event is missing or conflicting",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_is_a_noop_only_when_the_entire_target_is_absent(self) -> None:
        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    (select count(*) from app.workbench_exception_cases),
                    (select count(*) from app.workbench_exception_case_events),
                    (select count(*) from audit.events
                     where actor_id = 'system:migration:0155')
                );
                """,
            ),
            "0|0|0",
        )

    def test_0155_rejects_a_partial_target_when_the_relation_is_absent(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, normalized_payload, raw_payload
            ) values (
                'oa-source-2080', 'expense_claim', 'oa-exp-2080', 'active',
                '{}'::jsonb, '{}'::jsonb
            );
            """,
        )

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_relation_absence_rejects_orphan_decision_events_and_audit(
        self,
    ) -> None:
        orphan_events = (
            (
                "ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd",
                "workbench_anomaly_reviewed",
                "8",
            ),
            (
                "ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba",
                "workbench_anomaly_review_migrated",
                "system:migration:0154",
            ),
            (
                "ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba",
                "workbench_anomaly_review_system_corrected",
                "system:migration:0155",
            ),
        )
        for case_id, event_type, actor_id in orphan_events:
            migrate.run_psql(
                self.database_url,
                sql=f"""
                insert into app.workbench_exception_case_events(
                    case_id, event_type, actor_id, payload, raw_payload
                ) values (
                    '{case_id}', '{event_type}', '{actor_id}',
                    jsonb_build_object('case_id', '{case_id}'),
                    jsonb_build_object(
                        'normalized_payload',
                        jsonb_build_object('case_id', '{case_id}')
                    )
                );
                """,
            )
            with self.subTest(event_type=event_type), self.assertRaisesRegex(
                migrate.MigrationError,
                "target ETC relation is missing while target state partially exists",
            ):
                migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
            migrate.run_psql(
                self.database_url,
                sql=f"""
                delete from app.workbench_exception_case_events
                where case_id = '{case_id}'
                  and event_type = '{event_type}';
                """,
            )

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into audit.events(
                event_type, object_type, object_id, actor_id, action,
                outcome, request_id, payload, raw_payload
            ) values (
                'workbench.anomaly_review.system_corrected',
                'workbench_exception_case',
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba',
                'system:migration:0155',
                'workbench.exception.review.system_correction',
                'success', 'migration:0155:CASE-BATCH-txn_imported_1453',
                '{}'::jsonb, '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_relation_absence_rejects_each_runtime_and_history_anchor(
        self,
    ) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            with inserted_invoice as (
                insert into app.invoices(
                    legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                    invoice_month, amount, signed_amount, total_with_tax,
                    status, raw_payload
                ) values (
                    'orphan-active-link-invoice', 'input', 'ORPHAN-LINK-001',
                    '2026-03-31', '2026-03-01', 1.00, 1.00, 1.00,
                    'active', '{}'::jsonb
                )
                returning id
            )
            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key,
                link_status, link_source, confidence
            )
            select
                'ETC-OA-20260413-241125', id, 'orphan-link:001',
                'active', 'migration-0155-test', 'strict'
            from inserted_invoice;
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.etc_batch_invoice_links
            set link_status = 'removed'
            where business_batch_id = 'ETC-OA-20260413-241125';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            delete from app.etc_batch_invoice_links
            where business_batch_id = 'ETC-OA-20260413-241125';
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 orphan active-link cleanup',
                false
            );
            delete from app.invoices
            where legacy_mongo_id = 'orphan-active-link-invoice';
            """,
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.etc_submission_batches(
                submission_batch_id, status, scope_month, raw_payload
            ) values (
                'ETC-OA-20260413-241125', 'draft', '2026-04-01', '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            delete from app.etc_submission_batches
            where submission_batch_id = 'ETC-OA-20260413-241125';
            """,
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax,
                workbench_visibility, status, raw_payload
            ) values (
                'orphan-runtime-invoice', 'input', 'ORPHAN-RUNTIME-001',
                '2026-03-31', '2026-03-01', 1.00, 1.00, 1.00,
                'hidden_after_etc_submission', 'active',
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'etc_submission_batch_id', 'ETC-OA-20260413-241125',
                    'etc_submission_status', 'submitted'
                ))
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 orphan runtime invoice cleanup',
                false
            );
            delete from app.invoices
            where legacy_mongo_id = 'orphan-runtime-invoice';
            """,
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope,
                row_ids, row_types, amount_check, special_metadata
            ) values (
                'CASE-FOREIGN-ETC-MARKER-RESIDUE', 'manual_confirmed',
                'active', '2026-04-01',
                array['unrelated-row']::text[], array['bank']::text[],
                jsonb_build_object(
                    'external_etc_batch_id', 'ETC-OA-20260413-241125'
                ),
                '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            delete from app.workbench_pair_relations
            where case_id = 'CASE-FOREIGN-ETC-MARKER-RESIDUE';
            """,
        )

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_pair_relation_history(
                case_id, event_type, actor_id, before_payload, after_payload
            ) values (
                'CASE-BATCH-txn_imported_1453', 'relation_confirmed',
                'migration-0155-test', '{}'::jsonb, '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation is missing while target state partially exists",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_canonical_etc_summary_count_and_amount_drift(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.etc_business_batches
            set invoice_count = 43
            where business_batch_id = 'etc_business_batch_hist_20260413_241125';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target canonical ETC summary differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_fixed_contract_drift_with_unchanged_count_and_total(
        self,
    ) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.etc_invoices
            set amount = amount - 10.00,
                total_with_tax = total_with_tax - 10.00
            where etc_invoice_id = 'etc-target-1';

            update app.etc_invoices
            set amount = amount + 10.00,
                total_with_tax = total_with_tax + 10.00
            where etc_invoice_id = 'etc-target-2';
            """,
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws(
                    '|',
                    count(*),
                    to_char(round(sum(total_with_tax), 2), 'FM999999999999999999990.00')
                )
                from app.etc_invoices
                where business_batch_id = 'etc_business_batch_hist_20260413_241125';
                """,
            ),
            "44|2411.25",
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "runtime preferred ETC summary differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_missing_or_drifted_canonical_bank_transaction(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 bank contract negative test',
                false
            );
            delete from app.bank_transactions
            where legacy_mongo_id = 'txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target bank transaction identity is not unique",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            ) values (
                'txn_imported_1453', '8106', 'outflow', '批量账务集中处理',
                2411.25, -2411.25, '2026-04-13', '2026-04-01', 'active'
            );
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 bank amount drift test',
                false
            );
            update app.bank_transactions
            set amount = 2411.24
            where legacy_mongo_id = 'txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target bank transaction differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 bank direction drift test',
                false
            );
            update app.bank_transactions
            set amount = 2411.25, txn_direction = 'inflow'
            where legacy_mongo_id = 'txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target bank transaction differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            select set_config(
                'fin_ops.correction_reason',
                'migration 0155 bank scope drift test',
                false
            );
            update app.bank_transactions
            set txn_direction = 'outflow',
                txn_date = '2026-05-13',
                txn_month = '2026-05-01'
            where legacy_mongo_id = 'txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target bank transaction differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_an_active_link_that_changes_runtime_preferred_totals(
        self,
    ) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            with inserted_invoice as (
                insert into app.invoices(
                    legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                    invoice_date, invoice_month, amount, signed_amount,
                    total_with_tax, status, raw_payload
                ) values (
                    'runtime-extra-target-invoice', 'input', 'RUNTIME-EXTRA-001',
                    'RUNTIME-EXTRA-001', '2026-03-31', '2026-03-01',
                    0.01, 0.01, 0.01, 'active', '{}'::jsonb
                )
                returning id
            )
            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key, digital_invoice_no,
                link_status, link_source, confidence
            )
            select
                'etc_business_batch_hist_20260413_241125', id,
                'digital:RUNTIME-EXTRA-001', 'RUNTIME-EXTRA-001',
                'active', 'test', 'strict'
            from inserted_invoice;
            """,
        )

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "runtime preferred ETC summary differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_count_and_total_preserving_preferred_source_drift(
        self,
    ) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax,
                status, source_links, raw_payload
            )
            select
                'runtime-tier1-override-1', 'input', invoice.invoice_no,
                invoice.invoice_date, date_trunc('month', invoice.invoice_date)::date,
                invoice.amount - 10.00,
                invoice.amount - 10.00,
                coalesce(invoice.total_with_tax, invoice.amount) - 10.00,
                'active', '[]'::jsonb, '{}'::jsonb
            from app.etc_invoices invoice
            where invoice.etc_invoice_id = 'etc-target-1';

            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax,
                status, source_links, raw_payload
            )
            select
                'runtime-tier1-override-2', 'input', invoice.invoice_no,
                invoice.invoice_date, date_trunc('month', invoice.invoice_date)::date,
                invoice.amount + 10.00,
                invoice.amount + 10.00,
                coalesce(invoice.total_with_tax, invoice.amount) + 10.00,
                'active', '[]'::jsonb, '{}'::jsonb
            from app.etc_invoices invoice
            where invoice.etc_invoice_id = 'etc-target-2';

            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key,
                link_status, link_source, confidence, raw_payload
            )
            select
                'etc_business_batch_hist_20260413_241125', invoice.id,
                'runtime-tier1:' || invoice.legacy_mongo_id,
                'active', 'migration-0155-test', 'strict', '{}'::jsonb
            from app.invoices invoice
            where invoice.legacy_mongo_id in (
                'runtime-tier1-override-1',
                'runtime-tier1-override-2'
            );
            """,
        )

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "runtime preferred ETC summary differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_allows_equivalent_preferred_source_override(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            with inserted_invoice as (
                insert into app.invoices(
                    legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                    invoice_month, amount, signed_amount, total_with_tax,
                    status, source_links, raw_payload
                )
                select
                    'runtime-tier1-equivalent', 'input', invoice.invoice_no,
                    invoice.invoice_date,
                    date_trunc('month', invoice.invoice_date)::date,
                    invoice.amount, invoice.amount,
                    coalesce(invoice.total_with_tax, invoice.amount),
                    'active', '[]'::jsonb, '{}'::jsonb
                from app.etc_invoices invoice
                where invoice.etc_invoice_id = 'etc-target-1'
                returning id
            )
            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key,
                link_status, link_source, confidence, raw_payload
            )
            select
                'etc_business_batch_hist_20260413_241125', id,
                'runtime-tier1:equivalent', 'active',
                'migration-0155-test', 'strict', '{}'::jsonb
            from inserted_invoice;
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws('|', version, updated_by, resolution)
                from app.workbench_exception_cases
                where case_id =
                    'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "3|system:migration:0155|accept_paired",
        )

    def test_0155_matches_runtime_tiering_when_only_submission_source_is_extra(
        self,
    ) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.etc_submission_batches(
                submission_batch_id, status, scope_month, raw_payload
            ) values (
                'SUBMISSION-LOWER-TIER-EXTRA', 'submitted', '2026-04-01',
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'etc_batch_id', 'ETC-OA-20260413-241125'
                ))
            );
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date, invoice_month, amount, signed_amount,
                total_with_tax, workbench_visibility, status, raw_payload
            ) values (
                'submission-lower-tier-extra', 'input', 'SUBMISSION-EXTRA-001',
                'SUBMISSION-EXTRA-001', '2026-03-31', '2026-03-01',
                999.00, 999.00, 999.00, 'hidden_after_etc_submission', 'active',
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'etc_submission_batch_id', 'SUBMISSION-LOWER-TIER-EXTRA',
                    'etc_submission_status', 'submitted'
                ))
            );
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws('|', version, updated_by, resolution)
                from app.workbench_exception_cases
                where case_id =
                    'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
                """,
            ),
            "3|system:migration:0155|accept_paired",
        )

    def test_0155_rejects_old_v1_and_fresh_v2_generated_contract_drift(self) -> None:
        self._insert_exact_target(relation_updated_at="2026-08-25T16:00:00+08:00")
        self._insert_old_decision()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload, '{normalized_payload,version}', '2'::jsonb
            )
            where case_id =
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "old ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload, '{normalized_payload,version}', '1'::jsonb
            )
            where case_id =
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
            """,
        )
        self._insert_migrated_new_decision()
        self._insert_0154_migration_event()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,scenario_code}',
                '"workbench_other_review"'::jsonb
            )
            where case_id =
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "current ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_old_v1_table_and_normalized_array_drift(self) -> None:
        self._insert_exact_target()
        self._insert_old_decision()

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set business_line = 'other_business_line'
            where case_id =
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "old ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set business_line = 'reconciliation_workbench',
                row_ids = array['unexpected-row']::text[]
            where case_id =
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "old ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set row_ids = array[]::text[],
                raw_payload = jsonb_set(
                    raw_payload,
                    '{normalized_payload,candidate_ids}',
                    '["unexpected-candidate"]'::jsonb
                )
            where case_id =
                'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "old ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_fresh_v3_generated_contract_and_audit_drift(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,target_relation_case_id}',
                '"CASE-BATCH-WRONG"'::jsonb
            )
            where case_id =
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "current ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,target_relation_case_id}',
                '"CASE-BATCH-txn_imported_1453"'::jsonb
            )
            where case_id =
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            truncate table audit.events;
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "exact v3 decision has incomplete or conflicting system correction audit",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_correction_event_collision_by_target_decision_uuid(
        self,
    ) -> None:
        self._insert_exact_target()
        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_case_events(
                exception_case_id, case_id, event_type, actor_id,
                payload, raw_payload
            )
            select
                exception.id,
                'ANOMALY-REVIEW-DRIFTED-CORRECTION-EVENT',
                'workbench_anomaly_review_system_corrected',
                'drifted-system-actor',
                '{}'::jsonb,
                '{}'::jsonb
            from app.workbench_exception_cases exception
            where exception.case_id =
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            """,
        )

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "exact v3 decision has incomplete or conflicting system correction audit",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_orphaned_system_event_or_audit_before_writing(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.workbench_exception_case_events(
                case_id, event_type, actor_id, payload, raw_payload
            ) values (
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba',
                'workbench_anomaly_review_system_corrected',
                'system:migration:0155', '{}'::jsonb, '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "system correction audit exists without the target decision",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        migrate.run_psql(
            self.database_url,
            sql="""
            delete from app.workbench_exception_case_events
            where actor_id = 'system:migration:0155';
            insert into audit.events(
                event_type, object_type, object_id, actor_id, action,
                outcome, request_id, payload, raw_payload
            ) values (
                'workbench.anomaly_review.system_corrected',
                'workbench_exception_case',
                'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba',
                'system:migration:0155',
                'workbench.exception.review.system_correction', 'success',
                'migration:0155:CASE-BATCH-txn_imported_1453',
                '{}'::jsonb, '{}'::jsonb
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "system correction audit exists without the target decision",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_canonical_invoice_contract_drift(self) -> None:
        self._insert_exact_target()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.etc_business_batches
            set invoice_count = 44
            where business_batch_id = 'etc_business_batch_hist_20260413_241125';

            update app.etc_invoices
            set total_with_tax = total_with_tax + 0.01
            where etc_invoice_id = 'etc-target-1';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target canonical ETC summary differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_a_current_decision_fingerprint_drift(self) -> None:
        self._insert_exact_target()
        self._insert_migrated_new_decision()
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_exception_cases
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,fingerprint}',
                to_jsonb(repeat('f', 64))
            )
            where case_id = 'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
            """,
        )

        with self.assertRaisesRegex(
            migrate.MigrationError,
            "current ETC anomaly review decision conflicts with the authorized correction",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

    def test_0155_rejects_relation_evidence_and_decision_conflicts(self) -> None:
        self._insert_exact_target()

        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_pair_relations
            set amount_check = jsonb_set(
                amount_check,
                '{external_etc_batch_id}',
                '"ETC-WRONG"'::jsonb
            )
            where case_id = 'CASE-BATCH-txn_imported_1453';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target ETC relation differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.workbench_pair_relations
            set amount_check = jsonb_set(
                amount_check,
                '{external_etc_batch_id}',
                '"ETC-OA-20260413-241125"'::jsonb
            )
            where case_id = 'CASE-BATCH-txn_imported_1453';

            update app.oa_applications
            set normalized_payload = jsonb_set(
                normalized_payload,
                '{expense_items,0,amount}',
                '"2169.67"'::jsonb
            )
            where row_id = 'oa-exp-2080';
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "target OA evidence differs from the authorized correction contract",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)
        migrate.run_psql(
            self.database_url,
            sql="""
            update app.oa_applications
            set normalized_payload = jsonb_set(
                normalized_payload,
                '{expense_items,0,amount}',
                '"2169.68"'::jsonb
            )
            where row_id = 'oa-exp-2080';

            insert into app.workbench_exception_cases(
                case_id, status, resolution, version, business_line, scenario,
                scope_month, updated_by, raw_payload
            ) values (
                'ANOMALY-REVIEW-CONFLICTING-TARGET-GROUP',
                'resolved', 'keep_unpaired', 1, 'reconciliation_workbench',
                'workbench_anomaly_review', '2026-04-01', 'conflicting-reviewer',
                jsonb_build_object('normalized_payload', jsonb_build_object(
                    'fingerprint', repeat('a', 64),
                    'group_id', 'case:CASE-BATCH-txn_imported_1453',
                    'decision', 'keep_unpaired'
                ))
            );
            """,
        )
        with self.assertRaisesRegex(
            migrate.MigrationError,
            "another current decision exists for the target ETC group",
        ):
            migrate.run_psql(self.database_url, sql=MIGRATION_SQL)


if __name__ == "__main__":
    unittest.main()
