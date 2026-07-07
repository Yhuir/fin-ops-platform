from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID, PAY_STATUS_PENDING
from fin_ops_platform.services.oa_pending_payment_service import (
    OaPendingPaymentError,
    OaPendingPaymentQueryService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeWorkbenchRelationFacade


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records
        self.records_by_id = {record.id: record for record in records}

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class PartialListOAProjection(StaticOAProjection):
    def __init__(self, listed_records: list[OAApplicationRecord], lookup_records: list[OAApplicationRecord]) -> None:
        super().__init__(lookup_records)
        self.listed_records = list(listed_records)

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.listed_records)


class FakePaymentStatusRepository:
    def __init__(self, *, flow_ids: dict[str, str], paid_flow_ids: set[str]) -> None:
        self.flow_ids = dict(flow_ids)
        self.paid_flow_ids = set(paid_flow_ids)
        self.resolved_records: list[str] = []

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        self.resolved_records.append(record.id)
        return self.flow_ids.get(record.id)

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        pay_status = PAY_STATUS_PAID if flow_id in self.paid_flow_ids else PAY_STATUS_PENDING
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=pay_status)

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)


class FakeAdmissionPaymentStatusRepository:
    def __init__(self, *, flow_ids: dict[str, str], admitted_flow_ids: set[str]) -> None:
        self.flow_ids = dict(flow_ids)
        self.admitted_flow_ids = set(admitted_flow_ids)
        self.list_calls = 0

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        self.list_calls += 1
        return {
            flow_id: OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PENDING)
            for flow_id in self.admitted_flow_ids
        }

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        return self.flow_ids.get(record.id)

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        return self.list_payment_statuses().get(flow_id)

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)


class FakePendingRelationService:
    def __init__(self, relations: list[dict[str, object]] | None = None) -> None:
        self.relations = [dict(relation) for relation in list(relations or [])]

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        wanted = {str(row_id) for row_id in list(row_ids or [])}
        return [
            relation
            for relation in self.relations
            if wanted & {str(row_id) for row_id in list(relation.get("row_ids") or [])}
        ]


