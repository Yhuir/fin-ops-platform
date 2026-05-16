from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


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
    findings: list[dict[str, Any]] = field(default_factory=list)
    source_metrics: dict[str, Any] = field(default_factory=dict)
    actual_metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def has_blocking_findings(self) -> bool:
        return any(item.get("severity") == "error" for item in self.findings)

    def add_finding(
        self,
        *,
        code: str,
        message: str,
        severity: str = "error",
        object_type: str | None = None,
        legacy_id: str | None = None,
        row_no: int | None = None,
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
            "dimension": dimension,
            "expected": expected,
            "actual": actual,
        }.items():
            if value is not None:
                finding[key] = value
        self.findings.append(finding)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "failed" if self.has_blocking_findings else "passed",
            "blocking": self.has_blocking_findings,
            "findings": self.findings,
            "source_metrics": self.source_metrics,
            "actual_metrics": self.actual_metrics,
        }


@dataclass(slots=True)
class StagingImportPlan:
    manifest_record: dict[str, Any]
    rows: list[dict[str, Any]]
    report: ValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": IMPORT_TOOL_VERSION,
            "manifest_record": self.manifest_record,
            "rows": self.rows,
            "report": self.report.to_dict(),
        }


class AppMongoStagingImportBuilder:
    def build_plan(self, *, export_dir: Path, migration_run_id: str | None = None) -> StagingImportPlan:
        manifest_path = export_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_id = str(migration_run_id or uuid4())
        report = ValidationReport()
        records_by_dataset = self._read_records(export_dir=export_dir, manifest=manifest, report=report)
        metrics = self._build_metric_snapshot(records_by_dataset, report=report)
        report.source_metrics = self._build_manifest_metric_snapshot(manifest)
        report.actual_metrics = metrics
        self._validate_duplicate_legacy_ids(records_by_dataset=records_by_dataset, report=report)
        self._validate_manifest_counts(manifest=manifest, metrics=metrics, report=report)
        self._validate_manifest_checksums(export_dir=export_dir, manifest=manifest, report=report)
        self._validate_file_checksum_samples(records_by_dataset.get("gridfs-files-manifest", []), report=report)

        manifest_record = {
            "id": manifest_id,
            "source_database": str((manifest.get("source") or {}).get("database") or "unknown"),
            "export_name": export_dir.name,
            "exported_at": manifest.get("finished_at") or manifest.get("started_at") or datetime.now(UTC).isoformat(),
            "collection_count": len(records_by_dataset),
            "document_count": sum(len(records) for records in records_by_dataset.values()),
            "sha256_manifest": self.file_sha256(manifest_path),
            "storage_uri": str(export_dir),
            "created_by": IMPORT_TOOL_VERSION,
        }
        rows = self._build_staging_rows(
            manifest_id=manifest_id,
            records_by_dataset=records_by_dataset,
        )
        return StagingImportPlan(manifest_record=manifest_record, rows=rows, report=report)

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
        for dataset, filename in sorted(files.items(), key=lambda item: str(item[0])):
            path = export_dir / str(filename)
            records_by_dataset[dataset] = []
            if not path.exists():
                expected_count = int((manifest.get("record_counts") or {}).get(dataset) or 0)
                if expected_count:
                    report.add_finding(
                        code="MISSING_EXPORT_FILE",
                        message=f"Expected export file is missing: {filename}",
                        object_type=dataset,
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
                            object_type=dataset,
                            row_no=row_no,
                        )
                        continue
                    if not isinstance(parsed, dict):
                        report.add_finding(
                            code="NDJSON_ROW_NOT_OBJECT",
                            message="NDJSON row must be a JSON object.",
                            object_type=dataset,
                            row_no=row_no,
                        )
                        continue
                    parsed["_row_no"] = row_no
                    records_by_dataset[dataset].append(parsed)
        return records_by_dataset

    def _build_staging_rows(
        self,
        *,
        manifest_id: str,
        records_by_dataset: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        staging_rows: list[dict[str, Any]] = []
        for dataset, records in sorted(records_by_dataset.items()):
            target_table = TARGET_TABLE_BY_DATASET.get(dataset)
            for record in records:
                row_no = int(record.get("_row_no") or len(staging_rows) + 1)
                payload = {
                    key: value
                    for key, value in record.items()
                    if key != "_row_no"
                }
                staging_rows.append(
                    {
                        "manifest_id": manifest_id,
                        "legacy_collection": str(record.get("legacy_collection") or dataset),
                        "legacy_id": str(record.get("legacy_id") or f"{dataset}:{row_no}"),
                        "row_no": row_no,
                        "payload": payload,
                        "payload_hash": self.record_sha256(payload),
                        "target_table": target_table,
                        "status": "parsed",
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
            snapshot["record_counts"][dataset] = len(records)
            for record in records:
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

    def _add_file_checksum_sample(
        self,
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

    def _validate_manifest_counts(
        self,
        *,
        manifest: dict[str, Any],
        metrics: dict[str, Any],
        report: ValidationReport,
    ) -> None:
        expected_counts = manifest.get("record_counts") or {}
        for dataset, expected in sorted(expected_counts.items()):
            actual = metrics["record_counts"].get(dataset, 0)
            if int(expected or 0) != int(actual):
                report.add_finding(
                    code="COUNT_MISMATCH",
                    message="Manifest record count does not match NDJSON row count.",
                    object_type=dataset,
                    expected=int(expected or 0),
                    actual=int(actual),
                )

    def _validate_duplicate_legacy_ids(
        self,
        *,
        records_by_dataset: dict[str, list[dict[str, Any]]],
        report: ValidationReport,
    ) -> None:
        for dataset, records in sorted(records_by_dataset.items()):
            seen: set[tuple[str, str]] = set()
            for record in records:
                key = (
                    str(record.get("legacy_collection") or dataset),
                    str(record.get("legacy_id") or ""),
                )
                if key[1] == "":
                    continue
                if key in seen:
                    report.add_finding(
                        code="DUPLICATE_LEGACY_ID",
                        message="Duplicate legacy id in export dataset.",
                        object_type=dataset,
                        legacy_id=key[1],
                        row_no=record.get("_row_no"),
                    )
                    continue
                seen.add(key)

    def _validate_manifest_checksums(
        self,
        *,
        export_dir: Path,
        manifest: dict[str, Any],
        report: ValidationReport,
    ) -> None:
        checksums = manifest.get("checksums") or {}
        files = (manifest.get("output") or {}).get("files") or {}
        for dataset, filename in sorted(files.items()):
            expected = checksums.get(filename)
            path = export_dir / str(filename)
            if not expected or not path.exists():
                continue
            actual = self.file_sha256(path)
            if str(expected) != actual:
                report.add_finding(
                    code="FILE_CHECKSUM_MISMATCH",
                    message="Manifest file checksum does not match file content.",
                    object_type=str(dataset),
                    dimension=str(filename),
                    expected=str(expected),
                    actual=actual,
                )

    def _validate_file_checksum_samples(self, records: list[dict[str, Any]], *, report: ValidationReport) -> None:
        for record in records:
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
            expected = payload.get("sha256") or payload.get("expected_sha256")
            actual = payload.get("sample_sha256") or payload.get("actual_sha256")
            if expected and actual and expected != actual:
                report.add_finding(
                    code="FILE_CHECKSUM_MISMATCH",
                    message="File checksum sample mismatch.",
                    object_type="gridfs-files-manifest",
                    legacy_id=str(record.get("legacy_id") or ""),
                    expected=expected,
                    actual=actual,
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
    report = ValidationReport(source_metrics=expected, actual_metrics=actual)
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
                  status
                ) values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
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
                ),
            )
        connection.commit()
