from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository

_PREVIEW_ERROR_STATUSES = {
    "duplicate_file",
    "preview_ready_with_errors",
    "source_control_mismatch",
    "unrecognized_template",
}


class ImportLifecycleService:
    def __init__(self, repository: PostgresImportLifecycleRepository) -> None:
        self._repository = repository

    def list_events(self, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        rows, total = self._repository.list_events(page=page, page_size=page_size)
        normalized_page_size = min(max(int(page_size), 1), 100)
        return {
            "rows": [self._event_payload(row) for row in rows],
            "pagination": {
                "page": max(int(page), 1),
                "page_size": normalized_page_size,
                "total": total,
                "total_pages": (total + normalized_page_size - 1) // normalized_page_size,
            },
        }

    def list_active_sessions(self, *, imported_by: str, mode: str | None = None) -> list[dict[str, Any]]:
        rows = self._repository.list_active_sessions(imported_by=imported_by, mode=mode)
        return [
            {
                "session_id": str(row.get("session_id") or ""),
                "imported_by": str(row.get("imported_by") or ""),
                "file_count": int(row.get("file_count") or 0),
                "batch_type": str(row.get("batch_type") or ""),
                "created_at": self._timestamp(row.get("created_at") or row.get("updated_at")),
                "updated_at": self._timestamp(row.get("updated_at")),
                "status": self._display_state(row),
                "job_id": str(row.get("import_job_id") or "") or None,
                "job_stage": str(row.get("job_stage") or "") or None,
                "error": str(row.get("job_error") or "") or None,
            }
            for row in rows
            if self._display_state(row) in {"awaiting_confirmation", "preview_failed", "failed"}
        ]

    def discard_session(self, *, session_id: str, imported_by: str) -> int:
        return self._repository.discard_preview_session(session_id=session_id, imported_by=imported_by)

    @classmethod
    def _event_payload(cls, row: dict[str, Any]) -> dict[str, Any]:
        status = cls._display_state(row)
        batch_type = str(row.get("batch_type") or "")
        created_count = int(row.get("created_count") or 0)
        success_count = int(row.get("count") or 0)
        updated_count = int(row.get("updated_count") or 0)
        withdrawal = PostgresImportLifecycleRepository.withdrawal_payload(row)
        return {
            "key": str(row.get("event_id") or ""),
            "batch_id": str(row.get("batch_id") or row.get("event_id") or ""),
            "batch_type": batch_type,
            "source_key": str(row.get("source_key") or ""),
            "label": str(row.get("label") or ""),
            "source_name": str(row.get("source_name") or ""),
            "imported_by": str(row.get("imported_by") or ""),
            "count": int(row["count"]) if row.get("count") is not None else None,
            "supplementary_count": None,
            "imported_at": cls._timestamp(row.get("imported_at")),
            "status": status,
            "selected_bank_name": str(row.get("selected_bank_name") or "") or None,
            "selected_bank_last4": str(row.get("selected_bank_last4") or "") or None,
            "detected_bank_name": str(row.get("detected_bank_name") or "") or None,
            "detected_last4": str(row.get("detected_last4") or "") or None,
            "withdrawal": withdrawal,
            "withdrawal_allowed": (
                batch_type == "bank_transaction"
                and status == "succeeded"
                and updated_count == 0
                and created_count > 0
                and created_count == success_count
            ),
            "session_id": str(row.get("session_id") or "") or None,
            "file_id": str(row.get("file_id") or "") or None,
            "job_id": str(row.get("import_job_id") or "") or None,
            "job_stage": str(row.get("job_stage") or "") or None,
            "error": str(row.get("job_error") or "") or None,
        }

    @staticmethod
    def _display_state(row: dict[str, Any]) -> str:
        batch_status = str(row.get("batch_status") or "").lower()
        file_status = str(row.get("file_status") or "").lower()
        session_status = str(row.get("session_status") or "").lower()
        job_status = str(row.get("job_status") or "").lower()
        if "withdrawn" in {batch_status, file_status, session_status}:
            return "withdrawn"
        if "reverted" in {batch_status, file_status, session_status} or job_status == "canceled":
            return "discarded"
        if job_status == "failed" or batch_status == "failed":
            return "failed"
        if job_status == "processing":
            return "processing"
        if job_status == "pending":
            return "queued"
        if batch_status in {"completed", "completed_with_errors"} and file_status in {"", "confirmed"}:
            return "succeeded"
        if job_status == "succeeded":
            return "succeeded" if batch_status in {"completed", "completed_with_errors"} else "inconsistent"
        if bool(row.get("has_confirmable_file")):
            return "awaiting_confirmation"
        if file_status in _PREVIEW_ERROR_STATUSES or session_status == "preview_ready_with_errors":
            return "preview_failed"
        if session_status == "preview_ready" or (batch_status == "pending" and file_status in {"", "preview_ready"}):
            return "awaiting_confirmation"
        return "unknown"

    @staticmethod
    def _timestamp(value: Any) -> str | None:
        if value is None:
            return None
        isoformat = getattr(value, "isoformat", None)
        return str(isoformat()) if callable(isoformat) else str(value)
