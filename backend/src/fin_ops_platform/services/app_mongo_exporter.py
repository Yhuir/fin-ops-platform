from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from fin_ops_platform.services.state_store import (
    GRIDFS_BUCKET_NAME,
    ApplicationStateStore,
)


EXPORT_TOOL_VERSION = "app-mongo-export-v1"
EXPORT_SCHEMA_VERSION = "finops.app_mongo_export_manifest.v1"
EXPORT_COLLECTIONS_DIR = "collections"


EXPORT_FILE_NAMES = {
    "import_batches": f"{EXPORT_COLLECTIONS_DIR}/import_batches.ndjson",
    "bank_transactions": f"{EXPORT_COLLECTIONS_DIR}/bank_transactions.ndjson",
    "bank_transaction_categories": f"{EXPORT_COLLECTIONS_DIR}/bank_transaction_categories.ndjson",
    "invoices": f"{EXPORT_COLLECTIONS_DIR}/invoices.ndjson",
    "file_objects": f"{EXPORT_COLLECTIONS_DIR}/file_objects.ndjson",
    "matching_runs": f"{EXPORT_COLLECTIONS_DIR}/matching_runs.ndjson",
    "matching_results": f"{EXPORT_COLLECTIONS_DIR}/matching_results.ndjson",
    "workbench_overrides": f"{EXPORT_COLLECTIONS_DIR}/workbench_overrides.ndjson",
    "workbench_exception_cases": f"{EXPORT_COLLECTIONS_DIR}/workbench_exception_cases.ndjson",
    "workbench_pair_relations": f"{EXPORT_COLLECTIONS_DIR}/workbench_pair_relations.ndjson",
    "workbench_read_models": f"{EXPORT_COLLECTIONS_DIR}/workbench_read_models.ndjson",
    "workbench_candidate_matches": f"{EXPORT_COLLECTIONS_DIR}/workbench_candidate_matches.ndjson",
    "workbench_matching_dirty_scopes": f"{EXPORT_COLLECTIONS_DIR}/workbench_matching_dirty_scopes.ndjson",
    "no_oa_bank_batches": f"{EXPORT_COLLECTIONS_DIR}/no_oa_bank_batches.ndjson",
    "no_oa_bank_batch_audit_log": f"{EXPORT_COLLECTIONS_DIR}/no_oa_bank_batch_audit_log.ndjson",
    "turnover_relations": f"{EXPORT_COLLECTIONS_DIR}/turnover_relations.ndjson",
    "turnover_relation_audit_log": f"{EXPORT_COLLECTIONS_DIR}/turnover_relation_audit_log.ndjson",
    "turnover_ledger_extras": f"{EXPORT_COLLECTIONS_DIR}/turnover_ledger_extras.ndjson",
    "cost_statistics_read_models": f"{EXPORT_COLLECTIONS_DIR}/cost_statistics_read_models.ndjson",
    "tax_offset_read_models": f"{EXPORT_COLLECTIONS_DIR}/tax_offset_read_models.ndjson",
    "oa_attachment_invoice_cache": f"{EXPORT_COLLECTIONS_DIR}/oa_attachment_invoice_cache.ndjson",
    "oa_sync_state": f"{EXPORT_COLLECTIONS_DIR}/oa_sync_state.ndjson",
    "app_settings": f"{EXPORT_COLLECTIONS_DIR}/app_settings.ndjson",
    "tax_certified_import_sessions": f"{EXPORT_COLLECTIONS_DIR}/tax_certified_import_sessions.ndjson",
    "tax_certified_import_batches": f"{EXPORT_COLLECTIONS_DIR}/tax_certified_import_batches.ndjson",
    "tax_certified_import_records": f"{EXPORT_COLLECTIONS_DIR}/tax_certified_import_records.ndjson",
    "etc_state": f"{EXPORT_COLLECTIONS_DIR}/etc_state.ndjson",
    "etc_reconciliation_state": f"{EXPORT_COLLECTIONS_DIR}/etc_reconciliation_state.ndjson",
    "background_jobs": f"{EXPORT_COLLECTIONS_DIR}/background_jobs.ndjson",
    "app_health_alerts": f"{EXPORT_COLLECTIONS_DIR}/app_health_alerts.ndjson",
    "gridfs-files-manifest": f"{EXPORT_COLLECTIONS_DIR}/gridfs-files-manifest.ndjson",
}


