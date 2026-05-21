from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any

from fin_ops_platform.services.object_storage import ObjectStorageReadError, ObjectStorageRepository, ObjectStorageWriteError
from fin_ops_platform.services.postgres_repositories.common import jsonb as _jsonb


FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class ObjectWriteResult:
    storage_backend: str
    storage_uri: str
    bucket_name: str
    object_key: str
    etag: str | None
    sha256: str
    size_bytes: int
    temporary_object_key: str


def write_verified_object(
    *,
    object_storage_repository: ObjectStorageRepository,
    storage_backend: str,
    bucket_name: str,
    namespace: str,
    file_id: str,
    file_name: str,
    content: bytes,
    content_type: str | None = None,
) -> ObjectWriteResult:
    content_bytes = bytes(content or b"")
    sha256 = hashlib.sha256(content_bytes).hexdigest()
    safe_namespace = _sanitize_path_part(namespace) or "files"
    safe_file_id = _sanitize_path_part(file_id) or sha256
    safe_file_name = _sanitize_filename(file_name)
    temporary_object_key = f"tmp/{safe_namespace}/{safe_file_id}/{sha256}/{safe_file_name}"
    final_object_key = f"objects/{safe_namespace}/{safe_file_id}/{sha256}/{safe_file_name}"

    try:
        object_storage_repository.put_object(temporary_object_key, content_bytes, content_type=content_type)
        temporary_bytes = object_storage_repository.get_object(temporary_object_key)
        _verify_object_bytes(temporary_bytes, expected_sha256=sha256, expected_size=len(content_bytes), label=temporary_object_key)
        stored = object_storage_repository.put_object(final_object_key, content_bytes, content_type=content_type)
        final_bytes = object_storage_repository.get_object(final_object_key)
        _verify_object_bytes(final_bytes, expected_sha256=sha256, expected_size=len(content_bytes), label=final_object_key)
    except Exception as exc:
        try:
            object_storage_repository.delete_object(temporary_object_key)
        except Exception:
            pass
        raise ObjectStorageWriteError(str(exc) or exc.__class__.__name__) from exc

    try:
        object_storage_repository.delete_object(temporary_object_key)
    except Exception:
        pass

    return ObjectWriteResult(
        storage_backend=storage_backend,
        storage_uri=f"{storage_backend}://{bucket_name}/{final_object_key}",
        bucket_name=bucket_name,
        object_key=final_object_key,
        etag=stored.etag,
        sha256=sha256,
        size_bytes=len(content_bytes),
        temporary_object_key=temporary_object_key,
    )


def verified_object_key_from_uri(storage_uri: str, *, expected_bucket: str | None = None) -> str:
    raw_uri = str(storage_uri or "").strip()
    scheme, separator, rest = raw_uri.partition("://")
    if not scheme or not separator:
        raise ValueError("Object storage URI must include a scheme.")
    bucket, bucket_separator, object_key = rest.partition("/")
    if not bucket or not bucket_separator or not object_key:
        raise ValueError("Object storage URI must include bucket and object key.")
    if expected_bucket and bucket != expected_bucket:
        raise ValueError("Object storage URI bucket does not match configured bucket.")
    return object_key


def _verify_object_bytes(content: bytes, *, expected_sha256: str, expected_size: int, label: str) -> None:
    if len(content) != expected_size:
        raise ObjectStorageReadError(f"Object size mismatch for {label}.")
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ObjectStorageReadError(f"Object checksum mismatch for {label}.")


def _sanitize_path_part(value: str) -> str:
    return FILENAME_SAFE_RE.sub("_", str(value or "").strip()).strip("._-")


def _sanitize_filename(value: str) -> str:
    sanitized = _sanitize_path_part(value)
    return sanitized or "uploaded_file"


