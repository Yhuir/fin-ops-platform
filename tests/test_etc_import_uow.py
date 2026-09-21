from __future__ import annotations

import unittest
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.etc_import_preview_service import EtcImportPreviewService
from fin_ops_platform.services.etc_import_session_store import build_etc_import_session_store
from fin_ops_platform.services.etc_import_uow import EtcImportUow
from fin_ops_platform.services.etc_service import EtcService, UploadedEtcZipFile
from fin_ops_platform.services.import_job_queue import ImportJobCompletion, ImportJobRepository
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.object_storage import InMemoryObjectStorageRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database

from tests.test_etc_reconciliation_service import etc_zip, ready_task_with_requirement


class EtcImportUowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url))
        self.store = PostgresStateStore(data_dir=Path(self.directory.name), connection=self.connection,
                                       object_storage_repository=InMemoryObjectStorageRepository())
        self.task = ready_task_with_requirement(amount="25.00", transaction_at="2026-03-03 12:00:00", invoice_count=1)
        PostgresOpsTaxEtcRepository(self.connection).save_etc_reconciliation_task(self.task, expected_version=None)
        self.sessions = build_etc_import_session_store(self.store)
        self.service = EtcService(data_dir=Path(self.directory.name), state_store=self.store)
        self.preview = EtcImportPreviewService(etc_service=self.service,
            task_service=SimpleNamespace(get_task=lambda _identity: self.task), session_store=self.sessions)
        self.uow = EtcImportUow(connection=self.connection, archive_store=self.store, data_dir=Path(self.directory.name))

    def prepared(self):
        payload = self.preview.preview(task_id=self.task.task_id,
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], imported_by="YNSYLP005")
        repository = ImportJobRepository(self.connection)
        job = repository.create_or_get_job(import_type="etc_invoice_import.confirm", created_by="YNSYLP005",
            import_session_id=payload["sessionId"], idempotency_key=payload["sessionId"])
        claimed = repository.claim_next("test-worker", import_job_id=job.import_job_id)
        return self.preview.validate(session_id=payload["sessionId"], task_id=self.task.task_id,
                                     imported_by="YNSYLP005", load_manifest=True), ImportJobCompletion(claimed)

    def test_confirm_reads_no_archive_and_commit_reuses_prepared_parse(self) -> None:
        validated, completion = self.prepared()
        with patch.object(self.store, "read_etc_import_archive", side_effect=AssertionError("archive read at confirm")):
            self.preview.validate(session_id=validated.session.session_id, task_id=self.task.task_id, imported_by="YNSYLP005")
        with patch("fin_ops_platform.services.etc_service.build_etc_archive_manifest", side_effect=AssertionError("reparse")):
            result = self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["batch_members"], 1)
        self.assertEqual(ImportJobRepository(self.connection).get_job(completion.job.import_job_id).status, "succeeded")
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select status from app.etc_reconciliation_tasks")["status"], "imported")
        self.assertEqual(self.sessions.get(validated.session.session_id, load_uploads=False).status, "succeeded")

    def test_late_failure_rolls_back_all_facts_task_session_and_completion(self) -> None:
        validated, completion = self.prepared()
        with patch.object(ImportJobCompletion, "succeed", side_effect=RuntimeError("late completion failure")):
            with self.assertRaisesRegex(RuntimeError, "late completion"):
                self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        for table in ("etc_invoices", "etc_business_batches", "etc_import_batches", "invoices"):
            self.assertEqual(self.connection.fetch_one(f"select count(*) n from app.{table}")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select status from app.etc_reconciliation_tasks")["status"], "ready_for_import")
        self.assertEqual(self.sessions.get(validated.session.session_id, load_uploads=False).status, "preview_ready")
        self.assertEqual(ImportJobRepository(self.connection).get_job(completion.job.import_job_id).status, "processing")
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.file_objects where tombstoned_at is null and migration_status='verified'")["n"], 2)
        self.assertEqual(self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)["created"], 1)

    def test_duplicate_existing_invoice_still_joins_current_batch_without_reupload(self) -> None:
        self.service.import_zips([UploadedEtcZipFile("old.zip", etc_zip(["26537912000000000001"]))])
        original = next(iter(self.store.load_etc_state()["invoices"].values()))
        validated, completion = self.prepared()
        with patch.object(self.store, "store_etc_invoice_file", side_effect=AssertionError("duplicate upload")):
            result = self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["batch_members"], 1)
        current = next(iter(self.store.load_etc_state()["invoices"].values()))
        self.assertEqual(current["import_batch_id"], original["import_batch_id"])
        self.assertEqual(current["business_batch_id"], result["business_batch_id"])

    def test_task_changed_after_attachment_prepare_prevents_every_fact_write(self) -> None:
        validated, completion = self.prepared()
        self.connection.execute("update app.etc_reconciliation_tasks set raw_payload=jsonb_set(raw_payload, "
                                "'{normalized_payload,version}', '4'::jsonb),version=4")
        with self.assertRaisesRegex(ValueError, "stale_reconciliation"):
            self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.etc_invoices")["n"], 0)

    def test_registration_and_preparation_publish_one_durable_intent(self) -> None:
        repository = ImportJobRepository(self.connection)
        jobs = []
        def register(transaction, session):
            jobs.append(repository.create_or_get_job(import_type="etc_invoice_import.confirm", stage="prepare",
                created_by="YNSYLP005", import_session_id=session.session_id, transaction=transaction))
        session = self.preview.register(task_id=self.task.task_id, imported_by="YNSYLP005",
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], register_job=register)
        self.assertEqual(session.status, "preparing")
        claimed = repository.claim_next("test-worker", import_job_id=jobs[0].import_job_id)
        with patch.object(ImportJobCompletion, "preview", side_effect=RuntimeError("preview result failure")):
            with self.assertRaisesRegex(RuntimeError, "preview result"):
                self.preview.prepare(session_id=session.session_id, imported_by="YNSYLP005", completion=ImportJobCompletion(claimed))
        self.assertEqual(self.sessions.get(session.session_id, load_uploads=False).status, "preparing")
        result = self.preview.prepare(session_id=session.session_id, imported_by="YNSYLP005", completion=ImportJobCompletion(claimed))
        completed = repository.get_job(claimed.import_job_id)
        self.assertEqual(completed.status, "awaiting_confirmation")
        self.assertEqual(completed.result_payload["preview"], result)
        self.assertEqual(self.sessions.get(session.session_id, load_uploads=False).status, "preview_ready")

    def test_register_job_failure_leaves_no_session_or_job(self) -> None:
        def rejected(_transaction, _session):
            raise RuntimeError("registration failed")
        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            self.preview.register(task_id=self.task.task_id, imported_by="YNSYLP005",
                uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], register_job=rejected)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.etc_import_sessions")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) n from job.import_jobs")["n"], 0)

    def test_existing_canonical_link_commits_metadata_without_changing_financial_fields(self) -> None:
        imports = ImportNormalizationService()
        batch = imports.preview_import(batch_type=BatchType.INPUT_INVOICE, source_name="official.xlsx",
            imported_by="YNSYLP005", rows=[{"digital_invoice_no": "26537912000000000001", "invoice_date": "2026-03-03",
                "amount": "24.25", "tax_amount": "0.75", "total_with_tax": "25.00", "counterparty_name": "ETC seller"}])
        imports.confirm_import(batch.id)
        self.store.save_import_delta({"imports": imports.snapshot()})
        before = self.connection.fetch_one("select amount,tax_amount,total_with_tax,invoice_date from app.invoices")
        validated, completion = self.prepared()
        with patch.object(ImportJobCompletion, "succeed", side_effect=RuntimeError("late failure")):
            with self.assertRaisesRegex(RuntimeError, "late failure"):
                self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertIsNone(self.connection.fetch_one("select etc_invoice_id from app.invoices")["etc_invoice_id"])
        self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        after = self.connection.fetch_one("select amount,tax_amount,total_with_tax,invoice_date,etc_invoice_id from app.invoices")
        self.assertEqual({key: after[key] for key in before}, before)
        self.assertTrue(after["etc_invoice_id"])
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.invoices")["n"], 1)

    def test_attachment_write_failure_publishes_no_formal_fact(self) -> None:
        validated, completion = self.prepared()
        with patch.object(self.store, "store_etc_invoice_file", side_effect=RuntimeError("object store unavailable")):
            with self.assertRaisesRegex(RuntimeError, "object store unavailable"):
                self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.etc_invoices")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select status from app.etc_reconciliation_tasks")["status"], "ready_for_import")

    def test_full_120_ticket_package_does_not_enumerate_impossible_subset_sizes(self) -> None:
        from itertools import combinations
        self.task.expected_etc_invoice_requirements[0].invoice_count = 120
        self.task.expected_etc_invoice_requirements[0].amount = Decimal("3000")
        counts = []
        def record(iterable, count):
            counts.append(count)
            return combinations(iterable, count)
        with patch("fin_ops_platform.services.etc_reconciliation_zip_filter.combinations", side_effect=record):
            result = self.preview.preview(task_id=self.task.task_id, imported_by="YNSYLP005",
                uploads=[UploadedEtcZipFile("120.zip", etc_zip([f"26537912{index:012d}" for index in range(120)]))])
        self.assertEqual(result["summary"]["imported"], 120)
        self.assertEqual(counts, [60, 60])

    def test_registration_commit_ack_loss_preserves_referenced_original(self) -> None:
        repository = self.store.etc_import_session_repository
        original_save = repository.save_preview
        def commit_then_lose_ack(*args, **kwargs):
            original_save(*args, **kwargs)
            raise RuntimeError("commit acknowledgement lost")
        with patch.object(repository, "save_preview", side_effect=commit_then_lose_ack):
            with self.assertRaisesRegex(RuntimeError, "acknowledgement"):
                self.preview.register(task_id=self.task.task_id, imported_by="YNSYLP005",
                    uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))])
        session_id = self.connection.fetch_one("select session_id from app.etc_import_sessions")["session_id"]
        self.assertTrue(self.sessions.get(session_id).uploads[0].content)

    def test_commit_ack_loss_preserves_referenced_attachments(self) -> None:
        validated, completion = self.prepared()
        original_transaction = self.connection.transaction
        @contextmanager
        def commit_then_lose_ack():
            with original_transaction() as transaction:
                yield transaction
            raise RuntimeError("commit acknowledgement lost")
        with patch.object(self.connection, "transaction", side_effect=commit_then_lose_ack):
            with self.assertRaisesRegex(RuntimeError, "acknowledgement"):
                self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(ImportJobRepository(self.connection).get_job(completion.job.import_job_id).status, "succeeded")
        invoice = next(iter(self.store.load_etc_state()["invoices"].values()))
        self.assertTrue(self.store.read_etc_invoice_file(invoice["xml_file_path"]))
        self.assertTrue(self.store.read_etc_invoice_file(invoice["pdf_file_path"]))

    def test_second_attachment_failure_cleans_first_prepared_attachment(self) -> None:
        validated, completion = self.prepared()
        original_write = self.store.store_etc_invoice_file
        count = 0
        def fail_second(**kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("second attachment failed")
            return original_write(**kwargs)
        with patch.object(self.store, "store_etc_invoice_file", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second attachment"):
                self.uow.commit(validated=validated, owner_user_id="YNSYLP005", completion=completion)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.file_objects where tombstoned_at is null and migration_status='verified'")["n"], 2)
        self.assertEqual(self.connection.fetch_one("select count(*) n from app.etc_invoices")["n"], 0)

    def test_explicit_reprepare_uses_current_task_version_before_new_confirmation(self) -> None:
        validated, completion = self.prepared()
        repository = ImportJobRepository(self.connection)
        self.task.version += 1
        PostgresOpsTaxEtcRepository(self.connection).save_etc_reconciliation_task(self.task, expected_version=validated.session.task_version)
        repository.require_review(completion.job, error="stale_reconciliation_task_preview")
        review = repository.get_job(completion.job.import_job_id)
        repository.reprepare_job(review.import_job_id, expected_version=review.version)
        claimed = repository.claim_next("reprepare-worker", import_job_id=review.import_job_id)
        self.preview.prepare(session_id=validated.session.session_id, imported_by="YNSYLP005", completion=ImportJobCompletion(claimed))
        prepared = repository.get_job(review.import_job_id)
        self.assertEqual(prepared.status, "awaiting_confirmation")
        fresh = self.preview.validate(session_id=validated.session.session_id, task_id=self.task.task_id,
                                      imported_by="YNSYLP005", load_manifest=True)
        self.assertEqual(fresh.session.task_version, self.task.version)
        repository.confirm_job(prepared.import_job_id, expected_version=prepared.version, payload={"session_id": fresh.session.session_id})
        claimed = repository.claim_next("commit-worker", import_job_id=prepared.import_job_id)
        self.assertEqual(self.uow.commit(validated=fresh, owner_user_id="YNSYLP005", completion=ImportJobCompletion(claimed))["created"], 1)

    def test_discard_preparing_session_cancels_job_in_same_transaction(self) -> None:
        repository = ImportJobRepository(self.connection)
        jobs = []
        def register(transaction, session):
            jobs.append(repository.create_or_get_job(import_type="etc_invoice_import.confirm", stage="prepare",
                created_by="YNSYLP005", import_session_id=session.session_id, transaction=transaction))
        session = self.preview.register(task_id=self.task.task_id, imported_by="YNSYLP005",
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["26537912000000000001"]))], register_job=register)
        def cancel_then_fail(transaction):
            repository.cancel_job(jobs[0].import_job_id, created_by="YNSYLP005", transaction=transaction)
            raise RuntimeError("session update failure")
        with self.assertRaisesRegex(RuntimeError, "session update failure"):
            self.preview.discard(session_id=session.session_id, imported_by="YNSYLP005", on_discard=cancel_then_fail)
        self.assertEqual(repository.get_job(jobs[0].import_job_id).status, "pending")
        self.assertEqual(self.sessions.get(session.session_id, load_uploads=False).status, "preparing")
        self.preview.discard(session_id=session.session_id, imported_by="YNSYLP005",
            on_discard=lambda tx: repository.cancel_job(jobs[0].import_job_id, created_by="YNSYLP005", transaction=tx))
        self.preview.discard(session_id=session.session_id, imported_by="YNSYLP005")
        self.assertEqual(repository.get_job(jobs[0].import_job_id).status, "canceled")
        self.assertEqual(self.sessions.get(session.session_id, load_uploads=False).status, "reverted")

    def test_failed_new_object_verification_removes_temporary_and_final_bytes(self) -> None:
        objects = self.store._object_storage_repository
        original_get = objects.get_object
        def corrupt_final(key):
            return b"corrupt" if key.startswith("objects/") else original_get(key)
        with patch.object(objects, "get_object", side_effect=corrupt_final):
            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                self.store.store_etc_invoice_file(invoice_number="ticket", file_name="invoice.pdf", content=b"original")
        self.assertEqual(objects.objects, {})
