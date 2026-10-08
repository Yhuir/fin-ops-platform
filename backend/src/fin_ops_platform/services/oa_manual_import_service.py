from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.mongo_oa_adapter import (
    OA_IMPORT_FORM_TYPE_EXPENSE,
    OA_IMPORT_FORM_TYPE_PAYMENT,
    OA_IMPORT_STATUS_COMPLETED,
    OA_IMPORT_STATUS_IN_PROGRESS,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_attachment_summary import attachment_summary, record_attachment_summary

SUPPORTED_FORM_TYPES = [OA_IMPORT_FORM_TYPE_PAYMENT, OA_IMPORT_FORM_TYPE_EXPENSE]
SUPPORTED_STATUSES = [OA_IMPORT_STATUS_COMPLETED, OA_IMPORT_STATUS_IN_PROGRESS]


class ManualOAImportStateStore(Protocol):
    def load_manual_oa_imports(self) -> dict[str, object]: ...

    def remove_manual_oa_import(self, row_id: str, actor_id: str) -> bool: ...


class ManualOASearchPort(Protocol):
    def search_application_record_rows(
        self, *, q: str | None, form_types: list[str], statuses: list[str],
        date_from: str | None, date_to: str | None, page: int, page_size: int,
    ) -> dict[str, object]: ...


class OAManualImportService:
    def __init__(self, *, state_store: ManualOAImportStateStore, oa_adapter: ManualOASearchPort) -> None:
        self._state_store = state_store
        self._oa_adapter = oa_adapter

    def search(
        self, *, q: str | None = None, form_types: list[str] | None = None,
        statuses: list[str] | None = None, date_from: str | None = None,
        date_to: str | None = None, page: int = 0, page_size: int = 20,
    ) -> dict[str, object]:
        normalized_page = max(0, int(page or 0))
        normalized_page_size = max(1, min(int(page_size or 20), 100))
        normalized_form_types = self._normalize_options(form_types, SUPPORTED_FORM_TYPES, default=SUPPORTED_FORM_TYPES)
        normalized_statuses = self._normalize_options(statuses, SUPPORTED_STATUSES, default=SUPPORTED_STATUSES)
        for value in (date_from, date_to):
            if value and (len(value) != 10 or date.fromisoformat(value).isoformat() != value):
                raise ValueError("搜索日期必须为 YYYY-MM-DD。")
        if date_from and date_to and date_from > date_to:
            raise ValueError("开始日期不能晚于结束日期。")
        return self._oa_adapter.search_application_record_rows(
            q=q, form_types=normalized_form_types, statuses=normalized_statuses,
            date_from=date_from, date_to=date_to, page=normalized_page,
            page_size=normalized_page_size,
        )

    def list_manual_imports(self) -> dict[str, object]:
        payload = self._state_store.load_manual_oa_imports()
        return {
            "row_ids": list(payload.get("row_ids") or []),
            "entries": list((payload.get("entries") or {}).values()) if isinstance(payload.get("entries"), dict) else [],
        }

    def remove_manual_import(self, row_id: str, *, actor_id: str) -> dict[str, object]:
        normalized_row_id = clean_string(row_id)
        removed = self._state_store.remove_manual_oa_import(normalized_row_id, actor_id)
        return {"removed": removed, "row_id": normalized_row_id}

    def serialize_import_result_rows(
        self, records: list[OAApplicationRecord], *, imported_entries: dict[str, Any],
    ) -> list[dict[str, object]]:
        return [self._record_to_search_row(record, imported_entries=imported_entries) for record in records]

    def _record_to_search_row(self, record: OAApplicationRecord, *, imported_entries: dict[str, Any]) -> dict[str, object]:
        status = self._record_status(record)
        form_type = self._record_form_type(record)
        imported_entry = imported_entries.get(record.id, {})
        can_import = status == OA_IMPORT_STATUS_COMPLETED
        return {
            "row_id": record.id,
            "oa_no": self._oa_no(record),
            "applicant": record.applicant,
            "application_date": self._application_date(record),
            "form_type": form_type,
            "form_type_label": self._form_type_label(form_type),
            "status": status,
            "status_label": self._status_label(status),
            "project_name": record.project_name,
            "reason": record.reason,
            "amount": record.amount,
            **record_attachment_summary(record),
            "import_status": "imported" if record.id in imported_entries else "not_imported",
            "imported_at": imported_entry.get("imported_at") if isinstance(imported_entry, dict) else None,
            "can_import": can_import,
            "disabled_reason": "" if can_import else "流程未完成",
            "items": [self._expense_item_to_row(item, record) for item in record.expense_items],
        }

    def _expense_item_to_row(self, item: dict[str, Any], record: OAApplicationRecord) -> dict[str, object]:
        return {
            "date": clean_string(item.get("reimbursement_date") or item.get("date") or self._application_date(record)),
            "amount": clean_string(item.get("amount") or ""),
            "content": clean_string(item.get("expense_content") or item.get("content") or record.reason),
            "project_name": clean_string(item.get("project_name") or record.project_name),
            "reason": record.reason,
            **attachment_summary(file_count=self._int_value(item.get("attachment_file_count")),
                artifacts=list(item.get("attachment_artifacts") or []),
                invoices=list(item.get("attachment_invoices") or [])),
        }

    @staticmethod
    def _normalize_options(values: list[str] | None, allowed: list[str], *, default: list[str]) -> list[str]:
        if values is None:
            return list(default)
        seen: set[str] = set()
        for value in values:
            normalized = clean_string(value)
            if normalized in allowed:
                seen.add(normalized)
        return [value for value in allowed if value in seen]

    @staticmethod
    def _record_form_type(record: OAApplicationRecord) -> str:
        return OA_IMPORT_FORM_TYPE_PAYMENT if record.apply_type == "支付申请" else OA_IMPORT_FORM_TYPE_EXPENSE

    @staticmethod
    def _record_status(record: OAApplicationRecord) -> str:
        status_label = clean_string(record.detail_fields.get("流程状态") or "")
        return OA_IMPORT_STATUS_COMPLETED if status_label == "已完成" else OA_IMPORT_STATUS_IN_PROGRESS

    @staticmethod
    def _form_type_label(form_type: str) -> str:
        return "支付申请" if form_type == OA_IMPORT_FORM_TYPE_PAYMENT else "日常报销"

    @staticmethod
    def _status_label(status: str) -> str:
        return "已完成" if status == OA_IMPORT_STATUS_COMPLETED else "进行中"

    @staticmethod
    def _application_date(record: OAApplicationRecord) -> str:
        return clean_string(record.detail_fields.get("申请日期") or record.month)

    @staticmethod
    def _oa_no(record: OAApplicationRecord) -> str:
        return clean_string(record.detail_fields.get("OA单号") or record.id)

    @staticmethod
    def _int_value(value: object) -> int:
        try:
            return int(Decimal(clean_string(value) or "0"))
        except (InvalidOperation, ValueError):
            return 0
