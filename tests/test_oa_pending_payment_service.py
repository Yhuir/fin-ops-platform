from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
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


class OaPendingPaymentQueryServiceTests(unittest.TestCase):
    def test_statuses_use_oa_as_primary_row_and_decimal_payment_totals(self) -> None:
        bank_paid = self._bank("bank-paid", "100.00")
        bank_less = self._bank("bank-less", "80.00")
        bank_more = self._bank("bank-more", "140.00")
        bank_merged = self._bank("bank-merged", "150.00")
        invoice = self._invoice("inv-paid", "SD-001", "供应商A", "100.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-paid", ["oa-paid", bank_paid.id, invoice.id], matched=True)
        self._relation(pair_service, "case-less", ["oa-less", bank_less.id], matched=False)
        self._relation(pair_service, "case-more", ["oa-more", bank_more.id], matched=False)
        self._relation(pair_service, "case-merged-a", ["oa-merged-a", bank_merged.id], matched=True)
        self._relation(pair_service, "case-merged-b", ["oa-merged-b", bank_merged.id], matched=True)
        service = self._service(
            oa_records=[
                self._oa("oa-unpaid", "张三", "30.00"),
                self._oa("oa-paid", "李四", "100.00"),
                self._oa("oa-less", "王五", "100.00"),
                self._oa("oa-more", "赵六", "100.00"),
                self._oa("oa-merged-a", "钱七", "60.00"),
                self._oa("oa-merged-b", "孙八", "90.00"),
                self._oa("oa-bad", "周九", ""),
            ],
            transactions=[bank_paid, bank_less, bank_more, bank_merged],
            invoices=[invoice],
            pair_service=pair_service,
        )

        rows = {row["oa"]["id"]: row for row in service.list_rows(page_size=20)["rows"]}

        self.assertEqual(rows["oa-unpaid"]["paymentStatus"]["code"], "unpaid")
        self.assertEqual(rows["oa-paid"]["paymentStatus"]["code"], "paid")
        self.assertEqual(rows["oa-less"]["paymentStatus"]["code"], "partially_paid")
        self.assertEqual(rows["oa-more"]["paymentStatus"]["code"], "overpaid")
        self.assertEqual(rows["oa-merged-a"]["paymentStatus"]["code"], "merged_paid")
        self.assertEqual(rows["oa-merged-b"]["paymentStatus"]["code"], "merged_paid")
        self.assertEqual(rows["oa-bad"]["paymentStatus"]["code"], "pending_review")
        self.assertEqual(rows["oa-paid"]["bankTransaction"]["primaryBankTransactionId"], "bank-paid")
        self.assertEqual(rows["oa-paid"]["bankTransaction"]["accountNo"], "622200001234")
        self.assertEqual(rows["oa-paid"]["bankTransaction"]["accountLast4"], "1234")
        self.assertEqual(rows["oa-paid"]["bankTransaction"]["directionLabel"], "支出")
        self.assertEqual(rows["oa-paid"]["invoice"]["primaryInvoiceId"], "inv-paid")
        self.assertEqual(rows["oa-paid"]["invoice"]["digitalInvoiceNo"], "SD-001")

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
        bank_relations = service.row_relation_details(row_id, kind="bank")
        invoice_relations = service.row_relation_details(row_id, kind="invoice")
        self.assertEqual(bank_relations["kind"], "bank")
        self.assertEqual(invoice_relations["kind"], "invoice")
        self.assertEqual(bank_relations["title"], "支出流水关联明细")
        self.assertEqual(invoice_relations["title"], "发票关联明细")
        self.assertTrue(bank_relations["sections"])
        self.assertTrue(invoice_relations["sections"])

    def test_multiple_bank_transactions_use_total_paid_amount_for_status_and_summary(self) -> None:
        bank_a = self._bank("bank-split-a", "40.00")
        bank_b = self._bank("bank-split-b", "60.00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-split-a", ["oa-split", bank_a.id], matched=False)
        self._relation(pair_service, "case-split-b", ["oa-split", bank_b.id], matched=False)
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

    def test_only_outflow_bank_relations_count_as_payment_evidence(self) -> None:
        income_bank = self._bank("bank-income", "100.00", direction=TransactionDirection.INFLOW)
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-income", ["oa-income", income_bank.id], matched=True)
        service = self._service(
            oa_records=[self._oa("oa-income", "吴十", "100.00")],
            transactions=[income_bank],
            pair_service=pair_service,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "pending_review")
        self.assertIn("证据不完整", row["paymentStatus"]["reason"])
        self.assertEqual(row["bankTransaction"]["relationCount"], 0)

    def test_missing_related_bank_fact_is_pending_review_not_unpaid(self) -> None:
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-missing-bank", ["oa-missing-bank", "bank-missing"], matched=False)
        service = self._service(
            oa_records=[self._oa("oa-missing-bank", "郑十一", "100.00")],
            transactions=[],
            pair_service=pair_service,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "pending_review")
        self.assertIn("关联流水事实缺失", row["paymentStatus"]["reason"])

    def _service(
        self,
        *,
        oa_records: list[OAApplicationRecord],
        transactions: list[BankTransaction] | None = None,
        invoices: list[Invoice] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
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
            oa_projection=projection,
        )

    @staticmethod
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        project_name: str = "测试项目",
        apply_type: str = "报销",
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
            counterparty_name="测试供应商",
            reason="测试付款",
            relation_code="",
            relation_label="",
            relation_tone="",
            detail_fields=detail_fields or {},
            project_name_display=project_name,
        )

    @staticmethod
    def _bank(bank_id: str, amount: str, *, direction: TransactionDirection = TransactionDirection.OUTFLOW) -> BankTransaction:
        signed_amount = -Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount)
        return BankTransaction(
            id=bank_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw="测试供应商",
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
