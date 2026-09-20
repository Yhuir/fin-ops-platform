from __future__ import annotations

import hashlib
import unittest
from io import BytesIO
from uuid import UUID

import fitz
from fin_ops_platform.services.postgres_repositories.workbench_oa_supporting_document import (
    PostgresWorkbenchOaSupportingDocumentRepository,
)
from fin_ops_platform.services.workbench_oa_supporting_document_service import (
    SupportingDocumentUpload,
    WorkbenchOaSupportingDocumentError,
    WorkbenchOaSupportingDocumentService,
)
from PIL import Image


class _FileStore:
    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def store_workbench_oa_supporting_document(self, *, document_id, file_name, content, content_type):
        del file_name, content_type
        uri = f"store://{document_id}"
        self.contents[uri] = content
        return {
            "file_object_id": document_id,
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

    def save_bundle(self, **values):
        from copy import deepcopy
        rows_before = deepcopy(self.rows)
        current = self.list_active(oa_row_id=values["oa_row_id"], expense_item_id=values["expense_item_id"])
        retained = {row["content_sha256"] for row in current if row["id"] in values["retained_document_ids"]}
        hashes = retained | {row["content_sha256"] for row in values["documents"]}
        before = self.get_bundle(oa_row_id=values["oa_row_id"], expense_item_id=values["expense_item_id"])
        if hashes == {row["content_sha256"] for row in current} and before["total_amount"] == values["total_amount"]:
            return before
        removed = [row for row in current if row["content_sha256"] not in hashes]
        try:
            for row in removed:
                row["status"] = "deleted"
            for document in values["documents"]:
                if any(row["content_sha256"] == document["content_sha256"] for row in current):
                    continue
                self.counter += 1
                if self.fail_on_create == self.counter:
                    raise RuntimeError("create failed")
                row = {**document, "id": f"document-{self.counter}", "status": "active",
                       "oa_row_id": values["oa_row_id"], "expense_item_id": values["expense_item_id"],
                       "relation_case_id": values["relation_case_id"], "created_by": values["actor_id"]}
                self.rows[row["id"]] = row
        except Exception:
            self.rows = rows_before
            raise
        self.amount = values["total_amount"]
        self.version = before["version"] + 1
        return {**self.get_bundle(oa_row_id=values["oa_row_id"], expense_item_id=values["expense_item_id"]),
                "removed_storage_uris": [row["storage_uri"] for row in removed]}

    def get_bundle(self, *, oa_row_id, expense_item_id):
        return {"documents": self.list_active(oa_row_id=oa_row_id, expense_item_id=expense_item_id),
                "total_amount": getattr(self, "amount", None), "version": getattr(self, "version", 0)}

    def list_active(self, *, oa_row_id: str, expense_item_id: str):
        return [row for row in self.rows.values() if row["status"] == "active" and row["oa_row_id"] == oa_row_id and row["expense_item_id"] == expense_item_id]

    def list_active_page(self, *, cursor_created_at, cursor_id, limit):
        rows = sorted(
            (row for row in self.rows.values() if row["status"] == "active"),
            key=lambda row: (row["created_at"], row["id"]),
            reverse=True,
        )
        if cursor_created_at is not None and cursor_id is not None:
            rows = [
                row for row in rows
                if (row["created_at"], row["id"]) < (cursor_created_at, cursor_id)
            ]
        return rows[:limit]

    def get_active(self, document_id: str):
        row = self.rows.get(document_id)
        return row if row and row["status"] == "active" else None



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
        documents = self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7\ncontent")],
        )

        self.assertEqual(documents["documents"][0]["file_name"], "凭证.pdf")
        self.assertEqual(documents["documents"][0]["content_url"], "/api/workbench/oa-invoice-supplements/documents/document-1/content")
        listed = self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0")
        self.assertEqual([item["id"] for item in listed["documents"]], ["document-1"])
        _document, content = self.service.content("document-1")
        self.assertEqual(content, b"%PDF-1.7\ncontent")

        deleted = self.service.save(relation_case_id="CASE-1", oa_row_id="oa-1", expense_item_id="oa-1:item:0",
                                    actor_id="finance-user", retained_document_ids=[], total_amount=None,
                                    expected_version=1, uploads=[])

        self.assertEqual(self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0")["documents"], [])
        self.assertEqual(len(self.store.deleted), 1)
        self.assertEqual(deleted["total_amount"], None)
        self.assertEqual(deleted["version"], 2)

    def test_rejects_extension_signature_mismatch_before_storage(self) -> None:
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "文件内容与扩展名不一致"):
            self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("fake.pdf", b"not a pdf")],
            )

        self.assertEqual(self.store.contents, {})
    def test_rejects_unsupported_type_and_empty_target(self) -> None:
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "仅支持 JPG"):
            self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("transfer.docx", b"docx")],
            )
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "不能为空"):
            self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
                relation_case_id="CASE-1",
                oa_row_id="",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7")],
            )

    def test_rejects_stale_or_mismatched_oa_expense_item_before_storage(self) -> None:
        self.target_exists = False

        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "不存在或已变化"):
            self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-other:item:0",
                actor_id="finance-user",
                uploads=[SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7")],
            )

        self.assertEqual(self.store.contents, {})

    def test_accepts_jpeg_and_png_and_preserves_content_type(self) -> None:
        documents = self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
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
            [document["content_type"] for document in documents["documents"]],
            ["image/jpeg", "image/png"],
        )

    def test_retrying_same_file_is_idempotent_for_one_oa_expense_item(self) -> None:
        upload = SupportingDocumentUpload("凭证.pdf", b"%PDF-1.7\ncontent")

        first = self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[upload],
        )
        second = self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
            relation_case_id="CASE-1",
            oa_row_id="oa-1",
            expense_item_id="oa-1:item:0",
            actor_id="finance-user",
            uploads=[upload],
        )

        self.assertEqual(first["documents"][0]["id"], second["documents"][0]["id"])
        self.assertEqual(len(self.repository.rows), 1)
        self.assertEqual(len(self.store.contents), 1)

    def test_amount_validation_rejects_missing_negative_precision_and_non_numbers(self) -> None:
        for amount in (None, "", "-1", "1.001", "NaN", "Infinity", "1e2", " 2", "1000000000000000000.00"):
            with self.subTest(amount=amount), self.assertRaises(WorkbenchOaSupportingDocumentError):
                self.service.save(relation_case_id="CASE-1", oa_row_id="oa-1", expense_item_id="oa-1:item:0",
                                  actor_id="user", retained_document_ids=[], total_amount=amount,
                                  expected_version=0, uploads=[SupportingDocumentUpload("a.pdf", b"%PDF-a")])
        self.assertEqual(self.store.contents, {})

    def test_empty_group_only_accepts_null_amount_and_zero_is_valid_with_file(self) -> None:
        with self.assertRaises(WorkbenchOaSupportingDocumentError):
            self.service.save(relation_case_id="", oa_row_id="oa-1", expense_item_id="oa-1:item:0",
                              actor_id="user", retained_document_ids=[], total_amount="0",
                              expected_version=0, uploads=[])
        result = self.service.save(relation_case_id="", oa_row_id="oa-1", expense_item_id="oa-1:item:0",
                                   actor_id="user", retained_document_ids=[], total_amount="0",
                                   expected_version=0, uploads=[SupportingDocumentUpload("a.pdf", b"%PDF-a")])
        self.assertEqual(result["total_amount"], "0.00")

    def test_gallery_uses_stable_cursor_pages_and_only_returns_metadata(self) -> None:
        for index in range(11):
            document_id = f"00000000-0000-4000-8000-{index + 1:012d}"
            self.repository.rows[document_id] = {
                "id": document_id,
                "relation_case_id": f"CASE-{index}",
                "oa_row_id": f"oa-{index}",
                "expense_item_id": f"oa-{index}:item:0",
                "original_filename": f"voucher-{index}.pdf",
                "content_type": "application/pdf",
                "content_sha256": f"sha-{index}",
                "size_bytes": 10 + index,
                "created_by": "finance-user",
                "created_at": f"2026-08-{index + 1:02d}T08:00:00+08:00",
                "status": "active",
            }

        first = self.service.gallery()
        second = self.service.gallery(cursor=first["next_cursor"])

        self.assertEqual(len(first["documents"]), 9)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(second["documents"]), 2)
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_cursor"])
        self.assertEqual(first["documents"][0]["file_name"], "voucher-10.pdf")
        self.assertEqual(second["documents"][-1]["file_name"], "voucher-0.pdf")
        self.assertNotIn("content", first["documents"][0])
        self.assertEqual(
            first["documents"][0]["thumbnail_url"],
            "/api/workbench/oa-invoice-supplements/documents/00000000-0000-4000-8000-000000000011/thumbnail",
        )

    def test_gallery_rejects_invalid_cursor_and_unbounded_page_size(self) -> None:
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "分页位置无效"):
            self.service.gallery(cursor="not-a-cursor")
        with self.assertRaisesRegex(WorkbenchOaSupportingDocumentError, "1 至 9"):
            self.service.gallery(page_size=10)

    def test_thumbnail_renders_image_and_pdf_without_changing_original_content(self) -> None:
        image_buffer = BytesIO()
        Image.new("RGBA", (800, 400), (255, 0, 0, 128)).save(image_buffer, format="PNG")
        pdf = fitz.open()
        pdf.new_page(width=595, height=842)
        pdf_bytes = pdf.tobytes()
        pdf.close()

        for document_id, file_name, content, content_type in (
            ("00000000-0000-4000-8000-000000000001", "voucher.png", image_buffer.getvalue(), "image/png"),
            ("00000000-0000-4000-8000-000000000002", "voucher.pdf", pdf_bytes, "application/pdf"),
        ):
            storage_uri = f"store://{document_id}"
            self.store.contents[storage_uri] = content
            self.repository.rows[document_id] = {
                "id": document_id,
                "relation_case_id": "CASE-1",
                "oa_row_id": "oa-1",
                "expense_item_id": "oa-1:item:0",
                "original_filename": file_name,
                "content_type": content_type,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
                "created_by": "finance-user",
                "created_at": "2026-08-23T10:00:00+08:00",
                "storage_uri": storage_uri,
                "status": "active",
            }

            _document, thumbnail = self.service.thumbnail(document_id)

            with Image.open(BytesIO(thumbnail)) as rendered:
                self.assertEqual(rendered.format, "JPEG")
                self.assertLessEqual(max(rendered.size), 360)
            self.assertEqual(self.store.contents[storage_uri], content)

    def test_batch_failure_removes_documents_created_earlier_in_the_request(self) -> None:
        self.repository.fail_on_create = 2

        with self.assertRaisesRegex(RuntimeError, "create failed"):
            self.service.save(
            retained_document_ids=[], total_amount="100.00", expected_version=0,
                relation_case_id="CASE-1",
                oa_row_id="oa-1",
                expense_item_id="oa-1:item:0",
                actor_id="finance-user",
                uploads=[
                    SupportingDocumentUpload("first.pdf", b"%PDF-1.7\nfirst"),
                    SupportingDocumentUpload("second.pdf", b"%PDF-1.7\nsecond"),
                ],
            )

        self.assertEqual(self.service.list(oa_row_id="oa-1", expense_item_id="oa-1:item:0")["documents"], [])
        self.assertEqual(self.store.contents, {})


class PostgresWorkbenchOaSupportingDocumentRepositoryTests(unittest.TestCase):
    def test_gallery_page_query_is_keyset_bounded_and_active_only(self) -> None:
        class _Connection:
            def __init__(self) -> None:
                self.sql = ""
                self.params = ()

            def fetch_all(self, sql, params):
                self.sql = " ".join(sql.split()).lower()
                self.params = params
                return []

        connection = _Connection()
        cursor_id = "00000000-0000-4000-8000-000000000009"

        rows = PostgresWorkbenchOaSupportingDocumentRepository(connection).list_active_page(
            cursor_created_at="2026-08-23T10:00:00+08:00",
            cursor_id=cursor_id,
            limit=10,
        )

        self.assertEqual(rows, [])
        self.assertIn("document.status = 'active'", connection.sql)
        self.assertIn("file.tombstoned_at is null", connection.sql)
        self.assertIn("(document.created_at, document.id) < (%s::timestamptz, %s::uuid)", connection.sql)
        self.assertIn("order by document.created_at desc, document.id desc limit %s", connection.sql)
        self.assertEqual(connection.params, ("2026-08-23T10:00:00+08:00", cursor_id, 10))
        UUID(cursor_id)


if __name__ == "__main__":
    unittest.main()
