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
    EtcInvoiceNotFoundError,
    HttpEtcOAClient,
    EtcOAClient,
    EtcOAClientError,
    EtcService,
    UploadedEtcZipFile,
    parse_etc_xml,
)
from fin_ops_platform.services.etc_document_parsers import CcbCreditCardStatementParser, SupplementEvidenceParser, TicketRootPdfTextParser
from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind
from fin_ops_platform.services.historical_etc_repair_service import (
    HistoricalEtcRepairBatchSpec,
    HistoricalEtcRepairService,
)
from unittest.mock import patch


TICKET_ROOT_TEXT = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-03 17:06:18
入口站 昆明南站
出口站 九龙池站
金额 25.00
发票张数 1
"""

TICKET_ROOT_TEXT_WITHOUT_PLATE = """
票根网通行明细
交易时间 2026-03-03 17:06:18
入口站 昆明南站
出口站 九龙池站
金额 25.00
发票张数 1
"""

CCB_STATEMENT_TEXT = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-03-03 2026-03-04 3632 微信支付-云南昆明南站高速通行费 CNY 25.00 25.00
2026-03-03 2026-03-04 3632 云南九龙池站高速通行费 CNY 23.00 23.00
"""

TICKET_ROOT_CLIPBOARD_TEXT = """
收费公路通行费电子发票服务平台
按开票记录查看 按行程查看
返回卡列表
路网中心ETC：记账卡 990100**********4908    车牌号：云ADA0381
202604
入口收费站/出口收费站
交易时间：2026-04-08 18:57:17交易金额：￥71.25查看发票      发票下载      发票转发
云南
云南弥勒南站
云南
云南小喜村站
发票数量：2
"""


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


