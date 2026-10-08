from __future__ import annotations

import unittest
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import MagicMock, Mock, patch

from openpyxl import Workbook

from fin_ops_platform.services.tax_certified_import_service import (
    SOURCE_COLUMNS,
    TaxCertifiedImportService,
    UploadedCertifiedImportFile,
    _build_unique_key,
)


def certified_upload(*, deductible="0", amount="100", tax="13", month="202609", digital="TEST-DIGITAL-1",
                     buyer="TEST-BUYER", invoice_code="CODE-1", selection_time="2026-10-02 13:14:15", label="增值税专用发票",
                     bad_dimensions=False, extra_rows=None) -> UploadedCertifiedImportFile:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "发票"
    sheet.append(["发票清单"])
    sheet.append(["纳税人识别号", buyer, None, None, "税款所属期", month, None, "纳税人名称", "测试买方"])
    sheet.append(list(SOURCE_COLUMNS))
    row = [1, "已勾选", "电子发票", None, digital, invoice_code, "NUMBER-1", "2026-08-15",
           "TEST-SELLER", "测试销方", amount, tax, deductible, "01", label, "正常", selection_time, "低", "正常"]
    sheet.append(row)
    for extra in extra_rows or []:
        sheet.append(extra)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    if bad_dimensions:
        import re
        source, target = ZipFile(BytesIO(buffer.getvalue())), BytesIO()
        with source, ZipFile(target, "w") as dest:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "xl/worksheets/sheet1.xml":
                    content = re.sub(rb'<dimension ref="[^"]+"', b'<dimension ref="A1"', content)
                dest.writestr(info, content)
        buffer = target
    return UploadedCertifiedImportFile("用途确认信息.xlsx", buffer.getvalue())


class TaxCertifiedImportServiceTests(unittest.TestCase):
    def preview(self, **kwargs):
        return TaxCertifiedImportService(repository=Mock()).preview_files(imported_by="test-owner", uploads=[certified_upload(**kwargs)]).files[0]

    def test_bad_dimensions_source_labels_zero_and_dates_are_independent(self):
        file = self.preview(bad_dimensions=True)
        self.assertEqual((file.recognized_count, file.invalid_count, file.month), (1, 0, "2026-09"))
        row = file.rows[0]
        self.assertEqual(row.buyer_tax_no, "TEST-BUYER")
        self.assertEqual(row.issue_date, "2026-08-15")
        self.assertEqual(row.selection_time, "2026-10-02 13:14:15")
        self.assertEqual(row.deductible_tax_amount, "0")
        self.assertEqual(row.invoice_kind, "01")
        self.assertEqual(row.invoice_kind_label, "增值税专用发票")
        self.assertEqual(len(row.source_fields), 19)

    def test_missing_amounts_are_not_filled(self):
        row = self.preview(amount=None, tax=None, deductible=None).rows[0]
        self.assertIsNone(row.amount)
        self.assertIsNone(row.tax_amount)
        self.assertIsNone(row.deductible_tax_amount)

    def test_missing_month_does_not_use_selection_date_or_filename(self):
        self.assertIsNone(self.preview(month=None).month)

    def test_non_special_and_invalid_money_and_date_are_explicit(self):
        for kwargs in ({"amount": "NaN"}, {"tax": "bad"}, {"selection_time": "2026-99-99"}):
            with self.subTest(kwargs=kwargs):
                file = self.preview(**kwargs)
                self.assertEqual(file.recognized_count, 0)
                self.assertEqual(file.invalid_count, 1)
                self.assertTrue(file.row_results[0]["error_message"])

    def test_strong_identity_only(self):
        with self.assertRaisesRegex(ValueError, "缺少"):
            _build_unique_key(digital_invoice_no=None, invoice_code=None, invoice_no="123")
        self.assertEqual(_build_unique_key(digital_invoice_no="123", invoice_code="X", invoice_no="Y"), "digital:123")
        self.assertEqual(_build_unique_key(digital_invoice_no=None, invoice_code="X", invoice_no="Y"), "invoice:X:Y")

    def test_empty_uploads_and_conflicting_metadata_rejected(self):
        service = TaxCertifiedImportService(repository=Mock())
        with self.assertRaises(ValueError):
            service.preview_files(imported_by="owner", uploads=[])
        for kwargs in ({"month": "2026-13"}, {"month": "2026-08"}, {"buyer_tax_no": "OTHER"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                service.preview_files(imported_by="owner", uploads=[certified_upload()], **kwargs)

    def test_non_special_is_ignored_and_malformed_xlsx_is_rejected(self):
        file = self.preview(label="普通发票")
        self.assertEqual((file.recognized_count, file.invalid_count, file.ignored_count), (0, 0, 1))
        service = TaxCertifiedImportService(repository=Mock())
        with self.assertRaisesRegex(ValueError, "XLSX"):
            service.preview_files(imported_by="owner", uploads=[UploadedCertifiedImportFile("broken.xlsx", b"not zip")])
        valid = certified_upload()
        buffer = BytesIO()
        with ZipFile(BytesIO(valid.content)) as source, ZipFile(buffer, "w") as destination:
            for info in source.infolist():
                data = b"<broken" if info.filename == "xl/worksheets/sheet1.xml" else source.read(info.filename)
                destination.writestr(info, data)
        with self.assertRaisesRegex(ValueError, "XLSX"):
            service.preview_files(imported_by="owner", uploads=[UploadedCertifiedImportFile("broken.xlsx", buffer.getvalue())])

    def test_parser_stops_reading_at_row_and_column_limits_and_closes_workbook(self):
        workbook = MagicMock()
        workbook.sheetnames = ["发票"]
        sheet = workbook.__getitem__.return_value
        consumed = []
        def rows():
            yield tuple(SOURCE_COLUMNS)
            for number in range(20_005):
                consumed.append(number)
                yield (number, "已勾选")
        sheet.iter_rows.return_value = rows()
        with patch("fin_ops_platform.services.tax_certified_import_service.load_workbook", return_value=workbook):
            with self.assertRaisesRegex(ValueError, "20000"):
                self.preview()
        self.assertEqual(len(consumed), 20_001)
        workbook.close.assert_called_once()
        workbook.close.reset_mock()
        sheet.iter_rows.return_value = iter([tuple(range(65))])
        with patch("fin_ops_platform.services.tax_certified_import_service.load_workbook", return_value=workbook):
            with self.assertRaisesRegex(ValueError, "64"):
                self.preview()
        workbook.close.assert_called_once()

    def test_session_budget_is_shared_across_files_and_empty_rows_are_bounded(self):
        service = TaxCertifiedImportService(repository=Mock())
        with patch("fin_ops_platform.services.tax_certified_import_service.MAX_IMPORT_RECORDS", 1):
            with self.assertRaisesRegex(ValueError, "每次认证导入"):
                service.preview_files(imported_by="owner", uploads=[certified_upload(), certified_upload(digital="SECOND")])
        service._repository.save_session.assert_not_called()
        workbook = MagicMock()
        workbook.sheetnames = ["发票"]
        consumed = 0
        def empty_rows():
            nonlocal consumed
            yield tuple(SOURCE_COLUMNS)
            for _ in range(50_100):
                consumed += 1
                yield ()
        workbook.__getitem__.return_value.iter_rows.return_value = empty_rows()
        with patch("fin_ops_platform.services.tax_certified_import_service.load_workbook", return_value=workbook):
            with self.assertRaisesRegex(ValueError, "50000"):
                self.preview()
        self.assertEqual(consumed, 50_000)
        workbook.close.assert_called_once()
