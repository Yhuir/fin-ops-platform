from __future__ import annotations

import json
from pathlib import Path
import pickle
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from bson.binary import Binary

from fin_ops_platform.services.state_store import ApplicationStateStore, GRIDFS_BUCKET_NAME
from fin_ops_platform.services.app_mongo_exporter import AppMongoExporter
from tests.test_state_store import FakeGridFSBucket, FakeMongoClient


class AppMongoExporterTests(unittest.TestCase):
    def test_export_writes_normalized_ndjson_manifest_and_gridfs_manifest_without_secrets(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "exports"
            data_dir.mkdir()
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps(
                    {
                        "host": "127.0.0.1",
                        "database": "fin_ops_platform_app",
                        "username": "app_user",
                        "password": "super-secret-password",
                        "auth_source": "admin",
                    }
                ),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client), patch(
                "fin_ops_platform.services.state_store.GridFSBucket",
                side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
            ):
                store = ApplicationStateStore(data_dir)
                store.save(
                    {
                        "imports": {
                            "batches": {
                                "batch-1": {
                                    "batch": {
                                        "id": "batch-1",
                                        "batch_type": "bank_transaction",
                                        "source_name": "bank.xlsx",
                                        "status": "completed",
                                    }
                                }
                            },
                            "invoices": [{"id": "invoice-1", "invoice_no": "INV-001", "amount": "10.00"}],
                            "transactions": [{"id": "txn-1", "amount": "10.00", "txn_direction": "inflow"}],
                        },
                        "file_imports": {
                            "sessions": {
                                "session-1": {
                                    "id": "session-1",
                                    "files": [
                                        {
                                            "id": "file-1",
                                            "file_name": "bank.xlsx",
                                            "stored_file_path": "gridfs://file-1/bank.xlsx",
                                            "batch_id": "batch-1",
                                        }
                                    ],
                                }
                            }
                        },
                        "matching": {},
                        "workbench_overrides": {
                            "row_overrides": {"row-1": {"case_id": "case-1", "detail_note": "keep"}}
                        },
                        "workbench_pair_relations": {
                            "pair_relations": {"case-1": {"case_id": "case-1", "status": "active"}}
                        },
                        "workbench_candidate_matches": {
                            "candidates": {"candidate-1": {"id": "candidate-1", "score": "0.95"}}
                        },
                    }
                )
                store.save_background_jobs({"job-1": {"id": "job-1", "status": "succeeded"}})
                db = fake_client["fin_ops_platform_app"]
                db[f"{GRIDFS_BUCKET_NAME}.files"].documents["file-1"] = {
                    "_id": "file-1",
                    "filename": "bank.xlsx",
                    "length": 123,
                    "chunkSize": 255,
                    "uploadDate": "2026-05-16T00:00:00+00:00",
                    "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    "metadata": {"session_id": "session-1"},
                }
                db[f"{GRIDFS_BUCKET_NAME}.chunks"].documents["chunk-1"] = {"_id": "chunk-1", "files_id": "file-1"}

                result = AppMongoExporter(store).export(output_dir=output_dir)

            manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest_text = json.dumps(manifest, ensure_ascii=False)
            self.assertNotIn("super-secret-password", manifest_text)
            self.assertEqual(manifest["schema_version"], "finops.app_mongo_export_manifest.v1")
            self.assertEqual(manifest["tool_version"], "app-mongo-export-v1")
            self.assertEqual(manifest["source"]["database"], "fin_ops_platform_app")
            self.assertEqual(manifest["source_database"], "fin_ops_platform_app")
            self.assertIn("export_started_at", manifest)
            self.assertIn("export_finished_at", manifest)
            self.assertIn("collection_counts", manifest)
            self.assertIn("import_batches", manifest["collection_counts"])
            self.assertEqual(manifest["record_counts"]["import_batches"], 1)
            self.assertEqual(manifest["record_counts"]["gridfs-files-manifest"], 1)
            self.assertEqual(manifest["output"]["files"]["import_batches"], "collections/import_batches.ndjson")
            self.assertIn("collections/import_batches.ndjson", manifest["checksums"])
            self.assertIn("manifest.json", manifest["output"]["manifest_file"])
            self.assertEqual(manifest["hashes"]["algorithm"], "sha256")
            self.assertEqual(
                manifest["hashes"]["files"]["collections/import_batches.ndjson"],
                manifest["checksums"]["collections/import_batches.ndjson"],
            )
            self.assertIn("aggregate_sha256", manifest["hashes"])
            self.assertFalse(manifest["validation"]["errors"])
            self.assertTrue(
                any(item["code"] == "EMPTY_COLLECTION" for item in manifest["validation"]["warnings"])
            )
            self.assertEqual(result.record_counts["bank_transactions"], 1)

            import_batches = (output_dir / "collections" / "import_batches.ndjson").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(import_batches), 1)
            self.assertEqual(json.loads(import_batches[0])["legacy_id"], "batch-1")
            self.assertEqual(
                json.loads((output_dir / "collections" / "gridfs-files-manifest.ndjson").read_text(encoding="utf-8"))[
                    "chunk_count"
                ],
                1,
            )
            self.assertEqual(
                json.loads((output_dir / "collections" / "gridfs-files-manifest.ndjson").read_text(encoding="utf-8"))[
                    "content_type"
                ],
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    def test_dry_run_returns_counts_without_writing_export_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "exports"
            data_dir.mkdir()
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client), patch(
                "fin_ops_platform.services.state_store.GridFSBucket",
                side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
            ):
                store = ApplicationStateStore(data_dir)
                db = fake_client["fin_ops_platform_app"]
                db["import_batches"].documents["batch-1"] = {
                    "_id": "batch-1",
                    "payload": Binary(pickle.dumps({"batch": {"id": "batch-1"}})),
                }

                result = AppMongoExporter(store).export(output_dir=output_dir, dry_run=True)

        self.assertFalse(output_dir.exists())
        self.assertEqual(result.record_counts["import_batches"], 1)
        self.assertIn("aggregate_sha256", result.manifest["hashes"])

    def test_duplicate_legacy_ids_are_reported_as_blocking_errors(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "exports"
            data_dir.mkdir()
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client), patch(
                "fin_ops_platform.services.state_store.GridFSBucket",
                side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
            ):
                store = ApplicationStateStore(data_dir)
                db = fake_client["fin_ops_platform_app"]
                db["bank_transactions"].documents["txn-doc-1"] = {
                    "_id": "txn-doc-1",
                    "payload": Binary(pickle.dumps({"id": "txn-duplicate", "amount": "1.00"})),
                }
                db["bank_transactions"].documents["txn-doc-2"] = {
                    "_id": "txn-doc-2",
                    "payload": Binary(pickle.dumps({"id": "txn-duplicate", "amount": "2.00"})),
                }

                result = AppMongoExporter(store).export(output_dir=output_dir, dry_run=True)

        self.assertTrue(result.manifest["validation"]["errors"])
        self.assertEqual(result.manifest["validation"]["errors"][0]["code"], "DUPLICATE_LEGACY_ID")
        self.assertEqual(result.manifest["validation"]["errors"][0]["object_type"], "bank_transactions")

    def test_invalid_json_payload_is_reported_without_silent_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "state"
            output_dir = Path(temp_dir) / "exports"
            data_dir.mkdir()
            (data_dir / "app_mongo_config.json").write_text(
                json.dumps({"host": "127.0.0.1", "database": "fin_ops_platform_app"}),
                encoding="utf-8",
            )
            fake_client = FakeMongoClient()
            with patch("fin_ops_platform.services.state_store.MongoClient", return_value=fake_client), patch(
                "fin_ops_platform.services.state_store.GridFSBucket",
                side_effect=lambda db, bucket_name: FakeGridFSBucket(db, bucket_name),
            ):
                store = ApplicationStateStore(data_dir)
                db = fake_client["fin_ops_platform_app"]
                db["app_settings"].documents["settings"] = {
                    "_id": "settings",
                    "payload": {"raw_binary": b"\x00\x01"},
                }

                result = AppMongoExporter(store).export(output_dir=output_dir, dry_run=True)

        error_codes = {item["code"] for item in result.manifest["validation"]["errors"]}
        self.assertIn("INVALID_JSON_PAYLOAD", error_codes)
        self.assertTrue(result.has_errors)

    def test_export_requires_mongo_backed_app_store(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))

            with self.assertRaisesRegex(RuntimeError, "app Mongo"):
                AppMongoExporter(store).export(output_dir=Path(temp_dir) / "exports")


if __name__ == "__main__":
    unittest.main()
