from __future__ import annotations

import subprocess
import sys
import unittest
from decimal import Decimal
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from textwrap import dedent
from threading import Event

from fin_ops_platform.services.import_job_queue import (
    ImportJobCompletion,
    ImportJobIdempotencyConflict,
    ImportJobLeaseLost,
    ImportJobRepository,
    ImportJobWorker,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_worker import RuntimeWorkerResult, RuntimeWorkerShutdownRequested

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def _prepared_oa_record(record):
    return replace(record, attachment_artifacts=[
        {"source_attachment_key": f"{record.id}:file:{index}", "parse_status": "parsed"}
        for index in range(record.attachment_file_count)
    ])


class ImportDirectQueuePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)
        self.repository = ImportJobRepository(self.connection)
        from psycopg.types.json import Jsonb
        acl = {"access_control_version":1,"page_access_accounts":[{"username":"owner","page_keys":["imports.invoices","imports.bank-transactions","imports.etc-invoices","tax-offset","settings"]}]}
        self.connection.execute("insert into app.app_settings(settings_key,settings_payload,raw_payload) values ('app_settings',%s,%s)",
            (Jsonb(acl),Jsonb({"normalized_payload":acl})))

    def create(self, **kwargs):
        kwargs.setdefault('payload', {'route':'/imports/invoices'})
        return self.repository.create_or_get_job(import_type='file_import.confirm', created_by='owner', **kwargs)

    def test_activity_filters_before_limit_and_keeps_partial_results_without_mutating_history(self):
        from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
        from psycopg.types.json import Jsonb

        partial = self.create(import_session_id='partial')
        self.connection.execute("update job.import_jobs set status='succeeded', result_payload=%s where id=%s",
            (Jsonb({'outcome': 'partial_success', 'failed': ['file-1']}), partial.import_job_id))
        complete = self.create(import_session_id='complete')
        self.connection.execute("update job.import_jobs set status='succeeded', result_payload=%s where id=%s",
            (Jsonb({'created': 2}), complete.import_job_id))
        private = self.repository.create_or_get_job(import_type='oa_manual_import.create', created_by='private-owner')
        rows = self.repository.list_jobs(created_by='viewer', include_shared=True, include_completed=False, limit=1)
        self.assertEqual([row.import_job_id for row in rows], [partial.import_job_id])
        payloads = ImportWorkflowService(self.repository).active_payloads('viewer')
        self.assertEqual([row['status'] for row in payloads], ['partial_success'])
        self.assertNotIn(private.import_job_id, [row['import_job_id'] for row in payloads])
        stored = self.repository.get_job(complete.import_job_id)
        self.assertEqual(stored.status, 'succeeded')
        self.assertEqual(stored.result_payload, {'created': 2})
        self.assertIsNone(stored.acknowledged_at)

    def test_status_counts_use_file_facts_not_shared_type_or_wrong_route(self):
        from fin_ops_platform.services.import_workflow_service import import_job_payload
        from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
        from psycopg.types.json import Jsonb
        for file_id, session, batch_type in [('invoice-file','invoice-session','input_invoice'),('bank-file','bank-session','bank_transaction')]:
            self.connection.execute("insert into app.import_files(legacy_mongo_id,session_id,raw_payload) values (%s,%s,%s)",
                (file_id, session, Jsonb({'normalized_payload':{'batch_type':batch_type}})))
        invoice = self.create(import_session_id='invoice-session', payload={'selected_file_ids':['invoice-file'],'route':'/imports/bank-transactions'})
        self.connection.execute("update job.import_jobs set status='failed' where id=%s", (invoice.import_job_id,))
        self.create(import_session_id='bank-session', payload={'selected_file_ids':['bank-file']})
        repository = RuntimeMonitoringRepository(self.connection)
        counts = repository.import_status_counts()
        self.assertEqual({(tuple(r['affected_domains']),r['status']):r['count'] for r in counts},
                         {(('imports_invoices',),'failed'):1,(('imports_bank_transactions',),'pending'):1})
        payload = import_job_payload(self.repository.get_job(invoice.import_job_id))
        self.assertEqual(payload['route'], '/imports/invoices')
        self.assertEqual(payload['affected_domains'], ['imports_invoices'])
        self.assertEqual(len(repository.dashboard_queue_metrics()),2)
        self.assertEqual(len(self.repository.list_jobs(created_by='other')),0)
        self.repository.acknowledge_job(invoice.import_job_id, created_by='owner')
        self.assertEqual(len(repository.import_status_counts()),1)

    def test_timeout_retries_then_commits_once_and_exhaustion_is_terminal(self):
        from fin_ops_platform.services.runtime_worker import RuntimeWorkerTaskTimeout
        job=self.create(max_attempts=2)
        def timeout(_job):
            raise RuntimeWorkerTaskTimeout('test bounded timeout')
        worker=ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':timeout})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_RETRYABLE)
        failed=self.repository.get_job(job.import_job_id)
        self.assertEqual(failed.status,'pending')
        self.assertIn('timeout',failed.last_error)
        self.connection.execute("update job.import_jobs set available_at=now() where id=%s",(job.import_job_id,))
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
        self.assertEqual(self.repository.get_job(job.import_job_id).status,'failed')
        self.assertEqual(worker.run_once(),RuntimeWorkerResult.IDLE)
        self.repository.retry_job(job.import_job_id, expected_version=self.repository.get_job(job.import_job_id).version)
        def finish(claim):
            with self.connection.transaction() as tx:
                claim.completion.lock(tx)
                tx.execute("insert into app.app_settings(settings_key,settings_payload) values ('timeout-result','{}')")
                claim.completion.succeed(tx,{'created_count':1})
        worker=ImportJobWorker(repository=self.repository,worker_id='worker',processors={'file_import.confirm':finish})
        self.assertEqual(worker.run_once(),RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.run_once(),RuntimeWorkerResult.IDLE)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.app_settings where settings_key='timeout-result'")['n'],1)

    def test_review_rejection_and_historical_rejection_require_repreview(self):
        from fin_ops_platform.services.import_preview_audit import ImportReviewRequiredError
        from fin_ops_platform.services.import_workflow_service import ImportWorkflowService, import_job_payload
        job=self.create(import_session_id='review-session', payload={'session_id':'review-session','route':'/imports/invoices'})
        def reject(_job):
            raise ImportReviewRequiredError('selected files require review before confirmation: selected-file')
        worker=ImportJobWorker(repository=self.repository,worker_id='worker',processors={'file_import.confirm':reject})
        self.assertEqual(worker.run_once(),RuntimeWorkerResult.DEFERRED)
        current=self.repository.get_job(job.import_job_id)
        self.assertEqual(current.status,'needs_review')
        self.assertEqual(import_job_payload(current)['status'],'needs_review')
        self.assertEqual(worker.run_once(),RuntimeWorkerResult.IDLE)
        # Pre-fix records retain their failure history until an explicit operation.
        self.connection.execute("update job.import_jobs set status='failed' where id=%s",(job.import_job_id,))
        current=self.repository.get_job(job.import_job_id)
        self.assertEqual(import_job_payload(current)['retry_mode'],'reprepare')
        workflow=ImportWorkflowService(self.repository)
        with self.assertRaises(ImportJobIdempotencyConflict):
            workflow.confirm(session_id='review-session', owner='owner',import_type='file_import.confirm',payload=current.payload,expected_version=current.version)
        prepared=workflow.retry(job.import_job_id,'other')
        self.assertEqual(prepared.created_by, job.created_by)
        self.assertEqual(prepared.payload['actor_account'], 'other')
        self.assertEqual((prepared.status,prepared.stage),('pending','prepare'))

    def test_prepare_review_cannot_be_confirmed_without_new_preview(self):
        from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
        job = self.create(import_session_id='prepare-review', stage='prepare')
        self.connection.execute("update job.import_jobs set status='needs_review' where id=%s", (job.import_job_id,))
        with self.assertRaises(ImportJobIdempotencyConflict):
            ImportWorkflowService(self.repository).confirm(session_id='prepare-review', owner='owner',
                import_type='file_import.confirm', payload=job.payload, expected_version=job.version)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'needs_review')

    def test_timeout_automatically_recovers_on_next_attempt_without_duplicate_write(self):
        from fin_ops_platform.services.runtime_worker import RuntimeWorkerTaskTimeout
        job = self.create(max_attempts=2)
        def process(claim):
            if claim.attempt_count == 1:
                raise RuntimeWorkerTaskTimeout('temporary timeout')
            with self.connection.transaction() as tx:
                claim.completion.lock(tx)
                tx.execute("insert into app.app_settings(settings_key,settings_payload) values ('auto-result','{}')")
                claim.completion.succeed(tx, {'created_count':1})
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':process})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_RETRYABLE)
        self.connection.execute("update job.import_jobs set available_at=now() where id=%s", (job.import_job_id,))
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'succeeded')
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.app_settings where settings_key='auto-result'")['n'], 1)

    def test_mixed_session_counts_one_job_globally_and_only_selected_domains(self):
        from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
        from psycopg.types.json import Jsonb
        for file_id, kind in [('bank','bank_transaction'), ('invoice','input_invoice')]:
            self.connection.execute("insert into app.import_files(legacy_mongo_id,session_id,raw_payload) values (%s,'mixed',%s)",
                (file_id, Jsonb({'normalized_payload':{'batch_type':kind}})))
        self.create(import_session_id='mixed', payload={'selected_file_ids':['bank','invoice']})
        counts = RuntimeMonitoringRepository(self.connection).import_status_counts()
        self.assertEqual(len(counts), 1)
        self.assertEqual(counts[0]['count'], 1)
        self.assertEqual(set(counts[0]['affected_domains']), {'imports_invoices','imports_bank_transactions'})

    def test_upload_and_job_roll_back_together_and_replay_keeps_confirmed_payload(self):
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            with self.connection.transaction() as tx:
                self.create(idempotency_key='rolled-back', transaction=tx)
                raise RuntimeError('rollback')
        self.assertIsNone(self.repository.get_by_idempotency_key('rolled-back', created_by='owner'))
        job = self.create(idempotency_key='same', status='awaiting_confirmation', payload={'session_id':'s'})
        confirmed = self.repository.confirm_job(job.import_job_id, expected_version=job.version,
                                                payload={'session_id':'s', 'selected_file_ids':['a']})
        replay = self.create(idempotency_key='same', status='awaiting_confirmation', payload={'session_id':'s'})
        self.assertEqual(replay.payload, confirmed.payload)
        self.assertEqual(replay.version, confirmed.version)
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.create(idempotency_key='same', payload={'session_id':'other'})

    def test_two_claimants_have_one_owner_and_expired_owner_cannot_commit(self):
        job = self.create()
        with ThreadPoolExecutor(2) as executor:
            claims = list(executor.map(lambda name: self.repository.claim_next(name), ['a','b']))
        owned = [claim for claim in claims if claim is not None]
        self.assertEqual(len(owned), 1)
        first = owned[0]
        self.connection.execute("update job.import_jobs set locked_at=now()-interval '1 hour' where id=%s", (job.import_job_id,))
        successor = self.repository.claim_next('successor')
        self.assertGreater(successor.claim_version, first.claim_version)
        with self.assertRaises(ImportJobLeaseLost):
            with self.connection.transaction() as tx:
                ImportJobCompletion(first).lock(tx)
        with self.connection.transaction() as tx:
            completion = ImportJobCompletion(successor)
            completion.lock(tx)
            completion.succeed(tx, {'created_count':1})
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'succeeded')
        self.assertFalse(self.repository.fail_claim(first, error='late error', retry=True))

    def test_cancellation_wins_before_transaction_and_fences_same_worker_name(self):
        job = self.create()
        claim = self.repository.claim_next('stable-worker')
        canceled = self.repository.cancel_job(job.import_job_id, created_by='owner')
        self.assertEqual(canceled.status, 'canceled')
        with self.assertRaises(ImportJobLeaseLost):
            with self.connection.transaction() as tx:
                ImportJobCompletion(claim).lock(tx)
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.repository.retry_job(job.import_job_id, expected_version=self.repository.get_job(job.import_job_id).version)

    def test_business_write_and_success_rollback_together(self):
        job = self.create()
        claim = self.repository.claim_next('worker')
        with self.assertRaisesRegex(RuntimeError, 'rollback'):
            with self.connection.transaction() as tx:
                completion = ImportJobCompletion(claim)
                completion.lock(tx)
                tx.execute("insert into app.app_settings(settings_key,settings_payload) values ('queue-test','{}')")
                completion.succeed(tx, {'created_count':1})
                raise RuntimeError('rollback')
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'processing')
        self.assertIsNone(self.connection.fetch_one("select 1 from app.app_settings where settings_key='queue-test'"))

    def test_commit_wins_cancel_wait_and_reports_completed(self):
        job = self.create()
        claim = self.repository.claim_next('worker')
        attempted = Event()
        def cancel():
            attempted.set()
            return self.repository.cancel_job(job.import_job_id, created_by='owner')
        with ThreadPoolExecutor(1) as executor:
            with self.connection.transaction() as tx:
                completion = ImportJobCompletion(claim)
                completion.lock(tx)
                future = executor.submit(cancel)
                attempted.wait(2)
                completion.succeed(tx, {'created_count':1})
            with self.assertRaises(ImportJobIdempotencyConflict):
                future.result(timeout=3)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'succeeded')

    def test_prepare_confirm_commit_one_job_without_outbox(self):
        job = self.create(stage='prepare')
        def process(claim):
            with self.connection.transaction() as tx:
                claim.completion.lock(tx)
                if claim.stage == 'prepare':
                    claim.completion.preview(tx, {'preview': {'new_count':2}})
                else:
                    claim.completion.succeed(tx, {'created_count':2})
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':process})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        prepared = self.repository.get_job(job.import_job_id)
        self.assertEqual(prepared.status, 'awaiting_confirmation')
        self.repository.confirm_job(job.import_job_id, expected_version=prepared.version, payload=prepared.payload)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(self.repository.get_job(job.import_job_id).result_payload['created_count'], 2)
        self.assertEqual(self.connection.fetch_one('select count(*) as n from job.outbox_events')['n'], 0)
        self.assertTrue(self.repository.acknowledge_job(job.import_job_id, created_by='owner'))
        self.assertEqual(self.repository.list_jobs(created_by='owner'), [])

    def test_shutdown_releases_only_import_lease_and_max_attempts_is_bounded(self):
        job = self.create(max_attempts=2)
        def shutdown(_job):
            raise RuntimeWorkerShutdownRequested()
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':shutdown})
        with self.assertRaises(RuntimeWorkerShutdownRequested):
            worker.run_once()
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'pending')
        claim = self.repository.claim_next('worker')
        self.assertEqual(claim.attempt_count, 2)
        self.connection.execute("update job.import_jobs set locked_at=now()-interval '1 hour' where id=%s", (job.import_job_id,))
        self.assertIsNone(self.repository.claim_next('worker'))
        failed = self.repository.get_job(job.import_job_id)
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.stage, 'commit')

    def test_missing_transactional_completion_is_failure_not_fake_success(self):
        job = self.create(max_attempts=1)
        worker = ImportJobWorker(repository=self.repository, worker_id='worker',
                                 processors={'file_import.confirm':lambda job: {'success':True}})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'failed')

    def test_process_exit_rolls_back_domain_and_restarted_worker_recovers(self):
        job = self.create()
        program = dedent("""
            import os, sys
            from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
            from fin_ops_platform.services.import_job_queue import ImportJobRepository, ImportJobCompletion
            connection=PostgresConnection(PostgresSettings(database_url=sys.argv[1]))
            job=ImportJobRepository(connection).claim_next('terminated-process')
            with connection.transaction() as tx:
                ImportJobCompletion(job).lock(tx)
                tx.execute("insert into app.app_settings(settings_key,settings_payload) values ('crash-write','{}')")
                ImportJobCompletion(job).succeed(tx, {'created_count':1})
                os._exit(23)
        """)
        completed = subprocess.run([sys.executable, '-c', program, self.url], timeout=10, capture_output=True)
        self.assertEqual(completed.returncode, 23, completed.stderr.decode())
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'processing')
        self.assertIsNone(self.connection.fetch_one("select 1 from app.app_settings where settings_key='crash-write'"))
        self.connection.execute("update job.import_jobs set locked_at=now()-interval '1 hour' where id=%s", (job.import_job_id,))
        def recovered(claim):
            with self.connection.transaction() as tx:
                claim.completion.lock(tx)
                tx.execute("insert into app.app_settings(settings_key,settings_payload) values ('crash-write','{}')")
                claim.completion.succeed(tx, {'created_count':1})
        worker = ImportJobWorker(repository=self.repository, worker_id='replacement', processors={'file_import.confirm':recovered})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.app_settings where settings_key='crash-write'")['n'], 1)

    def test_shared_oa_import_adds_only_selected_rows_and_repeats_without_overwrite(self):
        from types import SimpleNamespace

        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor

        from tests.test_oa_manual_import_service import oa_record
        processor = SharedImportProcessor(self.connection, oa_source_adapter=SimpleNamespace(
            prepare_application_record_attachments=lambda ids, *, preparation_started_at: [_prepared_oa_record(oa_record(value, status="已完成")) for value in ids]))
        def create_oa(rows):
            return self.repository.create_or_get_job(import_type='oa_manual_import.create', payload={'row_ids':rows}, created_by='owner')
        first = create_oa(['A','B'])
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'oa_manual_import.create':processor.oa_manual})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(self.repository.get_job(first.import_job_id).result_payload['imported'], ['A','B'])
        second = create_oa(['B','C'])
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.repository.get_job(second.import_job_id).result_payload
        self.assertEqual(result['already_imported'], ['B'])
        self.assertEqual(result['imported'], ['C'])
        rows = self.connection.fetch_all("select row_id from app.manual_oa_imports where status='active' order by row_id")
        self.assertEqual([row['row_id'] for row in rows], ['A','B','C'])
        from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
            PostgresOaPendingPaymentSourceSnapshotRepository,
        )
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
        snapshot = PostgresOaPendingPaymentSourceSnapshotRepository(self.connection,
            relation_command_service_for_transaction=lambda _tx: self.fail("Retained manual OA must not lose relations"))
        snapshot.commit_authoritative_snapshot(scope_key='all', projection_records=[], admission_records=[],
            payment_statuses={}, authoritative_payment_flow_ids=[], retention_cutoff_month='2026-01')
        history = PostgresOAProjectionRepository(self.connection).list_application_records('2025-12')
        self.assertEqual({record.id for record in history}, {'A','B','C'})
        self.assertEqual(self.repository.get_job(second.import_job_id).status, 'succeeded')
        from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
        PostgresOAProjectionRepository(self.connection).upsert_application_records(
            [oa_record('auto', month='2026-02')], scope_key='2026-02')
        states = PostgresOpsTaxEtcRepository(self.connection).load_oa_search_import_states(['A', 'auto', 'new'])
        self.assertEqual({key: value['import_status'] for key, value in states.items()},
                         {'A':'imported', 'auto':'already_imported', 'new':'not_imported'})



    def test_manual_import_rolls_back_oa_when_marker_write_fails(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor

        from tests.test_oa_manual_import_service import oa_record
        processor = SharedImportProcessor(self.connection, oa_source_adapter=SimpleNamespace(
            prepare_application_record_attachments=lambda ids, *, preparation_started_at: [_prepared_oa_record(oa_record(value)) for value in ids]))
        job = self.repository.create_or_get_job(import_type='oa_manual_import.create',
            payload={'row_ids':['rollback-history']}, created_by='owner')
        worker = ImportJobWorker(repository=self.repository, worker_id='worker',
            processors={'oa_manual_import.create':processor.oa_manual})
        with patch('fin_ops_platform.services.shared_import_processor.PostgresSharedImportRepository.add_manual_oa_imports',
                   side_effect=RuntimeError('fixture marker persistence failed')):
            worker.run_once()
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.oa_applications')['n'], 0)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.manual_oa_imports')['n'], 0)
        self.assertNotEqual(self.repository.get_job(job.import_job_id).status, 'succeeded')

    def _manual_attachment_worker(self, *, records=None, prepare=None, mode="create_missing", max_attempts=5):
        from types import SimpleNamespace
        from psycopg.types.json import Jsonb
        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor
        self.connection.execute("""update app.app_settings
            set settings_payload=settings_payload || %s,
                raw_payload=jsonb_build_object('normalized_payload', settings_payload || %s)
            where settings_key='app_settings'""",
            (Jsonb({"oa_import": {"attachment_invoice_promotion_mode": mode}}),
             Jsonb({"oa_import": {"attachment_invoice_promotion_mode": mode}})))
        if records is None:
            records = [self._manual_attachment_record()]
        processor = SharedImportProcessor(self.connection, oa_source_adapter=SimpleNamespace(
            prepare_application_record_attachments=prepare or (lambda ids, *, preparation_started_at: records)))
        job = self.repository.create_or_get_job(import_type="oa_manual_import.create", created_by="owner",
            payload={"row_ids": [record.id for record in records]}, max_attempts=max_attempts)
        worker = ImportJobWorker(repository=self.repository, worker_id="attachment-worker",
            processors={"oa_manual_import.create": processor.oa_manual})
        return job, worker

    @staticmethod
    def _manual_attachment_record(row_id="oa-manual-attachment", number="26539150014000355216"):
        from tests.test_oa_manual_import_service import oa_record
        from tests.test_oa_attachment_invoice_promotion_service import _attachment
        invoice = _attachment(number, "135.00", f"{row_id}:item:1", "invoice.pdf")
        invoice["source_attachment_key"] = f"{row_id}:attachment"
        record = oa_record(row_id, month="2026-06", invoices=[invoice], attachment_file_count=1)
        record.expense_items[0]["expense_item_id"] = f"{row_id}:item:1"
        record.attachment_artifacts = [{"source_attachment_key": invoice["source_attachment_key"],
                                       "parse_status": "parsed", "has_invoice_evidence": "true"}]
        return record

    def test_manual_attachment_prepares_before_transaction_then_commits_ownership_and_completion_once(self):
        record = self._manual_attachment_record()
        calls = []
        def prepare(ids, *, preparation_started_at):
            calls.append((ids, preparation_started_at))
            self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 0)
            self.assertEqual(self.connection.fetch_one("select count(*) n from app.oa_applications")["n"], 0)
            return [record]
        job, worker = self._manual_attachment_worker(records=[record], prepare=prepare)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(calls, [([record.id], job.created_at.isoformat())])
        result = self.repository.get_job(job.import_job_id)
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.result_payload["attachment_invoice_promotion"]["summary"]["affected_invoice_count"], 1)
        invoice = self.connection.fetch_one("select legacy_mongo_id, total_with_tax, source_links from app.invoices")
        self.assertEqual(invoice["total_with_tax"], Decimal("135.00"))
        self.assertEqual(invoice["source_links"][0]["derived_from_oa_id"], record.id)
        self.assertEqual(invoice["source_links"][0]["source_expense_item_id"], f"{record.id}:item:1")
        self.assertGreater(self.connection.fetch_one("select count(*) n from job.workbench_matching_dirty_scopes")["n"], 0)
        second, repeated = self._manual_attachment_worker(records=[record])
        self.assertEqual(repeated.run_once(), RuntimeWorkerResult.PROCESSED)
        replay = self.repository.get_job(second.import_job_id).result_payload
        self.assertEqual(replay["already_imported"], [record.id])
        self.assertEqual(replay["attachment_invoice_promotion"]["summary"]["affected_invoice_count"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 1)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.manual_oa_imports")["n"], 1)

    def test_manual_attachment_failure_rolls_back_invoice_oa_marker_matching_and_completion(self):
        from unittest.mock import patch
        for failed_step in ("marker", "completion"):
            with self.subTest(failed_step=failed_step):
                job, worker = self._manual_attachment_worker()
                target = ("fin_ops_platform.services.shared_import_processor.PostgresSharedImportRepository.add_manual_oa_imports"
                          if failed_step == "marker" else "fin_ops_platform.services.import_job_queue.ImportJobCompletion.succeed")
                with patch(target, side_effect=RuntimeError("transaction failure")):
                    self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
                for table in ("app.invoices", "app.oa_applications", "app.manual_oa_imports", "job.workbench_matching_dirty_scopes"):
                    self.assertEqual(self.connection.fetch_one(f"select count(*) n from {table}")["n"], 0)
                self.assertEqual(self.repository.get_job(job.import_job_id).status, "failed")
                self.assertEqual(self.connection.fetch_one("select count(*) n from audit.events where object_id=%s", (job.import_job_id,))["n"], 0)

    def test_manual_attachment_honors_promotion_mode_and_does_not_create_from_unfinished_oa(self):
        good = self._manual_attachment_record()
        bad = self._manual_attachment_record("oa-failed", "26539150014000355217")
        bad.attachment_artifacts[0]["parse_status"] = "parse_failed"
        pending = self._manual_attachment_record("oa-pending", "26539150014000355218")
        pending.attachment_artifacts[0]["parse_status"] = "not_parsed"
        unsupported = self._manual_attachment_record("oa-support", "26539150014000355219")
        unsupported.attachment_invoices = []
        unsupported.expense_items[0]["attachment_invoices"] = []
        unsupported.attachment_artifacts[0].update(parse_status="unsupported", has_invoice_evidence="false")
        job, worker = self._manual_attachment_worker(records=[good, bad, pending, unsupported], mode="link_existing_only")
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.repository.get_job(job.import_job_id).result_payload
        self.assertEqual(result["outcome"], "partial_success")
        self.assertEqual(set(result["imported"]), {good.id, unsupported.id})
        self.assertEqual({item["row_id"] for item in result["failed"]}, {bad.id, pending.id})
        self.assertEqual({item["code"] for item in result["failed"]}, {"attachment_preparation_failed"})
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.oa_applications")["n"], 2)
        second, create_worker = self._manual_attachment_worker(records=[good, bad, pending, unsupported], mode="create_missing")
        self.assertEqual(create_worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(self.repository.get_job(second.import_job_id).result_payload["outcome"], "partial_success")
        invoices = self.connection.fetch_all("select invoice_no from app.invoices")
        self.assertEqual([row["invoice_no"] for row in invoices], [good.attachment_invoices[0]["invoice_no"]])

    def test_manual_attachment_bounded_progress_defers_without_exhausting_failure_budget(self):
        from fin_ops_platform.services.oa_adapter import OAAttachmentPreparationPending
        calls = []
        record = self._manual_attachment_record()
        def prepare(ids, *, preparation_started_at):
            calls.append((ids, preparation_started_at))
            if len(calls) <= 3:
                raise OAAttachmentPreparationPending(20)
            return [record]
        job, worker = self._manual_attachment_worker(records=[record], prepare=prepare, max_attempts=1)
        for _ in range(3):
            self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
            pending = self.repository.get_job(job.import_job_id)
            self.assertEqual(pending.status, "pending")
            self.assertEqual(pending.attempt_count, 0)
            self.assertEqual(pending.result_payload["parsed_in_attempt"], 20)
            self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 0)
            self.assertEqual(self.connection.fetch_one("select count(*) n from app.oa_applications")["n"], 0)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(calls, [([record.id], job.created_at.isoformat())] * 4)
        self.assertEqual(self.repository.get_job(job.import_job_id).attempt_count, 1)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 1)

    def test_manual_attachment_explicit_retry_starts_new_preparation_cycle_and_defers_keep_it(self):
        from fin_ops_platform.services.oa_adapter import OAAttachmentPreparationPending
        record = self._manual_attachment_record()
        calls = []
        def prepare(ids, *, preparation_started_at):
            calls.append(preparation_started_at)
            if len(calls) == 1:
                failed_record = replace(record, attachment_artifacts=[{
                    **record.attachment_artifacts[0], "parse_status": "download_failed"}])
                return [failed_record]
            if len(calls) == 2:
                raise OAAttachmentPreparationPending(20)
            return [record]
        job, worker = self._manual_attachment_worker(records=[record], prepare=prepare)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
        failed = self.repository.get_job(job.import_job_id)
        self.assertEqual(failed.result_payload["failed"][0]["code"], "attachment_preparation_failed")
        retried = self.repository.retry_job(job.import_job_id, expected_version=failed.version,
            command_context={"attachment_preparation_started_at": "cannot-override-server-cycle"})
        expected_cycle = retried.payload["attachment_preparation_started_at"]
        self.assertGreater(datetime.fromisoformat(expected_cycle), job.created_at)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        self.assertEqual(self.repository.get_job(job.import_job_id).payload["attachment_preparation_started_at"], expected_cycle)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(calls, [job.created_at.isoformat(), expected_cycle, expected_cycle])
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 1)

    def test_non_oa_retry_does_not_add_attachment_preparation_cycle(self):
        job = self.create()
        claimed = self.repository.claim_next("failed-worker")
        self.repository.fail_claim(claimed, error="test failure", retry=False)
        failed = self.repository.get_job(job.import_job_id)
        retried = self.repository.retry_job(job.import_job_id, expected_version=failed.version)
        self.assertEqual(retried.payload, job.payload)
        self.assertNotIn("attachment_preparation_started_at", retried.payload)

    def test_attachment_defer_cannot_release_a_newer_owner(self):
        job, _ = self._manual_attachment_worker()
        first = self.repository.claim_next("first")
        self.connection.execute("update job.import_jobs set locked_at=now()-interval '1 hour' where id=%s", (job.import_job_id,))
        replacement = self.repository.claim_next("replacement")
        self.assertFalse(self.repository.defer_attachment_preparation(first, parsed_count=20))
        current = self.repository.get_job(job.import_job_id)
        self.assertEqual(current.status, "processing")
        self.assertEqual(current.locked_by, "replacement")
        self.assertEqual(current.claim_version, replacement.claim_version)

    def test_shared_tax_certified_import_commits_one_batch_and_job_together(self):
        from fin_ops_platform.services.postgres_repositories.tax_certified_imports import PostgresTaxCertifiedImportRepository
        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor
        from fin_ops_platform.services.tax_certified_import_service import (
            TaxCertifiedImportService,
        )

        from tests.test_tax_certified_import_service import certified_upload
        service = TaxCertifiedImportService(repository=PostgresTaxCertifiedImportRepository(self.connection))
        session = service.preview_files(imported_by='owner', uploads=[certified_upload()])
        job = self.repository.create_or_get_job(import_type='tax_certified_import.confirm', payload={'session_id':session.id}, created_by='owner')
        processor = SharedImportProcessor(self.connection)
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'tax_certified_import.confirm':processor.tax_certified})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.repository.get_job(job.import_job_id)
        self.assertEqual(result.result_payload['batch']['persisted_record_count'], 1)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.tax_certified_import_batches')['n'], 1)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.tax_certified_import_records')['n'], 1)

    def test_stale_preview_requires_reprepare_and_only_known_transient_errors_retry(self):
        from fin_ops_platform.services.etc_service import EtcImportPreviewStaleError
        job = self.create()
        def stale(_job):
            raise EtcImportPreviewStaleError('changed task')
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':stale})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.DEFERRED)
        review = self.repository.get_job(job.import_job_id)
        self.assertEqual(review.status, 'needs_review')
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.IDLE)
        with self.connection.transaction() as tx:
            prepared = self.repository.reprepare_job(job.import_job_id, expected_version=review.version,
                                                      payload={'session_id':'revised', 'route':'/imports/invoices'}, transaction=tx)
        self.assertEqual(prepared.stage, 'prepare')
        self.assertGreater(prepared.claim_version, review.claim_version)
        def transient(_job):
            raise TimeoutError('temporary')
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'file_import.confirm':transient})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_RETRYABLE)
        self.assertEqual(self.repository.get_job(job.import_job_id).stage, 'prepare')

    def test_create_replay_cannot_change_authenticated_owner(self):
        self.create(idempotency_key='owner-identity')
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.repository.create_or_get_job(import_type='file_import.confirm', created_by='other', idempotency_key='owner-identity')

    def test_cancellation_participates_in_caller_transaction(self):
        job = self.create()
        with self.assertRaises(RuntimeError):
            with self.connection.transaction() as tx:
                self.repository.cancel_job(job.import_job_id, created_by='owner', transaction=tx)
                raise RuntimeError('draft persistence failed')
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'pending')

    def test_authorization_revoked_after_enqueue_blocks_commit(self):
        job = self.create()
        claim = self.repository.claim_next('worker')
        from psycopg.types.json import Jsonb
        revoked = {"page_access_accounts":[],"access_control_version":2}
        self.connection.execute("update app.app_settings set settings_payload=%s,raw_payload=%s where settings_key='app_settings'", (Jsonb(revoked),Jsonb({"normalized_payload":revoked})))
        with self.assertRaises(PermissionError):
            with self.connection.transaction() as tx:
                ImportJobCompletion(claim).lock(tx)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, 'processing')

    def test_tax_job_polling_rejects_other_owner(self):
        from fin_ops_platform.services.tax_certified_import_job_service import TaxCertifiedImportJobService
        job = self.repository.create_or_get_job(import_type='tax_certified_import.confirm', created_by='owner')
        service = TaxCertifiedImportJobService(import_job_repository_provider=lambda: self.repository)
        self.assertEqual(service.get_confirm_job_payload(job.import_job_id, owner_user_id='owner')['status'], 'pending')
        with self.assertRaises(KeyError):
            service.get_confirm_job_payload(job.import_job_id, owner_user_id='other')

    def test_oa_source_validation_does_not_admit_missing_or_in_progress_rows(self):
        from types import SimpleNamespace

        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor

        from tests.test_oa_manual_import_service import oa_record
        records = [oa_record('completed', status='已完成'), oa_record('progress', status='进行中')]
        processor = SharedImportProcessor(self.connection, oa_source_adapter=SimpleNamespace(
            prepare_application_record_attachments=lambda ids, *, preparation_started_at: [_prepared_oa_record(record) for record in records]))
        job = self.repository.create_or_get_job(import_type='oa_manual_import.create', created_by='owner',
            payload={'row_ids':['completed','progress','missing']})
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'oa_manual_import.create':processor.oa_manual})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.repository.get_job(job.import_job_id).result_payload
        self.assertEqual(result['imported'], ['completed'])
        self.assertEqual({row['code'] for row in result['failed']}, {'not_completed','not_found'})
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.oa_applications')['n'],1)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.manual_oa_imports')['n'],1)
        self.assertEqual(self.connection.fetch_one(
            "select outcome from audit.events where action='oa_manual_import.create'")['outcome'],'partial_success')
        from fin_ops_platform.services.import_workflow_service import import_job_payload
        progress = import_job_payload(self.repository.get_job(job.import_job_id))
        self.assertEqual(progress['status'],'partial_success')
        self.assertTrue(progress['attention'])
        self.assertTrue(progress['acknowledgeable'])
        self.assertFalse(progress['retryable'])

    def test_oa_all_failed_is_durable_failure_and_explicit_retry_can_succeed(self):
        from types import SimpleNamespace

        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor

        from tests.test_oa_manual_import_service import oa_record
        records = []
        processor = SharedImportProcessor(self.connection, oa_source_adapter=SimpleNamespace(
            prepare_application_record_attachments=lambda ids, *, preparation_started_at: [_prepared_oa_record(record) for record in records]))
        job = self.repository.create_or_get_job(import_type='oa_manual_import.create', created_by='owner', payload={'row_ids':['later']})
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'oa_manual_import.create':processor.oa_manual})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
        failed = self.repository.get_job(job.import_job_id)
        self.assertEqual(failed.status,'failed')
        from fin_ops_platform.services.import_workflow_service import import_job_payload
        progress = import_job_payload(failed)
        self.assertEqual(progress['status'],'failed')
        self.assertTrue(progress['retryable'])
        self.assertTrue(progress['attention'])
        self.assertEqual(failed.result_payload['failed'][0]['code'],'not_found')
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.manual_oa_imports')['n'],0)
        self.assertEqual(self.connection.fetch_one("select outcome from audit.events where object_id=%s",(job.import_job_id,))['outcome'],'failed')
        records.append(oa_record('later',status='已完成'))
        self.repository.retry_job(job.import_job_id, expected_version=self.repository.get_job(job.import_job_id).version)
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        self.assertEqual(self.repository.get_job(job.import_job_id).result_payload['imported'],['later'])

    def test_http_preview_stale_transition_uses_version_compare_and_swap(self):
        job = self.create(status='awaiting_confirmation')
        stale = self.repository.mark_preview_needs_review(job.import_job_id, expected_version=job.version)
        self.assertEqual(stale.status, 'needs_review')
        self.assertGreater(stale.version, job.version)
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.repository.confirm_job(job.import_job_id, expected_version=job.version, payload=job.payload)

    def test_migrated_pending_final_attempt_becomes_actionable_failure(self):
        job = self.create(max_attempts=1)
        self.connection.execute('update job.import_jobs set attempt_count=1 where id=%s',(job.import_job_id,))
        self.assertIsNone(self.repository.claim_next('worker'))
        self.assertEqual(self.repository.get_job(job.import_job_id).status,'failed')


if __name__ == '__main__':
    unittest.main()
