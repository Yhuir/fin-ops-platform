from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import fitz

from tests.app_test_support import build_local_state_application
from fin_ops_platform.services.etc_invoice_pdf_bundle_service import (
    EtcInvoicePdfBundleError,
    EtcInvoicePdfBundleService,
)
from fin_ops_platform.services.etc_service import EtcBusinessBatchStatus, EtcInvoice


def _pdf_bytes(label: str, *, pages: int = 1) -> bytes:
    document = fitz.open()
    try:
        for page_number in range(pages):
            page = document.new_page(width=595, height=842)
            page.insert_text((72, 96), f"{label} page {page_number + 1}", fontsize=18)
        return document.tobytes()
    finally:
        document.close()


def _invoice(invoice_number: str, content: bytes, *, issue_date: str = "2026-05-01") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"invoice-{invoice_number}",
        invoice_number=invoice_number,
        issue_date=issue_date,
        pdf_file_hash=hashlib.sha256(content).hexdigest(),
    )


class EtcInvoicePdfBundleServiceTests(unittest.TestCase):
    def test_builds_68_single_page_invoices_as_one_68_page_pdf_in_stable_order(self) -> None:
        contents = {f"invoice-ETC-{index:03d}": _pdf_bytes(f"ETC-{index:03d}") for index in range(68, 0, -1)}
        invoices = [
            _invoice(f"ETC-{index:03d}", contents[f"invoice-ETC-{index:03d}"])
            for index in range(68, 0, -1)
        ]
        service = EtcInvoicePdfBundleService(read_invoice_pdf=contents.__getitem__)

        result = service.build(
            batch=SimpleNamespace(oa_draft_id="oa-draft-001", title="5、6月高速费"),
            invoices=invoices,
        )

        document = fitz.open(stream=result.content, filetype="pdf")
        try:
            self.assertEqual(result.invoice_count, 68)
            self.assertEqual(result.page_count, 68)
            self.assertEqual(document.page_count, 68)
            self.assertIn("ETC-001", document[0].get_text())
            self.assertIn("ETC-068", document[67].get_text())
            self.assertEqual(result.filename, "ETC发票_5、6月高速费_68张.pdf")
        finally:
            document.close()

    def test_rejects_missing_corrupt_multi_page_and_hash_mismatch_without_partial_output(self) -> None:
        valid = _pdf_bytes("valid")
        multi_page = _pdf_bytes("multi", pages=2)
        hash_mismatch = _invoice("HASH", valid)
        hash_mismatch.pdf_file_hash = "0" * 64
        scenarios = [
            (
                "missing",
                _invoice("MISSING", valid),
                lambda _invoice_id: (_ for _ in ()).throw(FileNotFoundError("missing")),
                "invoice_pdf_unavailable",
            ),
            (
                "corrupt",
                _invoice("CORRUPT", b"not-a-pdf"),
                lambda _invoice_id: b"not-a-pdf",
                "invoice_pdf_invalid",
            ),
            (
                "multi-page",
                _invoice("MULTI", multi_page),
                lambda _invoice_id: multi_page,
                "invoice_pdf_page_count_invalid",
            ),
            (
                "hash-mismatch",
                hash_mismatch,
                lambda _invoice_id: valid,
                "invoice_pdf_unavailable",
            ),
        ]
        for label, invoice, reader, expected_code in scenarios:
            with self.subTest(label=label):
                service = EtcInvoicePdfBundleService(read_invoice_pdf=reader)
                with self.assertRaises(EtcInvoicePdfBundleError) as caught:
                    service.build(
                        batch=SimpleNamespace(oa_draft_id="oa-draft-001", title="ETC"),
                        invoices=[invoice],
                    )
                self.assertEqual(caught.exception.code, expected_code)

    def test_requires_a_successfully_created_oa_draft(self) -> None:
        content = _pdf_bytes("ETC-001")
        service = EtcInvoicePdfBundleService(read_invoice_pdf=lambda _invoice_id: content)

        with self.assertRaises(EtcInvoicePdfBundleError) as caught:
            service.build(
                batch=SimpleNamespace(oa_draft_id=None, title="ETC"),
                invoices=[_invoice("ETC-001", content)],
            )

        self.assertEqual(caught.exception.code, "invoice_pdf_bundle_not_ready")

    def test_rejects_empty_batches_and_bounded_resource_overflow(self) -> None:
        content = _pdf_bytes("ETC-001")
        batch = SimpleNamespace(oa_draft_id="oa-draft-001", title="ETC")
        scenarios = [
            (
                "empty",
                EtcInvoicePdfBundleService(read_invoice_pdf=lambda _invoice_id: content),
                [],
                "invoice_pdf_bundle_empty",
            ),
            (
                "invoice-count",
                EtcInvoicePdfBundleService(
                    read_invoice_pdf=lambda _invoice_id: content,
                    max_invoice_count=1,
                ),
                [_invoice("ETC-001", content), _invoice("ETC-002", content)],
                "invoice_pdf_bundle_too_large",
            ),
            (
                "source-bytes",
                EtcInvoicePdfBundleService(
                    read_invoice_pdf=lambda _invoice_id: content,
                    max_total_bytes=len(content) - 1,
                ),
                [_invoice("ETC-001", content)],
                "invoice_pdf_bundle_too_large",
            ),
        ]
        for label, service, invoices, expected_code in scenarios:
            with self.subTest(label=label):
                with self.assertRaises(EtcInvoicePdfBundleError) as caught:
                    service.build(batch=batch, invoices=invoices)
                self.assertEqual(caught.exception.code, expected_code)


