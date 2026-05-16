from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


IMPORT_TOOL_VERSION = "app-mongo-staging-import-v1"


TARGET_TABLE_BY_DATASET = {
    "import_batches": "app.import_batches",
    "bank_transactions": "app.bank_transactions",
    "bank_transaction_categories": "app.bank_transaction_categories",
    "invoices": "app.invoices",
    "file_objects": "app.file_objects",
    "matching_runs": "app.reconciliation_cases",
    "matching_results": "app.reconciliation_case_rows",
    "workbench_overrides": "app.workbench_row_overrides",
    "workbench_exception_cases": "app.workbench_exception_cases",
    "workbench_pair_relations": "app.reconciliation_cases",
    "workbench_read_models": "read_model.workbench_rows",
    "workbench_candidate_matches": "read_model.workbench_candidate_matches",
    "workbench_matching_dirty_scopes": "job.worker_tasks",
    "no_oa_bank_batches": "app.no_oa_bank_batches",
    "no_oa_bank_batch_audit_log": "audit.events",
    "turnover_relations": "app.turnover_relations",
    "turnover_relation_audit_log": "audit.events",
    "turnover_ledger_extras": "audit.events",
    "cost_statistics_read_models": "read_model.cost_statistics_read_models",
    "tax_offset_read_models": "read_model.tax_offset_read_models",
    "oa_attachment_invoice_cache": "app.oa_attachments",
    "oa_sync_state": "app.oa_sync_watermarks",
    "app_settings": "audit.events",
    "tax_certified_import_sessions": "app.import_batches",
    "tax_certified_import_batches": "app.import_batches",
    "tax_certified_import_records": "app.invoice_certifications",
    "etc_state": "audit.events",
    "etc_reconciliation_state": "audit.events",
    "background_jobs": "job.worker_tasks",
    "app_health_alerts": "job.worker_tasks",
    "gridfs-files-manifest": "app.file_objects",
}


@dataclass(slots=True)
class ValidationReport:
    migration_run_id: str
    manifest_id: str
    started_at: str
    finished_at: str | None = None
    findings: list[dict[str, Any]] = field(default_factory=list)
    expected_collection_counts: dict[str, int] = field(default_factory=dict)
    actual_imported_counts: dict[str, int] = field(default_factory=dict)
    failed_row_counts: dict[str, int] = field(default_factory=dict)
    input_file_hash_validation: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_metrics: dict[str, Any] = field(default_factory=dict)
    actual_metrics: dict[str, Any] = field(default_factory=dict)
    schema_notes: list[dict[str, str]] = field(default_factory=list)

    @property
    def has_blocking_findings(self) -> bool:
        return any(item.get("severity") == "error" for item in self.findings)

    @property
    def decision(self) -> dict[str, str]:
        if self.has_blocking_findings:
            return {
                "go_no_go": "NO_GO",
                "reason": "Blocking findings exist.",
                "required_action": "Fix source export, manifest, or staging import blocker and rerun.",
            }
        return {
            "go_no_go": "GO",
            "reason": "Manifest, file hashes, row parsing, and staging import plan validation passed.",
            "required_action": "Proceed only to the separate 06C staging-to-facts dry-run gate.",
        }

    def add_finding(
        self,
        *,
        code: str,
        message: str,
        severity: str = "error",
        object_type: str | None = None,
        legacy_id: str | None = None,
        row_no: int | None = None,
        source_file: str | None = None,
        dimension: str | None = None,
        expected: Any = None,
        actual: Any = None,
    ) -> None:
        finding = {
            "severity": severity,
            "code": code,
            "message": message,
        }
        for key, value in {
            "object_type": object_type,
            "legacy_id": legacy_id,
            "row_no": row_no,
            "source_file": source_file,
            "dimension": dimension,
            "expected": expected,
            "actual": actual,
        }.items():
            if value is not None:
                finding[key] = value
        self.findings.append(finding)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": IMPORT_TOOL_VERSION,
            "phase": "staging_import",
            "status": "failed" if self.has_blocking_findings else "passed",
            "blocking": self.has_blocking_findings,
            "migration_run_id": self.migration_run_id,
            "manifest_id": self.manifest_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "expected_collection_counts": self.expected_collection_counts,
            "actual_imported_counts": self.actual_imported_counts,
            "failed_row_counts": self.failed_row_counts,
            "input_file_hash_validation": self.input_file_hash_validation,
            "source_metrics": self.source_metrics,
            "actual_metrics": self.actual_metrics,
            "schema_notes": self.schema_notes,
            "findings": self.findings,
            "decision": self.decision,
        }


