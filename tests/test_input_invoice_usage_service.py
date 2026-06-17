from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeWorkbenchRelationFacade


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records
        self.records_by_id = {record.id: record for record in records}
        self.write_calls: list[object] = []

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def create_draft(self, *_: object, **__: object) -> None:
        self.write_calls.append("create_draft")


class RepositoryOnlyInvoiceFacts:
    def __init__(self, invoices: list[Invoice], transactions: list[BankTransaction] | None = None) -> None:
        self.invoices = invoices
        self.transactions = list(transactions or [])
        self.invoice_page_calls: list[dict[str, object]] = []
        self.transaction_page_calls: list[dict[str, object]] = []

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Invoice], int]:
        self.invoice_page_calls.append(
            {
                "page": page,
                "page_size": page_size,
                "month": month,
                "invoice_type": invoice_type,
                "status": status,
                "keyword": keyword,
            }
        )
        return list(self.invoices), len(self.invoices)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **_: object,
    ) -> tuple[list[BankTransaction], int]:
        self.transaction_page_calls.append({"page": page, "page_size": page_size})
        return list(self.transactions), len(self.transactions)


class InputInvoiceUsageQueryServiceTests(unittest.TestCase):
    def test_default_rows_read_repository_invoice_facts_when_memory_snapshot_is_empty(self) -> None:
        vendor = self._counterparty("vendor", "生产库供应商")
        invoice = self._invoice("inv-postgres", "PG-001", vendor, total_with_tax="118.00")
        repository = RepositoryOnlyInvoiceFacts([invoice])
        service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.list_rows()

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["invoiceId"], "inv-postgres")
        self.assertEqual(payload["rows"][0]["invoice"]["sellerName"], "生产库供应商")
        self.assertEqual(repository.invoice_page_calls[0]["month"], None)
        self.assertEqual(repository.invoice_page_calls[0]["invoice_type"], InvoiceType.INPUT.value)

    def test_list_rows_batches_repository_bank_reads_across_all_invoice_rows(self) -> None:
        vendor = self._counterparty("vendor", "生产库供应商")
        invoices = [
            self._invoice(f"inv-postgres-{index}", f"PG-{index:03d}", vendor, total_with_tax="118.00")
            for index in range(1, 6)
        ]
        bank = self._bank_transaction("bank-postgres-1", "118.00")
        repository = RepositoryOnlyInvoiceFacts(invoices, transactions=[bank])
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-postgres-1", [invoices[0].id, bank.id], amount_matched=True)
        service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service,
                transactions=[bank],
                invoices=invoices,
            ),
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 5)
        self.assertEqual(repository.invoice_page_calls[0]["invoice_type"], InvoiceType.INPUT.value)
        self.assertEqual(len(repository.invoice_page_calls), 1)
        self.assertEqual(len(repository.transaction_page_calls), 1)

    def test_filter_options_are_built_from_all_matching_rows_not_first_page_only(self) -> None:
        vendor = self._counterparty("vendor", "生产库供应商")
        invoices = [
            self._invoice(f"inv-postgres-{index}", f"PG-{index:03d}", vendor, total_with_tax="1.00")
            for index in range(1, 202)
        ]
        repository = RepositoryOnlyInvoiceFacts(invoices)
        service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.filter_options()

        seller_options = {
            option["value"]: option["count"]
            for field in payload["fields"]
            if field["field"] == "seller_name"
            for option in field["options"]
        }
        self.assertEqual(seller_options["生产库供应商"], 201)

    def test_import_invoices_are_aggregated_one_row_per_digital_invoice_and_detail_preserves_line_items(self) -> None:
        vendor = self._counterparty("vendor", "云南中招招标有限公司")
        line_1 = self._invoice(
            "invoice-line-1",
            "INV-001-A",
            vendor,
            digital_invoice_no="26372000000458116231",
            taxable_item_name="招标服务费",
            amount="66.04",
            tax_amount="3.96",
            total_with_tax="70.00",
        )
        line_2 = self._invoice(
            "invoice-line-2",
            "INV-001-B",
            vendor,
            digital_invoice_no="26372000000458116231",
            taxable_item_name="平台服务费",
            amount="33.02",
            tax_amount="1.98",
            total_with_tax="35.00",
        )
        service = self._service(invoices=[line_2, line_1])

        payload = service.list_rows()
        detail = service.invoice_detail("invoice-line-1")

        self.assertEqual(payload["pagination"]["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["invoiceId"], "invoice-line-1")
        self.assertEqual(row["invoiceIdentityKey"], "digital:26372000000458116231")
        self.assertEqual(row["invoice"]["lineItemCount"], 2)
        self.assertTrue(row["invoice"]["hasMoreInvoiceLines"])
        self.assertEqual(row["invoice"]["totalWithTax"], "105.00")
        self.assertEqual([item["id"] for item in detail["lineItems"]], ["invoice-line-1", "invoice-line-2"])
        self.assertEqual([item["taxableItemName"] for item in detail["lineItems"]], ["招标服务费", "平台服务费"])

    def test_invoice_identity_falls_back_to_code_number_then_stable_id(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        coded_1 = self._invoice("coded-line-1", "9001", vendor, invoice_code="033001")
        coded_2 = self._invoice("coded-line-2", "9001", vendor, invoice_code="033001")
        sparse = self._invoice("sparse-line", "", vendor)
        service = self._service(invoices=[sparse, coded_2, coded_1])

        payload = service.list_rows(sort_field="invoice_no", sort_direction="asc")

        self.assertEqual(payload["pagination"]["total"], 2)
        keys = [row["invoiceIdentityKey"] for row in payload["rows"]]
        self.assertEqual(keys, ["code_no:033001:9001", "id:sparse-line"])

    def test_pagination_filter_and_sort_are_server_side_contracts(self) -> None:
        vendor_a = self._counterparty("vendor-a", "甲供应商")
        vendor_b = self._counterparty("vendor-b", "乙供应商")
        service = self._service(
            invoices=[
                self._invoice("inv-1", "1001", vendor_a, total_with_tax="30.00", invoice_date="2026-05-01"),
                self._invoice("inv-2", "1002", vendor_b, total_with_tax="10.00", invoice_date="2026-05-02"),
                self._invoice("inv-3", "1003", vendor_a, total_with_tax="20.00", invoice_date="2026-05-03"),
            ]
        )

        payload = service.list_rows(
            page=1,
            page_size=1,
            filters='[{"field":"seller_name","operator":"in","values":["甲供应商"]}]',
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["invoiceId"], "inv-1")
        self.assertEqual(payload["summary"]["invoiceCount"], 2)
        self.assertEqual(payload["summary"]["totalWithTax"], "50.00")
        self.assertEqual(payload["sort"], {"field": "total_with_tax", "direction": "desc"})

    def test_page_size_limit_protects_first_screen_slo(self) -> None:
        vendor = self._counterparty("vendor-large", "大数据供应商")
        service = self._service(
            invoices=[
                self._invoice(
                    f"inv-large-{index}",
                    f"LG-{index:04d}",
                    vendor,
                    digital_invoice_no=f"2637200000045{index:07d}",
                    total_with_tax="1.00",
                )
                for index in range(250)
            ]
        )

        payload = service.list_rows(page=1, page_size=200)

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 200, "total": 250})
        self.assertEqual(len(payload["rows"]), 200)
        with self.assertRaises(InputInvoiceUsageError) as context:
            service.list_rows(page=1, page_size=201)
        self.assertEqual(context.exception.error_code, "invalid_paging")

    def test_canonical_filter_validation_rejects_unknown_fields_and_operators(self) -> None:
        service = self._service(invoices=[])

        with self.assertRaises(InputInvoiceUsageError) as field_context:
            service.list_rows(filters='[{"field":"unknown","operator":"equals","value":"x"}]')
        with self.assertRaises(InputInvoiceUsageError) as operator_context:
            service.list_rows(filters='[{"field":"seller_name","operator":"between","value":{"min":"a","max":"z"}}]')

        self.assertEqual(field_context.exception.error_code, "invalid_filter_field")
        self.assertEqual(operator_context.exception.error_code, "invalid_filter_operator")

    def test_payment_status_uses_priority_and_requires_provable_full_match(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        chen_invoice = self._invoice("inv-chen", "9001", vendor, total_with_tax="70.00")
        paid_invoice = self._invoice("inv-paid", "9002", vendor, total_with_tax="80.00")
        fallback_invoice = self._invoice("inv-fallback", "9003", vendor, total_with_tax="90.00")
        chen_bank = self._bank_transaction("bank-chen", "70.00")
        paid_bank = self._bank_transaction("bank-paid", "80.00")
        fallback_bank = self._bank_transaction("bank-fallback", "90.00")
        oa_records = [
            self._oa("oa-chen", "陈秀云", "70.00"),
            self._oa("oa-paid", "李四", "80.00"),
            self._oa("oa-fallback", "王五", "90.00"),
        ]
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-chen", [chen_invoice.id, "oa-chen", chen_bank.id], amount_matched=True)
        self._relation(pair_service, "case-paid", [paid_invoice.id, "oa-paid", paid_bank.id], amount_matched=True)
        self._relation(pair_service, "case-fallback", [fallback_invoice.id, "oa-fallback", fallback_bank.id], amount_matched=False)
        service = self._service(
            invoices=[fallback_invoice, paid_invoice, chen_invoice],
            transactions=[fallback_bank, paid_bank, chen_bank],
            pair_service=pair_service,
            oa_projection=StaticOAProjection(oa_records),
        )

        rows = {row["invoiceId"]: row for row in service.list_rows(page_size=20)["rows"]}

        self.assertEqual(rows["inv-chen"]["paymentStatus"]["code"], "cash_turnover")
        self.assertEqual(rows["inv-paid"]["paymentStatus"]["code"], "paid")
        self.assertEqual(rows["inv-fallback"]["paymentStatus"]["code"], "pending")
        self.assertIn("不能证明", rows["inv-fallback"]["paymentStatus"]["reason"])

    def test_no_bank_oa_rules_prioritize_offset_applicants_before_waiting_payment(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        zhou = self._invoice("inv-zhou", "9101", vendor, total_with_tax="50.00")
        liu = self._invoice("inv-liu", "9102", vendor, total_with_tax="60.00")
        wei = self._invoice("inv-wei", "9103", vendor, total_with_tax="70.00")
        wait = self._invoice("inv-wait", "9104", vendor, total_with_tax="80.00")
        oa_records = [
            self._oa("oa-zhou", "周洁莹", "50.00"),
            self._oa("oa-liu", "刘树刚不付", "10.00"),
            self._oa("oa-wei", "韦代连", "10.00"),
            self._oa("oa-wait", "赵六", "80.00"),
        ]
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-zhou", [zhou.id, "oa-zhou"], amount_matched=True)
        self._relation(pair_service, "case-liu", [liu.id, "oa-liu"], amount_matched=False)
        self._relation(pair_service, "case-wei", [wei.id, "oa-wei"], amount_matched=False)
        self._relation(pair_service, "case-wait", [wait.id, "oa-wait"], amount_matched=False)
        service = self._service(
            invoices=[wait, wei, liu, zhou],
            pair_service=pair_service,
            oa_projection=StaticOAProjection(oa_records),
        )

        rows = {row["invoiceId"]: row for row in service.list_rows(page_size=20)["rows"]}

        self.assertEqual(rows["inv-zhou"]["paymentStatus"]["code"], "offset_zhou_jieying")
        self.assertEqual(rows["inv-liu"]["paymentStatus"]["code"], "offset_liu_shugang_no_pay")
        self.assertEqual(rows["inv-wei"]["paymentStatus"]["code"], "offset_wei_dailian")
        self.assertEqual(rows["inv-wait"]["paymentStatus"]["code"], "waiting_payment")

    def test_one_to_many_oa_and_bank_relations_include_deterministic_primary_and_all_summaries(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        invoice = self._invoice("inv-many", "9201", vendor, total_with_tax="100.00")
        bank_old = self._bank_transaction("bank-old", "20.00", trade_time="2026-05-01 10:00:00")
        bank_exact = self._bank_transaction("bank-exact", "100.00", trade_time="2026-05-02 10:00:00")
        oa_records = [self._oa("oa-small", "张三", "20.00"), self._oa("oa-exact", "李四", "100.00")]
        pair_service = WorkbenchPairRelationService()
        self._relation(
            pair_service,
            "case-many",
            [invoice.id, "oa-small", bank_old.id, "oa-exact", bank_exact.id],
            amount_matched=True,
        )
        service = self._service(
            invoices=[invoice],
            transactions=[bank_old, bank_exact],
            pair_service=pair_service,
            oa_projection=StaticOAProjection(oa_records),
        )

        row = service.list_rows()["rows"][0]
        relation_detail = service.row_relation_details(row["id"], kind="bank")

        self.assertEqual(row["oa"]["primaryOaId"], "oa-exact")
        self.assertEqual(row["oa"]["relationCount"], 2)
        self.assertTrue(row["oa"]["hasMultiple"])
        self.assertEqual(row["oa"]["detailMode"], "list")
        self.assertEqual([summary["oaId"] for summary in row["oa"]["summaries"]], ["oa-exact", "oa-small"])
        self.assertEqual(row["bankTransactions"]["primaryBankTransactionId"], "bank-exact")
        self.assertEqual([summary["bankTransactionId"] for summary in relation_detail["summaries"]], ["bank-exact", "bank-old"])

    def test_candidate_relations_are_displayed_without_marking_invoice_paid(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        invoice = self._invoice("inv-candidate", "9202", vendor, total_with_tax="100.00")
        bank = self._bank_transaction("bank-candidate", "100.00")
        oa_projection = StaticOAProjection([self._oa("oa-candidate", "李四", "100.00")])
        relation_facade = FakeWorkbenchRelationFacade(
            [
                {
                    "row_id": invoice.id,
                    "row_type": "input_invoice",
                    "relation_status": "candidate",
                    "group_ids": ["decision-open-candidate"],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                }
            ],
            groups=[
                {
                    "group_id": "decision-open-candidate",
                    "scope_month": "2026-05",
                    "relation_source": "automatic_decision",
                    "relation_status": "candidate",
                    "oa_row_ids": ["oa-candidate"],
                    "bank_transaction_ids": [bank.id],
                    "input_invoice_ids": [invoice.id],
                    "output_invoice_ids": [],
                    "payload": {
                        "group_id": "decision-open-candidate",
                        "row_ids": ["oa-candidate", bank.id, invoice.id],
                        "row_types": ["oa", "bank", "invoice"],
                        "relation_mode": "automatic_decision",
                        "relation_status": "candidate",
                        "amount_check": {"matched": True},
                    },
                }
            ],
        )
        service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=[invoice],
                existing_transactions=[bank],
            ),
            relation_facade=relation_facade,
            oa_projection=oa_projection,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["oa"]["relationCount"], 1)
        self.assertEqual(row["bankTransactions"]["relationCount"], 1)
        self.assertEqual(row["oa"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["bankTransactions"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["paymentStatus"]["code"], "pending")

    def test_oa_attachment_source_relation_displays_for_promoted_formal_invoice(self) -> None:
        vendor = self._counterparty("vendor", "安徽德易智莱科技有限公司")
        invoice = self._invoice(
            "inv-formal-promoted",
            "01506808456",
            vendor,
            total_with_tax="423.80",
        )
        invoice.seller_tax_no = "913401003366798893"
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_workbench_row_id": "oa-att-inv-deyizhilai",
                "derived_from_oa_id": "oa-deyizhilai",
            }
        ]
        bank = self._bank_transaction("bank-deyizhilai", "423.80")
        oa_projection = StaticOAProjection([self._oa("oa-deyizhilai", "樊相芳", "423.80")])
        relation_facade = FakeWorkbenchRelationFacade(
            [
                {
                    "row_id": "oa-att-inv-deyizhilai",
                    "row_type": "input_invoice",
                    "relation_status": "candidate",
                    "group_ids": ["decision-oa-attachment-source"],
                    "linked_oa": [],
                    "linked_bank_transactions": [{"id": bank.id, "relation_status": "candidate"}],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                }
            ],
            groups=[
                {
                    "group_id": "decision-oa-attachment-source",
                    "scope_month": "2026-05",
                    "relation_source": "automatic_decision",
                    "relation_status": "candidate",
                    "oa_row_ids": ["oa-deyizhilai"],
                    "bank_transaction_ids": [bank.id],
                    "input_invoice_ids": ["oa-att-inv-deyizhilai"],
                    "output_invoice_ids": [],
                    "payload": {
                        "group_id": "decision-oa-attachment-source",
                        "row_ids": ["oa-deyizhilai", bank.id, "oa-att-inv-deyizhilai"],
                        "row_types": ["oa", "bank", "invoice"],
                        "relation_mode": "automatic_decision",
                        "relation_status": "candidate",
                        "amount_check": {"matched": True},
                    },
                }
            ],
        )
        service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=[invoice],
                existing_transactions=[bank],
            ),
            relation_facade=relation_facade,
            oa_projection=oa_projection,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["invoice"]["sellerName"], "安徽德易智莱科技有限公司")
        self.assertEqual(row["oa"]["relationCount"], 1)
        self.assertEqual(row["oa"]["primaryOaId"], "oa-deyizhilai")
        self.assertEqual(row["oa"]["applicantName"], "樊相芳")
        self.assertEqual(row["oa"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["bankTransactions"]["relationCount"], 1)
        self.assertEqual(row["bankTransactions"]["primaryBankTransactionId"], bank.id)
        self.assertEqual(row["bankTransactions"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["paymentStatus"]["code"], "pending")

    def test_details_and_filter_options_have_complete_contract_shape(self) -> None:
        vendor = self._counterparty("vendor", "云南中招招标有限公司")
        invoice = self._invoice("inv-detail", "9301", vendor, buyer_name="云南溯源科技有限公司", remark="发票备注")
        bank = self._bank_transaction("bank-detail", "100.00", summary="服务费", remark="银行备注")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-detail", [invoice.id, "oa-missing", bank.id], amount_matched=True)
        service = self._service(invoices=[invoice], transactions=[bank], pair_service=pair_service)

        options = service.filter_options(month="2026-05")
        invoice_detail = service.invoice_detail("inv-detail")
        bank_detail = service.bank_transaction_detail("bank-detail")
        oa_detail = service.oa_detail("oa-missing")

        self.assertIn("payment_status", [field["field"] for field in options["fields"]])
        self.assertEqual(invoice_detail["buyerName"], "云南溯源科技有限公司")
        self.assertEqual(invoice_detail["remark"], "发票备注")
        self.assertEqual(bank_detail["summary"], "服务费")
        self.assertEqual(bank_detail["remark"], "银行备注")
        self.assertFalse(oa_detail["detailAvailable"])

    def test_oa_and_bank_two_column_filters_are_and_filters_with_display_options(self) -> None:
        vendor = self._counterparty("vendor", "供应商")
        target = self._invoice("inv-target", "9401", vendor, total_with_tax="100.00")
        same_applicant_wrong_type = self._invoice("inv-wrong-type", "9402", vendor, total_with_tax="100.00")
        same_account_wrong_direction = self._invoice("inv-wrong-direction", "9403", vendor, total_with_tax="100.00")
        target_bank = self._bank_transaction(
            "bank-target",
            "100.00",
            bank_name="交通银行",
            account_last4="3847",
            direction=TransactionDirection.OUTFLOW,
        )
        wrong_direction_bank = self._bank_transaction(
            "bank-wrong-direction",
            "100.00",
            bank_name="交通银行",
            account_last4="3847",
            direction=TransactionDirection.INFLOW,
        )
        wrong_type_bank = self._bank_transaction(
            "bank-wrong-type",
            "100.00",
            bank_name="交通银行",
            account_last4="3847",
            direction=TransactionDirection.OUTFLOW,
        )
        oa_records = [
            self._oa("oa-target", "樊祖芳", "100.00", apply_type="支付申请"),
            self._oa("oa-wrong-type", "樊祖芳", "100.00", apply_type="报销"),
            self._oa("oa-wrong-direction", "樊祖芳", "100.00", apply_type="支付申请"),
        ]
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-target", [target.id, "oa-target", target_bank.id], amount_matched=True)
        self._relation(pair_service, "case-wrong-type", [same_applicant_wrong_type.id, "oa-wrong-type", wrong_type_bank.id], amount_matched=True)
        self._relation(pair_service, "case-wrong-direction", [same_account_wrong_direction.id, "oa-wrong-direction", wrong_direction_bank.id], amount_matched=True)
        service = self._service(
            invoices=[same_account_wrong_direction, same_applicant_wrong_type, target],
            transactions=[wrong_direction_bank, wrong_type_bank, target_bank],
            pair_service=pair_service,
            oa_projection=StaticOAProjection(oa_records),
        )

        payload = service.list_rows(
            page_size=20,
            filters=[
                {"field": "oa_applicant", "operator": "in", "values": ["樊祖芳"]},
                {"field": "oa_application_type", "operator": "in", "values": ["支付申请"]},
                {"field": "bank_account", "operator": "in", "values": ["交通银行 3847"]},
                {"field": "bank_direction", "operator": "in", "values": ["outflow"]},
            ],
        )
        options = service.filter_options()

        self.assertEqual([row["invoiceId"] for row in payload["rows"]], ["inv-target"])
        bank = payload["rows"][0]["bankTransactions"]
        self.assertEqual(bank["bankAccount"], "交通银行 3847")
        self.assertEqual(bank["direction"], "outflow")
        self.assertEqual(bank["directionLabel"], "支出")
        fields = {field["field"]: field for field in options["fields"]}
        self.assertIn({"value": "交通银行 3847", "label": "交通银行 3847", "count": 3}, fields["bank_account"]["options"])
        self.assertIn({"value": "outflow", "label": "支出", "count": 2}, fields["bank_direction"]["options"])
        self.assertIn({"value": "inflow", "label": "收入", "count": 1}, fields["bank_direction"]["options"])

    @staticmethod
    def _counterparty(counterparty_id: str, name: str) -> Counterparty:
        return Counterparty(id=counterparty_id, name=name, normalized_name=name, counterparty_type="supplier")

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        counterparty: Counterparty,
        *,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
        seller_name: str | None = None,
        buyer_name: str | None = None,
        amount: str = "94.34",
        tax_amount: str = "5.66",
        total_with_tax: str = "100.00",
        invoice_date: str = "2026-05-20",
        taxable_item_name: str = "服务费",
        remark: str | None = None,
    ) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=invoice_no,
            invoice_code=invoice_code,
            digital_invoice_no=digital_invoice_no,
            counterparty=counterparty,
            amount=Decimal(amount),
            signed_amount=Decimal(amount),
            invoice_date=invoice_date,
            seller_name=seller_name or counterparty.name,
            buyer_name=buyer_name,
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal(tax_amount),
            total_with_tax=Decimal(total_with_tax),
            specific_business_type="",
            taxable_item_name=taxable_item_name,
            invoice_source="import",
            invoice_kind="增值税专用发票",
            invoice_status_from_source="valid",
            is_positive_invoice="是",
            risk_level="低",
            issuer="开票人",
            remark=remark,
            source_batch_id="batch-001",
            source_links=[{"kind": "import_batch", "id": "batch-001"}],
        )

    @staticmethod
    def _bank_transaction(
        transaction_id: str,
        amount: str,
        *,
        trade_time: str = "2026-05-21 10:00:00",
        summary: str | None = None,
        remark: str | None = None,
        bank_name: str = "中国银行",
        account_last4: str = "1234",
        direction: TransactionDirection = TransactionDirection.OUTFLOW,
    ) -> BankTransaction:
        signed_amount = -Decimal(amount) if direction == TransactionDirection.OUTFLOW else Decimal(amount)
        return BankTransaction(
            id=transaction_id,
            account_no=f"62220000{account_last4}",
            txn_direction=direction,
            counterparty_name_raw="供应商",
            amount=Decimal(amount),
            signed_amount=signed_amount,
            txn_date=trade_time[:10],
            trade_time=trade_time,
            currency="CNY",
            counterparty_account_no="622233334444",
            counterparty_bank_name="开户行",
            booked_date=trade_time[:10],
            summary=summary,
            remark=remark,
            imported_bank_name=bank_name,
            imported_bank_last4=account_last4,
            bank_text_fields=[{"label": "摘要", "value": summary or ""}],
        )

    @staticmethod
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        apply_type: str = "报销",
        project_name: str | None = None,
    ) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="进行中",
            case_id=f"OA-{oa_id}",
            applicant=applicant,
            project_name=project_name or f"{applicant}项目",
            apply_type=apply_type,
            amount=amount,
            counterparty_name="供应商",
            reason="费用报销",
            relation_code="in_progress",
            relation_label="进行中",
            relation_tone="success",
        )

    @staticmethod
    def _relation(
        pair_service: WorkbenchPairRelationService,
        case_id: str,
        row_ids: list[str],
        *,
        amount_matched: bool,
    ) -> None:
        row_types = [
            "invoice" if row_id.startswith("inv") or row_id.startswith("invoice") else "bank" if row_id.startswith("bank") else "oa"
            for row_id in row_ids
        ]
        pair_service.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": amount_matched},
        )

    @staticmethod
    def _service(
        *,
        invoices: list[Invoice],
        transactions: list[BankTransaction] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
        oa_projection: object | None = None,
    ) -> InputInvoiceUsageQueryService:
        return InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=invoices,
                existing_transactions=transactions or [],
            ),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service or WorkbenchPairRelationService(),
                transactions=list(transactions or []),
                invoices=list(invoices),
                oa_projection=oa_projection,
            ),
            oa_projection=oa_projection,
        )
