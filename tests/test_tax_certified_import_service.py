from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.tax_certified_import_service import (
    TaxCertifiedImportService,
    UploadedCertifiedImportFile,
)
from tests.mock_import_files import CERTIFIED_FEB, CERTIFIED_JAN


class TaxCertifiedImportServiceTests(unittest.TestCase):
    def test_preview_files_parses_certified_invoice_template_and_filters_certified_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = TaxCertifiedImportService(state_store=store)

            session = service.preview_files(
                imported_by="user_finance_01",
                uploads=[
                    UploadedCertifiedImportFile(
                        file_name=CERTIFIED_JAN.name,
                        content=CERTIFIED_JAN.content,
                    )
                ],
            )

        self.assertEqual(session.file_count, 1)
        self.assertEqual(session.files[0].month, "2026-01")
        self.assertEqual(session.files[0].recognized_count, 2)
        self.assertEqual(session.files[0].invalid_count, 1)
        self.assertEqual(session.files[0].rows[0].invoice_no, "45098656")
        self.assertEqual(session.files[0].rows[0].digital_invoice_no, "25502000000145098656")
        self.assertEqual(session.files[0].rows[0].seller_tax_no, "91500226MA60KH3C0Q")
        self.assertEqual(session.files[0].rows[0].selection_status, "已勾选")
        self.assertEqual(session.files[0].rows[0].invoice_status, "正常")

    def test_confirm_session_persists_month_records_and_deduplicates_reimport(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = TaxCertifiedImportService(state_store=store)

            first_session = service.preview_files(
                imported_by="user_finance_01",
                uploads=[
                    UploadedCertifiedImportFile(file_name=CERTIFIED_JAN.name, content=CERTIFIED_JAN.content),
                    UploadedCertifiedImportFile(file_name=CERTIFIED_FEB.name, content=CERTIFIED_FEB.content),
                ],
            )
            first_batch = service.confirm_session(first_session.id)

            reimport_session = service.preview_files(
                imported_by="user_finance_01",
                uploads=[
                    UploadedCertifiedImportFile(file_name=CERTIFIED_JAN.name, content=CERTIFIED_JAN.content),
                ],
            )
            second_batch = service.confirm_session(reimport_session.id)

            january_records = service.list_records_for_month("2026-01")
            february_records = service.list_records_for_month("2026-02")

            reloaded_service = TaxCertifiedImportService(state_store=store)
            january_records_reloaded = reloaded_service.list_records_for_month("2026-01")

        self.assertEqual(first_batch.months, ["2026-01", "2026-02"])
        self.assertEqual(first_batch.persisted_record_count, 3)
        self.assertEqual(second_batch.months, ["2026-01"])
        self.assertEqual(second_batch.persisted_record_count, 2)
        self.assertEqual(len(january_records), 2)
        self.assertEqual(len(february_records), 1)
        self.assertEqual(len(january_records_reloaded), 2)
        self.assertEqual(january_records[0].month, "2026-01")
        self.assertTrue(all(record.unique_key for record in january_records))


if __name__ == "__main__":
    unittest.main()
