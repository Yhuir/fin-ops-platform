from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.etc_import_session_store import (
    EtcImportSessionStorePort,
    StoredEtcImportSession,
    StoredEtcImportUpload,
)
from fin_ops_platform.services.etc_reconciliation_zip_filter import (
    EtcZipFilterPreview,
    StaleReconciliationPreviewError,
    filter_manifest_by_allowlist,
    filter_uploads_by_allowlist,
    preview_etc_zip_for_task,
    validate_etc_zip_confirm_for_task,
)
from fin_ops_platform.services.etc_service import (
    EtcImportPreviewStaleError,
    UploadedEtcZipFile,
    build_etc_archive_manifest,
)


@dataclass(frozen=True, slots=True)
class ValidatedEtcImportPreview:
    session: StoredEtcImportSession
    uploads: tuple[UploadedEtcZipFile, ...]
    item_total: int


class EtcImportPreviewService:
    def __init__(self, *, etc_service: Any, task_service: Any, session_store: EtcImportSessionStorePort) -> None:
        self._etc_service = etc_service
        self._task_service = task_service
        self._session_store = session_store

    def preview(
        self,
        *,
        task_id: str,
        uploads: list[UploadedEtcZipFile],
        imported_by: str,
    ) -> dict[str, Any]:
        task = self._task_service.get_task(task_id)
        payload, reconciliation_preview, filtered_uploads = self._build_preview(task=task, uploads=uploads)
        session_id = uuid4().hex
        fingerprint = _preview_fingerprint(
            task=task,
            uploads=uploads,
            payload=payload,
            reconciliation_preview=reconciliation_preview,
        )
        stored_uploads = tuple(
            StoredEtcImportUpload(
                file_id=f"etc-import-{index + 1:04d}",
                file_name=upload.file_name,
                content=bytes(upload.content),
                sha256=hashlib.sha256(upload.content).hexdigest(),
                size_bytes=len(upload.content),
                ordinal=index,
            )
            for index, upload in enumerate(uploads)
        )
        session = StoredEtcImportSession(
            session_id=session_id,
            status="preview_ready",
            task_id=str(task.task_id),
            task_version=int(task.version),
            zip_preview_generation=int(getattr(task, "zip_preview_generation", 0) or 0),
            confirmed_item_set_hash=str(task.confirmed_item_set_hash or ""),
            preview_fingerprint=fingerprint,
            preview_result=dict(payload),
            preview_audit=dict(payload.get("audit") or {}),
            preview_files=[dict(item) for item in list(payload.get("files") or []) if isinstance(item, dict)],
            reconciliation_filter=reconciliation_preview.to_payload(),
            uploads=stored_uploads,
            imported_by=str(imported_by or "").strip(),
        )
        self._session_store.save_preview(session)
        return {**payload, "sessionId": session_id}

    def validate(self, *, session_id: str, task_id: str, imported_by: str) -> ValidatedEtcImportPreview:
        session = self._session_store.get(session_id)
        if session is None:
            raise KeyError("etc_import_session_not_found")
        if session.imported_by != str(imported_by or "").strip():
            raise PermissionError("ETC import session belongs to another user")
        if session.task_id != str(task_id or "").strip():
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        if session.status not in {"preview_ready", "queued", "processing", "failed"}:
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        try:
            task = self._task_service.get_task(session.task_id)
        except KeyError as error:
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview") from error
        original_uploads = [
            UploadedEtcZipFile(upload.file_name, bytes(upload.content))
            for upload in session.uploads
        ]
        for stored, upload in zip(session.uploads, original_uploads, strict=True):
            if hashlib.sha256(upload.content).hexdigest() != stored.sha256 or len(upload.content) != stored.size_bytes:
                raise EtcImportPreviewStaleError("ETC import archive hash or size no longer matches its preview.")
        payload, reconciliation_preview, filtered_uploads = self._build_preview(task=task, uploads=original_uploads)
        validate_etc_zip_confirm_for_task(task=task, preview=reconciliation_preview)
        fingerprint = _preview_fingerprint(
            task=task,
            uploads=original_uploads,
            payload=payload,
            reconciliation_preview=reconciliation_preview,
        )
        if (
            int(task.version) != session.task_version
            or str(task.confirmed_item_set_hash or "") != session.confirmed_item_set_hash
            or reconciliation_preview.to_payload() != session.reconciliation_filter
        ):
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        if fingerprint != session.preview_fingerprint:
            raise EtcImportPreviewStaleError("ETC import preview is stale; refresh preview before confirming.")
        return ValidatedEtcImportPreview(
            session=session,
            uploads=tuple(filtered_uploads),
            item_total=sum(
                int((payload.get("summary") if isinstance(payload.get("summary"), dict) else {}).get(key) or 0)
                for key in ("imported", "duplicatesSkipped", "attachmentsCompleted", "failed")
            ),
        )

    def mark_status(
        self,
        session_id: str,
        *,
        status: str,
        imported_by: str | None = None,
        last_error: str | None = None,
    ) -> StoredEtcImportSession:
        return self._session_store.update_status(
            session_id,
            status=status,
            imported_by=imported_by,
            last_error=last_error,
        )

    def discard(self, *, session_id: str, imported_by: str) -> None:
        self._session_store.discard_preview(session_id, imported_by=imported_by)

    def _build_preview(
        self,
        *,
        task: Any,
        uploads: list[UploadedEtcZipFile],
    ) -> tuple[dict[str, Any], EtcZipFilterPreview, list[UploadedEtcZipFile]]:
        manifest = build_etc_archive_manifest(uploads)
        reconciliation_preview = preview_etc_zip_for_task(task=task, uploads=uploads, manifest=manifest)
        filtered_uploads = filter_uploads_by_allowlist(
            uploads=uploads,
            allowed_invoice_numbers=reconciliation_preview.allowed_invoice_numbers,
            manifest=manifest,
        )
        filtered_manifest = filter_manifest_by_allowlist(
            manifest=manifest,
            allowed_invoice_numbers=reconciliation_preview.allowed_invoice_numbers,
        )
        import_result, import_audit, import_file_audits = self._etc_service.inspect_import_zips(
            filtered_uploads,
            manifest=filtered_manifest,
        )
        full_result, full_audit, full_file_audits = self._etc_service.inspect_import_zips(
            uploads,
            manifest=manifest,
        )
        payload: dict[str, Any] = {
            **import_result.to_payload(),
            "summary": import_result.summary_payload(),
            "importAudit": import_audit.to_payload(),
            "importFiles": import_file_audits,
            "audit": full_audit.to_payload(),
            "files": full_file_audits,
            "items": _preview_items_with_filter_status(full_result.items, reconciliation_preview),
            "taskId": str(task.task_id),
            "reconciliationFilter": reconciliation_preview.to_payload(),
        }
        return payload, reconciliation_preview, filtered_uploads