def multipart(files: dict[str, bytes], fields: dict[str, str] | None = None) -> tuple[bytes, dict[str, str]]:
    boundary = "----finops-etc-boundary"
    chunks: list[bytes] = []
    for name, value in (fields or {}).items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
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

    def test_create_historical_submitted_batch_is_idempotent_and_summarized(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips(
                [
                    UploadedEtcZipFile(
                        "historical.zip",
                        zip_bytes(
                            {
                                "xml/ETC001.xml": etc_xml(
                                    "ETC001",
                                    issue_date="2026-01-15",
                                    plate_number="云ADA0381",
                                    total_amount="10.00",
                                ),
                                "pdf/ETC001.pdf": fake_pdf("ETC001"),
                                "xml/ETC002.xml": etc_xml(
                                    "ETC002",
                                    issue_date="2026-01-20",
                                    plate_number="云A361SY",
                                    total_amount="20.00",
                                ),
                                "pdf/ETC002.pdf": fake_pdf("ETC002"),
                                "xml/ETC003.xml": etc_xml(
                                    "ETC003",
                                    issue_date="2026-01-21",
                                    plate_number="云ADA0381",
                                    total_amount="30.00",
                                ),
                                "pdf/ETC003.pdf": fake_pdf("ETC003"),
                            }
                        ),
                    )
                ]
            )

            batch = service.create_historical_submitted_batch(
                case_id="etc-historical-2026-01",
                external_batch_id="ETC-HIST-2026-01",
                invoice_numbers=["ETC001", "ETC002", "ETC003"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("59.00"),
                note="历史 OA 金额存在人工确认差额",
            )
            repeated = service.create_historical_submitted_batch(
                case_id="etc-historical-2026-01",
                external_batch_id="ETC-HIST-2026-01",
                invoice_numbers=["ETC001", "ETC002", "ETC003"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("59.00"),
                note="历史 OA 金额存在人工确认差额",
            )
            submitted_batches = service.list_batches(status="submitted")
            detail = service.get_batch_detail(batch.id)
            invoices, _total, counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(batch.id, repeated.id)
        self.assertEqual(len(submitted_batches), 1)
        self.assertEqual(batch.source_type, "historical_repair")
        self.assertEqual(batch.status, "submitted_confirmed")
        self.assertEqual(batch.linked_oa_row_id, "oa-exp-1994")
        self.assertEqual(batch.linked_oa_case_id, "etc-historical-2026-01")
        self.assertEqual(batch.amount_delta, Decimal("-1.00"))
        self.assertEqual(batch.issue_start_date, "2026-01-15")
        self.assertEqual(batch.issue_end_date, "2026-01-21")
        self.assertEqual(batch.passage_start_date, "2026-01-15")
        self.assertEqual(batch.passage_end_date, "2026-01-21")
        self.assertEqual(
            batch.plate_summary,
            [
                {"plate_number": "云ADA0381", "invoice_count": 2, "total_amount": Decimal("40.00")},
                {"plate_number": "云A361SY", "invoice_count": 1, "total_amount": Decimal("20.00")},
            ],
        )
        self.assertEqual(detail["summary"]["invoice_count"], 3)
        self.assertEqual(detail["summary"]["total_amount"], Decimal("60.00"))
        self.assertEqual(detail["plate_summary"], batch.plate_summary)
        self.assertEqual([item["invoice_number"] for item in detail["invoice_items"]], ["ETC001", "ETC002", "ETC003"])
        self.assertEqual(counts["submitted"], 3)
        self.assertEqual({invoice.current_batch_id for invoice in invoices}, {batch.id})
        self.assertEqual({invoice.last_batch_id for invoice in invoices}, {batch.id})

    def test_historical_batch_can_use_invoice_repaired_from_zip_import(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips([UploadedEtcZipFile("initial.zip", etc_zip(["ETC001"]))])

            with self.assertRaisesRegex(EtcInvoiceNotFoundError, "ETC002"):
                service.create_historical_submitted_batch(
                    case_id="etc-historical-2026-01",
                    external_batch_id="ETC-HIST-2026-01",
                    invoice_numbers=["ETC001", "ETC002"],
                    linked_oa_row_id="oa-exp-1994",
                    oa_amount=Decimal("30.00"),
                    note="缺失票补导入前不能落批次",
                )

            service.import_missing_invoices_from_zips(
                invoice_numbers=["ETC002"],
                uploads=[UploadedEtcZipFile("repair.zip", etc_zip(["ETC002"]))],
            )
            batch = service.create_historical_submitted_batch(
                case_id="etc-historical-2026-01",
                external_batch_id="ETC-HIST-2026-01",
                invoice_numbers=["ETC001", "ETC002"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("26.14"),
                note="缺失票补导入后进入历史批次",
            )

        self.assertEqual(batch.invoice_count, 2)
        self.assertEqual(batch.total_amount, Decimal("26.14"))

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

    def test_delete_import_batch_removes_unsubmitted_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])
            import_batch_id = service.list_import_batches()[0].id

            result = service.delete_batch(import_batch_id)
            invoices, total, counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(result, {"deleted": True, "batchId": import_batch_id, "kind": "import_batch"})
        self.assertEqual(service.list_import_batches(), [])
        self.assertEqual(invoices, [])
        self.assertEqual(total, 0)
        self.assertEqual(counts["unsubmitted"], 0)

    def test_delete_submission_batch_releases_import_batch_and_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])
            import_batch_id = service.list_import_batches()[0].id
            draft = service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])

            result = service.delete_batch(draft.batch_id)
            invoices, _total, counts = service.list_invoices(page=1, page_size=20)
            import_batch = service.list_import_batches()[0]

        self.assertEqual(result, {"deleted": True, "batchId": draft.batch_id, "kind": "submission_batch"})
        self.assertEqual(service.list_batches(), [])
        self.assertEqual(import_batch.id, import_batch_id)
        self.assertIsNone(import_batch.submission_batch_id)
        self.assertEqual({invoice.status for invoice in invoices}, {EtcInvoiceStatus.UNSUBMITTED})
        self.assertEqual({invoice.current_batch_id for invoice in invoices}, {None})
        self.assertEqual(counts["unsubmitted"], 2)

    def test_delete_submitted_batch_is_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])
            draft = service.create_oa_draft(["etc_invoice_0001"])
            service.confirm_submitted(draft.batch_id)

            with self.assertRaisesRegex(Exception, "submitted"):
                service.delete_batch(draft.batch_id)

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

    def _create_ready_reconciliation_task(
        self,
        app,
        *,
        amount: str = "13.07",
        invoice_count: int = 1,
        invoice_numbers: list[str] | None = None,
    ) -> str:
        task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
        if invoice_numbers is None:
            invoice_numbers = [f"ETC{i + 1:03d}" for i in range(invoice_count)]
        amounts = [
            f"{(Decimal(amount) + Decimal(index)).quantize(Decimal('0.01'))}"
            for index, _invoice_number in enumerate(invoice_numbers)
        ]
        statement_rows = "\n".join(
            f"2026-02-27 2026-02-28 3632 云南高速通行费 CNY {item_amount} {item_amount}"
            for item_amount in amounts
        )
        statement_text = f"""
中国建设银行信用卡账单
{statement_rows}
"""
        task = app._etc_reconciliation_task_service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id=f"{task.task_id}-CARD", text=statement_text),
            actor="alice",
        )
        for index, (_invoice_number, item_amount) in enumerate(zip(invoice_numbers, amounts, strict=False)):
            ticket_text = f"""
票根网通行明细
车牌号 云ADA0381
交易时间 2026-02-27 17:{28 + index:02d}:51
入口站 昆明南站
出口站 九龙池站
金额 {item_amount}
发票张数 1
"""
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=f"{task.task_id}-TICKET-{index}", text=ticket_text),
                actor="alice",
            )
        for card, ticket in zip(task.credit_card_items, task.ticket_root_items, strict=False):
            task = app._etc_reconciliation_task_service.patch_item(
                task_id=task.task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
            )
            task = app._etc_reconciliation_task_service.patch_item(
                task_id=task.task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
            )
        app._etc_reconciliation_task_service.confirm_task(
            task_id=task.task_id,
            expected_version=task.version,
            actor="alice",
        )
        return task.task_id

    def _preview_task_zip(self, app, invoice_numbers: list[str], *, amount: str = "13.07", nested: bool = True):
        task_id = self._create_ready_reconciliation_task(
            app,
            amount=amount,
            invoice_count=len(invoice_numbers),
            invoice_numbers=invoice_numbers,
        )
        amounts = [
            f"{(Decimal(amount) + Decimal(index)).quantize(Decimal('0.01'))}"
            for index, _invoice_number in enumerate(invoice_numbers)
        ]
        entries: dict[str, bytes] = {}
        for invoice_number, item_amount in zip(invoice_numbers, amounts, strict=False):
            entries[f"xml/{invoice_number}.xml"] = etc_xml(invoice_number, total_amount=item_amount)
            entries[f"pdf/{invoice_number}.pdf"] = fake_pdf(invoice_number)
        content = zip_bytes(entries)
        if nested:
            content = zip_bytes({"nested/invoices.zip": content})
        body, headers = multipart(
            {"outer.zip": content},
            fields={"task_id": task_id},
        )
        preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
        preview_payload = json.loads(preview_response.body)
        return task_id, preview_response, preview_payload

    def _create_ready_reconciliation_task_with_supplement(self, app) -> str:
        task = app._etc_reconciliation_task_service.create_task(title="2026-02 ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
账单周期 2026-02-01 至 2026-02-28
2026-02-25 2026-02-26 3632 云南高速通行费 CNY 13.07 13.07
2026-02-28 2026-03-01 3632 商旅补充凭证 CNY 88.00 88.00
"""
        task = app._etc_reconciliation_task_service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id=f"{task.task_id}-CARD", text=statement_text),
            actor="alice",
        )
        live_task = app._etc_reconciliation_task_service._tasks[task.task_id]
        live_task.statement_period_start = "2026-02-01"
        live_task.statement_period_end = "2026-02-28"
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-02-25 17:28:51
入口站 昆明南站
出口站 九龙池站
金额 13.07
发票张数 1
"""
        task = app._etc_reconciliation_task_service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=f"{task.task_id}-TICKET", text=ticket_text),
            actor="alice",
        )
        source_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
            original_name="supplement-ride.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nsupplement evidence\n",
            created_by="alice",
        )
        task = app._etc_reconciliation_task_service.apply_parse_result(
            task_id=task.task_id,
            parse_result=SupplementEvidenceParser().parse_text(
                file_id=source_file.file_id,
                source_name=source_file.original_name,
                text="商户 滴滴出行\n付款时间 2026年2月28日\n金额 88.00",
            ),
            actor="alice",
        )
        etc_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("13.07"))
        supplement_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("88.00"))
        ticket = task.ticket_root_items[0]
        supplement = task.supplement_evidences[0]
        task = app._etc_reconciliation_task_service.patch_item(
            task_id=task.task_id,
            item_id=etc_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = app._etc_reconciliation_task_service.patch_item(
            task_id=task.task_id,
            item_id=etc_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        task = app._etc_reconciliation_task_service.patch_item(
            task_id=task.task_id,
            item_id=supplement_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_supplement", "supplementEvidenceId": supplement.evidence_id, "note": "补充非ETC凭证"},
        )
        task = app._etc_reconciliation_task_service.confirm_task(
            task_id=task.task_id,
            expected_version=task.version,
            actor="alice",
        )
        self.assertEqual(task.oa_total_amount, Decimal("101.07"))
        self.assertEqual(task.etc_invoice_count, 1)
        self.assertEqual(task.supplement_count, 1)
        return task.task_id

    def _import_supplement_reconciliation_zip_and_create_draft(self, app) -> tuple[str, dict[str, object]]:
        task_id = self._create_ready_reconciliation_task_with_supplement(app)
        body, headers = multipart(
            {
                "etc.zip": zip_bytes(
                    {
                        "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-02-25", total_amount="13.07"),
                        "pdf/ETC001.pdf": fake_pdf("ETC001"),
                    }
                )
            },
            fields={"task_id": task_id},
        )
        preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
        preview_payload = json.loads(preview_response.body)
        confirm_response = app.handle_request(
            "POST",
            "/api/etc/import/confirm",
            json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
        )
        self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
        draft_response = app.handle_request(
            "POST",
            "/api/etc/batches/draft",
            json.dumps({"invoiceIds": ["etc_invoice_0001"]}),
        )
        return task_id, json.loads(draft_response.body)

    def test_reconciliation_task_routes_create_list_ready_and_get_without_route_swallowing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            create_response = app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "2026-02 ETC", "createdBy": "alice"}),
            )
            created = json.loads(create_response.body)
            list_response = app.handle_request("GET", "/api/etc/reconciliation-tasks")
            detail_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{created['taskId']}")
            ready_response = app.handle_request("GET", "/api/etc/reconciliation-tasks/ready-for-import")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(created["status"], "draft")
        self.assertEqual(json.loads(list_response.body)["tasks"][0]["taskId"], created["taskId"])
        self.assertEqual(json.loads(detail_response.body)["taskId"], created["taskId"])
        self.assertEqual(ready_response.status_code, 200)
        self.assertEqual(json.loads(ready_response.body)["tasks"], [])

    def test_created_reconciliation_task_payload_is_fresh_and_includes_source_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "fresh", "createdBy": "alice"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(payload["status"], "draft")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["sourceFiles"], [])
        self.assertEqual(payload["parseIssues"], [])
        self.assertEqual(payload["creditCardItems"], [])
        self.assertEqual(payload["ticketRootItems"], [])
        self.assertEqual(payload["supplementEvidences"], [])
        self.assertEqual(payload["vehiclePlates"], [])
        self.assertEqual([event["event_type"] for event in payload["auditEvents"]], ["task_created"])

    def test_reconciliation_task_payload_includes_source_file_context_for_parse_issues(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            good_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket-good.pdf",
                content_type="application/pdf",
                content=b"good ticket",
                created_by="alice",
            )
            bad_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket-bad.pdf",
                content_type="application/pdf",
                content=b"bad ticket",
                created_by="alice",
            )
            app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=good_file.file_id, text=TICKET_ROOT_TEXT),
                actor="alice",
            )
            app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=bad_file.file_id, text=TICKET_ROOT_TEXT_WITHOUT_PLATE),
                actor="alice",
            )

            response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task.task_id}")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual({source["fileId"]: source["originalName"] for source in payload["sourceFiles"]}, {
            good_file.file_id: "ticket-good.pdf",
            bad_file.file_id: "ticket-bad.pdf",
        })
        self.assertEqual(
            {source["fileId"]: source["hasBlockingIssue"] for source in payload["sourceFiles"]},
            {
                good_file.file_id: False,
                bad_file.file_id: True,
            },
        )
        self.assertEqual(len(payload["ticketRootItems"]), 1)
        self.assertEqual(len(payload["parseIssues"]), 1)
        issue = payload["parseIssues"][0]
        self.assertEqual(issue["fileId"], bad_file.file_id)
        self.assertEqual(issue["sourceKind"], "ticket_root")
        self.assertEqual(issue["originalName"], "ticket-bad.pdf")
        self.assertEqual(issue["sourcePage"], 1)
        self.assertEqual(issue["sourceLine"], None)
        self.assertEqual(issue["extractionMethod"], "pdf_text")
        self.assertEqual(issue["fieldName"], "vehicle_plate")

    def test_reconciliation_task_payload_is_not_confirmable_with_stale_included_etc_resolution(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-1", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            live_task = app._etc_reconciliation_task_service._tasks[task.task_id]
            first_candidate_seen = False
            for item in live_task.credit_card_items:
                if item.is_etc_candidate and not first_candidate_seen:
                    item.manual_resolution = "included_etc"
                    first_candidate_seen = True
                elif item.is_etc_candidate:
                    item.manual_resolution = "excluded_non_etc"
                    item.manual_resolution_reason = "非本次"
                    item.review_note = "非本次"

            payload = app._etc_reconciliation_task_payload(live_task)

        self.assertFalse(payload["canConfirm"])

    def test_delete_reconciliation_source_file_route_removes_file_parse_result_and_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            good_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket-good.pdf",
                content_type="application/pdf",
                content=b"good ticket",
                created_by="alice",
            )
            bad_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket-bad.pdf",
                content_type="application/pdf",
                content=b"bad ticket",
                created_by="alice",
            )
            app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=good_file.file_id, text=TICKET_ROOT_TEXT),
                actor="alice",
            )
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=bad_file.file_id, text=TICKET_ROOT_TEXT_WITHOUT_PLATE),
                actor="alice",
            )

            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task.task_id}/source-files/{bad_file.file_id}",
                json.dumps({"expectedVersion": task.version, "actor": "alice"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([source["fileId"] for source in payload["sourceFiles"]], [good_file.file_id])
        self.assertEqual(len(payload["ticketRootItems"]), 1)
        self.assertEqual(payload["parseIssues"], [])
        self.assertFalse(Path(bad_file.stored_path).exists())

    def test_delete_reconciliation_source_file_route_requires_version_and_mutable_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            source_file = app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket.pdf",
                content_type="application/pdf",
                content=b"ticket",
                created_by="alice",
            )
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=source_file.file_id, text=TICKET_ROOT_TEXT),
                actor="alice",
            )

            conflict = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task.task_id}/source-files/{source_file.file_id}",
                json.dumps({"expectedVersion": task.version - 1}),
            )
            missing = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task.task_id}/source-files/missing-file",
                json.dumps({"expectedVersion": task.version}),
            )

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(json.loads(conflict.body)["error"], "task_version_conflict")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(json.loads(missing.body)["error"], "unknown_source_file")

    def test_ticket_root_text_route_creates_source_file_parse_result_and_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)

            response = app.handle_request(
                "POST",
                f"/fin-ops-api/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-texts",
                json.dumps(
                    {
                        "expectedVersion": created["version"],
                        "entries": [{"clientId": "paste-1", "text": TICKET_ROOT_CLIPBOARD_TEXT}],
                    },
                    ensure_ascii=False,
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["sourceFiles"][0]["sourceKind"], "ticket_root")
        self.assertEqual(payload["sourceFiles"][0]["contentType"], "text/plain; charset=utf-8")
        self.assertIn("票根网手工粘贴-云ADA0381-202604", payload["sourceFiles"][0]["originalName"])
        self.assertEqual(len(payload["ticketRootItems"]), 1)
        self.assertEqual(payload["ticketRootItems"][0]["vehicle_plate"], "云ADA0381")
        self.assertEqual(payload["ticketRootItems"][0]["amount"], "71.25")
        self.assertEqual(payload["ticketRootItems"][0]["entry_station"], "云南弥勒南站")
        self.assertEqual(payload["ticketRootItems"][0]["exit_station"], "云南小喜村站")
        self.assertEqual(payload["parseIssues"], [])

    def test_ticket_root_text_route_rejects_existing_pdf_ticket_root_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4\n%%EOF",
                created_by="alice",
            )
            task = app._etc_reconciliation_task_service.get_task(task.task_id)

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/ticket-root-texts",
                json.dumps({"expectedVersion": task.version, "entries": [{"clientId": "paste-1", "text": TICKET_ROOT_CLIPBOARD_TEXT}]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "ticket_root_source_mode_conflict")
        self.assertIn("已有票根网 PDF/JPG 源文件", payload["message"])

    def test_ticket_root_upload_route_rejects_existing_clipboard_text_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="票根网手工粘贴-云ADA0381-202604-1.txt",
                content_type="text/plain; charset=utf-8",
                content=TICKET_ROOT_CLIPBOARD_TEXT.encode("utf-8"),
                created_by="alice",
            )
            task = app._etc_reconciliation_task_service.get_task(task.task_id)
            body, headers = multipart(
                {"ticket.pdf": b"%PDF-1.4\n%%EOF\n"},
                fields={"expectedVersion": str(task.version)},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/ticket-root-files",
                body=body,
                headers=headers,
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "ticket_root_source_mode_conflict")
        self.assertIn("已有手工粘贴票根网源", payload["message"])

    def test_credit_card_statement_uploaded_to_ticket_root_route_returns_wrong_slot_message(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC"}),
            ).body)
            body, headers = multipart(
                {"statement.txt": b"Longka Credit Card Statement\nStatement Date 2026-03-31\nPayment Due Date 2026-04-20\n"},
                fields={"expectedVersion": str(created["version"])},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-files",
                body=body,
                headers=headers,
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "wrong_reconciliation_source_kind")
        self.assertEqual(payload["message"], "检测到信用卡账单，请上传到信用卡账单栏。")
        self.assertNotIn("缺少车牌号", payload["message"])

    def test_chinese_ccb_statement_uploaded_to_ticket_root_route_returns_wrong_slot_message(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC"}),
            ).body)
            body, headers = multipart(
                {"statement.txt": "中国建设银行信用卡账单\n2026-03-28 高速通行费 CNY 21.52\n".encode("utf-8")},
                fields={"expectedVersion": str(created["version"])},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-files",
                body=body,
                headers=headers,
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "wrong_reconciliation_source_kind")
        self.assertEqual(payload["message"], "检测到信用卡账单，请上传到信用卡账单栏。")
        self.assertNotIn("缺少车牌号", payload["message"])

    def test_credit_card_pdf_uploaded_to_ticket_root_route_uses_extracted_text_for_wrong_slot_detection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC"}),
            ).body)
            body, headers = multipart(
                {"statement.pdf": b"%PDF-1.4\n%%EOF\n"},
                fields={"expectedVersion": str(created["version"])},
            )

            with patch(
                "fin_ops_platform.services.etc_document_parsers._extract_pdf_text",
                return_value="Credit Card Statement\nStatement Date 2026-03-31\nPayment Due Date 2026-04-20\n",
            ):
                response = app.handle_request(
                    "POST",
                    f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-files",
                    body=body,
                    headers=headers,
                )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["message"], "检测到信用卡账单，请上传到信用卡账单栏。")

    def test_delete_reconciliation_task_route_requires_mutable_status_and_version(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                body=json.dumps({"title": "待删除"}),
            ).body)

            conflict = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{created['taskId']}",
                body=json.dumps({"expectedVersion": created["version"] + 1}),
            )
            deleted = app.handle_request(
                "DELETE",
                f"/fin-ops-api/api/etc/reconciliation-tasks/{created['taskId']}",
                body=json.dumps({"expectedVersion": created["version"]}),
            )
            missing = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{created['taskId']}")

        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(json.loads(conflict.body)["error"], "task_version_conflict")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(json.loads(deleted.body), {"deleted": True, "taskId": created["taskId"], "kind": "reconciliation_task"})
        self.assertEqual(missing.status_code, 404)

    def test_delete_etc_batch_route_deletes_unsubmitted_and_rejects_submitted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_zips([UploadedEtcZipFile("unsubmitted.zip", etc_zip(["ETC001"]))])
            batches_payload = json.loads(app.handle_request("GET", "/api/etc/batches?status=unsubmitted").body)
            batch_id = batches_payload["items"][0]["id"]

            delete_response = app.handle_request("DELETE", f"/fin-ops-api/api/etc/batches/{batch_id}")
            unsubmitted_after_delete = json.loads(app.handle_request("GET", "/api/etc/batches?status=unsubmitted").body)

            app._etc_service.import_zips([UploadedEtcZipFile("submitted.zip", etc_zip(["ETC002"]))])
            draft = app._etc_service.create_oa_draft(["etc_invoice_0002"], oa_client=FakeEtcOAClient())
            app._etc_service.confirm_submitted(draft.batch_id)
            submitted_delete = app.handle_request("DELETE", f"/api/etc/batches/{draft.batch_id}")

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body), {"deleted": True, "batchId": batch_id, "kind": "import_batch"})
        self.assertEqual(unsubmitted_after_delete["items"], [])
        self.assertEqual(submitted_delete.status_code, 409)
        self.assertEqual(json.loads(submitted_delete.body)["error"], "etc_batch_delete_conflict")

    def test_reconciliation_item_patch_conflict_returns_task_version_conflict(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(app)
            task = app._etc_reconciliation_task_service.reopen_task(
                task_id=task_id,
                expected_version=app._etc_reconciliation_task_service.get_task(task_id).version,
                actor="alice",
            )
            card_id = task.credit_card_items[0].item_id

            response = app.handle_request(
                "PATCH",
                f"/api/etc/reconciliation-tasks/{task_id}/items/{card_id}",
                json.dumps({"expectedVersion": task.version - 1, "action": "manual_confirm", "note": "人工确认"}),
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(json.loads(response.body)["error"], "task_version_conflict")

    def test_reconciliation_mutations_require_expected_version_and_reject_ready_patch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(app)
            task = app._etc_reconciliation_task_service.get_task(task_id)
            card_id = task.credit_card_items[0].item_id
            body, headers = multipart({"statement.pdf": b"%PDF-1.4\n"})

            missing_version_patch = app.handle_request(
                "PATCH",
                f"/api/etc/reconciliation-tasks/{task_id}/items/{card_id}",
                json.dumps({"action": "manual_confirm", "note": "人工确认"}),
            )
            missing_version_upload = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task_id}/credit-card-statement",
                body=body,
                headers=headers,
            )
            ready_patch = app.handle_request(
                "PATCH",
                f"/api/etc/reconciliation-tasks/{task_id}/items/{card_id}",
                json.dumps({"expectedVersion": task.version, "action": "manual_confirm", "note": "人工确认"}),
            )
            ready_upload = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task_id}/credit-card-statement",
                body=multipart({"statement.pdf": b"%PDF-1.4\n"}, fields={"expectedVersion": str(task.version)})[0],
                headers=multipart({"statement.pdf": b"%PDF-1.4\n"}, fields={"expectedVersion": str(task.version)})[1],
            )

        self.assertEqual(missing_version_patch.status_code, 400)
        self.assertEqual(json.loads(missing_version_patch.body)["error"], "expected_version_required")
        self.assertEqual(missing_version_upload.status_code, 400)
        self.assertEqual(json.loads(missing_version_upload.body)["error"], "expected_version_required")
        self.assertEqual(ready_patch.status_code, 400)
        self.assertEqual(json.loads(ready_patch.body)["error"], "reconciliation_task_not_mutable")
        self.assertEqual(ready_upload.status_code, 400)
        self.assertEqual(json.loads(ready_upload.body)["error"], "reconciliation_task_not_mutable")

    def test_task_aware_etc_import_requires_task_filters_extra_and_marks_imported(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(app)
            missing_task_body, missing_task_headers = multipart({"etc.zip": etc_zip(["ETC001"])})
            body, headers = multipart(
                {
                    "etc.zip": zip_bytes(
                        {
                            "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-02-27", total_amount="13.07"),
                            "pdf/ETC001.pdf": fake_pdf("ETC001"),
                            "xml/EXTRA.xml": etc_xml("EXTRA", issue_date="2026-02-27", total_amount="999.99"),
                            "pdf/EXTRA.pdf": fake_pdf("EXTRA"),
                        }
                    )
                },
                fields={"task_id": task_id},
            )

            missing_task_response = app.handle_request(
                "POST",
                "/api/etc/import/preview",
                body=missing_task_body,
                headers=missing_task_headers,
            )
            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            retry_confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            completed_job = self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            ready = json.loads(app.handle_request("GET", "/api/etc/reconciliation-tasks/ready-for-import").body)
            task = app._etc_reconciliation_task_service.get_task(task_id)

        self.assertEqual(missing_task_response.status_code, 400)
        self.assertEqual(json.loads(missing_task_response.body)["error"], "task_id_required")
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(
            {item["invoiceNumber"]: item["filterStatus"] for item in preview_payload["reconciliationFilter"]["items"]},
            {"ETC001": "included", "EXTRA": "excluded_extra_zip_invoice"},
        )
        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(retry_confirm_response.status_code, 202)
        self.assertEqual(
            json.loads(retry_confirm_response.body)["job"]["job_id"],
            json.loads(confirm_response.body)["job"]["job_id"],
        )
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(invoices["total"], 1)
        self.assertEqual(invoices["items"][0]["invoice_number"], "ETC001")
        self.assertEqual(task.status.value, "imported")
        self.assertEqual(ready["tasks"], [])

    def test_etc_import_preview_requires_ready_task_even_when_no_tasks_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            body, headers = multipart({"invoices.zip": etc_zip(["ETC001"])})

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": "missing-session"}),
            )
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(preview_response.status_code, 400)
        self.assertEqual(json.loads(preview_response.body)["error"], "task_id_required")
        self.assertEqual(confirm_response.status_code, 400)
        self.assertEqual(json.loads(confirm_response.body)["error"], "task_id_required")
        self.assertEqual(json.loads(query_response.body)["total"], 0)

    def test_task_aware_etc_import_preview_ignores_corrupt_zip_during_allowlist_filtering(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(app)
            body, headers = multipart(
                {
                    "valid.zip": etc_zip(["ETC001"]),
                    "bad.zip": b"not a zip",
                },
                fields={"task_id": task_id},
            )

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["summary"]["imported"], 1)
        self.assertEqual(
            {item["invoiceNumber"]: item["filterStatus"] for item in preview_payload["reconciliationFilter"]["items"]},
            {"ETC001": "included"},
        )

    def test_task_aware_etc_import_empty_allowlist_does_not_import_original_zip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            statement_text = """
中国建设银行信用卡账单
2026-02-27 2026-02-28 3632 云南高速通行费 CNY 13.07 13.07
"""
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id=f"{task.task_id}-CARD", text=statement_text),
                actor="alice",
            )
            card = task.credit_card_items[0]
            task = app._etc_reconciliation_task_service.patch_item(
                task_id=task.task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "manual_confirm", "note": "人工确认无需ETC票"},
            )
            task = app._etc_reconciliation_task_service.confirm_task(
                task_id=task.task_id,
                expected_version=task.version,
                actor="alice",
                approved_delta="13.07",
                approved_delta_note="人工确认无需ETC票",
            )
            body, headers = multipart(
                {"etc.zip": etc_zip(["EXTRA"])},
                fields={"task_id": task.task_id},
            )

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task.task_id}),
            )
            completed_job = self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["summary"]["imported"], 0)
        self.assertEqual(
            {item["invoiceNumber"]: item["filterStatus"] for item in preview_payload["reconciliationFilter"]["items"]},
            {"EXTRA": "excluded_extra_zip_invoice"},
        )
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(invoices["total"], 0)

    def test_etc_confirm_returns_background_job_and_imports_asynchronously(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            before_confirm_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
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
            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
            session_id = preview_payload["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            invoices = app._import_service.list_invoices()

        self.assertEqual(len(invoices), 2)
        self.assertCountEqual([invoice.digital_invoice_no for invoice in invoices], ["ETC001", "ETC002"])
        self.assertEqual({invoice.source_unique_key for invoice in invoices}, {"ETC001", "ETC002"})

    def test_etc_import_confirm_returns_preview_stale_when_canonical_invoice_changes_after_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
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
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
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

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001"])
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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
                            "amount": "27.14",
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
        self.assertEqual(payload["summary"]["invoice_count"], 0)
        self.assertEqual(
            payload["invoice_inventory"],
            {
                "system_total": 2,
                "manual_import_total": 1,
                "workbench_visible_total": 0,
                "hidden_submitted_etc_total": 1,
                "extra_etc_total": 1,
                "etc_summary_batch_count": 1,
                "oa_attachment_total": 0,
            },
        )
        summary_row = invoice_rows[0]
        self.assertEqual(summary_row["source_kind"], "etc_invoice_summary")
        self.assertEqual(summary_row["seller_name"], "ETC发票 2 张")
        self.assertEqual(summary_row["etc_invoice_count"], 2)
        self.assertEqual(summary_row["total_with_tax"], "27.14")
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

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001"], nested=False)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001"])
            session_id = json.loads(preview_response.body)["sessionId"]
            first_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
            first_job = json.loads(first_response.body)["job"]
            second_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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
            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            preview_payload = json.loads(preview_response.body)
            session_id = preview_payload["sessionId"]
            original_upsert = app._etc_service._upsert_invoice_from_import

            def fail_second_required_invoice(zip_source_name, parsed, xml_entry, pdf_entry, *, import_batch):
                if parsed.invoice_number == "ETC002":
                    raise RuntimeError("synthetic persist failure")
                return original_upsert(
                    zip_source_name,
                    parsed,
                    xml_entry,
                    pdf_entry,
                    import_batch=import_batch,
                )

            app._etc_service._upsert_invoice_from_import = fail_second_required_invoice

            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
            job = json.loads(confirm_response.body)["job"]
            completed_job = self._wait_for_job(app, job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")
            task_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")

        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(preview_payload["audit"]["original_count"], 2)
        self.assertEqual(preview_payload["audit"]["importable_count"], 2)
        self.assertEqual(preview_payload["audit"]["error_count"], 0)
        self.assertEqual(preview_payload["audit"]["skipped_count"], 0)
        self.assertEqual(job["total"], 2)
        self.assertEqual(completed_job["status"], "partial_success")
        self.assertEqual(completed_job["current"], 2)
        self.assertEqual(completed_job["result_summary"]["created"], 1)
        self.assertEqual(completed_job["result_summary"]["failed"], 1)
        self.assertEqual(completed_job["result_summary"]["total"], 2)
        self.assertEqual(json.loads(query_response.body)["total"], 1)
        self.assertEqual(json.loads(task_response.body)["status"], "ready_for_import")

    def test_import_query_revoke_and_batch_api_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            preview_payload = json.loads(preview_response.body)
            before_confirm_response = app.handle_request("GET", "/api/etc/invoices?status=unsubmitted&month=2026-02&page=1&page_size=1")
            import_confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
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

    def test_reconciliation_backed_submitted_batch_detail_includes_supplement_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            _task_id, draft_payload = self._import_supplement_reconciliation_zip_and_create_draft(app)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            list_response = app.handle_request("GET", "/api/etc/batches?status=submitted&month=2026-02")
            detail_response = app.handle_request("GET", f"/api/etc/batches/{draft_payload['batchId']}")

        self.assertEqual(list_response.status_code, 200)
        list_payload = json.loads(list_response.body)
        summary = list_payload["items"][0]
        self.assertEqual(summary["oaTotalAmount"], "101.07")
        self.assertEqual(summary["etcInvoiceAmount"], "13.07")
        self.assertEqual(summary["supplementAmount"], "88.00")
        self.assertEqual(summary["etcInvoiceCount"], 1)
        self.assertEqual(summary["supplementCount"], 1)
        self.assertEqual(summary["displayCountText"], "ETC票 1 + 补充凭证 1")
        self.assertEqual(summary["passage_start_date"], "2026-02-25")
        self.assertEqual(summary["passage_end_date"], "2026-02-28")
        self.assertEqual(summary["statementPeriodStart"], "2026-02-01")
        self.assertEqual(summary["statementPeriodEnd"], "2026-02-28")

        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["summary"]["displayCountText"], "ETC票 1 + 补充凭证 1")
        self.assertEqual(detail_payload["supplementItems"][0]["tags"], ["ETC补充凭证"])
        self.assertEqual(detail_payload["supplementItems"][0]["amount"], "88.00")
        self.assertEqual(len(detail_payload["invoiceItems"]), 1)

    def test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            fake_oa = FakeEtcOAClient()
            app._etc_service.oa_client = fake_oa

            _task_id, draft_payload = self._import_supplement_reconciliation_zip_and_create_draft(app)

        self.assertEqual(draft_payload["oaDraftId"], "oa-draft-001")
        self.assertEqual(len(fake_oa.uploads), 2)
        self.assertEqual(Path(fake_oa.uploads[1]).name, "ETC-RECON-FILE-000001_supplement-ride.pdf")
        payload = fake_oa.draft_payloads[0]["payload"]
        self.assertEqual(payload["data"]["amount"], "101.07")
        uploaded_names = [item["name"] for item in payload["data"]["field101"]["list"]]
        self.assertEqual(uploaded_names, ["ETC001.pdf", "supplement-ride.pdf"])

    def test_missing_durable_supplement_file_blocks_reconciliation_oa_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id = self._create_ready_reconciliation_task_with_supplement(app)
            task = app._etc_reconciliation_task_service.get_task(task_id)
            Path(task.submission_supplement_attachments[0].stored_path).unlink()
            body, headers = multipart(
                {"etc.zip": zip_bytes({"xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-02-25"), "pdf/ETC001.pdf": fake_pdf("ETC001")})},
                fields={"task_id": task_id},
            )
            preview_payload = json.loads(app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers).body)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            draft_response = app.handle_request("POST", "/api/etc/batches/draft", json.dumps({"invoiceIds": ["etc_invoice_0001"]}))

        self.assertEqual(draft_response.status_code, 400)
        payload = json.loads(draft_response.body)
        self.assertEqual(payload["error"], "invalid_etc_draft_request")
        self.assertIn("supplement", payload["message"].lower())

    def test_reconciliation_supplement_enters_workbench_with_required_tag(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            _task_id, draft_payload = self._import_supplement_reconciliation_zip_and_create_draft(app)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            workbench_response = app.handle_request("GET", "/api/workbench?month=2026-02")

        self.assertEqual(workbench_response.status_code, 200)
        payload = json.loads(workbench_response.body)
        invoice_rows = [
            row
            for section in ("paired", "open")
            for group in payload.get(section, {}).get("groups", [])
            for row in group.get("invoice_rows", [])
        ]
        supplement_rows = [row for row in invoice_rows if "ETC补充凭证" in row.get("tags", [])]
        self.assertEqual(len(supplement_rows), 1)
        self.assertEqual(supplement_rows[0]["source_kind"], "etc_supplement_evidence")
        self.assertEqual(supplement_rows[0]["etc_invoice_count"], 0)

    def test_confirming_reconciliation_backed_oa_submission_finalizes_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, draft_payload = self._import_supplement_reconciliation_zip_and_create_draft(app)
            confirm_response = app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/confirm-submitted")
            ready_response = app.handle_request("GET", "/api/etc/reconciliation-tasks/ready-for-import")
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(json.loads(confirm_response.body)["batch"]["status"], "submitted_confirmed")
        self.assertEqual(task_payload["status"], "closed")
        self.assertIsNotNone(task_payload["submittedConfirmedAt"])
        self.assertIn("oa_draft_created", [event["event_type"] for event in task_payload["auditEvents"]])
        self.assertIn("oa_submitted_confirmed", [event["event_type"] for event in task_payload["auditEvents"]])
        self.assertEqual(json.loads(ready_response.body)["tasks"], [])

    def test_etc_batch_query_api_returns_counts_summary_plate_summary_and_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_zips(
                [
                    UploadedEtcZipFile(
                        "historical.zip",
                        zip_bytes(
                            {
                                "xml/ETC001.xml": etc_xml(
                                    "ETC001",
                                    issue_date="2026-01-15",
                                    plate_number="云ADA0381",
                                    total_amount="10.00",
                                ),
                                "pdf/ETC001.pdf": fake_pdf("ETC001"),
                                "xml/ETC002.xml": etc_xml(
                                    "ETC002",
                                    issue_date="2026-01-20",
                                    plate_number="云A361SY",
                                    total_amount="20.00",
                                ),
                                "pdf/ETC002.pdf": fake_pdf("ETC002"),
                            }
                        ),
                    )
                ]
            )
            batch = app._etc_service.create_historical_submitted_batch(
                case_id="etc-historical-2026-01",
                external_batch_id="ETC-HIST-2026-01",
                invoice_numbers=["ETC001", "ETC002"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("31.00"),
                note="历史补关联",
            )

            list_response = app.handle_request("GET", "/api/etc/batches?status=submitted&month=2026-01&plate=ADA")
            detail_response = app.handle_request("GET", f"/api/etc/batches/{batch.id}")

        self.assertEqual(list_response.status_code, 200)
        list_payload = json.loads(list_response.body)
        self.assertEqual(list_payload["counts"]["submitted"], 1)
        self.assertEqual(list_payload["counts"]["current"], 1)
        self.assertEqual(list_payload["items"][0]["id"], batch.id)
        self.assertEqual(list_payload["items"][0]["etc_batch_id"], "ETC-HIST-2026-01")
        self.assertEqual(list_payload["items"][0]["invoice_count"], 2)
        self.assertEqual(list_payload["selectedBatch"]["summary"]["amount_delta"], "1.00")
        self.assertEqual(list_payload["plateSummary"][0]["plate_number"], "云ADA0381")
        self.assertEqual([item["invoice_number"] for item in list_payload["invoiceItems"]], ["ETC001", "ETC002"])

        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["batch"]["source_type"], "historical_repair")
        self.assertEqual(detail_payload["summary"]["linked_oa_row_id"], "oa-exp-1994")
        self.assertEqual(detail_payload["plateSummary"][1]["plate_number"], "云A361SY")
        self.assertEqual(detail_payload["invoiceItems"][0]["has_pdf"], True)

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

    def test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            spec = HistoricalEtcRepairBatchSpec(
                label="测试历史批次",
                bundle_id="ETC-HIST-TEST",
                case_id="etc-historical-test",
                external_batch_id="ETC-HIST-TEST",
                oa_row_id="oa-exp-test",
                oa_amount=Decimal("30.00"),
            )
            service = HistoricalEtcRepairService(
                state_store=app._state_store,
                etc_service=app._etc_service,
                pair_relation_service=app._workbench_pair_relation_service,
                specs=[spec],
                oa_row_exists=lambda row_id: row_id == "oa-exp-test",
                sync_import_result_to_canonical_invoices=app._sync_etc_import_result_to_canonical_invoices,
                sync_etc_invoices_to_canonical_invoices=app._sync_etc_invoices_to_canonical_invoices,
                refresh_after_etc_invoice_sync=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )
            service.seed_bundle_from_upload(
                spec,
                UploadedEtcZipFile("historical-test.zip", etc_zip(["ETC001", "ETC002"])),
            )
            parsed_seed = app._state_store.load_historical_etc_repair_parsed_seed("ETC-HIST-TEST")
            self.assertIsNotNone(parsed_seed)
            assert parsed_seed is not None
            self.assertEqual(parsed_seed["invoice_count"], 2)
            self.assertEqual(parsed_seed["totals"]["invoice_count"], 2)
            self.assertEqual(len(parsed_seed["selected_invoice_records"]), 2)

            with patch.object(
                app._state_store,
                "read_historical_etc_repair_bundle",
                side_effect=AssertionError("parsed seed should restore missing invoices without reading audit zip"),
            ):
                first_result = service.reconcile(reason="test")
            service._sync_etc_invoices_to_canonical_invoices = (  # noqa: SLF001 - verifies parsed-seed fast path.
                lambda _invoices: (_ for _ in ()).throw(
                    AssertionError("existing historical repair should not resync canonical invoices")
                )
            )
            with patch.object(
                app._state_store,
                "read_historical_etc_repair_bundle",
                side_effect=AssertionError("parsed seed should avoid reading audit zip"),
            ):
                second_result = service.reconcile(reason="test-repeat")
            persisted_state = app._state_store.load_historical_etc_repair_states()

        self.assertEqual(first_result.status, "ok")
        self.assertEqual(first_result.batches[0].imported_count, 2)
        self.assertEqual(second_result.status, "ok")
        self.assertEqual(len(app._etc_service.list_batches(status="submitted")), 1)
        self.assertEqual(len(app._import_service.list_invoices()), 2)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("etc-historical-test")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "etc_batch_invoice_link")
        self.assertEqual(persisted_state["ETC-HIST-TEST"]["status"], "ok")

    def test_etc_draft_returns_clear_error_when_oa_token_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001"], nested=False)
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
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
