from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.services.app_mongo_migration_dry_run import (
    AppMongoMigrationDryRunBuilder,
    DATASET_MAPPINGS,
    DatasetMapping,
    PROMPT_B_REQUIRED_DOMAINS,
    dataset_mapping_summary,
)


def _fixture_records(*, invoice_status: str = "pending") -> dict[str, list[dict[str, object]]]:
    return {
        "bank_transactions": [
            {
                "legacy_collection": "bank_transactions",
                "legacy_id": "txn-1",
                "payload": {
                    "id": "txn-1",
                    "account_no": "62220001",
                    "amount": "125.50",
                    "signed_amount": "125.50",
                    "counterparty_name_raw": "Acme Buyer",
                    "txn_direction": "inflow",
                    "txn_date": "2026-05-02",
                    "status": "pending",
                },
            }
        ],
        "invoices": [
            {
                "legacy_collection": "invoices",
                "legacy_id": "inv-1",
                "payload": {
                    "id": "inv-1",
                    "amount": "125.50",
                    "buyer_name": "Acme Buyer",
                    "invoice_date": "2026-05-01",
                    "invoice_no": "INV-001",
                    "invoice_type": "output",
                    "seller_name": "Fin Ops Ltd",
                    "signed_amount": "125.50",
                    "status": invoice_status,
                    "tax_amount": "7.53",
                    "total_with_tax": "133.03",
                },
            }
        ],
        "workbench_pair_relations": [
            {
                "legacy_collection": "workbench_pair_relations",
                "legacy_id": "case-1",
                "payload": {
                    "case_id": "case-1",
                    "amount": "125.50",
                    "created_by": "migration-test",
                    "row_ids": ["txn-1", "inv-1"],
                    "row_types": ["bank", "invoice"],
                    "status": "confirmed",
                },
            }
        ],
        "background_jobs": [
            {
                "legacy_collection": "background_jobs",
                "legacy_id": "job-1",
                "payload": {
                    "id": "job-1",
                    "job_type": "workbench_rebuild",
                    "label": "Workbench rebuild",
                    "status": "succeeded",
                    "total_count": 1,
                    "current_count": 1,
                },
            }
        ],
    }


