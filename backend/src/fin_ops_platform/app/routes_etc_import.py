from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.etc_service import (
    EtcImportPreviewStaleError,
    EtcServiceError,
    UploadedEtcZipFile,
)
from fin_ops_platform.services.etc_reconciliation_zip_filter import (
    EtcZipFilterPreview,
    StaleReconciliationPreviewError,
    filter_uploads_by_allowlist,
    preview_etc_zip_for_task,
    validate_etc_zip_confirm_for_task,
)


class EtcImportApiRoutes:
    def __init__(
        self,
        *,
        etc_service: Any,
        task_service: Any,
        background_job_service: Any,
        reconciliation_import_previews: dict[str, EtcZipFilterPreview],
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        load_multipart_body: Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]],
        reconciliation_error_response: Callable[[ValueError], Any],
        resolve_background_job_owner: Callable[[dict[str, str] | None], str],
        import_job_processing_enabled: Callable[[], bool],
        enqueue_import_job: Callable[..., tuple[Any, Any]],
        serialize_import_job: Callable[[Any], dict[str, Any]],
        execute_etc_invoice_import_confirm_job: Callable[..., dict[str, object]],
    ) -> None:
        self._etc_service = etc_service
        self._task_service = task_service
        self._background_job_service = background_job_service
        self._reconciliation_import_previews = reconciliation_import_previews
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._reconciliation_error_response = reconciliation_error_response
        self._resolve_background_job_owner = resolve_background_job_owner
        self._import_job_processing_enabled = import_job_processing_enabled
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job
        self._execute_etc_invoice_import_confirm_job = execute_etc_invoice_import_confirm_job

    def route(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        if method == "POST" and route_path == "/api/etc/import/preview":
            return self.preview(body, headers)
        if method == "POST" and route_path == "/api/etc/import/confirm":
            return self.confirm(body, headers)
        if method == "POST" and route_path == "/api/etc/import":
            return self.direct_import_removed()
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_import_route"})

    def direct_import_removed(self) -> Any:
        return self._json_response(
            HTTPStatus.GONE,
            {
                "error": "etc_direct_import_removed",
                "message": "Use /api/etc/import/preview and /api/etc/import/confirm.",
            },
        )

    def preview(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "At least one zip file is required."},
            )
        invalid_files = [file.file_name for file in files if not file.file_name.lower().endswith(".zip")]
        if invalid_files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "Only .zip files can be imported."},
            )
        uploads = [UploadedEtcZipFile(file_name=file.file_name, content=file.content) for file in files]
        task_id = (fields.get("task_id") or fields.get("taskId") or [""])[0].strip()
        if not task_id:
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "task_id_required", "message": "task_id is required."})
        try:
            task = self._task_service.get_task(task_id)
            reconciliation_preview = preview_etc_zip_for_task(task=task, uploads=uploads)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        filtered_uploads = filter_uploads_by_allowlist(
            uploads=uploads,
            allowed_invoice_numbers=reconciliation_preview.allowed_invoice_numbers,
        )
        payload = self._etc_service.preview_import_zips(filtered_uploads)
        full_result, full_audit, full_file_audits = self._etc_service.inspect_import_zips(uploads)
        payload["importAudit"] = payload.get("audit")
        payload["importFiles"] = payload.get("files", [])
        payload["audit"] = full_audit.to_payload()
        payload["files"] = full_file_audits
        payload["items"] = self._preview_items_with_filter_status(
            full_result.items,
            reconciliation_preview,
        )
        session_id = str(payload.get("sessionId") or "")
        if session_id:
            self._reconciliation_import_previews[session_id] = reconciliation_preview
        payload["taskId"] = task_id
        payload["reconciliationFilter"] = reconciliation_preview.to_payload()
        return self._json_response(HTTPStatus.OK, payload)

    def confirm(self, body: str | bytes | None, headers: dict[str, str] | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("sessionId")
        task_id = payload.get("taskId") or payload.get("task_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "sessionId is required."},
            )
        normalized_session_id = session_id.strip()
        if not isinstance(task_id, str) or not task_id.strip():
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": "task_id_required", "message": "task_id is required."})
        normalized_task_id = task_id.strip()
        owner_user_id = self._resolve_background_job_owner(headers)
        idempotency_key = f"etc_import_session:{normalized_session_id}"
        existing_job = self._background_job_service.get_reusable_idempotent_job(owner_user_id, idempotency_key)
        if existing_job is not None:
            return self._json_response(HTTPStatus.ACCEPTED, {"job": existing_job.to_payload()})
        try:
            task = self._task_service.get_task(normalized_task_id)
            reconciliation_preview = self._reconciliation_import_previews.get(normalized_session_id)
            if reconciliation_preview is None:
                raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
            total = self._etc_service.get_import_session_item_total(normalized_session_id)
            self._etc_service.validate_import_session_preview_fresh(normalized_session_id)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except EtcImportPreviewStaleError as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "preview_stale", "message": str(error)})
        except StaleReconciliationPreviewError as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "stale_reconciliation_task_preview", "message": str(error)})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except EtcServiceError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_import_session_not_found", "message": str(error)})

        try:
            validate_etc_zip_confirm_for_task(task=task, preview=reconciliation_preview)
        except (StaleReconciliationPreviewError, EtcImportPreviewStaleError) as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "stale_reconciliation_task_preview", "message": str(error)})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        effective_task_version = int(getattr(task, "version", reconciliation_preview.task_version))
        initial_summary = {
            "created": 0,
            "imported": 0,
            "updated": 0,
            "attachments_completed": 0,
            "duplicates": 0,
            "failed": 0,
            "total": total,
        }
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="etc_invoice_import",
            label="导入 ETC发票",
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
            phase="queued",
            current=0,
            total=total,
            message="ETC发票导入任务已创建。",
            result_summary=initial_summary,
            source={
                "session_id": normalized_session_id,
                "task_id": normalized_task_id,
                "affected_domains": ["imports_etc_invoices", "etc_tickets"],
                "route": "/imports/etc-invoices",
            },
            affected_scopes=["etc_invoices", "imports", "workbench"],
        )
        if not created:
            return self._json_response(HTTPStatus.ACCEPTED, {"job": job.to_payload()})
        try:
            self._task_service.begin_import(
                task_id=normalized_task_id,
                task_version=effective_task_version,
                confirmed_item_set_hash=reconciliation_preview.confirmed_item_set_hash,
                import_session_id=normalized_session_id,
                actor=owner_user_id,
            )
        except ValueError as error:
            self._background_job_service.fail_job(job.job_id, "ETC发票导入任务未启动。", str(error))
            return self._reconciliation_error_response(error)

        if self._import_job_processing_enabled():
            try:
                import_job, event = self._enqueue_import_job(
                    import_type="etc_invoice_import.confirm",
                    import_session_id=normalized_session_id,
                    idempotency_key=f"etc_invoice_import.confirm:{normalized_task_id}:{normalized_session_id}",
                    payload={
                        "session_id": normalized_session_id,
                        "task_id": normalized_task_id,
                        "owner_user_id": owner_user_id,
                        "background_job_id": job.job_id,
                        "task_version": effective_task_version,
                        "confirmed_item_set_hash": reconciliation_preview.confirmed_item_set_hash,
                        "total": total,
                    },
                    created_by=owner_user_id,
                    reason="etc_invoice_import_confirm",
                )
                job_payload = job.to_payload()
                job_payload["import_job"] = self._serialize_import_job(import_job)
                job_payload["event_id"] = getattr(event, "event_id", None)
                return self._json_response(HTTPStatus.ACCEPTED, {"job": job_payload})
            except RuntimeError as exc:
                self._background_job_service.fail_job(job.job_id, "ETC发票导入任务未启动。", str(exc))
                return self._json_response(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "import_queue_unavailable", "message": str(exc), "job": job.to_payload()},
                )

        def run_etc_import(running_job):
            return self._execute_etc_invoice_import_confirm_job(
                session_id=normalized_session_id,
                task_id=normalized_task_id,
                owner_user_id=owner_user_id,
                background_job_id=running_job.job_id,
                task_version=effective_task_version,
                confirmed_item_set_hash=reconciliation_preview.confirmed_item_set_hash,
                total=total,
            )

        self._background_job_service.run_job(job, run_etc_import)
        return self._json_response(
            HTTPStatus.ACCEPTED,
            {"job": job.to_payload()},
        )

    @staticmethod
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
                item_payload["message"] = _etc_zip_filter_status_message(filter_status)
            decorated.append(item_payload)
        return decorated


def _etc_zip_filter_status_message(filter_status: str) -> str:
    labels = {
        "excluded_extra_zip_invoice": "zip 中存在，但不属于当前已确认 ETC 对账任务。",
        "ambiguous_zip_match": "zip 中有多张发票命中同一对账需求，需要人工处理后再导入。",
        "duplicate_requirement_invoice_match": "同一张发票命中多个对账需求，需要人工处理后再导入。",
        "not_in_reconciliation_preview": "未进入本次 ETC 对账任务筛选结果。",
    }
    return labels.get(filter_status, "")
