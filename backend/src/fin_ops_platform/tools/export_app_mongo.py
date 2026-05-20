from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

from bson.binary import Binary

from fin_ops_platform.services.state_store import (
    DEFAULT_APP_MONGO_DATABASE,
    GRIDFS_BUCKET_NAME,
    ApplicationStateStore,
    default_data_dir,
)
from fin_ops_platform.tools.export_manifest import (
    ExportFile,
    NdjsonWriter,
    binary_metadata,
    safe_jsonable,
    sha256_file,
    write_checksums,
    write_json,
)
from fin_ops_platform.tools.exporters import ExportDefinition, all_export_definitions


RESTORE_DATABASE = "fin_ops_platform_app_restore_20260520013830"
APP_BACKUP_ARCHIVE = "/data/backups/fin_ops/20260520013830/fin_ops_platform_app_20260520013830.archive.gz"
APP_BACKUP_SHA256 = "c25d9780fded4c4407c29df16796fec2c99d63d201e24daf53ccab98e23f8b48"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export app Mongo records to normalized NDJSON artifacts.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source", required=True, choices=("restore", "production"))
    parser.add_argument("--database", help="Override app Mongo database name.")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--export-id")
    args = parser.parse_args(argv)

    source_database = args.database or (RESTORE_DATABASE if args.source == "restore" else DEFAULT_APP_MONGO_DATABASE)
    os.environ["FIN_OPS_APP_MONGO_DATABASE"] = source_database
    os.environ.setdefault("FIN_OPS_STORAGE_MODE", "mongo_only")

    try:
        result = export_app_mongo(
            output_root=args.output,
            source_mode=args.source,
            source_database=source_database,
            data_dir=args.data_dir,
            dry_run=args.dry_run,
            force=args.force,
            export_id=args.export_id,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary with sanitized output.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def export_app_mongo(
    *,
    output_root: Path,
    source_mode: str,
    source_database: str,
    data_dir: Path | None,
    dry_run: bool,
    force: bool,
    export_id: str | None = None,
) -> dict[str, Any]:
    store = ApplicationStateStore(data_dir or default_data_dir(), read_only=True)
    if store.storage_backend != "mongo":
        raise RuntimeError("Mongo state storage is required for stage 03 export.")
    if store.mongo_database_name != source_database:
        raise RuntimeError("Resolved app Mongo database does not match requested source database.")

    definitions = all_export_definitions()
    plan = {
        "source_mode": source_mode,
        "source_database": source_database,
        "storage_backend": store.storage_backend,
        "output_root": str(output_root),
        "files": [definition.output_file for definition in definitions],
        "gridfs_bucket": GRIDFS_BUCKET_NAME,
        "dry_run": dry_run,
    }
    if dry_run:
        plan["mongo_counts"] = count_mongo_sources(store, definitions)
        plan["gridfs"] = inspect_gridfs(store, sample_limit=0)
        return plan

    created_at = datetime.now(UTC)
    resolved_export_id = export_id or f"fin_ops_app_export_{created_at.strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    export_dir = output_root / resolved_export_id
    prepare_export_dir(export_dir, force=force)

    warnings: list[str] = []
    files: list[ExportFile] = []
    counts: Counter[str] = Counter()
    try:
        for definition in definitions:
            writer = NdjsonWriter(export_dir / definition.output_file)
            try:
                for record in iter_records(store, definition, resolved_export_id, created_at, warnings):
                    writer.write(record)
                    counts[record["record_type"]] += 1
                files.append(writer.close())
            except Exception:
                writer.abort()
                raise

        gridfs = inspect_gridfs(store, sample_limit=5)
        manifest = {
            "export_id": resolved_export_id,
            "created_at": created_at,
            "completed_at": datetime.now(UTC),
            "status": "completed",
            "source_mode": source_mode,
            "source_database": source_database,
            "storage_backend": store.storage_backend,
            "code_git_commit": git_commit(),
            "schema_migration_versions": ["0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008"],
            "app_backup_archive": APP_BACKUP_ARCHIVE,
            "app_backup_sha256": APP_BACKUP_SHA256,
            "files": {
                item.path.name: {"record_count": item.record_count, "bytes": item.bytes, "sha256": item.sha256}
                for item in sorted(files, key=lambda item: item.path.name)
            },
            "counts": dict(sorted(counts.items())),
            "total_records": sum(item.record_count for item in files),
            "gridfs": gridfs,
            "warnings": warnings,
            "errors": [],
            "environment": {
                "source_mode": source_mode,
                "database": source_database,
                "storage_backend": store.storage_backend,
            },
        }
        write_json(export_dir / "manifest.json", manifest)
        manifest["manifest_sha256"] = sha256_file(export_dir / "manifest.json")
        write_json(export_dir / "manifest.json", manifest)
        write_json(export_dir / "counts.json", {"counts": dict(sorted(counts.items())), "total_records": manifest["total_records"]})
        files.append(ExportFile(export_dir / "manifest.json", 1, (export_dir / "manifest.json").stat().st_size, sha256_file(export_dir / "manifest.json")))
        files.append(ExportFile(export_dir / "counts.json", 1, (export_dir / "counts.json").stat().st_size, sha256_file(export_dir / "counts.json")))
        write_checksums(export_dir / "checksums.sha256", files)
    except Exception:
        write_json(
            export_dir / "manifest.failed.json",
            {
                "export_id": resolved_export_id,
                "status": "failed",
                "source_mode": source_mode,
                "source_database": source_database,
                "completed_at": datetime.now(UTC),
            },
        )
        raise

    return {
        "status": "completed",
        "export_id": resolved_export_id,
        "export_dir": str(export_dir),
        "manifest": str(export_dir / "manifest.json"),
        "total_records": sum(item.record_count for item in files if item.path.suffix == ".ndjson"),
        "manifest_sha256": sha256_file(export_dir / "manifest.json"),
    }


def prepare_export_dir(path: Path, *, force: bool) -> None:
    if path.exists():
        completed_manifest = path / "manifest.json"
        if completed_manifest.exists():
            try:
                manifest = json.loads(completed_manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                manifest = {}
            if manifest.get("status") == "completed":
                raise RuntimeError(f"Refusing to overwrite completed export directory: {path}")
        if not force:
            raise RuntimeError(f"Export directory already exists; pass --force only for failed/incomplete exports: {path}")
        for child in path.iterdir():
            if child.is_file():
                child.unlink()
            else:
                raise RuntimeError(f"Refusing to clean nested export path: {child}")
    else:
        path.mkdir(parents=True)


def count_mongo_sources(store: ApplicationStateStore, definitions: list[ExportDefinition]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for definition in definitions:
        if not definition.source_collection:
            continue
        if definition.output_file == "pending_invoice_manual_invoice_commands.ndjson":
            commands = (store.load() or {}).get("pending_invoice_commands")
            counts[definition.source_collection] = len(commands) if isinstance(commands, dict) else 0
            continue
        collection = store._mongo_detailed_collections.get(definition.source_collection)  # noqa: SLF001
        if collection is None:
            counts[definition.source_collection] = 0
            continue
        counts[definition.source_collection] = int(collection.count_documents({}))
    return counts


def iter_records(
    store: ApplicationStateStore,
    definition: ExportDefinition,
    export_id: str,
    exported_at: datetime,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if definition.output_file in {"file_objects.ndjson", "gridfs_files_manifest.ndjson"}:
        return gridfs_records(store, definition, export_id, exported_at)
    if definition.output_file == "import_batch_rows.ndjson":
        return import_batch_row_records(store, definition, export_id, exported_at, warnings)
    if definition.output_file == "pending_invoice_manual_invoice_commands.ndjson":
        return pending_invoice_command_records(store, definition, export_id, exported_at, warnings)
    if not definition.source_collection:
        return []
    collection = store._mongo_detailed_collections.get(definition.source_collection)  # noqa: SLF001
    if collection is None:
        warnings.append(f"missing_source_collection:{definition.source_collection}:{definition.output_file}")
        return []

    records: list[dict[str, Any]] = []
    for document in sorted(collection.find({}), key=lambda item: str(item.get("_id", ""))):
        normalized_payload = store._load_binary_payload(document)  # noqa: SLF001
        if normalized_payload is None:
            normalized_payload = {key: value for key, value in document.items() if key != "payload"}
        normalized_payload = safe_jsonable(normalized_payload, allow_binary_metadata=False)
        if definition.rebuildable and isinstance(normalized_payload, dict):
            normalized_payload = {**normalized_payload, "rebuildable": True}
        raw_payload = sanitized_raw_document(document)
        raw_payload["_mongo_source_collection"] = definition.source_collection
        legacy_id = extract_identity(document, normalized_payload, definition.identity_fields)
        if legacy_id is None:
            warnings.append(f"missing_legacy_identity:{definition.output_file}:{document.get('_id')}")
        records.append(
            {
                "export_id": export_id,
                "source_collection": exported_source_collection(definition),
                "legacy_mongo_id": legacy_id,
                "legacy_key": legacy_id,
                "record_type": definition.record_type,
                "normalized_payload": normalized_payload,
                "raw_payload": raw_payload,
                "source_versions": extract_source_versions(normalized_payload),
                "exported_at": exported_at,
            }
        )
    return records


def pending_invoice_command_records(
    store: ApplicationStateStore,
    definition: ExportDefinition,
    export_id: str,
    exported_at: datetime,
    warnings: list[str],
) -> list[dict[str, Any]]:
    snapshot = (store.load() or {}).get("pending_invoice_commands")
    if not isinstance(snapshot, dict):
        warnings.append("missing_snapshot_key:pending_invoice_commands:pending_invoice_manual_invoice_commands.ndjson")
        return []

    records: list[dict[str, Any]] = []
    for key in sorted(str(item) for item in snapshot):
        payload = snapshot.get(key)
        if not isinstance(payload, dict):
            warnings.append(f"invalid_pending_invoice_command:{key}")
            continue
        normalized_payload = safe_jsonable(payload, allow_binary_metadata=False)
        legacy_id = extract_identity({"_id": key}, normalized_payload, definition.identity_fields) or key
        records.append(
            {
                "export_id": export_id,
                "source_collection": exported_source_collection(definition),
                "legacy_mongo_id": legacy_id,
                "legacy_key": legacy_id,
                "record_type": definition.record_type,
                "normalized_payload": normalized_payload,
                "raw_payload": {
                    "_mongo_source_collection": "pending_invoice_commands",
                    "snapshot_key": key,
                    "normalized_payload": normalized_payload,
                },
                "source_versions": extract_source_versions(normalized_payload),
                "exported_at": exported_at,
            }
        )
    return records


def import_batch_row_records(
    store: ApplicationStateStore,
    definition: ExportDefinition,
    export_id: str,
    exported_at: datetime,
    warnings: list[str],
) -> list[dict[str, Any]]:
    collection = store._mongo_detailed_collections.get("import_batches")  # noqa: SLF001
    if collection is None:
        warnings.append("missing_source_collection:import_batches:import_batch_rows.ndjson")
        return []
    records: list[dict[str, Any]] = []
    for document in sorted(collection.find({}), key=lambda item: str(item.get("_id", ""))):
        batch_payload = store._load_binary_payload(document)  # noqa: SLF001
        batch_payload = safe_jsonable(batch_payload or {}, allow_binary_metadata=False)
        if not isinstance(batch_payload, dict):
            continue
        row_results = batch_payload.get("row_results") or []
        normalized_rows = batch_payload.get("normalized_rows") or []
        if not isinstance(row_results, list):
            row_results = []
        if not isinstance(normalized_rows, list):
            normalized_rows = []
        batch_id = str(batch_payload.get("id") or batch_payload.get("batch_id") or document.get("_id"))
        for index, row_result in enumerate(row_results):
            normalized_row = normalized_rows[index] if index < len(normalized_rows) else None
            row_payload = safe_jsonable(row_result, allow_binary_metadata=False)
            normalized_payload = {
                "batch_id": batch_id,
                "row_no": index + 1,
                "row_result": row_payload,
                "normalized_row": safe_jsonable(normalized_row, allow_binary_metadata=False),
            }
            legacy_id = f"{batch_id}:row:{index + 1}"
            records.append(
                {
                    "export_id": export_id,
                    "source_collection": exported_source_collection(definition),
                    "legacy_mongo_id": legacy_id,
                    "legacy_key": legacy_id,
                    "record_type": "import_batch_row",
                    "normalized_payload": normalized_payload,
                    "raw_payload": {
                        "_mongo_source_collection": "import_batches",
                        "batch_document_id": str(document.get("_id")),
                        "row_result": row_payload,
                    },
                    "source_versions": extract_source_versions(batch_payload),
                    "exported_at": exported_at,
                }
            )
        if not row_results:
            warnings.append(f"empty_import_batch_rows:{document.get('_id')}")
    return records


def sanitized_raw_document(document: dict[str, Any]) -> dict[str, Any]:
    raw: dict[str, Any] = {}
    for key, value in document.items():
        if isinstance(value, (bytes, bytearray, Binary)):
            raw[key] = binary_metadata(value)
        else:
            raw[key] = value
    return safe_jsonable(raw, allow_binary_metadata=True)


def extract_identity(document: dict[str, Any], payload: Any, identity_fields: tuple[str, ...]) -> str | None:
    candidates: list[Any] = [document.get("_id")]
    if isinstance(payload, dict):
        candidates.extend(payload.get(field) for field in identity_fields)
        candidates.extend(payload.get(field) for field in ("id", "_id", "legacy_mongo_id", "legacy_key"))
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return None


def extract_source_versions(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    source_versions = payload.get("source_versions")
    if isinstance(source_versions, dict):
        return safe_jsonable(source_versions, allow_binary_metadata=False)
    version = payload.get("version")
    return {"version": version} if version not in (None, "") else {}


def gridfs_records(
    store: ApplicationStateStore,
    definition: ExportDefinition,
    export_id: str,
    exported_at: datetime,
) -> list[dict[str, Any]]:
    database = store._mongo_database  # noqa: SLF001
    if database is None:
        return []
    files_collection = database[f"{GRIDFS_BUCKET_NAME}.files"]
    records: list[dict[str, Any]] = []
    for document in sorted(files_collection.find({}), key=lambda item: str(item.get("_id", ""))):
        payload = {
            "legacy_gridfs_id": str(document.get("_id")),
            "filename": document.get("filename"),
            "length": document.get("length"),
            "chunk_size": document.get("chunkSize"),
            "upload_date": document.get("uploadDate"),
            "metadata": document.get("metadata") or {},
            "content_type": (document.get("metadata") or {}).get("content_type"),
            "storage_backend": "gridfs",
            "bucket_name": GRIDFS_BUCKET_NAME,
        }
        records.append(
            {
                "export_id": export_id,
                "source_collection": exported_source_collection(definition),
                "legacy_mongo_id": str(document.get("_id")),
                "legacy_key": str(document.get("_id")),
                "record_type": definition.record_type,
                "normalized_payload": safe_jsonable(payload, allow_binary_metadata=False),
                "raw_payload": {
                    **sanitized_raw_document(document),
                    "_mongo_source_collection": f"{GRIDFS_BUCKET_NAME}.files",
                },
                "source_versions": {},
                "exported_at": exported_at,
            }
        )
    return records


def exported_source_collection(definition: ExportDefinition) -> str:
    if definition.source_collection is None:
        return Path(definition.output_file).stem
    duplicated_collection_outputs = {
        "etc_state",
        "etc_reconciliation_state",
    }
    if definition.source_collection in duplicated_collection_outputs:
        return f"{definition.source_collection}:{Path(definition.output_file).stem}"
    if definition.output_file == "import_batch_rows.ndjson":
        return "import_batches:row_results"
    if definition.output_file == "pending_invoice_manual_invoice_commands.ndjson":
        return "pending_invoice_manual_invoice_commands"
    return definition.source_collection


def inspect_gridfs(store: ApplicationStateStore, *, sample_limit: int) -> dict[str, Any]:
    database = store._mongo_database  # noqa: SLF001
    bucket = store._mongo_file_bucket  # noqa: SLF001
    if database is None:
        return {"files_count": 0, "chunks_count": 0, "total_bytes": 0, "sampled_checksums": []}
    files = list(database[f"{GRIDFS_BUCKET_NAME}.files"].find({}))
    chunks_count = int(database[f"{GRIDFS_BUCKET_NAME}.chunks"].count_documents({}))
    total_bytes = sum(int(file_doc.get("length") or 0) for file_doc in files)
    samples: list[dict[str, Any]] = []
    if sample_limit and bucket is not None:
        for document in sorted(files, key=lambda item: str(item.get("_id", "")))[:sample_limit]:
            stream = bucket.open_download_stream(document["_id"])
            content = stream.read()
            samples.append(
                {
                    "legacy_gridfs_id": str(document.get("_id")),
                    "filename": document.get("filename"),
                    "bytes": len(content),
                    "sha256": __import__("hashlib").sha256(content).hexdigest(),
                }
            )
    return {
        "bucket": GRIDFS_BUCKET_NAME,
        "files_count": len(files),
        "chunks_count": chunks_count,
        "total_bytes": total_bytes,
        "sampled_checksums": samples,
    }


def git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=False,
            cwd=Path(__file__).resolve().parents[4],
        )
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


if __name__ == "__main__":
    raise SystemExit(main())
