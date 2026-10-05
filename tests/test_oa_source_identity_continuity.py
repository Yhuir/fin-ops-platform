from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.oa_attachment_invoice_cache import ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord
from fin_ops_platform.services.oa_source_identity import OASourceIdentities, OASourceIdentityConflict
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_source_identity import PostgresOASourceIdentityRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.test_mongo_oa_adapter import MemoryAttachmentInvoiceCache, StubMongoOAAdapter


def payment_document() -> dict:
    return {"_id": "source-document", "form_id": 2, "data": {
        "processId": "original-process", "processStatus": 1, "status": "IN_PROGRESS",
        "applicationDate": "2026-09-15", "amount": "1711.33", "userName": "test",
        "cause": "ETC", "beneficiary": "test supplier",
    }}


class OASourceIdentityContinuityTests(unittest.TestCase):
    def test_new_document_identity_survives_both_optional_identifiers(self):
        doc = payment_document()
        doc["data"].pop("processId")
        adapter = StubMongoOAAdapter(form_documents={"2": [doc]}, project_documents=[])
        adapter._identity_loader = OASourceIdentities
        ids = []
        for fields in ({}, {"processId": "new-process"}, {"flowRequestId": 2496, "processStatus": 2}):
            doc["data"].update(fields)
            ids.append(adapter.load_sync_application_batch("all").admission_records[0].id)
        self.assertEqual(ids, ["oa-pay-source-document"] * 3)

    def test_existing_document_uses_one_owner_and_rejects_conflicting_alias(self):
        identities = OASourceIdentities(owners={"oa-pay-doc": "oa-pay-old"})
        self.assertEqual(identities.canonical_id("oa-pay-doc"), "oa-pay-old")
        identities.aliases["oa-pay-doc"] = "oa-pay-other"
        with self.assertRaises(OASourceIdentityConflict):
            identities.canonical_id("oa-pay-doc")

    def test_targeted_source_lookup_keeps_process_identity_after_request_number_added(self):
        doc = payment_document()
        doc["data"]["flowRequestId"] = 2496
        adapter = StubMongoOAAdapter(form_documents={}, project_documents=[])
        with patch.object(adapter, "_find_documents", return_value=[doc]):
            result = MongoOAAdapter._load_form_documents_by_external_ids(adapter, "2", {"original-process"})
        self.assertEqual(result, [doc])

    def test_expense_completion_preserves_items_artifacts_and_cached_invoice_without_ocr(self):
        doc = {"_id": "expense-doc", "form_id": 32, "data": {
            "processId": "expense-process", "processStatus": 1, "status": "IN_PROGRESS",
            "ApplicationDate": "2026-09-15", "userName": "test", "amount": "60",
            "schedule": [{"detailReimbursementAmount": "60", "feeContent": "transport",
                          "detailReimbursementAttachment": {"files": [{"filePath": "/test.pdf", "fileName": "test.pdf"}]}}],
        }}
        cache = MemoryAttachmentInvoiceCache()
        adapter = StubMongoOAAdapter(form_documents={"32": [doc]}, project_documents=[], attachment_invoice_cache=cache)
        initial = adapter.load_sync_application_batch("all").admission_records[0]
        item = initial.expense_items[0]
        files = adapter._attachment_files_with_source_context(
            adapter._attachment_files(doc["data"]["schedule"][0]),
            oa_external_id="expense-process", source_expense_row_index="0", source_expense_item_id=item["expense_item_id"],
        )
        self.assertEqual(len(files), 1)
        evidence = adapter._normalize_parsed_attachment_invoice(
            {"invoice_no": "12345678901234567890", "amount": "60", "price_tax_total": "60"}, file_entry=files[0],
        )
        cache.entries[adapter._attachment_invoice_cache_key(files[0])] = {
            "cache_schema_version": ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
            "parser_version": adapter._attachment_invoice_cache_parser_version(),
            "evidences": [evidence], "invoices": [evidence],
            "artifacts": [adapter._attachment_artifact_for_file(files[0], evidences=[evidence])],
        }
        before = adapter.load_sync_application_batch("all").admission_records[0]
        doc["data"].update(flowRequestId=2495, processStatus=2, status="COMPLETED")
        with patch.object(adapter, "_parse_attachment_invoice_files_now", side_effect=AssertionError("unexpected OCR")):
            after = adapter.load_sync_application_batch("all").admission_records[0]
        self.assertEqual(after.id, before.id)
        self.assertEqual(after.workflow_status, "completed")
        self.assertTrue(before.attachment_artifacts)
        self.assertTrue(before.attachment_evidences)
        self.assertEqual(after.expense_items, before.expense_items)
        self.assertEqual(after.attachment_artifacts, before.attachment_artifacts)
        self.assertEqual(after.attachment_evidences, before.attachment_evidences)
        self.assertEqual(after.attachment_invoices, before.attachment_invoices)


class OASourceIdentityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            self.connection,
            relation_command_service_for_transaction=lambda tx: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(tx), tenant_id="default",
            ),
        )
        self.doc = payment_document()
        self.adapter = StubMongoOAAdapter(form_documents={"2": [self.doc]}, project_documents=[])

    def commit(self):
        batch = self.adapter.load_sync_application_batch("all")
        return self.repository.commit_authoritative_snapshot(
            scope_key="all", projection_records=list(batch.projection_records),
            admission_records=list(batch.admission_records),
            authoritative_payment_flow_ids=["source-document"],
            payment_statuses={"source-document": OAPaymentStatusRecord("source-document", 1)},
        )

    def test_completed_transition_preserves_real_etc_relation_and_is_idempotent(self):
        self.commit()
        members = ["oa-pay-original-process", "txn-test", "etc-summary-batch-test"]
        metadata = {"etc_batch_link": {"oa_row_id": members[0], "external_etc_batch_id": "batch-test"}}
        self.connection.execute(
            """insert into app.workbench_pair_relations(case_id,relation_mode,status,row_ids,row_types,special_metadata)
               values ('CASE-TEST','manual_confirmed','active',%s,array['oa','bank','invoice'],%s)""",
            (members, jsonb(metadata)),
        )
        before = self.connection.fetch_one("select to_jsonb(r) as data from app.workbench_pair_relations r", ())
        self.adapter._identity_loader = PostgresOASourceIdentityRepository(self.connection).load_identities
        self.doc["data"].update(flowRequestId=2496, processStatus=2, status="COMPLETED")
        result = self.commit()
        self.assertEqual(result.upserted_completed_count, 1)
        self.assertEqual(self.connection.fetch_one("select to_jsonb(r) as data from app.workbench_pair_relations r", ()), before)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.oa_pending_payment_admissions", ())["n"], 0)
        row = self.connection.fetch_one("select row_id,workflow_status from app.oa_applications", ())
        self.assertEqual(row, {"row_id": members[0], "workflow_status": "completed"})
        self.assertEqual(self.commit().upserted_completed_count, 0)
        self.assertEqual(self.connection.fetch_one("select to_jsonb(r) as data from app.workbench_pair_relations r", ()), before)

    def test_identity_conflict_rolls_back_without_removing_pending_fact(self):
        self.commit()
        records = list(self.adapter.load_sync_application_batch("all").admission_records)
        wrong = copy.deepcopy(records[0])
        wrong.id = "oa-pay-wrong"
        wrong.workflow_status = "completed"
        with self.assertRaises(OASourceIdentityConflict):
            self.repository.commit_authoritative_snapshot(
                scope_key="all", projection_records=[wrong], admission_records=[wrong],
                authoritative_payment_flow_ids=["source-document"],
                payment_statuses={"source-document": OAPaymentStatusRecord("source-document", 1)},
            )
        self.assertEqual(self.connection.fetch_one("select oa_id from app.oa_pending_payment_admissions", ())["oa_id"], records[0].id)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.oa_applications", ())["n"], 0)

    def test_historical_repair_uses_canonical_command_and_records_audit(self):
        from fin_ops_platform.services.oa_identity_repair import build_identity_relation_repair, formal_repair_plans
        from fin_ops_platform.services.postgres_repositories.oa_identity_repair import (
            PostgresOAIdentityRepairRepository,
        )

        self.doc['data'].update(processStatus=2, status='COMPLETED')
        self.commit()
        self.connection.execute("""insert into app.bank_transactions(
            legacy_mongo_id, account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
            txn_date, txn_month, status) values ('repair-bank','test','outflow','test',1711.33,-1711.33,
            '2026-09-15','2026-09-01','pending')""")
        before = {'case_id': 'repair-case', 'status': 'active', 'version': 1,
                  'row_ids': ['oa-pay-source-document', 'repair-bank'], 'row_types': ['oa', 'bank'],
                  'relation_mode': 'manual_confirmed', 'month_scope': '2026-09',
                  'special_metadata': {'requires_oa': True}}
        after = {**before, 'status': 'cancelled', 'version': 2}
        repository = PostgresWorkbenchRelationRepository(self.connection)
        repository.save_workbench_pair_relations({'pair_relations': {'repair-case': after}, 'history': []})
        self.connection.execute("""insert into app.workbench_pair_relation_history(
            case_id,event_type,actor_id,before_payload,after_payload,raw_payload)
            values ('repair-case','cancel_relation_for_unavailable_oa_fact',
            'system:oa_pending_payment_source_sync',%s,%s,'{}')""", (jsonb([before]), jsonb([after])))
        with self.connection.transaction() as tx:
            evidence = PostgresOAIdentityRepairRepository(tx).load_evidence(['repair-case'])
            preview = build_identity_relation_repair(evidence, ['repair-case'])
            plans, metadata = formal_repair_plans(preview)
            result = WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(tx), tenant_id='default',
            ).confirm_formal_relation_plans(plans, actor_id='test:identity-repair',
                                           paired_requirements_by_case_id=metadata)
            self.assertEqual(result['changed_case_ids'], ['repair-case'])
        row = self.connection.fetch_one("select row_ids,status from app.workbench_pair_relations where case_id='repair-case'")
        self.assertEqual(set(row['row_ids']), {'oa-pay-original-process', 'repair-bank'})
        self.assertEqual(row['status'], 'active')
        self.assertEqual(self.connection.fetch_one(
            "select count(*) as n from app.workbench_pair_relation_history where actor_id='test:identity-repair'",
        )['n'], 1)
        with self.connection.transaction() as tx:
            with self.assertRaisesRegex(ValueError, 'later_change'):
                build_identity_relation_repair(PostgresOAIdentityRepairRepository(tx).load_evidence(['repair-case']), ['repair-case'])

    def test_queue_coalesces_retry_and_permanent_identity_failure_but_not_targeted_jobs(self):
        from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository

        queue = RuntimeQueueRepository(self.connection)
        full = queue.enqueue(event_type='oa.sync', scope_key='all', dedupe_key='oa.sync:all', payload={})
        self.assertTrue(queue.requeue_event(full.event_id, reason='test'))
        repeated = queue.enqueue(event_type='oa.sync', scope_key='all', dedupe_key='oa.sync:all', payload={})
        self.assertEqual(full.event_id, repeated.event_id)
        claimed = queue.claim_next('identity-test-worker', event_types=['oa.sync'])
        self.assertEqual(claimed.event_id, full.event_id)
        self.assertTrue(queue.fail_event(full.event_id, 'identity-test-worker',
                                        'oa_source_identity_conflict: test', retryable=False))
        blocked = queue.enqueue(event_type='oa.sync', scope_key='all', dedupe_key='oa.sync:all', payload={})
        self.assertEqual(blocked.status, 'failed')
        self.assertEqual(blocked.event_id, full.event_id)
        targeted = queue.enqueue(event_type='oa.sync', scope_key='all', dedupe_key='oa.attachments:test',
                                 payload={'operation': 'refresh_attachments'})
        self.assertNotEqual(targeted.event_id, full.event_id)

    def test_payment_reconcile_resolves_only_verified_aliases_and_deduplicates(self):
        from fin_ops_platform.services.postgres_repositories.oa_payment_status_reconcile import PostgresOAPaymentStatusReconcileRepository

        self.commit()
        repo = PostgresOAPaymentStatusReconcileRepository(self.connection)
        self.assertEqual(repo.resolve_canonical_oa_row_ids([
            'oa-pay-source-document', 'oa-pay-original-process', 'oa-pay-unknown',
        ]), ['oa-pay-original-process', 'oa-pay-unknown'])
        self.assertEqual(repo.resolve_canonical_oa_row_ids([]), [])

    def test_read_identity_uses_declared_aliases_without_attachment_inference(self):
        from fin_ops_platform.services.postgres_repositories.oa_source_alias_sql import oa_source_aliases_sql

        self.doc['data'].update(processStatus=2, status='COMPLETED', flowRequestId=2496)
        self.commit()
        sql = oa_source_aliases_sql('oa', 'oa.normalized_payload')
        row = self.connection.fetch_one('select ' + sql + ' as aliases from app.oa_applications oa')
        self.assertEqual(set(row['aliases']), {'oa-pay-original-process', 'oa-pay-source-document', 'oa-pay-2496'})
        self.assertNotIn('app.oa_application_items', sql)
        self.assertNotIn('app.oa_attachments', sql)
