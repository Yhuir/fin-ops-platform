from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.etc_reconciliation_zip_filter import StaleReconciliationPreviewError
from fin_ops_platform.services.etc_service import EtcImportPreviewStaleError, EtcServiceError, UploadedEtcZipFile
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.import_workflow_service import import_job_payload, upload_request_descriptor


class EtcImportApiRoutes:
    def __init__(
        self,
        *,
        preview_service: Any,
        workflow_provider: Callable[[], Any],
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        load_multipart_body: Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]],
        reconciliation_error_response: Callable[[ValueError], Any],
    ) -> None:
        self._preview_service = preview_service
        self._workflow_provider = workflow_provider
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._reconciliation_error_response = reconciliation_error_response

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
            return self.preview(body, headers, owner_user_id=actor_id)
        if method == "POST" and route_path == "/api/etc/import/confirm":
            return self.confirm(body, owner_user_id=actor_id)
        if method == "POST" and route_path == "/api/etc/import/discard":
            return self.discard(body, owner_user_id=actor_id)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_etc_import_route"})

    def preview(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        owner_user_id: str,
    ) -> Any:
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
            workflow = self._workflow_provider()
            request_id = (fields.get("request_id") or [str(uuid4())])[0]
            key = f"etc_import.upload:{owner_user_id}:{request_id}"
            existing = workflow.repository.get_by_idempotency_key(key, created_by=owner_user_id)
            descriptor = upload_request_descriptor(uploads)
            if existing is not None:
                if existing.payload.get("upload_manifest") != descriptor or existing.payload.get("task_id") != task_id:
                    raise ImportJobIdempotencyConflict("同一上传请求的文件或对账任务不同。")
                return self._json_response(HTTPStatus.ACCEPTED, {"job": import_job_payload(existing)})
            jobs = []
            def register_job(transaction, session):
                registered = workflow.repository.create_or_get_job(
                    import_type="etc_invoice_import.confirm", import_session_id=session.session_id,
                    idempotency_key=key, created_by=owner_user_id, stage="prepare", transaction=transaction,
                    payload={"session_id": session.session_id, "task_id": task_id,
                             "upload_manifest": descriptor,
                             "owner_user_id": owner_user_id, **workflow.command_context(owner_user_id), "route": "/imports/etc-invoices",
                             "affected_domains": ["imports_etc_invoices", "etc_tickets"]},
                )
                if registered.import_session_id != session.session_id:
                    raise ImportJobIdempotencyConflict("上传请求已经登记。")
                jobs.append(registered)
            self._preview_service.register(task_id=task_id, uploads=uploads,
                                           imported_by=owner_user_id, register_job=register_job)
            payload = {"job": import_job_payload(jobs[0])}
        except ImportJobIdempotencyConflict as error:
            existing = workflow.repository.get_by_idempotency_key(key, created_by=owner_user_id)
            if (existing is not None and existing.payload.get("upload_manifest") == descriptor
                    and existing.payload.get("task_id") == task_id):
                return self._json_response(HTTPStatus.ACCEPTED, {"job": import_job_payload(existing)})
            return self._json_response(HTTPStatus.CONFLICT, {"error": "idempotency_conflict", "message": str(error)})
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        except RuntimeError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "etc_import_storage_unavailable", "message": str(error)},
            )
        return self._json_response(HTTPStatus.ACCEPTED, payload)

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
        workflow = self._workflow_provider()
        try:
            existing = workflow.session_job(normalized_session_id, owner_user_id, "etc_invoice_import.confirm")
            if existing is not None and existing.stage == "commit":
                if existing.payload.get("task_id") != normalized_task_id:
                    raise ImportJobIdempotencyConflict("导入任务与对账批次不一致。")
                job = workflow.retry(existing.import_job_id, owner_user_id)
                return self._json_response(HTTPStatus.ACCEPTED, {"job": import_job_payload(job)})
            validated = self._preview_service.validate(
                session_id=normalized_session_id, task_id=normalized_task_id, imported_by=owner_user_id, authorized_job=existing,
            )
            job = workflow.confirm(
                session_id=normalized_session_id, owner=owner_user_id,
                import_type="etc_invoice_import.confirm", expected_version=payload.get("preview_version"),
                payload={"session_id": normalized_session_id, "task_id": normalized_task_id,
                         "owner_user_id": owner_user_id, "task_version": int(validated.session.task_version),
                         "confirmed_item_set_hash": validated.session.confirmed_item_set_hash,
                         "total": validated.item_total, "route": "/imports/etc-invoices",
                         "affected_domains": ["imports_etc_invoices", "etc_tickets"]},
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_import_session_not_found", "message": "ETC 导入会话不存在。"})
        except PermissionError as error:
            return self._json_response(HTTPStatus.FORBIDDEN, {"error": "etc_import_session_forbidden", "message": str(error)})
        except (EtcImportPreviewStaleError, StaleReconciliationPreviewError, ImportJobIdempotencyConflict) as error:
            if isinstance(error, (EtcImportPreviewStaleError, StaleReconciliationPreviewError)):
                current_job = workflow.session_job(normalized_session_id, owner_user_id, "etc_invoice_import.confirm")
                if current_job is not None and current_job.status == "awaiting_confirmation":
                    try:
                        workflow.repository.mark_preview_needs_review(current_job.import_job_id, expected_version=current_job.version)
                    except ImportJobIdempotencyConflict:
                        # A concurrent command already advanced this exact version.
                        pass
            return self._json_response(HTTPStatus.CONFLICT, {"error": "preview_stale", "message": str(error)})
        except ValueError as error:
            return self._json_response(HTTPStatus.CONFLICT, {"error": "invalid_import_confirmation", "message": str(error)})
        except EtcServiceError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_import_session_not_found", "message": str(error)})
        except RuntimeError as error:
            return self._json_response(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "import_queue_unavailable", "message": str(error)})
        return self._json_response(HTTPStatus.ACCEPTED, {"job": import_job_payload(job)})

    def discard(self, body: str | bytes | None, *, owner_user_id: str) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("sessionId") or payload.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "sessionId is required."},
            )
        normalized_session_id = session_id.strip()
        try:
            workflow = self._workflow_provider()
            job = workflow.session_job(normalized_session_id, owner_user_id, "etc_invoice_import.confirm")
            def cancel(transaction):
                if job is not None and job.status != "canceled":
                    workflow.repository.cancel_job(job.import_job_id, created_by=job.created_by, transaction=transaction)
            self._preview_service.discard(
                session_id=normalized_session_id, imported_by=owner_user_id, on_discard=cancel, authorized_job=job,
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "etc_import_session_not_found", "message": "ETC import session not found."},
            )
        except PermissionError as error:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "etc_import_session_forbidden", "message": str(error)},
            )
        except ValueError as error:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "etc_import_session_not_discardable", "message": str(error)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"sessionId": normalized_session_id, "status": "reverted"},
        )
