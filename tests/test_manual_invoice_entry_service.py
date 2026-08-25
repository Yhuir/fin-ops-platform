from __future__ import annotations

from io import BytesIO
import unittest

import fitz
from PIL import Image

from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.manual_invoice_entry_service import (
    ManualInvoiceEntryError,
    ManualInvoiceEntryService,
)
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.pending_invoice_service import PendingInvoiceApplicationService


class FakeDocumentRecognizer:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def recognize_uploaded_invoice(self, *, file_name: str, content: bytes) -> dict[str, str]:
        del file_name, content
        return dict(self.values)


def payload(**overrides: str) -> dict[str, str]:
    values = {
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
    values.update(overrides)
    return values


def _build_pdf_with_blank_pages(page_count: int) -> bytes:
    document = fitz.open()
    try:
        for _ in range(page_count):
            document.new_page(width=400, height=240)
        return document.tobytes()
    finally:
        document.close()


def _digital_invoice_text(invoice_no: str) -> str:
    return f"""
电子发票（普通发票）
下载次数：1
国家税务总局统一发票监制章 {invoice_no}
开票日期：2026年08月14日
名称：云南溯源科技有限公司
统一社会信用代码/纳税人识别号：915300007194052520
名称：云南供应商有限公司
统一社会信用代码/纳税人识别号：915300000000000001
合计¥100.00¥13.00
价税合计（小写）¥113.00
13%
"""


class ManualInvoiceEntryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.file_import_service = FileImportService(self.import_service)
        self.service = ManualInvoiceEntryService(
            file_import_service=self.file_import_service,
            document_recognizer=FakeDocumentRecognizer(),
        )

    def test_preview_batch_uses_current_invoice_import_session_and_canonical_shape(self) -> None:
        preview = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")

        self.assertEqual(preview.session.status, "preview_ready")
        self.assertEqual(preview.session.files[0].template_code, "manual_invoice_entry")
        self.assertEqual(preview.session.files[0].batch_type, BatchType.INPUT_INVOICE)
        normalized = preview.session.files[0].normalized_rows[0]
        self.assertEqual(normalized["digital_invoice_no"], "26117000001052654674")
        self.assertEqual(normalized["amount"], "100.00")
        self.assertEqual(normalized["tax_amount"], "13.00")
        self.assertEqual(normalized["total_with_tax"], "113.00")
        self.assertEqual(normalized["tax_rate"], "13%")
        self.assertEqual(normalized["is_positive_invoice"], "是")

    def test_red_invoice_accepts_positive_form_values_and_persists_negative_money(self) -> None:
        preview = self.service.preview_batch(
            payloads=[payload(
                invoice_direction="output",
                invoice_nature="red",
                invoice_number="12345678",
                invoice_code="123456789012",
            )],
            imported_by="finance-user",
        )
        file_item = preview.session.files[0]
        normalized = file_item.normalized_rows[0]

        self.assertEqual(normalized["invoice_no"], "12345678")
        self.assertEqual(normalized["amount"], "-100.00")
        self.assertEqual(normalized["tax_amount"], "-13.00")
        self.assertEqual(normalized["total_with_tax"], "-113.00")
        self.assertEqual(normalized["is_positive_invoice"], "否")

        self.file_import_service.confirm_session(
            session_id=preview.session.id,
            selected_file_ids=preview.file_ids,
        )
        invoice = self.import_service.list_invoices()[0]
        self.assertEqual(str(invoice.amount), "-100.00")
        self.assertEqual(str(invoice.total_with_tax), "-113.00")
        self.assertEqual(invoice.is_positive_invoice, "否")

    def test_traditional_invoice_requires_code_but_twenty_digit_invoice_does_not(self) -> None:
        with self.assertRaisesRegex(ManualInvoiceEntryError, "传统发票必须填写发票代码"):
            self.service.preview_batch(
                payloads=[payload(invoice_number="12345678", invoice_code="")],
                imported_by="finance-user",
            )

        preview = self.service.preview_batch(payloads=[payload(invoice_code="")], imported_by="finance-user")
        self.assertEqual(preview.values[0]["invoice_code"], "")

    def test_amount_balance_and_tax_rate_are_validated_before_import_preview(self) -> None:
        with self.assertRaisesRegex(ManualInvoiceEntryError, "价税合计必须等于"):
            self.service.preview_batch(
                payloads=[payload(total_with_tax="112.99")],
                imported_by="finance-user",
            )
        with self.assertRaisesRegex(ManualInvoiceEntryError, "税率必须是 0 到 100"):
            self.service.preview_batch(
                payloads=[payload(tax_rate="101")],
                imported_by="finance-user",
            )

    def test_duplicate_invoice_is_blocked_and_not_left_as_active_manual_session(self) -> None:
        first = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")
        self.file_import_service.confirm_session(
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )

        with self.assertRaisesRegex(ManualInvoiceEntryError, "已存在于统一发票池"):
            self.service.preview_batch(payloads=[payload()], imported_by="finance-user")

        self.assertEqual(
            self.file_import_service.list_active_sessions(imported_by="finance-user", mode="manual_invoice"),
            [],
        )

    def test_workbench_preview_accepts_only_a_strict_existing_invoice_identity(self) -> None:
        first = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")
        self.file_import_service.confirm_session(
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )

        preview = self.service.preview_workbench_batch(
            payloads=[payload()],
            imported_by="finance-user",
        )

        row_result = preview.session.files[0].row_results[0]
        self.assertEqual(row_result.decision.value, "duplicate_skipped")
        self.assertEqual(row_result.linked_object_type, "invoice")
        self.assertEqual(row_result.linked_object_id, self.import_service.list_invoices()[0].id)
        self.assertEqual(preview.session.status, "preview_ready")

    def test_workbench_preview_rejects_fingerprint_match_with_a_different_invoice_number(self) -> None:
        first = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")
        self.file_import_service.confirm_session(
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )
        existing_invoice_id = self.import_service.list_invoices()[0].id
        preview_entries = self.file_import_service.preview_manual_invoice_entries

        def fingerprint_fallback_preview(**kwargs):
            session = preview_entries(**kwargs)
            row_result = session.files[0].row_results[0]
            row_result.decision = ImportDecision.DUPLICATE_SKIPPED
            row_result.linked_object_type = "invoice"
            row_result.linked_object_id = existing_invoice_id
            return session

        self.file_import_service.preview_manual_invoice_entries = fingerprint_fallback_preview  # type: ignore[method-assign]

        with self.assertRaisesRegex(ManualInvoiceEntryError, "已存在于统一发票池"):
            self.service.preview_workbench_batch(
                payloads=[payload(invoice_number="26117000001052654675")],
                imported_by="finance-user",
            )

        self.assertEqual(
            self.file_import_service.list_active_sessions(
                imported_by="finance-user",
                mode="manual_invoice",
            ),
            [],
        )

    def test_workbench_preview_fails_closed_for_a_suspected_invoice_identity(self) -> None:
        preview_entries = self.file_import_service.preview_manual_invoice_entries

        def suspected_preview(**kwargs):
            session = preview_entries(**kwargs)
            row_result = session.files[0].row_results[0]
            row_result.decision = ImportDecision.SUSPECTED_DUPLICATE
            row_result.linked_object_type = "invoice"
            row_result.linked_object_id = "invoice-candidate"
            return session

        self.file_import_service.preview_manual_invoice_entries = suspected_preview  # type: ignore[method-assign]

        with self.assertRaisesRegex(ManualInvoiceEntryError, "高度相似"):
            self.service.preview_workbench_batch(
                payloads=[payload()],
                imported_by="finance-user",
            )

        self.assertEqual(
            self.file_import_service.list_active_sessions(
                imported_by="finance-user",
                mode="manual_invoice",
            ),
            [],
        )

    def test_preview_batch_keeps_multiple_invoices_in_one_confirmable_session(self) -> None:
        preview = self.service.preview_batch(
            payloads=[
                payload(invoice_number="26117000001052654674"),
                payload(invoice_number="26117000001052654675", total_with_tax="55.00", net_amount="50.00", tax_amount="5.00"),
            ],
            imported_by="finance-user",
        )

        self.assertEqual(preview.session.file_count, 2)
        self.assertEqual([item.file_name for item in preview.session.files], ["新发票1", "新发票2"])
        self.assertEqual(len(preview.file_ids), 2)
        self.file_import_service.confirm_session(
            session_id=preview.session.id,
            selected_file_ids=preview.file_ids,
        )
        self.assertEqual(len(self.import_service.list_invoices()), 2)

    def test_preview_batch_rejects_duplicate_entries_before_creating_a_session(self) -> None:
        with self.assertRaisesRegex(ManualInvoiceEntryError, "本次录入中存在重复发票"):
            self.service.preview_batch(
                payloads=[payload(), payload()],
                imported_by="finance-user",
            )

        self.assertEqual(
            self.file_import_service.list_active_sessions(imported_by="finance-user", mode="manual_invoice"),
            [],
        )

    def test_recognition_maps_only_supported_prefill_fields(self) -> None:
        service = ManualInvoiceEntryService(
            file_import_service=self.file_import_service,
            document_recognizer=FakeDocumentRecognizer(
                {
                    "invoice_no": "26117000001052654674",
                    "seller_name": "供应商",
                    "seller_tax_no": "seller-tax",
                    "buyer_name": "购方",
                    "buyer_tax_no": "buyer-tax",
                    "issue_date": "2026-08-14",
                    "net_amount": "100.00",
                    "tax_rate": "13%",
                    "tax_amount": "13.00",
                    "total_with_tax": "113.00",
                    "ignored": "never returned",
                }
            ),
        )

        values = service.recognize(file_name="invoice.jpg", content=b"image")

        self.assertEqual(values["invoice_number"], "26117000001052654674")
        self.assertEqual(values["tax_rate"], "13")
        self.assertNotIn("ignored", values)

    def test_obsolete_pending_invoice_manual_write_chain_is_removed(self) -> None:
        for symbol in (
            "preview_manual_invoice",
            "confirm_manual_invoice",
            "invoice_import_row",
            "request_key_for_payload",
        ):
            self.assertFalse(hasattr(PendingInvoiceApplicationService, symbol), symbol)


class UploadedInvoiceRecognitionTests(unittest.TestCase):
    def test_pdf_with_unrecognized_text_ocr_stops_after_first_recognized_page(self) -> None:
        pdf_bytes = _build_pdf_with_blank_pages(2)
        service = OAAttachmentInvoiceService()
        page_texts = iter(
            [
                _digital_invoice_text("126117000001052654674"),
                "second page without invoice evidence",
            ]
        )
        service._extract_pdf_page_text = lambda _page: next(page_texts)  # type: ignore[method-assign]
        ocr_calls: list[int] = []

        def fake_ocr(_content: bytes) -> list[str]:
            ocr_calls.append(1)
            return _digital_invoice_text("26117000001052654674").splitlines()

        service._run_image_ocr = fake_ocr  # type: ignore[method-assign]

        evidence = service.recognize_uploaded_invoice(file_name="invoice.pdf", content=pdf_bytes)

        self.assertEqual(evidence["invoice_no"], "26117000001052654674")
        self.assertEqual(evidence["net_amount"], "100.00")
        self.assertEqual(evidence["tax_amount"], "13.00")
        self.assertEqual(evidence["total_with_tax"], "113.00")
        self.assertEqual(len(ocr_calls), 1)

    def test_text_pdf_recognition_does_not_run_ocr(self) -> None:
        pdf_bytes = _build_pdf_with_blank_pages(1)
        service = OAAttachmentInvoiceService()
        service._extract_pdf_page_text = (  # type: ignore[method-assign]
            lambda _page: _digital_invoice_text("26117000001052654674")
        )

        def unexpected_ocr(_content: bytes) -> list[str]:
            raise AssertionError("text-recognized PDF page must not run OCR")

        service._run_image_ocr = unexpected_ocr  # type: ignore[method-assign]

        evidence = service.recognize_uploaded_invoice(file_name="invoice.pdf", content=pdf_bytes)

        self.assertEqual(evidence["invoice_no"], "26117000001052654674")

    def test_jpeg_upload_is_validated_by_signature(self) -> None:
        output = BytesIO()
        Image.new("RGB", (800, 600), color="white").save(output, format="JPEG")
        service = OAAttachmentInvoiceService()
        service._run_image_ocr = lambda _content: []  # type: ignore[method-assign]

        self.assertEqual(
            service.recognize_uploaded_invoice(file_name="invoice.jpg", content=output.getvalue()),
            {},
        )

    def test_png_upload_is_validated_and_reaches_image_recognition(self) -> None:
        output = BytesIO()
        Image.new("RGB", (800, 600), color="white").save(output, format="PNG")
        service = OAAttachmentInvoiceService()
        ocr_calls: list[bytes] = []
        service._run_image_ocr = lambda content: ocr_calls.append(content) or []  # type: ignore[method-assign]

        self.assertEqual(
            service.recognize_uploaded_invoice(file_name="invoice.png", content=output.getvalue()),
            {},
        )
        self.assertEqual(len(ocr_calls), 1)


if __name__ == "__main__":
    unittest.main()
