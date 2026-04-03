from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bson.binary import Binary

from fin_ops_platform.services.state_store import (
    DEFAULT_APP_MONGO_DATABASE,
    ApplicationStateStore,
    FILE_METADATA_COLLECTION,
    LEGACY_APP_MONGO_COLLECTION,
    META_COLLECTION,
    STATE_COLLECTIONS,
    load_mongo_state_settings,
)


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.update_one_calls = 0
        self.replace_one_calls = 0
        self.delete_many_calls = 0

    def find_one(self, query: dict) -> dict | None:
        if "_id" in query:
            return self.documents.get(query["_id"])
        for document in self.documents.values():
            if all(document.get(key) == value for key, value in query.items()):
                return document
        return None

    def find(self, query: dict | None = None) -> list[dict]:
        if not query:
            return list(self.documents.values())
        return [
            document
            for document in self.documents.values()
            if all(document.get(key) == value for key, value in query.items())
        ]

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        self.update_one_calls += 1
        document = dict(self.documents.get(query["_id"], {"_id": query["_id"]}))
        if "$setOnInsert" in update and query["_id"] not in self.documents:
            document.update(update["$setOnInsert"])
        if "$set" in update:
            document.update(update["$set"])
        if upsert or query["_id"] in self.documents:
            self.documents[query["_id"]] = document

    def replace_one(self, query: dict, replacement: dict, upsert: bool = False) -> None:
        self.replace_one_calls += 1
        if "_id" not in query:
            raise KeyError("_id is required in fake replace_one")
        if upsert or query["_id"] in self.documents:
            self.documents[query["_id"]] = dict(replacement)

    def delete_many(self, query: dict | None = None) -> None:
        self.delete_many_calls += 1
        if not query:
            self.documents.clear()
            return
        to_delete = [
            key
            for key, document in self.documents.items()
            if all(document.get(field) == value for field, value in query.items())
        ]
        for key in to_delete:
            self.documents.pop(key, None)


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}
        self.gridfs_buckets: dict[str, dict[str, dict]] = {}

    def __getitem__(self, collection_name: str) -> FakeCollection:
        return self.collections.setdefault(collection_name, FakeCollection())


class FakeMongoClient:
    def __init__(self, *args, **kwargs) -> None:
        self.databases: dict[str, FakeDatabase] = {}

    def __getitem__(self, database_name: str) -> FakeDatabase:
        return self.databases.setdefault(database_name, FakeDatabase())


class FakeGridFSDownloadStream:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def read(self) -> bytes:
        return self._content


class FakeGridFSBucket:
    def __init__(self, database: FakeDatabase, bucket_name: str) -> None:
        self._files = database.gridfs_buckets.setdefault(bucket_name, {})

    def upload_from_stream_with_id(self, file_id: str, filename: str, source, metadata: dict | None = None) -> str:
        if hasattr(source, "read"):
            content = source.read()
        else:
            content = bytes(source)
        self._files[str(file_id)] = {
            "_id": str(file_id),
            "filename": filename,
            "metadata": dict(metadata or {}),
            "content": content,
        }
        return str(file_id)

    def open_download_stream(self, file_id: str) -> FakeGridFSDownloadStream:
        return FakeGridFSDownloadStream(self._files[str(file_id)]["content"])


