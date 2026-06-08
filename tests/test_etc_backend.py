from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
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
    EtcBusinessBatchActiveExistsError,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchStatus,
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
from fin_ops_platform.services.etc_reconciliation_models import FileParseResult, SourceFileKind
from fin_ops_platform.services.historical_etc_repair_service import (
    HistoricalEtcRepairBatchSpec,
    HistoricalEtcRepairService,
)
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.existing_etc_batch_link_service import (
    ExistingEtcBatchLinkService,
    ExistingEtcBatchLinkSpec,
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

REAL_TICKET_ROOT_TXT_A516HJ_PATH = Path("/Users/yu/Desktop/sy/财务运营平台/票根网/4月/云A516HJ/云A516HJ")


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
        self.files: dict[str, bytes] = {}

    def load_etc_state(self) -> dict[str, object]:
        return dict(self.saved_snapshot or {})

    def save_etc_state(self, snapshot: dict[str, object]) -> None:
        self.saved_snapshot = dict(snapshot)

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str:
        ref = f"memory://etc_invoice/{invoice_number}/{file_name}"
        self.files[ref] = bytes(content)
        return ref

    def read_etc_invoice_file(self, stored_file_path: str) -> bytes:
        return self.files[stored_file_path]

    def etc_invoice_file_exists(self, stored_file_path: str) -> bool:
        return stored_file_path in self.files

    def delete_etc_invoice_file(self, stored_file_path: str) -> None:
        self.files.pop(stored_file_path, None)


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
    def test_business_batch_create_list_detail_and_active_guard(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            batch = service.create_business_batch(task_id="ETC-TASK-001", owner_user_id="alice", owner_org_id="finance")

            self.assertEqual(batch.business_batch_id, "etc_business_batch_0001")
            self.assertEqual(batch.task_id, "ETC-TASK-001")
            self.assertEqual(batch.status, EtcBusinessBatchStatus.DRAFT.value)
            self.assertEqual(batch.version, 1)
            self.assertTrue(batch.is_active)
            self.assertEqual(batch.task_active_key, "ETC-TASK-001:active")
            self.assertEqual(batch.owner_user_id, "alice")
            self.assertEqual(batch.owner_org_id, "finance")
            self.assertEqual(service.get_business_batch(batch.business_batch_id).business_batch_id, batch.business_batch_id)
            self.assertEqual([item.business_batch_id for item in service.list_business_batches()], [batch.business_batch_id])
            with self.assertRaises(EtcBusinessBatchActiveExistsError):
                service.create_business_batch(task_id="ETC-TASK-001")

    def test_business_batch_supplement_merge_rejects_after_draft_and_allows_after_revoke(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")

            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("first.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("supplement.zip", etc_zip(["ETC002"]))],
                expected_version=batch.version,
            )
            batch, result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )

            self.assertEqual(result.imported, 1)
            self.assertEqual(batch.status, EtcBusinessBatchStatus.IMPORTED.value)
            self.assertEqual(batch.import_batch_ids, ["etc_import_batch_0001", "etc_import_batch_0002"])
            self.assertEqual(batch.invoice_ids, ["etc_invoice_0001", "etc_invoice_0002"])

            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)
            with self.assertRaises(EtcBusinessBatchInvalidTransitionError):
                service.preview_business_batch_import_zips(
                    batch.business_batch_id,
                    [UploadedEtcZipFile("late.zip", etc_zip(["ETC003"]))],
                    expected_version=drafted.version,
                )

            revoked = service.revoke_business_batch_oa_draft(
                batch.business_batch_id,
                reason="补充漏导发票",
                expected_version=drafted.version,
            )
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("late.zip", etc_zip(["ETC003"]))],
                expected_version=revoked.version,
            )
            batch, result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )

            self.assertEqual(result.imported, 1)
            self.assertEqual(batch.status, EtcBusinessBatchStatus.IMPORTED.value)
            self.assertEqual(batch.invoice_ids, ["etc_invoice_0001", "etc_invoice_0002", "etc_invoice_0003"])

    def test_business_batch_oa_draft_is_idempotent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )

            first = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)
            second = service.create_business_batch_oa_draft(first.business_batch_id, expected_version=first.version)

            self.assertEqual(first.submission_batch_id, second.submission_batch_id)
            self.assertEqual(first.oa_draft_id, "oa-draft-001")
            self.assertEqual(second.status, EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value)
            self.assertEqual(len(fake_oa.draft_payloads), 1)
            cause = str(fake_oa.draft_payloads[0]["payload"]["data"]["cause"])
            self.assertIn(f"business_batch_id={batch.business_batch_id}", cause)

    def test_business_batch_revoke_is_idempotent_and_releases_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)

            first = service.revoke_business_batch_oa_draft(
                batch.business_batch_id,
                reason="撤销后补充导入",
                expected_version=drafted.version,
            )
            second = service.revoke_business_batch_oa_draft(
                batch.business_batch_id,
                reason="重复点击撤销",
                expected_version=first.version,
            )
            invoice = service.list_invoices_by_ids(["etc_invoice_0001"])[0]

            self.assertEqual(first.status, EtcBusinessBatchStatus.NOT_SUBMITTED.value)
            self.assertEqual(second.status, EtcBusinessBatchStatus.NOT_SUBMITTED.value)
            self.assertIsNone(second.submission_batch_id)
            self.assertIsNone(invoice.current_batch_id)
            self.assertEqual(invoice.status, EtcInvoiceStatus.UNSUBMITTED)
            self.assertEqual(
                [event["event_type"] for event in second.audit_events].count("oa_draft_revoked"),
                1,
            )

    def test_business_batch_delete_rejects_submitted_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)
            submitted = service.apply_business_batch_oa_detection_result(
                batch.business_batch_id,
                detection_status="detected",
                reason="oa_row_in_progress",
                oa_row_id="oa-row-001",
                process_status="in_progress",
                expected_version=drafted.version,
            )

            with self.assertRaises(EtcBusinessBatchInvalidTransitionError):
                service.delete_business_batch(batch.business_batch_id, expected_version=submitted.version)

    def test_business_batch_delete_is_idempotent_and_hides_deleted_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            first = service.delete_business_batch(
                batch.business_batch_id,
                expected_version=batch.version,
                reason="user_deleted_unsubmitted_batch",
            )
            second = service.delete_business_batch(
                batch.business_batch_id,
                expected_version=batch.version,
                reason="user_deleted_unsubmitted_batch_retry",
            )

            self.assertEqual(first, {"deleted": True, "businessBatchId": batch.business_batch_id, "kind": "business_batch"})
            self.assertEqual(second, {"deleted": True, "businessBatchId": batch.business_batch_id, "kind": "business_batch"})
            self.assertEqual(service.list_business_batches(), [])
            with self.assertRaises(EtcBusinessBatchNotFoundError):
                service.get_business_batch(batch.business_batch_id)

    def test_business_batch_delete_removes_unsubmitted_oa_draft_contents(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("etc.zip", etc_zip(["ETC001", "ETC002"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=batch.version,
            )
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)

            deleted = service.delete_business_batch(
                drafted.business_batch_id,
                expected_version=drafted.version,
                reason="delete_unsubmitted_business_batch_with_draft",
            )

            self.assertEqual(deleted, {"deleted": True, "businessBatchId": drafted.business_batch_id, "kind": "business_batch"})
            self.assertEqual(service.list_business_batches(), [])
            self.assertEqual(service.list_import_batches(), [])
            self.assertEqual(service.list_invoices()[0], [])
            with self.assertRaises(EtcBusinessBatchNotFoundError):
                service.get_business_batch(drafted.business_batch_id)

    def test_business_batch_oa_detection_marks_submitted_and_updates_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, expected_version=batch.version)

            detected = service.apply_business_batch_oa_detection_result(
                drafted.business_batch_id,
                expected_version=drafted.version,
                detection_status="detected",
                reason="unique_candidate_detected",
                oa_row_id="oa-pay-ETC-001",
                process_status="in_progress",
                candidates=[{"oaRowId": "oa-pay-ETC-001"}],
            )
            invoice = service.list_invoices_by_ids(["etc_invoice_0001"])[0]

            self.assertEqual(detected.status, EtcBusinessBatchStatus.OA_SUBMITTED.value)
            self.assertEqual(detected.oa_row_id, "oa-pay-ETC-001")
            self.assertEqual(invoice.status, EtcInvoiceStatus.SUBMITTED)
            self.assertEqual(invoice.current_batch_id, detected.submission_batch_id)
            self.assertIsNone(detected.task_active_key)
            with self.assertRaises(EtcBusinessBatchInvalidTransitionError):
                service.revoke_business_batch_oa_draft(
                    detected.business_batch_id,
                    reason="OA 已提交后不能释放发票",
                    expected_version=detected.version,
                )

    def test_business_batch_application_refresh_uses_postgres_oa_projection_adapter(self) -> None:
        from fin_ops_platform.services.etc_business_batch_application_service import (
            EtcBusinessBatchActor,
            EtcBusinessBatchApplicationService,
        )
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionAdapter

        class ReconciliationTasks:
            def get_task(self, task_id: str) -> object:
                raise KeyError(task_id)

        class ProjectionRepository:
            def __init__(self, etc_service: EtcService) -> None:
                self._etc_service = etc_service
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                target = self._etc_service.get_business_batch(str(kwargs["business_batch_id"]))
                payload = self._etc_service.business_batch_payload(target)
                invoice_summary = payload["invoiceSummary"]
                return [
                    {
                        "oa_row_id": "oa-pay-etc-001",
                        "form_id": "2",
                        "amount": str(invoice_summary["amount"]),
                        "invoice_count": int(invoice_summary["count"]),
                        "applicant_user_id": "user-001",
                        "owner_org_id": "org-001",
                        "created_at": target.updated_at,
                        "process_status": "in_progress",
                        "reason": (
                            "ETC批量提交\n"
                            f"business_batch_id={target.business_batch_id}\n"
                            f"etc_batch_id={target.external_etc_batch_id}"
                        ),
                        "detail_fields": {"表单ID": "2", "流程状态": "进行中"},
                    }
                ]

        with TemporaryDirectory() as temp_dir:
            etc_service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            projection_repository = ProjectionRepository(etc_service)
            changed_batches: list[list[str]] = []
            refreshes: list[tuple[list[str], str]] = []
            application_service = EtcBusinessBatchApplicationService(
                etc_service=etc_service,
                reconciliation_task_service=ReconciliationTasks(),
                oa_client_factory=lambda _headers: FakeEtcOAClient(),
                oa_adapter_provider=lambda: PostgresOAProjectionAdapter(projection_repository),
                sync_etc_invoices_to_canonical_invoices=lambda invoices: changed_batches.append(
                    [invoice.id for invoice in invoices]
                )
                or ["2026-02"],
                refresh_after_etc_invoice_sync=lambda months, reason: refreshes.append((list(months), reason)),
            )
            actor = EtcBusinessBatchActor(can_admin_access=True, can_mutate_data=True)
            batch = etc_service.create_business_batch(
                task_id="ETC-TASK-SQL",
                owner_user_id="user-001",
                owner_org_id="org-001",
            )
            preview = etc_service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = etc_service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            draft_payload = application_service.create_oa_draft_payload(
                batch.business_batch_id,
                expected_version=batch.version,
                actor=actor,
                headers={},
            )
            drafted = draft_payload["businessBatch"]

            refreshed_payload = application_service.refresh_oa_status_payload(
                batch.business_batch_id,
                expected_version=int(drafted["version"]),
                actor=actor,
            )

            refreshed = refreshed_payload["businessBatch"]
            invoice = etc_service.list_invoices_by_ids(["etc_invoice_0001"])[0]
            self.assertEqual(refreshed["status"], EtcBusinessBatchStatus.OA_SUBMITTED.value)
            self.assertEqual(refreshed["oaRowId"], "oa-pay-etc-001")
            self.assertEqual(refreshed["oaDetectionReason"], "unique_candidate_detected")
            self.assertNotEqual(refreshed["oaDetectionReason"], "oa_detector_not_configured")
            self.assertEqual(invoice.status, EtcInvoiceStatus.SUBMITTED)
            self.assertEqual(projection_repository.calls[0]["business_batch_id"], batch.business_batch_id)
            self.assertEqual(projection_repository.calls[0]["external_etc_batch_id"], drafted["externalEtcBatchId"])
            self.assertIn(["etc_invoice_0001"], changed_batches)
            self.assertIn((["2026-02"], "etc_business_oa_status_detected"), refreshes)

    def test_timeout_business_batch_refresh_detects_late_valid_oa_candidate(self) -> None:
        from fin_ops_platform.services.etc_business_batch_application_service import (
            EtcBusinessBatchActor,
            EtcBusinessBatchApplicationService,
        )
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionAdapter

        class ReconciliationTasks:
            def get_task(self, task_id: str) -> object:
                raise KeyError(task_id)

        class ProjectionRepository:
            def __init__(self, etc_service: EtcService) -> None:
                self._etc_service = etc_service
                self.calls: list[dict[str, object]] = []

            def list_etc_oa_detection_candidates(self, **kwargs: object) -> list[dict[str, object]]:
                self.calls.append(dict(kwargs))
                target = self._etc_service.get_business_batch(str(kwargs["business_batch_id"]))
                if target.oa_detection_deadline_at is None:
                    return []
                late_candidate_created_at = target.updated_at
                created_to = kwargs.get("created_to")
                if created_to is not None and created_to < late_candidate_created_at:
                    return []
                payload = self._etc_service.business_batch_payload(target)
                invoice_summary = payload["invoiceSummary"]
                return [
                    {
                        "oa_row_id": "oa-pay-etc-late-001",
                        "form_id": "2",
                        "amount": str(invoice_summary["amount"]),
                        "invoice_count": int(invoice_summary["count"]),
                        "applicant_user_id": "user-001",
                        "owner_org_id": "org-001",
                        "created_at": late_candidate_created_at,
                        "process_status": "in_progress",
                        "reason": (
                            "ETC批量提交\n"
                            f"business_batch_id={target.business_batch_id}\n"
                            f"etc_batch_id={target.external_etc_batch_id}"
                        ),
                        "detail_fields": {"表单ID": "2", "流程状态": "进行中"},
                    }
                ]

        with TemporaryDirectory() as temp_dir:
            etc_service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            projection_repository = ProjectionRepository(etc_service)
            changed_batches: list[list[str]] = []
            refreshes: list[tuple[list[str], str]] = []
            application_service = EtcBusinessBatchApplicationService(
                etc_service=etc_service,
                reconciliation_task_service=ReconciliationTasks(),
                oa_client_factory=lambda _headers: FakeEtcOAClient(),
                oa_adapter_provider=lambda: PostgresOAProjectionAdapter(projection_repository),
                sync_etc_invoices_to_canonical_invoices=lambda invoices: changed_batches.append(
                    [invoice.id for invoice in invoices]
                )
                or ["2026-02"],
                refresh_after_etc_invoice_sync=lambda months, reason: refreshes.append((list(months), reason)),
            )
            actor = EtcBusinessBatchActor(can_admin_access=True, can_mutate_data=True)
            batch = etc_service.create_business_batch(
                task_id="ETC-TASK-LATE-OA",
                owner_user_id="user-001",
                owner_org_id="org-001",
            )
            preview = etc_service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))],
                expected_version=batch.version,
            )
            batch, _result = etc_service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            draft_payload = application_service.create_oa_draft_payload(
                batch.business_batch_id,
                expected_version=batch.version,
                actor=actor,
                headers={},
            )
            drafted = draft_payload["businessBatch"]

            stored_batch = etc_service._business_batches[str(drafted["businessBatchId"])]
            stored_batch.oa_detection_deadline_at = stored_batch.updated_at - timedelta(days=3)
            stored_batch.oa_detection_final_retry_until = stored_batch.updated_at - timedelta(days=2)
            timed_out = etc_service.apply_business_batch_oa_detection_result(
                str(drafted["businessBatchId"]),
                expected_version=int(drafted["version"]),
                detection_status="timeout",
                reason="oa_detection_deadline_exceeded",
                candidates=[],
            )

            refreshed_payload = application_service.refresh_oa_status_payload(
                timed_out.business_batch_id,
                expected_version=timed_out.version,
                actor=actor,
            )

            refreshed = refreshed_payload["businessBatch"]
            invoice = etc_service.list_invoices_by_ids(["etc_invoice_0001"])[0]
            self.assertEqual(refreshed["status"], EtcBusinessBatchStatus.OA_SUBMITTED.value)
            self.assertEqual(refreshed["oaRowId"], "oa-pay-etc-late-001")
            self.assertEqual(refreshed["oaDetectionReason"], "unique_candidate_detected")
            self.assertEqual(invoice.status, EtcInvoiceStatus.SUBMITTED)
            self.assertGreaterEqual(projection_repository.calls[0]["created_to"], timed_out.updated_at)
            self.assertIn(["etc_invoice_0001"], changed_batches)
            self.assertIn((["2026-02"], "etc_business_oa_status_detected"), refreshes)

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

    def test_state_store_invoice_attachments_survive_service_reload_for_oa_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = MemoryEtcStateStore(Path(temp_dir))
            service = EtcService(state_store=store)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])

            fake_oa = FakeEtcOAClient()
            reloaded = EtcService(state_store=store, oa_client=fake_oa)
            draft = reloaded.create_oa_draft(["etc_invoice_0001"])
            invoices, _total, _counts = reloaded.list_invoices(page=1, page_size=20)

        self.assertEqual(draft.oa_draft_id, "oa-draft-001")
        self.assertEqual(len(fake_oa.uploads), 1)
        self.assertTrue(Path(fake_oa.uploads[0]).name.endswith(".pdf"))
        self.assertTrue(str(invoices[0].pdf_file_path).startswith("memory://"))
        self.assertTrue(str(invoices[0].xml_file_path).startswith("memory://"))

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

    def test_preview_parses_ticket_root_invoice_package_with_root_xml_and_pdf(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            preview = service.preview_import_zips(
                [
                    UploadedEtcZipFile(
                        "ticket-root.zip",
                        zip_bytes(
                            {
                                "single-invoice.xml": etc_xml("ETC001"),
                                "single-invoice.pdf": fake_pdf("ETC001"),
                                "single-invoice.ofd": b"ofd",
                            }
                        ),
                    )
                ]
            )

        self.assertEqual(preview["summary"]["imported"], 1)
        self.assertEqual(preview["audit"]["original_count"], 1)
        self.assertEqual(preview["items"][0]["invoiceNumber"], "ETC001")

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
        self.assertEqual(data["invoiceCount"], 2)
        self.assertEqual(data["invoice_count"], 2)
        self.assertEqual(data["etcInvoiceCount"], 2)
        self.assertEqual(payload["invoiceCount"], 2)
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

    def test_draft_creation_repairs_stale_attachment_paths_from_canonical_storage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])

            invoice = service._invoices["etc_invoice_0001"]
            original_pdf_path = invoice.pdf_file_path
            original_xml_path = invoice.xml_file_path
            invoice.pdf_file_path = str(Path(temp_dir) / "missing" / "invoice.pdf")
            invoice.pdf_file_hash = None
            invoice.xml_file_path = None
            invoice.xml_file_hash = None

            draft = service.create_oa_draft(["etc_invoice_0001"])
            repaired_invoice = service._invoices["etc_invoice_0001"]

        self.assertEqual(draft.oa_draft_id, "oa-draft-001")
        self.assertEqual(repaired_invoice.pdf_file_path, original_pdf_path)
        self.assertEqual(repaired_invoice.xml_file_path, original_xml_path)
        self.assertTrue(repaired_invoice.pdf_file_hash)
        self.assertTrue(repaired_invoice.xml_file_hash)
        self.assertEqual(len(fake_oa.uploads), 1)

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

    def test_delete_import_batch_removes_locally_submitted_invoices_without_oa_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])
            import_batch_id = service.list_import_batches()[0].id
            service.update_invoice_status(["etc_invoice_0001", "etc_invoice_0002"], EtcInvoiceStatus.SUBMITTED)

            result = service.delete_batch(import_batch_id)
            invoices, total, counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(result, {"deleted": True, "batchId": import_batch_id, "kind": "import_batch"})
        self.assertEqual(service.list_import_batches(), [])
        self.assertEqual(invoices, [])
        self.assertEqual(total, 0)
        self.assertEqual(counts["submitted"], 0)

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

    def test_delete_submission_batch_releases_locally_submitted_invoices_without_confirmed_oa(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])
            draft = service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            service.update_invoice_status(["etc_invoice_0001", "etc_invoice_0002"], EtcInvoiceStatus.SUBMITTED)

            result = service.delete_batch(draft.batch_id)
            invoices, _total, counts = service.list_invoices(page=1, page_size=20)
            import_batch = service.list_import_batches()[0]

        self.assertEqual(result, {"deleted": True, "batchId": draft.batch_id, "kind": "submission_batch"})
        self.assertEqual(service.list_batches(), [])
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

            with self.assertRaisesRegex(EtcDraftRequestError, "ETC001 缺少 PDF"):
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

    def _import_supplement_reconciliation_zip(self, app) -> tuple[str, str]:
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
        task = app._etc_reconciliation_task_service.get_task(task_id)
        return task_id, str(task.import_batch_id or "")

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

    def test_ready_for_import_lists_unavailable_unconfirmed_tasks_with_blocker(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="2026-02 ETC", created_by="alice")

            response = app.handle_request("GET", "/api/etc/reconciliation-tasks/ready-for-import")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["tasks"], [])
        self.assertEqual([item["taskId"] for item in payload["unavailableTasks"]], [task.task_id])
        self.assertEqual(payload["unavailableTasks"][0]["status"], "draft")
        self.assertEqual(
            payload["unavailableTasks"][0]["importBlockers"],
            [
                {
                    "code": "not_confirmed",
                    "message": "请先在 ETC 对账页确认对账。",
                }
            ],
        )

    def test_reconciliation_confirm_route_accepts_selected_credit_card_item_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-1", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-1", text=TICKET_ROOT_TEXT),
                actor="alice",
            )
            selected_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
            task = app._etc_reconciliation_task_service.patch_item(
                task_id=task.task_id,
                item_id=selected_card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "link_ticket", "ticketItemId": task.ticket_root_items[0].item_id},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/confirm",
                json.dumps({
                    "expectedVersion": task.version,
                    "confirmedCreditCardItemIds": [selected_card.item_id],
                }),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ready_for_import")
        self.assertEqual(payload["oaTotalAmount"], "25.00")
        self.assertEqual(
            [item["credit_card_item_id"] for item in payload["expectedEtcInvoiceRequirements"]],
            [selected_card.item_id],
        )

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

    def test_refresh_reconciliation_matches_route_recalculates_and_returns_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id=f"{task.task_id}-CARD", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=f"{task.task_id}-TICKET", text=TICKET_ROOT_TEXT),
                actor="alice",
            )
            live_task = app._etc_reconciliation_task_service._tasks[task.task_id]
            card_id = live_task.credit_card_items[0].item_id
            live_task.ticket_root_items[0].linked_credit_card_item_ids = []
            live_task.ticket_root_items[0].recommendation_status = "unmatched"

            response = app.handle_request("POST", f"/api/etc/reconciliation-tasks/{task.task_id}/refresh-matches")
            prefixed_response = app.handle_request(
                "POST",
                f"/fin-ops-api/api/etc/reconciliation-tasks/{task.task_id}/refresh-matches",
            )
            payload = json.loads(response.body)
            prefixed_payload = json.loads(prefixed_response.body)
            readiness = app.readiness_summary()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["taskId"], task.task_id)
        self.assertEqual(payload["ticketRootItems"][0]["linked_credit_card_item_ids"], [card_id])
        self.assertEqual(payload["ticketRootItems"][0]["recommendation_status"], "suggested_match")
        self.assertEqual(prefixed_response.status_code, 200)
        self.assertEqual(prefixed_payload["taskId"], task.task_id)
        self.assertIn(
            "/api/etc/reconciliation-tasks/{task_id}/refresh-matches",
            readiness["entrypoints"],
        )

    def test_refresh_reconciliation_matches_route_returns_404_for_unknown_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("POST", "/api/etc/reconciliation-tasks/missing-task/refresh-matches")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.body)["error"], "unknown_reconciliation_task")

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

    def test_ticket_root_text_route_rejects_existing_txt_ticket_root_source(self) -> None:
        if not REAL_TICKET_ROOT_TXT_A516HJ_PATH.exists():
            self.skipTest(f"missing local ticket root sample: {REAL_TICKET_ROOT_TXT_A516HJ_PATH}")
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="云A516HJ",
                content_type="text/plain; charset=utf-8",
                content=REAL_TICKET_ROOT_TXT_A516HJ_PATH.read_bytes(),
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
        self.assertIn("TXT", payload["message"])
        self.assertIn("删除已有票根来源后才能切换导入方式", payload["message"])

    def test_ticket_root_upload_route_imports_txt_without_extension_with_clipboard_parser(self) -> None:
        if not REAL_TICKET_ROOT_TXT_A516HJ_PATH.exists():
            self.skipTest(f"missing local ticket root sample: {REAL_TICKET_ROOT_TXT_A516HJ_PATH}")
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)
            body, headers = multipart(
                {"云A516HJ": REAL_TICKET_ROOT_TXT_A516HJ_PATH.read_bytes()},
                fields={"expectedVersion": str(created["version"])},
            )

            with patch(
                "fin_ops_platform.app.server.TicketRootDocumentParser.parse_file",
                return_value=FileParseResult(file_id="DOC-UNEXPECTED", parser_code="ticket_root_document_v1"),
            ) as document_parse:
                response = app.handle_request(
                    "POST",
                    f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-files",
                    body=body,
                    headers=headers,
                )
            payload = json.loads(response.body)

        document_parse.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["sourceFiles"][0]["originalName"], "云A516HJ")
        self.assertEqual(payload["sourceFiles"][0]["contentType"], "text/plain; charset=utf-8")
        self.assertEqual(len(payload["ticketRootItems"]), 11)
        self.assertEqual({item["extraction_method"] for item in payload["ticketRootItems"]}, {"clipboard_text"})
        self.assertIn(
            ("2026-04-02 13:30:29", "57.95", "云A516HJ"),
            {
                (item["transaction_at"], item["amount"], item["vehicle_plate"])
                for item in payload["ticketRootItems"]
            },
        )
        self.assertIn(
            ("2026-04-02 11:25:48", "88.86", "云A516HJ"),
            {
                (item["transaction_at"], item["amount"], item["vehicle_plate"])
                for item in payload["ticketRootItems"]
            },
        )
        self.assertEqual(payload["parseIssues"], [])

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

    def test_ticket_root_upload_route_rejects_existing_txt_ticket_root_source_before_pdf_upload(self) -> None:
        if not REAL_TICKET_ROOT_TXT_A516HJ_PATH.exists():
            self.skipTest(f"missing local ticket root sample: {REAL_TICKET_ROOT_TXT_A516HJ_PATH}")
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            app._etc_reconciliation_task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="云A516HJ",
                content_type="text/plain; charset=utf-8",
                content=REAL_TICKET_ROOT_TXT_A516HJ_PATH.read_bytes(),
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
        self.assertIn("TXT", payload["message"])
        self.assertIn("删除已有票根来源后才能切换导入方式", payload["message"])

    def test_ticket_root_upload_route_rejects_existing_pdf_ticket_root_source_before_txt_upload(self) -> None:
        if not REAL_TICKET_ROOT_TXT_A516HJ_PATH.exists():
            self.skipTest(f"missing local ticket root sample: {REAL_TICKET_ROOT_TXT_A516HJ_PATH}")
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
            body, headers = multipart(
                {"云A516HJ": REAL_TICKET_ROOT_TXT_A516HJ_PATH.read_bytes()},
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
        self.assertIn("PDF/JPG", payload["message"])
        self.assertIn("删除已有票根来源后才能切换导入方式", payload["message"])

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

    def test_delete_ready_for_import_reconciliation_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(app)
            task = app._etc_reconciliation_task_service.get_task(task_id)

            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                body=json.dumps({"expectedVersion": task.version}),
            )
            missing = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body), {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        self.assertEqual(missing.status_code, 404)

    def test_delete_imported_reconciliation_task_cascades_imported_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, _preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            imported_task = app._etc_reconciliation_task_service.get_task(task_id)

            stale_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                body=json.dumps({"expectedVersion": imported_task.version - 1}),
            )
            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                body=json.dumps({"expectedVersion": imported_task.version}),
            )
            missing = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            batches = json.loads(app.handle_request("GET", "/api/etc/batches?status=unsubmitted").body)

        self.assertEqual(stale_response.status_code, 409)
        self.assertEqual(json.loads(stale_response.body)["error"], "task_version_conflict")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body), {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(batches["items"], [])
        self.assertEqual(app._etc_service.list_import_batches(), [])
        self.assertEqual(app._import_service.list_invoices(), [])

    def test_delete_imported_reconciliation_task_tolerates_missing_import_batch_container(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, _preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            imported_task = app._etc_reconciliation_task_service.get_task(task_id)
            import_batch_id = str(imported_task.import_batch_id or "")
            app._etc_service._import_batches.pop(import_batch_id)

            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                body=json.dumps({"expectedVersion": imported_task.version}),
            )
            payload = json.loads(response.body)
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            missing = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(app._import_service.list_invoices(), [])

    def test_delete_imported_reconciliation_task_cleans_unsubmitted_external_oa_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, _preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            imported_task = app._etc_reconciliation_task_service.get_task(task_id)
            linked_task = app._etc_reconciliation_task_service.record_oa_draft_created(
                task_id=task_id,
                oa_draft_batch_id="missing-local-draft-batch-001",
                etc_batch_id="ETC-EXTERNAL-LINK-001",
                actor="test",
            )

            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                body=json.dumps({"expectedVersion": linked_task.version}),
            )
            payload = json.loads(response.body)
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            missing = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")

        self.assertEqual(imported_task.status.value, "imported")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload, {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(app._import_service.list_invoices(), [])

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

    def test_delete_etc_submission_batch_route_cascades_mutable_batch_contents(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            app._etc_service.import_zips([UploadedEtcZipFile("draft.zip", etc_zip(["ETC001", "ETC002"]))])
            draft = app._etc_service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            app._etc_service.update_invoice_status(["etc_invoice_0001", "etc_invoice_0002"], EtcInvoiceStatus.SUBMITTED)

            delete_response = app.handle_request("DELETE", f"/api/etc/batches/{draft.batch_id}")
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            batches = json.loads(app.handle_request("GET", "/api/etc/batches?status=unsubmitted").body)

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body), {"deleted": True, "batchId": draft.batch_id, "kind": "submission_batch"})
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(batches["items"], [])
        self.assertEqual(app._etc_service.list_import_batches(), [])

    def test_delete_etc_submission_batch_route_repairs_stale_invoice_references(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            app._etc_service.import_zips([UploadedEtcZipFile("draft.zip", etc_zip(["ETC001", "ETC002"]))])
            draft = app._etc_service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            app._etc_service._invoices.clear()
            app._etc_service._invoice_numbers.clear()
            app._etc_service._import_batches.clear()

            delete_response = app.handle_request("DELETE", f"/api/etc/batches/{draft.batch_id}")
            detail_response = app.handle_request("GET", f"/api/etc/batches/{draft.batch_id}")

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body), {"deleted": True, "batchId": draft.batch_id, "kind": "submission_batch"})
        self.assertEqual(detail_response.status_code, 404)

    def test_etc_business_batch_api_and_legacy_batches_use_unified_view(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": "ETC-TASK-001", "ownerUserId": "alice", "ownerOrgId": "finance"}),
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]
            preview_body, preview_headers = multipart(
                {"invoices.zip": etc_zip(["ETC001"])},
                {"expectedVersion": str(created["version"])},
            )
            preview_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/preview",
                preview_body,
                preview_headers,
            )
            preview = json.loads(preview_response.body)["data"]
            confirm_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/confirm",
                json.dumps({
                    "sessionId": preview["sessionId"],
                    "expectedVersion": preview["businessBatch"]["version"],
                }),
            )
            confirmed = json.loads(confirm_response.body)["data"]["businessBatch"]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": confirmed["version"]}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            detail_response = app.handle_request("GET", f"/api/etc/business-batches/{created['businessBatchId']}")
            list_response = app.handle_request("GET", "/api/etc/business-batches")
            legacy_response = app.handle_request("GET", "/api/etc/batches")
            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/business-batches/{created['businessBatchId']}",
                json.dumps({"expectedVersion": drafted["version"], "reason": "api_delete_unsubmitted_draft"}),
            )
            deleted_detail_response = app.handle_request("GET", f"/api/etc/business-batches/{created['businessBatchId']}")
            deleted_list_response = app.handle_request("GET", "/api/etc/business-batches")
            deleted_legacy_response = app.handle_request("GET", "/api/etc/batches")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(json.loads(detail_response.body)["data"]["businessBatch"]["businessBatchId"], created["businessBatchId"])
        self.assertEqual(json.loads(list_response.body)["data"]["items"][0]["businessBatchId"], created["businessBatchId"])
        legacy_items = json.loads(legacy_response.body)["items"]
        self.assertEqual([item["id"] for item in legacy_items], [created["businessBatchId"]])
        self.assertEqual(legacy_items[0]["source_type"], "etc_business_batch")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(deleted_detail_response.status_code, 404)
        self.assertEqual(json.loads(deleted_list_response.body)["data"]["items"], [])
        self.assertEqual(json.loads(deleted_legacy_response.body)["items"], [])

    def test_etc_business_batch_detail_returns_invoice_items_and_detection_fields(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": "ETC-TASK-DETAIL"}),
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]
            preview_body, preview_headers = multipart(
                {"invoices.zip": etc_zip(["ETC001"])},
                {"expectedVersion": str(created["version"])},
            )
            preview_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/preview",
                preview_body,
                preview_headers,
            )
            preview = json.loads(preview_response.body)["data"]
            confirm_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/confirm",
                json.dumps({
                    "sessionId": preview["sessionId"],
                    "expectedVersion": preview["businessBatch"]["version"],
                }),
            )
            detail_response = app.handle_request("GET", f"/api/etc/business-batches/{created['businessBatchId']}")

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        detail = json.loads(detail_response.body)["data"]["businessBatch"]
        self.assertEqual(detail["invoiceItems"][0]["invoice_number"], "ETC001")
        self.assertIn("oaDetectionError", detail)
        self.assertIn("oaDetectionStartedAt", detail)
        self.assertIn("oaDetectionNextRunAt", detail)
        self.assertIn("oaDetectionDeadlineAt", detail)
        self.assertIn("oaDetectionFinalRetryUntil", detail)

    def test_etc_business_batch_scope_uses_session_dept_id(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._access_control_service.dynamic_allowed_usernames_provider = lambda: ["OWNER", "OTHER", "ADMIN"]
            app._access_control_service.dynamic_admin_usernames_provider = lambda: ["ADMIN"]

            identities = {
                "owner-token": OAUserIdentity(
                    user_id="owner-id",
                    username="OWNER",
                    nickname="Owner",
                    display_name="Owner",
                    dept_id="D01",
                    permissions=[app._access_control_service.required_permission],
                ),
                "other-token": OAUserIdentity(
                    user_id="other-id",
                    username="OTHER",
                    nickname="Other",
                    display_name="Other",
                    dept_id="D02",
                    permissions=[app._access_control_service.required_permission],
                ),
                "admin-token": OAUserIdentity(
                    user_id="admin-id",
                    username="ADMIN",
                    nickname="Admin",
                    display_name="Admin",
                    dept_id="D99",
                    permissions=[app._access_control_service.required_permission],
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[str(token)]
            owner_headers = {"Authorization": "Bearer owner-token"}
            other_headers = {"Authorization": "Bearer other-token"}
            admin_headers = {"Authorization": "Bearer admin-token"}

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": "ETC-TASK-SCOPE"}),
                owner_headers,
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]
            other_list_response = app.handle_request("GET", "/api/etc/business-batches", headers=other_headers)
            other_detail_response = app.handle_request(
                "GET",
                f"/api/etc/business-batches/{created['businessBatchId']}",
                headers=other_headers,
            )
            admin_detail_response = app.handle_request(
                "GET",
                f"/api/etc/business-batches/{created['businessBatchId']}",
                headers=admin_headers,
            )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(created["ownerUserId"], "OWNER")
        self.assertEqual(created["ownerOrgId"], "D01")
        self.assertEqual(json.loads(other_list_response.body)["data"]["items"], [])
        self.assertEqual(other_detail_response.status_code, 403)
        self.assertEqual(json.loads(other_detail_response.body)["error"]["code"], "forbidden_scope")
        self.assertEqual(admin_detail_response.status_code, 200)

    def test_etc_business_batch_oa_draft_enqueues_detection_event(self) -> None:
        class QueueRecorder:
            def __init__(self) -> None:
                self.events: list[dict[str, object]] = []

            def enqueue(self, **kwargs):
                self.events.append(dict(kwargs))
                return {"event_id": f"evt-{len(self.events)}"}

        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            queue = QueueRecorder()
            object.__setattr__(app._runtime_repositories, "queue_repository", queue)

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": "ETC-TASK-QUEUE"}),
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]
            preview_body, preview_headers = multipart(
                {"invoices.zip": etc_zip(["ETC001"])},
                {"expectedVersion": str(created["version"])},
            )
            preview_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/preview",
                preview_body,
                preview_headers,
            )
            preview = json.loads(preview_response.body)["data"]
            confirm_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/confirm",
                json.dumps({
                    "sessionId": preview["sessionId"],
                    "expectedVersion": preview["businessBatch"]["version"],
                }),
            )
            confirmed = json.loads(confirm_response.body)["data"]["businessBatch"]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": confirmed["version"]}),
            )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual([event["event_type"] for event in queue.events], ["etc_business.oa_detection.refresh"])
        self.assertEqual(queue.events[0]["aggregate_id"], created["businessBatchId"])

    def test_etc_business_batch_source_files_append_to_reconciliation_task(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC source files", created_by="alice")
            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": task.task_id}),
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]
            body, headers = multipart({"ticket-root.zip": b"zip-bytes"})

            response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/source-files",
                body,
                headers,
            )
            payload = json.loads(response.body)["data"]
            task_after_upload = app._etc_reconciliation_task_service.get_task(task.task_id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["businessBatch"]["businessBatchId"], created["businessBatchId"])
        self.assertEqual(payload["sourceFiles"][0]["originalName"], "ticket-root.zip")
        self.assertEqual(payload["sourceFiles"][0]["sourceKind"], "etc_zip")
        self.assertEqual(task_after_upload.source_files[0].original_name, "ticket-root.zip")

    def test_etc_business_manual_status_rejects_detecting_state(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            app._etc_service.import_zips([UploadedEtcZipFile("draft.zip", etc_zip(["ETC001"]))])
            batch = app._etc_service.create_business_batch(task_id="ETC-TASK-MANUAL", owner_user_id="alice")
            imported, _ = app._etc_service.confirm_business_batch_import(
                batch.business_batch_id,
                app._etc_service.preview_business_batch_import_zips(
                    batch.business_batch_id,
                    [UploadedEtcZipFile("manual.zip", etc_zip(["ETC002"]))],
                    expected_version=batch.version,
                )["sessionId"],
                expected_version=batch.version,
            )
            drafted = app._etc_service.create_business_batch_oa_draft(
                imported.business_batch_id,
                expected_version=imported.version,
            )

            with self.assertRaises(EtcBusinessBatchInvalidTransitionError) as context:
                app._etc_service.manual_business_batch_oa_status(
                    drafted.business_batch_id,
                    decision="submitted",
                    reason="人工确认",
                    expected_version=drafted.version,
                )

        self.assertEqual(context.exception.code, "invalid_manual_status")

    def test_etc_business_batch_delete_is_idempotent_for_stale_business_ids(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            business_response = app.handle_request(
                "DELETE",
                "/api/etc/business-batches/etc_business_batch_0002",
                json.dumps({"reason": "stale_row_cleanup"}),
            )
            legacy_response = app.handle_request("DELETE", "/api/etc/batches/etc_business_batch_0002")

        expected = {
            "deleted": True,
            "businessBatchId": "etc_business_batch_0002",
            "kind": "business_batch",
        }
        self.assertEqual(business_response.status_code, 200)
        self.assertEqual(json.loads(business_response.body)["data"], expected)
        self.assertEqual(legacy_response.status_code, 200)
        self.assertEqual(json.loads(legacy_response.body)["data"], expected)

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

    def test_reconciliation_item_supplement_upload_requires_note_for_amount_delta(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="2026-03 ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-FILE-1", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
            body, headers = multipart(
                {"parking.pdf": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8")},
                fields={"expectedVersion": str(task.version), "evidenceKind": "non_etc_invoice"},
            )

            missing_note_response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/supplement-evidences/{card.item_id}",
                body=body,
                headers=headers,
            )
            task_after_failed_upload = app._etc_reconciliation_task_service.get_task(task.task_id)

            body_with_note, headers_with_note = multipart(
                {"parking.pdf": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8")},
                fields={
                    "expectedVersion": str(task.version),
                    "evidenceKind": "non_etc_invoice",
                    "note": "停车费凭证少开 2 元，按信用卡实际支出提交。",
                },
            )
            linked_response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/supplement-evidences/{card.item_id}",
                body=body_with_note,
                headers=headers_with_note,
            )
            linked_payload = json.loads(linked_response.body)

        self.assertEqual(missing_note_response.status_code, 400)
        self.assertEqual(json.loads(missing_note_response.body)["error"], "supplement_amount_delta_note_required")
        self.assertEqual(task_after_failed_upload.supplement_evidences, [])
        self.assertEqual(linked_response.status_code, 200)
        self.assertEqual(linked_payload["creditCardItems"][0]["manual_resolution"], "covered_by_supplement")
        self.assertEqual(linked_payload["creditCardItems"][0]["review_note"], "停车费凭证少开 2 元，按信用卡实际支出提交。")
        self.assertEqual(linked_payload["reconciledItems"][0]["claim_amount"], "25.00")
        self.assertEqual(linked_payload["reconciledItems"][0]["evidence_amount"], "23.00")
        self.assertEqual(linked_payload["reconciledItems"][0]["amount_delta"], "2.00")

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
        self.assertEqual(
            {item["invoiceNumber"]: item["filterStatus"] for item in preview_payload["items"]},
            {"ETC001": "included", "EXTRA": "excluded_extra_zip_invoice"},
        )
        self.assertEqual(preview_payload["audit"]["original_count"], 2)
        self.assertEqual(preview_payload["importAudit"]["original_count"], 1)
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

    def test_task_aware_etc_import_does_not_create_independent_batch_list_item(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])

            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            completed_job = self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)
            batch_list = json.loads(app.handle_request("GET", "/api/etc/batches").body)

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(task_payload["status"], "imported")
        self.assertIsNotNone(task_payload["importBatchId"])
        self.assertTrue(task_payload["hasImportedInvoices"])
        self.assertEqual(task_payload["importedInvoiceCount"], 1)
        self.assertEqual(task_payload["importedInvoiceAmount"], "13.07")
        self.assertEqual(batch_list["items"], [])
        self.assertEqual(batch_list["counts"]["unsubmitted"], 0)

    def test_remove_reconciliation_task_imported_invoices_allows_reimport(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, _preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            imported_task = app._etc_reconciliation_task_service.get_task(task_id)

            stale_remove_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}/imported-invoices",
                json.dumps({"expectedVersion": imported_task.version - 1, "actor": "alice"}),
            )
            remove_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}/imported-invoices",
                json.dumps({"expectedVersion": imported_task.version, "actor": "alice"}),
            )
            removed_payload = json.loads(remove_response.body)
            invoices_after_remove = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            canonical_etc_after_remove = [
                invoice
                for invoice in app._import_service.list_invoices()
                if getattr(invoice, "etc_import_batch_id", None)
            ]
            reimport_body, reimport_headers = multipart(
                {
                    "etc.zip": zip_bytes(
                        {
                            "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-02-27", total_amount="13.07"),
                            "pdf/ETC001.pdf": fake_pdf("ETC001"),
                        }
                    )
                },
                fields={"task_id": task_id},
            )
            reimport_preview_response = app.handle_request(
                "POST",
                "/api/etc/import/preview",
                body=reimport_body,
                headers=reimport_headers,
            )
            reimport_preview = json.loads(reimport_preview_response.body)
            reimport_confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": reimport_preview["sessionId"], "taskId": task_id}),
            )
            reimport_job = self._wait_for_job(app, json.loads(reimport_confirm_response.body)["job"]["job_id"])
            final_task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)
            final_invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(stale_remove_response.status_code, 409)
        self.assertEqual(json.loads(stale_remove_response.body)["error"], "task_version_conflict")
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(removed_payload["status"], "ready_for_import")
        self.assertIsNone(removed_payload["importBatchId"])
        self.assertFalse(removed_payload["hasImportedInvoices"])
        self.assertEqual(removed_payload["importedInvoiceCount"], 0)
        self.assertEqual(invoices_after_remove["total"], 0)
        self.assertEqual(canonical_etc_after_remove, [])
        self.assertEqual(reimport_preview_response.status_code, 200)
        self.assertEqual(reimport_preview["summary"]["imported"], 1)
        self.assertEqual(reimport_confirm_response.status_code, 202)
        self.assertEqual(reimport_job["status"], "succeeded")
        self.assertEqual(final_task_payload["status"], "imported")
        self.assertTrue(final_task_payload["hasImportedInvoices"])
        self.assertEqual(final_invoices["total"], 1)

    def test_remove_reconciliation_task_imported_invoices_deletes_unsubmitted_oa_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, import_batch_id = self._import_supplement_reconciliation_zip(app)
            draft_response = app.handle_request("POST", f"/api/etc/batches/{import_batch_id}/draft")
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/mark-not-submitted")
            linked_task = app._etc_reconciliation_task_service.get_task(task_id)

            remove_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}/imported-invoices",
                json.dumps({"expectedVersion": linked_task.version, "actor": "alice"}),
            )
            removed_payload = json.loads(remove_response.body)
            invoices_after_remove = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(removed_payload["status"], "ready_for_import")
        self.assertIsNone(removed_payload["importBatchId"])
        self.assertIsNone(removed_payload["oaDraftBatchId"])
        self.assertIsNone(removed_payload["etcBatchId"])
        self.assertEqual(invoices_after_remove["total"], 0)
        self.assertEqual(app._etc_service.list_import_batches(), [])

    def test_remove_reconciliation_task_imported_invoices_repairs_missing_unsubmitted_oa_draft_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, import_batch_id = self._import_supplement_reconciliation_zip(app)
            draft_response = app.handle_request("POST", f"/api/etc/batches/{import_batch_id}/draft")
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/mark-not-submitted")
            app._etc_service._batches.pop(draft_payload["batchId"])
            linked_task = app._etc_reconciliation_task_service.get_task(task_id)

            remove_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}/imported-invoices",
                json.dumps({"expectedVersion": linked_task.version, "actor": "alice"}),
            )
            removed_payload = json.loads(remove_response.body)
            invoices_after_remove = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(removed_payload["status"], "ready_for_import")
        self.assertIsNone(removed_payload["importBatchId"])
        self.assertIsNone(removed_payload["oaDraftBatchId"])
        self.assertIsNone(removed_payload["etcBatchId"])
        self.assertEqual(invoices_after_remove["total"], 0)
        self.assertEqual(app._etc_service.list_import_batches(), [])

    def test_unsubmitted_oa_draft_batch_is_listed_and_deletable(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, import_batch_id = self._import_supplement_reconciliation_zip(app)
            draft_response = app.handle_request("POST", f"/api/etc/batches/{import_batch_id}/draft")
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/mark-not-submitted")
            unsubmitted_before_delete = json.loads(app.handle_request("GET", "/api/etc/batches?status=unsubmitted").body)
            delete_response = app.handle_request("DELETE", f"/api/etc/batches/{draft_payload['batchId']}")
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)

        listed_ids = [item["id"] for item in unsubmitted_before_delete["items"]]
        self.assertIn(draft_payload["batchId"], listed_ids)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body)["kind"], "submission_batch")
        self.assertIsNone(task_payload["oaDraftBatchId"])
        self.assertIsNone(task_payload["etcBatchId"])

    def test_delete_missing_unsubmitted_oa_draft_batch_repairs_reconciliation_task_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, import_batch_id = self._import_supplement_reconciliation_zip(app)
            draft_response = app.handle_request("POST", f"/api/etc/batches/{import_batch_id}/draft")
            draft_payload = json.loads(draft_response.body)
            app.handle_request("POST", f"/api/etc/batches/{draft_payload['batchId']}/mark-not-submitted")
            app._etc_service._batches.pop(draft_payload["batchId"])

            delete_response = app.handle_request("DELETE", f"/api/etc/batches/{draft_payload['batchId']}")
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body), {
            "deleted": True,
            "batchId": draft_payload["batchId"],
            "kind": "missing_submission_batch",
        })
        self.assertIsNone(task_payload["oaDraftBatchId"])
        self.assertIsNone(task_payload["etcBatchId"])
        self.assertIsNone(task_payload["importBatchId"])
        self.assertEqual(task_payload["status"], "ready_for_import")
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(app._etc_service.list_import_batches(), [])

    def test_task_aware_etc_import_confirm_imports_sum_matched_invoices_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            statement_text = """
中国建设银行信用卡账单
2026-04-08 2026-04-09 3632 云南高速通行费 CNY 71.25 71.25
"""
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id=f"{task.task_id}-CARD", text=statement_text),
                actor="alice",
            )
            ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 18:57:17
