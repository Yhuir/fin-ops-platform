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
            ("tax_rate", ("100", "13", "113", None), "13%"),
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
            self.assertEqual(result.rate_label, "13%（推算）")
            self.assertEqual(result.total_with_tax, values[2])
        self.assertEqual(resolve("94.34", "5.66", "100").rate_label, "6%（推算）")
        self.assertEqual(resolve("2000", "190", "2190").rate_label, "9.5%（推算）")

    def test_zero_exempt_mixed_special_conflict_and_insufficient_values(self):
        for r in ("0", "免税", "不征税", "mixed", "0.13"):
            self.assertEqual(resolve(r=r).tax_rate, r)
            self.assertEqual(resolve(r=r).inferred_fields, ())
        self.assertIsNone(resolve("0", "0", "0").tax_rate)
        self.assertIsNone(resolve("100", "0", "100").tax_rate)
        self.assertIsNone(resolve(specific_business_type="差额征税").tax_rate)
        self.assertIsNone(resolve("100", "13", "120").tax_rate)
        self.assertIsNotNone(resolve("100", "13", "120").issue)
        self.assertIsNone(resolve("100", "-13", "87").tax_rate)
        self.assertIsNone(resolve("100", None, None).tax_amount)
        self.assertIsNone(resolve("100", None, None).total_with_tax)
        self.assertIsNone(resolve("100", None, "113").tax_rate)  # no inference chain
        self.assertIsNone(resolve("100", None, "106", "13%").tax_amount)
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
        self.assertEqual(fields["税率"], "13%（推算）")
        self.assertEqual(detail["taxRate"], "13%")
        self.assertEqual(detail["inferredFields"], ["taxRate"])
        self.assertEqual(invoice_financial_summary([inv])["taxRate"], "13%（推算）")
        raw = {"id": "query", "amount_without_tax": "100", "tax_amount": "13", "total_with_tax": None}
        original = deepcopy(raw)
        detail = query_source_detail("invoice", raw)
        self.assertEqual(raw, original)
        self.assertTrue(detail["sections"][0]["invoice_navigation"]["totalWithTaxInferred"])
        self.assertIn("113.00（推算）", [f["value"] for s in detail["sections"] for f in s["fields"]])

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
