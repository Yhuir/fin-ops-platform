from __future__ import annotations

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
from fin_ops_platform.services.search_query import normalize_money_search_query


SUPPORTED_FORM_TYPES = [OA_IMPORT_FORM_TYPE_PAYMENT, OA_IMPORT_FORM_TYPE_EXPENSE]
SUPPORTED_STATUSES = [OA_IMPORT_STATUS_COMPLETED, OA_IMPORT_STATUS_IN_PROGRESS]


class ManualOAImportStateStore(Protocol):
    def load_manual_oa_imports(self) -> dict[str, object]: ...

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        actor_id: str,
        audit: dict[str, object],
    ) -> dict[str, object]: ...

    def remove_manual_oa_import(self, row_id: str, actor_id: str) -> bool: ...


class OAManualImportService:
    def __init__(
        self,
        *,
        state_store: ManualOAImportStateStore,
        oa_adapter: object,
        workbench_query_service: object,
        attachment_invoice_promoter: object | None = None,
    ) -> None:
        self._state_store = state_store
        self._oa_adapter = oa_adapter
        self._workbench_query_service = workbench_query_service
        self._attachment_invoice_promoter = attachment_invoice_promoter

    def search(
        self,
        *,
        q: str | None = None,
        form_types: list[str] | None = None,
        statuses: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 0,
        page_size: int = 20,
    ) -> dict[str, object]:
        normalized_page = max(0, int(page or 0))
        normalized_page_size = max(1, min(int(page_size or 20), 100))
        normalized_form_types = self._normalize_options(form_types, SUPPORTED_FORM_TYPES, default=SUPPORTED_FORM_TYPES)
        normalized_statuses = self._normalize_options(statuses, SUPPORTED_STATUSES, default=SUPPORTED_STATUSES)
        fast_search = getattr(self._oa_adapter, "search_application_record_rows", None)
        if callable(fast_search):
            payload = fast_search(
                q=q,
                form_types=normalized_form_types,
                statuses=normalized_statuses,
                date_from=date_from,
                date_to=date_to,
                page=normalized_page,
                page_size=normalized_page_size,
                imported_entries=self._manual_import_entries(),
            )
            return self._normalize_fast_search_payload(
                payload,
                page=normalized_page,
                page_size=normalized_page_size,
            )
        records = self._search_records(
            q=q,
            form_types=normalized_form_types,
            statuses=normalized_statuses,
            date_from=date_from,
            date_to=date_to,
        )
        start = normalized_page * normalized_page_size
        end = start + normalized_page_size
        return {
            "rows": [self._record_to_search_row(record) for record in records[start:end]],
            "total": len(records),
            "page": normalized_page,
            "page_size": normalized_page_size,
        }

    @staticmethod
    def _normalize_fast_search_payload(payload: object, *, page: int, page_size: int) -> dict[str, object]:
        if not isinstance(payload, dict):
            return {"rows": [], "total": 0, "page": page, "page_size": page_size}
        rows = payload.get("rows")
        total = payload.get("total")
        try:
            total_count = int(total if total is not None else len(rows or []))
        except (TypeError, ValueError):
            total_count = len(rows or [])
        return {
            "rows": list(rows) if isinstance(rows, list) else [],
            "total": max(0, total_count),
            "page": page,
            "page_size": page_size,
        }

    def refresh_attachments(self, row_ids: list[str]) -> dict[str, object]:
        normalized_row_ids = self._dedupe_row_ids(row_ids)
        refresh = getattr(self._oa_adapter, "refresh_application_record_attachments", None)
        try:
            if callable(refresh):
                refreshed_records = list(refresh(normalized_row_ids))
            else:
                refreshed_records = self._records_by_row_ids(normalized_row_ids)
        except Exception as exc:
            return {
                "rows": [],
                "errors": [
                    self._error(row_id, "attachment_refresh_failed", self._failure_message(exc, "附件解析刷新失败"))
                    for row_id in normalized_row_ids
                ],
            }
        records_by_id = {record.id: record for record in refreshed_records}
        rows = [
            self._record_to_attachment_summary(records_by_id[row_id])
            for row_id in normalized_row_ids
            if row_id in records_by_id
        ]
        errors = [
            self._error(row_id, "not_found", "OA row_id 不存在")
            for row_id in normalized_row_ids
            if row_id not in records_by_id
        ]
        completed_records = [
            record
            for record in refreshed_records
            if self._record_status(record) == OA_IMPORT_STATUS_COMPLETED
        ]
        promotion_summary: dict[str, object] = {}
        if self._attachment_invoice_promoter is not None and completed_records:
            try:
                promotion = self._attachment_invoice_promoter.promote_records(completed_records)
                promotion_summary = dict((promotion or {}).get("summary") or {})
            except Exception as exc:
                errors.extend(
                    self._error(
                        record.id,
                        "attachment_promotion_failed",
                        self._failure_message(exc, "附件发票写入统一发票池失败"),
                    )
                    for record in completed_records
                )
        return {"rows": rows, "errors": errors, "promotion_summary": promotion_summary}

    def import_row_ids(self, row_ids: list[str], *, actor_id: str) -> dict[str, object]:
        normalized_row_ids = self._dedupe_row_ids(row_ids)
        try:
            records_by_id = {record.id: record for record in self._records_by_row_ids(normalized_row_ids)}
        except Exception as exc:
            return {
                "imported": [],
                "already_imported": [],
                "failed": [
                    self._error(row_id, "lookup_failed", self._failure_message(exc, "OA row_id 查询失败"))
                    for row_id in normalized_row_ids
                ],
                "rows": [],
            }
        importable_row_ids: list[str] = []
        failed: list[dict[str, str]] = []
        for row_id in normalized_row_ids:
            record = records_by_id.get(row_id)
            if record is None:
                failed.append(self._error(row_id, "not_found", "OA row_id 不存在"))
                continue
            if self._record_status(record) != OA_IMPORT_STATUS_COMPLETED:
                failed.append(self._error(row_id, "not_completed", "流程未完成，不能导入"))
                continue
            importable_row_ids.append(row_id)

        refreshed_records_by_id: dict[str, OAApplicationRecord] = {}
        if importable_row_ids:
            refresh = getattr(self._oa_adapter, "refresh_application_record_attachments", None)
            try:
                refreshed_records = (
                    list(refresh(importable_row_ids))
                    if callable(refresh)
                    else self._records_by_row_ids(importable_row_ids)
                )
            except Exception as exc:
                failed.extend(
                    self._error(row_id, "attachment_refresh_failed", self._failure_message(exc, "附件解析刷新失败"))
                    for row_id in importable_row_ids
                )
                importable_row_ids = []
                refreshed_records = []
            refreshed_records_by_id = {record.id: record for record in refreshed_records}
            missing_after_refresh = [row_id for row_id in importable_row_ids if row_id not in refreshed_records_by_id]
            if missing_after_refresh:
                failed.extend(
                    self._error(row_id, "not_found", "OA row_id 不存在")
                    for row_id in missing_after_refresh
                )
                importable_row_ids = [row_id for row_id in importable_row_ids if row_id in refreshed_records_by_id]

        store_result = {"imported": [], "already_imported": []}
        if importable_row_ids:
            sync = getattr(self._workbench_query_service, "sync_oa_row_ids", None)
            if callable(sync):
                try:
                    sync(importable_row_ids)
                except Exception as exc:
                    failed.extend(
                        self._error(row_id, "sync_failed", self._failure_message(exc, "OA 同步进 app 失败"))
                        for row_id in importable_row_ids
                    )
                    importable_row_ids = []
            if importable_row_ids:
                try:
                    store_result = self._state_store.add_manual_oa_imports(
                        importable_row_ids,
                        actor_id,
                        {
                            "operation": "manual_oa_import",
                            "row_ids": importable_row_ids,
                            "attachment_summaries": [
                                self._record_to_attachment_summary(refreshed_records_by_id[row_id])
                                for row_id in importable_row_ids
                                if row_id in refreshed_records_by_id
                            ],
                        },
                    )
                except Exception as exc:
                    failed.extend(
                        self._error(row_id, "persistence_failed", self._failure_message(exc, "手动导入状态保存失败"))
                        for row_id in importable_row_ids
                    )
                    importable_row_ids = []

        rows = [
            self._record_to_search_row(refreshed_records_by_id[row_id])
            for row_id in importable_row_ids
            if row_id in refreshed_records_by_id
        ]
        return {
            "imported": list(store_result.get("imported") or []),
            "already_imported": list(store_result.get("already_imported") or []),
            "failed": failed,
            "rows": rows,
        }

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

    def manual_retained_row_ids(self) -> list[str]:
        payload = self._state_store.load_manual_oa_imports()
        return [clean_string(row_id) for row_id in list(payload.get("row_ids") or []) if clean_string(row_id)]

    def _search_records(
        self,
        *,
        q: str | None,
        form_types: list[str],
        statuses: list[str],
        date_from: str | None,
        date_to: str | None,
    ) -> list[OAApplicationRecord]:
        search = getattr(self._oa_adapter, "search_application_records", None)
        if callable(search):
            records = list(
                search(
                    q=q,
                    form_types=form_types,
                    statuses=statuses,
                    date_from=date_from,
                    date_to=date_to,
                )
            )
        else:
            list_all = getattr(self._oa_adapter, "list_all_application_records", None)
            records = list(list_all()) if callable(list_all) else []
        return [
            record
            for record in records
            if self._record_form_type(record) in set(form_types)
            and self._record_status(record) in set(statuses)
            and self._record_matches_query(record, q)
            and self._record_matches_date_range(record, date_from=date_from, date_to=date_to)
        ]

    def _records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        list_by_ids = getattr(self._oa_adapter, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            return list(list_by_ids(row_ids))
        list_all = getattr(self._oa_adapter, "list_all_application_records", None)
        if not callable(list_all):
            return []
        records_by_id = {record.id: record for record in list(list_all())}
        return [records_by_id[row_id] for row_id in row_ids if row_id in records_by_id]

    def _record_to_search_row(self, record: OAApplicationRecord) -> dict[str, object]:
        status = self._record_status(record)
        form_type = self._record_form_type(record)
        imported_entries = self._manual_import_entries()
        imported_entry = imported_entries.get(record.id, {})
        can_import = status == OA_IMPORT_STATUS_COMPLETED
        attachment_file_count = self._attachment_file_count(record)
        importable_invoice_count = self._importable_invoice_count(record)
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
            "attachment_file_count": attachment_file_count,
            "importable_invoice_count": importable_invoice_count,
            "unrecognized_attachment_count": max(0, attachment_file_count - importable_invoice_count),
            "import_status": "imported" if record.id in imported_entries else "not_imported",
            "imported_at": imported_entry.get("imported_at") if isinstance(imported_entry, dict) else None,
            "can_import": can_import,
            "disabled_reason": "" if can_import else "流程未完成",
            "items": [self._expense_item_to_row(item, record) for item in record.expense_items],
        }

    def _record_to_attachment_summary(self, record: OAApplicationRecord) -> dict[str, object]:
        attachment_file_count = self._attachment_file_count(record)
        importable_invoice_count = self._importable_invoice_count(record)
        return {
            "row_id": record.id,
            "attachment_file_count": attachment_file_count,
            "importable_invoice_count": importable_invoice_count,
            "unrecognized_attachment_count": max(0, attachment_file_count - importable_invoice_count),
        }

    def _expense_item_to_row(self, item: dict[str, Any], record: OAApplicationRecord) -> dict[str, object]:
        attachment_file_count = self._int_value(item.get("attachment_file_count"))
        importable_invoice_count = len(
            [
                invoice
                for invoice in list(item.get("attachment_invoices") or [])
                if isinstance(invoice, dict)
            ]
        )
        return {
            "date": clean_string(item.get("reimbursement_date") or item.get("date") or self._application_date(record)),
            "amount": clean_string(item.get("amount") or ""),
            "content": clean_string(item.get("expense_content") or item.get("content") or record.reason),
            "project_name": clean_string(item.get("project_name") or record.project_name),
            "reason": record.reason,
            "attachment_file_count": attachment_file_count,
            "importable_invoice_count": importable_invoice_count,
        }

    def _manual_import_entries(self) -> dict[str, Any]:
        payload = self._state_store.load_manual_oa_imports()
        entries = payload.get("entries")
        return dict(entries) if isinstance(entries, dict) else {}

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
    def _dedupe_row_ids(row_ids: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for row_id in list(row_ids or []):
            normalized = clean_string(row_id)
            if not normalized or normalized in seen:
                continue
            result.append(normalized)
            seen.add(normalized)
        return result

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
    def _attachment_file_count(record: OAApplicationRecord) -> int:
        return max(int(record.attachment_file_count or 0), len(record.attachment_artifacts), len(record.attachment_invoices))

    @staticmethod
    def _importable_invoice_count(record: OAApplicationRecord) -> int:
        return len([invoice for invoice in record.attachment_invoices if isinstance(invoice, dict)])

    @classmethod
    def _record_matches_query(cls, record: OAApplicationRecord, q: str | None) -> bool:
        query = normalize_money_search_query(clean_string(q)).lower()
        if not query:
            return True
        values: list[str] = [
            record.id,
            record.month,
            record.applicant,
            record.project_name,
            record.apply_type,
            record.amount,
            record.counterparty_name,
            record.reason,
            record.expense_type or "",
            record.expense_content or "",
        ]

        def visit(value: Any) -> None:
            if value in (None, ""):
                return
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
                return
            if isinstance(value, (list, tuple, set)):
                for child in value:
                    visit(child)
                return
            text = clean_string(value)
            if text:
                values.append(text)

        visit(record.detail_fields)
        visit(record.attachment_invoices)
        visit(record.attachment_artifacts)
        visit(record.expense_items)
        haystack = "\n".join(values).lower()
        if query.replace(".", "", 1).lstrip("+-").isdigit():
            haystack = haystack.replace(",", "")
        return query in haystack

    @classmethod
    def _record_matches_date_range(
        cls,
        record: OAApplicationRecord,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        application_date = cls._application_date(record)
        if date_from and application_date and application_date < clean_string(date_from):
            return False
        if date_to and application_date and application_date > clean_string(date_to):
            return False
        return True

    @staticmethod
    def _int_value(value: object) -> int:
        try:
            return int(Decimal(clean_string(value) or "0"))
        except (InvalidOperation, ValueError):
            return 0

    @staticmethod
    def _error(row_id: str, code: str, message: str) -> dict[str, str]:
        return {"row_id": row_id, "code": code, "message": message}

    @staticmethod
    def _failure_message(exc: Exception, fallback: str) -> str:
        message = clean_string(str(exc))
        return f"{fallback}：{message}" if message else fallback
