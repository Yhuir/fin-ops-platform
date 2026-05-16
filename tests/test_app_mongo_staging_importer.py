from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.app_mongo_staging_importer import (
    AppMongoStagingImportBuilder,
    StagingImportExecutor,
    compare_metric_snapshots,
)


def _write_export(export_dir: Path, *, counts: dict[str, int] | None = None) -> dict[str, object]:
    export_dir.mkdir(parents=True)
    files = {
        "bank_transactions": "collections/bank_transactions.ndjson",
        "invoices": "collections/invoices.ndjson",
        "gridfs-files-manifest": "gridfs-files-manifest.ndjson",
    }
    manifest: dict[str, object] = {
        "tool": "app-mongo-export-v1",
        "schema_version": 1,
        "source": {"database": "fin_ops_platform_app"},
        "export_started_at": "2026-05-16T00:00:00+00:00",
        "export_finished_at": "2026-05-16T00:01:00+00:00",
        "output": {"files": files},
        "record_counts": counts
        or {
            "bank_transactions": 1,
            "invoices": 1,
            "gridfs-files-manifest": 1,
        },
        "checksums": {},
    }
    rows = {
        "collections/bank_transactions.ndjson": [
            {
                "legacy_collection": "bank_transactions",
                "legacy_id": "txn-1",
                "payload": {
                    "id": "txn-1",
                    "amount": "10.00",
                    "signed_amount": "10.00",
                    "txn_direction": "inflow",
                    "txn_date": "2026-05-02",
                    "status": "pending",
                },
            }
        ],
        "collections/invoices.ndjson": [
            {
                "legacy_collection": "invoices",
                "legacy_id": "inv-1",
                "payload": {
                    "id": "inv-1",
                    "amount": "10.00",
                    "invoice_date": "2026-05-01",
                    "invoice_type": "input",
                    "status": "pending",
                },
            }
        ],
        "gridfs-files-manifest.ndjson": [
            {
                "legacy_collection": "import_file_blobs.files",
                "legacy_id": "file-1",
                "payload": {
                    "filename": "bank.xlsx",
                    "length": 42,
                    "sha256": "abc",
                    "sample_sha256": "abc",
                },
            }
        ],
    }
    for filename, payload_rows in rows.items():
        path = export_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in payload_rows),
            encoding="utf-8",
        )
    manifest["checksums"] = {
        filename: AppMongoStagingImportBuilder.file_sha256(export_dir / filename)
        for filename in rows
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


class FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.calls.append((sql, params))


class FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True


class AppMongoStagingImporterTests(unittest.TestCase):
    def test_build_plan_generates_run_id_and_report_go_for_valid_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)

            plan = AppMongoStagingImportBuilder().build_plan(export_dir=export_dir)

        self.assertFalse(plan.report.has_blocking_findings)
        self.assertEqual(plan.report.decision["go_no_go"], "GO")
        self.assertEqual(plan.manifest_record["id"], plan.migration_run_id)
        self.assertEqual(plan.report.migration_run_id, plan.migration_run_id)
        self.assertEqual(plan.report.expected_collection_counts["bank_transactions"], 1)
        self.assertEqual(plan.report.actual_imported_counts["bank_transactions"], 1)
        self.assertEqual(plan.report.failed_row_counts, {})
        self.assertIn("started_at", plan.report.to_dict())
        self.assertIn("finished_at", plan.report.to_dict())
        self.assertEqual(len(plan.rows), 3)

    def test_staging_rows_keep_source_location_hash_payload_and_import_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="11111111-1111-4111-8111-111111111111",
            )

        row = next(item for item in plan.rows if item["legacy_collection"] == "bank_transactions")
        self.assertEqual(row["source_file"], "collections/bank_transactions.ndjson")
        self.assertEqual(row["source_line"], 1)
        self.assertEqual(row["import_status"], "parsed")
        self.assertEqual(row["status"], "parsed")
        self.assertEqual(row["row_hash"], row["payload_hash"])
        self.assertEqual(row["raw_payload"]["legacy_id"], "txn-1")
        self.assertEqual(row["payload"]["_staging_import"]["source_file"], "collections/bank_transactions.ndjson")
        self.assertEqual(row["payload"]["_staging_import"]["source_line"], 1)

    def test_invalid_ndjson_is_preserved_as_failed_staging_row_and_no_go(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir, counts={"bank_transactions": 2, "invoices": 1, "gridfs-files-manifest": 1})
            with (export_dir / "collections/bank_transactions.ndjson").open("a", encoding="utf-8") as handle:
                handle.write("{bad json\n")

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="22222222-2222-4222-8222-222222222222",
            )

        self.assertTrue(plan.report.has_blocking_findings)
        self.assertEqual(plan.report.decision["go_no_go"], "NO_GO")
        failed_row = next(row for row in plan.rows if row["status"] == "failed")
        self.assertEqual(failed_row["legacy_collection"], "bank_transactions")
        self.assertEqual(failed_row["source_line"], 2)
        self.assertEqual(failed_row["error_code"], "NDJSON_PARSE_ERROR")
        self.assertIn("raw_line", failed_row["raw_payload"])
        self.assertEqual(plan.report.failed_row_counts["bank_transactions"], 1)
        self.assertEqual(plan.report.actual_imported_counts["bank_transactions"], 1)

    def test_manifest_checksum_validation_is_reported_by_input_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)
            with (export_dir / "collections/invoices.ndjson").open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {"legacy_collection": "invoices", "legacy_id": "inv-2", "payload": {"amount": "2.00"}},
                        sort_keys=True,
                    )
                    + "\n"
                )

            plan = AppMongoStagingImportBuilder().build_plan(export_dir=export_dir)

        self.assertEqual(plan.report.decision["go_no_go"], "NO_GO")
        validation = plan.report.input_file_hash_validation["collections/invoices.ndjson"]
        self.assertFalse(validation["matched"])
        self.assertIn("FILE_CHECKSUM_MISMATCH", {item["code"] for item in plan.report.findings})

    def test_duplicate_legacy_id_marks_later_row_failed_to_avoid_staging_unique_conflict(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir, counts={"bank_transactions": 2, "invoices": 1, "gridfs-files-manifest": 1})
            first_line = (export_dir / "collections/bank_transactions.ndjson").read_text(encoding="utf-8")
            with (export_dir / "collections/bank_transactions.ndjson").open("a", encoding="utf-8") as handle:
                handle.write(first_line)

            plan = AppMongoStagingImportBuilder().build_plan(export_dir=export_dir)

        self.assertTrue(plan.report.has_blocking_findings)
        duplicate_row = next(row for row in plan.rows if row["error_code"] == "DUPLICATE_LEGACY_ID")
        self.assertEqual(duplicate_row["status"], "failed")
        self.assertTrue(duplicate_row["legacy_id"].startswith("__duplicate__:"))

    def test_metric_comparison_blocks_count_and_amount_differences(self) -> None:
        expected = {
            "record_counts": {"bank_transactions": 1},
            "amount_totals": {"bank_transactions.amount": "10.00"},
            "month_distribution": {"bank_transactions": {"2026-05": 1}},
            "status_distribution": {"bank_transactions": {"pending": 1}},
            "file_checksum_samples": [],
        }
        actual = {
            "record_counts": {"bank_transactions": 2},
            "amount_totals": {"bank_transactions.amount": "9.99"},
            "month_distribution": {"bank_transactions": {"2026-05": 2}},
            "status_distribution": {"bank_transactions": {"pending": 2}},
            "file_checksum_samples": [],
        }

        report = compare_metric_snapshots(expected, actual)

        self.assertTrue(report.has_blocking_findings)
        self.assertIn("COUNT_MISMATCH", {item["code"] for item in report.findings})
        self.assertIn("AMOUNT_MISMATCH", {item["code"] for item in report.findings})

    def test_file_checksum_sample_mismatch_blocks_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)
            records = (export_dir / "gridfs-files-manifest.ndjson").read_text(encoding="utf-8").splitlines()
            row = json.loads(records[0])
            row["payload"]["sample_sha256"] = "different"
            (export_dir / "gridfs-files-manifest.ndjson").write_text(json.dumps(row) + "\n", encoding="utf-8")

            plan = AppMongoStagingImportBuilder().build_plan(export_dir=export_dir)

        self.assertTrue(plan.report.has_blocking_findings)
        self.assertIn("FILE_CHECKSUM_MISMATCH", {item["code"] for item in plan.report.findings})

    def test_executor_writes_only_staging_manifest_and_import_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)
            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="44444444-4444-4444-8444-444444444444",
            )
            connection = FakeConnection()

            StagingImportExecutor().execute(connection, plan)

        sql = "\n".join(call[0] for call in connection.cursor_obj.calls)
        self.assertIn("staging.mongo_export_manifest", sql)
        self.assertIn("staging.mongo_import_rows", sql)
        self.assertNotIn(" app.", sql)
        self.assertNotIn("read_model.", sql)
        self.assertNotIn("job.", sql)
        self.assertNotIn("audit.", sql)
        self.assertTrue(connection.committed)


if __name__ == "__main__":
    unittest.main()