class OaPendingPaymentQueryServiceTests(unittest.TestCase):
    def test_relation_group_loads_all_oa_members_from_projection_lookup_and_suppresses_standalone_rows(self) -> None:
        banks = [
            self._bank("bank-group-a", "469600.00"),
            self._bank("bank-group-b", "64996.69"),
            self._bank("bank-group-c", "23053.31"),
            self._bank("bank-group-d", "29350.00"),
        ]
        invoice = self._invoice("inv-group-multi-bank", "SD-MULTI", "云南鹏源科技有限公司", "587000.00")
        oa_records = [
            self._oa("oa-group-primary", "樊祖芳", "469600.00", reason="80%尾款"),
            self._oa("oa-group-reserve", "樊祖芳", "29350.00", reason="5%质保金"),
            self._oa("oa-group-advance", "樊祖芳", "88050.00", reason="15%预付款"),
        ]
        pair_service = WorkbenchPairRelationService()
        self._relation(
            pair_service,
            "case-multi-oa-bank",
            [*[record.id for record in oa_records], *[bank.id for bank in banks], invoice.id],
            matched=True,
        )
        projection = PartialListOAProjection([oa_records[0]], oa_records)
        service = OaPendingPaymentQueryService(
            import_service=ImportNormalizationService(
                existing_transactions=banks,
                existing_invoices=[invoice],
            ),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service,
                transactions=banks,
                invoices=[invoice],
                oa_projection=projection,
            ),
            oa_projection=projection,
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["oa"]["amount"], "587000.00")
        self.assertEqual(row["oa"]["relationCount"], 3)
        self.assertEqual(row["oa"]["detailMode"], "list")
        self.assertEqual([summary["oaId"] for summary in row["oa"]["summaries"]], [
            "oa-group-primary",
            "oa-group-reserve",
            "oa-group-advance",
        ])
        self.assertEqual(row["bankTransaction"]["paidTotal"], "587000.00")
        self.assertEqual(row["bankTransaction"]["relationCount"], 4)
        self.assertEqual(row["bankTransaction"]["detailMode"], "list")

    def test_active_relation_group_returns_one_row_with_aggregated_totals(self) -> None:
        bank_group = self._bank("bank-group", "4450.00")
        invoice_group = self._invoice("inv-group", "SD-GROUP", "住宿供应商", "4450.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(
            pair_service,
            "case-grouped",
            ["oa-group-a", "oa-group-b", "oa-group-c", bank_group.id, invoice_group.id],
            matched=True,
        )
        service = self._service(
            oa_records=[
                self._oa("oa-group-a", "刘际涛", "1690.00", project_name="昭通卷烟厂平台维护"),
                self._oa("oa-group-b", "刘际涛", "1980.00", project_name="红塔集团应急维护"),
                self._oa("oa-group-c", "刘际涛", "780.00", project_name="昭通卷烟厂采购项目"),
            ],
            transactions=[bank_group],
            invoices=[invoice_group],
            pair_service=pair_service,
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["oaPaymentWriteback"]["code"], "not_written")
        self.assertEqual(row["oaPaymentWriteback"]["label"], "未写回")
        self.assertNotIn(row["paymentStatus"]["code"], {"overpaid", "merged_paid"})
        self.assertEqual(row["oa"]["amount"], "4450.00")
        self.assertEqual(row["oa"]["relationCount"], 3)
        self.assertTrue(row["oa"]["hasMultiple"])
        self.assertEqual(row["oa"]["detailMode"], "list")
        self.assertEqual([summary["oaId"] for summary in row["oa"]["summaries"]], ["oa-group-a", "oa-group-b", "oa-group-c"])
        self.assertEqual(row["bankTransaction"]["paidTotal"], "4450.00")
        self.assertEqual(row["bankTransaction"]["relationCount"], 1)
        self.assertEqual(row["invoice"]["totalWithTax"], "4450.00")
        self.assertEqual(row["invoice"]["relationCount"], 1)
        self.assertEqual(payload["summary"]["oaAmountTotal"], "4450.00")
        self.assertEqual(payload["summary"]["bankPaidTotal"], "4450.00")
        self.assertEqual(payload["summary"]["viewCounts"], {"completed": 3, "in_progress": 0})

    def test_paid_row_reads_oa_payment_status_writeback_state(self) -> None:
        bank = self._bank("bank-paid", "100.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-paid", ["oa-paid", bank.id], matched=True)
        payment_repository = FakePaymentStatusRepository(
            flow_ids={"oa-paid": "proc-paid"},
            paid_flow_ids={"proc-paid"},
        )
        service = self._service(
            oa_records=[
                self._oa("oa-paid", "张三", "100.00"),
            ],
            transactions=[bank],
            pair_service=pair_service,
            payment_repository=payment_repository,
        )

        row = service.list_rows(page_size=20)["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["oaPaymentWriteback"]["code"], "written")
        self.assertEqual(row["oaPaymentWriteback"]["label"], "已写回")
        self.assertEqual(row["oaPaymentWriteback"]["flowIds"], ["proc-paid"])
        self.assertEqual(payment_repository.resolved_records, ["oa-paid", "oa-paid"])

    def test_grouped_multiple_oa_and_multiple_banks_are_not_marked_overpaid(self) -> None:
        bank_first = self._bank("bank-group-first", "21966.70")
        bank_second = self._bank("bank-group-second", "9414.30")
        invoice_group = self._invoice("inv-bank-group", "SD-BANK-GROUP", "北京标志卓信科技有限公司", "31381.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(
            pair_service,
            "case-bank-group",
            ["oa-bank-group-a", "oa-bank-group-b", bank_first.id, bank_second.id, invoice_group.id],
            matched=True,
        )
        service = self._service(
            oa_records=[
                self._oa("oa-bank-group-a", "刘际涛", "21966.70", project_name="昭通卷烟厂能源集控维护"),
                self._oa("oa-bank-group-b", "杨丽萍", "9414.30", project_name="昭通卷烟厂能源集控维护"),
            ],
            transactions=[bank_first, bank_second],
            invoices=[invoice_group],
            pair_service=pair_service,
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertNotEqual(row["paymentStatus"]["code"], "overpaid")
        self.assertEqual(row["oa"]["amount"], "31381.00")
        self.assertEqual(row["bankTransaction"]["paidTotal"], "31381.00")
        self.assertEqual(row["bankTransaction"]["relationCount"], 2)
        self.assertTrue(row["bankTransaction"]["hasMultiple"])

    def test_grouped_payment_above_oa_total_is_paid_when_relation_is_linked(self) -> None:
        bank = self._bank("bank-above-group-total", "120.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(
            pair_service,
            "case-above-group-total",
            ["oa-above-a", "oa-above-b", bank.id],
            matched=False,
        )
        service = self._service(
            oa_records=[
                self._oa("oa-above-a", "张三", "50.00"),
                self._oa("oa-above-b", "李四", "40.00"),
            ],
            transactions=[bank],
            pair_service=pair_service,
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["oa"]["amount"], "90.00")
        self.assertEqual(row["bankTransaction"]["paidTotal"], "120.00")
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["oaPaymentWriteback"]["syncStatus"], "not_required")
        self.assertNotEqual(row["paymentStatus"]["code"], "overpaid")

    def test_oa_summary_exposes_application_time_from_detail_fields(self) -> None:
        service = self._service(
            oa_records=[
                self._oa(
                    "oa-application-time",
                    "张三",
                    "30.00",
                    detail_fields={"申请日期": "2026-05-25"},
                ),
            ]
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["oa"]["applicationTime"], "2026-05-25")
        self.assertEqual(row["paymentStatus"]["code"], "unpaid")

    def test_filter_sort_pagination_and_validation_are_server_side_contracts(self) -> None:
        service = self._service(
            oa_records=[
                self._oa("oa-1", "张三", "30.00", project_name="甲项目", apply_type="报销"),
                self._oa("oa-2", "李四", "80.00", project_name="乙项目", apply_type="支付"),
                self._oa("oa-3", "张三", "20.00", project_name="甲项目", apply_type="报销"),
            ]
        )

        payload = service.list_rows(
            page=1,
            page_size=1,
            keyword="甲项目",
            filters='[{"field":"oa_applicant","operator":"in","values":["张三"]}]',
            sort_field="oa_amount",
            sort_direction="desc",
        )

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["oa"]["id"], "oa-1")
        self.assertEqual(payload["summary"]["rowCount"], 2)
        self.assertEqual(payload["sort"], {"field": "oa_amount", "direction": "desc"})
        filter_fields = [field["field"] for field in service.filter_options()["fields"]]
        self.assertIn("oa_applicant", filter_fields)
        self.assertIn("payment_status", filter_fields)

        with self.assertRaises(OaPendingPaymentError) as field_error:
            service.list_rows(filters='[{"field":"bad","operator":"equals","value":"x"}]')
        with self.assertRaises(OaPendingPaymentError) as sort_error:
            service.list_rows(sort_field="bad")

        self.assertEqual(field_error.exception.error_code, "invalid_filter_field")
        self.assertEqual(sort_error.exception.error_code, "invalid_sort_field")

    def test_view_mode_filters_completed_and_in_progress_oa_records(self) -> None:
        service = self._service(
            oa_records=[
                self._oa("oa-completed", "张三", "30.00", workflow_status="completed"),
                self._oa("oa-legacy", "李四", "40.00", workflow_status=None),
                self._oa("oa-progress", "王五", "50.00", workflow_status="in_progress"),
            ]
        )

        default_payload = service.list_rows(page_size=20)
        progress_payload = service.list_rows(page_size=20, view_mode="in_progress")
        filter_payload = service.filter_options(view_mode="in_progress")

        self.assertEqual([row["oa"]["id"] for row in default_payload["rows"]], ["oa-completed", "oa-legacy"])
        self.assertEqual(default_payload["viewMode"], "completed")
        self.assertEqual([row["oa"]["id"] for row in progress_payload["rows"]], ["oa-progress"])
        self.assertEqual(progress_payload["rows"][0]["oa"]["workflowStatus"], "in_progress")
        self.assertEqual(progress_payload["viewMode"], "in_progress")
        self.assertEqual(filter_payload["context"]["viewMode"], "in_progress")

        with self.assertRaises(OaPendingPaymentError) as context:
            service.list_rows(view_mode="bad")
        self.assertEqual(context.exception.error_code, "invalid_view_mode")

    def test_only_in_progress_view_uses_payment_status_admission_projection(self) -> None:
        payment_repository = FakeAdmissionPaymentStatusRepository(
            flow_ids={
                "oa-progress-admitted": "mongo-progress",
                "oa-progress-duplicate": "mongo-duplicate",
            },
            admitted_flow_ids={"mongo-progress"},
        )
        service = self._service(
            oa_records=[
                self._oa("oa-completed-unified", "张三", "30.00", workflow_status="completed"),
            ],
            in_progress_oa_records=[
                self._oa("oa-progress-admitted", "李四", "40.00", workflow_status="in_progress"),
                self._oa("oa-progress-duplicate", "李四", "40.00", workflow_status="in_progress"),
            ],
            payment_repository=payment_repository,
        )

        completed_payload = service.list_rows(page_size=20)
        progress_payload = service.list_rows(page_size=20, view_mode="in_progress")

        self.assertEqual([row["oa"]["id"] for row in completed_payload["rows"]], ["oa-completed-unified"])
        self.assertEqual([row["oa"]["id"] for row in progress_payload["rows"]], ["oa-progress-admitted"])
        self.assertEqual(completed_payload["summary"]["viewCounts"], {"completed": 1, "in_progress": 1})
        self.assertEqual(progress_payload["summary"]["viewCounts"], {"completed": 1, "in_progress": 1})

    def test_in_progress_view_reuses_loaded_payment_statuses_for_admission_filter(self) -> None:
        payment_repository = FakeAdmissionPaymentStatusRepository(
            flow_ids={
                "oa-progress-admitted": "mongo-progress",
                "oa-progress-denied": "mongo-denied",
            },
            admitted_flow_ids={"mongo-progress"},
        )
        service = self._service(
            oa_records=[],
            in_progress_oa_records=[
                self._oa("oa-progress-admitted", "李四", "40.00", workflow_status="in_progress"),
                self._oa("oa-progress-denied", "李四", "40.00", workflow_status="in_progress"),
            ],
            payment_repository=payment_repository,
        )

        progress_payload = service.list_rows(page_size=20, view_mode="in_progress")

        self.assertEqual([row["oa"]["id"] for row in progress_payload["rows"]], ["oa-progress-admitted"])
        self.assertEqual(payment_repository.list_calls, 1)

    def test_in_progress_view_reads_bank_relation_from_pending_payment_source(self) -> None:
        bank = self._bank("bank-progress-paid", "163000.00", counterparty_name="威斯达昆明信息技术有限责任公司")
        pending_relation = {
            "case_id": "oa-pending-progress-paid",
            "relation_id": "oa-pending-progress-paid",
            "status": "active",
            "relation_mode": "oa_pending_payment_in_progress",
            "relation_source": "oa_pending_payment_bank_relations",
            "month_scope": "2026-02",
            "row_ids": ["oa-progress-paid", bank.id],
            "row_types": ["oa", "bank"],
            "oa_row_ids": ["oa-progress-paid"],
            "bank_transaction_ids": [bank.id],
            "amount_check": {"matched": True, "rule_code": "oa_bank_exact_amount"},
            "special_metadata": {
                "origin": "oa_pending_payment_in_progress",
                "source": "oa_pending_payment_bank_relations",
            },
        }
        payment_repository = FakePaymentStatusRepository(
            flow_ids={"oa-progress-paid": "flow-progress-paid"},
            paid_flow_ids={"flow-progress-paid"},
        )
        service = self._service(
            oa_records=[],
            in_progress_oa_records=[
                self._oa(
                    "oa-progress-paid",
                    "陈秀云",
                    "163000.00",
                    workflow_status="in_progress",
                    project_name="昭通卷烟厂2023-2025年度能源集中监控平台系统维护",
                    apply_type="支付申请",
                    counterparty_name="威斯达昆明信息技术有限责任公司",
                    reason="技术服务费",
                )
            ],
            transactions=[bank],
            pending_relation_service=FakePendingRelationService([pending_relation]),
            payment_repository=payment_repository,
        )

        progress_payload = service.list_rows(page_size=20, view_mode="in_progress")
        completed_payload = service.list_rows(page_size=20, view_mode="completed")

        self.assertEqual(completed_payload["rows"], [])
        self.assertEqual(progress_payload["pagination"]["total"], 1)
        row = progress_payload["rows"][0]
        self.assertEqual(row["oa"]["id"], "oa-progress-paid")
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["bankTransaction"]["primaryBankTransactionId"], "bank-progress-paid")
        self.assertEqual(row["bankTransaction"]["paidTotal"], "163000.00")
        self.assertEqual(row["bankTransaction"]["summaries"][0]["relationSource"], "oa_pending_payment_bank_relations")
        self.assertEqual(row["oaPaymentWriteback"]["code"], "written")
        self.assertEqual(set(payment_repository.resolved_records), {"oa-progress-paid"})

    def test_in_progress_view_keeps_payment_admitted_record_when_completed_projection_has_same_business_record(self) -> None:
        same_business_detail = {
            "申请日期": "2026-04-16",
            "开户行": "中国农业银行股份有限公司威信扎西支行",
            "收款账号": "24231201040003910",
        }
        payment_repository = FakeAdmissionPaymentStatusRepository(
            flow_ids={
                "oa-pay-old-mongo-id": "old-mongo-id",
                "oa-progress-real": "real-progress-id",
            },
            admitted_flow_ids={"old-mongo-id", "real-progress-id"},
        )
        service = self._service(
            oa_records=[
                self._oa(
                    "oa-pay-2094",
                    "樊祖芳",
                    "7000.00",
                    project_name="昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
                    apply_type="支付申请",
                    workflow_status="completed",
                    counterparty_name="云南心诚环保科技有限公司",
                    reason="申请支付昭通烟厂能源系统维护项目：环保数采仪1套，合同金额：7000元，全额付款7000元。",
                    detail_fields=same_business_detail,
                )
            ],
            in_progress_oa_records=[
                self._oa(
                    "oa-pay-old-mongo-id",
                    "樊祖芳",
                    "7000.00",
                    project_name="昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
                    apply_type="支付申请",
                    workflow_status="in_progress",
                    counterparty_name="云南心诚环保科技有限公司",
                    reason="申请支付昭通烟厂能源系统维护项目：环保数采仪1套，合同金额：7000元，全额付款7000元。",
                    detail_fields=same_business_detail,
                ),
                self._oa(
                    "oa-progress-real",
                    "樊祖芳",
                    "5000.00",
                    project_name="昭通卷烟厂2025-2028年度能源集中监控平台系统维护采购项目",
                    apply_type="支付申请",
                    workflow_status="in_progress",
                    counterparty_name="北京雪迪龙科技股份有限公司",
                    reason="申请支付昭通烟厂现场服务费：5000元",
                    detail_fields={
                        "申请日期": "2026-04-16",
                        "开户行": "中国建设银行北京沙河支行",
                        "收款账号": "11001016000059263662",
                    },
                ),
            ],
            payment_repository=payment_repository,
        )

        progress_payload = service.list_rows(page_size=20, view_mode="in_progress")
        completed_payload = service.list_rows(page_size=20)

        self.assertEqual([row["oa"]["id"] for row in progress_payload["rows"]], ["oa-pay-old-mongo-id", "oa-progress-real"])
        self.assertEqual(progress_payload["summary"]["viewCounts"], {"completed": 1, "in_progress": 2})
        self.assertEqual(completed_payload["summary"]["viewCounts"], {"completed": 1, "in_progress": 2})

    def test_page_size_limit_protects_first_screen_slo(self) -> None:
        service = self._service(
            oa_records=[
                self._oa(
                    f"oa-large-{index}",
                    "大数据申请人",
                    "1.00",
                    project_name=f"大数据项目 {index:04d}",
                )
                for index in range(250)
            ]
        )

        payload = service.list_rows(page=1, page_size=200)

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 200, "total": 250})
        self.assertEqual(len(payload["rows"]), 200)
        with self.assertRaises(OaPendingPaymentError) as context:
            service.list_rows(page=1, page_size=201)
        self.assertEqual(context.exception.error_code, "invalid_paging")

    def test_detail_routes_return_oa_bank_invoice_and_relation_payloads(self) -> None:
        bank = self._bank("bank-detail", "100.00")
        invoice = self._invoice("inv-detail", "SD-DETAIL", "详情供应商", "100.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-detail", ["oa-detail", bank.id, invoice.id], matched=True)
        service = self._service(
            oa_records=[self._oa("oa-detail", "陈秀云", "100.00")],
            transactions=[bank],
            invoices=[invoice],
            pair_service=pair_service,
        )
        row_id = service.list_rows()["rows"][0]["id"]

        self.assertEqual(service.oa_detail("oa-detail")["id"], "oa-detail")
        self.assertEqual(service.bank_transaction_detail("bank-detail")["id"], "bank-detail")
        invoice_detail = service.invoice_detail("inv-detail")
        self.assertEqual(invoice_detail["id"], "inv-detail")
        invoice_fields = invoice_detail["sections"][0]["fields"]
        self.assertIn({"label": "进项发票方名称", "value": "详情供应商"}, invoice_fields)
        self.assertNotIn("销方名称", [field["label"] for field in invoice_fields])
        try:
            oa_relations = service.row_relation_details(row_id, kind="oa")
        except OaPendingPaymentError as exc:
            self.fail(f"kind=oa relation details should be supported: {exc.error_code}")
        bank_relations = service.row_relation_details(row_id, kind="bank")
        invoice_relations = service.row_relation_details(row_id, kind="invoice")
        self.assertEqual(oa_relations["kind"], "oa")
        self.assertEqual(bank_relations["kind"], "bank")
        self.assertEqual(invoice_relations["kind"], "invoice")
        self.assertEqual(oa_relations["title"], "OA关联明细")
        self.assertEqual(bank_relations["title"], "支出流水关联明细")
        self.assertEqual(invoice_relations["title"], "发票关联明细")
        self.assertTrue(oa_relations["sections"])
        self.assertTrue(bank_relations["sections"])
        self.assertTrue(invoice_relations["sections"])

    def test_multiple_bank_transactions_use_total_paid_amount_for_status_and_summary(self) -> None:
        bank_a = self._bank("bank-split-a", "40.00")
        bank_b = self._bank("bank-split-b", "60.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-split", ["oa-split", bank_a.id, bank_b.id], matched=True)
        service = self._service(
            oa_records=[self._oa("oa-split", "刘一", "100.00")],
            transactions=[bank_a, bank_b],
            pair_service=pair_service,
        )

        payload = service.list_rows()
        row = payload["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["bankTransaction"]["paidTotal"], "100.00")
        self.assertEqual(payload["summary"]["bankPaidTotal"], "100.00")

    def test_linked_non_outflow_bank_relation_still_counts_as_paid_status(self) -> None:
        income_bank = self._bank("bank-income", "100.00", direction=TransactionDirection.INFLOW)
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-income", ["oa-income", income_bank.id], matched=True)
        service = self._service(
            oa_records=[self._oa("oa-income", "吴十", "100.00")],
            transactions=[income_bank],
            pair_service=pair_service,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertIn("流水方向待检查", row["paymentStatus"]["reason"])
        self.assertEqual(row["bankTransaction"]["relationCount"], 0)

    def test_missing_related_bank_fact_still_counts_as_paid_status(self) -> None:
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-missing-bank", ["oa-missing-bank", "bank-missing"], matched=False)
        service = self._service(
            oa_records=[self._oa("oa-missing-bank", "郑十一", "100.00")],
            transactions=[],
            pair_service=pair_service,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertIn("流水事实缺失", row["paymentStatus"]["reason"])

    def _service(
        self,
        *,
        oa_records: list[OAApplicationRecord],
        in_progress_oa_records: list[OAApplicationRecord] | None = None,
        transactions: list[BankTransaction] | None = None,
        invoices: list[Invoice] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
        pending_relation_service: FakePendingRelationService | None = None,
        payment_repository: FakePaymentStatusRepository | None = None,
    ) -> OaPendingPaymentQueryService:
        projection = StaticOAProjection(oa_records)
        return OaPendingPaymentQueryService(
            import_service=ImportNormalizationService(
                existing_transactions=transactions or [],
                existing_invoices=invoices or [],
            ),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service or WorkbenchPairRelationService(),
                transactions=list(transactions or []),
                invoices=list(invoices or []),
                oa_projection=projection,
            ),
            pending_relation_service=pending_relation_service,
            oa_projection=projection,
            in_progress_oa_projection=StaticOAProjection(in_progress_oa_records or oa_records),
            payment_status_repository=payment_repository,
        )

    @staticmethod
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        project_name: str = "测试项目",
        apply_type: str = "报销",
        workflow_status: str | None = "completed",
        counterparty_name: str = "测试供应商",
        reason: str = "测试付款",
        detail_fields: dict[str, object] | None = None,
    ) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="审批通过",
            case_id=None,
            applicant=applicant,
            project_name=project_name,
            apply_type=apply_type,
            amount=amount,
            counterparty_name=counterparty_name,
            reason=reason,
            relation_code="",
            relation_label="",
            relation_tone="",
            workflow_status=workflow_status,
            detail_fields=detail_fields or {},
            project_name_display=project_name,
        )

    @staticmethod
    def _bank(
        bank_id: str,
        amount: str,
        *,
        direction: TransactionDirection = TransactionDirection.OUTFLOW,
        counterparty_name: str = "测试供应商",
    ) -> BankTransaction:
        signed_amount = -Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount)
        return BankTransaction(
            id=bank_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw=counterparty_name,
            amount=Decimal(amount),
            signed_amount=signed_amount,
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            account_name="云南溯源科技有限公司",
            balance=Decimal("900.00"),
            currency="人民币元",
            counterparty_account_no="621700001",
            counterparty_bank_name="建行昆明支行",
            booked_date="20260521",
            summary="电子转账",
            remark="测试付款备注",
            account_detail_no=f"detail-{bank_id}",
            enterprise_serial_no=f"enterprise-{bank_id}",
            voucher_kind="电子转账凭证",
            voucher_no=f"voucher-{bank_id}",
            imported_bank_name="建设银行",
            imported_bank_last4="1234",
        )

    @staticmethod
    def _invoice(invoice_id: str, digital_no: str, seller_name: str, total: str) -> Invoice:
        counterparty = Counterparty(
            id=f"cp-{invoice_id}",
            name=seller_name,
            normalized_name=seller_name,
            counterparty_type="supplier",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=digital_no,
            digital_invoice_no=digital_no,
            counterparty=counterparty,
            amount=Decimal(total),
            signed_amount=Decimal(total),
            invoice_date="2026-05-20",
            seller_name=seller_name,
            buyer_name="云南溯源科技有限公司",
            total_with_tax=Decimal(total),
        )

    @staticmethod
    def _relation(
        service: WorkbenchPairRelationService,
        case_id: str,
        row_ids: list[str],
        *,
        matched: bool,
    ) -> None:
        service.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=[
                "oa" if row_id.startswith("oa-") else "bank" if row_id.startswith("bank-") else "invoice"
                for row_id in row_ids
            ],
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": matched},
        )


if __name__ == "__main__":
    unittest.main()
