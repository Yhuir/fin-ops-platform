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


def _write_export(export_dir: Path, *, counts: dict[str, int] | None = None) -> None:
    export_dir.mkdir(parents=True)
    files = {
        "bank_transactions": "bank_transactions.ndjson",
        "invoices": "invoices.ndjson",
        "gridfs-files-manifest": "gridfs-files-manifest.ndjson",
    }
    manifest = {
        "tool": "app-mongo-export-v1",
        "source": {"database": "fin_ops_platform_app"},
        "started_at": "2026-05-16T00:00:00+00:00",
        "finished_at": "2026-05-16T00:01:00+00:00",
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
        "bank_transactions.ndjson": [
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
        "invoices.ndjson": [
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
                "filename": "bank.xlsx",
                "length": 42,
                "sha256": "abc",
                "sample_sha256": "abc",
            }
        ],
    }
    for filename, payload_rows in rows.items():
        path = export_dir / filename
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in payload_rows),
            encoding="utf-8",
        )
    manifest["checksums"] = {
        filename: AppMongoStagingImportBuilder.file_sha256(export_dir / filename)
        for filename in rows
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


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
    def test_build_plan_uses_migration_run_id_as_manifest_id_and_creates_staging_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir)

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="11111111-1111-4111-8111-111111111111",
            )

        self.assertFalse(plan.report.has_blocking_findings)
        self.assertEqual(plan.manifest_record["id"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual(plan.manifest_record["source_database"], "fin_ops_platform_app")
        self.assertEqual(len(plan.rows), 3)
        self.assertTrue(all(row["manifest_id"] == plan.manifest_record["id"] for row in plan.rows))
        self.assertEqual(plan.rows[0]["status"], "parsed")
        self.assertIsNot(plan.report.source_metrics, plan.report.actual_metrics)
        self.assertEqual(plan.report.source_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(plan.report.actual_metrics["record_counts"]["bank_transactions"], 1)

    def test_invalid_ndjson_is_preserved_as_blocking_failure_with_row_location(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir, counts={"bank_transactions": 2, "invoices": 1, "gridfs-files-manifest": 1})
            with (export_dir / "bank_transactions.ndjson").open("a", encoding="utf-8") as handle:
                handle.write("{bad json\n")

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="22222222-2222-4222-8222-222222222222",
            )

        self.assertTrue(plan.report.has_blocking_findings)
        finding = next(item for item in plan.report.findings if item["code"] == "NDJSON_PARSE_ERROR")
        self.assertEqual(finding["object_type"], "bank_transactions")
        self.assertEqual(finding["row_no"], 2)

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
            row["sample_sha256"] = "different"
            (export_dir / "gridfs-files-manifest.ndjson").write_text(json.dumps(row) + "\n", encoding="utf-8")

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="33333333-3333-4333-8333-333333333333",
            )

        self.assertTrue(plan.report.has_blocking_findings)
        self.assertIn("FILE_CHECKSUM_MISMATCH", {item["code"] for item in plan.report.findings})

    def test_duplicate_legacy_id_blocks_report(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_export(export_dir, counts={"bank_transactions": 2, "invoices": 1, "gridfs-files-manifest": 1})
            first_line = (export_dir / "bank_transactions.ndjson").read_text(encoding="utf-8")
            with (export_dir / "bank_transactions.ndjson").open("a", encoding="utf-8") as handle:
                handle.write(first_line)

            plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="55555555-5555-4555-8555-555555555555",
            )

        self.assertTrue(plan.report.has_blocking_findings)
        self.assertIn("DUPLICATE_LEGACY_ID", {item["code"] for item in plan.report.findings})

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
        self.assertTrue(connection.committed)


if __name__ == "__main__":
    unittest.main()
