from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.services.audit import AuditTrailService

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
