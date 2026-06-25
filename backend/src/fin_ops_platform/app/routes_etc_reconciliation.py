from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import unquote

from fin_ops_platform.services.etc_service import EtcBatchDeleteError, EtcBatchNotFoundError
from fin_ops_platform.services.etc_reconciliation_import_cleanup_service import EtcReconciliationImportCleanupService
from fin_ops_platform.services.etc_reconciliation_models import SourceFileKind
from fin_ops_platform.services.object_storage import ObjectStorageWriteError


class EtcReconciliationTaskApiRoutes:
    def __init__(
        self,
        *,
        task_service: Any,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any],
        load_json_body: Callable[[str | bytes | None], tuple[dict[str, Any], Any | None]],
        load_multipart_body: Callable[[str | bytes | None, dict[str, str] | None], tuple[dict[str, list[str]], list[Any], Any | None]],
        task_payload: Callable[[Any], dict[str, Any]],
        unavailable_task_payload: Callable[[Any], dict[str, Any]],
        cleanup_service: EtcReconciliationImportCleanupService,
        expected_version_from_payload: Callable[[dict[str, object]], int],
        expected_version_from_fields: Callable[[dict[str, list[str]]], int],
        reconciliation_error_response: Callable[[ValueError], Any],
        reconciliation_storage_error_response: Callable[[ObjectStorageWriteError], Any],
        refresh_after_etc_invoice_link: Callable[[list[str], str], None],
        persist_state: Callable[[], None],
        upload_source: Callable[..., Any],
        submit_ticket_root_texts: Callable[[str, str | bytes | None], Any],
    ) -> None:
        self._task_service = task_service
        self._json_response = json_response
        self._load_json_body = load_json_body
        self._load_multipart_body = load_multipart_body
        self._task_payload = task_payload
        self._unavailable_task_payload = unavailable_task_payload
        self._cleanup_service = cleanup_service
        self._expected_version_from_payload = expected_version_from_payload
        self._expected_version_from_fields = expected_version_from_fields
        self._reconciliation_error_response = reconciliation_error_response
        self._reconciliation_storage_error_response = reconciliation_storage_error_response
        self._refresh_after_etc_invoice_link = refresh_after_etc_invoice_link
        self._persist_state = persist_state
        self._upload_source = upload_source
        self._submit_ticket_root_texts = submit_ticket_root_texts

    def route(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        if method == "GET" and route_path == "/api/etc/reconciliation-tasks/ready-for-import":
            return self.ready_for_import()
        if method == "GET" and route_path == "/api/etc/reconciliation-tasks":
            return self.list_tasks()
        if method == "POST" and route_path == "/api/etc/reconciliation-tasks":
            return self.create_task(body)
        if route_path.startswith("/api/etc/reconciliation-tasks/"):
            return self.route_task(method, route_path, body, headers)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task_route"})

    def list_tasks(self) -> Any:
        return self._json_response(
            HTTPStatus.OK,
            {"tasks": [self._task_payload(task) for task in self._task_service.list_tasks()]},
        )

    def ready_for_import(self) -> Any:
        ready_tasks = self._task_service.list_ready_for_import_tasks()
        unavailable_tasks = [
            task
            for task in self._task_service.list_tasks()
            if getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")) != "ready_for_import"
        ]
        return self._json_response(
            HTTPStatus.OK,
            {
                "tasks": [self._task_payload(task) for task in ready_tasks],
                "unavailableTasks": [self._unavailable_task_payload(task) for task in unavailable_tasks],
            },
        )

    def create_task(self, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        task = self._task_service.create_task(
            title=str(payload.get("title") or "").strip(),
            created_by=str(payload.get("createdBy") or payload.get("created_by") or "web_finance_user"),
        )
        return self._json_response(HTTPStatus.CREATED, self._task_payload(task))

    def route_task(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        relative = route_path.removeprefix("/api/etc/reconciliation-tasks/").strip("/")
        parts = [unquote(part) for part in relative.split("/") if part]
        if not parts:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        task_id = parts[0]
        if method == "GET" and len(parts) == 1:
            return self.detail(task_id)
        if method == "DELETE" and len(parts) == 1:
            return self.delete_task(task_id, body)
        if method == "DELETE" and len(parts) == 3 and parts[1] == "source-files":
            return self.delete_source_file(task_id, parts[2], body)
        if method == "POST" and len(parts) == 2 and parts[1] == "credit-card-statement":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.CREDIT_CARD_STATEMENT,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 2 and parts[1] == "ticket-root-files":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 2 and parts[1] == "ticket-root-texts":
            return self._submit_ticket_root_texts(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "supplement-evidences":
            return self._upload_source(
                task_id=task_id,
                source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
                body=body,
                headers=headers,
            )
        if method == "POST" and len(parts) == 3 and parts[1] == "supplement-evidences":
            return self.upload_supplement_for_card(
                task_id=task_id,
                item_id=parts[2],
                body=body,
                headers=headers,
            )
        if method == "PATCH" and len(parts) == 3 and parts[1] == "items":
            return self.patch_item(task_id, parts[2], body)
        if method == "POST" and len(parts) == 2 and parts[1] == "confirm":
            return self.confirm_task(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "reopen":
            return self.reopen_task(task_id, body)
        if method == "POST" and len(parts) == 2 and parts[1] == "refresh-matches":
            return self.refresh_matches(task_id)
        if method == "DELETE" and len(parts) == 2 and parts[1] == "imported-invoices":
            return self.delete_imported_invoices(task_id, body)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task_route"})

    def detail(self, task_id: str) -> Any:
        try:
            task = self._task_service.get_task(task_id)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def delete_imported_invoices(self, task_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            expected_version = self._expected_version_from_payload(payload)
            task = self._task_service.get_task(task_id)
            cleanup_result = self._cleanup_service.remove_imported_invoices(
                task=task,
                expected_version=expected_version,
                actor=str(payload.get("actor") or "web_finance_user"),
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        except EtcBatchDeleteError as error:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "etc_batch_delete_conflict", "message": str(error)},
            )
        except ValueError as error:
            return self._reconciliation_error_response(error)
        self._refresh_after_etc_invoice_link(
            cleanup_result.changed_months,
            "etc_reconciliation_imported_invoices_removed",
        )
        self._persist_state()
        response_payload = self._task_payload(cleanup_result.updated_task)
        response_payload["removedImportBatch"] = cleanup_result.delete_result
        response_payload["removedCanonicalInvoiceCount"] = cleanup_result.canonical_deleted
        return self._json_response(HTTPStatus.OK, response_payload)

    def delete_task(self, task_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        cleanup_result = None
        try:
            expected_version = self._expected_version_from_payload(payload)
            actor = str(payload.get("actor") or "web_finance_user")
            task = self._task_service.get_task(task_id)
            if int(getattr(task, "version", 0) or 0) != expected_version:
                raise ValueError("task_version_conflict")
            if str(getattr(task, "import_batch_id", "") or "").strip():
                cleanup_result = self._cleanup_service.cleanup_task_import_sources(
                    task=task,
                    actor=actor,
                )
                task = cleanup_result.task
            result = self._task_service.delete_task(
                task_id=task_id,
                expected_version=int(getattr(task, "version", expected_version) or expected_version),
                actor=actor,
                import_cleanup_confirmed=(
                    cleanup_result is not None
                    and (
                        cleanup_result.removed_import_batch is not None
                        or cleanup_result.removed_submission_batch is not None
                    )
                ),
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        except EtcBatchDeleteError as error:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "etc_batch_delete_conflict", "message": str(error)},
            )
        except ValueError as error:
            return self._reconciliation_error_response(error)
        if cleanup_result is not None and cleanup_result.removed_import_batch is not None:
            self._refresh_after_etc_invoice_link(cleanup_result.changed_months, "etc_reconciliation_task_deleted")
            self._persist_state()
        return self._json_response(HTTPStatus.OK, result)

    def upload_supplement_for_card(
        self,
        *,
        task_id: str,
        item_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Any:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_reconciliation_upload", "message": "file is required."},
            )
        actor = (fields.get("actor") or ["web_finance_user"])[0]
        try:
            expected_version = self._expected_version_from_fields(fields)
            task = self._task_service.upload_supplement_evidences_for_card(
                task_id=task_id,
                item_id=item_id,
                expected_version=expected_version,
                actor=actor,
                files=[
                    {
                        "original_name": upload.file_name,
                        "content_type": "application/octet-stream",
                        "content": upload.content,
                    }
                    for upload in files
                ],
                note=(fields.get("note") or fields.get("reviewNote") or fields.get("reason") or [""])[0],
                evidence_kind_override=(fields.get("evidenceKind") or [None])[0],
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ObjectStorageWriteError as error:
            return self._reconciliation_storage_error_response(error)
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def delete_source_file(self, task_id: str, file_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            expected_version = self._expected_version_from_payload(payload)
            task = self._task_service.delete_source_file(
                task_id=task_id,
                file_id=file_id,
                expected_version=expected_version,
                actor=str(payload.get("actor") or "web_finance_user"),
            )
        except KeyError as error:
            code = str(error).strip("'") or "unknown_source_file"
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": code, "message": code})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def patch_item(self, task_id: str, item_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            expected_version = self._expected_version_from_payload(payload)
            task = self._task_service.patch_item(
                task_id=task_id,
                item_id=item_id,
                expected_version=expected_version,
                actor=str(payload.get("actor") or "web_finance_user"),
                payload=payload,
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def confirm_task(self, task_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            expected_version = self._expected_version_from_payload(payload)
            confirmed_ids_payload = payload.get(
                "confirmedCreditCardItemIds",
                payload.get("confirmed_credit_card_item_ids"),
            )
            if confirmed_ids_payload is not None and not isinstance(confirmed_ids_payload, list):
                raise ValueError("invalid_confirmed_credit_card_item_ids")
            task = self._task_service.confirm_task(
                task_id=task_id,
                expected_version=expected_version,
                actor=str(payload.get("actor") or "web_finance_user"),
                approved_delta=payload.get("approvedDelta", payload.get("approved_delta")),
                approved_delta_note=payload.get("approvedDeltaNote", payload.get("approved_delta_note")),
                confirmed_credit_card_item_ids=confirmed_ids_payload,
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def reopen_task(self, task_id: str, body: str | bytes | None) -> Any:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            expected_version = self._expected_version_from_payload(payload)
            task = self._task_service.reopen_task(
                task_id=task_id,
                expected_version=expected_version,
                actor=str(payload.get("actor") or "web_finance_user"),
            )
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        except ValueError as error:
            return self._reconciliation_error_response(error)
        return self._json_response(HTTPStatus.OK, self._task_payload(task))

    def refresh_matches(self, task_id: str) -> Any:
        try:
            task = self._task_service.refresh_matches(task_id=task_id)
        except KeyError:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "unknown_reconciliation_task"})
        return self._json_response(HTTPStatus.OK, self._task_payload(task))
