from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, make_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
import json
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
import time
from types import SimpleNamespace
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from tests.app_test_support import build_local_state_application as _build_application, install_durable_import_queue
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services import etc_service as etc_service_module
from fin_ops_platform.services.etc_service import (
    EtcBusinessBatchActiveExistsError,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchStatus,
    EtcBusinessBatchVersionConflictError,
    EtcBusinessBatch,
    EtcDraftRequestError,
    EtcOAHttpClientSettings,
    EtcInvoiceStatus,
    EtcInvoiceNotFoundError,
    HttpEtcOAClient,
    EtcOAClient,
    EtcOAClientError,
    EtcOADraftOutcomeUnknownError,
    EtcService,
    UploadedEtcZipFile,
    parse_etc_xml,
)
from fin_ops_platform.app.routes_etc import EtcBusinessBatchApiRoutes
from fin_ops_platform.services.etc_business_batch_application_service import (
    EtcBusinessBatchActor,
    EtcBusinessBatchApplicationService,
    evaluate_etc_oa_draft_action,
)
from fin_ops_platform.services.etc_document_parsers import CcbCreditCardStatementParser, SupplementEvidenceParser, TicketRootPdfTextParser
from fin_ops_platform.services.etc_reconciliation_models import (
    EtcReconciliationTaskStatus,
    FileParseResult,
    SourceFileKind,
)
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.historical_etc_repair_service import (
    HistoricalEtcRepairBatchSpec,
    HistoricalEtcRepairService,
)
from fin_ops_platform.services.object_storage import ObjectStorageWriteError
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
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


def build_application(*args, **kwargs):
    application = _build_application(*args, **kwargs)
    application._test_import_queue = install_durable_import_queue(application)
    return application


def etc_xml(
    invoice_number: str,
    *,
    issue_date: str = "2026-02-27",
    passage_start_date: str | None = None,
    passage_end_date: str | None = None,
    plate_number: str = "云ADA0381",
    total_amount: str = "13.07",
    seller_name: str = "云南高速公路联网收费管理有限公司",
    buyer_name: str = "云南溯源科技有限公司",
) -> bytes:
    amount_without_tax = (Decimal(total_amount) - Decimal("0.39")).quantize(Decimal("0.01"))
    passage_start = passage_start_date or issue_date
    passage_end = passage_end_date or issue_date
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceNumber>{invoice_number}</InvoiceNumber>
  <IssueDate>{issue_date}</IssueDate>
  <PassageStartDate>{passage_start}</PassageStartDate>
  <PassageEndDate>{passage_end}</PassageEndDate>
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


class UnknownOutcomeEtcOAClient(FakeEtcOAClient):
    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        self.draft_payloads.append({"form_id": form_id, "payload": payload})
        raise EtcOADraftOutcomeUnknownError("OA result unknown")


class BlockingEtcOAClient(FakeEtcOAClient):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        self.started.set()
        if not self.release.wait(timeout=3):
            raise EtcOAClientError("test timeout")
        return super().create_form_draft(form_id=form_id, payload=payload)


class MemoryEtcStateStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.saved_snapshot: dict[str, object] | None = None
        self.files: dict[str, bytes] = {}

    def load_etc_state(self) -> dict[str, object]:
        return deepcopy(self.saved_snapshot or {})

    def save_etc_state(self, snapshot: dict[str, object]) -> None:
        self.saved_snapshot = deepcopy(snapshot)

    def save_etc_oa_draft_attempt(
        self,
        snapshot: dict[str, object],
        *,
        business_batch_id: str,
        expected_version: int,
    ) -> bool:
        current = dict(self.saved_snapshot or {})
        current_batch = dict(current.get("business_batches") or {}).get(business_batch_id)
        current_version = (
            current_batch.get("version")
            if isinstance(current_batch, dict)
            else getattr(current_batch, "version", None)
        )
        if int(current_version or 0) != int(expected_version):
            return False
        for collection in ("invoices", "batches", "import_batches", "business_batches"):
            merged = dict(current.get(collection) or {})
            merged.update(dict(snapshot.get(collection) or {}))
            current[collection] = merged
        for counter in ("invoice_counter", "batch_counter", "import_batch_counter", "business_batch_counter"):
            current[counter] = max(int(current.get(counter, 0) or 0), int(snapshot.get(counter, 0) or 0))
        day_counters = dict(current.get("batch_day_counters") or {})
        for day, value in dict(snapshot.get("batch_day_counters") or {}).items():
            day_counters[str(day)] = max(int(day_counters.get(str(day), 0) or 0), int(value or 0))
        current["batch_day_counters"] = day_counters
        self.saved_snapshot = deepcopy(current)
        return True

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


class PostgresLikeReconciliationStateStore(ApplicationStateStore):
    def __init__(self, data_dir: Path) -> None:
        super().__init__(data_dir)
        self.reconciliation_rows: dict[str, object] = {}
        self.reconciliation_task_counter = 0
        self.reconciliation_file_counter = 0
        self.reconciliation_audit_counter = 0

    def load_etc_reconciliation_state(self) -> dict:
        return {
            "schema_version": 1,
            "task_counter": self.reconciliation_task_counter,
            "file_counter": self.reconciliation_file_counter,
            "audit_counter": self.reconciliation_audit_counter,
            "tasks": dict(self.reconciliation_rows),
        }

    def save_etc_reconciliation_state(self, snapshot: dict) -> None:
        self.reconciliation_task_counter = int(snapshot.get("task_counter", 0) or 0)
        self.reconciliation_file_counter = int(snapshot.get("file_counter", 0) or 0)
        self.reconciliation_audit_counter = int(snapshot.get("audit_counter", 0) or 0)
        for task_id, payload in dict(snapshot.get("tasks") or {}).items():
            self.reconciliation_rows[str(task_id)] = payload
        super().save_etc_reconciliation_state(snapshot)


