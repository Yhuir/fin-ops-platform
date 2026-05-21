from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.object_storage import InMemoryObjectStorageRepository, ObjectStorageWriteError
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


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

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.file_objects" in normalized and "legacy_gridfs_id" in normalized:
            statuses = {"legacy", "failed", "pending_upload"}
            rows = [
                dict(row)
                for row in self.file_objects.values()
                if row.get("legacy_gridfs_id")
                and row.get("storage_uri", "").startswith("gridfs://")
                and row.get("migration_status") in statuses
            ]
            return rows[: int(params[0])]
        return []

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
                "raw_payload": unwrap_jsonb(params[5]),
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


class LegacyReader:
    def __init__(self, payloads: dict[str, bytes]) -> None:
        self.payloads = payloads
        self.reads: list[str] = []

    def read(self, stored_file_path: str) -> bytes:
        self.reads.append(stored_file_path)
        return self.payloads[stored_file_path]


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
            )

            self.assertTrue(stored_uri.startswith("minio://fin-ops-files/objects/imports/file-1/"))
            self.assertEqual(store.read_import_file(stored_uri), b"file-bytes")
            self.assertEqual(connection.file_objects["file-object-1"]["migration_status"], "verified")
            self.assertEqual(connection.import_files["file-1"]["stored_file_path"], stored_uri)
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

    def test_gridfs_migration_is_idempotent_and_verifies_checksum(self) -> None:
        connection = FileObjectConnection()
        connection.file_objects["legacy-row"] = {
            "id": "legacy-row",
            "legacy_mongo_id": "file-legacy",
            "legacy_gridfs_id": "gridfs-id-1",
            "storage_backend": "gridfs_legacy",
            "storage_uri": "gridfs://import_file_blobs/gridfs-id-1",
            "filename": "legacy.xlsx",
            "sha256": "dceda2dd1ec30247f7dc9a1239285488631c9594a320e5ec4c5a554cd7e42d26",
            "size_bytes": 12,
            "migration_status": "legacy",
        }
        object_store = InMemoryObjectStorageRepository(bucket="fin-ops-files", backend="minio")
        reader = LegacyReader({"gridfs://import_file_blobs/gridfs-id-1": b"legacy-bytes"})
        service = GridFSObjectMigrationService(connection=connection, object_storage_repository=object_store, legacy_file_reader=reader)

        first = service.migrate_batch(limit=10)
        second = service.migrate_batch(limit=10)

        self.assertEqual(first["migrated"], 1)
        self.assertEqual(second["migrated"], 0)
        self.assertEqual(reader.reads, ["gridfs://import_file_blobs/gridfs-id-1"])
        self.assertEqual(connection.file_objects["legacy-row"]["migration_status"], "verified")
        self.assertEqual(
            connection.file_objects["legacy-row"]["sha256"],
            "dceda2dd1ec30247f7dc9a1239285488631c9594a320e5ec4c5a554cd7e42d26",
        )
        self.assertEqual(connection.file_objects["legacy-row"]["size_bytes"], 12)
        self.assertEqual(object_store.get_object(connection.file_objects["legacy-row"]["object_key"]), b"legacy-bytes")

    def test_gridfs_migration_backfills_missing_checksum_metadata(self) -> None:
        connection = FileObjectConnection()
        connection.file_objects["legacy-row"] = {
            "id": "legacy-row",
            "legacy_mongo_id": "file-legacy",
            "legacy_gridfs_id": "gridfs-id-1",
            "storage_backend": "gridfs_legacy",
            "storage_uri": "gridfs://import_file_blobs/gridfs-id-1",
            "filename": "legacy.xlsx",
            "sha256": None,
            "size_bytes": None,
            "migration_status": "legacy",
        }
        service = GridFSObjectMigrationService(
            connection=connection,
            object_storage_repository=InMemoryObjectStorageRepository(bucket="fin-ops-files", backend="minio"),
            legacy_file_reader=LegacyReader({"gridfs://import_file_blobs/gridfs-id-1": b"legacy-bytes"}),
        )

        result = service.migrate_batch(limit=10)

        self.assertEqual(result["migrated"], 1)
        self.assertEqual(
            connection.file_objects["legacy-row"]["sha256"],
            "dceda2dd1ec30247f7dc9a1239285488631c9594a320e5ec4c5a554cd7e42d26",
        )
        self.assertEqual(connection.file_objects["legacy-row"]["size_bytes"], 12)

    def test_gridfs_migration_handler_processes_runtime_worker_event(self) -> None:
        connection = FileObjectConnection()
        connection.file_objects["legacy-row"] = {
            "id": "legacy-row",
            "legacy_mongo_id": "file-legacy",
            "legacy_gridfs_id": "gridfs-id-1",
            "storage_backend": "gridfs_legacy",
            "storage_uri": "gridfs://import_file_blobs/gridfs-id-1",
            "filename": "legacy.xlsx",
            "sha256": "dceda2dd1ec30247f7dc9a1239285488631c9594a320e5ec4c5a554cd7e42d26",
            "size_bytes": 12,
            "migration_status": "legacy",
        }
        service = GridFSObjectMigrationService(
            connection=connection,
            object_storage_repository=InMemoryObjectStorageRepository(bucket="fin-ops-files", backend="minio"),
            legacy_file_reader=LegacyReader({"gridfs://import_file_blobs/gridfs-id-1": b"legacy-bytes"}),
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="file_object.gridfs_migration",
            aggregate_type=None,
            aggregate_id=None,
            scope_type=None,
            scope_key=None,
            dedupe_key=None,
            payload={"limit": 10},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["migrated"], 1)


if __name__ == "__main__":
    unittest.main()