def _preview_items_with_filter_status(items: list[Any], preview: EtcZipFilterPreview) -> list[dict[str, object]]:
    filter_items_by_invoice = {
        item.invoice_number: item
        for item in preview.items
        if item.invoice_number
    }
    decorated: list[dict[str, object]] = []
    for item in items:
        item_payload = item.to_payload()
        invoice_number = str(item_payload.get("invoiceNumber") or "")
        filter_item = filter_items_by_invoice.get(invoice_number)
        filter_status = filter_item.filter_status if filter_item is not None else "not_in_reconciliation_preview"
        item_payload["filterStatus"] = filter_status
        item_payload["requirementId"] = filter_item.requirement_id if filter_item is not None else None
        if filter_status != "included" and not item_payload.get("message"):
            item_payload["message"] = _filter_status_message(filter_status)
        decorated.append(item_payload)
    return decorated


def _filter_status_message(filter_status: str) -> str:
    labels = {
        "excluded_extra_zip_invoice": "zip 中存在，但不属于当前已确认 ETC 对账任务。",
        "ambiguous_zip_match": "zip 中有多张发票命中同一对账需求，需要人工处理后再导入。",
        "not_in_reconciliation_preview": "未进入本次 ETC 对账任务筛选结果。",
    }
    return labels.get(filter_status, "")


def _preview_fingerprint(
    *,
    task: Any,
    uploads: list[UploadedEtcZipFile],
    payload: dict[str, Any],
    reconciliation_preview: EtcZipFilterPreview,
) -> str:
    canonical = {
        "task_id": str(task.task_id),
        "task_version": int(task.version),
        "confirmed_item_set_hash": str(task.confirmed_item_set_hash or ""),
        "zip_preview_generation": int(getattr(task, "zip_preview_generation", 0) or 0),
        "uploads": [
            {
                "file_name": upload.file_name,
                "sha256": hashlib.sha256(upload.content).hexdigest(),
                "size_bytes": len(upload.content),
            }
            for upload in uploads
        ],
        "summary": payload.get("summary"),
        "audit": payload.get("audit"),
        "items": [
            {
                "fileName": item.get("fileName"),
                "invoiceNumber": item.get("invoiceNumber"),
                "status": item.get("status"),
                "filterStatus": item.get("filterStatus"),
                "requirementId": item.get("requirementId"),
            }
            for item in list(payload.get("items") or [])
            if isinstance(item, dict)
        ],
        "reconciliation_filter": reconciliation_preview.to_payload(),
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
