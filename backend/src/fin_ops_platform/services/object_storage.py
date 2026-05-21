from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from typing import BinaryIO, Protocol


class ObjectStorageConfigurationError(RuntimeError):
    pass


class ObjectStorageWriteError(RuntimeError):
    pass


class ObjectStorageReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class ObjectStorageSettings:
    backend: str = "local"
    bucket: str | None = None
    endpoint_url: str | None = None
    region: str | None = None
    access_key_id: str | None = None
    secret_access_key: str | None = None

    @property
    def enabled(self) -> bool:
        return self.backend in {"s3", "minio"}

    @classmethod
    def from_env(cls) -> ObjectStorageSettings:
        backend = (os.environ.get("OBJECT_STORAGE_BACKEND") or "local").strip().lower()
        if backend not in {"local", "s3", "minio"}:
            raise ObjectStorageConfigurationError("OBJECT_STORAGE_BACKEND must be one of local, s3, or minio.")
        settings = cls(
            backend=backend,
            bucket=(os.environ.get("S3_BUCKET") or "").strip() or None,
            endpoint_url=(os.environ.get("S3_ENDPOINT_URL") or "").strip() or None,
            region=(os.environ.get("S3_REGION") or "").strip() or None,
            access_key_id=(os.environ.get("S3_ACCESS_KEY_ID") or "").strip() or None,
            secret_access_key=(os.environ.get("S3_SECRET_ACCESS_KEY") or "").strip() or None,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.enabled:
            return
        missing = [
            name
            for name, value in (
                ("S3_BUCKET", self.bucket),
                ("S3_ACCESS_KEY_ID", self.access_key_id),
                ("S3_SECRET_ACCESS_KEY", self.secret_access_key),
            )
            if not value
        ]
        if missing:
            raise ObjectStorageConfigurationError(f"Object storage is missing required config: {', '.join(missing)}.")


@dataclass(frozen=True)
class StoredObject:
    bucket: str
    object_key: str
    etag: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None


class ObjectStorageRepository(Protocol):
    def put_object(self, object_key: str, body: bytes | BinaryIO, *, content_type: str | None = None) -> StoredObject: ...

    def get_object(self, object_key: str) -> bytes: ...

    def delete_object(self, object_key: str) -> None: ...


class InMemoryObjectStorageRepository:
    def __init__(self, *, bucket: str = "fin-ops-files", backend: str = "minio") -> None:
        self.bucket = bucket
        self.backend = backend
        self.objects: dict[str, bytes] = {}
        self.metadata: dict[str, StoredObject] = {}
        self.put_calls: list[str] = []
        self.delete_calls: list[str] = []

    def put_object(self, object_key: str, body: bytes | BinaryIO, *, content_type: str | None = None) -> StoredObject:
        content = _read_body(body)
        etag = hashlib.md5(content).hexdigest()  # noqa: S324 - local S3-compatible test ETag only, not a security digest.
        stored = StoredObject(
            bucket=self.bucket,
            object_key=object_key,
            etag=etag,
            size_bytes=len(content),
            content_type=content_type,
        )
        self.objects[object_key] = content
        self.metadata[object_key] = stored
        self.put_calls.append(object_key)
        return stored

    def get_object(self, object_key: str) -> bytes:
        try:
            return self.objects[object_key]
        except KeyError as exc:
            raise FileNotFoundError(object_key) from exc

    def delete_object(self, object_key: str) -> None:
        self.objects.pop(object_key, None)
        self.metadata.pop(object_key, None)
        self.delete_calls.append(object_key)


def _read_body(body: bytes | BinaryIO) -> bytes:
    if isinstance(body, bytes):
        return bytes(body)
    return bytes(body.read())


class S3ObjectStorageRepository:
    def __init__(self, settings: ObjectStorageSettings) -> None:
        settings.validate()
        if not settings.enabled:
            raise ObjectStorageConfigurationError("S3ObjectStorageRepository requires OBJECT_STORAGE_BACKEND=s3 or minio.")
        try:
            import boto3
        except ImportError as exc:
            raise ObjectStorageConfigurationError("S3-compatible object storage requires the optional boto3 package.") from exc
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            region_name=settings.region,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
        )

    def put_object(self, object_key: str, body: bytes | BinaryIO, *, content_type: str | None = None) -> StoredObject:
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        response = self._client.put_object(Bucket=self._settings.bucket, Key=object_key, Body=body, **extra)
        return StoredObject(bucket=str(self._settings.bucket), object_key=object_key, etag=response.get("ETag"), content_type=content_type)

    def get_object(self, object_key: str) -> bytes:
        response = self._client.get_object(Bucket=self._settings.bucket, Key=object_key)
        return bytes(response["Body"].read())

    def delete_object(self, object_key: str) -> None:
        self._client.delete_object(Bucket=self._settings.bucket, Key=object_key)
