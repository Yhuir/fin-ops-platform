from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.etc_import_preview_service import EtcImportPreviewService
from fin_ops_platform.services.etc_import_session_store import build_etc_import_session_store
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import EtcService, UploadedEtcZipFile
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.import_job_operations_service import ImportJobOperationsService
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict, ImportJobRepository
from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.operations_audit_service import OperationsAuditService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.etc_import_sessions import PostgresEtcImportSessionRepository
from fin_ops_platform.services.postgres_repositories.import_job_operations import ImportJobOperationsRepository
from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore

from tests.app_test_support import build_local_state_application
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.test_etc_reconciliation_service import etc_zip, ready_task_with_requirement
from tests.test_import_closed_loop import invoice_row

ACTOR = {'actor_id': 'admin-id', 'actor_account': 'YNSYLP005', 'actor_name': '管理员'}


class ImportJobOperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = PostgresStateStore(data_dir=Path(self.directory.name), connection=self.connection)
        self.files = FileImportService(ImportNormalizationService(id_registry=self.store, fact_repository=self.store.import_fact_repository))
        self.session = self.files.preview_manual_invoice_entries(imported_by='owner', entries=[(BatchType.INPUT_INVOICE, invoice_row())])
        self.jobs = ImportJobRepository(self.connection)
        self.job = self.store.save_import_registration(self.files.preview_session_persistence_payload(self.session.id),
            register_job=lambda tx: self.jobs.create_or_get_job(import_type='file_import.confirm', import_session_id=self.session.id,
                created_by='owner', payload={'session_id':self.session.id, 'selected_file_ids':[self.session.files[0].id]}, transaction=tx))
        self.connection.execute("update job.import_jobs set status='failed', last_error='selected files require review before confirmation: file' where id=%s", (self.job.import_job_id,))
        self.repo = ImportJobOperationsRepository(self.connection)
        self.service = ImportJobOperationsService(self.repo, file_lifecycle=PostgresImportLifecycleRepository(self.connection),
                                                 etc_sessions=PostgresEtcImportSessionRepository(self.connection))
        self.command = {'version':self.job.version, 'action':'close', 'reason':'not_needed', 'note':'已核实'}

    def dispose(self, **changes):
        return self.service.dispose(self.job.import_job_id, {**self.command, **changes}, actor=ACTOR, request_id='test-dispose')

    def test_list_detail_close_refresh_history_and_replay(self):
        self.assertEqual(self.service.list_jobs(page=1,page_size=20)['pagination']['total'],1)
        detail = self.service.detail(self.job.import_job_id, actor_account='YNSYLP005')
        self.assertEqual(detail['job']['error_code'],'review_required')
        self.assertEqual(detail['job']['allowed_actions'],['close'])
        self.assertIsNone(detail['job']['continue_route'])
        self.assertEqual(detail['files'][0]['row_count'],1)
        self.assertEqual(detail['files'][0]['identity_match_count'],0)
        owner = self.service.detail(self.job.import_job_id,actor_account='owner')
        self.assertEqual(owner['job']['continue_route'],'/imports/invoices')
        result = self.dispose()
        self.assertEqual(result['status'],'failed')
        self.assertFalse(result['idempotent_replay'])
        self.assertTrue(self.dispose()['idempotent_replay'])
        self.assertEqual(self.service.list_jobs(page=1,page_size=20)['pagination']['total'],0)
        job = self.jobs.get_job(self.job.import_job_id)
        self.assertIn('selected files require review',job.last_error)
        self.assertIsNotNone(job.acknowledged_at)
        audit = self.connection.fetch_all("select actor_account,request_id,reason from audit.events where action='import_job.dispose'")
        self.assertEqual(len(audit),1)
        self.assertEqual(audit[0]['actor_account'],'YNSYLP005')
        self.assertEqual(audit[0]['request_id'],'test-dispose')
        self.assertEqual(self.service.detail(self.job.import_job_id,actor_account='owner')['job']['allowed_actions'],[])

    def test_disposed_job_rejects_all_resume_paths_but_acknowledged_can_retry(self):
        self.jobs.acknowledge_job(self.job.import_job_id,created_by='owner')
        self.jobs.retry_job(self.job.import_job_id,expected_version=self.job.version)
        job = self.jobs.get_job(self.job.import_job_id)
        self.connection.execute("update job.import_jobs set status='failed' where id=%s",(job.import_job_id,))
        self.command['version'] = job.version
        self.dispose()
        workflow = ImportWorkflowService(self.jobs)
        for action in [lambda: self.jobs.retry_job(job.import_job_id,expected_version=job.version),
                       lambda: self.jobs.reprepare_job(job.import_job_id,expected_version=job.version),
                       lambda: workflow.retry(job.import_job_id,'owner'),
                       lambda: workflow.confirm(session_id=self.session.id,owner='owner',import_type='file_import.confirm',payload=job.payload,expected_version=job.version),
                       lambda: workflow.revise_files(file_service=self.files,store=self.store,session_id=self.session.id,owner='owner',selected_file_ids=job.payload['selected_file_ids'])]:
            with self.assertRaises(ImportJobIdempotencyConflict): action()

    def test_discard_review_ends_file_batch_and_job_in_one_transaction(self):
        self.connection.execute("update job.import_jobs set status='needs_review' where id=%s",(self.job.import_job_id,))
        self.assertEqual(self.dispose(action='discard')['status'],'canceled')
        self.assertEqual(self.connection.fetch_one('select status from app.import_files')['status'],'reverted')
        self.assertEqual(self.connection.fetch_one('select status from app.import_batches')['status'],'reverted')
        self.assertEqual(self.connection.fetch_one('select count(*) as n from app.invoices')['n'],0)

    def test_admin_etc_discard_uses_same_transaction_and_rolls_back_on_audit_error(self):
        task = ready_task_with_requirement(amount="25.00", transaction_at="2026-03-03 12:00:00", invoice_count=1)
        PostgresOpsTaxEtcRepository(self.connection).save_etc_reconciliation_task(task, expected_version=None)
        sessions = build_etc_import_session_store(self.store)
        preview = EtcImportPreviewService(
            etc_service=EtcService(state_store=self.store, load_initial_state=False),
            task_service=EtcReconciliationTaskService(state_store=self.store, load_initial_state=False), session_store=sessions)
        jobs = []
        def register(tx, session):
            jobs.append(self.jobs.create_or_get_job(import_type="etc_invoice_import.confirm", stage="prepare",
                import_session_id=session.session_id, created_by="owner", transaction=tx))
        session = preview.register(task_id=task.task_id, imported_by="owner",
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], register_job=register)
        job = jobs[0]
        self.connection.execute("update job.import_jobs set status='needs_review' where id=%s", (job.import_job_id,))
        payload = {**self.command, 'version': job.version, 'action': 'discard'}
        with patch.object(PostgresOperationsAuditRepository, 'append_operation_event', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'audit unavailable'):
                self.service.dispose(job.import_job_id, payload, actor=ACTOR, request_id='etc-discard')
        self.assertNotEqual(sessions.get(session.session_id, load_uploads=False).status, 'reverted')
        self.assertEqual(self.jobs.get_job(job.import_job_id).status, 'needs_review')
        result = self.service.dispose(job.import_job_id, payload, actor=ACTOR, request_id='etc-discard')
        self.assertEqual(result['status'], 'canceled')
        self.assertEqual(sessions.get(session.session_id, load_uploads=False).status, 'reverted')

    def test_audit_failure_rolls_back_preview_job_and_disposition(self):
        self.connection.execute("update job.import_jobs set status='needs_review' where id=%s",(self.job.import_job_id,))
        with patch.object(PostgresOperationsAuditRepository,'append_operation_event',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaisesRegex(RuntimeError,'audit unavailable'): self.dispose(action='discard')
        self.assertEqual(self.jobs.get_job(self.job.import_job_id).status,'needs_review')
        self.assertNotEqual(self.connection.fetch_one('select status from app.import_files')['status'],'reverted')
        self.assertIsNone(self.jobs.get_job(self.job.import_job_id).acknowledged_at)

    def test_conflicts_validation_and_missing_task(self):
        for change in [{'version':True},{'version':0},{'reason':[]},{'reason':'invented'},{'note':[]},{'note':'x'*501},{'action':'retry'}]:
            with self.assertRaises(ValueError): self.dispose(**change)
        with self.assertRaises(ImportJobIdempotencyConflict): self.dispose(version=99)
        for state in ['pending','processing','awaiting_confirmation','succeeded','canceled']:
            self.connection.execute('update job.import_jobs set status=%s where id=%s',(state,self.job.import_job_id))
            with self.assertRaises(ImportJobIdempotencyConflict): self.dispose()
        with self.assertRaises(KeyError): self.service.detail('00000000-0000-0000-0000-000000000001',actor_account='admin')

    def test_missing_file_can_be_inspected_and_failure_closed_without_fabricating_preview(self):
        self.connection.execute('update job.import_jobs set import_session_id=%s where id=%s',('missing-session',self.job.import_job_id))
        detail = self.service.detail(self.job.import_job_id,actor_account='admin')
        self.assertEqual(detail['files'],[])
        self.assertEqual(detail['file_pagination']['total'],0)
        self.dispose()

    def test_current_invoice_evidence_requires_exact_identity(self):
        key = self.connection.fetch_one('select source_unique_key from app.import_batch_rows')['source_unique_key']
        self.assertTrue(key)
        self.connection.execute("""insert into app.invoices(invoice_type,invoice_no,amount,signed_amount,status,source_unique_key)
            values ('input','26110000000000000001',100,100,'active',%s)""",(key,))
        detail = self.service.detail(self.job.import_job_id,actor_account='admin')
        self.assertEqual(detail['files'][0]['identity_match_count'],1)
        self.assertEqual(detail['job']['status'],'failed')
        self.assertEqual(detail['files'][0]['linked_count'],0)

    def test_stable_pagination_and_empty_page(self):
        for _ in range(22): self.jobs.create_or_get_job(import_type='file_import.confirm',created_by='owner')
        first = self.service.list_jobs(page=1,page_size=20)
        second = self.service.list_jobs(page=2,page_size=20)
        self.assertEqual(first['pagination']['total'],23)
        self.assertEqual(len(first['rows']),20)
        self.assertEqual(len(second['rows']),3)
        self.assertFalse(set(r['job_id'] for r in first['rows']) & set(r['job_id'] for r in second['rows']))
        self.assertEqual(self.service.list_jobs(page=9,page_size=20)['rows'],[])

    def test_concurrent_duplicate_is_one_audited_change(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.dispose(), range(2)))
        self.assertEqual(sorted(r['idempotent_replay'] for r in results),[False,True])
        self.assertEqual(self.connection.fetch_one("select count(*) n from audit.events where action='import_job.dispose'")['n'],1)

    def test_retry_racing_disposition_has_only_one_winner(self):
        def retry():
            try: self.jobs.retry_job(self.job.import_job_id,expected_version=self.job.version); return 'retry'
            except ImportJobIdempotencyConflict: return 'conflict'
        def close():
            try: self.dispose(); return 'close'
            except ImportJobIdempotencyConflict: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result() for future in [pool.submit(retry),pool.submit(close)]]
        self.assertEqual(results.count('conflict'),1)
        job = self.jobs.get_job(self.job.import_job_id)
        self.assertTrue(job.status=='pending' and 'disposition' not in job.result_payload or job.status=='failed' and 'disposition' in job.result_payload)

    def test_api_contract_admin_nonadmin_and_owner_isolation(self):
        app = build_local_state_application(data_dir=Path(self.directory.name),test_username='YNSYLP005')
        app._state_store = self.store
        app._audit_service = AuditTrailService(PostgresOperationsAuditRepository(self.connection))
        app._import_job_repository_override = self.jobs
        url = '/api/imports/jobs/'+self.job.import_job_id
        response = app.handle_request('GET',url)
        self.assertEqual(response.status_code,200,response.body)
        self.assertEqual(json.loads(response.body)['job']['created_by'],'owner')
        self.assertEqual(app.handle_request('GET', '/api/background-jobs/import:'+self.job.import_job_id).status_code,404)
        self.assertEqual(app.handle_request('GET','/api/imports/jobs?page=bad').status_code,400)
        response = app.handle_request('POST',url+'/dispose',json.dumps(self.command), request_id='api-dispose')
        self.assertEqual(response.status_code,200,response.body)
        self.assertEqual(json.loads(response.body)['disposition']['actor_account'],'YNSYLP005')
        history = OperationsAuditService(PostgresOperationsAuditRepository(self.connection)).get_operation_history('request:api-dispose')
        self.assertFalse(history['detail']['legacy_evidence_missing'])
        self.assertEqual(history['detail']['target']['fields'][0]['value'], '不再继续导入')
        ordinary = build_local_state_application(data_dir=Path(self.directory.name),test_username='owner')
        ordinary._state_store = self.store
        self.assertEqual(ordinary.handle_request('GET',url).status_code,403)
        self.assertEqual(ordinary.handle_request('POST',url+'/dispose','not json').status_code,403)
