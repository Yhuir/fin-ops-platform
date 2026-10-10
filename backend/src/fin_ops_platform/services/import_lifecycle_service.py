from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository

_HISTORY_STATUSES = {
    "awaiting_confirmation", "queued", "processing", "succeeded", "partial_success",
    "withdrawn", "failed", "discarded", "preview_failed", "inconsistent", "unknown",
}


class ImportLifecycleService:
    def __init__(self, repository: PostgresImportLifecycleRepository) -> None:
        self._repository = repository

    def list_events(
        self, *, page: int = 1, page_size: int = 50, batch_type: str = "",
        status: str = "", search: str = "", start_date: str = "", end_date: str = "",
    ) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError("页码必须大于零，每页数量必须在 1–100 之间。")
        if batch_type and batch_type not in {"bank_transaction", "input_invoice", "output_invoice"}:
            raise ValueError("导入类型无效。")
        if status and status not in _HISTORY_STATUSES:
            raise ValueError("导入状态无效。")
        search = search.strip()
        if len(search) > 200:
            raise ValueError("文件名查询不能超过 200 个字符。")
        start = self._date_boundary(start_date)
        end = self._date_boundary(end_date, end=True)
        if start is not None and end is not None and start >= end:
            raise ValueError("开始日期不能晚于结束日期。")
        rows, total = self._repository.list_events(
            page=page, page_size=page_size, batch_type=batch_type, status=status,
            search=search, start_at=start, end_at=end,
        )
        return {"rows": [self._event_payload(row) for row in rows], "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        }}

    def detail_event(self, batch_id: str) -> dict[str, Any]:
        if not batch_id or len(batch_id) > 200:
            raise ValueError("导入批次编号无效。")
        rows, _ = self._repository.list_events(page=1, page_size=1, batch_id=batch_id)
        if not rows:
            raise KeyError(batch_id)
        return {"row": self._event_payload(rows[0])}

    @staticmethod
    def _date_boundary(value: str, *, end: bool = False) -> datetime | None:
        if not value:
            return None
        day = date.fromisoformat(value)
        if day.isoformat() != value:
            raise ValueError("日期必须使用 YYYY-MM-DD 格式。")
        if end:
            day += timedelta(days=1)
        return datetime.combine(day, time.min, ZoneInfo("Asia/Shanghai"))

    def discard_session(self, *, session_id: str, imported_by: str) -> int:
        return self._repository.discard_preview_session(session_id=session_id, imported_by=imported_by)

    @classmethod
    def _event_payload(cls, row: dict[str, Any]) -> dict[str, Any]:
        status = str(row["display_status"])
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
    def _timestamp(value: Any) -> str | None:
        if value is None:
            return None
        isoformat = getattr(value, "isoformat", None)
        return str(isoformat()) if callable(isoformat) else str(value)