class GridFSObjectMigrationService:
    def __init__(
        self,
        *,
        connection: Any,
        object_storage_repository: ObjectStorageRepository,
        legacy_file_reader: Any,
        storage_backend: str | None = None,
        bucket_name: str | None = None,
    ) -> None:
        self._connection = connection
        self._object_storage = object_storage_repository
        self._legacy_file_reader = legacy_file_reader
        self._storage_backend = storage_backend or str(getattr(object_storage_repository, "backend", "minio"))
        self._bucket_name = bucket_name or str(getattr(object_storage_repository, "bucket", ""))
        if not self._bucket_name:
            raise ValueError("bucket_name is required for GridFS object migration.")

    def migrate_batch(self, *, limit: int = 100) -> dict[str, int]:
        if limit <= 0:
            raise ValueError("limit must be positive.")
        rows = self._connection.fetch_all(
            """
            select id::text as id, legacy_mongo_id, legacy_gridfs_id, storage_backend, storage_uri,
                   bucket_name, object_key, filename, sha256, size_bytes, content_type,
                   etag, migration_status, raw_payload
            from app.file_objects
            where legacy_gridfs_id is not null
              and storage_uri like 'gridfs://%%'
              and coalesce(migration_status, 'legacy') in ('legacy', 'failed', 'pending_upload')
            order by created_at, id
            limit %s
            """,
            (limit,),
        )
        migrated = 0
        failed = 0
        skipped = 0
        for row in rows:
            try:
                changed = self.migrate_one(row)
            except Exception as exc:
                failed += 1
                self._mark_failed(str(row.get("id") or ""), str(exc) or exc.__class__.__name__)
                continue
            if changed:
                migrated += 1
            else:
                skipped += 1
        return {"migrated": migrated, "failed": failed, "skipped": skipped}

    def handle_runtime_event(self, event: Any) -> dict[str, int]:
        payload = getattr(event, "payload", {}) or {}
        action = str(payload.get("action") or "migrate") if isinstance(payload, dict) else "migrate"
        limit = int(payload.get("limit") or 100) if isinstance(payload, dict) else 100
        if action == "verify":
            return self.verify_verified_objects(limit=limit)
        if action == "cleanup":
            return self.cleanup_orphan_objects(limit=limit)
        return self.migrate_batch(limit=limit)

    def migrate_one(self, row: dict[str, Any]) -> bool:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            raise ValueError("file object row id is required.")
        if str(row.get("migration_status") or "").strip() == "verified":
            return False
        storage_uri = str(row.get("storage_uri") or "").strip()
        if not storage_uri.startswith("gridfs://"):
            return False
        content = bytes(self._legacy_file_reader.read(storage_uri))
        expected_sha256 = str(row.get("sha256") or "").strip()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise ObjectStorageWriteError(f"GridFS checksum mismatch for {storage_uri}.")
        expected_size = row.get("size_bytes")
        if expected_size not in (None, "") and int(expected_size) != len(content):
            raise ObjectStorageWriteError(f"GridFS size mismatch for {storage_uri}.")
        result = write_verified_object(
            object_storage_repository=self._object_storage,
            storage_backend=self._storage_backend,
            bucket_name=self._bucket_name,
            namespace="gridfs",
            file_id=str(row.get("legacy_gridfs_id") or row.get("legacy_mongo_id") or row_id),
            file_name=str(row.get("filename") or row.get("legacy_gridfs_id") or row_id),
            content=content,
            content_type=str(row.get("content_type") or "") or None,
        )
        self._mark_verified(row_id, result, source_uri=storage_uri)
        return True

    def verify_verified_objects(self, *, limit: int = 100) -> dict[str, int]:
        rows = self._connection.fetch_all(
            """
            select id::text as id, storage_uri, object_key, sha256, size_bytes
            from app.file_objects
            where migration_status = 'verified'
              and storage_backend in ('s3', 'minio')
            order by updated_at desc nulls last, created_at desc
            limit %s
            """,
            (limit,),
        )
        checked = 0
        failed = 0
        for row in rows:
            try:
                object_key = str(row.get("object_key") or verified_object_key_from_uri(str(row.get("storage_uri") or ""), expected_bucket=self._bucket_name))
                content = self._object_storage.get_object(object_key)
                _verify_object_bytes(
                    content,
                    expected_sha256=str(row.get("sha256") or ""),
                    expected_size=int(row.get("size_bytes") or 0),
                    label=object_key,
                )
                checked += 1
            except Exception:
                failed += 1
        return {"checked": checked, "failed": failed}

    def cleanup_orphan_objects(self, *, limit: int = 100) -> dict[str, int]:
        rows = self._connection.fetch_all(
            """
            select id::text as id, storage_uri, object_key, temporary_object_key, migration_status
            from app.file_objects
            where (
                    migration_status = 'tombstoned'
                    and storage_backend in ('s3', 'minio')
                    and object_key is not null
                  )
               or (
                    migration_status in ('pending_upload', 'temporary', 'failed')
                    and temporary_object_key is not null
                  )
            order by updated_at, created_at
            limit %s
            """,
            (limit,),
        )
        deleted = 0
        for row in rows:
            for key_name in ("temporary_object_key", "object_key"):
                object_key = str(row.get(key_name) or "").strip()
                if not object_key:
                    continue
                self._object_storage.delete_object(object_key)
                deleted += 1
            row_id = str(row.get("id") or "").strip()
            if row_id:
                self._connection.execute(
                    """
                    update app.file_objects
                    set temporary_object_key = null,
                        object_key = case when migration_status = 'tombstoned' then null else object_key end,
                        updated_at = now()
                    where id = %s::uuid
                    """,
                    (row_id,),
                )
        return {"deleted": deleted}

    def rollback_verified_to_legacy(self, *, legacy_gridfs_ids: list[str]) -> int:
        normalized = [str(value).strip() for value in legacy_gridfs_ids if str(value).strip()]
        if not normalized:
            return 0
        updated = 0
        for legacy_gridfs_id in normalized:
            updated += self._connection.execute(
                """
                update app.file_objects
                set migration_status = 'legacy',
                    storage_backend = 'gridfs_legacy',
                    storage_uri = 'gridfs://import_file_blobs/' || legacy_gridfs_id,
                    bucket_name = null,
                    object_key = null,
                    etag = null,
                    updated_at = now()
                where legacy_gridfs_id = %s
                  and migration_status = 'verified'
                """,
                (legacy_gridfs_id,),
            )
        return updated

    def _mark_verified(self, row_id: str, result: ObjectWriteResult, *, source_uri: str) -> None:
        self._connection.execute(
            """
            update app.file_objects
            set storage_backend = %s,
                storage_uri = %s,
                bucket_name = %s,
                object_key = %s,
                etag = %s,
                sha256 = %s,
                size_bytes = %s,
                migration_status = 'verified',
                temporary_object_key = null,
                source_storage_backend = 'gridfs_legacy',
                source_storage_uri = %s,
                verified_at = now(),
                last_error = null,
                raw_payload = %s,
                updated_at = now()
            where id = %s::uuid
            """,
            (
                result.storage_backend,
                result.storage_uri,
                result.bucket_name,
                result.object_key,
                result.etag,
                result.sha256,
                result.size_bytes,
                source_uri,
                _jsonb(
                    {
                        "migration": {
                            "verified_at": datetime.now(UTC).isoformat(),
                            "source_storage_uri": source_uri,
                            "sha256": result.sha256,
                            "size_bytes": result.size_bytes,
                        }
                    }
                ),
                row_id,
            ),
        )

    def _mark_failed(self, row_id: str, error: str) -> None:
        if not row_id:
            return
        self._connection.execute(
            """
            update app.file_objects
            set migration_status = 'failed',
                last_error = %s,
                failed_at = now(),
                updated_at = now()
            where id = %s::uuid
            """,
            (error[:1000], row_id),
        )


def audit_event(event: str, **payload: Any) -> str:
    return json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True)
