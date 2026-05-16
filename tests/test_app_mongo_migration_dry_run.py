from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.app_mongo_exporter import EXPORT_FILE_NAMES
from fin_ops_platform.services.app_mongo_migration_dry_run import (
    AppMongoMigrationDryRunBuilder,
    PROMPT_B_REQUIRED_DOMAINS,
    dataset_mapping_summary,
)
from fin_ops_platform.services.app_mongo_staging_importer import AppMongoStagingImportBuilder


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "app_mongo_dry_run_export" / "source_records.json"


def _write_fixture_export(export_dir: Path) -> None:
    export_dir.mkdir(parents=True)
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    files = {
        dataset: EXPORT_FILE_NAMES.get(dataset, f"{dataset}.ndjson")
        for dataset in sorted(fixture)
    }
    for dataset, filename in files.items():
        rows = fixture[dataset]
        (export_dir / filename).write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    manifest = {
        "tool": "app-mongo-export-v1",
        "dry_run": False,
        "source": {"database": "fin_ops_platform_app"},
        "started_at": "2026-05-16T00:00:00+00:00",
        "finished_at": "2026-05-16T00:01:00+00:00",
        "output": {"files": files},
        "record_counts": {dataset: len(rows) for dataset, rows in sorted(fixture.items())},
        "checksums": {
            filename: AppMongoStagingImportBuilder.file_sha256(export_dir / filename)
            for filename in files.values()
        },
    }
    (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


class AppMongoMigrationDryRunTests(unittest.TestCase):
    def test_mapping_registry_covers_prompt_b_domains(self) -> None:
        summary = dataset_mapping_summary()
        covered_domains = {
            domain
            for item in summary.values()
            for domain in item["domains"]
        }

        self.assertTrue(set(PROMPT_B_REQUIRED_DOMAINS).issubset(covered_domains))
        self.assertEqual(summary["bank_transactions"]["target_tables"], ["app.bank_transactions"])
        self.assertIn("staging.legacy_id_map", summary["bank_transactions"]["supporting_tables"])
        self.assertIn("read_model.tax_offset_read_models", summary["tax_offset_read_models"]["target_tables"])

    def test_fixture_export_builds_go_dry_run_with_separate_metrics_and_legacy_coverage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir)
            staging_plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="66666666-6666-4666-8666-666666666666",
            )

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                staging_plan=staging_plan,
                migration_run_id="66666666-6666-4666-8666-666666666666",
            )

        self.assertEqual(report.decision["go_no_go"], "GO")
        self.assertFalse(report.has_blockers)
        self.assertIsNot(report.source_metrics, report.staging_metrics)
        self.assertIsNot(report.staging_metrics, report.target_metrics)
        self.assertEqual(report.source_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.staging_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.target_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.legacy_id_coverage["expected"], 5)
        self.assertEqual(report.legacy_id_coverage["mapped"], 5)
        self.assertEqual(report.partition_plan["month_range"], {"min": "2026-05", "max": "2026-05"})
        self.assertIn(
            {
                "schema": "app",
                "parent_table": "bank_transactions",
                "month": "2026-05",
                "status": "planned",
            },
            report.partition_plan["prepared_partitions"],
        )
        self.assertIn("go/no-go | `GO`", report.to_markdown())

    def test_unmapped_staging_row_blocks_report_with_failed_row_reason(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir)
            manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["output"]["files"]["unknown_dataset"] = "unknown_dataset.ndjson"
            manifest["record_counts"]["unknown_dataset"] = 1
            row = {
                "legacy_collection": "unknown_dataset",
                "legacy_id": "unknown-1",
                "payload": {"id": "unknown-1", "status": "pending"},
            }
            (export_dir / "unknown_dataset.ndjson").write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
            manifest["checksums"]["unknown_dataset.ndjson"] = AppMongoStagingImportBuilder.file_sha256(
                export_dir / "unknown_dataset.ndjson"
            )
            (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            staging_plan = AppMongoStagingImportBuilder().build_plan(
                export_dir=export_dir,
                migration_run_id="77777777-7777-4777-8777-777777777777",
            )

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                staging_plan=staging_plan,
                migration_run_id="77777777-7777-4777-8777-777777777777",
            )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "UNMAPPED_LEGACY_ID")
        self.assertEqual(finding["object_type"], "unknown_dataset")
        self.assertEqual(finding["legacy_id"], "unknown-1")
        self.assertEqual(finding["dimension"], "legacy_id_coverage")


if __name__ == "__main__":
    unittest.main()
