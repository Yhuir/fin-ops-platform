from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest

from openpyxl import Workbook, load_workbook

from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile, is_company_identity
from fin_ops_platform.services.imports import ImportNormalizationService

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from mock_import_files import (
    BOCOM_JAN,
    CEB_JAN,
    INVOICE_JAN,
    PINGAN_JAN,
    icbc_history_file,
    invoice_export_file,
    invoice_summary_file,
)


def repeat_last_xlsx_row(content: bytes, *, total_data_rows: int) -> bytes:
    workbook = load_workbook(BytesIO(content))
    sheet = workbook.active
    last_row = [cell.value for cell in sheet[sheet.max_row]]
    for _ in range(total_data_rows - 1):
        sheet.append(last_row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def invoice_export_second_sheet_file() -> bytes:
    source = load_workbook(BytesIO(INVOICE_JAN.content))
    workbook = Workbook()
    summary = workbook.active
    summary.title = "导出摘要"
    summary["A1"] = "此工作表不是发票明细。"
    data_sheet = workbook.create_sheet("合并数据")
    for row in source.active.iter_rows(values_only=True):
        data_sheet.append(list(row))
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class FakeImportIdStore:
    def __init__(self) -> None:
        self._existing_session_ids = {"import_session_0001", "import_session_0002"}
        self._existing_file_ids = {"import_file_0001", "import_file_0002"}
        self._stored_refs: list[str] = []

    def import_session_exists(self, session_id: str) -> bool:
        return session_id in self._existing_session_ids

    def import_file_exists(self, file_id: str) -> bool:
        return file_id in self._existing_file_ids

    def store_import_file(self, *, session_id: str, file_id: str, file_name: str, content: bytes) -> str:
        self._existing_session_ids.add(session_id)
        self._existing_file_ids.add(file_id)
        ref = f"stored://{session_id}/{file_id}/{file_name}"
        self._stored_refs.append(ref)
        return ref


class FakeImportEntityRegistry:
    def __init__(self) -> None:
        self._existing_batch_ids = {"batch_import_0001"}
        self._existing_invoice_ids = {"inv_imported_0001"}
        self._existing_transaction_ids = {"txn_imported_0001"}

    def import_batch_exists(self, batch_id: str) -> bool:
        return batch_id in self._existing_batch_ids

    def invoice_exists(self, invoice_id: str) -> bool:
        return invoice_id in self._existing_invoice_ids

    def transaction_exists(self, transaction_id: str) -> bool:
        return transaction_id in self._existing_transaction_ids


class ImportFileServiceTests(unittest.TestCase):
    def test_company_identity_name_keywords_use_yunnan_and_generic_suyuan_names(self) -> None:
        self.assertTrue(is_company_identity(None, "云南溯源科技有限公司"))
        self.assertTrue(is_company_identity(None, "溯源科技有限公司"))
        self.assertTrue(is_company_identity("91330106589876543T", "无关公司名称"))

    def test_preview_marks_corrupt_excel_as_file_level_error_instead_of_raising(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name="损坏发票.xlsx", content=b"not-a-real-xlsx")],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "unrecognized_template")
        self.assertEqual(preview_file.row_count, 0)
        self.assertIn("文件读取失败", preview_file.message)

    def test_preview_accepts_invoice_summary_header_aliases(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = invoice_summary_file()

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=upload.name,
                    content=upload.content,
                    template_code_override="invoice_export",
                    batch_type_override="input_invoice",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "invoice_export")
        self.assertEqual(preview_file.batch_type.value, "input_invoice")
        self.assertEqual(preview_file.row_count, 1)
        self.assertEqual(preview_file.success_count, 1)
        normalized = preview_file.normalized_rows[0]
        self.assertEqual(normalized["digital_invoice_no"], "26312000002781821596")
        self.assertEqual(normalized["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(normalized["buyer_tax_no"], "915300007194052520")
        self.assertEqual(normalized["seller_name"], "阿法拉伐（上海）技术有限公司")
        self.assertEqual(normalized["seller_tax_no"], "91310000607371000G")
        self.assertEqual(normalized["counterparty_name"], "阿法拉伐（上海）技术有限公司")
        self.assertEqual(normalized["taxable_item_name"], "*通用设备*垫片板式换热器")
        self.assertEqual(normalized["invoice_kind"], "数电票(专用发票)")
        self.assertEqual(normalized["total_with_tax"], "14384.00")

    def test_preview_detects_invoice_summary_without_template_override(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = invoice_summary_file()

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=upload.name, content=upload.content)],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "invoice_export")
        self.assertEqual(preview_file.batch_type.value, "input_invoice")

    def test_preview_detects_invoice_data_when_summary_sheet_is_first(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name="进项发票合并.xlsx",
                    content=invoice_export_second_sheet_file(),
                    batch_type_override="input_invoice",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "invoice_export")
        self.assertEqual(preview_file.row_count, 1)
        self.assertEqual(preview_file.normalized_rows[0]["digital_invoice_no"], "25502000000145098656")

    def test_preview_skips_existing_session_file_and_batch_ids_when_counters_restart(self) -> None:
        file_store = FakeImportIdStore()
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service, file_store=file_store)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=INVOICE_JAN.name, content=INVOICE_JAN.content)],
        )

        self.assertEqual(session.id, "import_session_0003")
        self.assertEqual(session.files[0].id, "import_file_0003")
        self.assertEqual(session.files[0].preview_batch_id, "batch_import_0002")
        self.assertEqual(session.files[0].status, "preview_ready")
        self.assertTrue(session.files[0].stored_file_path)

    def test_preview_persists_selected_bank_mapping_and_marks_conflict_against_detected_account(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=PINGAN_JAN.name,
                    content=PINGAN_JAN.content,
                    selected_bank_mapping_id="bank_mapping_pingan_override",
                    selected_bank_name="建设银行",
                    selected_bank_last4="8826",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.selected_bank_mapping_id, "bank_mapping_pingan_override")
        self.assertEqual(preview_file.selected_bank_name, "建设银行")
        self.assertEqual(preview_file.selected_bank_last4, "8826")
        self.assertTrue(preview_file.bank_selection_conflict)
        self.assertEqual(preview_file.detected_last4, "0093")
        self.assertIn("建设银行", preview_file.conflict_message)
        self.assertIn("0093", preview_file.conflict_message)

    def test_preview_does_not_mark_bank_name_alias_as_conflict_when_last4_matches(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=CEB_JAN.name,
                    content=CEB_JAN.content,
                    selected_bank_mapping_id="bank_mapping_ceb_8826",
                    selected_bank_name="光大",
                    selected_bank_last4="8826",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.detected_bank_name, "光大银行")
        self.assertEqual(preview_file.detected_last4, "8826")
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertIsNone(preview_file.conflict_message)

    def test_preview_does_not_mark_bank_short_name_as_conflict_when_last4_matches(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=CEB_JAN.name,
                    content=CEB_JAN.content,
                    selected_bank_mapping_id="bank_mapping_ceb_8826",
                    selected_bank_name="中国光大银行股份有限公司",
                    selected_bank_short_name="光大",
                    selected_bank_last4="8826",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.selected_bank_short_name, "光大")
        self.assertEqual(preview_file.detected_bank_name, "光大银行")
        self.assertEqual(preview_file.detected_last4, "8826")
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertIsNone(preview_file.conflict_message)

    def test_preview_does_not_mark_bank_legal_name_as_conflict_when_last4_matches(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=CEB_JAN.name,
                    content=CEB_JAN.content,
                    selected_bank_mapping_id="bank_mapping_ceb_8826",
                    selected_bank_name="中国光大银行股份有限公司",
                    selected_bank_last4="8826",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.detected_bank_name, "光大银行")
        self.assertEqual(preview_file.detected_last4, "8826")
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertIsNone(preview_file.conflict_message)

    def test_preview_does_not_detect_icbc_last4_from_filename(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = icbc_history_file(name="historydetail1410.xlsx")

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=upload.name,
                    content=upload.content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "icbc_historydetail")
        self.assertEqual(preview_file.detected_bank_name, "工商银行")
        self.assertIsNone(preview_file.detected_last4)
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertIsNone(preview_file.conflict_message)

    def test_preview_uses_selected_bank_account_when_icbc_file_has_no_account(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = icbc_history_file(name="historydetail1410.xlsx")

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=upload.name,
                    content=upload.content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.success_count, 1)
        self.assertEqual(preview_file.error_count, 0)
        self.assertIsNone(preview_file.detected_last4)
        self.assertEqual(preview_file.normalized_rows[0]["account_no"], "bank_mapping_icbc_6386")
        self.assertEqual(preview_file.normalized_rows[0]["imported_bank_last4"], "6386")

    def test_preview_files_audit_counts_cross_file_invoice_duplicates(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        jan_upload = invoice_export_file("jan.xlsx")
        feb_upload = invoice_export_file("feb.xlsx")

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(file_name=jan_upload.name, content=jan_upload.content),
                UploadedImportFile(file_name=feb_upload.name, content=feb_upload.content),
            ],
        )

        self.assertEqual(session.audit.original_count, 2)
        self.assertEqual(session.audit.unique_count, 1)
        self.assertEqual(session.audit.duplicate_across_files_count, 1)
        self.assertEqual(session.audit.duplicate_count, 1)
        self.assertEqual(session.audit.importable_count, 1)
        self.assertEqual(len(session.duplicate_groups), 1)
        self.assertEqual(session.duplicate_groups[0].duplicate_type, "duplicate_across_files")
        self.assertEqual(session.files[0].audit.importable_count, 1)
        self.assertEqual(session.files[1].audit.duplicate_across_files_count, 1)

    def test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = invoice_export_file("large-invoice-duplicates.xlsx")
        content = repeat_last_xlsx_row(upload.content, total_data_rows=240)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=upload.name, content=content)],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.row_count, 240)
        self.assertEqual(preview_file.success_count, 240)
        self.assertEqual(preview_file.error_count, 0)
        self.assertEqual(session.audit.original_count, 240)
        self.assertEqual(session.audit.unique_count, 1)
        self.assertEqual(session.audit.duplicate_in_file_count, 239)
        self.assertEqual(session.audit.duplicate_across_files_count, 0)
        self.assertEqual(session.audit.importable_count, 1)
        self.assertEqual(session.audit.confirmable_count, 1)
        self.assertEqual(session.audit.skipped_count, 239)
        self.assertEqual(preview_file.audit.duplicate_in_file_count, 239)
        self.assertEqual(len(session.duplicate_groups), 1)
        duplicate_group = session.duplicate_groups[0]
        self.assertEqual(duplicate_group.record_type, "invoice")
        self.assertEqual(duplicate_group.duplicate_type, "duplicate_in_file")
        self.assertEqual(len(duplicate_group.rows), 240)
        self.assertEqual(duplicate_group.rows[-1]["row_no"], 240)

    def test_preview_files_audit_counts_cross_file_bank_transaction_identity_duplicates(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        jan_upload = icbc_history_file(name="historydetail-jan.xlsx")
        feb_upload = icbc_history_file(name="historydetail-feb.xlsx")

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=jan_upload.name,
                    content=jan_upload.content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                ),
                UploadedImportFile(
                    file_name=feb_upload.name,
                    content=feb_upload.content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                ),
            ],
        )

        self.assertEqual(session.audit.original_count, 2)
        self.assertEqual(session.audit.unique_count, 1)
        self.assertEqual(session.audit.duplicate_across_files_count, 1)
        self.assertEqual(session.audit.duplicate_count, 1)
        self.assertEqual(session.audit.importable_count, 1)
        self.assertEqual(session.audit.skipped_count, 1)
        self.assertEqual(len(session.duplicate_groups), 1)
        self.assertEqual(session.duplicate_groups[0].record_type, "bank_transaction")
        self.assertEqual(session.duplicate_groups[0].duplicate_type, "duplicate_across_files")
        duplicate_row = session.duplicate_groups[0].rows[1]
        self.assertEqual(duplicate_row["file_name"], "historydetail-feb.xlsx")
        self.assertEqual(duplicate_row["identity_kind"], "stable")
        self.assertEqual(duplicate_row["decision"], "created")
        self.assertEqual(duplicate_row["account_no"], "bank_mapping_icbc_6386")
        self.assertEqual(duplicate_row["trade_time"], "2026-01-03 09:12:00")
        self.assertEqual(duplicate_row["direction"], "outflow")
        self.assertEqual(duplicate_row["amount"], "6180.00")
        self.assertEqual(duplicate_row["counterparty_name"], "重庆高新技术产业开发区国家税务局")
        self.assertEqual(session.files[0].audit.importable_count, 1)
        self.assertEqual(session.files[1].audit.duplicate_across_files_count, 1)

    def test_preview_bounds_large_bank_duplicate_group_to_one_confirmable_row(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = icbc_history_file(name="large-historydetail.xlsx", account_no="6222020200006386")
        content = repeat_last_xlsx_row(upload.content, total_data_rows=240)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=upload.name,
                    content=content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.row_count, 240)
        self.assertEqual(preview_file.success_count, 240)
        self.assertEqual(preview_file.error_count, 0)
        self.assertEqual(session.audit.original_count, 240)
        self.assertEqual(session.audit.unique_count, 1)
        self.assertEqual(session.audit.duplicate_in_file_count, 239)
        self.assertEqual(session.audit.duplicate_across_files_count, 0)
        self.assertEqual(session.audit.importable_count, 1)
        self.assertEqual(session.audit.confirmable_count, 1)
        self.assertEqual(session.audit.skipped_count, 239)
        self.assertEqual(preview_file.audit.duplicate_in_file_count, 239)
        self.assertEqual(len(session.duplicate_groups), 1)
        duplicate_group = session.duplicate_groups[0]
        self.assertEqual(duplicate_group.record_type, "bank_transaction")
        self.assertEqual(duplicate_group.duplicate_type, "duplicate_in_file")
        self.assertEqual(len(duplicate_group.rows), 240)
        self.assertEqual(duplicate_group.rows[-1]["row_no"], 240)
        self.assertEqual(duplicate_group.rows[-1]["account_no"], "6222020200006386")
        self.assertEqual(duplicate_group.rows[-1]["direction"], "outflow")
        self.assertEqual(duplicate_group.rows[-1]["amount"], "6180.00")

    def test_confirm_session_rejects_stale_preview_when_existing_records_change(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = invoice_export_file("jan.xlsx")
        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=upload.name, content=upload.content)],
        )
        competing_preview = import_service.preview_import(
            batch_type=session.files[0].batch_type,
            source_name="competing.json",
            imported_by="user_finance_02",
            rows=[session.files[0].row_results[0].raw_payload],
        )
        import_service.confirm_import(competing_preview.id)

        with self.assertRaisesRegex(ValueError, "preview_stale"):
            service.confirm_session(session_id=session.id, selected_file_ids=[session.files[0].id])

    def test_preview_detects_icbc_last4_from_explicit_file_account(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)
        upload = icbc_history_file(name="historydetail1410.xlsx", account_no="6222020200006386")

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=upload.name,
                    content=upload.content,
                    selected_bank_mapping_id="bank_mapping_icbc_6386",
                    selected_bank_name="工商银行",
                    selected_bank_short_name="工行",
                    selected_bank_last4="6386",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "icbc_historydetail")
        self.assertEqual(preview_file.detected_bank_name, "工商银行")
        self.assertEqual(preview_file.detected_last4, "6386")
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertIsNone(preview_file.conflict_message)

    def test_preview_accepts_ceb_xlsx_statement_with_yuan_amount_headers(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["中国光大银行对公账户对账单"])
        sheet.append(["查询日期：2026-04-24 11:19:56"])
        sheet.append(["交易日期：20260101-20260423", "", "借贷方向：全部"])
        sheet.append(["账号：39610188000598826", "", "账户名称：云南溯源科技有限公司"])
        sheet.append(["借方笔数：1", "", "借方发生额汇总：23,053.31"])
        sheet.append(["贷方笔数：0", "", "贷方发生额汇总：0.00"])
        sheet.append(["交易日期", "交易时间", "借方发生额（元）", "贷方发生额（元）", "账户余额（元）", "对方账号", "对方名称", "摘要"])
        sheet.append(["2026-04-23", "11:18:17", "23,053.31", "", "3,518.86", "2502046609100018276", "云南辰飞机电工程有限公司", "货款"])
        buffer = BytesIO()
        workbook.save(buffer)
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name="光大银行EXCEL账户明细_39610188000598826_20260101-20260423_260424111837.xlsx",
                    content=buffer.getvalue(),
                    selected_bank_mapping_id="bank_mapping_ceb_8826",
                    selected_bank_name="光大银行",
                    selected_bank_short_name="光大",
                    selected_bank_last4="8826",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "ceb_transaction_detail")
        self.assertEqual(preview_file.detected_bank_name, "光大银行")
        self.assertEqual(preview_file.detected_last4, "8826")
        self.assertEqual(preview_file.row_count, 1)
        self.assertEqual(preview_file.success_count, 1)
        self.assertFalse(preview_file.bank_selection_conflict)

    def test_preview_accepts_bocom_transaction_detail_statement(self) -> None:
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[
                UploadedImportFile(
                    file_name=BOCOM_JAN.name,
                    content=BOCOM_JAN.content,
                    selected_bank_mapping_id="bank_mapping_bocom_3847",
                    selected_bank_name="交通银行",
                    selected_bank_short_name="交行",
                    selected_bank_last4="3847",
                )
            ],
        )

        preview_file = session.files[0]
        self.assertEqual(preview_file.status, "preview_ready")
        self.assertEqual(preview_file.template_code, "bocom_transaction_detail")
        self.assertEqual(preview_file.batch_type.value, "bank_transaction")
        self.assertEqual(preview_file.detected_bank_name, "交通银行")
        self.assertEqual(preview_file.detected_last4, "3847")
        self.assertEqual(preview_file.row_count, 2)
        self.assertEqual(preview_file.success_count, 2)
        self.assertEqual(preview_file.error_count, 0)
        self.assertFalse(preview_file.bank_selection_conflict)
        self.assertEqual(preview_file.normalized_rows[0]["account_no"], "531899991015003383847")
        self.assertEqual(preview_file.normalized_rows[0]["account_name"], "云南溯源科技有限公司")


if __name__ == "__main__":
    unittest.main()
