from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.etc_service import (
    EtcDraftRequestError,
    EtcOAHttpClientSettings,
    EtcInvoiceStatus,
    HttpEtcOAClient,
    EtcOAClient,
    EtcOAClientError,
    EtcService,
    UploadedEtcZipFile,
    parse_etc_xml,
)
from unittest.mock import patch


def etc_xml(
    invoice_number: str,
    *,
    issue_date: str = "2026-02-27",
    plate_number: str = "云ADA0381",
    total_amount: str = "13.07",
    seller_name: str = "云南高速公路联网收费管理有限公司",
    buyer_name: str = "云南溯源科技有限公司",
) -> bytes:
    amount_without_tax = (Decimal(total_amount) - Decimal("0.39")).quantize(Decimal("0.01"))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceNumber>{invoice_number}</InvoiceNumber>
  <IssueDate>{issue_date}</IssueDate>
  <PassageStartDate>{issue_date}</PassageStartDate>
  <PassageEndDate>{issue_date}</PassageEndDate>
  <PlateNumber>{plate_number}</PlateNumber>
  <VehicleType>一型客车</VehicleType>
  <AmountWithoutTax>{amount_without_tax}</AmountWithoutTax>
  <TaxAmount>0.39</TaxAmount>
  <TotalAmount>{total_amount}</TotalAmount>
  <TaxRate>3%</TaxRate>
  <SellerName>{seller_name}</SellerName>
  <SellerTaxNo>915300007194052520</SellerTaxNo>
  <BuyerName>{buyer_name}</BuyerName>
  <BuyerTaxNo>915300007194052521</BuyerTaxNo>
