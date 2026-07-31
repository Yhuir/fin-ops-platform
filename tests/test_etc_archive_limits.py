from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from fin_ops_platform.services.etc_service import EtcService


def archive(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as output:
        for name, content in entries.items():
            output.writestr(name, content)
    return buffer.getvalue()


class EtcArchiveLimitTests(unittest.TestCase):
    def test_rejects_path_traversal_before_extracting_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))

            with self.assertRaisesRegex(BadZipFile, "unsafe archive path"):
                service._extract_archive_entries("unsafe.zip", archive({"../invoice.xml": b"x"}))

    def test_rejects_entry_count_and_total_uncompressed_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            content = archive({"a.xml": b"1234", "b.xml": b"5678"})

            with patch("fin_ops_platform.services.etc_service.MAX_ARCHIVE_ENTRIES", 1):
                with self.assertRaisesRegex(BadZipFile, "entry count"):
                    service._extract_archive_entries("many.zip", content)
            with patch("fin_ops_platform.services.etc_service.MAX_ARCHIVE_TOTAL_UNCOMPRESSED_BYTES", 7):
                with self.assertRaisesRegex(BadZipFile, "total uncompressed size"):
                    service._extract_archive_entries("large.zip", content)

    def test_rejects_nested_depth_and_extreme_compression_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = EtcService(data_dir=Path(temp_dir))
            nested = archive({"nested.zip": archive({"invoice.xml": b"x"})})

            with patch("fin_ops_platform.services.etc_service.MAX_ARCHIVE_DEPTH", 0):
                with self.assertRaisesRegex(BadZipFile, "nested zip depth"):
                    service._extract_archive_entries("nested.zip", nested)
            compressed = archive({"invoice.xml": b"0" * 10_000})
            with patch("fin_ops_platform.services.etc_service.MAX_ARCHIVE_COMPRESSION_RATIO", 2):
                with self.assertRaisesRegex(BadZipFile, "compression ratio"):
                    service._extract_archive_entries("compressed.zip", compressed)


if __name__ == "__main__":
    unittest.main()