class EtcInvoicePdfBundleApiTests(unittest.TestCase):
    def test_download_endpoint_returns_pdf_headers_pages_and_audit_event(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            try:
                batch = app._etc_service.create_business_batch(task_id="ETC-TASK-PDF", title="五月高速费")
                invoice_ids: list[str] = []
                for index in range(1, 4):
                    content = _pdf_bytes(f"API-ETC-{index:03d}")
                    path = Path(temp_dir) / f"invoice-{index:03d}.pdf"
                    path.write_bytes(content)
                    invoice = EtcInvoice(
                        id=f"etc-invoice-{index:03d}",
                        invoice_number=f"API-ETC-{index:03d}",
                        issue_date=f"2026-05-{index:02d}",
                        passage_start_date=None,
                        passage_end_date=None,
                        plate_number="云ADA0381",
                        vehicle_type=None,
                        seller_name="高速公路",
                        seller_tax_no=None,
                        buyer_name="云南溯源科技有限公司",
                        buyer_tax_no=None,
                        amount_without_tax=Decimal("10.00"),
                        tax_amount=Decimal("0.30"),
                        total_amount=Decimal("10.30"),
                        tax_rate="3%",
                        zip_source_name="invoice.zip",
                        xml_file_path=None,
                        xml_file_hash=None,
                        pdf_file_path=str(path),
                        pdf_file_hash=hashlib.sha256(content).hexdigest(),
                        business_batch_id=batch.business_batch_id,
                        current_batch_id=batch.business_batch_id,
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                    app._etc_service._invoices[invoice.id] = invoice
                    app._etc_service._invoice_numbers[invoice.invoice_number] = invoice.id
                    invoice_ids.append(invoice.id)
                stored_batch = app._etc_service._business_batches[batch.business_batch_id]
                stored_batch.invoice_ids = invoice_ids
                stored_batch.status = EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value
                stored_batch.oa_draft_id = "oa-draft-pdf-001"
                stored_batch.oa_draft_url = "https://oa.example.test/draft/oa-draft-pdf-001"
                app._etc_service._persist()

                response = app.handle_request(
                    "GET",
                    f"/api/etc/business-batches/{batch.business_batch_id}/invoice-pdf",
                )
                audit_entries = app._audit_service.as_dicts()
            finally:
                app._background_job_service.shutdown()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])
        self.assertNotIn("Content-Length", response.headers)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertEqual(response.headers["X-ETC-Invoice-Count"], "3")
        self.assertEqual(response.headers["X-PDF-Page-Count"], "3")
        document = fitz.open(stream=bytes(response.body), filetype="pdf")
        try:
            self.assertEqual(document.page_count, 3)
        finally:
            document.close()
        self.assertEqual(audit_entries[-1]["action"], "etc_invoice_pdf_bundle_downloaded")
        self.assertEqual(audit_entries[-1]["entity_id"], batch.business_batch_id)
        self.assertEqual(audit_entries[-1]["metadata"]["invoice_count"], 3)

    def test_download_endpoint_rejects_batch_before_oa_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_local_state_application(data_dir=Path(temp_dir))
            try:
                batch = app._etc_service.create_business_batch(task_id="ETC-TASK-NO-DRAFT", title="未创建草稿")
                response = app.handle_request(
                    "GET",
                    f"/api/etc/business-batches/{batch.business_batch_id}/invoice-pdf",
                )
            finally:
                app._background_job_service.shutdown()

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"]["code"], "invoice_pdf_bundle_not_ready")


if __name__ == "__main__":
    unittest.main()
