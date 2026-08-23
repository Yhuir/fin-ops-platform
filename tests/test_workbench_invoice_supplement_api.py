from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.workbench_oa_supporting_document_service import (
    WorkbenchOaSupportingDocumentError,
)

from tests.app_test_support import build_local_state_application


def _multipart_document() -> tuple[bytes, dict[str, str]]:
    boundary = "----workbench-document-boundary"
    chunks: list[bytes] = []
    for name, value in (
        ("case_id", "CASE-1"),
        ("oa_row_id", "oa-1"),
        ("expense_item_id", "oa-1:item:0"),
    ):
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(),
            b"\r\n",
        ])
    chunks.extend([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="files"; filename="voucher.pdf"\r\n',
        b"Content-Type: application/pdf\r\n\r\n",
        b"%PDF-1.7\ncontent",
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def _manual_invoice_payload() -> dict[str, str]:
    return {
        "invoice_direction": "input",
        "invoice_nature": "blue",
        "seller_name": "云南供应商有限公司",
        "seller_tax_no": "915300000000000001",
        "buyer_name": "云南溯源科技有限公司",
        "buyer_tax_no": "915300007194052520",
        "invoice_number": "26117000001052654674",
        "invoice_code": "",
        "invoice_date": "2026-08-14",
        "net_amount": "100.00",
        "tax_rate": "13",
        "tax_amount": "13.00",
        "total_with_tax": "113.00",
    }


class WorkbenchInvoiceSupplementApiTests(unittest.TestCase):
    class _AuditRepository:
        def __init__(self) -> None:
            self.events: list[dict] = []

        def append_operation_event(self, event: dict) -> dict[str, str]:
            self.events.append(event)
            return {"id": f"00000000-0000-4000-8000-{len(self.events):012d}"}

    def test_manual_batch_endpoint_forwards_exact_oa_relation_target(self) -> None:
        app = build_local_state_application()
        audit_repository = self._AuditRepository()
        app._audit_service = AuditTrailService(audit_repository)
        service = SimpleNamespace(attach_manual_invoices=Mock(return_value={
            "status": "confirmed",
            "case_id": "CASE-1",
            "invoice_row_ids": ["invoice-1", "invoice-2"],
            "invoice_evidence_rows": [{
                "record_key": "file-1",
                "normalized": {
                    "digital_invoice_no": "26117000001052654674",
                    "seller_name": "云南供应商有限公司",
                },
            }],
        }))

        with patch.object(app, "_workbench_invoice_supplement_service", return_value=service):
            response = app.handle_request(
                "POST",
                "/api/workbench/oa-invoice-supplements/manual",
                json.dumps({
                    "session_id": "manual-session-1",
                    "file_ids": ["file-1", "file-2"],
                    "case_id": "CASE-1",
                    "oa_row_id": "oa-1",
                    "expense_item_id": "oa-1:item:0",
                }),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["invoice_row_ids"], ["invoice-1", "invoice-2"])
        command = service.attach_manual_invoices.call_args.args[0]
        self.assertEqual(command.file_ids, ("file-1", "file-2"))
        self.assertEqual(command.oa_row_id, "oa-1")
        self.assertEqual(command.expense_item_id, "oa-1:item:0")
        completed = next(event for event in audit_repository.events if event["event_type"] == "operation.completed")
        evidence = completed["payload"]["metadata"]["evidence"]
        self.assertEqual(evidence["records"][0]["title"], "26117000001052654674")
        self.assertEqual(evidence["target"]["title"], "关联关系 CASE-1")

    def test_workbench_preview_allows_linking_a_strict_existing_invoice(self) -> None:
        app = build_local_state_application()
        first = app._manual_invoice_entry_service.preview_batch(  # type: ignore[attr-defined]
            payloads=[_manual_invoice_payload()],
            imported_by="local",
        )
        app._file_import_service.confirm_session(  # type: ignore[attr-defined]
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )

        response = app.handle_request(
            "POST",
            "/api/workbench/oa-invoice-supplements/manual/preview",
            json.dumps({"invoices": [_manual_invoice_payload()]}),
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["import_session"]["files"][0]["duplicate_count"], 1)
        self.assertEqual(len(payload["file_ids"]), 1)

    def test_workbench_preview_hides_internal_runtime_errors(self) -> None:
        app = build_local_state_application()

        with patch.object(
            app._manual_invoice_entry_service,  # type: ignore[attr-defined]
            "preview_workbench_batch",
            side_effect=RuntimeError("postgres driver secret"),
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/oa-invoice-supplements/manual/preview",
                json.dumps({"invoices": [_manual_invoice_payload()]}),
            )

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "manual_invoice_preview_unavailable")
        self.assertEqual(payload["message"], "发票录入预览暂时不可用，请稍后重试。")
        self.assertNotIn("postgres", response.body)

    def test_manual_batch_endpoint_hides_internal_runtime_errors(self) -> None:
        app = build_local_state_application()
        service = SimpleNamespace(
            attach_manual_invoices=Mock(side_effect=RuntimeError("database password leaked"))
        )

        with patch.object(app, "_workbench_invoice_supplement_service", return_value=service):
            response = app.handle_request(
                "POST",
                "/api/workbench/oa-invoice-supplements/manual",
                json.dumps({
                    "session_id": "manual-session-1",
                    "file_ids": ["file-1"],
                    "case_id": "CASE-1",
                    "oa_row_id": "oa-1",
                    "expense_item_id": "oa-1:item:0",
                }),
            )

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "manual_invoice_supplement_unavailable")
        self.assertEqual(payload["message"], "发票录入暂时不可用，请稍后重试。")
        self.assertNotIn("password", response.body)

    def test_document_endpoints_upload_list_preview_and_delete(self) -> None:
        app = build_local_state_application()
        document = {
            "id": "document-1",
            "relation_case_id": "CASE-1",
            "oa_row_id": "oa-1",
            "expense_item_id": "oa-1:item:0",
            "file_name": "voucher.pdf",
            "content_type": "application/pdf",
            "size_bytes": 16,
            "content_url": "/api/workbench/oa-invoice-supplements/documents/document-1/content",
        }
        service = SimpleNamespace(
            upload=Mock(return_value=[document]),
            list=Mock(return_value=[document]),
            content=Mock(return_value=({"content_type": "application/pdf", "original_filename": "voucher.pdf"}, b"%PDF-1.7")),
            delete=Mock(return_value=document),
        )
        body, headers = _multipart_document()

        with patch.object(app, "_workbench_oa_supporting_document_service", return_value=service):
            upload = app.handle_request(
                "POST",
                "/api/workbench/oa-invoice-supplements/documents",
                body=body,
                headers=headers,
            )
            listed = app.handle_request(
                "GET",
                "/api/workbench/oa-invoice-supplements/documents?oa_row_id=oa-1&expense_item_id=oa-1%3Aitem%3A0",
            )
            content = app.handle_request(
                "GET",
                "/api/workbench/oa-invoice-supplements/documents/document-1/content",
            )
            deleted = app.handle_request(
                "DELETE",
                "/api/workbench/oa-invoice-supplements/documents/document-1",
            )

        self.assertEqual(upload.status_code, 201)
        self.assertEqual(json.loads(upload.body)["documents"][0]["id"], "document-1")
        service.upload.assert_called_once()
        upload_call = service.upload.call_args.kwargs
        self.assertEqual(upload_call["oa_row_id"], "oa-1")
        self.assertEqual(upload_call["expense_item_id"], "oa-1:item:0")
        self.assertEqual(upload_call["uploads"][0].content, b"%PDF-1.7\ncontent")
        self.assertEqual(listed.status_code, 200)
        service.list.assert_called_once_with(oa_row_id="oa-1", expense_item_id="oa-1:item:0")
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.body, b"%PDF-1.7")
        self.assertEqual(content.headers["Content-Type"], "application/pdf")
        self.assertEqual(deleted.status_code, 200)
        service.delete.assert_called_once()

    def test_document_gallery_and_thumbnail_are_read_only_and_bounded(self) -> None:
        app = build_local_state_application()
        document = {
            "id": "00000000-0000-4000-8000-000000000001",
            "file_name": "voucher.pdf",
            "content_type": "application/pdf",
            "content_sha256": "abc123",
        }
        service = SimpleNamespace(
            gallery=Mock(return_value={
                "documents": [document],
                "page_size": 9,
                "has_more": False,
                "next_cursor": None,
            }),
            thumbnail=Mock(return_value=(document, b"\xff\xd8\xffthumbnail")),
        )

        with patch.object(app, "_workbench_oa_supporting_document_service", return_value=service):
            gallery = app.handle_request(
                "GET",
                "/api/workbench/oa-invoice-supplements/gallery?page_size=9&cursor=cursor-1",
            )
            thumbnail = app.handle_request(
                "GET",
                "/api/workbench/oa-invoice-supplements/documents/00000000-0000-4000-8000-000000000001/thumbnail",
            )

        self.assertEqual(gallery.status_code, 200)
        self.assertFalse(json.loads(gallery.body)["has_more"])
        service.gallery.assert_called_once_with(page_size=9, cursor="cursor-1")
        self.assertEqual(thumbnail.status_code, 200)
        self.assertEqual(thumbnail.headers["Content-Type"], "image/jpeg")
        self.assertEqual(thumbnail.headers["Cache-Control"], "private, max-age=86400, immutable")
        self.assertEqual(thumbnail.headers["ETag"], '"abc123-thumbnail-v1"')

    def test_document_gallery_rejects_invalid_page_size(self) -> None:
        app = build_local_state_application()
        service = SimpleNamespace(
            gallery=Mock(side_effect=WorkbenchOaSupportingDocumentError(
                "supporting_document_page_size_invalid",
                "每次只能读取 1 至 9 个补充凭证。",
            )),
        )

        with patch.object(app, "_workbench_oa_supporting_document_service", return_value=service):
            response = app.handle_request(
                "GET",
                "/api/workbench/oa-invoice-supplements/gallery?page_size=all",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"], "supporting_document_page_size_invalid")
        service.gallery.assert_called_once_with(page_size=0, cursor="")

    def test_document_upload_persists_target_file_and_preview_evidence(self) -> None:
        app = build_local_state_application()
        audit_repository = self._AuditRepository()
        app._audit_service = AuditTrailService(audit_repository)
        document = {
            "id": "document-1",
            "relation_case_id": "CASE-1",
            "oa_row_id": "oa-1",
            "expense_item_id": "oa-1:item:0",
            "file_name": "voucher.pdf",
            "content_type": "application/pdf",
            "size_bytes": 16,
            "content_url": "/api/workbench/oa-invoice-supplements/documents/document-1/content",
        }
        body, headers = _multipart_document()

        with patch.object(
            app,
            "_workbench_oa_supporting_document_service",
            return_value=SimpleNamespace(upload=Mock(return_value=[document])),
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/oa-invoice-supplements/documents",
                body=body,
                headers=headers,
            )

        self.assertEqual(response.status_code, 201)
        completed = next(event for event in audit_repository.events if event["event_type"] == "operation.completed")
        evidence = completed["payload"]["metadata"]["evidence"]
        self.assertEqual(evidence["target"]["title"], "关联关系 CASE-1")
        self.assertEqual(evidence["artifacts"][0]["title"], "voucher.pdf")
        self.assertEqual(
            evidence["artifacts"][0]["preview_url"],
            "/api/workbench/oa-invoice-supplements/documents/document-1/content",
        )
        self.assertEqual(evidence["failure"], None)


if __name__ == "__main__":
    unittest.main()
