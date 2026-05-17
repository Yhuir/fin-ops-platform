from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import uuid
from typing import Any, Literal, Mapping, Protocol

from fin_ops_platform.services.state_store import (
    GRIDFS_BUCKET_NAME,
    ApplicationStateStore,
)


GRIDFS_MIGRATION_TOOL_VERSION = "app-gridfs-minio-migration-v1"
GRIDFS_FILE_OBJECT_NAMESPACE = uuid.UUID("19d5a545-25ce-4e7d-9a99-b9bffab8ff75")
GRIDFS_IMPORT_FILE_NAMESPACE = uuid.UUID("a4d21d3c-6224-4dd9-b4d4-5cf4a5fc72e3")
GridFSMigrationMode = Literal["dry-run", "upload", "verify"]
GRIDFS_MINIO_REPORT_SCHEMA_VERSION = "finops.gridfs_minio_06d_checksum_evidence.v1"


def build_gridfs_minio_export_dry_run_report(
    *,
    export_dir: Path,
    migration_run_id: str,
    environment: str,
    bucket: str | None,
    storage_provider: str,
    env: Mapping[str, str],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a secret-free 06D NO_GO report from a 06A GridFS metadata manifest."""
    generated = generated_at or datetime.now(UTC)
    source_manifest = _find_gridfs_files_manifest(export_dir)
    export_manifest_path = export_dir / "manifest.json"
    source_database = "unknown"
    findings: list[dict[str, Any]] = []
    if export_manifest_path.exists():
        try:
            export_manifest = json.loads(export_manifest_path.read_text(encoding="utf-8"))
            source_database = str((export_manifest.get("source") or {}).get("database") or source_database)
        except json.JSONDecodeError as exc:
            findings.append(
                _report_finding(
                    code="EXPORT_MANIFEST_PARSE_ERROR",
                    dimension="source_manifest",
                    message=f"06A manifest.json is not valid JSON: {exc.msg}.",
                    required_action="Regenerate the 06A export manifest and rerun 06D.",
                )
            )
    else:
        findings.append(
            _report_finding(
                code="EXPORT_MANIFEST_MISSING",
                dimension="source_manifest",
                message="06A manifest.json was not found in export-dir.",
                required_action="Provide the 06A app Mongo export directory.",
            )
        )

    records: list[dict[str, Any]] = []
    if source_manifest.exists():
        records.extend(_read_gridfs_metadata_manifest(source_manifest, findings))
    else:
        findings.append(
            _report_finding(
                code="GRIDFS_FILES_MANIFEST_MISSING",
                dimension="source_manifest",
                message="06A gridfs-files-manifest.ndjson was not found.",
                required_action="Regenerate 06A export with GridFS metadata enabled or provide app GridFS env for live dry-run.",
            )
        )

    env_presence = _gridfs_minio_env_presence(env)
    findings.extend(_environment_findings(env_presence, bucket=bucket))
    findings.extend(_metadata_findings(records))
    findings.append(
        _report_finding(
            code="DRY_RUN_CANNOT_PASS_FILE_CHECKSUM_GATE",
            dimension="sample_download_hash",
            message="Dry-run/export metadata mode does not upload objects or download samples.",
            required_action="Run upload or verify mode against controlled staging MinIO/S3 and require mismatched=0.",
        )
    )

    metadata_summary = _metadata_summary(records)
    source_sha256 = _sha256_file_if_exists(source_manifest)
    export_sha256 = _sha256_file_if_exists(export_manifest_path)
    metadata_plan = _metadata_plan(records, environment=environment, bucket=bucket, storage_provider=storage_provider)
    source_hash_missing_count = metadata_summary["source_sha256_missing_count"]
    if records and source_hash_missing_count:
        findings.append(
            _report_finding(
                code="SOURCE_SHA256_MISSING",
                dimension="source_hash",
                message=(
                    "06A GridFS metadata manifest does not contain source content SHA-256 for "
                    f"{source_hash_missing_count} file(s); 06D must read app GridFS before GO."
                ),
                required_action="Provide app GridFS env and rerun live dry-run/upload so source sha256 is computed.",
                severity="warning",
            )
        )

    return {
        "schema_version": GRIDFS_MINIO_REPORT_SCHEMA_VERSION,
        "tool": GRIDFS_MIGRATION_TOOL_VERSION,
        "phase": "06d_gridfs_minio_migration",
        "migration_run_id": migration_run_id,
        "generated_at": generated.isoformat(),
        "status": "NO_GO",
        "go_no_go": "NO_GO",
        "GO_NO_GO": "NO_GO",
        "blocking": True,
        "source": {
            "kind": "06a_app_mongo_gridfs_metadata_manifest",
            "database": source_database,
            "gridfs_bucket": GRIDFS_BUCKET_NAME,
            "export_manifest_path": str(export_manifest_path),
            "export_manifest_sha256": export_sha256,
            "source_manifest_path": str(source_manifest),
            "source_manifest_sha256": source_sha256,
        },
        "target": {
            "storage_provider": storage_provider,
            "environment": environment,
            "bucket": bucket if bucket else "missing",
            "endpoint_present": _any_present(env_presence["object_storage_endpoint"]),
            "auth_material_values_recorded": False,
            "temporary_object_url_recorded": False,
        },
        "environment_presence": env_presence,
        "execution": {
            "mode": "dry_run_export_manifest_metadata_only",
            "dry_run_counts_as_go": False,
            "upload_executed": False,
            "verify_executed": False,
            "sample_download_executed": False,
            "business_facts_touched": False,
            "postgres_written": False,
            "oa_source_database_accessed": False,
        },
        "object_naming_strategy": {
            "pattern": "<environment>/app-gridfs/<domain>/<yyyy>/<mm>/<legacy_gridfs_id_sha256_16>/<file_object_id>",
            "filename_in_key": False,
            "stable": True,
            "traceability": ["environment", "domain", "upload yyyy/mm", "legacy GridFS id hash", "file_object_id"],
        },
        "metadata_summary": metadata_summary,
        "metadata_plan": {
            "target_table": "app.file_objects",
            "target_relation": "app.import_files",
            "legacy_mapping": "legacy_gridfs_id -> file_object_id",
            "planned_file_objects": len(metadata_plan),
            "planned_import_files": len(metadata_plan),
            "writes_postgresql": False,
        },
        "metadata_plan_sample": metadata_plan[:20],
        "coverage": {
            "manifest_checksum": {
                "status": "covered" if source_sha256 else "missing",
                "sha256": source_sha256,
            },
            "sample_download_hash": {
                "sampled": 0,
                "matched": 0,
                "mismatched": 0,
                "status": "not_evaluated_dry_run",
            },
            "missing_files": {
                "count": None,
                "items": [],
                "status": "not_evaluated_without_gridfs_content_read",
            },
            "duplicate_files": {
                "count": metadata_summary["duplicate_legacy_gridfs_id_count"],
                "groups": _duplicate_legacy_id_groups(records),
            },
            "size_differences": {
                "count": None,
                "items": [],
                "status": "not_evaluated_without_gridfs_content_read",
            },
            "checksum_mismatches": {
                "count": None,
                "items": [],
                "status": "not_evaluated_without_upload_or_verify",
            },
        },
        "readiness_gates": {
            "file_checksum": {
                "decision": "NO_GO",
                "reasons": [
                    "dry_run_does_not_download_verify_objects",
                    "upload_or_verify_not_executed",
                    "environment_gaps_present",
                ],
                "requires_report": "gridfs-checksum-validation-report.json or paired gridfs-minio-migration-report-YYYYMMDD.{json,md}",
            }
        },
        "legacy_id_mapping": {
            "expected_gridfs_files": len(records),
            "mapped_file_objects": 0,
            "mapped_import_files": 0,
            "missing_mappings_status": "not_evaluated_upload_or_verify_not_executed",
        },
        "findings": findings,
        "decision": {
            "go_no_go": "NO_GO",
            "reason": (
                "06D dry-run/export metadata report was generated, but app GridFS content checksum, "
                "MinIO/S3 upload or verify, sample download checksum, and PostgreSQL metadata import were not executed."
            ),
            "required_action": (
                "Provide controlled app GridFS, MinIO/S3, and PostgreSQL migration environment variables; rerun "
                "06D live dry-run/upload or verify; require per-file source sha256 and sample_download_hash.mismatched=0."
            ),
        },
    }


def write_gridfs_minio_report_files(
    report: dict[str, Any],
    *,
    json_path: Path,
    md_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_gridfs_minio_report_markdown(report, json_path=json_path), encoding="utf-8")


def _find_gridfs_files_manifest(export_dir: Path) -> Path:
    manifest_path = export_dir / "manifest.json"
    candidates: list[Path] = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
        output_files = (manifest.get("output") or {}).get("files") or {}
        if isinstance(output_files, dict):
            for value in output_files.values():
                if isinstance(value, str) and "gridfs" in value.lower():
                    candidates.append(export_dir / value)
    candidates.extend(
        [
            export_dir / "collections" / "gridfs-files-manifest.ndjson",
            export_dir / "gridfs-files-manifest.ndjson",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else export_dir / "collections" / "gridfs-files-manifest.ndjson"


def _read_gridfs_metadata_manifest(path: Path, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                findings.append(
                    _report_finding(
                        code="GRIDFS_MANIFEST_PARSE_ERROR",
                        dimension="source_manifest",
                        message=f"gridfs-files-manifest.ndjson line {line_no} is not valid JSON: {exc.msg}.",
                        required_action="Regenerate 06A export and rerun 06D.",
                    )
                )
                continue
            records.append(_normalize_gridfs_manifest_record(payload, line_no=line_no))
    return records


def _normalize_gridfs_manifest_record(payload: dict[str, Any], *, line_no: int) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    legacy_gridfs_id = (
        payload.get("legacy_gridfs_id")
        or payload.get("legacy_id")
        or payload.get("file_id")
        or payload.get("_id")
        or ""
    )
    content_type = payload.get("content_type") or payload.get("contentType") or metadata.get("content_type")
    byte_size = payload.get("byte_size")
    if byte_size is None:
        byte_size = payload.get("size")
    if byte_size is None:
        byte_size = payload.get("length")
    chunk_count = payload.get("chunk_count")
    if chunk_count is None:
        chunk_count = payload.get("chunks")
    upload_date = payload.get("upload_date") or payload.get("uploadDate")
    sha256 = (
        payload.get("sha256")
        or payload.get("source_sha256")
        or payload.get("checksum")
        or metadata.get("sha256")
    )
    legacy_collection = payload.get("legacy_collection") or payload.get("source_collection") or f"{GRIDFS_BUCKET_NAME}.files"
    domain = _classify_gridfs_domain(str(legacy_gridfs_id), str(legacy_collection), metadata)
    return {
        "source_line": line_no,
        "raw": payload,
        "legacy_collection": str(legacy_collection),
        "legacy_gridfs_id": str(legacy_gridfs_id),
        "filename": payload.get("filename") or payload.get("file_name") or metadata.get("file_name"),
        "byte_size": _int_or_none(byte_size),
        "chunk_count": _int_or_none(chunk_count),
        "content_type": content_type or "application/octet-stream",
        "content_type_status": "provided" if content_type else "defaulted",
        "upload_date": str(upload_date) if upload_date is not None else None,
        "sha256": str(sha256).lower() if isinstance(sha256, str) and len(sha256) == 64 else None,
        "domain": domain,
        "purpose": _domain_to_purpose(domain, metadata),
    }


def _gridfs_minio_env_presence(env: Mapping[str, str]) -> dict[str, dict[str, str]]:
    return {
        "app_gridfs": _presence_map(
            env,
            [
                "APP_MONGO_URI",
                "STAGING_APP_MONGO_URI",
                "FIN_OPS_APP_MONGO_HOST",
                "FIN_OPS_APP_MONGO_DATABASE",
                "FIN_OPS_APP_MONGO_USERNAME",
                "FIN_OPS_APP_MONGO_PASSWORD",
            ],
        ),
        "object_storage_endpoint": _presence_map(env, ["FIN_OPS_S3_ENDPOINT_URL", "S3_ENDPOINT", "AWS_ENDPOINT_URL_S3"]),
        "object_storage_bucket": _presence_map(env, ["FIN_OPS_S3_BUCKET", "S3_BUCKET"]),
        "object_storage_auth": _presence_map(
            env,
            [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
                "MINIO_ACCESS_KEY",
                "MINIO_SECRET_KEY",
                "S3_ACCESS_KEY_ID",
                "S3_SECRET_ACCESS_KEY",
            ],
        ),
        "postgres_migration": _presence_map(env, ["FIN_OPS_POSTGRES_MIGRATION_URL", "DATABASE_URL"]),
    }


def _presence_map(env: Mapping[str, str], names: list[str]) -> dict[str, str]:
    return {name: "present" if env.get(name) else "missing" for name in names}


def _environment_findings(env_presence: dict[str, dict[str, str]], *, bucket: str | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    app_gridfs_present = (
        env_presence["app_gridfs"].get("APP_MONGO_URI") == "present"
        or env_presence["app_gridfs"].get("STAGING_APP_MONGO_URI") == "present"
        or (
            env_presence["app_gridfs"].get("FIN_OPS_APP_MONGO_HOST") == "present"
            and env_presence["app_gridfs"].get("FIN_OPS_APP_MONGO_DATABASE") == "present"
        )
    )
    if not app_gridfs_present:
        findings.append(
            _report_finding(
                code="APP_GRIDFS_ENV_MISSING",
                dimension="app_gridfs_environment",
                message="App Mongo/GridFS environment variables are not present; source file bytes cannot be read.",
                required_action="Set app GridFS connection env and rerun live 06D migration against app Mongo only.",
            )
        )
    object_storage_ready = (
        _any_present(env_presence["object_storage_endpoint"])
        and (bucket is not None or _any_present(env_presence["object_storage_bucket"]))
        and (
            env_presence["object_storage_auth"].get("AWS_ACCESS_KEY_ID") == "present"
            or env_presence["object_storage_auth"].get("MINIO_ACCESS_KEY") == "present"
            or env_presence["object_storage_auth"].get("S3_ACCESS_KEY_ID") == "present"
        )
        and (
            env_presence["object_storage_auth"].get("AWS_SECRET_ACCESS_KEY") == "present"
            or env_presence["object_storage_auth"].get("MINIO_SECRET_KEY") == "present"
            or env_presence["object_storage_auth"].get("S3_SECRET_ACCESS_KEY") == "present"
        )
    )
    if not object_storage_ready:
        findings.append(
            _report_finding(
                code="OBJECT_STORAGE_ENV_MISSING",
                dimension="object_storage_environment",
                message="MinIO/S3 endpoint, bucket, or authentication environment is incomplete.",
                required_action="Provide controlled staging object storage env and rerun upload or verify mode.",
            )
        )
    if not _any_present(env_presence["postgres_migration"]):
        findings.append(
            _report_finding(
                code="POSTGRES_MIGRATION_ENV_MISSING",
                dimension="postgres_metadata_environment",
                message="PostgreSQL migration connection environment is not present; metadata import cannot be executed.",
                required_action="Set FIN_OPS_POSTGRES_MIGRATION_URL for a controlled staging/dry-run database before writing metadata.",
            )
        )
    return findings


def _metadata_findings(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for record in records:
        legacy_id = record["legacy_gridfs_id"]
        seen[legacy_id] = seen.get(legacy_id, 0) + 1
        if not legacy_id:
            findings.append(
                _report_finding(
                    code="LEGACY_GRIDFS_ID_MISSING",
                    dimension="source_manifest",
                    message=f"GridFS metadata line {record['source_line']} is missing legacy GridFS _id.",
                    required_action="Regenerate 06A export with GridFS _id.",
                )
            )
        if record.get("byte_size") is None:
            findings.append(
                _report_finding(
                    code="GRIDFS_LENGTH_MISSING",
                    dimension="source_manifest",
                    message=f"GridFS metadata line {record['source_line']} is missing length/byte_size.",
                    required_action="Regenerate 06A export with GridFS length.",
                )
            )
        if record.get("chunk_count") is None:
            findings.append(
                _report_finding(
                    code="GRIDFS_CHUNK_COUNT_MISSING",
                    dimension="source_manifest",
                    message=f"GridFS metadata line {record['source_line']} is missing chunk count.",
                    required_action="Regenerate 06A export with GridFS chunk counts or run live GridFS inventory.",
                )
            )
    for legacy_id, count in sorted(seen.items()):
        if legacy_id and count > 1:
            findings.append(
                _report_finding(
                    code="DUPLICATE_LEGACY_GRIDFS_ID",
                    dimension="source_manifest",
                    message=f"GridFS metadata contains duplicate legacy GridFS _id {legacy_id!r}.",
                    required_action="Fix duplicate GridFS manifest entries before metadata import.",
                )
            )
    return findings


def _metadata_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    domain_counts: dict[str, int] = {}
    content_type_counts: dict[str, int] = {}
    upload_month_counts: dict[str, int] = {}
    for record in records:
        domain_counts[record["domain"]] = domain_counts.get(record["domain"], 0) + 1
        content_type = record["content_type"]
        content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1
        year, month = _year_month(record.get("upload_date"))
        upload_month = f"{year}-{month}" if year != "unknown" else "unknown"
        upload_month_counts[upload_month] = upload_month_counts.get(upload_month, 0) + 1
    duplicate_count = sum(len(group["legacy_gridfs_ids"]) for group in _duplicate_legacy_id_groups(records))
    return {
        "gridfs_metadata_entries": len(records),
        "total_bytes_from_metadata": sum(int(record.get("byte_size") or 0) for record in records),
        "source_sha256_missing_count": sum(1 for record in records if not record.get("sha256")),
        "content_type_defaulted_count": sum(1 for record in records if record["content_type_status"] == "defaulted"),
        "content_type_counts": dict(sorted(content_type_counts.items())),
        "domain_counts": dict(sorted(domain_counts.items())),
        "upload_month_counts": dict(sorted(upload_month_counts.items())),
        "duplicate_legacy_gridfs_id_count": duplicate_count,
    }


def _metadata_plan(
    records: list[dict[str, Any]],
    *,
    environment: str,
    bucket: str | None,
    storage_provider: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        legacy_id = record["legacy_gridfs_id"]
        file_object_id = _stable_file_object_id(legacy_id)
        object_key = _planned_object_key(
            environment=environment,
            domain=record["domain"],
            upload_date=record.get("upload_date"),
            legacy_gridfs_id=legacy_id,
            file_object_id=file_object_id,
        )
        rows.append(
            {
                "legacy_collection": record["legacy_collection"],
                "legacy_gridfs_id": legacy_id,
                "file_object_id": file_object_id,
                "import_file_id": _stable_import_file_id(legacy_id),
                "storage_provider": storage_provider,
                "bucket": bucket if bucket else "pending_env_bucket",
                "object_key": object_key,
                "storage_key": object_key,
                "file_name": record.get("filename"),
                "content_type": record["content_type"],
                "byte_size": record.get("byte_size"),
                "sha256": record.get("sha256"),
                "legacy_id": legacy_id,
                "purpose": record["purpose"],
                "domain": record["domain"],
                "metadata": {
                    "legacy_collection": record["legacy_collection"],
                    "chunk_count": record.get("chunk_count"),
                    "upload_date": record.get("upload_date"),
                    "source_line": record["source_line"],
                },
            }
        )
    return rows


def _gridfs_minio_report_markdown(report: dict[str, Any], *, json_path: Path) -> str:
    summary = report.get("metadata_summary") or {}
    execution = report.get("execution") or {}
    source = report.get("source") or {}
    gate = ((report.get("readiness_gates") or {}).get("file_checksum") or {}).get("decision", "NO_GO")
    findings = report.get("findings") or []
    lines = [
        "# 06D GridFS -> MinIO/S3 checksum validation report",
        "",
        "## 判定",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        f"| go/no-go | `{(report.get('decision') or {}).get('go_no_go', report.get('go_no_go', 'NO_GO'))}` |",
        f"| blocking | `{str(report.get('blocking', True)).lower()}` |",
        f"| generated_at | `{report.get('generated_at')}` |",
        f"| source_database | `{source.get('database')}` |",
        f"| source_manifest | `{source.get('source_manifest_path')}` |",
        f"| source_manifest_sha256 | `{source.get('source_manifest_sha256')}` |",
        f"| file_checksum gate | `{gate}` |",
        f"| upload executed | `{str(execution.get('upload_executed', False)).lower()}` |",
        f"| verify executed | `{str(execution.get('verify_executed', False)).lower()}` |",
        f"| sample download executed | `{str(execution.get('sample_download_executed', False)).lower()}` |",
        "",
        "本报告只记录环境变量是否存在，不记录 Mongo/PostgreSQL URI、S3 access key、secret key、session token、presigned URL 或其他 secret 值。dry-run/export metadata 不能作为 `file_checksum` GO 证据。",
        "",
        "## 06A GridFS metadata 摘要",
        "",
        "| 维度 | 值 |",
        "| --- | ---: |",
        f"| metadata entries | {summary.get('gridfs_metadata_entries', 0)} |",
        f"| total bytes from metadata | {summary.get('total_bytes_from_metadata', 0)} |",
        f"| content type defaulted | {summary.get('content_type_defaulted_count', 0)} |",
        f"| source content sha256 missing in metadata | {summary.get('source_sha256_missing_count', 0)} |",
        "",
        "## Blockers",
        "",
        "| code | dimension | action |",
        "| --- | --- | --- |",
    ]
    for finding in findings:
        lines.append(
            f"| `{finding.get('code')}` | `{finding.get('dimension', '')}` | {finding.get('required_action', '')} |"
        )
    if not findings:
        lines.append("| - | - | - |")
    lines.extend(
        [
            "",
            "## 安全边界",
            "",
            "- 未访问 OA 源数据库。",
            "- 未写入 `app`、`read_model`、`job`、`audit` 正式 facts。",
            "- 未删除 GridFS 原文件。",
            "- 未记录对象存储认证值、临时对象访问 URL、完整连接串或 bucket 访问材料。",
            "",
            "## 配套 JSON",
            "",
            f"- `{json_path}`",
            "",
        ]
    )
    return "\n".join(lines)


def _classify_gridfs_domain(legacy_gridfs_id: str, legacy_collection: str, metadata: dict[str, Any]) -> str:
    purpose = str(metadata.get("purpose") or "").lower()
    lowered_id = legacy_gridfs_id.lower()
    lowered_collection = legacy_collection.lower()
    if "repair" in lowered_id or "repair" in purpose:
        return "repair_bundle"
    if lowered_id.startswith("etc_") or lowered_id.startswith("etc-") or "etc" in purpose:
        return "etc_file"
    if "oa" in lowered_id or "oa" in lowered_collection or "oa" in purpose:
        return "oa_attachment_cache"
    if lowered_id.startswith("import_file_") or metadata.get("session_id") or metadata.get("file_id"):
        return "import_source_file"
    return "other"


def _domain_to_purpose(domain: str, metadata: dict[str, Any]) -> str:
    explicit = str(metadata.get("purpose") or "").strip()
    if explicit:
        return _safe_segment(explicit)
    return domain


def _planned_object_key(
    *,
    environment: str,
    domain: str,
    upload_date: str | None,
    legacy_gridfs_id: str,
    file_object_id: str,
) -> str:
    year, month = _year_month(upload_date)
    legacy_hash = hashlib.sha256(legacy_gridfs_id.encode("utf-8")).hexdigest()[:16]
    return "/".join(
        [
            _safe_segment(environment),
            "app-gridfs",
            _safe_segment(domain),
            year,
            month,
            legacy_hash,
            file_object_id,
        ]
    )


def _stable_file_object_id(legacy_gridfs_id: str) -> str:
    return str(uuid.uuid5(GRIDFS_FILE_OBJECT_NAMESPACE, f"app-gridfs:{legacy_gridfs_id}"))


def _stable_import_file_id(legacy_gridfs_id: str) -> str:
    return str(uuid.uuid5(GRIDFS_IMPORT_FILE_NAMESPACE, f"app-gridfs-import-file:{legacy_gridfs_id}"))


def _duplicate_legacy_id_groups(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        legacy_id = record.get("legacy_gridfs_id")
        if legacy_id:
            grouped.setdefault(str(legacy_id), []).append(record)
    return [
        {
            "legacy_gridfs_id": legacy_id,
            "legacy_gridfs_ids": [entry["legacy_gridfs_id"] for entry in entries],
            "source_lines": [entry["source_line"] for entry in entries],
        }
        for legacy_id, entries in sorted(grouped.items())
        if len(entries) > 1
    ]


def _report_finding(
    *,
    code: str,
    dimension: str,
    message: str,
    required_action: str,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "dimension": dimension,
        "message": message,
        "required_action": required_action,
    }


def _sha256_file_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _any_present(statuses: Mapping[str, str]) -> bool:
    return any(status == "present" for status in statuses.values())


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _year_month(upload_date: str | None) -> tuple[str, str]:
    if upload_date:
        try:
            parsed = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))
            return f"{parsed.year:04d}", f"{parsed.month:02d}"
        except ValueError:
            pass
    return "unknown", "unknown"


def _safe_segment(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value).lower())
    normalized = "-".join(segment for segment in normalized.split("-") if segment)
    return normalized or "unknown"


@dataclass(frozen=True, slots=True)
class ObjectStorageHead:
    etag: str | None = None
    version_id: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectStoragePutResult:
    etag: str | None = None
    version_id: str | None = None


class ObjectStorageClient(Protocol):
    def head_object(self, *, bucket: str, object_key: str) -> ObjectStorageHead | None:
        ...

    def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        body: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> ObjectStoragePutResult:
        ...

    def get_object_bytes(self, *, bucket: str, object_key: str) -> bytes:
        ...


class InMemoryObjectStorageClient:
    """Small object storage double used by migration tests."""

    def __init__(self, *, corrupt_downloads: bool = False) -> None:
        self._objects: dict[tuple[str, str], dict[str, Any]] = {}
        self._corrupt_downloads = corrupt_downloads
        self.put_calls: list[tuple[str, str]] = []

    def head_object(self, *, bucket: str, object_key: str) -> ObjectStorageHead | None:
        stored = self._objects.get((bucket, object_key))
        if stored is None:
            return None
        return ObjectStorageHead(etag=stored["etag"], version_id=stored.get("version_id"), sha256=stored["sha256"])

    def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        body: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> ObjectStoragePutResult:
        self.put_calls.append((bucket, object_key))
        digest = hashlib.sha256(body).hexdigest()
        etag = hashlib.md5(body, usedforsecurity=False).hexdigest()
        self._objects[(bucket, object_key)] = {
            "body": bytes(body),
            "content_type": content_type,
            "metadata": dict(metadata),
            "sha256": digest,
            "etag": etag,
            "version_id": None,
        }
        return ObjectStoragePutResult(etag=etag, version_id=None)

    def get_object_bytes(self, *, bucket: str, object_key: str) -> bytes:
        body = self._objects[(bucket, object_key)]["body"]
        if self._corrupt_downloads:
            return body + b"corrupt"
        return bytes(body)


class Boto3ObjectStorageClient:
    """Thin boto3 adapter for MinIO/S3. Credentials are read by boto3 from the environment."""

    def __init__(self, *, endpoint_url: str | None = None) -> None:
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on deployment environment.
            raise RuntimeError("boto3 is required for --execute GridFS object storage migration.") from exc
        self._client = boto3.client("s3", endpoint_url=endpoint_url)

    def head_object(self, *, bucket: str, object_key: str) -> ObjectStorageHead | None:
        try:
            response = self._client.head_object(Bucket=bucket, Key=object_key)
        except Exception as exc:  # pragma: no cover - boto3 exception classes vary by environment.
            error_response = getattr(exc, "response", {}) or {}
            code = (error_response.get("Error") or {}).get("Code")
            if str(code) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        metadata = response.get("Metadata") or {}
        return ObjectStorageHead(
            etag=str(response.get("ETag", "")).strip('"') or None,
            version_id=response.get("VersionId"),
            sha256=metadata.get("sha256"),
        )

    def put_object(
        self,
        *,
        bucket: str,
        object_key: str,
        body: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> ObjectStoragePutResult:
        kwargs: dict[str, Any] = {
            "Bucket": bucket,
            "Key": object_key,
            "Body": body,
            "Metadata": metadata,
        }
        if content_type:
            kwargs["ContentType"] = content_type
        response = self._client.put_object(**kwargs)
        return ObjectStoragePutResult(
            etag=str(response.get("ETag", "")).strip('"') or None,
            version_id=response.get("VersionId"),
        )

    def get_object_bytes(self, *, bucket: str, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=object_key)
        return response["Body"].read()


@dataclass(frozen=True, slots=True)
class AppGridFSMigrationResult:
    manifest: dict[str, Any]
    output_dir: Path


class AppGridFSToObjectStorageMigrator:
    """Migrate app Mongo GridFS files to MinIO/S3 with checksum verification."""

    def __init__(self, store: ApplicationStateStore, object_storage: ObjectStorageClient | None = None) -> None:
        self._store = store
        self._object_storage = object_storage

    def migrate(
        self,
        *,
        bucket: str,
        environment: str,
        output_dir: Path,
        mode: GridFSMigrationMode | str | None = None,
        dry_run: bool | None = None,
        storage_provider: str = "minio",
        sample_size: int = 20,
        max_workers: int = 1,
        max_retries: int = 3,
    ) -> AppGridFSMigrationResult:
        self._ensure_app_gridfs_store()
        migration_mode = self._resolve_mode(mode=mode, dry_run=dry_run)
        is_dry_run = migration_mode == "dry-run"
        if not is_dry_run and self._object_storage is None:
            raise RuntimeError("object storage client is required for upload or verify GridFS migration modes.")

        started_at = datetime.now(UTC)
        migration_run_id = str(uuid.uuid5(GRIDFS_FILE_OBJECT_NAMESPACE, started_at.isoformat()))
        records = self._list_gridfs_records()
        if max_workers > 1 and len(records) > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                files = list(
                    executor.map(
                        lambda record: self._process_record(
                            record,
                            bucket=bucket,
                            environment=environment,
                            mode=migration_mode,
                            storage_provider=storage_provider,
                            max_retries=max_retries,
                        ),
                        records,
                    )
                )
        else:
            files = [
                self._process_record(
                    record,
                    bucket=bucket,
                    environment=environment,
                    mode=migration_mode,
                    storage_provider=storage_provider,
                    max_retries=max_retries,
                )
                for record in records
            ]

        findings: list[dict[str, Any]] = []
        for file_entry in files:
            file_findings = file_entry.pop("_findings", [])
            if file_findings:
                self._mark_file_failed(file_entry, file_findings[0])
            findings.extend(file_findings)

        sample_summary = self._validate_checksum_samples(
            files,
            sample_size=sample_size,
            dry_run=is_dry_run,
            max_retries=max_retries,
            findings=findings,
        )
        summary = self._build_summary(
            files,
            sample_summary=sample_summary,
            dry_run=is_dry_run,
            mode=migration_mode,
            findings=findings,
        )
        readiness_gate = self._file_checksum_gate(
            files,
            sample_summary=sample_summary,
            dry_run=is_dry_run,
            findings=findings,
        )
        manifest = {
            "tool": GRIDFS_MIGRATION_TOOL_VERSION,
            "migration_run_id": migration_run_id,
            "mode": migration_mode,
            "dry_run": is_dry_run,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "source": {
                "storage_backend": self._store.storage_backend,
                "database": self._store.mongo_database_name,
                "gridfs_bucket": GRIDFS_BUCKET_NAME,
            },
            "target": {
                "storage_provider": storage_provider,
                "bucket": bucket,
                "environment": environment,
            },
            "retry_policy": {
                "max_retries": max(0, max_retries),
                "retryable_operations": ["head_object", "put_object", "get_object_bytes"],
            },
            "summary": summary,
            "readiness_gates": {"file_checksum": readiness_gate},
            "files": files,
            "findings": findings,
            "blocking": bool(findings),
            "status": "failed" if findings else "passed",
        }
        self._write_outputs(output_dir, manifest)
        return AppGridFSMigrationResult(manifest=manifest, output_dir=output_dir)

    def _ensure_app_gridfs_store(self) -> None:
        if self._store.storage_backend != "mongo":
            raise RuntimeError("GridFS migration requires an app Mongo-backed ApplicationStateStore.")
        if self._store.mongo_database_name is None or self._store._mongo_database is None:  # noqa: SLF001
            raise RuntimeError("GridFS migration requires a configured app Mongo database.")
        if self._store._mongo_file_bucket is None:  # noqa: SLF001
            raise RuntimeError("GridFS migration requires a configured app GridFS bucket.")

    def _list_gridfs_records(self) -> list[dict[str, Any]]:
        database = self._store._mongo_database  # noqa: SLF001 - migration tool intentionally uses app Mongo internals.
        files_collection = database[f"{GRIDFS_BUCKET_NAME}.files"]
        chunks_collection = database[f"{GRIDFS_BUCKET_NAME}.chunks"]
        records: list[dict[str, Any]] = []
        for document in sorted(files_collection.find({}), key=lambda item: str(item.get("_id", ""))):
            metadata = dict(document.get("metadata") or {})
            file_id = str(document.get("_id", ""))
            content_type = document.get("contentType") or metadata.get("content_type")
            content_type_status = "provided" if content_type else "defaulted"
            records.append(
                {
                    "legacy_gridfs_id": file_id,
                    "legacy_collection": f"{GRIDFS_BUCKET_NAME}.files",
                    "filename": document.get("filename"),
                    "byte_size": int(document.get("length") or 0),
                    "chunk_size": document.get("chunkSize"),
                    "chunk_count": chunks_collection.count_documents({"files_id": document.get("_id")}),
                    "content_type": content_type or "application/octet-stream",
                    "content_type_status": content_type_status,
                    "upload_date": self._serialize_value(document.get("uploadDate")),
                    "metadata": self._serialize_value(metadata),
                    "purpose": self._classify_purpose(file_id, metadata),
                }
            )
        return records

    def _process_record(
        self,
        record: dict[str, Any],
        *,
        bucket: str,
        environment: str,
        mode: GridFSMigrationMode,
        storage_provider: str,
        max_retries: int,
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        legacy_gridfs_id = record["legacy_gridfs_id"]
        file_object_id = self._file_object_id(legacy_gridfs_id)
        object_key = self._object_key(
            environment=environment,
            purpose=record["purpose"],
            upload_date=record.get("upload_date"),
            legacy_gridfs_id=legacy_gridfs_id,
            file_object_id=file_object_id,
        )
        try:
            content = self._read_gridfs_bytes(legacy_gridfs_id)
        except Exception as exc:
            return self._failed_file_entry(
                record,
                bucket=bucket,
                object_key=object_key,
                file_object_id=file_object_id,
                storage_provider=storage_provider,
                code="GRIDFS_READ_ERROR",
                message=f"Failed to read source GridFS file: {type(exc).__name__}.",
                exception=exc,
            )
        sha256 = hashlib.sha256(content).hexdigest()
        byte_size = len(content)
        status = "planned"
        etag = None
        object_version = None

        if record.get("byte_size") != byte_size:
            findings.append(
                {
                    "severity": "error",
                    "code": "GRIDFS_LENGTH_MISMATCH",
                    "legacy_gridfs_id": legacy_gridfs_id,
                    "expected": record.get("byte_size"),
                    "actual": byte_size,
                    "message": "GridFS file metadata length differs from downloaded bytes.",
                }
            )

        if mode in {"upload", "verify"}:
            try:
                existing = self._with_retries(
                    lambda: self._object_storage.head_object(  # type: ignore[union-attr]
                        bucket=bucket,
                        object_key=object_key,
                    ),
                    max_retries=max_retries,
                )
            except Exception as exc:
                return self._failed_file_entry(
                    record,
                    bucket=bucket,
                    object_key=object_key,
                    file_object_id=file_object_id,
                    storage_provider=storage_provider,
                    code="OBJECT_HEAD_ERROR",
                    message=f"Failed to inspect target object: {type(exc).__name__}.",
                    exception=exc,
                    sha256=sha256,
                    byte_size=byte_size,
                )
            if existing is not None and existing.sha256 == sha256:
                status = "skipped_existing"
                etag = existing.etag
                object_version = existing.version_id
            elif mode == "verify":
                if existing is None:
                    return self._failed_file_entry(
                        record,
                        bucket=bucket,
                        object_key=object_key,
                        file_object_id=file_object_id,
                        storage_provider=storage_provider,
                        code="OBJECT_NOT_FOUND",
                        message="Target object is missing during verify mode.",
                        sha256=sha256,
                        byte_size=byte_size,
                    )
                findings.append(
                    {
                        "severity": "error",
                        "code": "FILE_CHECKSUM_MISMATCH",
                        "legacy_gridfs_id": legacy_gridfs_id,
                        "file_object_id": file_object_id,
                        "expected": sha256,
                        "actual": existing.sha256,
                        "message": "Target object metadata sha256 differs from source GridFS checksum.",
                    }
                )
                status = "failed"
                etag = existing.etag
                object_version = existing.version_id
            else:
                try:
                    put_result = self._with_retries(
                        lambda: self._object_storage.put_object(  # type: ignore[union-attr]
                            bucket=bucket,
                            object_key=object_key,
                            body=content,
                            content_type=record.get("content_type"),
                            metadata={
                                "sha256": sha256,
                                "legacy-gridfs-id-sha256": hashlib.sha256(
                                    legacy_gridfs_id.encode("utf-8")
                                ).hexdigest(),
                                "file-object-id": file_object_id,
                            },
                        ),
                        max_retries=max_retries,
                    )
                except Exception as exc:
                    return self._failed_file_entry(
                        record,
                        bucket=bucket,
                        object_key=object_key,
                        file_object_id=file_object_id,
                        storage_provider=storage_provider,
                        code="OBJECT_UPLOAD_ERROR",
                        message=f"Failed to upload target object: {type(exc).__name__}.",
                        exception=exc,
                        sha256=sha256,
                        byte_size=byte_size,
                    )
                status = "uploaded"
                etag = put_result.etag
                object_version = put_result.version_id

        return self._file_entry(
            record,
            bucket=bucket,
            object_key=object_key,
            file_object_id=file_object_id,
            storage_provider=storage_provider,
            object_version=object_version,
            byte_size=byte_size,
            sha256=sha256,
            etag=etag,
            status=status,
            findings=findings,
        )

    def _file_entry(
        self,
        record: dict[str, Any],
        *,
        bucket: str,
        object_key: str,
        file_object_id: str,
        storage_provider: str,
        object_version: str | None,
        byte_size: int,
        sha256: str | None,
        etag: str | None,
        status: str,
        findings: list[dict[str, Any]] | None = None,
        failure_reason: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error_code = None
        error_summary = None
        if findings:
            first_finding = findings[0]
            error_code = first_finding.get("code")
            error_summary = first_finding.get("message")
        legacy_collection = record["legacy_collection"]
        return {
            "legacy_collection": record["legacy_collection"],
            "source_collection": legacy_collection,
            "legacy_gridfs_id": record["legacy_gridfs_id"],
            "file_object_id": file_object_id,
            "storage_provider": storage_provider,
            "bucket": bucket,
            "object_key": object_key,
            "storage_key": object_key,
            "object_version": object_version,
            "versioning": {
                "captured": object_version is not None,
                "object_version": object_version,
            },
            "file_name": record.get("filename"),
            "content_type": record.get("content_type"),
            "content_type_status": record.get("content_type_status", "provided"),
            "byte_size": byte_size,
            "size": byte_size,
            "sha256": sha256,
            "etag": etag,
            "purpose": record["purpose"],
            "chunk_count": record.get("chunk_count"),
            "upload_date": record.get("upload_date"),
            "status": status,
            "migration_status": status,
            "error_code": error_code,
            "error_summary": error_summary,
            "failure_reason": failure_reason,
            "_findings": findings or [],
        }

    def _validate_checksum_samples(
        self,
        files: list[dict[str, Any]],
        *,
        sample_size: int,
        dry_run: bool,
        max_retries: int,
        findings: list[dict[str, Any]],
    ) -> dict[str, int]:
        if dry_run or sample_size <= 0:
            return {"sampled": 0, "matched": 0, "mismatched": 0}
        candidates = [
            file_entry
            for file_entry in files
            if file_entry.get("status") in {"uploaded", "skipped_existing"}
        ][:sample_size]
        matched = 0
        mismatched = 0
        for file_entry in candidates:
            try:
                downloaded = self._with_retries(
                    lambda: self._object_storage.get_object_bytes(  # type: ignore[union-attr]
                        bucket=file_entry["bucket"],
                        object_key=file_entry["object_key"],
                    ),
                    max_retries=max_retries,
                )
            except Exception as exc:
                mismatched += 1
                finding = {
                    "severity": "error",
                    "code": "OBJECT_DOWNLOAD_ERROR",
                    "legacy_gridfs_id": file_entry["legacy_gridfs_id"],
                    "file_object_id": file_entry["file_object_id"],
                    "message": f"Failed to download object for checksum sample: {type(exc).__name__}.",
                }
                findings.append(finding)
                self._mark_file_failed(file_entry, finding)
                continue
            actual_sha256 = hashlib.sha256(downloaded).hexdigest()
            if actual_sha256 == file_entry["sha256"]:
                matched += 1
                continue
            mismatched += 1
            finding = {
                "severity": "error",
                "code": "FILE_CHECKSUM_MISMATCH",
                "legacy_gridfs_id": file_entry["legacy_gridfs_id"],
                "file_object_id": file_entry["file_object_id"],
                "expected": file_entry["sha256"],
                "actual": actual_sha256,
                "message": "Downloaded object checksum differs from source GridFS checksum.",
            }
            findings.append(finding)
            self._mark_file_failed(file_entry, finding)
        return {"sampled": len(candidates), "matched": matched, "mismatched": mismatched}

    def _failed_file_entry(
        self,
        record: dict[str, Any],
        *,
        bucket: str,
        object_key: str,
        file_object_id: str,
        storage_provider: str,
        code: str,
        message: str,
        exception: Exception | None = None,
        sha256: str | None = None,
        byte_size: int | None = None,
    ) -> dict[str, Any]:
        legacy_gridfs_id = record["legacy_gridfs_id"]
        failure_reason = self._failure_reason(code=code, message=message, exception=exception)
        findings = [
            {
                "severity": "error",
                "code": code,
                "legacy_gridfs_id": legacy_gridfs_id,
                "file_object_id": file_object_id,
                "message": message,
                "reason": failure_reason,
            }
        ]
        return self._file_entry(
            record,
            bucket=bucket,
            object_key=object_key,
            file_object_id=file_object_id,
            storage_provider=storage_provider,
            object_version=None,
            byte_size=byte_size if byte_size is not None else 0,
            sha256=sha256,
            etag=None,
            status="failed",
            findings=findings,
            failure_reason=failure_reason,
        )

    def _build_summary(
        self,
        files: list[dict[str, Any]],
        *,
        sample_summary: dict[str, int],
        dry_run: bool,
        mode: GridFSMigrationMode,
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        failed_ids = {
            str(finding.get("legacy_gridfs_id"))
            for finding in findings
            if finding.get("legacy_gridfs_id")
        }
        duplicate_groups = self._duplicate_file_groups(files)
        size_differences = [finding for finding in findings if finding.get("code") == "GRIDFS_LENGTH_MISMATCH"]
        return {
            "dry_run": dry_run,
            "mode": mode,
            "total_files": len(files),
            "empty_gridfs": len(files) == 0,
            "total_bytes": sum(int(file_entry.get("byte_size") or 0) for file_entry in files),
            "planned": sum(1 for file_entry in files if file_entry.get("status") == "planned"),
            "uploaded": sum(1 for file_entry in files if file_entry.get("status") == "uploaded"),
            "skipped_existing": sum(1 for file_entry in files if file_entry.get("status") == "skipped_existing"),
            "failed": len(failed_ids),
            "missing_files": sum(1 for finding in findings if finding.get("code") == "GRIDFS_READ_ERROR"),
            "duplicate_files": sum(len(group["legacy_gridfs_ids"]) for group in duplicate_groups),
            "size_differences": len(size_differences),
            "checksum_samples": sample_summary,
        }

    def _write_outputs(self, output_dir: Path, manifest: dict[str, Any]) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "gridfs-minio-migration-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self._write_ndjson(output_dir / "gridfs-object-mapping.ndjson", self._mapping_rows(manifest["files"]))
        self._write_ndjson(output_dir / "file-objects-import.ndjson", self._file_object_rows(manifest["files"]))
        self._write_ndjson(
            output_dir / "legacy-id-map-import.ndjson",
            self._legacy_id_map_rows(manifest["files"], migration_run_id=manifest["migration_run_id"]),
        )
        self._write_ndjson(output_dir / "gridfs-migration-failures.ndjson", manifest["findings"])
        checksum_report = self._checksum_validation_report(output_dir, manifest)
        (output_dir / "gridfs-checksum-validation-report.json").write_text(
            json.dumps(checksum_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _mapping_rows(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "source_system": "app_mongo_gridfs",
                "legacy_collection": file_entry["legacy_collection"],
                "legacy_gridfs_id": file_entry["legacy_gridfs_id"],
                "file_object_id": file_entry["file_object_id"],
                "import_file_id": self._import_file_id(file_entry["legacy_gridfs_id"]),
                "target_schema": "app",
                "target_table": "app.file_objects",
                "target_tables": ["app.file_objects", "app.import_files"],
                "bucket": file_entry["bucket"],
                "object_key": file_entry["object_key"],
                "object_version": file_entry["object_version"],
                "content_type": file_entry["content_type"],
                "etag": file_entry["etag"],
                "sha256": file_entry["sha256"],
                "byte_size": file_entry["byte_size"],
                "purpose": file_entry["purpose"],
                "status": file_entry["status"],
            }
            for file_entry in files
            if file_entry["status"] != "failed"
        ]

    def _legacy_id_map_rows(self, files: list[dict[str, Any]], *, migration_run_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for file_entry in files:
            if file_entry["status"] == "failed":
                continue
            import_file_id = self._import_file_id(file_entry["legacy_gridfs_id"])
            payload_hash = hashlib.sha256(
                json.dumps(
                    {
                        "legacy_gridfs_id": file_entry["legacy_gridfs_id"],
                        "file_object_id": file_entry["file_object_id"],
                        "import_file_id": import_file_id,
                        "object_key": file_entry["object_key"],
                        "sha256": file_entry["sha256"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            rows.extend(
                [
                    {
                        "source_system": "app_mongo_gridfs",
                        "legacy_collection": file_entry["legacy_collection"],
                        "legacy_id": file_entry["legacy_gridfs_id"],
                        "target_schema": "app",
                        "target_table": "file_objects",
                        "target_id": file_entry["file_object_id"],
                        "payload_hash": payload_hash,
                        "migration_run_id": migration_run_id,
                    },
                    {
                        "source_system": "app_mongo_gridfs",
                        "legacy_collection": file_entry["legacy_collection"],
                        "legacy_id": file_entry["legacy_gridfs_id"],
                        "target_schema": "app",
                        "target_table": "import_files",
                        "target_id": import_file_id,
                        "payload_hash": payload_hash,
                        "migration_run_id": migration_run_id,
                    },
                ]
            )
        return rows

    def _file_object_rows(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": file_entry["file_object_id"],
                "storage_provider": file_entry["storage_provider"],
                "bucket": file_entry["bucket"],
                "object_key": file_entry["object_key"],
                "object_version": file_entry["object_version"],
                "file_name": file_entry["file_name"],
                "content_type": file_entry["content_type"],
                "byte_size": file_entry["byte_size"],
                "sha256": file_entry["sha256"],
                "etag": file_entry["etag"],
                "metadata": {
                    "legacy_collection": file_entry["legacy_collection"],
                    "chunk_count": file_entry["chunk_count"],
                    "upload_date": file_entry["upload_date"],
                },
                "legacy_gridfs_id": file_entry["legacy_gridfs_id"],
                "purpose": file_entry["purpose"],
                "created_by": "mongo_migration",
            }
            for file_entry in files
            if file_entry["status"] != "failed"
        ]

    def _read_gridfs_bytes(self, legacy_gridfs_id: str) -> bytes:
        stream = self._store._mongo_file_bucket.open_download_stream(legacy_gridfs_id)  # noqa: SLF001
        try:
            return stream.read()
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def _object_key(
        self,
        *,
        environment: str,
        purpose: str,
        upload_date: str | None,
        legacy_gridfs_id: str,
        file_object_id: str,
    ) -> str:
        year, month = self._year_month(upload_date)
        legacy_hash = hashlib.sha256(legacy_gridfs_id.encode("utf-8")).hexdigest()[:16]
        return "/".join(
            [
                self._safe_segment(environment),
                "app-gridfs",
                self._safe_segment(purpose),
                year,
                month,
                legacy_hash,
                file_object_id,
            ]
        )

    def _classify_purpose(self, legacy_gridfs_id: str, metadata: dict[str, Any]) -> str:
        purpose = str(metadata.get("purpose") or "").strip()
        if purpose:
            return self._safe_segment(purpose)
        if legacy_gridfs_id.startswith("etc_reconciliation:"):
            return "etc_reconciliation_source"
        if legacy_gridfs_id.startswith("etc_invoice:"):
            return "etc_invoice_attachment"
        if legacy_gridfs_id.startswith("historical_etc_repair:"):
            return "historical_etc_repair_seed"
        if metadata.get("session_id") or legacy_gridfs_id.startswith("import_file_"):
            return "import_source_file"
        if "oa" in legacy_gridfs_id.lower():
            return "oa_attachment_cache"
        return "other_gridfs_file"

    def _file_object_id(self, legacy_gridfs_id: str) -> str:
        return str(uuid.uuid5(GRIDFS_FILE_OBJECT_NAMESPACE, f"app-gridfs:{legacy_gridfs_id}"))

    def _import_file_id(self, legacy_gridfs_id: str) -> str:
        return str(uuid.uuid5(GRIDFS_IMPORT_FILE_NAMESPACE, f"app-gridfs-import-file:{legacy_gridfs_id}"))

    def _file_checksum_gate(
        self,
        files: list[dict[str, Any]],
        *,
        sample_summary: dict[str, int],
        dry_run: bool,
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if dry_run:
            reasons.append("dry_run_does_not_download_verify_objects")
        if findings:
            reasons.append("blocking_findings_present")
        if sample_summary.get("mismatched", 0) > 0:
            reasons.append("sample_download_checksum_mismatch")
        if not dry_run and sample_summary.get("sampled", 0) == 0 and files:
            reasons.append("no_download_samples_verified")
        return {
            "decision": "NO_GO" if reasons else "GO",
            "reasons": reasons,
            "requires_report": "gridfs-checksum-validation-report.json",
        }

    @staticmethod
    def _mark_file_failed(file_entry: dict[str, Any], finding: dict[str, Any]) -> None:
        file_entry["status"] = "failed"
        file_entry["migration_status"] = "failed"
        file_entry["error_code"] = finding.get("code")
        file_entry["error_summary"] = finding.get("message")

    def _checksum_validation_report(self, output_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
        output_files = [
            "gridfs-minio-migration-manifest.json",
            "gridfs-object-mapping.ndjson",
            "file-objects-import.ndjson",
            "legacy-id-map-import.ndjson",
            "gridfs-migration-failures.ndjson",
        ]
        output_checksums = {
            name: self._sha256_file(output_dir / name)
            for name in output_files
            if (output_dir / name).exists()
        }
        duplicate_groups = self._duplicate_file_groups(manifest["files"])
        size_differences = [
            finding
            for finding in manifest["findings"]
            if finding.get("code") == "GRIDFS_LENGTH_MISMATCH"
        ]
        missing_files = [
            finding
            for finding in manifest["findings"]
            if finding.get("code") == "GRIDFS_READ_ERROR"
        ]
        source_manifest_path = output_dir / "gridfs-minio-migration-manifest.json"
        file_checksum_gate = manifest["readiness_gates"]["file_checksum"]
        status = "GO" if file_checksum_gate["decision"] == "GO" else "NO_GO"
        reason = "File checksum gate passed." if status == "GO" else "Blocking file checksum findings exist."
        return {
            "report_id": f"gridfs-minio-checksum-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
            "migration_run_id": manifest.get("migration_run_id")
            or str(uuid.uuid5(GRIDFS_FILE_OBJECT_NAMESPACE, manifest["started_at"])),
            "phase": "06d_gridfs_minio_migration",
            "tool": GRIDFS_MIGRATION_TOOL_VERSION,
            "status": status,
            "readiness_gates": manifest["readiness_gates"],
            "secret_free": True,
            "source": {
                "kind": "app_mongo_gridfs",
                "database": manifest["source"]["database"],
                "gridfs_bucket": manifest["source"]["gridfs_bucket"],
                "source_manifest_path": str(source_manifest_path),
                "source_manifest_sha256": output_checksums.get("gridfs-minio-migration-manifest.json"),
            },
            "target": {
                "storage_provider": manifest["target"]["storage_provider"],
                "bucket": manifest["target"]["bucket"],
                "environment": manifest["target"]["environment"],
                "endpoint_present": None,
            },
            "coverage": {
                "manifest_checksum": {
                    "status": "covered",
                    "sha256": output_checksums.get("gridfs-minio-migration-manifest.json"),
                },
                "output_file_checksums": output_checksums,
                "sample_download_hash": manifest["summary"]["checksum_samples"],
                "missing_files": {
                    "count": len(missing_files),
                    "items": missing_files,
                },
                "duplicate_files": {
                    "count": sum(len(group["legacy_gridfs_ids"]) for group in duplicate_groups),
                    "groups": duplicate_groups,
                },
                "size_differences": {
                    "count": len(size_differences),
                    "items": size_differences,
                },
            },
            "legacy_id_mapping": {
                "mapping_file": "gridfs-object-mapping.ndjson",
                "legacy_id_map_file": "legacy-id-map-import.ndjson",
                "expected_gridfs_files": manifest["summary"]["total_files"],
                "mapped_file_objects": len([file_entry for file_entry in manifest["files"] if file_entry["status"] != "failed"]),
                "mapped_import_files": len([file_entry for file_entry in manifest["files"] if file_entry["status"] != "failed"]),
                "missing_mappings": [
                    file_entry["legacy_gridfs_id"]
                    for file_entry in manifest["files"]
                    if file_entry["status"] == "failed"
                ],
            },
            "findings": manifest["findings"],
            "decision": {
                "go_no_go": status,
                "reason": reason,
                "required_action": ""
                if status == "GO"
                else "Fix object migration issue and rerun 06D upload or verify mode until file_checksum is GO.",
            },
        }

    def _duplicate_file_groups(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for file_entry in files:
            sha256 = file_entry.get("sha256")
            if not sha256:
                continue
            key = (str(sha256), int(file_entry.get("byte_size") or 0))
            grouped.setdefault(key, []).append(file_entry)
        return [
            {
                "sha256": sha256,
                "byte_size": byte_size,
                "legacy_gridfs_ids": [entry["legacy_gridfs_id"] for entry in entries],
                "file_object_ids": [entry["file_object_id"] for entry in entries],
            }
            for (sha256, byte_size), entries in sorted(grouped.items())
            if len(entries) > 1
        ]

    def _failure_reason(
        self,
        *,
        code: str,
        message: str,
        exception: Exception | None,
    ) -> dict[str, Any]:
        reason: dict[str, Any] = {"code": code, "message": message}
        if exception is not None:
            reason["exception_type"] = type(exception).__name__
            reason["exception"] = self._redact_text(str(exception))
        return reason

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _redact_text(value: str) -> str:
        redacted = value
        for marker in ("secret", "access_key", "session_token", "token", "password"):
            redacted = redacted.replace(marker, "[redacted]")
            redacted = redacted.replace(marker.upper(), "[redacted]")
        return redacted

    def _with_retries(self, operation, *, max_retries: int):
        attempts = max(1, max_retries + 1)
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError("operation failed")

    def _year_month(self, upload_date: str | None) -> tuple[str, str]:
        if upload_date:
            try:
                parsed = datetime.fromisoformat(upload_date.replace("Z", "+00:00"))
                return f"{parsed.year:04d}", f"{parsed.month:02d}"
            except ValueError:
                pass
        return "unknown", "unknown"

    def _serialize_value(self, value: Any) -> Any:
        return self._store._serialize_value(value)  # noqa: SLF001 - reuse existing app Mongo normalization.

    @staticmethod
    def _resolve_mode(*, mode: GridFSMigrationMode | str | None, dry_run: bool | None) -> GridFSMigrationMode:
        if mode is None:
            return "dry-run" if dry_run is not False else "upload"
        normalized = str(mode).strip().lower().replace("_", "-")
        if normalized in {"dryrun", "dry-run"}:
            return "dry-run"
        if normalized in {"upload", "verify"}:
            return normalized  # type: ignore[return-value]
        raise ValueError("GridFS migration mode must be one of: dry-run, upload, verify.")

    @staticmethod
    def _safe_segment(value: str) -> str:
        normalized = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in str(value).lower())
        normalized = "-".join(segment for segment in normalized.split("-") if segment)
        return normalized or "unknown"

    @staticmethod
    def _write_ndjson(path: Path, records: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
