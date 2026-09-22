from __future__ import annotations

import json
from dataclasses import replace
import unittest
from io import BytesIO
from unittest.mock import patch

from openpyxl import Workbook

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.imports import ImportNormalizationService
from tests.app_test_support import build_local_state_application
from tests.test_import_closed_loop import HEADERS, invoice_row


def review_workbook(*, corrected=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for index in range(33):
        conflict = index >= 29 and not corrected
        sheet.append(["", "", f"2699000000000000{index:04d}", "供应商", "DIFFERENT" if conflict else "SELLER",
                      "云南溯源科技有限公司", "915300007194052520", "2026-09-01",
                      "133.03" if conflict else "145", "11.97" if conflict else "0", "145"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def seed_review_invoices(imports):
    preview = imports.preview_import(batch_type=BatchType.INPUT_INVOICE, source_name="fixture", imported_by="owner", rows=[
        {**invoice_row(f"2699000000000000{index:04d}"), "amount": "145", "tax_amount": "0", "total_with_tax": "145", "invoice_source": "OA附件解析"}
        for index in range(19, 33)
    ])
    imports.confirm_import(preview.id)


class ImportReviewClosureTests(unittest.TestCase):
    def setUp(self):
        self.imports = ImportNormalizationService()
        seed_review_invoices(self.imports)
        self.files = FileImportService(self.imports)
        self.session = self.files.preview_files(imported_by="owner", uploads=[UploadedImportFile("review.xlsx", review_workbook())])

    def test_all_33_rows_share_summary_and_four_structured_conflicts(self):
        item = self.session.files[0]
        result = self.files.review_rows(session_id=self.session.id, file_id=item.id, offset=0, limit=100)
        self.assertEqual(result["summary"], {"new": 19, "existing": 10, "review": 4, "batch_duplicate": 0})
        self.assertEqual((result["total"], len(result["rows"])), (33, 33))
        self.assertEqual(self.session.audit.error_count, result["summary"]["review"])
        self.assertEqual(self.session.audit.importable_count, result["summary"]["new"])
        self.assertEqual(self.session.audit.existing_duplicate_count, result["summary"]["existing"])
        for row in result["rows"][:4]:
            self.assertEqual(row["category"], "review")
            self.assertEqual({conflict["field"] for conflict in row["conflicts"]}, {"amount", "tax_amount", "seller_tax_no"})
            self.assertEqual(next(c for c in row["conflicts"] if c["field"] == "amount")["current_value"], "145.00")
            self.assertNotIn("580", json.dumps(row))
            self.assertNotIn("file_name", row)
        self.assertTrue(all(row["category"] != "review" for row in result["rows"][4:]))
        page = self.files.review_rows(session_id=self.session.id, file_id=item.id, offset=4, limit=10)
        self.assertEqual(page["rows"], result["rows"][4:14])
        self.assertEqual(page["summary"], result["summary"])
        self.assertTrue(page["has_more"])

    def test_error_cannot_write_partial_facts_then_corrected_file_imports_once(self):
        with self.assertRaisesRegex(ValueError, "require review"):
            self.files.confirm_session(session_id=self.session.id, selected_file_ids=[self.session.files[0].id])
        self.assertEqual(len(self.imports.list_invoices()), 14)
        corrected = self.files.preview_files(imported_by="owner", uploads=[UploadedImportFile("corrected.xlsx", review_workbook(corrected=True))])
        ids = [corrected.files[0].id]
        self.files.assert_files_confirmable(session_id=corrected.id, selected_file_ids=ids)
        self.files.confirm_session(session_id=corrected.id, selected_file_ids=ids)
        self.files.confirm_session(session_id=corrected.id, selected_file_ids=ids)
        self.assertEqual(len(self.imports.list_invoices()), 33)
        self.assertEqual(corrected.status, "confirmed")
        self.files.discard_session(session_id=self.session.id, imported_by="owner")
        self.assertEqual(self.session.status, "reverted")
        self.assertEqual(len(self.imports.list_invoices()), 33)

    def test_file_isolation_unknown_file_and_bounded_pagination(self):
        other = self.files.preview_files(imported_by="owner", uploads=[UploadedImportFile("other.xlsx", review_workbook())])
        with self.assertRaises(KeyError):
            self.files.review_rows(session_id=self.session.id, file_id=other.files[0].id, offset=0, limit=100)
        for offset, limit in [(-1, 20), (0, 0), (0, 101)]:
            with self.assertRaises(ValueError):
                self.files.review_rows(session_id=self.session.id, file_id=self.session.files[0].id, offset=offset, limit=limit)

    def test_confirm_api_rejects_known_errors_before_queue_submission(self):
        app = build_local_state_application()
        self.addCleanup(app._test_import_storage_tmp.cleanup)
        app._file_import_service = self.files
        with patch.object(type(app._import_workflow()), "confirm", side_effect=AssertionError("must not enqueue")):
            response = app._handle_import_file_confirm(json.dumps({"session_id": self.session.id,
                "selected_file_ids": [self.session.files[0].id]}), owner_user_id="owner")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "import_file_session_not_confirmable")
        self.assertEqual(len(self.imports.list_invoices()), 14)

class ImportReviewPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore
        from tests.postgres_test_utils import truncate_test_database
        truncate_test_database(self.url)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)
        self.store = PostgresStateStore(data_dir=Path(self.directory.name), connection=self.connection)
        self.imports = ImportNormalizationService(id_registry=self.store, fact_repository=self.store.import_fact_repository)
        self.files = FileImportService(self.imports, file_store=self.store)
        seed = self.files.preview_manual_invoice_entries(imported_by="YNSYLP005", entries=[
            (BatchType.INPUT_INVOICE, {**invoice_row(f"2699000000000000{index:04d}"), "amount": "145", "tax_amount": "0", "total_with_tax": "145"})
            for index in range(19, 33)
        ])
        ids = [item.id for item in seed.files]
        self.files.confirm_session(session_id=seed.id, selected_file_ids=ids)
        self.store.save_import_delta(self.files.confirmed_session_persistence_payload(session_id=seed.id, selected_file_ids=ids))

    def test_durable_prepare_review_corrected_commit_and_batch_query(self):
        from fin_ops_platform.services.import_job_queue import ImportJobCompletion, ImportJobRepository
        from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
        from fin_ops_platform.services.runtime_worker_handlers import ImportRuntimeProcessorFactory
        jobs = ImportJobRepository(self.connection)
        workflow = ImportWorkflowService(jobs)
        session, job = workflow.register_files(file_service=self.files, store=self.store, owner="YNSYLP005",
            uploads=[UploadedImportFile("review.xlsx", review_workbook())], request_id="review-fixture")
        claimed = jobs.claim_next("review-test", import_job_id=job.import_job_id)
        factory = ImportRuntimeProcessorFactory(data_dir=self.directory.name, connection=self.connection)
        claimed = replace(claimed, completion=ImportJobCompletion(claimed))
        factory.build_processors()["file_import.confirm"](claimed)
        job = jobs.get_job(job.import_job_id)
        self.assertEqual(job.status, "needs_review")
        snapshot = self.store.load_file_import_session_snapshot(session.id)
        restored_imports = ImportNormalizationService.from_snapshot(snapshot["imports"], id_registry=self.store, fact_repository=self.store.import_fact_repository)
        restored = FileImportService.from_snapshot(restored_imports, snapshot["file_imports"], file_store=self.store)
        repository = self.store.import_fact_repository
        with patch.object(repository, "find_invoices_by_identity_keys", wraps=repository.find_invoices_by_identity_keys) as query:
            page = restored.review_rows(session_id=session.id, file_id=session.files[0].id, offset=0, limit=100)
        self.assertEqual(query.call_count, 1)
        self.assertEqual(page["summary"], {"new": 19, "existing": 10, "review": 4, "batch_duplicate": 0})
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 14)
        corrected, next_job = workflow.register_files(file_service=self.files, store=self.store, owner="YNSYLP005",
            uploads=[UploadedImportFile("corrected.xlsx", review_workbook(corrected=True))], request_id="corrected-fixture")
        next_claim = jobs.claim_next("review-test", import_job_id=next_job.import_job_id)
        next_claim = replace(next_claim, completion=ImportJobCompletion(next_claim))
        factory.build_processors()["file_import.confirm"](next_claim)
        next_job = jobs.get_job(next_job.import_job_id)
        self.assertEqual(next_job.status, "awaiting_confirmation")
        snapshot = self.store.load_file_import_session_snapshot(corrected.id)
        restored_imports = ImportNormalizationService.from_snapshot(snapshot["imports"], id_registry=self.store, fact_repository=repository)
        restored = FileImportService.from_snapshot(restored_imports, snapshot["file_imports"], file_store=self.store)
        ids = [corrected.files[0].id]
        restored.assert_files_confirmable(session_id=corrected.id, selected_file_ids=ids)
        workflow.confirm(session_id=corrected.id, owner="YNSYLP005", import_type="file_import.confirm",
            expected_version=next_job.version, payload={"session_id": corrected.id, "selected_file_ids": ids})
        commit = jobs.claim_next("review-test", import_job_id=next_job.import_job_id)
        restored.confirm_session(session_id=corrected.id, selected_file_ids=ids)
        self.store.save_confirmed_import_delta_with_oa_attachment_promotion(
            restored.confirmed_session_persistence_payload(session_id=corrected.id, selected_file_ids=ids),
            scope_months=[], promotion_mode="link_existing_only", source_versions={},
            completion=ImportJobCompletion(commit), result_payload={"created": 19})
        self.assertEqual(jobs.get_job(next_job.import_job_id).status, "succeeded")
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 33)
