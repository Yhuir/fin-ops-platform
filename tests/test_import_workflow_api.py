from __future__ import annotations

import json
import unittest

from tests.app_test_support import build_local_state_application as build_application
from tests.app_test_support import install_durable_import_queue
from fin_ops_platform.services.import_file_service import UploadedImportFile
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.import_workflow_service import ImportWorkflowService


class ImportWorkflowApiTests(unittest.TestCase):
    def setUp(self):
        self.app = build_application()
        self.queue = install_durable_import_queue(self.app)
        self.workflow = ImportWorkflowService(self.queue)

    def make_job(self, owner="test_finops_user"):
        return self.queue.create_or_get_job(
            import_type="file_import.confirm", import_session_id="session-1",
            idempotency_key="request-1", created_by=owner, stage="prepare",
            status="awaiting_confirmation", payload={"session_id": "session-1", "route": "/imports/invoices"},
        )

    def test_same_upload_request_returns_same_session_and_changed_bytes_conflict(self):
        args = dict(file_service=self.app._file_import_service, store=self.app._state_store,
                    owner="test_finops_user", request_id="upload-1")
        _, first = self.workflow.register_files(**args, uploads=[UploadedImportFile("one.xlsx", b"first")])
        _, repeated = self.workflow.register_files(**args, uploads=[UploadedImportFile("one.xlsx", b"first")])
        self.assertEqual(first.import_job_id, repeated.import_job_id)
        self.assertEqual(len(self.queue.jobs), 1)
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.workflow.register_files(**args, uploads=[UploadedImportFile("one.xlsx", b"changed")])
        self.assertEqual(len(self.queue.jobs), 1)

    def test_progress_is_summary_and_owned_result_retains_preview(self):
        job = self.make_job()
        self.queue.update(job.import_job_id, result_payload={"session": {"private": "preview"}, "created": 0})
        summary = self.app.handle_request("GET", "/api/background-jobs/active")
        self.assertEqual(summary.status_code, 200)
        payload = json.loads(summary.body)["jobs"][0]
        self.assertEqual(payload["status"], "awaiting_confirmation")
        self.assertNotIn("session", payload["result_summary"])
        self.assertEqual(payload["route"], "/imports/invoices")
        result = self.app.handle_request("GET", f"/api/background-jobs/import:{job.import_job_id}/result")
        self.assertEqual(json.loads(result.body)["result"]["session"], {"private": "preview"})

    def test_other_owner_cannot_read_cancel_or_retry(self):
        job = self.make_job(owner="another-user")
        for method, suffix in [("GET", ""), ("GET", "/result"), ("POST", "/cancel"), ("POST", "/retry")]:
            response = self.app.handle_request(method, f"/api/background-jobs/import:{job.import_job_id}{suffix}", body="{}")
            self.assertEqual(response.status_code, 404)
        self.assertEqual(self.queue.get_job(job.import_job_id).status, "awaiting_confirmation")

    def test_retry_preserves_confirmed_selection_and_success_is_idempotent(self):
        job = self.make_job()
        payload = {"session_id": "session-1", "selected_file_ids": ["file-1"]}
        committed = self.workflow.confirm(session_id="session-1", owner="test_finops_user",
                                          import_type="file_import.confirm", payload=payload, expected_version=job.version)
        self.queue.update(job.import_job_id, status="failed", last_error="storage unavailable")
        retried = self.workflow.retry(job.import_job_id, "test_finops_user")
        self.assertEqual(retried.stage, "commit")
        self.assertEqual(retried.payload, committed.payload)
        self.queue.update(job.import_job_id, status="succeeded", result_payload={"created": 1})
        self.assertEqual(self.workflow.retry(job.import_job_id, "test_finops_user").status, "succeeded")
        self.assertEqual(len(self.queue.jobs), 1)

    def test_changed_selection_after_acceptance_is_rejected(self):
        job = self.make_job()
        args = dict(session_id="session-1", owner="test_finops_user", import_type="file_import.confirm", expected_version=job.version)
        self.workflow.confirm(**args, payload={"session_id": "session-1", "selected_file_ids": ["file-1"]})
        with self.assertRaises(ImportJobIdempotencyConflict):
            self.workflow.confirm(**args, payload={"session_id": "session-1", "selected_file_ids": ["file-2"]})


if __name__ == "__main__":
    unittest.main()
