from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

import fitz
from PIL import Image

from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind
from fin_ops_platform.services.etc_reconciliation_source_upload_service import (
    EtcReconciliationSourceUpload,
    EtcReconciliationSourceUploadService,
)
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.untrusted_document_policy import (
    DocumentLimits,
    UntrustedDocumentError,
    inspect_untrusted_document,
)


def _image_bytes(format_name: str = "PNG") -> bytes:
    output = BytesIO()
    Image.new("RGB", (10, 10), "white").save(output, format=format_name)
    return output.getvalue()


def _pdf_bytes(page_count: int = 1) -> bytes:
    document = fitz.open()
    try:
        for _ in range(page_count):
            document.new_page(width=100, height=100)
        return document.tobytes()
    finally:
        document.close()


class UntrustedDocumentPolicyTests(unittest.TestCase):
    def test_valid_png_is_normalized_before_ocr(self) -> None:
        document = inspect_untrusted_document(
            file_name="invoice.png",
            content=_image_bytes(),
            allowed_kinds=frozenset({"png"}),
            limits=DocumentLimits(max_bytes=1024 * 1024),
        )

        self.assertEqual(document.kind, "png")
        self.assertTrue((document.ocr_content or b"").startswith(b"\x89PNG\r\n\x1a\n"))

    def test_extension_signature_mismatch_and_unknown_binary_are_rejected(self) -> None:
        for file_name, content in (
            ("renamed.jpg", _pdf_bytes()),
            ("payload.jpg", b"8BPS\x00\x01malicious"),
        ):
            with self.subTest(file_name=file_name):
                with self.assertRaises(UntrustedDocumentError):
                    inspect_untrusted_document(
                        file_name=file_name,
                        content=content,
                        allowed_kinds=frozenset({"jpeg"}),
                        limits=DocumentLimits(max_bytes=1024 * 1024),
                    )

    def test_size_page_and_archive_limits_fail_closed(self) -> None:
        with self.assertRaisesRegex(UntrustedDocumentError, "document_too_large"):
            inspect_untrusted_document(
                file_name="invoice.png",
                content=_image_bytes(),
                allowed_kinds=frozenset({"png"}),
                limits=DocumentLimits(max_bytes=4),
            )
        with self.assertRaisesRegex(UntrustedDocumentError, "document_image_too_large"):
            inspect_untrusted_document(
                file_name="invoice.png",
                content=_image_bytes(),
                allowed_kinds=frozenset({"png"}),
                limits=DocumentLimits(max_bytes=1024 * 1024, max_image_dimension=5),
            )
        with self.assertRaisesRegex(UntrustedDocumentError, "document_pdf_too_many_pages"):
            inspect_untrusted_document(
                file_name="statement.pdf",
                content=_pdf_bytes(page_count=2),
                allowed_kinds=frozenset({"pdf"}),
                limits=DocumentLimits(max_bytes=1024 * 1024, max_pdf_pages=1),
            )

        archive = BytesIO()
        with ZipFile(archive, "w") as document:
            document.writestr("[Content_Types].xml", "<Types />")
            document.writestr("word/document.xml", "<document />")
        with self.assertRaisesRegex(UntrustedDocumentError, "document_archive_too_many_entries"):
            inspect_untrusted_document(
                file_name="attachment.docx",
                content=archive.getvalue(),
                allowed_kinds=frozenset({"docx"}),
                limits=DocumentLimits(max_bytes=1024 * 1024, max_archive_entries=1),
            )

    def test_etc_rejects_untrusted_document_before_object_storage(self) -> None:
        task_service = Mock()
        task_service.get_task.return_value = SimpleNamespace(version=1, source_files=[])
        service = EtcReconciliationSourceUploadService(task_service=task_service)

        with self.assertRaises(UntrustedDocumentError):
            service.upload_sources(
                task_id="ETC-1",
                source_kind=SourceFileKind.TICKET_ROOT,
                expected_version=1,
                actor="alice",
                uploads=[EtcReconciliationSourceUpload(file_name="payload.jpg", content=b"8BPSmalicious")],
            )

        task_service.store_uploaded_source_file.assert_not_called()

    def test_oa_attachment_reports_signature_mismatch_without_parsing(self) -> None:
        service = OAAttachmentInvoiceService()
        with (
            patch.object(service, "_download_content", return_value=_pdf_bytes()),
            patch.object(service, "_run_image_ocr") as ocr,
        ):
            result = service.parse_file_result(
                {"fileName": "renamed.jpg", "filePath": "/renamed.jpg", "suffix": "jpg"}
            )

        self.assertEqual(result["parse_status"], "parse_failed")
        self.assertEqual(result["parse_error"], "document_signature_mismatch")
        ocr.assert_not_called()


if __name__ == "__main__":
    unittest.main()
