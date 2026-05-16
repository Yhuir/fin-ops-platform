from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from fin_ops_platform.services.app_mongo_staging_importer import (
    AppMongoStagingImportBuilder,
    StagingImportPlan,
    ValidationReport,
    compare_metric_snapshots,
)


DRY_RUN_TOOL_VERSION = "app-mongo-migration-dry-run-v1"
SOURCE_SYSTEM = "app_mongo"

PROMPT_B_REQUIRED_DOMAINS = (
    "bank_transactions",
    "invoices",
    "oa_applications",
    "oa_application_items",
    "oa_attachments",
    "reconciliation_cases",
    "reconciliation_case_rows",
    "workbench_overrides",
    "exceptions",
    "no_oa_batches",
    "turnover",
    "imports_files",
    "settings",
    "background_jobs",
    "tax_cost_read_model_sources",
)


@dataclass(frozen=True, slots=True)
class DatasetMapping:
    dataset: str
    legacy_collections: tuple[str, ...]
    target_tables: tuple[str, ...]
    domains: tuple[str, ...]
    supporting_tables: tuple[str, ...] = ("staging.legacy_id_map", "audit.events")
    partition_kind: str | None = None
    migrates: bool = True


DATASET_MAPPINGS: dict[str, DatasetMapping] = {
    "import_batches": DatasetMapping(
        "import_batches",
        ("import_batches",),
        ("app.import_batches",),
        ("imports_files",),
    ),
    "file_objects": DatasetMapping(
        "file_objects",
        ("file_import_files", "file_objects"),
        ("app.file_objects", "app.import_files"),
        ("imports_files",),
    ),
    "gridfs-files-manifest": DatasetMapping(
        "gridfs-files-manifest",
        ("import_file_blobs.files", "gridfs-files-manifest"),
        ("app.file_objects",),
        ("imports_files",),
    ),
    "bank_transactions": DatasetMapping(
        "bank_transactions",
        ("bank_transactions",),
        ("app.bank_transactions",),
        ("bank_transactions",),
        partition_kind="bank_transactions",
    ),
    "bank_transaction_categories": DatasetMapping(
        "bank_transaction_categories",
        ("bank_transaction_categories",),
        ("app.bank_transaction_categories",),
        ("bank_transactions",),
    ),
    "invoices": DatasetMapping(
        "invoices",
        ("invoices",),
        ("app.invoices",),
        ("invoices", "tax_cost_read_model_sources"),
        partition_kind="invoices",
    ),
    "tax_certified_import_sessions": DatasetMapping(
        "tax_certified_import_sessions",
        ("tax_certified_import_sessions",),
        ("app.import_batches",),
        ("imports_files", "tax_cost_read_model_sources"),
    ),
    "tax_certified_import_batches": DatasetMapping(
        "tax_certified_import_batches",
        ("tax_certified_import_batches",),
        ("app.import_batches",),
        ("imports_files", "tax_cost_read_model_sources"),
    ),
    "tax_certified_import_records": DatasetMapping(
        "tax_certified_import_records",
        ("tax_certified_import_records",),
        ("app.invoice_certifications",),
        ("tax_cost_read_model_sources",),
    ),
    "matching_runs": DatasetMapping(
        "matching_runs",
        ("matching_runs",),
        ("app.reconciliation_cases",),
        ("reconciliation_cases",),
    ),
    "matching_results": DatasetMapping(
        "matching_results",
        ("matching_results",),
        ("app.reconciliation_case_rows",),
        ("reconciliation_case_rows",),
    ),
    "workbench_overrides": DatasetMapping(
        "workbench_overrides",
        ("workbench_row_overrides",),
        ("app.workbench_row_overrides",),
        ("workbench_overrides",),
    ),
    "workbench_exception_cases": DatasetMapping(
        "workbench_exception_cases",
        ("workbench_exception_cases",),
        ("app.workbench_exception_cases",),
        ("exceptions",),
    ),
    "workbench_pair_relations": DatasetMapping(
        "workbench_pair_relations",
        ("workbench_pair_relations",),
        ("app.reconciliation_cases", "app.reconciliation_case_rows"),
        ("reconciliation_cases", "reconciliation_case_rows"),
    ),
    "workbench_read_models": DatasetMapping(
        "workbench_read_models",
        ("workbench_read_models",),
        ("read_model.workbench_rows", "read_model.search_index_rows"),
        ("tax_cost_read_model_sources",),
        partition_kind="read_model",
    ),
    "workbench_candidate_matches": DatasetMapping(
        "workbench_candidate_matches",
        ("workbench_candidate_matches",),
        ("read_model.workbench_candidate_matches",),
        ("tax_cost_read_model_sources",),
    ),
    "workbench_matching_dirty_scopes": DatasetMapping(
        "workbench_matching_dirty_scopes",
        ("workbench_matching_dirty_scopes",),
        ("job.worker_tasks",),
        ("background_jobs", "tax_cost_read_model_sources"),
    ),
    "no_oa_bank_batches": DatasetMapping(
        "no_oa_bank_batches",
        ("no_oa_bank_batches",),
        ("app.no_oa_bank_batches",),
        ("no_oa_batches",),
    ),
    "no_oa_bank_batch_audit_log": DatasetMapping(
        "no_oa_bank_batch_audit_log",
        ("no_oa_bank_batch_audit_log",),
        ("audit.events",),
        ("no_oa_batches",),
    ),
    "turnover_relations": DatasetMapping(
        "turnover_relations",
        ("turnover_relations",),
        ("app.turnover_relations",),
        ("turnover",),
    ),
    "turnover_relation_audit_log": DatasetMapping(
        "turnover_relation_audit_log",
        ("turnover_relation_audit_log",),
        ("audit.events",),
        ("turnover",),
    ),
    "turnover_ledger_extras": DatasetMapping(
        "turnover_ledger_extras",
        ("turnover_ledger_extras",),
        ("audit.events",),
        ("turnover",),
    ),
    "cost_statistics_read_models": DatasetMapping(
        "cost_statistics_read_models",
        ("cost_statistics_read_models",),
        ("read_model.cost_statistics_read_models",),
        ("tax_cost_read_model_sources",),
    ),
    "tax_offset_read_models": DatasetMapping(
        "tax_offset_read_models",
        ("tax_offset_read_models",),
        ("read_model.tax_offset_read_models",),
        ("tax_cost_read_model_sources",),
    ),
    "oa_attachment_invoice_cache": DatasetMapping(
        "oa_attachment_invoice_cache",
        ("oa_attachment_invoice_cache",),
        ("app.oa_attachments",),
        ("oa_attachments", "tax_cost_read_model_sources"),
    ),
    "oa_sync_state": DatasetMapping(
        "oa_sync_state",
        ("oa_sync_state",),
        ("app.oa_sync_watermarks",),
        ("oa_applications",),
    ),
    "oa_applications": DatasetMapping(
        "oa_applications",
        ("oa_applications",),
        ("app.oa_applications",),
        ("oa_applications",),
        partition_kind="oa_applications",
    ),
    "oa_application_items": DatasetMapping(
        "oa_application_items",
        ("oa_application_items",),
        ("app.oa_application_items",),
        ("oa_application_items",),
    ),
    "oa_attachments": DatasetMapping(
        "oa_attachments",
        ("oa_attachments",),
        ("app.oa_attachments",),
        ("oa_attachments",),
    ),
    "app_settings": DatasetMapping(
        "app_settings",
        ("app_settings",),
        ("audit.events",),
        ("settings",),
    ),
    "background_jobs": DatasetMapping(
        "background_jobs",
        ("background_jobs",),
        ("job.worker_tasks",),
        ("background_jobs",),
    ),
    "app_health_alerts": DatasetMapping(
        "app_health_alerts",
        ("app_health_alerts",),
        ("job.worker_tasks",),
        ("background_jobs",),
    ),
}