class StateStoreTests(unittest.TestCase):
    def test_uses_explicit_app_mongo_config_with_default_app_database(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps(
                    {
                        "host": "139.155.5.132",
                        "port": 27017,
                        "username": "admin",
                        "password": "Root@5858",
                        "auth_source": "admin",
                    }
                ),
                encoding="utf-8",
            )

            settings = load_mongo_state_settings(data_dir)

            self.assertIsNotNone(settings)
            assert settings is not None
            self.assertEqual(settings.host, "139.155.5.132")
            self.assertEqual(settings.database, DEFAULT_APP_MONGO_DATABASE)

    def test_mongo_store_persists_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                payload = {
                    "imports": {
                        "batch_counter": 4,
                        "invoice_counter": 1,
                        "txn_counter": 1,
                        "batches": {
                            "batch_import_0001": {
                                "batch": {
                                    "id": "batch_import_0001",
                                    "batch_type": "input_invoice",
                                    "source_name": "全量发票查询导出结果-2026年1月.xlsx",
                                    "imported_by": "user_finance_01",
                                    "row_count": 1,
                                    "success_count": 1,
                                    "error_count": 0,
                                    "status": "completed",
                                },
                                "row_results": [],
                                "normalized_rows": [],
                            }
                        },
                        "invoices": [
                            {
                                "id": "inv_imported_0001",
                                "invoice_type": "input",
                                "invoice_no": "5001",
                                "invoice_code": "033001",
                                "counterparty": {
                                    "id": "cp_imported_0001",
                                    "name": "供应商A",
                                    "normalized_name": "供应商a",
                                    "counterparty_type": "unknown",
                                },
                                "amount": "100.00",
                                "signed_amount": "100.00",
                                "invoice_date": "2026-01-11",
                            }
                        ],
                        "transactions": [
                            {
                                "id": "txn_imported_0001",
                                "account_no": "6222",
                                "txn_direction": "outflow",
                                "counterparty_name_raw": "供应商A",
                                "amount": "100.00",
                                "signed_amount": "-100.00",
                                "txn_date": "2026-01-11",
                            }
                        ],
                    },
                    "file_imports": {
                        "session_counter": 2,
                        "file_counter": 3,
                        "sessions": {
                            "import_session_0001": {
                                "id": "import_session_0001",
                                "imported_by": "user_finance_01",
                                "file_count": 1,
                                "status": "confirmed",
                                "created_at": "2026-03-30T12:00:00+00:00",
                                "files": [
                                    {
                                        "id": "import_file_0001",
                                        "file_name": "全量发票查询导出结果-2026年1月.xlsx",
                                        "status": "confirmed",
                                        "template_code": "invoice_export",
                                        "batch_type": "input_invoice",
                                        "stored_file_path": "gridfs://import_file_0001/全量发票查询导出结果-2026年1月.xlsx",
                                        "preview_batch_id": "batch_import_0001",
                                        "batch_id": "batch_import_0001",
                                    }
                                ],
                            }
                        },
                    },
                    "matching": {
                        "run_counter": 2,
                        "result_counter": 1,
                        "runs": {
                            "matching_run_0001": {
                                "id": "matching_run_0001",
                                "triggered_by": "import_session:import_session_0001",
                                "invoice_count": 1,
                                "transaction_count": 1,
                                "results": [],
                            }
                        },
                        "results": {},
                    },
                }

                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save(payload)
                    loaded = store.load()

            self.assertEqual(store.storage_backend, "mongo")
            self.assertEqual(store.mongo_database_name, "fin_ops_platform_app")
            self.assertEqual(loaded, payload)
            db = fake_client["fin_ops_platform_app"]
            self.assertIn("_meta", db[META_COLLECTION].documents)
            self.assertIn("current_state", db["imports_meta"].documents)
            self.assertIn("batch_import_0001", db["import_batches"].documents)
            self.assertIn("import_session_0001", db["file_import_sessions"].documents)
            self.assertIn("import_file_0001", db["file_import_files"].documents)
            self.assertIn("matching_run_0001", db["matching_runs"].documents)
            metadata_doc = db[FILE_METADATA_COLLECTION].documents["current_state"]
            metadata_payload = pickle.loads(bytes(metadata_doc["payload"]))  # noqa: S301 - test fixture
            self.assertEqual(metadata_payload["files"][0]["file_name"], "全量发票查询导出结果-2026年1月.xlsx")
            self.assertEqual(
                metadata_payload["files"][0]["stored_file_path"],
                "gridfs://import_file_0001/全量发票查询导出结果-2026年1月.xlsx",
            )
            session_doc = db["file_import_files"].documents["import_file_0001"]
            self.assertEqual(session_doc["session_id"], "import_session_0001")
            self.assertEqual(session_doc["file_name"], "全量发票查询导出结果-2026年1月.xlsx")
            self.assertIsInstance(session_doc["payload"], Binary)

    def test_mongo_mode_does_not_fallback_to_local_state_pickle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            legacy_payload = {"imports": {"batch_counter": 9}, "file_imports": {"session_counter": 3}}
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump(legacy_payload, handle)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    loaded = store.load()

            self.assertEqual(loaded, {})
            db = fake_client["fin_ops_platform_app"]
            self.assertNotIn("current_state", db["imports_meta"].documents)

    def test_save_workbench_overrides_does_not_rewrite_unrelated_detailed_collections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    db = fake_client["fin_ops_platform_app"]

                    db["import_batches"].documents["batch_import_0001"] = {"_id": "batch_import_0001", "payload": Binary(b"seed")}
                    db["bank_transactions"].documents["txn_imported_0001"] = {"_id": "txn_imported_0001", "payload": Binary(b"seed")}
                    db["matching_results"].documents["match_result_0001"] = {"_id": "match_result_0001", "payload": Binary(b"seed")}

                    store.save_workbench_overrides(
                        {
                            "case_counter": 3,
                            "row_overrides": {
                                "txn_imported_0001": {
                                    "case_id": "CASE-API-0001",
                                    "relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                                    "available_actions": ["detail"],
                                }
                            },
                        }
                    )

            db = fake_client["fin_ops_platform_app"]
            self.assertIn("txn_imported_0001", db["workbench_row_overrides"].documents)
            self.assertIn("batch_import_0001", db["import_batches"].documents)
            self.assertIn("match_result_0001", db["matching_results"].documents)
            self.assertEqual(db["import_batches"].delete_many_calls, 0)
            self.assertEqual(db["bank_transactions"].delete_many_calls, 0)
            self.assertEqual(db["matching_results"].delete_many_calls, 0)

    def test_migrates_legacy_single_collection_snapshot_into_split_collections(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            legacy_payload = {
                "imports": {"batch_counter": 5},
                "file_imports": {"session_counter": 2},
                "matching": {"run_counter": 1},
            }
            fake_client["fin_ops_platform_app"][LEGACY_APP_MONGO_COLLECTION].documents["current_state"] = {
                "_id": "current_state",
                "payload": Binary(pickle.dumps(legacy_payload)),
            }

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    loaded = store.load()

            self.assertEqual(loaded, legacy_payload)
            db = fake_client["fin_ops_platform_app"]
            self.assertIn("current_state", db["imports_meta"].documents)
            self.assertEqual(db[STATE_COLLECTIONS["imports"]].documents, {})
            self.assertEqual(db[STATE_COLLECTIONS["file_imports"]].documents, {})
            self.assertEqual(db[STATE_COLLECTIONS["matching"]].documents, {})

    def test_store_import_file_round_trips_through_gridfs_in_mongo_mode(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    stored_ref = store.store_import_file(
                        session_id="import_session_0001",
                        file_id="import_file_0001",
                        file_name="全量发票查询导出结果-2026年1月.xlsx",
                        content=b"invoice-content",
                    )
                    loaded = store.read_import_file(stored_ref)

            self.assertTrue(stored_ref.startswith("gridfs://"))
            self.assertEqual(loaded, b"invoice-content")
            self.assertFalse((data_dir / "import_files").exists())

    def test_migrates_legacy_local_file_reference_to_gridfs_on_load(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            legacy_file = data_dir / "legacy-upload.xlsx"
            legacy_file.write_bytes(b"legacy-file-content")
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            split_payload = {
                "imports": {"batch_counter": 1},
                "file_imports": {
                    "session_counter": 1,
                    "file_counter": 1,
                    "sessions": {
                        "import_session_0001": {
                            "id": "import_session_0001",
                            "imported_by": "user_finance_01",
                            "file_count": 1,
                            "status": "preview_ready",
                            "files": [
                                {
                                    "id": "import_file_0001",
                                    "file_name": "legacy-upload.xlsx",
                                    "stored_file_path": str(legacy_file),
                                    "status": "preview_ready",
                                }
                            ],
                        }
                    },
                },
                "matching": {"run_counter": 0},
            }
            for key, collection_name in STATE_COLLECTIONS.items():
                fake_client["fin_ops_platform_app"][collection_name].documents["current_state"] = {
                    "_id": "current_state",
                    "payload": Binary(pickle.dumps(split_payload.get(key, {}))),
                }

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    loaded = store.load()
                    stored_ref = loaded["file_imports"]["sessions"]["import_session_0001"]["files"][0]["stored_file_path"]
                    content = store.read_import_file(stored_ref)

            self.assertTrue(stored_ref.startswith("gridfs://"))
            self.assertEqual(content, b"legacy-file-content")
            self.assertFalse(legacy_file.exists())
            db = fake_client["fin_ops_platform_app"]
            migrated_file_doc = db["file_import_files"].documents["import_file_0001"]
            self.assertTrue(migrated_file_doc["stored_file_path"].startswith("gridfs://"))


if __name__ == "__main__":
    unittest.main()
