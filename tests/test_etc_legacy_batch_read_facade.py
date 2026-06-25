from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.etc_service import UploadedEtcZipFile
from tests.test_etc_backend import etc_zip


class EtcLegacyBatchReadFacadeTests(unittest.TestCase):
    def test_list_payload_preserves_counts_selected_detail_and_filters(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_zips(
                [UploadedEtcZipFile("batch.zip", etc_zip(["ETC001", "ETC002"]))]
            )
            facade = app._etc_legacy_batch_read_facade()

            payload = facade.list_payload(
                status="unsubmitted",
                month="",
                plate="",
                keyword="",
                page=1,
                page_size=20,
            )
            filtered = facade.list_payload(
                status="unsubmitted",
                month="",
                plate="",
                keyword="ETC001",
                page=1,
                page_size=20,
            )

        self.assertEqual(payload["counts"], {"unsubmitted": 1, "submitted": 0, "current": 1})
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(len(payload["items"]), 1)
        selected = payload["selectedBatch"]
        self.assertIsInstance(selected, dict)
        self.assertEqual(len(selected["invoiceItems"]), 2)
        self.assertEqual(len(payload["invoiceItems"]), 2)
        self.assertEqual(filtered["counts"]["current"], 1)
        self.assertEqual(filtered["pagination"]["total"], 1)
        self.assertEqual(len(filtered["invoiceItems"]), 2)

    def test_detail_payload_returns_none_for_unknown_batch(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            facade = app._etc_legacy_batch_read_facade()

            detail = facade.detail_payload("missing-batch")

        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
