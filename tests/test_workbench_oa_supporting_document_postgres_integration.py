from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_oa_supporting_document import (
    PostgresWorkbenchOaSupportingDocumentRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.workbench_oa_supporting_document_service import (
    SupportingDocumentUpload,
    WorkbenchOaSupportingDocumentError,
    WorkbenchOaSupportingDocumentService,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class WorkbenchOaSupportingDocumentPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.directory = TemporaryDirectory()
        self.store = PostgresStateStore(data_dir=Path(self.directory.name), connection=self.connection)
        self.repository = PostgresWorkbenchOaSupportingDocumentRepository(self.connection)
        self.service = WorkbenchOaSupportingDocumentService(
            repository=self.repository, file_store=self.store, target_exists=lambda oa, item: oa == "oa-1" and item == "oa-1:item:0",
        )
        self.connection.execute("""insert into app.oa_applications
            (oa_source_id, form_id, row_id, status, application_date, scope_month)
            values ('source-1', 'payment', 'oa-1', 'active', '2026-09-01', '2026-09-01')""")
        self.connection.execute("""insert into app.workbench_pair_relations
            (case_id, relation_mode, status, row_ids, row_types)
            values ('CASE-1', 'manual_confirmed', 'active', array['oa-1'], array['oa'])""")

    def tearDown(self) -> None:
        self.connection.close()
        self.directory.cleanup()
        truncate_test_database(self.database_url)

    def save(self, *, amount="125.50", version=0, retained=(), files=(b"%PDF-first", b"%PDF-second")):
        return self.service.save(
            relation_case_id="CASE-1", oa_row_id="oa-1", expense_item_id="oa-1:item:0", actor_id="finance-user",
            retained_document_ids=list(retained), total_amount=amount, expected_version=version,
            uploads=[SupportingDocumentUpload(f"voucher-{i}.pdf", content) for i, content in enumerate(files)],
        )

    def read(self):
        return self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0")

    def test_atomic_edit_amount_only_delete_and_semantic_retry_with_one_dirty_notification(self):
        self.assertEqual(self.read(), {"documents": [], "total_amount": None, "version": 0})
        with patch.object(PostgresWorkbenchMatchingQueueRepository, "mark_relation_matching_dirty",
                          autospec=True, wraps=None) as dirty:
            first = self.save()
            self.assertEqual(dirty.call_count, 1)
            retry = self.save()
            self.assertEqual(dirty.call_count, 1)
        self.assertEqual(first, retry)
        self.assertEqual(first["total_amount"], "125.50")
        self.assertEqual(len(first["documents"]), 2)
        ids = [row["id"] for row in first["documents"]]
        updated = self.save(amount="200.00", version=1, retained=ids, files=())
        self.assertEqual(updated["version"], 2)
        self.assertEqual([row["id"] for row in updated["documents"]], ids)
        audit = self.connection.fetch_all("select payload, actor_id from audit.events where event_type = 'workbench.oa_supporting_document_bundle.saved' order by occurred_at")
        self.assertEqual(len(audit), 2)
        self.assertEqual(audit[-1]["payload"]["before"]["total_amount"], "125.50")
        self.assertEqual(audit[-1]["payload"]["after"]["total_amount"], "200.00")
        self.assertEqual(audit[-1]["actor_id"], "finance-user")
        dirty = self.connection.fetch_one("select reason, status from job.workbench_matching_dirty_scopes")
        self.assertEqual(dirty, {"reason": "oa_supporting_document_changed", "status": "dirty"})
        rows = [{"id": "oa-1", "expense_items": [{"id": "oa-1:item:0"}, {"id": "other"}]}]
        self.repository.attach_to_oa_rows(rows)
        self.assertEqual(rows[0]["expense_items"][0]["supporting_document_amount"], "200.00")
        self.assertEqual(rows[0]["expense_items"][0]["supporting_document_version"], 2)
        self.assertEqual(rows[0]["expense_items"][1]["supporting_document_version"], 0)
        self.assertIsNone(rows[0]["expense_items"][1]["supporting_document_amount"])
        cleared = self.save(amount=None, version=2, retained=(), files=())
        self.assertEqual(cleared, {"documents": [], "total_amount": None, "version": 3})
        self.assertEqual(self.save(amount=None, version=2, retained=(), files=()), cleared)
        for document_id in ids:
            with self.assertRaises(WorkbenchOaSupportingDocumentError):
                self.service.content(document_id)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.invoices")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.tax_offset_plans")["n"], 0)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.workbench_oa_supporting_documents where status = 'deleted'")["n"], 2)

    def test_audit_failure_rolls_back_new_files_amount_removal_and_dirty(self):
        first = self.save(files=(b"%PDF-first",))
        original = self.repository.list_active(oa_row_id="oa-1", expense_item_id="oa-1:item:0")[0]
        with patch.object(PostgresOperationsAuditRepository, "append_operation_event", side_effect=RuntimeError("audit failure")):
            with self.assertRaisesRegex(RuntimeError, "audit failure"):
                self.save(amount="10.00", version=1, files=(b"%PDF-replacement", b"%PDF-more"))
        self.assertEqual(self.read(), first)
        self.assertTrue(Path(original["storage_uri"]).exists())
        self.assertEqual(self.service.content(first["documents"][0]["id"])[1], b"%PDF-first")
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.file_objects where tombstoned_at is null")["n"], 1)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from audit.events where event_type = 'workbench.oa_supporting_document_bundle.saved'")["n"], 1)

    def test_conflicting_concurrent_edits_publish_exactly_once_and_reject_foreign_ids(self):
        first = self.save(files=(b"%PDF-first",))
        ids = [row["id"] for row in first["documents"]]
        def edit(amount):
            try:
                return self.save(amount=amount, version=1, retained=ids, files=())
            except WorkbenchOaSupportingDocumentError as error:
                return error
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(edit, ["20.00", "30.00"]))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        conflict = next(result for result in results if isinstance(result, WorkbenchOaSupportingDocumentError))
        self.assertEqual(conflict.error, "supporting_document_version_conflict")
        self.assertEqual(conflict.current_version, 2)
        before = self.read()
        with self.assertRaises(WorkbenchOaSupportingDocumentError) as raised:
            self.save(amount="10.00", version=2, retained=["00000000-0000-4000-8000-000000000001"], files=())
        self.assertEqual(raised.exception.error, "supporting_document_selection_invalid")
        self.assertEqual(self.read(), before)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from audit.events where event_type = 'workbench.oa_supporting_document_bundle.saved'")["n"], 2)

    def test_second_file_preparation_failure_does_not_publish_or_remove_existing_files(self):
        first = self.save(files=(b"%PDF-first",))
        store = self.store.store_workbench_oa_supporting_document
        calls = 0
        def prepare(**values):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("storage unavailable")
            return store(**values)
        with patch.object(self.store, "store_workbench_oa_supporting_document", side_effect=prepare):
            with self.assertRaisesRegex(RuntimeError, "storage unavailable"):
                self.save(version=1, amount="20.00", files=(b"%PDF-new", b"%PDF-more"))
        self.assertEqual(self.read(), first)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.file_objects where tombstoned_at is null")["n"], 1)

    def test_dirty_failure_rolls_back_fact_and_audit_and_cleanup_failure_does_not_hide_commit(self):
        first = self.save(files=(b"%PDF-first",))
        with patch.object(PostgresWorkbenchMatchingQueueRepository, "mark_relation_matching_dirty", side_effect=RuntimeError("queue failed")):
            with self.assertRaisesRegex(RuntimeError, "queue failed"):
                self.save(version=1, amount="20.00", files=(b"%PDF-new",))
        self.assertEqual(self.read(), first)
        self.assertEqual(self.connection.fetch_one("select count(*) as n from audit.events where event_type = 'workbench.oa_supporting_document_bundle.saved'")["n"], 1)
        with patch.object(self.store, "delete_workbench_oa_supporting_document", side_effect=OSError("storage failed")):
            with self.assertLogs("fin_ops_platform.services.workbench_oa_supporting_document_service", level="ERROR"):
                result = self.save(version=1, amount=None, files=())
        self.assertEqual(result, {"documents": [], "total_amount": None, "version": 2})
        with self.assertRaises(WorkbenchOaSupportingDocumentError) as error:
            self.save(version=1, amount="10.00", retained=[first["documents"][0]["id"]], files=())
        self.assertEqual(error.exception.error, "supporting_document_version_conflict")
        with self.assertRaises(WorkbenchOaSupportingDocumentError):
            self.service.content(first["documents"][0]["id"])

    def test_historical_files_keep_unknown_amount_until_explicit_save(self):
        stored = self.store.store_workbench_oa_supporting_document(
            document_id="historical", file_name="old.pdf", content=b"%PDF-old", content_type="application/pdf",
        )
        self.connection.execute("""insert into app.workbench_oa_supporting_documents
            (oa_row_id, expense_item_id, file_object_id, original_filename, content_type, content_sha256, size_bytes, created_by)
            values ('oa-1', 'oa-1:item:0', %s::uuid, 'old.pdf', 'application/pdf', %s, %s, 'old-user')""",
            (stored["file_object_id"], stored["sha256"], stored["size_bytes"]))
        historical = self.read()
        self.assertEqual(len(historical["documents"]), 1)
        self.assertIsNone(historical["total_amount"])
        self.assertEqual(historical["version"], 0)
        with self.assertRaises(WorkbenchOaSupportingDocumentError):
            self.save(amount=None, retained=[historical["documents"][0]["id"]], files=())
        updated = self.save(amount="1.23", retained=[historical["documents"][0]["id"]], files=())
        self.assertEqual(updated["total_amount"], "1.23")
        self.assertEqual(updated["version"], 1)
