from __future__ import annotations

import unittest
from copy import deepcopy
from decimal import Decimal
from io import BytesIO

from fin_ops_platform.domain.enums import BatchType, InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.import_file_service import aggregate_invoice_line_rows
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_export_service import InputInvoiceUsageExportService
from fin_ops_platform.services.input_invoice_usage_query_contract import (
    InputInvoiceUsageQueryContractError,
    parse_input_invoice_usage_filters,
)
from fin_ops_platform.services.invoice_financial_values import (
    invoice_financial_summary,
    resolve_invoice_financial_values,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.source_record_details import invoice_source_detail, query_source_detail
from openpyxl import load_workbook


def resolve(a="100", t="13", g="113", r=None, **kwargs):
    return resolve_invoice_financial_values(amount=a, tax_amount=t, total_with_tax=g, tax_rate=r, **kwargs)


def invoice(**kwargs):
    values = dict(id="source", invoice_type=InvoiceType.INPUT, invoice_no="12345678",
                  counterparty=Counterparty("party", "供应商", "供应商", "supplier"),
                  amount=Decimal("100"), signed_amount=Decimal("100"))
    return Invoice(**{**values, **kwargs})


class InvoiceFinancialValuesTests(unittest.TestCase):
    def test_input_rate_filter_normalizes_source_rates_without_broadening_old_filters(self):
        [item] = parse_input_invoice_usage_filters([{"field": "tax_rate", "operator": "in", "values": ["0.13", "13%", "13%（推算）"]}])
        self.assertEqual(item["values"], ["13%", "13%（推算）"])
        with self.assertRaises(InputInvoiceUsageQueryContractError):
            parse_input_invoice_usage_filters([{"field": "tax_rate", "operator": "in", "values": "13%"}])

    def test_missing_money_stays_missing_even_when_other_fields_determine_a_number(self):
        for key, inputs in [
            ("amount", (None, "13", "113", "13%")),
            ("tax_amount", ("100", None, "113", "13%")),
            ("total_with_tax", ("100", "13", None, "13%")),
        ]:
            with self.subTest(key=key):
                result = resolve(*inputs)
                self.assertIsNone(getattr(result, key))
                self.assertFalse(hasattr(result, "inferred_fields"))
                self.assertIsNone(result.issue)
        self.assertIsNone(resolve("100", None, "106", "13%").tax_amount)
        self.assertIsNone(resolve("100", None, "90").tax_amount)

    def test_production_sample_and_red_invoice_never_infer_a_rate(self):
        for sign in (1, -1):
            values = [Decimal(x) * sign for x in ("1884674.86", "245007.73", "2129682.59")]
            result = resolve(*values)
            self.assertEqual(result.rate_label, "—")
            self.assertEqual(result.total_with_tax, values[2])
        for a, t, g in (("94.34", "5.66", "100"), ("2000", "190", "2190"),
                        ("22.82", "0.68", "23.50"), ("9.22", "0.28", "9.50"),
                        ("0.39", "0.04", "0.43"), ("1307.96", "170.04", "1478")):
            self.assertEqual(resolve(a, t, g).rate_label, "—")

    def test_zero_exempt_nontaxable_text_and_missing_are_distinct(self):
        for raw, label in (("0", "0%"), (0, "0%"), (Decimal("0"), "0%"),
                           ("免税", "免税"), ("不征税", "不征税"), ("*", "*"),
                           ("0.13", "13%"), ("mixed", "多税率"), (None, "—")):
            self.assertEqual(resolve(r=raw).rate_label, label)
        self.assertIsNone(resolve("0", "0", "0").tax_rate)
        self.assertIsNone(resolve("100", "0", "100").tax_rate)
        text = resolve("100", None, "100", "免税", tax_amount_text="*")
        self.assertIsNone(text.tax_amount)
        self.assertEqual(text.tax_amount_text, "*")
        self.assertIsNone(resolve("100", None, None).total_with_tax)

    def test_source_amount_conflicts_are_reported_without_rewriting_values(self):
        for a, t, g, issue in (("100", "13", "120", "金额、税额与价税合计不一致"),
                               ("100", "-13", "87", "发票金额与税额符号不一致")):
            result = resolve(a, t, g, "13%")
            self.assertEqual((result.amount, result.tax_amount, result.total_with_tax), tuple(map(Decimal, (a, t, g))))
            self.assertEqual(result.issue, issue)
            self.assertEqual(result.rate_label, "13%")
        for raw in ("invalid", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                resolve(raw)

    def test_sources_remain_unchanged_and_shared_details_have_no_synthetic_fields(self):
        inv = invoice(tax_amount=Decimal("13"), total_with_tax=Decimal("113"))
        before = deepcopy(inv)
        detail = invoice_source_detail({"primary": inv, "line_items": [inv], "identity_key": "invoice:1"})
        self.assertEqual(inv, before)
        self.assertEqual(detail["taxRate"], "—")
        self.assertEqual(detail["lineItems"], [])
        self.assertNotIn("inferredFields", detail)
        self.assertEqual(invoice_financial_summary([inv])["taxRate"], "—")
        raw = {"id": "query", "amount_without_tax": "100", "tax_amount": "13", "total_with_tax": None}
        original = deepcopy(raw)
        detail = query_source_detail("invoice", raw)
        self.assertEqual(raw, original)
        self.assertIsNone(detail["sections"][0]["invoice_navigation"]["totalWithTax"])
        self.assertNotIn("totalWithTaxInferred", detail["sections"][0]["invoice_navigation"])
        self.assertEqual(detail["totalWithTax"], "")
        self.assertNotIn("inferredFields", detail)

    def test_explicit_detail_rates_do_not_require_unprinted_money_fields(self):
        lines = [{"amount": "40", "tax_amount": "5.20", "tax_rate": "0.13"},
                 {"amount": "60", "tax_amount": "7.80", "tax_rate": "13.00%"}]
        before = deepcopy(lines)
        self.assertEqual(resolve(source_line_items=lines).rate_label, "—")
        self.assertEqual(resolve(None, None, None, source_line_items=lines).rate_label, "—")
        self.assertEqual(resolve(source_line_items=[{"tax_rate": "13%"}]).rate_label, "—")
        self.assertEqual(lines, before)
        missing_rate = [lines[0], {**lines[1], "tax_rate": None}]
        self.assertEqual(resolve(source_line_items=missing_rate).rate_label, "—")
        self.assertEqual(resolve(r="13%", source_line_items=missing_rate).rate_label, "13%")
        header_only = [{"source_sheet_role": "invoice_header", "tax_rate": "6%"}]
        self.assertEqual(resolve(source_line_items=header_only).rate_label, "—")
        self.assertEqual(resolve(source_line_items=[*header_only, *lines]).rate_label, "—")

    def test_mixed_source_lines_and_source_conflict_preserve_actual_details(self):
        lines = [{"amount": "1000", "tax_amount": "130", "tax_rate": "13%"},
                 {"amount": "1000", "tax_amount": "60", "tax_rate": "6%"}]
        self.assertEqual(resolve("2000", "190", "2190", source_line_items=lines).rate_label, "—")
        self.assertEqual(resolve("3000", "190", "3190", source_line_items=[*lines, {"amount": "1000"}]).rate_label, "—")
        conflict = resolve("2000", "190", "2190", "13%", source_line_items=lines)
        self.assertEqual(conflict.rate_label, "—")
        self.assertEqual(conflict.issue, "来源税率与明细税率不一致")
        detail = query_source_detail("invoice", {"id": "conflict", "amount_without_tax": "2000",
                    "tax_amount": "190", "total_with_tax": "2190", "tax_rate": "13%", "source_line_items": lines})
        self.assertEqual(detail["taxRate"], "—")
        self.assertNotIn("_sourceLineItems", detail)
        self.assertEqual(detail["financialIssue"], "来源税率与明细税率不一致")
        self.assertEqual([line["taxRate"] for line in detail["lineItems"]], ["13%", "6%"])
        self.assertEqual([line["totalWithTax"] for line in detail["lineItems"]], ["", ""])

    def test_group_rate_accounts_for_unknown_and_distinct_rates(self):
        for rates, expected in [(["0.13", "13%"], "13%"), (["13%", None], "—"),
                                ([None, None], "—"), (["13%", "6%", None], "多税率"),
                                (["0%", "免税"], "多税率"), (["免税", "不征税"], "多税率")]:
            with self.subTest(rates=rates):
                self.assertEqual(invoice_financial_summary([invoice(tax_rate=rate) for rate in rates])["taxRate"], expected)
        self.assertEqual(invoice_financial_summary([])["taxRate"], "—")

    def test_group_money_never_returns_a_partial_sum_or_missing_as_zero(self):
        values = invoice_financial_summary([invoice(tax_amount=None), invoice(amount=None, tax_amount=Decimal("13"))])
        self.assertEqual((values["amount"], values["taxAmount"], values["totalWithTax"]), ("", "", ""))
        self.assertEqual(invoice_financial_summary([])["amount"], "")
        self.assertEqual(invoice_financial_summary([invoice(amount=Decimal("0"))])["amount"], "0.00")

    def test_import_rate_aggregation_handles_normalized_missing_and_mixed_rates(self):
        for rates, expected in [(["0.13", "13%"], "13%"), (["13%", None], None),
                                (["13%", "6%", None], "mixed")]:
            rows = [{"digital_invoice_no": "12345678901234567890", "taxable_item_name": str(i),
                     "amount": "100", "tax_amount": "13", "total_with_tax": "113", "tax_rate": rate}
                    for i, rate in enumerate(rates)]
            before = deepcopy(rows)
            [result] = aggregate_invoice_line_rows(rows)
            self.assertIsNone(result["tax_rate"])
            self.assertEqual(result["source_line_items"], before)
            self.assertEqual(rows, before)

    def test_import_missing_amount_retains_original_without_completion(self):
        raw = {"invoice_no": "12345678", "counterparty_name": "供应商", "invoice_date": "2026-10-03",
               "amount": None, "tax_amount": "13", "total_with_tax": "113", "tax_rate": "13%"}
        original = deepcopy(raw)
        service = ImportNormalizationService()
        normalized, errors = service._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row=raw)
        self.assertEqual(errors, [])
        self.assertEqual(raw, original)
        self.assertIsNone(normalized["amount"])
        self.assertNotIn("inferred_fields", normalized)
        result = service._build_invoice_from_normalized(BatchType.INPUT_INVOICE, "batch", normalized)
        self.assertEqual(invoice_financial_summary([result])["amount"], "")
        again, errors = service._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row=raw)
        self.assertEqual(again, normalized)
        self.assertEqual(errors, [])

    def test_import_invalid_amounts_are_reported_without_fabrication(self):
        service = ImportNormalizationService()
        for amount, tax in ((None, "NaN"), (None, "invalid"), ("NaN", "13")):
            normalized, errors = service._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row={
                "invoice_no": "123", "counterparty_name": "供应商", "invoice_date": "2026-10-03",
                "amount": amount, "tax_amount": tax, "total_with_tax": "113",
            })
            self.assertTrue(errors)
            self.assertIsNone(normalized.get("amount"))
            self.assertNotIn("inferred_fields", normalized)

    def test_import_text_tax_reaches_header_and_actual_detail_without_becoming_zero(self):
        raw = {"invoice_no": "12345678", "counterparty_name": "供应商", "invoice_date": "2026-10-03",
               "amount": "100", "tax_amount": "*", "total_with_tax": "100", "tax_rate": "不征税",
               "source_line_items": [{"taxable_item_name": "预付卡充值", "amount": "100",
                                      "tax_amount": "*", "tax_rate": "不征税"}]}
        original = deepcopy(raw)
        service = ImportNormalizationService()
        normalized, errors = service._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row=raw)
        self.assertEqual(errors, [])
        inv = service._build_invoice_from_normalized(BatchType.INPUT_INVOICE, "batch", normalized)
        detail = invoice_source_detail({"primary": inv, "line_items": [inv], "identity_key": "text-tax"})
        self.assertEqual(raw, original)
        self.assertEqual((detail["taxAmount"], detail["taxAmountText"]), ("", "*"))
        self.assertEqual((detail["lineItems"][0]["taxAmount"], detail["lineItems"][0]["taxAmountText"]), ("", "*"))
        self.assertEqual(detail["lineItems"][0]["totalWithTax"], "")

    def test_multi_line_import_never_turns_missing_tax_into_zero_or_partial_sum(self):
        base = {"digital_invoice_no": "12345678901234567890", "amount": "100", "tax_rate": None}
        rows = [{**base, "taxable_item_name": "A", "tax_amount": None, "total_with_tax": "113"},
                {**base, "taxable_item_name": "B", "tax_amount": "13", "total_with_tax": "113"}]
        original = deepcopy(rows)
        [merged] = aggregate_invoice_line_rows(rows)
        self.assertEqual(rows, original)
        self.assertIsNone(merged["tax_amount"])
        self.assertNotIn("inferred_fields", merged)
        self.assertIsNone(merged["tax_rate"])
        rows[0]["total_with_tax"] = None
        [merged] = aggregate_invoice_line_rows(rows)
        self.assertIsNone(merged["tax_amount"])
        self.assertIsNone(merged["total_with_tax"])

    def test_export_keeps_numeric_money_text_tax_and_missing_values_separate(self):
        for tax, text, exported in ((None, None, None), (None, "*", "*"), (Decimal("0"), None, 0)):
            with self.subTest(tax=tax, text=text):
                inv = {"invoiceNo": "123", "digitalInvoiceNo": "", "invoiceCode": "", "sellerTaxNo": "", "sellerName": "公司",
                       "buyerTaxNo": "", "buyerName": "公司", "invoiceDate": "2026-10-03",
                       "specificBusinessType": "", "taxableItemName": "服务", "remark": "",
                       **invoice_financial_summary([invoice(tax_amount=tax, tax_amount_text=text,
                           total_with_tax=Decimal("113"), tax_rate="13%")])}
                service = InputInvoiceUsageExportService(row_export_loader=lambda **_: {"total": 1, "rows": [{"invoice": inv}]})
                _, binary = service.export()
                book = load_workbook(BytesIO(binary), data_only=True)
                values = list(book.active.values)
                self.assertEqual(values[1][10], exported)
                self.assertEqual(values[1][11], 113)
                self.assertNotIn("税额来源", values[0])
                book.close()
                row = OutputInvoiceCollectionQueryService._export_row(1, {"invoice": inv})
                self.assertEqual(row["税额"], exported)
                self.assertNotIn("税额来源", row)
