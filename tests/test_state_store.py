from __future__ import annotations

import json
import os
import pickle
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bson.binary import Binary
from pymongo.errors import AutoReconnect

from fin_ops_platform.services.import_file_service import FileImportPreviewItem
from fin_ops_platform.services.state_store import (
    APP_HEALTH_ALERTS_COLLECTION,
    COST_STATISTICS_READ_MODELS_COLLECTION,
    DEFAULT_APP_MONGO_DATABASE,
    ApplicationStateStore,
    FILE_METADATA_COLLECTION,
    LEGACY_APP_MONGO_COLLECTION,
    META_COLLECTION,
    OA_ATTACHMENT_INVOICE_CACHE_COLLECTION,
    STATE_COLLECTIONS,
    TAX_OFFSET_READ_MODELS_COLLECTION,
    WORKBENCH_CANDIDATE_MATCHES_COLLECTION,
    WORKBENCH_READ_MODELS_COLLECTION,
    WORKBENCH_PAIR_RELATIONS_COLLECTION,
    default_data_dir,
    load_mongo_state_settings,
)


class FakeDeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


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

    def delete_many(self, query: dict | None = None) -> FakeDeleteResult:
        self.delete_many_calls += 1
        if not query:
            deleted_count = len(self.documents)
            self.documents.clear()
            return FakeDeleteResult(deleted_count)
        to_delete = [
            key
            for key, document in self.documents.items()
            if all(document.get(field) == value for field, value in query.items())
        ]
        for key in to_delete:
            self.documents.pop(key, None)
        return FakeDeleteResult(len(to_delete))

    def count_documents(self, query: dict | None = None) -> int:
        return len(self.find(query))


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