LEGACY_COLLECTION_TO_DATASET = {
    legacy_collection: dataset
    for dataset, mapping in DATASET_MAPPINGS.items()
    for legacy_collection in mapping.legacy_collections
}


@dataclass(slots=True)
class MigrationDryRunReport:
    report_id: str
    migration_run_id: str
    manifest_id: str
    source: dict[str, Any]
    target: dict[str, Any]
    source_metrics: dict[str, Any]
    staging_metrics: dict[str, Any]
    target_metrics: dict[str, Any]
    partition_plan: dict[str, Any]
    legacy_id_coverage: dict[str, Any]
    target_rows: list[dict[str, Any]]
    legacy_id_map_rows: list[dict[str, Any]]
    findings: list[dict[str, Any]] = field(default_factory=list)
    decision: dict[str, Any] = field(default_factory=dict)

    @property
    def has_blockers(self) -> bool:
        return any(item.get("severity") == "error" for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "migration_run_id": self.migration_run_id,
            "manifest_id": self.manifest_id,
            "phase": "staging_to_facts_dry_run",
            "tool": DRY_RUN_TOOL_VERSION,
            "source": self.source,
            "target": self.target,
            "status": "failed" if self.has_blockers else "passed",
            "blocking": self.has_blockers,
            "source_metrics": self.source_metrics,
            "staging_metrics": self.staging_metrics,
            "target_metrics": self.target_metrics,
            "partition_plan": self.partition_plan,
            "legacy_id_coverage": self.legacy_id_coverage,
            "target_row_count": len(self.target_rows),
            "legacy_id_map_row_count": len(self.legacy_id_map_rows),
            "findings": self.findings,
            "decision": self.decision,
        }

    def to_markdown(self) -> str:
        status = self.decision.get("go_no_go", "NO_GO")
        lines = [
            f"# 数据迁移 Dry-run 报告 - {self.report_id}",
            "",
            f"go/no-go | `{status}`",
            "",
            f"- migration_run_id: `{self.migration_run_id}`",
            f"- manifest_id: `{self.manifest_id}`",
            f"- blocking: `{str(self.has_blockers).lower()}`",
            f"- target_row_count: `{len(self.target_rows)}`",
            f"- legacy_id_coverage: `{self.legacy_id_coverage.get('mapped')}/{self.legacy_id_coverage.get('expected')}`",
            "",
            "## Metrics",
            "",
            "| Dimension | Source | Staging | Target |",
            "| --- | --- | --- | --- |",
        ]
        for dimension in ("record_counts", "amount_totals", "month_distribution", "status_distribution", "hashes"):
            lines.append(
                "| "
                + dimension
                + " | `"
                + json.dumps(self.source_metrics.get(dimension, {}), ensure_ascii=False, sort_keys=True)
                + "` | `"
                + json.dumps(self.staging_metrics.get(dimension, {}), ensure_ascii=False, sort_keys=True)
                + "` | `"
                + json.dumps(self.target_metrics.get(dimension, {}), ensure_ascii=False, sort_keys=True)
                + "` |"
            )
        lines.extend(
            [
                "",
                "## Findings",
                "",
            ]
        )
        if not self.findings:
            lines.append("- none")
        else:
            for finding in self.findings:
                lines.append(
                    "- `"
                    + str(finding.get("code"))
                    + "` "
                    + str(finding.get("object_type", "-"))
                    + " "
                    + str(finding.get("legacy_id", "-"))
                    + ": "
                    + str(finding.get("message"))
                )
        return "\n".join(lines) + "\n"


