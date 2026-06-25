from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from fin_ops_platform.services.etc_document_parsers import (
    CcbCreditCardStatementParser,
    SupplementEvidenceParser,
    TicketRootClipboardTextParser,
    TicketRootDocumentParser,
    TicketRootPdfTextParser,
)
from fin_ops_platform.services.etc_reconciliation_models import (
    EtcReconciliationTask,
    EtcReconciliationTaskStatus,
    ExpectedEtcInvoiceRequirement,
    ParseIssueSeverity,
    SourceFileKind,
)
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_reconciliation_source_upload_service import (
    EtcReconciliationSourceUpload,
    EtcReconciliationSourceUploadService,
)
from fin_ops_platform.services.etc_reconciliation_zip_filter import (
    StaleReconciliationPreviewError,
    preview_etc_zip_for_task,
    validate_etc_zip_confirm_for_task,
)
from fin_ops_platform.services.etc_service import UploadedEtcZipFile
from fin_ops_platform.services.state_store import ApplicationStateStore


REAL_TICKET_ROOT_TXT_SAMPLES = {
    "a516hj": (
        Path("/Users/yu/Desktop/sy/财务运营平台/票根网/4月/云A516HJ/云A516HJ"),
        "云A516HJ",
        11,
    ),
    "ada0381": (
        Path("/Users/yu/Desktop/sy/财务运营平台/票根网/4月/云ADA0381/云a0381"),
        "云ADA0381",
        48,
    ),
    "a361hx": (
        Path("/Users/yu/Desktop/sy/财务运营平台/票根网/4月/云A361HX/云A361HX"),
        "云A361HX",
        2,
    ),
}

CCB_STATEMENT_TEXT = """
中国建设银行信用卡账单
卡号末四位 3632
账单周期 2026-03-01 至 2026-03-31
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-03-03 2026-03-04 3632 微信支付-云南昆明南站高速通行费 CNY 25.00 25.00
2026-03-03 2026-03-04 3632 云南九龙池站高速通行费 CNY 23.00 23.00
2026-03-04 2026-03-05 3632 中国石化加油费 CNY 200.00 200.00
2026-03-05 2026-03-05 3632 自动还款 CNY -248.00 -248.00
"""

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

TICKET_ROOT_TEXT_WITHOUT_AMOUNT = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-03 17:06:18
入口站 昆明南站
出口站 九龙池站
"""

TICKET_ROOT_TEXT_WITHOUT_TRANSACTION_AT = """
票根网通行明细
车牌号 云ADA0381
入口站 昆明南站
出口站 九龙池站
金额 25.00
"""

NON_ETC_SUPPLEMENT_TEXT = """
付款凭证
商品 加油费
商户全称 中国石化销售股份有限公司云南昆明石油分公司
支付时间 2026年3月4日 14:13:44
金额 200.00
"""

APRIL_STATEMENT_TEXT = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-10 2026-04-11 8514 财付通-贵州黔通智联高速通行费 CNY 147.25 147.25
"""

APRIL_TICKET_TEXT = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-10 21:36:24
入口站 昆明南站
出口站 九龙池站
金额 147.25
发票张数 1
"""

TICKET_ROOT_CLIPBOARD_TEXT = """
收费公路通行费电子发票服务平台
首页
我的ETC
我要开票
我的发票
发票抬头
个人中心
客服协助
刘树刚
修改手机号修改密码退出登录
首页  >  我的发票电子发票可以电子形式保存，不打印也可报销、抵扣
按开票记录查看 按行程查看
返回卡列表
 路网中心ETC：记账卡 990100**********4908    车牌号：云ADA0381
202604
  点击此处选择月份
入口收费站/出口收费站
交易时间：2026-04-08 18:57:17交易金额：￥71.25查看发票      发票下载      发票转发
云南
云南弥勒南站

云南
云南小喜村站
发票数量：2
交易时间：2026-04-08 11:13:41交易金额：￥71.25查看发票      发票下载      发票转发
云南
云南小喜村站

云南
云南弥勒南站
发票数量：2
交易时间：2026-04-03 18:24:36交易金额：￥1.90查看发票      发票下载      发票转发
云南
云南河尾村开放式站

云南
云南河尾村开放式站
发票数量：1
交易时间：2026-04-03 18:14:27交易金额：￥42.39查看发票      发票下载      发票转发
云南
云南通站站

云南
云南晖湾站
发票数量：4
1234

版权所有：行云数聚（北京）科技有限公司            京ICP备17066956号
"""


def fake_pdf(invoice_number: str) -> bytes:
    return f"%PDF-1.4\n% fake ETC invoice {invoice_number}\n%%EOF\n".encode("ascii")


def etc_xml(
    invoice_number: str,
    *,
    issue_date: str = "2026-03-03",
    request_time: str | None = None,
    plate_number: str = "云ADA0381",
    total_amount: str = "25.00",
) -> bytes:
    amount_without_tax = (Decimal(total_amount) - Decimal("0.75")).quantize(Decimal("0.01"))
    request_time_xml = f"<RequestTime>{request_time}</RequestTime>" if request_time else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice>
  <InvoiceNumber>{invoice_number}</InvoiceNumber>
  <IssueDate>{issue_date}</IssueDate>
  {request_time_xml}
  <PassageStartDate>{issue_date}</PassageStartDate>
  <PassageEndDate>{issue_date}</PassageEndDate>
  <PlateNumber>{plate_number}</PlateNumber>
  <AmountWithoutTax>{amount_without_tax}</AmountWithoutTax>
  <TaxAmount>0.75</TaxAmount>
  <TotalAmount>{total_amount}</TotalAmount>
</Invoice>
""".encode("utf-8")


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def etc_zip(invoice_numbers: list[str], *, include_pdf: bool = True) -> bytes:
    entries: dict[str, bytes] = {}
    for invoice_number in invoice_numbers:
        entries[f"xml/{invoice_number}.xml"] = etc_xml(invoice_number)
        if include_pdf:
            entries[f"pdf/{invoice_number}.pdf"] = fake_pdf(invoice_number)
    return zip_bytes(entries)


def ready_task_with_requirement(
    *,
    amount: str,
    transaction_at: str,
    invoice_count: int,
    plate: str = "云ADA0381",
    requirement_id: str = "TASK-REQ-0001",
) -> EtcReconciliationTask:
    return EtcReconciliationTask(
        task_id="TASK",
        status=EtcReconciliationTaskStatus.READY_FOR_IMPORT,
        version=3,
        title="ETC",
        confirmed_item_set_hash="confirmed-hash",
        expected_etc_invoice_requirements=[
            ExpectedEtcInvoiceRequirement(
                requirement_id=requirement_id,
                task_id="TASK",
                credit_card_item_id="CARD-1",
                ticket_root_item_id="TICKET-1",
                vehicle_plate=plate,
                transaction_at=transaction_at,
                date_window_start=transaction_at[:10],
                date_window_end=transaction_at[:10],
                amount=Decimal(amount),
                invoice_count=invoice_count,
            )
        ],
    )


