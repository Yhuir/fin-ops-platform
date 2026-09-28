from io import BytesIO
from unittest import TestCase
from unittest.mock import Mock

from fin_ops_platform.services.input_invoice_usage_export_service import (
    InputInvoiceUsageExportError,
    InputInvoiceUsageExportService,
)
from openpyxl import load_workbook


class InputInvoiceUsageExportServiceTests(TestCase):
    def test_summary_reads_no_details_and_passes_exact_filters(self):
        loader = Mock(return_value={"total": 47, "rows": [], "filterOptions": {"payment_status": []}})
        result = InputInvoiceUsageExportService(row_export_loader=loader).export_summary(filters=[{"field": "relation_status", "operator": "in", "values": ["oa_bank"]}])
        self.assertEqual(result, {"row_count": 47, "filter_options": {"payment_status": []}})
        self.assertEqual(loader.call_args.kwargs["limit"], 0)
        self.assertEqual(loader.call_args.kwargs["filters"][0]["values"], ["oa_bank"])
        self.assertNotIn("sample_rows", result)

    def test_file_has_public_fields_exact_identifiers_numeric_money_and_safe_text(self):
        invoice = {"invoiceNo": "00123456789012345678", "invoiceCode": "0012", "sellerTaxNo": "000123", "sellerName": "=SUM(1,2)", "invoiceDate": "2026-09-01", "specificBusinessType": "", "taxableItemName": "服务", "amount": "100.00", "taxRate": "6%", "taxAmount": "6.00", "totalWithTax": "106.00"}
        loader = Mock(return_value={"total": 1, "rows": [{"invoice": invoice}]})
        filename, data = InputInvoiceUsageExportService(row_export_loader=loader).export()
        self.assertTrue(filename.endswith('.xlsx'))
        sheet = load_workbook(BytesIO(data)).active
        headers = [cell.value for cell in sheet[1]]
        self.assertFalse(any('ID' in field or '状态代码' in field for field in headers))
        self.assertEqual(sheet['B2'].value, invoice['invoiceNo'])
        self.assertEqual(sheet['E2'].data_type, 's')
        self.assertEqual(sheet['L2'].value, 106)
        self.assertEqual(sheet.max_row, 2)

    def test_limit_is_real_invoice_count_and_failure_is_not_replaced_by_partial_file(self):
        loader = Mock(return_value={"total": 20001, "rows": []})
        with self.assertRaises(InputInvoiceUsageExportError):
            InputInvoiceUsageExportService(row_export_loader=loader).export()
        loader.side_effect = RuntimeError('database unavailable')
        with self.assertRaisesRegex(RuntimeError, 'database unavailable'):
            InputInvoiceUsageExportService(row_export_loader=loader).export_summary()
