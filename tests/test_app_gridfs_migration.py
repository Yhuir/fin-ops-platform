from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.services.app_gridfs_migration import (
    AppGridFSToObjectStorageMigrator,
    InMemoryObjectStorageClient,
)
from fin_ops_platform.services.state_store import ApplicationStateStore, GRIDFS_BUCKET_NAME
from tests.test_state_store import FakeGridFSBucket, FakeMongoClient


def _build_store_with_gridfs_file(
    data_dir: Path,
    *,
    file_id: str = "import_file_0001",
    filename: str = "供应商银行流水明细.xlsx",
    content: bytes = b"bank rows",
    metadata: dict | None = None,
) -> tuple[ApplicationStateStore, FakeMongoClient]:
    (data_dir / "app_mongo_config.json").write_text(
        json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
        encoding="utf-8",
    )
    fake_client = FakeMongoClient()
    patchers = [
        patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client),
        patch(
            "fin_ops_platform.services.state_store.GridFSBucket",
            side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
        ),
    ]
    for patcher in patchers:
        patcher.start()
    try:
        store = ApplicationStateStore(data_dir)
    finally:
        for patcher in reversed(patchers):
            patcher.stop()

    db = fake_client["fin_ops_platform_app"]
    db.gridfs_buckets.setdefault(GRIDFS_BUCKET_NAME, {})[file_id] = {
        "_id": file_id,
        "filename": filename,
        "content": content,
        "metadata": dict(metadata or {}),
    }
    db[f"{GRIDFS_BUCKET_NAME}.files"].documents[file_id] = {
        "_id": file_id,
        "filename": filename,
        "length": len(content),
        "chunkSize": 255,
        "uploadDate": "2026-05-16T00:00:00+00:00",
        "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "metadata": dict(metadata or {}),
    }
    db[f"{GRIDFS_BUCKET_NAME}.chunks"].documents[f"{file_id}:0"] = {
        "_id": f"{file_id}:0",
        "files_id": file_id,
    }
    return store, fake_client


