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
from fin_ops_platform.services.source_record_details import invoice_source_detail, query_source_detail
from openpyxl import load_workbook


def resolve(a="100", t="13", g="113", r=None, **kwargs):
    return resolve_invoice_financial_values(amount=a, tax_amount=t, total_with_tax=g, tax_rate=r, **kwargs)


def invoice(**kwargs):
    return Invoice(**dict(id="derived", invoice_type=InvoiceType.INPUT, invoice_no="12345678",
                         counterparty=Counterparty("party", "供应商", "供应商", "supplier"),
                         amount=Decimal("100"), signed_amount=Decimal("100"), **kwargs))


class InvoiceFinancialValuesTests(unittest.TestCase):
    def test_input_rate_filter_normalizes_source_rates_without_merging_inferred_rates(self):
        [item] = parse_input_invoice_usage_filters([{"field": "tax_rate", "operator": "in", "values": ["0.13", "13%", "13%（推算）"]}])
        self.assertEqual(item["values"], ["13%", "13%（推算）"])
        with self.assertRaises(InputInvoiceUsageQueryContractError):
            parse_input_invoice_usage_filters([{"field": "tax_rate", "operator": "in", "values": "13%"}])

    def test_missing_money_and_rate_have_per_field_provenance(self):
        for key, inputs, expected in [
            ("amount", (None, "13", "113", "13%"), Decimal("100.00")),
            ("tax_amount", ("100", None, "113", "13%"), Decimal("13.00")),
            ("total_with_tax", ("100", "13", None, "13%"), Decimal("113.00")),
        ]:
            with self.subTest(key=key):
                result = resolve(*inputs)
                self.assertEqual(getattr(result, key), expected)
                self.assertEqual(result.inferred_fields, (key,))
                self.assertIsNone(result.issue)

    def test_production_sample_and_red_invoice(self):
        for sign in (1, -1):
            values = [Decimal(x) * sign for x in ("1884674.86", "245007.73", "2129682.59")]
            result = resolve(*values)
            self.assertEqual(result.rate_label, "无法确定")
            self.assertNotIn("tax_rate", result.inferred_fields)
            self.assertEqual(result.total_with_tax, values[2])
        for a, t, g in (("94.34", "5.66", "100"), ("2000", "190", "2190"),
                        ("22.82", "0.68", "23.50"), ("9.22", "0.28", "9.50"),
                        ("0.39", "0.04", "0.43"), ("1307.96", "170.04", "1478")):
            self.assertEqual(resolve(a, t, g).rate_label, "无法确定")

    def test_zero_exempt_mixed_special_conflict_and_insufficient_values(self):
        for r, label in (("0", "0%"), (0, "0%"), (Decimal("0"), "0%"), ("免税", "免税"), ("不征税", "不征税"), ("0.13", "13%")):
            self.assertEqual(resolve(r=r).tax_rate, label)
            self.assertEqual(resolve(r=r).inferred_fields, ())
        self.assertIsNone(resolve("0", "0", "0").tax_rate)
        self.assertIsNone(resolve("100", "0", "100").tax_rate)
        self.assertIsNone(resolve("100", "13", "120").tax_rate)
        self.assertIsNotNone(resolve("100", "13", "120").issue)
        self.assertIsNone(resolve("100", "-13", "87").tax_rate)
        self.assertIsNone(resolve("100", None, None).tax_amount)
        self.assertIsNone(resolve("100", None, None).total_with_tax)
        self.assertIsNone(resolve("100", None, "113").tax_rate)  # no inference chain
        # 整票总额与明细分别舍入，不能用固定税率误差拒绝确定性的加减结果。
        self.assertEqual(resolve("100", None, "106", "13%").tax_amount, Decimal("6.00"))
        self.assertIsNone(resolve(r="mixed").tax_rate)
        self.assertIsNone(resolve("100", None, "90").tax_amount)  # invalid sign
        for raw in ("invalid", "NaN", "Infinity"):
            with self.assertRaises(ValueError):
                resolve(raw)

    def test_sources_remain_unchanged_and_all_shared_details_label_inferences(self):
        inv = invoice(tax_amount=Decimal("13"), total_with_tax=Decimal("113"))
        before = deepcopy(inv)
        group = {"primary": inv, "line_items": [inv], "identity_key": "invoice:1"}
        detail = invoice_source_detail(group)
        self.assertEqual(inv, before)
        fields = {field["label"]: field["value"] for section in detail["sections"] for field in section["fields"]}
        self.assertEqual(fields["税率"], "无法确定")
        self.assertEqual(detail["taxRate"], "无法确定")
        self.assertEqual(detail["inferredFields"], [])
        self.assertEqual(invoice_financial_summary([inv])["taxRate"], "无法确定")
        raw = {"id": "query", "amount_without_tax": "100", "tax_amount": "13", "total_with_tax": None}
        original = deepcopy(raw)
        detail = query_source_detail("invoice", raw)
        self.assertEqual(raw, original)
        self.assertTrue(detail["sections"][0]["invoice_navigation"]["totalWithTaxInferred"])
        self.assertIn("113.00（推算）", [f["value"] for s in detail["sections"] for f in s["fields"]])

    def test_old_inferred_rate_is_removed_without_erasing_money_provenance(self):
        inv = invoice(tax_rate="13%", tax_amount=Decimal("13"), total_with_tax=Decimal("113"),
                      inferred_fields=["amount", "tax_rate"])
        original = deepcopy(inv)
        result = invoice_financial_summary([inv])
        self.assertEqual(result["taxRate"], "无法确定")
        self.assertEqual(result["inferredFields"], ["amount"])
        self.assertEqual(inv, original)

    def test_original_lines_recover_rate_only_with_complete_amount_coverage(self):
        lines = [{"amount": "40", "tax_amount": "5.20", "total_with_tax": "45.20", "tax_rate": "0.13"},
                 {"amount": "60", "tax_amount": "7.80", "total_with_tax": "67.80", "tax_rate": "13.00%"}]
        before = deepcopy(lines)
        for raw in (None, "mixed"):
            result = resolve(r=raw, source_line_items=lines)
            self.assertEqual(result.rate_label, "13%")
            self.assertEqual(result.inferred_fields, ())
        self.assertEqual(lines, before)
        recovered = resolve(r="10.26%", inferred_fields=["tax_rate"], source_line_items=lines)
        self.assertEqual(recovered.rate_label, "13%")
        self.assertEqual(recovered.inferred_fields, ())
        self.assertEqual(resolve(source_line_items=lines[:1]).rate_label, "无法确定")
        self.assertEqual(resolve(None, None, None, source_line_items=lines).rate_label, "无法确定")
        incomplete = [{**line, "tax_amount": None, "total_with_tax": None} for line in lines]
        self.assertEqual(resolve(source_line_items=incomplete).rate_label, "无法确定")
        missing_rate = [lines[0], {**lines[1], "tax_rate": None}]
        self.assertEqual(resolve(source_line_items=missing_rate).rate_label, "无法确定")
        self.assertEqual(resolve(r="13%", source_line_items=missing_rate).rate_label, "13%")

    def test_source_coverage_rejects_invalid_line_money_and_checks_completed_header(self):
        invalid = [{"amount": "100", "tax_amount": None, "total_with_tax": "90", "tax_rate": "13%"}]
        self.assertEqual(resolve("100", None, None, source_line_items=invalid).rate_label, "无法确定")
        fractional = [{"amount": "0.001", "tax_amount": "0.001", "total_with_tax": "0.002", "tax_rate": "13%"}]
        self.assertEqual(resolve("0.004", "0.004", None, source_line_items=fractional).rate_label, "无法确定")
        comma = [{"amount": "1,000", "tax_amount": "130", "total_with_tax": "1,130", "tax_rate": "13%"}]
        self.assertEqual(resolve("1000", "130", "1130", source_line_items=comma).rate_label, "13%")

    def test_mixed_source_lines_and_source_conflict_do_not_use_weighted_rate(self):
        lines = [{"amount": "1000", "tax_amount": "130", "total_with_tax": "1130", "tax_rate": "13%"},
                 {"amount": "1000", "tax_amount": "60", "total_with_tax": "1060", "tax_rate": "6%"}]
        self.assertEqual(resolve("2000", "190", "2190", source_line_items=lines).rate_label, "多税率")
        self.assertEqual(resolve("3000", "190", "3190", source_line_items=[*lines, {"amount": "1000"}]).rate_label, "多税率")
        conflict = resolve("2000", "190", "2190", "13%", source_line_items=lines)
        self.assertEqual(conflict.rate_label, "无法确定")
        self.assertEqual(conflict.issue, "来源税率与明细税率不一致")
        detail = query_source_detail("invoice", {"id": "conflict", "amount_without_tax": "2000",
                    "tax_amount": "190", "total_with_tax": "2190", "tax_rate": "13%", "source_line_items": lines})
        self.assertEqual(detail["taxRate"], "无法确定")
        self.assertNotIn("_sourceLineItems", detail)
        fields = {field["label"]: field["value"] for section in detail["sections"] for field in section["fields"]}
        self.assertEqual(fields["核对说明"], "来源税率与明细税率不一致")

    def test_group_rate_accounts_for_unknown_and_distinct_rates(self):
        for rates, expected in [(["0.13", "13%"], "13%"), (["13%", None], "无法确定"),
                                ([None, None], "无法确定"), (["13%", "6%", None], "多税率"),
                                (["0%", "免税"], "多税率"), (["免税", "不征税"], "多税率")]:
            with self.subTest(rates=rates):
                self.assertEqual(invoice_financial_summary([invoice(tax_rate=rate) for rate in rates])["taxRate"], expected)
        self.assertEqual(invoice_financial_summary([])["taxRate"], "无法确定")

    def test_import_rate_aggregation_handles_normalized_missing_and_mixed_rates(self):
        for rates, expected in [(["0.13", "13%"], "13%"), (["13%", None], None),
                                (["13%", "6%", None], "mixed")]:
            rows = [{"digital_invoice_no": "12345678901234567890", "taxable_item_name": str(i),
                     "amount": "100", "tax_amount": "13", "total_with_tax": "113", "tax_rate": rate}
                    for i, rate in enumerate(rates)]
            before = deepcopy(rows)
            [result] = aggregate_invoice_line_rows(rows)
            self.assertEqual(result["tax_rate"], expected)
            self.assertEqual(result["source_line_items"], before)
            self.assertEqual(rows, before)

    def test_import_missing_required_amount_retains_original_and_provenance(self):
        raw = {"invoice_no": "12345678", "counterparty_name": "供应商", "invoice_date": "2026-10-03",
               "amount": None, "tax_amount": "13", "total_with_tax": "113", "tax_rate": "13%"}
        original = deepcopy(raw)
        service = ImportNormalizationService()
        normalized, errors = service._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row=raw)
        self.assertEqual(errors, [])
        self.assertEqual(raw, original)
        self.assertEqual(normalized["amount"], "100.00")
        self.assertEqual(normalized["inferred_fields"], ["amount"])
        result = service._build_invoice_from_normalized(BatchType.INPUT_INVOICE, "batch", normalized)
        self.assertEqual(invoice_financial_summary([result])["inferredFields"], ["amount"])
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
            self.assertNotIn("amount", normalized)
            self.assertEqual(normalized["inferred_fields"], [])

    def test_multi_line_import_never_turns_missing_tax_into_zero(self):
        base = {"digital_invoice_no": "12345678901234567890", "amount": "100", "tax_rate": None}
        rows = [{**base, "taxable_item_name": "A", "tax_amount": None, "total_with_tax": "113"},
                {**base, "taxable_item_name": "B", "tax_amount": "13", "total_with_tax": "113"}]
        original = deepcopy(rows)
        [merged] = aggregate_invoice_line_rows(rows)
        self.assertEqual(rows, original)
        self.assertEqual(merged["tax_amount"], "26.00")
        self.assertEqual(merged["inferred_fields"], ["tax_amount"])
        self.assertIsNone(merged["tax_rate"])
        rows[0]["total_with_tax"] = None
        [merged] = aggregate_invoice_line_rows(rows)
        self.assertIsNone(merged["tax_amount"])
        self.assertIsNone(merged["total_with_tax"])

    def test_export_keeps_numeric_money_and_provenance(self):
        inv = {"invoiceNo": "123", "invoiceCode": "", "sellerTaxNo": "", "sellerName": "公司",
               "invoiceDate": "2026-10-03", "specificBusinessType": "", "taxableItemName": "服务",
               **invoice_financial_summary([invoice(tax_amount=None, total_with_tax=Decimal("113"), tax_rate="13%")])}
        service = InputInvoiceUsageExportService(row_export_loader=lambda **_: {"total": 1, "rows": [{"invoice": inv}]})
        _, binary = service.export()
        book = load_workbook(BytesIO(binary), data_only=True)
        values = list(book.active.values)
        self.assertEqual(values[1][10], 13)
        self.assertEqual(values[1][13], "推算")
        book.close()
