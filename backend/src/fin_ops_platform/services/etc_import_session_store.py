from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StoredEtcImportUpload:
    file_id: str
    file_name: str
    content: bytes
    sha256: str
    size_bytes: int
    ordinal: int
    file_object_id: str | None = None
    stored_file_path: str | None = None


@dataclass(frozen=True, slots=True)
class StoredEtcImportSession:
    session_id: str
    status: str
    task_id: str
    task_version: int
    zip_preview_generation: int
    confirmed_item_set_hash: str
    preview_fingerprint: str
    preview_result: dict[str, Any]
    preview_audit: dict[str, Any]
    preview_files: list[dict[str, Any]]
    reconciliation_filter: dict[str, Any]
    uploads: tuple[StoredEtcImportUpload, ...]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    imported_by: str | None = None
    imported_at: datetime | None = None
    last_error: str | None = None


class EtcImportSessionStorePort(Protocol):
    durable: bool

    def save_preview(self, session: StoredEtcImportSession) -> StoredEtcImportSession: ...

    def get(self, session_id: str) -> StoredEtcImportSession | None: ...

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None = None,
        last_error: str | None = None,
    ) -> StoredEtcImportSession: ...


class InMemoryEtcImportSessionStore:
    """Explicit unit-test/local adapter; production composition must use a durable adapter."""

    durable = False

    def __init__(self) -> None:
        self._sessions: dict[str, StoredEtcImportSession] = {}

    def save_preview(self, session: StoredEtcImportSession) -> StoredEtcImportSession:
        copied = _copy_session(session)
        self._sessions[copied.session_id] = copied
        return _copy_session(copied)

    def get(self, session_id: str) -> StoredEtcImportSession | None:
        session = self._sessions.get(str(session_id or "").strip())
        return _copy_session(session) if session is not None else None

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None = None,
        last_error: str | None = None,
    ) -> StoredEtcImportSession:
        current = self._sessions.get(str(session_id or "").strip())
        if current is None:
            raise KeyError(session_id)
        terminal = status in {"succeeded", "partial_success"}
        updated = replace(
            current,
            status=str(status),
            imported_by=str(imported_by or "").strip() or current.imported_by,
            imported_at=datetime.now(UTC) if terminal else current.imported_at,
            last_error=str(last_error or "").strip() or None,
        )
        self._sessions[updated.session_id] = _copy_session(updated)
        return _copy_session(updated)


class PostgresEtcImportSessionStore:
    durable = True

    def __init__(self, *, repository: Any, archive_store: Any) -> None:
        self._repository = repository
        self._archive_store = archive_store

    def save_preview(self, session: StoredEtcImportSession) -> StoredEtcImportSession:
        stored_paths: list[str] = []
        stored_uploads: list[StoredEtcImportUpload] = []
        try:
            for upload in session.uploads:
                metadata = self._archive_store.store_etc_import_archive(
                    session_id=session.session_id,
                    file_id=upload.file_id,
                    file_name=upload.file_name,
                    content=upload.content,
                )
                stored_path = str(metadata.get("stored_file_path") or "").strip()
                file_object_id = str(metadata.get("file_object_id") or "").strip()
                if not stored_path or not file_object_id:
                    raise RuntimeError("ETC import archive storage did not return a verified object reference.")
                if (
                    str(metadata.get("sha256") or "") != upload.sha256
                    or int(metadata.get("size_bytes") or -1) != upload.size_bytes
                ):
                    raise RuntimeError("ETC import archive storage hash or size verification failed.")
                stored_paths.append(stored_path)
                stored_uploads.append(
                    replace(
                        upload,
                        file_object_id=file_object_id,
                        stored_file_path=stored_path,
                    )
                )
            persisted = replace(session, uploads=tuple(stored_uploads))
            self._repository.save_preview(
                _session_payload(persisted),
                [_upload_payload(upload) for upload in persisted.uploads],
            )
        except Exception:
            if stored_paths:
                self._archive_store.delete_etc_import_archives(stored_paths)
            raise
        return persisted

    def get(self, session_id: str) -> StoredEtcImportSession | None:
        row = self._repository.get(str(session_id or "").strip())
        if row is None:
            return None
        payload = _normalized_payload(row.get("raw_payload"))
        uploads: list[StoredEtcImportUpload] = []
        for file_row in list(row.get("files") or []):
            if file_row.get("tombstoned_at") is not None:
                raise RuntimeError("ETC import archive object is tombstoned.")
            stored_path = str(file_row.get("storage_uri") or "").strip()
            if not stored_path:
                raise RuntimeError("ETC import archive object has no storage URI.")
            content = bytes(self._archive_store.read_etc_import_archive(stored_path))
            uploads.append(
                StoredEtcImportUpload(
                    file_id=str(file_row.get("file_id") or ""),
                    file_name=str(file_row.get("original_filename") or ""),
                    content=content,
                    sha256=str(file_row.get("sha256") or ""),
                    size_bytes=int(file_row.get("size_bytes") or 0),
                    ordinal=int(file_row.get("ordinal") or 0),
                    file_object_id=str(file_row.get("file_object_id") or "") or None,
                    stored_file_path=stored_path,
                )
            )
        return StoredEtcImportSession(
            session_id=str(row.get("session_id") or ""),
            status=str(row.get("status") or "preview_ready"),
            task_id=str(row.get("task_id") or payload.get("task_id") or ""),
            task_version=int(row.get("task_version") or payload.get("task_version") or 0),
            zip_preview_generation=int(
                row.get("zip_preview_generation") or payload.get("zip_preview_generation") or 0
            ),
            confirmed_item_set_hash=str(
                row.get("confirmed_item_set_hash") or payload.get("confirmed_item_set_hash") or ""
            ),
            preview_fingerprint=str(row.get("preview_fingerprint") or payload.get("preview_fingerprint") or ""),
            preview_result=dict(payload.get("preview_result") or {}),
            preview_audit=dict(payload.get("preview_audit") or {}),
            preview_files=[dict(item) for item in list(payload.get("preview_files") or []) if isinstance(item, dict)],
            reconciliation_filter=dict(payload.get("reconciliation_filter") or {}),
            uploads=tuple(uploads),
            created_at=_datetime_value(row.get("created_at")),
            imported_by=str(row.get("imported_by") or "") or None,
            imported_at=_optional_datetime(row.get("imported_at")),
            last_error=str(row.get("last_error") or "") or None,
        )

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None = None,
        last_error: str | None = None,
    ) -> StoredEtcImportSession:
        self._repository.update_status(
            str(session_id or "").strip(),
            status=str(status),
            imported_by=str(imported_by or "").strip() or None,
            last_error=str(last_error or "").strip() or None,
        )
        loaded = self.get(session_id)
        if loaded is None:
            raise KeyError(session_id)
        return loaded


