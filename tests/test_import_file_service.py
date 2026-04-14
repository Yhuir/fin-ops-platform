from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.imports import ImportNormalizationService


ROOT = Path(__file__).resolve().parents[1]
INVOICE_JAN = ROOT / "fixtures" / "发票信息导出1-3月" / "全量发票查询导出结果-2026年1月.xlsx"


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
    def test_preview_skips_existing_session_file_and_batch_ids_when_counters_restart(self) -> None:
        file_store = FakeImportIdStore()
        import_service = ImportNormalizationService(id_registry=FakeImportEntityRegistry())
        service = FileImportService(import_service, file_store=file_store)

        session = service.preview_files(
            imported_by="user_finance_01",
            uploads=[UploadedImportFile(file_name=INVOICE_JAN.name, content=INVOICE_JAN.read_bytes())],
        )

        self.assertEqual(session.id, "import_session_0003")
        self.assertEqual(session.files[0].id, "import_file_0003")
        self.assertEqual(session.files[0].preview_batch_id, "batch_import_0002")
        self.assertEqual(session.files[0].status, "preview_ready")
        self.assertTrue(session.files[0].stored_file_path)


if __name__ == "__main__":
    unittest.main()
