from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid4, uuid5


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
    status_values: tuple[str, ...] = ()
    migrates: bool = True


DATASET_MAPPINGS: dict[str, DatasetMapping] = {
    "import_batches": DatasetMapping(
        "import_batches",
        ("import_batches",),
        ("app.import_batches",),
        ("imports_files",),
        status_values=("pending", "completed", "completed_with_errors", "reverted", "failed"),
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
        status_values=(
            "pending",
            "partially_reconciled",
            "reconciled",
            "classified_as_prepayment",
            "classified_as_advance_receipt",
            "pending_refund",
            "pending_counterparty_confirmation",
        ),
    ),
    "bank_transaction_categories": DatasetMapping(
        "bank_transaction_categories",
        ("bank_transaction_categories",),
        ("app.bank_transaction_categories",),
        ("bank_transactions",),
        status_values=("active", "cancelled", "replaced"),
    ),
    "invoices": DatasetMapping(
        "invoices",
        ("invoices",),
        ("app.invoices",),
        ("invoices", "tax_cost_read_model_sources"),
        partition_kind="invoices",
        status_values=(
            "pending",
            "partially_reconciled",
            "reconciled",
            "pending_offline_confirmation",
            "pending_offset",
            "pending_invoice_issue",
            "pending_invoice_receive",
        ),
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
        status_values=("draft", "confirmed", "follow_up_required", "cancelled"),
    ),
    "matching_results": DatasetMapping(
        "matching_results",
        ("matching_results",),
        ("app.reconciliation_case_rows",),
        ("reconciliation_case_rows",),
        status_values=("active", "cancelled", "reverted"),
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
        status_values=("draft", "confirmed", "follow_up_required", "cancelled"),
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
        status_values=("active", "superseded", "dismissed"),
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
        status_values=("approved", "in_progress", "rejected", "cancelled", "unknown"),
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
        status_values=("queued", "running", "succeeded", "failed", "retrying", "dead_lettered", "cancelled"),
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
    row_hash_reconciliation: list[dict[str, Any]]
    unmapped_invalid_enums: dict[str, dict[str, list[str]]]
    file_checksum_scope: dict[str, Any]
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
            "row_hash_reconciliation": self.row_hash_reconciliation,
            "unmapped_invalid_enums": self.unmapped_invalid_enums,
            "file_checksum_scope": self.file_checksum_scope,
            "target_row_count": len(self.target_rows),
            "legacy_id_map_row_count": len(self.legacy_id_map_rows),
            "target_rows": self.target_rows,
            "legacy_id_map_rows": self.legacy_id_map_rows,
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
            f"- dry-run tool: `{DRY_RUN_TOOL_VERSION}`",
            "- execute mode: `false` unless this report was explicitly applied to an isolated dry-run database",
            f"- blocking: `{str(self.has_blockers).lower()}`",
            f"- target_row_count: `{len(self.target_rows)}`",
            f"- legacy_id_coverage: `{self.legacy_id_coverage.get('mapped')}/{self.legacy_id_coverage.get('expected')}`",
            "- file checksum: `deferred_to_06D_not_evaluated_in_06C`",
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
        lines.extend(["", "## Findings", ""])
        if not self.findings:
            lines.append("- none")
        else:
            for finding in self.findings:
                location = "/".join(
                    str(finding.get(key, "-"))
                    for key in ("object_type", "month", "status", "legacy_id", "source_line")
                    if finding.get(key) is not None
                )
                lines.append(f"- `{finding.get('code')}` {location}: {finding.get('message')}")
        return "\n".join(lines) + "\n"


def dataset_mapping_summary() -> dict[str, dict[str, Any]]:
    return {
        dataset: {
            "legacy_collections": list(mapping.legacy_collections),
            "target_tables": list(mapping.target_tables),
            "supporting_tables": list(mapping.supporting_tables),
            "domains": list(mapping.domains),
            "partition_kind": mapping.partition_kind,
            "status_values": list(mapping.status_values),
            "migrates": mapping.migrates,
        }
        for dataset, mapping in sorted(DATASET_MAPPINGS.items())
    }


class AppMongoMigrationDryRunBuilder:
    def build_report(
        self,
        *,
        export_dir: Path,
        migration_run_id: str | None = None,
    ) -> MigrationDryRunReport:
        manifest_path = export_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        migration_id = str(migration_run_id or uuid4())
        source_records, read_findings = self._read_source_records(export_dir=export_dir, manifest=manifest)
        staging_rows = self.build_staging_rows_from_records(
            records_by_dataset=source_records,
            migration_run_id=migration_id,
        )
        manifest_record = {
            "id": migration_id,
            "source_database": str((manifest.get("source") or {}).get("database") or "unknown"),
            "export_name": export_dir.name,
            "sha256_manifest": self.file_sha256(manifest_path),
        }
        report = self.build_report_from_staging_rows(
            migration_run_id=migration_id,
            staging_rows=staging_rows,
            manifest_record=manifest_record,
            source_records_by_dataset=source_records,
            source_findings=read_findings,
        )
        report.source["manifest_sha256"] = self.file_sha256(manifest_path)
        report.source_metrics["manifest_record_counts"] = {
            str(dataset): int(count or 0)
            for dataset, count in sorted((manifest.get("record_counts") or {}).items())
        }
        report.source_metrics["manifest_hashes"] = {
            str(filename): str(checksum)
            for filename, checksum in sorted((manifest.get("checksums") or {}).items())
        }
        report.findings.extend(self._manifest_findings(export_dir=export_dir, manifest=manifest, source_records=source_records))
        report.decision = self._decision(report.findings)
        return report

    def build_report_from_staging_rows(
        self,
        *,
        migration_run_id: str,
        staging_rows: list[dict[str, Any]],
        manifest_record: dict[str, Any],
        source_records_by_dataset: dict[str, list[dict[str, Any]]] | None = None,
        source_findings: list[dict[str, Any]] | None = None,
    ) -> MigrationDryRunReport:
        isolated_rows = [
            dict(row)
            for row in staging_rows
            if str(row.get("manifest_id") or row.get("migration_run_id")) == migration_run_id
        ]
        source_records = source_records_by_dataset or self._records_from_staging_rows(isolated_rows, include_failed=True)
        source_metrics = self._metric_snapshot(source_records)
        staging_records = self._records_from_staging_rows(isolated_rows, include_failed=True)
        staging_metrics = self._metric_snapshot(staging_records)
        target_rows, legacy_id_map_rows, row_hashes, enum_values, findings = self._map_staging_rows(
            staging_rows=isolated_rows,
            migration_run_id=migration_run_id,
        )
        target_records = self._records_from_target_rows(target_rows)
        target_metrics = self._metric_snapshot(target_records)
        partition_plan = self._build_partition_plan(
            migration_run_id=migration_run_id,
            source_manifest=str(manifest_record.get("export_name") or "staging_rows"),
            records_by_dataset={**source_records, **target_records},
        )
        coverage = self._build_legacy_id_coverage(source_records_by_dataset=source_records, legacy_id_map_rows=legacy_id_map_rows)
        findings.extend(source_findings or [])
        findings.extend(source_metrics.get("failed_row_reasons", []))
        findings.extend(self._compare_source_staging(source_metrics, staging_metrics))
        findings.extend(self._compare_source_target(source_metrics=source_metrics, target_metrics=target_metrics))
        findings.extend(self._coverage_findings(coverage))
        if partition_plan.get("blocking"):
            findings.append(
                self._finding(
                    code="PARTITION_PLAN_MISSING",
                    message="Partitioned target datasets exist but no source month could be derived.",
                    dimension="partition_plan",
                    object_type="partitioned_facts",
                )
            )
        report = MigrationDryRunReport(
            report_id=f"migration-dry-run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            migration_run_id=migration_run_id,
            manifest_id=str(manifest_record.get("id") or migration_run_id),
            source={
                "kind": "postgresql_staging_rows" if source_records_by_dataset is None else "app_mongo_export",
                "database": str(manifest_record.get("source_database") or "unknown"),
                "export_name": str(manifest_record.get("export_name") or "staging_rows"),
                "manifest_sha256": str(manifest_record.get("sha256_manifest") or "not_available"),
            },
            target={
                "kind": "postgresql_dry_run_plan",
                "schemas": ["app", "read_model", "job", "audit", "staging"],
                "execute_required": False,
                "writes_production_facts": False,
                "oa_source_database_accessed": False,
            },
            source_metrics=source_metrics,
            staging_metrics=staging_metrics,
            target_metrics=target_metrics,
            partition_plan=partition_plan,
            legacy_id_coverage=coverage,
            target_rows=target_rows,
            legacy_id_map_rows=legacy_id_map_rows,
            row_hash_reconciliation=row_hashes,
            unmapped_invalid_enums=enum_values,
            file_checksum_scope={
                "owner_phase": "06D",
                "status": "not_evaluated_in_06c",
                "message": "06C records manifest/file checksum metadata only; file content checksum gate belongs to 06D.",
            },
            findings=findings,
            decision=self._decision(findings),
        )
        return report

    def build_staging_rows_from_records(
        self,
        *,
        records_by_dataset: dict[str, list[dict[str, Any]]],
        migration_run_id: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for dataset, records in sorted(records_by_dataset.items()):
            target_table = DATASET_MAPPINGS.get(dataset).target_tables[0] if dataset in DATASET_MAPPINGS else None
            for index, record in enumerate(records, start=1):
                row_no = int(record.get("_row_no") or index)
                payload = {
                    key: value
                    for key, value in record.items()
                    if key != "_row_no"
                }
                rows.append(
                    {
                        "manifest_id": migration_run_id,
                        "legacy_collection": str(record.get("legacy_collection") or dataset),
                        "legacy_id": str(record.get("legacy_id") or f"{dataset}:{row_no}"),
                        "row_no": row_no,
                        "payload": payload,
                        "payload_hash": self.record_sha256(payload),
                        "target_table": target_table,
                        "status": "parsed",
                    }
                )
        return rows

    def load_staging_rows_from_postgres(self, *, connection: Any, migration_run_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cursor = connection.cursor()
        cursor.execute(
            """
            select id, source_database, export_name, sha256_manifest
            from staging.mongo_export_manifest
            where id = %s
            """,
            (migration_run_id,),
        )
        manifest = cursor.fetchone()
        if manifest is None:
            raise RuntimeError("No staging.mongo_export_manifest row found for migration_run_id.")
        cursor.execute(
            """
            select
              manifest_id,
              legacy_collection,
              legacy_id,
              row_no,
              payload,
              payload_hash,
              target_table,
              status,
              error_code,
              error_message
            from staging.mongo_import_rows
            where manifest_id = %s
            order by legacy_collection, row_no
            """,
            (migration_run_id,),
        )
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        manifest_record = {
            "id": str(manifest[0]),
            "source_database": str(manifest[1]),
            "export_name": str(manifest[2]),
            "sha256_manifest": str(manifest[3]),
        }
        return manifest_record, rows

    def _read_source_records(
        self,
        *,
        export_dir: Path,
        manifest: dict[str, Any],
    ) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        findings: list[dict[str, Any]] = []
        files = (manifest.get("output") or {}).get("files") or {}
        if not isinstance(files, dict):
            return records_by_dataset, [
                self._finding(code="BLOCKED_FACT_SOURCE", message="manifest.output.files must be an object.", dimension="manifest")
            ]
        for dataset, filename in sorted(files.items(), key=lambda item: str(item[0])):
            path = export_dir / str(filename)
            records_by_dataset[str(dataset)] = []
            if not path.exists():
                expected_count = int((manifest.get("record_counts") or {}).get(dataset) or 0)
                if expected_count:
                    findings.append(
                        self._finding(
                            code="BLOCKED_FACT_SOURCE",
                            message=f"Expected export file is missing: {filename}",
                            object_type=str(dataset),
                            dimension="source_file",
                            expected=expected_count,
                            actual=0,
                        )
                    )
                continue
            with path.open("r", encoding="utf-8") as handle:
                for row_no, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError as exc:
                        findings.append(
                            self._finding(
                                code="BLOCKED_FACT_SOURCE",
                                message=str(exc),
                                object_type=str(dataset),
                                source_line=row_no,
                                dimension="ndjson_parse",
                            )
                        )
                        continue
                    if not isinstance(parsed, dict):
                        findings.append(
                            self._finding(
                                code="BLOCKED_FACT_SOURCE",
                                message="NDJSON row must be a JSON object.",
                                object_type=str(dataset),
                                source_line=row_no,
                                dimension="ndjson_shape",
                            )
                        )
                        continue
                    parsed["_row_no"] = row_no
                    records_by_dataset[str(dataset)].append(parsed)
        return records_by_dataset, findings

    def _records_from_staging_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        include_failed: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if not include_failed and row.get("status") == "failed":
                continue
            legacy_collection = str(row.get("legacy_collection") or "")
            dataset = self._dataset_for_legacy_collection(legacy_collection)
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            record = dict(payload)
            record.setdefault("legacy_collection", legacy_collection)
            record.setdefault("legacy_id", str(row.get("legacy_id") or ""))
            record.setdefault("_row_no", row.get("row_no"))
            records_by_dataset.setdefault(dataset, []).append(record)
        return records_by_dataset

    def _map_staging_rows(
        self,
        *,
        staging_rows: list[dict[str, Any]],
        migration_run_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, list[str]]], list[dict[str, Any]]]:
        target_rows: list[dict[str, Any]] = []
        legacy_id_map_rows: list[dict[str, Any]] = []
        row_hashes: list[dict[str, Any]] = []
        invalid_enums: dict[str, dict[str, set[str]]] = {}
        findings: list[dict[str, Any]] = []
        for row in staging_rows:
            legacy_collection = str(row.get("legacy_collection") or "")
            legacy_id = str(row.get("legacy_id") or "")
            row_no = int(row.get("row_no") or 0)
            dataset = self._dataset_for_legacy_collection(legacy_collection)
            mapping = DATASET_MAPPINGS.get(dataset)
            source_record = dict(row.get("payload") or {})
            payload = source_record.get("payload") if isinstance(source_record.get("payload"), dict) else source_record
            actual_hash = self.record_sha256(source_record)
            expected_hash = str(row.get("payload_hash") or "")
            row_hashes.append(
                {
                    "object_type": dataset,
                    "legacy_id": legacy_id,
                    "source_line": row_no,
                    "staging_payload_hash": expected_hash,
                    "computed_payload_hash": actual_hash,
                    "matched": bool(expected_hash and expected_hash == actual_hash),
                }
            )
            if expected_hash and expected_hash != actual_hash:
                findings.append(
                    self._finding(
                        code="ROW_HASH_MISMATCH",
                        message="staging.mongo_import_rows.payload_hash does not match payload.",
                        object_type=dataset,
                        legacy_id=legacy_id,
                        source_line=row_no,
                        dimension="row_hash",
                        expected=expected_hash,
                        actual=actual_hash,
                    )
                )
            if row.get("status") == "failed":
                findings.append(
                    self._finding(
                        code="BLOCKED_FACT_SOURCE",
                        message=str(row.get("error_message") or "Staging row status is failed."),
                        object_type=dataset,
                        legacy_id=legacy_id,
                        source_line=row_no,
                        dimension="staging_status",
                        status="failed",
                        actual=row.get("error_code"),
                    )
                )
                continue
            if mapping is None or not mapping.migrates:
                findings.append(
                    self._finding(
                        code="MAPPING_BLOCKER",
                        message="No explicit PostgreSQL target mapping exists for this app Mongo dataset.",
                        object_type=dataset,
                        legacy_collection=legacy_collection,
                        legacy_id=legacy_id,
                        source_line=row_no,
                        dimension="legacy_id_coverage",
                    )
                )
                continue
            status = payload.get("status")
            if status not in (None, "") and mapping.status_values and str(status) not in mapping.status_values:
                invalid_enums.setdefault(dataset, {}).setdefault("status", set()).add(str(status))
                findings.append(
                    self._finding(
                        code="INVALID_ENUM",
                        message="Status value is not allowed by the target PostgreSQL check constraint.",
                        object_type=dataset,
                        legacy_id=legacy_id,
                        source_line=row_no,
                        dimension="status_distribution",
                        status=str(status),
                        expected=list(mapping.status_values),
                        actual=str(status),
                    )
                )
                continue
            primary_table = mapping.target_tables[0]
            target_id = str(uuid5(NAMESPACE_URL, f"{migration_run_id}:{legacy_collection}:{legacy_id}:{primary_table}"))
            partition_month = self._partition_month(dataset=dataset, payload=payload)
            target_row = {
                "source_dataset": dataset,
                "legacy_collection": legacy_collection,
                "legacy_id": legacy_id,
                "source_line": row_no,
                "target_schema": primary_table.split(".", 1)[0],
                "target_table": primary_table.split(".", 1)[1],
                "target_id": target_id,
                "target_tables": list(mapping.target_tables),
                "supporting_tables": list(mapping.supporting_tables),
                "target_partition_month": partition_month,
                "payload_hash": expected_hash or actual_hash,
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
                    "target_partition_month": partition_month,
                    "payload_hash": target_row["payload_hash"],
                    "migration_run_id": migration_run_id,
                    "source_line": row_no,
                }
            )
        enum_report = {
            dataset: {field_name: sorted(values) for field_name, values in fields.items()}
            for dataset, fields in sorted(invalid_enums.items())
        }
        return target_rows, legacy_id_map_rows, row_hashes, enum_report, findings

    def _records_from_target_rows(self, target_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        for row in target_rows:
            dataset = str(row["source_dataset"])
            records_by_dataset.setdefault(dataset, []).append(
                {
                    "legacy_collection": row["legacy_collection"],
                    "legacy_id": row["legacy_id"],
                    "_row_no": row["source_line"],
                    "payload": row["payload"],
                }
            )
        return records_by_dataset

    def _metric_snapshot(self, records_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "record_counts": {},
            "amount_totals": {},
            "month_distribution": {},
            "status_distribution": {},
            "hashes": {},
            "failed_row_reasons": [],
        }
        for dataset, records in sorted(records_by_dataset.items()):
            snapshot["record_counts"][dataset] = len(records)
            snapshot["hashes"][dataset] = self._records_hash(records)
            for record in records:
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
                legacy_id = str(record.get("legacy_id") or "")
                row_no = int(record.get("_row_no") or 0)
                self._add_status(snapshot, dataset=dataset, payload=payload)
                self._add_month(snapshot, dataset=dataset, payload=payload)
                self._add_amounts(snapshot, dataset=dataset, payload=payload, legacy_id=legacy_id, row_no=row_no)
        snapshot["amount_totals"] = {
            key: str(value.quantize(Decimal("0.01")))
            for key, value in sorted(snapshot["amount_totals"].items())
        }
        return snapshot

    def _add_status(self, snapshot: dict[str, Any], *, dataset: str, payload: dict[str, Any]) -> None:
        status = payload.get("status")
        if status in (None, ""):
            return
        distribution = snapshot["status_distribution"].setdefault(dataset, {})
        status_key = str(status)
        distribution[status_key] = distribution.get(status_key, 0) + 1

    def _add_month(self, snapshot: dict[str, Any], *, dataset: str, payload: dict[str, Any]) -> None:
        month = self._extract_month(dataset=dataset, payload=payload)
        if month is None:
            return
        distribution = snapshot["month_distribution"].setdefault(dataset, {})
        distribution[month] = distribution.get(month, 0) + 1

    def _add_amounts(
        self,
        snapshot: dict[str, Any],
        *,
        dataset: str,
        payload: dict[str, Any],
        legacy_id: str,
        row_no: int,
    ) -> None:
        for field_name in ("amount", "signed_amount", "tax_amount", "total_with_tax"):
            if field_name not in payload or payload.get(field_name) in (None, ""):
                continue
            try:
                amount = Decimal(str(payload.get(field_name)))
            except InvalidOperation:
                snapshot["failed_row_reasons"].append(
                    self._finding(
                        code="AMOUNT_PARSE_ERROR",
                        message=f"Cannot parse amount field {field_name}.",
                        object_type=dataset,
                        legacy_id=legacy_id,
                        source_line=row_no,
                        dimension=field_name,
                        actual=payload.get(field_name),
                    )
                )
                continue
            metric_key = f"{dataset}.{field_name}"
            snapshot["amount_totals"][metric_key] = snapshot["amount_totals"].get(metric_key, Decimal("0")) + amount

    def _compare_source_staging(self, source_metrics: dict[str, Any], staging_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for dimension, code in (
            ("record_counts", "COUNT_MISMATCH"),
            ("amount_totals", "AMOUNT_MISMATCH"),
            ("month_distribution", "MONTH_MISMATCH"),
            ("status_distribution", "STATUS_MISMATCH"),
        ):
            findings.extend(
                self._compare_mapping(
                    code=code,
                    dimension=dimension,
                    expected=source_metrics.get(dimension, {}),
                    actual=staging_metrics.get(dimension, {}),
                )
            )
        findings.extend(staging_metrics.get("failed_row_reasons", []))
        return findings

    def _compare_source_target(self, *, source_metrics: dict[str, Any], target_metrics: dict[str, Any]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for dimension, code in (
            ("record_counts", "COUNT_MISMATCH"),
            ("amount_totals", "AMOUNT_MISMATCH"),
            ("month_distribution", "MONTH_MISMATCH"),
            ("status_distribution", "STATUS_MISMATCH"),
        ):
            expected = {
                key: source_metrics.get(dimension, {}).get(key)
                for key in target_metrics.get(dimension, {})
            }
            findings.extend(
                self._compare_mapping(
                    code=code,
                    dimension=dimension,
                    expected=expected,
                    actual=target_metrics.get(dimension, {}),
                )
            )
        findings.extend(target_metrics.get("failed_row_reasons", []))
        return findings

    def _compare_mapping(
        self,
        *,
        code: str,
        dimension: str,
        expected: dict[str, Any],
        actual: dict[str, Any],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for key in sorted(set(expected) | set(actual)):
            expected_value = expected.get(key)
            actual_value = actual.get(key)
            if expected_value == actual_value:
                continue
            finding: dict[str, Any] = self._finding(
                code=code,
                message=f"{dimension} differs for {key}.",
                object_type=str(key).split(".", 1)[0],
                dimension=dimension,
                expected=expected_value,
                actual=actual_value,
            )
            if dimension == "month_distribution":
                finding["month"] = self._first_diff_key(expected_value, actual_value)
            if dimension == "status_distribution":
                finding["status"] = self._first_diff_key(expected_value, actual_value)
            findings.append(finding)
        return findings

    def _manifest_findings(
        self,
        *,
        export_dir: Path,
        manifest: dict[str, Any],
        source_records: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        expected_counts = manifest.get("record_counts") or {}
        for dataset, expected in sorted(expected_counts.items()):
            actual = len(source_records.get(str(dataset), []))
            if int(expected or 0) != actual:
                findings.append(
                    self._finding(
                        code="COUNT_MISMATCH",
                        message="Manifest record count does not match NDJSON row count.",
                        object_type=str(dataset),
                        dimension="record_counts",
                        expected=int(expected or 0),
                        actual=actual,
                    )
                )
        checksums = manifest.get("checksums") or {}
        files = (manifest.get("output") or {}).get("files") or {}
        for dataset, filename in sorted(files.items()):
            expected = checksums.get(filename)
            path = export_dir / str(filename)
            if not expected or not path.exists():
                continue
            actual = self.file_sha256(path)
            if str(expected) != actual:
                findings.append(
                    self._finding(
                        code="SOURCE_HASH_MISMATCH",
                        message="Manifest NDJSON checksum does not match file content.",
                        object_type=str(dataset),
                        dimension=str(filename),
                        expected=str(expected),
                        actual=actual,
                    )
                )
        return findings

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
        expected = [
            {
                "dataset": dataset,
                "legacy_collection": str(record.get("legacy_collection") or dataset),
                "legacy_id": str(record.get("legacy_id") or ""),
                "source_line": record.get("_row_no"),
            }
            for dataset, records in sorted(source_records_by_dataset.items())
            for record in records
        ]
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
        return [
            self._finding(
                code="UNMAPPED_LEGACY_ID",
                message="Source legacy id has no target mapping row.",
                object_type=item.get("dataset"),
                legacy_collection=item.get("legacy_collection"),
                legacy_id=item.get("legacy_id"),
                source_line=item.get("source_line"),
                dimension="legacy_id_coverage",
            )
            for item in coverage.get("missing", [])
        ]

    def _dataset_for_legacy_collection(self, legacy_collection: str) -> str:
        return LEGACY_COLLECTION_TO_DATASET.get(legacy_collection, legacy_collection)

    def _target_payload(self, *, dataset: str, payload: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:
        result = dict(payload)
        result.setdefault("legacy_collection", source_record.get("legacy_collection") or dataset)
        result.setdefault("legacy_id", source_record.get("legacy_id"))
        result.setdefault("raw_payload", payload)
        return result

    def _partition_month(self, *, dataset: str, payload: dict[str, Any]) -> str | None:
        month = self._extract_month(dataset=dataset, payload=payload)
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

    def _extract_month(self, *, dataset: str, payload: dict[str, Any]) -> str | None:
        field_candidates = {
            "bank_transactions": ("txn_date", "trade_time", "created_at"),
            "invoices": ("invoice_date", "created_at"),
            "import_batches": ("imported_at", "created_at"),
            "file_objects": ("created_at",),
            "oa_applications": ("source_updated_at", "approved_at", "created_at"),
            "workbench_read_models": ("scope_month", "created_at", "updated_at"),
        }.get(dataset, ("created_at", "updated_at"))
        for field_name in field_candidates:
            value = payload.get(field_name)
            if not value:
                continue
            text = str(value)
            if len(text) >= 7:
                return text[:7]
        return None

    def _records_hash(self, records: Iterable[dict[str, Any]]) -> str:
        digest = hashlib.sha256()
        for record in records:
            digest.update(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            digest.update(b"\n")
        return digest.hexdigest()

    def _decision(self, findings: list[dict[str, Any]]) -> dict[str, Any]:
        has_blockers = any(item.get("severity") == "error" for item in findings)
        return {
            "go_no_go": "NO_GO" if has_blockers else "GO",
            "reason": "Blocking findings exist." if has_blockers else "Dry-run reconciliation passed.",
            "required_action": "Fix mapping/import/partition/hash issue and rerun dry-run."
            if has_blockers
            else "Eligible for human gate review; this dry-run does not authorize production cutover.",
        }

    def _finding(
        self,
        *,
        code: str,
        message: str,
        severity: str = "error",
        object_type: Any = None,
        legacy_collection: Any = None,
        legacy_id: Any = None,
        source_line: Any = None,
        dimension: Any = None,
        month: Any = None,
        status: Any = None,
        expected: Any = None,
        actual: Any = None,
    ) -> dict[str, Any]:
        finding = {"severity": severity, "code": code, "message": message}
        for key, value in {
            "object_type": object_type,
            "legacy_collection": legacy_collection,
            "legacy_id": legacy_id,
            "source_line": source_line,
            "dimension": dimension,
            "month": month,
            "status": status,
            "expected": expected,
            "actual": actual,
        }.items():
            if value is not None:
                finding[key] = value
        return finding

    def _first_diff_key(self, expected: Any, actual: Any) -> str | None:
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return None
        for key in sorted(set(expected) | set(actual)):
            if expected.get(key) != actual.get(key):
                return str(key)
        return None

    @staticmethod
    def file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def record_sha256(record: dict[str, Any]) -> str:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        cursor.execute(
            "delete from staging.legacy_id_map where migration_run_id = %s",
            (report.migration_run_id,),
        )
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
