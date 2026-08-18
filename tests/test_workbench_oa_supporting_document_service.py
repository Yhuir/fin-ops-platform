from __future__ import annotations

import hashlib
import unittest

from fin_ops_platform.services.postgres_repositories.workbench_oa_supporting_document import (
    PostgresWorkbenchOaSupportingDocumentRepository,
)
from fin_ops_platform.services.workbench_oa_supporting_document_service import (
    SupportingDocumentUpload,
    WorkbenchOaSupportingDocumentError,
    WorkbenchOaSupportingDocumentService,
)


class _FileStore:
    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def store_workbench_oa_supporting_document(self, *, document_id, file_name, content, content_type):
        del file_name, content_type
        uri = f"store://{document_id}"
        self.contents[uri] = content
        return {
            "file_object_id": "00000000-0000-0000-0000-000000000001",
            "storage_uri": uri,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    def read_workbench_oa_supporting_document(self, storage_uri: str) -> bytes:
        return self.contents[storage_uri]

    def delete_workbench_oa_supporting_document(self, storage_uri: str) -> None:
        self.deleted.append(storage_uri)
        self.contents.pop(storage_uri, None)


class _Repository:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.counter = 0
        self.fail_on_create = 0

    def create(self, **values):
        self.counter += 1
        if self.fail_on_create == self.counter:
            raise RuntimeError("create failed")
        row = {
            "id": f"document-{self.counter}",
            "storage_uri": f"store://{values['file_object_id']}",
            "status": "active",
            **values,
        }
        # The production repository obtains storage_uri through app.file_objects on reads.
        row["storage_uri"] = next(reversed(self._file_store.contents)) if hasattr(self, "_file_store") else ""
        self.rows[row["id"]] = row
        return row

    def find_active_by_content(self, *, oa_row_id: str, expense_item_id: str, content_sha256: str):
        return next((
            row for row in self.rows.values()
            if row["status"] == "active"
            and row["oa_row_id"] == oa_row_id
            and row["expense_item_id"] == expense_item_id
            and row["content_sha256"] == content_sha256
        ), None)

    def list_active(self, *, oa_row_id: str, expense_item_id: str):
        return [row for row in self.rows.values() if row["status"] == "active" and row["oa_row_id"] == oa_row_id and row["expense_item_id"] == expense_item_id]

    def get_active(self, document_id: str):
        row = self.rows.get(document_id)
        return row if row and row["status"] == "active" else None

    def soft_delete(self, document_id: str, *, deleted_by: str):
        row = self.get_active(document_id)
        if row is None:
            return None
        row["status"] = "deleted"
        row["deleted_by"] = deleted_by
        return row


class WorkbenchOaSupportingDocumentServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _FileStore()
        self.repository = _Repository()
        self.repository._file_store = self.store
        self.target_exists = True
        self.service = WorkbenchOaSupportingDocumentService(
            repository=self.repository,
            file_store=self.store,
            target_exists=lambda _oa_row_id, _expense_item_id: self.target_exists,
        )

    def test_upload_list_preview_and_delete_stay_outside_invoice_pool(self) -> None:
        documents = self.service.upload(
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7\ncontent")],
        )

        self.assertEqual(documents[0]["file_name"], "凭证.pdf")
        self.assertEqual(documents[0]["content_url"], "/api/workbench/oa-invoice-supplements/documents/document-1/content")
        listed = self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0")
        self.assertEqual([item["id"] for item in listed], ["document-1"])
        _document, content = self.service.content("document-1")
        self.assertEqual(content, b"%PDF-1.7\ncontent")

        deleted = self.service.delete("document-1", actor_id="finance-user")

        self.assertEqual(self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0"), [])
        self.assertEqual(len(self.store.deleted), 1)
        self.assertEqual(deleted["file_name"], "凭证.pdf")
        self.assertEqual(deleted["relation_case_id"], "CASE-1")

    def test_rejects_extension_signature_mismatch_before_storage(self) -> None:
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "文件内容与扩展名不一致"):
            self.service.upload(
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("fake.pdf", b"not a pdf")],
            )

        self.assertEqual(self.store.contents, {})
    def test_rejects_unsupported_type_and_empty_target(self) -> None:
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "仅支持 JPG"):
            self.service.upload(
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("transfer.docx", b"docx")],
            )
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "不能为空"):
            self.service.upload(
                relation_case_id="CASE-1",
                oa_row_id="",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7")],
            )

    def test_rejects_stale_or_mismatched_oa_expense_item_before_storage(self) -> None:
        self.target_exists = False

        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "不存在或已变化"):
            self.service.upload(
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-other:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7")],
            )

        self.assertEqual(self.store.contents, {})

    def test_accepts_jpeg_and_png_and_preserves_content_type(self) -> None:
        documents = self.service.upload(
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[
                SupportingDocumentUpload("photo.JPG", b"\xff\xd8\xffimage"),
                SupportingDocumentUpload("screenshot.png", b"\x89PNG\r\n\x1a\nimage"),
            ],
        )

        self.assertEqual(
            [document["content_type"] for document in documents],
            ["image/jpeg", "image/png"],
        )

    def test_retrying_same_file_is_idempotent_for_one_oa_expense_item(self) -> None:
        upload = SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7\ncontent")

        first = self.service.upload(
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[upload],
        )
        second = self.service.upload(
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[upload],
        )

        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertEqual(len(self.repository.rows), 1)
        self.assertEqual(len(self.store.contents), 1)

    def test_batch_failure_removes_documents_created_earlier_in_the_request(self) -> None:
        self.repository.fail_on_create = 2

        with self.assertRaisesRegex(RuntimeError, "create failed"):
            self.service.upload(
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[
                    SupportingDocumentUpload("first.pdf", b"%PDF-1.7\nfirst"),
                    SupportingDocumentUpload("second.pdf", b"%PDF-1.7\nsecond"),
                ],
            )

        self.assertEqual(self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0"), [])
        self.assertEqual(self.store.contents, {})


class PostgresWorkbenchOaSupportingDocumentRepositoryTests(unittest.TestCase):
    def test_create_uses_partial_unique_conflict_as_idempotent_noop(self) -> None:
        class _Connection:
            def __init__(self) -> None:
                self.sql = ""
                self.params = ()

            def fetch_one(self, sql, params):
                self.sql = " ".join(sql.split()).lower()
                self.params = params
                return None

        connection = _Connection()
        created = PostgresWorkbenchOaSupportingDocumentRepository(connection).create(
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            file_object_id="00000000-0000-0000-0000-000000000001",
            original_filename="凭证.png",
            content_type="image/png",
            content_sha256="sha",
            size_bytes=8,
            created_by="finance-user",
        )

        self.assertIsNone(created)
        self.assertIn(
            "on conflict (oa_row_id, expense_item_id, content_sha256) where status = 'active' do nothing",
            connection.sql,
        )


if __name__ == "__main__":
    unittest.main()