def build_etc_import_session_store(state_store: Any) -> EtcImportSessionStorePort:
    repository = getattr(state_store, "etc_import_session_repository", None)
    required_methods = (
        "store_etc_import_archive",
        "read_etc_import_archive",
        "delete_etc_import_archives",
    )
    if repository is not None and all(callable(getattr(state_store, name, None)) for name in required_methods):
        return PostgresEtcImportSessionStore(repository=repository, archive_store=state_store)
    return InMemoryEtcImportSessionStore()


def _copy_session(session: StoredEtcImportSession) -> StoredEtcImportSession:
    return replace(
        session,
        preview_result=deepcopy(session.preview_result),
        preview_audit=deepcopy(session.preview_audit),
        preview_files=deepcopy(session.preview_files),
        reconciliation_filter=deepcopy(session.reconciliation_filter),
        uploads=tuple(
            replace(upload, content=bytes(upload.content))
            for upload in session.uploads
        ),
    )


def _session_payload(session: StoredEtcImportSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "status": session.status,
        "task_id": session.task_id,
        "task_version": session.task_version,
        "zip_preview_generation": session.zip_preview_generation,
        "confirmed_item_set_hash": session.confirmed_item_set_hash,
        "preview_fingerprint": session.preview_fingerprint,
        "preview_result": deepcopy(session.preview_result),
        "preview_audit": deepcopy(session.preview_audit),
        "preview_files": deepcopy(session.preview_files),
        "reconciliation_filter": deepcopy(session.reconciliation_filter),
        "created_at": session.created_at.isoformat(),
        "imported_by": session.imported_by,
        "imported_at": session.imported_at.isoformat() if session.imported_at is not None else None,
        "last_error": session.last_error,
    }


def _upload_payload(upload: StoredEtcImportUpload) -> dict[str, Any]:
    return {
        "file_id": upload.file_id,
        "file_name": upload.file_name,
        "ordinal": upload.ordinal,
        "file_object_id": upload.file_object_id,
        "stored_file_path": upload.stored_file_path,
        "sha256": upload.sha256,
        "size_bytes": upload.size_bytes,
    }


def _normalized_payload(value: Any) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    normalized = payload.get("normalized_payload")
    return dict(normalized) if isinstance(normalized, dict) else dict(payload)


def _datetime_value(value: Any) -> datetime:
    parsed = _optional_datetime(value)
    return parsed or datetime.now(UTC)


def _optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