@dataclass(frozen=True, slots=True)
class AppMongoExportResult:
    manifest: dict[str, Any]
    record_counts: dict[str, int]
    output_dir: Path
    dry_run: bool = False
    validate_only: bool = False

    @property
    def has_errors(self) -> bool:
        validation = self.manifest.get("validation") if isinstance(self.manifest, dict) else {}
        errors = validation.get("errors") if isinstance(validation, dict) else []
        return bool(errors)


class AppMongoExporter:
    """Read-only app Mongo exporter for PostgreSQL migration dry-runs."""

    def __init__(self, store: ApplicationStateStore) -> None:
        self._store = store

    def export(
        self,
        *,
        output_dir: Path,
        dry_run: bool = False,
        validate_only: bool = False,
    ) -> AppMongoExportResult:
        self._ensure_app_mongo_store()
        started_at = datetime.now(UTC)

        records_by_dataset = self._build_records_by_dataset()
        record_counts = {
            dataset: len(records)
            for dataset, records in records_by_dataset.items()
        }
        collection_counts = self._collection_counts()
        validation = self._validate_export_records(
            records_by_dataset=records_by_dataset,
            collection_counts=collection_counts,
        )
        checksums = (
            self._empty_dataset_checksums(records_by_dataset)
            if self._has_validation_error(validation, "INVALID_JSON_PAYLOAD")
            else self._calculate_dataset_checksums(records_by_dataset)
        )
        hashes = self._build_hashes(checksums)
        manifest = self._build_manifest(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            output_dir=output_dir,
            record_counts=record_counts,
            collection_counts=collection_counts,
            checksums=checksums,
            hashes=hashes,
            validation=validation,
            dry_run=dry_run,
            validate_only=validate_only,
        )

        if not (dry_run or validate_only):
            output_dir.mkdir(parents=True, exist_ok=True)
            if not validation["errors"]:
                for dataset, records in records_by_dataset.items():
                    output_path = output_dir / EXPORT_FILE_NAMES[dataset]
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    self._write_ndjson(output_path, records)
            (output_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        return AppMongoExportResult(
            manifest=manifest,
            record_counts=record_counts,
            output_dir=output_dir,
            dry_run=dry_run,
            validate_only=validate_only,
        )

    def _ensure_app_mongo_store(self) -> None:
        if self._store.storage_backend != "mongo":
            raise RuntimeError("app Mongo export requires an app Mongo-backed ApplicationStateStore.")
        if self._store.mongo_database_name is None:
            raise RuntimeError("app Mongo export requires a configured app Mongo database.")

    def _build_records_by_dataset(self) -> dict[str, list[dict[str, Any]]]:
        imports_payload = self._store._load_imports_detailed_payload()  # noqa: SLF001 - reuse trusted state decoding.
        bank_transaction_categories_payload = self._store._load_bank_transaction_categories_detailed_payload()  # noqa: SLF001
        file_imports_payload = self._store._load_file_imports_detailed_payload()  # noqa: SLF001
        matching_payload = self._store._load_matching_detailed_payload()  # noqa: SLF001
        workbench_overrides_payload = self._store._load_workbench_overrides_detailed_payload()  # noqa: SLF001
        workbench_exception_cases_payload = self._store._load_workbench_exception_cases_detailed_payload()  # noqa: SLF001
        workbench_pair_relations_payload = self._store._load_workbench_pair_relations_detailed_payload()  # noqa: SLF001
        workbench_read_models_payload = self._store._load_workbench_read_models_detailed_payload()  # noqa: SLF001
        workbench_candidate_matches_payload = self._store._load_workbench_candidate_matches_detailed_payload()  # noqa: SLF001
        workbench_matching_dirty_scopes_payload = self._store._load_workbench_matching_dirty_scopes_detailed_payload()  # noqa: SLF001
        no_oa_bank_batches_payload = self._store._load_no_oa_bank_batches_detailed_payload()  # noqa: SLF001
        turnover_relations_payload = self._store._load_turnover_relations_detailed_payload()  # noqa: SLF001
        turnover_ledger_extras_payload = self._store._load_turnover_ledger_extras_detailed_payload()  # noqa: SLF001
        cost_statistics_read_models_payload = self._store._load_cost_statistics_read_models_detailed_payload()  # noqa: SLF001
        tax_offset_read_models_payload = self._store._load_tax_offset_read_models_detailed_payload()  # noqa: SLF001
        tax_certified_imports_payload = self._store.load_tax_certified_imports()
        background_jobs_payload = self._store.load_background_jobs()

        return {
            "import_batches": self._records_from_mapping(
                legacy_collection="import_batches",
                values=imports_payload.get("batches", {}),
            ),
            "bank_transactions": self._records_from_sequence(
                legacy_collection="bank_transactions",
                values=imports_payload.get("transactions", []),
            ),
            "bank_transaction_categories": self._records_from_mapping(
                legacy_collection="bank_transaction_categories",
                values=bank_transaction_categories_payload.get("categories", {}),
            ),
            "invoices": self._records_from_sequence(
                legacy_collection="invoices",
                values=imports_payload.get("invoices", []),
            ),
            "file_objects": self._file_object_records(file_imports_payload),
            "matching_runs": self._records_from_mapping(
                legacy_collection="matching_runs",
                values=matching_payload.get("runs", {}),
            ),
            "matching_results": self._records_from_mapping(
                legacy_collection="matching_results",
                values=matching_payload.get("results", {}),
            ),
            "workbench_overrides": self._records_from_mapping(
                legacy_collection="workbench_row_overrides",
                values=workbench_overrides_payload.get("row_overrides", {}),
            ),
            "workbench_exception_cases": self._records_from_mapping(
                legacy_collection="workbench_exception_cases",
                values=workbench_exception_cases_payload.get("cases", {}),
            ),
            "workbench_pair_relations": self._records_from_mapping(
                legacy_collection="workbench_pair_relations",
                values=workbench_pair_relations_payload.get("pair_relations", {}),
            ),
            "workbench_read_models": self._records_from_mapping(
                legacy_collection="workbench_read_models",
                values=workbench_read_models_payload.get("read_models", {}),
            ),
            "workbench_candidate_matches": self._records_from_mapping(
                legacy_collection="workbench_candidate_matches",
                values=workbench_candidate_matches_payload.get("candidates", {}),
            ),
            "workbench_matching_dirty_scopes": self._records_from_mapping(
                legacy_collection="workbench_matching_dirty_scopes",
                values=workbench_matching_dirty_scopes_payload.get("dirty_scopes", {}),
            ),
            "no_oa_bank_batches": self._records_from_mapping(
                legacy_collection="no_oa_bank_batches",
                values=no_oa_bank_batches_payload.get("batches", {}),
            ),
            "no_oa_bank_batch_audit_log": self._records_from_sequence(
                legacy_collection="no_oa_bank_batch_audit_log",
                values=no_oa_bank_batches_payload.get("audit_log", []),
            ),
            "turnover_relations": self._records_from_sequence(
                legacy_collection="turnover_relations",
                values=turnover_relations_payload.get("relations", []),
            ),
            "turnover_relation_audit_log": self._records_from_sequence(
                legacy_collection="turnover_relation_audit_log",
                values=turnover_relations_payload.get("audit_log", []),
            ),
            "turnover_ledger_extras": self._records_from_sequence(
                legacy_collection="turnover_ledger_extras",
                values=turnover_ledger_extras_payload.get("extras", []),
            ),
            "cost_statistics_read_models": self._records_from_mapping(
                legacy_collection="cost_statistics_read_models",
                values=cost_statistics_read_models_payload.get("read_models", {}),
            ),
            "tax_offset_read_models": self._records_from_mapping(
                legacy_collection="tax_offset_read_models",
                values=tax_offset_read_models_payload.get("read_models", {}),
            ),
            "oa_attachment_invoice_cache": self._records_from_collection_documents(
                collection_name="oa_attachment_invoice_cache",
                legacy_collection="oa_attachment_invoice_cache",
            ),
            "oa_sync_state": self._records_from_collection_documents(
                collection_name="oa_sync_state",
                legacy_collection="oa_sync_state",
            ),
            "app_settings": self._records_from_collection_documents(
                collection_name="app_settings",
                legacy_collection="app_settings",
            ),
            "tax_certified_import_sessions": self._records_from_mapping(
                legacy_collection="tax_certified_import_sessions",
                values=tax_certified_imports_payload.get("sessions", {}),
            ),
            "tax_certified_import_batches": self._records_from_mapping(
                legacy_collection="tax_certified_import_batches",
                values=tax_certified_imports_payload.get("batches", {}),
            ),
            "tax_certified_import_records": self._records_from_mapping(
                legacy_collection="tax_certified_import_records",
                values=tax_certified_imports_payload.get("records", {}),
            ),
            "etc_state": self._records_from_collection_documents(
                collection_name="etc_state",
                legacy_collection="etc_state",
            ),
            "etc_reconciliation_state": self._records_from_collection_documents(
                collection_name="etc_reconciliation_state",
                legacy_collection="etc_reconciliation_state",
            ),
            "background_jobs": self._records_from_mapping(
                legacy_collection="background_jobs",
                values=background_jobs_payload,
            ),
            "app_health_alerts": self._records_from_collection_documents(
                collection_name="app_health_alerts",
                legacy_collection="app_health_alerts",
            ),
            "gridfs-files-manifest": self._gridfs_file_records(),
        }

    def _records_from_mapping(self, *, legacy_collection: str, values: Any) -> list[dict[str, Any]]:
        if not isinstance(values, dict):
            return []
        return [
            self._export_record(
                legacy_collection=legacy_collection,
                legacy_id=str(legacy_id),
                payload=payload,
            )
            for legacy_id, payload in sorted(values.items(), key=lambda item: str(item[0]))
        ]

    def _records_from_sequence(self, *, legacy_collection: str, values: Any) -> list[dict[str, Any]]:
        if not isinstance(values, list):
            return []
        records = [
            self._export_record(
                legacy_collection=legacy_collection,
                legacy_id=self._payload_legacy_id(payload, fallback_index=index),
                payload=payload,
            )
            for index, payload in enumerate(values)
        ]
        return sorted(records, key=lambda item: str(item["legacy_id"]))

    def _file_object_records(self, file_imports_payload: dict[str, Any]) -> list[dict[str, Any]]:
        sessions = file_imports_payload.get("sessions", {})
        if not isinstance(sessions, dict):
            return []
        records: list[dict[str, Any]] = []
        for session_id, session in sorted(sessions.items(), key=lambda item: str(item[0])):
            if not isinstance(session, dict):
                continue
            files = session.get("files", [])
            if not isinstance(files, list):
                continue
            for index, file_payload in enumerate(files):
                if not isinstance(file_payload, dict):
                    continue
                legacy_id = str(file_payload.get("id") or f"{session_id}:{index}")
                records.append(
                    self._export_record(
                        legacy_collection="file_import_files",
                        legacy_id=legacy_id,
                        payload={
                            **file_payload,
                            "session_id": str(session_id),
                        },
                    )
                )
        return sorted(records, key=lambda item: str(item["legacy_id"]))

    def _records_from_collection_documents(
        self,
        *,
        collection_name: str,
        legacy_collection: str,
    ) -> list[dict[str, Any]]:
        collection = self._store._mongo_detailed_collections.get(collection_name)  # noqa: SLF001
        if collection is None:
            return []
        records: list[dict[str, Any]] = []
        for document in sorted(collection.find({}), key=lambda item: str(item.get("_id", ""))):
            legacy_id = str(document.get("_id") or "")
            loaded = self._store._load_binary_payload(document)  # noqa: SLF001
            if loaded is None:
                loaded = {
                    key: value
                    for key, value in document.items()
                    if key not in {"_id", "payload"}
                }
            records.append(
                self._export_record(
                    legacy_collection=legacy_collection,
                    legacy_id=legacy_id,
                    payload=loaded,
                )
            )
        return records

    def _gridfs_file_records(self) -> list[dict[str, Any]]:
        database = self._store._mongo_database  # noqa: SLF001 - exporter is bound to app Mongo store internals.
        if database is None:
            return []
        files_collection = database[f"{GRIDFS_BUCKET_NAME}.files"]
        chunks_collection = database[f"{GRIDFS_BUCKET_NAME}.chunks"]
        records = []
        for document in sorted(files_collection.find({}), key=lambda item: str(item.get("_id", ""))):
            file_id = str(document.get("_id", ""))
            chunk_count = chunks_collection.count_documents({"files_id": document.get("_id")})
            records.append(
                {
                    "legacy_collection": f"{GRIDFS_BUCKET_NAME}.files",
                    "legacy_id": file_id,
                    "filename": document.get("filename"),
                    "length": document.get("length"),
                    "chunk_size": document.get("chunkSize"),
                    "chunk_count": chunk_count,
                    "content_type": document.get("contentType") or (document.get("metadata") or {}).get("content_type"),
                    "upload_date": self._normalize(document.get("uploadDate")),
                    "metadata": self._normalize(document.get("metadata") or {}),
                }
            )
        return records

    def _collection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for logical_name, collection in sorted(self._store._mongo_detailed_collections.items()):  # noqa: SLF001
            counts[logical_name] = int(collection.count_documents({}))
        database = self._store._mongo_database  # noqa: SLF001
        if database is not None:
            counts[f"{GRIDFS_BUCKET_NAME}.files"] = int(database[f"{GRIDFS_BUCKET_NAME}.files"].count_documents({}))
            counts[f"{GRIDFS_BUCKET_NAME}.chunks"] = int(database[f"{GRIDFS_BUCKET_NAME}.chunks"].count_documents({}))
        return counts

    def _validate_export_records(
        self,
        *,
        records_by_dataset: dict[str, list[dict[str, Any]]],
        collection_counts: dict[str, int],
    ) -> dict[str, list[dict[str, Any]]]:
        warnings: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for dataset, records in sorted(records_by_dataset.items()):
            if not records:
                warnings.append(
                    {
                        "severity": "warning",
                        "code": "EMPTY_COLLECTION",
                        "object_type": dataset,
                        "message": "Export dataset contains zero records.",
                    }
                )

            seen_legacy_ids: dict[str, int] = {}
            for row_no, record in enumerate(records, start=1):
                legacy_id = str(record.get("legacy_id") or "")
                if legacy_id in seen_legacy_ids:
                    errors.append(
                        {
                            "severity": "error",
                            "code": "DUPLICATE_LEGACY_ID",
                            "object_type": dataset,
                            "legacy_id": legacy_id,
                            "row_no": row_no,
                            "first_row_no": seen_legacy_ids[legacy_id],
                            "message": "Duplicate legacy_id in one export dataset.",
                        }
                    )
                else:
                    seen_legacy_ids[legacy_id] = row_no

                try:
                    self._json_line(record)
                except TypeError as exc:
                    errors.append(
                        {
                            "severity": "error",
                            "code": "INVALID_JSON_PAYLOAD",
                            "object_type": dataset,
                            "legacy_id": legacy_id,
                            "row_no": row_no,
                            "message": str(exc),
                        }
                    )

        gridfs_files_key = f"{GRIDFS_BUCKET_NAME}.files"
        gridfs_chunks_key = f"{GRIDFS_BUCKET_NAME}.chunks"
        if gridfs_files_key not in collection_counts or gridfs_chunks_key not in collection_counts:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "MISSING_GRIDFS_COLLECTION",
                    "object_type": "gridfs-files-manifest",
                    "message": "GridFS files/chunks collection is not available in the source database.",
                }
            )
        elif collection_counts.get(gridfs_files_key, 0) == 0:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "EMPTY_GRIDFS",
                    "object_type": "gridfs-files-manifest",
                    "message": "GridFS files collection contains zero records.",
                }
            )

        return {"warnings": warnings, "errors": errors}

    def _export_record(self, *, legacy_collection: str, legacy_id: str, payload: Any) -> dict[str, Any]:
        return {
            "legacy_collection": legacy_collection,
            "legacy_id": legacy_id,
            "payload": self._normalize(payload),
        }

    def _payload_legacy_id(self, payload: Any, *, fallback_index: int) -> str:
        if isinstance(payload, dict):
            for key in ("id", "invoice_id", "transaction_id", "job_id", "relation_id", "audit_id", "case_id"):
                value = payload.get(key)
                if value not in (None, ""):
                    return str(value)
        return f"row-{fallback_index:08d}"

    def _normalize(self, value: Any) -> Any:
        return self._store._serialize_value(value)  # noqa: SLF001 - existing normalization handles dataclasses/Decimal/time.

    def _build_manifest(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        output_dir: Path,
        record_counts: dict[str, int],
        collection_counts: dict[str, int],
        checksums: dict[str, str],
        hashes: dict[str, Any],
        validation: dict[str, list[dict[str, Any]]],
        dry_run: bool,
        validate_only: bool,
    ) -> dict[str, Any]:
        return {
            "tool": EXPORT_TOOL_VERSION,
            "tool_version": EXPORT_TOOL_VERSION,
            "schema_version": EXPORT_SCHEMA_VERSION,
            "dry_run": dry_run,
            "validate_only": validate_only,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "export_started_at": started_at.isoformat(),
            "export_finished_at": finished_at.isoformat(),
            "source": self._source_summary(),
            "source_database": self._store.mongo_database_name,
            "output": {
                "directory": str(output_dir),
                "manifest_file": "manifest.json",
                "files": {
                    dataset: EXPORT_FILE_NAMES[dataset]
                    for dataset in sorted(EXPORT_FILE_NAMES)
                },
            },
            "collection_counts": {
                collection: collection_counts.get(collection, 0)
                for collection in sorted(collection_counts)
            },
            "record_counts": {
                dataset: record_counts.get(dataset, 0)
                for dataset in sorted(EXPORT_FILE_NAMES)
            },
            "checksums": checksums,
            "hashes": hashes,
            "validation": validation,
        }

    def _source_summary(self) -> dict[str, Any]:
        settings = getattr(self._store, "_mongo_settings", None)
        if settings is None:
            return {
                "storage_backend": self._store.storage_backend,
                "database": self._store.mongo_database_name,
            }
        return {
            "storage_backend": self._store.storage_backend,
            "database": settings.database,
            "host": settings.host,
            "port": settings.port,
            "auth_source": settings.auth_source,
            "has_username": bool(settings.username),
            "has_password": bool(settings.password),
        }

    def _calculate_dataset_checksums(self, records_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
        return {
            EXPORT_FILE_NAMES[dataset]: self._records_sha256(records)
            for dataset, records in sorted(records_by_dataset.items())
        }

    def _empty_dataset_checksums(self, records_by_dataset: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
        return {
            EXPORT_FILE_NAMES[dataset]: ""
            for dataset in sorted(records_by_dataset)
        }

    @staticmethod
    def _has_validation_error(validation: dict[str, list[dict[str, Any]]], code: str) -> bool:
        return any(item.get("code") == code for item in validation.get("errors", []))

    @staticmethod
    def _build_hashes(checksums: dict[str, str]) -> dict[str, Any]:
        digest = hashlib.sha256()
        for filename, checksum in sorted(checksums.items()):
            digest.update(f"{filename}:{checksum}\n".encode("utf-8"))
        return {
            "algorithm": "sha256",
            "files": dict(sorted(checksums.items())),
            "aggregate_sha256": digest.hexdigest(),
        }

    def _records_sha256(self, records: Iterable[dict[str, Any]]) -> str:
        digest = hashlib.sha256()
        for record in records:
            digest.update(self._json_line(record).encode("utf-8"))
        return digest.hexdigest()

    def _write_ndjson(self, path: Path, records: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(self._json_line(record))

    @staticmethod
    def _json_line(record: dict[str, Any]) -> str:
        return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
