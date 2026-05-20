from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
import pickle
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bson.binary import Binary

from fin_ops_platform.services.state_store import ApplicationStateStore, DEFAULT_APP_MONGO_DATABASE
from fin_ops_platform.tools.export_app_mongo import export_app_mongo
from fin_ops_platform.tools.exporters import all_export_definitions


class FakeCollection:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self.documents = list(documents or [])
        self.update_one_calls = 0
        self.replace_one_calls = 0
        self.delete_many_calls = 0

    def find(self, query: dict | None = None) -> list[dict]:
        if not query:
            return list(self.documents)
        return [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]

    def count_documents(self, query: dict | None = None) -> int:
        return len(self.find(query))


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


class FakeStream:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class FakeBucket:
    def open_download_stream(self, file_id: str) -> FakeStream:
        return FakeStream(f"content:{file_id}".encode("utf-8"))


def binary_payload(payload: dict) -> Binary:
    return Binary(pickle.dumps(payload))


def make_fake_store() -> ApplicationStateStore:
    store = object.__new__(ApplicationStateStore)
    database = FakeDatabase()
    collections = {
        definition.source_collection
        for definition in all_export_definitions()
        if definition.source_collection is not None
    }
    detailed = {name: FakeCollection() for name in collections}
    detailed["import_batches"] = FakeCollection(
        [
            {
                "_id": "batch-1",
                "payload": binary_payload(
                    {
                        "id": "batch-1",
                        "batch_type": "invoice",
                        "row_results": [{"decision": "created", "raw_payload": {"发票号码": "001"}}],
                        "normalized_rows": [{"invoice_no": "001", "amount": Decimal("12.30")}],
                    }
                ),
            }
        ]
    )
    detailed["invoices"] = FakeCollection(
        [
            {
                "_id": "invoice-1",
                "payload": binary_payload(
                    {
                        "id": "invoice-1",
                        "invoice_no": "001",
                        "amount": Decimal("12.30"),
                        "created_at": datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
                    }
                ),
            }
        ]
    )
    store._loaded_snapshot = {
        "pending_invoice_commands": {
            "cmd-1": {
                "request_id": "cmd-1",
                "request_key": "manual-pending-invoice:bank-1:expense:digest",
                "status": "failed_recoverable",
                "status_history": ["started", "invoice_created", "failed_recoverable"],
                "invoice_id": "invoice-1",
                "last_successful_status": "invoice_created",
                "created_at": "2026-05-20T10:00:00+00:00",
                "updated_at": "2026-05-20T10:01:00+00:00",
            }
        }
    }
    store.load = lambda: store._loaded_snapshot
    database.collections["import_file_blobs.files"] = FakeCollection(
        [
            {
                "_id": "file-1",
                "filename": "source.xlsx",
                "length": 14,
                "chunkSize": 255,
                "uploadDate": datetime(2026, 5, 20, 8, 30, tzinfo=UTC),
                "metadata": {"session_id": "session-1", "file_id": "file-1", "content_type": "application/vnd.ms-excel"},
            }
        ]
    )
    database.collections["import_file_blobs.chunks"] = FakeCollection([{"_id": "chunk-1"}])
    store._mongo_detailed_collections = detailed
    store._mongo_database = database
    store._mongo_file_bucket = FakeBucket()
    store._mongo_settings = SimpleNamespace(database=DEFAULT_APP_MONGO_DATABASE)
    store._storage_mode = "mongo_only"
    store._read_only = True
    return store


class ExportAppMongoTests(unittest.TestCase):
    def test_export_definitions_include_snapshot_meta_domains_needed_for_shadow_read(self) -> None:
        source_collections = {
            definition.source_collection
            for definition in all_export_definitions()
            if definition.source_collection is not None
        }

        self.assertIn("no_oa_bank_batches_meta", source_collections)
        self.assertIn("turnover_relations_meta", source_collections)
        self.assertIn("bank_transaction_categories_meta", source_collections)
        self.assertIn("pending_invoice_commands", source_collections)

    def test_export_generates_manifest_ndjson_counts_and_uses_read_only_store(self) -> None:
        fake_store = make_fake_store()
        with TemporaryDirectory() as temp_dir:
            with patch("fin_ops_platform.tools.export_app_mongo.ApplicationStateStore", return_value=fake_store):
                result = export_app_mongo(
                    output_root=Path(temp_dir),
                    source_mode="production",
                    source_database=DEFAULT_APP_MONGO_DATABASE,
                    data_dir=None,
                    dry_run=False,
                    force=False,
                    export_id="unit-export",
                )
            export_dir = Path(result["export_dir"])
            manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
            invoice_lines = (export_dir / "invoices.ndjson").read_text(encoding="utf-8").splitlines()
            row_lines = (export_dir / "import_batch_rows.ndjson").read_text(encoding="utf-8").splitlines()
            file_object_lines = (export_dir / "file_objects.ndjson").read_text(encoding="utf-8").splitlines()
            command_lines = (export_dir / "pending_invoice_manual_invoice_commands.ndjson").read_text(encoding="utf-8").splitlines()

        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["files"]["invoices.ndjson"]["record_count"], 1)
        self.assertEqual(manifest["files"]["import_batch_rows.ndjson"]["record_count"], 1)
        self.assertEqual(manifest["files"]["pending_invoice_manual_invoice_commands.ndjson"]["record_count"], 1)
        self.assertEqual(manifest["gridfs"]["files_count"], 1)
        self.assertIn('"amount":"12.30"', invoice_lines[0])
        self.assertIn('"source_collection":"import_batches:row_results"', row_lines[0])
        self.assertIn('"source_collection":"file_objects"', file_object_lines[0])
        self.assertIn('"source_collection":"pending_invoice_manual_invoice_commands"', command_lines[0])
        self.assertIn('"request_id":"cmd-1"', command_lines[0])
        for collection in fake_store._mongo_detailed_collections.values():
            self.assertEqual(collection.update_one_calls, 0)
            self.assertEqual(collection.replace_one_calls, 0)
            self.assertEqual(collection.delete_many_calls, 0)

    def test_completed_export_directory_cannot_be_overwritten(self) -> None:
        fake_store = make_fake_store()
        with TemporaryDirectory() as temp_dir:
            with patch("fin_ops_platform.tools.export_app_mongo.ApplicationStateStore", return_value=fake_store):
                export_app_mongo(
                    output_root=Path(temp_dir),
                    source_mode="production",
                    source_database=DEFAULT_APP_MONGO_DATABASE,
                    data_dir=None,
                    dry_run=False,
                    force=False,
                    export_id="unit-export",
                )
                with self.assertRaises(RuntimeError):
                    export_app_mongo(
                        output_root=Path(temp_dir),
                        source_mode="production",
                        source_database=DEFAULT_APP_MONGO_DATABASE,
                        data_dir=None,
                        dry_run=False,
                        force=True,
                        export_id="unit-export",
                    )
