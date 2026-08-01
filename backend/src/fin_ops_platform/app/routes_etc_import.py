from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.etc_service import EtcImportPreviewStaleError, EtcServiceError, UploadedEtcZipFile
from fin_ops_platform.services.etc_reconciliation_zip_filter import StaleReconciliationPreviewError


class EtcImportApiRoutes:
    def __init__(
        self,
        *,
        preview_service: Any,
        background_job_service: Any,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        load_multipart_body: Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]],
        reconciliation_error_response: Callable[[ValueError], Any],
        enqueue_import_job: Callable[..., tuple[Any, Any]],
        serialize_import_job: Callable[[Any], dict[str, Any]],
    ) -> None:
        self._preview_service = preview_service
        self._background_job_service = background_job_service
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._reconciliation_error_response = reconciliation_error_response
        self._enqueue_import_job = enqueue_import_job
        self._serialize_import_job = serialize_import_job

    def route(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        actor_id: str,
    ) -> Any:
        if method == "POST" and route_path == "/api/etc/import/preview":
            return self.preview(body, headers)
        if method == "POST" and route_path == "/api/etc/import/confirm":
            return self.confirm(body, owner_user_id=actor_id)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_import_route"})

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
            payload = self._preview_service.preview(task_id=task_id, uploads=uploads)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except RuntimeError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "etc_import_storage_unavailable", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def confirm(self, body: str | bytes | None, *, owner_user_id: str) -> Any:
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
        idempotency_key = f"etc_import_session:{normalized_session_id}"
        existing_job = self._background_job_service.get_reusable_idempotent_job(owner_user_id, idempotency_key)
        if existing_job is not None:
            return self._json_response(HTTPStatus.ACCEPTED, {"job": existing_job.to_payload()})
        try:
            validated_preview = self._preview_service.validate(
                session_id=normalized_session_id,
                task_id=normalized_task_id,
            )
            total = validated_preview.item_total
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "etc_import_session_not_found", "message": "ETC import session not found."},
            )
        except EtcImportPreviewStaleError as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "preview_stale", "message": str(error)})
        except StaleReconciliationPreviewError as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "stale_reconciliation_task_preview", "message": str(error)})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except EtcServiceError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_import_session_not_found", "message": str(error)})

        effective_task_version = int(validated_preview.session.task_version)
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
                        "confirmed_item_set_hash": validated_preview.session.confirmed_item_set_hash,
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
            self._preview_service.mark_status(
                normalized_session_id,
                status="failed",
                imported_by=owner_user_id,
                last_error=str(exc),
            )
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "import_queue_unavailable", "message": str(exc), "job": job.to_payload()},
            )