</Invoice>
""".encode("utf-8")


def real_etc_xml() -> bytes:
    return (
        "<EInvoice><Header><EIid>26537912570200055449</EIid></Header><EInvoiceData>"
        "<SellerInformation><SellerIdNum>9153000077859986X2</SellerIdNum>"
        "<SellerName>云南国道主干线昆明绕城高速公路建设有限公司</SellerName></SellerInformation>"
        "<BuyerInformation><BuyerIdNum>915300007194052520</BuyerIdNum>"
        "<BuyerName>云南溯源科技有限公司</BuyerName></BuyerInformation>"
        "<BasicInformation><TotalAmWithoutTax>18.63</TotalAmWithoutTax><TotalTaxAm>0.56</TotalTaxAm>"
        "<TotalTax-includedAmount>19.19</TotalTax-includedAmount></BasicInformation>"
        "<IssuItemInformation><TaxRate>0.03</TaxRate></IssuItemInformation>"
        "<SpecificInformation><Toll><PlateNumber>云ADA0381</PlateNumber><VehicleType>客车</VehicleType>"
        "<StartDatesOfPassage>20260227172851000</StartDatesOfPassage>"
        "<EndDatesOfPassage>20260227172851000</EndDatesOfPassage></Toll></SpecificInformation>"
        "</EInvoiceData><TaxSupervisionInfo><InvoiceNumber>26537912570200055449</InvoiceNumber>"
        "<IssueTime>2026-02-28</IssueTime></TaxSupervisionInfo></EInvoice>"
    ).encode("utf-8")


def fake_pdf(invoice_number: str) -> bytes:
    return f"%PDF-1.4\n% fake ETC invoice {invoice_number}\n%%EOF\n".encode("ascii")


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def etc_zip(
    invoice_numbers: list[str],
    *,
    include_pdf: bool = True,
    nested: bool = False,
) -> bytes:
    entries: dict[str, bytes] = {}
    for invoice_number in invoice_numbers:
        entries[f"xml/{invoice_number}.xml"] = etc_xml(invoice_number)
        if include_pdf:
            entries[f"pdf/{invoice_number}.pdf"] = fake_pdf(invoice_number)
    inner = zip_bytes(entries)
    if nested:
        return zip_bytes({"nested/invoices.zip": inner})
    return inner


def multipart(files: dict[str, bytes]) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-etc-boundary"
    chunks: list[bytes] = []
    for filename, content in files.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'
                "Content-Type: application/zip\r\n\r\n"
            ).encode("utf-8")
        )
        chunks.append(content)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


@dataclass(slots=True)
class UploadedAttachment:
    path: str
    oa_file_id: str


class FakeEtcOAClient(EtcOAClient):
    def __init__(self, *, fail_upload: bool = False, fail_draft: bool = False) -> None:
        self.fail_upload = fail_upload
        self.fail_draft = fail_draft
        self.uploads: list[str] = []
        self.draft_payloads: list[dict[str, object]] = []

    def upload_attachment(self, path: Path) -> str:
        if self.fail_upload:
            raise EtcOAClientError("upload failed")
        self.uploads.append(str(path))
        return f"oa-file-{len(self.uploads)}"

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        if self.fail_draft:
            raise EtcOAClientError("draft failed")
        self.draft_payloads.append({"form_id": form_id, "payload": payload})
        return "oa-draft-001", "https://www.yn-sourcing.com/oa/#/normal/forms/form/2?formId=2&id=oa-draft-001"


class MemoryEtcStateStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.saved_snapshot: dict[str, object] | None = None

    def load_etc_state(self) -> dict[str, object]:
        return dict(self.saved_snapshot or {})

    def save_etc_state(self, snapshot: dict[str, object]) -> None:
        self.saved_snapshot = dict(snapshot)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class EtcServiceTests(unittest.TestCase):
    def test_parse_real_world_etc_xml_shape(self) -> None:
        parsed = parse_etc_xml(real_etc_xml())

        self.assertEqual(parsed.invoice_number, "26537912570200055449")
        self.assertEqual(parsed.issue_date, "2026-02-28")
        self.assertEqual(parsed.passage_start_date, "2026-02-27")
        self.assertEqual(parsed.passage_end_date, "2026-02-27")
        self.assertEqual(parsed.plate_number, "云ADA0381")
        self.assertEqual(parsed.seller_tax_no, "9153000077859986X2")
        self.assertEqual(parsed.buyer_tax_no, "915300007194052520")
        self.assertEqual(parsed.amount_without_tax, Decimal("18.63"))
        self.assertEqual(parsed.tax_amount, Decimal("0.56"))
        self.assertEqual(parsed.total_amount, Decimal("19.19"))

    def test_http_oa_client_uploads_file_and_creates_form_draft(self) -> None:
        calls: list[object] = []

        def fake_urlopen(request: object, *, timeout: float) -> FakeHTTPResponse:
            calls.append(request)
            full_url = getattr(request, "full_url")
            if full_url.endswith("/file/upload"):
                return FakeHTTPResponse({"code": 200, "data": {"url": "/profile/etc.pdf"}})
            if full_url.endswith("/forms/form/2/records/record"):
                return FakeHTTPResponse({"code": 200, "data": "oa-draft-001"})
            raise AssertionError(full_url)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invoice.pdf"
            path.write_bytes(b"%PDF-1.4\n")
            client = HttpEtcOAClient(
                token="oa-token",
                settings=EtcOAHttpClientSettings(base_url="https://oa.example.test/prod-api"),
            )

            with patch("fin_ops_platform.services.etc_service.urlopen", fake_urlopen):
                file_id = client.upload_attachment(path)
                draft_id, draft_url = client.create_form_draft(
                    form_id=2,
                    payload={"formId": 2, "isDraft": True, "data": {"cause": "ETC批量提交"}},
                )

        self.assertEqual(file_id, "/profile/etc.pdf")
        self.assertEqual(draft_id, "oa-draft-001")
        self.assertIn("formId=2", draft_url)
        self.assertEqual(len(calls), 2)
        self.assertIn("Bearer oa-token", str(calls[0].headers))

    def test_http_oa_settings_treats_oa_page_base_as_oa_api_base(self) -> None:
        settings = EtcOAHttpClientSettings(base_url="https://www.yn-sourcing.com/oa")

        self.assertEqual(settings.base_url, "https://www.yn-sourcing.com/oa-api")

    def test_service_persists_invoice_metadata_through_state_store_when_available(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = MemoryEtcStateStore(Path(temp_dir))
            service = EtcService(state_store=store)

            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])
            reloaded = EtcService(state_store=store)
            invoices, total, _counts = reloaded.list_invoices(page=1, page_size=20)

        self.assertIsNotNone(store.saved_snapshot)
        self.assertEqual(total, 1)
        self.assertEqual(invoices[0].invoice_number, "ETC001")

    def test_preview_valid_zip_reports_imported_without_persisting_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            preview = service.preview_import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(preview["summary"]["imported"], 2)
        self.assertEqual(preview["summary"]["duplicatesSkipped"], 0)
        self.assertEqual(preview["summary"]["attachmentsCompleted"], 0)
        self.assertEqual(preview["summary"]["failed"], 0)
        self.assertTrue(preview["sessionId"])
        self.assertEqual(len(preview["items"]), 2)
        self.assertEqual(total, 0)
        self.assertEqual(invoices, [])

    def test_preview_audit_reports_duplicate_xml_inside_zip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            preview = service.preview_import_zips(
                [
                    UploadedEtcZipFile(
                        "duplicate-inside.zip",
                        zip_bytes(
                            {
                                "xml/ETC001.xml": etc_xml("ETC001"),
                                "xml/copy-ETC001.xml": etc_xml("ETC001"),
                                "pdf/ETC001.pdf": fake_pdf("ETC001"),
                            }
                        ),
                    )
                ]
            )

        self.assertEqual(preview["summary"], {"imported": 1, "duplicatesSkipped": 1, "attachmentsCompleted": 0, "failed": 0})
        self.assertEqual(
            preview["audit"],
            {
                "original_count": 2,
                "unique_count": 1,
                "duplicate_count": 1,
                "duplicate_in_file_count": 1,
                "duplicate_across_files_count": 0,
                "existing_duplicate_count": 0,
                "importable_count": 1,
                "update_count": 0,
                "merge_count": 0,
                "suspected_duplicate_count": 0,
                "error_count": 0,
                "confirmable_count": 1,
                "skipped_count": 1,
            },
        )

    def test_preview_audit_reports_duplicate_xml_across_zips(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            preview = service.preview_import_zips(
                [
                    UploadedEtcZipFile("first.zip", etc_zip(["ETC001"])),
                    UploadedEtcZipFile("second.zip", etc_zip(["ETC001"])),
                ]
            )

        self.assertEqual(preview["summary"], {"imported": 1, "duplicatesSkipped": 1, "attachmentsCompleted": 0, "failed": 0})
        self.assertEqual(preview["audit"]["original_count"], 2)
        self.assertEqual(preview["audit"]["unique_count"], 1)
        self.assertEqual(preview["audit"]["duplicate_count"], 1)
        self.assertEqual(preview["audit"]["duplicate_in_file_count"], 0)
        self.assertEqual(preview["audit"]["duplicate_across_files_count"], 1)
        self.assertEqual(preview["audit"]["importable_count"], 1)
        self.assertEqual(preview["audit"]["skipped_count"], 1)

    def test_confirm_import_session_persists_records_and_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            preview = service.preview_import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])

            confirmed = service.confirm_import_session(str(preview["sessionId"]))
            repeated = service.confirm_import_session(str(preview["sessionId"]))
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)
            import_batch = service.list_import_batches()[0]

        self.assertEqual(confirmed.imported, 2)
        self.assertEqual(repeated.imported, 2)
        self.assertEqual(total, 2)
        self.assertEqual({invoice.invoice_number for invoice in invoices}, {"ETC001", "ETC002"})
        self.assertEqual(import_batch.source_session_id, preview["sessionId"])
        self.assertEqual({invoice.import_session_id for invoice in invoices}, {preview["sessionId"]})

    def test_import_batch_tracks_invoice_ids_and_date_ranges(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            service.import_zips(
                [
                    UploadedEtcZipFile(
                        "jan-feb.zip",
                        zip_bytes(
                            {
                                "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-01-15", total_amount="10.00"),
                                "pdf/ETC001.pdf": fake_pdf("ETC001"),
                                "xml/ETC002.xml": etc_xml("ETC002", issue_date="2026-02-14", total_amount="20.00"),
                                "pdf/ETC002.pdf": fake_pdf("ETC002"),
                            }
                        ),
                    )
                ]
            )
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)
            import_batches = service.list_import_batches()

        self.assertEqual(total, 2)
        self.assertEqual(len(import_batches), 1)
        import_batch = import_batches[0]
        self.assertEqual(import_batch.id, "etc_import_batch_0001")
        self.assertEqual(import_batch.invoice_ids, ["etc_invoice_0001", "etc_invoice_0002"])
        self.assertEqual(import_batch.invoice_count, 2)
        self.assertEqual(import_batch.total_amount, Decimal("30.00"))
        self.assertEqual(import_batch.issue_date_start, "2026-01-15")
        self.assertEqual(import_batch.issue_date_end, "2026-02-14")
        self.assertEqual(import_batch.passage_date_start, "2026-01-15")
        self.assertEqual(import_batch.passage_date_end, "2026-02-14")
        self.assertEqual({invoice.import_batch_id for invoice in invoices}, {"etc_import_batch_0001"})

    def test_import_zip_parses_nested_xml_stores_files_deduplicates_and_completes_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            first = service.import_zips(
                [
                    UploadedEtcZipFile("outer.zip", etc_zip(["ETC001", "ETC002"], include_pdf=False, nested=True)),
                    UploadedEtcZipFile("second.zip", etc_zip(["ETC003", "ETC004"], include_pdf=True)),
                ]
            )
            duplicate = service.import_zips([UploadedEtcZipFile("duplicate.zip", etc_zip(["ETC003"], include_pdf=True))])
            completed = service.import_zips([UploadedEtcZipFile("complete.zip", etc_zip(["ETC001"], include_pdf=True))])
            invoices, total, counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(first.imported, 4)
        self.assertEqual(first.failed, 0)
        self.assertEqual(duplicate.duplicates_skipped, 1)
        self.assertEqual(completed.attachments_completed, 1)
        self.assertEqual(total, 4)
        self.assertEqual(counts["unsubmitted"], 4)
        invoice_by_no = {invoice.invoice_number: invoice for invoice in invoices}
        self.assertEqual(invoice_by_no["ETC001"].total_amount, Decimal("13.07"))
        self.assertTrue(invoice_by_no["ETC001"].xml_file_path)
        self.assertTrue(invoice_by_no["ETC001"].xml_file_hash)
        self.assertTrue(invoice_by_no["ETC001"].pdf_file_path)
        self.assertTrue(invoice_by_no["ETC001"].pdf_file_hash)

    def test_preview_and_confirm_report_duplicates_and_attachment_completion(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips([UploadedEtcZipFile("missing-pdf.zip", etc_zip(["ETC001"], include_pdf=False))])
            service.import_zips([UploadedEtcZipFile("existing.zip", etc_zip(["ETC002"], include_pdf=True))])

            preview = service.preview_import_zips(
                [
                    UploadedEtcZipFile("complete-existing.zip", etc_zip(["ETC001"], include_pdf=True)),
                    UploadedEtcZipFile("duplicate.zip", etc_zip(["ETC002"], include_pdf=True)),
                    UploadedEtcZipFile("new.zip", etc_zip(["ETC003"], include_pdf=True)),
                ]
            )
            confirmed = service.confirm_import_session(str(preview["sessionId"]))
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(preview["summary"], {"imported": 1, "duplicatesSkipped": 1, "attachmentsCompleted": 1, "failed": 0})
        self.assertEqual(preview["audit"]["original_count"], 3)
        self.assertEqual(preview["audit"]["unique_count"], 3)
        self.assertEqual(preview["audit"]["existing_duplicate_count"], 1)
        self.assertEqual(preview["audit"]["importable_count"], 1)
        self.assertEqual(preview["audit"]["update_count"], 1)
        self.assertEqual(preview["audit"]["confirmable_count"], 2)
        self.assertEqual(preview["audit"]["skipped_count"], 1)
        self.assertEqual(confirmed.imported, 1)
        self.assertEqual(confirmed.duplicates_skipped, 1)
        self.assertEqual(confirmed.attachments_completed, 1)
        self.assertEqual(total, 3)
        invoice_by_no = {invoice.invoice_number: invoice for invoice in invoices}
        self.assertTrue(invoice_by_no["ETC001"].pdf_file_path)

    def test_reimport_completes_attachment_when_stored_pdf_file_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips([UploadedEtcZipFile("initial.zip", etc_zip(["ETC001"], include_pdf=True))])
            invoices, _total, _counts = service.list_invoices(page=1, page_size=20)
            self.assertTrue(invoices[0].pdf_file_path)
            Path(str(invoices[0].pdf_file_path)).unlink()

            preview = service.preview_import_zips([UploadedEtcZipFile("repair.zip", etc_zip(["ETC001"], include_pdf=True))])
            confirmed = service.confirm_import_session(str(preview["sessionId"]))
            repaired, _total, _counts = service.list_invoices(page=1, page_size=20)

            self.assertEqual(preview["summary"], {"imported": 0, "duplicatesSkipped": 0, "attachmentsCompleted": 1, "failed": 0})
            self.assertEqual(confirmed.attachments_completed, 1)
            self.assertTrue(repaired[0].pdf_file_path)
            self.assertTrue(Path(str(repaired[0].pdf_file_path)).exists())

    def test_import_reports_missing_xml_and_malformed_xml_without_blocking_other_zips(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            result = service.import_zips(
                [
                    UploadedEtcZipFile("missing-xml.zip", zip_bytes({"pdf/only.pdf": fake_pdf("ONLY")})),
                    UploadedEtcZipFile("bad-xml.zip", zip_bytes({"xml/bad.xml": b"<Invoice>"})),
                    UploadedEtcZipFile("valid.zip", etc_zip(["ETC100"])),
                ]
            )
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(result.imported, 1)
        self.assertEqual(result.failed, 2)
        self.assertEqual(total, 1)
        self.assertEqual(invoices[0].invoice_number, "ETC100")
        self.assertEqual([item.status for item in result.items].count("failed"), 2)

    def test_query_filters_counts_and_pagination(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips(
                [
                    UploadedEtcZipFile(
                        "invoices.zip",
                        zip_bytes(
                            {
                                "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-02-27", plate_number="云ADA0381"),
                                "pdf/ETC001.pdf": fake_pdf("ETC001"),
                                "xml/ETC002.xml": etc_xml("ETC002", issue_date="2026-03-01", plate_number="云B12345"),
                                "pdf/ETC002.pdf": fake_pdf("ETC002"),
                                "xml/ETC003.xml": etc_xml("ETC003", issue_date="2026-02-28", plate_number="云ADA0381", seller_name="昆明高速"),
                                "pdf/ETC003.pdf": fake_pdf("ETC003"),
                            }
                        ),
                    )
                ]
            )
            service.update_invoice_status(["etc_invoice_0002"], EtcInvoiceStatus.SUBMITTED)

            invoices, total, counts = service.list_invoices(
                status=EtcInvoiceStatus.UNSUBMITTED,
                month="2026-02",
                plate="ADA",
                keyword="高速",
                page=1,
                page_size=1,
            )

        self.assertEqual(total, 2)
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0].invoice_number, "ETC003")
        self.assertEqual(counts, {"unsubmitted": 2, "submitted": 1, "current": 2})

    def test_batch_status_revoke_and_draft_creation_with_fake_oa_client(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])

            draft = service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            after_draft, _total, _counts = service.list_invoices(page=1, page_size=20)
            confirmed = service.confirm_submitted(draft.batch_id)
            revoked = service.revoke_submitted(["etc_invoice_0001", "etc_invoice_0002"])
            not_submitted = service.mark_not_submitted(draft.batch_id)

        self.assertEqual(draft.oa_draft_id, "oa-draft-001")
        self.assertEqual(len(fake_oa.uploads), 2)
        self.assertTrue(all(Path(upload).suffix == ".pdf" for upload in fake_oa.uploads))
        self.assertEqual(after_draft[0].status, EtcInvoiceStatus.UNSUBMITTED)
        payload = fake_oa.draft_payloads[0]["payload"]
        data = payload["data"]
        self.assertTrue(payload["isDraft"])
        self.assertEqual(payload["formId"], 2)
        self.assertEqual(data["applicationDate"], date.today().isoformat())
        self.assertEqual(data["category"], "s5")
        self.assertEqual(data["paymentProof"], "")
        self.assertEqual(data["projectName"], "6486ca70cd6cae5d4e2b0b48")
        self.assertEqual(data["cause"], f"ETC批量提交\netc_batch_id={draft.etc_batch_id}")
        uploaded_invoices = data["field101"]["list"]
        self.assertEqual(
            [(item["name"], item["response"]["data"], item["response"]["extra"]["fileName"]) for item in uploaded_invoices],
            [
                ("ETC001.pdf", "oa-file-1", "ETC001.pdf"),
                ("ETC002.pdf", "oa-file-2", "ETC002.pdf"),
            ],
        )
        self.assertEqual(confirmed.status, "submitted_confirmed")
        self.assertEqual(revoked["updated"], 2)
        self.assertEqual(not_submitted.status, "not_submitted")

    def test_draft_creation_rejects_partial_import_batch_submission(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])

            with self.assertRaisesRegex(EtcDraftRequestError, "完整未提交 ETC 导入批次"):
                service.create_oa_draft(["etc_invoice_0001"])

        self.assertEqual(fake_oa.uploads, [])
        self.assertEqual(fake_oa.draft_payloads, [])

    def test_draft_creation_accepts_complete_import_batch_submission(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])

            draft = service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            invoices, _total, _counts = service.list_invoices(page=1, page_size=20)
            import_batch = service.list_import_batches()[0]

        self.assertEqual(draft.oa_draft_id, "oa-draft-001")
        self.assertEqual(import_batch.submission_batch_id, draft.batch_id)
        self.assertEqual({invoice.current_batch_id for invoice in invoices}, {draft.batch_id})
        self.assertEqual({invoice.import_batch_id for invoice in invoices}, {import_batch.id})
        self.assertEqual(len(fake_oa.uploads), 2)

    def test_draft_creation_failure_marks_batch_failed_and_keeps_invoice_unsubmitted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient(fail_draft=True))
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])

            with self.assertRaises(EtcDraftRequestError):
                service.create_oa_draft(["etc_invoice_0001"])
            invoices, _total, _counts = service.list_invoices(page=1, page_size=20)
            batches = service.list_batches()

        self.assertEqual(invoices[0].status, EtcInvoiceStatus.UNSUBMITTED)
        self.assertEqual(batches[0].status, "failed")
        self.assertIn("draft failed", batches[0].error_message or "")

    def test_draft_creation_rejects_missing_pdf_and_submitted_invoice_before_oa_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("missing-pdf.zip", etc_zip(["ETC001"], include_pdf=False))])

            with self.assertRaises(EtcDraftRequestError):
                service.create_oa_draft(["etc_invoice_0001"])

            service.import_zips([UploadedEtcZipFile("complete.zip", etc_zip(["ETC001"], include_pdf=True))])
            service.update_invoice_status(["etc_invoice_0001"], EtcInvoiceStatus.SUBMITTED)
            with self.assertRaises(EtcDraftRequestError):
                service.create_oa_draft(["etc_invoice_0001"])

        self.assertEqual(fake_oa.uploads, [])
        self.assertEqual(fake_oa.draft_payloads, [])


class EtcApiTests(unittest.TestCase):
    def _wait_for_job(self, app, job_id: str, *, timeout: float = 2.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            response = app.handle_request("GET", f"/api/background-jobs/{job_id}")
            payload = json.loads(response.body)
            job = payload.get("job", {})
            if isinstance(job, dict) and job.get("status") in {"succeeded", "partial_success", "failed"}:
                return job
            time.sleep(0.02)
        self.fail(f"background job {job_id} did not finish: {payload}")

    def test_etc_confirm_returns_background_job_and_imports_asynchronously(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001", "ETC002"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            before_confirm_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"]}),
            )
            confirm_payload = json.loads(confirm_response.body)
            job = confirm_payload["job"]
            completed_job = self._wait_for_job(app, job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(json.loads(before_confirm_response.body)["total"], 0)
        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(job["type"], "etc_invoice_import")
        self.assertEqual(job["total"], 2)
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(completed_job["current"], 2)
        self.assertEqual(completed_job["total"], 2)
        self.assertEqual(completed_job["result_summary"]["created"], 2)
        self.assertEqual(completed_job["result_summary"]["imported"], 2)
        self.assertEqual(completed_job["result_summary"]["total"], 2)
        self.assertEqual(json.loads(query_response.body)["total"], 2)

    def test_etc_import_syncs_to_canonical_invoices_and_dedupes_manual_invoice(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            manual_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="input-invoices.xlsx",
                imported_by="finance",
                rows=[
                    {
                        "digital_invoice_no": "ETC001",
                        "counterparty_name": "云南高速公路联网收费管理有限公司",
                        "seller_name": "云南高速公路联网收费管理有限公司",
                        "seller_tax_no": "915300007194052520",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052521",
                        "amount": "13.07",
                        "total_with_tax": "13.07",
                        "tax_amount": "0.39",
                        "invoice_date": "2026-02-27",
                    }
                ],
            )
            app._import_service.confirm_import(manual_preview.id)
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            session_id = preview_payload["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            invoices = app._import_service.list_invoices()

        self.assertEqual(preview_payload["audit"]["importable_count"], 0)
        self.assertEqual(preview_payload["audit"]["merge_count"], 1)
        self.assertEqual(preview_payload["audit"]["confirmable_count"], 1)
        self.assertEqual(len(invoices), 1)
        self.assertIn("ETC", invoices[0].tags)
        self.assertEqual(invoices[0].etc_invoice_id, "etc_invoice_0001")
        source_types = {source_link["source_type"] for source_link in invoices[0].source_links}
        self.assertEqual(source_types, {"manual_invoice_import", "etc_invoice_import"})

    def test_etc_import_keeps_distinct_invoice_numbers_with_same_amount_as_separate_canonical_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001", "ETC002"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            invoices = app._import_service.list_invoices()

        self.assertEqual(len(invoices), 2)
        self.assertCountEqual([invoice.digital_invoice_no for invoice in invoices], ["ETC001", "ETC002"])
        self.assertEqual({invoice.source_unique_key for invoice in invoices}, {"ETC001", "ETC002"})

    def test_etc_import_confirm_returns_preview_stale_when_canonical_invoice_changes_after_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            manual_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="input-invoices.xlsx",
                imported_by="finance",
                rows=[
                    {
                        "digital_invoice_no": "ETC001",
                        "counterparty_name": "云南高速公路联网收费管理有限公司",
                        "seller_name": "云南高速公路联网收费管理有限公司",
                        "seller_tax_no": "915300007194052520",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052521",
                        "amount": "13.07",
                        "total_with_tax": "13.07",
                        "tax_amount": "0.39",
                        "invoice_date": "2026-02-27",
                    }
                ],
            )
            app._import_service.confirm_import(manual_preview.id)

            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"]}),
            )
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(preview_payload["audit"]["importable_count"], 1)
        self.assertEqual(preview_payload["audit"]["merge_count"], 0)
        self.assertEqual(confirm_response.status_code, 409)
        self.assertEqual(json.loads(confirm_response.body)["error"], "preview_stale")
        self.assertEqual(json.loads(query_response.body)["total"], 0)

    def test_confirmed_etc_submission_hides_scatter_invoice_from_workbench(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            before_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-02").body)
            draft_response = app.handle_request(
                "POST",
                "/api/etc/batches/draft",
                json.dumps({"invoiceIds": ["etc_invoice_0001"]}),
            )
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            after_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-02").body)
            canonical_invoice = app._import_service.list_invoices()[0]

        before_invoice_rows = [
            row
            for group in before_payload["open"]["groups"]
            for row in group["invoice_rows"]
        ]
        after_invoice_rows = [
            row
            for group in after_payload["open"]["groups"]
            for row in group["invoice_rows"]
        ]
        self.assertEqual(len(before_invoice_rows), 1)
        self.assertEqual(before_invoice_rows[0]["source_kind"], "etc_invoice")
        self.assertIn("ETC", before_invoice_rows[0]["tags"])
        self.assertEqual(after_invoice_rows, [])
        self.assertEqual(canonical_invoice.workbench_visibility, "hidden_after_etc_submission")

    def test_confirmed_etc_submission_renders_folded_invoice_summary_for_matching_oa(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            body, headers = multipart({"outer.zip": etc_zip(["ETC001", "ETC002"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            draft_response = app.handle_request(
                "POST",
                "/api/etc/batches/draft",
                json.dumps({"invoiceIds": ["etc_invoice_0001", "etc_invoice_0002"]}),
            )
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            raw_payload = {
                "month": "2026-02",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {
                            "id": "oa-etc-202602-001",
                            "type": "oa",
                            "source": "etc_batch",
                            "etc_batch_id": draft_payload["etcBatchId"],
                            "etcBatchId": draft_payload["etcBatchId"],
                            "tags": ["ETC批量提交"],
                            "case_id": "",
                            "applicant": "张三",
                            "apply_type": "支付申请",
                            "amount": "26.14",
                            "counterparty_name": "云南高速通行费",
                            "reason": f"ETC批量提交\netc_batch_id={draft_payload['etcBatchId']}",
                            "oa_bank_relation": {"code": "pending_match", "label": "待找流水", "tone": "warn"},
                            "available_actions": ["detail"],
                        }
                    ],
                    "bank": [],
                    "invoice": [],
                },
            }
            with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
                payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-02").body)
            invoice_rows = [
                row
                for group in payload["open"]["groups"]
                for row in group["invoice_rows"]
            ]
            detail_response = app.handle_request("GET", f"/api/workbench/rows/{invoice_rows[0]['id']}")
            detail_payload = json.loads(detail_response.body)

        self.assertEqual(len(invoice_rows), 1)
        summary_row = invoice_rows[0]
        self.assertEqual(summary_row["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary_row["seller_name"], "ETC发票 2 张")
        self.assertEqual(summary_row["etc_invoice_count"], 2)
        self.assertEqual(summary_row["total_with_tax"], "26.14")
        self.assertEqual(summary_row["etc_batch_id"], draft_payload["etcBatchId"])
        self.assertIn("ETC", summary_row["tags"])
        self.assertIn("已关联ETC发票", summary_row["tags"])
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_payload["row"]["id"], summary_row["id"])
        self.assertIn("ETC001", detail_payload["row"]["detail_fields"]["发票清单"])
        self.assertIn("ETC002", detail_payload["row"]["detail_fields"]["发票清单"])

    def test_etc_invoice_api_reports_attachment_existence_flags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"])})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        payload = json.loads(query_response.body)
        self.assertEqual(payload["total"], 1)
        self.assertTrue(payload["items"][0]["has_pdf"])
        self.assertTrue(payload["items"][0]["has_xml"])

    def test_etc_confirm_repeated_session_returns_same_job_without_duplicate_import(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            first_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            first_job = json.loads(first_response.body)["job"]
            second_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            second_job = json.loads(second_response.body)["job"]
            self._wait_for_job(app, first_job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(first_response.status_code, 202)
        self.assertEqual(second_response.status_code, 202)
        self.assertEqual(second_job["job_id"], first_job["job_id"])
        self.assertEqual(json.loads(query_response.body)["total"], 1)

    def test_etc_confirm_job_partial_success_when_some_items_fail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart(
                {
                    "mixed.zip": zip_bytes(
                        {
                            "xml/ETC001.xml": etc_xml("ETC001"),
                            "pdf/ETC001.pdf": fake_pdf("ETC001"),
                            "xml/bad.xml": b"<Invoice>",
                        }
                    )
                }
            )

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            session_id = preview_payload["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            completed_job = self._wait_for_job(app, job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(preview_payload["audit"]["original_count"], 2)
        self.assertEqual(preview_payload["audit"]["importable_count"], 1)
        self.assertEqual(preview_payload["audit"]["error_count"], 1)
        self.assertEqual(preview_payload["audit"]["skipped_count"], 1)
        self.assertEqual(job["total"], 2)
        self.assertEqual(completed_job["status"], "partial_success")
        self.assertEqual(completed_job["current"], 2)
        self.assertEqual(completed_job["result_summary"]["created"], 1)
        self.assertEqual(completed_job["result_summary"]["failed"], 1)
        self.assertEqual(completed_job["result_summary"]["total"], 2)
        self.assertEqual(json.loads(query_response.body)["total"], 1)

    def test_import_query_revoke_and_batch_api_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            body, headers = multipart({"outer.zip": etc_zip(["ETC001", "ETC002"], nested=True)})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            before_confirm_response = app.handle_request("GET", "/api/etc/invoices?status=unsubmitted&month=2026-02&page=1&page_size=1")
            import_confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"]}),
            )
            import_confirm_payload = json.loads(import_confirm_response.body)
            self._wait_for_job(app, import_confirm_payload["job"]["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?status=unsubmitted&month=2026-02&page=1&page_size=1")
            draft_response = app.handle_request(
                "POST",
                "/api/etc/batches/draft",
                json.dumps({"invoiceIds": ["etc_invoice_0001", "etc_invoice_0002"]}),
            )
            draft_payload = json.loads(draft_response.body)
            confirm_response = app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            revoke_response = app.handle_request(
                "POST",
                "/api/etc/invoices/revoke-submitted",
                json.dumps({"invoiceIds": ["etc_invoice_0001", "etc_invoice_0002"]}),
            )
            not_submitted_response = app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/mark-not-submitted")

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["summary"]["imported"], 2)
        self.assertEqual(preview_payload["imported"], 2)
        self.assertEqual(before_confirm_response.status_code, 200)
        self.assertEqual(json.loads(before_confirm_response.body)["total"], 0)
        self.assertEqual(import_confirm_response.status_code, 202)
        self.assertEqual(import_confirm_payload["job"]["type"], "etc_invoice_import")
        self.assertEqual(import_confirm_payload["job"]["total"], 2)
        self.assertEqual(query_response.status_code, 200)
        query_payload = json.loads(query_response.body)
        self.assertEqual(query_payload["total"], 2)
        self.assertEqual(query_payload["pageSize"], 1)
        self.assertEqual(query_payload["counts"], {"unsubmitted": 2, "submitted": 0, "current": 2})
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["oaDraftId"], "oa-draft-001")
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(json.loads(confirm_response.body)["batch"]["status"], "submitted_confirmed")
        self.assertEqual(revoke_response.status_code, 200)
        self.assertEqual(json.loads(revoke_response.body)["updated"], 2)
        self.assertEqual(not_submitted_response.status_code, 200)
        self.assertEqual(json.loads(not_submitted_response.body)["batch"]["status"], "not_submitted")

    def test_preview_rejects_non_zip_upload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"not-a-zip.txt": b"plain text"})

            response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(json.loads(response.body)["error"], "invalid_etc_import_request")

    def test_old_direct_import_no_longer_persists_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"invoices.zip": etc_zip(["ETC001"])})

            response = app.handle_request("POST", "/api/etc/import", body=body, headers=headers)
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertIn(response.status_code, {400, 410})
        self.assertEqual(json.loads(query_response.body)["total"], 0)

    def test_api_returns_clear_errors_for_invalid_input(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            empty_draft = app.handle_request("POST", "/api/etc/batches/draft", json.dumps({"invoiceIds": []}))
            missing_batch = app.handle_request("POST", "/api/etc/batches/missing/confirm-submitted")
            bad_revoke = app.handle_request("POST", "/api/etc/invoices/revoke-submitted", json.dumps({"invoiceIds": []}))

        self.assertEqual(empty_draft.status_code, 400)
        self.assertEqual(json.loads(empty_draft.body)["error"], "invalid_etc_draft_request")
        self.assertEqual(missing_batch.status_code, 404)
        self.assertEqual(json.loads(missing_batch.body)["error"], "etc_batch_not_found")
        self.assertEqual(bad_revoke.status_code, 400)
        self.assertEqual(json.loads(bad_revoke.body)["error"], "invalid_etc_invoice_request")

    def test_etc_draft_returns_clear_error_when_oa_token_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"outer.zip": etc_zip(["ETC001"])})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            draft_response = app.handle_request(
                "POST",
                "/api/etc/batches/draft",
                json.dumps({"invoiceIds": ["etc_invoice_0001"]}),
            )

        self.assertEqual(draft_response.status_code, 400)
        payload = json.loads(draft_response.body)
        self.assertEqual(payload["error"], "invalid_etc_draft_request")
        self.assertIn("OA 登录 token 缺失", payload["message"])


if __name__ == "__main__":
    unittest.main()