def _write_fixture_export(export_dir: Path, *, records: dict[str, list[dict[str, object]]] | None = None) -> None:
    export_dir.mkdir(parents=True)
    fixture = records or _fixture_records()
    files = {dataset: f"collections/{dataset}.ndjson" for dataset in sorted(fixture)}
    for dataset, filename in files.items():
        rows = fixture[dataset]
        output_path = export_dir / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
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
            filename: AppMongoMigrationDryRunBuilder.file_sha256(export_dir / filename)
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

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                migration_run_id="66666666-6666-4666-8666-666666666666",
            )

        self.assertEqual(report.decision["go_no_go"], "GO")
        self.assertFalse(report.has_blockers)
        self.assertIsNot(report.source_metrics, report.staging_metrics)
        self.assertIsNot(report.staging_metrics, report.target_metrics)
        self.assertEqual(report.source_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.staging_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.target_metrics["record_counts"]["bank_transactions"], 1)
        self.assertEqual(report.legacy_id_coverage["expected"], 4)
        self.assertEqual(report.legacy_id_coverage["mapped"], 4)
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
        self.assertEqual(report.file_checksum_scope["owner_phase"], "06D")
        self.assertEqual(report.file_checksum_scope["status"], "not_evaluated_in_06c")
        self.assertIn("go/no-go | `GO`", report.to_markdown())

    def test_unmapped_staging_row_blocks_report_with_failed_row_reason(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir)
            manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest["output"]["files"]["unknown_dataset"] = "collections/unknown_dataset.ndjson"
            manifest["record_counts"]["unknown_dataset"] = 1
            row = {
                "legacy_collection": "unknown_dataset",
                "legacy_id": "unknown-1",
                "payload": {"id": "unknown-1", "status": "pending"},
            }
            unknown_path = export_dir / "collections/unknown_dataset.ndjson"
            unknown_path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
            manifest["checksums"]["collections/unknown_dataset.ndjson"] = AppMongoMigrationDryRunBuilder.file_sha256(
                unknown_path
            )
            (export_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                migration_run_id="77777777-7777-4777-8777-777777777777",
            )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "MAPPING_BLOCKER")
        self.assertEqual(finding["object_type"], "unknown_dataset")
        self.assertEqual(finding["legacy_id"], "unknown-1")
        self.assertEqual(finding["dimension"], "legacy_id_coverage")
        self.assertIn("source_line", finding)

    def test_invalid_enum_blocks_report_with_locatable_finding(self) -> None:
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir, records=_fixture_records(invoice_status="mystery"))

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                migration_run_id="88888888-8888-4888-8888-888888888888",
            )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "INVALID_ENUM")
        self.assertEqual(finding["object_type"], "invoices")
        self.assertEqual(finding["legacy_id"], "inv-1")
        self.assertEqual(finding["status"], "mystery")
        self.assertEqual(finding["source_line"], 1)
        self.assertEqual(report.unmapped_invalid_enums["invoices"]["status"], ["mystery"])

    def test_known_blocker_datasets_have_explicit_contracts(self) -> None:
        summary = dataset_mapping_summary()

        self.assertEqual(summary["etc_state"]["target_tables"], ["audit.events"])
        self.assertEqual(summary["etc_state"]["migration_strategy"], "archive_raw_payload")
        self.assertIn("ETC legacy aggregate state", summary["etc_state"]["exclusion_reason"])
        self.assertEqual(summary["etc_reconciliation_state"]["target_tables"], ["audit.events"])
        self.assertEqual(summary["etc_reconciliation_state"]["migration_strategy"], "archive_raw_payload")
        self.assertIn("ETC reconciliation legacy aggregate state", summary["etc_reconciliation_state"]["exclusion_reason"])

    def test_legacy_status_normalization_maps_known_blockers_and_preserves_raw_status(self) -> None:
        records = _fixture_records()
        records["background_jobs"][0]["payload"]["status"] = "acknowledged"
        records["workbench_pair_relations"][0]["payload"]["status"] = "active"
        records["workbench_candidate_matches"] = [
            {
                "legacy_collection": "workbench_candidate_matches",
                "legacy_id": "candidate-1",
                "payload": {
                    "candidate_id": "candidate-1",
                    "candidate_key": "candidate-1",
                    "scope_month": "2026-05",
                    "status": "needs_review",
                    "amount": "125.50",
                },
            },
            {
                "legacy_collection": "workbench_candidate_matches",
                "legacy_id": "candidate-2",
                "payload": {
                    "candidate_id": "candidate-2",
                    "candidate_key": "candidate-2",
                    "scope_month": "2026-05",
                    "status": "suppressed",
                    "amount": "125.50",
                },
            },
        ]
        records["etc_state"] = [
            {
                "legacy_collection": "etc_state",
                "legacy_id": "current_state",
                "payload": {"batches": {}, "invoices": {}},
            }
        ]
        records["etc_reconciliation_state"] = [
            {
                "legacy_collection": "etc_reconciliation_state",
                "legacy_id": "current_state",
                "payload": {"tasks": {}, "schema_version": 1},
            }
        ]

        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir, records=records)

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                migration_run_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            )

        self.assertEqual(report.decision["go_no_go"], "GO")
        self.assertEqual(report.legacy_id_coverage["expected"], 8)
        self.assertEqual(report.legacy_id_coverage["mapped"], 8)
        payload_by_legacy_id = {row["legacy_id"]: row["payload"] for row in report.target_rows}
        self.assertEqual(payload_by_legacy_id["job-1"]["status"], "succeeded")
        self.assertEqual(payload_by_legacy_id["job-1"]["migration_metadata"]["legacy_status"], "acknowledged")
        self.assertEqual(payload_by_legacy_id["case-1"]["status"], "confirmed")
        self.assertEqual(payload_by_legacy_id["case-1"]["migration_metadata"]["legacy_status"], "active")
        self.assertEqual(payload_by_legacy_id["candidate-1"]["status"], "active")
        self.assertEqual(payload_by_legacy_id["candidate-1"]["migration_metadata"]["legacy_status"], "needs_review")
        self.assertEqual(payload_by_legacy_id["candidate-2"]["status"], "dismissed")
        self.assertEqual(payload_by_legacy_id["candidate-2"]["migration_metadata"]["legacy_status"], "suppressed")

    def test_each_known_legacy_status_mapping_is_explicitly_supported(self) -> None:
        cases = {
            "background_jobs": {
                "acknowledged": "succeeded",
                "superseded": "cancelled",
            },
            "workbench_candidate_matches": {
                "needs_review": "active",
                "suppressed": "dismissed",
                "incomplete": "active",
                "auto_closed": "active",
                "conflict": "active",
            },
            "workbench_pair_relations": {
                "active": "confirmed",
            },
        }

        for dataset, status_cases in cases.items():
            mapping = DATASET_MAPPINGS[dataset]
            for legacy_status, target_status in status_cases.items():
                with self.subTest(dataset=dataset, legacy_status=legacy_status):
                    self.assertEqual(mapping.normalized_status(legacy_status), target_status)

    def test_unknown_legacy_status_still_blocks_after_normalization_contract(self) -> None:
        records = _fixture_records()
        records["workbench_candidate_matches"] = [
            {
                "legacy_collection": "workbench_candidate_matches",
                "legacy_id": "candidate-unknown",
                "payload": {
                    "candidate_id": "candidate-unknown",
                    "candidate_key": "candidate-unknown",
                    "scope_month": "2026-05",
                    "status": "mystery",
                    "amount": "1.00",
                },
            }
        ]
        with TemporaryDirectory() as temp_dir:
            export_dir = Path(temp_dir) / "export"
            _write_fixture_export(export_dir, records=records)

            report = AppMongoMigrationDryRunBuilder().build_report(
                export_dir=export_dir,
                migration_run_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
            )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "INVALID_ENUM")
        self.assertEqual(finding["object_type"], "workbench_candidate_matches")
        self.assertEqual(finding["legacy_id"], "candidate-unknown")
        self.assertEqual(finding["status"], "mystery")

    def test_empty_dataset_count_does_not_block_when_staging_omits_absent_key(self) -> None:
        builder = AppMongoMigrationDryRunBuilder()
        findings = builder._compare_mapping(
            code="COUNT_MISMATCH",
            dimension="record_counts",
            expected={"empty_dataset": 0, "non_empty_dataset": 1},
            actual={"non_empty_dataset": 1},
        )

        self.assertEqual(findings, [])

    def test_excluded_dataset_does_not_inflate_legacy_id_map_coverage(self) -> None:
        DATASET_MAPPINGS["excluded_unit_dataset"] = DatasetMapping(
            "excluded_unit_dataset",
            ("excluded_unit_dataset",),
            (),
            ("settings",),
            migrates=False,
            migration_strategy="exclude",
            exclusion_reason="Unit test exclusion reason.",
        )
        try:
            report = AppMongoMigrationDryRunBuilder().build_report_from_staging_rows(
                migration_run_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                staging_rows=[
                    {
                        "manifest_id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                        "legacy_collection": "excluded_unit_dataset",
                        "legacy_id": "excluded-1",
                        "row_no": 1,
                        "payload": {
                            "legacy_collection": "excluded_unit_dataset",
                            "legacy_id": "excluded-1",
                            "payload": {"status": "archived"},
                        },
                        "payload_hash": AppMongoMigrationDryRunBuilder.record_sha256(
                            {
                                "legacy_collection": "excluded_unit_dataset",
                                "legacy_id": "excluded-1",
                                "payload": {"status": "archived"},
                            }
                        ),
                        "target_table": None,
                        "status": "parsed",
                    }
                ],
                manifest_record={
                    "id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                    "source_database": "fin_ops_platform_app",
                    "export_name": "unit-fixture",
                    "sha256_manifest": "not-a-file-checksum",
                },
            )
        finally:
            DATASET_MAPPINGS.pop("excluded_unit_dataset", None)

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        self.assertEqual(report.legacy_id_coverage["expected"], 1)
        self.assertEqual(report.legacy_id_coverage["mapped"], 0)
        finding = next(item for item in report.findings if item["code"] == "MAPPING_BLOCKER")
        self.assertEqual(finding["object_type"], "excluded_unit_dataset")
        self.assertIn("Unit test exclusion reason.", finding["message"])

    def test_staging_failed_row_blocks_as_blocked_fact_source(self) -> None:
        staging_rows = AppMongoMigrationDryRunBuilder().build_staging_rows_from_records(
            records_by_dataset=_fixture_records(),
            migration_run_id="99999999-9999-4999-8999-999999999999",
        )
        failed_row = next(row for row in staging_rows if row["legacy_id"] == "txn-1")
        failed_row["status"] = "failed"
        failed_row["error_code"] = "STAGING_PARSE_ERROR"
        failed_row["error_message"] = "row failed before conversion"

        report = AppMongoMigrationDryRunBuilder().build_report_from_staging_rows(
            migration_run_id="99999999-9999-4999-8999-999999999999",
            staging_rows=staging_rows,
            manifest_record={
                "id": "99999999-9999-4999-8999-999999999999",
                "source_database": "fin_ops_platform_app",
                "export_name": "unit-fixture",
                "sha256_manifest": "not-a-file-checksum",
            },
        )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "BLOCKED_FACT_SOURCE")
        self.assertEqual(finding["object_type"], "bank_transactions")
        self.assertEqual(finding["legacy_id"], "txn-1")
        self.assertEqual(finding["source_line"], 1)
        self.assertEqual(finding["dimension"], "staging_status")

    def test_payload_hash_mismatch_blocks_report(self) -> None:
        staging_rows = AppMongoMigrationDryRunBuilder().build_staging_rows_from_records(
            records_by_dataset=_fixture_records(),
            migration_run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        )
        mismatched_row = next(row for row in staging_rows if row["legacy_id"] == "txn-1")
        mismatched_row["payload_hash"] = "0" * 64

        report = AppMongoMigrationDryRunBuilder().build_report_from_staging_rows(
            migration_run_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            staging_rows=staging_rows,
            manifest_record={
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                "source_database": "fin_ops_platform_app",
                "export_name": "unit-fixture",
                "sha256_manifest": "not-a-file-checksum",
            },
        )

        self.assertEqual(report.decision["go_no_go"], "NO_GO")
        finding = next(item for item in report.findings if item["code"] == "ROW_HASH_MISMATCH")
        self.assertEqual(finding["object_type"], "bank_transactions")
        self.assertEqual(finding["legacy_id"], "txn-1")
        self.assertEqual(finding["source_line"], 1)


if __name__ == "__main__":
    unittest.main()
