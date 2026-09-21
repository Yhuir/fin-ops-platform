from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_file_service import (
    FileImportService,
    UploadedImportFile,
    normalize_signed_debit_credit_columns,
)
from fin_ops_platform.services.import_job_queue import ImportJobCompletion, ImportJobRepository
from fin_ops_platform.services.import_workflow_service import ImportWorkflowService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from openpyxl import Workbook
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from test_import_file_service import FakeImportIdStore

HEADERS = ["发票代码", "发票号码", "数电发票号码", "销方名称", "销方识别号", "购买方名称", "购方识别号", "开票日期", "金额", "税额", "价税合计"]


def invoice_row(number: str = "26110000000000000001") -> dict:
    return {"digital_invoice_no": number, "invoice_date": "2026-09-01", "counterparty_name": "供应商",
            "seller_name": "供应商", "seller_tax_no": "SELLER", "buyer_name": "云南溯源科技有限公司",
            "buyer_tax_no": "915300007194052520", "amount": "100", "tax_amount": "13", "total_with_tax": "113"}


def workbook_bytes(*, sheets: int = 1, mixed: bool = False, missing_identity: bool = False) -> bytes:
    workbook = Workbook()
    for index in range(sheets):
        sheet = workbook.active if index == 0 else workbook.create_sheet()
        sheet.append(HEADERS)
        sheet.append(["", "" if missing_identity else f"261100000000000000{index + 1:02d}", "", "供应商", "SELLER", "云南溯源科技有限公司", "915300007194052520", "2026-09-01", "100", "13", "113"])
        if mixed:
            sheet.append(["", "26110000000000000099", "", "云南溯源科技有限公司", "915300007194052520", "客户", "BUYER", "2026-09-01", "100", "13", "113"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


class ImportClosedLoopTests(unittest.TestCase):
    def test_reversal_with_numeric_zero_in_other_column(self):
        for zero in (None, "", "0", "0.00", "0.000"):
            self.assertEqual(normalize_signed_debit_credit_columns("-1050.23", zero), (None, "1050.23"))
            self.assertEqual(normalize_signed_debit_credit_columns(zero, "-1050.23"), ("1050.23", None))
        self.assertEqual(normalize_signed_debit_credit_columns("-1050.23", "5"), ("-1050.23", "5"))

    def test_upload_registration_does_not_parse_and_survives_restore(self):
        store = FakeImportIdStore()
        service = FileImportService(ImportNormalizationService(), file_store=store)
        with patch.object(service, "_read_rows", side_effect=AssertionError("must not parse during registration")):
            registered = service.register_uploads(imported_by="owner", uploads=[UploadedImportFile(file_name="invoice.xlsx", content=workbook_bytes())])
        self.assertEqual(registered.status, "uploaded")
        self.assertEqual(registered.files[0].row_count, 0)
        restored = FileImportService.from_snapshot(ImportNormalizationService(), service.snapshot(), file_store=store)
        prepared = restored.prepare_registered_session(registered.id)
        self.assertEqual(prepared.status, "preview_ready")
        self.assertEqual(prepared.audit.importable_count, 1)
        restored.confirm_session(session_id=prepared.id, selected_file_ids=[prepared.files[0].id])

    def test_missing_identity_multiple_sheets_and_mixed_directions_never_silently_succeed(self):
        for kwargs in ({"missing_identity": True}, {"sheets": 2}, {"mixed": True}):
            service = FileImportService(ImportNormalizationService())
            session = service.preview_files(imported_by="owner", uploads=[UploadedImportFile(file_name="invoice.xlsx", content=workbook_bytes(**kwargs))])
            self.assertNotEqual(session.files[0].status, "preview_ready")
            with self.assertRaises(ValueError):
                service.confirm_session(session_id=session.id, selected_file_ids=[session.files[0].id])

    def test_selected_scope_with_bad_row_has_zero_facts(self):
        imports = ImportNormalizationService()
        service = FileImportService(imports)
        session = service.preview_manual_invoice_entries(imported_by="owner", entries=[
            (BatchType.INPUT_INVOICE, invoice_row()),
            (BatchType.INPUT_INVOICE, {**invoice_row("26110000000000000002"), "invoice_date": "invalid"}),
        ])
        with self.assertRaisesRegex(ValueError, "require review"):
            service.confirm_session(session_id=session.id, selected_file_ids=[item.id for item in session.files])
        self.assertEqual(imports.list_invoices(), [])
        self.assertTrue(all(item.status == "preview_ready" for item in session.files))

    def test_bank_distinct_references_share_fingerprint_without_quadratic_identity_work(self):
        imports = ImportNormalizationService()
        rows = [{"account_no": "62220001", "trade_time": "2026-09-01 10:00:00", "counterparty_name": "供应商",
                 "debit_amount": "100", "balance": "10000", "bank_serial_no": f"SERIAL-{i}"} for i in range(100)]
        batch = imports.preview_import(batch_type=BatchType.BANK_TRANSACTION, source_name="synthetic", imported_by="owner", rows=rows)
        with patch.object(imports._object_identity_policy, "identify_bank_transaction", wraps=imports._object_identity_policy.identify_bank_transaction) as identify:
            imports.confirm_imports([batch.id], reject_issues=True)
        self.assertEqual(len(imports.list_transactions()), 100)
        self.assertLess(identify.call_count, 500)

    def test_oa_incomplete_financial_evidence_does_not_create_facts_or_overwrite_tax_header(self):
        imports = ImportNormalizationService()
        evidence = {"invoice_no": "26110000000000000001", "issue_date": "2026-09-01", "amount": "", "net_amount": "",
                    "tax_amount": "", "total_with_tax": "113", "invoice_type": "进项发票", "evidence_type": "tax_invoice",
                    "financial_review_reason": "Missing net and tax"}
        self.assertIsNone(imports.upsert_oa_attachment_invoice(evidence, allow_create=True))
        batch = imports.preview_import(batch_type=BatchType.INPUT_INVOICE, source_name="tax header", imported_by="owner", rows=[invoice_row()])
        imports.confirm_import(batch.id)
        invoice = imports.list_invoices()[0]
        before = (invoice.amount, invoice.tax_amount, invoice.total_with_tax)
        linked = imports.upsert_oa_attachment_invoice(evidence, oa_form_id="form-1", oa_row_id="row-1", allow_create=True)
        self.assertEqual(linked.id, invoice.id)
        imports.upsert_oa_attachment_invoice({**evidence, "financial_review_reason": "", "amount": "113", "net_amount": "113", "tax_amount": "0"}, allow_create=True)
        self.assertEqual((invoice.amount, invoice.tax_amount, invoice.total_with_tax), before)
        self.assertEqual(len(imports.list_invoices()), 1)

    def test_second_file_failure_rolls_back_first_file_and_can_retry(self):
        imports = ImportNormalizationService()
        service = FileImportService(imports)
        session = service.preview_manual_invoice_entries(imported_by="owner", entries=[
            (BatchType.INPUT_INVOICE, invoice_row()), (BatchType.INPUT_INVOICE, invoice_row("26110000000000000002")),
        ])
        original = imports._persist_created_row
        def fail_second(batch_type, row_result, normalized):
            if normalized["digital_invoice_no"].endswith("02"):
                raise RuntimeError("second file failed")
            return original(batch_type, row_result, normalized)
        with patch.object(imports, "_persist_created_row", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second file failed"):
                service.confirm_session(session_id=session.id, selected_file_ids=[item.id for item in session.files])
        self.assertEqual(imports.list_invoices(), [])
        restored = service.get_session(session.id)
        self.assertTrue(all(item.status == "preview_ready" for item in restored.files))
        service.confirm_session(session_id=session.id, selected_file_ids=[item.id for item in restored.files])
        self.assertEqual(len(imports.list_invoices()), 2)

    def test_unselected_file_remains_available_for_later_confirmation(self):
        imports = ImportNormalizationService()
        service = FileImportService(imports)
        session = service.preview_manual_invoice_entries(imported_by="owner", entries=[
            (BatchType.INPUT_INVOICE, invoice_row()), (BatchType.INPUT_INVOICE, invoice_row("26110000000000000002")),
        ])
        service.confirm_session(session_id=session.id, selected_file_ids=[session.files[0].id])
        self.assertEqual(session.files[1].status, "preview_ready")
        self.assertEqual(session.status, "preview_ready")
        service.confirm_session(session_id=session.id, selected_file_ids=[session.files[1].id])
        self.assertEqual(len(imports.list_invoices()), 2)

    def test_financial_total_conflict_is_visible_and_blocks_scope(self):
        imports = ImportNormalizationService()
        service = FileImportService(imports)
        session = service.preview_manual_invoice_entries(imported_by="owner", entries=[
            (BatchType.INPUT_INVOICE, {**invoice_row(), "total_with_tax": "100"}),
        ])
        self.assertEqual(session.files[0].error_count, 1)
        with self.assertRaises(ValueError):
            service.confirm_session(session_id=session.id, selected_file_ids=[session.files[0].id])
        self.assertEqual(imports.list_invoices(), [])


class ImportClosedLoopPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = PostgresStateStore(data_dir=Path(self.temp.name), connection=self.connection)
        self.imports = ImportNormalizationService(id_registry=self.store, fact_repository=self.store.import_fact_repository)
        self.files = FileImportService(self.imports)
        self.session = self.files.preview_manual_invoice_entries(imported_by="YNSYLP005", entries=[(BatchType.INPUT_INVOICE, invoice_row())])
        self.repository = ImportJobRepository(self.connection)
        self.job = self.store.save_import_registration(
            self.files.preview_session_persistence_payload(self.session.id),
            register_job=lambda transaction: self.repository.create_or_get_job(
                import_type="file_import.confirm", import_session_id=self.session.id,
                created_by="YNSYLP005", payload={"session_id": self.session.id, "selected_file_ids": [self.session.files[0].id]},
                transaction=transaction,
            ),
        )

    def test_registration_job_failure_does_not_leave_a_durable_orphan(self):
        other = self.files.preview_manual_invoice_entries(imported_by="YNSYLP005", entries=[
            (BatchType.INPUT_INVOICE, invoice_row("26110000000000000002")),
        ])
        def fail_registration(_transaction):
            raise RuntimeError("job admission failed")
        with self.assertRaisesRegex(RuntimeError, "job admission failed"):
            self.store.save_import_registration(self.files.preview_session_persistence_payload(other.id), register_job=fail_registration)
        with self.assertRaises(KeyError):
            self.store.load_file_import_session_snapshot(other.id)
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.import_batches")["count"], 1)

    def test_concurrent_same_request_registers_one_session_and_job(self):
        barrier = Barrier(2)
        request_id = "concurrent-upload"
        def upload():
            connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
            try:
                store = PostgresStateStore(data_dir=Path(self.temp.name), connection=connection)
                files = FileImportService(ImportNormalizationService(id_registry=store, fact_repository=store.import_fact_repository), file_store=store)
                repository = ImportJobRepository(connection)
                lookup = repository.get_by_idempotency_key
                first = True
                def synchronized(key, *, created_by):
                    nonlocal first
                    result = lookup(key, created_by=created_by)
                    if first:
                        first = False
                        barrier.wait(timeout=10)
                    return result
                repository.get_by_idempotency_key = synchronized
                _, job = ImportWorkflowService(repository).register_files(
                    file_service=files, store=store, owner="YNSYLP005", request_id=request_id,
                    uploads=[UploadedImportFile(file_name="invoice.xlsx", content=workbook_bytes())],
                )
                return job.import_job_id, job.import_session_id
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: upload(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.connection.fetch_one("select count(distinct session_id) as count from app.import_files")["count"], 2)
        self.assertEqual(self.connection.fetch_one("select count(*) as count from job.import_jobs")["count"], 2)

    def test_upload_admission_failure_cleans_only_unreferenced_original(self):
        files = FileImportService(ImportNormalizationService(id_registry=self.store), file_store=self.store)
        with patch.object(self.repository, "create_or_get_job", side_effect=RuntimeError("admission unavailable")):
            with self.assertRaisesRegex(RuntimeError, "admission unavailable"):
                ImportWorkflowService(self.repository).register_files(file_service=files, store=self.store, owner="YNSYLP005",
                    uploads=[UploadedImportFile(file_name="invoice.xlsx", content=workbook_bytes())], request_id="failed")
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.import_files")["count"], 1)
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.file_objects where tombstoned_at is null")["count"], 0)
        self.assertEqual([path for path in Path(self.temp.name).rglob("*") if path.is_file()], [])

    def test_lost_registration_response_preserves_committed_original_and_repeats_job(self):
        files = FileImportService(ImportNormalizationService(id_registry=self.store), file_store=self.store)
        workflow = ImportWorkflowService(self.repository)
        uploads = [UploadedImportFile(file_name="invoice.xlsx", content=workbook_bytes())]
        save = self.store.save_import_registration
        def commit_then_lose_response(*args, **kwargs):
            save(*args, **kwargs)
            raise RuntimeError("response lost")
        with patch.object(self.store, "save_import_registration", side_effect=commit_then_lose_response):
            with self.assertRaisesRegex(RuntimeError, "response lost"):
                workflow.register_files(file_service=files, store=self.store, owner="YNSYLP005", uploads=uploads, request_id="lost")
        _, repeated = workflow.register_files(file_service=files, store=self.store, owner="YNSYLP005", uploads=uploads, request_id="lost")
        self.assertEqual(repeated.status, "pending")
        snapshot = self.store.load_file_import_session_snapshot(repeated.import_session_id)
        item = snapshot["file_imports"]["sessions"][repeated.import_session_id].files[0]
        self.assertEqual(self.store.read_import_file(item.stored_file_path), uploads[0].content)

    def test_scoped_restore_does_not_load_canonical_pool(self):
        snapshot = self.store.load_file_import_session_snapshot(self.session.id)
        self.assertEqual(set(snapshot["file_imports"]["sessions"]), {self.session.id})
        self.assertNotIn("invoices", snapshot["imports"])
        self.assertEqual(set(snapshot["imports"]["batches"]), {self.session.files[0].preview_batch_id})
        restored_imports = ImportNormalizationService.from_snapshot(snapshot["imports"], id_registry=self.store, fact_repository=self.store.import_fact_repository)
        restored = FileImportService.from_snapshot(restored_imports, snapshot["file_imports"])
        restored.confirm_session(session_id=self.session.id, selected_file_ids=[self.session.files[0].id])
        self.assertEqual(len(restored_imports.list_invoices()), 1)

    def _confirm(self, completion):
        self.files.confirm_session(session_id=self.session.id, selected_file_ids=[self.session.files[0].id])
        return self.store.save_confirmed_import_delta_with_oa_attachment_promotion(
            self.files.confirmed_session_persistence_payload(session_id=self.session.id, selected_file_ids=[self.session.files[0].id]),
            scope_months=[], promotion_mode="link_existing_only", source_versions={},
            completion=completion, result_payload={"created": 1, "session_id": self.session.id},
        )

    def test_facts_and_success_are_committed_together(self):
        claimed = self.repository.claim_next("worker", import_job_id=self.job.import_job_id)
        result = self._confirm(ImportJobCompletion(claimed))
        self.assertEqual(result["created"], 1)
        self.assertEqual(self.repository.get_job(self.job.import_job_id).status, "succeeded")
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.invoices")["count"], 1)

    def test_failure_to_write_success_rolls_back_all_facts(self):
        claimed = self.repository.claim_next("worker", import_job_id=self.job.import_job_id)
        with patch.object(ImportJobCompletion, "succeed", side_effect=RuntimeError("commit receipt failed")):
            with self.assertRaisesRegex(RuntimeError, "receipt failed"):
                self._confirm(ImportJobCompletion(claimed))
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.invoices")["count"], 0)
        self.assertEqual(self.repository.get_job(self.job.import_job_id).status, "processing")
        snapshot = self.store.load_file_import_session_snapshot(self.session.id)
        self.assertEqual(snapshot["file_imports"]["sessions"][self.session.id].files[0].status, "preview_ready")

    def test_stale_worker_is_fenced_before_any_fact_write(self):
        claimed = self.repository.claim_next("worker", import_job_id=self.job.import_job_id)
        stale = replace(claimed, claim_version=claimed.claim_version - 1)
        with self.assertRaisesRegex(RuntimeError, "ownership|lease|claim|Lease|Import"):
            self._confirm(ImportJobCompletion(stale))
        self.assertEqual(self.connection.fetch_one("select count(*) as count from app.invoices")["count"], 0)
