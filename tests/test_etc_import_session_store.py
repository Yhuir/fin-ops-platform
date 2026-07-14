from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.etc_import_session_store import (
    InMemoryEtcImportSessionStore,
    PostgresEtcImportSessionStore,
    StoredEtcImportSession,
    StoredEtcImportUpload,
    build_etc_import_session_store,
)
from fin_ops_platform.services.object_storage import InMemoryObjectStorageRepository
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def _session() -> StoredEtcImportSession:
    content = b"PK\x03\x04deterministic-etc-archive"
    audit = {"original_count": 1, "unique_count": 1, "importable_count": 1, "confirmable_count": 1}
    return StoredEtcImportSession(
        session_id="session-1",
        status="preview_ready",
        task_id="task-1",
        task_version=3,
        zip_preview_generation=2,
        confirmed_item_set_hash="confirmed-hash",
        preview_fingerprint="preview-hash",
        preview_result={"summary": {"imported": 1}, "audit": audit, "items": []},
        preview_audit=audit,
        preview_files=[{"fileName": "input.zip", "audit": audit}],
        reconciliation_filter={"taskId": "task-1", "taskVersion": 3},
        uploads=(
            StoredEtcImportUpload(
                file_id="etc-import-0001",
                file_name="input.zip",
                content=content,
                sha256=sha256(content).hexdigest(),
                size_bytes=len(content),
                ordinal=0,
            ),
        ),
    )


class EtcImportSessionStoreTests(unittest.TestCase):
    def test_in_memory_adapter_is_explicitly_non_durable_and_copies_bytes(self) -> None:
        store = InMemoryEtcImportSessionStore()

        saved = store.save_preview(_session())
        loaded = store.get("session-1")

        self.assertFalse(store.durable)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded, saved)
        self.assertIsNot(loaded, saved)
        self.assertEqual(loaded.uploads[0].content, _session().uploads[0].content)

    def test_durable_save_does_not_redownload_archives_after_verified_write(self) -> None:
        class Repository:
            def save_preview(self, _payload: dict, _files: list[dict]) -> None:
                return None

            def get(self, _session_id: str) -> dict:
                raise AssertionError("save_preview must not reload persisted archive bytes")

        class ArchiveStore:
            def store_etc_import_archive(self, **kwargs: object) -> dict[str, object]:
                content = bytes(kwargs["content"])
                file_id = str(kwargs["file_id"])
                return {
                    "stored_file_path": f"minio://bucket/{file_id}",
                    "file_object_id": f"object-{file_id}",
                    "sha256": sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }

            def read_etc_import_archive(self, _stored_file_path: str) -> bytes:
                raise AssertionError("save_preview must not reload persisted archive bytes")

            def delete_etc_import_archives(self, _stored_file_paths: list[str]) -> int:
                return 0

        store = PostgresEtcImportSessionStore(repository=Repository(), archive_store=ArchiveStore())

        saved = store.save_preview(_session())

        self.assertEqual(saved.uploads[0].stored_file_path, "minio://bucket/etc-import-0001")
        self.assertEqual(saved.uploads[0].content, _session().uploads[0].content)


class PostgresEtcImportSessionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.temp_dir = TemporaryDirectory()
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.object_storage = InMemoryObjectStorageRepository(bucket="etc-import-test")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _state_store(self) -> PostgresStateStore:
        return PostgresStateStore(
            data_dir=Path(self.temp_dir.name),
            connection=self.connection,
            object_storage_repository=self.object_storage,
        )

    def test_preview_survives_new_store_instance_and_status_updates_remain_consistent(self) -> None:
        first = build_etc_import_session_store(self._state_store())
        self.assertTrue(first.durable)

        saved = first.save_preview(_session())
        second = build_etc_import_session_store(self._state_store())
        loaded = second.get(saved.session_id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.task_id, "task-1")
        self.assertEqual(loaded.zip_preview_generation, 2)
        self.assertEqual(loaded.uploads[0].content, _session().uploads[0].content)
        self.assertEqual(loaded.uploads[0].sha256, _session().uploads[0].sha256)

        completed = second.update_status("session-1", status="succeeded", imported_by="worker")
        third = build_etc_import_session_store(self._state_store()).get("session-1")
        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(third.status, "succeeded")
        self.assertEqual(third.imported_by, "worker")
        self.assertIsNone(third.last_error)


if __name__ == "__main__":
    unittest.main()