class AppGridFSToObjectStorageMigratorTests(unittest.TestCase):
    def test_dry_run_builds_secret_free_manifest_without_uploading_objects(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "gridfs-report"
            data_dir.mkdir()
            store, _ = _build_store_with_gridfs_file(data_dir, metadata={"session_id": "session-1"})
            storage = InMemoryObjectStorageClient()

            result = AppGridFSToObjectStorageMigrator(store, storage).migrate(
                bucket="fin-ops-files",
                environment="dryrun",
                output_dir=output_dir,
                dry_run=True,
                sample_size=1,
            )

            self.assertEqual(result.manifest["status"], "passed")
            self.assertEqual(result.manifest["summary"]["total_files"], 1)
            self.assertEqual(result.manifest["summary"]["uploaded"], 0)
            self.assertEqual(storage.put_calls, [])
            file_entry = result.manifest["files"][0]
            self.assertEqual(file_entry["legacy_gridfs_id"], "import_file_0001")
            self.assertEqual(file_entry["purpose"], "import_source_file")
            self.assertNotIn("供应商", file_entry["object_key"])
            self.assertTrue((output_dir / "gridfs-object-mapping.ndjson").exists())
            self.assertTrue((output_dir / "file-objects-import.ndjson").exists())

    def test_execute_uploads_file_and_validates_sample_download_checksum(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "gridfs-report"
            data_dir.mkdir()
            store, _ = _build_store_with_gridfs_file(
                data_dir,
                file_id="etc_reconciliation:task-1:file-1",
                filename="card statement.pdf",
                content=b"statement",
                metadata={"purpose": "etc_reconciliation_source"},
            )
            storage = InMemoryObjectStorageClient()

            result = AppGridFSToObjectStorageMigrator(store, storage).migrate(
                bucket="fin-ops-files",
                environment="staging",
                output_dir=output_dir,
                dry_run=False,
                sample_size=1,
            )

            self.assertEqual(result.manifest["status"], "passed")
            self.assertEqual(result.manifest["summary"]["uploaded"], 1)
            self.assertEqual(result.manifest["summary"]["checksum_samples"]["matched"], 1)
            self.assertEqual(len(storage.put_calls), 1)
            mapping = json.loads((output_dir / "gridfs-object-mapping.ndjson").read_text(encoding="utf-8"))
            self.assertEqual(mapping["legacy_gridfs_id"], "etc_reconciliation:task-1:file-1")
            self.assertEqual(mapping["target_table"], "app.file_objects")
            self.assertIn("import_file_id", mapping)
            checksum_report = json.loads(
                (output_dir / "gridfs-checksum-validation-report.json").read_text(encoding="utf-8")
            )
            self.assertEqual(checksum_report["readiness_gates"]["file_checksum"]["decision"], "GO")
            self.assertEqual(checksum_report["coverage"]["manifest_checksum"]["status"], "covered")
            self.assertEqual(checksum_report["coverage"]["sample_download_hash"]["matched"], 1)
            self.assertEqual(checksum_report["coverage"]["missing_files"]["count"], 0)
            self.assertEqual(checksum_report["coverage"]["duplicate_files"]["count"], 0)
            self.assertEqual(checksum_report["coverage"]["size_differences"]["count"], 0)

    def test_existing_object_with_same_checksum_is_skipped_without_upload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "gridfs-report"
            data_dir.mkdir()
            content = b"already uploaded"
            store, _ = _build_store_with_gridfs_file(data_dir, content=content)
            storage = InMemoryObjectStorageClient()
            first = AppGridFSToObjectStorageMigrator(store, storage).migrate(
                bucket="fin-ops-files",
                environment="staging",
                output_dir=output_dir,
                dry_run=False,
                sample_size=1,
            )
            storage.put_calls.clear()

            second = AppGridFSToObjectStorageMigrator(store, storage).migrate(
                bucket="fin-ops-files",
                environment="staging",
                output_dir=Path(temp_dir) / "gridfs-report-2",
                dry_run=False,
                sample_size=1,
            )

        self.assertEqual(first.manifest["summary"]["uploaded"], 1)
        self.assertEqual(second.manifest["summary"]["skipped_existing"], 1)
        self.assertEqual(storage.put_calls, [])

    def test_checksum_sample_mismatch_blocks_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "gridfs-report"
            data_dir.mkdir()
            store, _ = _build_store_with_gridfs_file(data_dir, content=b"expected content")
            storage = InMemoryObjectStorageClient(corrupt_downloads=True)

            result = AppGridFSToObjectStorageMigrator(store, storage).migrate(
                bucket="fin-ops-files",
                environment="staging",
                output_dir=output_dir,
                dry_run=False,
                sample_size=1,
            )

        self.assertEqual(result.manifest["status"], "failed")
        self.assertTrue(result.manifest["blocking"])
        self.assertEqual(result.manifest["summary"]["checksum_samples"]["mismatched"], 1)
        self.assertEqual(result.manifest["findings"][0]["code"], "FILE_CHECKSUM_MISMATCH")

    def test_failed_file_entries_preserve_structured_reason(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "gridfs-report"
            data_dir.mkdir()
            store, _ = _build_store_with_gridfs_file(data_dir, file_id="missing-gridfs-file")
            del store._mongo_database.gridfs_buckets[GRIDFS_BUCKET_NAME]["missing-gridfs-file"]  # noqa: SLF001

            result = AppGridFSToObjectStorageMigrator(store, InMemoryObjectStorageClient()).migrate(
                bucket="fin-ops-files",
                environment="staging",
                output_dir=output_dir,
                dry_run=False,
                sample_size=1,
            )

            failed = result.manifest["files"][0]
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["failure_reason"]["code"], "GRIDFS_READ_ERROR")
            self.assertIn("exception_type", failed["failure_reason"])
            failures = (output_dir / "gridfs-migration-failures.ndjson").read_text(encoding="utf-8")
            self.assertIn("GRIDFS_READ_ERROR", failures)


if __name__ == "__main__":
    unittest.main()