class EtcReconciliationServiceTests(unittest.TestCase):
    class _PostgresLikeReconciliationStateStore:
        data_dir = None

        def __init__(self) -> None:
            self.rows: dict[str, object] = {}
            self.task_counter = 0
            self.file_counter = 0
            self.audit_counter = 0

        def load_etc_reconciliation_state(self) -> dict:
            return {
                "schema_version": 1,
                "task_counter": self.task_counter,
                "file_counter": self.file_counter,
                "audit_counter": self.audit_counter,
                "tasks": dict(self.rows),
            }

        def save_etc_reconciliation_state(self, snapshot: dict) -> None:
            self.task_counter = int(snapshot.get("task_counter", 0) or 0)
            self.file_counter = int(snapshot.get("file_counter", 0) or 0)
            self.audit_counter = int(snapshot.get("audit_counter", 0) or 0)
            for task_id, payload in dict(snapshot.get("tasks") or {}).items():
                self.rows[str(task_id)] = payload

    def test_source_upload_service_imports_ticket_root_text_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = task_service.create_task(title="ETC", created_by="alice")
            source_upload_service = EtcReconciliationSourceUploadService(task_service=task_service)

            updated = source_upload_service.upload_sources(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                expected_version=task.version,
                actor="alice",
                uploads=[
                    EtcReconciliationSourceUpload(
                        file_name="云ADA0381.txt",
                        content=TICKET_ROOT_CLIPBOARD_TEXT.encode("utf-8"),
                    )
                ],
            )

        self.assertEqual(updated.source_files[0].source_kind, SourceFileKind.TICKET_ROOT)
        self.assertEqual(updated.source_files[0].content_type, "text/plain; charset=utf-8")
        self.assertEqual(updated.ticket_root_items[0].vehicle_plate, "云ADA0381")
        self.assertEqual(updated.ticket_root_items[0].amount, Decimal("71.25"))
        self.assertEqual(updated.parse_results[0].parser_code, TicketRootClipboardTextParser.parser_code)

    def test_source_upload_service_submits_ticket_root_manual_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            task_service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = task_service.create_task(title="ETC", created_by="alice")
            source_upload_service = EtcReconciliationSourceUploadService(task_service=task_service)

            updated = source_upload_service.submit_ticket_root_texts(
                task_id=task.task_id,
                expected_version=task.version,
                actor="alice",
                texts=[TICKET_ROOT_CLIPBOARD_TEXT],
            )

        self.assertEqual(updated.source_files[0].source_kind, SourceFileKind.TICKET_ROOT)
        self.assertEqual(updated.source_files[0].content_type, "text/plain; charset=utf-8")
        self.assertIn("票根网手工粘贴-云ADA0381-202604", updated.source_files[0].original_name)
        self.assertEqual(updated.ticket_root_items[0].vehicle_plate, "云ADA0381")
        self.assertEqual(updated.ticket_root_items[0].amount, Decimal("71.25"))
        self.assertEqual(updated.parse_results[0].parser_code, TicketRootClipboardTextParser.parser_code)

    def _parsed_task(self, *, ticket_text: str = TICKET_ROOT_TEXT) -> tuple[EtcReconciliationTaskService, str]:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-1", text=CCB_STATEMENT_TEXT),
            actor="alice",
        )
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-1", text=ticket_text),
            actor="alice",
        )
        return service, task.task_id

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_task_starts_as_fresh_empty_batch(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))

        task = service.create_task(title="ETC fresh", created_by="alice")

        self.assertEqual(task.status, EtcReconciliationTaskStatus.DRAFT)
        self.assertEqual(task.version, 1)
        self.assertEqual(task.source_files, [])
        self.assertEqual(task.parse_results, [])
        self.assertEqual(task.credit_card_items, [])
        self.assertEqual(task.ticket_root_items, [])
        self.assertEqual(task.supplement_evidences, [])
        self.assertEqual(task.vehicle_plates, [])
        self.assertEqual([event.event_type for event in task.audit_events], ["task_created"])

    def test_ticket_root_clipboard_text_parser_reads_real_trip_copy_sample(self) -> None:
        result = TicketRootClipboardTextParser().parse_text(file_id="PASTE-1", text=TICKET_ROOT_CLIPBOARD_TEXT)

        self.assertEqual(result.issues, [])
        self.assertEqual(len(result.ticket_root_items), 4)
        self.assertEqual(
            [
                (
                    item.vehicle_plate,
                    item.transaction_at,
                    str(item.amount),
                    item.entry_station,
                    item.exit_station,
                    item.invoice_count,
                )
                for item in result.ticket_root_items
            ],
            [
                ("云ADA0381", "2026-04-08 18:57:17", "71.25", "云南弥勒南站", "云南小喜村站", 2),
                ("云ADA0381", "2026-04-08 11:13:41", "71.25", "云南小喜村站", "云南弥勒南站", 2),
                ("云ADA0381", "2026-04-03 18:24:36", "1.90", "云南河尾村开放式站", "云南河尾村开放式站", 1),
                ("云ADA0381", "2026-04-03 18:14:27", "42.39", "云南通站站", "云南晖湾站", 4),
            ],
        )
        self.assertTrue(all(item.extraction_method == "clipboard_text" for item in result.ticket_root_items))

    def test_ticket_root_clipboard_text_parser_reads_real_txt_file_samples(self) -> None:
        parser = TicketRootClipboardTextParser()
        for sample_key, (sample_path, expected_plate, expected_count) in REAL_TICKET_ROOT_TXT_SAMPLES.items():
            if not sample_path.exists():
                self.skipTest(f"missing local ticket root sample: {sample_path}")
            with self.subTest(sample=sample_key):
                result = parser.parse_text(file_id=f"TXT-{sample_key}", text=sample_path.read_text(encoding="utf-8"))

                self.assertEqual(result.issues, [])
                self.assertEqual(len(result.ticket_root_items), expected_count)
                self.assertEqual({item.vehicle_plate for item in result.ticket_root_items}, {expected_plate})

        a516_result = parser.parse_text(
            file_id="TXT-a516hj-key-records",
            text=REAL_TICKET_ROOT_TXT_SAMPLES["a516hj"][0].read_text(encoding="utf-8"),
        )
        self.assertIn(
            ("2026-04-02 13:30:29", Decimal("57.95"), "云A516HJ"),
            {
                (item.transaction_at, item.amount, item.vehicle_plate)
                for item in a516_result.ticket_root_items
            },
        )
        self.assertIn(
            ("2026-04-02 11:25:48", Decimal("88.86"), "云A516HJ"),
            {
                (item.transaction_at, item.amount, item.vehicle_plate)
                for item in a516_result.ticket_root_items
            },
        )

    def test_ticket_root_clipboard_text_parser_blocks_missing_plate(self) -> None:
        text = TICKET_ROOT_CLIPBOARD_TEXT.replace("车牌号：云ADA0381", "")

        result = TicketRootClipboardTextParser().parse_text(file_id="PASTE-1", text=text)

        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].message, "票根网手工粘贴内容缺少车牌号，不能进入核对。")

    def test_ticket_root_clipboard_text_parser_blocks_without_trip_rows(self) -> None:
        result = TicketRootClipboardTextParser().parse_text(
            file_id="PASTE-1",
            text="收费公路通行费电子发票服务平台\n按行程查看\n车牌号：云ADA0381\n暂无数据",
        )

        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].message, "票根网手工粘贴内容未识别到通行明细，不能进入核对。")

    def test_ticket_root_clipboard_text_parser_prompts_trip_tab_for_invoice_record_page(self) -> None:
        result = TicketRootClipboardTextParser().parse_text(
            file_id="PASTE-1",
            text="收费公路通行费电子发票服务平台\n按开票记录查看\n开票记录\n开票完成\n车牌号：云ADA0381",
        )

        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].message, "请切换到按行程查看后复制粘贴。")

    def test_ticket_root_clipboard_text_parser_blocks_invoice_record_page_with_trip_nav(self) -> None:
        result = TicketRootClipboardTextParser().parse_text(
            file_id="PASTE-INVOICE-RECORDS",
            text="""
收费公路通行费电子发票服务平台
按开票记录查看 按行程查看
返回卡列表
路网中心ETC：记账卡 990100**********4908    车牌号：云ADA0381
开票记录
开票完成
开票申请时间：2026-03-31 17:19:57
开票金额：￥9.50
消费发票申请
发票数量：1张
""",
        )

        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].message, "请切换到按行程查看后复制粘贴。")

    def test_rebuild_task_deduplicates_ticket_root_items_by_natural_trip_key(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        first_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket-1.txt",
            content_type="text/plain; charset=utf-8",
            content=f"{TICKET_ROOT_CLIPBOARD_TEXT}\n重复复制".encode("utf-8"),
            created_by="alice",
        )
        second_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket-2.txt",
            content_type="text/plain; charset=utf-8",
            content=TICKET_ROOT_CLIPBOARD_TEXT.encode("utf-8"),
            created_by="alice",
        )

        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootClipboardTextParser().parse_text(file_id=first_file.file_id, text=TICKET_ROOT_CLIPBOARD_TEXT),
            actor="alice",
        )
        updated = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootClipboardTextParser().parse_text(file_id=second_file.file_id, text=f"{TICKET_ROOT_CLIPBOARD_TEXT}\n重复复制"),
            actor="alice",
        )

        self.assertEqual(len(updated.ticket_root_items), 4)
        self.assertEqual(updated.ticket_root_items[0].vehicle_plate, "云ADA0381")
        self.assertEqual(updated.ticket_root_items[0].amount, Decimal("71.25"))

    def test_delete_failed_source_file_removes_issue_and_keeps_successful_ticket_items(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        good_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket-good.pdf",
            content_type="application/pdf",
            content=b"good ticket",
            created_by="alice",
        )
        bad_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket-bad.pdf",
            content_type="application/pdf",
            content=b"bad ticket",
            created_by="alice",
        )
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=good_file.file_id, text=TICKET_ROOT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=bad_file.file_id, text=TICKET_ROOT_TEXT_WITHOUT_PLATE),
            actor="alice",
        )

        updated = service.delete_source_file(
            task_id=task.task_id,
            file_id=bad_file.file_id,
            expected_version=task.version,
            actor="alice",
        )

        self.assertEqual([source.file_id for source in updated.source_files], [good_file.file_id])
        self.assertEqual([result.file_id for result in updated.parse_results], [good_file.file_id])
        self.assertEqual(len(updated.ticket_root_items), 1)
        self.assertEqual(updated.ticket_root_items[0].vehicle_plate, "云ADA0381")
        self.assertEqual([issue for result in updated.parse_results for issue in result.issues], [])
        self.assertFalse(Path(bad_file.stored_path).exists())
        self.assertTrue(Path(good_file.stored_path).exists())
        self.assertEqual(updated.audit_events[-1].event_type, "source_file_deleted")

    def test_delete_successful_source_file_removes_only_its_parsed_items(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        ticket_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket",
            created_by="alice",
        )
        statement_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
            original_name="statement.pdf",
            content_type="application/pdf",
            content=b"statement",
            created_by="alice",
        )
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=ticket_file.file_id, text=TICKET_ROOT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id=statement_file.file_id, text=CCB_STATEMENT_TEXT),
            actor="alice",
        )

        updated = service.delete_source_file(
            task_id=task.task_id,
            file_id=ticket_file.file_id,
            expected_version=task.version,
            actor="alice",
        )

        self.assertEqual(len(updated.ticket_root_items), 0)
        self.assertEqual(len(updated.credit_card_items), 4)
        self.assertEqual([source.file_id for source in updated.source_files], [statement_file.file_id])
        self.assertFalse(Path(ticket_file.stored_path).exists())

    def test_delete_linked_ticket_source_file_resets_invalid_card_resolution(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        card_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
            original_name="statement.pdf",
            content_type="application/pdf",
            content=b"statement",
            created_by="alice",
        )
        ticket_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket",
            created_by="alice",
        )
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id=card_file.file_id, text=CCB_STATEMENT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=ticket_file.file_id, text=TICKET_ROOT_TEXT),
            actor="alice",
        )
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task.task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )

        updated = service.delete_source_file(
            task_id=task.task_id,
            file_id=ticket_file.file_id,
            expected_version=task.version,
            actor="alice",
        )
        updated_card = next(item for item in updated.credit_card_items if item.item_id == card.item_id)

        self.assertEqual(updated.ticket_root_items, [])
        self.assertEqual(updated_card.manual_resolution, "unresolved")
        self.assertIsNone(updated_card.manual_resolution_reason)
        self.assertIsNone(updated_card.review_note)

    def test_delete_linked_supplement_source_file_resets_invalid_card_resolution(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        card_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
            original_name="statement.pdf",
            content_type="application/pdf",
            content=b"statement",
            created_by="alice",
        )
        supplement_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
            original_name="supplement.pdf",
            content_type="application/pdf",
            content=b"supplement",
            created_by="alice",
        )
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id=card_file.file_id, text=CCB_STATEMENT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=SupplementEvidenceParser().parse_text(
                file_id=supplement_file.file_id,
                text=NON_ETC_SUPPLEMENT_TEXT,
                source_name=supplement_file.original_name,
            ),
            actor="alice",
        )
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        evidence = task.supplement_evidences[0]
        task = service.patch_item(
            task_id=task.task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_supplement", "supplementEvidenceId": evidence.evidence_id, "note": "补充凭证"},
        )

        updated = service.delete_source_file(
            task_id=task.task_id,
            file_id=supplement_file.file_id,
            expected_version=task.version,
            actor="alice",
        )
        updated_card = next(item for item in updated.credit_card_items if item.item_id == card.item_id)

        self.assertEqual(updated.supplement_evidences, [])
        self.assertEqual(updated.reconciled_items, [])
        self.assertEqual(updated_card.manual_resolution, "unresolved")
        self.assertIsNone(updated_card.review_note)

    def test_upload_supplement_for_card_requires_delta_note_and_claims_card_amount(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-FILE-1", text=CCB_STATEMENT_TEXT),
            actor="alice",
        )
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))

        with self.assertRaisesRegex(ValueError, "supplement_amount_delta_note_required"):
            service.upload_supplement_evidences_for_card(
                task_id=task.task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                files=[
                    {
                        "original_name": "parking.pdf",
                        "content_type": "application/pdf",
                        "content": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8"),
                    }
                ],
                note="",
                evidence_kind_override="non_etc_invoice",
            )
        self.assertEqual(len(service.get_task(task.task_id).supplement_evidences), 0)

        updated = service.upload_supplement_evidences_for_card(
            task_id=task.task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            files=[
                {
                    "original_name": "parking.pdf",
                    "content_type": "application/pdf",
                    "content": "商户 停车场\n付款时间 2026年3月3日\n金额 23.00".encode("utf-8"),
                }
            ],
            note="停车费凭证少开 2 元，按信用卡实际支出提交。",
            evidence_kind_override="non_etc_invoice",
        )
        updated_card = next(item for item in updated.credit_card_items if item.item_id == card.item_id)
        reconciled = next(item for item in updated.reconciled_items if item.credit_card_item_id == card.item_id)

        self.assertEqual(updated_card.manual_resolution, "covered_by_supplement")
        self.assertEqual(updated_card.review_note, "停车费凭证少开 2 元，按信用卡实际支出提交。")
        self.assertEqual(reconciled.claim_amount, Decimal("25.00"))
        self.assertEqual(reconciled.evidence_amount, Decimal("23.00"))
        self.assertEqual(reconciled.amount_delta, Decimal("2.00"))
        self.assertEqual(reconciled.amount_delta_note, "停车费凭证少开 2 元，按信用卡实际支出提交。")

        confirmed = service.confirm_task(
            task_id=updated.task_id,
            expected_version=updated.version,
            actor="alice",
            confirmed_credit_card_item_ids=[card.item_id],
        )
        self.assertEqual(confirmed.oa_total_amount, Decimal("25.00"))
        self.assertEqual(confirmed.supplement_amount, Decimal("25.00"))
        self.assertEqual(confirmed.etc_invoice_amount, Decimal("0.00"))
        self.assertEqual(confirmed.approved_delta, Decimal("0.00"))

    def test_delete_source_file_rolls_back_memory_state_when_persist_fails(self) -> None:
        class FlakyStateStore:
            data_dir = None

            def __init__(self) -> None:
                self.snapshot: dict = {}
                self.fail_next_save = False

            def load_etc_reconciliation_state(self) -> dict:
                return self.snapshot

            def save_etc_reconciliation_state(self, snapshot: dict) -> None:
                if self.fail_next_save:
                    self.fail_next_save = False
                    raise RuntimeError("simulated state write failure")
                self.snapshot = snapshot

            def store_etc_reconciliation_file(
                self,
                *,
                task_id: str,
                file_id: str,
                file_name: str,
                content: bytes,
            ) -> str:
                return f"gridfs://{task_id}:{file_id}/{file_name}"

        store = FlakyStateStore()
        service = EtcReconciliationTaskService(state_store=store)
        task = service.create_task(title="ETC", created_by="alice")
        source_file = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket",
            created_by="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id=source_file.file_id, text=TICKET_ROOT_TEXT),
            actor="alice",
        )
        store.fail_next_save = True

        with self.assertRaisesRegex(RuntimeError, "simulated state write failure"):
            service.delete_source_file(
                task_id=task.task_id,
                file_id=source_file.file_id,
                expected_version=task.version,
                actor="alice",
            )
        current = service.get_task(task.task_id)

        self.assertEqual([source.file_id for source in current.source_files], [source_file.file_id])
        self.assertEqual([result.file_id for result in current.parse_results], [source_file.file_id])
        self.assertEqual(len(current.ticket_root_items), 1)

    def test_delete_source_file_requires_expected_version_mutable_status_and_known_file(self) -> None:
        service, task_id = self._parsed_task()
        task = service.get_task(task_id)
        file_id = task.parse_results[0].file_id

        with self.assertRaisesRegex(ValueError, "task_version_conflict"):
            service.delete_source_file(task_id=task_id, file_id=file_id, expected_version=task.version + 1, actor="alice")
        with self.assertRaisesRegex(KeyError, "unknown_source_file"):
            service.delete_source_file(task_id=task_id, file_id="missing-file", expected_version=task.version, actor="alice")

        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        ready = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")

        with self.assertRaisesRegex(ValueError, "reconciliation_task_not_mutable"):
            service.delete_source_file(task_id=task_id, file_id=file_id, expected_version=ready.version, actor="alice")

    def test_delete_draft_task_removes_task_and_uploaded_files(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC待删除", created_by="alice")
        uploaded = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket bytes",
            created_by="alice",
        )

        result = service.delete_task(task_id=task.task_id, expected_version=task.version + 1, actor="alice")

        self.assertEqual(result, {"deleted": True, "taskId": task.task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            service.get_task(task.task_id)
        self.assertFalse(Path(uploaded.stored_path).exists())

    def test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id(self) -> None:
        store = self._PostgresLikeReconciliationStateStore()
        service = EtcReconciliationTaskService(state_store=store)
        task = service.create_task(title="ETC待删除", created_by="alice")

        service.delete_task(task_id=task.task_id, expected_version=task.version, actor="alice")
        reloaded = EtcReconciliationTaskService(state_store=store)
        next_task = reloaded.create_task(title="ETC新批次", created_by="alice")

        self.assertEqual(reloaded.list_tasks(), [next_task])
        with self.assertRaises(KeyError):
            reloaded.get_task(task.task_id)
        self.assertNotEqual(next_task.task_id, task.task_id)
        self.assertTrue(next_task.task_id.endswith("000002"))

    def test_delete_reviewing_task_enforces_expected_version(self) -> None:
        service, task_id = self._parsed_task()
        task = service.get_task(task_id)

        with self.assertRaisesRegex(ValueError, "task_version_conflict"):
            service.delete_task(task_id=task_id, expected_version=task.version + 1, actor="alice")

        deleted = service.delete_task(task_id=task_id, expected_version=task.version, actor="alice")

        self.assertEqual(deleted["taskId"], task_id)
        with self.assertRaises(KeyError):
            service.get_task(task_id)

    def test_delete_ready_task_removes_task_and_uploaded_files(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        uploaded = service.store_uploaded_source_file(
            task_id=task_id,
            source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
            original_name="supplement.txt",
            content_type="text/plain",
            content=b"supplement",
            created_by="alice",
        )
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.get_task(task_id)
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        ready = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")

        result = service.delete_task(task_id=task_id, expected_version=ready.version, actor="alice")

        self.assertEqual(result, {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            service.get_task(task_id)
        self.assertFalse(Path(uploaded.stored_path).exists())

    def test_delete_imported_task_requires_cleanup_confirmation_and_deletes_after_cleanup(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        ready = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")
        imported = service.mark_imported(
            task_id=task_id,
            task_version=ready.version,
            confirmed_item_set_hash=ready.confirmed_item_set_hash or "",
            import_batch_id="import-batch-1",
            actor="alice",
        )

        with self.assertRaisesRegex(ValueError, "reconciliation_task_import_cleanup_required"):
            service.delete_task(task_id=task_id, expected_version=imported.version, actor="alice")

        result = service.delete_task(
            task_id=task_id,
            expected_version=imported.version,
            actor="alice",
            import_cleanup_confirmed=True,
        )

        self.assertEqual(result, {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            service.get_task(task_id)

    def test_delete_task_allows_importing_closed_and_submission_links_after_confirmation(self) -> None:
        def build_importing_service(suffix: str) -> tuple[EtcReconciliationTaskService, EtcReconciliationTask]:
            service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name) / suffix)
            task = service.create_task(title="ETC", created_by="alice")
            service.apply_parse_result(
                task_id=task.task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-1", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )
            task = service.apply_parse_result(
                task_id=task.task_id,
                parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-1", text=TICKET_ROOT_TEXT),
                actor="alice",
            )
            task = service.refresh_matches(task_id=task.task_id)
            card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
            ticket = task.ticket_root_items[0]
            task = service.patch_item(
                task_id=task.task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
            )
            other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
            task = service.patch_item(
                task_id=task.task_id,
                item_id=other_card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
            )
            ready = service.confirm_task(task_id=task.task_id, expected_version=task.version, actor="alice")
            importing = service.begin_import(
                task_id=task.task_id,
                task_version=ready.version,
                confirmed_item_set_hash=ready.confirmed_item_set_hash or "",
                import_session_id=f"session-{suffix}",
                actor="alice",
            )
            return service, importing

        service, importing = build_importing_service("importing")
        deleted_importing = service.delete_task(
            task_id=importing.task_id,
            expected_version=importing.version,
            actor="alice",
        )

        self.assertEqual(deleted_importing, {"deleted": True, "taskId": importing.task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            service.get_task(importing.task_id)

        linked_service, linked_importing = build_importing_service("linked")
        linked_service.mark_imported(
            task_id=linked_importing.task_id,
            task_version=linked_importing.version,
            confirmed_item_set_hash=linked_importing.confirmed_item_set_hash or "",
            import_batch_id="import-batch-1",
            actor="alice",
        )
        linked = linked_service.record_oa_draft_created(
            task_id=linked_importing.task_id,
            oa_draft_batch_id="oa-draft-1",
            etc_batch_id="etc-submission-1",
            actor="alice",
        )

        deleted = linked_service.delete_task(
            task_id=linked_importing.task_id,
            expected_version=linked.version,
            actor="alice",
            import_cleanup_confirmed=True,
        )
        self.assertEqual(deleted, {"deleted": True, "taskId": linked_importing.task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            linked_service.get_task(linked_importing.task_id)

        closed_service, closed_importing = build_importing_service("closed")
        closed_service.mark_imported(
            task_id=closed_importing.task_id,
            task_version=closed_importing.version,
            confirmed_item_set_hash=closed_importing.confirmed_item_set_hash or "",
            import_batch_id="import-batch-1",
            actor="alice",
        )
        closed_service.record_oa_draft_created(
            task_id=closed_importing.task_id,
            oa_draft_batch_id="oa-draft-1",
            etc_batch_id="etc-submission-1",
            actor="alice",
        )
        closed_service.record_oa_submitted_confirmed(
            task_id=closed_importing.task_id,
            oa_draft_batch_id="oa-draft-1",
            actor="alice",
        )
        closed = closed_service.get_task(closed_importing.task_id)
        deleted_closed = closed_service.delete_task(
            task_id=closed_importing.task_id,
            expected_version=closed.version,
            actor="alice",
            import_cleanup_confirmed=True,
        )

        self.assertEqual(deleted_closed, {"deleted": True, "taskId": closed_importing.task_id, "kind": "reconciliation_task"})
        with self.assertRaises(KeyError):
            closed_service.get_task(closed_importing.task_id)

    def test_matching_links_best_candidate_and_keeps_alternatives_for_review(self) -> None:
        multi_ticket_text = TICKET_ROOT_TEXT + """
车牌号 云ADA0381
交易时间 2026-03-04 09:30:00
入口站 呈贡站
出口站 石林站
金额 25.00
发票张数 1
"""
        service, task_id = self._parsed_task(ticket_text=multi_ticket_text)
        service.apply_parse_result(
            task_id=task_id,
            parse_result=TicketRootPdfTextParser().parse_text(
                file_id="TICKET-2",
                text="""
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-04 09:30:00
入口站 呈贡站
出口站 石林站
金额 25.00
发票张数 1
""",
            ),
            actor="alice",
        )

        task = service.refresh_matches(task_id=task_id)
        statuses = {item.description: item.recommendation_status for item in task.credit_card_items}
        ticket_statuses = {item.transaction_at: item.recommendation_status for item in task.ticket_root_items}

        self.assertEqual(statuses["微信支付-云南昆明南站高速通行费"], "suggested_match")
        self.assertEqual(statuses["云南九龙池站高速通行费"], "missing_ticket")
        self.assertEqual(ticket_statuses["2026-03-03 17:06:18"], "suggested_match")
        self.assertEqual(ticket_statuses["2026-03-04 09:30:00"], "needs_review")
        self.assertEqual(
            next(item for item in task.ticket_root_items if item.transaction_at == "2026-03-03 17:06:18").linked_credit_card_item_ids,
            [next(item for item in task.credit_card_items if item.description == "微信支付-云南昆明南站高速通行费").item_id],
        )

        single_service, single_task_id = self._parsed_task()
        single_task = single_service.refresh_matches(task_id=single_task_id)
        single_statuses = {item.description: item.recommendation_status for item in single_task.credit_card_items}
        self.assertEqual(single_statuses["微信支付-云南昆明南站高速通行费"], "suggested_match")
        self.assertEqual(single_statuses["云南九龙池站高速通行费"], "missing_ticket")

    def test_matching_uses_posting_date_window_and_writes_auto_link(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 ETC", created_by="alice")
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-APRIL", text=APRIL_STATEMENT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-APRIL", text=APRIL_TICKET_TEXT),
            actor="alice",
        )

        card = task.credit_card_items[0]
        ticket = task.ticket_root_items[0]

        self.assertEqual(card.recommendation_status, "suggested_match")
        self.assertEqual(ticket.recommendation_status, "suggested_match")
        self.assertEqual(ticket.linked_credit_card_item_ids, [card.item_id])

    def test_matching_links_beijing_sutong_card_rows_to_ticket_root_txt_rows(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-05 Beijing Sutong ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-05-10 2026-05-10 8514 财付通-北京速通科技有限公司 CNY 23.50 23.50
2026-05-15 2026-05-15 8514 财付通-北京速通科技有限公司 CNY 88.35 88.35
2026-05-25 2026-05-25 8514 财付通-北京速通科技有限公司 CNY 88.35 88.35
"""
        ticket_text = """
票根网通行明细
车牌号 云A546NH
交易时间 2026-05-25 17:02:37
入口站 A站
出口站 B站
金额 88.35
发票张数 1
车牌号 云A546NH
交易时间 2026-05-15 14:47:17
入口站 A站
出口站 B站
金额 88.35
发票张数 1
车牌号 云ADA0381
交易时间 2026-05-22 17:09:29
入口站 A站
出口站 B站
金额 23.50
发票张数 1
车牌号 云ADA0381
交易时间 2026-05-24 19:15:18
入口站 A站
出口站 B站
金额 23.50
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-BEIJING-SUTONG", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootClipboardTextParser().parse_text(file_id="TICKET-A546NH", text=ticket_text),
            actor="alice",
        )

        status_by_amount_and_date = {
            (item.transaction_date, item.settlement_amount): item.recommendation_status
            for item in task.credit_card_items
        }
        self.assertEqual(status_by_amount_and_date[("2026-05-15", Decimal("88.35"))], "suggested_match")
        self.assertEqual(status_by_amount_and_date[("2026-05-25", Decimal("88.35"))], "suggested_match")
        self.assertEqual(status_by_amount_and_date[("2026-05-10", Decimal("23.50"))], "suggested_match")
        linked_by_time = {item.transaction_at: item.linked_credit_card_item_ids for item in task.ticket_root_items}
        card_by_date = {item.transaction_date: item for item in task.credit_card_items}
        self.assertEqual(linked_by_time["2026-05-15 14:47:17"], [card_by_date["2026-05-15"].item_id])
        self.assertEqual(linked_by_time["2026-05-25 17:02:37"], [card_by_date["2026-05-25"].item_id])
        self.assertEqual(linked_by_time["2026-05-22 17:09:29"], [card_by_date["2026-05-10"].item_id])
        self.assertEqual(linked_by_time["2026-05-24 19:15:18"], [])

    def test_matching_prefers_closest_ticket_when_more_tickets_than_cards(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 closest ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-28 2026-04-29 8514 财付通-贵州黔通智联科技股份有限公司 CNY 75.05 75.05
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-27 14:21:44
入口站 云南会泽站
出口站 云南昭通南站
金额 75.05
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-28 18:11:15
入口站 云南昭通南站
出口站 云南会泽站
金额 75.05
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-CLOSEST", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-CLOSEST", text=ticket_text),
            actor="alice",
        )

        self.assertEqual(task.credit_card_items[0].recommendation_status, "suggested_match")
        linked_by_time = {item.transaction_at: item.linked_credit_card_item_ids for item in task.ticket_root_items}
        self.assertEqual(linked_by_time["2026-04-28 18:11:15"], [task.credit_card_items[0].item_id])
        self.assertEqual(linked_by_time["2026-04-27 14:21:44"], [])

    def test_matching_links_repeated_amount_by_stable_one_to_one_order(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 stable repeated ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-08 2026-04-09 8514 高速通行费-晚 CNY 71.25 71.25
2026-04-08 2026-04-09 8514 高速通行费-早 CNY 71.25 71.25
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 18:57:17
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 11:13:41
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-AMBIGUOUS", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-AMBIGUOUS", text=ticket_text),
            actor="alice",
        )

        self.assertEqual([item.recommendation_status for item in task.credit_card_items], ["suggested_match", "suggested_match"])
        self.assertEqual([item.recommendation_status for item in task.ticket_root_items], ["suggested_match", "suggested_match"])
        self.assertEqual(
            {item.transaction_at: item.linked_credit_card_item_ids for item in task.ticket_root_items},
            {
                "2026-04-08 11:13:41": [task.credit_card_items[0].item_id],
                "2026-04-08 18:57:17": [task.credit_card_items[1].item_id],
            },
        )

    def test_matching_links_repeated_amount_batches_and_fills_nearest_fallback_gap(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 production ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-08 2026-04-09 8514 高速通行费71A CNY 71.25 71.25
2026-04-08 2026-04-09 8514 高速通行费71B CNY 71.25 71.25
2026-04-08 2026-04-09 8514 高速通行费23A CNY 23.50 23.50
2026-04-08 2026-04-09 8514 高速通行费23B CNY 23.50 23.50
2026-04-08 2026-04-09 8514 高速通行费9A CNY 9.50 9.50
2026-04-08 2026-04-09 8514 高速通行费9B CNY 9.50 9.50
2026-04-09 2026-04-09 8514 高速通行费缺票 CNY 57.95 57.95
2026-04-02 2026-04-02 8514 高速通行费跨窗 CNY 88.86 88.86
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 18:57:17
入口站 A
出口站 B
金额 71.25
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 11:13:41
入口站 B
出口站 A
金额 71.25
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 12:00:00
入口站 C
出口站 D
金额 23.50
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 13:00:00
入口站 D
出口站 C
金额 23.50
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 14:00:00
入口站 E
出口站 F
金额 9.50
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-08 15:00:00
入口站 F
出口站 E
金额 9.50
发票张数 1
车牌号 云ADA0381
交易时间 2026-03-09 08:00:00
入口站 G
出口站 H
金额 88.86
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-23 08:00:00
入口站 H
出口站 G
金额 88.86
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-PRODUCTION", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-PRODUCTION", text=ticket_text),
            actor="alice",
        )

        statuses = {item.description: item.recommendation_status for item in task.credit_card_items}
        linked_by_ticket_time = {item.transaction_at: item.linked_credit_card_item_ids for item in task.ticket_root_items}

        for amount in (Decimal("71.25"), Decimal("23.50"), Decimal("9.50")):
            cards = [item for item in task.credit_card_items if item.settlement_amount == amount]
            tickets = [item for item in task.ticket_root_items if item.amount == amount]
            self.assertEqual([item.recommendation_status for item in cards], ["suggested_match", "suggested_match"])
            self.assertEqual([item.recommendation_status for item in tickets], ["suggested_match", "suggested_match"])
            self.assertEqual(sorted(len(item.linked_credit_card_item_ids) for item in tickets), [1, 1])
            self.assertEqual(
                sorted(card_id for item in tickets for card_id in item.linked_credit_card_item_ids),
                sorted(item.item_id for item in cards),
            )
        self.assertEqual(statuses["高速通行费缺票"], "missing_ticket")
        self.assertEqual(statuses["高速通行费跨窗"], "suggested_match")
        self.assertEqual(linked_by_ticket_time["2026-03-09 08:00:00"], [])
        self.assertEqual(
            linked_by_ticket_time["2026-04-23 08:00:00"],
            [next(item for item in task.credit_card_items if item.description == "高速通行费跨窗").item_id],
        )

    def test_matching_uses_description_business_date_as_primary_anchor(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-03 business date ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-03-29 2026-03-29 8514 20260327高速通行费云南 CNY 21.52 21.52
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-27 10:30:00
入口站 昆明南站
出口站 九龙池站
金额 21.52
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-BUSINESS-DATE", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-BUSINESS-DATE", text=ticket_text),
            actor="alice",
        )

        self.assertEqual(task.credit_card_items[0].recommendation_status, "suggested_match")
        self.assertEqual(task.ticket_root_items[0].recommendation_status, "suggested_match")
        self.assertEqual(task.ticket_root_items[0].linked_credit_card_item_ids, [task.credit_card_items[0].item_id])

    def test_matching_locks_explicit_business_date_before_fallback_window(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-03 business date exact ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-03-28 2026-03-28 8514 20260327高速通行费云南昆明南站云 CNY 23.50 23.50
"""
        ticket_text = """
票根网通行明细
车牌号 云A361HX
交易时间 2026-03-27 16:29:49
入口站 昆明南站
出口站 通站站
金额 23.50
发票张数 1
车牌号 云A516HJ
交易时间 2026-03-26 16:37:53
入口站 通站站
出口站 昆明南站
金额 23.50
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-BUSINESS-DATE-EXACT", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-BUSINESS-DATE-EXACT", text=ticket_text),
            actor="alice",
        )

        self.assertEqual(task.credit_card_items[0].recommendation_status, "suggested_match")
        linked_by_time = {item.transaction_at: item.linked_credit_card_item_ids for item in task.ticket_root_items}
        status_by_time = {item.transaction_at: item.recommendation_status for item in task.ticket_root_items}
        self.assertEqual(linked_by_time["2026-03-27 16:29:49"], [task.credit_card_items[0].item_id])
        self.assertEqual(status_by_time["2026-03-27 16:29:49"], "suggested_match")
        self.assertEqual(linked_by_time["2026-03-26 16:37:53"], [])
        self.assertEqual(status_by_time["2026-03-26 16:37:53"], "extra_ticket")

    def test_matching_does_not_consume_one_ticket_more_than_once(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 duplicate guard ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-08 2026-04-09 8514 高速通行费-A CNY 71.25 71.25
2026-04-08 2026-04-09 8514 高速通行费-B CNY 71.25 71.25
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 11:13:41
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-DUPLICATE-GUARD", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-DUPLICATE-GUARD", text=ticket_text),
            actor="alice",
        )

        self.assertEqual(task.ticket_root_items[0].linked_credit_card_item_ids, [task.credit_card_items[0].item_id])
        self.assertEqual(task.credit_card_items[0].recommendation_status, "suggested_match")
        self.assertEqual(task.credit_card_items[1].recommendation_status, "needs_review")

    def test_matching_finds_large_repeated_amount_set_without_greedy_loss(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 large duplicate ETC", created_by="alice")
        statement_rows = [
            f"2026-04-{day:02d} 2026-04-30 8514 高速通行费-{day:02d} CNY 12.34 12.34"
            for day in range(1, 19)
        ]
        ticket_rows = [
            f"""
车牌号 云ADA0381
交易时间 2026-04-{day:02d} 08:00:00
入口站 昆明南站
出口站 九龙池站
金额 12.34
发票张数 1
"""
            for day in range(1, 19)
        ]
        statement_text = "\n".join(
            [
                "中国建设银行信用卡账单",
                "交易日 入账日 卡号 摘要 币种 交易金额 入账金额",
                *statement_rows,
            ]
        )
        ticket_text = "票根网通行明细\n" + "\n".join(ticket_rows)
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-LARGE-DUPLICATE", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-LARGE-DUPLICATE", text=ticket_text),
            actor="alice",
        )

        self.assertEqual(len(task.credit_card_items), 18)
        self.assertEqual(len(task.ticket_root_items), 18)
        self.assertEqual({item.recommendation_status for item in task.credit_card_items}, {"suggested_match"})
        self.assertEqual({item.recommendation_status for item in task.ticket_root_items}, {"suggested_match"})
        self.assertEqual(sorted(len(item.linked_credit_card_item_ids) for item in task.ticket_root_items), [1] * 18)
        self.assertEqual(
            sorted(card_id for item in task.ticket_root_items for card_id in item.linked_credit_card_item_ids),
            sorted(item.item_id for item in task.credit_card_items),
        )

    def test_manual_link_replaces_previous_ticket_consumer(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 manual duplicate guard ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-08 2026-04-09 8514 高速通行费-A CNY 71.25 71.25
2026-04-08 2026-04-09 8514 高速通行费-B CNY 71.25 71.25
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 11:13:41
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-MANUAL-DUPLICATE", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-MANUAL-DUPLICATE", text=ticket_text),
            actor="alice",
        )
        ticket = task.ticket_root_items[0]
        first_card, second_card = task.credit_card_items

        task = service.patch_item(
            task_id=task.task_id,
            item_id=first_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task.task_id,
            item_id=second_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )

        linked_ticket = task.ticket_root_items[0]
        cards_by_id = {item.item_id: item for item in task.credit_card_items}
        self.assertEqual(linked_ticket.linked_credit_card_item_ids, [second_card.item_id])
        self.assertEqual(cards_by_id[first_card.item_id].manual_resolution, "unresolved")
        self.assertEqual(cards_by_id[second_card.item_id].manual_resolution, "included_etc")

    def test_matching_links_repeated_amount_when_posting_windows_disambiguate(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 disambiguated ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 入账金额
2026-04-08 2026-04-08 8514 高速通行费-早 CNY 71.25 71.25
2026-04-10 2026-04-10 8514 高速通行费-晚 CNY 71.25 71.25
"""
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-04-08 11:13:41
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
车牌号 云ADA0381
交易时间 2026-04-10 21:36:24
入口站 昆明南站
出口站 九龙池站
金额 71.25
发票张数 1
"""
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-DISAMBIGUATED", text=statement_text),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-DISAMBIGUATED", text=ticket_text),
            actor="alice",
        )

        self.assertEqual([item.recommendation_status for item in task.credit_card_items], ["suggested_match", "suggested_match"])
        self.assertEqual([item.recommendation_status for item in task.ticket_root_items], ["suggested_match", "suggested_match"])
        self.assertEqual(
            [item.linked_credit_card_item_ids for item in task.ticket_root_items],
            [[task.credit_card_items[0].item_id], [task.credit_card_items[1].item_id]],
        )

    def test_matching_marks_unmatched_card_and_ticket_separately(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="2026-04 unmatched ETC", created_by="alice")
        service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-UNMATCHED", text=APRIL_STATEMENT_TEXT),
            actor="alice",
        )
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(
                file_id="TICKET-UNMATCHED",
                text=APRIL_TICKET_TEXT.replace("147.25", "12.00"),
            ),
            actor="alice",
        )

        self.assertEqual(task.credit_card_items[0].recommendation_status, "missing_ticket")
        self.assertEqual(task.ticket_root_items[0].recommendation_status, "extra_ticket")
        self.assertEqual(task.ticket_root_items[0].linked_credit_card_item_ids, [])

    def test_manual_actions_require_expected_version_and_notes_before_confirm(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card_by_amount = {item.settlement_amount: item for item in task.credit_card_items}
        ticket = task.ticket_root_items[0]

        with self.assertRaisesRegex(ValueError, "task_version_conflict"):
            service.patch_item(
                task_id=task_id,
                item_id=card_by_amount[Decimal("25.00")].item_id,
                expected_version=1,
                actor="alice",
                payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
            )

        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("25.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        with self.assertRaisesRegex(ValueError, "manual_resolution_required"):
            service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")

        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("25.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        with self.assertRaisesRegex(ValueError, "review_note_required"):
            service.patch_item(
                task_id=task_id,
                item_id=card_by_amount[Decimal("23.00")].item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "exclude_card", "manualResolution": "excluded_non_etc"},
            )
        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("23.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )

        confirmed = service.confirm_task(
            task_id=task_id,
            expected_version=task.version,
            actor="alice",
        )

        self.assertEqual(confirmed.status, EtcReconciliationTaskStatus.READY_FOR_IMPORT)
        self.assertEqual(confirmed.oa_total_amount, Decimal("25.00"))
        self.assertEqual(confirmed.etc_invoice_amount, Decimal("25.00"))
        self.assertEqual(confirmed.supplement_amount, Decimal("0.00"))
        self.assertEqual(len(confirmed.expected_etc_invoice_requirements), 1)
        self.assertTrue(confirmed.confirmed_item_set_hash)

    def test_confirm_with_selected_card_ids_uses_only_selected_requirements_and_amounts(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card_by_amount = {item.settlement_amount: item for item in task.credit_card_items}
        selected_card = card_by_amount[Decimal("25.00")]
        unselected_missing_card = card_by_amount[Decimal("23.00")]
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=selected_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )

        confirmed = service.confirm_task(
            task_id=task_id,
            expected_version=task.version,
            actor="alice",
            confirmed_credit_card_item_ids=[selected_card.item_id],
        )

        self.assertEqual(confirmed.status, EtcReconciliationTaskStatus.READY_FOR_IMPORT)
        self.assertEqual(confirmed.oa_total_amount, Decimal("25.00"))
        self.assertEqual(confirmed.etc_invoice_amount, Decimal("25.00"))
        self.assertEqual(confirmed.supplement_amount, Decimal("0.00"))
        self.assertEqual(confirmed.supplement_count, 0)
        self.assertEqual(
            [item.credit_card_item_id for item in confirmed.expected_etc_invoice_requirements],
            [selected_card.item_id],
        )
        self.assertNotIn(unselected_missing_card.item_id, confirmed.confirmed_item_set_hash or "")

    def test_included_etc_requires_linked_ticket_or_etc_supplement_evidence(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))

        with self.assertRaisesRegex(ValueError, "linked_etc_evidence_required"):
            service.patch_item(
                task_id=task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
            )

    def test_confirm_blocks_without_statement_or_without_final_items(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        empty_task = service.create_task(title="ETC", created_by="alice")

        with self.assertRaisesRegex(ValueError, "credit_card_statement_required"):
            service.confirm_task(task_id=empty_task.task_id, expected_version=empty_task.version, actor="alice")

        task = service.create_task(title="ETC no candidates", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
2026-03-04 2026-03-05 3632 中国石化加油费 CNY 200.00 200.00
"""
        parsed = CcbCreditCardStatementParser().parse_text(file_id="CARD-NO-ETC", text=statement_text)
        task = service.apply_parse_result(task_id=task.task_id, parse_result=parsed, actor="alice")

        with self.assertRaisesRegex(ValueError, "no_confirmable_credit_card_items"):
            service.confirm_task(task_id=task.task_id, expected_version=task.version, actor="alice")

        candidate_service, candidate_task_id = self._parsed_task()
        candidate_task = candidate_service.refresh_matches(task_id=candidate_task_id)
        card_by_amount = {item.settlement_amount: item for item in candidate_task.credit_card_items}
        candidate_task = candidate_service.patch_item(
            task_id=candidate_task_id,
            item_id=card_by_amount[Decimal("25.00")].item_id,
            expected_version=candidate_task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        candidate_task = candidate_service.patch_item(
            task_id=candidate_task_id,
            item_id=card_by_amount[Decimal("23.00")].item_id,
            expected_version=candidate_task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )

        with self.assertRaisesRegex(ValueError, "no_confirmable_credit_card_items"):
            candidate_service.confirm_task(task_id=candidate_task_id, expected_version=candidate_task.version, actor="alice")

    def test_ready_imported_and_importing_tasks_reject_direct_mutations(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        confirmed = service.confirm_task(
            task_id=task_id,
            expected_version=task.version,
            actor="alice",
        )

        with self.assertRaisesRegex(ValueError, "reconciliation_task_not_mutable"):
            service.patch_item(
                task_id=task_id,
                item_id=card.item_id,
                expected_version=confirmed.version,
                actor="alice",
                payload={"action": "manual_confirm", "note": "人工确认"},
            )
        with self.assertRaisesRegex(ValueError, "reconciliation_task_not_mutable"):
            service.apply_parse_result(
                task_id=task_id,
                parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD-2", text=CCB_STATEMENT_TEXT),
                actor="alice",
            )

        importing = service.begin_import(
            task_id=task_id,
            task_version=confirmed.version,
            confirmed_item_set_hash=confirmed.confirmed_item_set_hash or "",
            import_session_id="session-1",
            actor="alice",
        )
        with self.assertRaisesRegex(ValueError, "reconciliation_task_not_reopenable"):
            service.reopen_task(task_id=task_id, expected_version=importing.version, actor="alice")
        with self.assertRaisesRegex(ValueError, "invalid_reconciliation_task_status"):
            service.confirm_task(task_id=task_id, expected_version=importing.version, actor="alice")
        imported = service.mark_imported(
            task_id=task_id,
            task_version=confirmed.version,
            confirmed_item_set_hash=confirmed.confirmed_item_set_hash or "",
            import_batch_id="import-batch-1",
            actor="alice",
        )
        with self.assertRaisesRegex(ValueError, "invalid_reconciliation_task_status"):
            service.confirm_task(task_id=task_id, expected_version=imported.version, actor="alice")
        with self.assertRaisesRegex(ValueError, "reconciliation_task_not_mutable"):
            service.patch_item(
                task_id=task_id,
                item_id=card.item_id,
                expected_version=imported.version,
                actor="alice",
                payload={"action": "manual_confirm", "note": "人工确认"},
            )

    def test_interrupted_importing_task_recovers_to_ready_after_hydration(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        confirmed = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")
        importing = service.begin_import(
            task_id=task_id,
            task_version=confirmed.version,
            confirmed_item_set_hash=confirmed.confirmed_item_set_hash or "",
            import_session_id="session-1",
            actor="alice",
        )

        recovered_service = EtcReconciliationTaskService.from_snapshot(service.snapshot(), data_dir=Path(self.temp_dir.name))
        recovered = recovered_service.get_task(task_id)

        self.assertEqual(importing.status, EtcReconciliationTaskStatus.IMPORTING)
        self.assertEqual(recovered.status, EtcReconciliationTaskStatus.READY_FOR_IMPORT)
        self.assertIsNone(recovered.import_batch_id)
        self.assertGreater(recovered.version, importing.version)

    def test_active_import_session_is_not_recovered_after_hydration(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        confirmed = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")
        importing = service.begin_import(
            task_id=task_id,
            task_version=confirmed.version,
            confirmed_item_set_hash=confirmed.confirmed_item_set_hash or "",
            import_session_id="session-1",
            actor="alice",
        )

        recovered_service = EtcReconciliationTaskService.from_snapshot(
            service.snapshot(),
            data_dir=Path(self.temp_dir.name),
            active_import_session_ids={"session-1"},
        )
        recovered = recovered_service.get_task(task_id)

        self.assertEqual(importing.status, EtcReconciliationTaskStatus.IMPORTING)
        self.assertEqual(recovered.status, EtcReconciliationTaskStatus.IMPORTING)
        self.assertEqual(recovered.import_batch_id, "session-1")
        self.assertEqual(recovered.version, importing.version)

    def test_reopen_returns_to_reviewing_and_invalidates_zip_preview(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card_by_amount = {item.settlement_amount: item for item in task.credit_card_items}
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("25.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("25.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card_by_amount[Decimal("23.00")].item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        confirmed = service.confirm_task(task_id=task_id, expected_version=task.version, actor="alice")
        preview = preview_etc_zip_for_task(
            task=confirmed,
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["ETC001"], include_pdf=True))],
        )

        reopened = service.reopen_task(task_id=task_id, expected_version=confirmed.version, actor="alice")

        self.assertEqual(reopened.status, EtcReconciliationTaskStatus.REVIEWING)
        self.assertEqual(reopened.confirmed_item_set_hash, None)
        with self.assertRaises(StaleReconciliationPreviewError):
            validate_etc_zip_confirm_for_task(task=reopened, preview=preview)

    def test_zip_preview_persists_allowlist_and_blocks_missing_required_invoice(self) -> None:
        service, task_id = self._parsed_task()
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_error", "reason": "重复"},
        )
        confirmed = service.confirm_task(
            task_id=task_id,
            expected_version=task.version,
            actor="alice",
        )

        preview = preview_etc_zip_for_task(
            task=confirmed,
            uploads=[
                UploadedEtcZipFile(
                    "etc.zip",
                    zip_bytes(
                        {
                            "xml/ETC001.xml": etc_xml("ETC001", issue_date="2026-03-03", total_amount="25.00"),
                            "pdf/ETC001.pdf": fake_pdf("ETC001"),
                            "xml/EXTRA.xml": etc_xml("EXTRA", issue_date="2026-03-03", total_amount="999.99"),
                            "pdf/EXTRA.pdf": fake_pdf("EXTRA"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.allowed_invoice_numbers, ["ETC001"])
        self.assertEqual(
            {item.invoice_number: item.filter_status for item in preview.items},
            {"ETC001": "included", "EXTRA": "excluded_extra_zip_invoice"},
        )

        missing = preview_etc_zip_for_task(
            task=confirmed,
            uploads=[
                UploadedEtcZipFile(
                    "etc.zip",
                    zip_bytes(
                        {
                            "xml/WRONG.xml": etc_xml("WRONG", issue_date="2026-03-03", total_amount="999.99"),
                            "pdf/WRONG.pdf": fake_pdf("WRONG"),
                        }
                    ),
                )
            ],
        )
        with self.assertRaisesRegex(ValueError, "missing_required_etc_invoice"):
            validate_etc_zip_confirm_for_task(task=confirmed, preview=missing)

    def test_zip_preview_matches_requirement_to_two_invoice_amount_sum(self) -> None:
        task = ready_task_with_requirement(amount="71.25", transaction_at="2026-04-08 18:57:17", invoice_count=2)

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "package/xml/ETC2950.xml": etc_xml("ETC2950", issue_date="2026-04-08", total_amount="29.50"),
                            "package/pdf/ETC2950.pdf": fake_pdf("ETC2950"),
                            "package/xml/ETC4175.xml": etc_xml("ETC4175", issue_date="2026-04-08", total_amount="41.75"),
                            "package/pdf/ETC4175.pdf": fake_pdf("ETC4175"),
                            "package/xml/EXTRA.xml": etc_xml("EXTRA", issue_date="2026-04-08", total_amount="99.99"),
                            "package/pdf/EXTRA.pdf": fake_pdf("EXTRA"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC2950", "ETC4175"])
        self.assertEqual(
            {item.invoice_number: item.filter_status for item in preview.items},
            {"ETC2950": "included", "ETC4175": "included", "EXTRA": "excluded_extra_zip_invoice"},
        )
        self.assertEqual(
            {item.invoice_number: item.requirement_id for item in preview.items if item.filter_status == "included"},
            {"ETC2950": "TASK-REQ-0001", "ETC4175": "TASK-REQ-0001"},
        )

    def test_zip_preview_matches_requirement_to_four_invoice_amount_sum(self) -> None:
        task = ready_task_with_requirement(amount="42.39", transaction_at="2026-04-03 18:14:27", invoice_count=4)

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "april/xml/ETC1201.xml": etc_xml("ETC1201", issue_date="2026-04-03", total_amount="12.01"),
                            "april/xml/ETC1708.xml": etc_xml("ETC1708", issue_date="2026-04-03", total_amount="17.08"),
                            "april/xml/ETC0023.xml": etc_xml("ETC0023", issue_date="2026-04-03", total_amount="0.23"),
                            "april/xml/ETC1307.xml": etc_xml("ETC1307", issue_date="2026-04-03", total_amount="13.07"),
                            "april/xml/EXTRA.xml": etc_xml("EXTRA", issue_date="2026-04-03", total_amount="50.00"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC0023", "ETC1201", "ETC1307", "ETC1708"])
        included = [item for item in preview.items if item.filter_status == "included"]
        self.assertEqual({item.invoice_number for item in included}, {"ETC1201", "ETC1708", "ETC0023", "ETC1307"})
        self.assertTrue(all(item.requirement_id == "TASK-REQ-0001" for item in included))

    def test_zip_preview_deduplicates_repeated_invoice_number_before_matching(self) -> None:
        task = ready_task_with_requirement(amount="71.25", transaction_at="2026-04-08 18:57:17", invoice_count=2)

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "package/xml/ETC2950.xml": etc_xml("ETC2950", issue_date="2026-04-08", total_amount="29.50"),
                            "package/xml/copy-ETC2950.xml": etc_xml("ETC2950", issue_date="2026-04-08", total_amount="29.50"),
                            "package/xml/ETC4175.xml": etc_xml("ETC4175", issue_date="2026-04-08", total_amount="41.75"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC2950", "ETC4175"])
        self.assertEqual([item.invoice_number for item in preview.items].count("ETC2950"), 2)
        self.assertTrue(all(issue["error"] != "ambiguous_etc_invoice_match" for issue in preview.blocking_issues))

    def test_zip_preview_blocks_multiple_distinct_exact_invoice_candidates(self) -> None:
        task = ready_task_with_requirement(amount="25.00", transaction_at="2026-03-03 17:06:18", invoice_count=1)

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "package/xml/ETC-A.xml": etc_xml("ETC-A", issue_date="2026-03-03", total_amount="25.00"),
                            "package/xml/ETC-B.xml": etc_xml("ETC-B", issue_date="2026-03-03", total_amount="25.00"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.allowed_invoice_numbers, [])
        self.assertTrue(any(issue["error"] == "ambiguous_etc_invoice_match" for issue in preview.blocking_issues))
        self.assertEqual(
            {item.invoice_number: item.filter_status for item in preview.items},
            {"ETC-A": "ambiguous_zip_match", "ETC-B": "ambiguous_zip_match"},
        )

    def test_zip_preview_requires_combination_length_to_match_invoice_count(self) -> None:
        task = ready_task_with_requirement(amount="42.39", transaction_at="2026-04-03 18:14:27", invoice_count=4)

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "package/xml/ETC2000.xml": etc_xml("ETC2000", issue_date="2026-04-03", total_amount="20.00"),
                            "package/xml/ETC2239.xml": etc_xml("ETC2239", issue_date="2026-04-03", total_amount="22.39"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.allowed_invoice_numbers, [])
        missing_issue = next(issue for issue in preview.blocking_issues if issue["error"] == "missing_required_etc_invoice")
        self.assertEqual(missing_issue["requirementId"], "TASK-REQ-0001")
        self.assertEqual(missing_issue["transactionAt"], "2026-04-03 18:14:27")
        self.assertEqual(missing_issue["transactionDate"], "2026-04-03")
        self.assertEqual(missing_issue["amount"], "42.39")
        self.assertEqual(missing_issue["vehiclePlate"], "云ADA0381")
        self.assertEqual(missing_issue["invoiceCount"], 4)

    def test_confirmed_requirement_zip_window_includes_linked_ticket_transaction_date(self) -> None:
        service = EtcReconciliationTaskService(data_dir=Path(self.temp_dir.name))
        task = service.create_task(title="ETC", created_by="alice")
        statement_text = """
中国建设银行信用卡账单
2026-03-29 2026-03-29 3632 20260327高速通行费云南昆明南站云 CNY 23.50 23.50
"""
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=CcbCreditCardStatementParser().parse_text(file_id="CARD", text=statement_text),
            actor="alice",
        )
        ticket_text = """
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-27 16:29:49
入口站 昆明南站
出口站 九龙池站
金额 23.50
发票张数 1
"""
        task = service.apply_parse_result(
            task_id=task.task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET", text=ticket_text),
            actor="alice",
        )
        card = task.credit_card_items[0]
        ticket = task.ticket_root_items[0]
        task = service.patch_item(
            task_id=task.task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
        )
        task = service.patch_item(
            task_id=task.task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        confirmed = service.confirm_task(task_id=task.task_id, expected_version=task.version, actor="alice")

        preview = preview_etc_zip_for_task(
            task=confirmed,
            uploads=[
                UploadedEtcZipFile(
                    "etc.zip",
                    zip_bytes({"xml/ETC2350.xml": etc_xml("ETC2350", issue_date="2026-03-27", total_amount="23.50")}),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC2350"])

    def test_zip_preview_uses_global_assignment_when_exact_match_would_starve_later_requirement(self) -> None:
        task = ready_task_with_requirement(amount="30.00", transaction_at="2026-04-08 18:00:00", invoice_count=2)
        task.expected_etc_invoice_requirements.append(
            ExpectedEtcInvoiceRequirement(
                requirement_id="TASK-REQ-0002",
                task_id="TASK",
                credit_card_item_id="CARD-2",
                ticket_root_item_id="TICKET-2",
                vehicle_plate="云ADA0381",
                transaction_at="2026-04-08 18:05:00",
                date_window_start="2026-04-08",
                date_window_end="2026-04-08",
                amount=Decimal("30.00"),
                invoice_count=1,
            )
        )

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "package/xml/ETC1000.xml": etc_xml("ETC1000", issue_date="2026-04-08", total_amount="10.00"),
                            "package/xml/ETC2000.xml": etc_xml("ETC2000", issue_date="2026-04-08", total_amount="20.00"),
                            "package/xml/ETC3000.xml": etc_xml("ETC3000", issue_date="2026-04-08", total_amount="30.00"),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC1000", "ETC2000", "ETC3000"])
        included_by_requirement = {
            requirement_id: {
                item.invoice_number
                for item in preview.items
                if item.requirement_id == requirement_id and item.filter_status == "included"
            }
            for requirement_id in {"TASK-REQ-0001", "TASK-REQ-0002"}
        }
        self.assertEqual(included_by_requirement["TASK-REQ-0001"], {"ETC1000", "ETC2000"})
        self.assertEqual(included_by_requirement["TASK-REQ-0002"], {"ETC3000"})

    def test_zip_preview_matches_single_invoice_package_to_multiple_requirements(self) -> None:
        task = ready_task_with_requirement(
            amount="57.95",
            transaction_at="2026-04-02 13:30:29",
            invoice_count=2,
            plate="云A516HJ",
        )
        task.expected_etc_invoice_requirements.append(
            ExpectedEtcInvoiceRequirement(
                requirement_id="TASK-REQ-0002",
                task_id="TASK",
                credit_card_item_id="CARD-2",
                ticket_root_item_id="TICKET-2",
                vehicle_plate="云A516HJ",
                transaction_at="2026-04-02 11:25:48",
                date_window_start="2026-04-02",
                date_window_end="2026-04-02",
                amount=Decimal("88.86"),
                invoice_count=1,
            )
        )

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "20260407_通行费电子发票_2张.zip/invoice.zip/xml/ETC14638.xml": etc_xml(
                                "ETC14638",
                                issue_date="2026-04-02",
                                plate_number="云A516HJ",
                                total_amount="146.38",
                            ),
                            "20260407_通行费电子发票_2张.zip/invoice.zip/xml/ETC0043.xml": etc_xml(
                                "ETC0043",
                                issue_date="2026-04-02",
                                plate_number="云A516HJ",
                                total_amount="0.43",
                            ),
                            "extra/xml/EXTRA.xml": etc_xml(
                                "EXTRA",
                                issue_date="2026-04-02",
                                plate_number="云A516HJ",
                                total_amount="99.99",
                            ),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        self.assertEqual(preview.allowed_invoice_numbers, ["ETC0043", "ETC14638"])
        included = [item for item in preview.items if item.filter_status == "included"]
        self.assertEqual({item.invoice_number for item in included}, {"ETC14638", "ETC0043"})
        self.assertEqual({item.requirement_id for item in included}, {"TASK-REQ-0001+TASK-REQ-0002"})

    def test_zip_preview_disambiguates_same_day_duplicate_amount_by_invoice_request_time(self) -> None:
        task = ready_task_with_requirement(
            amount="71.25",
            transaction_at="2026-04-08 18:57:17",
            invoice_count=2,
        )
        task.expected_etc_invoice_requirements.append(
            ExpectedEtcInvoiceRequirement(
                requirement_id="TASK-REQ-0002",
                task_id="TASK",
                credit_card_item_id="CARD-2",
                ticket_root_item_id="TICKET-2",
                vehicle_plate="云ADA0381",
                transaction_at="2026-04-08 11:13:41",
                date_window_start="2026-04-07",
                date_window_end="2026-04-09",
                amount=Decimal("71.25"),
                invoice_count=2,
            )
        )

        preview = preview_etc_zip_for_task(
            task=task,
            uploads=[
                UploadedEtcZipFile(
                    "ticket-root.zip",
                    zip_bytes(
                        {
                            "20260408_通行费电子发票_2张.zip/invoice.zip/xml/ETC2950-A.xml": etc_xml(
                                "ETC2950-A",
                                issue_date="2026-04-08",
                                request_time="2026-04-08 16:27:04",
                                total_amount="29.50",
                            ),
                            "20260408_通行费电子发票_2张.zip/invoice.zip/xml/ETC4175-A.xml": etc_xml(
                                "ETC4175-A",
                                issue_date="2026-04-08",
                                request_time="2026-04-08 16:27:04",
                                total_amount="41.75",
                            ),
                            "20260410_通行费电子发票_2张.zip/invoice.zip/xml/ETC2935-B.xml": etc_xml(
                                "ETC2935-B",
                                issue_date="2026-04-08",
                                request_time="2026-04-10 16:26:33",
                                total_amount="29.35",
                            ),
                            "20260410_通行费电子发票_2张.zip/invoice.zip/xml/ETC4190-B.xml": etc_xml(
                                "ETC4190-B",
                                issue_date="2026-04-08",
                                request_time="2026-04-10 16:26:32",
                                total_amount="41.90",
                            ),
                        }
                    ),
                )
            ],
        )

        self.assertEqual(preview.blocking_issues, [])
        included_by_requirement = {
            requirement_id: {
                item.invoice_number
                for item in preview.items
                if item.requirement_id == requirement_id and item.filter_status == "included"
            }
            for requirement_id in {"TASK-REQ-0001", "TASK-REQ-0002"}
        }
        self.assertEqual(included_by_requirement["TASK-REQ-0001"], {"ETC2935-B", "ETC4190-B"})
        self.assertEqual(included_by_requirement["TASK-REQ-0002"], {"ETC2950-A", "ETC4175-A"})

    def test_zip_preview_blocks_single_invoice_allocated_to_multiple_requirements(self) -> None:
        duplicate_ticket_text = TICKET_ROOT_TEXT + """
车牌号 云ADA0381
交易时间 2026-03-03 18:06:18
入口站 昆明南站
出口站 九龙池站
金额 25.00
发票张数 1
"""
        service, task_id = self._parsed_task()
        service.apply_parse_result(
            task_id=task_id,
            parse_result=TicketRootPdfTextParser().parse_text(file_id="TICKET-2", text=duplicate_ticket_text),
            actor="alice",
        )
        task = service.refresh_matches(task_id=task_id)
        card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("25.00"))
        matching_tickets = [ticket for ticket in task.ticket_root_items if ticket.amount == Decimal("25.00")]
        for ticket in matching_tickets:
            task = service.patch_item(
                task_id=task_id,
                item_id=card.item_id,
                expected_version=task.version,
                actor="alice",
                payload={"action": "link_ticket", "ticketItemId": ticket.item_id},
            )
        task = service.patch_item(
            task_id=task_id,
            item_id=card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "set_manual_resolution", "manualResolution": "included_etc"},
        )
        other_card = next(item for item in task.credit_card_items if item.settlement_amount == Decimal("23.00"))
        task = service.patch_item(
            task_id=task_id,
            item_id=other_card.item_id,
            expected_version=task.version,
            actor="alice",
            payload={"action": "exclude_card", "manualResolution": "excluded_non_etc", "reason": "非本次报销"},
        )
        confirmed = service.confirm_task(
            task_id=task_id,
            expected_version=task.version,
            actor="alice",
            approved_delta="-50.00",
            approved_delta_note="测试重复requirement",
        )

        preview = preview_etc_zip_for_task(
            task=confirmed,
            uploads=[UploadedEtcZipFile("etc.zip", etc_zip(["ETC001"], include_pdf=True))],
        )

        self.assertTrue(any(issue["error"] == "duplicate_requirement_invoice_match" for issue in preview.blocking_issues))
        with self.assertRaisesRegex(ValueError, "duplicate_requirement_invoice_match"):
            validate_etc_zip_confirm_for_task(task=confirmed, preview=preview)

    def test_uploaded_source_file_uses_state_store_file_storage_api_when_available(self) -> None:
        class FakeStateStore:
            data_dir = None

            def __init__(self) -> None:
                self.snapshot: dict = {}
                self.stored: list[dict] = []

            def load_etc_reconciliation_state(self) -> dict:
                return self.snapshot

            def save_etc_reconciliation_state(self, snapshot: dict) -> None:
                self.snapshot = snapshot

            def store_etc_reconciliation_file(
                self,
                *,
                task_id: str,
                file_id: str,
                file_name: str,
                content: bytes,
            ) -> str:
                self.stored.append(
                    {
                        "task_id": task_id,
                        "file_id": file_id,
                        "file_name": file_name,
                        "content": content,
                    }
                )
                return f"gridfs://{file_id}/{file_name}"

        store = FakeStateStore()
        service = EtcReconciliationTaskService(state_store=store)
        task = service.create_task(title="ETC", created_by="alice")

        uploaded = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket bytes",
            created_by="alice",
        )

        self.assertEqual(uploaded.stored_path, f"gridfs://{uploaded.file_id}/ticket.pdf")
        self.assertEqual(store.stored[0]["task_id"], task.task_id)
        self.assertEqual(store.stored[0]["content"], b"ticket bytes")

    def test_upload_rolls_back_memory_state_when_persist_fails_and_retry_can_overwrite_blob(self) -> None:
        class FlakyStateStore:
            data_dir = None

            def __init__(self) -> None:
                self.snapshot: dict = {}
                self.fail_next_save = False
                self.stored_by_ref: dict[str, bytes] = {}

            def load_etc_reconciliation_state(self) -> dict:
                return self.snapshot

            def save_etc_reconciliation_state(self, snapshot: dict) -> None:
                if self.fail_next_save:
                    self.fail_next_save = False
                    raise RuntimeError("simulated state write failure")
                self.snapshot = snapshot

            def store_etc_reconciliation_file(
                self,
                *,
                task_id: str,
                file_id: str,
                file_name: str,
                content: bytes,
            ) -> str:
                ref = f"gridfs://{task_id}:{file_id}/{file_name}"
                self.stored_by_ref[ref] = content
                return ref

        store = FlakyStateStore()
        service = EtcReconciliationTaskService(state_store=store)
        task = service.create_task(title="ETC", created_by="alice")
        store.fail_next_save = True

        with self.assertRaises(RuntimeError):
            service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name="ticket.pdf",
                content_type="application/pdf",
                content=b"ticket bytes",
                created_by="alice",
            )

        self.assertEqual(service.get_task(task.task_id).source_files, [])

        uploaded = service.store_uploaded_source_file(
            task_id=task.task_id,
            source_kind=SourceFileKind.TICKET_ROOT,
            original_name="ticket.pdf",
            content_type="application/pdf",
            content=b"ticket bytes",
            created_by="alice",
        )

        self.assertEqual(uploaded.file_id, "ETC-RECON-FILE-000001")
        self.assertEqual(len(service.get_task(task.task_id).source_files), 1)

    def test_create_task_returns_draft_task_and_persists_to_state_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = EtcReconciliationTaskService(state_store=store)

            task = service.create_task(title="2026-03 ETC 对账", created_by="alice")
            reloaded = EtcReconciliationTaskService(state_store=store)

        self.assertEqual(task.status, EtcReconciliationTaskStatus.DRAFT)
        self.assertEqual(task.version, 1)
        self.assertEqual(task.title, "2026-03 ETC 对账")
        self.assertEqual(task.created_by, "alice")
        self.assertEqual(len(task.audit_events), 1)
        self.assertEqual(reloaded.get_task(task.task_id).title, "2026-03 ETC 对账")

    def test_uploaded_source_file_metadata_is_durable_and_idempotent_by_hash(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = EtcReconciliationTaskService(state_store=store)
            task = service.create_task(title="ETC", created_by="alice")
            content = b"synthetic statement bytes"

            first = service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
                original_name="ccb.pdf",
                content_type="application/pdf",
                content=content,
                created_by="alice",
            )
            second = service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
                original_name="same-content.pdf",
                content_type="application/pdf",
                content=content,
                created_by="alice",
            )
            reloaded = EtcReconciliationTaskService(state_store=store)

            reloaded_file = reloaded.get_task(task.task_id).source_files[0]
            self.assertEqual(first.file_id, second.file_id)
            self.assertEqual(first.original_name, "ccb.pdf")
            self.assertEqual(first.content_type, "application/pdf")
            self.assertEqual(first.size_bytes, len(content))
            self.assertEqual(len(first.sha256), 64)
            self.assertEqual(Path(first.stored_path).read_bytes(), content)
            self.assertEqual(Path(reloaded_file.stored_path).read_bytes(), content)
            self.assertEqual(reloaded.get_task(task.task_id).version, 2)

    def test_apply_parse_result_replaces_existing_file_result_without_duplicate_amounts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = service.create_task(title="ETC", created_by="alice")
            source_file = service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
                original_name="fuel.jpg",
                content_type="image/jpeg",
                content=b"fuel image bytes",
                created_by="alice",
            )
            parse_result = SupplementEvidenceParser().parse_text(
                file_id=source_file.file_id,
                text=NON_ETC_SUPPLEMENT_TEXT,
                source_name=source_file.original_name,
            )

            first = service.apply_parse_result(task_id=task.task_id, parse_result=parse_result, actor="alice")
            second = service.apply_parse_result(task_id=task.task_id, parse_result=parse_result, actor="alice")

            self.assertEqual(len(first.supplement_evidences), 1)
            self.assertEqual(len(second.parse_results), 1)
            self.assertEqual(len(second.supplement_evidences), 1)
            self.assertEqual(second.supplement_count, 1)
            self.assertEqual(second.supplement_amount, Decimal("200.00"))

    def test_apply_parse_result_rejects_blocking_reparse_without_deleting_previous_items(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = service.create_task(title="ETC", created_by="alice")
            initial = CcbCreditCardStatementParser().parse_text(file_id="FILE-1", text=CCB_STATEMENT_TEXT)
            failed = CcbCreditCardStatementParser().parse_text(file_id="FILE-1", text="")

            service.apply_parse_result(task_id=task.task_id, parse_result=initial, actor="alice")

            with self.assertRaises(ValueError):
                service.apply_parse_result(task_id=task.task_id, parse_result=failed, actor="alice")

            current_task = service.get_task(task.task_id)
            self.assertEqual(len(current_task.parse_results), 1)
            self.assertEqual(len(current_task.credit_card_items), 4)

    def test_apply_parse_result_preserves_new_blocking_issue_and_hydrates_it(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = service.create_task(title="ETC", created_by="alice")
            failed = TicketRootDocumentParser(
                pdf_text_extractor=lambda _content: "",
                ocr_text_extractor=lambda _content: [],
            ).parse_file(file_id="FILE-1", content=b"%PDF-1.4")

            updated = service.apply_parse_result(task_id=task.task_id, parse_result=failed, actor="alice")
            restored = EtcReconciliationTaskService.from_snapshot(service.snapshot(), data_dir=Path(temp_dir))
            restored_issue = restored.get_task(task.task_id).parse_results[0].issues[0]

            self.assertFalse(updated.parse_results[0].ok)
            self.assertEqual(updated.parse_results[0].issues[0].severity, ParseIssueSeverity.BLOCKING)
            self.assertEqual(restored_issue.severity, ParseIssueSeverity.BLOCKING)
            self.assertEqual(restored_issue.field_name, "ticket_root_text")

    def test_snapshot_hydrate_preserves_items_issues_and_audit_events(self) -> None:
        with TemporaryDirectory() as temp_dir:
            service = EtcReconciliationTaskService(data_dir=Path(temp_dir))
            task = service.create_task(title="ETC", created_by="alice")
            source_file = service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
                original_name="fuel.jpg",
                content_type="image/jpeg",
                content=b"fuel image bytes",
                created_by="alice",
            )
            parse_result = SupplementEvidenceParser().parse_text(
                file_id=source_file.file_id,
                text=NON_ETC_SUPPLEMENT_TEXT,
                source_name=source_file.original_name,
            )
            service.apply_parse_result(task_id=task.task_id, parse_result=parse_result, actor="alice")

            restored = EtcReconciliationTaskService.from_snapshot(
                service.snapshot(),
                data_dir=Path(temp_dir),
            )
            restored_task = restored.get_task(task.task_id)

            self.assertEqual(restored.snapshot(), service.snapshot())
            self.assertEqual(len(restored_task.supplement_evidences), 1)
            self.assertEqual(restored_task.supplement_evidences[0].tags, ["ETC补充凭证"])
            self.assertEqual(len(restored_task.parse_results), 1)
            self.assertGreaterEqual(len(restored_task.audit_events), 3)
            self.assertEqual(Path(restored_task.source_files[0].stored_path).read_bytes(), b"fuel image bytes")

    def test_ccb_credit_card_statement_parser_preserves_rows_and_marks_etc_candidates(self) -> None:
        result = CcbCreditCardStatementParser().parse_text(file_id="FILE-1", text=CCB_STATEMENT_TEXT)

        self.assertTrue(result.ok)
        self.assertEqual(len(result.credit_card_items), 4)
        first = result.credit_card_items[0]
        self.assertEqual(first.transaction_date, "2026-03-03")
        self.assertEqual(first.posting_date, "2026-03-04")
        self.assertEqual(first.card_last4, "3632")
        self.assertEqual(first.description, "微信支付-云南昆明南站高速通行费")
        self.assertEqual(first.currency, "CNY")
        self.assertEqual(first.amount, Decimal("25.00"))
        self.assertEqual(first.settlement_amount, Decimal("25.00"))
        self.assertTrue(first.is_etc_candidate)
        self.assertEqual(first.candidate_reason, "etc_keyword")
        self.assertEqual(first.source_line, 6)

        fuel = result.credit_card_items[2]
        repayment = result.credit_card_items[3]
        self.assertFalse(fuel.is_etc_candidate)
        self.assertEqual(fuel.recommendation_status, "not_candidate")
        self.assertFalse(repayment.is_etc_candidate)
        self.assertEqual(repayment.amount, Decimal("-248.00"))

    def test_ccb_credit_card_statement_parser_accepts_repeated_settlement_currency_rows(self) -> None:
        result = CcbCreditCardStatementParser().parse_text(
            file_id="FILE-1",
            text="""
中国建设银行信用卡账单
交易日 入账日 卡号 摘要 币种 交易金额 币种 入账金额
2026-03-28 2026-03-28 8514 20260327高速通行费云南昆明南站云 CNY 23.50 CNY 23.50
2026-04-15 2026-04-15 8514 财付通-贵州黔通智联科技股份有限公司 CNY 146.98 CNY 146.98
2026-04-20 2026-04-20 8514 自动还款 CNY -500.00 CNY -500.00
""",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.credit_card_items), 3)
        first = result.credit_card_items[0]
        self.assertEqual(first.transaction_date, "2026-03-28")
        self.assertEqual(first.posting_date, "2026-03-28")
        self.assertEqual(first.card_last4, "8514")
        self.assertEqual(first.description, "20260327高速通行费云南昆明南站云")
        self.assertEqual(first.amount, Decimal("23.50"))
        self.assertEqual(first.settlement_amount, Decimal("23.50"))
        self.assertTrue(first.is_etc_candidate)
        self.assertTrue(result.credit_card_items[1].is_etc_candidate)
        self.assertFalse(result.credit_card_items[2].is_etc_candidate)

    def test_ccb_credit_card_statement_empty_text_creates_blocking_parse_issue(self) -> None:
        result = CcbCreditCardStatementParser().parse_text(file_id="FILE-1", text="")

        self.assertFalse(result.ok)
        self.assertEqual(result.credit_card_items, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].field_name, "statement_rows")

    def test_ticket_root_pdf_text_parser_extracts_normalized_item(self) -> None:
        result = TicketRootPdfTextParser().parse_text(file_id="FILE-1", text=TICKET_ROOT_TEXT, page_number=2)

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 1)
        item = result.ticket_root_items[0]
        self.assertEqual(item.vehicle_plate, "云ADA0381")
        self.assertEqual(item.transaction_at, "2026-03-03 17:06:18")
        self.assertEqual(item.amount, Decimal("25.00"))
        self.assertEqual(item.entry_station, "昆明南站")
        self.assertEqual(item.exit_station, "九龙池站")
        self.assertEqual(item.invoice_count, 1)
        self.assertEqual(item.source_page, 2)
        self.assertEqual(item.extraction_method, "pdf_text")

    def test_ticket_root_pdf_text_parser_extracts_multiple_records_with_page_plate(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text="""
票根网通行明细
车牌号 云ADA0381
交易时间 2026-03-03 17:06:18
入口站 昆明南站
出口站 九龙池站
金额 25.00
发票张数 1
交易时间 2026-03-04 09:30:00
入口站 呈贡站
出口站 石林站
金额 23.00
发票张数 2
""",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 2)
        self.assertEqual([item.vehicle_plate for item in result.ticket_root_items], ["云ADA0381", "云ADA0381"])
        self.assertEqual([item.amount for item in result.ticket_root_items], [Decimal("25.00"), Decimal("23.00")])
        self.assertEqual(result.ticket_root_items[1].invoice_count, 2)

    def test_ticket_root_pdf_text_parser_extracts_multiple_ocr_ticket_root_records(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text="""
票根网
车牌号 云ADA0381
交易时间：2026-04-28 20:43:33
交易金额：￥126.35
发票数量：1
云南会泽站 -> 云南昆明北站
交易时间：2026-04-29 08:15:01
交易金额：￥35.20
发票数量：2
云南昆明北站 -> 云南嵩明站
""",
            extraction_method="ocr",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 2)
        first, second = result.ticket_root_items
        self.assertEqual(first.vehicle_plate, "云ADA0381")
        self.assertEqual(first.transaction_at, "2026-04-28 20:43:33")
        self.assertEqual(first.amount, Decimal("126.35"))
        self.assertEqual(first.invoice_count, 1)
        self.assertEqual(first.entry_station, "云南会泽站")
        self.assertEqual(first.exit_station, "云南昆明北站")
        self.assertEqual(first.extraction_method, "ocr")
        self.assertEqual(second.amount, Decimal("35.20"))
        self.assertEqual(second.invoice_count, 2)
        self.assertEqual(second.entry_station, "云南昆明北站")
        self.assertEqual(second.exit_station, "云南嵩明站")

    def test_ticket_root_pdf_text_parser_extracts_ocr_records_with_compact_time_and_station_rows(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text="""
票根网
车牌号：
云ADA0381
入口收费站/出口收费站
￥126.35
交易时间：2026-04-2820:43:33
交易金额：
发票数量：1
云南会泽站
云南昆明北站
交易时间：2026-04-2818:11:15
交易金额：￥75.05
发票数量：1
云南昭通南站
云南会泽站
""",
            extraction_method="ocr",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 2)
        first, second = result.ticket_root_items
        self.assertEqual(first.transaction_at, "2026-04-28 20:43:33")
        self.assertEqual(first.amount, Decimal("126.35"))
        self.assertEqual(first.entry_station, "云南会泽站")
        self.assertEqual(first.exit_station, "云南昆明北站")
        self.assertEqual(second.transaction_at, "2026-04-28 18:11:15")
        self.assertEqual(second.amount, Decimal("75.05"))
        self.assertEqual(second.entry_station, "云南昭通南站")
        self.assertEqual(second.exit_station, "云南会泽站")

    def test_ticket_root_pdf_text_parser_keeps_prefixed_amount_with_next_ocr_record(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text="""
票根网
车牌号 云ADA0381
交易时间：2026-04-2519:41:54
交易金额：￥12.35
发票数量：1
云南兔耳站
云南昆明北站
交易金额：￥18.05
交易时间：2026-04-2514:13:09
发票数量：1
云南军马场站
云南昆明北站
""",
            extraction_method="ocr",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 2)
        self.assertEqual([item.amount for item in result.ticket_root_items], [Decimal("12.35"), Decimal("18.05")])
        self.assertEqual([item.transaction_at for item in result.ticket_root_items], ["2026-04-25 19:41:54", "2026-04-25 14:13:09"])
        self.assertEqual(result.ticket_root_items[1].entry_station, "云南军马场站")
        self.assertEqual(result.ticket_root_items[1].exit_station, "云南昆明北站")

    def test_ticket_root_document_parser_default_ocr_extractor_reads_image_text(self) -> None:
        from PIL import Image
        import fin_ops_platform.services.etc_document_parsers as parsers

        class FakeRapidOCR:
            def __call__(self, _content: bytes) -> tuple[list[list[object]], object]:
                return (
                    [
                        [None, "票根网"],
                        [None, "车牌号 云ADA0381"],
                        [None, "交易时间：2026-04-28 20:43:33"],
                        [None, "交易金额：￥126.35"],
                        [None, "发票数量：1"],
                        [None, "云南会泽站 -> 云南昆明北站"],
                    ],
                    None,
                )

        image = Image.new("RGB", (10, 10), "white")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        original_rapid_ocr = parsers.RapidOCR
        try:
            parsers.RapidOCR = FakeRapidOCR
            result = TicketRootDocumentParser(
                pdf_text_extractor=lambda _content: "",
            ).parse_file(file_id="FILE-1", content=buffer.getvalue())
        finally:
            parsers.RapidOCR = original_rapid_ocr

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 1)
        self.assertEqual(result.ticket_root_items[0].amount, Decimal("126.35"))
        self.assertEqual(result.ticket_root_items[0].entry_station, "云南会泽站")
        self.assertEqual(result.ticket_root_items[0].exit_station, "云南昆明北站")
        self.assertEqual(result.ticket_root_items[0].extraction_method, "ocr")

    def test_ticket_root_pdf_text_extraction_tries_fitz_after_empty_pdfplumber_and_closes_document(self) -> None:
        import fin_ops_platform.services.etc_document_parsers as parsers

        class EmptyPdfplumber:
            class Document:
                pages = []

                def __enter__(self) -> "EmptyPdfplumber.Document":
                    return self

                def __exit__(self, *_args: object) -> None:
                    return None

            @staticmethod
            def open(_content: BytesIO) -> "EmptyPdfplumber.Document":
                return EmptyPdfplumber.Document()

        class FakeFitzPage:
            @staticmethod
            def get_text(_mode: str = "text") -> str:
                return TICKET_ROOT_TEXT

        class FakeFitzDocument:
            def __init__(self) -> None:
                self.closed = False

            def __iter__(self):
                return iter([FakeFitzPage()])

            def close(self) -> None:
                self.closed = True

        fake_document = FakeFitzDocument()

        class FakeFitz:
            @staticmethod
            def open(*_args: object, **_kwargs: object) -> FakeFitzDocument:
                return fake_document

        original_pdfplumber = parsers.pdfplumber
        original_fitz = parsers.fitz
        try:
            parsers.pdfplumber = EmptyPdfplumber
            parsers.fitz = FakeFitz
            text = parsers._extract_pdf_text(b"%PDF-1.4")
        finally:
            parsers.pdfplumber = original_pdfplumber
            parsers.fitz = original_fitz

        self.assertIn("车牌号 云ADA0381", text)
        self.assertTrue(fake_document.closed)

    def test_pdf_text_extraction_uses_pdftotext_when_python_pdf_libraries_are_unavailable(self) -> None:
        import fin_ops_platform.services.etc_document_parsers as parsers

        calls: list[tuple[list[str], int | float | None, bool, bool]] = []

        def fake_run(command: list[str], *, timeout: int | float | None, capture_output: bool, check: bool) -> SimpleNamespace:
            calls.append((command, timeout, capture_output, check))
            return SimpleNamespace(returncode=0, stdout=f"{APRIL_STATEMENT_TEXT}\n交易明细".encode("utf-8"), stderr=b"")

        originals = {
            "pdfplumber": (hasattr(parsers, "pdfplumber"), getattr(parsers, "pdfplumber", None)),
            "fitz": (hasattr(parsers, "fitz"), getattr(parsers, "fitz", None)),
            "shutil": (hasattr(parsers, "shutil"), getattr(parsers, "shutil", None)),
            "subprocess": (hasattr(parsers, "subprocess"), getattr(parsers, "subprocess", None)),
        }
        try:
            parsers.pdfplumber = None
            parsers.fitz = None
            parsers.shutil = SimpleNamespace(which=lambda name: "/usr/bin/pdftotext" if name == "pdftotext" else None)
            parsers.subprocess = SimpleNamespace(run=fake_run)
            text = parsers._extract_pdf_text(b"%PDF-1.4\n%%EOF")
        finally:
            for name, (existed, value) in originals.items():
                if existed:
                    setattr(parsers, name, value)
                elif hasattr(parsers, name):
                    delattr(parsers, name)

        self.assertIn("交易明细", text)
        self.assertEqual(len(calls), 1)
        command, timeout, capture_output, check = calls[0]
        self.assertEqual(command[0], "/usr/bin/pdftotext")
        self.assertIn("-layout", command)
        self.assertEqual(command[-1], "-")
        self.assertLessEqual(timeout or 999, 10)
        self.assertTrue(capture_output)
        self.assertFalse(check)

    def test_credit_card_statement_pdf_parse_uses_pdftotext_when_python_pdf_libraries_are_unavailable(self) -> None:
        import fin_ops_platform.services.etc_document_parsers as parsers

        def fake_run(command: list[str], *, timeout: int | float | None, capture_output: bool, check: bool) -> SimpleNamespace:
            self.assertIn("-layout", command)
            self.assertEqual(command[-1], "-")
            return SimpleNamespace(returncode=0, stdout=APRIL_STATEMENT_TEXT.encode("utf-8"), stderr=b"")

        originals = {
            "pdfplumber": (hasattr(parsers, "pdfplumber"), getattr(parsers, "pdfplumber", None)),
            "fitz": (hasattr(parsers, "fitz"), getattr(parsers, "fitz", None)),
            "shutil": (hasattr(parsers, "shutil"), getattr(parsers, "shutil", None)),
            "subprocess": (hasattr(parsers, "subprocess"), getattr(parsers, "subprocess", None)),
        }
        try:
            parsers.pdfplumber = None
            parsers.fitz = None
            parsers.shutil = SimpleNamespace(which=lambda name: "/usr/bin/pdftotext" if name == "pdftotext" else None)
            parsers.subprocess = SimpleNamespace(run=fake_run)
            result = CcbCreditCardStatementParser().parse_pdf_bytes(file_id="CARD-APRIL", content=b"%PDF-1.4\n%%EOF")
        finally:
            for name, (existed, value) in originals.items():
                if existed:
                    setattr(parsers, name, value)
                elif hasattr(parsers, name):
                    delattr(parsers, name)

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, [])
        self.assertGreater(len(result.credit_card_items), 0)
        self.assertEqual(result.credit_card_items[0].description, "财付通-贵州黔通智联高速通行费")

    def test_pdf_text_extraction_returns_empty_string_when_pdftotext_is_unavailable_or_fails(self) -> None:
        import fin_ops_platform.services.etc_document_parsers as parsers

        originals = {
            "pdfplumber": (hasattr(parsers, "pdfplumber"), getattr(parsers, "pdfplumber", None)),
            "fitz": (hasattr(parsers, "fitz"), getattr(parsers, "fitz", None)),
            "shutil": (hasattr(parsers, "shutil"), getattr(parsers, "shutil", None)),
            "subprocess": (hasattr(parsers, "subprocess"), getattr(parsers, "subprocess", None)),
        }
        try:
            parsers.pdfplumber = None
            parsers.fitz = None
            parsers.shutil = SimpleNamespace(which=lambda _name: None)
            parsers.subprocess = SimpleNamespace(run=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
            self.assertEqual(parsers._extract_pdf_text(b"%PDF-1.4\n%%EOF"), "")

            parsers.shutil = SimpleNamespace(which=lambda name: "/usr/bin/pdftotext" if name == "pdftotext" else None)
            self.assertEqual(parsers._extract_pdf_text(b"%PDF-1.4\n%%EOF"), "")
        finally:
            for name, (existed, value) in originals.items():
                if existed:
                    setattr(parsers, name, value)
                elif hasattr(parsers, name):
                    delattr(parsers, name)

    def test_ticket_root_parser_falls_back_to_ocr_when_pdf_text_has_no_items(self) -> None:
        parser = TicketRootDocumentParser(
            pdf_text_extractor=lambda _content: "",
            ocr_text_extractor=lambda _content: [TICKET_ROOT_TEXT],
        )

        result = parser.parse_file(file_id="FILE-1", content=b"%PDF-1.4")

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 1)
        self.assertEqual(result.ticket_root_items[0].extraction_method, "ocr")

    def test_ticket_root_parser_falls_back_to_ocr_when_pdf_text_is_incomplete(self) -> None:
        parser = TicketRootDocumentParser(
            pdf_text_extractor=lambda _content: TICKET_ROOT_TEXT_WITHOUT_PLATE,
            ocr_text_extractor=lambda _content: [TICKET_ROOT_TEXT],
        )

        result = parser.parse_file(file_id="FILE-1", content=b"%PDF-1.4")

        self.assertTrue(result.ok)
        self.assertEqual(len(result.ticket_root_items), 1)
        self.assertEqual(result.ticket_root_items[0].vehicle_plate, "云ADA0381")
        self.assertEqual(result.ticket_root_items[0].extraction_method, "ocr")

    def test_ticket_root_parser_ignores_invoice_application_pages_without_ticket_details(self) -> None:
        parser = TicketRootDocumentParser(
            pdf_text_extractor=lambda _content: "",
            ocr_text_extractor=lambda _content: [
                """
票根网
车牌号：
云ADA0381
开票申请时间：2026-03-3117:19:57
开票金额：￥9.50
发票数量：1张
""",
                """
开票金额：￥197.60
开票申请时间：2026-03-2520:23:57
消费发票申请
发票数量：1张
开票金额：￥19.00
开票申请时间：2026-03-2315:46:00
消费发票申请
发票数量：1张
""",
                """
下一页
版权所有：行云数聚（北京）科技有限公司
京ICP备17066956号
""",
            ],
        )

        result = parser.parse_file(file_id="FILE-1", content=b"%PDF-1.4")

        self.assertTrue(result.ok)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.ticket_root_items, [])

    def test_ticket_root_parser_ignores_invoice_application_page_without_missing_plate_issue(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-INVOICE-APPLICATION",
            text="""
消费发票申请
开票记录
开票完成
交易时间 2026-04-10 21:36:24
金额 147.25
""",
            page_number=1,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(result.issues, [])

    def test_ticket_root_parser_without_text_or_ocr_creates_blocking_parse_issue(self) -> None:
        result = TicketRootDocumentParser(
            pdf_text_extractor=lambda _content: "",
            ocr_text_extractor=lambda _content: [],
        ).parse_file(file_id="FILE-1", content=b"%PDF-1.4")

        self.assertFalse(result.ok)
        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].field_name, "ticket_root_text")

    def test_ticket_root_item_without_vehicle_plate_creates_blocking_parse_issue(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text=TICKET_ROOT_TEXT_WITHOUT_PLATE,
            page_number=1,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].file_id, "FILE-1")
        self.assertEqual(result.issues[0].source_page, 1)
        self.assertEqual(result.issues[0].extraction_method, "pdf_text")
        self.assertIn("车牌", result.issues[0].message)

    def test_ticket_root_item_missing_required_amount_creates_blocking_parse_issue(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text=TICKET_ROOT_TEXT_WITHOUT_AMOUNT,
            page_number=1,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].field_name, "amount")
        self.assertIn("金额", result.issues[0].message)

    def test_ticket_root_item_missing_required_transaction_time_creates_blocking_parse_issue(self) -> None:
        result = TicketRootPdfTextParser().parse_text(
            file_id="FILE-1",
            text=TICKET_ROOT_TEXT_WITHOUT_TRANSACTION_AT,
            page_number=1,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.ticket_root_items, [])
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0].severity, ParseIssueSeverity.BLOCKING)
        self.assertEqual(result.issues[0].field_name, "transaction_at")
        self.assertIn("交易时间", result.issues[0].message)

    def test_supplement_parser_classifies_non_etc_evidence_with_required_tag(self) -> None:
        result = SupplementEvidenceParser().parse_text(
            file_id="FILE-1",
            text=NON_ETC_SUPPLEMENT_TEXT,
            source_name="fuel.jpg",
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.supplement_evidences), 1)
        evidence = result.supplement_evidences[0]
        self.assertEqual(evidence.evidence_kind, "non_etc_invoice")
        self.assertEqual(evidence.amount, Decimal("200.00"))
        self.assertEqual(evidence.tags, ["ETC补充凭证"])
        self.assertFalse(evidence.include_in_etc_zip_check)
        self.assertTrue(evidence.include_in_oa_submission)
        self.assertTrue(evidence.include_in_workbench)

    def test_supplement_parser_accepts_api_etc_invoice_kind_for_zip_check(self) -> None:
        result = SupplementEvidenceParser().parse_text(
            file_id="FILE-1",
            text="""
ETC发票
商户全称 云南高速
支付时间 2026年3月4日 14:13:44
金额 23.00
""",
            source_name="etc-supplement.pdf",
            evidence_kind_override="etc_invoice",
        )

        self.assertTrue(result.ok)
        evidence = result.supplement_evidences[0]
        self.assertEqual(evidence.evidence_kind, "etc_invoice")
        self.assertTrue(evidence.include_in_etc_zip_check)


if __name__ == "__main__":
    unittest.main()
