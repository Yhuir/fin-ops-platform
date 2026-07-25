from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_projection_audit import (
    workbench_etc_relation_integrity_issues,
)
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


EXTERNAL_BATCH_ID = "etc_20260622_001"
BUSINESS_BATCH_ID = "etc_business_batch_0014"
OA_ROW_ID = "oa-etc-0014"
CASE_ID = "case:etc-0014"


class WorkbenchEtcRelationEnrichmentPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        truncate_test_database(self.database_url)

    def test_exact_candidate_transaction_validation_and_audit_owner_proof(self) -> None:
        self._seed_exact_etc_relation()
        repository = PostgresWorkbenchFormalRelationFactRepository(self.connection)

        fact_batch = repository.load_batch(["2026-06"])
        candidates = repository.load_etc_batch_link_candidates(["2026-06"])

        fact_member_keys = {fact.member_key for fact in fact_batch.facts}
        self.assertIn(("oa", OA_ROW_ID), fact_member_keys)
        self.assertNotIn(("bank", "txn-claimed"), fact_member_keys)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["external_etc_batch_id"], EXTERNAL_BATCH_ID)
        self.assertEqual(candidates[0]["business_batch_id"], BUSINESS_BATCH_ID)
        self.assertEqual(candidates[0]["invoice_count"], 34)
        self.assertEqual(candidates[0]["total_amount"], "1584.350000")
        self.assertEqual(candidates[0]["scope_keys"], ["2026-06"])

        with self.connection.transaction() as transaction:
            transactional_repository = PostgresWorkbenchFormalRelationFactRepository(transaction)
            validation = transactional_repository.validate_etc_batch_links(
                [{**candidates[0], "case_id": CASE_ID}]
            )
        self.assertEqual(validation, {"valid": True, "issues": []})

        before_codes = {
            issue.code
            for issue in workbench_etc_relation_integrity_issues(
                self.connection,
                tenant_id="default",
                limit=20,
            )
        }
        self.assertIn("workbench_etc_relation_expected_owner_mismatch", before_codes)

        self.connection.execute(
            """
            update app.workbench_pair_relations
            set special_metadata = jsonb_build_object(
                    'etc_batch_link',
                    jsonb_build_object(
                        'external_etc_batch_id', %s::text,
                        'business_batch_id', %s::text,
                        'oa_row_id', %s::text,
                        'invoice_count', 34,
                        'total_amount', '1584.35'
                    )
                )
            where case_id = %s
            """,
            (EXTERNAL_BATCH_ID, BUSINESS_BATCH_ID, OA_ROW_ID, CASE_ID),
        )
        after_codes = {
            issue.code
            for issue in workbench_etc_relation_integrity_issues(
                self.connection,
                tenant_id="default",
                limit=20,
            )
        }
        self.assertNotIn("workbench_etc_relation_expected_owner_mismatch", after_codes)
        self.assertNotIn("workbench_etc_relation_unique_owner_mismatch", after_codes)

        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types, special_metadata
            )
            values (%s, 'manual_confirmed', 'active', '2026-06-01', array['oa-other'], array['oa'], %s::jsonb)
            """,
            (
                "case:other-owner",
                json.dumps({"etc_batch_link": {"external_etc_batch_id": EXTERNAL_BATCH_ID}}),
            ),
        )
        duplicate_codes = {
            issue.code
            for issue in workbench_etc_relation_integrity_issues(
                self.connection,
                tenant_id="default",
                limit=20,
            )
        }
        self.assertIn("workbench_etc_relation_unique_owner_mismatch", duplicate_codes)

    def test_urgent_dirty_event_expedites_and_reschedules_processing_scope(self) -> None:
        repository = PostgresReadModelRepository(self.connection)
        repository.mark_workbench_matching_dirty_scopes(
            tenant_id="default",
            scope_months=["2026-06"],
            reason="ordinary",
            source_versions={"proof": "v1"},
            debounce_seconds=60,
        )
        delayed = self.connection.fetch_one(
            """
            select extract(epoch from (available_at - now())) as delay_seconds
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default' and scope_month = '2026-06-01'
            """
        )
        self.assertGreater(float(delayed["delay_seconds"]), 50)

        repository.mark_workbench_matching_dirty_scopes(
            tenant_id="default",
            scope_months=["2026-06"],
            reason="urgent",
            source_versions={"proof": "v2"},
            debounce_seconds=0,
        )
        claimed = repository.claim_workbench_matching_dirty_scopes(
            tenant_id="default",
            worker_id="test-worker",
            limit=1,
            lease_seconds=60,
            request_id="test-run",
        )
        self.assertEqual(claimed, ["2026-06"])

        repository.mark_workbench_matching_dirty_scopes(
            tenant_id="default",
            scope_months=["2026-06"],
            reason="changed-during-processing",
            source_versions={"proof": "v3"},
            debounce_seconds=0,
        )
        processing = self.connection.fetch_one(
            """
            select status, lease_owner,
                   coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false) as refresh_again
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default' and scope_month = '2026-06-01'
            """
        )
        self.assertEqual(processing["status"], "processing")
        self.assertEqual(processing["lease_owner"], "test-worker")
        self.assertTrue(processing["refresh_again"])

        repository.complete_workbench_matching_dirty_scope(
            tenant_id="default",
            scope_month="2026-06",
            source_versions={"proof": "v3"},
            worker_id="test-worker",
            request_id="test-run:2026-06",
        )
        completed = self.connection.fetch_one(
            """
            select status, available_at <= now() as due,
                   raw_payload ? 'refresh_requested_while_processing' as refresh_flag_present
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default' and scope_month = '2026-06-01'
            """
        )
        self.assertEqual(completed["status"], "dirty")
        self.assertTrue(completed["due"])
        self.assertFalse(completed["refresh_flag_present"])

        self.connection.execute(
            """
            update job.workbench_matching_dirty_scopes
            set status = 'failed', source_versions = '{"proof":"v1"}'::jsonb
            where tenant_id = 'default' and scope_month = '2026-06-01'
            """
        )
        requeued = repository.mark_stale_workbench_matching_completed_scopes(
            tenant_id="default",
            source_versions={"proof": "v2"},
            reason="matching_source_versions_changed",
            debounce_seconds=0,
            limit=10,
        )
        recovered = self.connection.fetch_one(
            """
            select status, available_at <= now() as due
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default' and scope_month = '2026-06-01'
            """
        )
        self.assertEqual(requeued, ["2026-06"])
        self.assertEqual(recovered["status"], "dirty")
        self.assertTrue(recovered["due"])

    def test_hot_path_indexes_are_applied(self) -> None:
        rows = self.connection.fetch_all(
            """
            select indexname
            from pg_indexes
            where schemaname = 'app'
              and indexname = any(%s::text[])
            order by indexname
            """,
            (
                [
                    "oa_applications_etc_batch_marker_idx",
                    "etc_business_batches_external_scope_idx",
                    "workbench_pair_relations_active_etc_link_idx",
                    "bank_transactions_workbench_identity_idx",
                    "invoices_workbench_identity_idx",
                ],
            ),
        )
        self.assertEqual(
            [row["indexname"] for row in rows],
            [
                "bank_transactions_workbench_identity_idx",
                "etc_business_batches_external_scope_idx",
                "invoices_workbench_identity_idx",
                "oa_applications_etc_batch_marker_idx",
                "workbench_pair_relations_active_etc_link_idx",
            ],
        )
        privilege = self.connection.fetch_one(
            """
            select has_table_privilege(
                'fin_ops_app_runtime',
                'app.workbench_idempotency_records',
                'SELECT,INSERT,UPDATE'
            ) as allowed
            """
        )
        self.assertTrue(privilege["allowed"])

    def test_workbench_canonical_proof_tracks_etc_and_deleted_fact_changes(self) -> None:
        invoice = self.connection.fetch_one(
            """
            insert into app.invoices(
                invoice_type, invoice_no, invoice_month, amount, signed_amount, status
            )
            values ('input', 'WB-PROOF-INV', '2026-06-01', 100, 100, 'active')
            returning id
            """
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            )
            values (
                'wb-proof-bank', '6222', 'outflow', 'proof',
                100, -100, '2026-06-15', '2026-06-01', 'active'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.etc_submission_batches(
                submission_batch_id, status, scope_month, invoice_ids
            )
            values ('wb-proof-submission', 'submitted', '2026-06-01', array['wb-proof-etc'])
            """
        )
        self.connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count, total_amount, raw_payload
            )
            values (
                'wb-proof-business', 'oa_submitted', '2026-06-01', 1, 100,
                '{"normalized_payload":{"invoice_ids":["wb-proof-etc"]}}'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, invoice_no, invoice_date, scope_month,
                amount, total_with_tax, status, business_batch_id
            )
            values (
                'wb-proof-etc', 'WB-PROOF-ETC', '2026-06-15', '2026-06-01',
                100, 100, 'active', 'wb-proof-business'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.etc_batch_invoice_links(
                business_batch_id, etc_invoice_id, invoice_id, identity_key,
                link_status, link_source, confidence
            )
            values (
                'wb-proof-business', 'wb-proof-etc', %s, 'wb-proof-link',
                'active', 'test', 'strict'
            )
            """,
            (invoice["id"],),
        )

        builder = WorkbenchSqlProjectionBuilder(connection=self.connection)
        before = builder.source_versions_for_scope("2026-06")
        updates = (
            ("app.etc_submission_batches", "submission_batch_id = 'wb-proof-submission'", "etc_submission_batches_updated_at"),
            ("app.etc_business_batches", "business_batch_id = 'wb-proof-business'", "etc_business_batches_updated_at"),
            ("app.etc_invoices", "etc_invoice_id = 'wb-proof-etc'", "etc_invoices_updated_at"),
            ("app.etc_batch_invoice_links", "identity_key = 'wb-proof-link'", "etc_batch_invoice_links_updated_at"),
        )
        for table_name, predicate, proof_key in updates:
            self.connection.execute(
                f"update {table_name} set updated_at = updated_at + interval '1 second' where {predicate}"
            )
            after = builder.source_versions_for_scope("2026-06")
            self.assertNotEqual(before[proof_key], after[proof_key])
            before = after

        self.connection.execute(
            """
            update app.bank_transactions
            set status = 'deleted', updated_at = updated_at + interval '1 second'
            where legacy_mongo_id = 'wb-proof-bank'
            """
        )
        after_bank_delete = builder.source_versions_for_scope("2026-06")
        self.assertNotEqual(
            before["bank_transactions_updated_at"],
            after_bank_delete["bank_transactions_updated_at"],
        )

        self.connection.execute(
            """
            update app.invoices
            set status = 'deleted', updated_at = updated_at + interval '1 second'
            where id = %s
            """,
            (invoice["id"],),
        )
        after_invoice_delete = builder.source_versions_for_scope("2026-06")
        self.assertNotEqual(
            after_bank_delete["invoices_updated_at"],
            after_invoice_delete["invoices_updated_at"],
        )

    def test_cross_month_relation_proof_tracks_member_and_withdrawal_changes(self) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            )
            values (
                'wb-proof-cross-bank', '6222', 'outflow', 'proof',
                100, -100, '2026-05-15', '2026-05-01', 'active'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_month,
                amount, signed_amount, status
            )
            values (
                'wb-proof-cross-invoice', 'input', 'WB-PROOF-CROSS',
                '2026-06-01', 100, 100, 'active'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types
            )
            values (
                'wb-proof-cross-relation', 'manual_confirmed', 'active', '2026-05-01',
                array['wb-proof-cross-bank', 'wb-proof-cross-invoice'],
                array['bank', 'invoice']
            )
            """
        )

        builder = WorkbenchSqlProjectionBuilder(connection=self.connection)
        before = builder.source_versions_for_scopes(["2026-05", "2026-06"])
        self.connection.execute(
            """
            update app.bank_transactions
            set updated_at = updated_at + interval '1 second'
            where legacy_mongo_id = 'wb-proof-cross-bank'
            """
        )
        after_member_change = builder.source_versions_for_scopes(["2026-05", "2026-06"])
        for scope_key in ("2026-05", "2026-06"):
            self.assertNotEqual(
                before[scope_key]["bank_transactions_updated_at"],
                after_member_change[scope_key]["bank_transactions_updated_at"],
                msg=scope_key,
            )

        self.connection.execute(
            """
            update app.workbench_pair_relations
            set status = 'withdrawn', updated_at = updated_at + interval '1 second'
            where case_id = 'wb-proof-cross-relation'
            """
        )
        after_withdrawal = builder.source_versions_for_scopes(["2026-05", "2026-06"])
        for scope_key in ("2026-05", "2026-06"):
            self.assertNotEqual(
                after_member_change[scope_key]["workbench_pair_relations_updated_at"],
                after_withdrawal[scope_key]["workbench_pair_relations_updated_at"],
                msg=scope_key,
            )

    def test_workbench_canonical_proof_tracks_only_consumed_bank_settings(self) -> None:
        self.connection.execute(
            """
            insert into app.app_settings(settings_key, settings_payload)
            values (
                'app_settings',
                '{
                  "bank_transaction_tags":{"version":7},
                  "bank_account_mappings":[{"bank_name":"甲银行","last4":"6222"}],
                  "layout":{"density":"compact"}
                }'::jsonb
            )
            """
        )
        builder = WorkbenchSqlProjectionBuilder(connection=self.connection)
        before = builder.source_versions_for_scope("2026-06")

        self.connection.execute(
            """
            update app.app_settings
            set settings_payload = jsonb_set(
                  settings_payload,
                  '{bank_account_mappings}',
                  '[{"bank_name":"乙银行","last4":"6222"}]'::jsonb
                ),
                updated_at = updated_at + interval '1 second'
            where settings_key = 'app_settings'
            """
        )
        after_mapping = builder.source_versions_for_scope("2026-06")

        self.assertEqual(before["bank_auto_tag_rules_version"], 7)
        self.assertEqual(after_mapping["bank_auto_tag_rules_version"], 7)
        self.assertNotEqual(
            before["bank_account_mappings_fingerprint"],
            after_mapping["bank_account_mappings_fingerprint"],
        )

        self.connection.execute(
            """
            update app.app_settings
            set settings_payload = jsonb_set(
                  settings_payload,
                  '{layout,density}',
                  '"comfortable"'::jsonb
                ),
                updated_at = updated_at + interval '1 second'
            where settings_key = 'app_settings'
            """
        )
        after_unrelated_setting = builder.source_versions_for_scope("2026-06")

        self.assertEqual(
            after_mapping["bank_account_mappings_fingerprint"],
            after_unrelated_setting["bank_account_mappings_fingerprint"],
        )
        self.assertEqual(
            after_mapping["bank_auto_tag_rules_version"],
            after_unrelated_setting["bank_auto_tag_rules_version"],
        )

    def _seed_exact_etc_relation(self) -> None:
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, row_id, status, workflow_status,
                application_date, scope_month, amount, currency, normalized_payload
            )
            values (
                'oa-source', 'oa-form-0014', %s, 'active', 'completed',
                '2026-06-22', '2026-06-01', 1584.35, 'CNY', %s::jsonb
            )
            """,
            (OA_ROW_ID, json.dumps({"etc_batch_id": EXTERNAL_BATCH_ID})),
        )
        self.connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count, total_amount, raw_payload
            )
            values (%s, 'oa_submitted', '2026-06-01', 34, 1584.35, %s::jsonb)
            """,
            (
                BUSINESS_BATCH_ID,
                json.dumps(
                    {
                        "normalized_payload": {
                            "external_etc_batch_id": EXTERNAL_BATCH_ID,
                            "submission_batch_id": "etc_submission_0014",
                        }
                    }
                ),
            ),
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types
            )
            values (
                %s, 'manual_confirmed', 'active', '2026-06-01',
                array[%s, 'bank-etc-0014'], array['oa', 'bank']
            )
            """,
            (CASE_ID, OA_ROW_ID),
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status, raw_payload
            ) values (
                'txn-claimed', '6222', 'outflow', '已被批次占用',
                10, -10, '2026-06-22', '2026-06-01', 'active', '{}'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types
            ) values (
                'no_oa_batch_claimed', 'bank_flow_rule_batch', 'active', '2026-06-01',
                array['txn-claimed'], array['bank']
            )
            """
        )


if __name__ == "__main__":
    unittest.main()
