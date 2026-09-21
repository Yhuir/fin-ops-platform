from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fin_ops_platform.services.etc_import_preview_service import EtcImportPreviewService
from fin_ops_platform.services.etc_import_session_store import build_etc_import_session_store
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import EtcService, UploadedEtcZipFile
from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.import_job_queue import ImportJobRepository
from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.object_storage import InMemoryObjectStorageRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database

from tests.app_test_support import build_local_state_application
from tests.test_etc_reconciliation_service import etc_zip, ready_task_with_requirement


class ImportWorkflowCancelApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url))
        self.addCleanup(self.connection.close)
        self.store = PostgresStateStore(data_dir=Path(directory.name), connection=self.connection,
                                       object_storage_repository=InMemoryObjectStorageRepository())
        self.repository = ImportJobRepository(self.connection)
        self.workflow = ImportWorkflowService(self.repository)
        self.app = build_local_state_application(data_dir=Path(directory.name), test_username="YNSYLP005")
        self.app._state_store = self.store
        self.app._import_job_repository_override = self.repository

    def cancel(self, job):
        return self.app.handle_request("POST", f"/api/background-jobs/import:{job.import_job_id}/cancel", "{}")

    def register_file(self):
        service = FileImportService(ImportNormalizationService(), file_store=self.store)
        return self.workflow.register_files(file_service=service, store=self.store, owner="YNSYLP005",
            uploads=[UploadedImportFile("original.xlsx", b"awaiting parser")], request_id="request")

    def test_global_cancel_preparing_file_is_atomic_and_repeatable(self):
        session, job = self.register_file()
        for _ in range(2):
            response = self.cancel(job)
            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(json.loads(response.body)["job"]["status"], "cancelled")
        snapshot = self.store.load_file_import_session_snapshot(session.id)
        self.assertEqual(snapshot["file_imports"]["sessions"][session.id].status, "reverted")

    def test_file_cancel_persistence_failure_rolls_back_job_and_session(self):
        session, job = self.register_file()
        with patch.object(self.store, "save_import_delta", side_effect=ValueError("cancel persistence failed")):
            response = self.cancel(job)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "import_job_state_conflict")
        self.assertEqual(self.repository.get_job(job.import_job_id).status, "pending")
        snapshot = self.store.load_file_import_session_snapshot(session.id)
        self.assertEqual(snapshot["file_imports"]["sessions"][session.id].status, "uploaded")

    def test_global_cancel_preparing_etc_reuses_domain_discard(self):
        task = ready_task_with_requirement(amount="25.00", transaction_at="2026-03-03 12:00:00", invoice_count=1)
        PostgresOpsTaxEtcRepository(self.connection).save_etc_reconciliation_task(task, expected_version=None)
        sessions = build_etc_import_session_store(self.store)
        self.app._etc_import_preview_service = EtcImportPreviewService(
            etc_service=EtcService(state_store=self.store, load_initial_state=False),
            task_service=EtcReconciliationTaskService(state_store=self.store, load_initial_state=False), session_store=sessions)
        jobs = []
        def register(transaction, session):
            jobs.append(self.repository.create_or_get_job(import_type="etc_invoice_import.confirm", stage="prepare",
                import_session_id=session.session_id, created_by="YNSYLP005", transaction=transaction))
        session = self.app._etc_import_preview_service.register(task_id=task.task_id, imported_by="YNSYLP005",
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], register_job=register)
        for _ in range(2):
            response = self.cancel(jobs[0])
            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(json.loads(response.body)["job"]["status"], "cancelled")
        self.assertEqual(sessions.get(session.session_id, load_uploads=False).status, "reverted")

    def test_completed_job_cannot_discard_its_session(self):
        session, job = self.register_file()
        self.connection.execute("update job.import_jobs set status='succeeded' where id=%s", (job.import_job_id,))
        response = self.cancel(job)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.repository.get_job(job.import_job_id).status, "succeeded")
        snapshot = self.store.load_file_import_session_snapshot(session.id)
        self.assertEqual(snapshot["file_imports"]["sessions"][session.id].status, "uploaded")

    def test_tax_and_oa_cancel_only_job_and_preserve_import_data(self):
        for kind in ("tax_certified_import.confirm", "oa_manual_import.create"):
            job = self.repository.create_or_get_job(import_type=kind, created_by="YNSYLP005",
                import_session_id="preserved-source", idempotency_key=kind)
            for _ in range(2):
                response = self.cancel(job)
                self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(self.repository.get_job(job.import_job_id).import_session_id, "preserved-source")
