from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bson.binary import Binary

from fin_ops_platform.tools.export_manifest import ExportSerializationError, NdjsonWriter, safe_jsonable, sha256_file


class DemoEnum(Enum):
    READY = "ready"


class MongoExportManifestTests(unittest.TestCase):
    def test_safe_jsonable_preserves_decimal_and_temporal_types_without_float(self) -> None:
        payload = safe_jsonable(
            {
                "amount": Decimal("1.20"),
                "day": date(2026, 5, 20),
                "at": datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
                "status": DemoEnum.READY,
                "path": Path("/tmp/demo"),
            }
        )

        self.assertEqual(payload["amount"], "1.20")
        self.assertEqual(payload["day"], "2026-05-20")
        self.assertEqual(payload["at"], "2026-05-20T08:30:00+00:00")
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["path"], "/tmp/demo")

    def test_safe_jsonable_serializes_finite_float_as_string_and_rejects_binary(self) -> None:
        self.assertEqual(safe_jsonable({"amount": 1.2})["amount"], "1.2")
        with self.assertRaises(ExportSerializationError):
            safe_jsonable({"amount": float("nan")})
        with self.assertRaises(ExportSerializationError):
            safe_jsonable({"payload": b"raw"})
        with self.assertRaises(ExportSerializationError):
            safe_jsonable({"payload": Binary(b"raw")})
        self.assertEqual(
            safe_jsonable({"created_at": datetime(2026, 5, 20, 8, 30)})["created_at"],
            "2026-05-20T08:30:00+00:00",
        )

    def test_ndjson_writer_writes_single_line_and_tracks_checksum(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "records.ndjson"
            writer = NdjsonWriter(output)
            writer.write({"id": "row-1", "amount": Decimal("12.30")})
            result = writer.close()

            lines = output.read_text(encoding="utf-8").splitlines()
            actual_sha = sha256_file(result.path)

        self.assertEqual(lines, ['{"id":"row-1","amount":"12.30"}'])
        self.assertEqual(result.record_count, 1)
        self.assertEqual(result.sha256, actual_sha)