入口站 昆明南站
出口站 小喜村站
金额 71.25
发票张数 2
"""
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id=f"{task.task_id}-TICKET", text=ticket_text),
                actor="alice",
            )
            card = task.credit_card_items[0]
            ticket = task.ticket_root_items[0]
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
            confirmed = app._etc_reconciliation_task_service.confirm_task(
                task_id=task.task_id,
                expected_version=task.version,
                actor="alice",
            )
            body, headers = multipart(
                {
                    "etc.zip": zip_bytes(
                        {
                            "xml/ETC2950.xml": etc_xml("ETC2950", issue_date="2026-04-08", total_amount="29.50"),
                            "pdf/ETC2950.pdf": fake_pdf("ETC2950"),
                            "xml/ETC4175.xml": etc_xml("ETC4175", issue_date="2026-04-08", total_amount="41.75"),
                            "pdf/ETC4175.pdf": fake_pdf("ETC4175"),
                            "xml/EXTRA.xml": etc_xml("EXTRA", issue_date="2026-04-08", total_amount="999.99"),
                            "pdf/EXTRA.pdf": fake_pdf("EXTRA"),
                        }
                    )
                },
                fields={"task_id": confirmed.task_id},
            )

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": confirmed.task_id}),
            )
            completed_job = self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)
            business_batches = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={confirmed.task_id}").body
            )
            active_business_batches = json.loads(
                app.handle_request("GET", "/api/etc/business-batches?status=active&page=1&page_size=100").body
            )

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["reconciliationFilter"]["allowedInvoiceNumbers"], ["ETC2950", "ETC4175"])
        self.assertEqual(preview_payload["summary"]["imported"], 2)
        self.assertEqual(preview_payload["audit"]["original_count"], 3)
        self.assertEqual(preview_payload["importAudit"]["original_count"], 2)
        self.assertEqual(
            {item["invoiceNumber"]: item["filterStatus"] for item in preview_payload["reconciliationFilter"]["items"]},
            {"ETC2950": "included", "ETC4175": "included", "EXTRA": "excluded_extra_zip_invoice"},
        )
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(invoices["total"], 2)
        self.assertEqual({item["invoice_number"] for item in invoices["items"]}, {"ETC2950", "ETC4175"})
        self.assertEqual(business_batches["data"]["total"], 1)
        business_batch = business_batches["data"]["items"][0]
        self.assertEqual(business_batch["taskId"], confirmed.task_id)
        self.assertEqual(business_batch["status"], "imported")
        self.assertEqual(business_batch["invoiceSummary"]["count"], 2)
        self.assertEqual(business_batch["importBatchIds"], ["etc_import_batch_0001"])
        self.assertEqual(active_business_batches["data"]["counts"]["active"], 1)
        self.assertEqual(active_business_batches["data"]["total"], 1)
        self.assertEqual(active_business_batches["data"]["items"][0]["businessBatchId"], business_batch["businessBatchId"])

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

    def test_reconciliation_import_batch_route_creates_oa_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            fake_oa = FakeEtcOAClient()
            app._etc_service.oa_client = fake_oa

            task_id, import_batch_id = self._import_supplement_reconciliation_zip(app)
            draft_response = app.handle_request("POST", f"/api/etc/batches/{import_batch_id}/draft")
            draft_payload = json.loads(draft_response.body)
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["oaDraftId"], "oa-draft-001")
        self.assertEqual(task_payload["oaDraftBatchId"], draft_payload["batchId"])
        self.assertEqual(task_payload["etcBatchId"], draft_payload["etcBatchId"])
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

    def test_etc_batch_list_only_checks_attachment_status_for_selected_detail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            for batch_index in range(4):
                invoice_numbers = [f"ETC{batch_index}{invoice_index}" for invoice_index in range(2)]
                app._etc_service.import_zips([UploadedEtcZipFile(f"batch-{batch_index}.zip", etc_zip(invoice_numbers))])

            for batch_index in (2, 3):
                invoice_numbers = [f"ETC{batch_index}{invoice_index}" for invoice_index in range(2)]
                submitted_batch = app._etc_service.create_historical_submitted_batch(
                    case_id=f"etc-historical-{batch_index}",
                    external_batch_id=f"ETC-HIST-{batch_index}",
                    invoice_numbers=invoice_numbers,
                    linked_oa_row_id=f"oa-exp-{batch_index}",
                    oa_amount=Decimal("26.14"),
                    note="历史补关联",
                )
                import_batch = next(
                    batch
                    for batch in app._etc_service.list_import_batches()
                    if batch.source_names == [f"batch-{batch_index}.zip"]
                )
                import_batch.submission_batch_id = submitted_batch.id

            attachment_exists_calls = 0

            def count_attachment_exists(_path: object) -> bool:
                nonlocal attachment_exists_calls
                attachment_exists_calls += 1
                return True

            app._etc_service._stored_invoice_file_exists = count_attachment_exists

            unsubmitted_response = app.handle_request("GET", "/api/etc/batches?status=unsubmitted&page=1&page_size=20")
            unsubmitted_attachment_checks = attachment_exists_calls
            attachment_exists_calls = 0
            submitted_response = app.handle_request("GET", "/api/etc/batches?status=submitted&page=1&page_size=20")
            submitted_attachment_checks = attachment_exists_calls

        self.assertEqual(unsubmitted_response.status_code, 200)
        self.assertEqual(submitted_response.status_code, 200)
        self.assertEqual(json.loads(unsubmitted_response.body)["pagination"]["total"], 2)
        self.assertEqual(json.loads(submitted_response.body)["pagination"]["total"], 2)
        self.assertEqual(unsubmitted_attachment_checks, 4)
        self.assertEqual(submitted_attachment_checks, 4)

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

    def test_existing_etc_batch_link_extends_active_oa_bank_relation_and_renders_summary(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            manual_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="manual-etc.xlsx",
                imported_by="finance",
                rows=[
                    {
                        "digital_invoice_no": "ETC001",
                        "invoice_no": "ETC001",
                        "counterparty_name": "云南高速公路联网收费管理有限公司",
                        "seller_name": "云南高速公路联网收费管理有限公司",
                        "seller_tax_no": "915300007194052520",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052521",
                        "amount": "12.68",
                        "total_with_tax": "13.07",
                        "tax_amount": "0.39",
                        "invoice_date": "2026-02-27",
                    },
                    {
                        "digital_invoice_no": "ETC002",
                        "invoice_no": "ETC002",
                        "counterparty_name": "云南高速公路联网收费管理有限公司",
                        "seller_name": "云南高速公路联网收费管理有限公司",
                        "seller_tax_no": "915300007194052520",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052521",
                        "amount": "12.68",
                        "total_with_tax": "13.07",
                        "tax_amount": "0.39",
                        "invoice_date": "2026-02-28",
                    },
                ],
            )
            app._import_service.confirm_import(manual_preview.id)
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-EXISTING-ETC",
                row_ids=["txn-existing-etc", "oa-existing-etc"],
                row_types=["bank", "oa"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-02",
                note="existing OA-bank relation",
                amount_check={
                    "status": "matched",
                    "direction": "expense",
                    "oa_amount": "30.00",
                    "bank_amount": "30.00",
                    "amount_delta": "0.00",
                },
            )
            service = ExistingEtcBatchLinkService(
                etc_service=app._etc_service,
                import_service=app._import_service,
                pair_relation_service=app._workbench_pair_relation_service,
                sync_import_result_to_canonical_invoices=app._sync_etc_import_result_to_canonical_invoices,
                sync_etc_invoices_to_canonical_invoices=app._sync_etc_invoices_to_canonical_invoices,
                refresh_after_etc_invoice_sync=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )

            result = service.link_existing_invoices(
                ExistingEtcBatchLinkSpec(
                    label="测试 ETC 批次",
                    case_id="CASE-EXISTING-ETC",
                    external_batch_id="ETC-EXISTING-2026-02",
                    oa_row_id="oa-existing-etc",
                    bank_row_id="txn-existing-etc",
                    oa_amount=Decimal("30.00"),
                    bank_amount=Decimal("30.00"),
                    invoice_numbers=("ETC001", "ETC002"),
                    note="把现有 ETC 发票补充到已配对 OA-银行批次",
                )
            )
            relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-EXISTING-ETC")
            invoices = {invoice.invoice_no: invoice for invoice in app._import_service.list_invoices()}
            raw_payload = {
                "month": "2026-02",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {
                            "id": "oa-existing-etc",
                            "type": "oa",
                            "case_id": "",
                            "applicant": "张三",
                            "apply_type": "支付申请",
                            "amount": "30.00",
                            "counterparty_name": "云南高速通行费",
                            "reason": "ETC通行费",
                            "oa_bank_relation": {"code": "pending_match", "label": "待找流水", "tone": "warn"},
                            "available_actions": ["detail"],
                        }
                    ],
                    "bank": [
                        {
                            "id": "txn-existing-etc",
                            "type": "bank",
                            "trade_time": "2026-02-15 09:04:01",
                            "direction": "支出",
                            "debit_amount": "30.00",
                            "credit_amount": "",
                            "counterparty_name": "批量账务集中处理",
                            "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                            "available_actions": ["detail"],
                        }
                    ],
                    "invoice": [],
                },
            }
            with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
                payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-02").body)
            invoice_rows = [
                row
                for group in payload["paired"]["groups"]
                for row in group["invoice_rows"]
            ]

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.invoice_count, 2)
        self.assertEqual(result.invoice_total, Decimal("26.14"))
        self.assertEqual(result.delta, Decimal("3.86"))
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["case_id"], "CASE-EXISTING-ETC")
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
        self.assertEqual(relation["row_ids"], ["txn-existing-etc", "oa-existing-etc"])
        self.assertEqual(relation["amount_check"]["status"], "mismatch")
        self.assertEqual(relation["amount_check"]["invoice_total"], "26.14")
        self.assertEqual(relation["amount_check"]["delta"], "3.86")
        self.assertEqual(relation["amount_check"]["external_etc_batch_id"], "ETC-EXISTING-2026-02")
        self.assertEqual(invoices["ETC001"].workbench_visibility, "hidden_after_etc_submission")
        self.assertEqual(invoices["ETC001"].etc_submission_status, "submitted")
        self.assertEqual(invoices["ETC002"].workbench_visibility, "hidden_after_etc_submission")
        self.assertEqual(len(invoice_rows), 1)
        self.assertEqual(invoice_rows[0]["source_kind"], "etc_invoice_summary")
        self.assertEqual(invoice_rows[0]["seller_name"], "ETC发票 2 张")
        self.assertEqual(invoice_rows[0]["total_with_tax"], "26.14")

    def test_existing_etc_batch_link_is_idempotent_and_does_not_create_parallel_relation(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            manual_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="manual-etc.xlsx",
                imported_by="finance",
                rows=[
                    {
                        "digital_invoice_no": "ETC001",
                        "invoice_no": "ETC001",
                        "counterparty_name": "云南高速公路联网收费管理有限公司",
                        "seller_name": "云南高速公路联网收费管理有限公司",
                        "seller_tax_no": "915300007194052520",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052521",
                        "amount": "12.68",
                        "total_with_tax": "13.07",
                        "tax_amount": "0.39",
                        "invoice_date": "2026-02-27",
                    },
                ],
            )
            app._import_service.confirm_import(manual_preview.id)
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-IDEMPOTENT-ETC",
                row_ids=["txn-idempotent-etc", "oa-idempotent-etc"],
                row_types=["bank", "oa"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-02",
                amount_check={"status": "matched", "oa_amount": "13.07", "bank_amount": "13.07", "amount_delta": "0.00"},
            )
            service = ExistingEtcBatchLinkService(
                etc_service=app._etc_service,
                import_service=app._import_service,
                pair_relation_service=app._workbench_pair_relation_service,
                sync_import_result_to_canonical_invoices=app._sync_etc_import_result_to_canonical_invoices,
                sync_etc_invoices_to_canonical_invoices=app._sync_etc_invoices_to_canonical_invoices,
                refresh_after_etc_invoice_sync=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )
            spec = ExistingEtcBatchLinkSpec(
                label="幂等 ETC 批次",
                case_id="CASE-IDEMPOTENT-ETC",
                external_batch_id="ETC-IDEMPOTENT-2026-02",
                oa_row_id="oa-idempotent-etc",
                bank_row_id="txn-idempotent-etc",
                oa_amount=Decimal("13.07"),
                bank_amount=Decimal("13.07"),
                invoice_numbers=("ETC001",),
            )

            first = service.link_existing_invoices(spec)
            second = service.link_existing_invoices(spec)
            relations = app._workbench_pair_relation_service.list_active_relations()
            batches = app._etc_service.list_batches(status="submitted")

        self.assertEqual(first.status, "ok")
        self.assertEqual(second.status, "ok")
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual([relation["case_id"] for relation in relations], ["CASE-IDEMPOTENT-ETC"])
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].etc_batch_id, "ETC-IDEMPOTENT-2026-02")

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
