from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.services.import_job_queue import ImportJobRepository, ImportJobWorker
from fin_ops_platform.services.invoice_kind import invoice_kind_fields
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.tax_certified_imports import (
    PostgresTaxCertifiedImportRepository,
    TaxCertifiedImportConflict,
)
from fin_ops_platform.services.postgres_repositories.tax_offset import PostgresTaxOffsetCanonicalRepository
from fin_ops_platform.services.runtime_worker import RuntimeWorkerResult
from fin_ops_platform.services.shared_import_processor import SharedImportProcessor
from fin_ops_platform.services.tax_certified_import_application_service import TaxCertifiedImportApplicationService
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQuery
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database

from tests.test_tax_certified_import_service import certified_upload


class TaxCertifiedImportPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        acl = {"access_control_version": 1, "page_access_accounts": [{"username": "owner", "page_keys": ["tax-offset"]}]}
        self.connection.execute("INSERT INTO app.app_settings(settings_key,settings_payload,raw_payload) VALUES ('app_settings',%s,%s)",
                                (jsonb(acl), jsonb({"normalized_payload": acl})))
        self.repository = PostgresTaxCertifiedImportRepository(self.connection)
        self.service = TaxCertifiedImportService(repository=self.repository)
        self.jobs = ImportJobRepository(self.connection)
        self.processor = SharedImportProcessor(self.connection)
        self.worker = ImportJobWorker(repository=self.jobs, worker_id="cert-test-worker",
                                    processors={"tax_certified_import.confirm": self.processor.tax_certified})
        self.invoice_id = self.connection.fetch_one("""
            INSERT INTO app.invoices(invoice_type,invoice_no,invoice_code,digital_invoice_no,buyer_tax_no,
                amount,signed_amount,tax_amount,invoice_date,invoice_month,status,raw_payload)
            VALUES ('input','NUMBER-1','CODE-1','TEST-DIGITAL-1','TEST-BUYER',100,100,13,'2026-08-15','2026-08-01','active',%s)
            RETURNING id::text AS id
        """, (jsonb({"normalized_payload": {**invoice_kind_fields("增值税专用发票")}}),))["id"]

    def preview(self, **kwargs):
        return self.service.preview_files(imported_by="owner", uploads=[certified_upload(**kwargs)])

    def confirm(self, session, **kwargs):
        return self.service.confirm_session(session.id, actor_id="owner", **kwargs)

    def current(self):
        row = self.connection.fetch_one("SELECT raw_payload,status,version,invoice_id::text AS invoice_id FROM app.tax_certified_import_records ORDER BY created_at DESC LIMIT 1")
        return {**row["raw_payload"]["normalized_payload"], "status": row["status"], "version": row["version"], "matched_invoice_id": row["invoice_id"]}

    def test_worker_preview_commit_query_and_revoke_closed_loop(self):
        app = TaxCertifiedImportApplicationService(certified_import_service=self.service)
        preview = app.preview_payload(imported_by="owner", uploads=[certified_upload()])
        self.assertEqual(preview["summary"]["matched_invoice_count"], 1)
        self.assertEqual(preview["files"][0]["rows"][0]["dedupe_status"], "new")
        job = self.jobs.create_or_get_job(import_type="tax_certified_import.confirm", created_by="owner",
                                         payload={"session_id": preview["session"]["id"]})
        self.assertEqual(self.worker.run_once(), RuntimeWorkerResult.PROCESSED)
        result = self.jobs.get_job(job.import_job_id)
        self.assertEqual(result.status, "succeeded")
        batch = result.result_payload["batch"]
        self.assertEqual(batch["persisted_record_count"], 1)
        row = self.current()
        self.assertEqual(row["matched_invoice_id"], self.invoice_id)
        page = PostgresTaxOffsetCanonicalRepository(self.connection).load_page(TaxOffsetQuery())
        self.assertEqual(page["rows"][0]["certification_status"], "certified")
        self.assertEqual(str(page["rows"][0]["amount"]), "100.00")
        invoice = self.connection.fetch_one("SELECT amount,tax_amount FROM app.invoices WHERE id=%s", (self.invoice_id,))
        self.assertEqual(str(invoice["amount"]), "100.000000")
        self.assertEqual(str(invoice["tax_amount"]), "13.000000")
        revoked = self.service.revoke_batch(batch["id"], actor_id="owner", expected_version=1)
        self.assertEqual((revoked["status"], revoked["revoked_record_count"]), ("revoked", 1))
        self.assertEqual(self.current()["status"], "revoked")
        page = PostgresTaxOffsetCanonicalRepository(self.connection).load_page(TaxOffsetQuery())
        self.assertEqual(page["rows"][0]["certification_status"], "uncertified")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], 2)

    def test_reimport_does_not_claim_original_evidence_or_restore_revoked_batch(self):
        first_session = self.preview()
        first = self.confirm(first_session)
        second = self.confirm(self.preview())
        self.assertEqual((second["persisted_record_count"], second["duplicate_count"]), (0, 1))
        self.service.revoke_batch(second["id"], actor_id="owner", expected_version=1)
        self.assertEqual(self.current()["batch_id"], first["id"])
        self.assertEqual(self.current()["status"], "active")
        self.service.revoke_batch(first["id"], actor_id="owner", expected_version=1)
        self.assertEqual(self.confirm(first_session)["status"], "revoked")
        self.assertEqual(self.current()["status"], "revoked")

    def test_explicit_correction_and_old_revoke_cannot_undo_new_contribution(self):
        first = self.confirm(self.preview())
        correction_session = self.preview(deductible="9")
        with self.assertRaises(TaxCertifiedImportConflict):
            self.confirm(correction_session)
        self.assertEqual(self.current()["deductible_tax_amount"], "0")
        correction = {"unique_key": "digital:TEST-DIGITAL-1", "expected_version": 1}
        corrected = self.confirm(correction_session, corrections=[correction])
        self.assertEqual(self.current()["version"], 2)
        self.assertNotIn("previous_records", corrected)
        with self.assertRaises(TaxCertifiedImportConflict):
            self.service.revoke_batch(first["id"], actor_id="owner", expected_version=1)
        self.assertEqual(self.current()["status"], "active")
        self.assertEqual(self.current()["batch_id"], corrected["id"])
        stale = self.preview(deductible="10")
        with self.assertRaises(TaxCertifiedImportConflict):
            self.confirm(stale, corrections=[correction])

    def test_owner_versions_and_missing_identity_match_are_enforced(self):
        session = self.preview()
        with self.assertRaises(PermissionError):
            self.service.confirm_session(session.id, actor_id="other")
        batch = self.confirm(session)
        with self.assertRaises(PermissionError):
            self.service.revoke_batch(batch["id"], actor_id="other", expected_version=1)
        with self.assertRaises(TaxCertifiedImportConflict):
            self.service.revoke_batch(batch["id"], actor_id="owner", expected_version=2)
        mismatch = self.preview(digital="OTHER-DIGITAL", buyer="OTHER-BUYER")
        outside = self.confirm(mismatch)
        self.assertEqual(outside["persisted_record_count"], 1)
        unmatched = next(row for row in self.repository.records_payload()["records"] if row["unique_key"] == "digital:OTHER-DIGITAL")
        self.assertIsNone(unmatched["matched_invoice_id"])
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.invoices")["n"], 1)

    def test_parallel_identical_imports_create_one_effective_contribution(self):
        sessions = [self.preview(), self.preview()]
        with ThreadPoolExecutor(max_workers=2) as executor:
            batches = list(executor.map(self.confirm, sessions))
        self.assertEqual(sorted(batch["persisted_record_count"] for batch in batches), [0, 1])
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.tax_certified_import_records")["n"], 1)

    def test_worker_audit_failure_rolls_back_batch_records_and_success(self):
        session = self.preview()
        job = self.jobs.create_or_get_job(import_type="tax_certified_import.confirm", created_by="owner",
                                         payload={"session_id": session.id}, max_attempts=1)
        with patch.object(SharedImportProcessor, "_record_completion", side_effect=RuntimeError("test audit failure")):
            self.worker.run_once()
        self.assertNotEqual(self.jobs.get_job(job.import_job_id).status, "succeeded")
        self.assertEqual(self.repository.records_payload()["records"], [])
        self.assertEqual(self.repository.records_payload()["batches"], [])
        self.assertEqual(self.service.get_session(session.id).status, "preview_ready")

    def test_missing_amounts_persist_null_and_multiple_sources_conflict(self):
        self.confirm(self.preview(amount=None, tax=None, deductible=None))
        row = self.connection.fetch_one("SELECT amount,tax_amount,deductible_tax_amount FROM app.tax_certified_import_records")
        self.assertEqual(row, {"amount": None, "tax_amount": None, "deductible_tax_amount": None})
        session = self.service.preview_files(imported_by="owner", uploads=[certified_upload(deductible="1"), certified_upload(deductible="2")])
        with self.assertRaises(TaxCertifiedImportConflict):
            self.confirm(session)

    def test_historical_migration_preserves_deleted_unknown_and_strong_buyer_identity(self):
        for key, status, buyer in (("legacy-match", "已勾选", "TEST-BUYER"),
                                  ("legacy-deleted", "deleted", "TEST-BUYER"),
                                  ("legacy-unknown", "unexpected", "TEST-BUYER"),
                                  ("legacy-other", "已认证", "OTHER-BUYER"),
                                  ("legacy-amount-conflict", "已认证", "TEST-BUYER"),
                                  ("legacy-identity-conflict", "已认证", "TEST-BUYER")):
            self.connection.execute("""INSERT INTO app.tax_certified_import_records
                (certified_unique_key,digital_invoice_no,status,raw_payload) VALUES (%s,'TEST-DIGITAL-1',%s,%s)""",
                (key, status, jsonb({"normalized_payload": {"taxpayer_tax_no": buyer,
                    "selection_time": "2026-10-02 13:14:15", "deductible_tax_amount": "0"}})))
        self.connection.execute("UPDATE app.tax_certified_import_records SET amount=999 WHERE certified_unique_key='legacy-amount-conflict'")
        self.connection.execute("UPDATE app.tax_certified_import_records SET invoice_code='OTHER-CODE' WHERE certified_unique_key='legacy-identity-conflict'")
        batch = self.connection.fetch_one("INSERT INTO app.tax_certified_import_batches(batch_id,status,raw_payload) VALUES ('historical-batch','confirmed',%s) RETURNING id",
            (jsonb({"normalized_payload": {"id": "historical-batch"}}),))
        self.connection.execute("UPDATE app.tax_certified_import_records SET batch_id=%s WHERE certified_unique_key='legacy-match'", (batch["id"],))
        migration = Path("backend/src/fin_ops_platform/postgres/migrations/0187_tax_certification_evidence.sql").read_text()
        backfill = migration[migration.index("UPDATE app.tax_certified_import_records SET status="):migration.index("CREATE UNIQUE INDEX")]
        self.connection.execute(backfill)
        records = {row["certified_unique_key"]: row for row in self.connection.fetch_all(
            "SELECT certified_unique_key,status,match_status,invoice_id::text AS invoice_id FROM app.tax_certified_import_records")}
        self.assertEqual(records["legacy-match"]["invoice_id"], self.invoice_id)
        self.assertEqual(records["legacy-match"]["status"], "active")
        self.assertEqual(records["legacy-deleted"]["status"], "deleted")
        self.assertEqual(records["legacy-unknown"]["status"], "unexpected")
        self.assertIsNone(records["legacy-other"]["invoice_id"])
        self.assertEqual(records["legacy-other"]["match_status"], "unresolved")
        self.assertIsNone(records["legacy-amount-conflict"]["invoice_id"])
        self.assertIsNone(records["legacy-identity-conflict"]["invoice_id"])
        stored_batch = self.connection.fetch_one("SELECT raw_payload FROM app.tax_certified_import_batches WHERE id=%s", (batch["id"],))
        self.assertEqual(stored_batch["raw_payload"]["normalized_payload"]["record_keys"], ["legacy-match"])

    def test_missing_repository_fails_and_acl_revocation_blocks_worker_writes(self):
        with self.assertRaisesRegex(RuntimeError, "未配置"):
            TaxCertifiedImportService().preview_files(imported_by="owner", uploads=[certified_upload()])
        session = self.preview()
        job = self.jobs.create_or_get_job(import_type="tax_certified_import.confirm", created_by="owner",
                                         payload={"session_id": session.id}, max_attempts=1)
        acl = {"access_control_version": 2, "page_access_accounts": []}
        self.connection.execute("UPDATE app.app_settings SET settings_payload=%s,raw_payload=%s WHERE settings_key='app_settings'",
                                (jsonb(acl), jsonb({"normalized_payload": acl})))
        self.assertEqual(self.worker.run_once(), RuntimeWorkerResult.FAILED_PERMANENT)
        self.assertEqual(self.jobs.get_job(job.import_job_id).status, "failed")
        self.assertEqual(self.repository.records_payload()["batches"], [])

    def test_existing_invoice_reset_clears_certification_without_fk_regression(self):
        from fin_ops_platform.services.postgres_repositories.settings_data_reset import (
            PostgresSettingsDataResetRepository,
        )
        self.confirm(self.preview())
        with self.connection.transaction() as transaction:
            repository = PostgresSettingsDataResetRepository(transaction)
            with patch.object(repository, "_validate_guard"):
                result = repository.reset_invoice_data(expected_impact_fingerprint="test-boundary",
                    recovery_receipt_id="test-boundary", job_id="test-boundary", actor_id="owner", reason="test reset")
        self.assertEqual(result["invoices"], 1)
        self.assertEqual(result["tax_certified_import_records"], 1)
        self.assertEqual(result["tax_certified_import_batches"], 1)
        self.assertEqual(self.repository.records_payload()["records"], [])

    def test_reimport_after_canonical_invoice_arrives_links_without_stealing_original_batch(self):
        first = self.confirm(self.preview(digital="LATE-DIGITAL"))
        self.assertIsNone(self.current()["matched_invoice_id"])
        invoice = self.connection.fetch_one("""INSERT INTO app.invoices(invoice_type,invoice_no,digital_invoice_no,
            buyer_tax_no,amount,signed_amount,status,raw_payload)
            VALUES ('input','NUMBER-1','LATE-DIGITAL','TEST-BUYER',100,100,'active',%s) RETURNING id::text AS id""",
            (jsonb({"normalized_payload": {**invoice_kind_fields("增值税专用发票")}}),))
        second = self.confirm(self.preview(digital="LATE-DIGITAL"))
        self.assertEqual((second["persisted_record_count"], second["duplicate_count"]), (0, 1))
        self.assertEqual(self.current()["matched_invoice_id"], invoice["id"])
        self.assertEqual(self.current()["batch_id"], first["id"])
        self.service.revoke_batch(second["id"], actor_id="owner", expected_version=1)
        self.assertEqual(self.current()["status"], "active")

    def test_correction_revoke_restores_original_owner_and_monotonic_version(self):
        first = self.confirm(self.preview())
        corrected = self.confirm(self.preview(deductible="9"), corrections=[{"unique_key": "digital:TEST-DIGITAL-1", "expected_version": 1}])
        with self.assertRaises(TaxCertifiedImportConflict):
            self.service.revoke_batch(first["id"], actor_id="owner", expected_version=1)
        restored = self.service.revoke_batch(corrected["id"], actor_id="owner", expected_version=1)
        self.assertEqual(restored["restored_record_count"], 1)
        self.assertEqual(self.current()["batch_id"], first["id"])
        self.assertEqual(self.current()["version"], 3)
        self.assertEqual(self.current()["deductible_tax_amount"], "0")
        self.assertEqual(self.current()["matched_invoice_id"], self.invoice_id)
        self.assertEqual(self.current()["status"], "active")
        self.service.revoke_batch(first["id"], actor_id="owner", expected_version=1)
        self.assertEqual(self.current()["status"], "revoked")

    def test_management_lists_are_bounded_and_do_not_expose_preimages(self):
        self.confirm(self.preview(digital="MISSING-1"))
        self.confirm(self.preview(digital="MISSING-2"))
        payload = self.repository.records_payload(page_size=1)
        self.assertEqual((payload["records_total"], payload["batches_total"]), (2, 2))
        self.assertEqual((len(payload["records"]), len(payload["batches"])), (1, 1))
        second = self.repository.records_payload(records_page=2, batches_page=2, page_size=1)
        self.assertNotEqual(payload["records"][0]["unique_key"], second["records"][0]["unique_key"])
        self.assertNotIn("previous_records", payload["batches"][0])
        self.assertNotIn("source_fields", payload["records"][0])
        with self.assertRaises(ValueError):
            self.repository.records_payload(page_size=101)

    def test_canonical_amount_conflict_is_blocking_in_preview_and_worker_even_with_correction(self):
        app = TaxCertifiedImportApplicationService(certified_import_service=self.service)
        for kwargs in ({"amount": "999"}, {"tax": "999"}):
            with self.subTest(kwargs=kwargs):
                preview = app.preview_payload(imported_by="owner", uploads=[certified_upload(**kwargs)])
                self.assertEqual(preview["summary"]["blocking_count"], 1)
                self.assertEqual(preview["files"][0]["rows"][0]["row_status"], "invalid")
                with self.assertRaisesRegex(TaxCertifiedImportConflict, "不一致"):
                    self.service.confirm_session(preview["session"]["id"], actor_id="owner", corrections=[
                        {"unique_key": "digital:TEST-DIGITAL-1", "expected_version": 1}])
        self.assertEqual(self.repository.records_payload()["batches_total"], 0)
        self.assertEqual(str(self.connection.fetch_one("SELECT amount FROM app.invoices WHERE id=%s", (self.invoice_id,))["amount"]), "100.000000")

    def test_cross_identity_same_invoice_conflict_is_explicit_and_preserves_original(self):
        original = self.confirm(self.preview())
        app = TaxCertifiedImportApplicationService(certified_import_service=self.service)
        preview = app.preview_payload(imported_by="owner", uploads=[certified_upload(digital=None)])
        self.assertEqual(preview["summary"]["blocking_count"], 1)
        self.assertIn("其他认证标识", preview["files"][0]["rows"][0]["error_message"])
        with self.assertRaisesRegex(TaxCertifiedImportConflict, "其他认证标识"):
            self.service.confirm_session(preview["session"]["id"], actor_id="owner")
        self.assertEqual(self.current()["batch_id"], original["id"])

    def test_secondary_nonempty_identity_conflict_is_blocking(self):
        app = TaxCertifiedImportApplicationService(certified_import_service=self.service)
        preview = app.preview_payload(imported_by="owner", uploads=[certified_upload(invoice_code="CONFLICT-CODE")])
        self.assertEqual(preview["summary"]["blocking_count"], 1)
        self.assertIn("身份不一致", preview["files"][0]["rows"][0]["error_message"])
        with self.assertRaisesRegex(TaxCertifiedImportConflict, "身份不一致"):
            self.service.confirm_session(preview["session"]["id"], actor_id="owner")

    def test_preview_blocks_conflicting_facts_across_files_before_confirmation(self):
        app = TaxCertifiedImportApplicationService(certified_import_service=self.service)
        preview = app.preview_payload(imported_by="owner", uploads=[certified_upload(), certified_upload(selection_time="2026-10-03 13:14:15")])
        self.assertEqual(preview["summary"]["blocking_count"], 2)
        self.assertEqual(preview["summary"]["recognized_count"], 0)
        self.assertTrue(all(file["rows"][0]["blocking"] for file in preview["files"]))
        with self.assertRaises(TaxCertifiedImportConflict):
            self.service.confirm_session(preview["session"]["id"], actor_id="owner")
