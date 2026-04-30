from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import Workbook

from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile, is_company_identity
from fin_ops_platform.services.imports import ImportNormalizationService
from tests.mock_import_files import CEB_JAN, INVOICE_JAN, PINGAN_JAN


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


if __name__ == "__main__":
    unittest.main()