class EtcServiceTests(unittest.TestCase):
    def test_oa_draft_action_fails_closed_when_reconciliation_task_is_missing(self) -> None:
        batch = EtcBusinessBatch(
            business_batch_id="batch-missing-task",
            task_id="task-missing",
            status=EtcBusinessBatchStatus.IMPORTED.value,
            invoice_ids=["invoice-1"],
        )
        actor = EtcBusinessBatchActor(can_mutate_data=True)

        action = evaluate_etc_oa_draft_action(batch, None, actor)

        self.assertEqual(action["enabled"], False)
        self.assertEqual(action["code"], "reconciliation_task_missing")
        with self.assertRaisesRegex(EtcBusinessBatchInvalidTransitionError, "缺少绑定") as raised:
            EtcBusinessBatchApplicationService._assert_reconciliation_task_allows_oa_draft(None)
        self.assertEqual(raised.exception.code, "reconciliation_task_missing")

    def test_recovery_route_requires_a_real_boolean_and_exclusive_evidence(self) -> None:
        class FakeApplicationService:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def recover_oa_draft_payload(self, _batch_id: str, **payload: object) -> dict[str, object]:
                self.calls.append(payload)
                return {"status": "oa_confirmation_pending"}

        application_service = FakeApplicationService()
        routes = EtcBusinessBatchApiRoutes(
            application_service,  # type: ignore[arg-type]
            delete_service=None,  # type: ignore[arg-type]
            load_json_body=lambda _body: ({}, None),
            refresh_after_etc_invoice_link=lambda _months, _reason: None,
            persist_state=lambda: None,
        )
        session = SimpleNamespace(
            identity=SimpleNamespace(user_id="u-1", username="finance", dept_id="finance"),
            can_admin_access=True,
            can_mutate_data=True,
        )

        for invalid in ("false", 0, None):
            status, payload = routes.recover_oa_draft(
                "batch-1",
                {"confirmedNotCreated": invalid},
                session=session,  # type: ignore[arg-type]
            )
            self.assertEqual(status, 422)
            self.assertEqual(payload["error"]["code"], "invalid_oa_draft_recovery_decision")  # type: ignore[index]
        status, _payload = routes.recover_oa_draft(
            "batch-1",
            {"confirmedNotCreated": True, "draftId": "oa-1", "draftUrl": "https://oa.test/1"},
            session=session,  # type: ignore[arg-type]
        )
        self.assertEqual(status, 422)
        self.assertEqual(application_service.calls, [])

    def test_legacy_business_batch_pickle_drops_removed_oa_detection_status(self) -> None:
        current_batch_cls = etc_service_module.EtcBusinessBatch
        legacy_batch_cls = make_dataclass(
            "EtcBusinessBatch",
            [
                ("business_batch_id", str),
                ("task_id", str),
                ("status", str, EtcBusinessBatchStatus.DRAFT.value),
                ("version", int, 1),
                ("oa_detection_status", str, "legacy_detection_pending"),
            ],
            slots=True,
        )
        legacy_batch_cls.__module__ = etc_service_module.__name__
        legacy_batch_cls.__qualname__ = "EtcBusinessBatch"
        try:
            etc_service_module.EtcBusinessBatch = legacy_batch_cls
            legacy_payload = pickle.dumps(
                legacy_batch_cls(
                    business_batch_id="etc_business_batch_legacy",
                    task_id="ETC-RECON-LEGACY",
                    oa_detection_status="legacy_detection_pending",
                )
            )
        finally:
            etc_service_module.EtcBusinessBatch = current_batch_cls

        loaded = pickle.loads(legacy_payload)  # noqa: S301 - trusted legacy state fixture

        self.assertIsInstance(loaded, EtcBusinessBatch)
        self.assertEqual(loaded.business_batch_id, "etc_business_batch_legacy")
        self.assertEqual(loaded.task_id, "ETC-RECON-LEGACY")
        self.assertFalse(hasattr(loaded, "oa_detection_status"))
        self.assertEqual(loaded.import_batch_ids, [])
        self.assertEqual(loaded.amount_breakdown, {})

    def test_business_batch_create_list_detail_and_active_guard(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            batch = service.create_business_batch(task_id="ETC-TASK-001", title="高速费三月批次", owner_user_id="alice", owner_org_id="finance")

            self.assertEqual(batch.business_batch_id, "etc_business_batch_0001")
            self.assertEqual(batch.task_id, "ETC-TASK-001")
            self.assertEqual(batch.title, "高速费三月批次")
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

    def test_business_batch_title_update_persists_and_locks_submitted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            batch = service.create_business_batch(task_id="ETC-TASK-001", title="旧高速批次")

            updated = service.update_business_batch_title(
                batch.business_batch_id,
                title=" 高速费三月批次 ",
                expected_version=batch.version,
            )

            self.assertEqual(updated.title, "高速费三月批次")
            self.assertEqual(updated.version, batch.version + 1)
            self.assertEqual(service.business_batch_payload(updated)["title"], "高速费三月批次")
            self.assertIn("business_batch_title_updated", [event["event_type"] for event in updated.audit_events])
            reloaded = EtcService(data_dir=Path(temp_dir))
            self.assertEqual(reloaded.get_business_batch(batch.business_batch_id).title, "高速费三月批次")
            with self.assertRaises(EtcBusinessBatchVersionConflictError):
                service.update_business_batch_title(
                    batch.business_batch_id,
                    title="过期版本标题",
                    expected_version=batch.version,
                )
            with self.assertRaises(EtcBusinessBatchInvalidTransitionError) as blank_error:
                service.update_business_batch_title(
                    batch.business_batch_id,
                    title=" ",
                    expected_version=updated.version,
                )
            self.assertEqual(blank_error.exception.code, "invalid_business_batch_title")
            service._business_batches[batch.business_batch_id].status = EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value
            with self.assertRaises(EtcBusinessBatchInvalidTransitionError) as locked_error:
                service.update_business_batch_title(
                    batch.business_batch_id,
                    title="提交后标题",
                    expected_version=updated.version,
                )
            self.assertEqual(locked_error.exception.code, "business_batch_title_locked")

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

            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, idempotency_key="draft-merge-1", expected_version=batch.version)
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

            first = service.create_business_batch_oa_draft(batch.business_batch_id, idempotency_key="draft-idempotent-1", expected_version=batch.version)
            second = service.create_business_batch_oa_draft(first.business_batch_id, idempotency_key="draft-idempotent-1", expected_version=first.version)

            self.assertEqual(first.submission_batch_id, second.submission_batch_id)
            self.assertEqual(first.oa_draft_id, "oa-draft-001")
            self.assertEqual(second.status, EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value)
            self.assertEqual(len(fake_oa.draft_payloads), 1)
            cause = str(fake_oa.draft_payloads[0]["payload"]["data"]["cause"])
            self.assertIn(f"business_batch_id={batch.business_batch_id}", cause)

    def test_oa_draft_finalize_only_updates_its_target_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = MemoryEtcStateStore(data_dir)
            service_a = EtcService(data_dir=data_dir, state_store=store, oa_client=FakeEtcOAClient())

            imported_batches: list[EtcBusinessBatch] = []
            for task_id, invoice_number in (("ETC-TASK-A", "ETC-A"), ("ETC-TASK-B", "ETC-B")):
                batch = service_a.create_business_batch(task_id=task_id, title=task_id)
                preview = service_a.preview_business_batch_import_zips(
                    batch.business_batch_id,
                    [UploadedEtcZipFile(f"{invoice_number}.zip", etc_zip([invoice_number]))],
                    expected_version=batch.version,
                )
                batch, _result = service_a.confirm_business_batch_import(
                    batch.business_batch_id,
                    str(preview["sessionId"]),
                    expected_version=preview["businessBatch"]["version"],
                )
                imported_batches.append(batch)

            target, independent = imported_batches
            attempt = service_a.prepare_business_batch_oa_draft(
                target.business_batch_id,
                idempotency_key="target-scoped-finalize",
                expected_version=target.version,
                reconciliation_task=None,
            )
            self.assertIsNotNone(attempt)
            assert attempt is not None
            draft = service_a.execute_business_batch_oa_draft(attempt)

            service_b = EtcService(data_dir=data_dir, state_store=store)
            latest_independent = service_b.get_business_batch(independent.business_batch_id)
            service_b.update_business_batch_title(
                independent.business_batch_id,
                title="independent worker update",
                expected_version=latest_independent.version,
            )

            completed = service_a.complete_business_batch_oa_draft(attempt, draft)
            reloaded = EtcService(data_dir=data_dir, state_store=store)

            self.assertEqual(completed.status, EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value)
            self.assertEqual(
                reloaded.get_business_batch(independent.business_batch_id).title,
                "independent worker update",
            )

    def test_oa_draft_retry_repairs_task_metadata_without_creating_a_second_draft(self) -> None:
        class FlakyTaskService:
            def __init__(self, task_id: str) -> None:
                self.task = SimpleNamespace(
                    task_id=task_id,
                    status=EtcReconciliationTaskStatus.IMPORTED,
                    oa_draft_batch_id="",
                    etc_batch_id="",
                    oa_draft_status="",
                )
                self.record_calls = 0

            def get_task(self, _task_id: str):
                return self.task

            def record_oa_draft_created(
                self,
                *,
                task_id: str,
                oa_draft_batch_id: str,
                etc_batch_id: str,
                actor: str,
            ):
                del task_id, actor
                self.record_calls += 1
                if self.record_calls == 1:
                    raise RuntimeError("task metadata persistence failed")
                self.task.oa_draft_batch_id = oa_draft_batch_id
                self.task.etc_batch_id = etc_batch_id
                self.task.oa_draft_status = "draft_created"
                return self.task

        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            etc_service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            batch = etc_service.create_business_batch(task_id="ETC-TASK-REPAIR")
            preview = etc_service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("repair.zip", etc_zip(["ETC-REPAIR"]))],
                expected_version=batch.version,
            )
            batch, _result = etc_service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            task_service = FlakyTaskService(batch.task_id)
            application = EtcBusinessBatchApplicationService(
                etc_service=etc_service,
                reconciliation_task_service=task_service,
            )
            actor = EtcBusinessBatchActor(can_admin_access=True, can_mutate_data=True)

            with self.assertRaisesRegex(RuntimeError, "persistence failed"):
                application.create_oa_draft_payload(
                    batch.business_batch_id,
                    idempotency_key="repair-task-metadata",
                    expected_version=batch.version,
                    actor=actor,
                    headers=None,
                )
            pending = etc_service.get_business_batch(batch.business_batch_id)
            replay = application.create_oa_draft_payload(
                batch.business_batch_id,
                idempotency_key="repair-task-metadata",
                expected_version=batch.version,
                actor=actor,
                headers=None,
            )

            self.assertEqual(pending.status, EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value)
            self.assertEqual(replay["businessBatch"]["status"], EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value)
            self.assertEqual(task_service.record_calls, 2)
            self.assertEqual(len(fake_oa.draft_payloads), 1)

    def test_oa_recovery_replay_repairs_task_metadata_after_partial_failure(self) -> None:
        class FlakyTaskService:
            def __init__(self, task_id: str) -> None:
                self.task = SimpleNamespace(
                    task_id=task_id,
                    status=EtcReconciliationTaskStatus.IMPORTED,
                    oa_draft_batch_id="",
                    etc_batch_id="",
                    oa_draft_status="",
                )
                self.calls = 0

            def get_task(self, _task_id: str):
                return self.task

            def record_oa_draft_created(self, **payload: object):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("recovery metadata persistence failed")
                self.task.oa_draft_batch_id = str(payload["oa_draft_batch_id"])
                self.task.etc_batch_id = str(payload["etc_batch_id"])
                self.task.oa_draft_status = "draft_created"
                return self.task

        with TemporaryDirectory() as temp_dir:
            etc_service = EtcService(data_dir=Path(temp_dir))
            batch = etc_service.create_business_batch(task_id="ETC-TASK-RECOVERY-REPLAY")
            preview = etc_service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("recovery.zip", etc_zip(["ETC-RECOVERY"]))],
                expected_version=batch.version,
            )
            batch, _result = etc_service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            attempt = etc_service.prepare_business_batch_oa_draft(
                batch.business_batch_id,
                idempotency_key="recovery-replay",
                expected_version=batch.version,
                reconciliation_task=None,
            )
            assert attempt is not None
            unknown = etc_service.mark_business_batch_oa_draft_outcome_unknown(attempt, reason="timeout")
            task_service = FlakyTaskService(batch.task_id)
            application = EtcBusinessBatchApplicationService(
                etc_service=etc_service,
                reconciliation_task_service=task_service,
            )
            actor = EtcBusinessBatchActor(can_admin_access=True, can_mutate_data=True)
            recovery = {
                "expected_version": unknown.version,
                "reason": "OA 已核实",
                "evidence": "OA 草稿记录",
                "oa_draft_id": "oa-recovered-1",
                "oa_draft_url": "https://oa.test/recovered-1",
                "confirmed_not_created": False,
                "actor": actor,
            }

            with self.assertRaisesRegex(RuntimeError, "persistence failed"):
                application.recover_oa_draft_payload(batch.business_batch_id, **recovery)
            replay = application.recover_oa_draft_payload(batch.business_batch_id, **recovery)

            self.assertEqual(replay["businessBatch"]["status"], EtcBusinessBatchStatus.OA_CONFIRMATION_PENDING.value)
            self.assertEqual(task_service.calls, 2)

    def test_business_batch_oa_draft_unknown_outcome_requires_recovery_and_reuses_attempt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=UnknownOutcomeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-UNKNOWN")
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

            with self.assertRaises(EtcOADraftOutcomeUnknownError):
                service.create_business_batch_oa_draft(
                    batch.business_batch_id,
                    idempotency_key="draft-unknown-1",
                    expected_version=batch.version,
                )
            unknown = service.get_business_batch(batch.business_batch_id)
            submission_batch_id = unknown.submission_batch_id
            self.assertEqual(unknown.status, EtcBusinessBatchStatus.OA_DRAFT_CREATING.value)
            with self.assertRaises(EtcOADraftOutcomeUnknownError):
                service.create_business_batch_oa_draft(
                    batch.business_batch_id,
                    idempotency_key="draft-unknown-1",
                    expected_version=unknown.version,
                )

            recovered = service.recover_business_batch_oa_draft(
                batch.business_batch_id,
                expected_version=unknown.version,
                reason="管理员已核实 OA 无草稿",
                evidence="OA 管理后台按 business_batch_id 查询为零",
                oa_draft_id=None,
                oa_draft_url=None,
                confirmed_not_created=True,
            )
            service.oa_client = FakeEtcOAClient()
            completed = service.create_business_batch_oa_draft(
                batch.business_batch_id,
                idempotency_key="draft-unknown-2",
                expected_version=recovered.version,
            )
            self.assertEqual(completed.submission_batch_id, submission_batch_id)
            self.assertEqual(len(service.list_batches()), 1)

    def test_legacy_creating_batch_without_attempt_can_only_recover_as_not_created(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = MemoryEtcStateStore(data_dir)
            service = EtcService(data_dir=data_dir, state_store=store)
            batch = service.create_business_batch(task_id="ETC-TASK-LEGACY-RECOVERY")
            legacy_batch = service._business_batches[batch.business_batch_id]
            legacy_batch.status = EtcBusinessBatchStatus.OA_DRAFT_CREATING.value
            legacy_batch.version = 2
            legacy_batch.submission_batch_id = None
            legacy_batch.external_etc_batch_id = None
            service._persist()

            reloaded = EtcService(data_dir=data_dir, state_store=store)
            with self.assertRaises(EtcBusinessBatchInvalidTransitionError) as adoption_error:
                reloaded.recover_business_batch_oa_draft(
                    batch.business_batch_id,
                    expected_version=2,
                    reason="管理员核实历史请求",
                    evidence="OA 主集合按业务批次标记查询为零",
                    oa_draft_id="unexpected-draft",
                    oa_draft_url="https://oa.test/unexpected-draft",
                    confirmed_not_created=False,
                )
            self.assertEqual(adoption_error.exception.code, "oa_draft_attempt_missing")

            recovered = reloaded.recover_business_batch_oa_draft(
                batch.business_batch_id,
                expected_version=2,
                reason="管理员核实历史请求",
                evidence="OA 主集合按业务批次标记查询为零",
                oa_draft_id=None,
                oa_draft_url=None,
                confirmed_not_created=True,
            )

            self.assertEqual(recovered.status, EtcBusinessBatchStatus.OA_DRAFT_FAILED.value)
            self.assertEqual(recovered.version, 3)
            self.assertIsNone(recovered.submission_batch_id)
            self.assertEqual(
                recovered.audit_events[-1]["event_type"],
                "oa_draft_recovery_confirmed_not_created",
            )
            persisted = EtcService(data_dir=data_dir, state_store=store).get_business_batch(batch.business_batch_id)
            self.assertEqual(persisted.status, EtcBusinessBatchStatus.OA_DRAFT_FAILED.value)
            self.assertEqual(persisted.version, 3)

    def test_business_batch_oa_http_call_does_not_hold_business_lock(self) -> None:
        with TemporaryDirectory() as temp_dir:
            client = BlockingEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=client)
            batch = service.create_business_batch(task_id="ETC-TASK-LOCK")
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
            errors: list[Exception] = []

            def create_draft() -> None:
                try:
                    service.create_business_batch_oa_draft(
                        batch.business_batch_id,
                        idempotency_key="draft-lock-1",
                        expected_version=batch.version,
                    )
                except Exception as exc:  # pragma: no cover - assertion reports captured errors
                    errors.append(exc)

            worker = Thread(target=create_draft)
            worker.start()
            self.assertTrue(client.started.wait(timeout=2))
            self.assertTrue(service._business_batch_lock.acquire(timeout=0.2))
            service._business_batch_lock.release()
            client.release.set()
            worker.join(timeout=3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

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
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, idempotency_key="draft-revoke-1", expected_version=batch.version)

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

    def test_business_batch_delete_resets_submitted_batch_and_releases_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            batch = service.create_business_batch(task_id="ETC-TASK-001")
            preview = service.preview_business_batch_import_zips(
                batch.business_batch_id,
                [UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))],
                expected_version=batch.version,
            )
            batch, _result = service.confirm_business_batch_import(
                batch.business_batch_id,
                str(preview["sessionId"]),
                expected_version=preview["businessBatch"]["version"],
            )
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, idempotency_key="draft-delete-submitted-1", expected_version=batch.version)
            submitted = service.manual_business_batch_oa_status(
                batch.business_batch_id,
                decision="submitted",
                reason="用户确认 OA 草稿已提交。",
                expected_version=drafted.version,
            )

            deleted = service.delete_business_batch(
                batch.business_batch_id,
                expected_version=submitted.version,
                reason="用户确认删除已提交批次并释放 ETC 发票。",
            )
            invoices = service.list_invoices_by_ids(["etc_invoice_0001", "etc_invoice_0002"])
            submission_batch = service._batches[str(submitted.submission_batch_id)]
            import_batch = service.list_import_batches()[0]
            deleted_batch = service._business_batches[batch.business_batch_id]

            self.assertEqual(
                deleted,
                {
                    "deleted": True,
                    "businessBatchId": batch.business_batch_id,
                    "kind": "submitted_business_batch_reset",
                    "releasedInvoiceCount": 2,
                    "submissionBatchId": submitted.submission_batch_id,
                },
            )
            self.assertEqual(service.list_business_batches(), [])
            self.assertEqual(deleted_batch.status, EtcBusinessBatchStatus.DELETED.value)
            self.assertIsNone(deleted_batch.task_active_key)
            self.assertIn("submitted_business_batch_reset", [event["event_type"] for event in deleted_batch.audit_events])
            self.assertEqual(submission_batch.status, "not_submitted")
            self.assertIsNone(import_batch.submission_batch_id)
            self.assertEqual({invoice.status for invoice in invoices}, {EtcInvoiceStatus.UNSUBMITTED})
            self.assertEqual({invoice.current_batch_id for invoice in invoices}, {None})
            self.assertEqual({invoice.business_batch_id for invoice in invoices}, {None})
            self.assertEqual({invoice.last_batch_id for invoice in invoices}, {submitted.submission_batch_id})

    def test_create_historical_submitted_business_batch_links_existing_submission_to_new_model(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            service.import_zips([UploadedEtcZipFile("historical.zip", etc_zip(["ETC001", "ETC002"]))])
            submitted_batch = service.create_historical_submitted_batch(
                case_id="CASE-BATCH-txn_imported_1328",
                external_batch_id="ETC-OA-20260215-154900",
                invoice_numbers=["ETC001", "ETC002"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("1549.00"),
                note="existing relation",
            )

            business_batch = service.create_historical_submitted_business_batch(
                business_batch_id="etc_business_batch_hist_20260215_154900",
                task_id="ETC-RECON-HIST-20260215-154900",
                submission_batch_id=submitted_batch.id,
                external_etc_batch_id="ETC-OA-20260215-154900",
                reported_amount=Decimal("1549.00"),
                relation_case_id="CASE-BATCH-txn_imported_1328",
                linked_oa_row_id="oa-exp-1994",
                gap_reason="骑行费/非ETC发票差额",
                scope_month="2026-02",
            )
            replayed = service.create_historical_submitted_business_batch(
                business_batch_id="etc_business_batch_hist_20260215_154900",
                task_id="ETC-RECON-HIST-20260215-154900",
                submission_batch_id=submitted_batch.id,
                external_etc_batch_id="ETC-OA-20260215-154900",
                reported_amount=Decimal("1549.00"),
                relation_case_id="CASE-BATCH-txn_imported_1328",
                linked_oa_row_id="oa-exp-1994",
                gap_reason="骑行费/非ETC发票差额",
                scope_month="2026-02",
            )

            invoices = service.list_invoices_by_ids(["etc_invoice_0001", "etc_invoice_0002"])
            stored_submission = service._batches[submitted_batch.id]
            stored_business = service._business_batches[business_batch.business_batch_id]

            self.assertEqual(business_batch.business_batch_id, "etc_business_batch_hist_20260215_154900")
            self.assertEqual(replayed.business_batch_id, business_batch.business_batch_id)
            self.assertEqual(len(service.list_business_batches(status=EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value)), 1)
            self.assertEqual(business_batch.status, EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value)
            self.assertEqual(business_batch.task_id, "ETC-RECON-HIST-20260215-154900")
            self.assertEqual(business_batch.submission_batch_id, submitted_batch.id)
            self.assertEqual(business_batch.external_etc_batch_id, "ETC-OA-20260215-154900")
            self.assertEqual(business_batch.oa_row_id, "oa-exp-1994")
            self.assertEqual(business_batch.oa_process_status, "in_progress")
            self.assertEqual({invoice.business_batch_id for invoice in invoices}, {business_batch.business_batch_id})
            self.assertEqual({invoice.current_batch_id for invoice in invoices}, {submitted_batch.id})
            self.assertEqual({invoice.status for invoice in invoices}, {EtcInvoiceStatus.SUBMITTED})
            self.assertEqual(stored_submission.oa_total_amount, Decimal("1549.00"))
            self.assertEqual(stored_submission.etc_invoice_amount, Decimal("26.14"))
            self.assertEqual(stored_submission.etc_invoice_count, 2)
            self.assertEqual(stored_submission.amount_delta, Decimal("1522.86"))
            self.assertEqual(stored_business.amount_breakdown["reported_amount"], "1549.00")
            self.assertEqual(stored_business.amount_breakdown["etc_invoice_amount"], "26.14")
            self.assertEqual(stored_business.amount_breakdown["gap_amount"], "1522.86")
            self.assertEqual(stored_business.amount_breakdown["gap_reason"], "骑行费/非ETC发票差额")
            self.assertEqual(
                [event["event_type"] for event in stored_business.audit_events].count("historical_business_batch_migrated"),
                1,
            )

    def test_linked_submitted_business_batch_cannot_be_deleted_and_deleted_tombstone_can_be_restored(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir), oa_client=FakeEtcOAClient())
            service.import_zips([UploadedEtcZipFile("historical.zip", etc_zip(["ETC001", "ETC002"]))])
            submitted_batch = service.create_historical_submitted_batch(
                case_id="CASE-BATCH-txn_imported_0090",
                external_batch_id="etc_20260520_001",
                invoice_numbers=["ETC001", "ETC002"],
                linked_oa_row_id="oa-source-0004",
                oa_amount=Decimal("26.14"),
            )
            business_batch = service.create_historical_submitted_business_batch(
                business_batch_id="etc_business_batch_0004",
                task_id="ETC-RECON-0004",
                submission_batch_id=submitted_batch.id,
                external_etc_batch_id="etc_20260520_001",
                reported_amount=Decimal("26.14"),
                relation_case_id="CASE-BATCH-txn_imported_0090",
                linked_oa_row_id="oa-source-0004",
                scope_month="2026-05",
            )

            with self.assertRaises(EtcBusinessBatchInvalidTransitionError) as blocked:
                service.delete_business_batch(
                    business_batch.business_batch_id,
                    expected_version=business_batch.version,
                    reason="must not orphan an existing OA",
                )
            self.assertEqual(blocked.exception.code, "submitted_batch_linked_oa_delete_forbidden")

            tombstone = service._business_batches[business_batch.business_batch_id]
            service._reset_submitted_business_batch_for_delete(tombstone, reason="legacy reset before guard")
            tombstone.oa_row_id = None
            service._batches[submitted_batch.id].linked_oa_row_id = None
            preview = service.preview_deleted_submitted_business_batch_restore(
                business_batch.business_batch_id,
                expected_invoice_count=2,
                expected_total_amount=Decimal("26.14"),
                expected_oa_row_id=None,
                canonical_oa_row_id="oa-pay-2200",
                canonical_title="Recovered ETC batch",
            )
            self.assertEqual(preview["stored_oa_row_id"], "")
            restored = service.restore_deleted_submitted_business_batch(
                business_batch.business_batch_id,
                expected_version=int(preview["version"]),
                expected_invoice_count=2,
                expected_total_amount=Decimal("26.14"),
                expected_oa_row_id=None,
                canonical_oa_row_id="oa-pay-2200",
                canonical_title="Recovered ETC batch",
                reason="restore proven production tombstone",
            )
            tombstone = service._business_batches[business_batch.business_batch_id]
            submission = service._batches[submitted_batch.id]
            tombstone.title = None
            tombstone.oa_process_status = "manual_without_oa_row"
            submission.invoice_count = 3
            submission.etc_invoice_count = 3
            service._persist()
            normalization_preview = service.preview_deleted_submitted_business_batch_restore(
                business_batch.business_batch_id,
                expected_invoice_count=2,
                expected_total_amount=Decimal("26.14"),
                expected_oa_row_id="oa-pay-2200",
                canonical_oa_row_id="oa-pay-2200",
                canonical_title="Recovered ETC batch",
            )
            replayed = service.restore_deleted_submitted_business_batch(
                business_batch.business_batch_id,
                expected_version=int(normalization_preview["version"]),
                expected_invoice_count=2,
                expected_total_amount=Decimal("26.14"),
                expected_oa_row_id="oa-pay-2200",
                canonical_oa_row_id="oa-pay-2200",
                canonical_title="Recovered ETC batch",
                reason="idempotent retry",
            )
            unchanged = service.restore_deleted_submitted_business_batch(
                business_batch.business_batch_id,
                expected_version=replayed.version,
                expected_invoice_count=2,
                expected_total_amount=Decimal("26.14"),
                expected_oa_row_id="oa-pay-2200",
                canonical_oa_row_id="oa-pay-2200",
                canonical_title="Recovered ETC batch",
                reason="idempotent retry after normalization",
            )
            invoices = service.list_invoices_by_ids(["etc_invoice_0001", "etc_invoice_0002"])
            normalized_submission = service.get_batch(submitted_batch.id)

            self.assertEqual(restored.status, EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value)
            self.assertEqual(restored.oa_row_id, "oa-pay-2200")
            self.assertEqual(restored.oa_process_status, "in_progress")
            self.assertEqual(replayed.version, restored.version + 1)
            self.assertEqual(unchanged.version, replayed.version)
            self.assertEqual(replayed.title, "Recovered ETC batch")
            self.assertEqual(replayed.oa_process_status, "in_progress")
            self.assertEqual(normalized_submission.invoice_count, 2)
            self.assertEqual(normalized_submission.etc_invoice_count, 2)
            self.assertEqual(normalized_submission.total_amount, Decimal("26.14"))
            self.assertEqual(normalized_submission.oa_total_amount, Decimal("26.14"))
            self.assertEqual(normalized_submission.etc_invoice_amount, Decimal("26.14"))
            self.assertEqual(normalized_submission.amount_delta, Decimal("0.00"))
            self.assertEqual(restored.submission_batch_id, submitted_batch.id)
            self.assertEqual({invoice.status for invoice in invoices}, {EtcInvoiceStatus.SUBMITTED})
            self.assertEqual({invoice.current_batch_id for invoice in invoices}, {submitted_batch.id})
            self.assertEqual({invoice.business_batch_id for invoice in invoices}, {business_batch.business_batch_id})
            self.assertEqual(
                [event["event_type"] for event in replayed.audit_events][-1],
                "deleted_submitted_business_batch_restore_normalized",
            )

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
            drafted = service.create_business_batch_oa_draft(batch.business_batch_id, idempotency_key="draft-delete-1", expected_version=batch.version)

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

    def test_http_oa_client_normalizes_known_absolute_attachment_urls(self) -> None:
        upload_urls = iter(
            [
                "http://127.0.0.1:9300/fileManager/2026/05/20/internal.pdf",
                "https://www.yn-sourcing.com/oa-api/fileManager/2026/05/20/public.pdf",
            ]
        )

        def fake_urlopen(request: object, *, timeout: float) -> FakeHTTPResponse:
            return FakeHTTPResponse({"code": 200, "data": {"url": next(upload_urls)}})

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invoice.pdf"
            path.write_bytes(b"%PDF-1.4\n")
            client = HttpEtcOAClient(
                token="oa-token",
                settings=EtcOAHttpClientSettings(base_url="https://www.yn-sourcing.com/oa-api"),
            )
            with patch("fin_ops_platform.services.etc_service.urlopen", fake_urlopen):
                internal_path = client.upload_attachment(path)
                public_path = client.upload_attachment(path)

        self.assertEqual(internal_path, "/fileManager/2026/05/20/internal.pdf")
        self.assertEqual(public_path, "/fileManager/2026/05/20/public.pdf")

    def test_http_oa_client_rejects_unexpected_absolute_attachment_host(self) -> None:
        def fake_urlopen(request: object, *, timeout: float) -> FakeHTTPResponse:
            return FakeHTTPResponse({"code": 200, "data": {"url": "https://files.example.test/fileManager/invoice.pdf"}})

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "invoice.pdf"
            path.write_bytes(b"%PDF-1.4\n")
            client = HttpEtcOAClient(
                token="oa-token",
                settings=EtcOAHttpClientSettings(base_url="https://www.yn-sourcing.com/oa-api"),
            )
            with patch("fin_ops_platform.services.etc_service.urlopen", fake_urlopen):
                with self.assertRaises(EtcOAClientError):
                    client.upload_attachment(path)

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

    def test_service_filters_invoices_by_import_batch_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            service.import_zips([UploadedEtcZipFile("first.zip", etc_zip(["ETC001"]))])
            first_batch_id = service.list_import_batches()[0].id
            service.import_zips([UploadedEtcZipFile("second.zip", etc_zip(["ETC002"]))])
            second_batch_id = service.list_import_batches()[1].id

            first_invoices, first_total, first_counts = service.list_invoices(
                import_batch_id=first_batch_id,
                page=1,
                page_size=20,
            )
            second_invoices, second_total, _second_counts = service.list_invoices(
                import_batch_id=second_batch_id,
                page=1,
                page_size=20,
            )

        self.assertEqual(first_total, 1)
        self.assertEqual([invoice.invoice_number for invoice in first_invoices], ["ETC001"])
        self.assertEqual(first_counts["current"], 1)
        self.assertEqual(second_total, 1)
        self.assertEqual([invoice.invoice_number for invoice in second_invoices], ["ETC002"])

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

    def test_etc_invoice_list_serializer_does_not_probe_attachment_storage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            class RaisingEtcService:
                def _stored_invoice_file_exists(self, _path: str) -> bool:
                    raise AssertionError("list serialization must not probe attachment storage")

            app._etc_service = RaisingEtcService()
            payload = app._serialize_etc_invoice(
                {
                    "id": "etc_invoice_0001",
                    "invoice_number": "ETC001",
                    "pdf_file_path": "minio://bucket/etc/ETC001.pdf",
                    "xml_file_path": "minio://bucket/etc/ETC001.xml",
                }
            )

        self.assertTrue(payload["has_pdf"])
        self.assertTrue(payload["has_xml"])

    def test_preview_does_not_download_verified_object_attachments_for_existing_invoices(self) -> None:
        class NoPreviewProbeStore(MemoryEtcStateStore):
            def etc_invoice_file_exists(self, _stored_file_path: str) -> bool:
                raise AssertionError("preview must not download verified object attachments")

        with TemporaryDirectory() as temp_dir:
            store = NoPreviewProbeStore(Path(temp_dir))
            service = EtcService(state_store=store)
            service.import_zips([UploadedEtcZipFile("initial.zip", etc_zip(["ETC001"]))])
            invoice = service._invoices["etc_invoice_0001"]
            invoice.xml_file_path = "minio://fin-ops-files/objects/etc_invoice/ETC001.xml"
            invoice.pdf_file_path = "minio://fin-ops-files/objects/etc_invoice/ETC001.pdf"

            preview = service.preview_import_zips(
                [UploadedEtcZipFile("duplicate.zip", etc_zip(["ETC001"]))]
            )

        self.assertEqual(
            preview["summary"],
            {"imported": 0, "duplicatesSkipped": 1, "attachmentsCompleted": 0, "failed": 0},
        )

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

    def test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate(self) -> None:
        entries: dict[str, bytes] = {}
        for index in range(1, 121):
            invoice_number = f"ETC{index:03d}"
            entries[f"xml/{invoice_number}.xml"] = etc_xml(invoice_number)
            entries[f"pdf/{invoice_number}.pdf"] = fake_pdf(invoice_number)
        entries["xml/ETC001-copy.xml"] = etc_xml("ETC001")
        entries["bad/malformed.xml"] = b"<Invoice>"

        with TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            preview = service.preview_import_zips([UploadedEtcZipFile("mixed-large-ticket-root.zip", zip_bytes(entries))])
            invoices, total, _counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(preview["summary"], {"imported": 120, "duplicatesSkipped": 1, "attachmentsCompleted": 0, "failed": 1})
        self.assertEqual(preview["audit"]["original_count"], 122)
        self.assertEqual(preview["audit"]["unique_count"], 120)
        self.assertEqual(preview["audit"]["duplicate_in_file_count"], 1)
        self.assertEqual(preview["audit"]["error_count"], 1)
        self.assertEqual(preview["audit"]["importable_count"], 120)
        self.assertEqual(preview["audit"]["confirmable_count"], 120)
        self.assertEqual(preview["audit"]["skipped_count"], 2)
        self.assertEqual(len(preview["items"]), 122)
        failed_items = [item for item in preview["items"] if item["status"] == "failed"]
        self.assertEqual(len(failed_items), 1)
        self.assertIn("XML 解析失败", failed_items[0]["message"])
        self.assertEqual(total, 0)
        self.assertEqual(invoices, [])

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

    def test_batch_status_mark_not_submitted_and_draft_creation_with_fake_oa_client(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001", "ETC002"]))])

            draft = service.create_oa_draft(["etc_invoice_0001", "etc_invoice_0002"])
            after_draft, _total, _counts = service.list_invoices(page=1, page_size=20)
            confirmed = service.confirm_submitted(draft.batch_id)
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

    def test_delete_submitted_batch_releases_local_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            fake_oa = FakeEtcOAClient()
            service = EtcService(data_dir=Path(temp_dir), oa_client=fake_oa)
            service.import_zips([UploadedEtcZipFile("invoices.zip", etc_zip(["ETC001"]))])
            draft = service.create_oa_draft(["etc_invoice_0001"])
            service.confirm_submitted(draft.batch_id)

            result = service.delete_batch(draft.batch_id)
            invoices, _total, counts = service.list_invoices(page=1, page_size=20)

        self.assertEqual(result, {"deleted": True, "batchId": draft.batch_id, "kind": "submission_batch"})
        self.assertEqual(service.list_batches(), [])
        self.assertEqual({invoice.status for invoice in invoices}, {EtcInvoiceStatus.UNSUBMITTED})
        self.assertEqual({invoice.current_batch_id for invoice in invoices}, {None})
        self.assertEqual(counts["unsubmitted"], 1)

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
    def test_etc_query_services_reload_worker_writes_from_postgres_state_store(self) -> None:
        class SharedPostgresEtcStateStore(MemoryEtcStateStore):
            storage_backend = "postgres"

            def __init__(self, data_dir: Path) -> None:
                super().__init__(data_dir)
                self.reconciliation_snapshot: dict[str, object] = {}

            def load_etc_reconciliation_state(self) -> dict[str, object]:
                return dict(self.reconciliation_snapshot)

            def save_etc_reconciliation_state(self, snapshot: dict[str, object]) -> None:
                self.reconciliation_snapshot = dict(snapshot)

        with TemporaryDirectory() as temp_dir:
            store = SharedPostgresEtcStateStore(Path(temp_dir))
            api_task_service = EtcReconciliationTaskService(state_store=store)
            api_etc_service = EtcService(state_store=store)
            worker_task_service = EtcReconciliationTaskService(state_store=store)
            worker_etc_service = EtcService(state_store=store)

            task = worker_task_service.create_task(title="worker imported ETC", created_by="worker")
            batch = worker_etc_service.create_business_batch(task_id=task.task_id, title=task.title)
            worker_etc_service.import_zips([
                UploadedEtcZipFile(
                    "worker.zip",
                    zip_bytes({
                        "xml/ETC-WORKER-001.xml": etc_xml("ETC-WORKER-001"),
                        "pdf/ETC-WORKER-001.pdf": fake_pdf("ETC-WORKER-001"),
                    }),
                )
            ])

            invoices, total, _counts = api_etc_service.list_invoices()

        self.assertEqual(api_task_service.get_task(task.task_id).task_id, task.task_id)
        self.assertEqual(api_etc_service.get_business_batch(batch.business_batch_id).business_batch_id, batch.business_batch_id)
        self.assertEqual(total, 1)
        self.assertEqual(invoices[0].invoice_number, "ETC-WORKER-001")

    def _wait_for_job(self, app, job_id: str, *, timeout: float = 2.0) -> dict[str, object]:
        app._test_import_queue.process_all(raise_errors=False)
        deadline = time.monotonic() + timeout
        payload: dict[str, object] = {}
        while time.monotonic() < deadline:
            response = app.handle_request("GET", f"/api/background-jobs/{job_id}")
            payload = json.loads(response.body)
            job = payload.get("job", {})
            if isinstance(job, dict) and job.get("status") in {"succeeded", "partial_success", "failed"}:
                wait_for_completion = getattr(app._background_job_service, "wait_for_job_completion", None)
                if callable(wait_for_completion):
                    wait_for_completion(job_id, timeout=max(0.1, deadline - time.monotonic()))
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
        business_batch = json.loads(
            app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
        )["data"]["items"][0]
        draft_response = app.handle_request(
            "POST",
            f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
            json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-supplement-helper"}),
        )
        return task_id, json.loads(draft_response.body)["data"]["businessBatch"]

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

            payload = app._etc_reconciliation_task_payload_facade().task_payload(live_task)

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

    def test_delete_reconciliation_source_file_route_cleans_orphan_parse_result(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(
                    file_id="ORPHAN-CARD-FILE",
                    text=CCB_STATEMENT_TEXT,
                ),
                actor="alice",
            )

            response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task.task_id}/source-files/ORPHAN-CARD-FILE",
                json.dumps({"expectedVersion": task.version, "actor": "alice"}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["sourceFiles"], [])
        self.assertEqual(payload["creditCardItems"], [])
        self.assertEqual(payload["auditEvents"][-1]["event_type"], "orphan_parse_result_deleted")

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
                "fin_ops_platform.services.etc_reconciliation_source_upload_service.TicketRootDocumentParser.parse_file",
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

    def test_ticket_root_upload_route_imports_txt_file_with_clipboard_parser(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)
            body, headers = multipart(
                {"云ADA0381.txt": TICKET_ROOT_CLIPBOARD_TEXT.encode("utf-8")},
                fields={"expectedVersion": str(created["version"])},
            )

            with patch(
                "fin_ops_platform.services.etc_reconciliation_source_upload_service.TicketRootDocumentParser.parse_file",
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
        self.assertEqual(payload["sourceFiles"][0]["originalName"], "云ADA0381.txt")
        self.assertEqual(payload["sourceFiles"][0]["contentType"], "text/plain; charset=utf-8")
        self.assertEqual(len(payload["ticketRootItems"]), 1)
        self.assertEqual(payload["ticketRootItems"][0]["vehicle_plate"], "云ADA0381")
        self.assertEqual(payload["ticketRootItems"][0]["amount"], "71.25")
        self.assertEqual(payload["ticketRootItems"][0]["extraction_method"], "clipboard_text")
        self.assertEqual(payload["parseIssues"], [])

    def test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)
            body, headers = multipart(
                {"云A516HJ-4月.txt": TICKET_ROOT_CLIPBOARD_TEXT.replace("云ADA0381", "云A516HJ").encode("gb18030")},
                fields={"expectedVersion": str(created["version"])},
            )

            with patch(
                "fin_ops_platform.services.etc_reconciliation_source_upload_service.TicketRootDocumentParser.parse_file",
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
        self.assertEqual(payload["sourceFiles"][0]["originalName"], "云A516HJ-4月.txt")
        self.assertTrue(payload["sourceFiles"][0]["contentType"].startswith("text/plain"))
        self.assertFalse(payload["sourceFiles"][0]["hasBlockingIssue"])
        self.assertEqual(len(payload["ticketRootItems"]), 1)
        self.assertEqual(payload["ticketRootItems"][0]["vehicle_plate"], "云A516HJ")
        self.assertEqual(payload["ticketRootItems"][0]["amount"], "71.25")
        self.assertEqual(payload["ticketRootItems"][0]["extraction_method"], "clipboard_text")
        self.assertEqual(payload["parseIssues"], [])

    def test_ticket_root_txt_file_upload_returns_structured_storage_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)

            def fail_store(**_kwargs: object) -> str:
                raise ObjectStorageWriteError("object storage unavailable")

            app._state_store.store_etc_reconciliation_file = fail_store
            body, headers = multipart(
                {"云ADA0381.txt": TICKET_ROOT_CLIPBOARD_TEXT.encode("utf-8")},
                fields={"expectedVersion": str(created["version"])},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-files",
                body=body,
                headers=headers,
            )
            stored_task = app._etc_reconciliation_task_service.get_task(created["taskId"])

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "reconciliation_file_storage_unavailable")
        self.assertIn("文件存储", payload["message"])
        self.assertEqual(stored_task.source_files, [])

    def test_ticket_root_text_route_returns_structured_storage_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            created = json.loads(app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                json.dumps({"title": "ETC", "createdBy": "alice"}),
            ).body)

            def fail_store(**_kwargs: object) -> str:
                raise ObjectStorageWriteError("object storage unavailable")

            app._state_store.store_etc_reconciliation_file = fail_store

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{created['taskId']}/ticket-root-texts",
                json.dumps(
                    {
                        "expectedVersion": created["version"],
                        "entries": [{"clientId": "paste-1", "text": TICKET_ROOT_CLIPBOARD_TEXT}],
                    },
                    ensure_ascii=False,
                ),
            )
            stored_task = app._etc_reconciliation_task_service.get_task(created["taskId"])

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "reconciliation_file_storage_unavailable")
        self.assertIn("文件存储", payload["message"])
        self.assertEqual(stored_task.source_files, [])

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

    def test_deleted_reconciliation_task_route_does_not_reappear_after_postgres_rehydrate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresLikeReconciliationStateStore(Path(temp_dir))
            with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
                app = build_application(data_dir=Path(temp_dir))
                created = json.loads(app.handle_request(
                    "POST",
                    "/api/etc/reconciliation-tasks",
                    body=json.dumps({"title": "待删除"}),
                ).body)
                deleted = app.handle_request(
                    "DELETE",
                    f"/api/etc/reconciliation-tasks/{created['taskId']}",
                    body=json.dumps({"expectedVersion": created["version"]}),
                )
                reloaded_app = build_application(data_dir=Path(temp_dir))
                list_response = reloaded_app.handle_request("GET", "/api/etc/reconciliation-tasks")
                next_created = json.loads(reloaded_app.handle_request(
                    "POST",
                    "/api/etc/reconciliation-tasks",
                    body=json.dumps({"title": "新批次"}),
                ).body)

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(json.loads(list_response.body)["tasks"], [])
        self.assertNotEqual(next_created["taskId"], created["taskId"])
        self.assertTrue(next_created["taskId"].endswith("000002"))

    def test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresLikeReconciliationStateStore(Path(temp_dir))
            with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
                app = build_application(data_dir=Path(temp_dir))
                created_task = json.loads(app.handle_request(
                    "POST",
                    "/api/etc/reconciliation-tasks",
                    body=json.dumps({"title": "待删除批次"}),
                ).body)
                created_batch = json.loads(app.handle_request(
                    "POST",
                    "/api/etc/business-batches",
                    json.dumps({"taskId": created_task["taskId"]}),
                ).body)["data"]["businessBatch"]
                deleted = app.handle_request(
                    "DELETE",
                    f"/api/etc/business-batches/{created_batch['businessBatchId']}",
                    json.dumps({
                        "expectedVersion": created_batch["version"],
                        "reason": "delete_batch_should_tombstone_task",
                    }),
                )
                reloaded_app = build_application(data_dir=Path(temp_dir))
                task_list = json.loads(reloaded_app.handle_request("GET", "/api/etc/reconciliation-tasks").body)
                business_batches = json.loads(reloaded_app.handle_request("GET", "/api/etc/business-batches").body)
                next_created = json.loads(reloaded_app.handle_request(
                    "POST",
                    "/api/etc/reconciliation-tasks",
                    body=json.dumps({"title": "重新新建批次"}),
                ).body)

        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(json.loads(deleted.body)["data"], {
            "deleted": True,
            "businessBatchId": created_batch["businessBatchId"],
            "kind": "business_batch",
        })
        self.assertEqual(task_list["tasks"], [])
        self.assertEqual(business_batches["data"]["items"], [])
        self.assertNotEqual(next_created["taskId"], created_task["taskId"])
        self.assertTrue(next_created["taskId"].endswith("000002"))

    def test_business_batch_create_without_task_id_creates_linked_task_and_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresLikeReconciliationStateStore(Path(temp_dir))
            with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
                app = build_application(data_dir=Path(temp_dir))
                create_response = app.handle_request(
                    "POST",
                    "/api/etc/business-batches",
                    json.dumps({"title": "新建高速批次"}),
                )
                self.assertEqual(create_response.status_code, 201, create_response.body)
                created = json.loads(create_response.body)["data"]["businessBatch"]
                task_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{created['taskId']}")
                active_batches = json.loads(
                    app.handle_request("GET", "/api/etc/business-batches?bucket=unsubmitted").body
                )["data"]
                reloaded_app = build_application(data_dir=Path(temp_dir))
                reloaded_batches = json.loads(
                    reloaded_app.handle_request("GET", "/api/etc/business-batches?bucket=unsubmitted").body
                )["data"]

        self.assertEqual(create_response.status_code, 201)
        self.assertTrue(created["taskId"].startswith("ETC-RECON-"))
        self.assertEqual(created["title"], "新建高速批次")
        self.assertEqual(created["status"], "draft")
        self.assertEqual(task_response.status_code, 200)
        task_payload = json.loads(task_response.body)
        self.assertEqual(task_payload["taskId"], created["taskId"])
        self.assertEqual(task_payload["title"], "新建高速批次")
        self.assertEqual(active_batches["total"], 1)
        self.assertEqual(active_batches["items"][0]["businessBatchId"], created["businessBatchId"])
        self.assertEqual(active_batches["items"][0]["title"], "新建高速批次")
        self.assertEqual(reloaded_batches["total"], 1)
        self.assertEqual(reloaded_batches["items"][0]["taskId"], created["taskId"])
        self.assertEqual(reloaded_batches["items"][0]["title"], "新建高速批次")

    def test_business_batch_title_patch_updates_linked_task_title(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresLikeReconciliationStateStore(Path(temp_dir))
            with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
                app = build_application(data_dir=Path(temp_dir))
                created = json.loads(app.handle_request(
                    "POST",
                    "/api/etc/business-batches",
                    json.dumps({"title": "旧高速批次"}),
                ).body)["data"]["businessBatch"]
                patch_response = app.handle_request(
                    "PATCH",
                    f"/api/etc/business-batches/{created['businessBatchId']}",
                    json.dumps({"title": " 高速费三月批次 ", "expectedVersion": created["version"]}),
                )
                patched = json.loads(patch_response.body)["data"]["businessBatch"]
                task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{created['taskId']}").body)
                blank_response = app.handle_request(
                    "PATCH",
                    f"/api/etc/business-batches/{created['businessBatchId']}",
                    json.dumps({"title": " ", "expectedVersion": patched["version"]}),
                )
                app._etc_service._business_batches[created["businessBatchId"]].status = EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value
                locked_response = app.handle_request(
                    "PATCH",
                    f"/api/etc/business-batches/{created['businessBatchId']}",
                    json.dumps({"title": "提交后标题", "expectedVersion": patched["version"]}),
                )
                reloaded_app = build_application(data_dir=Path(temp_dir))
                reloaded_batch = json.loads(reloaded_app.handle_request(
                    "GET",
                    f"/api/etc/business-batches/{created['businessBatchId']}",
                ).body)["data"]["businessBatch"]
                reloaded_task = json.loads(reloaded_app.handle_request("GET", f"/api/etc/reconciliation-tasks/{created['taskId']}").body)

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patched["title"], "高速费三月批次")
        self.assertEqual(patched["version"], created["version"] + 1)
        self.assertEqual(task_payload["title"], "高速费三月批次")
        self.assertEqual(blank_response.status_code, 422)
        self.assertEqual(json.loads(blank_response.body)["error"]["code"], "invalid_business_batch_title")
        self.assertEqual(locked_response.status_code, 422)
        self.assertEqual(json.loads(locked_response.body)["error"]["code"], "business_batch_title_locked")
        self.assertEqual(reloaded_batch["title"], "高速费三月批次")
        self.assertEqual(reloaded_task["title"], "高速费三月批次")

    def test_business_batch_create_without_task_id_tombstones_created_task_when_batch_create_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PostgresLikeReconciliationStateStore(Path(temp_dir))
            with patch("fin_ops_platform.app.server.build_state_store", return_value=store):
                app = build_application(data_dir=Path(temp_dir))

                def fail_create_business_batch(**_kwargs: object) -> object:
                    raise EtcBusinessBatchInvalidTransitionError("forced create failure.", code="forced_create_failure")

                app._etc_service.create_business_batch = fail_create_business_batch
                response = app.handle_request(
                    "POST",
                    "/api/etc/business-batches",
                    json.dumps({}),
                )
                task_list = json.loads(app.handle_request("GET", "/api/etc/reconciliation-tasks").body)
                reloaded_app = build_application(data_dir=Path(temp_dir))
                reloaded_task_list = json.loads(reloaded_app.handle_request("GET", "/api/etc/reconciliation-tasks").body)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(json.loads(response.body)["error"]["code"], "forced_create_failure")
        self.assertEqual(task_list["tasks"], [])
        self.assertEqual(reloaded_task_list["tasks"], [])

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

    def test_etc_business_batch_oa_draft_revoke_route_resets_batch_and_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            task = app._etc_reconciliation_task_service.create_task(title="ETC-TASK-REVOKE", created_by="alice")
            app._etc_reconciliation_task_service._get_active_task_mutable(task.task_id).status = (  # noqa: SLF001
                EtcReconciliationTaskStatus.IMPORTED
            )
            app._etc_reconciliation_task_service._persist()  # noqa: SLF001

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": task.task_id, "ownerUserId": "alice", "ownerOrgId": "finance"}),
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
                json.dumps({"expectedVersion": confirmed["version"], "idempotencyKey": "draft-revoke-route"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            revoke_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/oa-draft/revoke",
                json.dumps({"expectedVersion": drafted["version"], "reason": "补充漏导发票"}),
            )
            revoked_payload = json.loads(revoke_response.body)
            invoice = app._etc_service.list_invoices_by_ids(["etc_invoice_0001"])[0]

        self.assertEqual(revoke_response.status_code, 200)
        self.assertTrue(revoked_payload["ok"])
        revoked = revoked_payload["data"]["businessBatch"]
        self.assertEqual(revoked["status"], "not_submitted")
        self.assertIsNone(revoked["submissionBatchId"])
        self.assertIsNone(revoked["oaDraftId"])
        self.assertIsNone(invoice.current_batch_id)
        self.assertEqual(invoice.status, EtcInvoiceStatus.UNSUBMITTED)

    def test_etc_business_batch_detail_returns_invoice_items_without_detection_fields(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            try:
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
            finally:
                app.close()

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        detail = json.loads(detail_response.body)["data"]["businessBatch"]
        self.assertEqual(detail["invoiceItems"][0]["invoice_number"], "ETC001")
        self.assertNotIn("oaDetectionStatus", detail)
        self.assertNotIn("oaDetectionReason", detail)
        self.assertNotIn("oaDetectionError", detail)
        self.assertNotIn("oaDetectionStartedAt", detail)
        self.assertNotIn("oaDetectionNextRunAt", detail)
        self.assertNotIn("oaDetectionDeadlineAt", detail)
        self.assertNotIn("oaDetectionFinalRetryUntil", detail)

    def test_etc_business_batch_list_and_detail_keep_fixed_io_budgets_for_65_invoices(self) -> None:
        invoice_numbers = [f"ETC-PERF-{index:03d}" for index in range(65)]
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            try:
                create_response = app.handle_request(
                    "POST",
                    "/api/etc/business-batches",
                    json.dumps({"taskId": "ETC-TASK-PERF"}),
                )
                created = json.loads(create_response.body)["data"]["businessBatch"]
                preview_body, preview_headers = multipart(
                    {"invoices.zip": etc_zip(invoice_numbers)},
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
                with (
                    patch.object(
                        app._state_store,
                        "read_etc_invoice_file",
                        wraps=app._state_store.read_etc_invoice_file,
                    ) as read_invoice_file,
                    patch.object(
                        app._state_store,
                        "etc_invoice_file_exists",
                        wraps=app._state_store.etc_invoice_file_exists,
                    ) as invoice_file_exists,
                ):
                    list_response = app.handle_request(
                        "GET",
                        "/api/etc/business-batches?bucket=unsubmitted&page=1&page_size=100",
                    )
                    detail_response = app.handle_request(
                        "GET",
                        f"/api/etc/business-batches/{created['businessBatchId']}",
                    )
            finally:
                app.close()

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(list_response.status_code, 200)
        self.assertLessEqual(len(list_response.body.encode("utf-8")), 250 * 1024)
        list_payload = json.loads(list_response.body)["data"]
        self.assertEqual(list_payload["total"], 1)
        self.assertEqual(list_payload["items"][0]["invoiceSummary"]["count"], 65)
        self.assertNotIn("invoiceIds", list_payload["items"][0])
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)["data"]["businessBatch"]
        self.assertEqual(len(detail_payload["invoiceItems"]), 65)
        read_invoice_file.assert_not_called()
        invoice_file_exists.assert_not_called()

        invoice_ids = [f"etc_invoice_{index:04d}" for index in range(1, 66)]
        fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
        fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        batch_payload = {
            "business_batch_id": "ETC-BATCH-PERF-SQL",
            "task_id": "ETC-TASK-PERF-SQL",
            "status": "imported",
            "invoice_ids": invoice_ids,
            "title": "65 张 ETC 发票查询预算",
            "created_at": "2026-07-18T00:00:00+00:00",
            "version": 1,
        }

        def fetch_all(sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
            normalized_sql = " ".join(sql.split())
            fetch_all_calls.append((normalized_sql, params))
            if "group by bucket" in normalized_sql:
                return [{
                    "bucket": "unsubmitted",
                    "count": 1,
                    "etc_invoice_count": 65,
                    "business_batch_count": 9,
                    "unsubmitted_batch_count": 6,
                    "draft_batch_count": 1,
                    "submitted_batch_count": 2,
                    "reconciliation_task_count": 4,
                    "source_file_count": 7,
                    "imported_invoice_count": 60,
                    "linked_canonical_invoice_count": 58,
                    "oa_draft_batch_count": 2,
                }]
            if "select batch_payload, task_payload" in normalized_sql:
                return [{
                    "batch_payload": batch_payload,
                    "task_payload": {"task_id": "ETC-TASK-PERF-SQL", "status": "imported"},
                    "scope_month": None,
                    "invoice_count": 65,
                    "total_amount": "849.55",
                }]
            if "from app.etc_invoices" in normalized_sql:
                return [
                    {
                        "etc_invoice_id": invoice_id,
                        "raw_payload": {
                            "id": invoice_id,
                            "invoice_number": invoice_number,
                            "total_amount": "13.07",
                        },
                    }
                    for invoice_id, invoice_number in zip(invoice_ids, invoice_numbers, strict=True)
                ]
            raise AssertionError(f"unexpected fetch_all SQL: {normalized_sql}")

        def fetch_one(sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
            normalized_sql = " ".join(sql.split())
            fetch_one_calls.append((normalized_sql, params))
            if "from app.etc_business_batches" in normalized_sql:
                return {"raw_payload": batch_payload}
            if "from app.etc_reconciliation_tasks" in normalized_sql:
                return {"raw_payload": {"task_id": "ETC-TASK-PERF-SQL", "status": "imported"}}
            raise AssertionError(f"unexpected fetch_one SQL: {normalized_sql}")

        repository = PostgresOpsTaxEtcRepository(
            SimpleNamespace(fetch_all=fetch_all, fetch_one=fetch_one),
        )
        list_payload = repository.list_etc_business_batch_summaries(
            bucket="unsubmitted",
            page=1,
            page_size=100,
            can_admin_access=True,
        )
        list_query_count = len(fetch_all_calls) + len(fetch_one_calls)
        list_count_sql = fetch_all_calls[0][0]
        list_page_sql = fetch_all_calls[1][0]
        self.assertIn("%s::boolean", list_count_sql)
        self.assertIn("any(%s::text[])", list_count_sql)
        self.assertIn("(%s::text is null or task_id = %s::text)", list_count_sql)
        self.assertIn("scope_month = to_date(%s::text, 'YYYY-MM')", list_count_sql)
        self.assertIn("lower(%s::text)", list_count_sql)
        self.assertIn("where bucket = %s::text", list_page_sql)
        self.assertIn("limit %s::integer offset %s::integer", list_page_sql)
        self.assertIn("left join app.etc_import_batches import_batch", list_count_sql)
        self.assertIn("invoice.raw_payload->'normalized_payload'->>'import_batch_id'", list_count_sql)
        self.assertIn("count(*) filter (where import_batch.batch_id is not null)", list_count_sql)
        self.assertIn("count(*) filter (where oa_draft_id is not null)", list_count_sql)
        self.assertEqual(list_count_sql.count("from app.etc_business_batches"), 1)
        self.assertNotIn("jsonb_array_elements_text", list_count_sql)
        self.assertNotIn("cross join lateral unnest", list_count_sql)
        self.assertEqual(list_payload["counts"]["unsubmitted"], 1)
        self.assertEqual(list_payload["statistics"]["business_batch_count"], 9)
        self.assertEqual(list_payload["statistics"]["invoice_count"], 65)
        repository.get_etc_business_batch_record("ETC-BATCH-PERF-SQL")
        repository.list_etc_invoice_records_by_ids(invoice_ids)
        repository.get_etc_reconciliation_task_record("ETC-TASK-PERF-SQL")
        detail_query_count = len(fetch_all_calls) + len(fetch_one_calls) - list_query_count

        self.assertEqual(list_query_count, 2)
        self.assertEqual(detail_query_count, 3)

    def test_etc_business_batch_summaries_use_one_repeatable_read_only_snapshot(self) -> None:
        snapshot_calls: list[tuple[str, tuple[object, ...]]] = []
        transaction_count = 0

        class SnapshotConnection:
            def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
                snapshot_calls.append((" ".join(sql.split()), params))

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
                normalized_sql = " ".join(sql.split())
                snapshot_calls.append((normalized_sql, params))
                if "group by bucket" in normalized_sql:
                    return [{
                        "bucket": "unsubmitted",
                        "count": 1,
                        "etc_invoice_count": 2,
                        "business_batch_count": 1,
                        "unsubmitted_batch_count": 1,
                        "draft_batch_count": 0,
                        "submitted_batch_count": 0,
                        "reconciliation_task_count": 1,
                        "source_file_count": 1,
                        "imported_invoice_count": 2,
                        "linked_canonical_invoice_count": 2,
                        "oa_draft_batch_count": 0,
                    }]
                if "select batch_payload, task_payload" in normalized_sql:
                    return [{
                        "batch_payload": {
                            "business_batch_id": "ETC-BATCH-SNAPSHOT",
                            "task_id": "ETC-TASK-SNAPSHOT",
                            "status": "imported",
                            "invoice_ids": ["invoice-1", "invoice-2"],
                            "created_at": "2026-07-22T00:00:00+00:00",
                            "version": 1,
                        },
                        "task_payload": {"task_id": "ETC-TASK-SNAPSHOT", "status": "imported"},
                        "scope_month": None,
                        "invoice_count": 2,
                        "total_amount": "26.14",
                    }]
                raise AssertionError(f"unexpected fetch_all SQL: {normalized_sql}")

        snapshot_connection = SnapshotConnection()

        class Transaction:
            def __enter__(self) -> SnapshotConnection:
                return snapshot_connection

            def __exit__(self, *_args: object) -> None:
                return None

        class RootConnection:
            def transaction(self) -> Transaction:
                nonlocal transaction_count
                transaction_count += 1
                return Transaction()

            def fetch_all(self, *_args: object, **_kwargs: object) -> list[dict[str, object]]:
                raise AssertionError("ETC summary queries must use the snapshot connection")

        payload = PostgresOpsTaxEtcRepository(RootConnection()).list_etc_business_batch_summaries(
            bucket="unsubmitted",
            page=1,
            page_size=20,
            can_admin_access=True,
        )

        self.assertEqual(transaction_count, 1)
        self.assertEqual(snapshot_calls[0], ("set transaction isolation level repeatable read read only", ()))
        self.assertEqual(len([call for call in snapshot_calls if call[0] != snapshot_calls[0][0]]), 2)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["statistics"]["invoice_count"], 2)
        self.assertEqual(
            payload["items"][0]["business_batch"]["business_batch_id"],
            "ETC-BATCH-SNAPSHOT",
        )

    def test_etc_business_batch_scope_uses_session_dept_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
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

    def test_etc_business_batch_oa_draft_waits_for_manual_confirmation_without_detection_runtime(self) -> None:
        from fin_ops_platform.services.runtime_worker_registry import RUNTIME_WORKER_REGISTRY

        class QueueRecorder:
            def __init__(self) -> None:
                self.events: list[dict[str, object]] = []

            def enqueue(self, **kwargs):
                self.events.append(dict(kwargs))
                return {"event_id": f"evt-{len(self.events)}"}

        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            task = app._etc_reconciliation_task_service.create_task(title="ETC-TASK-QUEUE", created_by="alice")
            app._etc_reconciliation_task_service._get_active_task_mutable(task.task_id).status = (  # noqa: SLF001
                EtcReconciliationTaskStatus.IMPORTED
            )
            app._etc_reconciliation_task_service._persist()  # noqa: SLF001
            queue = QueueRecorder()
            object.__setattr__(app._runtime_repositories, "queue_repository", queue)

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": task.task_id}),
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
                json.dumps({"expectedVersion": confirmed["version"], "idempotencyKey": "draft-manual-wait"}),
            )
            draft_payload = json.loads(draft_response.body)["data"]["businessBatch"]
            refresh_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/oa-status/refresh",
                json.dumps({"expectedVersion": draft_payload["version"]}),
            )
            registry_instance_names = {registration.instance_name for registration in RUNTIME_WORKER_REGISTRY}
            registry_event_types = {
                event_type
                for registration in RUNTIME_WORKER_REGISTRY
                for event_type in registration.event_types
            }

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["status"], "oa_confirmation_pending")
        self.assertNotIn("oaDetectionStatus", draft_payload)
        self.assertNotIn("oaDetectionReason", draft_payload)
        self.assertEqual(refresh_response.status_code, 404)
        self.assertEqual(queue.events, [])
        self.assertNotIn("etc-business-oa-detection", registry_instance_names)
        self.assertNotIn("etc_business.oa_detection.refresh", registry_event_types)

    def test_etc_business_batch_source_files_append_to_reconciliation_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
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

    def test_etc_business_batch_source_file_upload_returns_structured_storage_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC source files", created_by="alice")
            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": task.task_id}),
            )
            created = json.loads(create_response.body)["data"]["businessBatch"]

            def fail_store(**_kwargs: object) -> str:
                raise ObjectStorageWriteError("object storage unavailable")

            app._state_store.store_etc_reconciliation_file = fail_store
            body, headers = multipart({"ticket-root.zip": b"zip-bytes"})

            response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/source-files",
                body,
                headers,
            )
            task_after_upload = app._etc_reconciliation_task_service.get_task(task.task_id)

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "reconciliation_file_storage_unavailable")
        self.assertIn("文件存储", payload["error"]["message"])
        self.assertEqual(task_after_upload.source_files, [])

    def test_etc_business_manual_status_accepts_confirmation_pending_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            status_refreshes: list[tuple[list[str], str]] = []
            try:
                app._etc_service.oa_client = FakeEtcOAClient()
                app._etc_service.import_zips([UploadedEtcZipFile("draft.zip", etc_zip(["ETC001"]))])
                batch = app._etc_service.create_business_batch(task_id="ETC-TASK-MANUAL")
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
                    idempotency_key="draft-manual-state",
                    expected_version=imported.version,
                )
                app._etc_business_application_service()._refresh_after_etc_business_batch_status_change = (  # noqa: SLF001
                    lambda months, reason: status_refreshes.append((list(months), str(reason)))
                )

                response = app.handle_request(
                    "POST",
                    f"/api/etc/business-batches/{drafted.business_batch_id}/manual-oa-status",
                    json.dumps({
                        "decision": "submitted",
                        "reason": "用户确认 OA 草稿已提交。",
                        "expectedVersion": drafted.version,
                    }),
                )
                payload = json.loads(response.body)["data"]["businessBatch"]
            finally:
                app.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "manually_marked_submitted")
        self.assertEqual(payload["oaProcessStatus"], "manual_without_oa_row")
        self.assertEqual(status_refreshes, [(["2026-02"], "etc_business_manual_oa_status")])

    def test_etc_business_manual_submitted_closes_the_linked_reconciliation_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            self.assertEqual(preview_response.status_code, 200)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            business_batches = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
            )["data"]["items"]
            business_batch = business_batches[0]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-close-task"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]

            manual_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{drafted['businessBatchId']}/manual-oa-status",
                json.dumps({
                    "decision": "submitted",
                    "reason": "用户确认 OA 草稿已提交。",
                    "expectedVersion": drafted["version"],
                }),
            )
            manual_payload = json.loads(manual_response.body)["data"]["businessBatch"]
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)
            active_batches = json.loads(app.handle_request("GET", "/api/etc/business-batches?bucket=unsubmitted").body)["data"]
            submitted_batches = json.loads(app.handle_request("GET", "/api/etc/business-batches?bucket=submitted").body)["data"]

        self.assertEqual(manual_response.status_code, 200)
        self.assertEqual(manual_payload["status"], "manually_marked_submitted")
        self.assertEqual(task_payload["status"], "closed")
        self.assertEqual(task_payload["oaDraftStatus"], "submitted_confirmed")
        self.assertIsNotNone(task_payload["submittedConfirmedAt"])
        self.assertEqual(active_batches["total"], 0)
        self.assertEqual(submitted_batches["total"], 1)
        self.assertEqual(submitted_batches["items"][0]["businessBatchId"], manual_payload["businessBatchId"])

    def test_etc_business_batch_submitted_list_counts_use_filtered_passage_month(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()
            task = app._etc_reconciliation_task_service.create_task(title="ETC passage month", created_by="alice")
            app._etc_reconciliation_task_service._get_active_task_mutable(task.task_id).status = (  # noqa: SLF001
                EtcReconciliationTaskStatus.IMPORTED
            )
            app._etc_reconciliation_task_service._persist()  # noqa: SLF001

            create_response = app.handle_request(
                "POST",
                "/api/etc/business-batches",
                json.dumps({"taskId": task.task_id, "ownerUserId": "alice", "ownerOrgId": "finance"}),
            )
            self.assertEqual(create_response.status_code, 201)
            created = json.loads(create_response.body)["data"]["businessBatch"]
            body, headers = multipart(
                {
                    "etc.zip": zip_bytes(
                        {
                            "xml/ETC-PASSAGE-APRIL.xml": etc_xml(
                                "ETC-PASSAGE-APRIL",
                                issue_date="2026-05-20",
                                passage_start_date="2026-03-28",
                                passage_end_date="2026-04-27",
                                total_amount="1673.30",
                            ),
                            "pdf/ETC-PASSAGE-APRIL.pdf": fake_pdf("ETC-PASSAGE-APRIL"),
                        }
                    )
                },
                fields={"expectedVersion": str(created["version"])},
            )
            preview_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/preview",
                body,
                headers,
            )
            preview_payload = json.loads(preview_response.body)["data"]
            confirm_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{created['businessBatchId']}/etc-import/confirm",
                json.dumps({
                    "sessionId": preview_payload["sessionId"],
                    "expectedVersion": preview_payload["businessBatch"]["version"],
                }),
            )
            business_batch = json.loads(confirm_response.body)["data"]["businessBatch"]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-month-filter"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            manual_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{drafted['businessBatchId']}/manual-oa-status",
                json.dumps({
                    "decision": "submitted",
                    "reason": "用户确认 OA 草稿已提交。",
                    "expectedVersion": drafted["version"],
                }),
            )
            april_payload = json.loads(
                app.handle_request("GET", "/api/etc/business-batches?bucket=submitted&month=2026-04").body
            )["data"]
            june_payload = json.loads(
                app.handle_request("GET", "/api/etc/business-batches?bucket=submitted&month=2026-06").body
            )["data"]

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(manual_response.status_code, 200)
        self.assertEqual(april_payload["counts"], {"unsubmitted": 0, "staged": 0, "submitted": 1})
        self.assertEqual(april_payload["total"], 1)
        self.assertEqual(april_payload["items"][0]["businessBatchId"], business_batch["businessBatchId"])
        self.assertEqual(june_payload["counts"], {"unsubmitted": 0, "staged": 0, "submitted": 0})
        self.assertEqual(june_payload["total"], 0)
        self.assertEqual(june_payload["items"], [])

    def test_etc_business_batch_submitted_list_prefers_scope_month_when_available(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_zips([
                UploadedEtcZipFile(
                    "historical-cross-month.zip",
                    zip_bytes({
                        "xml/ETC-SCOPE-JAN.xml": etc_xml(
                            "ETC-SCOPE-JAN",
                            issue_date="2026-02-01",
                            passage_start_date="2026-01-31",
                            passage_end_date="2026-03-01",
                            total_amount="11.00",
                        ),
                        "pdf/ETC-SCOPE-JAN.pdf": fake_pdf("ETC-SCOPE-JAN"),
                        "xml/ETC-SCOPE-FEB.xml": etc_xml(
                            "ETC-SCOPE-FEB",
                            issue_date="2026-02-05",
                            passage_start_date="2026-01-31",
                            passage_end_date="2026-03-01",
                            total_amount="22.00",
                        ),
                        "pdf/ETC-SCOPE-FEB.pdf": fake_pdf("ETC-SCOPE-FEB"),
                        "xml/ETC-SCOPE-MAR.xml": etc_xml(
                            "ETC-SCOPE-MAR",
                            issue_date="2026-02-10",
                            passage_start_date="2026-01-31",
                            passage_end_date="2026-03-01",
                            total_amount="33.00",
                        ),
                        "pdf/ETC-SCOPE-MAR.pdf": fake_pdf("ETC-SCOPE-MAR"),
                    }),
                )
            ])
            expected_by_month = {
                "2026-01": ("ETC-OA-20260114-187293", "ETC-SCOPE-JAN", "11.00"),
                "2026-02": ("ETC-OA-20260215-154900", "ETC-SCOPE-FEB", "22.00"),
                "2026-03": ("ETC-OA-20260312-193545", "ETC-SCOPE-MAR", "33.00"),
            }
            for scope_month, (external_batch_id, invoice_number, amount) in expected_by_month.items():
                submitted_batch = app._etc_service.create_historical_submitted_batch(
                    case_id=f"CASE-{scope_month}",
                    external_batch_id=external_batch_id,
                    invoice_numbers=[invoice_number],
                    linked_oa_row_id=f"oa-{scope_month}",
                    oa_amount=Decimal(amount),
                )
                app._etc_service.create_historical_submitted_business_batch(
                    business_batch_id=f"etc_business_batch_hist_{scope_month.replace('-', '')}",
                    task_id=f"ETC-RECON-HIST-{scope_month}",
                    submission_batch_id=submitted_batch.id,
                    external_etc_batch_id=external_batch_id,
                    reported_amount=Decimal(amount),
                    relation_case_id=f"CASE-{scope_month}",
                    linked_oa_row_id=f"oa-{scope_month}",
                    scope_month=scope_month,
                )

            payloads = {
                month: json.loads(
                    app.handle_request("GET", f"/api/etc/business-batches?bucket=submitted&month={month}").body
                )["data"]
                for month in expected_by_month
            }

        for month, payload in payloads.items():
            expected_external_batch_id = expected_by_month[month][0]
            self.assertEqual(payload["counts"], {"unsubmitted": 0, "staged": 0, "submitted": 1})
            self.assertEqual(payload["total"], 1)
            self.assertEqual([item["externalEtcBatchId"] for item in payload["items"]], [expected_external_batch_id])

    def test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            self.assertEqual(preview_response.status_code, 200)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            business_batch = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
            )["data"]["items"][0]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-delete-summary"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            submission_batch = app._etc_service._batches[str(drafted["submissionBatchId"])]
            submission_batch.total_amount = Decimal("1673.30")
            submission_batch.oa_total_amount = Decimal("1673.30")
            submission_batch.etc_invoice_amount = Decimal("27.14")
            submission_batch.etc_invoice_count = 2
            submission_batch.display_count_text = "ETC票 2 + 补充凭证 0"
            manual_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{drafted['businessBatchId']}/manual-oa-status",
                json.dumps({
                    "decision": "submitted",
                    "reason": "用户确认 OA 草稿已提交。",
                    "expectedVersion": drafted["version"],
                }),
            )
            manual_payload = json.loads(manual_response.body)["data"]["businessBatch"]
            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/business-batches/{manual_payload['businessBatchId']}",
                json.dumps({
                    "expectedVersion": manual_payload["version"],
                    "reason": "用户删除已提交 ETC 批次并释放发票。",
                }),
            )
            submitted_batches = json.loads(app.handle_request("GET", "/api/etc/business-batches?bucket=submitted").body)["data"]
            active_batches = json.loads(app.handle_request("GET", "/api/etc/business-batches?bucket=unsubmitted").body)["data"]
            task_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")
            canonical_invoices = {invoice.digital_invoice_no: invoice for invoice in app._import_service.list_invoices()}
            etc_invoices = app._etc_service.list_invoices_by_ids(["etc_invoice_0001", "etc_invoice_0002"])

        self.assertEqual(manual_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = json.loads(delete_response.body)["data"]
        self.assertEqual(delete_payload["kind"], "submitted_business_batch_reset")
        self.assertEqual(delete_payload["releasedInvoiceCount"], 2)
        self.assertEqual(submitted_batches["total"], 0)
        self.assertEqual(active_batches["total"], 0)
        self.assertEqual(task_response.status_code, 404)
        self.assertEqual(canonical_invoices, {})
        self.assertEqual({invoice.status for invoice in etc_invoices}, {EtcInvoiceStatus.UNSUBMITTED})
        self.assertEqual({invoice.current_batch_id for invoice in etc_invoices}, {None})

    def test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            self.assertEqual(preview_response.status_code, 200)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            business_batch = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
            )["data"]["items"][0]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-delete-relation"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            submission_batch = app._etc_service._batches[str(drafted["submissionBatchId"])]
            submission_batch.total_amount = Decimal("1673.30")
            submission_batch.oa_total_amount = Decimal("1673.30")
            submission_batch.etc_invoice_amount = Decimal("27.14")
            submission_batch.etc_invoice_count = 2
            submission_batch.display_count_text = "ETC票 2 + 补充凭证 0"
            manual_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{drafted['businessBatchId']}/manual-oa-status",
                json.dumps({
                    "decision": "submitted",
                    "reason": "用户确认 OA 草稿已提交。",
                    "expectedVersion": drafted["version"],
                }),
            )
            manual_payload = json.loads(manual_response.body)["data"]["businessBatch"]
            summary_row_id = app._etc_invoice_summary_row_id(manual_payload["externalEtcBatchId"])
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-ETC-DELETE-OLD",
                row_ids=["oa-etc-delete", "txn-etc-delete"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                created_at="2026-02-15T09:00:00+00:00",
            )
            app._workbench_pair_relation_service.replace_with_confirmed_relation(
                case_id="CASE-ETC-DELETE",
                row_ids=["oa-etc-delete", "txn-etc-delete", summary_row_id],
                row_types=["oa", "bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                note="ETC三栏配对",
                amount_check={
                    "status": "matched",
                    "external_etc_batch_id": manual_payload["externalEtcBatchId"],
                    "invoice_total": "1673.30",
                },
                created_at="2026-02-15T10:00:00+00:00",
            )
            app._persist_workbench_pair_relations(changed_case_ids=["CASE-ETC-DELETE-OLD", "CASE-ETC-DELETE"])

            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/business-batches/{manual_payload['businessBatchId']}",
                json.dumps({
                    "expectedVersion": manual_payload["version"],
                    "reason": "用户删除已提交 ETC 批次并取消三栏配对。",
                }),
            )
            relation_for_summary = app._workbench_pair_relation_service.get_active_relation_by_row_id(summary_row_id)
            relation_for_oa = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-etc-delete")
            history = app._workbench_pair_relation_service.list_history()

        self.assertEqual(manual_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertIsNone(relation_for_summary)
        self.assertIsNone(relation_for_oa)
        self.assertTrue(any(entry.get("operation_type") == "etc_summary_unmerged" for entry in history))

    def test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            batch = SimpleNamespace(
                business_batch_id="etc_business_batch_command",
                submission_batch_id="etc_batch_command",
                external_etc_batch_id="ETC-COMMAND-202602",
            )
            summary_row_id = app._etc_invoice_summary_row_id("ETC-COMMAND-202602")
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-ETC-COMMAND",
                row_ids=["oa-etc-command", "txn-etc-command", summary_row_id],
                row_types=["oa", "bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                note="ETC三栏配对",
            )
            original_cancel_relation = app._workbench_pair_relation_service.cancel_relation

            def forbidden_direct_cancel(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("ETC summary relation cancel must not use direct pair service batch cancel.")

            app._workbench_pair_relation_service.cancel_active_relations_for_row_ids = forbidden_direct_cancel

            class FreshRelationFacade:
                def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                    self.requested_row_ids = list(row_ids)
                    return {
                        "read_model_status": "fresh",
                        "read_model_scope_keys": ["2026-02"],
                        "stale_reasons": [],
                        "refresh_enqueued": False,
                        "rows": [
                            {
                                "row_id": summary_row_id,
                                "group_ids": ["CASE-ETC-COMMAND"],
                            }
                        ],
                        "groups": [
                            {
                                "group_id": "CASE-ETC-COMMAND",
                                "scope_month": "2026-02",
                                "payload": {
                                    "relation_mode": "manual_confirmed",
                                    "row_ids": ["oa-etc-command", "txn-etc-command", summary_row_id],
                                    "row_types": ["oa", "bank", "invoice"],
                                    "amount_check": {"external_etc_batch_id": "ETC-COMMAND-202602"},
                                },
                            }
                        ],
                        "source_versions": {},
                    }

            class RecordingRelationCommandService:
                def __init__(self) -> None:
                    self.cancel_calls: list[dict[str, object]] = []

                def cancel_relation(self, **kwargs: object) -> dict[str, object]:
                    self.cancel_calls.append(dict(kwargs))
                    relation = original_cancel_relation(str(kwargs["case_id"]))
                    return {
                        "status": "cancelled",
                        "relation": relation,
                        "changed_case_ids": [str(kwargs["case_id"])],
                        "affected_months": ["2026-02"],
                        "read_model_status": "fresh",
                        "read_model_stale_reasons": [],
                        "read_model_scope_keys": ["2026-02"],
                        "refresh_enqueued": False,
                    }

            command_service = RecordingRelationCommandService()
            persisted_case_ids: list[list[str]] = []
            app._workbench_relation_read_facade = lambda: FreshRelationFacade()
            app._workbench_relation_command_service = lambda **_kwargs: command_service
            app._persist_workbench_pair_relations = lambda *, changed_case_ids: persisted_case_ids.append(list(changed_case_ids))

            changed_months = app._cancel_etc_summary_relations_for_batch(batch)
            active_after = app._workbench_pair_relation_service.get_active_relation_by_row_id(summary_row_id)

        self.assertEqual(changed_months, ["2026-02"])
        self.assertIsNone(active_after)
        self.assertEqual(len(command_service.cancel_calls), 1)
        self.assertEqual(command_service.cancel_calls[0]["case_id"], "CASE-ETC-COMMAND")
        self.assertEqual(command_service.cancel_calls[0]["history_operation_type"], "etc_summary_unmerged")
        self.assertEqual(persisted_case_ids, [["CASE-ETC-COMMAND"]])

    def test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            batch = app._etc_service.create_business_batch(task_id="ETC-STALE-TASK")
            mutable_batch = app._etc_service._business_batches[batch.business_batch_id]
            mutable_batch.status = EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value
            mutable_batch.external_etc_batch_id = "ETC-STALE-202602"
            mutable_batch.submission_batch_id = "etc_batch_stale"
            mutable_batch.amount_breakdown = {"scope_month": "2026-02"}
            summary_row_id = app._etc_invoice_summary_row_id("ETC-STALE-202602")
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-ETC-STALE",
                row_ids=["oa-etc-stale", "txn-etc-stale", summary_row_id],
                row_types=["oa", "bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                note="ETC三栏配对",
            )

            class StaleRelationFacade:
                def get_by_row_ids(self, _row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                    return {
                        "status": "stale",
                        "read_model_status": "stale",
                        "read_model_scope_keys": ["2026-02"],
                        "stale_reasons": ["test_stale_relation_projection"],
                        "refresh_enqueued": True,
                        "rows": [],
                        "groups": [],
                    }

            app._workbench_relation_read_facade = lambda: StaleRelationFacade()

            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/business-batches/{batch.business_batch_id}",
                json.dumps({
                    "expectedVersion": 1,
                    "reason": "用户删除已提交 ETC 批次并取消三栏配对。",
                }),
            )
            response_payload = json.loads(delete_response.body)
            relation_after = app._workbench_pair_relation_service.get_active_relation_by_row_id(summary_row_id)
            with self.assertRaises(EtcBusinessBatchNotFoundError):
                app._etc_service.get_business_batch(batch.business_batch_id)

        self.assertEqual(delete_response.status_code, 200, delete_response.body)
        self.assertEqual(response_payload["data"]["deleted"], True)
        self.assertIsNone(relation_after)

    def test_reconciliation_task_delete_cancels_submitted_business_summary_relation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            self.assertEqual(preview_response.status_code, 200)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            business_batch = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
            )["data"]["items"][0]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-task-delete"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            submission_batch = app._etc_service._batches[str(drafted["submissionBatchId"])]
            submission_batch.total_amount = Decimal("1673.30")
            submission_batch.oa_total_amount = Decimal("1673.30")
            submission_batch.etc_invoice_amount = Decimal("27.14")
            submission_batch.etc_invoice_count = 2
            submission_batch.display_count_text = "ETC票 2 + 补充凭证 0"
            manual_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{drafted['businessBatchId']}/manual-oa-status",
                json.dumps({
                    "decision": "submitted",
                    "reason": "用户确认 OA 草稿已提交。",
                    "expectedVersion": drafted["version"],
                }),
            )
            manual_payload = json.loads(manual_response.body)["data"]["businessBatch"]
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)
            summary_row_id = app._etc_invoice_summary_row_id(manual_payload["externalEtcBatchId"])
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-ETC-TASK-DELETE-OLD",
                row_ids=["oa-etc-task-delete", "txn-etc-task-delete"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                created_at="2026-02-15T09:00:00+00:00",
            )
            app._workbench_pair_relation_service.replace_with_confirmed_relation(
                case_id="CASE-ETC-TASK-DELETE",
                row_ids=["oa-etc-task-delete", "txn-etc-task-delete", summary_row_id],
                row_types=["oa", "bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="finance",
                month_scope="2026-02",
                note="ETC三栏配对",
                amount_check={
                    "status": "matched",
                    "external_etc_batch_id": manual_payload["externalEtcBatchId"],
                    "invoice_total": "1673.30",
                },
                created_at="2026-02-15T10:00:00+00:00",
            )
            app._persist_workbench_pair_relations(changed_case_ids=["CASE-ETC-TASK-DELETE-OLD", "CASE-ETC-TASK-DELETE"])

            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                json.dumps({"expectedVersion": task_payload["version"]}),
            )
            missing_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")
            relation_for_summary = app._workbench_pair_relation_service.get_active_relation_by_row_id(summary_row_id)
            relation_for_oa = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-etc-task-delete")
            history = app._workbench_pair_relation_service.list_history()

        self.assertEqual(manual_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(missing_response.status_code, 404)
        self.assertIsNone(relation_for_summary)
        self.assertIsNone(relation_for_oa)
        self.assertTrue(any(entry.get("operation_type") == "etc_summary_unmerged" for entry in history))

    def test_reconciliation_task_delete_removes_orphan_submission_metadata_link(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.oa_client = FakeEtcOAClient()

            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            self.assertEqual(preview_response.status_code, 200)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            self._wait_for_job(app, json.loads(confirm_response.body)["job"]["job_id"])
            business_batch = json.loads(
                app.handle_request("GET", f"/api/etc/business-batches?taskId={task_id}").body
            )["data"]["items"][0]
            draft_response = app.handle_request(
                "POST",
                f"/api/etc/business-batches/{business_batch['businessBatchId']}/oa-draft",
                json.dumps({"expectedVersion": business_batch["version"], "idempotencyKey": "draft-orphan-link"}),
            )
            drafted = json.loads(draft_response.body)["data"]["businessBatch"]
            submission_batch = app._etc_service._batches[str(drafted["submissionBatchId"])]
            submission_batch.confirmed_at = datetime.now(UTC)
            app._etc_service._business_batches.pop(str(drafted["businessBatchId"]))
            task_payload = json.loads(app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}").body)

            delete_response = app.handle_request(
                "DELETE",
                f"/api/etc/reconciliation-tasks/{task_id}",
                json.dumps({"expectedVersion": task_payload["version"]}),
            )
            missing_response = app.handle_request("GET", f"/api/etc/reconciliation-tasks/{task_id}")
            invoices = json.loads(app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20").body)

        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(json.loads(delete_response.body), {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(invoices["total"], 0)
        self.assertEqual(app._etc_service.list_import_batches(), [])
        self.assertEqual(app._etc_service.list_batches(), [])
        self.assertEqual(app._import_service.list_invoices(), [])

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

    def test_credit_card_statement_upload_returns_structured_storage_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC upload", created_by="alice")

            def fail_store(**_kwargs: object) -> str:
                raise ObjectStorageWriteError("object storage unavailable")

            app._state_store.store_etc_reconciliation_file = fail_store
            body, headers = multipart(
                {"statement.pdf": b"%PDF-1.4\n%%EOF"},
                fields={"expectedVersion": str(task.version)},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/credit-card-statement",
                body=body,
                headers=headers,
            )
            stored_task = app._etc_reconciliation_task_service.get_task(task.task_id)

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "reconciliation_file_storage_unavailable")
        self.assertIn("文件存储", payload["message"])
        self.assertEqual(stored_task.source_files, [])

    def test_credit_card_statement_upload_parses_pdf_and_returns_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC upload", created_by="alice")
            body, headers = multipart(
                {"statement.pdf": b"%PDF-1.4\n%%EOF"},
                fields={"expectedVersion": str(task.version)},
            )

            with patch(
                "fin_ops_platform.services.etc_document_parsers._extract_pdf_text",
                return_value=CCB_STATEMENT_TEXT,
            ):
                response = app.handle_request(
                    "POST",
                    f"/api/etc/reconciliation-tasks/{task.task_id}/credit-card-statement",
                    body=body,
                    headers=headers,
                )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["sourceFiles"]), 1)
        self.assertEqual(payload["sourceFiles"][0]["sourceKind"], "credit_card_statement")
        self.assertEqual(len(payload["creditCardItems"]), 2)
        self.assertEqual(payload["parseIssues"], [])

    def test_credit_card_statement_upload_rejects_parse_commit_after_source_deleted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC upload", created_by="alice")
            body, headers = multipart(
                {"statement.pdf": b"%PDF-1.4\n%%EOF"},
                fields={"expectedVersion": str(task.version)},
            )

            def parse_after_source_delete(*, file_id: str, content: bytes) -> FileParseResult:
                _ = content
                current = app._etc_reconciliation_task_service.get_task(task.task_id)
                app._etc_reconciliation_task_service.delete_source_file(
                    task_id=task.task_id,
                    file_id=file_id,
                    expected_version=current.version,
                    actor="alice",
                )
                return CcbCreditCardStatementParser().parse_text(file_id=file_id, text=CCB_STATEMENT_TEXT)

            with patch(
                "fin_ops_platform.services.etc_reconciliation_source_upload_service."
                "CcbCreditCardStatementParser.parse_pdf_bytes",
                side_effect=parse_after_source_delete,
            ):
                response = app.handle_request(
                    "POST",
                    f"/api/etc/reconciliation-tasks/{task.task_id}/credit-card-statement",
                    body=body,
                    headers=headers,
                )
            payload = json.loads(response.body)
            stored_task = app._etc_reconciliation_task_service.get_task(task.task_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "source_file_deleted_during_parse")
        self.assertEqual(payload["message"], "源文件在解析完成前已被删除，请重新上传。")
        self.assertEqual(stored_task.source_files, [])
        self.assertEqual(stored_task.parse_results, [])
        self.assertEqual(stored_task.credit_card_items, [])

    def test_credit_card_statement_image_pdf_upload_returns_ocr_warning(self) -> None:
        ocr_row = "2026-04-10 2026-04-11 8514 财付通-贵州黔通智联高速通行费 CNY 147.25CNY 147.25"
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="ETC OCR upload", created_by="alice")
            body, headers = multipart(
                {"scan.pdf": b"%PDF-1.4\n%%EOF"},
                fields={"expectedVersion": str(task.version)},
            )

            with (
                patch("fin_ops_platform.services.etc_document_parsers._extract_pdf_text", return_value=""),
                patch(
                    "fin_ops_platform.services.etc_document_parsers.TicketRootOcrTextExtractor.__call__",
                    return_value=[ocr_row],
                ),
            ):
                response = app.handle_request(
                    "POST",
                    f"/api/etc/reconciliation-tasks/{task.task_id}/credit-card-statement",
                    body=body,
                    headers=headers,
                )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["creditCardItems"]), 1)
        self.assertEqual(len(payload["parseIssues"]), 1)
        self.assertEqual(payload["parseIssues"][0]["severity"], "warning")
        self.assertEqual(payload["parseIssues"][0]["extractionMethod"], "ocr")

    def test_reconciliation_task_level_supplement_upload_parses_evidence(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="2026-03 ETC", created_by="alice")
            body, headers = multipart(
                {"parking.txt": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8")},
                fields={"expectedVersion": str(task.version), "evidenceKind": "non_etc_invoice"},
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/supplement-evidences",
                body=body,
                headers=headers,
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["sourceFiles"][0]["sourceKind"], "supplement_evidence")
        self.assertEqual(payload["supplementEvidences"][0]["source_name"], "parking.txt")
        self.assertEqual(payload["supplementEvidences"][0]["amount"], "23.00")
        self.assertEqual(payload["parseIssues"], [])

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

    def test_reconciliation_item_supplement_upload_returns_structured_storage_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task = app._etc_reconciliation_task_service.create_task(title="2026-03 ETC", created_by="alice")
            task = app._etc_reconciliation_task_service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-FILE-1", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))

            def fail_store(**_kwargs: object) -> str:
                raise ObjectStorageWriteError("object storage unavailable")

            app._state_store.store_etc_reconciliation_file = fail_store
            body, headers = multipart(
                {"parking.pdf": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8")},
                fields={
                    "expectedVersion": str(task.version),
                    "evidenceKind": "non_etc_invoice",
                    "note": "停车费凭证少开 2 元，按信用卡实际支出提交。",
                },
            )

            response = app.handle_request(
                "POST",
                f"/api/etc/reconciliation-tasks/{task.task_id}/supplement-evidences/{card.item_id}",
                body=body,
                headers=headers,
            )
            stored_task = app._etc_reconciliation_task_service.get_task(task.task_id)

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "reconciliation_file_storage_unavailable")
        self.assertIn("文件存储", payload["message"])
        self.assertEqual(stored_task.supplement_evidences, [])

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
        self.assertNotIn("removedCanonicalInvoiceCount", removed_payload)
        self.assertEqual(invoices_after_remove["total"], 0)
        self.assertEqual(canonical_etc_after_remove, [])
        self.assertEqual(reimport_preview_response.status_code, 200)
        self.assertEqual(reimport_preview["summary"]["imported"], 1)
        self.assertEqual(reimport_confirm_response.status_code, 202)
        self.assertEqual(reimport_job["status"], "succeeded")
        self.assertEqual(final_task_payload["status"], "imported")
        self.assertTrue(final_task_payload["hasImportedInvoices"])
        self.assertEqual(final_invoices["total"], 1)

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
                app.handle_request("GET", "/api/etc/business-batches?bucket=unsubmitted&page=1&page_size=100").body
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
        self.assertEqual(active_business_batches["data"]["counts"]["unsubmitted"], 1)
        self.assertEqual(active_business_batches["data"]["total"], 1)
        self.assertEqual(active_business_batches["data"]["items"][0]["businessBatchId"], business_batch["businessBatchId"])

    def test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            try:
                fake_oa = FakeEtcOAClient()
                app._build_etc_oa_client = lambda _headers: fake_oa
                task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001"])
                session_id = str(preview_payload["sessionId"])
                validated_preview = app._etc_import_preview_service.validate(session_id=session_id, task_id=task_id)
                app._etc_reconciliation_task_service.begin_import(
                    task_id=task_id,
                    task_version=validated_preview.session.task_version,
                    confirmed_item_set_hash=validated_preview.session.confirmed_item_set_hash,
                    import_session_id=session_id,
                    actor="alice",
                )
                app._etc_reconciliation_task_service.recover_interrupted_imports(active_import_session_ids=[])
                business_batch = app._import_processing_service.resolve_task_etc_business_batch(
                    task_id=task_id,
                    owner_user_id="web_finance_user",
                    idempotency_key=f"etc_business_task_import:{task_id}:{session_id}",
                )
                business_batch, result = app._etc_service.confirm_business_batch_import(
                    business_batch.business_batch_id,
                    session_id,
                    expected_version=business_batch.version,
                    idempotency_key=f"etc_import_session:{session_id}",
                    uploads=list(validated_preview.uploads),
                )

                draft_payload = app._etc_business_application_service().create_oa_draft_payload(
                    business_batch.business_batch_id,
                    idempotency_key="draft-durable-restart",
                    expected_version=business_batch.version,
                    actor=EtcBusinessBatchActor(can_admin_access=True, can_mutate_data=True),
                    headers={},
                )
                task = app._etc_reconciliation_task_service.get_task(task_id)
            finally:
                app.close()

        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.imported, 1)
        self.assertIn("businessBatch", draft_payload)
        self.assertEqual(task.status.value, "imported")
        self.assertEqual(task.import_batch_id, "etc_import_batch_0001")
        self.assertEqual(task.oa_draft_batch_id, draft_payload["businessBatch"]["submissionBatchId"])
        self.assertEqual(len(fake_oa.draft_payloads), 1)

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
        self.assertEqual(job["affected_domains"], ["imports_etc_invoices", "etc_tickets"])
        self.assertEqual(job["route"], "/imports/etc-invoices")
        self.assertEqual(job["source"]["task_id"], task_id)
        self.assertEqual(job["total"], 2)
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(completed_job["current"], 2)
        self.assertEqual(completed_job["total"], 2)
        self.assertEqual(completed_job["result_summary"]["created"], 2)
        self.assertEqual(completed_job["result_summary"]["imported"], 2)
        self.assertEqual(completed_job["result_summary"]["total"], 2)
        self.assertEqual(json.loads(query_response.body)["total"], 2)

    def test_etc_import_links_existing_canonical_invoices_and_dedupes_manual_invoice(self) -> None:
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

    def test_etc_import_keeps_distinct_invoice_numbers_with_same_amount_without_creating_canonical_invoices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            session_id = json.loads(preview_response.body)["sessionId"]
            confirm_response = app.handle_request("POST", "/api/etc/import/confirm", json.dumps({"sessionId": session_id, "taskId": task_id}))
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            invoices = app._import_service.list_invoices()
            etc_invoices = app._etc_service.list_invoices_by_numbers(["ETC001", "ETC002"])

        self.assertEqual(invoices, [])
        self.assertEqual(len(etc_invoices), 2)
        self.assertCountEqual([invoice.invoice_number for invoice in etc_invoices], ["ETC001", "ETC002"])

    def test_etc_import_drops_extra_zip_invoices_not_selected_by_current_task(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id = self._create_ready_reconciliation_task(
                app,
                amount="13.07",
                invoice_count=1,
                invoice_numbers=["ETC001"],
            )
            zip_content = zip_bytes(
                {
                    "xml/ETC001.xml": etc_xml("ETC001", total_amount="13.07"),
                    "pdf/ETC001.pdf": fake_pdf("ETC001"),
                    "xml/ETC999.xml": etc_xml("ETC999", total_amount="99.99"),
                    "pdf/ETC999.pdf": fake_pdf("ETC999"),
                }
            )
            body, headers = multipart(
                {"outer.zip": zip_content},
                fields={"task_id": task_id},
            )

            preview_response = app.handle_request("POST", "/api/etc/import/preview", body=body, headers=headers)
            preview_payload = json.loads(preview_response.body)
            confirm_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": preview_payload["sessionId"], "taskId": task_id}),
            )
            job = json.loads(confirm_response.body)["job"]
            self._wait_for_job(app, job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")
            canonical_invoices = app._import_service.list_invoices()
            stored_etc_invoices = app._etc_service.list_invoices_by_numbers(["ETC001", "ETC999"])

        filter_status_by_invoice = {
            str(item.get("invoiceNumber")): str(item.get("filterStatus"))
            for item in preview_payload["items"]
        }
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(confirm_response.status_code, 202)
        self.assertEqual(filter_status_by_invoice["ETC001"], "included")
        self.assertEqual(filter_status_by_invoice["ETC999"], "excluded_extra_zip_invoice")
        self.assertEqual(json.loads(query_response.body)["total"], 1)
        self.assertEqual([invoice.invoice_number for invoice in stored_etc_invoices], ["ETC001"])
        self.assertEqual(canonical_invoices, [])

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

    def test_etc_confirm_failed_session_can_retry_with_same_preview(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            task_id, preview_response, _preview_payload = self._preview_task_zip(app, ["ETC001"])
            session_id = json.loads(preview_response.body)["sessionId"]
            original_confirm = app._etc_service.confirm_business_batch_import

            def fail_once(*args, **kwargs):
                raise RuntimeError("synthetic canonical persist failure")

            app._etc_service.confirm_business_batch_import = fail_once
            first_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": session_id, "taskId": task_id}),
            )
            first_job = json.loads(first_response.body)["job"]
            failed_job = self._wait_for_job(app, first_job["job_id"])
            app._etc_service.confirm_business_batch_import = original_confirm

            second_response = app.handle_request(
                "POST",
                "/api/etc/import/confirm",
                json.dumps({"sessionId": session_id, "taskId": task_id}),
            )
            second_job = json.loads(second_response.body)["job"]
            completed_job = self._wait_for_job(app, second_job["job_id"])
            query_response = app.handle_request("GET", "/api/etc/invoices?page=1&page_size=20")

        self.assertEqual(first_response.status_code, 202)
        self.assertEqual(failed_job["status"], "failed")
        self.assertEqual(second_response.status_code, 202)
        self.assertNotEqual(second_job["job_id"], first_job["job_id"])
        self.assertEqual(completed_job["status"], "succeeded")
        self.assertEqual(json.loads(query_response.body)["total"], 1)

    def test_etc_confirm_job_partial_success_when_some_items_fail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            task_id, preview_response, preview_payload = self._preview_task_zip(app, ["ETC001", "ETC002"])
            preview_payload = json.loads(preview_response.body)
            session_id = preview_payload["sessionId"]
            original_upsert = app._etc_service._upsert_attachment_metadata_from_import

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

            app._etc_service._upsert_attachment_metadata_from_import = fail_second_required_invoice

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

    def test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            fake_oa = FakeEtcOAClient()
            app._etc_service.oa_client = fake_oa

            _task_id, draft_payload = self._import_supplement_reconciliation_zip_and_create_draft(app)

        self.assertEqual(draft_payload["oaDraftId"], "oa-draft-001")
        self.assertEqual(draft_payload["invoiceSummary"], {"count": 1, "amount": "13.07"})
        self.assertEqual(len(fake_oa.uploads), 2)
        self.assertEqual(Path(fake_oa.uploads[1]).name, "ETC-RECON-FILE-000001_supplement-ride.pdf")
        payload = fake_oa.draft_payloads[0]["payload"]
        self.assertEqual(payload["data"]["amount"], "101.07")
        uploaded_names = [item["name"] for item in payload["data"]["field101"]["list"]]
        self.assertEqual(uploaded_names, ["ETC001.pdf", "supplement-ride.pdf"])

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

        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(query_response.body)["total"], 0)

    def test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            spec = HistoricalEtcRepairBatchSpec(
                label="测试历史批次",
                bundle_id="ETC-HIST-TEST",
                case_id="etc-historical-test",
                external_batch_id="ETC-HIST-TEST",
                oa_row_id="oa-exp-test",
                oa_amount=Decimal("30.00"),
            )
            original_create_relation = app._workbench_pair_relation_service.create_active_relation

            def forbidden_direct_relation_create(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("historical ETC repair must create relation via command service.")

            app._workbench_pair_relation_service.create_active_relation = forbidden_direct_relation_create

            class RecordingRelationCommandService:
                def __init__(self) -> None:
                    self.confirm_calls: list[dict[str, object]] = []

                def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
                    return app._workbench_pair_relation_service.get_active_relation_by_case_id(case_id)

                def confirm_relation(self, **kwargs: object) -> dict[str, object]:
                    self.confirm_calls.append(dict(kwargs))
                    relation = original_create_relation(
                        case_id=str(kwargs["case_id"]),
                        row_ids=list(kwargs["row_ids"]),
                        row_types=list(kwargs["row_types"]),
                        relation_mode=str(kwargs["relation_mode"]),
                        created_by=str(kwargs["actor_id"]),
                        month_scope=str(kwargs.get("month_scope") or "all"),
                        note=str(kwargs.get("note") or ""),
                        amount_check=dict(kwargs.get("amount_check") or {}),
                    )
                    return {
                        "status": "confirmed",
                        "relation": relation,
                        "changed_case_ids": [str(kwargs["case_id"])],
                        "affected_months": [],
                        "read_model_status": "fresh",
                        "read_model_stale_reasons": [],
                        "read_model_scope_keys": ["all"],
                        "refresh_enqueued": False,
                    }

            relation_command_service = RecordingRelationCommandService()
            service = HistoricalEtcRepairService(
                state_store=app._state_store,
                etc_service=app._etc_service,
                relation_command_service=relation_command_service,
                specs=[spec],
                oa_row_exists=lambda row_id: row_id == "oa-exp-test",
                link_import_result_to_existing_invoices=app._link_etc_import_result_to_existing_invoices,
                link_etc_invoices_to_existing_invoices=app._link_etc_invoices_to_existing_invoices,
                refresh_after_etc_invoice_link=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
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
            service._link_etc_invoices_to_existing_invoices = (  # noqa: SLF001 - verifies parsed-seed fast path.
                lambda _invoices: (_ for _ in ()).throw(
                    AssertionError("existing historical repair should not relink existing invoices")
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
        self.assertEqual(app._import_service.list_invoices(), [])
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("etc-historical-test")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "etc_batch_invoice_link")
        self.assertEqual(persisted_state["ETC-HIST-TEST"]["status"], "ok")
        self.assertEqual(relation_command_service.confirm_calls[-1]["case_id"], "etc-historical-test")
        self.assertEqual(relation_command_service.confirm_calls[-1]["relation_mode"], "etc_batch_invoice_link")

    def test_historical_etc_repair_requires_relation_command_service_before_local_writes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            spec = HistoricalEtcRepairBatchSpec(
                label="测试历史批次",
                bundle_id="ETC-HIST-NO-COMMAND",
                case_id="etc-historical-no-command",
                external_batch_id="ETC-HIST-NO-COMMAND",
                oa_row_id="oa-exp-no-command",
                oa_amount=Decimal("30.00"),
            )

            def forbidden_direct_relation_create(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("historical ETC repair must fail fast instead of using pair service fallback.")

            app._workbench_pair_relation_service.create_active_relation = forbidden_direct_relation_create
            service = HistoricalEtcRepairService(
                state_store=app._state_store,
                etc_service=app._etc_service,
                specs=[spec],
                oa_row_exists=lambda row_id: row_id == "oa-exp-no-command",
                link_import_result_to_existing_invoices=app._link_etc_import_result_to_existing_invoices,
                link_etc_invoices_to_existing_invoices=app._link_etc_invoices_to_existing_invoices,
                refresh_after_etc_invoice_link=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )
            service.seed_bundle_from_upload(
                spec,
                UploadedEtcZipFile("historical-no-command.zip", etc_zip(["ETC001", "ETC002"])),
            )

            with self.assertRaises(WorkbenchRelationCommandError) as context:
                service.reconcile(reason="test")

            submitted_batches = app._etc_service.list_batches(status="submitted")
            relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("etc-historical-no-command")

        self.assertEqual(context.exception.error_code, "workbench_relation_command_unavailable")
        self.assertEqual(submitted_batches, [])
        self.assertIsNone(relation)



if __name__ == "__main__":
    unittest.main()
