from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from fin_ops_platform.services.object_storage import ObjectStorageReadError, ObjectStorageRepository, ObjectStorageWriteError


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


def audit_event(event: str, **payload: Any) -> str:
    return json.dumps({"event": event, **payload}, ensure_ascii=False, sort_keys=True)
