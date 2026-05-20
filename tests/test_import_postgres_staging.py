from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.postgres.migrate import MigrationError
from fin_ops_platform.tools.export_manifest import NdjsonWriter, safe_jsonable, sha256_file, write_json
from fin_ops_platform.tools.import_postgres_staging import import_postgres_staging


def create_export_dir(root: Path) -> Path:
    export_dir = root / "unit-export"
    export_dir.mkdir()
    writer = NdjsonWriter(export_dir / "invoices.ndjson")
    writer.write(
        {
            "export_id": "unit-export",
            "source_collection": "invoices",
            "legacy_mongo_id": "invoice-1",
            "record_type": "invoice",
            "normalized_payload": {"invoice_no": "001"},
            "raw_payload": {},
        }
    )
    file_result = writer.close()
    manifest = {
        "export_id": "unit-export",
        "created_at": datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
        "completed_at": datetime(2026, 5, 20, 8, 31, tzinfo=UTC),
        "status": "completed",
        "source_mode": "restore",
        "source_database": "fin_ops_platform_app_restore_20260520013830",
        "app_backup_archive": "/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz",
        "app_backup_sha256": "c25d9780fded4c4407c29df16796fec2c99d63d201e24daf53ccab98e23f8b48",
        "files": {
            file_result.path.name: {
                "record_count": file_result.record_count,
                "bytes": file_result.bytes,
                "sha256": file_result.sha256,
            }
        },
        "counts": {"invoice": 1},
        "total_records": 1,
        "gridfs": {"files_count": 0, "chunks_count": 0, "total_bytes": 0, "sampled_checksums": []},
        "warnings": [],
        "errors": [],
    }
    write_json(export_dir / "manifest.json", manifest)
    manifest["manifest_sha256"] = sha256_file(export_dir / "manifest.json")
    write_json(export_dir / "manifest.json", manifest)
    return export_dir


class ImportPostgresStagingTests(unittest.TestCase):
    def test_dry_run_validates_manifest_without_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = create_export_dir(Path(temp_dir))

            result = import_postgres_staging(export_dir=export_dir, dry_run=True)

        self.assertEqual(result["export_id"], "unit-export")
        self.assertEqual(result["total_records"], 1)

    def test_checksum_drift_blocks_import(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = create_export_dir(Path(temp_dir))
            (export_dir / "invoices.ndjson").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(MigrationError):
                import_postgres_staging(export_dir=export_dir, dry_run=True)

    def test_repeated_import_with_same_manifest_checksum_skips(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = create_export_dir(Path(temp_dir))
            manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
            calls: list[str] = []

            def fake_run_psql(_database_url: str, *, sql: str) -> str:
                calls.append(sql)
                if "from public.schema_migrations" in sql:
                    return "0001,0002,0003,0004,0005,0006,0007,0008"
                if "from staging.mongo_exports" in sql:
                    return manifest["manifest_sha256"]
                return ""

            with patch("fin_ops_platform.tools.import_postgres_staging.run_psql", side_effect=fake_run_psql):
                result = import_postgres_staging(
                    export_dir=export_dir,
                    database_url="unit-test-dsn",
                    dry_run=False,
                )

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(len(calls), 2)
        self.assertIn("'0008'", calls[0])