class FailOnceCollection(FakeCollection):
    def __init__(self, *, fail_method: str) -> None:
        super().__init__()
        self._fail_method = fail_method
        self._failed = False

    def _maybe_fail_once(self, method_name: str) -> None:
        if self._fail_method == method_name and not self._failed:
            self._failed = True
            raise AutoReconnect("mock connection closed")

    def find_one(self, query: dict) -> dict | None:
        self._maybe_fail_once("find_one")
        return super().find_one(query)

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        self._maybe_fail_once("update_one")
        return super().update_one(query, update, upsert=upsert)

    def delete_many(self, query: dict | None = None) -> FakeDeleteResult:
        self._maybe_fail_once("delete_many")
        return super().delete_many(query)


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
    def test_default_data_dir_honors_environment_override(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"FIN_OPS_DATA_DIR": temp_dir}):
                self.assertEqual(default_data_dir(), Path(temp_dir))

    def test_serialize_file_import_preview_item_tolerates_missing_new_fields_from_old_pickle(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            item = FileImportPreviewItem(
                id="import_file_0001",
                file_name="old.xlsx",
                template_code=None,
                batch_type=None,
                status="unrecognized_template",
                message="无法识别文件模板。",
                row_count=0,
            )
            delattr(item, "selected_bank_short_name")

            serialized = store._serialize_value(item)

        self.assertIn("selected_bank_short_name", serialized)
        self.assertIsNone(serialized["selected_bank_short_name"])

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

    def test_save_workbench_overrides_can_incrementally_update_changed_rows_only(self) -> None:
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
                    db["workbench_row_overrides"].documents["row_a"] = {
                        "_id": "row_a",
                        "payload": Binary(pickle.dumps({"case_id": "CASE-A", "detail_note": "old a"})),
                    }
                    db["workbench_row_overrides"].documents["row_b"] = {
                        "_id": "row_b",
                        "payload": Binary(pickle.dumps({"case_id": "CASE-B", "detail_note": "old b"})),
                    }

                    store.save_workbench_overrides(
                        {
                            "case_counter": 7,
                            "row_overrides": {
                                "row_a": {"case_id": "CASE-A", "detail_note": "new a"},
                                "row_b": {"case_id": "CASE-B", "detail_note": "old b"},
                            },
                        },
                        changed_row_ids=["row_a"],
                    )

            db = fake_client["fin_ops_platform_app"]
            row_a = pickle.loads(bytes(db["workbench_row_overrides"].documents["row_a"]["payload"]))  # noqa: S301
            row_b = pickle.loads(bytes(db["workbench_row_overrides"].documents["row_b"]["payload"]))  # noqa: S301
            self.assertEqual(row_a["detail_note"], "new a")
            self.assertEqual(row_b["detail_note"], "old b")
            self.assertEqual(db["workbench_row_overrides"].delete_many_calls, 0)
            self.assertEqual(db["workbench_row_overrides"].replace_one_calls, 1)

    def test_save_workbench_pair_relations_persists_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            snapshot = {
                "pair_relations": {
                    "CASE-PAIR-001": {
                        "case_id": "CASE-PAIR-001",
                        "row_ids": ["oa-001", "bk-001"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "YNSYLP005",
                        "created_at": "2026-04-08T10:00:00+00:00",
                        "updated_at": "2026-04-08T10:00:00+00:00",
                    }
                }
            }

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save_workbench_pair_relations(snapshot)
                    loaded = store.load_workbench_pair_relations()

            self.assertEqual(loaded, snapshot)
            db = fake_client["fin_ops_platform_app"]
            self.assertIn("CASE-PAIR-001", db[WORKBENCH_PAIR_RELATIONS_COLLECTION].documents)

    def test_save_workbench_pair_relations_does_not_rewrite_unrelated_detailed_collections(self) -> None:
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
                    db["matching_results"].documents["match_result_0001"] = {"_id": "match_result_0001", "payload": Binary(b"seed")}

                    store.save_workbench_pair_relations(
                        {
                            "pair_relations": {
                                "CASE-PAIR-001": {
                                    "case_id": "CASE-PAIR-001",
                                    "row_ids": ["oa-001", "bk-001"],
                                    "row_types": ["oa", "bank"],
                                    "status": "active",
                                    "relation_mode": "manual_confirmed",
                                    "month_scope": "all",
                                    "created_by": "YNSYLP005",
                                    "created_at": "2026-04-08T10:00:00+00:00",
                                    "updated_at": "2026-04-08T10:00:00+00:00",
                                }
                            }
                        }
                    )

            db = fake_client["fin_ops_platform_app"]
            self.assertIn("CASE-PAIR-001", db[WORKBENCH_PAIR_RELATIONS_COLLECTION].documents)
            self.assertIn("batch_import_0001", db["import_batches"].documents)
            self.assertIn("match_result_0001", db["matching_results"].documents)
            self.assertEqual(db["import_batches"].delete_many_calls, 0)
            self.assertEqual(db["matching_results"].delete_many_calls, 0)

    def test_save_workbench_pair_relations_can_incrementally_update_changed_case_only(self) -> None:
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
                    db["workbench_pair_relations"].documents["CASE-A"] = {
                        "_id": "CASE-A",
                        "payload": Binary(pickle.dumps({"case_id": "CASE-A", "status": "active"})),
                    }
                    db["workbench_pair_relations"].documents["CASE-B"] = {
                        "_id": "CASE-B",
                        "payload": Binary(pickle.dumps({"case_id": "CASE-B", "status": "active"})),
                    }

                    store.save_workbench_pair_relations(
                        {
                            "pair_relations": {
                                "CASE-A": {"case_id": "CASE-A", "status": "cancelled"},
                                "CASE-B": {"case_id": "CASE-B", "status": "active"},
                            }
                        },
                        changed_case_ids=["CASE-A"],
                    )

            db = fake_client["fin_ops_platform_app"]
            case_a = pickle.loads(bytes(db["workbench_pair_relations"].documents["CASE-A"]["payload"]))  # noqa: S301
            case_b = pickle.loads(bytes(db["workbench_pair_relations"].documents["CASE-B"]["payload"]))  # noqa: S301
            self.assertEqual(case_a["status"], "cancelled")
            self.assertEqual(case_b["status"], "active")
            self.assertEqual(db["workbench_pair_relations"].delete_many_calls, 0)
            self.assertEqual(db["workbench_pair_relations"].replace_one_calls, 1)

    def test_save_workbench_pair_relations_persists_history_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "pair_relations": {
                    "CASE-A": {
                        "case_id": "CASE-A",
                        "row_ids": ["oa-1", "bk-1"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                    }
                },
                "pair_relation_history": [
                    {
                        "operation_id": "op-1",
                        "operation_type": "confirm_link",
                        "before_relations": [],
                        "after_relations": [{"case_id": "CASE-A", "row_ids": ["oa-1", "bk-1"]}],
                        "affected_row_ids": ["oa-1", "bk-1"],
                        "note": "金额不一致说明",
                        "amount_check": {"status": "mismatch"},
                        "created_by": "test",
                        "created_at": "2026-05-02T00:00:00+00:00",
                    }
                ],
            }
            store = ApplicationStateStore(data_dir)
            store.save_workbench_pair_relations(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_workbench_pair_relations()

        self.assertEqual(loaded["pair_relation_history"][0]["operation_type"], "confirm_link")
        self.assertEqual(loaded["pair_relation_history"][0]["amount_check"]["status"], "mismatch")

    def test_save_workbench_read_models_persists_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()

            snapshot = {
                "read_models": {
                    "all": {
                        "scope_key": "all",
                        "scope_type": "all_time",
                        "generated_at": "2026-04-08T12:00:00+00:00",
                        "payload": {"summary": {"paired_count": 3}},
                    }
                }
            }

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save_workbench_read_models(snapshot)
                    loaded = store.load_workbench_read_models()

            self.assertEqual(loaded, snapshot)
            db = fake_client["fin_ops_platform_app"]
            self.assertIn("all", db[WORKBENCH_READ_MODELS_COLLECTION].documents)

    def test_local_snapshot_persists_and_loads_workbench_candidate_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "imports": {},
                "file_imports": {},
                "matching": {},
                "workbench_candidate_matches": {
                    "candidates": {
                        "candidate:001": {
                            "candidate_key": "candidate:001",
                            "scope_month": "2026-05",
                            "status": "needs_review",
                        }
                    }
                },
            }

            store = ApplicationStateStore(data_dir)
            store.save(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load()

        self.assertEqual(loaded["workbench_candidate_matches"], snapshot["workbench_candidate_matches"])

    def test_save_workbench_candidate_matches_persists_and_loads_mongo_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            snapshot = {
                "candidates": {
                    "candidate:001": {
                        "candidate_id": "candidate:001",
                        "candidate_key": "candidate:001",
                        "scope_month": "2026-05",
                        "candidate_type": "oa_bank_invoice",
                        "status": "needs_review",
                        "confidence": "medium",
                        "rule_code": "same_amount",
                        "row_ids": ["oa-001", "bank-001"],
                        "generated_at": "2026-05-06T10:00:00+00:00",
                    }
                }
            }

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save_workbench_candidate_matches(snapshot)
                    loaded = store.load_workbench_candidate_matches()

            self.assertEqual(loaded, snapshot)
            db = fake_client["fin_ops_platform_app"]
            self.assertIn("candidate:001", db[WORKBENCH_CANDIDATE_MATCHES_COLLECTION].documents)

    def test_save_workbench_read_models_does_not_rewrite_unrelated_detailed_collections(self) -> None:
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
                    db["matching_results"].documents["match_result_0001"] = {"_id": "match_result_0001", "payload": Binary(b"seed")}

                    store.save_workbench_read_models(
                        {
                            "read_models": {
                                "2026-03": {
                                    "scope_key": "2026-03",
                                    "scope_type": "month",
                                    "generated_at": "2026-04-08T12:00:00+00:00",
                                    "payload": {"summary": {"paired_count": 2}},
                                }
                            }
                        }
                    )

            db = fake_client["fin_ops_platform_app"]
            self.assertIn("2026-03", db[WORKBENCH_READ_MODELS_COLLECTION].documents)
            self.assertIn("batch_import_0001", db["import_batches"].documents)
            self.assertIn("match_result_0001", db["matching_results"].documents)
            self.assertEqual(db["import_batches"].delete_many_calls, 0)
            self.assertEqual(db["matching_results"].delete_many_calls, 0)

    def test_save_workbench_read_models_can_incrementally_update_changed_scope_only(self) -> None:
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
                    db["workbench_read_models"].documents["all"] = {
                        "_id": "all",
                        "payload": Binary(pickle.dumps({"scope_key": "all", "payload": {"summary": {"paired_count": 1}}})),
                    }
                    db["workbench_read_models"].documents["2026-03"] = {
                        "_id": "2026-03",
                        "payload": Binary(pickle.dumps({"scope_key": "2026-03", "payload": {"summary": {"paired_count": 2}}})),
                    }

                    store.save_workbench_read_models(
                        {
                            "read_models": {
                                "all": {"scope_key": "all", "payload": {"summary": {"paired_count": 9}}},
                                "2026-03": {"scope_key": "2026-03", "payload": {"summary": {"paired_count": 2}}},
                            }
                        },
                        changed_scope_keys=["all"],
                    )

            db = fake_client["fin_ops_platform_app"]
            all_scope = pickle.loads(bytes(db["workbench_read_models"].documents["all"]["payload"]))  # noqa: S301
            month_scope = pickle.loads(bytes(db["workbench_read_models"].documents["2026-03"]["payload"]))  # noqa: S301
            self.assertEqual(all_scope["payload"]["summary"]["paired_count"], 9)
            self.assertEqual(month_scope["payload"]["summary"]["paired_count"], 2)
            self.assertEqual(db["workbench_read_models"].delete_many_calls, 0)
            self.assertEqual(db["workbench_read_models"].replace_one_calls, 1)

    def test_save_cost_statistics_read_models_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "read_models": {
                    "active:2026-05": {
                        "scope_key": "active:2026-05",
                        "scope_type": "month",
                        "schema_version": "2026-05-cost-statistics-explorer-v1",
                        "month": "2026-05",
                        "project_scope": "active",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "entry_count": 3,
                        "payload": {"summary": {"transaction_count": 3}},
                        "source_scope_keys": ["workbench:2026-05"],
                    }
                }
            }
            store = ApplicationStateStore(data_dir)
            store.save_cost_statistics_read_models(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_cost_statistics_read_models()

        self.assertEqual(loaded, snapshot)

    def test_save_cost_statistics_read_models_can_incrementally_update_changed_scope_only(self) -> None:
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
                    db["cost_statistics_read_models"].documents["active:2026-04"] = {
                        "_id": "active:2026-04",
                        "payload": Binary(
                            pickle.dumps(
                                {
                                    "scope_key": "active:2026-04",
                                    "payload": {"summary": {"transaction_count": 1}},
                                }
                            )
                        ),
                    }
                    db["cost_statistics_read_models"].documents["active:2026-05"] = {
                        "_id": "active:2026-05",
                        "payload": Binary(
                            pickle.dumps(
                                {
                                    "scope_key": "active:2026-05",
                                    "payload": {"summary": {"transaction_count": 2}},
                                }
                            )
                        ),
                    }

                    store.save_cost_statistics_read_models(
                        {
                            "read_models": {
                                "active:2026-04": {
                                    "scope_key": "active:2026-04",
                                    "payload": {"summary": {"transaction_count": 1}},
                                },
                                "active:2026-05": {
                                    "scope_key": "active:2026-05",
                                    "scope_type": "month",
                                    "schema_version": "2026-05-cost-statistics-explorer-v1",
                                    "month": "2026-05",
                                    "project_scope": "active",
                                    "generated_at": "2026-05-04T12:00:00+00:00",
                                    "cache_status": "ready",
                                    "entry_count": 9,
                                    "payload": {"summary": {"transaction_count": 9}},
                                },
                            }
                        },
                        changed_scope_keys=["active:2026-05"],
                    )
                    loaded = store.load_cost_statistics_read_models()

            db = fake_client["fin_ops_platform_app"]
            unchanged = pickle.loads(  # noqa: S301
                bytes(db["cost_statistics_read_models"].documents["active:2026-04"]["payload"])
            )
            changed = pickle.loads(  # noqa: S301
                bytes(db["cost_statistics_read_models"].documents["active:2026-05"]["payload"])
            )
            self.assertEqual(unchanged["payload"]["summary"]["transaction_count"], 1)
            self.assertEqual(changed["payload"]["summary"]["transaction_count"], 9)
            self.assertEqual(db["cost_statistics_read_models"].delete_many_calls, 0)
            self.assertEqual(db["cost_statistics_read_models"].replace_one_calls, 1)
            self.assertIn("active:2026-05", db[COST_STATISTICS_READ_MODELS_COLLECTION].documents)
            self.assertEqual(loaded["read_models"]["active:2026-05"]["entry_count"], 9)

    def test_save_tax_offset_read_models_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            snapshot = {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "scope_type": "month",
                        "schema_version": "2026-05-tax-offset-month-v1",
                        "month": "2026-05",
                        "generated_at": "2026-05-04T12:00:00+00:00",
                        "cache_status": "ready",
                        "output_count": 2,
                        "input_plan_count": 1,
                        "certified_count": 3,
                        "payload": {
                            "output_items": [{"id": "output-1"}, {"id": "output-2"}],
                            "input_plan_items": [{"id": "input-1"}],
                            "certified_items": [{"id": "cert-1"}, {"id": "cert-2"}, {"id": "cert-3"}],
                        },
                        "source_scope_keys": ["tax-offset:source:2026-05"],
                    }
                }
            }
            store = ApplicationStateStore(data_dir)
            store.save_tax_offset_read_models(snapshot)

            reloaded = ApplicationStateStore(data_dir)
            loaded = reloaded.load_tax_offset_read_models()

        self.assertEqual(loaded, snapshot)

    def test_save_tax_offset_read_models_can_incrementally_update_and_delete_changed_scopes(self) -> None:
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
                    db["tax_offset_read_models"].documents["2026-04"] = {
                        "_id": "2026-04",
                        "payload": Binary(
                            pickle.dumps(
                                {
                                    "scope_key": "2026-04",
                                    "payload": {
                                        "output_items": [{"id": "old-output"}],
                                        "input_plan_items": [],
                                        "certified_items": [],
                                    },
                                }
                            )
                        ),
                    }
                    db["tax_offset_read_models"].documents["2026-05"] = {
                        "_id": "2026-05",
                        "payload": Binary(
                            pickle.dumps(
                                {
                                    "scope_key": "2026-05",
                                    "payload": {
                                        "output_items": [{"id": "old-output"}],
                                        "input_plan_items": [],
                                        "certified_items": [],
                                    },
                                }
                            )
                        ),
                    }

                    store.save_tax_offset_read_models(
                        {
                            "read_models": {
                                "2026-05": {
                                    "scope_key": "2026-05",
                                    "scope_type": "month",
                                    "schema_version": "2026-05-tax-offset-month-v1",
                                    "month": "2026-05",
                                    "generated_at": "2026-05-04T12:00:00+00:00",
                                    "cache_status": "ready",
                                    "output_count": 2,
                                    "input_plan_count": 1,
                                    "certified_count": 3,
                                    "payload": {
                                        "output_items": [{"id": "output-1"}, {"id": "output-2"}],
                                        "input_plan_items": [{"id": "input-1"}],
                                        "certified_items": [
                                            {"id": "cert-1"},
                                            {"id": "cert-2"},
                                            {"id": "cert-3"},
                                        ],
                                    },
                                    "source_scope_keys": ["tax-offset:source:2026-05"],
                                }
                            }
                        },
                        changed_scope_keys=["2026-05", "2026-04"],
                    )
                    loaded = store.load_tax_offset_read_models()

            db = fake_client["fin_ops_platform_app"]
            changed = pickle.loads(  # noqa: S301
                bytes(db["tax_offset_read_models"].documents["2026-05"]["payload"])
            )
            self.assertNotIn("2026-04", db[TAX_OFFSET_READ_MODELS_COLLECTION].documents)
            self.assertEqual(changed["output_count"], 2)
            self.assertEqual(changed["payload"]["certified_items"][2]["id"], "cert-3")
            self.assertEqual(db["tax_offset_read_models"].delete_many_calls, 1)
            self.assertEqual(db["tax_offset_read_models"].replace_one_calls, 1)
            self.assertEqual(loaded["read_models"]["2026-05"]["certified_count"], 3)

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

    def test_oa_attachment_invoice_cache_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_oa_attachment_invoice_cache_entry(
                "cache-key-001",
                {"invoices": [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}]},
            )

            reloaded_store = ApplicationStateStore(data_dir)
            cached = reloaded_store.load_oa_attachment_invoice_cache_entry("cache-key-001")

        self.assertEqual(
            cached,
            {
                "cache_key": "cache-key-001",
                "invoices": [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}],
            },
        )

    def test_oa_sync_state_persists_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            store.save_oa_sync_state({"poll_fingerprints": {"2026-03": "fingerprint-001", "all": "fingerprint-all"}})

            reloaded_store = ApplicationStateStore(data_dir)
            state = reloaded_store.load_oa_sync_state()

        self.assertEqual(state["poll_fingerprints"], {"2026-03": "fingerprint-001", "all": "fingerprint-all"})

    def test_app_health_alerts_persist_locally_across_store_instances(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            store = ApplicationStateStore(data_dir)
            snapshot = {
                "records": {
                    "alert_1": {
                        "alert_id": "alert_1",
                        "kind": "dependency_unavailable",
                        "severity": "critical",
                        "status": "active",
                    }
                }
            }

            store.save_app_health_alerts(snapshot)
            reloaded_store = ApplicationStateStore(data_dir)

            self.assertEqual(reloaded_store.load_app_health_alerts(), snapshot)

    def test_mongo_app_health_alerts_save_and_load_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            snapshot = {"records": {"alert_1": {"alert_id": "alert_1", "status": "active"}}}

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save_app_health_alerts(snapshot)
                    loaded = store.load_app_health_alerts()

            collection = fake_client["fin_ops_platform_app"][APP_HEALTH_ALERTS_COLLECTION]
            self.assertIn("current_state", collection.documents)
            self.assertEqual(loaded, snapshot)

    def test_mongo_oa_attachment_invoice_cache_save_retries_transient_autoreconnect(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            db = fake_client["fin_ops_platform_app"]
            db.collections[OA_ATTACHMENT_INVOICE_CACHE_COLLECTION] = FailOnceCollection(fail_method="update_one")

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    store.save_oa_attachment_invoice_cache_entry(
                        "cache-key-001",
                        {"invoices": [{"invoice_no": "40512344"}]},
                    )

            collection = db[OA_ATTACHMENT_INVOICE_CACHE_COLLECTION]
            self.assertEqual(collection.update_one_calls, 1)
            self.assertIn("cache-key-001", collection.documents)

    def test_mongo_oa_attachment_invoice_cache_load_retries_transient_autoreconnect(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            db = fake_client["fin_ops_platform_app"]
            collection = FailOnceCollection(fail_method="find_one")
            collection.documents["cache-key-001"] = {
                "_id": "cache-key-001",
                "payload": Binary(pickle.dumps({"cache_key": "cache-key-001", "invoices": [{"invoice_no": "40512344"}]})),
            }
            db.collections[OA_ATTACHMENT_INVOICE_CACHE_COLLECTION] = collection

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    cached = store.load_oa_attachment_invoice_cache_entry("cache-key-001")

            self.assertEqual(cached, {"cache_key": "cache-key-001", "invoices": [{"invoice_no": "40512344"}]})

    def test_mongo_reset_oa_collections_retry_transient_autoreconnect(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            db = fake_client["fin_ops_platform_app"]
            cache_collection = FailOnceCollection(fail_method="delete_many")
            cache_collection.documents["cache-key-001"] = {"_id": "cache-key-001", "payload": Binary(pickle.dumps({}))}
            db.collections[OA_ATTACHMENT_INVOICE_CACHE_COLLECTION] = cache_collection
            read_model_collection = FailOnceCollection(fail_method="delete_many")
            read_model_collection.documents["all"] = {"_id": "all", "payload": Binary(pickle.dumps({}))}
            db.collections[WORKBENCH_READ_MODELS_COLLECTION] = read_model_collection

            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client):
                with patch(
                    "fin_ops_platform.services.state_store.GridFSBucket",
                    side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
                ):
                    store = ApplicationStateStore(data_dir)
                    deleted_count = store.clear_oa_attachment_invoice_cache()
                    store.save_workbench_read_models({})

            self.assertEqual(deleted_count, 1)
            self.assertEqual(cache_collection.delete_many_calls, 1)
            self.assertEqual(read_model_collection.delete_many_calls, 1)


if __name__ == "__main__":
    unittest.main()
