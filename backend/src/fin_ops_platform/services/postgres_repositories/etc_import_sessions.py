from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import run_in_transaction


class PostgresEtcImportSessionRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def save_preview(self, payload: dict[str, Any], files: list[dict[str, Any]]) -> None:
        def write(connection: Any) -> None:
            connection.execute(
                """
                insert into app.etc_import_sessions(
                    session_id, status, imported_by, imported_at, task_id, task_version,
                    zip_preview_generation, confirmed_item_set_hash, preview_fingerprint, preview_summary, last_error, raw_payload
                )
                values (%s, %s, %s, %s::timestamptz, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (session_id) do update set
                    status = excluded.status,
                    imported_by = excluded.imported_by,
                    imported_at = excluded.imported_at,
                    task_id = excluded.task_id,
                    task_version = excluded.task_version,
                    zip_preview_generation = excluded.zip_preview_generation,
                    confirmed_item_set_hash = excluded.confirmed_item_set_hash,
                    preview_fingerprint = excluded.preview_fingerprint,
                    preview_summary = excluded.preview_summary,
                    last_error = excluded.last_error,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    payload["session_id"],
                    payload["status"],
                    payload.get("imported_by"),
                    _datetime_text(payload.get("imported_at")),
                    payload["task_id"],
                    int(payload["task_version"]),
                    int(payload["zip_preview_generation"]),
                    payload["confirmed_item_set_hash"],
                    payload["preview_fingerprint"],
                    _jsonb(payload.get("preview_audit") or {}),
                    payload.get("last_error"),
                    _jsonb({"normalized_payload": payload}),
                ),
            )
            row = connection.fetch_one(
                "select id::text as id from app.etc_import_sessions where session_id = %s",
                (payload["session_id"],),
            )
            if row is None or not row.get("id"):
                raise RuntimeError("ETC import session persistence did not return an id.")
            session_row_id = str(row["id"])
            connection.execute(
                "delete from app.etc_import_session_files where session_id = %s::uuid",
                (session_row_id,),
            )
            for file_payload in files:
                connection.execute(
                    """
                    insert into app.etc_import_session_files(
                        session_id, file_id, ordinal, file_object_id, original_filename,
                        sha256, size_bytes, raw_payload
                    )
                    values (%s::uuid, %s, %s, %s::uuid, %s, %s, %s, %s)
                    """,
                    (
                        session_row_id,
                        file_payload["file_id"],
                        int(file_payload["ordinal"]),
                        file_payload["file_object_id"],
                        file_payload["file_name"],
                        file_payload["sha256"],
                        int(file_payload["size_bytes"]),
                        _jsonb({"normalized_payload": file_payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def get(self, session_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select session.id::text as row_id, session.session_id, session.status,
                   session.imported_by, session.imported_at, session.task_id,
                   session.task_version, session.zip_preview_generation, session.confirmed_item_set_hash,
                   session.preview_fingerprint, session.preview_summary,
                   session.last_error, session.raw_payload, session.created_at
            from app.etc_import_sessions session
            where session.session_id = %s
            """,
            (session_id,),
        )
        if row is None:
            return None
        files = self._connection.fetch_all(
            """
            select file.file_id, file.ordinal, file.file_object_id::text as file_object_id,
                   file.original_filename, file.sha256, file.size_bytes, file.raw_payload,
                   object.storage_uri, object.object_key, object.migration_status,
                   object.tombstoned_at
            from app.etc_import_session_files file
            join app.file_objects object on object.id = file.file_object_id
            where file.session_id = %s::uuid
            order by file.ordinal, file.file_id
            """,
            (str(row["row_id"]),),
        )
        return {**dict(row), "files": [dict(item) for item in files]}

    def update_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None,
        last_error: str | None,
    ) -> dict[str, Any]:
        terminal = status in {"succeeded", "partial_success"}
        current = self.get(session_id)
        if current is None:
            raise KeyError(session_id)
        raw_payload = current.get("raw_payload") if isinstance(current.get("raw_payload"), dict) else {}
        normalized_payload = raw_payload.get("normalized_payload")
        payload = dict(normalized_payload) if isinstance(normalized_payload, dict) else dict(raw_payload)
        payload["status"] = status
        payload["imported_by"] = imported_by or payload.get("imported_by")
        payload["last_error"] = last_error
        if terminal:
            payload["imported_at"] = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            update app.etc_import_sessions
            set status = %s,
                imported_by = coalesce(%s, imported_by),
                imported_at = case when %s then now() else imported_at end,
                last_error = %s,
                raw_payload = %s,
                updated_at = now()
            where session_id = %s
            """,
            (status, imported_by, terminal, last_error, _jsonb({"normalized_payload": payload}), session_id),
        )
        row = self.get(session_id)
        if row is None:
            raise KeyError(session_id)
        return row


def _datetime_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    text = str(value or "").strip()
    return text or None


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)
