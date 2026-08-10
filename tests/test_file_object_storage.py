from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.object_storage import InMemoryObjectStorageRepository, ObjectStorageWriteError
from fin_ops_platform.services.postgres_state_store import PostgresStateStore


def unwrap_jsonb(value):
    return getattr(value, "obj", value)


class FileObjectConnection:
    def __init__(self) -> None:
        self.file_objects: dict[str, dict] = {}
        self.import_files: dict[str, dict] = {}
        self.executed: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "insert into app.file_objects" in normalized:
            legacy_id = str(params[0])
            row = self.file_objects.setdefault("file-object-1", {"id": "file-object-1", "legacy_mongo_id": legacy_id})
            row.update(
                {
                    "legacy_mongo_id": legacy_id,
                    "legacy_gridfs_id": params[1],
                    "storage_backend": params[2],
                    "storage_uri": params[3],
                    "bucket_name": params[4],
                    "object_key": params[5],
                    "filename": params[6],
                    "sha256": params[7],
                    "size_bytes": params[8],
                    "content_type": params[9],
                    "etag": params[10],
                    "migration_status": params[11],
                    "temporary_object_key": params[12],
                    "source_storage_backend": params[13],
                    "source_storage_uri": params[14],
                    "last_error": params[15],
                    "raw_payload": unwrap_jsonb(params[16]),
                }
            )
            return {"id": row["id"]}
        if "select id::text" in normalized and "from app.file_objects" in normalized:
            storage_uri = str(params[0])
            for row in self.file_objects.values():
                if row.get("storage_uri") == storage_uri:
                    return dict(row)
            return None
        return None

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "insert into app.import_files" in normalized:
            self.import_files[str(params[0])] = {
                "legacy_mongo_id": params[0],
                "session_id": params[1],
                "stored_file_path": params[2],
                "original_filename": params[3],
                "file_object_id": params[4],
                "uploaded_by": params[5],
                "raw_payload": unwrap_jsonb(params[6]),
            }
            return 1
        if "update app.file_objects" in normalized and "migration_status = 'failed'" in normalized:
            row = self.file_objects.get(str(params[-1]))
            if row:
                row["migration_status"] = "failed"
                row["last_error"] = params[0]
            return 1
        if "update app.file_objects" in normalized and "migration_status = 'verified'" in normalized:
            row = self.file_objects.get(str(params[-1]))
            if row:
                updates = {
                    "storage_backend": params[0],
                    "storage_uri": params[1],
                    "bucket_name": params[2],
                    "object_key": params[3],
                    "etag": params[4],
                    "migration_status": "verified",
                    "temporary_object_key": None,
                    "last_error": None,
                }
                if "source_storage_backend = 'gridfs_legacy'" in normalized:
                    updates["sha256"] = params[5]
                    updates["size_bytes"] = params[6]
                row.update(updates)
            return 1
        if "update app.import_files set status = 'deleted'" in normalized:
            return 1
        return 1


class FailingObjectStorageRepository(InMemoryObjectStorageRepository):
    def put_object(self, object_key, body, *, content_type=None):  # type: ignore[override]
        raise RuntimeError("object storage unavailable")


class FileObjectStorageTests(unittest.TestCase):
    def test_postgres_import_upload_writes_verified_object_and_reads_only_object_storage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FileObjectConnection()
            object_store = InMemoryObjectStorageRepository(bucket="fin-ops-files", backend="minio")
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection, object_storage_repository=object_store)

            stored_uri = store.store_import_file(
                session_id="session-1",
                file_id="file-1",
                file_name="bank.xlsx",
                content=b"file-bytes",
                imported_by="YNSYLP005",
            )

            self.assertTrue(stored_uri.startswith("minio://fin-ops-files/objects/imports/file-1/"))
            self.assertEqual(store.read_import_file(stored_uri), b"file-bytes")
            self.assertEqual(connection.file_objects["file-object-1"]["migration_status"], "verified")
            self.assertEqual(connection.import_files["file-1"]["stored_file_path"], stored_uri)
            self.assertEqual(connection.import_files["file-1"]["uploaded_by"], "YNSYLP005")
            self.assertEqual(
                connection.import_files["file-1"]["raw_payload"]["normalized_payload"]["imported_by"],
                "YNSYLP005",
            )
            self.assertFalse((Path(temp_dir) / "postgres_files").exists())

    def test_postgres_import_upload_fails_fast_and_marks_file_object_failed_when_object_storage_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FileObjectConnection()
            store = PostgresStateStore(
                data_dir=Path(temp_dir),
                connection=connection,
                object_storage_repository=FailingObjectStorageRepository(bucket="fin-ops-files", backend="minio"),
            )

            with self.assertRaisesRegex(ObjectStorageWriteError, "object storage unavailable"):
                store.store_import_file(
                    session_id="session-1",
                    file_id="file-1",
                    file_name="bank.xlsx",
                    content=b"file-bytes",
                )

            self.assertEqual(connection.file_objects["file-object-1"]["migration_status"], "failed")

    def test_verified_object_read_rejects_unverified_metadata_without_legacy_fallback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            connection = FileObjectConnection()
            object_store = InMemoryObjectStorageRepository(bucket="fin-ops-files", backend="minio")
            store = PostgresStateStore(data_dir=Path(temp_dir), connection=connection, object_storage_repository=object_store)
            stored_uri = store.store_import_file(
                session_id="session-1",
                file_id="file-1",
                file_name="bank.xlsx",
                content=b"file-bytes",
            )
            connection.file_objects["file-object-1"]["migration_status"] = "pending_upload"

            with self.assertRaisesRegex(RuntimeError, "verified"):
                store.read_import_file(stored_uri)


if __name__ == "__main__":
    unittest.main()
