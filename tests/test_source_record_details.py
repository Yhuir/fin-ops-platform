from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from decimal import Decimal
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock, patch

from fin_ops_platform.app.routes_bank_transaction_splits import BankTransactionSplitApiRoutes
from fin_ops_platform.app.routes_pending_invoices import PendingInvoiceApiRoutes
from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.oa_pending_payment_details import oa_pending_payment_source_detail
from fin_ops_platform.services.pending_invoice_canonical_query import PendingInvoiceCanonicalQueryService
from fin_ops_platform.services.source_record_details import (
    bank_source_detail,
    invoice_source_detail,
    query_source_detail,
    source_detail_sections,
    workbench_source_row,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade

from tests.app_test_support import build_local_state_application, configure_access_control


def _invoice(**overrides: object) -> Invoice:
    values = {
        "id": "invoice-1",
        "invoice_type": InvoiceType.INPUT,
        "invoice_no": "12345678",
        "counterparty": Counterparty("party-1", "关联对手方", "关联对手方", "supplier", tax_no="guessed-tax"),
        "amount": Decimal("100.00"),
        "signed_amount": Decimal("100.00"),
    }
    return Invoice(**{**values, **overrides})


def _invoice_group(*lines: Invoice) -> dict[str, object]:
    return {"primary": lines[0], "line_items": list(lines), "identity_key": "source-invoice-1"}


def _fields(payload: dict[str, object], section: int | None = None) -> dict[str, str]:
    sections = [payload["sections"][section]] if section is not None else [entry for entry in payload["sections"] if not entry["title"].startswith("费用明细")]
    return {item["label"]: item["value"] for entry in sections for item in entry["fields"]}


class SourceRecordProjectionTests(unittest.TestCase):
    def test_invoice_navigation_preserves_direction_identity_and_source_values(self) -> None:
        for invoice_type, expected in ((InvoiceType.INPUT, "销方原名"), (InvoiceType.OUTPUT, "购方原名")):
            for total in (Decimal("0"), Decimal("-2100.005"), None):
                invoice = _invoice(invoice_type=invoice_type, seller_name="销方原名", buyer_name="购方原名",
                                   total_with_tax=total, invoice_date="2026-10-02", is_positive_invoice="否")
                projection = invoice_source_detail(_invoice_group(invoice))
                summary = projection["sections"][0]["invoice_navigation"]
                self.assertEqual(summary, {"polarity": "红字", "counterpartyName": expected,
                    "totalWithTax": "0.00" if total == 0 else "-2100.005" if total is not None else None,
                    "invoiceDate": "2026-10-02"})
                row = {"id": invoice.id, "invoice_type": invoice_type.value, "seller_name": invoice.seller_name,
                       "buyer_name": invoice.buyer_name, "total_with_tax": total, "invoice_no": invoice.invoice_no,
                       "issue_date": invoice.invoice_date, "is_positive_invoice": "否"}
                original = deepcopy(row)
                self.assertEqual(query_source_detail("invoice", row)["sections"][0]["invoice_navigation"], summary)
                self.assertEqual(row, original)
        multi = invoice_source_detail(_invoice_group(_invoice(), _invoice(id="line-2")))
        self.assertIsNone(multi["sections"][0]["invoice_navigation"]["totalWithTax"])
        self.assertEqual(len({section["document_id"] for section in multi["sections"]}), 1)

    def test_bank_navigation_preserves_raw_amount_direction_and_current_labels(self):
        for direction, label, amount in [("outflow", "支出", "1050.00"), ("inflow", "收入", "35.00")]:
            row = {"id": "bank-1", "counterparty_name": "原始对方", "transaction_date": "2026-06-10",
                   "amount": amount, "txn_direction": direction, "bank_labels": ["货款 / 设备", "子项 2：退款"]}
            original = deepcopy(row)
            detail = query_source_detail("bank", row)
            navigation = detail["sections"][0]["bank_navigation"]
            self.assertEqual(navigation, {"counterpartyName": "原始对方", "transactionDate": "2026-06-10",
                "amount": amount, "direction": label, "labels": row["bank_labels"]})
            self.assertEqual(detail["sections"][-1]["bank_labels"], navigation["labels"])
            self.assertEqual(row, original)
        empty = query_source_detail("bank", {**row, "bank_labels": []})
        self.assertEqual(empty["sections"][-1]["bank_labels"], [])

    def test_navigation_titles_use_original_names_and_amounts_only(self) -> None:
        cases = [
            ("oa", {"oaId": "oa-1", "applicantName": "张三", "amount": Decimal("8000.00"), "workflowNo": "2440"}, "张三 · 8000.00"),
            ("oa", {"oaId": "oa-2", "applicantName": "李四", "amount": None, "workflowNo": "private-id", "expenseItems": [{"amount": "30"}]}, "李四"),
            ("bank", {"id": "bank-1", "counterpartyName": "公司", "amount": Decimal("0.00")}, "公司 · 0.00"),
            ("invoice", {"id": "red", "buyerName": "购方", "totalWithTax": "-2100.00", "isPositiveInvoice": False, "invoiceNo": "123"}, "红字 · 购方 · -2100.00"),
            ("invoice", {"id": "blue", "buyerName": "购方", "amount": "100", "totalWithTax": None, "isPositiveInvoice": "是"}, "蓝字 · 购方"),
            ("bank", {"id": "bank-2", "amount": Decimal("10.123400")}, "10.123400"),
        ]
        for kind, payload, expected in cases:
            with self.subTest(kind=kind, payload=payload):
                sections = source_detail_sections(kind, payload)
                self.assertTrue(sections)
                self.assertTrue(all(section["document_title"] == expected for section in sections))
                self.assertTrue(all(section["document_id"] == payload.get("oaId", payload.get("id")) for section in sections))

    def test_invoice_missing_source_values_do_not_use_operational_defaults(self) -> None:
        invoice = _invoice()
        result = invoice_source_detail(_invoice_group(invoice))

        self.assertIsNone(result["invoiceStatus"])
        self.assertIsNone(result["sellerName"])
        self.assertIsNone(result["sellerTaxNo"])
        self.assertNotIn("currency", result)
        self.assertNotIn("status", result)
        self.assertEqual(result["taxAmount"], "")
        self.assertEqual(result["totalWithTax"], "")
        self.assertEqual(result["lineItems"], [])
        self.assertEqual(result["amount"], "100.00")

    def test_invoice_source_status_zero_and_false_are_preserved(self) -> None:
        invoice = _invoice(
            amount=Decimal("0"), tax_amount=Decimal("0"), total_with_tax=Decimal("0"),
            invoice_status_from_source="已作废", seller_name="文件销方", is_positive_invoice=False,
            quantity=Decimal("0"), unit_price=Decimal("0"),
            source_line_items=[{"amount": "0", "tax_amount": "0", "total_with_tax": "0",
                                "quantity": 0, "unit_price": 0}],
        )
        result = invoice_source_detail(_invoice_group(invoice))

        self.assertEqual(result["invoiceStatus"], "已作废")
        self.assertEqual(result["sellerName"], "文件销方")
        self.assertIs(result["isPositiveInvoice"], False)
        for key in ("amount", "taxAmount", "totalWithTax"):
            self.assertEqual(result[key], "0.00")
        self.assertEqual(result["lineItems"][0]["quantity"], Decimal("0"))
        self.assertEqual(result["lineItems"][0]["unitPrice"], Decimal("0"))

    def test_invoice_group_keeps_source_lines_without_inventing_printed_totals(self) -> None:
        first = _invoice(tax_amount=Decimal("6"), total_with_tax=Decimal("106"),
                         source_line_items=[{"amount": "100", "tax_amount": "6", "total_with_tax": "106"}])
        second = _invoice(id="invoice-2", amount=Decimal("50"), tax_amount=Decimal("3"), total_with_tax=Decimal("53"),
                          source_line_items=[{"amount": "50", "tax_amount": "3", "total_with_tax": "53"}])
        result = invoice_source_detail(_invoice_group(first, second))

        for key in ("amount", "taxAmount", "totalWithTax"):
            self.assertEqual(result[key], "")
        self.assertEqual([line["amount"] for line in result["lineItems"]], ["100.00", "50.00"])
        self.assertEqual([line["totalWithTax"] for line in result["lineItems"]], ["106.00", "53.00"])

    def test_invoice_preserves_source_fractional_precision_in_amount_quantity_and_unit_price(self) -> None:
        invoice = _invoice(amount=Decimal("0.005"), tax_amount=Decimal("0.001"), total_with_tax=Decimal("0.006"),
                           quantity=Decimal("0.12345"), unit_price=Decimal("0.040502227"),
                           source_line_items=[{"amount": "0.005", "tax_amount": "0.001", "total_with_tax": "0.006",
                                               "quantity": Decimal("0.12345"), "unit_price": Decimal("0.040502227")}])
        result = invoice_source_detail(_invoice_group(invoice))
        self.assertEqual(result["amount"], "0.005")
        self.assertEqual(result["taxAmount"], "0.001")
        self.assertEqual(result["totalWithTax"], "0.006")
        self.assertEqual(result["lineItems"][0]["amount"], "0.005")
        self.assertEqual(result["lineItems"][0]["quantity"], Decimal("0.12345"))
        self.assertEqual(result["lineItems"][0]["unitPrice"], Decimal("0.040502227"))

    def test_formal_and_query_details_preserve_actual_lines_and_text_tax_without_gross(self) -> None:
        lines = [
            {"source_sheet_role": "invoice_header", "amount": "100", "tax_rate": "6%"},
            {"source_sheet_role": "line", "taxable_item_name": "商品", "amount": "110", "tax_amount": "14.3", "tax_rate": "13%"},
            {"source_sheet_role": "line", "taxable_item_name": "折扣", "amount": "-10", "tax_amount": "-1.3", "tax_rate": "13%"},
            {"source_sheet_role": "line", "taxable_item_name": "免税商品", "amount": "20", "tax_amount": None, "tax_amount_text": "*", "tax_rate": "免税"},
        ]
        original = deepcopy(lines)
        invoice = _invoice(amount=Decimal("120"), tax_amount=None, tax_amount_text="*",
                           source_line_items=lines, total_with_tax=Decimal("133"))
        formal = invoice_source_detail(_invoice_group(invoice))
        query = query_source_detail("invoice", {"id": invoice.id, "amount_without_tax": "120",
            "tax_amount": None, "tax_amount_text": "*", "total_with_tax": "133", "source_line_items": lines})
        self.assertEqual(formal["lineItems"], query["lineItems"])
        self.assertEqual(lines, original)
        self.assertEqual(formal["taxRate"], "多税率")
        self.assertEqual(formal["taxAmount"], "")
        self.assertEqual(formal["taxAmountText"], "*")
        self.assertEqual([line["amount"] for line in formal["lineItems"]], ["110.00", "-10.00", "20.00"])
        self.assertEqual([line["totalWithTax"] for line in formal["lineItems"]], ["", "", ""])
        self.assertEqual([line["taxRate"] for line in formal["lineItems"]], ["13%", "13%", "免税"])
        self.assertEqual(_fields(formal)["税额"], "*")
        last_line = next(section for section in formal["sections"] if section["title"] == "货物或应税劳务明细 3")
        self.assertEqual({item["label"]: item["value"] for item in last_line["fields"]}["税额"], "*")

    def test_generated_invoice_identifier_is_not_a_source_invoice_number(self) -> None:
        result = invoice_source_detail(_invoice_group(_invoice(invoice_no="invoice-1")))
        self.assertIsNone(result["invoiceNo"])
        self.assertEqual(result["id"], "invoice-1")

    def test_unstructured_source_line_is_visible_without_guessed_item_columns(self) -> None:
        text = "*汽油*95号车用汽油 95#汽油 25.75 6.87339806 176.99 13% 23.01"
        source = {"source_line_text": text, "amount": "176.99", "tax_amount": "23.01", "tax_rate": "13%"}
        result = invoice_source_detail(_invoice_group(_invoice(source_line_items=[source])))
        [line] = result["lineItems"]
        self.assertEqual(line["sourceLineText"], text)
        fields = _fields(result, section=-1)
        self.assertEqual(fields["原文"], text)
        for label in ("货物或应税劳务名称", "规格型号", "单位", "数量", "单价"):
            self.assertNotIn(label, fields)
        without = invoice_source_detail(_invoice_group(_invoice(source_line_items=[{"amount": "100"}])))
        self.assertNotIn("原文", _fields(without, section=-1))

    def test_bank_preserves_dates_without_synthesized_timestamp_or_booked_date(self) -> None:
        transaction = BankTransaction(
            id="bank-1", account_no="001234", txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="文件对方户名", amount=Decimal("100"), signed_amount=Decimal("-100"),
            txn_date="2026-09-27", trade_time="2026-09-27T00:00:00", currency="CNY", balance=Decimal("0"),
            account_name="文件账户名", bank_serial_no="0001", enterprise_serial_no="0002",
            voucher_kind="付款凭证", voucher_no="0003", account_detail_no="0004",
        )
        result = bank_source_detail(transaction)

        self.assertEqual(result["transactionDate"], "2026-09-27")
        self.assertIsNone(result["bookedDate"])
        self.assertEqual(result["balance"], "0.00")
        self.assertEqual(result["accountNo"], "001234")
        self.assertEqual(result["counterpartyName"], "文件对方户名")
        self.assertEqual(result["accountName"], "文件账户名")
        self.assertEqual(result["bankSerialNo"], "0001")
        self.assertEqual(result["enterpriseSerialNo"], "0002")
        self.assertEqual(result["voucherKind"], "付款凭证")
        self.assertEqual(result["voucherNo"], "0003")
        self.assertEqual(result["accountDetailNo"], "0004")
        for field in ("status", "currency", "tradeTime", "writtenOffAmount"):
            self.assertNotIn(field, result)

        transaction.booked_date = "2026-09-28"
        self.assertEqual(bank_source_detail(transaction)["bookedDate"], "2026-09-28")

    def test_bank_detail_projection_does_not_mutate_search_or_business_row(self) -> None:
        row = {
            "id": "bank-1", "type": "bank", "amount": "100.00", "status": "unpaired",
            "detail_fields": {
                "status": "pending", "currency": "CNY", "written_off_amount": "0",
                "trade_time": "2026-09-27T00:00:00", "txn_date": "2026-09-27",
                "counterparty_name_raw": "文件对方户名", "amount": "100.00", "balance": 0,
                "remark": "normal",
            },
        }
        original = deepcopy(row)
        result = workbench_source_row(row)

        self.assertEqual(row, original)
        self.assertEqual(result["status"], "unpaired")
        self.assertEqual(result["detail_fields"], {
            "txn_date": "2026-09-27", "counterparty_name": "文件对方户名",
            "amount": "100.00", "balance": 0, "remark": "normal",
        })

    def test_workbench_invoice_retains_real_status_and_false_without_internal_status(self) -> None:
        result = workbench_source_row({
            "id": "invoice-1", "type": "invoice",
            "detail_fields": {"status": "pending", "invoice_status_from_source": "正常",
                              "is_positive_invoice": False, "tax_amount": 0, "currency": "CNY"},
        })
        self.assertEqual(result["detail_fields"], {
            "invoice_status_from_source": "正常", "is_positive_invoice": False, "tax_amount": 0,
        })

    def test_oa_removes_inferred_category_modified_time_and_aggregate_but_keeps_source_fields(self) -> None:
        row = {
            "id": "oa-exp-1", "type": "oa", "applicant": "真实申请人", "amount": "120",
            "project_name": "拼接项目", "reason": "拼接费用", "workflow_status": "completed", "apply_type": "日常报销",
            "detail_fields": {
                "OA单号": "OA-001", "申请日期": "2026-09-27", "流程状态": "进行中",
                "费用类型": "财务费用", "审批完成时间": "2026-09-28T00:00:00",
                "金额来源": "明细合计", "币种": "CNY",
            },
            "expense_items": [{"project_name": "原始项目", "amount": 0, "fee_content": "文件费用说明",
                               "expense_content": "推断费用", "expense_type": "财务费用", "ticket_count": 0}],
        }
        original = deepcopy(row)
        result = workbench_source_row(row)

        self.assertEqual(row, original)
        self.assertEqual(result["detail_fields"], {
            "OA单号": "OA-001", "申请日期": "2026-09-27", "流程状态": "进行中", "申请人": "真实申请人", "OA类型": "日常报销",
        })
        self.assertEqual(result["expense_items"], [{
            "project_name": "原始项目", "amount": 0, "expense_content": "文件费用说明", "ticket_count": 0,
        }])
        self.assertEqual(result["amount"], "120")

    def test_oa_actual_header_zero_amount_remains_visible(self) -> None:
        result = workbench_source_row({
            "id": "oa-exp-1", "type": "oa", "amount": 0, "applicant": "申请人",
            "detail_fields": {"金额来源": "主表总金额"},
        })
        self.assertEqual(result["detail_fields"]["金额"], 0)

    def test_payment_oa_with_canonical_unprefixed_id_uses_real_application_type(self) -> None:
        result = workbench_source_row({
            "id": "canonical-847", "type": "oa", "apply_type": "支付申请", "amount": "125.50",
            "reason": "真实申请事由", "project_name": "真实项目", "applicant": "申请人",
            "detail_fields": {"流程状态": "进行中"},
        })
        self.assertEqual(result["detail_fields"]["金额"], "125.50")
        self.assertEqual(result["detail_fields"]["申请事由"], "真实申请事由")
        self.assertEqual(result["detail_fields"]["项目名称"], "真实项目")
        self.assertEqual(result["detail_fields"]["OA类型"], "支付申请")

    def test_workbench_facade_projects_only_detail_and_uses_one_exact_row_lookup(self) -> None:
        row = {"id": "bank-1", "type": "bank", "detail_fields": {"status": "pending", "amount": "100.00"}}
        payload = {"row": row, "scope_key": "all"}
        original = deepcopy(payload)
        repository = Mock()
        repository.get_workbench_row_detail.return_value = payload
        facade = WorkbenchQueryFacade(repository=repository)

        result = facade.row_detail("all", row_id="bank-1", row_type="bank")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["row"]["detail_fields"], {"amount": "100.00"})
        self.assertEqual(payload, original)
        repository.get_workbench_row_detail.assert_called_once_with(scope_key="all", row_id="bank-1", row_type="bank")


class SourceDetailApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = Mock()
        self.service = PendingInvoiceCanonicalQueryService(repository=self.repository)

    def test_canonical_invoice_detail_missing_tax_and_gross_stay_missing(self) -> None:
        self.repository.invoice_detail.return_value = {
            "id": "invoice-1", "invoice_no": "12345678", "amount_without_tax": "100.00", "status": "pending",
        }
        fields = _fields(self.service.invoice_detail("invoice-1"))
        self.assertEqual(fields["不含税金额"], "100.00")
        for label in ("税额", "价税合计", "税率"):
            self.assertEqual(fields[label], "—")
        self.assertNotIn("发票状态", fields)

    def test_canonical_bank_without_amount_or_direction_does_not_invent_zero_expense(self) -> None:
        self.repository.bank_transaction_detail.return_value = {"id": "bank-1", "account_no": "001234"}
        result = self.service.bank_transaction_detail("bank-1")
        self.assertEqual(result["sections"][0]["title"], "账户信息")
        self.assertEqual(_fields(result), {"账号": "001234"})

    def test_canonical_bank_known_amount_without_direction_stays_unclassified(self) -> None:
        self.repository.bank_transaction_detail.return_value = {"id": "bank-1", "amount": 0}
        result = self.service.bank_transaction_detail("bank-1")
        self.assertEqual(_fields(result), {"金额": "0.00"})

    def test_canonical_bank_explicit_direction_retains_zero_without_changing_income_to_expense(self) -> None:
        for direction, label in (("inflow", "收入"), ("outflow", "支出")):
            with self.subTest(direction=direction):
                self.repository.bank_transaction_detail.return_value = {
                    "id": "bank-1", "txn_direction": direction, "amount": 0,
                }
                result = self.service.bank_transaction_detail("bank-1")
                self.assertEqual(result["sections"][0]["title"], "交易信息")
                self.assertEqual(_fields(result), {f"{label}金额": "0.00"})

    def test_oa_pending_source_detail_uses_exact_source_id_not_matching_amount_or_relation_id(self) -> None:
        first = _invoice(seller_name="第一张发票的销方")
        second = _invoice(id="invoice-2", seller_name="目标发票的销方")
        facts = {"invoices": [first, second], "rows": [{"id": "relation-1", "amount": "100"}]}

        result = oa_pending_payment_source_detail(facts, "invoice", "invoice-2")

        self.assertEqual(result["id"], "invoice-2")
        self.assertIs(result["detailAvailable"], True)
        self.assertEqual(_fields(result)["销方名称"], "目标发票的销方")
        with self.assertRaisesRegex(ValueError, "Source detail identity is absent"):
            oa_pending_payment_source_detail(facts, "invoice", "relation-1")

    def test_canonical_invoice_zero_false_and_actual_status_survive(self) -> None:
        self.repository.invoice_detail.return_value = {
            "id": "invoice-1", "invoice_no": "12345678", "tax_amount": 0,
            "total_with_tax": 0, "amount_without_tax": 0, "quantity": 0,
            "is_positive_invoice": False, "invoice_status_from_source": "已作废",
            "source_line_items": [{"quantity": 0, "amount": 0, "tax_amount": 0, "total_with_tax": 0}],
        }
        fields = _fields(self.service.invoice_detail("invoice-1"))
        self.assertEqual(fields["税额"], "0.00")
        self.assertEqual(fields["价税合计"], "0.00")
        self.assertEqual(fields["数量"], 0)
        self.assertEqual(fields["是否正数发票"], False)
        self.assertEqual(fields["发票状态"], "已作废")

    def test_canonical_oa_keeps_original_fields_and_omits_inferred_summary(self) -> None:
        self.repository.oa_detail.return_value = {
            "oa_id": "oa-exp-2047", "workflow_no": "2047", "application_type": "expense_claim",
            "applicant": "真实申请人", "status": "completed", "amount": "999.00", "month": "2026-09",
            "project_name": "多个项目拼接", "reason": "费用明细拼接",
            "detail_fields": {"OA单号": "2047", "流程状态": "进行中", "申请日期": "2026-09-27",
                              "费用类型": "财务费用", "审批完成时间": "2026-09-28", "金额来源": "明细合计"},
            "expense_items": [{"amount": 0, "fee_content": "原始费用内容", "expense_type": "财务费用"}],
        }
        result = self.service.oa_detail("oa-exp-2047")
        fields = _fields(result)
        self.assertEqual(fields["OA单号"], "2047")
        self.assertEqual(fields["流程状态"], "进行中")
        self.assertEqual(fields["申请日期"], "2026-09-27")
        for label in ("费用类型", "审批完成时间", "金额", "申请事由", "项目名称", "月份"):
            self.assertNotIn(label, fields)
        expense_fields = {item["label"]: item["value"] for entry in result["sections"] if entry["title"] == "费用明细 1" for item in entry["fields"]}
        self.assertEqual(expense_fields["报销金额"], 0)
        self.assertEqual(expense_fields["费用内容"], "原始费用内容")
        self.assertNotIn("费用类型", expense_fields)

    def test_missing_oa_projection_is_explicitly_unavailable_without_guessed_sections(self) -> None:
        self.repository.oa_detail.return_value = None
        result = self.service.oa_detail("oa-exp-2047")
        self.assertIs(result["detail_available"], False)
        self.assertTrue(result["unavailable_reason"])
        self.assertNotIn("sections", result)

    def test_canonical_payment_oa_missing_header_amount_does_not_become_zero(self) -> None:
        self.repository.oa_detail.return_value = {
            "oa_id": "oa-pay-2047", "application_type": "payment_request", "amount": None,
            "detail_fields": {"OA单号": "2047"},
        }
        self.assertNotIn("金额", _fields(self.service.oa_detail("oa-pay-2047")))

    def test_application_dispatch_reaches_shared_bank_source_detail_and_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            try:
                configure_access_control(app, page_access={"test_finops_user": ["bank-details"]})
                app._pending_invoice_page_query_service = self.service  # noqa: SLF001
                split_routes = BankTransactionSplitApiRoutes(
                    service=Mock(), resolve_session=Mock(), load_json_body=Mock(), json_response=Mock(),
                )
                self.repository.bank_transaction_detail.return_value = {
                    "id": "bank-1", "amount": "100", "txn_direction": "outflow", "transaction_date": "2026-09-27",
                }
                with patch.object(app, "_bank_transaction_split_routes", return_value=split_routes):
                    response = app.handle_request("GET", "/api/bank-transactions/bank-1/source-detail")
                self.assertEqual(response.status_code, 200)
                payload = json.loads(response.body)
                self.assertIs(payload["detail_available"], True)
                self.assertEqual(payload["sections"][0]["bank_transaction_id"], "bank-1")
                self.assertEqual(_fields(payload)["支出金额"], "100.00")
                self.repository.bank_transaction_detail.assert_called_once_with("bank-1")

                self.repository.bank_transaction_detail.return_value = None
                with patch.object(app, "_bank_transaction_split_routes", return_value=split_routes):
                    missing = app.handle_request("GET", "/api/bank-transactions/missing/source-detail")
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(json.loads(missing.body)["error"], "bank_transaction_not_found")

                configure_access_control(app, page_access={"test_finops_user": ["imports.invoices"]})
                self.repository.bank_transaction_detail.reset_mock()
                denied = app.handle_request("GET", "/api/bank-transactions/bank-1/source-detail")
                self.assertEqual(denied.status_code, 403)
                self.assertEqual(json.loads(denied.body)["error"], "page_access_denied")
                self.repository.bank_transaction_detail.assert_not_called()
            finally:
                app.close()

    def test_shared_bank_route_authenticates_and_returns_source_detail_contract(self) -> None:
        self.repository.bank_transaction_detail.return_value = {
            "id": "bank-1", "txn_direction": "outflow", "amount": "100",
            "transaction_date": "2026-09-27", "booked_date": None, "balance": 0,
            "status": "pending", "currency": "CNY", "trade_time": "2026-09-27T00:00:00",
        }
        auth = Mock(return_value=(object(), None))
        route = self._route(auth)
        headers = {"Authorization": "test-value"}

        status, payload = route.route("GET", "/api/bank-transactions/bank-1/source-detail", {}, None, headers)

        auth.assert_called_once_with(headers)
        self.repository.bank_transaction_detail.assert_called_once_with("bank-1")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIs(payload["detail_available"], True)
        self.assertEqual(payload["sections"][0]["bank_transaction_id"], "bank-1")
        fields = _fields(payload)
        self.assertEqual(fields["交易日期"], "2026-09-27")
        self.assertEqual(fields["支出金额"], "100.00")
        self.assertEqual(fields["余额"], "0.00")
        for label in ("状态", "币种", "交易时间", "入账日期"):
            self.assertNotIn(label, fields)

    def test_shared_bank_route_auth_failure_never_reads_source(self) -> None:
        denied = (HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        route = self._route(Mock(return_value=(None, denied)))
        self.assertEqual(route.route("GET", "/api/bank-transactions/bank-1/source-detail", {}, None, {}), denied)
        self.repository.bank_transaction_detail.assert_not_called()

    def test_shared_bank_route_missing_record_returns_typed_not_found(self) -> None:
        self.repository.bank_transaction_detail.return_value = None
        route = self._route(Mock(return_value=(object(), None)))
        status, payload = route.route("GET", "/api/bank-transactions/missing/source-detail", {}, None, {})
        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(payload["error"], "bank_transaction_not_found")
        self.assertIn("missing", payload["message"])

    def _route(self, auth: Mock) -> PendingInvoiceApiRoutes:
        return PendingInvoiceApiRoutes(
            query_service=Mock(), application_service=Mock(), page_query_service=self.service,
            rules_service=Mock(), export_content_type="text/csv", resolve_read_session=auth,
            error_response=lambda exc: (exc.status_code, {"error": exc.error_code, "message": str(exc)}),
        )


if __name__ == "__main__":
    unittest.main()
