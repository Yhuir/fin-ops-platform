from __future__ import annotations

import subprocess
import sys
import unittest
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
        self.assertEqual(len(repository.dashboard_import_jobs()),2)
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
        self.repository.retry_job(job.import_job_id)
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
        with self.assertRaises(KeyError): workflow.retry(job.import_job_id,'other')
        with self.assertRaises(ImportJobIdempotencyConflict):
            workflow.confirm(session_id='review-session', owner='owner',import_type='file_import.confirm',payload=current.payload,expected_version=current.version)
        prepared=workflow.retry(job.import_job_id,'owner')
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
            self.repository.retry_job(job.import_job_id)

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
            list_application_records_by_row_ids=lambda ids: [oa_record(value, status="已完成") for value in ids]))
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

    def test_shared_tax_certified_import_commits_one_batch_and_job_together(self):
        from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
        from fin_ops_platform.services.shared_import_processor import SharedImportProcessor
        from fin_ops_platform.services.tax_certified_import_service import (
            TaxCertifiedImportService,
            UploadedCertifiedImportFile,
        )

        from tests.mock_import_files import CERTIFIED_JAN
        service = TaxCertifiedImportService(state_store=PostgresOpsTaxEtcRepository(self.connection))
        session = service.preview_files(imported_by='owner', uploads=[UploadedCertifiedImportFile(CERTIFIED_JAN.name, CERTIFIED_JAN.content)])
        job = self.repository.create_or_get_job(import_type='tax_certified_import.confirm', payload={'session_id':session.id}, created_by='owner')
        processor = SharedImportProcessor(self.connection)
        worker = ImportJobWorker(repository=self.repository, worker_id='worker', processors={'tax_certified_import.confirm':processor.tax_certified})
        self.assertEqual(worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.repository.get_job(job.import_job_id)
        self.assertEqual(result.result_payload['batch']['persisted_record_count'], 2)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.tax_certified_import_batches')['n'], 1)
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.tax_certified_import_records')['n'], 2)

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
            list_application_records_by_row_ids=lambda ids: records))
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
            list_application_records_by_row_ids=lambda ids: records))
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
        self.repository.retry_job(job.import_job_id)
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