@dataclass(slots=True)
class StagingImportPlan:
    migration_run_id: str
    manifest_record: dict[str, Any]
    rows: list[dict[str, Any]]
    legacy_id_map_draft: list[dict[str, Any]]
    report: ValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": IMPORT_TOOL_VERSION,
            "migration_run_id": self.migration_run_id,
            "manifest_record": self.manifest_record,
            "rows": self.rows,
            "legacy_id_map_draft": self.legacy_id_map_draft,
            "report": self.report.to_dict(),
        }


class AppMongoStagingImportBuilder:
    def build_plan(self, *, export_dir: Path, migration_run_id: str | None = None) -> StagingImportPlan:
        started_at = datetime.now(UTC).isoformat()
        manifest_id = self._coerce_migration_run_id(migration_run_id)
        report = ValidationReport(migration_run_id=manifest_id, manifest_id=manifest_id, started_at=started_at)
        manifest_path = export_dir / "manifest.json"
        manifest = self._read_manifest(manifest_path=manifest_path, report=report)
        records_by_dataset = self._read_records(export_dir=export_dir, manifest=manifest, report=report)
        rows = self._build_staging_rows(manifest_id=manifest_id, records_by_dataset=records_by_dataset, report=report)
        metrics = self._build_metric_snapshot(records_by_dataset, report=report)
        report.source_metrics = self._build_manifest_metric_snapshot(manifest)
        report.actual_metrics = metrics
        report.expected_collection_counts = report.source_metrics.get("record_counts", {})
        report.actual_imported_counts = self._count_rows_by_status(rows, status="parsed")
        report.failed_row_counts = self._count_rows_by_status(rows, status="failed")
        self._validate_manifest_counts(manifest=manifest, records_by_dataset=records_by_dataset, rows=rows, report=report)
        self._validate_manifest_checksums(export_dir=export_dir, manifest=manifest, report=report)
        self._validate_file_checksum_samples(records_by_dataset.get("gridfs-files-manifest", []), report=report)
        self._add_schema_notes(report)

        manifest_record = {
            "id": manifest_id,
            "source_database": str((manifest.get("source") or {}).get("database") or "unknown"),
            "export_name": export_dir.name,
            "exported_at": (
                manifest.get("export_finished_at")
                or manifest.get("finished_at")
                or manifest.get("export_started_at")
                or manifest.get("started_at")
                or started_at
            ),
            "collection_count": len(report.expected_collection_counts),
            "document_count": sum(report.expected_collection_counts.values()),
            "sha256_manifest": self.file_sha256(manifest_path) if manifest_path.exists() else "",
            "storage_uri": export_dir.name,
            "created_by": IMPORT_TOOL_VERSION,
        }
        report.finished_at = datetime.now(UTC).isoformat()
        legacy_id_map_draft = self._build_legacy_id_map_draft(migration_run_id=manifest_id, rows=rows)
        return StagingImportPlan(
            migration_run_id=manifest_id,
            manifest_record=manifest_record,
            rows=rows,
            legacy_id_map_draft=legacy_id_map_draft,
            report=report,
        )

    def _read_manifest(self, *, manifest_path: Path, report: ValidationReport) -> dict[str, Any]:
        if not manifest_path.exists():
            report.add_finding(
                code="MISSING_MANIFEST",
                message="manifest.json is required in the 06A export directory.",
                source_file="manifest.json",
            )
            return {}
        try:
            parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            report.add_finding(
                code="INVALID_MANIFEST_JSON",
                message=str(exc),
                source_file="manifest.json",
            )
            return {}
        if not isinstance(parsed, dict):
            report.add_finding(
                code="INVALID_MANIFEST",
                message="manifest.json must contain a JSON object.",
                source_file="manifest.json",
            )
            return {}
        return parsed

    def _read_records(
        self,
        *,
        export_dir: Path,
        manifest: dict[str, Any],
        report: ValidationReport,
    ) -> dict[str, list[dict[str, Any]]]:
        files = (manifest.get("output") or {}).get("files") or {}
        if not isinstance(files, dict):
            report.add_finding(code="INVALID_MANIFEST", message="manifest.output.files must be an object")
            return {}

        records_by_dataset: dict[str, list[dict[str, Any]]] = {}
        for dataset, filename_value in sorted(files.items(), key=lambda item: str(item[0])):
            dataset_name = str(dataset)
            filename = str(filename_value)
            path = export_dir / filename
            records_by_dataset[dataset_name] = []
            if not path.exists():
                expected_count = int((manifest.get("record_counts") or {}).get(dataset_name) or 0)
                if expected_count:
                    report.add_finding(
                        code="MISSING_EXPORT_FILE",
                        message=f"Expected export file is missing: {filename}",
                        object_type=dataset_name,
                        source_file=filename,
                        expected=expected_count,
                        actual=0,
                    )
                continue
            with path.open("r", encoding="utf-8") as handle:
                for row_no, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        parsed = json.loads(line)
                    except json.JSONDecodeError as exc:
                        report.add_finding(
                            code="NDJSON_PARSE_ERROR",
                            message=str(exc),
                            object_type=dataset_name,
                            row_no=row_no,
                            source_file=filename,
                        )
                        records_by_dataset[dataset_name].append(
                            self._failed_raw_record(
                                dataset=dataset_name,
                                filename=filename,
                                row_no=row_no,
                                raw_line=line.rstrip("\n"),
                                error_code="NDJSON_PARSE_ERROR",
                                error_summary=str(exc),
                            )
                        )
                        continue
                    if not isinstance(parsed, dict):
                        report.add_finding(
                            code="NDJSON_ROW_NOT_OBJECT",
                            message="NDJSON row must be a JSON object.",
                            object_type=dataset_name,
                            row_no=row_no,
                            source_file=filename,
                        )
                        records_by_dataset[dataset_name].append(
                            self._failed_raw_record(
                                dataset=dataset_name,
                                filename=filename,
                                row_no=row_no,
                                raw_line=line.rstrip("\n"),
                                error_code="NDJSON_ROW_NOT_OBJECT",
                                error_summary="NDJSON row must be a JSON object.",
                            )
                        )
                        continue
                    parsed["_source_file"] = filename
                    parsed["_source_line"] = row_no
                    records_by_dataset[dataset_name].append(parsed)
        return records_by_dataset

    def _failed_raw_record(
        self,
        *,
        dataset: str,
        filename: str,
        row_no: int,
        raw_line: str,
        error_code: str,
        error_summary: str,
    ) -> dict[str, Any]:
        return {
            "legacy_collection": dataset,
            "legacy_id": f"__failed__:{filename}:{row_no}",
            "payload": {"raw_line": raw_line},
            "_source_file": filename,
            "_source_line": row_no,
            "_import_status": "failed",
            "_error_code": error_code,
            "_error_summary": error_summary,
        }

    def _build_staging_rows(
        self,
        *,
        manifest_id: str,
        records_by_dataset: dict[str, list[dict[str, Any]]],
        report: ValidationReport,
    ) -> list[dict[str, Any]]:
        staging_rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for dataset, records in sorted(records_by_dataset.items()):
            target_table = TARGET_TABLE_BY_DATASET.get(dataset)
            for record in records:
                row_no = int(record.get("_source_line") or len(staging_rows) + 1)
                source_file = str(record.get("_source_file") or "")
                legacy_collection = str(record.get("legacy_collection") or dataset)
                legacy_id = str(record.get("legacy_id") or f"{dataset}:{row_no}")
                raw_payload = {
                    key: value
                    for key, value in record.items()
                    if not key.startswith("_")
                }
                if record.get("_import_status") == "failed" and isinstance(record.get("payload"), dict):
                    raw_payload = dict(record["payload"])
                status = str(record.get("_import_status") or "parsed")
                error_code = record.get("_error_code")
                error_summary = record.get("_error_summary")
                if status != "failed":
                    key = (legacy_collection, legacy_id)
                    if key in seen:
                        status = "failed"
                        error_code = "DUPLICATE_LEGACY_ID"
                        error_summary = "Duplicate legacy id in export dataset."
                        report.add_finding(
                            code="DUPLICATE_LEGACY_ID",
                            message=error_summary,
                            object_type=dataset,
                            legacy_id=legacy_id,
                            row_no=row_no,
                            source_file=source_file,
                        )
                        legacy_id = f"__duplicate__:{legacy_collection}:{legacy_id}:{row_no}"
                    else:
                        seen.add(key)
                payload = {
                    **raw_payload,
                    "_staging_import": {
                        "source_file": source_file,
                        "source_line": row_no,
                        "import_status": status,
                        "error_code": error_code,
                        "error_summary": error_summary,
                    },
                }
                row_hash = self.record_sha256(raw_payload)
                staging_rows.append(
                    {
                        "manifest_id": manifest_id,
                        "legacy_collection": legacy_collection,
                        "legacy_id": legacy_id,
                        "row_no": row_no,
                        "payload": payload,
                        "raw_payload": raw_payload,
                        "payload_hash": row_hash,
                        "row_hash": row_hash,
                        "target_table": target_table,
                        "status": status,
                        "import_status": status,
                        "source_file": source_file,
                        "source_line": row_no,
                        "error_code": error_code,
                        "error_message": error_summary,
                        "error_summary": error_summary,
                    }
                )
        return staging_rows

    def _build_metric_snapshot(
        self,
        records_by_dataset: dict[str, list[dict[str, Any]]],
        *,
        report: ValidationReport,
    ) -> dict[str, Any]:
        snapshot: dict[str, Any] = {
            "record_counts": {},
            "amount_totals": {},
            "month_distribution": {},
            "status_distribution": {},
            "file_checksum_samples": [],
        }
        for dataset, records in sorted(records_by_dataset.items()):
            parsed_records = [record for record in records if record.get("_import_status") != "failed"]
            snapshot["record_counts"][dataset] = len(parsed_records)
            for record in parsed_records:
                payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
                legacy_id = str(record.get("legacy_id") or "")
                self._add_status(snapshot, dataset=dataset, payload=payload)
                self._add_month(snapshot, dataset=dataset, payload=payload)
                self._add_amounts(snapshot, dataset=dataset, payload=payload, legacy_id=legacy_id, report=report)
                self._add_file_checksum_sample(snapshot, dataset=dataset, payload=payload, legacy_id=legacy_id)
        snapshot["amount_totals"] = {
            key: str(value.quantize(Decimal("0.01")))
            for key, value in sorted(snapshot["amount_totals"].items())
        }
        return snapshot

    def _build_manifest_metric_snapshot(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return {
            "record_counts": {
                str(dataset): int(count or 0)
                for dataset, count in sorted((manifest.get("record_counts") or {}).items())
            },
            "hashes": {
                str(filename): str(checksum)
                for filename, checksum in sorted((manifest.get("checksums") or {}).items())
            },
        }

    def _validate_manifest_counts(
        self,
        *,
        manifest: dict[str, Any],
        records_by_dataset: dict[str, list[dict[str, Any]]],
        rows: list[dict[str, Any]],
        report: ValidationReport,
    ) -> None:
        expected_counts = manifest.get("record_counts") or {}
        for dataset, expected in sorted(expected_counts.items()):
            total_seen = len(records_by_dataset.get(str(dataset), []))
            actual_imported = sum(
                1
                for row in rows
                if row["source_file"] == self._filename_for_dataset(manifest, str(dataset)) and row["status"] == "parsed"
            )
            if int(expected or 0) != int(total_seen):
                report.add_finding(
                    code="COUNT_MISMATCH",
                    message="Manifest record count does not match NDJSON physical row count.",
                    object_type=str(dataset),
                    expected=int(expected or 0),
                    actual=int(total_seen),
                )
            if actual_imported + report.failed_row_counts.get(str(dataset), 0) != int(total_seen):
                report.add_finding(
                    code="STAGING_ROW_COUNT_MISMATCH",
                    message="Parsed plus failed staging rows do not match observed source rows.",
                    object_type=str(dataset),
                    expected=int(total_seen),
                    actual=actual_imported + report.failed_row_counts.get(str(dataset), 0),
                )

    def _validate_manifest_checksums(
        self,
        *,
        export_dir: Path,
        manifest: dict[str, Any],
        report: ValidationReport,
    ) -> None:
        checksums = manifest.get("checksums") or {}
        files = (manifest.get("output") or {}).get("files") or {}
        for dataset, filename_value in sorted(files.items()):
            filename = str(filename_value)
            expected = checksums.get(filename)
            path = export_dir / filename
            if not path.exists():
                continue
            actual = self.file_sha256(path)
            validation = {
                "object_type": str(dataset),
                "expected_sha256": str(expected) if expected else None,
                "actual_sha256": actual,
                "matched": bool(expected and str(expected) == actual),
            }
            report.input_file_hash_validation[filename] = validation
            if not expected:
                report.add_finding(
                    code="FILE_CHECKSUM_MISSING",
                    message="Manifest missing checksum for input file.",
                    object_type=str(dataset),
                    source_file=filename,
                )
            elif str(expected) != actual:
                report.add_finding(
                    code="FILE_CHECKSUM_MISMATCH",
                    message="Manifest file checksum does not match file content.",
                    object_type=str(dataset),
                    source_file=filename,
                    dimension=filename,
                    expected=str(expected),
                    actual=actual,
                )

    def _validate_file_checksum_samples(self, records: list[dict[str, Any]], *, report: ValidationReport) -> None:
        for record in records:
            if record.get("_import_status") == "failed":
                continue
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
            expected = payload.get("sha256") or payload.get("expected_sha256")
            actual = payload.get("sample_sha256") or payload.get("actual_sha256")
            if expected and actual and expected != actual:
                report.add_finding(
                    code="FILE_CHECKSUM_MISMATCH",
                    message="File checksum sample mismatch.",
                    object_type="gridfs-files-manifest",
                    legacy_id=str(record.get("legacy_id") or ""),
                    row_no=record.get("_source_line"),
                    source_file=record.get("_source_file"),
                    expected=expected,
                    actual=actual,
                )

    def _build_legacy_id_map_draft(self, *, migration_run_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        draft = []
        for row in rows:
            if row["status"] != "parsed":
                continue
            draft.append(
                {
                    "migration_run_id": migration_run_id,
                    "source_system": "app_mongo",
                    "legacy_collection": row["legacy_collection"],
                    "legacy_id": row["legacy_id"],
                    "payload_hash": row["payload_hash"],
                    "target_schema": None,
                    "target_table": row["target_table"],
                    "target_id": None,
                    "status": "requires_06c_fact_mapping",
                }
            )
        return draft

    def _add_schema_notes(self, report: ValidationReport) -> None:
        report.schema_notes.append(
            {
                "code": "LEGACY_ID_MAP_DEFERRED_TO_06C",
                "message": (
                    "staging.legacy_id_map target_schema, target_table, and target_id require facts mapping; "
                    "06B emits legacy_id_map_draft but does not write the table."
                ),
            }
        )

    @staticmethod
    def _coerce_migration_run_id(migration_run_id: str | None) -> str:
        value = migration_run_id or str(uuid4())
        return str(UUID(value))

    @staticmethod
    def _filename_for_dataset(manifest: dict[str, Any], dataset: str) -> str:
        files = (manifest.get("output") or {}).get("files") or {}
        return str(files.get(dataset) or "")

    @staticmethod
    def _count_rows_by_status(rows: list[dict[str, Any]], *, status: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            if row["status"] != status:
                continue
            key = str(row["legacy_collection"])
            counts[key] = counts.get(key, 0) + 1
        return counts

    @staticmethod
    def _add_status(snapshot: dict[str, Any], *, dataset: str, payload: dict[str, Any]) -> None:
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
        report: ValidationReport,
    ) -> None:
        for field_name in ("amount", "signed_amount", "tax_amount", "total_with_tax"):
            if field_name not in payload or payload.get(field_name) in (None, ""):
                continue
            try:
                amount = Decimal(str(payload.get(field_name)))
            except InvalidOperation:
                report.add_finding(
                    code="AMOUNT_PARSE_ERROR",
                    message=f"Cannot parse amount field {field_name}.",
                    object_type=dataset,
                    legacy_id=legacy_id,
                    dimension=field_name,
                    actual=payload.get(field_name),
                )
                continue
            metric_key = f"{dataset}.{field_name}"
            snapshot["amount_totals"][metric_key] = snapshot["amount_totals"].get(metric_key, Decimal("0")) + amount

    @staticmethod
    def _add_file_checksum_sample(
        snapshot: dict[str, Any],
        *,
        dataset: str,
        payload: dict[str, Any],
        legacy_id: str,
    ) -> None:
        if dataset != "gridfs-files-manifest":
            return
        expected = payload.get("sha256") or payload.get("expected_sha256")
        actual = payload.get("sample_sha256") or payload.get("actual_sha256")
        if expected or actual:
            snapshot["file_checksum_samples"].append(
                {
                    "legacy_id": legacy_id,
                    "expected": expected,
                    "actual": actual,
                    "matched": bool(expected and actual and expected == actual),
                }
            )

    @staticmethod
    def _extract_month(*, dataset: str, payload: dict[str, Any]) -> str | None:
        field_candidates = {
            "bank_transactions": ("txn_date", "trade_time", "created_at"),
            "invoices": ("invoice_date", "created_at"),
            "import_batches": ("imported_at", "created_at"),
            "file_objects": ("created_at",),
        }.get(dataset, ("created_at", "updated_at"))
        for field_name in field_candidates:
            value = payload.get(field_name)
            if not value:
                continue
            text = str(value)
            if len(text) >= 7:
                return text[:7]
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


def compare_metric_snapshots(expected: dict[str, Any], actual: dict[str, Any]) -> ValidationReport:
    now = datetime.now(UTC).isoformat()
    report = ValidationReport(
        migration_run_id="00000000-0000-4000-8000-000000000000",
        manifest_id="00000000-0000-4000-8000-000000000000",
        started_at=now,
        finished_at=now,
        source_metrics=expected,
        actual_metrics=actual,
    )
    _compare_mapping(
        report,
        code="COUNT_MISMATCH",
        dimension="record_counts",
        expected=expected.get("record_counts", {}),
        actual=actual.get("record_counts", {}),
    )
    _compare_mapping(
        report,
        code="AMOUNT_MISMATCH",
        dimension="amount_totals",
        expected=expected.get("amount_totals", {}),
        actual=actual.get("amount_totals", {}),
    )
    _compare_mapping(
        report,
        code="MONTH_MISMATCH",
        dimension="month_distribution",
        expected=expected.get("month_distribution", {}),
        actual=actual.get("month_distribution", {}),
    )
    _compare_mapping(
        report,
        code="STATUS_MISMATCH",
        dimension="status_distribution",
        expected=expected.get("status_distribution", {}),
        actual=actual.get("status_distribution", {}),
    )
    for sample in actual.get("file_checksum_samples", []) or []:
        if sample.get("expected") and sample.get("actual") and sample.get("expected") != sample.get("actual"):
            report.add_finding(
                code="FILE_CHECKSUM_MISMATCH",
                message="File checksum sample mismatch.",
                object_type="gridfs-files-manifest",
                legacy_id=sample.get("legacy_id"),
                expected=sample.get("expected"),
                actual=sample.get("actual"),
            )
    return report


def _compare_mapping(
    report: ValidationReport,
    *,
    code: str,
    dimension: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> None:
    keys = sorted(set(expected) | set(actual))
    for key in keys:
        expected_value = expected.get(key)
        actual_value = actual.get(key)
        if expected_value != actual_value:
            report.add_finding(
                code=code,
                message=f"{dimension} differs for {key}.",
                object_type=str(key),
                dimension=dimension,
                expected=expected_value,
                actual=actual_value,
            )


class StagingImportExecutor:
    def execute(self, connection: Any, plan: StagingImportPlan) -> None:
        if plan.report.has_blocking_findings:
            raise RuntimeError("Refusing to import staging rows while validation has blocking findings.")
        cursor = connection.cursor()
        manifest = plan.manifest_record
        cursor.execute(
            """
            delete from staging.mongo_import_rows where manifest_id = %s
            """,
            (manifest["id"],),
        )
        cursor.execute(
            """
            delete from staging.mongo_export_manifest where id = %s
            """,
            (manifest["id"],),
        )
        cursor.execute(
            """
            insert into staging.mongo_export_manifest (
              id,
              source_database,
              export_name,
              exported_at,
              collection_count,
              document_count,
              sha256_manifest,
              storage_uri,
              created_by
            ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                manifest["id"],
                manifest["source_database"],
                manifest["export_name"],
                manifest["exported_at"],
                manifest["collection_count"],
                manifest["document_count"],
                manifest["sha256_manifest"],
                manifest["storage_uri"],
                manifest["created_by"],
            ),
        )
        for row in plan.rows:
            cursor.execute(
                """
                insert into staging.mongo_import_rows (
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
                ) values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                """,
                (
                    row["manifest_id"],
                    row["legacy_collection"],
                    row["legacy_id"],
                    row["row_no"],
                    json.dumps(row["payload"], ensure_ascii=False, sort_keys=True),
                    row["payload_hash"],
                    row["target_table"],
                    row["status"],
                    row["error_code"],
                    row["error_message"],
                ),
            )
        connection.commit()