def dataset_mapping_summary() -> dict[str, dict[str, Any]]:
    return {
        dataset: {
            "legacy_collections": list(mapping.legacy_collections),
            "target_tables": list(mapping.target_tables),
            "supporting_tables": list(mapping.supporting_tables),
            "domains": list(mapping.domains),
            "partition_kind": mapping.partition_kind,
            "migrates": mapping.migrates,
        }
        for dataset, mapping in sorted(DATASET_MAPPINGS.items())
    }


class AppMongoMigrationDryRunBuilder:
    def build_report(
        self,
        *,
        export_dir: Path,
        staging_plan: StagingImportPlan,
        migration_run_id: str | None = None,
    ) -> MigrationDryRunReport:
        migration_id = str(migration_run_id or staging_plan.manifest_record["id"])
        manifest = json.loads((export_dir / "manifest.json").read_text(encoding="utf-8"))
        source_records_by_dataset = self._read_source_records(export_dir=export_dir, manifest=manifest)
        source_metrics = self._metric_snapshot(source_records_by_dataset)
        staging_records_by_dataset = self._records_from_staging_plan(
            staging_plan=staging_plan,
            source_records_by_dataset=source_records_by_dataset,
        )
        staging_metrics = self._metric_snapshot(staging_records_by_dataset)
        target_rows, legacy_id_map_rows, findings = self._map_staging_rows(
            staging_plan=staging_plan,
            migration_run_id=migration_id,
            source_records_by_dataset=source_records_by_dataset,
        )
        target_records_by_dataset = self._records_from_target_rows(target_rows)
        target_metrics = self._metric_snapshot(target_records_by_dataset)
        partition_plan = self._build_partition_plan(
            migration_run_id=migration_id,
            source_manifest=str(export_dir / "manifest.json"),
            records_by_dataset={**source_records_by_dataset, **target_records_by_dataset},
        )
        coverage = self._build_legacy_id_coverage(
            source_records_by_dataset=source_records_by_dataset,
            legacy_id_map_rows=legacy_id_map_rows,
        )

        compare_source_staging = compare_metric_snapshots(source_metrics, staging_metrics)
        compare_source_target = compare_metric_snapshots(
            self._comparable_target_expected_metrics(source_metrics, target_metrics),
            target_metrics,
        )
        findings.extend(compare_source_staging.findings)
        findings.extend(compare_source_target.findings)
        findings.extend(self._coverage_findings(coverage))
        if partition_plan.get("blocking"):
            findings.append(
                {
                    "severity": "error",
                    "code": "PARTITION_PLAN_MISSING",
                    "dimension": "partition_plan",
                    "message": "Partitioned target datasets exist but no source month could be derived.",
                }
            )

        report_id = f"migration-dry-run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        decision = {
            "go_no_go": "NO_GO" if any(item.get("severity") == "error" for item in findings) else "GO",
            "reason": "Blocking findings exist." if any(item.get("severity") == "error" for item in findings) else "Dry-run reconciliation passed.",
            "required_action": "Fix mapping/import/partition issue and rerun dry-run."
            if any(item.get("severity") == "error" for item in findings)
            else "Eligible for human gate review; this dry-run does not authorize production cutover.",
        }
        return MigrationDryRunReport(
            report_id=report_id,
            migration_run_id=migration_id,
            manifest_id=str(staging_plan.manifest_record["id"]),
            source={
                "kind": "app_mongo_export",
                "database": str((manifest.get("source") or {}).get("database") or "unknown"),
                "export_name": export_dir.name,
                "manifest_sha256": AppMongoStagingImportBuilder.file_sha256(export_dir / "manifest.json"),
            },
            target={
                "kind": "postgresql_dry_run",
                "schemas": ["app", "read_model", "job", "audit", "staging"],
                "execute_required": False,
            },
            source_metrics=source_metrics,
            staging_metrics=staging_metrics,
            target_metrics=target_metrics,
            partition_plan=partition_plan,
            legacy_id_coverage=coverage,
            target_rows=target_rows,
            legacy_id_map_rows=legacy_id_map_rows,
            findings=findings,
            decision=decision,
        )

    def _read_source_records(self, *, export_dir: Path, manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        files = (manifest.get("output") or {}).get("files") or {}
        if not isinstance(files, dict):
            return records_by_dataset
        for dataset, filename in sorted(files.items(), key=lambda item: str(item[0])):
            path = export_dir / str(filename)
            records_by_dataset[dataset] = []
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        records_by_dataset[dataset].append(parsed)
        return records_by_dataset

    def _records_from_staging_plan(
        self,
        *,
        staging_plan: StagingImportPlan,
        source_records_by_dataset: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        dataset_by_legacy = self._dataset_by_legacy(source_records_by_dataset)
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        for row in staging_plan.rows:
            dataset = dataset_by_legacy.get(
                (str(row.get("legacy_collection")), str(row.get("legacy_id"))),
                self._dataset_for_legacy_collection(str(row.get("legacy_collection"))),
            )
            records_by_dataset.setdefault(dataset, []).append(dict(row.get("payload") or {}))
        return records_by_dataset

    def _map_staging_rows(
        self,
        *,
        staging_plan: StagingImportPlan,
        migration_run_id: str,
        source_records_by_dataset: dict[str, list[dict[str, Any]]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        dataset_by_legacy = self._dataset_by_legacy(source_records_by_dataset)
        target_rows: list[dict[str, Any]] = []
        legacy_id_map_rows: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        for row in staging_plan.rows:
            legacy_collection = str(row.get("legacy_collection"))
            legacy_id = str(row.get("legacy_id"))
            dataset = dataset_by_legacy.get(
                (legacy_collection, legacy_id),
                self._dataset_for_legacy_collection(legacy_collection),
            )
            mapping = DATASET_MAPPINGS.get(dataset)
            source_record = dict(row.get("payload") or {})
            payload = source_record.get("payload") if isinstance(source_record.get("payload"), dict) else source_record
            if mapping is None or not mapping.migrates:
                findings.append(
                    {
                        "severity": "error",
                        "code": "UNMAPPED_LEGACY_ID",
                        "object_type": dataset,
                        "legacy_id": legacy_id,
                        "dimension": "legacy_id_coverage",
                        "message": "No explicit PostgreSQL target mapping exists for this app Mongo dataset.",
                    }
                )
                continue
            primary_table = mapping.target_tables[0]
            target_id = str(uuid5(NAMESPACE_URL, f"{migration_run_id}:{legacy_collection}:{legacy_id}:{primary_table}"))
            target_row = {
                "source_dataset": dataset,
                "legacy_collection": legacy_collection,
                "legacy_id": legacy_id,
                "target_schema": primary_table.split(".", 1)[0],
                "target_table": primary_table.split(".", 1)[1],
                "target_id": target_id,
                "target_tables": list(mapping.target_tables),
                "target_partition_month": self._partition_month(dataset=dataset, payload=payload),
                "payload_hash": str(row.get("payload_hash") or AppMongoStagingImportBuilder.record_sha256(source_record)),
                "payload": self._target_payload(dataset=dataset, payload=payload, source_record=source_record),
            }
            target_rows.append(target_row)
            legacy_id_map_rows.append(
                {
                    "source_system": SOURCE_SYSTEM,
                    "legacy_collection": legacy_collection,
                    "legacy_id": legacy_id,
                    "target_schema": target_row["target_schema"],
                    "target_table": target_row["target_table"],
                    "target_id": target_id,
                    "target_partition_month": target_row["target_partition_month"],
                    "payload_hash": target_row["payload_hash"],
                    "migration_run_id": migration_run_id,
                }
            )
        return target_rows, legacy_id_map_rows, findings

    def _records_from_target_rows(self, target_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        for row in target_rows:
            dataset = str(row["source_dataset"])
            records_by_dataset.setdefault(dataset, []).append(
                {
                    "legacy_collection": row["legacy_collection"],
                    "legacy_id": row["legacy_id"],
                    "payload": row["payload"],
                }
            )
        return records_by_dataset

    def _metric_snapshot(self, records_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        report = ValidationReport()
        snapshot = AppMongoStagingImportBuilder()._build_metric_snapshot(records_by_dataset, report=report)  # noqa: SLF001
        snapshot["hashes"] = {
            dataset: self._records_hash(records)
            for dataset, records in sorted(records_by_dataset.items())
        }
        snapshot["failed_row_reasons"] = [
            finding
            for finding in report.findings
            if finding.get("severity") == "error"
        ]
        return snapshot

    def _comparable_target_expected_metrics(
        self,
        source_metrics: dict[str, Any],
        target_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        comparable_counts = {
            dataset: source_metrics.get("record_counts", {}).get(dataset)
            for dataset in target_metrics.get("record_counts", {})
        }
        comparable_amounts = {
            key: source_metrics.get("amount_totals", {}).get(key)
            for key in target_metrics.get("amount_totals", {})
        }
        comparable_months = {
            dataset: source_metrics.get("month_distribution", {}).get(dataset)
            for dataset in target_metrics.get("month_distribution", {})
        }
        comparable_status = {
            dataset: source_metrics.get("status_distribution", {}).get(dataset)
            for dataset in target_metrics.get("status_distribution", {})
        }
        return {
            "record_counts": comparable_counts,
            "amount_totals": comparable_amounts,
            "month_distribution": comparable_months,
            "status_distribution": comparable_status,
            "file_checksum_samples": [],
        }

    def _build_partition_plan(
        self,
        *,
        migration_run_id: str,
        source_manifest: str,
        records_by_dataset: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        entries: dict[tuple[str, str, str], dict[str, Any]] = {}
        partitioned_dataset_seen = False
        for dataset, records in sorted(records_by_dataset.items()):
            mapping = DATASET_MAPPINGS.get(dataset)
            if mapping is None or mapping.partition_kind is None:
                continue
            partitioned_dataset_seen = True
            for record in records:
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
                month = self._partition_month(dataset=dataset, payload=payload)
                if month is None:
                    continue
                for entry in self._partition_entries(mapping.partition_kind, month):
                    entries[(entry["schema"], entry["parent_table"], entry["month"])] = entry
        months = sorted({entry["month"] for entry in entries.values()})
        return {
            "migration_run_id": migration_run_id,
            "source_manifest": source_manifest,
            "month_range": {"min": months[0], "max": months[-1]} if months else None,
            "prepared_partitions": sorted(entries.values(), key=lambda item: (item["schema"], item["parent_table"], item["month"])),
            "blocking": bool(partitioned_dataset_seen and not months),
        }

    def _build_legacy_id_coverage(
        self,
        *,
        source_records_by_dataset: dict[str, list[dict[str, Any]]],
        legacy_id_map_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        expected = []
        for dataset, records in sorted(source_records_by_dataset.items()):
            mapping = DATASET_MAPPINGS.get(dataset)
            if mapping is None or not mapping.migrates:
                expected.extend(
                    {
                        "dataset": dataset,
                        "legacy_collection": str(record.get("legacy_collection") or dataset),
                        "legacy_id": str(record.get("legacy_id") or ""),
                    }
                    for record in records
                )
                continue
            expected.extend(
                {
                    "dataset": dataset,
                    "legacy_collection": str(record.get("legacy_collection") or dataset),
                    "legacy_id": str(record.get("legacy_id") or ""),
                }
                for record in records
            )
        mapped = {
            (str(row["legacy_collection"]), str(row["legacy_id"]))
            for row in legacy_id_map_rows
        }
        missing = [
            item
            for item in expected
            if (item["legacy_collection"], item["legacy_id"]) not in mapped
        ]
        return {
            "expected": len(expected),
            "mapped": len(expected) - len(missing),
            "coverage_ratio": "1.0000" if not expected else f"{(len(expected) - len(missing)) / len(expected):.4f}",
            "missing": missing,
            "map_rows": legacy_id_map_rows,
        }

    def _coverage_findings(self, coverage: dict[str, Any]) -> list[dict[str, Any]]:
        findings = []
        for item in coverage.get("missing", []):
            findings.append(
                {
                    "severity": "error",
                    "code": "UNMAPPED_LEGACY_ID",
                    "object_type": item.get("dataset"),
                    "legacy_collection": item.get("legacy_collection"),
                    "legacy_id": item.get("legacy_id"),
                    "dimension": "legacy_id_coverage",
                    "message": "Source legacy id has no target mapping row.",
                }
            )
        return findings

    def _dataset_by_legacy(self, records_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[tuple[str, str], str]:
        result: dict[tuple[str, str], str] = {}
        for dataset, records in records_by_dataset.items():
            for record in records:
                result[(str(record.get("legacy_collection") or dataset), str(record.get("legacy_id") or ""))] = dataset
        return result

    def _dataset_for_legacy_collection(self, legacy_collection: str) -> str:
        return LEGACY_COLLECTION_TO_DATASET.get(legacy_collection, legacy_collection)

    def _target_payload(self, *, dataset: str, payload: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result.setdefault("legacy_collection", source_record.get("legacy_collection") or dataset)
        result.setdefault("legacy_id", source_record.get("legacy_id"))
        result.setdefault("raw_payload", payload)
        return result

    def _partition_month(self, *, dataset: str, payload: dict[str, Any]) -> str | None:
        month = AppMongoStagingImportBuilder._extract_month(dataset=dataset, payload=payload)  # noqa: SLF001
        if month:
            return month
        for field_name in ("scope_month", "month", "source_updated_at", "approved_at", "created_at", "updated_at"):
            value = payload.get(field_name)
            if value:
                return str(value)[:7]
        return None

    def _partition_entries(self, partition_kind: str, month: str) -> list[dict[str, Any]]:
        if partition_kind == "bank_transactions":
            return [{"schema": "app", "parent_table": "bank_transactions", "month": month, "status": "planned"}]
        if partition_kind == "invoices":
            return [{"schema": "app", "parent_table": "invoices", "month": month, "status": "planned"}]
        if partition_kind == "oa_applications":
            return [{"schema": "app", "parent_table": "oa_applications", "month": month, "status": "planned"}]
        if partition_kind == "read_model":
            return [
                {"schema": "read_model", "parent_table": "workbench_rows", "month": month, "status": "planned"},
                {"schema": "read_model", "parent_table": "search_index_rows", "month": month, "status": "planned"},
            ]
        return []

    def _records_hash(self, records: Iterable[dict[str, Any]]) -> str:
        digest = hashlib.sha256()
        for record in records:
            digest.update(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()


class MigrationDryRunExecutor:
    def execute(self, connection: Any, report: MigrationDryRunReport) -> None:
        if report.has_blockers:
            raise RuntimeError("Refusing to execute migration dry-run while report has blocking findings.")
        cursor = connection.cursor()
        for entry in report.partition_plan.get("prepared_partitions", []):
            schema = entry["schema"]
            parent_table = entry["parent_table"]
            month = f"{entry['month']}-01"
            if schema == "app" and parent_table in {"bank_transactions", "invoices"}:
                cursor.execute(
                    "select app.create_financial_fact_month_partition(%s::regclass, %s::date)",
                    (f"app.{parent_table}", month),
                )
            elif schema == "app" and parent_table == "oa_applications":
                cursor.execute("select app.create_oa_applications_month_partition(%s::date)", (month,))
            elif schema == "read_model" and parent_table == "workbench_rows":
                cursor.execute("select read_model.create_workbench_rows_partition(%s::date)", (month,))
            elif schema == "read_model" and parent_table == "search_index_rows":
                cursor.execute("select read_model.create_search_index_rows_partition(%s::date)", (month,))
        for row in report.legacy_id_map_rows:
            cursor.execute(
                """
                insert into staging.legacy_id_map (
                  source_system,
                  legacy_collection,
                  legacy_id,
                  target_schema,
                  target_table,
                  target_id,
                  target_partition_month,
                  payload_hash,
                  migration_run_id
                ) values (%s, %s, %s, %s, %s, %s, %s::date, %s, %s)
                on conflict (
                  source_system,
                  legacy_collection,
                  legacy_id,
                  target_schema,
                  target_table
                ) do update set
                  target_id = excluded.target_id,
                  target_partition_month = excluded.target_partition_month,
                  payload_hash = excluded.payload_hash,
                  migration_run_id = excluded.migration_run_id
                """,
                (
                    row["source_system"],
                    row["legacy_collection"],
                    row["legacy_id"],
                    row["target_schema"],
                    row["target_table"],
                    row["target_id"],
                    f"{row['target_partition_month']}-01" if row.get("target_partition_month") else None,
                    row["payload_hash"],
                    row["migration_run_id"],
                ),
            )
        connection.commit()
