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
        self.assertEqual(detail['files'][0]['row_count'],1)
        self.assertEqual(detail['files'][0]['identity_match_count'],0)
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

    def test_api_contract_admin_platform_user_and_unlisted_user(self):
        app = build_local_state_application(data_dir=Path(self.directory.name),test_username='YNSYLP005')
        app._state_store = self.store
        app._audit_service = AuditTrailService(PostgresOperationsAuditRepository(self.connection))
        app._import_job_repository_override = self.jobs
        url = '/api/imports/jobs/'+self.job.import_job_id
        response = app.handle_request('GET',url)
        self.assertEqual(response.status_code,200,response.body)
        self.assertEqual(json.loads(response.body)['job']['created_by'],'owner')
        self.assertEqual(app.handle_request('GET', '/api/background-jobs/import:'+self.job.import_job_id).status_code,200)
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

    def test_platform_user_without_import_page_access_can_read_and_close(self):
        app = build_local_state_application(data_dir=Path(self.directory.name))
        app._state_store = self.store
        app._audit_service = AuditTrailService(PostgresOperationsAuditRepository(self.connection))
        app._import_job_repository_override = self.jobs
        app._access_control_service.access_control_snapshot_provider = lambda: {
            "page_access_accounts": [{"username": "test_finops_user", "page_keys": ["cost-statistics"]}]}
        url = '/api/imports/jobs/' + self.job.import_job_id
        response = app.handle_request('GET', url)
        self.assertEqual(response.status_code, 200, response.body)
        preview = app.handle_request('GET', '/imports/files/sessions/' + self.session.id)
        self.assertEqual(preview.status_code, 200, preview.body)
        self.assertEqual(json.loads(preview.body)['session']['imported_by'], 'owner')
        progress = app.handle_request('GET', '/api/background-jobs/import%3A' + self.job.import_job_id)
        self.assertEqual(progress.status_code, 200, progress.body)
        response = app.handle_request('POST', url + '/dispose', json.dumps(self.command), request_id='ordinary-close')
        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(json.loads(response.body)['disposition']['actor_account'], 'test_finops_user')
        self.assertEqual(self.jobs.get_job(self.job.import_job_id).created_by, 'owner')
        self.assertEqual(app.handle_request('GET', '/api/operations/app-health-dashboard').status_code, 403)
        self.assertEqual(app.handle_request('GET', '/api/workbench/settings').status_code, 403)

    def test_shared_access_does_not_expose_private_drafts_or_other_job_types(self):
        workflow = ImportWorkflowService(self.jobs)
        private = self.files.preview_manual_invoice_entries(imported_by='owner', entries=[(BatchType.INPUT_INVOICE, invoice_row('26110000000000000002'))])
        with self.assertRaises(PermissionError):
            workflow.assert_file_session_access(self.files, session_id=private.id, actor='other')
        shared = workflow.assert_file_session_access(self.files, session_id=self.session.id, actor='other')
        self.assertEqual(shared.imported_by, 'owner')
        private_job = self.jobs.create_or_get_job(import_type='oa_manual_import.create', created_by='owner')
        with self.assertRaises(KeyError): workflow.get_accessible(private_job.import_job_id, 'other')
        with self.assertRaises(KeyError): self.service.detail(private_job.import_job_id, actor_account='other')
        with self.assertRaises(KeyError):
            self.service.dispose(private_job.import_job_id, self.command, actor=ACTOR, request_id='private')
        self.assertEqual(self.service.list_jobs(page=1, page_size=20)['pagination']['total'], 1)

    def test_domain_filter_applies_before_pagination_and_totals(self):
        for _ in range(25):
            self.jobs.create_or_get_job(import_type='etc_invoice_import.confirm', created_by='another')
        page = self.service.list_jobs(page=1, page_size=20, domain='imports_invoices')
        self.assertEqual(page['pagination']['total'], 1)
        self.assertEqual(page['rows'][0]['job_id'], self.job.import_job_id)
        self.assertEqual(self.service.list_jobs(page=2, page_size=20, domain='imports_etc_invoices')['pagination']['total'],25)
        with self.assertRaises(ValueError): self.service.list_jobs(page=1, page_size=20, domain='settings')

    def test_cross_user_confirm_keeps_creator_and_persists_actual_actor(self):
        self.connection.execute("update job.import_jobs set status='awaiting_confirmation', stage='prepare', last_error=null where id=%s", (self.job.import_job_id,))
        workflow = ImportWorkflowService(self.jobs, command_actor={'actor_id':'other-id','actor_name':'另一人','actor_account':'YNSYLP005','request_id':'shared-confirm'})
        job = workflow.confirm(session_id=self.session.id, owner='YNSYLP005', import_type='file_import.confirm',
            expected_version=self.job.version, payload={'session_id':self.session.id,'selected_file_ids':[self.session.files[0].id]})
        self.assertEqual(job.created_by, 'owner')
        self.assertEqual(job.payload['owner_user_id'], 'owner')
        self.assertEqual(job.payload['actor_account'], 'YNSYLP005')
        from fin_ops_platform.services.import_job_queue import ImportJobCompletion
        claimed = self.jobs.claim_next('shared-worker', import_job_id=job.import_job_id)
        completion = ImportJobCompletion(claimed)
        self.files.confirm_session(session_id=self.session.id, selected_file_ids=[self.session.files[0].id])
        self.store.save_confirmed_import_delta_with_oa_attachment_promotion(
            self.files.confirmed_session_persistence_payload(session_id=self.session.id, selected_file_ids=[self.session.files[0].id]),
            scope_months=[], promotion_mode='link_existing_only', source_versions={}, completion=completion, result_payload={'created':1})
        self.assertEqual(self.jobs.get_job(job.import_job_id).status, 'succeeded')
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.invoices')['n'], 1)
        audit = self.connection.fetch_one("select actor_account, request_id from audit.events where action='import_job.completed'")
        self.assertEqual(audit['actor_account'], 'YNSYLP005')
        self.assertEqual(audit['request_id'], 'shared-confirm')
        replay = ImportWorkflowService(self.jobs).confirm(session_id=self.session.id, owner='third-user', import_type='file_import.confirm',
            expected_version=self.job.version, payload={'session_id':self.session.id,'selected_file_ids':[self.session.files[0].id]})
        self.assertEqual(replay.import_job_id, job.import_job_id)
        self.assertEqual(replay.payload['actor_account'], 'YNSYLP005')

    def test_a_upload_b_repreview_c_confirm_commits_facts_and_real_actors(self):
        from psycopg.types.json import Jsonb
        from fin_ops_platform.services.import_file_service import UploadedImportFile
        from fin_ops_platform.services.import_job_queue import ImportJobCompletion
        from tests.test_import_closed_loop import workbook_bytes
        self.connection.execute("insert into app.app_settings(settings_key,settings_payload) values ('app_settings',%s)",
            (Jsonb({'access_control_version':1,'page_access_accounts':[
                {'username':'reviewer_b','page_keys':['cost-statistics']},
                {'username':'confirmer_c','page_keys':['cost-statistics']}]}),))
        files = FileImportService(ImportNormalizationService(id_registry=self.store, fact_repository=self.store.import_fact_repository), file_store=self.store)
        session, job = ImportWorkflowService(self.jobs).register_files(file_service=files, store=self.store,
            owner='creator_a', uploads=[UploadedImportFile('shared.xlsx', workbook_bytes())], request_id='upload-a')
        self.connection.execute("update job.import_jobs set status='needs_review' where id=%s", (job.import_job_id,))
        b = ImportWorkflowService(self.jobs, command_actor={'actor_id':'b','actor_name':'B','actor_account':'reviewer_b','request_id':'prepare-b'})
        prepared = b.revise_files(file_service=files, store=self.store, session_id=session.id,
            owner='reviewer_b', selected_file_ids=[session.files[0].id])
        self.assertEqual(prepared.created_by, 'creator_a')
        claimed = self.jobs.claim_next('prepare-worker', import_job_id=job.import_job_id)
        files.prepare_registered_session(session.id)
        self.store.save_import_preview_with_completion(files.preview_session_persistence_payload(session.id),
            completion=ImportJobCompletion(claimed), result_payload={'session_id': session.id})
        current = self.jobs.get_job(job.import_job_id)
        self.assertEqual(current.status, 'awaiting_confirmation')
        c = ImportWorkflowService(self.jobs, command_actor={'actor_id':'c','actor_name':'C','actor_account':'confirmer_c','request_id':'confirm-c'})
        c.assert_file_session_access(files, session_id=session.id, actor='confirmer_c')
        c.confirm(session_id=session.id, owner='confirmer_c', import_type='file_import.confirm', expected_version=current.version,
            payload={'session_id':session.id, 'selected_file_ids':[session.files[0].id]})
        claimed = self.jobs.claim_next('confirm-worker', import_job_id=job.import_job_id)
        files.confirm_session(session_id=session.id, selected_file_ids=[session.files[0].id])
        self.store.save_confirmed_import_delta_with_oa_attachment_promotion(
            files.confirmed_session_persistence_payload(session_id=session.id, selected_file_ids=[session.files[0].id]),
            scope_months=[], promotion_mode='link_existing_only', source_versions={},
            completion=ImportJobCompletion(claimed), result_payload={'created':1})
        current = self.jobs.get_job(job.import_job_id)
        self.assertEqual((current.status,current.created_by,current.payload['actor_account']), ('succeeded','creator_a','confirmer_c'))
        self.assertEqual(files.get_session(session.id).imported_by, 'creator_a')
        self.assertEqual(self.connection.fetch_one('select count(*) n from app.invoices')['n'], 1)
        actors = self.connection.fetch_all("select actor_account,request_id from audit.events where action='import_job.completed'")
        self.assertCountEqual([(a['actor_account'],a['request_id']) for a in actors], [('reviewer_b','prepare-b'),('confirmer_c','confirm-c')])
