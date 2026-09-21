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
    prepared_manifest: bytes | None = None
    prepared_manifest_ref: str | None = None


class EtcImportSessionStorePort(Protocol):
    durable: bool

    def save_preview(self, session: StoredEtcImportSession, *, on_saved: Any = None) -> StoredEtcImportSession: ...

    def get(self, session_id: str, *, load_uploads: bool = True, load_manifest: bool = False) -> StoredEtcImportSession | None: ...

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None = None,
        last_error: str | None = None,
    ) -> StoredEtcImportSession: ...

    def discard_preview(self, session_id: str, *, imported_by: str, on_discard: Any = None) -> None: ...


class InMemoryEtcImportSessionStore:
    """Explicit unit-test/local adapter; production composition must use a durable adapter."""

    durable = False

    def __init__(self) -> None:
        self._sessions: dict[str, StoredEtcImportSession] = {}

    def save_preview(self, session: StoredEtcImportSession, *, on_saved: Any = None) -> StoredEtcImportSession:
        copied = _copy_session(session)
        if on_saved is not None:
            on_saved(None, copied)
        self._sessions[copied.session_id] = copied
        return _copy_session(copied)

    def get(self, session_id: str, *, load_uploads: bool = True, load_manifest: bool = False) -> StoredEtcImportSession | None:
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

    def discard_preview(self, session_id: str, *, imported_by: str, on_discard: Any = None) -> None:
        current = self._sessions.get(str(session_id or "").strip())
        if current is None:
            raise KeyError(session_id)
        if current.imported_by != str(imported_by or "").strip():
            raise PermissionError("ETC import session belongs to another user")
        if current.status == "reverted":
            return
        if current.status not in {"preparing", "preview_ready", "failed"}:
            raise ValueError(f"ETC import session cannot be discarded from status: {current.status}")
        if on_discard is not None:
            on_discard(None)
        updated = replace(current, status="reverted", last_error=None)
        self._sessions[updated.session_id] = _copy_session(updated)


class PostgresEtcImportSessionStore:
    durable = True

    def __init__(self, *, repository: Any, archive_store: Any) -> None:
        self._repository = repository
        self._archive_store = archive_store

    def save_preview(self, session: StoredEtcImportSession, *, on_saved: Any = None) -> StoredEtcImportSession:
        stored_paths: list[str] = []
        stored_uploads: list[StoredEtcImportUpload] = []
        previous_manifest = None
        if session.prepared_manifest is not None:
            previous = self._repository.get(session.session_id)
            if previous is not None:
                previous_manifest = _normalized_payload(previous.get("raw_payload")).get("prepared_manifest_ref")
        try:
            for upload in session.uploads:
                if upload.stored_file_path and upload.file_object_id:
                    stored_uploads.append(upload)
                    continue
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
                stored_paths.append(stored_path)
                if (
                    str(metadata.get("sha256") or "") != upload.sha256
                    or int(metadata.get("size_bytes") or -1) != upload.size_bytes
                ):
                    raise RuntimeError("ETC import archive storage hash or size verification failed.")
                stored_uploads.append(
                    replace(
                        upload,
                        file_object_id=file_object_id,
                        stored_file_path=stored_path,
                    )
                )
            manifest_ref = session.prepared_manifest_ref
            if session.prepared_manifest is not None and manifest_ref is None:
                metadata = self._archive_store.store_etc_import_archive(
                    session_id=session.session_id, file_id="prepared-manifest", file_name="manifest.json.gz",
                    content=session.prepared_manifest,
                )
                manifest_ref = str(metadata["stored_file_path"])
                stored_paths.append(manifest_ref)
            persisted = replace(session, uploads=tuple(stored_uploads), prepared_manifest_ref=manifest_ref)
            self._repository.save_preview(
                _session_payload(persisted),
                [_upload_payload(upload) for upload in persisted.uploads],
                **({"on_saved": lambda transaction: on_saved(transaction, persisted)} if on_saved is not None else {}),
            )
        except Exception:
            if stored_paths:
                self._archive_store.delete_unreferenced_etc_import_files(stored_paths)
            raise
        if previous_manifest and previous_manifest != persisted.prepared_manifest_ref:
            self._archive_store.delete_unreferenced_etc_import_files([previous_manifest])
        return persisted

    def get(self, session_id: str, *, load_uploads: bool = True, load_manifest: bool = False) -> StoredEtcImportSession | None:
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
            content = bytes(self._archive_store.read_etc_import_archive(stored_path)) if load_uploads else b""
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
            prepared_manifest_ref=payload.get("prepared_manifest_ref"),
            prepared_manifest=(bytes(self._archive_store.read_etc_import_archive(payload["prepared_manifest_ref"]))
                               if load_manifest and payload.get("prepared_manifest_ref") else None),
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
        loaded = self.get(session_id, load_uploads=False)
        if loaded is None:
            raise KeyError(session_id)
        return loaded

    def discard_preview(self, session_id: str, *, imported_by: str, on_discard: Any = None) -> None:
        self._repository.discard_preview(
            str(session_id or "").strip(),
            imported_by=str(imported_by or "").strip(),
            **({"on_discard": on_discard} if on_discard is not None else {}),
        )


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
        "prepared_manifest_ref": session.prepared_manifest_ref,
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
