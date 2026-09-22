from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.etc_import_session_store import (
    EtcImportSessionStorePort,
    StoredEtcImportSession,
    StoredEtcImportUpload,
)
from fin_ops_platform.services.etc_reconciliation_zip_filter import (
    EtcZipFilterItem,
    EtcZipFilterPreview,
    StaleReconciliationPreviewError,
    filter_manifest_by_allowlist,
    preview_etc_zip_for_task,
    validate_etc_zip_confirm_for_task,
)
from fin_ops_platform.services.etc_service import (
    EtcArchiveManifest,
    EtcImportPreviewStaleError,
    UploadedEtcZipFile,
    build_etc_archive_manifest,
)


@dataclass(frozen=True, slots=True)
class ValidatedEtcImportPreview:
    session: StoredEtcImportSession
    uploads: tuple[UploadedEtcZipFile, ...]
    item_total: int
    manifest: EtcArchiveManifest | None = None


class EtcImportPreviewService:
    def __init__(self, *, etc_service: Any, task_service: Any, session_store: EtcImportSessionStorePort) -> None:
        self._etc_service = etc_service
        self._task_service = task_service
        self._session_store = session_store

    def register(self, *, task_id: str, uploads: list[UploadedEtcZipFile], imported_by: str, register_job: Any = None) -> StoredEtcImportSession:
        task = self._task_service.get_task(task_id)
        if str(getattr(task.status, "value", task.status)) != "ready_for_import":
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        session = StoredEtcImportSession(
            session_id=uuid4().hex, status="preparing", task_id=task_id, task_version=int(task.version),
            zip_preview_generation=int(task.zip_preview_generation or 0),
            confirmed_item_set_hash=str(task.confirmed_item_set_hash or ""),
            preview_fingerprint="", preview_result={}, preview_audit={}, preview_files=[], reconciliation_filter={},
            uploads=tuple(StoredEtcImportUpload(
                file_id=f"etc-import-{index + 1:04d}", file_name=upload.file_name,
                content=bytes(upload.content), sha256=hashlib.sha256(upload.content).hexdigest(),
                size_bytes=len(upload.content), ordinal=index,
            ) for index, upload in enumerate(uploads)),
            imported_by=imported_by,
        )
        return self._session_store.save_preview(session, on_saved=register_job)

    def preview(self, *, task_id: str, uploads: list[UploadedEtcZipFile], imported_by: str) -> dict[str, Any]:
        session = self.register(task_id=task_id, uploads=uploads, imported_by=imported_by)
        return self.prepare(session_id=session.session_id, imported_by=imported_by)

    def prepare(self, *, session_id: str, imported_by: str, completion: Any = None) -> dict[str, Any]:
        from fin_ops_platform.services.etc_import_manifest import encode_manifest

        session = self._session_store.get(session_id)
        if session is None:
            raise KeyError("etc_import_session_not_found")
        if session.imported_by != imported_by:
            raise PermissionError("ETC import session belongs to another user")
        task = self._task_service.get_task(session.task_id)
        if str(getattr(task.status, "value", task.status)) != "ready_for_import":
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        uploads = [UploadedEtcZipFile(upload.file_name, upload.content) for upload in session.uploads]
        for stored in session.uploads:
            if len(stored.content) != stored.size_bytes or hashlib.sha256(stored.content).hexdigest() != stored.sha256:
                raise EtcImportPreviewStaleError("ETC archive identity changed.")
        payload, reconciliation_preview, manifest = self._build_preview(task=task, uploads=uploads)
        updated = replace(
            session, task_version=int(task.version),
            confirmed_item_set_hash=str(task.confirmed_item_set_hash or ""),
            zip_preview_generation=int(task.zip_preview_generation or 0),
            status="preview_ready", preview_result=payload, preview_audit=dict(payload["audit"]),
            preview_files=list(payload["files"]), reconciliation_filter=reconciliation_preview.to_payload(),
            preview_fingerprint=_preview_fingerprint(task=task, uploads=uploads, payload=payload,
                                                     reconciliation_preview=reconciliation_preview),
            prepared_manifest=encode_manifest(manifest), prepared_manifest_ref=None,
        )
        result = {**payload, "sessionId": session_id}
        def finish(transaction: Any, _session: StoredEtcImportSession) -> None:
            completion.lock(transaction)
            completion.preview(transaction, {"preview": result}, status=("needs_review" if reconciliation_preview.blocking_issues
                                                           else "awaiting_confirmation"))
        self._session_store.save_preview(updated, on_saved=finish if completion is not None else None)
        return result

    @staticmethod
    def _assert_task_version(task: Any, session: StoredEtcImportSession) -> None:
        if (int(task.version) != session.task_version
                or str(task.confirmed_item_set_hash or "") != session.confirmed_item_set_hash
                or int(task.zip_preview_generation or 0) != session.zip_preview_generation):
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")

    def validate(self, *, session_id: str, task_id: str, imported_by: str,
                 load_manifest: bool = False, authorized_job=None) -> ValidatedEtcImportPreview:
        from fin_ops_platform.services.etc_import_manifest import decode_manifest

        session = self._session_store.get(session_id, load_uploads=False, load_manifest=load_manifest)
        if session is None:
            raise KeyError("etc_import_session_not_found")
        from fin_ops_platform.services.import_workflow_service import assert_import_session_access
        assert_import_session_access(session_id=session_id, creator=session.imported_by,
                                     actor=imported_by, job=authorized_job)
        if session.task_id != task_id or session.status not in {"preview_ready", "queued", "processing", "failed"}:
            raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
        task = self._task_service.get_task(task_id)
        self._assert_task_version(task, session)
        if not session.prepared_manifest_ref and session.prepared_manifest is None:
            raise EtcImportPreviewStaleError("ETC preview has no prepared manifest; prepare a new preview.")
        value = session.reconciliation_filter
        preview = EtcZipFilterPreview(
            task_id=value["taskId"], task_version=value["taskVersion"],
            confirmed_item_set_hash=value["confirmedItemSetHash"],
            allowed_invoice_numbers=list(value["allowedInvoiceNumbers"]),
            blocking_issues=list(value["blockingIssues"]),
            items=[EtcZipFilterItem(file_name=item["fileName"], invoice_number=item["invoiceNumber"],
                                   filter_status=item["filterStatus"], requirement_id=item.get("requirementId"),
                                   message=item.get("message", "")) for item in value["items"]],
        )
        validate_etc_zip_confirm_for_task(task=task, preview=preview)
        manifest = decode_manifest(session.prepared_manifest) if load_manifest and session.prepared_manifest else None
        uploads = tuple(UploadedEtcZipFile(file.source_name, b"") for file in manifest.files) if manifest else ()
        return ValidatedEtcImportPreview(
            session=session, uploads=uploads, manifest=manifest,
            item_total=len(set(preview.allowed_invoice_numbers)),
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

    def discard(self, *, session_id: str, imported_by: str, on_discard: Any = None, authorized_job=None) -> None:
        self._session_store.discard_preview(session_id, imported_by=imported_by, on_discard=on_discard, authorized_job=authorized_job)

    def _build_preview(
        self,
        *,
        task: Any,
        uploads: list[UploadedEtcZipFile],
    ) -> tuple[dict[str, Any], EtcZipFilterPreview, EtcArchiveManifest]:
        manifest = build_etc_archive_manifest(uploads)
        self._etc_service.load_import_candidates(sorted({entry.parsed_invoice.invoice_number
            for file in manifest.files for entry in file.entries if entry.parsed_invoice is not None}))
        reconciliation_preview = preview_etc_zip_for_task(task=task, uploads=uploads, manifest=manifest)
        filtered_manifest = filter_manifest_by_allowlist(
            manifest=manifest,
            allowed_invoice_numbers=reconciliation_preview.allowed_invoice_numbers,
        )
        filtered_uploads = [UploadedEtcZipFile(file.source_name, b"") for file in filtered_manifest.files]
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
        return payload, reconciliation_preview, filtered_manifest


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
